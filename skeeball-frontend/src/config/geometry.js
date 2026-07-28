/**
 * Pure level geometry — no React/JSX so headless tools (scripts/tune-sim.mjs)
 * can import the exact math the game world uses.
 */
import { DEFAULT_LEVEL } from './levelConfig.js'

export const POCKET_DEPTH = 1.2
export const RAMP_SEGMENTS = 14
// Well above earth-normal: at toy scale (12m lane) real gravity reads as
// floaty slow-motion. Canvas and tune-sim both use this.
export const GRAVITY_Y = -22

/**
 * Split the ramp into N box segments following a power-curve profile:
 * y = rise · t^(1 + 2·curve). curve 0 = straight incline; higher values stay
 * flatter at the bottom and launch steeper at the lip (ski-jump shape).
 * The same segments drive both the meshes and the physics colliders.
 */
export function computeRampSegments(lane, ramp) {
  const exponent = 1 + 2 * ramp.curve
  const z0 = lane.length / 2
  const y = (t) => ramp.rise * Math.pow(t, exponent)
  const segs = []
  for (let i = 0; i < RAMP_SEGMENTS; i++) {
    const t0 = i / RAMP_SEGMENTS
    const t1 = (i + 1) / RAMP_SEGMENTS
    const dz = (t1 - t0) * ramp.length
    const dy = y(t1) - y(t0)
    segs.push({
      position: [0, (y(t0) + y(t1)) / 2, z0 + ((t0 + t1) / 2) * ramp.length],
      angle: Math.atan2(dy, dz),
      length: Math.hypot(dz, dy) + 0.02, // slight overlap so segments don't gap
    })
  }
  return segs
}

export const BACKSTOP_SEGMENTS = 7

/**
 * Raised guard arc over the top half of a jackpot hole (the ring guards of a
 * real skeeball machine): a climbing ball that reaches the hole is caught by
 * the arc, killed of its speed, and funneled back down into the opening —
 * reaching the corner is the skill; the arc converts arrival into capture.
 */
export function computeBackstopSegments(hole, boardFaceZ, wallHeight = 0.5) {
  const radius = hole.r + 0.3
  const arc = Math.PI * 0.78 // top ~140° of the circle
  const start = Math.PI / 2 - arc / 2
  const chord = 2 * radius * Math.sin(arc / BACKSTOP_SEGMENTS / 2) + 0.05
  return Array.from({ length: BACKSTOP_SEGMENTS }, (_, i) => {
    const theta = start + ((i + 0.5) / BACKSTOP_SEGMENTS) * arc
    return {
      position: [
        hole.x + radius * Math.cos(theta),
        hole.y + radius * Math.sin(theta),
        boardFaceZ - wallHeight / 2,
      ],
      rotation: [0, 0, theta + Math.PI / 2],
      args: [chord / 2, 0.07, wallHeight / 2], // half-extents (collider)
    }
  })
}

/**
 * Pure geometry derivation from a level config. Everything the world,
 * aim arrow, preview ball and play ball need, computed in one place.
 */
export function computeGeometry(level = DEFAULT_LEVEL) {
  const { lane, ramp, backboard, ball } = level
  const rampTopZ = lane.length / 2 + ramp.length
  // Gap between the ramp lip and the backboard: the ball flies it ballistically.
  const backboardZ = rampTopZ + ramp.gap + backboard.thickness / 2
  const boardCenterY = ramp.rise + backboard.height / 2
  const boardFaceZ = backboardZ - backboard.thickness / 2
  const boardBackZ = backboardZ + backboard.thickness / 2
  // Deck tilt (radians from vertical): the whole board group is rotated back
  // around its bottom edge (pivot line y=ramp.rise, z=backboardZ) so the ball
  // lands on the face and rolls across the holes.
  const tilt = backboard.tilt ?? 0

  // Board is one meter wider than the lane; holes sit in the band the ball
  // can physically reach off the ramp lip, apex corners higher.
  const boardWidth = lane.width + 1
  const BOARD = { x0: -boardWidth / 2, x1: boardWidth / 2, y0: ramp.rise, y1: ramp.rise + backboard.height }

  const BALL_START = [0, lane.thickness / 2 + ball.radius, -lane.length / 2 + 1.2]

  // Stray-ball kill bounds, scaled to the arena (tilt pushes the deck top
  // and its pockets further back in z).
  const missBounds = {
    minY: -2.5,
    maxZ: boardBackZ + backboard.height * Math.sin(tilt) + POCKET_DEPTH + 1,
    minZ: -(lane.length - 3),
    maxAbsX: lane.width * 2,
    // Rolling backward is a natural part of play ON the deck (a failed high
    // shot rolls down across the lower holes) — only before the deck does
    // backward motion mean the ball is hopeless.
    backwardZ: rampTopZ,
  }

  /** Board-plane point (board coords x, y + offset from the face) → world. */
  const boardPoint = (x, y, dz = 0) => {
    const cos = Math.cos(tilt)
    const sin = Math.sin(tilt)
    const ly = y - ramp.rise
    const lz = boardFaceZ + dz - backboardZ
    return [x, ramp.rise + ly * cos - lz * sin, backboardZ + ly * sin + lz * cos]
  }

  return {
    lane,
    ramp,
    backboard,
    tilt,
    rampTopZ,
    backboardZ,
    boardCenterY,
    boardFaceZ,
    boardBackZ,
    BOARD,
    BALL_START,
    missBounds,
    boardPoint,
  }
}
