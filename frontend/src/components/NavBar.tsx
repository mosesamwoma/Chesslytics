import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.tsx'

const LINKS = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/games', label: 'Games' },
  { to: '/jobs', label: 'Jobs' },
  { to: '/patterns', label: 'Patterns' },
  { to: '/training', label: 'Training' },
  { to: '/dna', label: 'Chess DNA' },
  { to: '/coach', label: 'Coach' },
]

function storedTheme(): string | null {
  try {
    return window.localStorage.getItem('chess-theme')
  } catch {
    return null
  }
}

function ThemeIcon({ theme }: { theme: string }) {
  if (theme === 'dark') {
    return (
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
        <path d="M20.5 14.2A8.5 8.5 0 0 1 9.8 3.5a8.5 8.5 0 1 0 10.7 10.7z" fill="currentColor" />
      </svg>
    )
  }
  if (theme === 'light') {
    return (
      <svg
        viewBox="0 0 24 24"
        width="18"
        height="18"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="4" fill="currentColor" />
        <path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" />
    </svg>
  )
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
  const initial = (user?.username || '?').slice(0, 1)

  return (
    <nav className="nav">
      <NavLink to="/" end className="nav-brand">
        <span className="nav-logo" aria-hidden="true">
          &#9822;
        </span>
        <span>Chesslytics</span>
      </NavLink>
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
        className="icon-button"
        onClick={() => setTheme(next)}
        title={`Colour theme: ${theme}. Click to switch.`}
        aria-label={`Colour theme: ${theme}. Click to switch.`}
      >
        <ThemeIcon theme={theme} />
      </button>
      {status === 'authenticated' ? (
        <>
          {user?.is_admin ? (
            <NavLink
              to="/admin"
              className={({ isActive }) => (isActive ? 'nav-chip active' : 'nav-chip')}
            >
              Admin console
            </NavLink>
          ) : null}
          <NavLink
            to="/account"
            className={({ isActive }) => (isActive ? 'user-pill active' : 'user-pill')}
            title="Account settings"
          >
            <span className="avatar" aria-hidden="true">
              {initial}
            </span>
            <span>{user?.username}</span>
          </NavLink>
          <button type="button" className="button" onClick={logout}>
            Sign out
          </button>
        </>
      ) : null}
    </nav>
  )
}
