import { Suspense, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Sparkles, Text, useTexture } from '@react-three/drei'
import { BallCollider, CuboidCollider, RigidBody } from '@react-three/rapier'
import * as THREE from 'three'
import { DEFAULT_LEVEL } from '../config/levelConfig.js'
import TextureErrorBoundary from './TextureErrorBoundary.jsx'
import * as sfx from '../audio/sfx.js'

export { computeGeometry, computeRampSegments } from '../config/geometry.js'
import { computeBackstopSegments, computeGeometry, computeRampSegments, POCKET_DEPTH } from '../config/geometry.js'

export const COLORS = {
  lane: '#8b5a2b',
  ramp: '#a06a35',
  backboard: '#20242c',
  pocket: '#0b1120',
  gutter: '#334155',
  ball: '#dc2626',
  outerRing: '#38bdf8',
  middleRing: '#a78bfa',
  innerRing: '#f59e0b',
  apex: '#facc15',
}

// Wood-like contact feel: low bounce, high friction so the ball rolls.
export const WOOD = { friction: 0.9, restitution: 0.25 }

const POCKET_WALL = 0.08
const RIM_SEGMENTS = 10

export function useLevelGeometry(level) {
  return useMemo(() => computeGeometry(level), [level])
}

/**
 * Split the solid backboard into cuboid rectangles around the hole openings.
 * Each hole cuts a square aperture (half-side = hole radius); the round rim
 * colliders inside the aperture make the playable opening circular.
 */
function computeBoardSegments(holes, BOARD) {
  let rects = [{ x0: BOARD.x0, x1: BOARD.x1, y0: BOARD.y0, y1: BOARD.y1 }]
  for (const h of holes) {
    const hx0 = Math.max(h.x - h.r, BOARD.x0)
    const hx1 = Math.min(h.x + h.r, BOARD.x1)
    const hy0 = Math.max(h.y - h.r, BOARD.y0)
    const hy1 = Math.min(h.y + h.r, BOARD.y1)
    const next = []
    for (const r of rects) {
      if (hx1 <= r.x0 || hx0 >= r.x1 || hy1 <= r.y0 || hy0 >= r.y1) {
        next.push(r)
        continue
      }
      if (hx0 > r.x0) next.push({ x0: r.x0, x1: hx0, y0: r.y0, y1: r.y1 })
      if (hx1 < r.x1) next.push({ x0: hx1, x1: r.x1, y0: r.y0, y1: r.y1 })
      const ix0 = Math.max(hx0, r.x0)
      const ix1 = Math.min(hx1, r.x1)
      if (hy0 > r.y0) next.push({ x0: ix0, x1: ix1, y0: r.y0, y1: hy0 })
      if (hy1 < r.y1) next.push({ x0: ix0, x1: ix1, y0: hy1, y1: r.y1 })
    }
    rects = next
  }
  return rects.filter((r) => r.x1 - r.x0 > 0.01 && r.y1 - r.y0 > 0.01)
}

function LaneSurface({ textureUrl, color, roughness }) {
  return (
    <TextureErrorBoundary
      resetKey={textureUrl}
      fallback={<meshStandardMaterial color={color} roughness={roughness} />}
    >
      <Suspense fallback={<meshStandardMaterial color={color} roughness={roughness} />}>
        <LaneMaterial url={textureUrl} color={color} roughness={roughness} />
      </Suspense>
    </TextureErrorBoundary>
  )
}

function LaneMaterial({ url, color, roughness }) {
  const texture = useTexture(url)
  useMemo(() => {
    texture.colorSpace = THREE.SRGBColorSpace
  }, [texture])
  return <meshStandardMaterial map={texture} color={color} roughness={roughness} />
}

/** Floor/ramp material: texture when a lane URL is set, flat color otherwise.
 * Textures render untinted — multiplying by the brown fallback color turned
 * the gunmetal plates to mud. */
function WoodSurface({ textureUrl, color, roughness }) {
  return textureUrl ? (
    <LaneSurface textureUrl={textureUrl} color="#ffffff" roughness={roughness} />
  ) : (
    <meshStandardMaterial color={color} roughness={roughness} />
  )
}

