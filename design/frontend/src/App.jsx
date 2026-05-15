import { useState } from 'react'
import Inventory from './tabs/Inventory.jsx'
import Rigging from './tabs/Rigging.jsx'
import Setlist from './tabs/Setlist.jsx'

const TABS = [
  { id: 'inventory', label: 'Inventory', component: Inventory },
  { id: 'rigging', label: 'Rigging', component: Rigging },
  { id: 'setlist', label: 'Setlist', component: Setlist },
]

export default function App() {
  const [tab, setTab] = useState('inventory')
  const Active = TABS.find(t => t.id === tab)?.component ?? (() => null)

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">dmx<span>·</span>ai design</div>
        <nav className="tabs">
          {TABS.map(t => (
            <button key={t.id} className={`tab ${tab === t.id ? 'active' : ''}`}
                    onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
      </header>
      <main className="main">
        <Active />
      </main>
    </div>
  )
}
