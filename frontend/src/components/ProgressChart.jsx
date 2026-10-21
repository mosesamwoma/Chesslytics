import { useMemo } from 'react'

const WIDTH = 640
const HEIGHT = 220
const PAD = { left: 46, right: 16, top: 16, bottom: 34 }

function shortDate(value) {
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function niceMax(value) {
  if (value <= 0) return 1
  const exponent = Math.pow(10, Math.floor(Math.log10(value)))
  const fraction = value / exponent
  const step = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10
  return step * exponent
}

function LineChart({ title, rows, valueKey, digits, color, unit }) {
  const points = useMemo(
    () => rows.filter((row) => row[valueKey] !== null && row[valueKey] !== undefined),
    [rows, valueKey],
  )
  if (points.length < 2) return null

  const top = niceMax(Math.max(...points.map((row) => row[valueKey])))
  const innerWidth = WIDTH - PAD.left - PAD.right
  const innerHeight = HEIGHT - PAD.top - PAD.bottom
  const xFor = (index) => PAD.left + (innerWidth * index) / (points.length - 1)
  const yFor = (value) => PAD.top + innerHeight - (innerHeight * value) / top
  const path = points
    .map((row, index) => `${index === 0 ? 'M' : 'L'}${xFor(index).toFixed(1)},${yFor(row[valueKey]).toFixed(1)}`)
    .join(' ')
  const ticks = [0, 0.5, 1].map((fraction) => top * fraction)
  const labelEvery = Math.max(1, Math.ceil(points.length / 6))

  return (
    <figure className="chart-figure">
      <figcaption className="chart-title">{title}</figcaption>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="chart-svg"
        role="img"
        aria-label={`${title} by week, ${points.length} weeks`}
      >
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={PAD.left}
              x2={WIDTH - PAD.right}
              y1={yFor(tick)}
              y2={yFor(tick)}
              style={{ stroke: tick === 0 ? 'var(--baseline)' : 'var(--gridline)', strokeWidth: 1 }}
            />
            <text x={PAD.left - 8} y={yFor(tick) + 4} textAnchor="end" className="axis-text">
              {tick.toFixed(digits > 1 ? 1 : 0)}
            </text>
          </g>
        ))}
        <path
          d={path}
          fill="none"
          style={{ stroke: color, strokeWidth: 2.5 }}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {points.map((row, index) => (
          <g key={row.week_start}>
            <circle
              cx={xFor(index)}
              cy={yFor(row[valueKey])}
              r="4.5"
              style={{ fill: color, stroke: 'var(--surface-1)', strokeWidth: 2 }}
            >
              <title>
                {`Week of ${shortDate(row.week_start)}: ${row[valueKey].toFixed(digits)} ${unit} (${row.games} ${row.games === 1 ? 'game' : 'games'}, ${row.moves} moves)`}
              </title>
            </circle>
            {index % labelEvery === 0 || index === points.length - 1 ? (
              <text
                x={xFor(index)}
                y={HEIGHT - 12}
                textAnchor="middle"
                className="axis-text"
              >
                {shortDate(row.week_start)}
              </text>
            ) : null}
          </g>
        ))}
      </svg>
    </figure>
  )
}

function change(recent, earlier) {
  if (!earlier) return null
  const delta = ((recent - earlier) / earlier) * 100
  if (Math.abs(delta) < 1) return 'about the same'
  return `${Math.abs(delta).toFixed(0)}% ${delta < 0 ? 'lower' : 'higher'}`
}

export default function ProgressChart({ progress }) {
  const rows = progress?.weeks || []
  if (rows.length < 2) {
    return (
      <div className="notice">
        Analyze games from at least two different weeks to see how you are improving.
      </div>
    )
  }
  const trend = progress.trend

  return (
    <div>
      {trend ? (
        <p className="subtitle" style={{ marginTop: 0 }}>
          Last {trend.weeks} weeks compared with the {trend.weeks} before: average loss per move{' '}
          <strong>
            {trend.recent.average_loss.toFixed(2)} vs {trend.earlier.average_loss.toFixed(2)} pawns
          </strong>{' '}
          ({change(trend.recent.average_loss, trend.earlier.average_loss)}), mistakes per 100
          moves{' '}
          <strong>
            {trend.recent.mistakes_per_100.toFixed(1)} vs {trend.earlier.mistakes_per_100.toFixed(1)}
          </strong>{' '}
          ({change(trend.recent.mistakes_per_100, trend.earlier.mistakes_per_100)}). Lower is
          better.
        </p>
      ) : (
        <p className="subtitle" style={{ marginTop: 0 }}>
          {progress.player ? `Your moves as ${progress.player}.` : 'Both sides of every game.'}{' '}
          Lower is better. Weeks start on Monday.
        </p>
      )}
      <div className="grid grid-two">
        <LineChart
          title="Average loss per move (pawns)"
          rows={rows}
          valueKey="average_loss"
          digits={2}
          color="var(--series-1)"
          unit="pawns"
        />
        <LineChart
          title="Mistakes per 100 moves"
          rows={rows}
          valueKey="mistakes_per_100"
          digits={1}
          color="var(--series-2)"
          unit="mistakes per 100 moves"
        />
      </div>
      <details className="chart-data">
        <summary>Show the numbers</summary>
        <div style={{ overflowX: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th>Week of</th>
                <th className="num">Games</th>
                <th className="num">Moves</th>
                <th className="num">Mistakes</th>
                <th className="num">Per 100 moves</th>
                <th className="num">Avg loss (pawns)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.week_start}>
                  <td>{shortDate(row.week_start)}</td>
                  <td className="num">{row.games}</td>
                  <td className="num">{row.moves}</td>
                  <td className="num">{row.mistakes}</td>
                  <td className="num">{row.mistakes_per_100 === null ? '—' : row.mistakes_per_100.toFixed(1)}</td>
                  <td className="num">{row.average_loss === null ? '—' : row.average_loss.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  )
}
