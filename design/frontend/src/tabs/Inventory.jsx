import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import ChannelTable from '../components/ChannelTable.jsx'
import OflBrowser from '../components/OflBrowser.jsx'
import Toast from '../components/Toast.jsx'

const slug = s => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')

const blankProfile = () => ({
  id: '',
  manufacturer: '',
  model: '',
  type: 'par',
  physical: { beam_deg: 25, watts: 0, pan_range_deg: 540, tilt_range_deg: 270 },
  verified: false,
  modes: [{ id: 'default', label: 'Default', footprint: 4, channels: [
    { offset: 0, function: 'red', default: 0, lock: false },
    { offset: 1, function: 'green', default: 0, lock: false },
    { offset: 2, function: 'blue', default: 0, lock: false },
    { offset: 3, function: 'master_dimmer', default: 255, lock: true },
  ] }],
})

export default function Inventory() {
  const [meta, setMeta] = useState({ functions: [], fixture_types: [] })
  const [profiles, setProfiles] = useState([])
  const [selected, setSelected] = useState(null)   // working copy of the selected profile
  const [dirty, setDirty] = useState(false)
  const [toast, setToast] = useState(null)
  const fileRef = useRef()

  const refresh = () => api.profiles.list().then(setProfiles)
  useEffect(() => { api.meta().then(setMeta); refresh() }, [])

  const select = p => { setSelected(structuredClone(p)); setDirty(false) }
  const newProfile = () => { setSelected(blankProfile()); setDirty(true) }

  const update = (path, value) => {
    setSelected(prev => {
      const next = structuredClone(prev)
      let o = next
      for (let i = 0; i < path.length - 1; i++) o = o[path[i]]
      o[path[path.length - 1]] = value
      return next
    })
    setDirty(true)
  }

  const save = async () => {
    const p = { ...selected, id: selected.id || slug(`${selected.manufacturer}-${selected.model}`) }
    if (!p.id) { setToast({ msg: 'Set a manufacturer + model first', kind: 'err' }); return }
    try {
      await api.profiles.save(p)
      setToast({ msg: `Saved ${p.id}` })
      setSelected(p); setDirty(false); refresh()
    } catch (e) {
      setToast({ msg: e.message + (e.details ? ': ' + e.details.join('; ') : ''), kind: 'err' })
    }
  }

  const del = async () => {
    if (!confirm(`Delete profile ${selected.id}?`)) return
    await api.profiles.delete(selected.id)
    setSelected(null); setDirty(false); refresh()
  }

  const importQxf = async file => {
    try {
      const p = await api.profiles.importQxf(file)
      setToast({ msg: `Imported ${p.id} from QLC+ — verify the channel map before relying on it` })
      refresh(); select(p)
    } catch (e) { setToast({ msg: e.message, kind: 'err' }) }
  }

  const oflImport = async key => {
    const p = await api.ofl.import(key)
    setToast({ msg: `Imported ${p.id} from OFL — verify before relying on it` })
    refresh(); select(p)
  }

  const m = selected?.modes?.[0]

  return (
    <div className="split">
      {/* ---------------------------------------------------------- left list */}
      <div className="left panel">
        <h2>Fixture profiles</h2>
        <p className="sub">{profiles.length} profiles</p>
        <div className="row" style={{ marginBottom: 12, flexWrap: 'wrap' }}>
          <button className="primary" onClick={newProfile}>+ New</button>
          <button onClick={() => fileRef.current?.click()}>Import .qxf</button>
          <input ref={fileRef} type="file" accept=".qxf,.xml" style={{ display: 'none' }}
                 onChange={e => { if (e.target.files[0]) importQxf(e.target.files[0]); e.target.value = '' }} />
        </div>

        <OflBrowser onImport={oflImport} onError={msg => setToast({ msg, kind: 'err' })} />

        <div className="grid">
          {profiles.map(p => (
            <div key={p.id} className={`card ${selected?.id === p.id ? 'selected' : ''}`}
                 onClick={() => select(p)} style={{ cursor: 'pointer' }}>
              <div className="row spread">
                <b>{p.manufacturer} {p.model}</b>
                <span className={`badge ${p.verified ? 'verified' : 'unverified'}`}>
                  {p.verified ? '✓' : '?'}
                </span>
              </div>
              <div className="row" style={{ marginTop: 6, fontSize: 12, color: 'var(--fg-dim)' }}>
                <span className="badge type">{p.type}</span>
                <span>{p.modes?.length} mode{p.modes?.length !== 1 ? 's' : ''}</span>
                <span>{p.modes?.[0]?.channels?.length}ch</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* -------------------------------------------------------- right detail */}
      <div className="right panel">
        {!selected ? (
          <div style={{ color: 'var(--fg-dim)', marginTop: 80, textAlign: 'center' }}>
            Select a profile, create a new one, or import from QLC+ / OFL.
          </div>
        ) : (
          <>
            <div className="row spread" style={{ marginBottom: 16 }}>
              <h2 style={{ margin: 0 }}>
                {selected.manufacturer || 'New'} {selected.model}
                {dirty && <span style={{ color: 'var(--accent)' }}> *</span>}
              </h2>
              <div className="row">
                {!selected.verified && <span className="badge unverified">unverified — sweep before trusting</span>}
                {selected.id && !dirty && (
                  <button title="Download an OFL-format JSON for upstreaming to the Open Fixture Library — verify first, OFL is community-trusted"
                          onClick={() => window.location.href = api.ofl.exportUrl(selected.id)}>
                    ⬆ OFL
                  </button>
                )}
                <button className="primary" onClick={save} disabled={!dirty}>Save</button>
                {selected.id && <button className="danger" onClick={del}>Delete</button>}
              </div>
            </div>

            {selected.verified && selected.id && !dirty && (
              <div className="card" style={{ marginBottom: 16, fontSize: 13, color: 'var(--fg-dim)' }}>
                Verified profile — public-spirited to upstream it.{' '}
                <b>⬆ OFL</b> downloads an OFL-format JSON; paste it into the{' '}
                <a href={api.ofl.editorUrl} target="_blank" rel="noreferrer">OFL fixture editor</a>{' '}
                to fill in the missing physical/wheel details and submit.
              </div>
            )}

            <div className="grid" style={{ gridTemplateColumns: '1fr 1fr 1fr 1fr', marginBottom: 18 }}>
              <div className="col"><label>Manufacturer</label>
                <input value={selected.manufacturer} onChange={e => update(['manufacturer'], e.target.value)} /></div>
              <div className="col"><label>Model</label>
                <input value={selected.model} onChange={e => update(['model'], e.target.value)} /></div>
              <div className="col"><label>Type</label>
                <select value={selected.type} onChange={e => update(['type'], e.target.value)}>
                  {meta.fixture_types.map(t => <option key={t} value={t}>{t}</option>)}
                </select></div>
              <div className="col"><label>Verified</label>
                <select value={selected.verified ? '1' : '0'}
                        onChange={e => update(['verified'], e.target.value === '1')}>
                  <option value="0">No — channel map not hardware-tested</option>
                  <option value="1">Yes — confirmed with a sweep</option>
                </select></div>
            </div>

            <div className="grid" style={{ gridTemplateColumns: 'repeat(5, 1fr)', marginBottom: 18 }}>
              {[['beam_deg', 'Beam °'], ['watts', 'Watts'], ['weight_kg', 'Weight kg'],
                ['pan_range_deg', 'Pan range °'], ['tilt_range_deg', 'Tilt range °']].map(([k, l]) => (
                <div key={k} className="col"><label>{l}</label>
                  <input type="number" value={selected.physical?.[k] ?? ''}
                         onChange={e => update(['physical', k], parseFloat(e.target.value) || 0)} /></div>
              ))}
            </div>

            {m && (
              <>
                <div className="row spread" style={{ marginBottom: 8 }}>
                  <div className="row">
                    <label>Mode</label>
                    <select value={0} onChange={() => {}}>
                      {selected.modes.map((mo, i) => <option key={i} value={i}>{mo.label}</option>)}
                    </select>
                    <input value={m.label} placeholder="label"
                           onChange={e => update(['modes', 0, 'label'], e.target.value)} />
                    <input value={m.id} placeholder="id" style={{ width: 90 }}
                           onChange={e => update(['modes', 0, 'id'], e.target.value)} />
                  </div>
                </div>
                <ChannelTable mode={m} functions={meta.functions}
                              onChange={mo => update(['modes', 0], mo)} />
              </>
            )}
          </>
        )}
      </div>

      <Toast {...toast} onClose={() => setToast(null)} />
    </div>
  )
}
