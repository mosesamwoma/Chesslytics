import { BASE, del, postForm, post, put } from './api.js'

export function setEmail(email, password) {
  return put('/api/account/email', { email, password })
}

export function resendVerification() {
  return post('/api/account/email/resend', {})
}

export function removeEmail(password) {
  return del('/api/account/email', { password })
}

export function backupUrl() {
  return `${BASE}/api/account/backup`
}

export function restoreBackup(file) {
  const form = new FormData()
  form.append('file', file)
  return postForm('/api/account/backup/restore', form)
}
