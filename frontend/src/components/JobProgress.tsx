import type { Job } from '../types.ts'

interface JobProgressProps {
  job: Job | null
  onCancel?: () => void
}

export default function JobProgress({ job, onCancel }: JobProgressProps) {
  if (!job) return null
  const total = job.total_games || 0
  const done = Math.min(job.done_games || 0, total)
  const percent = total ? Math.round((done / total) * 100) : 0
  const active = job.status === 'queued' || job.status === 'running'

  if (!active) {
    return job.status === 'cancelled' ? (
      <div className="notice" style={{ marginTop: 12 }}>
        Analysis cancelled.
      </div>
    ) : null
  }

  return (
    <div className="notice" style={{ marginTop: 12 }}>
      <div className="row">
        <span className="spinner" aria-hidden="true" />
        <span>
          {job.status === 'queued'
            ? 'Waiting for a free analysis slot…'
            : `Analyzing game ${Math.min(done + 1, total)} of ${total}…`}
        </span>
        {onCancel ? (
          <button type="button" className="button" onClick={onCancel}>
            Cancel
          </button>
        ) : null}
      </div>
      <progress value={percent} max="100" style={{ width: '100%', marginTop: 8 }} />
    </div>
  )
}
