import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Trail } from '@react-three/drei'
import { RigidBody } from '@react-three/rapier'
import { BallSurface } from './SkeeballWorld.jsx'
import { DEFAULT_LEVEL } from '../config/levelConfig.js'

const MAX_FLIGHT_TIME = 14 // seconds — the pachinko drop is part of the ride
const STALL_SPEED = 0.55 // m/s — below this the ball is "going nowhere"
const STALL_TIME = 1.2 // seconds of going-nowhere before retiring
const BACKWARD_TIME = 1.1 // seconds of rolling back toward the player
const NUDGE_ACCEL = 7 // m/s² of ←→ mid-roll steering
const NUDGE_BUDGET = 2.6 // total m/s of Δv a ball may be steered

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
  posRef,
  nudgeRef,
}) {
  const body = useRef()
  const done = useRef(false)
  const bornAt = useRef(null)
  const stallSince = useRef(null)
  const backwardSince = useRef(null)
  const nudgeBudget = useRef(NUDGE_BUDGET)

  const launchVelocity = useMemo(() => {
    const speed = ballCfg.minSpeed + power * (ballCfg.maxSpeed - ballCfg.minSpeed)
    // Nearly flat launch — a rolling ball with a hint of hop at full power,
    // not a pitch. The ramp (not the lob) does the lifting.
    const up = ballCfg.upBase + power * ballCfg.upScale
    const dir = { x: Math.sin(angle), y: up, z: Math.cos(angle) }
    const len = Math.hypot(dir.x, dir.y, dir.z)
    return [(dir.x / len) * speed, (dir.y / len) * speed, (dir.z / len) * speed]
  }, [angle, power, ballCfg])

  useFrame(({ clock }, dt) => {
    const api = body.current
    if (!api) return

    if (bornAt.current === null) {
      bornAt.current = clock.elapsedTime
      return
    }

    if (done.current) return
    const { x, y, z } = api.translation()
    if (posRef) posRef.current = { x, y, z }

    // Mid-roll steering (←→ / on-screen buttons): a small, budget-capped
    // lateral push — enough to save a drifting shot, not enough to aim
    // after the fact.
    const steer = nudgeRef?.current || 0
    if (steer && nudgeBudget.current > 0) {
      const dv = NUDGE_ACCEL * Math.min(dt, 0.05)
      api.applyImpulse({ x: steer * dv * ballCfg.mass, y: 0, z: 0 }, true)
      nudgeBudget.current -= dv
    }
    const b = missBounds
    const outOfBounds = b && (y < b.minY || z > b.maxZ || z < b.minZ || Math.abs(x) > b.maxAbsX)
    const timedOut = clock.elapsedTime - bornAt.current > MAX_FLIGHT_TIME

    // A ball that stalls, or rolls backward down the lane, can never score —
    // retire it early instead of making the player watch it creep out of
    // bounds. Grace period ~0.5s so the launch itself never trips these.
    const now = clock.elapsedTime
    const alive = now - bornAt.current
    let deadEnd = false
    if (alive > 0.5) {
      const v = api.linvel()
      const speed = Math.hypot(v.x, v.y, v.z)
      // In the drop field slow creeping is normal (dead-bounce collector) —
      // only a truly parked ball gets retired, and it gets longer to recover.
      const inDrop = z > (b?.backwardZ ?? Infinity)
      const stallSpeed = inDrop ? 0.2 : STALL_SPEED
      const stallTime = inDrop ? 3.0 : STALL_TIME
      if (speed < stallSpeed) {
        stallSince.current ??= now
        deadEnd = now - stallSince.current > stallTime
      } else {
        stallSince.current = null
      }
      // Backward motion on the tilted deck / in the drop field is normal
      // play — only count it once the ball is back before the deck AND
      // above the collector (i.e. rolling down the lane toward the player).
      if (v.z < -0.4 && z < (b?.backwardZ ?? Infinity) && y > 0) {
        backwardSince.current ??= now
        deadEnd ||= now - backwardSince.current > BACKWARD_TIME
      } else {
        backwardSince.current = null
      }
    }

    if (outOfBounds || timedOut || deadEnd) {
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
      linearDamping={0.08}
      angularDamping={0.15}
      ccd
      linearVelocity={launchVelocity}
      userData={{ isSkeeball: true }}
    >
      <Trail width={1.6} length={5} color="#fbbf24" attenuation={(t) => t * t}>
        <mesh castShadow>
          <sphereGeometry args={[ballCfg.radius, 48, 48]} />
          <BallSurface textureUrl={textureUrl} />
        </mesh>
      </Trail>
    </RigidBody>
  )
}
