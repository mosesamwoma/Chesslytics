import { categoryLabel, titleCase } from '../labels.ts'
import type { TimeControlReport } from '../types.ts'

function number(value: number | null | undefined, digits: number): string {
  return value === null || value === undefined ? '—' : value.toFixed(digits)
}

export default function TimeControlTable({ report }: { report: TimeControlReport | null }) {
  const rows = report?.time_controls || []
  if (!report || !rows.length) {
    return (
      <div className="notice">
        No analyzed games yet. Time controls come from the TimeControl header of your PGN files.
      </div>
    )
  }

  return (
    <div className="card" style={{ overflowX: 'auto' }}>
      <table className="table">
        <thead>
          <tr>
            <th>Time control</th>
            <th className="num">Games</th>
            <th className="num">Mistakes</th>
            <th className="num">Per 100 moves</th>
            <th className="num">Avg loss</th>
            <th className="num">Win rate</th>
            <th>Most common</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <td>{titleCase(row.key)}</td>
              <td className="num">{row.games}</td>
              <td className="num">{row.mistakes}</td>
              <td className="num">{number(row.mistakes_per_100, 1)}</td>
              <td className="num">{number(row.average_loss, 2)}</td>
              <td className="num">
                {row.win_rate === null ? '—' : `${row.win_rate.toFixed(0)}%`}
              </td>
              <td>{row.top_category ? categoryLabel(row.top_category) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted" style={{ fontSize: 13, marginBottom: 0 }}>
        Games are grouped by base time plus 40 times the increment, the same rule Lichess uses.
        Win rate needs your username to be set when you analyze.
      </p>
    </div>
  )
}
