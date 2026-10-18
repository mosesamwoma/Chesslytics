const TOKEN_KEY = 'chesslytics-token'

export const AUTH_EVENT = 'chesslytics-auth-expired'

let memoryToken = null

export function getToken() {
  try {
    return window.localStorage.getItem(TOKEN_KEY) || memoryToken
  } catch {
    return memoryToken
  }
}

export function setToken(token) {
  memoryToken = token
  try {
    window.localStorage.setItem(TOKEN_KEY, token)
  } catch {}
}

export function clearToken() {
  memoryToken = null
  try {
    window.localStorage.removeItem(TOKEN_KEY)
  } catch {}
}