function Lane({ geom, textureUrl }) {
  const { lane, ramp } = geom
  return (
    <group>
      <RigidBody type="fixed" colliders="cuboid" {...WOOD}>
        <mesh position={[0, 0, 0]} receiveShadow>
          <boxGeometry args={[lane.width, lane.thickness, lane.length]} />
          <WoodSurface textureUrl={textureUrl} color={COLORS.lane} roughness={0.8} />
        </mesh>
      </RigidBody>
      {[-1, 1].map((side) => (
        <RigidBody key={side} type="fixed" colliders="cuboid" {...WOOD}>
          <mesh
            position={[(side * (lane.width + 0.4)) / 2, lane.thickness / 2 + 0.1, (ramp.length + ramp.gap) / 2]}
            castShadow
          >
            <boxGeometry args={[0.4, 0.5, lane.length + ramp.length + ramp.gap]} />
            <meshStandardMaterial color={COLORS.gutter} roughness={0.6} />
          </mesh>
        </RigidBody>
      ))}
      {/* Safety floor far below the lane to catch stray balls before the kill-z. */}
      <RigidBody type="fixed" colliders="cuboid">
        <mesh position={[0, -3.2, 4]} visible={false}>
          <boxGeometry args={[30, 0.3, 40]} />
          <meshStandardMaterial />
        </mesh>
      </RigidBody>
    </group>
  )
}

function Ramp({ geom, textureUrl }) {
  const { lane, ramp } = geom
  const segments = useMemo(() => computeRampSegments(lane, ramp), [lane, ramp])
  return (
    <group>
      {segments.map((s, i) => (
        <RigidBody
          key={i}
          type="fixed"
          colliders="cuboid"
          {...WOOD}
          position={s.position}
          rotation={[-s.angle, 0, 0]}
        >
          <mesh castShadow receiveShadow>
            <boxGeometry args={[lane.width, lane.thickness, s.length]} />
            <WoodSurface textureUrl={textureUrl} color={COLORS.ramp} roughness={0.7} />
          </mesh>
        </RigidBody>
      ))}
    </group>
  )
}

/** Backboard built from cuboid segments with real apertures at each hole. */
function Backboard({ geom, targets }) {
  const { backboard, backboardZ, BOARD } = geom
  const segments = useMemo(() => computeBoardSegments(targets, BOARD), [targets, BOARD])
  return (
    <group>
      {segments.map((s, i) => {
        const w = s.x1 - s.x0
        const h = s.y1 - s.y0
        return (
          <RigidBody key={i} type="fixed" colliders="cuboid" {...WOOD}>
            <mesh
              position={[(s.x0 + s.x1) / 2, (s.y0 + s.y1) / 2, backboardZ]}
              castShadow
              receiveShadow
            >
              <boxGeometry args={[w, h, backboard.thickness]} />
              <meshStandardMaterial color={COLORS.backboard} roughness={0.45} metalness={0.35} />
            </mesh>
          </RigidBody>
        )
      })}
    </group>
  )
}

/** Ring of small cuboid colliders forming a physical, bouncy circular rim. */
function RimColliders({ hole, geom, onRimHit }) {
  const { backboard, backboardZ } = geom
  const segments = useMemo(() => {
    const chord = 2 * hole.r * Math.sin(Math.PI / RIM_SEGMENTS) + 0.06
    return Array.from({ length: RIM_SEGMENTS }, (_, i) => {
      const theta = (i / RIM_SEGMENTS) * Math.PI * 2
      return {
        position: [
          hole.x + hole.r * Math.cos(theta),
          hole.y + hole.r * Math.sin(theta),
          backboardZ,
        ],
        rotation: [0, 0, theta + Math.PI / 2],
        args: [chord / 2, 0.07, backboard.thickness],
      }
    })
  }, [hole, backboard, backboardZ])
  return (
    <RigidBody
      type="fixed"
      colliders={false}
      friction={0.6}
      restitution={0.2}
      onCollisionEnter={({ other }) => {
        if (other.rigidBody?.userData?.isSkeeball) onRimHit?.(hole)
      }}
    >
      {segments.map((s, i) => (
        <CuboidCollider key={i} args={s.args} position={s.position} rotation={s.rotation} />
      ))}
    </RigidBody>
  )
}

