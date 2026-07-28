import { useEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Billboard, Text } from '@react-three/drei'
import * as THREE from 'three'

/**
 * One-shot particle explosion at a hole. Parent mounts it with a unique key
 * and removes it when onEnd(id) fires. `big` = golden-hole version.
 */
export function ScoreBurst({ id, position, color = '#fbbf24', big = false, onEnd }) {
  const points = useRef()
  const life = big ? 1.5 : 0.9
  const count = big ? 120 : 45

  const sim = useMemo(() => {
    const velocities = new Float32Array(count * 3)
    const positions = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      // Random sphere, biased back toward the camera so the burst pops out
      // of the board instead of disappearing into it.
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)
      const speed = (big ? 5.5 : 4) * (0.4 + Math.random() * 0.6)
      velocities[i * 3] = Math.sin(phi) * Math.cos(theta) * speed
      velocities[i * 3 + 1] = Math.abs(Math.sin(phi) * Math.sin(theta)) * speed * 0.9
      velocities[i * 3 + 2] = -Math.abs(Math.cos(phi)) * speed
      positions[i * 3] = position[0]
      positions[i * 3 + 1] = position[1]
      positions[i * 3 + 2] = position[2]
    }
    return { velocities, positions, t: 0 }
  }, [count, big, position])

  useEffect(() => {
    const timer = setTimeout(() => onEnd?.(id), life * 1000 + 100)
    return () => clearTimeout(timer)
  }, [id, life, onEnd])

  useFrame((_, dt) => {
    const geo = points.current?.geometry
    if (!geo) return
    sim.t += dt
    const pos = geo.attributes.position.array
    for (let i = 0; i < count; i++) {
      sim.velocities[i * 3 + 1] -= 7 * dt // gravity
      pos[i * 3] += sim.velocities[i * 3] * dt
      pos[i * 3 + 1] += sim.velocities[i * 3 + 1] * dt
      pos[i * 3 + 2] += sim.velocities[i * 3 + 2] * dt
    }
    geo.attributes.position.needsUpdate = true
    const mat = points.current.material
    mat.opacity = Math.max(0, 1 - sim.t / life)
  })

  return (
    <points ref={points}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[sim.positions, 3]} />
      </bufferGeometry>
      <pointsMaterial
        color={color}
        size={big ? 0.16 : 0.11}
        transparent
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  )
}

/** Floating "+N" text that rises out of the hole and unmounts. */
export function ScorePop({ id, position, text, color = '#fef3c7', big = false, onEnd }) {
  const group = useRef()
  const life = big ? 1.6 : 1.1

  useEffect(() => {
    const timer = setTimeout(() => onEnd?.(id), life * 1000)
    return () => clearTimeout(timer)
  }, [id, life, onEnd])

  useFrame((_, dt) => {
    if (group.current) group.current.position.y += dt * (big ? 1.0 : 0.8)
  })

  return (
    <group ref={group} position={position}>
      <Billboard>
        <Text
          fontSize={big ? 0.6 : 0.42}
          color={color}
          anchorX="center"
          anchorY="middle"
          outlineWidth={0.03}
          outlineColor="#0f172a"
        >
          {text}
        </Text>
      </Billboard>
    </group>
  )
}

/** DOM confetti for the game-over prize modal (pure CSS animation). */
export function ConfettiRain({ pieces = 60, gold = false }) {
  const items = useMemo(() => {
    const palette = gold
      ? ['#facc15', '#fbbf24', '#fde68a', '#f59e0b', '#fff7d6']
      : ['#38bdf8', '#a78bfa', '#f59e0b', '#34d399', '#f87171', '#facc15']
    return Array.from({ length: pieces }, (_, i) => ({
      left: Math.random() * 100,
      delay: Math.random() * 1.4,
      duration: 2.2 + Math.random() * 1.6,
      size: 6 + Math.random() * 7,
      color: palette[i % palette.length],
      spin: Math.random() > 0.5 ? 1 : -1,
    }))
  }, [pieces, gold])
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {items.map((p, i) => (
        <span
          key={i}
          className="confetti-piece"
          style={{
            left: `${p.left}%`,
            width: `${p.size}px`,
            height: `${p.size * 0.45}px`,
            backgroundColor: p.color,
            animationDelay: `${p.delay}s`,
            animationDuration: `${p.duration}s`,
            '--spin-dir': p.spin,
          }}
        />
      ))}
    </div>
  )
}
