import { useEffect } from 'react'

export default function Toast({ msg, kind = 'info', onClose, ttl = 4000 }) {
  useEffect(() => {
    if (!msg) return
    const t = setTimeout(onClose, ttl)
    return () => clearTimeout(t)
  }, [msg, ttl, onClose])
  if (!msg) return null
  return <div className={`toast ${kind}`}>{msg}</div>
}
