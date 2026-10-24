import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.tsx'
import ErrorNotice from '../components/ErrorNotice.tsx'
import RecoveryCode from '../components/RecoveryCode.tsx'
import { useRetryAfter } from '../hooks/useRetryAfter.ts'
import { toProblem } from '../services/api.ts'
import type { Problem } from '../services/api.ts'
import { forgotPassword, recoverPassword } from '../services/authService.ts'

type Mode = 'email' | 'code'

export default function ForgotPassword() {
  const { info } = useAuth()
  const navigate = useNavigate()
  const [mode, setMode] = useState<Mode>(info.email_enabled ? 'email' : 'code')
  const [identifier, setIdentifier] = useState('')
  const [username, setUsername] = useState('')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [repeat, setRepeat] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Problem>(null)
  const [sent, setSent] = useState(false)
  const [newCode, setNewCode] = useState<string | null>(null)
  const gate = useRetryAfter(error)

  const switchMode = (next: Mode) => {
    setMode(next)
    setError(null)
  }

  const submitEmail = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await forgotPassword(identifier.trim())
      setSent(true)
    } catch (err) {
      setError(toProblem(err))
    } finally {
      setBusy(false)
    }
  }

  const submitCode = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    if (password !== repeat) {
      setError('The two passwords do not match.')
      return
    }
    setBusy(true)
    try {
      const result = await recoverPassword(username.trim(), code.trim(), password)
      setNewCode(result.recovery_code)
    } catch (err) {
      setError(toProblem(err))
    } finally {
      setBusy(false)
    }
  }

  if (newCode) {
    return (
      <RecoveryCode
        code={newCode}
        heading="Password changed"
        intro="Your password is updated and you are signed out everywhere. Your old recovery code was used up, so here is a new one. Save it now; it is shown only once."
        continueLabel="Continue to sign in"
        onDone={() => navigate('/')}
      />
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
          Nothing arrived? Check your spam folder, or use your recovery code instead.
        </p>
        <button type="button" className="button" onClick={() => setSent(false)}>
          Try again
        </button>
        <Link className="button" to="/">
          Back to sign in
        </Link>
      </div>
    )
  }

  return (
    <div className="card login">
      <h1>Reset your password</h1>
      {info.email_enabled ? (
        <div className="tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'email'}
            className={mode === 'email' ? 'tab active' : 'tab'}
            onClick={() => switchMode('email')}
          >
            By email
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'code'}
            className={mode === 'code' ? 'tab active' : 'tab'}
            onClick={() => switchMode('code')}
          >
            Recovery code
          </button>
        </div>
      ) : null}

      {mode === 'email' && info.email_enabled ? (
        <form className="login" style={{ padding: 0, maxWidth: 'none' }} onSubmit={submitEmail}>
          <p className="subtitle">
            Enter your username or the email address on your account. We only send a link when
            that address has been confirmed.
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
            {busy ? 'Please wait…' : 'Email me a reset link'}
          </button>
        </form>
      ) : (
        <form className="login" style={{ padding: 0, maxWidth: 'none' }} onSubmit={submitCode}>
          <p className="subtitle">
            Enter your username and the recovery code you saved when you created your account.
            No email and no administrator needed.
          </p>
          <div className="field">
            <label htmlFor="recover-username">Username</label>
            <input
              id="recover-username"
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
            <label htmlFor="recover-code">Recovery code</label>
            <input
              id="recover-code"
              type="text"
              className="mono"
              autoComplete="off"
              spellCheck={false}
              required
              maxLength={40}
              placeholder="XXXX-XXXX-XXXX-XXXX"
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="recover-password">New password</label>
            <input
              id="recover-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={info.min_password_length}
              maxLength={128}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="recover-repeat">Repeat new password</label>
            <input
              id="recover-repeat"
              type="password"
              autoComplete="new-password"
              required
              maxLength={128}
              value={repeat}
              onChange={(event) => setRepeat(event.target.value)}
            />
            <span className="muted">At least {info.min_password_length} characters.</span>
          </div>
          <ErrorNotice error={error} />
          <button type="submit" className="button primary" disabled={busy || gate.blocked}>
            {busy ? 'Please wait…' : 'Set new password'}
          </button>
          <p className="muted">
            No recovery code? {info.email_enabled
              ? 'Use the By email tab if you confirmed an address, or ask the administrator.'
              : 'Ask the administrator for a one-time reset link.'}
          </p>
        </form>
      )}
      <Link className="button" to="/">
        Back to sign in
      </Link>
    </div>
  )
}
