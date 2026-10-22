import type { RestoreResult, UserEnvelope } from '../types.ts'
import { BASE, del, post, postForm, put } from './api.ts'

export function setEmail(email: string, password: string): Promise<UserEnvelope> {
  return put<UserEnvelope>('/api/account/email', { email, password })
}

export function resendVerification(): Promise<unknown> {
  return post<unknown>('/api/account/email/resend', {})
}

export function removeEmail(password: string): Promise<UserEnvelope> {
  return del<UserEnvelope>('/api/account/email', { password })
}

export function backupUrl(): string {
  return `${BASE}/api/account/backup`
}

export function restoreBackup(file: File): Promise<RestoreResult> {
  const form = new FormData()
  form.append('file', file)
  return postForm<RestoreResult>('/api/account/backup/restore', form)
}
