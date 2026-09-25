import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'

const LINKS = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/games', label: 'Games' },
  { to: '/patterns', label: 'Patterns' },
  { to: '/dna', label: 'Chess DNA' },
]

function storedTheme() {
  try {
    return window.localStorage.getItem('chess-theme')
  } catch {
    return null
  }
}

export default function NavBar() {
  const [theme, setTheme] = useState(() => storedTheme() || 'system')

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') {
      root.removeAttribute('data-theme')
    } else {
      root.setAttribute('data-theme', theme)
    }
    try {
      window.localStorage.setItem('chess-theme', theme)
    } catch {
      /* storage unavailable */
    }
  }, [theme])

  const next = theme === 'dark' ? 'light' : theme === 'light' ? 'system' : 'dark'

  return (
    <nav className="nav">
      <span className="nav-brand">Chess Mistakes Miner</span>
      <div className="nav-links">
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className={({ isActive }) => (isActive ? 'active' : undefined)}
          >
            {link.label}
          </NavLink>
        ))}
      </div>
      <span className="nav-spacer" />
      <button
        type="button"
        className="button"
        onClick={() => setTheme(next)}
        title="Switch colour theme"
      >
        Theme: {theme}
      </button>
    </nav>
  )
}
