import { useMemo, useRef } from 'react'
import { CuboidCollider, RigidBody } from '@react-three/rapier'
import * as THREE from 'three'
import { BonusRing, BossStation, rollRingValue } from './dropShared.jsx'

/**
 * 漩渦大砲軌道 — the sketch's right side: every ball drops into a giant
 * funnel, spirals down through scattered rings, falls into a cartoon cannon,
 * and gets BLASTED through two mid-air rings straight into the boss's face.
 */

const C = { x: 0, topY: -2.2, z: 12.6 }   // funnel center
const R_TOP = 5.8
const R_BOT = 0.85
const DEPTH = 4
const PANELS = 28
const CANNON_POS = [0, -7.1, 12.6]
const MUZZLE = [0, -6.2, 13.5]
const LAUNCH = { x: 0, y: 15, z: 9 }       // arc lands on the face center
const FACE_POS = [0, -1.6, 21]

export function genFunnelRings() {
  const rings = []
  // three scattered in the bowl, standing across the spiral path
  for (let i = 0; i < 3; i++) {
    const phi = Math.random() * Math.PI * 2
    const r = 2.6 + Math.random() * 1.6
    const t = (r - R_BOT) / (R_TOP - R_BOT)
    rings.push({
      id: `${Date.now()}-bowl-${i}`,
      ...rollRingValue(),
      position: [Math.sin(phi) * r, C.topY - DEPTH * (1 - t) + 0.55, C.z + Math.cos(phi) * r],
      rotation: [0, phi, 0],
      collected: false,
    })
  }
  // two on the cannon's flight arc — the guaranteed fireworks
  rings.push({
    id: `${Date.now()}-arc-1`, ...rollRingValue(), collected: false,
    position: [0, -3.6, 16.3], rotation: [0.5, 0, 0],
  })
  rings.push({
    id: `${Date.now()}-arc-2`, ...rollRingValue(), collected: false,
    position: [0, -1.9, 18.6], rotation: [0.25, 0, 0],
  })
  return rings
}

export function funnelCams(geom) {
  return {
    deckZ: geom.backboardZ,
    faceZ: FACE_POS[2],
    side: new THREE.Vector3(-10.2, 1.6, 10.8),
    impact: new THREE.Vector3(-4.6, 0.6, 16.2),
  }
}

function FunnelWall() {
  const slope = Math.atan2(DEPTH, R_TOP - R_BOT) // wall angle from horizontal
  const slant = Math.hypot(DEPTH, R_TOP - R_BOT) + 0.3
  const rMid = (R_TOP + R_BOT) / 2
  const chord = (2 * Math.PI * rMid) / PANELS + 0.5
  const panels = useMemo(
    () => Array.from({ length: PANELS }, (_, i) => (i / PANELS) * Math.PI * 2),
    []
  )
  return (
    <>
      {panels.map((theta, i) => (
        <group key={i} rotation={[0, theta, 0]} position={[C.x, 0, C.z]}>
          {/* panel lies on the cone surface: floor tilted up toward +z (rim) */}
          <group position={[0, C.topY - DEPTH / 2, rMid]} rotation={[slope, 0, 0]}>
            <RigidBody type="fixed" colliders="cuboid" friction={0.12} restitution={0.12}>
              <mesh receiveShadow>
                <boxGeometry args={[chord, 0.25, slant]} />
                <meshStandardMaterial color="#1b2027" roughness={0.75} metalness={0.3} />
              </mesh>
            </RigidBody>
          </group>
        </group>
      ))}
      {/* glowing rim so the bowl reads from above */}
      <mesh position={[C.x, C.topY + 0.05, C.z]} rotation={[-Math.PI / 2, 0, 0]}>
        <torusGeometry args={[R_TOP, 0.09, 12, 64]} />
        <meshStandardMaterial color="#7c2d12" emissive="#f97316" emissiveIntensity={1.5} />
      </mesh>
    </>
  )
}

/** The cartoon cannon: catches the ball under the funnel exit, holds it a
 * beat, then fires it along the arc. */
function Cannon({ onFire }) {
  const busy = useRef(false)
  return (
    <group>
      {/* barrel visual, aimed along the launch arc */}
      <group position={CANNON_POS} rotation={[-Math.atan2(LAUNCH.y, LAUNCH.z), 0, 0]}>
        <mesh castShadow>
          <cylinderGeometry args={[0.75, 0.95, 2.6, 20]} />
          <meshStandardMaterial color="#2f3640" metalness={0.7} roughness={0.35} />
        </mesh>
        <mesh position={[0, 1.35, 0]}>
          <torusGeometry args={[0.78, 0.12, 12, 24]} />
          <meshStandardMaterial color="#b45309" emissive="#f59e0b" emissiveIntensity={1.2} metalness={0.6} />
        </mesh>
      </group>
      {/* catch walls under the funnel hole so the ball settles into the trap */}
      <RigidBody type="fixed" colliders="cuboid" friction={0.4} restitution={0.1}>
        {[[-1.2, 0], [1.2, 0], [0, -1.2], [0, 1.2]].map(([dx, dz], i) => (
          <mesh key={i} position={[C.x + dx, -6.7, C.z + dz]} visible={false}>
            <boxGeometry args={[dx ? 0.25 : 2.6, 1.8, dz ? 0.25 : 2.6]} />
            <meshStandardMaterial />
          </mesh>
        ))}
        <mesh position={[C.x, -7.7, C.z]} visible={false}>
          <boxGeometry args={[2.6, 0.25, 2.6]} />
          <meshStandardMaterial />
        </mesh>
      </RigidBody>
      {/* trap sensor: hold 0.45s, then BLAST */}
      <RigidBody type="fixed" colliders={false}>
        <CuboidCollider
          args={[1.1, 0.8, 1.1]}
          position={[C.x, -7.0, C.z]}
          sensor
          onIntersectionEnter={({ other }) => {
            const rb = other.rigidBody
            if (!rb?.userData?.isSkeeball || busy.current) return
            busy.current = true
            try {
              rb.setLinvel({ x: 0, y: 0, z: 0 }, true)
              rb.setAngvel({ x: 0, y: 0, z: 0 }, true)
              rb.setGravityScale(0, true)
              rb.setTranslation({ x: MUZZLE[0], y: MUZZLE[1] - 0.6, z: MUZZLE[2] - 0.5 }, true)
            } catch { /* ball may already be gone */ }
            setTimeout(() => {
              busy.current = false
              try {
                rb.setGravityScale(1, true)
                rb.setTranslation({ x: MUZZLE[0], y: MUZZLE[1], z: MUZZLE[2] }, true)
                rb.setLinvel(LAUNCH, true)
                onFire?.()
              } catch { /* ball resolved while loaded */ }
            }, 450)
          }}
        />
      </RigidBody>
    </group>
  )
}

export default function FunnelTrack({ rings, onRingCollect, onFaceHit, onCannonFire, faceStage, laughing, faceHitKey }) {
  return (
    <group>
      <FunnelWall />
      <Cannon onFire={onCannonFire} />

      {rings.map((ring) => (
        <BonusRing key={ring.id} ring={ring} onCollect={onRingCollect} />
      ))}

      {/* boss floats beyond the muzzle, waiting for the delivery */}
      <group position={FACE_POS} rotation={[0.15, Math.PI, 0]}>
        <BossStation
          width={7}
          faceStage={faceStage}
          laughing={laughing}
          faceHitKey={faceHitKey}
          onFaceHit={onFaceHit}
        />
      </group>

      <pointLight position={[0, 0.5, 16.5]} intensity={22} color="#ffd9a0" distance={12} decay={1.7} />
    </group>
  )
}
