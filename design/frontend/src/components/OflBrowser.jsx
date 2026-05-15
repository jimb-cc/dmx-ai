// OFL search + browse. Two ways in: free-text search (their search endpoint
// has a global index), or pick a manufacturer to list their fixtures.
// Both use server-side disk-cached endpoints so browsing doesn't hammer OFL.

import { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function OflBrowser({ onImport, onError }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [mans, setMans] = useState(null)         // null = not yet loaded
  const [man, setMan] = useState('')             // selected manufacturer slug
  const [results, setResults] = useState([])     // [{key, manufacturer?, name?, model?, categories?}]
  const [busy, setBusy] = useState(false)

  // Lazy-load the manufacturer list the first time the section opens.
  useEffect(() => {
    if (open && mans === null) {
      api.ofl.manufacturers().then(setMans).catch(e => { onError?.(e.message); setMans([]) })
    }
  }, [open, mans, onError])

  const doSearch = async () => {
    if (!q.trim()) return
    setBusy(true); setMan('')
    try { setResults(await api.ofl.search(q)) }
    catch (e) { onError?.(e.message); setResults([]) }
    setBusy(false)
  }

  const pickMan = async slug => {
    setMan(slug); setQ(''); setResults([])
    if (!slug) return
    setBusy(true)
    try { setResults(await api.ofl.fixtures(slug)) }
    catch (e) { onError?.(e.message) }
    setBusy(false)
  }

  const doImport = async key => {
    setBusy(true)
    try { await onImport(key); setResults([]) }
    catch (e) { onError?.(e.message) }
    setBusy(false)
  }

  if (!open) {
    return <button onClick={() => setOpen(true)} style={{ marginBottom: 12, width: '100%' }}>
      🔎 Browse Open Fixture Library
    </button>
  }

  const manName = mans?.find(m => m.slug === man)?.name

  return (
    <div className="ofl-browser card" style={{ marginBottom: 12 }}>
      <div className="row spread" style={{ marginBottom: 8 }}>
        <b style={{ fontSize: 13 }}>Open Fixture Library</b>
        <button className="small" onClick={() => setOpen(false)}>✕</button>
      </div>

      <div className="col" style={{ marginBottom: 8 }}>
        <label>Manufacturer</label>
        <select value={man} onChange={e => pickMan(e.target.value)} disabled={mans === null}>
          <option value="">{mans === null ? 'loading…' : `— ${mans.length} manufacturers —`}</option>
          {(mans || []).map(m => <option key={m.slug} value={m.slug}>{m.name} ({m.fixtureCount})</option>)}
        </select>
      </div>

      <div className="row" style={{ marginBottom: 8 }}>
        <input placeholder="…or free-text search" value={q}
               onChange={e => setQ(e.target.value)}
               onKeyDown={e => e.key === 'Enter' && doSearch()} style={{ flex: 1 }} />
        <button className="small" onClick={doSearch} disabled={busy}>{busy ? '…' : '🔎'}</button>
      </div>

      {results.length > 0 && (
        <div style={{ maxHeight: 240, overflowY: 'auto', marginBottom: 4 }}>
          {man && <div style={{ fontSize: 11, color: 'var(--fg-dim)', marginBottom: 4 }}>{manName} · {results.length} fixtures</div>}
          {results.map(r => (
            <div key={r.key} className="row spread ofl-result">
              <span style={{ fontSize: 13, minWidth: 0 }}>
                {r.manufacturer && <span style={{ color: 'var(--fg-dim)' }}>{r.manufacturer} </span>}
                <b>{r.name || r.model}</b>
                {r.categories?.length > 0 && <small style={{ display: 'block', color: 'var(--fg-dim)', fontSize: 11 }}>{r.categories.join(', ')}</small>}
              </span>
              <button className="small" onClick={() => doImport(r.key)} disabled={busy}>Import</button>
            </div>
          ))}
        </div>
      )}
      {results.length === 0 && (man || q) && !busy && (
        <div style={{ fontSize: 12, color: 'var(--fg-dim)', padding: '4px 0' }}>No results.</div>
      )}
      <div style={{ fontSize: 10, color: 'var(--fg-dim)', borderTop: '1px solid var(--border)', paddingTop: 6 }}>
        <a href="https://open-fixture-library.org" target="_blank" rel="noreferrer">open-fixture-library.org</a> — community-sourced, unverified until you sweep.
      </div>
    </div>
  )
}
