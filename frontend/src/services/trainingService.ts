import type { AttemptResult, Puzzle, PuzzlePage, Solution, TrainingStats } from '../types.ts'
import { get, post } from './api.ts'

type QueryValue = string | number | boolean | undefined | null

function query(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '' || value === false) return
    search.append(key, String(value))
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}

export interface PuzzleFilters {
  category?: string
  severity?: string
  player?: string
  unseenOnly?: boolean
  practice?: string
  limit?: number
  offset?: number
}

export function listPuzzles({
  category,
  severity,
  player,
  unseenOnly,
  practice,
  limit,
  offset,
}: PuzzleFilters = {}): Promise<PuzzlePage> {
  return get<PuzzlePage>(
    `/api/training/puzzles${query({
      category,
      severity,
      player,
      unseen_only: unseenOnly,
      practice,
      limit,
      offset,
    })}`,
  )
}

export function getPuzzle(id: number): Promise<Puzzle> {
  return get<Puzzle>(`/api/training/puzzles/${id}`)
}

export function getSolution(id: number): Promise<Solution> {
  return get<Solution>(`/api/training/puzzles/${id}/solution`)
}

export function submitAttempt(
  id: number,
  {
    uci,
    depth,
    timeLimit,
  }: { uci?: string; depth?: number; timeLimit?: number } = {},
): Promise<AttemptResult> {
  return post<AttemptResult>(`/api/training/puzzles/${id}/attempt`, {
    uci,
    depth,
    time_limit: timeLimit,
  })
}

export function getStats(): Promise<TrainingStats> {
  return get<TrainingStats>('/api/training/stats')
}

export function listAttempts({ limit }: { limit?: number } = {}): Promise<unknown> {
  return get<unknown>(`/api/training/attempts${query({ limit })}`)
}
