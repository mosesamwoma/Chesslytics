interface HeatBoardProps {
  values: number[]
  title: string
  caption?: string
}

const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']

export default function HeatBoard({ values, title, caption }: HeatBoardProps) {
  const max = Math.max(0, ...values)
  const total = values.reduce((sum, value) => sum + value, 0)
  const rows = [7, 6, 5, 4, 3, 2, 1, 0]

  return (
    <figure className="heat">
      <figcaption className="chart-title">{title}</figcaption>
      <div className="heat-grid" role="img" aria-label={`${title}. ${total} in total.`}>
        {rows.map((rank) =>
          FILES.map((file, fileIndex) => {
            const value = values[rank * 8 + fileIndex] || 0
            const alpha = max ? Math.round((value / max) * 85) : 0
            const dark = (rank + fileIndex) % 2 === 0
            return (
              <div
                key={`${file}${rank + 1}`}
                className={dark ? 'heat-cell dark' : 'heat-cell light'}
                title={`${file}${rank + 1}: ${value}`}
              >
                {value ? (
                  <span
                    className="heat-fill"
                    style={{
                      background: `color-mix(in srgb, var(--status-critical) ${alpha + 15}%, transparent)`,
                    }}
                  >
                    {value}
                  </span>
                ) : null}
              </div>
            )
          }),
        )}
      </div>
      {caption ? <p className="muted heat-caption">{caption}</p> : null}
    </figure>
  )
}
