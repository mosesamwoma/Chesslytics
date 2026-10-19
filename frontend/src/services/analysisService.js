import { BASE, get, post, postForm } from './api.js'

const FINISHED = ['done', 'failed', 'cancelled']
const POLL_MS = 1500

export function runAnalysis(options) {
  return post('/api/analysis/run', options)
}

export function uploadAndAnalyze(file, options = {}) {
  const form = new FormData()
  form.append('file', file)
  Object.entries(options).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      form.append(key, value)
    }
  })
  return postForm('/api/analysis/upload', form)
}

export function getJob(jobId) {
  return get(`/api/analysis/jobs/${jobId}`)
}

export function cancelJob(jobId) {
  return post(`/api/analysis/jobs/${jobId}/cancel`, {})
}

export function listJobs(limit = 10) {
  return get(`/api/analysis/jobs?limit=${limit}`)
}

export function isFinished(job) {
  return Boolean(job) && FINISHED.includes(job.status)
}

export async function waitForJob(jobId, { onUpdate, signal } = {}) {
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
      if (err.status === 404 || err.status === 401 || failures >= 5) throw err
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_MS))
  }
}

export function exportUrl(format = 'csv') {
  return `${BASE}/api/analysis/export?format=${encodeURIComponent(format)}`
}

export function getAnalyzedGame(gameId) {
  return get(`/api/analysis/games/${gameId}`)
}

export function listMistakes(filters = {}) {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.append(key, value)
    }
  })
  const query = params.toString()
  return get(`/api/analysis/mistakes${query ? `?${query}` : ''}`)
}
