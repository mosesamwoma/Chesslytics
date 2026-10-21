import { del, get, post, request } from './api.js'

export function fetchStatus() {
  return request('/api/auth/status', { method: 'GET', quiet: true })
}

export function fetchMe() {
  return request('/api/auth/me', { method: 'GET', quiet: true })
}

export function login(username, password) {
  return request('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
    quiet: true,
  })
}

export function register(username, password) {
  return request('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
    quiet: true,
  })
}

export function logout() {
  return request('/api/auth/logout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
    quiet: true,
  })
}

export function forgotPassword(identifier) {
  return request('/api/auth/forgot', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ identifier }),
    quiet: true,
  })
}

export function resetPassword(token, newPassword) {
  return request('/api/auth/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, new_password: newPassword }),
    quiet: true,
  })
}

export function verifyEmail(token) {
  return request('/api/auth/verify-email', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
    quiet: true,
  })
}

export function changePassword(currentPassword, newPassword) {
  return post('/api/auth/password', {
    current_password: currentPassword,
    new_password: newPassword,
  })
}

export function deleteAccount(password) {
  return del('/api/auth/me', { password })
}

export { get }
