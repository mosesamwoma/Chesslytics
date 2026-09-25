import { useCallback, useEffect, useState } from 'react'
import GameCard from '../components/GameCard.jsx'
import UploadForm from '../components/UploadForm.jsx'
import { deleteGame, listGames } from '../services/gamesService.js'
import { runAnalysis } from '../services/analysisService.js'

const PAGE_SIZE = 20

export default function Games() {
  const [page, setPage] = useState(0)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const payload = await listGames({ limit: PAGE_SIZE, offset: page * PAGE_SIZE })
      setData(payload)
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => {
    load()
  }, [load])

  const analyzeAll = async () => {
    setBusy(true)
    setMessage(null)
    setError(null)
    try {
      const report = await runAnalysis({ use_cache: true })
      setMessage(
        `Analyzed ${report.counts?.games_analyzed ?? 0} new games, reused ${
          report.counts?.games_reused ?? 0
        } from cache, found ${report.mistakes?.length ?? 0} mistakes.`,
      )
      await load()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (game) => {
    if (!window.confirm(`Delete ${game.white} vs ${game.black}?`)) return
    try {
      await deleteGame(game.id)
      await load()
    } catch (err) {
      setError(err)
    }
  }

  const total = data?.total ?? 0
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1)

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Games</h1>
          <p className="subtitle">
            {total} {total === 1 ? 'game' : 'games'} stored. Uploads are deduplicated by a
            fingerprint of the headers and moves.
          </p>
        </div>
        <button type="button" className="button" onClick={analyzeAll} disabled={busy || !total}>
          {busy ? 'Analyzing…' : 'Analyze stored games'}
        </button>
      </div>

      <UploadForm onComplete={load} />

      {message ? (
        <div className="notice good" style={{ marginTop: 16 }}>
          {message}
        </div>
      ) : null}

      {error ? (
        <div className="notice error" style={{ marginTop: 16 }}>
          {error.message}
        </div>
      ) : null}

      <div className={loading && data ? 'loading-dim' : undefined} style={{ marginTop: 16 }}>
        {data && data.games.length ? (
          <div className="list">
            {data.games.map((game) => (
              <GameCard key={game.id} game={game} onDelete={remove} />
            ))}
          </div>
        ) : (
          !loading && <p className="muted">No games stored yet.</p>
        )}
      </div>

      {total > PAGE_SIZE ? (
        <div className="row" style={{ marginTop: 16 }}>
          <button
            type="button"
            className="button"
            onClick={() => setPage((value) => Math.max(0, value - 1))}
            disabled={page === 0}
          >
            Previous
          </button>
          <span className="muted">
            Page {page + 1} of {lastPage + 1}
          </span>
          <button
            type="button"
            className="button"
            onClick={() => setPage((value) => Math.min(lastPage, value + 1))}
            disabled={page >= lastPage}
          >
            Next
          </button>
        </div>
      ) : null}
    </div>
  )
}
