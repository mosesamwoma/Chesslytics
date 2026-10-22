const LEVELS: Record<string, { dot: string; label: string }> = {
  inaccuracy: { dot: 'dot-warning', label: 'inaccuracy' },
  mistake: { dot: 'dot-serious', label: 'mistake' },
  blunder: { dot: 'dot-critical', label: 'blunder' },
  normal: { dot: 'dot-good', label: 'normal' },
}

export default function SeverityBadge({ severity }: { severity: string }) {
  const level = LEVELS[severity] || { dot: 'dot-muted', label: severity }
  return (
    <span className="badge">
      <span className={`dot ${level.dot}`} aria-hidden="true" />
      {level.label}
    </span>
  )
}
