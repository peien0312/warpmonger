import { useMemo, useRef } from 'react'
import { CuboidCollider, RigidBody } from '@react-three/rapier'
import * as THREE from 'three'
import { BonusRing, BossStation, WALL, rollRingValue } from './dropShared.jsx'

/**
 * 音速迴圈軌道 — the sketch's middle: a hotwheels-style run. Every drop is
 * funneled onto a narrow track, accelerator pads (>>>) slam the ball up to
 * speed, it rides a full vertical LOOP (ring waiting at the apex), gets one
 * more boost, and rockets into the boss.
 */

// The catch ramp must span the ENTIRE deck drop zone (z≈10-14.5) — the loop
// lives beyond it, so balls only ever enter it from the inside via the track
// (an earlier layout put the loop under the deck: drops landed ON the wheel).
const CATCH = { z0: 5, y: -1.8, angle: 0.3, length: 11, width: 11 }
const TRACK_W = 2.4
const TRACK_Y = -5.1             // flat running height after the catch ramp
const LOOP = { z: 19.3, r: 2.3, segs: 22 }   // center z; center y = TRACK_Y + r
const BOOST_SPEED = 17
const PAD1_Z = 16.4
const PAD2_Z = 22.4
const FACE_POS = [0, -3.0, 25.0]

export function genSonicRings() {
  const mk = (id, position, rotation = [0, 0, 0]) => ({
    id: `${Date.now()}-${id}`, ...rollRingValue(), position, rotation, collected: false,
  })
  return [
    mk('catch-1', [(Math.random() - 0.5) * 6, CATCH.y - 2.1 + 0.55, 9.2]),
    mk('run-1', [0, TRACK_Y + 0.55, 17.2]),
    // the hero ring: apex of the loop, collected upside down
    mk('apex', [0, TRACK_Y + 2 * LOOP.r - 0.85, LOOP.z]),
    mk('run-2', [0, TRACK_Y + 0.55, 23.4]),
  ]
}

export function sonicCams(geom) {
  return {
    deckZ: geom.backboardZ,
    faceZ: FACE_POS[2],
    side: new THREE.Vector3(-11.2, -1.4, 18.6),
    impact: new THREE.Vector3(-5.0, -0.8, 21.8),
  }
}

/** Full vertical loop built from tangent segments (ball rides the inside). */
function Loop() {
  const segs = useMemo(() => {
    const out = []
    const cy = TRACK_Y + LOOP.r
    for (let i = 0; i < LOOP.segs; i++) {
      const ang = -Math.PI / 2 + (i / LOOP.segs) * Math.PI * 2
      const chord = (2 * Math.PI * LOOP.r) / LOOP.segs + 0.15
      out.push({
        position: [0, cy + LOOP.r * Math.sin(ang), LOOP.z + LOOP.r * Math.cos(ang)],
        rotation: [-ang, 0, 0], // tangent to the circle in the y-z plane
        chord,
      })
    }
    return out
  }, [])
  return (
    <>
      {segs.map((s, i) => (
        <group key={i} position={s.position} rotation={s.rotation}>
          <RigidBody type="fixed" colliders="cuboid" friction={0.1} restitution={0.05}>
            <mesh castShadow>
              <boxGeometry args={[TRACK_W, 0.22, s.chord]} />
              <meshStandardMaterial color="#20242c" metalness={0.5} roughness={0.4} />
            </mesh>
          </RigidBody>
          {/* side lips keep the ball centered through the loop */}
          {[-1, 1].map((side) => (
            <RigidBody key={side} type="fixed" colliders="cuboid" friction={0.1} restitution={0.2}>
              <mesh position={[(side * (TRACK_W + 0.25)) / 2, 0.3, 0]}>
                <boxGeometry args={[0.22, 0.55, s.chord]} />
                <meshStandardMaterial color="#7c2d12" emissive="#f97316" emissiveIntensity={0.9} />
              </mesh>
            </RigidBody>
          ))}
        </group>
      ))}
    </>
  )
}

/** Accelerator pad: chevrons + a sensor that slams the ball to BOOST_SPEED. */
function BoostPad({ z, onBoost }) {
  const cooling = useRef(false)
  return (
    <group position={[0, TRACK_Y, z]}>
      {[0, 1, 2].map((i) => (
        <mesh key={i} position={[0, 0.13, -0.4 + i * 0.4]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[TRACK_W - 0.5, 0.28]} />
          <meshStandardMaterial color="#0e7490" emissive="#22d3ee" emissiveIntensity={1.8} transparent opacity={0.9} />
        </mesh>
      ))}
      <RigidBody type="fixed" colliders={false}>
        <CuboidCollider
          args={[TRACK_W / 2, 0.5, 0.7]}
          position={[0, 0.4, 0]}
          sensor
          onIntersectionEnter={({ other }) => {
            const rb = other.rigidBody
            if (!rb?.userData?.isSkeeball || cooling.current) return
            cooling.current = true
            setTimeout(() => { cooling.current = false }, 400)
            try {
              const v = rb.linvel()
              rb.setLinvel({ x: v.x * 0.2, y: v.y, z: BOOST_SPEED }, true)
              onBoost?.()
            } catch { /* ball already resolved */ }
          }}
        />
      </RigidBody>
    </group>
  )
}

