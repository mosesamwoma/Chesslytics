import { useCallback } from 'react'
import * as gamesService from '../services/gamesService.js'
import { useAsync } from './useAsync.js'

export function useGames({ limit = 100, offset = 0 } = {}) {
  const loader = useCallback(
    () => gamesService.listGames({ limit, offset }),
    [limit, offset],
  )
  return useAsync(loader, [limit, offset])
}
