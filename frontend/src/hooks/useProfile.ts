import { useCallback } from 'react'
import * as patternsService from '../services/patternsService.ts'
import type { Overview, ProfileResponse } from '../types.ts'
import { useAsync } from './useAsync.ts'
import type { AsyncState } from './useAsync.ts'

export function useProfile(player?: string): AsyncState<ProfileResponse> {
  const loader = useCallback(() => patternsService.getLatestProfile(player), [player])
  return useAsync(loader, [player])
}

export function useOverview(): AsyncState<Overview> {
  const loader = useCallback(() => patternsService.getOverview(), [])
  return useAsync(loader, [])
}
