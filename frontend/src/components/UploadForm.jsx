import { useState } from 'react'
import { uploadAndAnalyze } from '../services/analysisService.js'

export default function UploadForm({ onComplete }) {
  const [file, setFile] = useState(null)
  const [player, setPlayer] = useState('')
  const [color, setColor] = useState('both')
  const [depth, setDepth] = useState(12)
  const [minLoss, setMinLoss] = useState(1)
  const [ignoreDecided, setIgnoreDecided] = useState(true)
  const [useCache, setUseCache] = useState(true)
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
        use_cache: useCache,
      })
      setResult(summary)
      if (onComplete) onComplete(summary)
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
        Every move is evaluated with Stockfish and cached, so re-running with different thresholds
        costs no engine time.
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
            max="30"
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
        <div className="field">
          <label htmlFor="cache">Cache</label>
          <select
            id="cache"
            value={useCache ? 'use' : 'skip'}
            onChange={(event) => setUseCache(event.target.value === 'use')}
          >
            <option value="use">reuse engine results</option>
            <option value="skip">do not read or write</option>
          </select>
        </div>
      </div>

      <div className="row">
        <button type="submit" className="button primary" disabled={busy}>
          {busy ? 'Analyzing…' : 'Upload and analyze'}
        </button>
        {busy ? <span className="spinner" aria-hidden="true" /> : null}
        {busy ? (
          <span className="muted">
            Stockfish evaluates every move twice; a large export takes minutes.
          </span>
        ) : null}
      </div>

      {error ? (
        <div className="notice error" style={{ marginTop: 12 }}>
          {error}
        </div>
      ) : null}

      {result ? (
        <div className="notice good" style={{ marginTop: 12 }}>
          Analyzed {result.parsed} games &middot; {result.mistakes?.length || 0} mistakes &middot;{' '}
          {result.counts?.moves_analyzed || 0} moves evaluated
          {result.persistence ? ` · stored ${result.persistence.mistakes} records` : ''}
          {result.errors && result.errors.length
            ? ` · ${result.errors.length} games skipped while parsing`
            : ''}
        </div>
      ) : null}
    </form>
  )
}
