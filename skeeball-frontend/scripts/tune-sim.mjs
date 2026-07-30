// Headless power-sweep of a level (tilted deck + curved ramp).
// Mirrors computeGeometry/computeRampSegments/SkeeballWorld colliders and
// PlayBall's launch math, then reports where each power lands.
// Run: node scripts/tune-sim.mjs [aimRadians] [presetKey]
// NOTE: the patrolling DeckSweeper is NOT modeled — results are best-case timing.
import RAPIER from '@dimforge/rapier3d-compat'
import { LEVEL_PRESETS } from '../src/config/presets.js'
import { computeBackstopSegments, computeGeometry, computeRampSegments, GRAVITY_Y } from '../src/config/geometry.js'

await RAPIER.init()

const PRESET = process.argv[3] ?? 'classic'
const level = LEVEL_PRESETS[PRESET].level
const geom = computeGeometry(level)
const { lane, ramp, backboard, ball } = level
const tilt = geom.tilt
const PIVOT = { y: ramp.rise, z: geom.backboardZ }
const POCKET_DEPTH = 1.2
const GRAVITY = GRAVITY_Y
const AIM = Number(process.argv[2] ?? 0)

// --- quaternion helpers (x-axis tilt composed with local z rotations) ---
const qx = (a) => ({ x: Math.sin(a / 2), y: 0, z: 0, w: Math.cos(a / 2) })
const qz = (a) => ({ x: 0, y: 0, z: Math.sin(a / 2), w: Math.cos(a / 2) })
function qmul(a, b) {
  return {
    w: a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
    x: a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
    y: a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
    z: a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
  }
}
/** Rotate a deck-local point (old vertical-board coords) into world. */
function deckToWorld([x, y, z]) {
  const ly = y - PIVOT.y
  const lz = z - PIVOT.z
  const c = Math.cos(tilt)
  const s = Math.sin(tilt)
  return [x, PIVOT.y + ly * c - lz * s, PIVOT.z + ly * s + lz * c]
}
/** World → deck-local (for hole-entry detection). */
function worldToDeck([x, y, z]) {
  const wy = y - PIVOT.y
  const wz = z - PIVOT.z
  const c = Math.cos(tilt)
  const s = Math.sin(tilt)
  return [x, PIVOT.y + wy * c + wz * s, PIVOT.z - wy * s + wz * c]
}

const world = new RAPIER.World({ x: 0, y: GRAVITY, z: 0 })
function cuboid(pos, rot, half, friction, restitution) {
  const body = world.createRigidBody(RAPIER.RigidBodyDesc.fixed())
  const desc = RAPIER.ColliderDesc.cuboid(...half)
    .setFriction(friction)
    .setRestitution(restitution)
    .setTranslation(...pos)
  if (rot) desc.setRotation(rot)
  world.createCollider(desc, body)
}
const deckCuboid = (pos, localRot, half, f, r) =>
  cuboid(deckToWorld(pos), localRot ? qmul(qx(tilt), localRot) : qx(tilt), half, f, r)

// lane + gutters + safety floor (world frame)
cuboid([0, 0, 0], null, [lane.width / 2, lane.thickness / 2, lane.length / 2], 0.9, 0.25)
for (const side of [-1, 1]) {
  cuboid([(side * (lane.width + 0.4)) / 2, lane.thickness / 2 + 0.1, (ramp.length + ramp.gap) / 2],
    null, [0.2, 0.25, (lane.length + ramp.length + ramp.gap) / 2], 0.9, 0.25)
}
cuboid([0, -3.2, 4], null, [15, 0.15, 20], 0.9, 0.25)

// curved ramp (world frame)
for (const s of computeRampSegments(lane, ramp)) {
  cuboid(s.position, qx(-s.angle), [lane.width / 2, lane.thickness / 2, s.length / 2], 0.9, 0.25)
}

