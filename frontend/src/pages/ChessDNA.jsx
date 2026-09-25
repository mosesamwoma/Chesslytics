import { Link } from 'react-router-dom'
import CategoryBars from '../components/CategoryBars.jsx'
import StatTile from '../components/StatTile.jsx'
import { useProfile } from '../hooks/useProfile.js'
import { phaseLabel, titleCase } from '../labels.js'

export default function ChessDNA() {
  const { data, error, loading, reload } = useProfile()

  if (error) {
    const missing = error.status === 404
    return (
      <div className="notice">
        {missing ? (
          <>
            No profile yet. Import a PGN and run an analysis on the{' '}
            <Link to="/games">Games</Link> page.
          </>
        ) : (
          <>
            {error.message}{' '}
            <button type="button" className="button" onClick={reload}>
              Retry
            </button>
          </>
        )}
      </div>
    )
  }

  if (!data) {
    return <p className="muted">{loading ? 'Loading…' : 'No profile yet.'}</p>
  }

  const profile = data.profile || {}
  const pressure = profile.time_pressure || {}

  return (
    <div className={loading ? 'loading-dim' : undefined}>
      <div className="page-head">
        <div>
          <h1>Chess DNA</h1>
          <p className="subtitle">
            {data.player ? `${data.player} · ` : ''}
            {data.color} · {data.games_analyzed} games · {data.moves_scored} moves scored
            {data.engine ? ` · ${data.engine}` : ''}
          </p>
        </div>
        <Link className="button" to="/patterns">
          Patterns
        </Link>
      </div>

      <div className="grid grid-kpi">
        <StatTile label="Mistakes" value={data.mistake_count} />
        <StatTile
          label="Average loss per mistake"
          value={Number(profile.average_loss || 0).toFixed(2)}
          delta="pawns"
        />
        <StatTile
          label="Most problematic phase"
          value={profile.most_problematic_phase ? phaseLabel(profile.most_problematic_phase.phase) : '—'}
        />
        <StatTile
          label="Positions that failed to evaluate"
          value={data.moves_failed}
          delta={data.moves_failed ? 'excluded from every count' : 'none'}
        />
      </div>

      <div className="grid grid-two" style={{ marginTop: 16 }}>
        <div className="card">
          <h2>Time pressure</h2>
          <p className="subtitle">
            {pressure.count || 0} of {data.mistake_count} mistakes were played below{' '}
            {pressure.threshold_seconds}s. Clock data was present in{' '}
            {profile.games_with_clock ?? 0} of {profile.games_analyzed ?? 0} games, so this
            describes only those.
          </p>
          <div
            className="bar-track"
            style={{ height: 22, background: 'var(--seq-low)', borderRadius: 4 }}
          >
            <div
              className="bar-fill"
              style={{
                width: `${Math.min(100, pressure.share || 0)}%`,
                background: 'var(--seq-high)',
              }}
            />
          </div>
          <div className="row secondary" style={{ marginTop: 6, fontSize: 13 }}>
            <span>{pressure.share || 0}% of mistakes</span>
            <span className="muted">threshold: under {pressure.threshold_seconds}s remaining</span>
          </div>
        </div>

        <div className="card">
          <h2>Tactical weaknesses</h2>
          <p className="subtitle">
            Mistake categories with a concrete board cause behind them.
          </p>
          <CategoryBars
            rows={(profile.tactical_weaknesses || []).map((row) => ({
              key: row.label,
              count: row.count,
              games: row.games,
            }))}
            emptyLabel="No missed mates, hanging pieces or missed captures recorded."
          />
        </div>
      </div>

      <div className="grid grid-two" style={{ marginTop: 16 }}>
        <div className="card">
          <h2>Mistake types</h2>
          <CategoryBars
            rows={(profile.most_common_categories || []).map((row) => ({
              key: row.label,
              count: row.count,
              games: row.games,
            }))}
            emptyLabel="Nothing recurring yet."
          />
        </div>

        <div className="card">
          <h2>By phase</h2>
          <CategoryBars
            rows={(profile.phase_breakdown || []).map((row) => ({
              key: row.phase,
              count: row.count,
              games: row.games,
            }))}
            labelFor={phaseLabel}
            emptyLabel="Nothing recorded yet."
          />
        </div>
      </div>

      <div className="grid grid-two" style={{ marginTop: 16 }}>
        <div className="card">
          <h2>By severity</h2>
          <CategoryBars
            rows={(profile.severity_breakdown || []).map((row) => ({
              key: row.severity,
              count: row.count,
            }))}
            labelFor={titleCase}
            emptyLabel="Nothing recorded yet."
          />
        </div>

        <div className="card">
          <h2>Average loss by phase</h2>
          <table className="table">
            <thead>
              <tr>
                <th>Phase</th>
                <th className="num">Mistakes</th>
                <th className="num">Average loss</th>
              </tr>
            </thead>
            <tbody>
              {(profile.average_loss_by_phase || []).map((row) => (
                <tr key={row.phase}>
                  <td>{phaseLabel(row.phase)}</td>
                  <td className="num">{row.count}</td>
                  <td className="num">{row.average_loss.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-two" style={{ marginTop: 16 }}>
        <div className="card">
          <h2>Openings you lose ground in</h2>
          {(profile.opening_patterns || []).length ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Opening</th>
                  <th className="num">Mistakes</th>
                  <th className="num">Games</th>
                </tr>
              </thead>
              <tbody>
                {profile.opening_patterns.map((row) => (
                  <tr key={row.opening}>
                    <td>{row.opening}</td>
                    <td className="num">{row.count}</td>
                    <td className="num">{row.games}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted">
              No opening headers were found in the analyzed games, so nothing can be grouped here.
            </p>
          )}
        </div>

        <div className="card">
          <h2>What the data says</h2>
          <p className="subtitle">
            Frequency and conditions only &mdash; no claims about why you played a move.
          </p>
          {profile.observations && profile.observations.length ? (
            <ul className="observations">
              {profile.observations.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">Not enough analyzed mistakes for observations.</p>
          )}
        </div>
      </div>
    </div>
  )
}
