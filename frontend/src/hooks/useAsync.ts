import { useCallback, useEffect, useState } from 'react'
import { toProblem } from '../services/api.ts'
import type { Problem } from '../services/api.ts'

export interface AsyncState<T> {
  data: T | null
  error: Problem
  loading: boolean
  reload: () => () => void
}

export function useAsync<T>(loader: () => Promise<T>, deps: readonly unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<Problem>(null)
  const [loading, setLoading] = useState(true)

  const run = useCallback(() => {
    let active = true
    setLoading(true)
    setError(null)
    loader()
      .then((result) => {
        if (active) {
          setData(result)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(toProblem(err))
          setLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, deps)

  useEffect(() => run(), [run])

  return { data, error, loading, reload: run }
}
