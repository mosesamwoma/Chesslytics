import { AUTH_EVENT, clearToken, getToken } from './session.js'

const BASE = import.meta.env.VITE_API_BASE || ''

async function parse(response) {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return { detail: text }
  }
}

export async function request(path, options = {}) {
  const { anonymous = false, ...init } = options
  const headers = new Headers(init.headers || {})
  const token = anonymous ? null : getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`${BASE}${path}`, { ...init, headers })
  const body = await parse(response)
  if (!response.ok) {
    if (response.status === 401 && token) {
      clearToken()
      window.dispatchEvent(new Event(AUTH_EVENT))
    }
    const detail = body && body.detail ? body.detail : response.statusText
    const error = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    error.status = response.status
    error.body = body
    throw error
  }
  return body
}

export function get(path) {
  return request(path, { method: 'GET' })
}

export function post(path, payload) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  })
}

export function postForm(path, formData) {
  return request(path, { method: 'POST', body: formData })
}

export function del(path) {
  return request(path, { method: 'DELETE' })
}

export { BASE }
