const BASE = import.meta.env.VITE_API_BASE || ''

export const AUTH_EVENT = 'chesslytics:session-expired'

async function parse(response) {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return { detail: text }
  }
}

function messageFrom(body, fallback) {
  const detail = body && body.detail ? body.detail : fallback
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || JSON.stringify(item)).join('; ')
  }
  return JSON.stringify(detail)
}

export async function request(path, options = {}) {
  const { quiet = false, ...init } = options
  const headers = new Headers(init.headers || {})
  headers.set('X-CSRF-Protection', '1')
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers,
    credentials: BASE ? 'include' : 'same-origin',
  })
  const body = await parse(response)
  if (!response.ok) {
    if (response.status === 401 && !quiet) {
      window.dispatchEvent(new Event(AUTH_EVENT))
    }
    const error = new Error(messageFrom(body, response.statusText))
    error.status = response.status
    error.body = body
    error.retryAfter = Number(response.headers.get('Retry-After')) || null
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

export function patch(path, payload) {
  return request(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  })
}

export function postForm(path, formData) {
  return request(path, { method: 'POST', body: formData })
}

export function del(path, payload) {
  if (payload === undefined) return request(path, { method: 'DELETE' })
  return request(path, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export { BASE }
