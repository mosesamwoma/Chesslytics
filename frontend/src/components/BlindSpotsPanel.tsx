import CategoryBars from './CategoryBars.tsx'
import ErrorNotice from './ErrorNotice.tsx'
import HeatBoard from './HeatBoard.tsx'
import { useAsync } from '../hooks/useAsync.ts'
import { REGION_LABELS, themeLabel, titleCase } from '../labels.ts'
import { getBlindSpots } from '../services/patternsService.ts'
import type { BlindSpotInsight } from '../types.ts'

function sentence(item: BlindSpotInsight, total: number): string {
  const theme = item.theme ? themeLabel(item.theme).toLowerCase() : ''
  if (item.kind === 'theme_piece') {
    return `Mistakes involving ${theme} most often came from moving a ${item.piece} (${item.count} times).`
  }
  if (item.kind === 'theme_region') {
    const region = REGION_LABELS[item.region || ''] || item.region
    return `Most of your ${theme} mistakes (${item.count}) happened on ${region}.`
  }
  const share = total ? Math.round((item.count / total) * 100) : 0
  return `Moves with your ${item.piece} make up ${share}% of your mistakes.`
}

export default function BlindSpotsPanel() {
  const spots = useAsync(() => getBlindSpots(), [])
  if (spots.error) return <ErrorNotice error={spots.error} />
  if (!spots.data) return <p className="muted">Loading&hellip;</p>
  const data = spots.data
  if (!data.total) {
    return (
      <div className="notice">
        No analysed mistakes yet. Blind spots appear after you analyse a few games.
      </div>
    )
  }

  return (
    <div className="stack">
      <div className="card">
        <h2>What stands out</h2>
        {data.insights.length ? (
          <ul className="observations">
            {data.insights.map((item) => (
              <li key={`${item.kind}-${item.theme || ''}-${item.piece || ''}-${item.region || ''}`}>
                {sentence(item, data.total)}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted" style={{ marginBottom: 0 }}>
            No strong pattern yet. Patterns need at least three similar mistakes.
          </p>
        )}
        <p className="muted tactic-note">
          Based on {data.total} mistakes{data.player ? ` by ${data.player}` : ''}. Tactic labels are
          pattern-based hints, not proofs.
        </p>
      </div>

      <div className="grid grid-two">
        <div className="card">
          <h3>Tactics involved</h3>
          <CategoryBars
            rows={data.themes.map((item) => ({ key: item.theme, count: item.count }))}
            labelFor={themeLabel}
          />
        </div>
        <div className="card">
          <h3>Piece you moved</h3>
          <CategoryBars
            rows={data.pieces.map((item) => ({ key: item.piece, count: item.count }))}
            labelFor={titleCase}
          />
          <h3 style={{ marginTop: 16 }}>Side of the board</h3>
          <CategoryBars
            rows={data.regions.map((item) => ({ key: item.region, count: item.count }))}
            labelFor={(key) => titleCase(REGION_LABELS[key] || key)}
          />
        </div>
      </div>

      <div className="grid grid-two">
        <div className="card">
          <HeatBoard
            values={data.loose_squares}
            title="Where your pieces were left loose"
            caption="White's side at the bottom. Darker squares mean it happened there more often."
          />
        </div>
        <div className="card">
          <HeatBoard
            values={data.landing_squares}
            title="Where your mistaken moves landed"
            caption="The square the piece moved to when the mistake was made."
          />
        </div>
      </div>
    </div>
  )
}
