/**
 * HORUSBALL admin level editor configuration.
 * DEFAULT_LEVEL mirrors the historically hard-coded geometry/physics values;
 * sanitizeLevel defensively clamps any external input back into valid ranges.
 */

export const DEFAULT_LEVEL = {
  targets: [
    { name: 'Outer Ring', points: 50, r: 0.9, x: 0, y: 3.2, color: '#38bdf8' },
    { name: 'Middle Ring', points: 100, r: 0.75, x: -1.7, y: 2.95, color: '#a78bfa' },
    { name: 'Inner Ring', points: 150, r: 0.75, x: 1.7, y: 3.0, color: '#f59e0b' },
    { name: 'Apex Corner L', points: 300, r: 0.65, x: -1.95, y: 4.35, color: '#facc15' },
    { name: 'Apex Corner R', points: 300, r: 0.65, x: 1.95, y: 4.35, color: '#facc15' },
  ],
  lane: { width: 4, length: 12, thickness: 0.3 },
  ramp: { length: 3.5, rise: 2.2, gap: 2, curve: 0.3 },
  backboard: { height: 4, thickness: 0.25 },
  ball: {
    radius: 0.45,
    mass: 2.5,
    friction: 1.2,
    restitution: 0.3,
    minSpeed: 1.8,
    maxSpeed: 24,
    upBase: 0.05,
    upScale: 0.1,
  },
  aim: { maxAngle: 0.38, oscSpeed: 1.6 },
  textures: { ballUrl: '', laneUrl: '', backgroundUrl: '' },
}

const STORAGE_KEY = 'horusball-level'

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value))
}

function num(value, fallback, min, max) {
  const n = typeof value === 'string' ? Number(value) : value
  if (typeof n !== 'number' || !Number.isFinite(n)) return fallback
  return clamp(n, min, max)
}

function intNum(value, fallback, min, max) {
  return Math.round(num(value, fallback, min, max))
}

function color(value, fallback) {
  return typeof value === 'string' && /^#[0-9a-fA-F]{6}$/.test(value) ? value.toLowerCase() : fallback
}

function url(value, fallback) {
  if (value === '' || value == null) return ''
  if (typeof value !== 'string' || value.length > 500) return fallback
  return /^https?:\/\//.test(value) ? value : fallback
}

function sanitizeTarget(raw, fallback) {
  const src = raw && typeof raw === 'object' ? raw : {}
  return {
    name: typeof src.name === 'string' && src.name.trim() ? src.name.slice(0, 40) : fallback.name,
    points: intNum(src.points, fallback.points, 10, 999),
    r: num(src.r, fallback.r, 0.2, 1.2),
    x: num(src.x, fallback.x, -2.4, 2.4),
    y: num(src.y, fallback.y, 2.2, 6.0),
    color: color(src.color, fallback.color),
  }
}

/** Deep-merge `raw` over DEFAULT_LEVEL, clamping every field into range. */
export function sanitizeLevel(raw) {
  const d = DEFAULT_LEVEL
  const src = raw && typeof raw === 'object' ? raw : {}

  let targets = Array.isArray(src.targets) ? src.targets.slice(0, 8) : []
  targets = targets.map((t, i) => sanitizeTarget(t, d.targets[i % d.targets.length]))
  if (targets.length === 0) targets = d.targets.map((t) => ({ ...t }))

  const laneSrc = src.lane && typeof src.lane === 'object' ? src.lane : {}
  const rampSrc = src.ramp && typeof src.ramp === 'object' ? src.ramp : {}
  const boardSrc = src.backboard && typeof src.backboard === 'object' ? src.backboard : {}
  const ballSrc = src.ball && typeof src.ball === 'object' ? src.ball : {}
  const aimSrc = src.aim && typeof src.aim === 'object' ? src.aim : {}
  const texSrc = src.textures && typeof src.textures === 'object' ? src.textures : {}

  const minSpeed = num(ballSrc.minSpeed, d.ball.minSpeed, 0.5, 10)
  return {
    targets,
    lane: {
      width: num(laneSrc.width, d.lane.width, 2, 6),
      length: num(laneSrc.length, d.lane.length, 6, 20),
      thickness: num(laneSrc.thickness, d.lane.thickness, 0.1, 0.6),
    },
    ramp: {
      length: num(rampSrc.length, d.ramp.length, 1.5, 6),
      rise: num(rampSrc.rise, d.ramp.rise, 0.5, 4),
      gap: num(rampSrc.gap, d.ramp.gap, 0, 4),
      curve: num(rampSrc.curve, d.ramp.curve, 0, 1),
    },
    backboard: {
      height: num(boardSrc.height, d.backboard.height, 2, 8),
      thickness: num(boardSrc.thickness, d.backboard.thickness, 0.1, 0.5),
    },
    ball: {
      radius: num(ballSrc.radius, d.ball.radius, 0.2, 0.6),
      mass: num(ballSrc.mass, d.ball.mass, 0.5, 10),
      friction: num(ballSrc.friction, d.ball.friction, 0, 2),
      restitution: num(ballSrc.restitution, d.ball.restitution, 0, 1),
      minSpeed,
      maxSpeed: clamp(num(ballSrc.maxSpeed, d.ball.maxSpeed, 0, 40), minSpeed, 40),
      upBase: num(ballSrc.upBase, d.ball.upBase, 0, 0.3),
      upScale: num(ballSrc.upScale, d.ball.upScale, 0, 0.5),
    },
    aim: {
      maxAngle: num(aimSrc.maxAngle, d.aim.maxAngle, 0.05, 0.8),
      oscSpeed: num(aimSrc.oscSpeed, d.aim.oscSpeed, 0.2, 5),
    },
    textures: {
      ballUrl: url(texSrc.ballUrl, ''),
      laneUrl: url(texSrc.laneUrl, ''),
      backgroundUrl: url(texSrc.backgroundUrl, ''),
    },
  }
}

export function loadLevelLocal() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? sanitizeLevel(JSON.parse(raw)) : null
  } catch {
    return null
  }
}

export function saveLevelLocal(level) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sanitizeLevel(level)))
  } catch {
    // Storage unavailable (private mode, quota) — ignore.
  }
}
