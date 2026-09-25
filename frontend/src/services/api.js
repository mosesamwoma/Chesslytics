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

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, options)
  const body = await parse(response)
  if (!response.ok) {
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
