import { useState } from 'react'
import { useAsync } from '../hooks/useAsync.ts'
import { toProblem } from '../services/api.ts'
import type { Problem } from '../services/api.ts'
import { getEmailStatus, sendTestEmail } from '../services/adminService.ts'
import ErrorNotice from './ErrorNotice.tsx'

const PROVIDER_NAMES: Record<string, string> = {
  smtp: 'SMTP server',
  gmail: 'Gmail (HTTPS API)',
  brevo: 'Brevo (HTTPS API)',
  resend: 'Resend (HTTPS API)',
  mailjet: 'Mailjet (HTTPS API)',
  smtp2go: 'SMTP2GO (HTTPS API)',
}

export default function EmailPanel() {
  const status = useAsync(() => getEmailStatus(), [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Problem>(null)
  const [message, setMessage] = useState<string | null>(null)

  const test = async () => {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const result = await sendTestEmail()
      setMessage(`A test email was sent to ${result.sent_to}. Check your inbox and spam folder.`)
    } catch (err) {
      setError(toProblem(err))
    } finally {
      setBusy(false)
    }
  }

  if (status.error) return <ErrorNotice error={status.error} />
  if (!status.data) return null
  const data = status.data

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div>
          <h2>Email</h2>
          <p className="subtitle" style={{ marginBottom: 0 }}>
            Needed for password reset by email, email confirmation and the weekly digest.
          </p>
        </div>
        <span className="badge">
          <span className={data.enabled ? 'dot dot-good' : 'dot dot-critical'} />
          {data.enabled ? 'working configuration' : 'not set up'}
        </span>
      </div>
      {data.enabled ? (
        <dl className="kv" style={{ marginTop: 12 }}>
          <dt>Provider</dt>
          <dd>{PROVIDER_NAMES[data.provider] || data.provider}</dd>
          <dt>Sends from</dt>
          <dd>{data.from}</dd>
          <dt>Links point to</dt>
          <dd>{data.public_url}</dd>
        </dl>
      ) : (
        <div className="notice error" style={{ marginTop: 12 }}>
          Password reset by email is hidden until these settings exist on the server:{' '}
          <strong>{data.missing.join(', ')}</strong>. Set them in your hosting dashboard and
          redeploy. The README explains the free Gmail setup step by step.
        </div>
      )}
      {data.enabled ? (
        <div className="row" style={{ marginTop: 12 }}>
          <button type="button" className="button" onClick={test} disabled={busy}>
            {busy ? 'Sending…' : 'Send a test email to my address'}
          </button>
          <span className="muted">Uses the email address on your own account.</span>
        </div>
      ) : null}
      <ErrorNotice error={error} style={{ marginTop: 12 }} />
      {message ? (
        <div className="notice good" style={{ marginTop: 12 }}>
          {message}
        </div>
      ) : null}
    </div>
  )
}
