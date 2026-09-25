import { useCallback } from 'react'
import * as patternsService from '../services/patternsService.js'
import { useAsync } from './useAsync.js'

export function useProfile(player) {
  const loader = useCallback(() => patternsService.getLatestProfile(player), [player])
  return useAsync(loader, [player])
}

export function useOverview() {
  const loader = useCallback(() => patternsService.getOverview(), [])
  return useAsync(loader, [])
}
