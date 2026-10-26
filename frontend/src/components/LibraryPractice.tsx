import { useCallback, useEffect, useState } from 'react'
import ChessBoard from './ChessBoard.tsx'
import ErrorNotice from './ErrorNotice.tsx'
import { destinations, movesFrom, pieceAt } from '../chessUtils.ts'
import { themeLabel } from '../labels.ts'
import { toProblem } from '../services/api.ts'
import type { Problem } from '../services/api.ts'
import {
  getLibraryStatus,
  libraryMove,
  librarySolution,
  nextLibraryPuzzle,
} from '../services/trainingService.ts'
import type { LibraryPuzzle, LibraryStatus } from '../types.ts'

const PROMOTION_NAMES: Record<string, string> = {
  q: 'queen',
  r: 'rook',
  b: 'bishop',
  n: 'knight',
}

interface Promotion {
  from: string
  to: string
  candidates: string[]
}

export default function LibraryPractice() {
  const [status, setStatus] = useState<LibraryStatus | null>(null)
  const [theme, setTheme] = useState('')
  const [minRating, setMinRating] = useState('')
  const [maxRating, setMaxRating] = useState('')
  const [puzzle, setPuzzle] = useState<LibraryPuzzle | null>(null)
  const [fen, setFen] = useState('')
  const [legal, setLegal] = useState<string[]>([])
  const [step, setStep] = useState(1)
  const [done, setDone] = useState(false)
  const [message, setMessage] = useState('')
  const [lastMove, setLastMove] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [promotion, setPromotion] = useState<Promotion | null>(null)
  const [solution, setSolution] = useState<string[] | null>(null)
  const [wrong, setWrong] = useState(0)
  const [solved, setSolved] = useState(0)
  const [seen, setSeen] = useState<number[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Problem>(null)

  useEffect(() => {
    let active = true
    getLibraryStatus()
      .then((payload) => {
        if (active) setStatus(payload)
      })
      .catch((err: unknown) => {
        if (active) setError(toProblem(err))
      })
    return () => {
      active = false
    }
  }, [])

  const load = useCallback(
    async (chosenTheme: string) => {
      setBusy(true)
      setError(null)
      try {
        const next = await nextLibraryPuzzle({
          theme: chosenTheme || undefined,
          minRating: minRating ? Number(minRating) : undefined,
          maxRating: maxRating ? Number(maxRating) : undefined,
          exclude: seen.slice(-60),
        })
        setPuzzle(next)
        setFen(next.fen)
        setLegal(next.legal_moves)
        setStep(next.step)
        setDone(false)
        setLastMove(next.opponent_uci)
        setSelected(null)
        setPromotion(null)
        setSolution(null)
        setWrong(0)
        setMessage(`The opponent played ${next.opponent_san}. Your move.`)
        setSeen((value) => [...value, next.id])
      } catch (err) {
        setError(toProblem(err))
      } finally {
        setBusy(false)
      }
    },
    [maxRating, minRating, seen],
  )

  const play = useCallback(
    async (uci: string) => {
      if (!puzzle || done) return
      setBusy(true)
      setError(null)
      try {
        const result = await libraryMove(puzzle.id, step, uci)
        setSelected(null)
        setPromotion(null)
        if (!result.correct) {
          setWrong((value) => value + 1)
          setMessage(`${result.played_san} is not the move. Try again.`)
        } else if (result.done) {
          setFen(result.fen || fen)
          setLegal([])
          setDone(true)
          setLastMove(uci)
          setSolved((value) => value + 1)
          setMessage('Solved. Well done.')
        } else {
          setFen(result.fen || fen)
          setLegal(result.legal_moves || [])
          setStep(result.step)
          setLastMove(result.opponent_uci || null)
          setMessage(`Correct. The opponent played ${result.opponent_san}. Keep going.`)
        }
      } catch (err) {
        setError(toProblem(err))
      } finally {
        setBusy(false)
      }
    },
    [done, fen, puzzle, step],
  )

  const onSquare = (square: string) => {
    if (!puzzle || busy || done) return
    const reachable = selected ? destinations(legal, selected) : []
    if (selected && reachable.includes(square)) {
      const candidates = movesFrom(legal, selected).filter((uci) => uci.slice(2, 4) === square)
      if (candidates.length > 1) {
        setPromotion({ from: selected, to: square, candidates })
        return
      }
      if (candidates.length === 1) play(candidates[0])
      return
    }
    const piece = pieceAt(fen, square)
    if (piece && (puzzle.orientation === 'white') === piece.isWhite) {
      setSelected(square === selected ? null : square)
      return
    }
    setSelected(null)
  }

  const showSolution = async () => {
    if (!puzzle) return
    try {
      const result = await librarySolution(puzzle.id)
      setSolution(result.san)
    } catch (err) {
      setError(toProblem(err))
    }
  }

  const choose = (value: string) => {
    setTheme(value)
    load(value)
  }

  if (error && !status) return <ErrorNotice error={error} />
  if (!status) return <p className="muted">Loading&hellip;</p>

  if (!status.count) {
    return (
      <div className="notice">
        <p style={{ marginTop: 0 }}>
          The practice library is empty. It holds puzzles from the free Lichess puzzle database,
          which an administrator loads once. Download <span className="mono">lichess_db_puzzle.csv.zst</span>{' '}
          from database.lichess.org, then run:
        </p>
        <p className="mono" style={{ marginBottom: 0 }}>
          python -m app.manage import-puzzles lichess_db_puzzle.csv.zst --limit 50000
        </p>
      </div>
    )
  }

  const reachable = selected ? destinations(legal, selected) : []

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Practice library</h1>
          <p className="subtitle">
            {status.count.toLocaleString()} puzzles from the Lichess database. Pick a tactic to
            drill, ideally one you keep missing in your own games.
          </p>
        </div>
        <span className="badge">solved this session: {solved}</span>
      </div>

      <ErrorNotice error={error} style={{ marginBottom: 16 }} />

      {status.recommended.length ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <strong>Recommended from your own mistakes</strong>
          <div className="row" style={{ marginTop: 8 }}>
            {status.recommended.map((item) => (
              <button
                key={item.theme}
                type="button"
                className="button"
                onClick={() => choose(item.lichess)}
                disabled={busy}
              >
                {themeLabel(item.theme)} ({item.mistakes} in your games)
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="filters">
        <div className="field">
          <label htmlFor="library-theme">Tactic</label>
          <select
            id="library-theme"
            value={theme}
            onChange={(event) => setTheme(event.target.value)}
          >
            <option value="">any tactic</option>
            {status.themes.map((item) => (
              <option key={item.lichess} value={item.lichess}>
                {themeLabel(item.theme)} ({item.available.toLocaleString()})
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="library-min">Rating from</label>
          <input
            id="library-min"
            type="number"
            min={0}
            max={4000}
            step={50}
            placeholder="any"
            value={minRating}
            onChange={(event) => setMinRating(event.target.value)}
            style={{ width: 110 }}
          />
        </div>
        <div className="field">
          <label htmlFor="library-max">Rating to</label>
          <input
            id="library-max"
            type="number"
            min={0}
            max={4000}
            step={50}
            placeholder="any"
            value={maxRating}
            onChange={(event) => setMaxRating(event.target.value)}
            style={{ width: 110 }}
          />
        </div>
        <button
          type="button"
          className="button primary"
          onClick={() => load(theme)}
          disabled={busy}
        >
          {puzzle ? 'Next puzzle' : 'Start'}
        </button>
      </div>

      {puzzle ? (
        <div className="split">
          <div className="card">
            <div className="board-wrap">
              <ChessBoard
                fen={fen}
                orientation={puzzle.orientation}
                selected={selected}
                targets={reachable}
                lastMove={lastMove}
                onSquareClick={onSquare}
              />
              <p className="muted" style={{ fontSize: 13, margin: 0 }}>
                {message}
              </p>
              {promotion ? (
                <div className="row">
                  <span className="secondary">Promote to</span>
                  {promotion.candidates.map((uci) => (
                    <button
                      key={uci}
                      type="button"
                      className="button primary"
                      onClick={() => play(uci)}
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
          <div className="stack">
            <div className="card">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <strong>
                  You play {puzzle.orientation} &middot; rated {puzzle.rating}
                </strong>
                <span className="badge">
                  move {Math.min(Math.ceil(step / 2), puzzle.total)} of {puzzle.total}
                </span>
              </div>
              {done || solution ? (
                <div className="row" style={{ marginTop: 10 }}>
                  {puzzle.themes
                    .filter((item) => item !== 'short' && item !== 'long' && item !== 'veryLong')
                    .map((item) => (
                      <span className="badge theme" key={item}>
                        {themeLabel(item) === item
                          ? item.replace(/([A-Z])/g, ' $1').toLowerCase()
                          : themeLabel(item)}
                      </span>
                    ))}
                </div>
              ) : (
                <p className="muted" style={{ marginBottom: 0 }}>
                  Themes are hidden until you solve it. Wrong tries: {wrong}.
                </p>
              )}
              <div className="row" style={{ marginTop: 12 }}>
                <button type="button" className="button" onClick={showSolution}>
                  Show solution
                </button>
                <button type="button" className="button" onClick={() => load(theme)} disabled={busy}>
                  Skip
                </button>
              </div>
              {solution ? (
                <p className="secondary" style={{ marginBottom: 0 }}>
                  Solution: <span className="best mono">{solution.join(' ')}</span>
                </p>
              ) : null}
            </div>
          </div>
        </div>
      ) : (
        <p className="muted">Choose a tactic and press Start.</p>
      )}
    </div>
  )
}
