import type { CoachInsight } from '../types.ts'
import { get } from './api.ts'

export function getInsight({
  player,
  refresh,
}: { player?: string; refresh?: boolean } = {}): Promise<CoachInsight> {
  const params = new URLSearchParams()
  if (player) params.append('player', player)
  if (refresh) params.append('refresh', 'true')
  const query = params.toString()
  return get<CoachInsight>(`/api/coach${query ? `?${query}` : ''}`)
}
