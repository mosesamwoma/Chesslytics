import { useMemo, useState } from 'react'

const WIDTH = 760
const HEIGHT = 280
const PAD = { top: 14, right: 18, bottom: 36, left: 44 }
const PLOT_W = WIDTH - PAD.left - PAD.right
const PLOT_H = HEIGHT - PAD.top - PAD.bottom

const SEVERITY_COLOR = {
  inaccuracy: 'var(--status-warning)',
  mistake: 'var(--status-serious)',
  blunder: 'var(--status-critical)',
}

function flip(value, color, perspective) {
  if (value === null || value === undefined) return null
  return color === perspective ? value : 100 - value
}

function formatClock(seconds) {
  if (seconds === null || seconds === undefined) return '—'
  const total = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(total / 60)
  const rest = total % 60
  return `${minutes}:${String(rest).padStart(2, '0')}`
}

function formatEval(cp, mate) {
  if (mate !== null && mate !== undefined) return `#${mate}`
  if (cp === null || cp === undefined) return '—'
  return `${cp >= 0 ? '+' : ''}${(cp / 100).toFixed(2)}`
}

export default function AnalysisChart({ sequence = [], mistakes = [], perspective = 'white' }) {
  const [active, setActive] = useState(null)
  const [showTable, setShowTable] = useState(false)

  const points = useMemo(() => {
    const rows = []
    sequence.forEach((move) => {
      const before = flip(move.winpct_before, move.color, perspective)
      const after = flip(move.winpct_after, move.color, perspective)
      if (before === null) return
      rows.push({ ply: move.ply, value: before, post: after === null ? before : after, move })
    })
    const last = sequence[sequence.length - 1]
    if (last) {
      const after = flip(last.winpct_after, last.color, perspective)
      if (after !== null) {
        rows.push({ ply: last.ply + 1, value: after, post: after, move: last, tail: true })
      }
    }
    return rows
  }, [sequence, perspective])

  const markers = useMemo(() => {
    const indexByPly = new Map(points.map((point, index) => [point.ply, index]))
    return mistakes
      .map((mistake) => {
        const index = indexByPly.get(mistake.ply)
        if (index === undefined) return null
        return { mistake, index, point: points[index] }
      })
      .filter(Boolean)
  }, [mistakes, points])

  if (points.length < 2) {
    return (
      <div className="card chart-card">
        <h2>Win probability</h2>
        <p className="muted">This game has not been analyzed yet.</p>
      </div>
    )
  }

  const xFor = (index) => PAD.left + (index / (points.length - 1)) * PLOT_W
  const yFor = (value) => PAD.top + (1 - value / 100) * PLOT_H

  const linePath = points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${xFor(index)} ${yFor(point.value)}`)
    .join(' ')

  const current = active === null ? null : points[active]

  const onKeyDown = (event) => {
    if (event.key === 'ArrowRight') {
      event.preventDefault()
      setActive((index) => Math.min(points.length - 1, (index === null ? -1 : index) + 1))
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault()
      setActive((index) => Math.max(0, (index === null ? points.length : index) - 1))
    } else if (event.key === 'Escape') {
      setActive(null)
    }
  }

  const onPointerMove = (event) => {
    const box = event.currentTarget.getBoundingClientRect()
    if (!box.width) return
    const ratio = (event.clientX - box.left) / box.width
    const raw = (ratio * WIDTH - PAD.left) / PLOT_W
    const index = Math.round(raw * (points.length - 1))
    setActive(Math.max(0, Math.min(points.length - 1, index)))
  }

  const severities = [...new Set(markers.map((marker) => marker.mistake.severity))]

  return (
    <div className="card chart-card">
      <div className="chart-head">
        <div>
          <h2>Win probability</h2>
          <p className="subtitle">
            Engine win chance for {perspective === 'white' ? 'White' : 'Black'}, one point per
            played move.
          </p>
        </div>
        <button type="button" className="button" onClick={() => setShowTable((value) => !value)}>
          {showTable ? 'Show chart' : 'Table view'}
        </button>
      </div>

      {showTable ? (
        <table className="table">
          <thead>
            <tr>
              <th>Move</th>
              <th>Played</th>
              <th className="num">Win %</th>
              <th className="num">Eval</th>
              <th className="num">Loss</th>
              <th className="num">Clock</th>
            </tr>
          </thead>
          <tbody>
            {points.map((point) => (
              <tr key={`${point.ply}-${point.tail ? 't' : 'm'}`}>
                <td>
                  {point.move.move_number}
                  {point.move.color === 'white' ? '.' : '...'}
                </td>
                <td className="mono">{point.move.san || '—'}</td>
                <td className="num">{point.post.toFixed(1)}</td>
                <td className="num">
                  {formatEval(point.move.eval_after_cp, point.move.eval_after_mate)}
                </td>
                <td className="num">
                  {point.move.loss_cp === null || point.move.loss_cp === undefined
                    ? '—'
                    : (point.move.loss_cp / 100).toFixed(2)}
                </td>
                <td className="num">{formatClock(point.move.clock_after)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div style={{ position: 'relative' }}>
          <svg
            className="chart-svg"
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            preserveAspectRatio="xMidYMid meet"
            role="img"
            aria-label={`Win probability for ${perspective} across ${points.length} moves`}
            tabIndex={0}
            onKeyDown={onKeyDown}
            onMouseMove={onPointerMove}
            onMouseLeave={() => setActive(null)}
          >
            {[0, 25, 50, 75, 100].map((value) => (
              <g key={value}>
                <line
                  x1={PAD.left}
                  x2={WIDTH - PAD.right}
                  y1={yFor(value)}
                  y2={yFor(value)}
                  style={{
                    stroke: value === 50 ? 'var(--baseline)' : 'var(--gridline)',
                    strokeWidth: 1,
                  }}
                />
                <text className="axis-text" x={PAD.left - 8} y={yFor(value) + 3} textAnchor="end">
                  {value}
                </text>
              </g>
            ))}

            {points.map((point, index) =>
              index % 10 === 0 ? (
                <text
                  key={`tick-${point.ply}-${index}`}
                  className="axis-text"
                  x={xFor(index)}
                  y={HEIGHT - PAD.bottom + 16}
                  textAnchor="middle"
                >
                  {point.move.move_number}
                </text>
              ) : null,
            )}

            <text
              className="axis-text"
              x={PAD.left + PLOT_W / 2}
              y={HEIGHT - 4}
              textAnchor="middle"
            >
              move number
            </text>

            <path
              d={linePath}
              fill="none"
              style={{ stroke: 'var(--series-1)', strokeWidth: 2 }}
              strokeLinejoin="round"
              strokeLinecap="round"
            />

            {markers.map(({ mistake, index, point }) => (
              <circle
                key={`${mistake.id || mistake.ply}-dot`}
                cx={xFor(index)}
                cy={yFor(point.post)}
                r={4.5}
                style={{
                  fill: SEVERITY_COLOR[mistake.severity] || 'var(--status-critical)',
                  stroke: 'var(--surface-1)',
                  strokeWidth: 2,
                }}
              />
            ))}

            {current ? (
              <g>
                <line
                  x1={xFor(active)}
                  x2={xFor(active)}
                  y1={PAD.top}
                  y2={PAD.top + PLOT_H}
                  style={{ stroke: 'var(--baseline)', strokeWidth: 1 }}
                />
                <circle
                  cx={xFor(active)}
                  cy={yFor(current.value)}
                  r={4.5}
                  style={{
                    fill: 'var(--series-1)',
                    stroke: 'var(--surface-1)',
                    strokeWidth: 2,
                  }}
                />
              </g>
            ) : null}
          </svg>

          {current ? (
            <div
              className="tooltip"
              style={{
                position: 'absolute',
                left: `${(xFor(active) / WIDTH) * 100}%`,
                top: `${(yFor(current.value) / HEIGHT) * 100}%`,
                transform: 'translate(-50%, -112%)',
                pointerEvents: 'none',
              }}
            >
              <div className="title">
                {current.move.move_number}
                {current.move.color === 'white' ? '.' : '...'} {current.move.san || '—'}
              </div>
              <div className="line">
                <span>Win %</span>
                <b>{current.post.toFixed(1)}</b>
              </div>
              <div className="line">
                <span>Eval</span>
                <b>{formatEval(current.move.eval_after_cp, current.move.eval_after_mate)}</b>
              </div>
              <div className="line">
                <span>Loss</span>
                <b>
                  {current.move.loss_cp === null || current.move.loss_cp === undefined
                    ? '—'
                    : `${(current.move.loss_cp / 100).toFixed(2)}`}
                </b>
              </div>
              <div className="line">
                <span>Clock</span>
                <b>{formatClock(current.move.clock_after)}</b>
              </div>
            </div>
          ) : null}
        </div>
      )}

      {severities.length ? (
        <div className="chart-legend">
          {severities.map((severity) => (
            <span key={severity}>
              <span
                className="dot"
                style={{
                  background: SEVERITY_COLOR[severity] || 'var(--status-critical)',
                }}
                aria-hidden="true"
              />
              {severity}
            </span>
          ))}
          <span className="muted">
            Marker colour shows the severity of the mistake played at that move.
          </span>
        </div>
      ) : null}
    </div>
  )
}
