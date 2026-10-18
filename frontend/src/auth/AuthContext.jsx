import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { fetchMe, fetchStatus, login as loginRequest } from '../services/authService.js'
import { AUTH_EVENT, clearToken, getToken, setToken } from '../services/session.js'

export const AuthContext = createContext(null)

async function resolveStatus() {
  const info = await fetchStatus()
  if (!info.enabled) return 'open'
  if (!getToken()) return 'anonymous'
  try {
    await fetchMe()
    return 'authenticated'
  } catch (err) {
    if (err.status === 401) {
      clearToken()
      return 'anonymous'
    }
    throw err
  }
}

export function AuthProvider({ children }) {
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    setStatus('loading')
    setError(null)
    resolveStatus()
      .then((next) => {
        if (active) setStatus(next)
      })
      .catch((err) => {
        if (active) {
          setError(err)
          setStatus('error')
        }
      })
    return () => {
      active = false
    }
  }, [attempt])

  useEffect(() => {
    const expired = () => setStatus((current) => (current === 'open' ? current : 'anonymous'))
    window.addEventListener(AUTH_EVENT, expired)
    return () => window.removeEventListener(AUTH_EVENT, expired)
  }, [])

  const login = useCallback(async (username, password) => {
    const result = await loginRequest(username, password)
    setToken(result.token)
    setStatus('authenticated')
  }, [])

  const logout = useCallback(() => {
    clearToken()
    setStatus('anonymous')
  }, [])

  const retry = useCallback(() => setAttempt((value) => value + 1), [])

  const value = useMemo(
    () => ({ status, error, login, logout, retry }),
    [status, error, login, logout, retry],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
