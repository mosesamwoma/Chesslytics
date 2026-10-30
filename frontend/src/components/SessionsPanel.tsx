import { useState } from 'react'
import ErrorNotice from './ErrorNotice.tsx'
import { useAuth } from '../auth/AuthContext.tsx'
import { useAsync } from '../hooks/useAsync.ts'
import { toProblem } from '../services/api.ts'
import type { Problem } from '../services/api.ts'
import { listSessions, revokeOtherSessions, revokeSession } from '../services/authService.ts'

function describeAgent(agent: string | null): string {
  if (!agent) return 'Unknown device'
  const browser = /Edg\//.test(agent)
    ? 'Edge'
    : /Chrome\//.test(agent)
      ? 'Chrome'
      : /Firefox\//.test(agent)
        ? 'Firefox'
        : /Safari\//.test(agent)
          ? 'Safari'
          : 'Browser'
  const system = /Windows/.test(agent)
    ? 'Windows'
    : /Android/.test(agent)
      ? 'Android'
      : /iPhone|iPad|iOS/.test(agent)
        ? 'iOS'
        : /Mac OS X/.test(agent)
          ? 'macOS'
          : /Linux/.test(agent)
            ? 'Linux'
            : 'unknown system'
  return `${browser} on ${system}`
}

function formatWhen(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export default function SessionsPanel() {
  const { endSession } = useAuth()
  const sessions = useAsync(() => listSessions(), [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Problem>(null)

  const revoke = async (id: number) => {
    setBusy(true)
    setError(null)
    try {
      const result = await revokeSession(id)
      if (result.signed_out) {
        endSession()
        return
      }
      sessions.reload()
    } catch (err) {
      setError(toProblem(err))
    } finally {
      setBusy(false)
    }
  }

  const revokeOthers = async () => {
    setBusy(true)
    setError(null)
    try {
      await revokeOtherSessions()
      sessions.reload()
    } catch (err) {
      setError(toProblem(err))
    } finally {
      setBusy(false)
    }
  }

  const rows = sessions.data?.sessions || []

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h2>Where you are signed in</h2>
      <p className="subtitle">
        Each browser or phone you sign in on is listed here. If you do not recognise one, sign it out
        and change your password.
      </p>
      <ErrorNotice error={sessions.error || error} />
      <div className="list" style={{ marginTop: 12 }}>
        {rows.map((row) => (
          <div className="row session-row" key={row.id}>
            <div>
              <strong>{describeAgent(row.user_agent)}</strong>
              {row.current ? <span className="badge theme"> this device</span> : null}
              <div className="muted" style={{ fontSize: 13 }}>
                {row.ip || 'unknown address'} &middot; last active {formatWhen(row.last_seen_at)}
              </div>
            </div>
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => revoke(row.id)}
            >
              {row.current ? 'Sign out' : 'Revoke'}
            </button>
          </div>
        ))}
      </div>
      {rows.length > 1 ? (
        <div className="row" style={{ marginTop: 12 }}>
          <button type="button" className="button" disabled={busy} onClick={revokeOthers}>
            Sign out all other devices
          </button>
        </div>
      ) : null}
    </div>
  )
}
