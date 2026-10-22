import type { GamesPage } from '../types.ts'
import { del, get, postForm } from './api.ts'

export function listGames({
  limit = 100,
  offset = 0,
}: { limit?: number; offset?: number } = {}): Promise<GamesPage> {
  return get<GamesPage>(`/api/games?limit=${limit}&offset=${offset}`)
}

export function deleteGame(gameId: number): Promise<unknown> {
  return del<unknown>(`/api/games/${gameId}`)
}

export function uploadGames(file: File): Promise<unknown> {
  const form = new FormData()
  form.append('file', file)
  return postForm<unknown>('/api/games/upload', form)
}
