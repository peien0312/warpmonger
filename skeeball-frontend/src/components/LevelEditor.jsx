import { useRef, useState } from 'react'
import { DEFAULT_LEVEL, sanitizeLevel } from '../config/levelConfig.js'

/** Labeled slider + number input pair. */
function SliderField({ label, value, min, max, step = 0.01, onChange }) {
  return (
    <label className="block text-xs text-slate-300">
      <span className="mb-1 flex items-center justify-between">
        <span>{label}</span>
        <input
          type="number"
          className="w-20 rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 text-right text-slate-100"
          value={value}
          min={min}
          max={max}
          step={step}
          onChange={(e) => onChange(Number(e.target.value))}
        />
      </span>
      <input
        type="range"
        className="w-full accent-amber-400"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  )
}

/** URL text input with a thumbnail that flags broken URLs. `hint` shows the recommended texture size. */
function TextureField({ label, value, onChange, hint }) {
  const [broken, setBroken] = useState(false)
  return (
    <label className="block text-xs text-slate-300">
      <span className="mb-1 block">{label}</span>
      <div className="flex items-center gap-2">
        <input
          type="text"
          className="w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-slate-100"
          placeholder="https://…"
          value={value}
          onChange={(e) => {
            setBroken(false)
            onChange(e.target.value.trim())
          }}
        />
        {value && (
          <img
            src={value}
            alt=""
            className="h-8 w-8 shrink-0 rounded border border-slate-700 object-cover"
            onError={() => setBroken(true)}
            onLoad={() => setBroken(false)}
          />
        )}
      </div>
      {hint && <span className="mt-1 block text-slate-500">建議尺寸：{hint}</span>}
      {broken && <span className="mt-1 block text-red-400">invalid URL</span>}
    </label>
  )
}

/**
 * 2D front-view editor of the backboard. Circles are the score targets;
 * drag to move (pointer events, px → world coords), click to select.
 */
