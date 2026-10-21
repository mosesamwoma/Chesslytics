import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { AUTH_EVENT } from '../services/api.js'
import {
  fetchMe,
  fetchStatus,
  login as loginRequest,
  logout as logoutRequest,
  register as registerRequest,
} from '../services/authService.js'

export const AuthContext = createContext(null)

async function resolveSession() {
  const info = await fetchStatus()
  try {
    const me = await fetchMe()
    return { status: 'authenticated', user: me.user, info }
  } catch (err) {
    if (err.status === 401) return { status: 'anonymous', user: null, info }
    throw err
  }
}

export function AuthProvider({ children }) {
  const [status, setStatus] = useState('loading')
  const [user, setUser] = useState(null)
  const [info, setInfo] = useState({
    registration_enabled: false,
    min_password_length: 10,
    email_enabled: false,
  })
  const [error, setError] = useState(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    setStatus('loading')
    setError(null)
    resolveSession()
      .then((next) => {
        if (!active) return
        setUser(next.user)
        setInfo(next.info)
        setStatus(next.status)
      })
      .catch((err) => {
        if (!active) return
        setError(err)
        setStatus('error')
      })
    return () => {
      active = false
    }
  }, [attempt])

  useEffect(() => {
    const expired = () => {
      setUser(null)
      setStatus('anonymous')
    }
    window.addEventListener(AUTH_EVENT, expired)
    return () => window.removeEventListener(AUTH_EVENT, expired)
  }, [])

  const login = useCallback(async (username, password) => {
    const result = await loginRequest(username, password)
    setUser(result.user)
    setStatus('authenticated')
  }, [])

  const register = useCallback(async (username, password) => {
    const result = await registerRequest(username, password)
    setUser(result.user)
    setStatus('authenticated')
  }, [])

  const logout = useCallback(async () => {
    await logoutRequest().catch(() => null)
    setUser(null)
    setStatus('anonymous')
  }, [])

  const refreshUser = useCallback(async () => {
    const me = await fetchMe()
    setUser(me.user)
    return me.user
  }, [])

  const endSession = useCallback(() => {
    setUser(null)
    setStatus('anonymous')
  }, [])

  const retry = useCallback(() => setAttempt((value) => value + 1), [])

  const value = useMemo(
    () => ({
      status,
      user,
      info,
      error,
      login,
      register,
      logout,
      endSession,
      refreshUser,
      setUser,
      retry,
    }),
    [status, user, info, error, login, register, logout, endSession, refreshUser, retry],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
