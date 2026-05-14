// Phase 3 placeholder.
export default function Rigging() {
  return (
    <div className="panel" style={{ flex: 1 }}>
      <h2>Rigging</h2>
      <p className="sub">Coming in Phase 3 — top-down stage plot, drag fixtures, beam cones,
        auto-patch, conflict highlight, printable cheat sheet.</p>
      <div className="card" style={{ maxWidth: 600, color: 'var(--fg-dim)' }}>
        For now, edit <code>data/rigs/gravelaxe.json</code> by hand — the schema is documented
        in <code>shared/rig.py</code>. The Show app loads it directly with
        <code> python3 show/app.py --rig data/rigs/gravelaxe.json</code>.
      </div>
    </div>
  )
}
