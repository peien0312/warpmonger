import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Html, Stars } from '@react-three/drei'
import { Bloom, EffectComposer, Vignette } from '@react-three/postprocessing'
import { Physics } from '@react-three/rapier'
import * as THREE from 'three'
import SkeeballWorld, { computeGeometry, PreviewBall, SceneBackground } from './SkeeballWorld.jsx'
import { GRAVITY_Y } from '../config/geometry.js'
import AimArrow from './AimArrow.jsx'
import PlayBall from './PlayBall.jsx'
import { ConfettiRain, ScoreBurst, ScorePop } from './Effects.jsx'
import * as sfx from '../audio/sfx.js'
import { completeSession, postRoll, startSession } from '../api/skeeballApi.js'
import { DEFAULT_LEVEL } from '../config/levelConfig.js'
import TextureErrorBoundary from './TextureErrorBoundary.jsx'

const LOCAL_BALLS_PER_SESSION = 3
const BEST_KEY = 'horusball-best'

function loadBest() {
  try {
    return parseInt(localStorage.getItem(BEST_KEY), 10) || 0
  } catch {
    return 0
  }
}

const HOME_CAM = new THREE.Vector3(0, 5.5, -11)

/**
 * Camera rig with three behaviors:
 * - follow: while a ball is rolling, chase it from behind-above and look at
 *   it (speed reads faster and the deck action plays out up close);
 * - return: after the ball ends, glide back to the home framing;
 * - free: hold A/D to rotate, or drag (mouse/touch) — the container feeds
 *   pixel deltas through dragRef; dragging also tilts the camera height.
 */
function CameraRig({ target = [0, 1.5, 4], speed = 1.6, dragRef, ballRef, following }) {
  const keys = useRef({ a: false, d: false })
  const returning = useRef(false)
  const wasFollowing = useRef(false)

  useEffect(() => {
    const set = (key, value) => {
      const k = key.toLowerCase()
      if (k === 'a') keys.current.a = value
      if (k === 'd') keys.current.d = value
    }
    const onDown = (e) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      set(e.key, true)
    }
    const onUp = (e) => set(e.key, false)
    window.addEventListener('keydown', onDown)
    window.addEventListener('keyup', onUp)
    return () => {
      window.removeEventListener('keydown', onDown)
      window.removeEventListener('keyup', onUp)
    }
  }, [])

  useFrame(({ camera }, dt) => {
    const t = new THREE.Vector3(...target)
    const drag = dragRef?.current

    if (following && ballRef?.current) {
      wasFollowing.current = true
      const b = ballRef.current
      const desired = new THREE.Vector3(b.x * 0.5, b.y + 2.2, b.z - 4.5)
      camera.position.lerp(desired, 1 - Math.exp(-dt * 4.5))
      camera.lookAt(b.x, b.y + 0.3, b.z)
      if (drag) { drag.dx = 0; drag.dy = 0 }
      return
    }
    if (wasFollowing.current) {
      wasFollowing.current = false
      returning.current = true
    }

    const dir = (keys.current.a ? 1 : 0) - (keys.current.d ? 1 : 0)
    const dragged = drag && (drag.dx || drag.dy)
    if (dir || dragged) returning.current = false

    if (returning.current) {
      camera.position.lerp(HOME_CAM, 1 - Math.exp(-dt * 3.5))
      camera.lookAt(t)
      if (camera.position.distanceTo(HOME_CAM) < 0.15) returning.current = false
      return
    }

    let angle = dir * speed * Math.min(dt, 0.05)
    if (dragged) {
      angle += drag.dx * 0.006 // drag right → scene turns with the pointer
      camera.position.y = Math.min(10, Math.max(2, camera.position.y - drag.dy * 0.03))
      drag.dx = 0
      drag.dy = 0
    } else if (!dir) {
      return
    }
    const offset = camera.position.clone().sub(t)
    const cos = Math.cos(angle)
    const sin = Math.sin(angle)
    camera.position.set(
      t.x + offset.x * cos - offset.z * sin,
      camera.position.y,
      t.z + offset.x * sin + offset.z * cos
    )
    camera.lookAt(t)
  })

  return null
}

function LoadingFallback() {
  return (
    <Html center>
      <div className="flex flex-col items-center gap-2 text-slate-200">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-500 border-t-amber-400" />
        <span className="text-sm">載入中…</span>
      </div>
    </Html>
  )
}

