import { useState } from 'react'
import type { FormEvent } from 'react'
import { useRetryAfter } from '../hooks/useRetryAfter.ts'
import { toProblem } from '../services/api.ts'
import type { Problem } from '../services/api.ts'
import { importAndAnalyze } from '../services/analysisService.ts'
import { importGames } from '../services/gamesService.ts'
import type { UploadSummary } from '../types.ts'
import ErrorNotice from './ErrorNotice.tsx'

interface ImportFormProps {
  onImported: (summary: UploadSummary | null) => void
  disabled?: boolean
}

export default function ImportForm({ onImported, disabled = false }: ImportFormProps) {
  const [source, setSource] = useState<'chesscom' | 'lichess'>('chesscom')
  const [username, setUsername] = useState('')
  const [maxGames, setMaxGames] = useState(50)
  const [months, setMonths] = useState(1)
  const [analyze, setAnalyze] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Problem>(null)
  const [message, setMessage] = useState<string | null>(null)
  const gate = useRetryAfter(error)

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setMessage(null)
    const options = { source, username: username.trim(), max_games: maxGames, months }
    try {
      if (analyze) {
        const summary = await importAndAnalyze(options)
        setMessage(
          `Imported ${summary.stored} new ${summary.stored === 1 ? 'game' : 'games'}` +
            (summary.skipped ? ` (${summary.skipped} already stored)` : '') +
            '.',
        )
        onImported(summary)
      } else {
        const summary = (await importGames(options)) as { stored: number; skipped: number }
        setMessage(
          `Imported ${summary.stored} new ${summary.stored === 1 ? 'game' : 'games'}` +
            (summary.skipped ? ` (${summary.skipped} already stored)` : '') +
            '.',
        )
        onImported(null)
      }
    } catch (err) {
      setError(toProblem(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card" onSubmit={submit} style={{ marginTop: 16 }}>
      <h2>Import by username</h2>
      <p className="subtitle">
        Fetch recent public games straight from Chess.com or Lichess. No PGN file needed.
      </p>
      <div className="filters">
        <div className="field">
          <label htmlFor="import-source">Site</label>
          <select
            id="import-source"
            value={source}
            onChange={(event) => setSource(event.target.value as 'chesscom' | 'lichess')}
          >
            <option value="chesscom">Chess.com</option>
            <option value="lichess">Lichess</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="import-username">Username</label>
          <input
            id="import-username"
            type="text"
            required
            minLength={2}
            maxLength={40}
            autoComplete="off"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="import-count">Newest games</label>
          <input
            id="import-count"
            type="number"
            min={1}
            max={300}
            value={maxGames}
            onChange={(event) =>
              setMaxGames(Math.max(1, Math.min(300, Number(event.target.value) || 1)))
            }
          />
        </div>
        {source === 'chesscom' ? (
          <div className="field">
            <label htmlFor="import-months">Months to look back</label>
            <input
              id="import-months"
              type="number"
              min={1}
              max={6}
              value={months}
              onChange={(event) =>
                setMonths(Math.max(1, Math.min(6, Number(event.target.value) || 1)))
              }
            />
          </div>
        ) : null}
      </div>
      <label className="row" style={{ marginTop: 8 }}>
        <input
          type="checkbox"
          checked={analyze}
          onChange={(event) => setAnalyze(event.target.checked)}
        />
        <span>Analyze the games after importing (tracks this username as you)</span>
      </label>
      <ErrorNotice error={error} style={{ marginTop: 12 }} />
      {message ? (
        <div className="notice good" style={{ marginTop: 12 }}>
          {message}
        </div>
      ) : null}
      <div className="row" style={{ marginTop: 12 }}>
        <button
          type="submit"
          className="button primary"
          disabled={busy || disabled || gate.blocked || !username.trim()}
        >
          {busy ? 'Importing…' : 'Import games'}
        </button>
      </div>
    </form>
  )
}
