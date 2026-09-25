import { del, get, post, postForm } from './api.js'

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

export function getCacheInfo() {
  return get('/api/analysis/cache')
}

export function clearCache() {
  return del('/api/analysis/cache')
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
