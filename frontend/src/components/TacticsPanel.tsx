import { themeLabel } from '../labels.ts'
import type { Tactics } from '../types.ts'

interface TacticsPanelProps {
  tactics: Tactics | undefined | null
  onFocus?: (squares: string[]) => void
  compact?: boolean
}

const OUTCOMES: Record<string, string> = {
  mate: 'leads to checkmate',
  wins_material: 'wins material',
  promotion: 'promotes a pawn',
}

function FocusButton({
  squares,
  onFocus,
}: {
  squares: string[]
  onFocus?: (squares: string[]) => void
}) {
  if (!onFocus || !squares.length) return null
  return (
    <button type="button" className="link-button focus-link" onClick={() => onFocus(squares)}>
      show on board
    </button>
  )
}

export default function TacticsPanel({ tactics, onFocus, compact = false }: TacticsPanelProps) {
  if (!tactics || tactics.failed) return null
  const hasContent =
    tactics.themes.length > 0 ||
    tactics.missed.length > 0 ||
    tactics.allowed.length > 0 ||
    tactics.forced_mate !== null ||
    tactics.exchange !== null ||
    (tactics.line !== null && tactics.line.outcome !== 'none')
  if (!hasContent) return null

  const line = tactics.line
  const mate = tactics.forced_mate

  return (
    <div className="tactics">
      <div className="row">
        {tactics.themes.map((theme) => (
          <span className="badge theme" key={theme}>
            {themeLabel(theme)}
          </span>
        ))}
        <FocusButton squares={tactics.squares} onFocus={onFocus} />
      </div>

      {!compact && tactics.missed.length ? (
        <div className="tactic-group">
          <div className="tactic-title">What you missed</div>
          <ul>
            {tactics.missed.map((entry) => (
              <li key={`${entry.kind}-${entry.detail}`}>
                {entry.detail} <FocusButton squares={entry.squares} onFocus={onFocus} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {!compact && tactics.allowed.length ? (
        <div className="tactic-group">
          <div className="tactic-title">What your move allowed</div>
          <ul>
            {tactics.allowed.slice(0, 5).map((entry) => (
              <li key={`${entry.kind}-${entry.detail}`}>
                {entry.detail} <FocusButton squares={entry.squares} onFocus={onFocus} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {line && line.outcome !== 'none' && line.san.length ? (
        <p className="muted tactic-line">
          Engine line <span className="mono best">{line.san.join(' ')}</span>{' '}
          {OUTCOMES[line.outcome] || line.outcome}
          {line.outcome === 'wins_material' ? ` (about ${(line.gain_cp / 100).toFixed(1)} pawns)` : ''}
          {line.mate_in ? ` in ${line.mate_in}` : ''}.
        </p>
      ) : null}

      {mate ? (
        <p className="muted tactic-line">
          {mate.for === 'mover'
            ? `A forced mate in ${mate.in} was available: `
            : `Your move allowed a forced mate in ${mate.in}: `}
          <span className="mono">{mate.san.join(' ')}</span>
        </p>
      ) : null}

      {tactics.exchange ? (
        <p className="muted tactic-line">
          Exchange <span className="mono">{tactics.exchange}</span>
        </p>
      ) : null}

      <p className="muted tactic-note">
        Pattern-based detection, not a proof. Treat these labels as hints and check the board.
      </p>
    </div>
  )
}
