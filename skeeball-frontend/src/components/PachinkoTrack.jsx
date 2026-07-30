import { useMemo } from 'react'
import { CuboidCollider, RigidBody } from '@react-three/rapier'
import * as THREE from 'three'
import { BonusRing, BossStation, WALL, rollRingValue } from './dropShared.jsx'

/**
 * 柏青哥軌道 — the original drop: one continuous inclined plane (single
 * piece — seams trap balls), staggered pegs, rings on the run, boss at the
 * bottom. Authored in plane-local coordinates inside one rotated group.
 */

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

export function genPachinkoRings(geom) {
  const p = geom.pachinko
  return Array.from({ length: 5 }, (_, i) => ({
    id: `${Date.now()}-${i}`,
    ...rollRingValue(),
    position: [
      (Math.random() - 0.5) * (p.width - 2.4),
      0.55,
      p.ringZone.z0 + ((i + Math.random() * 0.8) / 5) * (p.ringZone.z1 - p.ringZone.z0),
    ],
    collected: false,
  }))
}

export function pachinkoCams(geom) {
  const p = geom.pachinko
  return {
    deckZ: geom.backboardZ,
    faceZ: p.faceZ,
    side: new THREE.Vector3(-(p.width / 2 + 5.4), 0.9, p.faceZ - 6.8),
    impact: new THREE.Vector3(-(p.width / 2 + 1.4), p.faceY + 3.8, p.faceZ - 4.8),
  }
}

export default function PachinkoTrack({ geom, rings, onRingCollect, onFaceHit, faceStage, laughing, faceHitKey }) {
  const p = geom.pachinko
  const { z0, y, angle, length } = p.drop

  return (
    <group position={[0, y, z0]} rotation={[angle, 0, 0]}>
      <RigidBody type="fixed" colliders="cuboid" friction={0.2} restitution={0.05}>
        <mesh position={[0, -0.15, length / 2]} receiveShadow>
          <boxGeometry args={[p.width, 0.3, length + 1]} />
          <meshStandardMaterial color="#151922" roughness={0.85} />
        </mesh>
      </RigidBody>

      {/* tall walls (deck-height: side escapes flew over shorter ones) */}
      {[-1, 1].map((side) => (
        <RigidBody key={side} type="fixed" colliders="cuboid" {...WALL}>
          <mesh position={[(side * p.width) / 2, 4.5, 4 + (length - 3.5) / 2]}>
            <boxGeometry args={[0.25, 11, length - 3.5]} />
            <meshStandardMaterial color="#242a35" roughness={0.7} transparent opacity={0.3} />
          </mesh>
        </RigidBody>
      ))}

      {/* top wall BELOW the lane underside (taller poked through the lane) */}
      <RigidBody type="fixed" colliders="cuboid" {...WALL}>
        <mesh position={[0, 0.45, -0.4]}>
          <boxGeometry args={[p.width, 1.2, 0.25]} />
          <meshStandardMaterial color="#242a35" roughness={0.7} transparent opacity={0.3} />
        </mesh>
      </RigidBody>

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

      <group position={[0, 2.2, length + 0.6]} rotation={[0.3, Math.PI, 0]}>
        <BossStation
          width={p.width}
          faceStage={faceStage}
          laughing={laughing}
          faceHitKey={faceHitKey}
          onFaceHit={onFaceHit}
        />
      </group>

      <pointLight position={[0, 3.2, length - 1.5]} intensity={20} color="#ffd9a0" distance={10} decay={1.7} />
    </group>
  )
}
