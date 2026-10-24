import type {
  AdminStats,
  AdminUser,
  AdminUsersPage,
  AuditEvent,
  EmailStatus,
  ResetLink,
} from '../types.ts'
import { del, get, patch, post } from './api.ts'

export function getStats(): Promise<AdminStats> {
  return get<AdminStats>('/api/admin/stats')
}

export function getEmailStatus(): Promise<EmailStatus> {
  return get<EmailStatus>('/api/admin/email')
}

export function sendTestEmail(): Promise<{ sent_to: string }> {
  return post<{ sent_to: string }>('/api/admin/email/test', {})
}

export function listUsers({
  q,
  limit = 50,
  offset = 0,
}: { q?: string; limit?: number; offset?: number } = {}): Promise<AdminUsersPage> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (q) params.set('q', q)
  return get<AdminUsersPage>(`/api/admin/users?${params.toString()}`)
}

export function updateUser(
  id: number,
  changes: { is_active?: boolean; role?: string },
): Promise<unknown> {
  return patch<AdminUser>(`/api/admin/users/${id}`, changes)
}

export function resetUserPassword(id: number, newPassword: string): Promise<unknown> {
  return post<unknown>(`/api/admin/users/${id}/password`, { new_password: newPassword })
}

export function createResetLink(id: number): Promise<ResetLink> {
  return post<ResetLink>(`/api/admin/users/${id}/reset-link`, {})
}

export function unlockUser(id: number): Promise<unknown> {
  return post<unknown>(`/api/admin/users/${id}/unlock`, {})
}

export function deleteUser(id: number): Promise<unknown> {
  return del<unknown>(`/api/admin/users/${id}`)
}

export function getAudit(limit = 100): Promise<{ events: AuditEvent[] }> {
  return get<{ events: AuditEvent[] }>(`/api/admin/audit?limit=${limit}`)
}