export default function SonicTrack({ rings, onRingCollect, onFaceHit, onBoost, faceStage, laughing, faceHitKey }) {
  return (
    <group>
      {/* catch ramp: wide plane with V guide walls funneling into the track */}
      <group position={[0, CATCH.y, CATCH.z0]} rotation={[CATCH.angle, 0, 0]}>
        <RigidBody type="fixed" colliders="cuboid" friction={0.15} restitution={0.05}>
          <mesh receiveShadow>
            <mesh position={[0, -0.15, CATCH.length / 2]}>
              <boxGeometry args={[CATCH.width, 0.3, CATCH.length + 1]} />
              <meshStandardMaterial color="#151922" roughness={0.85} />
            </mesh>
          </mesh>
        </RigidBody>
        {/* V guides */}
        {[-1, 1].map((side) => (
          <RigidBody key={side} type="fixed" colliders="cuboid" {...WALL}>
            <mesh
              position={[(side * CATCH.width) / 4 + (side * TRACK_W) / 4, 0.8, CATCH.length - 1.4]}
              rotation={[0, side * -0.55, 0]}
            >
              <boxGeometry args={[0.25, 2.2, CATCH.width * 0.55]} />
              <meshStandardMaterial color="#242a35" roughness={0.7} transparent opacity={0.4} />
            </mesh>
          </RigidBody>
        ))}
        {/* tall outer walls (deck-height) */}
        {[-1, 1].map((side) => (
          <RigidBody key={`w${side}`} type="fixed" colliders="cuboid" {...WALL}>
            <mesh position={[(side * CATCH.width) / 2, 4.5, CATCH.length / 2]}>
              <boxGeometry args={[0.25, 11, CATCH.length + 1]} />
              <meshStandardMaterial color="#242a35" roughness={0.7} transparent opacity={0.3} />
            </mesh>
          </RigidBody>
        ))}
        {/* top wall below the lane underside */}
        <RigidBody type="fixed" colliders="cuboid" {...WALL}>
          <mesh position={[0, 0.45, -0.4]}>
            <boxGeometry args={[CATCH.width, 1.2, 0.25]} />
            <meshStandardMaterial color="#242a35" roughness={0.7} transparent opacity={0.3} />
          </mesh>
        </RigidBody>
      </group>

      {/* the running track: catch end → past the loop → the boss */}
      <RigidBody type="fixed" colliders="cuboid" friction={0.1} restitution={0.05}>
        <mesh position={[0, TRACK_Y - 0.11, 20.2]} receiveShadow>
          <boxGeometry args={[TRACK_W, 0.22, 10.6]} />
          <meshStandardMaterial color="#20242c" metalness={0.5} roughness={0.4} />
        </mesh>
      </RigidBody>
      {/* track side rails the whole way */}
      {[-1, 1].map((side) => (
        <RigidBody key={side} type="fixed" colliders="cuboid" friction={0.1} restitution={0.2}>
          <mesh position={[(side * (TRACK_W + 0.25)) / 2, TRACK_Y + 0.3, 20.2]}>
            <boxGeometry args={[0.22, 0.55, 10.6]} />
            <meshStandardMaterial color="#7c2d12" emissive="#f97316" emissiveIntensity={0.9} />
          </mesh>
        </RigidBody>
      ))}

      <BoostPad z={PAD1_Z} onBoost={onBoost} />
      <Loop />
      <BoostPad z={PAD2_Z} onBoost={onBoost} />

      {rings.map((ring) => (
        <BonusRing key={ring.id} ring={ring} onCollect={onRingCollect} />
      ))}

      <group position={FACE_POS} rotation={[0.15, Math.PI, 0]}>
        <BossStation
          width={6}
          faceStage={faceStage}
          laughing={laughing}
          faceHitKey={faceHitKey}
          onFaceHit={onFaceHit}
        />
      </group>

      <pointLight position={[0, 1.5, 16]} intensity={22} color="#ffd9a0" distance={12} decay={1.7} />
    </group>
  )
}
