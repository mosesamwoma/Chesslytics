import { useCallback, useEffect, useRef, useState } from 'react'
import { cancelJob, isFinished, waitForJob } from '../services/analysisService.js'

export default function useJobRunner() {
  const [job, setJob] = useState(null)
  const [error, setError] = useState(null)
  const controller = useRef(null)

  useEffect(
    () => () => {
      if (controller.current) controller.current.abort()
    },
    [],
  )

  const follow = useCallback(async (initial) => {
    if (!initial) return null
    if (controller.current) controller.current.abort()
    const abort = new AbortController()
    controller.current = abort
    setError(null)
    setJob(initial)
    try {
      return await waitForJob(initial.id, {
        onUpdate: (next) => {
          if (!abort.signal.aborted) setJob(next)
        },
        signal: abort.signal,
      })
    } catch (err) {
      if (!abort.signal.aborted) setError(err)
      return null
    }
  }, [])

  const cancel = useCallback(async () => {
    if (!job) return
    try {
      await cancelJob(job.id)
    } catch (err) {
      setError(err)
    }
  }, [job])

  const clear = useCallback(() => {
    setJob(null)
    setError(null)
  }, [])

  const running = Boolean(job) && !isFinished(job)

  return { job, error, running, follow, cancel, clear, setError }
}
