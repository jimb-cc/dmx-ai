// Animated scene preview — top-down stage plot with the fixtures coloured
// from a server-rendered preview. The backend runs the actual Show app scene
// code; this just plays the frame strip back as an SVG animation.

import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

const TYPE_GLYPH = { par: '◉', mover: '▲', batten: '▬', strobe: '✦', wash: '◎', spot: '●', generic: '○' }
const SECS = 8, FPS = 12

export default function ScenePreview({ scene, hue = 0, bpm = 120, choreo = '' }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [frame, setFrame] = useState(0)
  const reqRef = useRef(0)   // track in-flight requests so a stale response can't clobber

  // Re-fetch when scene/hue/bpm/choreo changes (debounced).
  useEffect(() => {
    if (!scene) { setData(null); return }
    const reqId = ++reqRef.current
    setErr(null)
    const t = setTimeout(() => {
      api.preview(scene, { hue, bpm, choreo, secs: SECS, fps: FPS })
        .then(d => { if (reqId === reqRef.current) { setData(d); setFrame(0) } })
        .catch(e => { if (reqId === reqRef.current) { setErr(e.message); setData(null) } })
    }, 250)
    return () => clearTimeout(t)
  }, [scene, hue, bpm, choreo])

  // Animation loop.
  useEffect(() => {
    if (!data) return
    const interval = 1000 / data.fps
    const t = setInterval(() => setFrame(f => (f + 1) % data.frames.length), interval)
    return () => clearInterval(t)
  }, [data])

  if (!scene) return <div className="preview-empty">Pick a song to preview its scene.</div>
  if (err) return <div className="preview-empty err">⚠ {err}</div>
  if (!data) return <div className="preview-empty">Rendering…</div>

  return (
    <div>
      <PreviewSvg data={data} frame={frame} />
      <div className="preview-strip">
        {data.frames.map((fr, i) => (
          <div key={i} className={`tick ${i === frame ? 'cur' : ''}`}
               onClick={() => setFrame(i)}
               style={{ background: avg(fr) }} />
        ))}
      </div>
      <div className="preview-meta">
        {data.scene} · hue {Math.round(data.hue)}° · {Math.round(data.bpm)} bpm
        {data.movers?.length > 0 && ` · ${data.choreo} choreo`}
      </div>
    </div>
  )
}

function PreviewSvg({ data, frame }) {
  // Stage bounds from the fixture positions.
  const xs = data.fixtures.map(f => f.x)
  const ys = data.fixtures.map(f => f.y)
  const W = Math.max(4, (Math.max(...xs) - Math.min(...xs)) + 1.5)
  const D = Math.max(2, (Math.max(...ys) - Math.min(...ys)) + 1.5)
  const PAD = 0.5
  const PADB = 1.0
  const vb = `${-W / 2 - PAD} ${-D - PAD} ${W + 2 * PAD} ${D + PAD + PADB}`
  const colours = data.frames[frame] ?? []
  const beams = data.beams?.[frame] ?? []
  const moverIdx = data.movers ?? []

  return (
    <svg className="scene-preview" viewBox={vb} preserveAspectRatio="xMidYMid meet">
      <rect x={-W / 2} y={-D} width={W} height={D} className="stage-floor" />
      <line x1={-W / 2} y1={0} x2={W / 2} y2={0} className="stage-ds" />
      {data.fixtures.map((f, i) => {
        const [r, g, b] = colours[i] ?? [0, 0, 0]
        const lit = (r + g + b) / 765
        const fill = `rgb(${r},${g},${b})`
        const mIdx = moverIdx.indexOf(i)
        const beam = mIdx >= 0 ? beams[mIdx] : null
        return (
          <g key={f.id} transform={`translate(${f.x} ${-f.y})`}>
            {/* glow proportional to brightness */}
            <circle r={0.32 + 0.5 * lit} fill={fill} opacity={0.28 * lit} />
            {/* mover beam wedge — direction from pan, width fixed, length from intensity */}
            {beam && beam[2] > 0.02 && <Beam pan={beam[0]} inten={beam[2]} fill={fill} />}
            <circle r={0.26} fill={fill} stroke="rgba(255,255,255,.25)" strokeWidth={0.025} />
            <text className="fx-glyph" textAnchor="middle" dy="0.085"
                  style={{ pointerEvents: 'none', fill: lit > 0.5 ? '#000' : '#fff', opacity: 0.7 }}>
              {TYPE_GLYPH[f.type] ?? '○'}
            </text>
            <text className="fx-id" y={0.5} textAnchor="middle">{f.id}</text>
          </g>
        )
      })}
    </svg>
  )
}

function Beam({ pan, inten, fill }) {
  // Normalised pan 0..1 → an angle around centre; we don't have the home
  // pan so this is a relative visualisation, not absolute geometry. Centre
  // (0.5) faces downstage (toward the audience in preview = -y in fixture
  // local space = +y SVG since the fixture is at -y already).
  const ang = (pan - 0.5) * Math.PI * 0.8   // ±72° looks readable
  const half = 0.18
  const len = 0.6 + inten * 1.4
  const a1 = ang - half, a2 = ang + half
  const p1 = [Math.sin(a1) * len, Math.cos(a1) * len]
  const p2 = [Math.sin(a2) * len, Math.cos(a2) * len]
  return <path d={`M 0 0 L ${p1[0]} ${p1[1]} L ${p2[0]} ${p2[1]} Z`}
               fill={fill} opacity={0.25 + inten * 0.4} />
}

const avg = fr => {
  const n = fr.length
  const [r, g, b] = fr.reduce((a, c) => [a[0] + c[0], a[1] + c[1], a[2] + c[2]], [0, 0, 0])
  return `rgb(${Math.round(r / n)},${Math.round(g / n)},${Math.round(b / n)})`
}
