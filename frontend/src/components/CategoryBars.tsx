import type { CountRow } from '../types.ts'

interface CategoryBarsProps {
  rows?: CountRow[]
  labelFor?: (key: string) => string
  emptyLabel?: string
}

const identity = (key: string): string => key

export default function CategoryBars({
  rows = [],
  labelFor = identity,
  emptyLabel,
}: CategoryBarsProps) {
  if (!rows.length) {
    return <p className="muted">{emptyLabel || 'Nothing to show yet.'}</p>
  }

  const max = Math.max(...rows.map((row) => row.count))

  return (
    <div>
      {rows.map((row) => (
        <div className="bar-row" key={row.key}>
          <span className="secondary">
            {labelFor(row.key)}
            {row.games ? <span className="muted"> ({row.games} games)</span> : null}
          </span>
          <div className="bar-track">
            <div
              className="bar-fill"
              style={{ width: `${max ? (row.count / max) * 100 : 0}%` }}
            />
          </div>
          <span className="bar-value">{row.count}</span>
        </div>
      ))}
    </div>
  )
}
