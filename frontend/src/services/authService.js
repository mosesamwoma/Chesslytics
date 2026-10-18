import { request } from './api.js'

export function fetchStatus() {
  return request('/api/auth/status', { method: 'GET', anonymous: true })
}

export function fetchMe() {
  return request('/api/auth/me', { method: 'GET' })
}

export function login(username, password) {
  return request('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
    anonymous: true,
  })
}