function ApexBackstop({ hole, geom }) {
  const segments = useMemo(
    () => computeBackstopSegments(hole, geom.boardFaceZ),
    [hole, geom]
  )
  return (
    <RigidBody type="fixed" colliders={false} friction={0.8} restitution={0.08}>
      {segments.map((s, i) => (
        <group key={i}>
          <CuboidCollider args={s.args} position={s.position} rotation={s.rotation} />
          <mesh position={s.position} rotation={s.rotation} castShadow>
            <boxGeometry args={s.args.map((v) => v * 2)} />
            <meshStandardMaterial
              color={COLORS.apex}
              emissive={COLORS.apex}
              emissiveIntensity={0.25}
              metalness={0.5}
              roughness={0.35}
            />
          </mesh>
        </group>
      ))}
    </RigidBody>
  )
}

/**
 * Capture pocket behind a hole: a short walled box tunnel. The ball falls in,
 * rolls to the back, and only then hits the score sensor.
 */
function CapturePocket({ hole, geom, onScore }) {
  const { boardBackZ } = geom
  const half = hole.r + 0.05
  const z0 = boardBackZ
  const z1 = boardBackZ + POCKET_DEPTH
  const zc = (z0 + z1) / 2
  const walls = [
    // floor, ceiling, left, right, back
    { pos: [hole.x, hole.y - half - POCKET_WALL / 2, zc], size: [half * 2 + POCKET_WALL * 2, POCKET_WALL, POCKET_DEPTH] },
    { pos: [hole.x, hole.y + half + POCKET_WALL / 2, zc], size: [half * 2 + POCKET_WALL * 2, POCKET_WALL, POCKET_DEPTH] },
    { pos: [hole.x - half - POCKET_WALL / 2, hole.y, zc], size: [POCKET_WALL, half * 2, POCKET_DEPTH] },
    { pos: [hole.x + half + POCKET_WALL / 2, hole.y, zc], size: [POCKET_WALL, half * 2, POCKET_DEPTH] },
    { pos: [hole.x, hole.y, z1 + POCKET_WALL / 2], size: [half * 2 + POCKET_WALL * 2, half * 2 + POCKET_WALL * 2, POCKET_WALL] },
  ]
  return (
    <group>
      <RigidBody type="fixed" colliders="cuboid" friction={0.7} restitution={0.2}>
        {walls.map((w, i) => (
          <mesh key={i} position={w.pos}>
            <boxGeometry args={w.size} />
            <meshStandardMaterial color={COLORS.pocket} roughness={0.95} />
          </mesh>
        ))}
      </RigidBody>
      {/* Score sensor at the BACK of the pocket. */}
      <RigidBody type="fixed" colliders={false}>
        <BallCollider
          args={[Math.min(hole.r * 0.6, 0.35)]}
          position={[hole.x, hole.y, z1 - 0.25]}
          sensor
          onIntersectionEnter={({ other }) => {
            if (other.rigidBody?.userData?.isSkeeball) onScore(hole)
          }}
        />
      </RigidBody>
    </group>
  )
}

/** Apex rim: emissive intensity breathes so the jackpot holes feel alive. */
function ApexRim({ hole, boardFaceZ }) {
  const mat = useRef()
  useFrame(({ clock }) => {
    if (mat.current) {
      mat.current.emissiveIntensity = 0.9 + Math.sin(clock.elapsedTime * 3.2) * 0.5
    }
  })
  return (
    <mesh position={[hole.x, hole.y, boardFaceZ - 0.02]}>
      <torusGeometry args={[hole.r, 0.06, 20, 48]} />
      <meshStandardMaterial
        ref={mat}
        color={hole.color}
        emissive={hole.color}
        emissiveIntensity={0.9}
        roughness={0.3}
        metalness={0.4}
      />
    </mesh>
  )
}

