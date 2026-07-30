import { Suspense, useEffect, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Sparkles, useTexture } from '@react-three/drei'
import { BallCollider, CuboidCollider, RigidBody } from '@react-three/rapier'
import { BOSS } from '../config/boss.js'

/** Shared pieces for every drop track: bonus rings + the boss face. */

export const WALL = { friction: 0.25, restitution: 0.3 }

/** One glowing bonus hoop; ball through the middle = collect.
 * `ring` carries position/rotation in the PARENT's frame. */
export function BonusRing({ ring, onCollect }) {
  if (ring.collected) return null
  return (
    <group position={ring.position} rotation={ring.rotation ?? [0, 0, 0]}>
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
 * Place + orient via the wrapping group in each track.
 */
export function BossFace({ stage, laughing, hitKey, size = 5 }) {
  const group = useRef()
  const kick = useRef(0)
  useEffect(() => {
    if (hitKey) kick.current = 1
  }, [hitKey])
  useFrame((_, dt) => {
    if (!group.current) return
    kick.current = Math.max(0, kick.current - dt * 3)
    const k = kick.current
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

/** Boss + hit sensor + backstop, positioned by the wrapping group. */
export function BossStation({ width, faceStage, laughing, faceHitKey, onFaceHit }) {
  return (
    <>
      <BossFace stage={faceStage} laughing={laughing} hitKey={faceHitKey} />
      <RigidBody type="fixed" colliders={false}>
        <CuboidCollider
          args={[width / 2, 2.6, 0.3]}
          position={[0, 0, 0.6]}
          sensor
          onIntersectionEnter={({ other }) => {
            if (other.rigidBody?.userData?.isSkeeball) onFaceHit?.()
          }}
        />
      </RigidBody>
      <RigidBody type="fixed" colliders="cuboid" friction={0.5} restitution={0.25}>
        <mesh position={[0, 0, -0.2]} visible={false}>
          <boxGeometry args={[width, 5.6, 0.3]} />
          <meshStandardMaterial />
        </mesh>
      </RigidBody>
    </>
  )
}

/** Weighted random ring value/color, shared by every track's generator. */
export function rollRingValue() {
  const roll = Math.random()
  return roll < 0.55
    ? { value: 10, color: '#38bdf8' }
    : roll < 0.85
      ? { value: 25, color: '#a78bfa' }
      : { value: 50, color: '#facc15' }
}
