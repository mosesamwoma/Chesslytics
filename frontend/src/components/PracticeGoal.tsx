import { useState } from 'react'
import { toProblem } from '../services/api.ts'
import type { Problem } from '../services/api.ts'
import { setGoal } from '../services/trainingService.ts'
import type { Activity } from '../types.ts'
import ErrorNotice from './ErrorNotice.tsx'

interface PracticeGoalProps {
  activity: Activity
  onChange: (activity: Activity) => void
}

function weekday(date: string): string {
  const day = new Date(`${date}T00:00:00Z`)
  return day.toLocaleDateString(undefined, { weekday: 'short', timeZone: 'UTC' })
}

export default function PracticeGoal({ activity, onChange }: PracticeGoalProps) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(activity.daily_goal)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Problem>(null)
  const percent = Math.min(100, Math.round((activity.today / activity.daily_goal) * 100))

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      onChange(await setGoal(value))
      setEditing(false)
    } catch (err) {
      setError(toProblem(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div>
          <strong>
            {activity.goal_met
              ? 'Daily goal reached'
              : `${activity.today} of ${activity.daily_goal} puzzles today`}
          </strong>
          <div className="secondary" style={{ fontSize: 13 }}>
            Streak {activity.current_streak} {activity.current_streak === 1 ? 'day' : 'days'}
            {' · '}best {activity.longest_streak}
            {' · '}days are counted in UTC
          </div>
        </div>
        {editing ? (
          <div className="row">
            <input
              type="number"
              aria-label="Daily puzzle goal"
              min={1}
              max={100}
              value={value}
              onChange={(event) =>
                setValue(Math.max(1, Math.min(100, Number(event.target.value) || 1)))
              }
              style={{ width: 80 }}
            />
            <button type="button" className="button primary" onClick={save} disabled={busy}>
              Save
            </button>
            <button type="button" className="button" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        ) : (
          <button
            type="button"
            className="button"
            onClick={() => {
              setValue(activity.daily_goal)
              setEditing(true)
            }}
          >
            Change goal
          </button>
        )}
      </div>
      <div
        className="bar-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        style={{ marginTop: 10 }}
      >
        <div className="bar-fill" style={{ width: `${percent}%` }} />
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        {activity.week.map((day) => (
          <span
            key={day.date}
            className={day.met ? 'badge' : 'muted'}
            title={`${day.date}: ${day.count} ${day.count === 1 ? 'attempt' : 'attempts'}`}
            style={{ fontSize: 12 }}
          >
            {weekday(day.date)} {day.count}
          </span>
        ))}
      </div>
      <ErrorNotice error={error} style={{ marginTop: 12 }} />
    </div>
  )
}
