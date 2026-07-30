import { Suspense, useEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Sparkles, useTexture } from '@react-three/drei'
import { BallCollider, CuboidCollider, RigidBody } from '@react-three/rapier'
import { BOSS } from '../config/boss.js'

/**
 * The 柏青哥 drop field behind the deck: ONE continuous inclined plane (no
 * seams — an earlier collector+chute two-piece design had ball-trapping
 * junctions). Every launched ball lands on it, rattles through pegs and
 * random bonus rings, and ends its journey in the boss's face at the bottom.
 *
 * Everything is authored in plane-local coordinates inside one rotated
 * group: x across, z down-slope, y off the surface.
 */

const WALL = { friction: 0.25, restitution: 0.3 }

/** Staggered peg grid — the pachinko chaos. */
function Pegs({ p }) {
  const pegs = useMemo(() => {
    const rows = []
    p.pegRowsZ.forEach((lz, r) => {
      const count = 4 + (r % 2)
      for (let i = 0; i < count; i++) {
        const x = (i - (count - 1) / 2) * (p.width / count) * 0.82
        rows.push([x, lz])
      }
    })
    return rows
  }, [p])
  return (
    <>
      {pegs.map(([x, lz], i) => (
        <RigidBody key={i} type="fixed" colliders={false} friction={0.3} restitution={0.65}>
          <CuboidCollider args={[0.14, 0.5, 0.14]} position={[x, 0.5, lz]} />
          <mesh position={[x, 0.5, lz]} castShadow>
            <cylinderGeometry args={[0.14, 0.16, 1.0, 12]} />
            <meshStandardMaterial color="#8a929f" metalness={0.7} roughness={0.35} />
          </mesh>
        </RigidBody>
      ))}
    </>
  )
}

/** One glowing bonus hoop; ball through the middle = collect. */
function BonusRing({ ring, onCollect }) {
  if (ring.collected) return null
  return (
    <group position={[ring.x, 0.55, ring.lz]}>
      <mesh>
        <torusGeometry args={[0.62, 0.07, 14, 40]} />
        <meshStandardMaterial
          color={ring.color}
          emissive={ring.color}
          emissiveIntensity={1.6}
          metalness={0.4}
          roughness={0.3}
        />
      </mesh>
      <Sparkles count={8} scale={[1.4, 1.4, 0.6]} size={2} speed={0.6} color={ring.color} />
      <RigidBody type="fixed" colliders={false}>
        <BallCollider
          args={[0.34]}
          sensor
          onIntersectionEnter={({ other }) => {
            if (other.rigidBody?.userData?.isSkeeball) onCollect(ring)
          }}
        />
      </RigidBody>
    </group>
  )
}

function FaceMaterial({ url }) {
  const tex = useTexture(url)
  return <meshStandardMaterial map={tex} transparent roughness={0.6} />
}

/**
 * The boss. Recoils on every hit (bump `hitKey`), swaps through bruise
 * stages, and flips to the mocking laugh texture while `laughing`.
 */
function BossFace({ stage, laughing, hitKey, size = 5 }) {
  const group = useRef()
  const kick = useRef(0)
  useEffect(() => {
    if (hitKey) kick.current = 1
  }, [hitKey])
  useFrame((_, dt) => {
    if (!group.current) return
    kick.current = Math.max(0, kick.current - dt * 3)
    const k = kick.current
    // squash back + shake while the kick decays
    group.current.position.z = 0.65 * k
    group.current.position.x = Math.sin(k * 40) * 0.12 * k
    const s = 1 - 0.16 * k
    group.current.scale.set(1 + 0.18 * k, s, 1)
  })
  const url = laughing ? BOSS.textures.laugh : BOSS.textures.stages[stage] ?? BOSS.textures.stages[0]
  return (
    <group ref={group}>
      <mesh>
        <planeGeometry args={[size, size]} />
        <Suspense fallback={<meshStandardMaterial color="#c49a5c" />}>
          <FaceMaterial url={url} />
        </Suspense>
      </mesh>
    </group>
  )
}

