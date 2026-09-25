import { del, get, postForm } from './api.js'

export function listGames({ limit = 100, offset = 0 } = {}) {
  return get(`/api/games?limit=${limit}&offset=${offset}`)
}

export function deleteGame(gameId) {
  return del(`/api/games/${gameId}`)
}

export function uploadGames(file) {
  const form = new FormData()
  form.append('file', file)
  return postForm('/api/games/upload', form)
}
