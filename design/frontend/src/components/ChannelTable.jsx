// Channel editor for a single fixture mode.
// Function dropdown, default value, lock toggle, optional label.

export default function ChannelTable({ mode, functions, onChange }) {
  const update = (idx, field, value) => {
    const channels = mode.channels.map((c, i) => i === idx ? { ...c, [field]: value } : c)
    onChange({ ...mode, channels })
  }
  const addChannel = () => {
    const next = mode.channels.length
    onChange({
      ...mode,
      channels: [...mode.channels, { offset: next, function: 'none', default: 0, lock: false }],
      footprint: Math.max(mode.footprint, next + 1),
    })
  }
  const removeChannel = idx => {
    const channels = mode.channels.filter((_, i) => i !== idx).map((c, i) => ({ ...c, offset: i }))
    onChange({ ...mode, channels })
  }

  return (
    <div>
      <div className="row spread" style={{ marginBottom: 8 }}>
        <div className="row">
          <label>Footprint</label>
          <input type="number" min={mode.channels.length} max={512} style={{ width: 70 }}
                 value={mode.footprint}
                 onChange={e => onChange({ ...mode, footprint: parseInt(e.target.value) || mode.channels.length })}/>
          <span style={{ fontSize: 12, color: 'var(--fg-dim)' }}>
            patch spacing — pad above the channel count for unverified fixtures
          </span>
        </div>
        <button className="small" onClick={addChannel}>+ Channel</button>
      </div>
      <table>
        <thead>
          <tr>
            <th style={{ width: 50 }}>CH</th>
            <th style={{ width: 180 }}>Function</th>
            <th style={{ width: 80 }}>Default</th>
            <th style={{ width: 60 }}>Lock</th>
            <th>Label</th>
            <th style={{ width: 40 }} />
          </tr>
        </thead>
        <tbody>
          {mode.channels.map((c, i) => (
            <tr key={i}>
              <td>{c.offset + 1}</td>
              <td>
                <select value={c.function} onChange={e => update(i, 'function', e.target.value)}>
                  {functions.map(f => <option key={f} value={f}>{f}</option>)}
                </select>
              </td>
              <td>
                <input type="number" min={0} max={255} value={c.default || 0}
                       onChange={e => update(i, 'default', parseInt(e.target.value) || 0)} />
              </td>
              <td>
                <input type="checkbox" checked={!!c.lock}
                       onChange={e => update(i, 'lock', e.target.checked)}
                       title="Locked channels are written to their default once and never touched" />
              </td>
              <td>
                <input value={c.label || ''} placeholder="notes…"
                       onChange={e => update(i, 'label', e.target.value)} />
              </td>
              <td>
                <button className="small danger" onClick={() => removeChannel(i)}>✕</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
