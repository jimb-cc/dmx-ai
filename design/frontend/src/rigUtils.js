// Client-side mirrors of the helpers in shared/rig.py and shared/profile.py.
// The Python side is the source of truth (it runs on save and on the Pi);
// these exist so the UI can give instant feedback while editing.

/** profile id -> Profile, for quick lookup. */
export function profilesById(profiles) {
  return Object.fromEntries(profiles.map(p => [p.id, p]))
}

export function modeOf(profile, modeId) {
  return profile?.modes?.find(m => m.id === modeId) ?? profile?.modes?.[0]
}

export function footprintOf(fx, byId) {
  const m = modeOf(byId[fx.profile], fx.mode)
  return m?.footprint ?? 16
}

export function channelCountOf(fx, byId) {
  const m = modeOf(byId[fx.profile], fx.mode)
  return m?.channels?.length ?? 0
}

/** [start, end] inclusive DMX address span for a fixture. */
export function spanOf(fx, byId) {
  return [fx.address, fx.address + footprintOf(fx, byId) - 1]
}

/** Returns a map fxId -> Set<fxId> of address-overlap conflicts. */
export function conflicts(fixtures, byId) {
  const out = {}
  const spans = fixtures.map(f => ({ id: f.id, u: f.universe, span: spanOf(f, byId) }))
  for (let i = 0; i < spans.length; i++) {
    for (let j = i + 1; j < spans.length; j++) {
      const a = spans[i], b = spans[j]
      if (a.u !== b.u) continue
      const lo = Math.max(a.span[0], b.span[0])
      const hi = Math.min(a.span[1], b.span[1])
      if (lo <= hi) {
        ;(out[a.id] ??= new Set()).add(b.id)
        ;(out[b.id] ??= new Set()).add(a.id)
      }
    }
  }
  return out
}

/** Return a copy of `fixtures` with sequential addresses footprint-spaced. */
export function autoPatch(fixtures, byId, start = 1, universe = 1) {
  let addr = start
  return fixtures.map(f => {
    if (f.universe !== universe) return f
    const next = { ...f, address: addr }
    addr += footprintOf(f, byId)
    return next
  })
}

/** Next free fixture id like "FX3", avoiding ids already in the rig. */
export function nextId(fixtures, prefix = 'FX') {
  const used = new Set(fixtures.map(f => f.id))
  let n = 1
  while (used.has(`${prefix}${n}`)) n++
  return `${prefix}${n}`
}

/** First unoccupied DMX address with room for `footprint` channels. */
export function nextFreeAddress(fixtures, byId, footprint, universe = 1) {
  const taken = []
  for (const f of fixtures) {
    if (f.universe !== universe) continue
    taken.push(spanOf(f, byId))
  }
  taken.sort((a, b) => a[0] - b[0])
  let addr = 1
  for (const [lo, hi] of taken) {
    if (addr + footprint - 1 < lo) break
    addr = Math.max(addr, hi + 1)
  }
  return Math.min(addr, 512)
}
