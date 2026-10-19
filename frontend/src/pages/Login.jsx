import { useState } from 'react'
import { useAuth } from '../auth/AuthContext.jsx'

export default function Login() {
  const { login, register, info } = useAuth()
  const [mode, setMode] = useState('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const creating = mode === 'register'

  const switchMode = (next) => {
    setMode(next)
    setError(null)
    setPassword('')
    setConfirm('')
  }

  const submit = async (event) => {
    event.preventDefault()
    setError(null)
    if (creating && password !== confirm) {
      setError('The two passwords do not match.')
      return
    }
    setBusy(true)
    try {
      if (creating) {
        await register(username.trim(), password)
      } else {
        await login(username.trim(), password)
      }
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <main className="main">
      <form className="card login" onSubmit={submit}>
        <h1>Chesslytics</h1>
        <p className="subtitle">
          {creating ? 'Create your account.' : 'Sign in to continue.'}
        </p>
        <div className="field">
          <label htmlFor="username">Username</label>
          <input
            id="username"
            type="text"
            autoComplete="username"
            autoFocus
            required
            maxLength={64}
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete={creating ? 'new-password' : 'current-password'}
            required
            minLength={creating ? info.min_password_length : undefined}
            maxLength={128}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        {creating ? (
          <div className="field">
            <label htmlFor="confirm">Repeat password</label>
            <input
              id="confirm"
              type="password"
              autoComplete="new-password"
              required
              maxLength={128}
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
            />
            <span className="muted">
              At least {info.min_password_length} characters. A short passphrase of unrelated
              words works well.
            </span>
          </div>
        ) : null}
        {error ? <div className="notice error">{error}</div> : null}
        <button type="submit" className="button primary" disabled={busy}>
          {busy ? 'Please wait…' : creating ? 'Create account' : 'Sign in'}
        </button>
        {creating ? (
          <button type="button" className="button" onClick={() => switchMode('login')}>
            I already have an account
          </button>
        ) : info.registration_enabled ? (
          <button type="button" className="button" onClick={() => switchMode('register')}>
            Create an account
          </button>
        ) : (
          <p className="muted">Registration is currently closed.</p>
        )}
      </form>
    </main>
  )
}