function ScoreHole({ hole, geom, onScore, onRimHit }) {
  const { boardFaceZ } = geom
  const isApex = hole.points === 300
  return (
    <group>
      {/* Dark disc just inside the aperture so the opening reads as a hole. */}
      <mesh position={[hole.x, hole.y, boardFaceZ + 0.03]}>
        <circleGeometry args={[hole.r, 48]} />
        <meshStandardMaterial color="#020617" roughness={1} />
      </mesh>
      {/* Visible rim ring */}
      {isApex ? (
        <ApexRim hole={hole} boardFaceZ={boardFaceZ} />
      ) : (
        <mesh position={[hole.x, hole.y, boardFaceZ - 0.02]}>
          <torusGeometry args={[hole.r, 0.06, 20, 48]} />
          <meshStandardMaterial
            color={hole.color}
            emissive={hole.color}
            emissiveIntensity={0.35}
            roughness={0.4}
          />
        </mesh>
      )}
      {isApex && (
        <Sparkles
          count={18}
          position={[hole.x, hole.y, boardFaceZ - 0.25]}
          scale={[hole.r * 3, hole.r * 3, 0.5]}
          size={3}
          speed={0.5}
          color={COLORS.apex}
        />
      )}
      {/* Big point value INSIDE the ring, facing the player (rotation flips
          the text plane toward -z — without it the glyphs render mirrored). */}
      <Text
        position={[hole.x, hole.y, boardFaceZ - 0.06]}
        rotation={[0, Math.PI, 0]}
        fontSize={hole.r * 0.8}
        color={isApex ? '#fde047' : '#f1f5f9'}
        anchorX="center"
        anchorY="middle"
        outlineWidth={hole.r * 0.07}
        outlineColor="#0f172a"
      >
        {String(hole.points)}
      </Text>
      {isApex && <ApexBackstop hole={hole} geom={geom} />}
      <RimColliders hole={hole} geom={geom} onRimHit={onRimHit} />
      <CapturePocket hole={hole} geom={geom} onScore={onScore} />
    </group>
  )
}

export function SceneBackground({ url }) {
  const texture = useTexture(url)
  useMemo(() => {
    texture.mapping = THREE.EquirectangularReflectionMapping
    texture.colorSpace = THREE.SRGBColorSpace
  }, [texture])
  return <primitive object={texture} attach="background" />
}

export function BallMaterial({ url }) {
  const texture = useTexture(url)
  useMemo(() => {
    texture.colorSpace = THREE.SRGBColorSpace
  }, [texture])
  return <meshStandardMaterial map={texture} roughness={0.35} />
}

export function BallSurface({ textureUrl }) {
  const fallback = <meshStandardMaterial color={COLORS.ball} roughness={0.35} />
  return textureUrl ? (
    <TextureErrorBoundary resetKey={textureUrl} fallback={fallback}>
      <Suspense fallback={fallback}>
        <BallMaterial url={textureUrl} />
      </Suspense>
    </TextureErrorBoundary>
  ) : (
    fallback
  )
}

/** Static preview ball shown at the start position while aiming. */
export function PreviewBall({ textureUrl, position, radius = 0.45 }) {
  return (
    <mesh position={position} castShadow>
      <sphereGeometry args={[radius, 48, 48]} />
      <BallSurface textureUrl={textureUrl} />
    </mesh>
  )
}

/** Emissive dressing: neon rails along the gutters + a glowing frame around
 * the deck. Pure decor (no colliders) — with bloom these carry the look. */
function ArenaTrim({ geom }) {
  const { lane, ramp } = geom
  const railLength = lane.length + ramp.length + ramp.gap
  const railZ = (ramp.length + ramp.gap) / 2
  const railY = lane.thickness / 2 + 0.38
  return (
    <group>
      {[-1, 1].map((side) => (
        <mesh key={side} position={[(side * (lane.width + 0.4)) / 2, railY, railZ]}>
          <boxGeometry args={[0.12, 0.06, railLength]} />
          <meshStandardMaterial color="#b45309" emissive="#f59e0b" emissiveIntensity={1.8} />
        </mesh>
      ))}
    </group>
  )
}

