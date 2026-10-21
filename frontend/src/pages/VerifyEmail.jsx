import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'
import { verifyEmail } from '../services/authService.js'

export default function VerifyEmail() {
  const { status, refreshUser } = useAuth()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [token] = useState(() => params.get('token') || '')
  const [state, setState] = useState(token ? 'working' : 'missing')
  const [message, setMessage] = useState('')
  const started = useRef(false)

  useEffect(() => {
    navigate('/verify-email', { replace: true })
  }, [navigate])

  useEffect(() => {
    if (!token || started.current) return
    started.current = true
    verifyEmail(token)
      .then(async () => {
        if (status === 'authenticated') await refreshUser().catch(() => null)
        setState('done')
      })
      .catch((err) => {
        setMessage(err.message)
        setState('failed')
      })
  }, [token, status, refreshUser])

  return (
    <div className="card login">
      <h1>Confirm your email</h1>
      {state === 'working' ? <p className="subtitle">Confirming your address…</p> : null}
      {state === 'done' ? (
        <div className="notice good">Your email address is confirmed.</div>
      ) : null}
      {state === 'failed' ? <div className="notice error">{message}</div> : null}
      {state === 'missing' ? (
        <div className="notice error">
          This page needs a confirmation link. Open the link from your email.
        </div>
      ) : null}
      {state !== 'working' ? (
        <Link className="button primary" to={status === 'authenticated' ? '/account' : '/'}>
          {status === 'authenticated' ? 'Back to your account' : 'Go to sign in'}
        </Link>
      ) : null}
    </div>
  )
}
