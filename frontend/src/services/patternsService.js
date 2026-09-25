import { get } from './api.js'

export function getOverview() {
  return get('/api/patterns/overview')
}

export function getLatestProfile(player) {
  const query = player ? `?player=${encodeURIComponent(player)}` : ''
  return get(`/api/patterns/profile${query}`)
}

export function listProfiles(limit = 20) {
  return get(`/api/patterns/profiles?limit=${limit}`)
}

export function listPatterns({ profileId, kind, recurringOnly } = {}) {
  const params = new URLSearchParams()
  if (profileId) params.append('profile_id', profileId)
  if (kind) params.append('kind', kind)
  if (recurringOnly) params.append('recurring_only', true)
  const query = params.toString()
  return get(`/api/patterns${query ? `?${query}` : ''}`)
}
