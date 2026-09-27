import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import ChessBoard from '../components/ChessBoard.jsx'
import SeverityBadge from '../components/SeverityBadge.jsx'
import StatTile from '../components/StatTile.jsx'
import { categoryLabel, phaseLabel } from '../labels.js'
import {
  getSolution,
  getStats,
  listPuzzles,
  submitAttempt,
} from '../services/trainingService.js'

const CATEGORIES = [
  'allowed_mate',
  'missed_mate',
  'hanging_piece',
  'missed_capture',
  'time_pressure',
  'opening',
  'middlegame',
  'endgame',
]

const SEVERITIES = ['blunder', 'mistake', 'inaccuracy']

const PROMOTION_NAMES = { q: 'queen', r: 'rook', b: 'bishop', n: 'knight' }

export function sideToMove(fen) {
  return (fen || '').split(' ')[1] === 'b' ? 'black' : 'white'
}

export function pieceAt(fen, square) {
  const placement = (fen || '').split(' ')[0]
  if (!placement || !square) return null
  const file = square.charCodeAt(0) - 97
  const rank = Number(square[1])
  if (file < 0 || file > 7 || !(rank >= 1 && rank <= 8)) return null
  const row = placement.split('/')[8 - rank]
  if (!row) return null
  let index = 0
  for (const char of row) {
    if (/\d/.test(char)) {
      index += Number(char)
      continue
    }
    if (index === file) {
      return { type: char.toLowerCase(), isWhite: char === char.toUpperCase() }
    }
    index += 1
  }
  return null
}

export function movesFrom(legalMoves, square) {
  return (legalMoves || []).filter((uci) => uci.slice(0, 2) === square)
}

export function destinations(legalMoves, square) {
  return [...new Set(movesFrom(legalMoves, square).map((uci) => uci.slice(2, 4)))]
}

