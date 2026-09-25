import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import AnalysisChart from '../components/AnalysisChart.jsx'
import ChessBoard, { squareFromUci } from '../components/ChessBoard.jsx'
import MistakeCard from '../components/MistakeCard.jsx'
import { getAnalyzedGame, runAnalysis } from '../services/analysisService.js'

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'

export default function GameAnalysis() {
  const { gameId } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [ply, setPly] = useState(1)
  const [perspective, setPerspective] = useState('white')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const payload = await getAnalyzedGame(gameId)
      setData(payload)
      const first = payload.mistakes?.[0]
      setPly(first ? first.ply : payload.moves?.[0]?.ply || 1)
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [gameId])

  useEffect(() => {
    load()
  }, [load])

  const moves = data?.moves || []
  const mistakes = data?.mistakes || []

  const indexed = useMemo(() => new Map(moves.map((move) => [move.ply, move])), [moves])
  const mistakePlies = useMemo(
    () => new Map(mistakes.map((mistake) => [mistake.ply, mistake])),
    [mistakes],
  )

  const current = indexed.get(ply)
  const fen = current?.fen_before || moves[moves.length - 1]?.fen_after || START_FEN
  const selected = mistakePlies.get(ply)

  const analyze = async () => {
    setBusy(true)
    setError(null)
    try {
      await runAnalysis({ game_ids: [Number(gameId)], use_cache: true })
      await load()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  if (error && !data) {
    return (
      <div className="notice error">
        {error.message} <Link to="/games">Back to games</Link>
      </div>
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
        </div>
        <div className="row">
          <Link className="button" to="/games">
            Back
          </Link>
          <button type="button" className="button" onClick={analyze} disabled={busy}>
            {busy ? 'Analyzing…' : moves.length ? 'Re-analyze' : 'Analyze this game'}
          </button>
        </div>
      </div>

      {error ? (
        <div className="notice error" style={{ marginBottom: 16 }}>
          {error.message}
        </div>
      ) : null}

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
                    onClick={() =>
                      setPly((value) => Math.min(moves[moves.length - 1].ply, value + 1))
                    }
                    disabled={ply >= moves[moves.length - 1].ply}
                  >
                    &rarr;
                  </button>
                  <span>
                    {current
                      ? `Move ${current.move_number}${
                          current.color === 'white' ? '.' : '...'
                        } ${current.san || '—'}`
                      : 'Starting position'}
                  </span>
                  {selected ? <span className="badge">mistake here</span> : null}
                </div>

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
                  onSelect={(item) => setPly(item.ply === ply ? 1 : item.ply)}
                />
              ))}
            </div>
          </div>
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
