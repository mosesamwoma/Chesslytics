import { useCallback, useEffect, useRef, useState } from 'react'
import GameCard from '../components/GameCard.jsx'
import UploadForm from '../components/UploadForm.jsx'
import JobProgress from '../components/JobProgress.jsx'
import useJobRunner from '../hooks/useJobRunner.js'
import { deleteGame, listGames } from '../services/gamesService.js'
import { isFinished, listJobs, runAnalysis } from '../services/analysisService.js'

const PAGE_SIZE = 20

export default function Games() {
  const [page, setPage] = useState(0)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const runner = useJobRunner()
  const { follow } = runner

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const payload = await listGames({ limit: PAGE_SIZE, offset: page * PAGE_SIZE })
      const last = Math.max(0, Math.ceil(payload.total / PAGE_SIZE) - 1)
      if (page > last) {
        setPage(last)
        return
      }
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

  const loadRef = useRef(load)

  useEffect(() => {
    loadRef.current = load
  }, [load])

  const track = useCallback(
    async (job) => {
      await follow(job)
      await loadRef.current()
    },
    [follow],
  )

  useEffect(() => {
    let active = true
    listJobs(1)
      .then(({ jobs }) => {
        const latest = jobs[0]
        if (active && latest && !isFinished(latest)) track(latest)
      })
      .catch(() => null)
    return () => {
      active = false
    }
  }, [track])

  const analyzeAll = async () => {
    setBusy(true)
    setError(null)
    try {
      const { job } = await runAnalysis({})
      setBusy(false)
      await track(job)
    } catch (err) {
      setError(err)
      setBusy(false)
    }
  }

  const uploaded = (summary) => {
    load()
    if (summary.job) track(summary.job)
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
        <button
          type="button"
          className="button"
          onClick={analyzeAll}
          disabled={busy || runner.running || !total}
        >
          {busy ? 'Starting…' : 'Analyze stored games'}
        </button>
      </div>

      <UploadForm onUploaded={uploaded} disabled={runner.running} />

      <JobProgress job={runner.job} onCancel={runner.cancel} />

      {runner.job && runner.job.status === 'done' && runner.job.summary ? (
        <div className="notice good" style={{ marginTop: 12 }}>
          Analyzed {runner.job.summary.games_analyzed} games &middot;{' '}
          {runner.job.summary.mistakes} mistakes &middot; {runner.job.summary.moves_scored} moves
          evaluated
          {runner.job.summary.player_not_found
            ? ' · that player name did not match any game'
            : ''}
        </div>
      ) : null}

      {runner.job && runner.job.status === 'failed' ? (
        <div className="notice error" style={{ marginTop: 12 }}>
          {runner.job.error || 'The analysis failed.'}
        </div>
      ) : null}

      {runner.error ? (
        <div className="notice error" style={{ marginTop: 12 }}>
          {runner.error.message}
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
