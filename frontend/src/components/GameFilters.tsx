import { useEffect, useState } from 'react'
import { listTags } from '../services/gamesService.ts'
import type { GameFilters as Filters, TagCount } from '../types.ts'

interface GameFiltersProps {
  filters: Filters
  player: string | null
  onChange: (filters: Filters) => void
}

const SORTS: { value: string; label: string }[] = [
  { value: 'date_desc', label: 'Newest first' },
  { value: 'date_asc', label: 'Oldest first' },
  { value: 'mistakes_desc', label: 'Most mistakes' },
  { value: 'opening_asc', label: 'Opening A to Z' },
]

export default function GameFilters({ filters, player, onChange }: GameFiltersProps) {
  const [search, setSearch] = useState(filters.q || '')
  const [tags, setTags] = useState<TagCount[]>([])
  const { q } = filters

  useEffect(() => {
    let active = true
    listTags()
      .then((payload) => {
        if (active) setTags(payload.tags)
      })
      .catch(() => null)
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => {
      if (search.trim() !== (q || '')) onChange({ ...filters, q: search.trim() })
    }, 350)
    return () => clearTimeout(timer)
  }, [search, q, filters, onChange])

  const set = (key: keyof Filters, value: string) => onChange({ ...filters, [key]: value })
  const active = Boolean(
    filters.q ||
      filters.result ||
      filters.analyzed ||
      filters.opening ||
      filters.color ||
      filters.tag ||
      (filters.sort && filters.sort !== 'date_desc'),
  )

  return (
    <div className="filters" style={{ marginTop: 16 }}>
      <div className="field">
        <label htmlFor="game-search">Search</label>
        <input
          id="game-search"
          type="search"
          placeholder="player, opening or event"
          maxLength={80}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="game-result">Result</label>
        <select
          id="game-result"
          value={filters.result || ''}
          onChange={(event) => set('result', event.target.value)}
        >
          <option value="">any result</option>
          {player ? (
            <>
              <option value="won">I won</option>
              <option value="lost">I lost</option>
              <option value="drawn">Drawn</option>
            </>
          ) : (
            <>
              <option value="1-0">White won</option>
              <option value="0-1">Black won</option>
              <option value="1/2-1/2">Drawn</option>
            </>
          )}
        </select>
      </div>
      {player ? (
        <div className="field">
          <label htmlFor="game-color">I played</label>
          <select
            id="game-color"
            value={filters.color || ''}
            onChange={(event) => set('color', event.target.value)}
          >
            <option value="">either colour</option>
            <option value="white">White</option>
            <option value="black">Black</option>
          </select>
        </div>
      ) : null}
      <div className="field">
        <label htmlFor="game-analyzed">Analysis</label>
        <select
          id="game-analyzed"
          value={filters.analyzed || ''}
          onChange={(event) => set('analyzed', event.target.value)}
        >
          <option value="">analyzed or not</option>
          <option value="true">Analyzed</option>
          <option value="false">Not analyzed</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="game-opening">Opening</label>
        <input
          id="game-opening"
          type="text"
          placeholder="any opening"
          maxLength={80}
          value={filters.opening || ''}
          onChange={(event) => set('opening', event.target.value)}
        />
      </div>
      {tags.length ? (
        <div className="field">
          <label htmlFor="game-tag">Tag</label>
          <select
            id="game-tag"
            value={filters.tag || ''}
            onChange={(event) => set('tag', event.target.value)}
          >
            <option value="">any tag</option>
            {tags.map((item) => (
              <option key={item.tag} value={item.tag}>
                {item.tag} ({item.count})
              </option>
            ))}
          </select>
        </div>
      ) : null}
      <div className="field">
        <label htmlFor="game-sort">Sort</label>
        <select
          id="game-sort"
          value={filters.sort || 'date_desc'}
          onChange={(event) => set('sort', event.target.value)}
        >
          {SORTS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </div>
      {active ? (
        <button
          type="button"
          className="button"
          onClick={() => {
            setSearch('')
            onChange({})
          }}
        >
          Clear filters
        </button>
      ) : null}
    </div>
  )
}
