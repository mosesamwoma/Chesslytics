import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import AnalysisChart from '../components/AnalysisChart.tsx'
import ChessBoard, { sourceFromUci, squareFromUci } from '../components/ChessBoard.tsx'
import type { BoardArrow } from '../components/ChessBoard.tsx'
import GameNotes from '../components/GameNotes.tsx'
import ErrorNotice from '../components/ErrorNotice.tsx'
import JobProgress from '../components/JobProgress.tsx'
import MistakeCard from '../components/MistakeCard.tsx'
import { useCopy } from '../hooks/useCopy.ts'
import useJobRunner from '../hooks/useJobRunner.ts'
import { getAnalyzedGame, runAnalysis } from '../services/analysisService.ts'
import { toProblem } from '../services/api.ts'
import { getPgn } from '../services/gamesService.ts'
import type { Problem } from '../services/api.ts'
import type { Game, GameDetail, Mistake, Move, Side } from '../types.ts'

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'

export default function GameAnalysis() {
  const { gameId } = useParams()
  const [data, setData] = useState<GameDetail | null>(null)
  const [error, setError] = useState<Problem>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [ply, setPly] = useState(1)
  const [perspective, setPerspective] = useState<Side>('white')
  const [showArrows, setShowArrows] = useState(true)
  const [copyError, setCopyError] = useState<Problem>(null)
  const fenCopy = useCopy()
  const pgnCopy = useCopy()
  const runner = useJobRunner()

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const payload = await getAnalyzedGame(gameId || '')
      setData(payload)
      const first = payload.mistakes?.[0]
      setPly(first ? first.ply : payload.moves?.[0]?.ply || 1)
    } catch (err) {
      setError(toProblem(err))
    } finally {
      setLoading(false)
    }
  }, [gameId])

  useEffect(() => {
    load()
  }, [load])

  const moves: Move[] = useMemo(() => data?.moves || [], [data])
  const mistakes: Mistake[] = useMemo(() => data?.mistakes || [], [data])

  const indexed = useMemo(() => new Map(moves.map((move) => [move.ply, move])), [moves])
  const mistakePlies = useMemo(
    () => new Map(mistakes.map((mistake) => [mistake.ply, mistake])),
    [mistakes],
  )

  const lastPly = moves.length ? moves[moves.length - 1].ply : 1
  const atEnd = moves.length > 0 && ply > lastPly
  const current = atEnd ? undefined : indexed.get(ply)
  const fen = atEnd
    ? moves[moves.length - 1].fen_after || START_FEN
    : current?.fen_before || START_FEN
  const selected = atEnd ? undefined : mistakePlies.get(ply)

  const arrows: BoardArrow[] = useMemo(() => {
    if (!showArrows || atEnd || !current) return []
    const best = current.best_move_uci
    const played = current.uci
    const list: BoardArrow[] = []
    if (best && sourceFromUci(best) && squareFromUci(best)) {
      list.push({ from: sourceFromUci(best) || '', to: squareFromUci(best) || '', kind: 'best' })
    }
    if (played && played !== best && sourceFromUci(played) && squareFromUci(played)) {
      list.push({
        from: sourceFromUci(played) || '',
        to: squareFromUci(played) || '',
        kind: 'played',
      })
    }
    return list
  }, [showArrows, atEnd, current])

  const copyPgn = async () => {
    setCopyError(null)
    try {
      const payload = await getPgn(Number(gameId))
      await pgnCopy.copy(payload.pgn)
    } catch (err) {
      setCopyError(toProblem(err))
    }
  }

  const saved = (game: Game) => {
    setData((value) =>
      value ? { ...value, notes: game.notes, tags: game.tags } : value,
    )
  }

  const analyze = async () => {
    setBusy(true)
    setError(null)
    try {
      const { job } = await runAnalysis({
        game_ids: [Number(gameId)],
        update_profile: false,
      })
      setBusy(false)
      const finished = await runner.follow(job)
      if (finished && finished.status === 'done') await load()
    } catch (err) {
      setError(toProblem(err))
      setBusy(false)
    }
  }

  if (error && !data) {
    return (
      <ErrorNotice error={error}>
        <Link to="/games">Back to games</Link>
      </ErrorNotice>
    )
  }

  if (!data) {
    return <p className="muted">{loading ? 'Loading…' : 'Game not found.'}</p>
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>
            {data.white} <span className="muted">vs</span> {data.black}
          </h1>
          <p className="subtitle">
            {data.result || 'result unknown'}
            {data.date ? ` · ${data.date}` : ''}
            {data.opening ? ` · ${data.eco ? `${data.eco} ` : ''}${data.opening}` : ''}
            {data.analyzed_depth ? ` · depth ${data.analyzed_depth}` : ''}
          </p>
          {data.accuracy.white !== null || data.accuracy.black !== null ? (
            <p className="secondary" style={{ margin: 0 }}>
              Accuracy
              {data.accuracy.white !== null ? ` · White ${data.accuracy.white.toFixed(1)}%` : ''}
              {data.accuracy.black !== null ? ` · Black ${data.accuracy.black.toFixed(1)}%` : ''}
            </p>
          ) : null}
        </div>
        <div className="row">
          <Link className="button" to="/games">
            Back
          </Link>
          <button
            type="button"
            className="button"
            onClick={analyze}
            disabled={busy || runner.running}
          >
            {busy || runner.running
              ? 'Analyzing…'
              : moves.length
                ? 'Re-analyze'
                : 'Analyze this game'}
          </button>
        </div>
      </div>

      <JobProgress job={runner.job} onCancel={runner.cancel} />

      {runner.job && runner.job.status === 'failed' ? (
        <div className="notice error" style={{ marginBottom: 16 }}>
          {runner.job.error || 'The analysis failed.'}
        </div>
      ) : null}

      <ErrorNotice error={error || runner.error} style={{ marginBottom: 16 }} />

      {moves.length ? (
        <>
          <div className="row" style={{ marginBottom: 12 }}>
            <span className="secondary">Win probability for</span>
            <button
              type="button"
              className={perspective === 'white' ? 'button primary' : 'button'}
              onClick={() => setPerspective('white')}
            >
              White
            </button>
            <button
              type="button"
              className={perspective === 'black' ? 'button primary' : 'button'}
              onClick={() => setPerspective('black')}
            >
              Black
            </button>
          </div>

          <AnalysisChart sequence={moves} mistakes={mistakes} perspective={perspective} />

          <div className="split" style={{ marginTop: 16 }}>
            <div className="card">
              <div className="board-wrap">
                <ChessBoard
                  fen={fen}
                  highlight={[squareFromUci(current?.uci)]}
                  arrows={arrows}
                />
                <div className="board-controls">
                  <button
                    type="button"
                    className="button"
                    onClick={() => setPly((value) => Math.max(1, value - 1))}
                    disabled={ply <= 1}
                  >
                    &larr;
                  </button>
                  <button
                    type="button"
                    className="button"
                    onClick={() => setPly((value) => Math.min(lastPly + 1, value + 1))}
                    disabled={ply >= lastPly + 1}
                  >
                    &rarr;
                  </button>
                  <span>
                    {atEnd
                      ? 'Final position'
                      : current
                        ? `Move ${current.move_number}${
                            current.color === 'white' ? '.' : '...'
                          } ${current.san || '—'}`
                        : 'Starting position'}
                  </span>
                  {selected ? <span className="badge">mistake here</span> : null}
                </div>

                <div className="row">
                  <label className="row">
                    <input
                      type="checkbox"
                      checked={showArrows}
                      onChange={(event) => setShowArrows(event.target.checked)}
                    />
                    <span>Show best move (green) and played move (red)</span>
                  </label>
                </div>
                <div className="row">
                  <button type="button" className="button" onClick={() => fenCopy.copy(fen)}>
                    {fenCopy.copied ? 'FEN copied' : fenCopy.failed ? 'Copy failed' : 'Copy FEN'}
                  </button>
                  <button type="button" className="button" onClick={copyPgn}>
                    {pgnCopy.copied ? 'PGN copied' : pgnCopy.failed ? 'Copy failed' : 'Copy PGN'}
                  </button>
                </div>
                <ErrorNotice error={copyError} />

                <div
                  className="list"
                  style={{ maxHeight: 220, overflowY: 'auto', fontSize: 13 }}
                >
                  {moves.map((move) => (
                    <button
                      key={move.ply}
                      type="button"
                      className={move.ply === ply ? 'button primary' : 'button'}
                      style={{ justifyContent: 'flex-start', textAlign: 'left' }}
                      onClick={() => setPly(move.ply)}
                    >
                      {move.move_number}
                      {move.color === 'white' ? '.' : '...'} {move.san || '—'}
                      {mistakePlies.has(move.ply) ? ' ●' : ''}
                    </button>
                  ))}
                  <button
                    type="button"
                    className={atEnd ? 'button primary' : 'button'}
                    style={{ justifyContent: 'flex-start', textAlign: 'left' }}
                    onClick={() => setPly(lastPly + 1)}
                  >
                    Final position
                  </button>
                </div>
              </div>
            </div>

            <div className="list">
              <div className="card">
                <h2>Mistakes in this game</h2>
                <p className="subtitle">
                  {mistakes.length
                    ? `${mistakes.length} recorded above the current thresholds.`
                    : 'None recorded above the current thresholds.'}
                </p>
              </div>
              {mistakes.map((mistake) => (
                <MistakeCard
                  key={mistake.id || mistake.ply}
                  mistake={mistake}
                  selected={mistake.ply === ply}
                  onSelect={(item: Mistake) => setPly(item.ply === ply ? 1 : item.ply)}
                />
              ))}
            </div>
          </div>

          <GameNotes
            key={data.id}
            gameId={data.id}
            notes={data.notes}
            tags={data.tags}
            onSaved={saved}
          />
        </>
      ) : (
        <div className="notice">
          This game is stored but has no evaluated moves yet. Run the analysis to fill in the chart,
          the board and the mistake list.
        </div>
      )}
    </div>
  )
}