export default function Pachinko({ geom, rings, onRingCollect, onFaceHit, faceStage, laughing, faceHitKey }) {
  const p = geom.pachinko
  const { z0, y, angle, length } = p.drop

  return (
    /* single rotated frame: the whole drop field lives on one plane */
    <group position={[0, y, z0]} rotation={[angle, 0, 0]}>
      {/* the plane itself — dead bounce so deck-height drops don't fly */}
      <RigidBody type="fixed" colliders="cuboid" friction={0.2} restitution={0.05}>
        <mesh position={[0, -0.15, length / 2]} receiveShadow>
          <boxGeometry args={[p.width, 0.3, length + 1]} />
          <meshStandardMaterial color="#151922" roughness={0.85} />
        </mesh>
      </RigidBody>

      {/* full-length tall side walls (translucent so the camera reads them) */}
      {/* walls start past the ramp so they don't tower beside the lane */}
      {[-1, 1].map((side) => (
        <RigidBody key={side} type="fixed" colliders="cuboid" {...WALL}>
          <mesh position={[(side * p.width) / 2, 4.5, 4 + (length - 3.5) / 2]}>
            <boxGeometry args={[0.25, 11, length - 3.5]} />
            <meshStandardMaterial color="#242a35" roughness={0.7} transparent opacity={0.3} />
          </mesh>
        </RigidBody>
      ))}

      {/* top wall: uphill rollbacks bounce and come back down. MUST stay
          below the lane underside — a taller wall pokes up through the lane
          and invisibly fences the rolling ball (beta bug). */}
      <RigidBody type="fixed" colliders="cuboid" {...WALL}>
        <mesh position={[0, 0.45, -0.4]}>
          <boxGeometry args={[p.width, 1.2, 0.25]} />
          <meshStandardMaterial color="#242a35" roughness={0.7} transparent opacity={0.3} />
        </mesh>
      </RigidBody>

      {/* neon guide rails */}
      {[-1, 1].map((side) => (
        <mesh key={`rail${side}`} position={[(side * (p.width - 0.5)) / 2, 0.05, length / 2]}>
          <boxGeometry args={[0.08, 0.05, length]} />
          <meshStandardMaterial color="#7c2d12" emissive="#f97316" emissiveIntensity={1.4} />
        </mesh>
      ))}

      <Pegs p={p} />

      {rings.map((ring) => (
        <BonusRing key={ring.id} ring={ring} onCollect={onRingCollect} />
      ))}

      {/* the boss, leaning back at the end of the run */}
      {/* standing at the end of the slope, facing UP-slope toward the
          incoming ball (Y-flip turns the plane around; slight X lean-back) */}
      <group position={[0, 2.2, length + 0.6]} rotation={[0.3, Math.PI, 0]}>
        <BossFace stage={faceStage} laughing={laughing} hitKey={faceHitKey} />
        {/* hit sensor floating just in front of the face */}
        <RigidBody type="fixed" colliders={false}>
          <CuboidCollider
            args={[p.width / 2, 2.6, 0.3]}
            position={[0, 0, 0.6]}
            sensor
            onIntersectionEnter={({ other }) => {
              if (other.rigidBody?.userData?.isSkeeball) onFaceHit?.()
            }}
          />
        </RigidBody>
        {/* solid backstop behind the face so the ball thuds and drops */}
        <RigidBody type="fixed" colliders="cuboid" friction={0.5} restitution={0.25}>
          <mesh position={[0, 0, -0.2]} visible={false}>
            <boxGeometry args={[p.width, 5.6, 0.3]} />
            <meshStandardMaterial />
          </mesh>
        </RigidBody>
      </group>

      {/* warm spotlight pooling on the boss */}
      <pointLight position={[0, 3.2, length - 1.5]} intensity={20} color="#ffd9a0" distance={10} decay={1.7} />
    </group>
  )
}
