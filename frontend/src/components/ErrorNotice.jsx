import { formatWait, useRetryAfter } from '../hooks/useRetryAfter.js'

const WAIT_PHRASE = /[;,.]?\s*(?:please\s+)?try again in \d+ seconds?\.?/i

export default function ErrorNotice({ error, style, children }) {
  const { remaining, blocked } = useRetryAfter(error)
  if (!error) return null
  const raw = typeof error === 'string' ? error : error.message || 'Something went wrong.'
  const timed = typeof error !== 'string' && Boolean(error.retryAfter)
  const message = timed ? raw.replace(WAIT_PHRASE, '').trim() || 'Too many requests.' : raw
  return (
    <div className="notice error" role="alert" style={style}>
      {message}
      {timed ? (
        blocked ? (
          <strong> Try again in {formatWait(remaining)}.</strong>
        ) : (
          <strong> You can try again now.</strong>
        )
      ) : null}
      {children ? <> {children}</> : null}
    </div>
  )
}
