import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'

export const MAX_AIM_ANGLE = 0.38 // radians; sweeps the full lane width at the ramp
const OSC_SPEED = 1.6 // oscillations pacing (rad/s of the sine driver)

/**
 * Oscillating aim arrow in front of the ball start position.
 * Writes the current locked-candidate angle (radians) into aimRef.current
 * every frame so the overlay click handler can lock it.
 */
export default function AimArrow({
  aimRef,
  startPosition,
  maxAngle = MAX_AIM_ANGLE,
  oscSpeed = OSC_SPEED,
}) {
  const group = useRef()

  useFrame(({ clock }) => {
    const angle = Math.sin(clock.elapsedTime * oscSpeed) * maxAngle
    aimRef.current = angle
    if (group.current) group.current.rotation.y = angle
  })

  return (
    <group
      ref={group}
      position={[startPosition[0], startPosition[1], startPosition[2] + 0.8]}
    >
      {/* Shaft pointing down-lane (+z) */}
      <mesh position={[0, 0, 0.7]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.05, 0.05, 1.4, 12]} />
        <meshStandardMaterial
          color="#f8fafc"
          emissive="#f8fafc"
          emissiveIntensity={0.4}
          roughness={0.4}
        />
      </mesh>
      {/* Arrow head */}
      <mesh position={[0, 0, 1.55]} rotation={[Math.PI / 2, 0, 0]}>
        <coneGeometry args={[0.18, 0.45, 16]} />
        <meshStandardMaterial
          color="#facc15"
          emissive="#facc15"
          emissiveIntensity={0.6}
          roughness={0.3}
        />
      </mesh>
    </group>
  )
}
