import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { RigidBody } from '@react-three/rapier'
import { BallSurface } from './SkeeballWorld.jsx'
import { DEFAULT_LEVEL } from '../config/levelConfig.js'

const MAX_FLIGHT_TIME = 8 // seconds before a stray ball is retired

/**
 * Dynamic physics ball. Launch velocity is set through the RigidBody's
 * `linearVelocity` prop, which rapier applies when the body is created —
 * an impulse fired from useFrame/useEffect can be lost when StrictMode's
 * double-mount recreates the physics body after the ref flag was already
 * set, leaving the ball frozen at the start.
 * Scoring is reported by the hole sensors via the parent's onScore; this
 * component only reports a miss (out of bounds or timed out) through onMiss,
 * exactly once.
 */
export default function PlayBall({
  angle,
  power,
  textureUrl,
  onMiss,
  ballCfg = DEFAULT_LEVEL.ball,
  startPosition,
  missBounds,
}) {
  const body = useRef()
  const done = useRef(false)
  const bornAt = useRef(null)

  const launchVelocity = useMemo(() => {
    const speed = ballCfg.minSpeed + power * (ballCfg.maxSpeed - ballCfg.minSpeed)
    // Nearly flat launch — a rolling ball with a hint of hop at full power,
    // not a pitch. The ramp (not the lob) does the lifting.
    const up = ballCfg.upBase + power * ballCfg.upScale
    const dir = { x: Math.sin(angle), y: up, z: Math.cos(angle) }
    const len = Math.hypot(dir.x, dir.y, dir.z)
    return [(dir.x / len) * speed, (dir.y / len) * speed, (dir.z / len) * speed]
  }, [angle, power, ballCfg])

  useFrame(({ clock }) => {
    const api = body.current
    if (!api) return

    if (bornAt.current === null) {
      bornAt.current = clock.elapsedTime
      return
    }

    if (done.current) return
    const { x, y, z } = api.translation()
    const b = missBounds
    const outOfBounds = b && (y < b.minY || z > b.maxZ || z < b.minZ || Math.abs(x) > b.maxAbsX)
    const timedOut = clock.elapsedTime - bornAt.current > MAX_FLIGHT_TIME
    if (outOfBounds || timedOut) {
      done.current = true
      onMiss()
    }
  })

  return (
    <RigidBody
      ref={body}
      colliders="ball"
      position={startPosition}
      mass={ballCfg.mass}
      friction={ballCfg.friction}
      restitution={ballCfg.restitution}
      linearDamping={0.2}
      angularDamping={0.5}
      ccd
      linearVelocity={launchVelocity}
      userData={{ isSkeeball: true }}
    >
      <mesh castShadow>
        <sphereGeometry args={[ballCfg.radius, 48, 48]} />
        <BallSurface textureUrl={textureUrl} />
      </mesh>
    </RigidBody>
  )
}
