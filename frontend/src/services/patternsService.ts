import type {
  OpeningsReport,
  Overview,
  PatternsResponse,
  ProfileResponse,
  Progress,
} from '../types.ts'
import { get } from './api.ts'

export function getOverview(): Promise<Overview> {
  return get<Overview>('/api/patterns/overview')
}

export function getLatestProfile(player?: string): Promise<ProfileResponse> {
  const query = player ? `?player=${encodeURIComponent(player)}` : ''
  return get<ProfileResponse>(`/api/patterns/profile${query}`)
}

export function getProgress(weeks = 26): Promise<Progress> {
  return get<Progress>(`/api/patterns/progress?weeks=${weeks}`)
}

export function getOpenings(minGames = 1): Promise<OpeningsReport> {
  return get<OpeningsReport>(`/api/patterns/openings?min_games=${minGames}`)
}

export function listProfiles(limit = 20): Promise<unknown> {
  return get<unknown>(`/api/patterns/profiles?limit=${limit}`)
}

export function listPatterns({
  profileId,
  kind,
  recurringOnly,
}: { profileId?: number; kind?: string; recurringOnly?: boolean } = {}): Promise<PatternsResponse> {
  const params = new URLSearchParams()
  if (profileId) params.append('profile_id', String(profileId))
  if (kind) params.append('kind', kind)
  if (recurringOnly) params.append('recurring_only', 'true')
  const query = params.toString()
  return get<PatternsResponse>(`/api/patterns${query ? `?${query}` : ''}`)
}
