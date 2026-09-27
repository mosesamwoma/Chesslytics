import { get } from './api.js'

export function getInsight({ player, refresh } = {}) {
  const params = new URLSearchParams()
  if (player) params.append('player', player)
  if (refresh) params.append('refresh', 'true')
  const query = params.toString()
  return get(`/api/coach${query ? `?${query}` : ''}`)
}
