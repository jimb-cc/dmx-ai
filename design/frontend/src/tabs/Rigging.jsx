// Rigging tab — top-down stage plot, fixture palette, patch table, export.
//
// Left panel: rig picker + fixture palette (click a profile to add it).
// Right panel: StagePlot SVG (drag to position, rotate handle for facing),
//   FixtureDetail side card when something's selected, patch table below.
// Toolbar: auto-patch, save, export show package, print cheat sheet.

import { useEffect, useState } from 'react'
import { api } from '../api.js'
import StagePlot from '../components/StagePlot.jsx'
import FixtureDetail from '../components/FixtureDetail.jsx'
import PatchSummary from '../components/PatchSummary.jsx'
import Toast from '../components/Toast.jsx'
import { profilesById, autoPatch, conflicts, footprintOf, nextId, nextFreeAddress } from '../rigUtils.js'

const slug = s => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')

const blankRig = name => ({
  name,
  stage: { width_m: 5.0, depth_m: 3.0, origin: 'front-centre' },
  fixtures: [],
})

const ID_PREFIX = { par: 'PAR', mover: 'MOV', batten: 'BAT', strobe: 'STR', wash: 'WASH', spot: 'SPOT', generic: 'FX' }

export default function Rigging() {
  const [profiles, setProfiles] = useState([])
  const [rigList, setRigList] = useState([])
  const [rigFile, setRigFile] = useState(null)   // slug used as the file name
  const [rig, setRig] = useState(null)           // working copy
  const [selected, setSelected] = useState(null) // fixture id
  const [dirty, setDirty] = useState(false)
  const [warnings, setWarnings] = useState([])
  const [toast, setToast] = useState(null)

  const byId = profilesById(profiles)

  const refreshList = () => api.rigs.list().then(setRigList)
  useEffect(() => { api.profiles.list().then(setProfiles); refreshList() }, [])

  // Auto-load the first rig once the list arrives.
  useEffect(() => {
    if (rig === null && rigList.length > 0) loadRig(rigList[0].file)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rigList])

  const loadRig = async file => {
    try {
      const r = await api.rigs.get(file)
      setRig(r); setRigFile(file); setSelected(null); setDirty(false); setWarnings([])
    } catch (e) { setToast({ msg: e.message, kind: 'err' }) }
  }

  const newRig = () => {
    const name = prompt('Rig name?', 'New Rig')
    if (!name) return
    const file = slug(name)
    if (!file) { setToast({ msg: 'Name needs at least one letter or digit', kind: 'err' }); return }
    setRig(blankRig(name)); setRigFile(file); setSelected(null); setDirty(true); setWarnings([])
  }

  const change = next => { setRig(next); setDirty(true) }

  const save = async () => {
    if (!rig || !rigFile) return
    try {
      const { rig: saved, warnings: w } = await api.rigs.save(rigFile, rig)
      setRig(saved); setDirty(false); setWarnings(w || [])
      setToast({ msg: w?.length ? `Saved with ${w.length} warning(s)` : `Saved ${rigFile}`, kind: w?.length ? 'err' : 'info' })
      refreshList()
    } catch (e) { setToast({ msg: e.message, kind: 'err' }) }
  }

  const del = async () => {
    if (!rigFile || !confirm(`Delete rig ${rigFile}?`)) return
    await api.rigs.delete(rigFile)
    setRig(null); setRigFile(null); setSelected(null); setDirty(false)
    refreshList()
  }

  const addFixture = profile => {
    const m = profile.modes?.[0]
    if (!m) { setToast({ msg: `${profile.id} has no modes`, kind: 'err' }); return }
    const id = nextId(rig.fixtures, ID_PREFIX[profile.type] ?? 'FX')
    const addr = nextFreeAddress(rig.fixtures, byId, m.footprint ?? m.channels.length)
    const fx = {
      id, label: '', profile: profile.id, mode: m.id,
      universe: 1, address: addr,
      x: 0, y: rig.stage?.depth_m ? rig.stage.depth_m / 2 : 1.5, z: 2.2,
      facing_deg: 180, tilt_deg: -25, groups: [],
    }
    change({ ...rig, fixtures: [...rig.fixtures, fx] })
    setSelected(id)
  }

  const removeFixture = id => {
    change({ ...rig, fixtures: rig.fixtures.filter(f => f.id !== id) })
    if (selected === id) setSelected(null)
  }

  const doAutoPatch = () => {
    change({ ...rig, fixtures: autoPatch(rig.fixtures, byId) })
    setToast({ msg: 'Auto-patched — addresses are footprint-spaced from 1' })
  }

  const exportPackage = () => {
    if (dirty) { setToast({ msg: 'Save first — export bundles the saved rig', kind: 'err' }); return }
    window.location.href = api.rigs.exportUrl(rigFile)
  }

  const conflictCount = rig ? Object.keys(conflicts(rig.fixtures, byId)).length : 0
  const channelTotal = rig ? rig.fixtures.reduce((s, f) => s + footprintOf(f, byId), 0) : 0

  return (
    <div className="split">
      {/* ---------------------------------------------------------- left panel */}
      <div className="left panel">
        <h2>Rigs</h2>
        <p className="sub">{rigList.length} saved</p>
        <div className="row" style={{ marginBottom: 12 }}>
          <select value={rigFile ?? ''} onChange={e => e.target.value && loadRig(e.target.value)} style={{ flex: 1 }}>
            {!rigFile && <option value="">— pick a rig —</option>}
            {rigList.map(r => <option key={r.file} value={r.file}>{r.name} ({r.fixtures})</option>)}
            {rigFile && !rigList.some(r => r.file === rigFile) && <option value={rigFile}>{rig?.name} (unsaved)</option>}
          </select>
          <button className="primary small" onClick={newRig}>+ New</button>
        </div>

        {rig && (
          <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', marginBottom: 16 }}>
            <div className="col"><label>Name</label>
              <input value={rig.name} onChange={e => change({ ...rig, name: e.target.value })} /></div>
            <div className="col"><label>File</label>
              <input value={rigFile ?? ''} onChange={e => { setRigFile(slug(e.target.value)); setDirty(true) }} /></div>
            <div className="col"><label>Stage W m</label>
              <input type="number" step={0.5} value={rig.stage?.width_m ?? 5}
                     onChange={e => change({ ...rig, stage: { ...rig.stage, width_m: parseFloat(e.target.value) || 5 } })} /></div>
            <div className="col"><label>Stage D m</label>
              <input type="number" step={0.5} value={rig.stage?.depth_m ?? 3}
                     onChange={e => change({ ...rig, stage: { ...rig.stage, depth_m: parseFloat(e.target.value) || 3 } })} /></div>
          </div>
        )}

        <h2>Palette</h2>
        <p className="sub">click a profile to add it to the rig</p>
        <div className="grid">
          {profiles.map(p => (
            <div key={p.id} className="card palette" onClick={() => rig && addFixture(p)}
                 style={{ cursor: rig ? 'pointer' : 'not-allowed', opacity: rig ? 1 : 0.5 }}>
              <div className="row spread">
                <b>{p.manufacturer} {p.model}</b>
                <span className={`badge ${p.verified ? 'verified' : 'unverified'}`}>{p.verified ? '✓' : '?'}</span>
              </div>
              <div className="row" style={{ marginTop: 4, fontSize: 12, color: 'var(--fg-dim)' }}>
                <span className="badge type">{p.type}</span>
                <span>{p.modes?.[0]?.channels?.length}ch / {p.modes?.[0]?.footprint}fp</span>
                <span>beam {p.physical?.beam_deg ?? '?'}°</span>
              </div>
            </div>
          ))}
          {profiles.length === 0 && <div style={{ color: 'var(--fg-dim)', fontSize: 13 }}>No profiles — add some in the Inventory tab.</div>}
        </div>
      </div>

      {/* --------------------------------------------------------- right panel */}
      <div className="right panel rigging">
        {!rig ? (
          <div style={{ color: 'var(--fg-dim)', marginTop: 80, textAlign: 'center' }}>
            Pick a rig or create a new one.
          </div>
        ) : (
          <>
            <div className="row spread" style={{ marginBottom: 12 }}>
              <h2 style={{ margin: 0 }}>
                {rig.name}{dirty && <span style={{ color: 'var(--accent)' }}> *</span>}
                <span style={{ fontSize: 13, color: 'var(--fg-dim)', fontWeight: 400, marginLeft: 12 }}>
                  {rig.fixtures.length} fixtures · {channelTotal}ch
                  {conflictCount > 0 && <span style={{ color: 'var(--err)' }}> · {conflictCount} conflicts</span>}
                </span>
              </h2>
              <div className="row">
                <button onClick={doAutoPatch} disabled={!rig.fixtures.length} title="Reassign addresses footprint-spaced from 1">Auto-patch</button>
                <button onClick={() => window.print()} disabled={!rig.fixtures.length}>Print sheet</button>
                <button onClick={exportPackage} disabled={!rigFile}>Export package</button>
                <button className="primary" onClick={save} disabled={!dirty}>Save</button>
                <button className="danger small" onClick={del} disabled={!rigFile}>Delete</button>
              </div>
            </div>

            {warnings.length > 0 && (
              <div className="card warn" style={{ marginBottom: 12 }}>
                {warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
              </div>
            )}

            <div className="rigging-layout">
              <div className="card plot-card">
                <StagePlot rig={rig} byId={byId} selected={selected}
                           onSelect={setSelected} onChange={change} />
              </div>
              {selected && (
                <FixtureDetail rig={rig} byId={byId} fxId={selected}
                               onChange={change} onRemove={removeFixture} />
              )}
            </div>

            <h3 style={{ margin: '18px 0 8px', fontSize: 14 }}>Patch</h3>
            <PatchSummary rig={rig} byId={byId} selected={selected} onSelect={setSelected} />
          </>
        )}
      </div>

      <Toast {...toast} onClose={() => setToast(null)} />
    </div>
  )
}
