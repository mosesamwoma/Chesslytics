import type {
  AnalysisOptions,
  GameDetail,
  Job,
  JobEnvelope,
  JobsPage,
  Mistake,
  UploadOptions,
  UploadSummary,
} from '../types.ts'
import { BASE, get, post, postForm, statusOf } from './api.ts'

const FINISHED = ['done', 'failed', 'cancelled']
const POLL_MS = 1500

export function runAnalysis(options: AnalysisOptions): Promise<JobEnvelope> {
  return post<JobEnvelope>('/api/analysis/run', options)
}

export function uploadAndAnalyze(
  file: File,
  options: UploadOptions = {},
): Promise<UploadSummary> {
  const form = new FormData()
  form.append('file', file)
  Object.entries(options).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      form.append(key, String(value))
    }
  })
  return postForm<UploadSummary>('/api/analysis/upload', form)
}

export function getJob(jobId: number): Promise<JobEnvelope> {
  return get<JobEnvelope>(`/api/analysis/jobs/${jobId}`)
}

export function cancelJob(jobId: number): Promise<JobEnvelope> {
  return post<JobEnvelope>(`/api/analysis/jobs/${jobId}/cancel`, {})
}

export function listJobs(limit = 10, offset = 0): Promise<JobsPage> {
  return get<JobsPage>(`/api/analysis/jobs?limit=${limit}&offset=${offset}`)
}

export function retryJob(jobId: number): Promise<JobEnvelope> {
  return post<JobEnvelope>(`/api/analysis/jobs/${jobId}/retry`, {})
}

export function isFinished(job: Job | null | undefined): boolean {
  return Boolean(job) && FINISHED.includes((job as Job).status)
}

export async function waitForJob(
  jobId: number,
  { onUpdate, signal }: { onUpdate?: (job: Job) => void; signal?: AbortSignal } = {},
): Promise<Job | null> {
  let failures = 0
  for (;;) {
    if (signal && signal.aborted) return null
    try {
      const { job } = await getJob(jobId)
      failures = 0
      if (onUpdate) onUpdate(job)
      if (isFinished(job)) return job
    } catch (err) {
      failures += 1
      const status = statusOf(err)
      if (status === 404 || status === 401 || failures >= 5) throw err
    }
    await new Promise<void>((resolve) => setTimeout(resolve, POLL_MS))
  }
}

export function exportUrl(format = 'csv'): string {
  return `${BASE}/api/analysis/export?format=${encodeURIComponent(format)}`
}

export function getAnalyzedGame(gameId: string | number): Promise<GameDetail> {
  return get<GameDetail>(`/api/analysis/games/${gameId}`)
}

export function listMistakes(
  filters: Record<string, string | number | undefined | null> = {},
): Promise<{ mistakes: Mistake[] }> {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.append(key, String(value))
    }
  })
  const query = params.toString()
  return get<{ mistakes: Mistake[] }>(`/api/analysis/mistakes${query ? `?${query}` : ''}`)
}
