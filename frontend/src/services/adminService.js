import { del, get, patch, post } from './api.js'

export function getStats() {
  return get('/api/admin/stats')
}

export function listUsers({ q, limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (q) params.set('q', q)
  return get(`/api/admin/users?${params.toString()}`)
}

export function updateUser(id, changes) {
  return patch(`/api/admin/users/${id}`, changes)
}

export function resetUserPassword(id, newPassword) {
  return post(`/api/admin/users/${id}/password`, { new_password: newPassword })
}

export function createResetLink(id) {
  return post(`/api/admin/users/${id}/reset-link`, {})
}

export function unlockUser(id) {
  return post(`/api/admin/users/${id}/unlock`, {})
}

export function deleteUser(id) {
  return del(`/api/admin/users/${id}`)
}

export function getAudit(limit = 100) {
  return get(`/api/admin/audit?limit=${limit}`)
}
