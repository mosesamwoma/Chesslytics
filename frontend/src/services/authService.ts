import type { AuthInfo, UserEnvelope } from '../types.ts'
import { del, post, request } from './api.ts'

function quietPost<T>(path: string, payload: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    quiet: true,
  })
}

export function fetchStatus(): Promise<AuthInfo> {
  return request<AuthInfo>('/api/auth/status', { method: 'GET', quiet: true })
}

export function fetchMe(): Promise<UserEnvelope> {
  return request<UserEnvelope>('/api/auth/me', { method: 'GET', quiet: true })
}

export function login(username: string, password: string): Promise<UserEnvelope> {
  return quietPost<UserEnvelope>('/api/auth/login', { username, password })
}

export function register(username: string, password: string): Promise<UserEnvelope> {
  return quietPost<UserEnvelope>('/api/auth/register', { username, password })
}

export function logout(): Promise<unknown> {
  return quietPost<unknown>('/api/auth/logout', {})
}

export function forgotPassword(identifier: string): Promise<unknown> {
  return quietPost<unknown>('/api/auth/forgot', { identifier })
}

export function resetPassword(token: string, newPassword: string): Promise<unknown> {
  return quietPost<unknown>('/api/auth/reset', { token, new_password: newPassword })
}

export function verifyEmail(token: string): Promise<unknown> {
  return quietPost<unknown>('/api/auth/verify-email', { token })
}

export function changePassword(currentPassword: string, newPassword: string): Promise<unknown> {
  return post<unknown>('/api/auth/password', {
    current_password: currentPassword,
    new_password: newPassword,
  })
}

export function deleteAccount(password: string): Promise<unknown> {
  return del<unknown>('/api/auth/me', { password })
}
