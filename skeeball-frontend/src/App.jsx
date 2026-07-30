import { useCallback, useEffect, useState } from 'react'
import SkeeballCanvas from './components/SkeeballCanvas.jsx'
import LevelEditor from './components/LevelEditor.jsx'
import { putLevel } from './api/skeeballApi.js'
import { isMuted, setMuted } from './audio/sfx.js'
import { DEFAULT_LEVEL, loadLevelLocal, sanitizeLevel, saveLevelLocal } from './config/levelConfig.js'
import { LEVEL_PRESETS } from './config/presets.js'
import { DROP_TRACKS } from './components/dropRegistry.js'

// ?level=<key> deep-links a level; the in-page picker keeps it in sync.
// Presets apply client-side only — the served default level is untouched;
// sessions still score normally.
const INITIAL_KEY = (() => {
  const k = new URLSearchParams(window.location.search).get('level')
  return LEVEL_PRESETS[k] ? k : 'classic'
})()
const INITIAL_TRACK = (() => {
  const k = new URLSearchParams(window.location.search).get('track')
  return DROP_TRACKS[k] ? k : 'pachinko'
})()

/** Password prompt shown before the level editor opens (?admin in the URL). */
function AdminKeyModal({ onSubmit, onCancel }) {
  const [key, setKey] = useState('')
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70">
      <form
        className="flex w-72 flex-col gap-3 rounded-2xl border border-slate-700 bg-slate-900 p-5 shadow-2xl"
        onSubmit={(e) => {
          e.preventDefault()
          if (key.trim()) onSubmit(key.trim())
        }}
      >
        <h2 className="text-base font-bold text-amber-400">Admin Access</h2>
        <input
          type="password"
          autoFocus
          placeholder="Admin key"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          className="rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100"
        />
        <div className="flex gap-2">
          <button
            type="submit"
            className="rounded bg-amber-500 px-3 py-1.5 text-sm font-bold text-slate-950 hover:bg-amber-400"
          >
            Enter
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="rounded bg-slate-800 px-3 py-1.5 text-sm hover:bg-slate-700"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  )
}

