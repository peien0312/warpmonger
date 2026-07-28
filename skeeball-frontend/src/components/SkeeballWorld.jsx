import { Suspense, useMemo } from 'react'
import { Text, useTexture } from '@react-three/drei'
import { BallCollider, CuboidCollider, RigidBody } from '@react-three/rapier'
import * as THREE from 'three'
import { DEFAULT_LEVEL } from '../config/levelConfig.js'
import TextureErrorBoundary from './TextureErrorBoundary.jsx'

export const COLORS = {
  lane: '#8b5a2b',
  ramp: '#a06a35',
  backboard: '#1e293b',
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

const POCKET_DEPTH = 1.2
const POCKET_WALL = 0.08
const RIM_SEGMENTS = 10
const RAMP_SEGMENTS = 14

/**
 * Split the ramp into N box segments following a power-curve profile:
 * y = rise · t^(1 + 2·curve). curve 0 = straight incline; higher values stay
 * flatter at the bottom and launch steeper at the lip (ski-jump shape).
 * The same segments drive both the meshes and the physics colliders.
 */
export function computeRampSegments(lane, ramp) {
  const exponent = 1 + 2 * ramp.curve
  const z0 = lane.length / 2
  const y = (t) => ramp.rise * Math.pow(t, exponent)
  const segs = []
  for (let i = 0; i < RAMP_SEGMENTS; i++) {
    const t0 = i / RAMP_SEGMENTS
    const t1 = (i + 1) / RAMP_SEGMENTS
    const dz = (t1 - t0) * ramp.length
    const dy = y(t1) - y(t0)
    segs.push({
      position: [0, (y(t0) + y(t1)) / 2, z0 + ((t0 + t1) / 2) * ramp.length],
      angle: Math.atan2(dy, dz),
      length: Math.hypot(dz, dy) + 0.02, // slight overlap so segments don't gap
    })
  }
  return segs
}

/**
 * Pure geometry derivation from a level config. Everything the world,
 * aim arrow, preview ball and play ball need, computed in one place.
 */
export function computeGeometry(level = DEFAULT_LEVEL) {
  const { lane, ramp, backboard, ball } = level
  const rampTopZ = lane.length / 2 + ramp.length
  // Gap between the ramp lip and the backboard: the ball flies it ballistically.
  const backboardZ = rampTopZ + ramp.gap + backboard.thickness / 2
  const boardCenterY = ramp.rise + backboard.height / 2
  const boardFaceZ = backboardZ - backboard.thickness / 2
  const boardBackZ = backboardZ + backboard.thickness / 2

  // Board is one meter wider than the lane; holes sit in the band the ball
  // can physically reach off the ramp lip, apex corners higher.
  const boardWidth = lane.width + 1
  const BOARD = { x0: -boardWidth / 2, x1: boardWidth / 2, y0: ramp.rise, y1: ramp.rise + backboard.height }

  const BALL_START = [0, lane.thickness / 2 + ball.radius, -lane.length / 2 + 1.2]

  // Stray-ball kill bounds, scaled to the arena size (defaults: y<-2.5, z>13, z<-9, |x|>8).
  const missBounds = {
    minY: -2.5,
    maxZ: boardBackZ + POCKET_DEPTH + 1,
    minZ: -(lane.length - 3),
    maxAbsX: lane.width * 2,
  }

  return {
    lane,
    ramp,
    backboard,
    rampTopZ,
    backboardZ,
    boardCenterY,
    boardFaceZ,
    boardBackZ,
    BOARD,
    BALL_START,
    missBounds,
  }
}

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

/** Floor/ramp material: texture when a lane URL is set, flat color otherwise. */
function WoodSurface({ textureUrl, color, roughness }) {
  return textureUrl ? (
    <LaneSurface textureUrl={textureUrl} color={color} roughness={roughness} />
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
              <meshStandardMaterial color={COLORS.backboard} roughness={0.5} />
            </mesh>
          </RigidBody>
        )
      })}
    </group>
  )
}

/** Ring of small cuboid colliders forming a physical, bouncy circular rim. */
function RimColliders({ hole, geom }) {
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
    <RigidBody type="fixed" colliders={false} friction={0.6} restitution={0.35}>
      {segments.map((s, i) => (
        <CuboidCollider key={i} args={s.args} position={s.position} rotation={s.rotation} />
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
            if (other.rigidBody?.userData?.isSkeeball) onScore(hole.points)
          }}
        />
      </RigidBody>
    </group>
  )
}

function ScoreHole({ hole, geom, onScore }) {
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
      <mesh position={[hole.x, hole.y, boardFaceZ - 0.02]}>
        <torusGeometry args={[hole.r, 0.06, 20, 48]} />
        <meshStandardMaterial
          color={hole.color}
          emissive={hole.color}
          emissiveIntensity={isApex ? 0.8 : 0.35}
          roughness={0.4}
        />
      </mesh>
      <Text
        position={[hole.x, isApex ? hole.y - hole.r - 0.35 : hole.y + hole.r + 0.3, boardFaceZ - 0.05]}
        fontSize={isApex ? 0.16 : 0.22}
        color={isApex ? COLORS.apex : '#f8fafc'}
        anchorX="center"
        anchorY="middle"
        outlineWidth={0.012}
        outlineColor="#0f172a"
      >
        {isApex ? `${hole.points} Golden Ticket` : `${hole.points}`}
      </Text>
      <RimColliders hole={hole} geom={geom} />
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

export default function SkeeballWorld({ level = DEFAULT_LEVEL, onScore }) {
  const geom = useLevelGeometry(level)
  return (
    <group>
      <Lane geom={geom} textureUrl={level.textures.laneUrl} />
      <Ramp geom={geom} textureUrl={level.textures.laneUrl} />
      <Backboard geom={geom} targets={level.targets} />
      {level.targets.map((hole) => (
        <ScoreHole key={hole.name} hole={hole} geom={geom} onScore={onScore} />
      ))}
    </group>
  )
}
