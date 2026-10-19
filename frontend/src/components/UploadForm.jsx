import { useState } from 'react'
import { uploadAndAnalyze } from '../services/analysisService.js'

export default function UploadForm({ onUploaded, disabled = false }) {
  const [file, setFile] = useState(null)
  const [player, setPlayer] = useState('')
  const [color, setColor] = useState('both')
  const [depth, setDepth] = useState(12)
  const [minLoss, setMinLoss] = useState(1)
  const [ignoreDecided, setIgnoreDecided] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  const submit = async (event) => {
    event.preventDefault()
    if (!file) {
      setError('Choose a PGN file first.')
      return
    }
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const summary = await uploadAndAnalyze(file, {
        player: player || undefined,
        color,
        depth,
        min_loss: minLoss,
        ignore_decided: ignoreDecided,
      })
      setResult(summary)
      if (onUploaded) onUploaded(summary)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <h2>Analyze a PGN export</h2>
      <p className="subtitle">
        Every move is evaluated with Stockfish in the background, so you can keep using the site
        while a large export is processed.
      </p>

      <div className="filters" style={{ marginBottom: 12 }}>
        <div className="field" style={{ flex: '1 1 220px' }}>
          <label htmlFor="pgn">PGN file</label>
          <input
            id="pgn"
            type="file"
            accept=".pgn,.txt"
            onChange={(event) => setFile(event.target.files?.[0] || null)}
          />
        </div>
        <div className="field">
          <label htmlFor="player">Your username</label>
          <input
            id="player"
            type="text"
            placeholder="optional"
            value={player}
            onChange={(event) => setPlayer(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="color">Colour</label>
          <select id="color" value={color} onChange={(event) => setColor(event.target.value)}>
            <option value="both">both</option>
            <option value="white">white</option>
            <option value="black">black</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="depth">Depth</label>
          <input
            id="depth"
            type="number"
            min="4"
            max="18"
            value={depth}
            onChange={(event) => setDepth(Number(event.target.value))}
          />
        </div>
        <div className="field">
          <label htmlFor="min-loss">Min loss (pawns)</label>
          <input
            id="min-loss"
            type="number"
            step="0.1"
            min="0"
            value={minLoss}
            onChange={(event) => setMinLoss(Number(event.target.value))}
          />
        </div>
        <div className="field">
          <label htmlFor="decided">Decided positions</label>
          <select
            id="decided"
            value={ignoreDecided ? 'ignore' : 'include'}
            onChange={(event) => setIgnoreDecided(event.target.value === 'ignore')}
          >
            <option value="ignore">ignore them</option>
            <option value="include">count them</option>
          </select>
        </div>
      </div>

      <div className="row">
        <button type="submit" className="button primary" disabled={busy || disabled}>
          {busy ? 'Uploading…' : 'Upload and analyze'}
        </button>
        {busy ? <span className="spinner" aria-hidden="true" /> : null}
        {disabled && !busy ? (
          <span className="muted">An analysis is already running for your account.</span>
        ) : null}
      </div>

      {error ? (
        <div className="notice error" style={{ marginTop: 12 }}>
          {error}
        </div>
      ) : null}

      {result ? (
        <div className={result.job ? 'notice good' : 'notice'} style={{ marginTop: 12 }}>
          Read {result.parsed} {result.parsed === 1 ? 'game' : 'games'} &middot; {result.stored} new
          &middot; {result.skipped} already stored
          {result.errors && result.errors.length
            ? ` · ${result.errors.length} skipped while parsing`
            : ''}
          {result.job_error ? ` · ${result.job_error}` : ''}
        </div>
      ) : null}
    </form>
  )
}
