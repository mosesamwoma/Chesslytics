import { PATTERN_KIND_LABELS, categoryLabel, motifLabel } from '../labels.js'

const KEY_LABELS = { category: categoryLabel, motif: motifLabel }

export default function PatternCard({ pattern }) {
  const labelFor = KEY_LABELS[pattern.kind]
  const label = labelFor ? labelFor(pattern.key) : pattern.key
  return (
    <div className="card">
      <div className="game-card">
        <div>
          <strong>{label}</strong>
          <div className="secondary" style={{ fontSize: 13 }}>
            {PATTERN_KIND_LABELS[pattern.kind] || pattern.kind}
            {pattern.description && pattern.description !== label ? ` · ${pattern.description}` : ''}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 22, fontWeight: 600 }}>{pattern.count}</div>
          <div className="muted" style={{ fontSize: 12 }}>
            {pattern.games} {pattern.games === 1 ? 'game' : 'games'}
          </div>
        </div>
      </div>
      {pattern.recurring ? (
        <div className="tag-row">
          <span className="badge">
            <span className="dot dot-good" aria-hidden="true" />
            recurs across games
          </span>
        </div>
      ) : (
        <div className="tag-row">
          <span className="badge">
            <span className="dot dot-muted" aria-hidden="true" />
            seen in one game only
          </span>
        </div>
      )}
    </div>
  )
}