/** Vertical power meter overlay; oscillates 0–100% until locked. */
function PowerMeter({ powerRef, onLock }) {
  const [display, setDisplay] = useState(0)

  useEffect(() => {
    let raf
    const start = performance.now()
    const tick = (now) => {
      // Triangle wave, ~1.6s round trip 0 → 100 → 0.
      const t = ((now - start) / 1600) % 2
      const value = t < 1 ? t : 2 - t
      powerRef.current = value
      setDisplay(value)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [powerRef])

  const pct = Math.round(display * 100)
  return (
    <div className="pointer-events-none absolute right-4 top-1/2 flex -translate-y-1/2 flex-col items-center gap-2">
      <div className="flex h-48 w-6 items-end overflow-hidden rounded-full border border-slate-600 bg-slate-900/80">
        <div
          className="w-full rounded-full bg-gradient-to-t from-emerald-400 via-amber-400 to-red-500 transition-none"
          style={{ height: `${pct}%` }}
        />
      </div>
      <span className="rounded bg-slate-900/80 px-2 py-0.5 text-xs font-semibold text-slate-100">
        {pct}%
      </span>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          onLock()
        }}
        className="pointer-events-auto rounded-full bg-amber-500 px-4 py-1.5 text-sm font-bold text-slate-950 shadow-lg hover:bg-amber-400"
      >
        Lock
      </button>
    </div>
  )
}

