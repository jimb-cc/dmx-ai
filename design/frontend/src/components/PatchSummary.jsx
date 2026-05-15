// Patch table — fixtures sorted by address, conflicts highlighted, plus a
// print-only cheat sheet for the rigging crew.

import { footprintOf, conflicts as findConflicts, modeOf } from '../rigUtils.js'

export default function PatchSummary({ rig, byId, selected, onSelect }) {
  const conf = findConflicts(rig.fixtures, byId)
  const sorted = [...rig.fixtures].sort((a, b) => a.universe - b.universe || a.address - b.address)
  const total = sorted.reduce((s, f) => s + footprintOf(f, byId), 0)
  const conflictCount = Object.keys(conf).length

  return (
    <>
      <table className="patch-table">
        <thead>
          <tr>
            <th style={{ width: 70 }}>ID</th>
            <th>Fixture</th>
            <th style={{ width: 80 }}>Mode</th>
            <th style={{ width: 36 }}>U</th>
            <th style={{ width: 110 }}>DMX</th>
            <th style={{ width: 50 }}>Footprint</th>
            <th>Groups</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map(f => {
            const p = byId[f.profile]
            const fp = footprintOf(f, byId)
            const isConf = conf[f.id]?.size > 0
            return (
              <tr key={f.id} onClick={() => onSelect?.(f.id)}
                  className={`${selected === f.id ? 'sel' : ''} ${isConf ? 'conflict' : ''}`}
                  style={{ cursor: onSelect ? 'pointer' : undefined }}>
                <td><b>{f.id}</b></td>
                <td>{p ? `${p.manufacturer} ${p.model}`.trim() : <span className="missing">{f.profile}?</span>}</td>
                <td>{f.mode}</td>
                <td>{f.universe}</td>
                <td className={isConf ? 'conflict-cell' : ''}>
                  {f.address}–{f.address + fp - 1}
                  {isConf && <span title={`overlaps ${[...conf[f.id]].join(', ')}`}> ⚠</span>}
                </td>
                <td>{fp}</td>
                <td className="groups">{(f.groups || []).join(', ')}</td>
              </tr>
            )
          })}
          {sorted.length === 0 && <tr><td colSpan={7} style={{ color: 'var(--fg-dim)' }}>No fixtures yet — click a profile in the palette.</td></tr>}
        </tbody>
        <tfoot>
          <tr>
            <td colSpan={5} style={{ color: 'var(--fg-dim)' }}>
              {sorted.length} fixtures · {total} channels patched
              {conflictCount > 0 && <span style={{ color: 'var(--err)' }}> · {conflictCount} in conflict</span>}
            </td>
            <td colSpan={2} />
          </tr>
        </tfoot>
      </table>

      <PrintSheet rig={rig} byId={byId} sorted={sorted} conf={conf} />
    </>
  )
}

// -- Print-only cheat sheet ---------------------------------------------------
// Hidden on screen; @media print swaps it in (see styles.css). Designed to be
// taped to the dimmer rack: model, mode, DMX address, the panel digits to dial
// in, and any footnotes (conflicts, unverified profiles).

function PrintSheet({ rig, byId, sorted, conf }) {
  return (
    <div className="print-only">
      <h1>{rig.name}</h1>
      <p className="print-sub">
        {sorted.length} fixtures · stage {rig.stage?.width_m ?? '?'}m × {rig.stage?.depth_m ?? '?'}m
        · printed {new Date().toLocaleDateString()}
      </p>
      <table>
        <thead>
          <tr><th>ID</th><th>Label</th><th>Fixture</th><th>Mode</th><th>U</th><th>DMX start</th><th>Span</th><th>Position</th><th>Notes</th></tr>
        </thead>
        <tbody>
          {sorted.map(f => {
            const p = byId[f.profile]
            const m = modeOf(p, f.mode)
            const fp = footprintOf(f, byId)
            const notes = []
            if (conf[f.id]?.size) notes.push(`⚠ overlaps ${[...conf[f.id]].join(', ')}`)
            if (p && !p.verified) notes.push('unverified — sweep before show')
            if (!p) notes.push('profile missing!')
            return (
              <tr key={f.id}>
                <td><b>{f.id}</b></td>
                <td>{f.label || ''}</td>
                <td>{p ? `${p.manufacturer} ${p.model}`.trim() : f.profile}</td>
                <td>{m?.label ?? f.mode}</td>
                <td>{f.universe}</td>
                <td className="addr"><b>{String(f.address).padStart(3, '0')}</b></td>
                <td>{f.address}–{f.address + fp - 1}</td>
                <td>{round1(f.x)}, {round1(f.y)} @ {round1(f.z)}m · facing {Math.round(f.facing_deg)}°</td>
                <td>{notes.join(' · ')}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="print-foot">dmx·ai design · positions are stage-metres from front-centre, +x stage-left, +y upstage</p>
    </div>
  )
}

const round1 = v => Math.round((v ?? 0) * 10) / 10
