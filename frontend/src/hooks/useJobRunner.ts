import { useCallback, useEffect, useRef, useState } from 'react'
import { toProblem } from '../services/api.ts'
import type { Problem } from '../services/api.ts'
import { cancelJob, isFinished, waitForJob } from '../services/analysisService.ts'
import type { Job } from '../types.ts'

export interface JobRunner {
  job: Job | null
  error: Problem
  running: boolean
  follow: (initial: Job | null | undefined) => Promise<Job | null>
  cancel: () => Promise<void>
  clear: () => void
  setError: (error: Problem) => void
}

export default function useJobRunner(): JobRunner {
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState<Problem>(null)
  const controller = useRef<AbortController | null>(null)

  useEffect(
    () => () => {
      if (controller.current) controller.current.abort()
    },
    [],
  )

  const follow = useCallback(async (initial: Job | null | undefined): Promise<Job | null> => {
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
      if (!abort.signal.aborted) setError(toProblem(err))
      return null
    }
  }, [])

  const cancel = useCallback(async () => {
    if (!job) return
    try {
      await cancelJob(job.id)
    } catch (err) {
      setError(toProblem(err))
    }
  }, [job])

  const clear = useCallback(() => {
    setJob(null)
    setError(null)
  }, [])

  const running = Boolean(job) && !isFinished(job)

  return { job, error, running, follow, cancel, clear, setError }
}
