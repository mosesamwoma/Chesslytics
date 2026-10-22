export const BASE: string = import.meta.env.VITE_API_BASE || ''

export const AUTH_EVENT = 'chesslytics:session-expired'

export class ApiError extends Error {
  status: number
  body: unknown
  retryAfter: number | null

  constructor(message: string, status: number, body: unknown, retryAfter: number | null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
    this.retryAfter = retryAfter
  }
}

export type Problem = Error | string | null

export function toProblem(error: unknown): Problem {
  if (error instanceof Error) return error
  if (typeof error === 'string') return error
  return 'Something went wrong.'
}

export function statusOf(error: unknown): number | null {
  return error instanceof ApiError ? error.status : null
}

export function retryAfterOf(error: unknown): number {
  return error instanceof ApiError && error.retryAfter ? error.retryAfter : 0
}

interface RequestOptions extends RequestInit {
  quiet?: boolean
}

interface ErrorBody {
  detail?: unknown
}

async function parse(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text) as unknown
  } catch {
    return { detail: text }
  }
}

function messageFrom(body: unknown, fallback: string): string {
  const detail = body && (body as ErrorBody).detail ? (body as ErrorBody).detail : fallback
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item: unknown) => {
        const msg = item && typeof item === 'object' ? (item as { msg?: unknown }).msg : null
        return typeof msg === 'string' ? msg : JSON.stringify(item)
      })
      .join('; ')
  }
  return JSON.stringify(detail)
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
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
    throw new ApiError(
      messageFrom(body, response.statusText),
      response.status,
      body,
      Number(response.headers.get('Retry-After')) || null,
    )
  }
  return body as T
}

export function get<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'GET' })
}

function withBody<T>(method: string, path: string, payload?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  })
}

export function post<T>(path: string, payload?: unknown): Promise<T> {
  return withBody<T>('POST', path, payload)
}

export function put<T>(path: string, payload?: unknown): Promise<T> {
  return withBody<T>('PUT', path, payload)
}

export function patch<T>(path: string, payload?: unknown): Promise<T> {
  return withBody<T>('PATCH', path, payload)
}

export function postForm<T>(path: string, formData: FormData): Promise<T> {
  return request<T>(path, { method: 'POST', body: formData })
}

export function del<T>(path: string, payload?: unknown): Promise<T> {
  if (payload === undefined) return request<T>(path, { method: 'DELETE' })
  return request<T>(path, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