/** Glowing border around the deck (deck-local coordinates). */
function DeckFrame({ geom }) {
  const B = geom.BOARD
  const z = geom.boardFaceZ - 0.02
  const bars = [
    { pos: [0, B.y1 + 0.1, z], size: [B.x1 - B.x0 + 0.34, 0.1, 0.1] },
    { pos: [0, B.y0 - 0.1, z], size: [B.x1 - B.x0 + 0.34, 0.1, 0.1] },
    { pos: [B.x0 - 0.12, (B.y0 + B.y1) / 2, z], size: [0.1, B.y1 - B.y0 + 0.34, 0.1] },
    { pos: [B.x1 + 0.12, (B.y0 + B.y1) / 2, z], size: [0.1, B.y1 - B.y0 + 0.34, 0.1] },
  ]
  return (
    <group>
      {bars.map((b, i) => (
        <mesh key={i} position={b.pos}>
          <boxGeometry args={b.size} />
          <meshStandardMaterial color="#7c2d12" emissive="#f97316" emissiveIntensity={1.2} />
        </mesh>
      ))}
    </group>
  )
}

// 巡邏門 patrol path: guards the upper deck (150 + golden corners approach)
// while the low 50 stays free — memorized aim+power now needs TIMING too.
const SWEEP_Y = 4.15
const SWEEP_PERIOD = 4.6 // seconds per full left-right-left cycle

/**
 * Kinematic guard bar sweeping across the deck face. Lives OUTSIDE the
 * tilted group: kinematic bodies are driven in world coordinates every
 * frame, so it derives its pose from geom.boardPoint directly.
 */
function DeckSweeper({ geom, onSweeperHit }) {
  const body = useRef()
  const amplitude = geom.BOARD.x1 - 0.75
  const initial = useMemo(() => geom.boardPoint(0, SWEEP_Y, -0.3), [geom])

  useFrame(({ clock }) => {
    if (!body.current) return
    const x = Math.sin((clock.elapsedTime * Math.PI * 2) / SWEEP_PERIOD) * amplitude
    const [wx, wy, wz] = geom.boardPoint(x, SWEEP_Y, -0.3)
    body.current.setNextKinematicTranslation({ x: wx, y: wy, z: wz })
  })

  return (
    <RigidBody
      ref={body}
      type="kinematicPosition"
      position={initial}
      rotation={[geom.tilt, 0, 0]}
      colliders="cuboid"
      friction={0.4}
      restitution={0.55}
      onCollisionEnter={({ other }) => {
        if (other.rigidBody?.userData?.isSkeeball) {
          sfx.clank()
          onSweeperHit?.()
        }
      }}
    >
      <mesh castShadow>
        <boxGeometry args={[1.25, 0.26, 0.55]} />
        <meshStandardMaterial
          color="#b45309"
          emissive="#fbbf24"
          emissiveIntensity={1.4}
          metalness={0.6}
          roughness={0.3}
        />
      </mesh>
    </RigidBody>
  )
}

export default function SkeeballWorld({ level = DEFAULT_LEVEL, onScore, onRimHit, onSweeperHit }) {
  const geom = useLevelGeometry(level)
  const { rise } = geom.ramp
  return (
    <group>
      <Lane geom={geom} textureUrl={level.textures.laneUrl} />
      <Ramp geom={geom} textureUrl={level.textures.laneUrl} />
      {/* Deck group: everything board-related is built in the flat (vertical)
          coordinates and rotated back around the deck's bottom edge. Fixed
          rapier bodies pick up the group transform at creation; Physics
          remounts on level change so the colliders follow edits. */}
      <group position={[0, rise, geom.backboardZ]} rotation={[geom.tilt, 0, 0]}>
        <group position={[0, -rise, -geom.backboardZ]}>
          <Backboard geom={geom} targets={level.targets} />
          <DeckFrame geom={geom} />
          {level.targets.map((hole) => (
            <ScoreHole key={hole.name} hole={hole} geom={geom} onScore={onScore} onRimHit={onRimHit} />
          ))}
        </group>
      </group>
      <DeckSweeper geom={geom} onSweeperHit={onSweeperHit} />
      <ArenaTrim geom={geom} />
      {/* warm key light over the deck: gives the gunmetal + brass materials
          something to reflect and pools the eye on the target zone */}
      <pointLight
        position={geom.boardPoint(0, 4.6, -3)}
        intensity={26}
        color="#ffc978"
        distance={14}
        decay={1.6}
      />
    </group>
  )
}
