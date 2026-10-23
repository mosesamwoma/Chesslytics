import { Link } from 'react-router-dom'
import type { Game } from '../types.ts'

interface GameCardProps {
  game: Game
  player?: string | null
  onDelete?: (game: Game) => void
}

function accuracyText(game: Game, player: string | null | undefined): string | null {
  const { white, black } = game.accuracy
  if (white === null && black === null) return null
  const wanted = (player || '').trim().toLowerCase()
  if (wanted && game.white.trim().toLowerCase() === wanted && white !== null) {
    return `accuracy ${white.toFixed(1)}%`
  }
  if (wanted && game.black.trim().toLowerCase() === wanted && black !== null) {
    return `accuracy ${black.toFixed(1)}%`
  }
  const parts: string[] = []
  if (white !== null) parts.push(`White ${white.toFixed(1)}%`)
  if (black !== null) parts.push(`Black ${black.toFixed(1)}%`)
  return `accuracy ${parts.join(' · ')}`
}

export default function GameCard({ game, player, onDelete }: GameCardProps) {
  const accuracy = accuracyText(game, player)
  return (
    <div className="card">
      <div className="game-card">
        <div>
          <div className="players">
            {game.white} <span className="muted">vs</span> {game.black}
          </div>
          <div className="secondary" style={{ fontSize: 13 }}>
            {game.result || 'result unknown'}
            {game.date ? ` · ${game.date}` : ''}
            {game.time_control ? ` · ${game.time_control}` : ''}
          </div>
          {game.opening ? (
            <div className="muted" style={{ fontSize: 13 }}>
              {game.eco ? `${game.eco} ` : ''}
              {game.opening}
            </div>
          ) : null}
        </div>
        <div style={{ textAlign: 'right', fontSize: 13 }}>
          <div>{game.analyzed ? `${game.mistake_count} mistakes` : 'not analyzed'}</div>
          {accuracy ? <div className="secondary">{accuracy}</div> : null}
          <div className="muted">
            {game.move_count} {game.move_count === 1 ? 'move' : 'moves'}
            {game.analyzed_depth ? ` · depth ${game.analyzed_depth}` : ''}
          </div>
        </div>
      </div>

      {game.tags.length || game.notes ? (
        <div className="tag-list">
          {game.tags.map((tag) => (
            <span className="badge" key={tag}>
              {tag}
            </span>
          ))}
          {game.notes ? <span className="muted">has notes</span> : null}
        </div>
      ) : null}

      <div className="row" style={{ marginTop: 10 }}>
        <Link className="button" to={`/games/${game.id}`}>
          Open analysis
        </Link>
        {onDelete ? (
          <button type="button" className="button danger" onClick={() => onDelete(game)}>
            Delete
          </button>
        ) : null}
      </div>
    </div>
  )
}
