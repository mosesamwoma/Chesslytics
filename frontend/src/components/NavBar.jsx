import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'

const LINKS = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/games', label: 'Games' },
  { to: '/patterns', label: 'Patterns' },
  { to: '/training', label: 'Training' },
  { to: '/dna', label: 'Chess DNA' },
  { to: '/coach', label: 'Coach' },
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
  const { status, user, logout } = useAuth()

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') {
      root.removeAttribute('data-theme')
    } else {
      root.setAttribute('data-theme', theme)
    }
    try {
      window.localStorage.setItem('chess-theme', theme)
    } catch {}
  }, [theme])

  const next = theme === 'dark' ? 'light' : theme === 'light' ? 'system' : 'dark'

  return (
    <nav className="nav">
      <span className="nav-brand">Chesslytics</span>
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
      {status === 'authenticated' ? (
        <>
          {user?.is_admin ? (
            <NavLink to="/admin" className="button">
              Admin
            </NavLink>
          ) : null}
          <NavLink to="/account" className="button" title="Account settings">
            {user?.username}
          </NavLink>
          <button type="button" className="button" onClick={logout}>
            Sign out
          </button>
        </>
      ) : null}
    </nav>
  )
}
