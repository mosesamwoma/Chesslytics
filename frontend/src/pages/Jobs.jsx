import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import ErrorNotice from '../components/ErrorNotice.jsx'
import { useRetryAfter } from '../hooks/useRetryAfter.js'
import { cancelJob, isFinished, listJobs, retryJob } from '../services/analysisService.js'

const PAGE_SIZE = 15
const REFRESH_MS = 3000

const STATUS_DOT = {
  queued: 'dot-muted',
  running: 'dot-warning',
  done: 'dot-good',
  failed: 'dot-critical',
  cancelled: 'dot-muted',
}

function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString()
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 60) return `${Math.round(seconds)}s`
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds % 60)
  return `${minutes}m ${String(rest).padStart(2, '0')}s`
}

function settingsLabel(options) {
  if (!options) return '—'
  const limit =
    options.limit_kind === 'time'
      ? `${options.limit_value}s per move`
      : options.limit_kind === 'depth'
        ? `depth ${Math.round(options.limit_value)}`
        : null
  const parts = [limit]
  if (options.player) parts.push(`player ${options.player}`)
  if (options.color && options.color !== 'both') parts.push(`${options.color} only`)
  return parts.filter(Boolean).join(' · ') || '—'
}

function outcome(job) {
  if (job.status === 'failed') return job.error || 'The analysis failed.'
  if (job.status === 'cancelled') return 'Cancelled before it finished.'
  if (job.status === 'done' && job.summary) {
    return `${job.summary.mistakes} mistakes in ${job.summary.moves_scored} moves`
  }
  if (job.status === 'running') return job.message || 'Working…'
  return 'Waiting for a free analysis slot.'
}

export default function Jobs() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [page, setPage] = useState(0)
  const [error, setError] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const timer = useRef(null)
  const gate = useRetryAfter(actionError)

  const load = useCallback(async () => {
    try {
      const payload = await listJobs(PAGE_SIZE, page * PAGE_SIZE)
      const last = Math.max(0, Math.ceil(payload.total / PAGE_SIZE) - 1)
      if (page > last) {
        setPage(last)
        return
      }
      setData(payload)
      setError(null)
    } catch (err) {
      setError(err)
    }
  }, [page])

  useEffect(() => {
    load()
  }, [load])

  const active = Boolean(data) && data.jobs.some((job) => !isFinished(job))

  useEffect(() => {
    if (!active) return undefined
    timer.current = setInterval(load, REFRESH_MS)
    return () => clearInterval(timer.current)
  }, [active, load])

  const act = async (job, work) => {
    setBusyId(job.id)
    setActionError(null)
    try {
      await work()
      await load()
    } catch (err) {
      setActionError(err)
    } finally {
      setBusyId(null)
    }
  }

  const lastPage = data ? Math.max(0, Math.ceil(data.total / PAGE_SIZE) - 1) : 0

  if (error && !data) {
    return <ErrorNotice error={error} />
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Analyses</h1>
          <p className="subtitle">
            Every analysis you started, newest first. Finished runs are kept for two weeks.
          </p>
        </div>
        <Link className="button primary" to="/games">
          Start a new analysis
        </Link>
      </div>

      <ErrorNotice error={actionError} />

      <div className="card" style={{ marginTop: 16 }}>
        {!data ? (
          <p className="muted">Loading…</p>
        ) : data.jobs.length === 0 ? (
          <p className="muted">
            Nothing yet. Upload a PGN on the <Link to="/games">Games</Link> page to start one.
          </p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="table">
              <thead>
                <tr>
                  <th className="num">#</th>
                  <th>Status</th>
                  <th className="num">Games</th>
                  <th>Started</th>
                  <th className="num">Took</th>
                  <th>Settings</th>
                  <th>Result</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.jobs.map((job) => {
                  const running = !isFinished(job)
                  return (
                    <tr key={job.id}>
                      <td className="num">{job.id}</td>
                      <td>
                        <span className="badge">
                          <span className={`dot ${STATUS_DOT[job.status] || 'dot-muted'}`} />
                          {job.status}
                        </span>
                      </td>
                      <td className="num">
                        {running ? `${job.done_games} of ${job.total_games}` : job.total_games}
                      </td>
                      <td>{formatDate(job.started_at || job.created_at)}</td>
                      <td className="num">{formatDuration(job.duration_seconds)}</td>
                      <td>{settingsLabel(job.options)}</td>
                      <td className="job-result">{outcome(job)}</td>
                      <td>
                        <div className="row">
                          {running ? (
                            <button
                              type="button"
                              className="button"
                              disabled={busyId === job.id || job.cancel_requested}
                              onClick={() => act(job, () => cancelJob(job.id))}
                            >
                              {job.cancel_requested ? 'Cancelling…' : 'Cancel'}
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="button"
                              disabled={busyId === job.id || gate.blocked}
                              onClick={() =>
                                act(job, async () => {
                                  await retryJob(job.id)
                                  setPage(0)
                                })
                              }
                            >
                              Run again
                            </button>
                          )}
                          {job.status === 'done' ? (
                            <button
                              type="button"
                              className="button"
                              onClick={() => navigate('/patterns')}
                            >
                              See patterns
                            </button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {data && data.total > PAGE_SIZE ? (
          <div className="row" style={{ marginTop: 12 }}>
            <button
              type="button"
              className="button"
              disabled={page === 0}
              onClick={() => setPage((value) => Math.max(0, value - 1))}
            >
              Newer
            </button>
            <span className="muted">
              Page {page + 1} of {lastPage + 1}
            </span>
            <button
              type="button"
              className="button"
              disabled={page >= lastPage}
              onClick={() => setPage((value) => Math.min(lastPage, value + 1))}
            >
              Older
            </button>
          </div>
        ) : null}
      </div>
    </div>
  )
}
