import type { ReactNode } from 'react'

interface StatTileProps {
  label: string
  value: ReactNode
  delta?: ReactNode
}

export default function StatTile({ label, value, delta }: StatTileProps) {
  return (
    <div className="card stat-tile">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {delta ? <div className="delta">{delta}</div> : null}
    </div>
  )
}
