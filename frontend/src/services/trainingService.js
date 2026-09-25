import { get, post } from './api.js'

function query(params) {
  const search = new URLSearchParams()
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '' || value === false) return
    search.append(key, value)
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}

export function listPuzzles({ category, severity, player, unseenOnly, limit, offset } = {}) {
  return get(
    `/api/training/puzzles${query({
      category,
      severity,
      player,
      unseen_only: unseenOnly,
      limit,
      offset,
    })}`,
  )
}

export function getPuzzle(id) {
  return get(`/api/training/puzzles/${id}`)
}

export function getSolution(id) {
  return get(`/api/training/puzzles/${id}/solution`)
}

export function submitAttempt(id, { uci, player, depth, timeLimit, stockfishPath } = {}) {
  return post(`/api/training/puzzles/${id}/attempt`, {
    uci,
    player,
    depth,
    time_limit: timeLimit,
    stockfish_path: stockfishPath,
  })
}

export function getStats(player) {
  return get(`/api/training/stats${query({ player })}`)
}

export function listAttempts({ player, limit } = {}) {
  return get(`/api/training/attempts${query({ player, limit })}`)
}
