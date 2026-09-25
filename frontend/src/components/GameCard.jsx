import { Link } from 'react-router-dom'

export default function GameCard({ game, onDelete }) {
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
          <div className="muted">
            {game.move_count} {game.move_count === 1 ? 'move' : 'moves'}
            {game.analyzed_depth ? ` · depth ${game.analyzed_depth}` : ''}
          </div>
        </div>
      </div>

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
