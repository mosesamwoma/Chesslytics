import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'
import ErrorNotice from '../components/ErrorNotice.jsx'
import { useRetryAfter } from '../hooks/useRetryAfter.js'
import { forgotPassword } from '../services/authService.js'

export default function ForgotPassword() {
  const { info } = useAuth()
  const [identifier, setIdentifier] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [sent, setSent] = useState(false)
  const gate = useRetryAfter(error)

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await forgotPassword(identifier.trim())
      setSent(true)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  if (!info.email_enabled) {
    return (
      <div className="card login">
        <h1>Reset your password</h1>
        <p className="subtitle">
          Password reset by email is not set up on this server. Ask the administrator for a reset
          link.
        </p>
        <Link className="button" to="/">
          Back to sign in
        </Link>
      </div>
    )
  }

  if (sent) {
    return (
      <div className="card login">
        <h1>Check your email</h1>
        <p className="subtitle">
          If an account with a confirmed email address matches what you entered, a reset link is
          on its way. It works once and expires in one hour.
        </p>
        <p className="muted">
          Nothing arrived? Check your spam folder, or ask the administrator for a reset link.
        </p>
        <Link className="button" to="/">
          Back to sign in
        </Link>
      </div>
    )
  }

  return (
    <form className="card login" onSubmit={submit}>
      <h1>Reset your password</h1>
      <p className="subtitle">
        Enter your username or the email address on your account. We only send a link when that
        address has been confirmed.
      </p>
      <div className="field">
        <label htmlFor="identifier">Username or email</label>
        <input
          id="identifier"
          type="text"
          autoComplete="username"
          autoFocus
          required
          maxLength={254}
          value={identifier}
          onChange={(event) => setIdentifier(event.target.value)}
        />
      </div>
      <ErrorNotice error={error} />
      <button type="submit" className="button primary" disabled={busy || gate.blocked}>
        {busy ? 'Please wait…' : 'Send reset link'}
      </button>
      <Link className="button" to="/">
        Back to sign in
      </Link>
    </form>
  )
}
