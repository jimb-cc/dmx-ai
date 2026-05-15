// Setlist tab — desktop-friendly editor for show/setlist.yaml with a live
// scene preview. The Show app has its own setlist UI for the gig (touch,
// one tap = song change); this one is for pre-show planning on a real
// keyboard with a "what does this scene actually look like" preview.

import { useEffect, useState } from 'react'
import { api } from '../api.js'
import ScenePreview from '../components/ScenePreview.jsx'
import Toast from '../components/Toast.jsx'

const blankSong = section => ({ title: '', artist: '', section, scene: '', bpm: 120, hue: 0, choreo: '', notes: '' })

export default function Setlist() {
  const [scenes, setScenes] = useState([])
  const [choreos, setChoreos] = useState([])
  const [setlist, setSetlist] = useState(null)
  const [sel, setSel] = useState(null)        // song index, or 'between'
  const [dirty, setDirty] = useState(false)
  const [toast, setToast] = useState(null)

  useEffect(() => {
    api.scenes().then(d => { setScenes(d.scenes); setChoreos(d.choreos) }).catch(() => {})
    api.setlist.get().then(d => { setSetlist(d); setSel(d.songs?.length ? 0 : 'between') }).catch(e => setToast({ msg: e.message, kind: 'err' }))
  }, [])

  const change = next => { setSetlist(next); setDirty(true) }

  const updateSong = (i, patch) => {
    if (i === 'between') change({ ...setlist, between: { ...setlist.between, ...patch } })
    else change({ ...setlist, songs: setlist.songs.map((s, j) => j === i ? { ...s, ...patch } : s) })
  }

  const addSong = section => {
    const next = [...setlist.songs, blankSong(section)]
    change({ ...setlist, songs: next })
    setSel(next.length - 1)
  }

  const removeSong = i => {
    change({ ...setlist, songs: setlist.songs.filter((_, j) => j !== i) })
    if (sel === i) setSel(null)
    else if (typeof sel === 'number' && sel > i) setSel(sel - 1)
  }

  const moveSong = (i, dir) => {
    const j = i + dir
    if (j < 0 || j >= setlist.songs.length) return
    const songs = [...setlist.songs]
    ;[songs[i], songs[j]] = [songs[j], songs[i]]
    change({ ...setlist, songs })
    if (sel === i) setSel(j)
    else if (sel === j) setSel(i)
  }

  const save = async () => {
    try {
      const saved = await api.setlist.save(setlist)
      setSetlist(saved); setDirty(false)
      setToast({ msg: `Saved ${saved.songs.length} songs to show/setlist.yaml` })
    } catch (e) { setToast({ msg: e.message, kind: 'err' }) }
  }

  if (!setlist) return <div className="panel" style={{ flex: 1, color: 'var(--fg-dim)', textAlign: 'center', paddingTop: 80 }}>Loading…</div>

  // Group songs by section for the rendered list. Preserves order.
  const sections = []
  let cur = null
  setlist.songs.forEach((s, i) => {
    const sec = s.section || ''
    if (sec !== cur) { sections.push({ section: sec, items: [] }); cur = sec }
    sections[sections.length - 1].items.push([i, s])
  })

  const song = sel === 'between' ? setlist.between : (typeof sel === 'number' ? setlist.songs[sel] : null)
  const sceneName = sel === 'between' ? (setlist.between?.scene || '') : (song?.scene || '')
  const sceneInfo = scenes.find(sc => sc.name === sceneName)

  return (
    <div className="split">
      {/* ---------------------------------------------------------- left list */}
      <div className="left panel setlist-list">
        <div className="row spread" style={{ marginBottom: 4 }}>
          <h2 style={{ margin: 0 }}>Setlist{dirty && <span style={{ color: 'var(--accent)' }}> *</span>}</h2>
          <button className="primary small" onClick={save} disabled={!dirty}>Save</button>
        </div>
        <p className="sub">{setlist.songs.length} songs · saves to <code>show/setlist.yaml</code></p>

        <div className="col" style={{ marginBottom: 14 }}>
          <label>Setlist name</label>
          <input value={setlist.name} onChange={e => change({ ...setlist, name: e.target.value })} />
        </div>

        <div className={`song-row between ${sel === 'between' ? 'sel' : ''}`} onClick={() => setSel('between')}>
          <span className="song-title">Between songs</span>
          <span className="song-scene">{sceneLabel(scenes, setlist.between?.scene)}</span>
        </div>

        {sections.map((sec, si) => (
          <div key={si}>
            {sec.section && <div className="section-head">{sec.section}</div>}
            {sec.items.map(([i, s]) => (
              <div key={i} className={`song-row ${sel === i ? 'sel' : ''}`} onClick={() => setSel(i)}>
                <span className="song-num">{i + 1}</span>
                <span className="song-title">{s.title || '(untitled)'}<small>{s.artist}</small></span>
                <span className="song-scene">{sceneLabel(scenes, s.scene)}</span>
                <span className="song-bpm">{s.bpm || ''}</span>
              </div>
            ))}
          </div>
        ))}
        <button className="small" style={{ marginTop: 10, width: '100%' }}
                onClick={() => addSong(setlist.songs.at(-1)?.section || 'Set 1')}>+ Add song</button>
      </div>

      {/* --------------------------------------------------------- right edit */}
      <div className="right panel">
        {sel === null ? (
          <div style={{ color: 'var(--fg-dim)', marginTop: 80, textAlign: 'center' }}>Pick a song.</div>
        ) : (
          <div className="setlist-detail">
            <div className="card">
              <div className="row spread" style={{ marginBottom: 12 }}>
                <h2 style={{ margin: 0 }}>
                  {sel === 'between' ? 'Between songs' : `${(typeof sel === 'number' ? sel + 1 : '')}. ${song?.title || '(untitled)'}`}
                </h2>
                {typeof sel === 'number' && (
                  <div className="row">
                    <button className="small" onClick={() => moveSong(sel, -1)} disabled={sel === 0}>↑</button>
                    <button className="small" onClick={() => moveSong(sel, 1)} disabled={sel === setlist.songs.length - 1}>↓</button>
                    <button className="small danger" onClick={() => removeSong(sel)}>Remove</button>
                  </div>
                )}
              </div>

              {sel !== 'between' && (
                <div className="grid" style={{ gridTemplateColumns: '2fr 2fr 1fr', marginBottom: 12 }}>
                  <div className="col"><label>Title</label>
                    <input value={song?.title || ''} onChange={e => updateSong(sel, { title: e.target.value })} /></div>
                  <div className="col"><label>Artist</label>
                    <input value={song?.artist || ''} onChange={e => updateSong(sel, { artist: e.target.value })} /></div>
                  <div className="col"><label>Section</label>
                    <input value={song?.section || ''} onChange={e => updateSong(sel, { section: e.target.value })}
                           placeholder="Set 1" list="sections" />
                    <datalist id="sections">{[...new Set(setlist.songs.map(s => s.section).filter(Boolean))].map(s => <option key={s} value={s} />)}</datalist></div>
                </div>
              )}

              <div className="grid" style={{ gridTemplateColumns: '2fr 1fr 1fr 1.4fr', marginBottom: 12 }}>
                <div className="col"><label>Scene</label>
                  <select value={song?.scene || ''} onChange={e => updateSong(sel, { scene: e.target.value || undefined })}>
                    <option value="">— none —</option>
                    {scenes.map(s => <option key={s.name} value={s.name}>{s.label} ({s.mood})</option>)}
                  </select></div>
                <div className="col"><label>BPM</label>
                  <input type="number" min={40} max={240} value={song?.bpm || ''}
                         onChange={e => updateSong(sel, { bpm: parseInt(e.target.value) || undefined })} /></div>
                <div className="col"><label>Hue °</label>
                  <input type="number" min={0} max={359} value={song?.hue || 0}
                         onChange={e => updateSong(sel, { hue: parseInt(e.target.value) || 0 })} /></div>
                <div className="col"><label>Movers</label>
                  <select value={song?.choreo || ''} onChange={e => updateSong(sel, { choreo: e.target.value || undefined })}>
                    <option value="">— auto —</option>
                    {choreos.map(c => <option key={c.name} value={c.name}>{c.label}</option>)}
                  </select></div>
              </div>

              <div className="row" style={{ marginBottom: 12, alignItems: 'flex-end' }}>
                <input type="range" min={0} max={359} value={song?.hue || 0} style={{ flex: 1 }}
                       className="hue-slider"
                       onChange={e => updateSong(sel, { hue: parseInt(e.target.value) })} />
                <button className="small" onClick={() => updateSong(sel, { hue: 0 })}>↺</button>
              </div>

              <div className="col">
                <label>Notes</label>
                <textarea rows={2} value={song?.notes || ''}
                          onChange={e => updateSong(sel, { notes: e.target.value || undefined })}
                          placeholder="cues, transitions, what to watch for…" />
              </div>
            </div>

            <div className="card preview-card">
              <h3 style={{ margin: '0 0 4px', fontSize: 14 }}>
                Preview {sceneInfo && <span style={{ color: 'var(--fg-dim)', fontWeight: 400 }}>· {sceneInfo.label} · {sceneInfo.mood}</span>}
              </h3>
              <p className="sub" style={{ marginBottom: 10 }}>
                actual Show app scene code rendered against the current rig
              </p>
              <ScenePreview scene={sceneName} hue={song?.hue || 0} bpm={song?.bpm || 120} choreo={song?.choreo || ''} />
            </div>
          </div>
        )}
      </div>

      <Toast {...toast} onClose={() => setToast(null)} />
    </div>
  )
}

const sceneLabel = (scenes, name) => scenes.find(s => s.name === name)?.label ?? (name ? name : '—')
