// Headless repro of the skeeball world physics (debug — not shipped).
import RAPIER from '@dimforge/rapier3d-compat'
await RAPIER.init()

const LANE = { width: 4, length: 12, thickness: 0.3 }
const RAMP = { length: 3.5, rise: 2.2 }
const BACKBOARD = { width: LANE.width + 1, height: 4, thickness: 0.25 }
const rampAngle = Math.atan2(RAMP.rise, RAMP.length)
const rampSlope = Math.hypot(RAMP.rise, RAMP.length)
const rampCenterZ = LANE.length / 2 + RAMP.length / 2
const rampTopZ = LANE.length / 2 + RAMP.length
const backboardZ = rampTopZ + BACKBOARD.thickness / 2
const boardBackZ = backboardZ + BACKBOARD.thickness / 2
const BOARD = { x0: -2.5, x1: 2.5, y0: RAMP.rise, y1: RAMP.rise + BACKBOARD.height }
const TARGETS = [
  { name: 'Outer', points: 50, r: 0.9, x: 0, y: 3.2 },
  { name: 'Middle', points: 100, r: 0.75, x: -1.7, y: 2.95 },
  { name: 'Inner', points: 150, r: 0.6, x: 1.7, y: 3.0 },
  { name: 'ApexL', points: 300, r: 0.52, x: -1.95, y: 4.35 },
  { name: 'ApexR', points: 300, r: 0.52, x: 1.95, y: 4.35 },
]
const POCKET_DEPTH = 1.2
const POCKET_WALL = 0.08
const RIM_SEGMENTS = 10

