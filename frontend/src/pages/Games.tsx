import { useCallback, useEffect, useRef, useState } from 'react'
import ConfirmDialog from '../components/ConfirmDialog.tsx'
import ErrorNotice from '../components/ErrorNotice.tsx'
import GameCard from '../components/GameCard.tsx'
import GameFilters from '../components/GameFilters.tsx'
import ImportForm from '../components/ImportForm.tsx'
import UploadForm from '../components/UploadForm.tsx'
import JobProgress from '../components/JobProgress.tsx'
import useJobRunner from '../hooks/useJobRunner.ts'
import { useRetryAfter } from '../hooks/useRetryAfter.ts'
import { toProblem } from '../services/api.ts'
import type { Problem } from '../services/api.ts'
import { deleteGame, listGames } from '../services/gamesService.ts'
import { analyzeSample, isFinished, listJobs, runAnalysis } from '../services/analysisService.ts'
import type { Game, GameFilters as Filters, GamesPage, Job, UploadSummary } from '../types.ts'

const PAGE_SIZE = 20

export default function Games() {
  const [page, setPage] = useState(0)
  const [filters, setFilters] = useState<Filters>({})
  const [data, setData] = useState<GamesPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Problem>(null)
  const [busy, setBusy] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<Game | null>(null)
  const [deleting, setDeleting] = useState(false)
  const runner = useJobRunner()
  const gate = useRetryAfter(error)
  const { follow } = runner

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const payload = await listGames({
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
        filters,
      })
      const last = Math.max(0, Math.ceil(payload.total / PAGE_SIZE) - 1)
      if (page > last) {
        setPage(last)
        return
      }
      setData(payload)
    } catch (err) {
      setError(toProblem(err))
    } finally {
      setLoading(false)
    }
  }, [page, filters])

  useEffect(() => {
    load()
  }, [load])

  const loadRef = useRef(load)

  useEffect(() => {
    loadRef.current = load
  }, [load])

  const track = useCallback(
    async (job: Job) => {
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
      setError(toProblem(err))
      setBusy(false)
    }
  }

  const uploaded = (summary: UploadSummary | null) => {
    load()
    if (summary && summary.job) track(summary.job)
  }

  const changeFilters = useCallback((next: Filters) => {
    setPage(0)
    setFilters(next)
  }, [])

  const trySample = async () => {
    setBusy(true)
    setError(null)
    try {
      const summary = await analyzeSample()
      setBusy(false)
      uploaded(summary)
    } catch (err) {
      setError(toProblem(err))
      setBusy(false)
    }
  }

  const confirmRemove = async () => {
    if (!pendingDelete) return
    setDeleting(true)
    try {
      await deleteGame(pendingDelete.id)
      setPendingDelete(null)
      await load()
    } catch (err) {
      setPendingDelete(null)
      setError(toProblem(err))
    } finally {
      setDeleting(false)
    }
  }

  const total = data?.total ?? 0
  const filtering = Object.values(filters).some(Boolean)
  const empty = !loading && total === 0 && !filtering
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
          disabled={busy || runner.running || !total || gate.blocked}
        >
          {busy ? 'Starting…' : 'Analyze stored games'}
        </button>
      </div>

      <UploadForm onUploaded={uploaded} disabled={runner.running} />

      <ImportForm onImported={uploaded} disabled={runner.running} />

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

      <ErrorNotice error={runner.error} style={{ marginTop: 12 }} />
      <ErrorNotice error={error} style={{ marginTop: 16 }} />

      {!empty ? (
        <GameFilters filters={filters} player={data?.player ?? null} onChange={changeFilters} />
      ) : null}

      <div className={loading && data ? 'loading-dim' : undefined} style={{ marginTop: 16 }}>
        {data && data.games.length ? (
          <div className="list">
            {data.games.map((game) => (
              <GameCard
                key={game.id}
                game={game}
                player={data.player}
                onDelete={setPendingDelete}
              />
            ))}
          </div>
        ) : empty ? (
          <div className="notice">
            <p style={{ marginTop: 0 }}>
              No games stored yet. Upload a PGN file, import by username, or see how it works
              with three short sample games.
            </p>
            <button
              type="button"
              className="button primary"
              onClick={trySample}
              disabled={busy || runner.running}
            >
              {busy ? 'Starting…' : 'Try a sample game'}
            </button>
          </div>
        ) : (
          !loading && <p className="muted">No games match these filters.</p>
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

      {pendingDelete ? (
        <ConfirmDialog
          title="Delete this game?"
          confirmLabel="Delete game"
          danger
          busy={deleting}
          onConfirm={confirmRemove}
          onCancel={() => setPendingDelete(null)}
        >
          <p>
            <strong>
              {pendingDelete.white} vs {pendingDelete.black}
            </strong>{' '}
            and the analysis stored for it will be removed. Your other games are not affected.
          </p>
        </ConfirmDialog>
      ) : null}
    </div>
  )
}
