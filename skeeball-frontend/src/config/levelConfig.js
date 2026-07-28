/**
 * HORUSBALL admin level editor configuration.
 * DEFAULT_LEVEL mirrors the historically hard-coded geometry/physics values;
 * sanitizeLevel defensively clamps any external input back into valid ranges.
 */

/**
 * Layout philosophy (2026-07 rebuild): the target deck is TILTED back
 * (backboard.tilt, radians from vertical) so the ball lands on it and rolls —
 * the easy 50 sits low-center right in the natural landing path, the 100s
 * flank mid-deck, the 150 sits high-center, and the two golden 300s live in
 * the top corners where only a committed full-power shot reaches. A ball that
 * fails a high hole rolls back down across the lower holes — easy small
 * scores, rare jackpots.
 */
export const DEFAULT_LEVEL = {
  targets: [
    { name: '中央之門 50', points: 50, r: 0.85, x: 0, y: 3.0, color: '#38bdf8' },
    { name: '左聖印 100', points: 100, r: 0.7, x: -1.5, y: 3.7, color: '#a78bfa' },
    { name: '右聖印 100', points: 100, r: 0.7, x: 1.5, y: 3.7, color: '#a78bfa' },
    { name: '帝皇之眼 150', points: 150, r: 0.66, x: 0, y: 4.5, color: '#f59e0b' },
    { name: '荷魯斯之眼 L', points: 300, r: 0.62, x: -1.85, y: 5.2, color: '#facc15' },
    { name: '荷魯斯之眼 R', points: 300, r: 0.62, x: 1.85, y: 5.2, color: '#facc15' },
  ],
  lane: { width: 4, length: 12, thickness: 0.3 },
  ramp: { length: 3.5, rise: 2.2, gap: 1.0, curve: 0.45 },
  backboard: { height: 4, thickness: 0.25, tilt: 0.62 },
  ball: {
    radius: 0.4,
    mass: 2.5,
    friction: 0.9,
    restitution: 0.22,
    minSpeed: 13,
    maxSpeed: 24,
    upBase: 0.06,
    upScale: 0.1,
  },
  aim: { maxAngle: 0.14, oscSpeed: 1.6 },
  textures: {
    ballUrl: '/static/game/tex/wh_ball.jpg',
    laneUrl: '/static/game/tex/wh_lane.jpg',
    backgroundUrl: '/static/game/tex/wh_space.jpg',
  },
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
  // http(s) or site-relative (the bundled /static/game/tex/* skins)
  return /^(https?:\/\/|\/[^/])/.test(value) ? value : fallback
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

  const minSpeed = num(ballSrc.minSpeed, d.ball.minSpeed, 0.5, 20)
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
      tilt: num(boardSrc.tilt, d.backboard.tilt, 0, 1.2),
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
      ballUrl: url(texSrc.ballUrl, d.textures.ballUrl),
      laneUrl: url(texSrc.laneUrl, d.textures.laneUrl),
      backgroundUrl: url(texSrc.backgroundUrl, d.textures.backgroundUrl),
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
