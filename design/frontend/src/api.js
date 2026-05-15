// Thin fetch wrappers around the design backend.
// Same-origin in production (Flask serves dist/); proxied to :5050 in dev.

async function req(method, url, body) {
  const opts = { method, headers: {} }
  if (body instanceof FormData) {
    opts.body = body
  } else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const r = await fetch(url, opts)
  const data = await r.json().catch(() => ({}))
  if (!r.ok) {
    const e = new Error(data.error || `${r.status} ${r.statusText}`)
    e.details = data.details
    throw e
  }
  return data
}

export const api = {
  meta: () => req('GET', '/api/meta'),

  profiles: {
    list: () => req('GET', '/api/profiles').then(d => d.profiles),
    get: id => req('GET', `/api/profiles/${id}`),
    save: p => req('PUT', `/api/profiles/${p.id}`, p),
    delete: id => req('DELETE', `/api/profiles/${id}`),
    importQxf: file => {
      const fd = new FormData()
      fd.append('file', file)
      return req('POST', '/api/profiles/import/qxf', fd)
    },
  },

  ofl: {
    search: q => req('GET', `/api/ofl/search?q=${encodeURIComponent(q)}`).then(d => d.results),
    import: key => req('POST', '/api/ofl/import', { key }),
  },

  rigs: {
    list: () => req('GET', '/api/rigs').then(d => d.rigs),
    get: name => req('GET', `/api/rigs/${name}`),
    save: (name, rig) => req('PUT', `/api/rigs/${name}`, rig),
    delete: name => req('DELETE', `/api/rigs/${name}`),
    autoPatch: (name, rig, start = 1, universe = 1) =>
      req('POST', `/api/rigs/${name}/auto_patch`, { rig, start, universe }),
    exportUrl: name => `/api/export/${name}`,
  },
}
