/**
 * Level presets — alternate arenas sharing the ball/aim/texture setup of
 * DEFAULT_LEVEL. Preview any of them on /game?level=<key> (client-side
 * override, sessions still count); the served default stays whatever the
 * server ships. Tuned with scripts/tune-sim.mjs (pass the key as argv[3]).
 */
import { DEFAULT_LEVEL } from './levelConfig.js'

const base = () => JSON.parse(JSON.stringify(DEFAULT_LEVEL))

/** 雙子疑陣 — the obvious center shot is a 10-point trap; value lives on the
 * flanks and in the 200/300 column stacked above the trap. */
function decoy() {
  const l = base()
  l.targets = [
    { name: '疑陣之心 10', points: 10, r: 0.8, x: 0, y: 3.1, color: '#64748b' },
    { name: '左隘口 50', points: 50, r: 0.72, x: -1.7, y: 2.9, color: '#38bdf8' },
    { name: '右隘口 50', points: 50, r: 0.72, x: 1.7, y: 2.9, color: '#38bdf8' },
    { name: '左聖印 100', points: 100, r: 0.62, x: -1.5, y: 4.35, color: '#a78bfa' },
    { name: '右聖印 100', points: 100, r: 0.62, x: 1.5, y: 4.35, color: '#a78bfa' },
    { name: '帝皇之眼 200', points: 200, r: 0.66, x: -0.85, y: 5.35, color: '#f59e0b' },
    { name: '荷魯斯之眼 300', points: 300, r: 0.58, x: 0.85, y: 5.6, color: '#facc15' },
  ]
  return l
}

/** 天梯試煉 — a zigzag staircase: each rung offsets to the other side so it
 * has a clean approach lane (a straight column would let the lower rims eat
 * every climb). Higher rung = harder aim+power combo. */
function ladder() {
  const l = base()
  l.targets = [
    { name: '起始之階 50', points: 50, r: 0.72, x: -0.75, y: 2.9, color: '#38bdf8' },
    { name: '第二階 100', points: 100, r: 0.66, x: 0.75, y: 3.6, color: '#a78bfa' },
    { name: '第三階 150', points: 150, r: 0.62, x: -0.75, y: 4.4, color: '#f59e0b' },
    { name: '荷魯斯之巔 300', points: 300, r: 0.58, x: 0.75, y: 5.3, color: '#facc15' },
    { name: '左護翼 50', points: 50, r: 0.65, x: -1.95, y: 3.4, color: '#38bdf8' },
    { name: '右護翼 50', points: 50, r: 0.65, x: 1.95, y: 3.4, color: '#38bdf8' },
  ]
  return l
}

/** 荷魯斯之怒 — the 300 sits mid-deck right on the guard bar's patrol line:
 * close and reachable, brutally timed. No easy 50 anywhere. */
function fury() {
  const l = base()
  l.targets = [
    { name: '左靜滯 20', points: 20, r: 0.72, x: -1.05, y: 3.0, color: '#64748b' },
    { name: '右靜滯 20', points: 20, r: 0.72, x: 1.05, y: 3.0, color: '#64748b' },
    { name: '怒火之眼 300', points: 300, r: 0.62, x: 0, y: 4.35, color: '#facc15' },
    { name: '左怒濤 150', points: 150, r: 0.6, x: -1.15, y: 5.25, color: '#f87171' },
    { name: '右怒濤 150', points: 150, r: 0.6, x: 1.15, y: 5.25, color: '#f87171' },
  ]
  return l
}

export const LEVEL_PRESETS = {
  classic: { name: '經典聖殿', level: DEFAULT_LEVEL },
  decoy: { name: '雙子疑陣', level: decoy() },
  ladder: { name: '天梯試煉', level: ladder() },
  fury: { name: '荷魯斯之怒', level: fury() },
}
