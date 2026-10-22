import { useEffect, useState } from 'react'
import { retryAfterOf } from '../services/api.ts'

export function formatWait(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  if (minutes < 60) return rest ? `${minutes}m ${String(rest).padStart(2, '0')}s` : `${minutes}m`
  const hours = Math.floor(minutes / 60)
  const left = minutes % 60
  return left ? `${hours}h ${String(left).padStart(2, '0')}m` : `${hours}h`
}

export function useRetryAfter(error: unknown): { remaining: number; blocked: boolean } {
  const total = retryAfterOf(error)
  const [remaining, setRemaining] = useState(total)

  useEffect(() => {
    if (!total) {
      setRemaining(0)
      return undefined
    }
    const end = Date.now() + total * 1000
    setRemaining(total)
    const timer = setInterval(() => {
      const left = Math.max(0, Math.ceil((end - Date.now()) / 1000))
      setRemaining(left)
      if (left === 0) clearInterval(timer)
    }, 500)
    return () => clearInterval(timer)
  }, [error, total])

  return { remaining, blocked: total > 0 && remaining > 0 }
}
