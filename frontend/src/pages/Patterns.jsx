import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import PatternCard from '../components/PatternCard.jsx'
import { listPatterns } from '../services/patternsService.js'
import { PATTERN_KIND_LABELS } from '../labels.js'

export default function Patterns() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [kind, setKind] = useState('all')
  const [recurringOnly, setRecurringOnly] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await listPatterns({}))
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const patterns = data?.patterns || []

  const filtered = useMemo(() => {
    let rows = patterns
    if (kind !== 'all') rows = rows.filter((row) => row.kind === kind)
    if (recurringOnly) rows = rows.filter((row) => row.recurring)
    return rows
  }, [patterns, kind, recurringOnly])

  const grouped = useMemo(() => {
    const groups = new Map()
    filtered.forEach((row) => {
      if (!groups.has(row.kind)) groups.set(row.kind, [])
      groups.get(row.kind).push(row)
    })
    return [...groups.entries()]
  }, [filtered])

  const kinds = [...new Set(patterns.map((row) => row.kind))]

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Recurring patterns</h1>
          <p className="subtitle">
            A pattern is only worth acting on when it repeats across independent games. Everything
            found is listed; the ones that repeat are marked.
          </p>
        </div>
        <Link className="button" to="/dna">
          Chess DNA
        </Link>
      </div>

      {error ? (
        <div className="notice error">
          {error.message} <button type="button" className="button" onClick={load}>Retry</button>
        </div>
      ) : null}

      {!error && !loading && !patterns.length ? (
        <div className="notice">
          No profile yet. Import a PGN and run an analysis on the <Link to="/games">Games</Link>{' '}
          page first.
        </div>
      ) : null}

      {patterns.length ? (
        <>
          <div className="filters">
            <div className="field">
              <label htmlFor="kind">Pattern kind</label>
              <select id="kind" value={kind} onChange={(event) => setKind(event.target.value)}>
                <option value="all">all kinds</option>
                {kinds.map((value) => (
                  <option key={value} value={value}>
                    {PATTERN_KIND_LABELS[value] || value}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="recurring">Repetition</label>
              <select
                id="recurring"
                value={recurringOnly ? 'recurring' : 'all'}
                onChange={(event) => setRecurringOnly(event.target.value === 'recurring')}
              >
                <option value="all">show everything</option>
                <option value="recurring">only recurring</option>
              </select>
            </div>
            <span className="muted">
              {filtered.length} of {patterns.length} patterns shown
            </span>
          </div>

          <div className={loading ? 'loading-dim' : undefined}>
            {grouped.map(([groupKind, rows]) => (
              <div key={groupKind} style={{ marginBottom: 20 }}>
                <h2 style={{ marginBottom: 8 }}>
                  {PATTERN_KIND_LABELS[groupKind] || groupKind}
                </h2>
                <div className="grid grid-two">
                  {rows.map((row) => (
                    <PatternCard key={`${row.kind}-${row.key}`} pattern={row} />
                  ))}
                </div>
              </div>
            ))}
            {!filtered.length ? <p className="muted">No pattern matches these filters.</p> : null}
          </div>
        </>
      ) : null}
    </div>
  )
}
