import { useCallback } from 'react'
import * as gamesService from '../services/gamesService.ts'
import type { GamesPage } from '../types.ts'
import { useAsync } from './useAsync.ts'
import type { AsyncState } from './useAsync.ts'

export function useGames({
  limit = 100,
  offset = 0,
}: { limit?: number; offset?: number } = {}): AsyncState<GamesPage> {
  const loader = useCallback(
    () => gamesService.listGames({ limit, offset }),
    [limit, offset],
  )
  return useAsync(loader, [limit, offset])
}
