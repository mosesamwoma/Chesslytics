import { useMemo, useState } from 'react'
import { categoryLabel } from '../labels.js'

const COLUMNS = [
  { key: 'games', label: 'Games', numeric: true },
  { key: 'win_rate', label: 'Win rate', numeric: true },
  { key: 'average_loss', label: 'Avg loss', numeric: true },
  { key: 'mistakes_per_game', label: 'Mistakes / game', numeric: true },
]

function percent(value) {
  return value === null || value === undefined ? '—' : `${value.toFixed(0)}%`
}

export default function OpeningsTable({ report }) {
  const [sortKey, setSortKey] = useState('games')
  const [descending, setDescending] = useState(true)
  const rows = useMemo(() => report?.openings || [], [report])

  const sorted = useMemo(() => {
    const copy = [...rows]
    copy.sort((a, b) => {
      const left = a[sortKey]
      const right = b[sortKey]
      if (left === null || left === undefined) return 1
      if (right === null || right === undefined) return -1
      return descending ? right - left : left - right
    })
    return copy
  }, [rows, sortKey, descending])

  if (!rows.length) {
    return (
      <div className="notice">
        No analyzed games yet. Run an analysis on the Games page to see how each opening goes.
      </div>
    )
  }

  const choose = (key) => {
    if (key === sortKey) {
      setDescending((value) => !value)
    } else {
      setSortKey(key)
      setDescending(key === 'games' || key === 'win_rate')
    }
  }

  const hasWinRates = rows.some((row) => row.win_rate !== null)

  return (
    <div>
      <p className="subtitle" style={{ marginTop: 0 }}>
        {report.player
          ? `Your games as ${report.player}, grouped by opening.`
          : 'Both sides of every game are counted. Set your username when you analyze to see win rates.'}{' '}
        Average loss is in pawns per move; lower is better.
      </p>
      <div style={{ overflowX: 'auto' }}>
        <table className="table">
          <thead>
            <tr>
              <th>Opening</th>
              {COLUMNS.map((column) => (
                <th
                  key={column.key}
                  className="num"
                  aria-sort={
                    column.key === sortKey ? (descending ? 'descending' : 'ascending') : 'none'
                  }
                >
                  <button type="button" className="th-button" onClick={() => choose(column.key)}>
                    {column.label}
                    {column.key === sortKey ? (descending ? ' ▼' : ' ▲') : ''}
                  </button>
                </th>
              ))}
              <th>Most mistakes at</th>
              <th>Most common</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <tr key={row.opening}>
                <td>
                  {row.opening}
                  {row.eco ? <span className="muted"> · {row.eco}</span> : null}
                  {report.player ? (
                    <div className="muted">
                      {row.as_white} as White · {row.as_black} as Black
                    </div>
                  ) : null}
                </td>
                <td className="num">{row.games}</td>
                <td className="num">
                  {percent(row.win_rate)}
                  {row.win_rate !== null ? (
                    <div className="muted">
                      {row.wins}W {row.draws}D {row.losses}L
                    </div>
                  ) : null}
                </td>
                <td className="num">
                  {row.average_loss === null ? '—' : row.average_loss.toFixed(2)}
                </td>
                <td className="num">{row.mistakes_per_game.toFixed(1)}</td>
                <td>
                  {row.worst_move ? (
                    <>
                      move {row.worst_move}
                      <div className="muted">
                        {row.worst_move_mistakes} of {row.mistakes}
                      </div>
                    </>
                  ) : (
                    '—'
                  )}
                </td>
                <td>{row.top_category ? categoryLabel(row.top_category) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!hasWinRates && report.player ? (
        <p className="muted">Win rates appear once results are known for these games.</p>
      ) : null}
    </div>
  )
}