export default function SkeeballCanvas({ level = DEFAULT_LEVEL, freePlay = false, onGameComplete }) {
  const geom = useMemo(() => computeGeometry(level), [level])
  const ballUrl = level.textures.ballUrl
  const bgUrl = level.textures.backgroundUrl
  const [step, setStep] = useState('idle') // idle | aim | power | rolling | over
  const [score, setScore] = useState(0)
  const [ballsLeft, setBallsLeft] = useState(LOCAL_BALLS_PER_SESSION)
  const [lastHit, setLastHit] = useState(null)
  const [launch, setLaunch] = useState(null) // { angle, power, key }
  const [starting, setStarting] = useState(false)
  const [offlineReason, setOfflineReason] = useState(null) // null when synced
  const [completeResult, setCompleteResult] = useState(null) // { totalScore, golden, prize }
  const [fx, setFx] = useState([]) // live burst/pop effects
  const [best, setBest] = useState(loadBest)
  const [newBest, setNewBest] = useState(false)

  const aimRef = useRef(0)
  const powerRef = useRef(0)
  const stepRef = useRef(step)
  stepRef.current = step
  const sessionRef = useRef(null) // { sessionId, nonce } when synced
  const rollIndexRef = useRef(0)
  const scoredRef = useRef(false) // one score per launched ball
  const ballDoneRef = useRef(false) // one END (score OR miss/skip) per ball
  const syncedRef = useRef(false)
  const fxIdRef = useRef(0)

  // Drag-to-orbit vs click-to-lock: a press that travels >6px is a camera
  // drag (deltas stream through dragDeltaRef to CameraRig) and the click that
  // follows it is swallowed via wasDragRef.
  const pointerRef = useRef(null) // { lastX, lastY, startX, startY }
  const dragDeltaRef = useRef({ dx: 0, dy: 0 })
  const wasDragRef = useRef(false)
  const ballPosRef = useRef(null) // live ball position for the chase camera

  const onPointerDown = useCallback((e) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return
    pointerRef.current = { lastX: e.clientX, lastY: e.clientY, startX: e.clientX, startY: e.clientY }
    wasDragRef.current = false
  }, [])

  const onPointerMove = useCallback((e) => {
    const p = pointerRef.current
    if (!p) return
    if (!wasDragRef.current &&
        Math.hypot(e.clientX - p.startX, e.clientY - p.startY) > 6) {
      wasDragRef.current = true
    }
    if (wasDragRef.current) {
      dragDeltaRef.current.dx += e.clientX - p.lastX
      dragDeltaRef.current.dy += e.clientY - p.lastY
    }
    p.lastX = e.clientX
    p.lastY = e.clientY
  }, [])

  const onPointerEnd = useCallback(() => {
    pointerRef.current = null
  }, [])

  const removeFx = useCallback((id) => {
    setFx((list) => list.filter((f) => f.id !== id))
  }, [])

  const spawnFx = useCallback((items) => {
    setFx((list) => [
      ...list,
      ...items.map((item) => ({ ...item, id: ++fxIdRef.current })),
    ])
  }, [])

  const handleStartGame = async () => {
    if (starting) return
    setStarting(true)
    setCompleteResult(null)
    setNewBest(false)
    setOfflineReason(null)
    sessionRef.current = null
    syncedRef.current = false
    try {
      const data = await startSession()
      sessionRef.current = { sessionId: data.sessionId, nonce: data.nonce }
      syncedRef.current = true
      rollIndexRef.current = 0
      setScore(0)
      setBallsLeft(data.maxBalls || LOCAL_BALLS_PER_SESSION)
      setLastHit(null)
      setLaunch(null)
      setStep('aim')
    } catch (err) {
      if (err?.code === 'insufficient_tokens') {
        // No chances left — don't start a phantom game.
        setOfflineReason('遊戲次數不足 — 無法開始新的一場')
        setStarting(false)
        return
      }
      // Offline mode: full local game, nothing synced — practice only.
      setOfflineReason('未連線 — 練習模式（不計獎品）')
      rollIndexRef.current = 0
      setScore(0)
      setBallsLeft(LOCAL_BALLS_PER_SESSION)
      setLastHit(null)
      setLaunch(null)
      setStep('aim')
    } finally {
      setStarting(false)
    }
  }

  const reportRoll = useCallback((points) => {
    if (!syncedRef.current || !sessionRef.current) return
    rollIndexRef.current += 1
    postRoll(sessionRef.current.sessionId, {
      rollIndex: rollIndexRef.current,
      pinsHit: points > 0 ? 1 : 0,
      score: points,
      nonce: sessionRef.current.nonce,
      clientTs: Date.now(),
    }).catch(() => {
      // A rejected roll desyncs the session — finish locally, skip complete.
      syncedRef.current = false
      setOfflineReason('未連線 — 練習模式（不計獎品）')
    })
  }, [])

  const endBall = useCallback(
    (points) => {
      reportRoll(points)
      setBallsLeft((left) => {
        if (left - 1 <= 0) {
          setStep('over')
          return 0
        }
        setStep('aim')
        return left - 1
      })
      setLaunch(null)
    },
    [reportRoll]
  )

  const handleScore = useCallback(
    (hole) => {
      if (stepRef.current !== 'rolling') return
      if (ballDoneRef.current) return // one END per ball
      ballDoneRef.current = true
      scoredRef.current = true
      const points = hole.points
      const golden = points >= 300
      setScore((s) => s + points)
      setLastHit(points)
      sfx.score(points)
      const at = geom.boardPoint(hole.x, hole.y, -0.2)
      spawnFx([
        { kind: 'burst', position: at, color: hole.color, big: golden },
        { kind: 'pop', position: at, text: `+${points}`, big: golden,
          color: golden ? '#fde68a' : '#fef3c7' },
      ])
      // Let the ball visibly settle into the pocket before unmounting it.
      setTimeout(() => endBall(points), 300)
    },
    [endBall, geom, spawnFx]
  )

  const handleMiss = useCallback(() => {
    if (stepRef.current !== 'rolling') return
    if (ballDoneRef.current) return
    ballDoneRef.current = true
    setLastHit(0)
    sfx.miss()
    endBall(0)
  }, [endBall])

  // [R] forfeits a hopeless ball (stuck, rolled backward) — counts as a miss.
  useEffect(() => {
    const onKey = (e) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key.toLowerCase() === 'r') handleMiss()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [handleMiss])

  // Personal best (client-side, per browser) — update the moment a game ends.
  useEffect(() => {
    if (step !== 'over') return
    setNewBest(score > best && score > 0)
    if (score > best) {
      setBest(score)
      try {
        localStorage.setItem(BEST_KEY, String(score))
      } catch {
        // Storage unavailable — best just won't persist.
      }
    }
  }, [step]) // eslint-disable-line react-hooks/exhaustive-deps

  // Server recomputes the score from stored rolls — never send client totals.
  useEffect(() => {
    if (step !== 'over' || !syncedRef.current || !sessionRef.current) return
    let cancelled = false
    completeSession(sessionRef.current.sessionId)
      .then((data) => {
        if (cancelled) return
        setCompleteResult(data)
        sfx.gameOver(Boolean(data?.prize))
        onGameComplete?.(data)
      })
      .catch(() => {
        if (!cancelled) setOfflineReason('未連線 — 練習模式（不計獎品）')
      })
    return () => {
      cancelled = true
    }
  }, [step, onGameComplete])

  const handleLockAngle = () => {
    if (step !== 'aim' || wasDragRef.current) return
    sfx.click()
    setStep('power')
  }

  const handleLockPower = useCallback(() => {
    if (stepRef.current !== 'power' || wasDragRef.current) return
    scoredRef.current = false
    ballDoneRef.current = false
    ballPosRef.current = {
      x: geom.BALL_START[0], y: geom.BALL_START[1], z: geom.BALL_START[2],
    }
    sfx.click()
    sfx.launch(powerRef.current)
    setLaunch({ angle: aimRef.current, power: powerRef.current, key: Date.now() })
    setLastHit(null)
    setStep('rolling')
  }, [geom])

  const aiming = step === 'aim' || step === 'power'

  return (
    <div
      className="relative w-full touch-pan-y select-none overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-xl"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerEnd}
      onPointerCancel={onPointerEnd}
      onPointerLeave={onPointerEnd}
    >
      <div className="h-[60vh] min-h-[320px] w-full md:h-[70vh]">
        <Canvas
          shadows
          camera={{ position: [0, 5.5, -11], fov: 50 }}
          dpr={[1, 2]}
          gl={{ antialias: true }}
        >
          <Suspense fallback={<LoadingFallback />}>
            <color attach="background" args={['#0b1120']} />
            {bgUrl ? (
              <TextureErrorBoundary resetKey={bgUrl} fallback={null}>
                <Suspense fallback={null}>
                  <SceneBackground url={bgUrl} />
                </Suspense>
              </TextureErrorBoundary>
            ) : (
              <Stars radius={70} depth={40} count={2500} factor={4} fade speed={0.6} />
            )}

            <ambientLight intensity={0.55} />
            <directionalLight
              position={[6, 10, -6]}
              intensity={1.2}
              castShadow
              shadow-mapSize-width={1024}
              shadow-mapSize-height={1024}
            />
            <directionalLight position={[-5, 6, 4]} intensity={0.3} />

            {/* key on level: fixed physics bodies are recreated so editor edits apply live. */}
            <Physics key={JSON.stringify(level)} gravity={[0, GRAVITY_Y, 0]}>
              <SkeeballWorld level={level} onScore={handleScore} />
              {(aiming || step === 'idle') && (
                <>
                  <PreviewBall
                    textureUrl={ballUrl}
                    position={geom.BALL_START}
                    radius={level.ball.radius}
                  />
                  {step === 'aim' && (
                    <AimArrow
                      aimRef={aimRef}
                      startPosition={geom.BALL_START}
                      maxAngle={level.aim.maxAngle}
                      oscSpeed={level.aim.oscSpeed}
                    />
                  )}
                </>
              )}
              {step === 'rolling' && launch && (
                <PlayBall
                  key={launch.key}
                  angle={launch.angle}
                  power={launch.power}
                  textureUrl={ballUrl}
                  ballCfg={level.ball}
                  startPosition={geom.BALL_START}
                  missBounds={geom.missBounds}
                  onMiss={handleMiss}
                  posRef={ballPosRef}
                />
              )}
            </Physics>

            {fx.map((f) =>
              f.kind === 'burst' ? (
                <ScoreBurst key={f.id} {...f} onEnd={removeFx} />
              ) : (
                <ScorePop key={f.id} {...f} onEnd={removeFx} />
              )
            )}

            <CameraRig
              target={[0, 1.5, 4]}
              dragRef={dragDeltaRef}
              ballRef={ballPosRef}
              following={step === 'rolling'}
            />

            {/* The "lens": bloom makes every emissive surface (rings,
                backstops, guard bar, trim) actually glow; vignette focuses
                the eye. This is most of the distance between raw three.js
                and a screenshot people share. */}
            <EffectComposer>
              <Bloom mipmapBlur intensity={0.85} luminanceThreshold={0.55} luminanceSmoothing={0.2} />
              <Vignette eskil={false} offset={0.18} darkness={0.72} />
            </EffectComposer>
          </Suspense>
        </Canvas>
      </div>

      {/* HUD */}
      <div className="pointer-events-none absolute left-3 top-3 rounded-xl bg-slate-950/70 px-4 py-2 text-sm text-slate-100">
        分數：<span key={score} className="score-bump font-bold text-amber-300">{score}</span>
        {best > 0 && (
          <span className="ml-3 text-xs text-slate-400">最佳 {best}</span>
        )}
      </div>
      <div className="pointer-events-none absolute right-3 top-3 rounded-xl bg-slate-950/70 px-4 py-2 text-sm text-slate-100">
        剩餘球數：<span className="font-bold text-sky-300">{ballsLeft}</span>
      </div>
      {offlineReason && step !== 'idle' && (
        <div className="pointer-events-none absolute left-1/2 top-3 -translate-x-1/2 rounded-full bg-slate-950/80 px-4 py-1 text-xs font-medium text-amber-300">
          {offlineReason}
        </div>
      )}
      {lastHit !== null && step !== 'over' && step !== 'idle' && (
        <div className="pointer-events-none absolute left-1/2 top-16 -translate-x-1/2 rounded-full bg-slate-950/80 px-5 py-1.5 text-sm font-semibold text-slate-100">
          {lastHit > 0 ? `+${lastHit} 分！` : '沒進洞'}
        </div>
      )}

      {/* Start screen — user gesture also kicks off the backend session. */}
      {step === 'idle' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-slate-950/60">
          <button
            type="button"
            onClick={handleStartGame}
            disabled={starting}
            className="rounded-full bg-amber-500 px-8 py-3 text-lg font-bold text-slate-950 shadow-xl hover:bg-amber-400 disabled:opacity-60"
          >
            {starting ? '開始中…' : freePlay ? '開始遊戲（3 球）' : '開始遊戲（1 次機會・3 球）'}
          </button>
          {offlineReason && (
            <span className="rounded-full bg-slate-950/80 px-4 py-1 text-xs font-medium text-amber-300">
              {offlineReason}
            </span>
          )}
        </div>
      )}

      {/* Input overlay — captures clicks only while aiming/powering. */}
      {aiming && (
        <div
          className="absolute inset-0 cursor-pointer"
          onClick={step === 'aim' ? handleLockAngle : handleLockPower}
        >
          <div className="pointer-events-none absolute left-1/2 top-4 -translate-x-1/2 rounded-full bg-slate-950/80 px-5 py-2 text-sm font-semibold text-slate-100 md:text-base">
            {step === 'aim' ? '點擊鎖定角度' : '點擊鎖定力度'}
          </div>
          {step === 'power' && <PowerMeter powerRef={powerRef} onLock={handleLockPower} />}
        </div>
      )}

      {/* Game over — prize reveal */}
      {step === 'over' && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-950/70">
          {completeResult?.prize && (
            <ConfettiRain gold={Boolean(completeResult.golden)} />
          )}
          <div className="flex max-w-sm flex-col items-center gap-4 rounded-2xl border border-slate-700 bg-slate-900 px-10 py-8 text-center shadow-2xl">
            <p className="text-xl font-bold text-slate-100 md:text-2xl">
              遊戲結束 — 總分 <span className="text-amber-300">{score}</span>
            </p>
            {newBest && (
              <p className="text-sm font-bold text-sky-300">🏆 新紀錄！</p>
            )}
            {completeResult?.golden && completeResult?.prize && (
              <p className="text-lg font-bold text-amber-300">⭐ 命中金色頂孔！</p>
            )}
            {completeResult?.prize ? (
              <div className="flex flex-col items-center gap-2">
                <p className="text-base font-semibold text-emerald-300">
                  🎉 恭喜獲得「{completeResult.prize.title}」
                </p>
                <p className="text-xs text-slate-400">
                  優惠券已存入你的會員帳戶，結帳時直接選用
                </p>
                <a
                  href="/account"
                  className="rounded-full border border-emerald-400/60 px-4 py-1.5 text-sm font-semibold text-emerald-300 hover:bg-emerald-400/10"
                >
                  前往會員中心查看
                </a>
              </div>
            ) : completeResult ? (
              <p className="text-sm text-slate-300">差一點！再接再厲 💪</p>
            ) : syncedRef.current ? (
              <p className="text-sm text-slate-400">結算中…</p>
            ) : null}
            <button
              type="button"
              onClick={() => setStep('idle')}
              className="rounded-full bg-amber-500 px-6 py-2 font-bold text-slate-950 shadow-lg hover:bg-amber-400"
            >
              再玩一場
            </button>
          </div>
        </div>
      )}

      {/* Controls cheat-sheet — always visible. */}
      <div className="pointer-events-none absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-3 rounded-full bg-slate-950/70 px-4 py-1.5 text-xs text-slate-300">
        <span>
          拖曳（或
          <kbd className="rounded border border-slate-600 bg-slate-800 px-1.5 py-0.5 font-bold text-slate-100">A</kbd>
          {'/'}
          <kbd className="rounded border border-slate-600 bg-slate-800 px-1.5 py-0.5 font-bold text-slate-100">D</kbd>
          ）旋轉視角
        </span>
        <span className="text-slate-600">|</span>
        <span>點擊：鎖定角度 → 鎖定力度</span>
        <span className="text-slate-600">|</span>
        <span>
          <kbd className="rounded border border-slate-600 bg-slate-800 px-1.5 py-0.5 font-bold text-slate-100">R</kbd>
          {' 跳過卡住的球'}
        </span>
      </div>
    </div>
  )
}