export default function Training() {
  const [filters, setFilters] = useState({ category: '', severity: '', unseenOnly: false })
  const [data, setData] = useState(null)
  const [stats, setStats] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [index, setIndex] = useState(0)
  const [selected, setSelected] = useState(null)
  const [promotion, setPromotion] = useState(null)
  const [feedback, setFeedback] = useState(null)
  const [revealed, setRevealed] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [listing, summary] = await Promise.all([
        listPuzzles({ ...filters, limit: 50 }),
        getStats(),
      ])
      setData(listing)
      setStats(summary)
      setIndex(0)
      setSelected(null)
      setPromotion(null)
      setFeedback(null)
      setRevealed(null)
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => {
    load()
  }, [load])

  const puzzles = data?.puzzles || []
  const puzzle = puzzles[index] || null
  const legalMoves = puzzle?.legal_moves || []
  const mover = puzzle ? puzzle.orientation || sideToMove(puzzle.fen) : 'white'

  const shownFen = feedback?.fen_after || revealed?.fen || puzzle?.fen || ''
  const reachable = selected ? destinations(legalMoves, selected) : []

  const advance = useCallback(
    (step) => {
      setIndex((value) => {
        if (!puzzles.length) return 0
        return (value + step + puzzles.length) % puzzles.length
      })
      setSelected(null)
      setPromotion(null)
      setFeedback(null)
      setRevealed(null)
    },
    [puzzles.length],
  )

  useEffect(() => {
    const onKey = (event) => {
      if (event.key === 'ArrowRight') advance(1)
      if (event.key === 'ArrowLeft') advance(-1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [advance])

  const attempt = useCallback(
    async (uci) => {
      if (!puzzle) return
      setBusy(true)
      setError(null)
      try {
        const result = await submitAttempt(puzzle.id, { uci, player: puzzle.player })
        setFeedback(result)
        setSelected(null)
        setPromotion(null)
        setRevealed(null)
        setStats(await getStats())
        setData((current) =>
          current
            ? {
                ...current,
                puzzles: current.puzzles.map((row) =>
                  row.id === puzzle.id
                    ? {
                        ...row,
                        attempts: result.attempts?.attempts ?? row.attempts + 1,
                        solved: row.solved || result.correct,
                      }
                    : row,
                ),
              }
            : current,
        )
      } catch (err) {
        setError(err)
      } finally {
        setBusy(false)
      }
    },
    [puzzle],
  )

  const onSquareClick = useCallback(
    (square) => {
      if (!puzzle || feedback || busy) return
      const piece = pieceAt(shownFen, square)
      if (selected && reachable.includes(square)) {
        const candidates = movesFrom(legalMoves, selected).filter(
          (uci) => uci.slice(2, 4) === square,
        )
        if (candidates.length > 1) {
          setPromotion({ from: selected, to: square, candidates })
          return
        }
        if (candidates.length === 1) attempt(candidates[0])
        return
      }
      if (piece && ((mover === 'white') === piece.isWhite)) {
        setSelected(square === selected ? null : square)
        return
      }
      setSelected(null)
    },
    [attempt, busy, feedback, legalMoves, mover, puzzle, reachable, selected, shownFen],
  )

  const reveal = useCallback(async () => {
    if (!puzzle) return
    try {
      setRevealed(await getSolution(puzzle.id))
    } catch (err) {
      setError(err)
    }
  }, [puzzle])

  const weakest = stats?.weakest_category

  if (error && !data) {
    return (
      <div className="notice error">
        {error.message} <button type="button" className="button" onClick={load}>Retry</button>
      </div>
    )
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Training</h1>
          <p className="subtitle">
            Your own mistakes, replayed as puzzles. Find the move the engine wanted; a move
            within {data?.tolerance_winpct ?? 5} win% of the best counts.
          </p>
        </div>
        <Link className="button" to="/games">
          Games
        </Link>
      </div>

      {error ? (
        <div className="notice error" style={{ marginBottom: 16 }}>
          {error.message}
        </div>
      ) : null}

      {stats ? (
        <div className="tiles">
          <StatTile label="Puzzles available" value={stats.puzzles_available} />
          <StatTile label="Attempts" value={stats.attempts} />
          <StatTile label="Solved" value={stats.correct} />
          <StatTile
            label="Accuracy"
            value={`${stats.accuracy}%`}
            delta={weakest ? `weakest: ${categoryLabel(weakest.category)}` : null}
          />
        </div>
      ) : null}

      <div className="filters">
        <div className="field">
          <label htmlFor="category">Mistake type</label>
          <select
            id="category"
            value={filters.category}
            onChange={(event) => setFilters({ ...filters, category: event.target.value })}
          >
            <option value="">all types</option>
            {CATEGORIES.map((value) => (
              <option key={value} value={value}>
                {categoryLabel(value)}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="severity">Severity</label>
          <select
            id="severity"
            value={filters.severity}
            onChange={(event) => setFilters({ ...filters, severity: event.target.value })}
          >
            <option value="">any severity</option>
            {SEVERITIES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="unseen">Repetition</label>
          <select
            id="unseen"
            value={filters.unseenOnly ? 'unseen' : 'all'}
            onChange={(event) =>
              setFilters({ ...filters, unseenOnly: event.target.value === 'unseen' })
            }
          >
            <option value="all">every puzzle</option>
            <option value="unseen">only ones I have not tried</option>
          </select>
        </div>
        <span className="muted">
          {puzzles.length ? `${index + 1} of ${data.total}` : '0'} shown
        </span>
      </div>

      {!loading && !puzzles.length ? (
        <div className="notice">
          No puzzles match these filters. Mistakes are mined from your games — import a PGN and
          run an analysis on the <Link to="/games">Games</Link> page first.
        </div>
      ) : null}

      {puzzle ? (
        <div className="split">
          <div className="card">
            <div className="board-wrap">
              <ChessBoard
                fen={shownFen}
                orientation={mover}
                selected={selected}
                targets={reachable}
                lastMove={feedback?.played_uci || null}
                onSquareClick={onSquareClick}
              />
              <div className="board-controls">
                <button type="button" className="button" onClick={() => advance(-1)}>
                  &larr;
                </button>
                <button type="button" className="button" onClick={() => advance(1)}>
                  &rarr;
                </button>
                <span>
                  Move {puzzle.move_number}
                  {puzzle.color === 'white' ? '.' : '...'} &middot; you are{' '}
                  {puzzle.orientation || mover}
                </span>
              </div>
              <p className="muted" style={{ fontSize: 13, marginBottom: 0 }}>
                {feedback
                  ? 'Attempt recorded. Press → for the next puzzle.'
                  : 'Click the piece you want to move, then the square you want to move it to.'}
              </p>
              {promotion ? (
                <div className="row" style={{ marginTop: 8 }}>
                  <span className="secondary">Promote to</span>
                  {promotion.candidates.map((uci) => (
                    <button
                      key={uci}
                      type="button"
                      className="button primary"
                      onClick={() => attempt(uci)}
                      disabled={busy}
                    >
                      {PROMOTION_NAMES[uci.slice(4, 5)] || uci.slice(4, 5)}
                    </button>
                  ))}
                  <button type="button" className="button" onClick={() => setPromotion(null)}>
                    Cancel
                  </button>
                </div>
              ) : null}
            </div>
          </div>

          <div className="list">
            <div className="card">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <div>
                  <strong>Puzzle {puzzle.id}</strong>{' '}
                  <span className="secondary">
                    {puzzle.player || puzzle.color} as {puzzle.color}
                  </span>
                </div>
                <div className="row">
                  <SeverityBadge severity={puzzle.severity} />
                  <span className="badge">{categoryLabel(puzzle.category)}</span>
                </div>
              </div>
              <div className="row secondary" style={{ fontSize: 13, marginTop: 8 }}>
                <span>
                  Loss in the game <strong>{Number(puzzle.loss).toFixed(2)}</strong> pawns
                </span>
                <span>{phaseLabel(puzzle.phase)}</span>
                {puzzle.opening ? <span>{puzzle.opening}</span> : null}
                <span>
                  {puzzle.attempts
                    ? `tried ${puzzle.attempts}x${puzzle.solved ? ', solved' : ''}`
                    : 'not tried yet'}
                </span>
                {puzzle.in_book ? <span className="badge">theory</span> : null}
              </div>
              <div className="row" style={{ marginTop: 12 }}>
                <button type="button" className="button" onClick={reveal} disabled={!puzzle}>
                  Show solution
                </button>
                <Link className="button" to={`/games/${puzzle.game_id}`}>
                  Open the game
                </Link>
              </div>
            </div>

            {feedback ? (
              <div className={feedback.correct ? 'card good' : 'card bad'}>
                <strong>
                  {feedback.correct
                    ? feedback.verdict === 'mate'
                      ? 'Checkmate — correct'
                      : 'Correct'
                    : 'Not the move'}
                </strong>
                <div className="row secondary" style={{ fontSize: 13, marginTop: 6 }}>
                  <span>
                    You played <span className="played mono">{feedback.played_san}</span>
                  </span>
                  <span>
                    Engine wanted{' '}
                    <span className="best mono">{feedback.best_move || feedback.best_move_uci}</span>
                  </span>
                  {feedback.loss_vs_best ? (
                    <span>loss vs best {Number(feedback.loss_vs_best).toFixed(2)} pawns</span>
                  ) : null}
                  <span className="badge">graded by {feedback.graded_by}</span>
                </div>
                {feedback.category_basis ? (
                  <p className="muted" style={{ fontSize: 13, marginBottom: 0 }}>
                    {feedback.category_basis}
                  </p>
                ) : null}
                {feedback.notes?.length ? (
                  <ul className="muted" style={{ fontSize: 13, marginBottom: 0 }}>
                    {feedback.notes.map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}

            {revealed ? (
              <div className="card">
                <strong>Solution</strong>
                <div className="row secondary" style={{ fontSize: 13, marginTop: 6 }}>
                  <span>
                    Best <span className="best mono">{revealed.best_move}</span>
                  </span>
                  <span>
                    You played <span className="played mono">{revealed.played_move}</span>
                  </span>
                  {revealed.book_move ? <span>Book move: {revealed.book_move}</span> : null}
                </div>
                {revealed.category_basis ? (
                  <p className="muted" style={{ fontSize: 13, marginBottom: 0 }}>
                    {revealed.category_basis}
                  </p>
                ) : null}
              </div>
            ) : null}

            {stats?.by_category?.length ? (
              <div className="card">
                <h2>Accuracy by mistake type</h2>
                <div className="list">
                  {stats.by_category.map((row) => (
                    <div className="row" key={row.category} style={{ justifyContent: 'space-between' }}>
                      <span>{categoryLabel(row.category)}</span>
                      <span className="secondary">
                        {row.correct}/{row.attempts} &middot; {row.accuracy}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {loading && !puzzles.length ? <p className="muted">Loading puzzles…</p> : null}
    </div>
  )
}