// deck: board segments, rims, pockets (deck frame → world)
const BOARD = geom.BOARD
let rects = [{ ...BOARD }]
for (const h of level.targets) {
  const hx0 = Math.max(h.x - h.r, BOARD.x0), hx1 = Math.min(h.x + h.r, BOARD.x1)
  const hy0 = Math.max(h.y - h.r, BOARD.y0), hy1 = Math.min(h.y + h.r, BOARD.y1)
  const next = []
  for (const r of rects) {
    if (hx1 <= r.x0 || hx0 >= r.x1 || hy1 <= r.y0 || hy0 >= r.y1) { next.push(r); continue }
    if (hx0 > r.x0) next.push({ x0: r.x0, x1: hx0, y0: r.y0, y1: r.y1 })
    if (hx1 < r.x1) next.push({ x0: hx1, x1: r.x1, y0: r.y0, y1: r.y1 })
    const ix0 = Math.max(hx0, r.x0), ix1 = Math.min(hx1, r.x1)
    if (hy0 > r.y0) next.push({ x0: ix0, x1: ix1, y0: r.y0, y1: hy0 })
    if (hy1 < r.y1) next.push({ x0: ix0, x1: ix1, y0: hy1, y1: r.y1 })
  }
  rects = next
}
for (const s of rects.filter((r) => r.x1 - r.x0 > 0.01 && r.y1 - r.y0 > 0.01)) {
  deckCuboid([(s.x0 + s.x1) / 2, (s.y0 + s.y1) / 2, geom.backboardZ], null,
    [(s.x1 - s.x0) / 2, (s.y1 - s.y0) / 2, backboard.thickness / 2], 0.9, 0.25)
}
const RIM_SEGMENTS = 10
for (const hole of level.targets) {
  const chord = 2 * hole.r * Math.sin(Math.PI / RIM_SEGMENTS) + 0.06
  for (let i = 0; i < RIM_SEGMENTS; i++) {
    const theta = (i / RIM_SEGMENTS) * Math.PI * 2
    deckCuboid(
      [hole.x + hole.r * Math.cos(theta), hole.y + hole.r * Math.sin(theta), geom.backboardZ],
      qz(theta + Math.PI / 2), [chord / 2, 0.07, backboard.thickness], 0.6, 0.2)
  }
  if (hole.points >= 300) {
    for (const s of computeBackstopSegments(hole, geom.boardFaceZ)) {
      deckCuboid(s.position, qz(s.rotation[2]), s.args, 0.8, 0.08)
    }
  }
  const half = hole.r + 0.05
  const z1 = geom.boardBackZ + POCKET_DEPTH
  const zc = (geom.boardBackZ + z1) / 2
  const POCKET_WALL = 0.08
  // pass-through pockets (no back wall) — mirror of SkeeballWorld
  for (const w of [
    { pos: [hole.x, hole.y - half - POCKET_WALL / 2, zc], size: [half * 2, POCKET_WALL, POCKET_DEPTH] },
    { pos: [hole.x, hole.y + half + POCKET_WALL / 2, zc], size: [half * 2, POCKET_WALL, POCKET_DEPTH] },
    { pos: [hole.x - half - POCKET_WALL / 2, hole.y, zc], size: [POCKET_WALL, half * 2, POCKET_DEPTH] },
    { pos: [hole.x + half + POCKET_WALL / 2, hole.y, zc], size: [POCKET_WALL, half * 2, POCKET_DEPTH] },
  ]) {
    deckCuboid(w.pos, null, w.size.map((v) => v / 2), 0.7, 0.2)
  }
}

function runShot(power, aim) {
  const body = world.createRigidBody(
    RAPIER.RigidBodyDesc.dynamic()
      .setTranslation(...geom.BALL_START)
      .setLinearDamping(0.08)
      .setAngularDamping(0.15)
      .setCcdEnabled(true))
  world.createCollider(
    RAPIER.ColliderDesc.ball(ball.radius).setMass(ball.mass)
      .setFriction(ball.friction).setRestitution(ball.restitution), body)

  const speed = ball.minSpeed + power * (ball.maxSpeed - ball.minSpeed)
  const up = ball.upBase + power * ball.upScale
  const dir = { x: Math.sin(aim), y: up, z: Math.cos(aim) }
  const len = Math.hypot(dir.x, dir.y, dir.z)
  body.setLinvel({ x: (dir.x / len) * speed, y: (dir.y / len) * speed, z: (dir.z / len) * speed }, true)

  let result = 'timeout'
  let maxDeckY = 0
  let xAtMax = 0
  for (let i = 0; i < 60 * 8; i++) {
    world.step()
    const t = body.translation()
    const [dx, dy, dz] = worldToDeck([t.x, t.y, t.z])
    if (dz > geom.boardFaceZ + 0.1) {
      if (dy > maxDeckY) { maxDeckY = dy; xAtMax = dx }
      const hit = level.targets.find((h) => Math.hypot(dx - h.x, dy - h.y) < h.r + 0.1)
      if (hit && dz > geom.boardBackZ) { result = `SCORE ${hit.points} (${hit.name})`; break }
    } else if (dz > geom.boardFaceZ - ball.radius) {
      if (dy > maxDeckY) { maxDeckY = dy; xAtMax = dx }
    }
    if (t.y < -2.5 || t.z > geom.missBounds.maxZ || t.z < geom.missBounds.minZ) { result = 'miss'; break }
    const v = body.linvel()
    if (i > 60 && Math.hypot(v.x, v.y, v.z) < 0.3) { result = 'stall'; break }
  }
  world.removeRigidBody(body)
  return { result, maxDeckY: maxDeckY.toFixed(2), xAtMax: xAtMax.toFixed(2) }
}

if (process.argv[2] === 'grid') {
  // Coverage check: sweep aim × power, count what each hole receives.
  const hits = new Map(level.targets.map((t) => [t.name, { n: 0, first: null }]))
  let total = 0
  let misses = 0
  for (let aim = -0.13; aim <= 0.1301; aim += 0.02) {
    for (let p = 0.1; p <= 1.001; p += 0.05) {
      total++
      const { result } = runShot(p, aim)
      const m = result.match(/^SCORE \d+ \((.+)\)$/)
      if (!m) {
        misses++
        continue
      }
      const h = hits.get(m[1])
      h.n++
      h.first ??= `aim ${aim.toFixed(2)} power ${p.toFixed(2)}`
    }
  }
  console.log(`preset=${PRESET} shots=${total} noscore=${misses} (${Math.round((misses / total) * 100)}%)`)
  for (const t of level.targets) {
    const h = hits.get(t.name)
    console.log(`${String(t.points).padStart(3)} ${t.name}: ${h.n} hits` +
      (h.first ? ` (first: ${h.first})` : '  ⚠️ UNREACHABLE'))
  }
} else {
  console.log(`aim=${AIM} preset=${PRESET} tilt=${tilt} gravity=${GRAVITY} maxSpeed=${ball.maxSpeed}`)
  for (let p = 0.1; p <= 1.001; p += 0.05) {
    const { result, maxDeckY, xAtMax } = runShot(p, AIM)
    console.log(`power=${p.toFixed(2)} peak=(x ${xAtMax}, y ${maxDeckY}) -> ${result}`)
  }
}
