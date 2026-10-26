interface EvalBarProps {
  white: number | null
  flipped?: boolean
}

export default function EvalBar({ white, flipped = false }: EvalBarProps) {
  if (white === null) return <div className="eval-bar empty" aria-hidden="true" />
  const clamped = Math.max(0, Math.min(100, white))
  const label = `${clamped.toFixed(0)}% for White`
  return (
    <div
      className={flipped ? 'eval-bar flipped' : 'eval-bar'}
      role="img"
      aria-label={`Engine evaluation: ${label}`}
      title={label}
    >
      <div className="eval-fill" style={{ height: `${clamped}%` }} />
    </div>
  )
}
