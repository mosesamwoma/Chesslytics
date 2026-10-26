import { BASE, get, post, put } from './api.ts'
import type {
  Activity,
  AttemptResult,
  LibraryMoveResult,
  LibraryPuzzle,
  LibrarySolution,
  LibraryStatus,
  LineResult,
  Puzzle,
  PuzzlePage,
  Solution,
  ThemeCount,
  TrainingStats,
} from '../types.ts'

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
  theme?: string
  player?: string
  unseenOnly?: boolean
  practice?: string
  limit?: number
  offset?: number
}

export function listPuzzles({
  category,
  severity,
  theme,
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
      theme,
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

export function continueLine(id: number, step: number, uci: string): Promise<LineResult> {
  return post<LineResult>(`/api/training/puzzles/${id}/continue`, { step, uci })
}

export function setGoal(goal: number): Promise<Activity> {
  return put<Activity>('/api/training/goal', { goal })
}

export function exportUrl(
  filters: { category?: string; severity?: string; theme?: string } = {},
): string {
  return `${BASE}/api/training/export${query(filters)}`
}

export function getStats(): Promise<TrainingStats> {
  return get<TrainingStats>('/api/training/stats')
}

export function listAttempts({ limit }: { limit?: number } = {}): Promise<unknown> {
  return get<unknown>(`/api/training/attempts${query({ limit })}`)
}

export function listThemes(): Promise<{ themes: ThemeCount[] }> {
  return get<{ themes: ThemeCount[] }>('/api/training/themes')
}

export function getLibraryStatus(): Promise<LibraryStatus> {
  return get<LibraryStatus>('/api/training/library/status')
}

export function nextLibraryPuzzle(
  filters: { theme?: string; minRating?: number; maxRating?: number; exclude?: number[] } = {},
): Promise<LibraryPuzzle> {
  return get<LibraryPuzzle>(
    `/api/training/library/next${query({
      theme: filters.theme,
      min_rating: filters.minRating,
      max_rating: filters.maxRating,
      exclude: filters.exclude && filters.exclude.length ? filters.exclude.join(',') : undefined,
    })}`,
  )
}

export function libraryMove(id: number, step: number, uci: string): Promise<LibraryMoveResult> {
  return post<LibraryMoveResult>(`/api/training/library/${id}/move`, { step, uci })
}

export function librarySolution(id: number): Promise<LibrarySolution> {
  return get<LibrarySolution>(`/api/training/library/${id}/solution`)
}
