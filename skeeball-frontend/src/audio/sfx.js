/**
 * Synthesized sound effects — Web Audio only, no asset files (keeps the
 * bundle self-contained). The AudioContext is created lazily on the first
 * user gesture (autoplay policy). Mute preference persists per browser.
 */
const MUTE_KEY = 'horusball-muted'

let ctx = null

function ac() {
  if (!ctx) {
    const AC = window.AudioContext || window.webkitAudioContext
    if (!AC) return null
    ctx = new AC()
  }
  if (ctx.state === 'suspended') ctx.resume()
  return ctx
}

export function isMuted() {
  try {
    return localStorage.getItem(MUTE_KEY) === '1'
  } catch {
    return false
  }
}

export function setMuted(muted) {
  try {
    localStorage.setItem(MUTE_KEY, muted ? '1' : '0')
  } catch {
    // Private-mode storage failure — sound state just won't persist.
  }
}

/** One enveloped oscillator note. */
function tone(a, { freq = 440, type = 'sine', at = 0, dur = 0.15, gain = 0.2, slideTo = null }) {
  const t0 = a.currentTime + at
  const osc = a.createOscillator()
  const g = a.createGain()
  osc.type = type
  osc.frequency.setValueAtTime(freq, t0)
  if (slideTo) osc.frequency.exponentialRampToValueAtTime(slideTo, t0 + dur)
  g.gain.setValueAtTime(0, t0)
  g.gain.linearRampToValueAtTime(gain, t0 + 0.012)
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur)
  osc.connect(g).connect(a.destination)
  osc.start(t0)
  osc.stop(t0 + dur + 0.05)
}

/** Enveloped white-noise burst through a filter (whoosh / thud bodies). */
function noise(a, { at = 0, dur = 0.3, gain = 0.15, filterFreq = 1200, filterType = 'lowpass', slideTo = null }) {
  const t0 = a.currentTime + at
  const buf = a.createBuffer(1, a.sampleRate * dur, a.sampleRate)
  const data = buf.getChannelData(0)
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1
  const src = a.createBufferSource()
  src.buffer = buf
  const filter = a.createBiquadFilter()
  filter.type = filterType
  filter.frequency.setValueAtTime(filterFreq, t0)
  if (slideTo) filter.frequency.exponentialRampToValueAtTime(slideTo, t0 + dur)
  const g = a.createGain()
  g.gain.setValueAtTime(gain, t0)
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur)
  src.connect(filter).connect(g).connect(a.destination)
  src.start(t0)
}

function play(fn) {
  if (isMuted()) return
  const a = ac()
  if (!a) return
  try {
    fn(a)
  } catch {
    // Audio glitches must never break the game.
  }
}

/** UI tick — aim/power lock. */
export function click() {
  play((a) => tone(a, { freq: 950, type: 'square', dur: 0.05, gain: 0.06 }))
}

/** Ball launch: pitch and length scale with power. */
export function launch(power = 0.5) {
  play((a) => {
    noise(a, { dur: 0.35 + power * 0.2, gain: 0.12, filterFreq: 400, slideTo: 2200 })
    tone(a, { freq: 90, type: 'sine', dur: 0.18, gain: 0.25, slideTo: 55 })
  })
}

/** Score ding — higher holes ring higher and longer; 300 gets a fanfare. */
export function score(points) {
  play((a) => {
    if (points >= 300) {
      // Golden-hole fanfare: rising major arpeggio + sparkle noise.
      const notes = [523.25, 659.25, 783.99, 1046.5, 1318.5]
      notes.forEach((f, i) =>
        tone(a, { freq: f, type: 'triangle', at: i * 0.09, dur: 0.5, gain: 0.16 }))
      noise(a, { at: 0.15, dur: 0.7, gain: 0.05, filterFreq: 6000, filterType: 'highpass' })
      return
    }
    const base = points >= 150 ? 880 : points >= 100 ? 659.25 : 523.25
    tone(a, { freq: base, type: 'triangle', dur: 0.35, gain: 0.18 })
    tone(a, { freq: base * 1.5, type: 'triangle', at: 0.08, dur: 0.4, gain: 0.14 })
  })
}

/** Metallic clank — ball vs the patrolling guard bar. */
let lastClank = 0
export function clank() {
  const now = performance.now()
  if (now - lastClank < 150) return // grinding contact spams collision events
  lastClank = now
  play((a) => {
    tone(a, { freq: 2200, type: 'square', dur: 0.08, gain: 0.05, slideTo: 900 })
    noise(a, { dur: 0.12, gain: 0.08, filterFreq: 3500, filterType: 'highpass' })
  })
}

/** Soft womp for a missed / skipped ball. */
export function miss() {
  play((a) => {
    tone(a, { freq: 180, type: 'sine', dur: 0.3, gain: 0.12, slideTo: 70 })
    noise(a, { dur: 0.15, gain: 0.05, filterFreq: 300 })
  })
}

/** Single firework pop for the end-of-game celebration bursts. */
export function pop() {
  play((a) => {
    tone(a, { freq: 300 + Math.random() * 500, type: 'triangle', dur: 0.25, gain: 0.1, slideTo: 90 })
    noise(a, { dur: 0.3, gain: 0.06, filterFreq: 5000, filterType: 'highpass' })
  })
}

/** Game-over sting: win = warm resolve; no prize = gentle descending pair. */
export function gameOver(won) {
  play((a) => {
    if (won) {
      ;[392, 523.25, 659.25].forEach((f, i) =>
        tone(a, { freq: f, type: 'triangle', at: i * 0.12, dur: 0.6, gain: 0.15 }))
    } else {
      tone(a, { freq: 330, type: 'triangle', dur: 0.35, gain: 0.12 })
      tone(a, { freq: 262, type: 'triangle', at: 0.18, dur: 0.5, gain: 0.12 })
    }
  })
}
