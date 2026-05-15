// Top-down SVG stage plot. Drag fixtures, drag the rotation handle for
// facing_deg, beam cone shows physical.beam_deg.
//
// Stage coordinates (shared/rig.py): origin front-centre, +x stage-left
// (audience right), +y upstage. SVG y increases downward, so stage y is
// negated when drawing — back of stage at the top, audience at the bottom.

import { useRef, useState } from 'react'
import { footprintOf, conflicts as findConflicts } from '../rigUtils.js'

const TYPE_GLYPH = { par: '◉', mover: '▲', batten: '▬', strobe: '✦', wash: '◎', spot: '●', generic: '○' }
const HANDLE_DIST = 0.55       // m, rotation handle offset
const SNAP = 0.1               // m, position grid snap

export default function StagePlot({ rig, byId, selected, onSelect, onChange }) {
  const svgRef = useRef()
  const [drag, setDrag] = useState(null)  // { kind, id, dx, dy } | null

  const W = rig.stage?.width_m ?? 5
  const D = rig.stage?.depth_m ?? 3
  // Asymmetric padding: extra below for the fixture id/address labels.
  const PAD = Math.max(0.5, Math.max(W, D) * 0.1)
  const PADB = PAD + 0.55
  const beamLen = D * 0.7
  const conf = findConflicts(rig.fixtures, byId)

  // pointer -> stage coords (SVG units == metres after viewBox)
  const toStage = e => {
    const svg = svgRef.current
    const pt = svg.createSVGPoint()
    pt.x = e.clientX; pt.y = e.clientY
    const m = svg.getScreenCTM()
    if (!m) return { x: 0, y: 0 }
    const p = pt.matrixTransform(m.inverse())
    return { x: p.x, y: -p.y }   // un-flip
  }

  const update = (id, patch) => onChange({
    ...rig,
    fixtures: rig.fixtures.map(f => f.id === id ? { ...f, ...patch } : f),
  })

  const startDrag = (e, kind, fx) => {
    e.stopPropagation()
    e.preventDefault()
    onSelect(fx.id)
    const p = toStage(e)
    setDrag({ kind, id: fx.id, dx: fx.x - p.x, dy: fx.y - p.y })
    try { e.target.setPointerCapture?.(e.pointerId) } catch { /* synthetic event */ }
  }

  const onMove = e => {
    if (!drag) return
    const fx = rig.fixtures.find(f => f.id === drag.id)
    if (!fx) return
    const p = toStage(e)
    if (drag.kind === 'move') {
      const x = clamp(snap(p.x + drag.dx), -W / 2 - PAD, W / 2 + PAD)
      const y = clamp(snap(p.y + drag.dy), -0.3, D + PAD)
      update(fx.id, { x, y })
    } else {  // rotate — angle from fixture toward pointer
      const ang = (Math.atan2(p.x - fx.x, p.y - fx.y) * 180 / Math.PI + 360) % 360
      update(fx.id, { facing_deg: e.shiftKey ? Math.round(ang) : Math.round(ang / 15) * 15 % 360 })
    }
  }

  const stopDrag = () => setDrag(null)

  // viewBox: x ∈ [-W/2-PAD, W/2+PAD], svgY ∈ [-D-PAD, PADB] (stage y flipped)
  const vb = `${-W / 2 - PAD} ${-D - PAD} ${W + 2 * PAD} ${D + PAD + PADB}`

  return (
    <svg ref={svgRef} className="stage-plot" viewBox={vb} preserveAspectRatio="xMidYMid meet"
         onPointerMove={onMove} onPointerUp={stopDrag} onPointerLeave={stopDrag}
         onPointerDown={() => onSelect(null)}>
      {/* stage floor */}
      <rect x={-W / 2} y={-D} width={W} height={D} className="stage-floor" />
      {/* grid lines every 0.5m */}
      <g className="stage-grid">
        {ticks(-W / 2, W / 2, 0.5).map(x => <line key={`v${x}`} x1={x} y1={-D} x2={x} y2={0} />)}
        {ticks(0, D, 0.5).map(y => <line key={`h${y}`} x1={-W / 2} y1={-y} x2={W / 2} y2={-y} />)}
      </g>
      {/* centreline + downstage edge */}
      <line x1={0} y1={-D} x2={0} y2={0} className="stage-cl" />
      <line x1={-W / 2} y1={0} x2={W / 2} y2={0} className="stage-ds" />
      <text x={0} y={PADB - 0.15} className="stage-label" textAnchor="middle">audience</text>
      <text x={0} y={-D - PAD * 0.3} className="stage-label" textAnchor="middle">upstage</text>

      {/* beam cones (under the fixture markers) */}
      {rig.fixtures.map(f => {
        const beam = byId[f.profile]?.physical?.beam_deg ?? 25
        return <BeamCone key={f.id} fx={f} beamDeg={beam} length={beamLen}
                         dim={selected && selected !== f.id} />
      })}

      {/* fixture markers */}
      {rig.fixtures.map(f => {
        const p = byId[f.profile]
        const isSel = selected === f.id
        const inConflict = conf[f.id]?.size > 0
        return (
          <g key={f.id} transform={`translate(${f.x} ${-f.y})`}
             className={`fx ${isSel ? 'sel' : ''} ${inConflict ? 'conflict' : ''}`}>
            <circle r={0.22} className="fx-body"
                    onPointerDown={e => startDrag(e, 'move', f)} />
            <text className="fx-glyph" textAnchor="middle" dy="0.075"
                  style={{ pointerEvents: 'none' }}>
              {TYPE_GLYPH[p?.type] ?? '○'}
            </text>
            <text className="fx-id" y={0.45} textAnchor="middle" style={{ pointerEvents: 'none' }}>
              {f.id}
            </text>
            <text className="fx-addr" y={0.62} textAnchor="middle" style={{ pointerEvents: 'none' }}>
              {f.address}–{f.address + footprintOf(f, byId) - 1}
            </text>
            {isSel && <RotationHandle fx={f} onPointerDown={e => startDrag(e, 'rotate', f)} />}
          </g>
        )
      })}
    </svg>
  )
}

