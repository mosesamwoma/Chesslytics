import SeverityBadge from './SeverityBadge.jsx'
import { categoryLabel, motifLabel, phaseLabel } from '../labels.js'

function formatEval(value) {
  if (value === null || value === undefined) return '—'
  return `${value >= 0 ? '+' : ''}${Number(value).toFixed(2)}`
}

function formatClock(seconds) {
  if (seconds === null || seconds === undefined) return null
  const total = Math.max(0, Math.round(seconds))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

export default function MistakeCard({ mistake, onSelect, selected }) {
  const clock = formatClock(mistake.time_remaining)
  const motifs = mistake.facts?.motifs_allowed || []
  const hung = mistake.facts?.hung_piece
  return (
    <div className="card mistake-card">
      <div className="head">
        <div>
          <strong>
            Move {mistake.move_number}
            {mistake.color === 'white' ? '.' : '...'}
          </strong>{' '}
          <span className="secondary">{mistake.player || mistake.color}</span>
        </div>
        <div className="row">
          <SeverityBadge severity={mistake.severity} />
          <span className="badge">{categoryLabel(mistake.category)}</span>
          <button type="button" className="button" onClick={() => onSelect && onSelect(mistake)}>
            {selected ? 'Hide board' : 'Show board'}
          </button>
        </div>
      </div>

      <div className="moves">
        Played <span className="played mono">{mistake.played_move || '—'}</span> &middot; Engine
        preferred <span className="best mono">{mistake.best_move || '—'}</span>
      </div>

      <div className="row secondary" style={{ fontSize: 13 }}>
        <span>
          Loss <strong>{Number(mistake.loss).toFixed(2)}</strong> pawns
        </span>
        <span>
          Eval {formatEval(mistake.eval_before)} &rarr; {formatEval(mistake.eval_after)}
        </span>
        <span>
          Win {Number(mistake.winpct_before).toFixed(0)}% &rarr;{' '}
          {Number(mistake.winpct_after).toFixed(0)}%
        </span>
        <span>{phaseLabel(mistake.phase)}</span>
        {clock ? <span>Clock {clock}</span> : null}
        {mistake.in_time_pressure ? <span className="badge">time pressure</span> : null}
        {mistake.game_decided ? <span className="badge">decided position</span> : null}
        {motifs.map((motif) => (
          <span className="badge" key={`${motif.kind}-${motif.detail || ''}`}>
            {motifLabel(motif.kind)}
          </span>
        ))}
      </div>

      {motifs.length ? (
        <ul className="muted" style={{ marginTop: 8, marginBottom: 0, fontSize: 13 }}>
          {motifs.map((motif) => (
            <li key={`${motif.kind}-${motif.detail || ''}`}>{motif.detail || motifLabel(motif.kind)}</li>
          ))}
        </ul>
      ) : null}

      {hung && hung.square ? (
        <p className="muted" style={{ marginTop: 8, marginBottom: 0, fontSize: 13 }}>
          {hung.name || hung.piece} on {hung.square}
          {hung.see_pawns
            ? ` — the opponent wins ${Number(hung.see_pawns).toFixed(1)} pawns by exchange`
            : null}
        </p>
      ) : null}

      {mistake.category_basis ? (
        <p className="muted" style={{ marginTop: 8, marginBottom: 0, fontSize: 13 }}>
          {mistake.category_basis}
        </p>
      ) : null}
    </div>
  )
}
