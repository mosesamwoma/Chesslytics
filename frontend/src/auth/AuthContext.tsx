import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import type { Dispatch, ReactNode, SetStateAction } from 'react'
import { AUTH_EVENT, statusOf, toProblem } from '../services/api.ts'
import type { Problem } from '../services/api.ts'
import {
  fetchMe,
  fetchStatus,
  login as loginRequest,
  logout as logoutRequest,
  register as registerRequest,
} from '../services/authService.ts'
import type { AuthInfo, User } from '../types.ts'

export type SessionStatus = 'loading' | 'authenticated' | 'anonymous' | 'error'

export interface AuthValue {
  status: SessionStatus
  user: User | null
  info: AuthInfo
  error: Problem
  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  endSession: () => void
  refreshUser: () => Promise<User>
  setUser: Dispatch<SetStateAction<User | null>>
  retry: () => void
}

interface ResolvedSession {
  status: 'authenticated' | 'anonymous'
  user: User | null
  info: AuthInfo
}

export const AuthContext = createContext<AuthValue | null>(null)

async function resolveSession(): Promise<ResolvedSession> {
  const info = await fetchStatus()
  try {
    const me = await fetchMe()
    return { status: 'authenticated', user: me.user, info }
  } catch (err) {
    if (statusOf(err) === 401) return { status: 'anonymous', user: null, info }
    throw err
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>('loading')
  const [user, setUser] = useState<User | null>(null)
  const [info, setInfo] = useState<AuthInfo>({
    registration_enabled: false,
    min_password_length: 10,
    email_enabled: false,
  })
  const [error, setError] = useState<Problem>(null)
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
      .catch((err: unknown) => {
        if (!active) return
        setError(toProblem(err))
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

  const login = useCallback(async (username: string, password: string) => {
    const result = await loginRequest(username, password)
    setUser(result.user)
    setStatus('authenticated')
  }, [])

  const register = useCallback(async (username: string, password: string) => {
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

  const value = useMemo<AuthValue>(
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

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