function BeamCone({ fx, beamDeg, length, dim }) {
  // facing_deg=0 → +y (upstage). In SVG y-down with translate(fx.x, -fx.y):
  // direction = (sin(f), -cos(f)).
  const f = fx.facing_deg * Math.PI / 180
  const half = (beamDeg / 2) * Math.PI / 180
  const a1 = f - half, a2 = f + half
  const ox = fx.x, oy = -fx.y
  const p1 = [ox + Math.sin(a1) * length, oy - Math.cos(a1) * length]
  const p2 = [ox + Math.sin(a2) * length, oy - Math.cos(a2) * length]
  // arc flag: large if beamDeg > 180 (won't happen, but be correct)
  const large = beamDeg > 180 ? 1 : 0
  return (
    <path className={`beam ${dim ? 'dim' : ''}`}
          d={`M ${ox} ${oy} L ${p1[0]} ${p1[1]} A ${length} ${length} 0 ${large} 1 ${p2[0]} ${p2[1]} Z`} />
  )
}

function RotationHandle({ fx, onPointerDown }) {
  const f = fx.facing_deg * Math.PI / 180
  const hx = Math.sin(f) * HANDLE_DIST
  const hy = -Math.cos(f) * HANDLE_DIST
  return (
    <g className="rot">
      <line x1={0} y1={0} x2={hx} y2={hy} />
      <circle cx={hx} cy={hy} r={0.1} onPointerDown={onPointerDown} />
    </g>
  )
}

const ticks = (lo, hi, step) => {
  const out = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-6; v += step) out.push(round2(v))
  return out
}
const snap = v => Math.round(v / SNAP) * SNAP
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v))
const round2 = v => Math.round(v * 100) / 100
