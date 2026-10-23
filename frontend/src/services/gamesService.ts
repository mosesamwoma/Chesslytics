import type { Game, GameFilters, GamesPage, ImportOptions, TagCount } from '../types.ts'
import { del, get, patch, post, postForm } from './api.ts'

export function listGames({
  limit = 100,
  offset = 0,
  filters = {},
}: { limit?: number; offset?: number; filters?: GameFilters } = {}): Promise<GamesPage> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value)
  })
  return get<GamesPage>(`/api/games?${params.toString()}`)
}

export function listTags(): Promise<{ tags: TagCount[] }> {
  return get<{ tags: TagCount[] }>('/api/games/tags')
}

export function updateGame(
  gameId: number,
  changes: { notes?: string | null; tags?: string[] },
): Promise<Game> {
  return patch<Game>(`/api/games/${gameId}`, changes)
}

export function getPgn(gameId: number): Promise<{ pgn: string }> {
  return get<{ pgn: string }>(`/api/games/${gameId}/pgn`)
}

export function importGames(options: ImportOptions): Promise<unknown> {
  return post<unknown>('/api/games/import', options)
}


export function deleteGame(gameId: number): Promise<unknown> {
  return del<unknown>(`/api/games/${gameId}`)
}

export function uploadGames(file: File): Promise<unknown> {
  const form = new FormData()
  form.append('file', file)
  return postForm<unknown>('/api/games/upload', form)
}