function computeBoardSegments(holes) {
  let rects = [{ ...BOARD }]
  for (const h of holes) {
    const hx0 = Math.max(h.x - h.r, BOARD.x0)
    const hx1 = Math.min(h.x + h.r, BOARD.x1)
    const hy0 = Math.max(h.y - h.r, BOARD.y0)
    const hy1 = Math.min(h.y + h.r, BOARD.y1)
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
  return rects.filter((r) => r.x1 - r.x0 > 0.01 && r.y1 - r.y0 > 0.01)
}

const world = new RAPIER.World({ x: 0, y: -9.81, z: 0 })
const fixed = (friction = 0.9, restitution = 0.25) =>
  world.createRigidBody(RAPIER.RigidBodyDesc.fixed().setLinearDamping(0).setAngularDamping(0)) &&
  { friction, restitution }
function cuboid(pos, rot, half, friction = 0.9, restitution = 0.25) {
  const body = world.createRigidBody(RAPIER.RigidBodyDesc.fixed())
  const desc = RAPIER.ColliderDesc.cuboid(...half)
    .setFriction(friction)
    .setRestitution(restitution)
    .setTranslation(pos[0], pos[1], pos[2])
  if (rot) desc.setRotation(rot)
  world.createCollider(desc, body)
  return body
}

// lane
cuboid([0, 0, 0], null, [LANE.width / 2, LANE.thickness / 2, LANE.length / 2])
// gutters
for (const side of [-1, 1]) {
  cuboid([(side * (LANE.width + 0.4)) / 2, LANE.thickness / 2 + 0.1, RAMP.length / 2], null, [0.2, 0.25, (LANE.length + RAMP.length) / 2])
}
// ramp (rotated about x by -rampAngle)
{
  const q = new RAPIER.Quaternion(0, 0, 0, 1)
  const angle = -rampAngle
  const rot = { x: Math.sin(angle / 2), y: 0, z: 0, w: Math.cos(angle / 2) }
  cuboid([0, RAMP.rise / 2, rampCenterZ], rot, [LANE.width / 2, LANE.thickness / 2, rampSlope / 2])
  void q
}
// board segments
for (const s of computeBoardSegments(TARGETS)) {
  cuboid([(s.x0 + s.x1) / 2, (s.y0 + s.y1) / 2, backboardZ], null, [(s.x1 - s.x0) / 2, (s.y1 - s.y0) / 2, BACKBOARD.thickness / 2])
}
// rims
for (const hole of TARGETS) {
  const chord = 2 * hole.r * Math.sin(Math.PI / RIM_SEGMENTS) + 0.06
  for (let i = 0; i < RIM_SEGMENTS; i++) {
    const theta = (i / RIM_SEGMENTS) * Math.PI * 2
    const rot = { x: 0, y: 0, z: Math.sin((theta + Math.PI / 2) / 2), w: Math.cos((theta + Math.PI / 2) / 2) }
    cuboid(
      [hole.x + hole.r * Math.cos(theta), hole.y + hole.r * Math.sin(theta), backboardZ],
      rot,
      [chord / 2, 0.07, BACKBOARD.thickness],
      0.6,
      0.35
    )
  }
}
// pockets
for (const hole of TARGETS) {
  const half = hole.r + 0.05
  const z1 = boardBackZ + POCKET_DEPTH
  const zc = (boardBackZ + z1) / 2
  const walls = [
    { pos: [hole.x, hole.y - half - POCKET_WALL / 2, zc], size: [half * 2 + POCKET_WALL * 2, POCKET_WALL, POCKET_DEPTH] },
    { pos: [hole.x, hole.y + half + POCKET_WALL / 2, zc], size: [half * 2 + POCKET_WALL * 2, POCKET_WALL, POCKET_DEPTH] },
    { pos: [hole.x - half - POCKET_WALL / 2, hole.y, zc], size: [POCKET_WALL, half * 2, POCKET_DEPTH] },
    { pos: [hole.x + half + POCKET_WALL / 2, hole.y, zc], size: [POCKET_WALL, half * 2, POCKET_DEPTH] },
    { pos: [hole.x, hole.y, z1 + POCKET_WALL / 2], size: [half * 2 + POCKET_WALL * 2, half * 2 + POCKET_WALL * 2, POCKET_WALL] },
  ]
  for (const w of walls) cuboid(w.pos, null, w.size.map((v) => v / 2), 0.7, 0.2)
}

// ball: launch params from CLI: node physics-repro.mjs <power> <maxSpeed> <linDamp> <upBase> <upScale> <angle>
const power = Number(process.argv[2] ?? 1)
const MAX_SPEED = Number(process.argv[3] ?? 12)
const LIN_DAMP = Number(process.argv[4] ?? 0.2)
const UP_BASE = Number(process.argv[5] ?? 0.05)
const UP_SCALE = Number(process.argv[6] ?? 0.1)
const AIM = Number(process.argv[7] ?? 0)
const ball = world.createRigidBody(
  RAPIER.RigidBodyDesc.dynamic()
    .setTranslation(0, LANE.thickness / 2 + 0.45, -LANE.length / 2 + 1.2)
    .setLinearDamping(LIN_DAMP)
    .setAngularDamping(0.5)
    .setCcdEnabled(true)
)
world.createCollider(
  RAPIER.ColliderDesc.ball(0.45).setMass(2.5).setFriction(1.2).setRestitution(0.3),
  ball
)
const speed = 1.8 + power * (MAX_SPEED - 1.8)
const up = UP_BASE + power * UP_SCALE
const len = Math.hypot(Math.sin(AIM), up, Math.cos(AIM))
ball.wakeUp()
ball.applyImpulse(
  {
    x: (Math.sin(AIM) / len) * speed * 2.5,
    y: (up / len) * speed * 2.5,
    z: (Math.cos(AIM) / len) * speed * 2.5,
  },
  true
)

// Diagnostic: which colliders touch the spawn sphere?
world.step()
{
  const t = ball.translation()
  console.log('after first step:', t.x.toFixed(3), t.y.toFixed(3), t.z.toFixed(3))
}
for (let i = 1; i <= 240; i++) {
  world.step()
  if (i % 20 === 0) {
    const t = ball.translation()
    const v = ball.linvel()
    console.log(
      `t=${(i / 60).toFixed(2)}s pos=(${t.x.toFixed(2)}, ${t.y.toFixed(2)}, ${t.z.toFixed(2)}) v=(${v.x.toFixed(1)}, ${v.y.toFixed(1)}, ${v.z.toFixed(1)})`
    )
  }
}
