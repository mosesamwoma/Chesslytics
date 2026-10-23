import { useState } from 'react'
import type { KeyboardEvent } from 'react'
import { toProblem } from '../services/api.ts'
import type { Problem } from '../services/api.ts'
import { updateGame } from '../services/gamesService.ts'
import type { Game } from '../types.ts'
import ErrorNotice from './ErrorNotice.tsx'

interface GameNotesProps {
  gameId: number
  notes: string | null
  tags: string[]
  onSaved: (game: Game) => void
}

const MAX_TAGS = 10

export default function GameNotes({ gameId, notes, tags, onSaved }: GameNotesProps) {
  const [text, setText] = useState(notes || '')
  const [list, setList] = useState<string[]>(tags)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Problem>(null)
  const [saved, setSaved] = useState(false)

  const dirty = text.trim() !== (notes || '') || list.join('|') !== tags.join('|')

  const addTag = () => {
    const tag = draft.trim().toLowerCase().replace(/\s+/g, ' ')
    if (!tag || list.includes(tag) || list.length >= MAX_TAGS) {
      setDraft('')
      return
    }
    setList([...list, tag])
    setDraft('')
    setSaved(false)
  }

  const onKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault()
      addTag()
    }
  }

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      const game = await updateGame(gameId, { notes: text.trim() || null, tags: list })
      onSaved(game)
      setSaved(true)
    } catch (err) {
      setError(toProblem(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h2>Notes and tags</h2>
      <div className="field">
        <label htmlFor="game-notes">Notes</label>
        <textarea
          id="game-notes"
          rows={3}
          maxLength={2000}
          value={text}
          onChange={(event) => {
            setText(event.target.value)
            setSaved(false)
          }}
        />
      </div>
      <div className="field" style={{ marginTop: 8 }}>
        <label htmlFor="game-tag-input">Tags</label>
        <div className="row">
          {list.map((tag) => (
            <span className="badge" key={tag}>
              {tag}{' '}
              <button
                type="button"
                className="link-button"
                aria-label={`Remove tag ${tag}`}
                onClick={() => {
                  setList(list.filter((item) => item !== tag))
                  setSaved(false)
                }}
              >
                &times;
              </button>
            </span>
          ))}
          <input
            id="game-tag-input"
            type="text"
            placeholder={list.length >= MAX_TAGS ? 'tag limit reached' : 'add a tag, press Enter'}
            maxLength={24}
            disabled={list.length >= MAX_TAGS}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={onKey}
            onBlur={addTag}
          />
        </div>
      </div>
      <ErrorNotice error={error} style={{ marginTop: 12 }} />
      <div className="row" style={{ marginTop: 12 }}>
        <button type="button" className="button primary" onClick={save} disabled={busy || !dirty}>
          {busy ? 'Saving…' : 'Save notes and tags'}
        </button>
        {saved && !dirty ? <span className="muted">Saved.</span> : null}
      </div>
    </div>
  )
}