function TargetBoard({ level, selected, onSelect, onMove }) {
  const svgRef = useRef(null)
  const dragging = useRef(null)
  const { lane, ramp, backboard } = level
  const x0 = -(lane.width + 1) / 2
  const x1 = (lane.width + 1) / 2
  const y0 = ramp.rise
  const y1 = ramp.rise + backboard.height

  const W = 280
  const H = 280
  const scale = Math.min(W / (x1 - x0), H / (y1 - y0))
  const padX = (W - (x1 - x0) * scale) / 2
  const padY = (H - (y1 - y0) * scale) / 2
  const toPx = (x, y) => [padX + (x - x0) * scale, H - padY - (y - y0) * scale]
  const toWorld = (px, py) => [(px - padX) / scale + x0, (H - padY - py) / scale + y0]

  const handlePointerMove = (e) => {
    if (dragging.current === null) return
    const rect = svgRef.current.getBoundingClientRect()
    const px = ((e.clientX - rect.left) / rect.width) * W
    const py = ((e.clientY - rect.top) / rect.height) * H
    const [wx, wy] = toWorld(px, py)
    onMove(dragging.current, wx, wy)
  }

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${W} ${H}`}
      className="w-full touch-none rounded border border-slate-700 bg-slate-900"
      onPointerMove={handlePointerMove}
      onPointerUp={() => (dragging.current = null)}
      onPointerLeave={() => (dragging.current = null)}
    >
      {/* board */}
      <rect
        x={toPx(x0, y1)[0]}
        y={toPx(x0, y1)[1]}
        width={(x1 - x0) * scale}
        height={(y1 - y0) * scale}
        fill="#1e293b"
        stroke="#475569"
      />
      {level.targets.map((t, i) => {
        const [cx, cy] = toPx(t.x, t.y)
        const isSel = i === selected
        return (
          <g key={i}>
            <circle
              cx={cx}
              cy={cy}
              r={t.r * scale}
              fill={t.color}
              fillOpacity={0.25}
              stroke={isSel ? '#facc15' : t.color}
              strokeWidth={isSel ? 3 : 1.5}
              className="cursor-grab"
              onPointerDown={(e) => {
                e.target.setPointerCapture?.(e.pointerId)
                dragging.current = i
                onSelect(i)
              }}
            />
            <text
              x={cx}
              y={cy}
              textAnchor="middle"
              dominantBaseline="middle"
              className="pointer-events-none fill-slate-100"
              fontSize="11"
            >
              {t.points}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

export default function LevelEditor({ level, onChange, onSave, onClose, saveStatus }) {
  const [selected, setSelected] = useState(0)
  const fileRef = useRef(null)

  const update = (patch) => onChange(sanitizeLevel({ ...level, ...patch }))
  const updateSection = (key, patch) => update({ [key]: { ...level[key], ...patch } })
  const updateTarget = (i, patch) => {
    const targets = level.targets.map((t, j) => (j === i ? { ...t, ...patch } : t))
    update({ targets })
  }

  const sel = level.targets[selected] ?? null

  const handleExport = () => {
    const blob = new Blob([JSON.stringify(level, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'horusball-level.json'
    a.click()
    URL.revokeObjectURL(a.href)
  }

  const handleImport = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      try {
        onChange(sanitizeLevel(JSON.parse(reader.result)))
      } catch {
        // Not valid JSON — ignore the file.
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  return (
    <aside className="fixed right-0 top-0 z-50 flex h-full w-80 flex-col overflow-y-auto border-l border-slate-700 bg-slate-950/95 p-4 text-slate-100 shadow-2xl">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-bold text-amber-400">Level Editor</h2>
        <button
          type="button"
          onClick={onClose}
          className="rounded bg-slate-800 px-2 py-1 text-xs hover:bg-slate-700"
        >
          Close
        </button>
      </div>

      {/* Targets */}
      <section className="mb-5">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
          Targets
        </h3>
        <TargetBoard
          level={level}
          selected={selected}
          onSelect={setSelected}
          onMove={(i, x, y) => updateTarget(i, { x, y })}
        />
        <div className="mt-2 flex gap-2">
          <button
            type="button"
            disabled={level.targets.length >= 8}
            onClick={() => {
              update({
                targets: [
                  ...level.targets,
                  { name: `Target ${level.targets.length + 1}`, points: 100, r: 0.6, x: 0, y: (level.ramp.rise + level.backboard.height / 2), color: '#38bdf8' },
                ],
              })
              setSelected(level.targets.length)
            }}
            className="rounded bg-sky-600 px-2 py-1 text-xs font-semibold hover:bg-sky-500 disabled:opacity-40"
          >
            新增得分區
          </button>
          <button
            type="button"
            disabled={!sel || level.targets.length <= 1}
            onClick={() => {
              update({ targets: level.targets.filter((_, j) => j !== selected) })
              setSelected(0)
            }}
            className="rounded bg-red-600 px-2 py-1 text-xs font-semibold hover:bg-red-500 disabled:opacity-40"
          >
            刪除
          </button>
        </div>
        {sel && (
          <div className="mt-3 space-y-2 rounded border border-slate-700 bg-slate-900 p-2">
            <label className="block text-xs text-slate-300">
              <span className="mb-1 block">Name</span>
              <input
                type="text"
                className="w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-slate-100"
                value={sel.name}
                onChange={(e) => updateTarget(selected, { name: e.target.value })}
              />
            </label>
            <SliderField
              label="Points"
              value={sel.points}
              min={10}
              max={999}
              step={1}
              onChange={(v) => updateTarget(selected, { points: v })}
            />
            <SliderField
              label="Radius"
              value={sel.r}
              min={0.2}
              max={1.2}
              onChange={(v) => updateTarget(selected, { r: v })}
            />
            <label className="flex items-center justify-between text-xs text-slate-300">
              <span>Color</span>
              <input
                type="color"
                value={sel.color}
                onChange={(e) => updateTarget(selected, { color: e.target.value })}
              />
            </label>
          </div>
        )}
      </section>

      {/* Lane / Ramp / Backboard */}
      <section className="mb-5 space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          Lane / Ramp / Backboard
        </h3>
        <SliderField label="Lane width" value={level.lane.width} min={2} max={6} onChange={(v) => updateSection('lane', { width: v })} />
        <SliderField label="Lane length" value={level.lane.length} min={6} max={20} onChange={(v) => updateSection('lane', { length: v })} />
        <SliderField label="Lane thickness" value={level.lane.thickness} min={0.1} max={0.6} onChange={(v) => updateSection('lane', { thickness: v })} />
        <SliderField label="Ramp length" value={level.ramp.length} min={1.5} max={6} onChange={(v) => updateSection('ramp', { length: v })} />
        <SliderField label="Ramp rise" value={level.ramp.rise} min={0.5} max={4} onChange={(v) => updateSection('ramp', { rise: v })} />
        <SliderField label="Ramp gap (滑道到背板距離)" value={level.ramp.gap} min={0} max={4} step={0.1} onChange={(v) => updateSection('ramp', { gap: v })} />
        <SliderField label="Ramp curve (滑道弧度)" value={level.ramp.curve} min={0} max={1} step={0.05} onChange={(v) => updateSection('ramp', { curve: v })} />
        <SliderField label="Backboard height" value={level.backboard.height} min={2} max={8} onChange={(v) => updateSection('backboard', { height: v })} />
        <SliderField label="Backboard thickness" value={level.backboard.thickness} min={0.1} max={0.5} onChange={(v) => updateSection('backboard', { thickness: v })} />
        <SliderField label="Backboard tilt (背板後傾角)" value={level.backboard.tilt} min={0} max={1.2} step={0.02} onChange={(v) => updateSection('backboard', { tilt: v })} />
      </section>

      {/* Ball & Aim */}
      <section className="mb-5 space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          Ball &amp; Aim
        </h3>
        <SliderField label="Min speed" value={level.ball.minSpeed} min={0.5} max={10} onChange={(v) => updateSection('ball', { minSpeed: v })} />
        <SliderField label="Max speed" value={level.ball.maxSpeed} min={level.ball.minSpeed} max={40} onChange={(v) => updateSection('ball', { maxSpeed: v })} />
        <SliderField label="Mass" value={level.ball.mass} min={0.5} max={10} onChange={(v) => updateSection('ball', { mass: v })} />
        <SliderField label="Restitution" value={level.ball.restitution} min={0} max={1} onChange={(v) => updateSection('ball', { restitution: v })} />
        <SliderField label="Aim max angle" value={level.aim.maxAngle} min={0.05} max={0.8} onChange={(v) => updateSection('aim', { maxAngle: v })} />
      </section>

      {/* Textures */}
      <section className="mb-5 space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Textures</h3>
        <TextureField label="Ball URL" value={level.textures.ballUrl} onChange={(v) => updateSection('textures', { ballUrl: v })} hint="1024×1024 px（1:1，球面 UV 展開）" />
        <TextureField label="Lane URL" value={level.textures.laneUrl} onChange={(v) => updateSection('textures', { laneUrl: v })} hint="1024×1024 px（1:1，可無縫平鋪的四方連續圖）" />
        <TextureField label="Background URL" value={level.textures.backgroundUrl} onChange={(v) => updateSection('textures', { backgroundUrl: v })} hint="2048×1024 px（2:1 等距柱狀全景圖 equirectangular）" />
      </section>

      {/* Actions */}
      <div className="mt-auto flex flex-wrap gap-2 border-t border-slate-800 pt-3">
        <button
          type="button"
          onClick={onSave}
          className="rounded bg-amber-500 px-3 py-1.5 text-sm font-bold text-slate-950 hover:bg-amber-400"
        >
          Save
        </button>
        <button
          type="button"
          onClick={() => onChange(sanitizeLevel(DEFAULT_LEVEL))}
          className="rounded bg-slate-800 px-3 py-1.5 text-sm hover:bg-slate-700"
        >
          Reset to defaults
        </button>
        <button
          type="button"
          onClick={handleExport}
          className="rounded bg-slate-800 px-3 py-1.5 text-sm hover:bg-slate-700"
        >
          Export JSON
        </button>
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          className="rounded bg-slate-800 px-3 py-1.5 text-sm hover:bg-slate-700"
        >
          Import JSON
        </button>
        <input ref={fileRef} type="file" accept="application/json" className="hidden" onChange={handleImport} />
      </div>
      {saveStatus && <p className="mt-2 text-xs text-slate-300">{saveStatus}</p>}
    </aside>
  )
}
