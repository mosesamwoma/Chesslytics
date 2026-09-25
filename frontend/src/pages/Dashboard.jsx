import { Link } from 'react-router-dom'
import CategoryBars from '../components/CategoryBars.jsx'
import GameCard from '../components/GameCard.jsx'
import StatTile from '../components/StatTile.jsx'
import { useGames } from '../hooks/useGames.js'
import { useOverview } from '../hooks/useProfile.js'
import { SEVERITY_ORDER, categoryLabel, phaseLabel, titleCase } from '../labels.js'

export default function Dashboard() {
  const overview = useOverview()
  const games = useGames({ limit: 5 })

  if (overview.error) {
    return (
      <div className="notice error">
        Could not reach the API: {overview.error.message}
      </div>
    )
  }

  const data = overview.data
  const severityRows = data
    ? SEVERITY_ORDER.filter((level) =>
        data.by_severity.some((row) => row.key === level),
      ).map((level) => data.by_severity.find((row) => row.key === level))
    : []

  const pressured =
    data && data.mistakes ? Math.round((data.time_pressure_mistakes / data.mistakes) * 100) : 0

  return (
    <div className={overview.loading && data ? 'loading-dim' : undefined}>
      <div className="page-head">
        <div>
          <h1>Dashboard</h1>
          <p className="subtitle">
            What you repeat, not just what you played. Counts come from stored analyses.
          </p>
        </div>
        <Link className="button primary" to="/games">
          Import games
        </Link>
      </div>

      {!data && overview.loading ? <p className="muted">Loading&hellip;</p> : null}

      {data ? (
        <>
          <div className="card" style={{ marginBottom: 12 }}>
            <div className="hero-label">Mistakes recorded</div>
            <div className="hero">{data.mistakes}</div>
            <div className="secondary">
              across {data.games_analyzed} analyzed {data.games_analyzed === 1 ? 'game' : 'games'}
              {data.games > data.games_analyzed
                ? ` (${data.games - data.games_analyzed} stored but not analyzed)`
                : ''}
            </div>
          </div>

          <div className="grid grid-kpi">
            <StatTile label="Games stored" value={data.games} />
            <StatTile label="Games analyzed" value={data.games_analyzed} />
            <StatTile
              label="Average loss per mistake"
              value={`${data.average_loss.toFixed(2)}`}
              delta="pawns"
            />
            <StatTile
              label="Mistakes under time pressure"
              value={data.time_pressure_mistakes}
              delta={`${pressured}% of all mistakes`}
            />
          </div>

          <div className="grid grid-two" style={{ marginTop: 16 }}>
            <div className="card">
              <h2>Mistake types</h2>
              <p className="subtitle">
                Each mistake is assigned one category, by the first rule that matches.
              </p>
              <CategoryBars
                rows={data.by_category}
                labelFor={categoryLabel}
                emptyLabel="No analyzed mistakes yet."
              />
            </div>

            <div className="card">
              <h2>Where they happen</h2>
              <p className="subtitle">Game phase at the moment of the mistake.</p>
              <CategoryBars
                rows={data.by_phase}
                labelFor={phaseLabel}
                emptyLabel="No analyzed mistakes yet."
              />
            </div>
          </div>

          <div className="grid grid-two" style={{ marginTop: 16 }}>
            <div className="card">
              <h2>By severity</h2>
              <p className="subtitle">Evaluation loss in pawns, banded.</p>
              <CategoryBars
                rows={severityRows}
                labelFor={titleCase}
                emptyLabel="No analyzed mistakes yet."
              />
            </div>

            <div className="card">
              <h2>Openings with the most mistakes</h2>
              <p className="subtitle">Only games whose headers name an opening appear here.</p>
              <CategoryBars
                rows={data.top_openings}
                emptyLabel="No opening headers found in the analyzed games."
              />
            </div>
          </div>

          <div className="card" style={{ marginTop: 16 }}>
            <div className="chart-head">
              <h2>Recent games</h2>
              <Link to="/games">All games</Link>
            </div>
            {games.data && games.data.games.length ? (
              <div className="list" style={{ marginTop: 12 }}>
                {games.data.games.map((game) => (
                  <GameCard key={game.id} game={game} />
                ))}
              </div>
            ) : (
              <p className="muted">Nothing imported yet.</p>
            )}
          </div>
        </>
      ) : null}
    </div>
  )
}