/** 本週排行榜 — best score per member over the rolling week. */
function Leaderboard({ entries }) {
  if (!entries?.length) return null
  const medals = ['🥇', '🥈', '🥉']
  return (
    <section className="mt-6 rounded-2xl border border-slate-700 bg-slate-900 p-5">
      <h2 className="text-lg font-bold text-amber-400">⚔️ 本週排行榜</h2>
      <p className="mt-1 text-xs text-slate-400">近 7 天最佳單場成績</p>
      <ul className="mt-3 flex flex-col gap-1.5">
        {entries.map((e) => (
          <li
            key={e.rank}
            className={`flex items-center justify-between rounded-xl px-4 py-2 ${
              e.me ? 'border border-amber-500/50 bg-amber-500/10' : 'bg-slate-800/60'
            }`}
          >
            <span className="flex items-center gap-2 text-sm">
              <span className="w-7 text-center">{medals[e.rank - 1] ?? `${e.rank}.`}</span>
              <span className={e.me ? 'font-bold text-amber-200' : 'text-slate-200'}>
                {e.name}{e.me && '（你）'}
              </span>
              <span className="text-xs text-slate-500">{e.games} 場</span>
            </span>
            <span className="text-sm font-bold text-slate-100">{e.best}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** 獎品表 — what score wins which coupon (from /config, codes never shown). */
function PrizeTable({ prizes }) {
  const tiers = prizes?.tiers ?? []
  if (!tiers.length && !prizes?.apex) return null
  return (
    <section className="mt-6 rounded-2xl border border-slate-700 bg-slate-900 p-5">
      <h2 className="text-lg font-bold text-amber-400">🏆 獎品表</h2>
      <p className="mt-1 text-xs text-slate-400">
        每場 3 球，總分越高獎品越好；中獎優惠券直接發到你的會員帳戶。
      </p>
      <ul className="mt-3 flex flex-col gap-2">
        {prizes?.apex && (
          <li className="flex items-center justify-between rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-2.5">
            <span className="text-sm font-semibold text-amber-300">
              ⭐ 單球命中金色頂孔（300 分）
            </span>
            <span className="text-sm font-bold text-amber-200">{prizes.apex.title}</span>
          </li>
        )}
        {tiers.map((t) => (
          <li
            key={t.minScore}
            className="flex items-center justify-between rounded-xl bg-slate-800/70 px-4 py-2.5"
          >
            <span className="text-sm text-slate-200">總分 {t.minScore} 以上</span>
            <span className="text-sm font-semibold text-slate-100">{t.title}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default function App() {
  const [config, setConfig] = useState(null)
  const [balance, setBalance] = useState(null)
  const [apiError, setApiError] = useState(false)
  const [presetKey, setPresetKey] = useState(INITIAL_KEY)
  const [dropKey, setDropKey] = useState(INITIAL_TRACK)

  const chooseTrack = (key) => {
    if (key === dropKey) return
    setDropKey(key)
    const url = new URL(window.location)
    if (key === 'pachinko') url.searchParams.delete('track')
    else url.searchParams.set('track', key)
    window.history.replaceState(null, '', url)
  }
  const [serverLevel, setServerLevel] = useState(null)
  const [level, setLevel] = useState(() =>
    INITIAL_KEY !== 'classic'
      ? sanitizeLevel(LEVEL_PRESETS[INITIAL_KEY].level)
      : (loadLevelLocal() ?? DEFAULT_LEVEL))

  const choosePreset = (key) => {
    if (key === presetKey) return
    setPresetKey(key)
    setLevel(key === 'classic'
      ? (serverLevel ?? loadLevelLocal() ?? DEFAULT_LEVEL)
      : sanitizeLevel(LEVEL_PRESETS[key].level))
    const url = new URL(window.location)
    if (key === 'classic') url.searchParams.delete('level')
    else url.searchParams.set('level', key)
    window.history.replaceState(null, '', url)
  }
  const [adminKey, setAdminKey] = useState(null)
  const [showKeyPrompt, setShowKeyPrompt] = useState(false)
  const [editorOpen, setEditorOpen] = useState(false)
  const [saveStatus, setSaveStatus] = useState('')
  const [muted, setMutedState] = useState(isMuted)

  const toggleMute = () => {
    setMuted(!muted)
    setMutedState(!muted)
  }

  const isAdmin = new URLSearchParams(window.location.search).has('admin')

  const refreshBalance = useCallback(async () => {
    try {
      const res = await fetch('/api/skeeball/user/balance', { credentials: 'include' })
      if (!res.ok) throw new Error('API request failed')
      setBalance(await res.json())
    } catch {
      // Keep showing the last known balance.
    }
  }, [])

  const [board, setBoard] = useState(null)
  const refreshBoard = useCallback(async () => {
    try {
      const res = await fetch('/api/skeeball/leaderboard', { credentials: 'include' })
      if (!res.ok) throw new Error('API request failed')
      setBoard((await res.json()).entries)
    } catch {
      // Board stays hidden (offline / logged out).
    }
  }, [])

  useEffect(() => {
    refreshBoard()
  }, [refreshBoard])

  const handleGameComplete = useCallback(() => {
    refreshBalance()
    refreshBoard()
  }, [refreshBalance, refreshBoard])

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const [configRes, balanceRes] = await Promise.all([
          fetch('/api/skeeball/config'),
          fetch('/api/skeeball/user/balance', { credentials: 'include' }),
        ])
        if (!configRes.ok || !balanceRes.ok) throw new Error('API request failed')
        const [configData, balanceData] = await Promise.all([
          configRes.json(),
          balanceRes.json(),
        ])
        if (cancelled) return
        setConfig(configData)
        setBalance(balanceData)
        // Server-saved level wins over the local fallback (for 經典 only —
        // preset picks stay as chosen).
        if (configData.level) {
          const lv = sanitizeLevel(configData.level)
          setServerLevel(lv)
          if (INITIAL_KEY === 'classic') setLevel(lv)
        }
      } catch {
        if (!cancelled) setApiError(true)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  const handleLevelChange = useCallback((newLevel) => {
    setLevel(newLevel)
    setSaveStatus('unsaved changes')
  }, [])

  const handleSaveLevel = useCallback(async () => {
    setSaveStatus('saving…')
    try {
      await putLevel(level, adminKey)
      saveLevelLocal(level)
      setSaveStatus('saved')
    } catch (err) {
      if (err?.status === 422) {
        setSaveStatus(`rejected: ${err.message}`)
      } else if (err?.status === 403 || err?.status === 404 || !err?.status) {
        // No backend (or wrong/missing admin route) — keep a local copy.
        saveLevelLocal(level)
        setSaveStatus(
          err?.status === 403 ? 'invalid admin key — saved locally (offline)' : 'saved locally (offline)'
        )
      } else {
        saveLevelLocal(level)
        setSaveStatus('saved locally (offline)')
      }
    }
  }, [level, adminKey])

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-5">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-amber-400 md:text-3xl">
            荷魯斯滾球 <span className="text-lg font-semibold text-slate-400">HORUS BALL</span>
          </h1>
          <a href="/" className="text-xs text-slate-400 underline-offset-2 hover:text-amber-300 hover:underline">
            ← 回阿北玩具堂
          </a>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <button
            type="button"
            onClick={toggleMute}
            title={muted ? '開啟音效' : '關閉音效'}
            className="rounded-full bg-slate-800 px-3 py-1.5 hover:bg-slate-700"
          >
            {muted ? '🔇' : '🔊'}
          </button>
          {balance ? (
            <span className="rounded-full bg-slate-800 px-4 py-1.5">
              遊戲次數：
              <span className="font-semibold text-sky-300">
                {balance.freePlay ? '無限 ∞（封測）' : balance.tokenBalance}
              </span>
            </span>
          ) : (
            <span className="rounded-full bg-slate-800/60 px-4 py-1.5 text-slate-400">
              {apiError ? '連線失敗 — 展示模式' : '載入中…'}
            </span>
          )}
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-4 pb-10">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-slate-400">軌道</span>
          {Object.entries(DROP_TRACKS).map(([key, t]) => (
            <button
              key={key}
              type="button"
              onClick={() => chooseTrack(key)}
              className={
                key === dropKey
                  ? 'rounded-full bg-orange-500 px-4 py-1.5 text-sm font-bold text-slate-950 shadow'
                  : 'rounded-full bg-slate-800 px-4 py-1.5 text-sm text-slate-200 hover:bg-slate-700'
              }
            >
              {t.name}
            </button>
          ))}
        </div>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-slate-400">關卡</span>
          {Object.entries(LEVEL_PRESETS).map(([key, p]) => (
            <button
              key={key}
              type="button"
              onClick={() => choosePreset(key)}
              className={
                key === presetKey
                  ? 'rounded-full bg-amber-500 px-4 py-1.5 text-sm font-bold text-slate-950 shadow'
                  : 'rounded-full bg-slate-800 px-4 py-1.5 text-sm text-slate-200 hover:bg-slate-700'
              }
            >
              {p.name}
            </button>
          ))}
        </div>

        {/* key on the preset: switching levels resets the game to the start
            screen instead of swapping the board out mid-throw. */}
        <SkeeballCanvas
          key={presetKey + dropKey}
          level={level}
          dropKey={dropKey}
          freePlay={Boolean(balance?.freePlay)}
          onGameComplete={handleGameComplete}
        />

        {isAdmin && !editorOpen && !showKeyPrompt && (
          <button
            type="button"
            onClick={() => (adminKey ? setEditorOpen(true) : setShowKeyPrompt(true))}
            className="mt-4 rounded bg-slate-800 px-4 py-2 text-sm hover:bg-slate-700"
          >
            Open Level Editor
          </button>
        )}

        <Leaderboard entries={board} />

        <PrizeTable prizes={config?.prizes} />

        <section className="mt-6 grid gap-3 text-left sm:grid-cols-3">
          <div className="rounded-xl bg-slate-900 p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">怎麼玩</p>
            <p className="mt-1 text-sm">點擊鎖定角度 → 點擊鎖定力度，一場 3 球</p>
          </div>
          <div className="rounded-xl bg-slate-900 p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">遊戲機會</p>
            <p className="mt-1 text-sm">封測期間無限暢玩！正式開賽後每消費滿 NT$1,000 送 1 次</p>
          </div>
          <div className="rounded-xl bg-slate-900 p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">中獎領取</p>
            <p className="mt-1 text-sm">
              優惠券自動存入{' '}
              <a href="/account" className="text-amber-300 underline underline-offset-2 hover:text-amber-200">
                會員中心
              </a>
              ，結帳時直接選用
            </p>
          </div>
        </section>
      </main>

      {showKeyPrompt && (
        <AdminKeyModal
          onSubmit={(key) => {
            setAdminKey(key)
            setShowKeyPrompt(false)
            setEditorOpen(true)
          }}
          onCancel={() => setShowKeyPrompt(false)}
        />
      )}

      {editorOpen && (
        <LevelEditor
          level={level}
          onChange={handleLevelChange}
          onSave={handleSaveLevel}
          onClose={() => setEditorOpen(false)}
          saveStatus={saveStatus}
        />
      )}
    </div>
  )
}
