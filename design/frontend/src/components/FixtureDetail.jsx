// Side panel for the fixture selected in the StagePlot. Address, mode,
// universe, position, groups. Address conflicts are highlighted inline.

import { footprintOf, conflicts as findConflicts, modeOf } from '../rigUtils.js'

export default function FixtureDetail({ rig, byId, fxId, onChange, onRemove }) {
  const fx = rig.fixtures.find(f => f.id === fxId)
  if (!fx) return null
  const profile = byId[fx.profile]
  const mode = modeOf(profile, fx.mode)
  const fp = footprintOf(fx, byId)
  const conf = findConflicts(rig.fixtures, byId)[fx.id]

  const set = patch => onChange({
    ...rig,
    fixtures: rig.fixtures.map(f => f.id === fx.id ? { ...f, ...patch } : f),
  })

  const setId = newId => {
    if (!newId || rig.fixtures.some(f => f.id === newId && f.id !== fx.id)) return
    onChange({ ...rig, fixtures: rig.fixtures.map(f => f.id === fx.id ? { ...f, id: newId } : f) })
  }

  return (
    <div className="card fx-detail">
      <div className="row spread" style={{ marginBottom: 10 }}>
        <b style={{ fontSize: 15 }}>{fx.id} <span style={{ color: 'var(--fg-dim)', fontWeight: 400 }}>· {profile?.manufacturer} {profile?.model}</span></b>
        <button className="small danger" onClick={() => onRemove(fx.id)}>Remove</button>
      </div>

      <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', marginBottom: 10 }}>
        <div className="col"><label>ID</label>
          <input value={fx.id} onChange={e => setId(e.target.value.replace(/\s/g, ''))} /></div>
        <div className="col"><label>Label</label>
          <input value={fx.label || ''} onChange={e => set({ label: e.target.value })} /></div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: '2fr 70px 80px', marginBottom: 10 }}>
        <div className="col" style={{ minWidth: 0 }}><label>Mode</label>
          <select value={fx.mode} onChange={e => set({ mode: e.target.value })} title={mode?.label}>
            {(profile?.modes ?? []).map(m => <option key={m.id} value={m.id}>{m.id} · {m.channels.length}ch</option>)}
          </select></div>
        <div className="col"><label>Universe</label>
          <input type="number" min={1} max={4} value={fx.universe}
                 onChange={e => set({ universe: clampInt(e.target.value, 1, 4) })} /></div>
        <div className="col"><label>Address</label>
          <input type="number" min={1} max={512} value={fx.address}
                 className={conf?.size ? 'has-conflict' : ''}
                 onChange={e => set({ address: clampInt(e.target.value, 1, 512) })} /></div>
      </div>

      <div className="patch-strip" style={{ marginBottom: 12 }}>
        <span>DMX <b>{fx.address}</b>–<b>{fx.address + fp - 1}</b></span>
        <span style={{ color: 'var(--fg-dim)' }}>{mode?.channels?.length}ch used / {fp} footprint</span>
        {conf?.size > 0 && <span className="conflict-pill">overlaps {[...conf].join(', ')}</span>}
      </div>

      <div className="grid" style={{ gridTemplateColumns: '1fr 1fr 1fr', marginBottom: 10 }}>
        {[['x', 'X m'], ['y', 'Y m'], ['z', 'Z m'], ['facing_deg', 'Facing °'], ['tilt_deg', 'Tilt °']].map(([k, l]) => (
          <div key={k} className="col" style={{ minWidth: 0 }}><label>{l}</label>
            <input type="number" step={k.endsWith('deg') ? 5 : 0.1} value={round2(fx[k])}
                   onChange={e => set({ [k]: parseFloat(e.target.value) || 0 })} /></div>
        ))}
      </div>

      <div className="col" style={{ marginBottom: 4 }}>
        <label>Groups</label>
        <input value={(fx.groups || []).join(', ')} placeholder="front, left, pars"
               onChange={e => set({ groups: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })} />
      </div>
    </div>
  )
}

const clampInt = (v, lo, hi) => Math.max(lo, Math.min(hi, parseInt(v) || lo))
const round2 = v => Math.round((v ?? 0) * 100) / 100
