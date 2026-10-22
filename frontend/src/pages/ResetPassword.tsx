import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.tsx'
import ErrorNotice from '../components/ErrorNotice.tsx'
import { toProblem } from '../services/api.ts'
import type { Problem } from '../services/api.ts'
import { resetPassword } from '../services/authService.ts'

export default function ResetPassword() {
  const { info, status, endSession } = useAuth()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [token] = useState(() => params.get('token') || '')
  const [password, setPassword] = useState('')
  const [repeat, setRepeat] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Problem>(null)
  const [done, setDone] = useState(false)

  useEffect(() => {
    navigate('/reset-password', { replace: true })
  }, [navigate])

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    if (password !== repeat) {
      setError('The two passwords do not match.')
      return
    }
    setBusy(true)
    try {
      await resetPassword(token, password)
      setDone(true)
    } catch (err) {
      setError(toProblem(err))
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    return (
      <div className="card login">
        <h1>Password updated</h1>
        <p className="subtitle">You can now sign in with your new password.</p>
        <Link
          className="button primary"
          to="/"
          onClick={() => {
            if (status === 'authenticated') endSession()
          }}
        >
          Go to sign in
        </Link>
      </div>
    )
  }

  if (!token) {
    return (
      <div className="card login">
        <h1>Reset your password</h1>
        <div className="notice error">
          This page needs a reset link. Open the link from your email, or ask the administrator
          for a new one.
        </div>
        <Link className="button" to="/">
          Back to sign in
        </Link>
      </div>
    )
  }

  return (
    <form className="card login" onSubmit={submit}>
      <h1>Choose a new password</h1>
      <div className="field">
        <label htmlFor="reset-password">New password</label>
        <input
          id="reset-password"
          type="password"
          autoComplete="new-password"
          autoFocus
          required
          minLength={info.min_password_length}
          maxLength={128}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="reset-repeat">Repeat new password</label>
        <input
          id="reset-repeat"
          type="password"
          autoComplete="new-password"
          required
          maxLength={128}
          value={repeat}
          onChange={(event) => setRepeat(event.target.value)}
        />
        <span className="muted">
          At least {info.min_password_length} characters. A short passphrase of unrelated words
          works well.
        </span>
      </div>
      <ErrorNotice error={error} />
      <button type="submit" className="button primary" disabled={busy}>
        {busy ? 'Please wait…' : 'Set new password'}
      </button>
    </form>
  )
}
