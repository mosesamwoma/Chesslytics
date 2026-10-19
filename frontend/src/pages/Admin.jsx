import { useCallback, useEffect, useState } from 'react'
import StatTile from '../components/StatTile.jsx'
import { useAuth } from '../auth/AuthContext.jsx'
import {
  deleteUser,
  getAudit,
  getStats,
  listUsers,
  resetUserPassword,
  unlockUser,
  updateUser,
} from '../services/adminService.js'

const PAGE_SIZE = 25

function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString()
}

export default function Admin() {
  const { user: me } = useAuth()
  const [stats, setStats] = useState(null)
  const [users, setUsers] = useState([])
  const [total, setTotal] = useState(0)
  const [events, setEvents] = useState([])
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setError(null)
    try {
      const [statPayload, userPayload, auditPayload] = await Promise.all([
        getStats(),
        listUsers({ q: search, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
        getAudit(50),
      ])
      setStats(statPayload)
      setUsers(userPayload.users)
      setTotal(userPayload.total)
      setEvents(auditPayload.events)
    } catch (err) {
      setError(err)
    }
  }, [search, page])

  useEffect(() => {
    load()
  }, [load])

  const act = async (work, success) => {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await work()
      if (success) setNotice(success)
      await load()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  const toggleActive = (row) =>
    act(
      () => updateUser(row.id, { is_active: !row.is_active }),
      `${row.username} is now ${row.is_active ? 'disabled' : 'enabled'}.`,
    )

  const toggleRole = (row) =>
    act(
      () => updateUser(row.id, { role: row.is_admin ? 'user' : 'admin' }),
      `${row.username} is now ${row.is_admin ? 'a regular user' : 'an administrator'}.`,
    )

  const unlock = (row) => act(() => unlockUser(row.id), `${row.username} was unlocked.`)

  const resetPassword = (row) => {
    const value = window.prompt(`New password for ${row.username} (at least 10 characters):`)
    if (!value) return
    act(() => resetUserPassword(row.id, value), `Password reset for ${row.username}.`)
  }

  const remove = (row) => {
    if (!window.confirm(`Permanently delete ${row.username} and all of their data?`)) return
    act(() => deleteUser(row.id), `${row.username} was deleted.`)
  }

  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1)

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Administration</h1>
          <p className="subtitle">
            Accounts and platform health. Private game data is never shown here.
          </p>
        </div>
      </div>

      {error ? <div className="notice error">{error.message}</div> : null}
      {notice ? <div className="notice good">{notice}</div> : null}

      {stats ? (
        <div className="grid grid-kpi" style={{ marginTop: 16 }}>
          <StatTile
            label="Users"
            value={stats.users}
            delta={`${stats.active_users} active · ${stats.admins} admin`}
          />
          <StatTile
            label="Signed in (24h)"
            value={stats.active_users_24h}
            delta={`${stats.new_users_7d} new this week`}
          />
          <StatTile
            label="Games"
            value={stats.games}
            delta={`${stats.games_analyzed} analyzed`}
          />
          <StatTile
            label="Analysis queue"
            value={`${stats.jobs_running} running`}
            delta={`${stats.jobs_queued} waiting`}
          />
        </div>
      ) : null}

      <div className="card" style={{ marginTop: 16 }}>
        <form
          className="row"
          onSubmit={(event) => {
            event.preventDefault()
            setPage(0)
            setSearch(query.trim())
          }}
        >
          <div className="field">
            <label htmlFor="user-search">Find a user</label>
            <input
              id="user-search"
              type="search"
              maxLength={64}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          <button type="submit" className="button">
            Search
          </button>
        </form>

        <div style={{ overflowX: 'auto', marginTop: 12 }}>
          <table className="table">
            <thead>
              <tr>
                <th>User</th>
                <th>Role</th>
                <th>Status</th>
                <th className="num">Games</th>
                <th className="num">Mistakes</th>
                <th>Last sign-in</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((row) => {
                const self = row.id === me?.id
                return (
                  <tr key={row.id}>
                    <td>
                      {row.username}
                      {self ? ' (you)' : ''}
                    </td>
                    <td>{row.is_admin ? 'admin' : 'user'}</td>
                    <td>
                      {row.is_active ? 'active' : 'disabled'}
                      {row.locked ? ' · locked' : ''}
                    </td>
                    <td className="num">{row.games}</td>
                    <td className="num">{row.mistakes}</td>
                    <td>{formatDate(row.last_login_at)}</td>
                    <td>
                      <div className="row">
                        {self ? null : (
                          <>
                            <button
                              type="button"
                              className="button"
                              disabled={busy}
                              onClick={() => toggleActive(row)}
                            >
                              {row.is_active ? 'Disable' : 'Enable'}
                            </button>
                            <button
                              type="button"
                              className="button"
                              disabled={busy}
                              onClick={() => toggleRole(row)}
                            >
                              {row.is_admin ? 'Make user' : 'Make admin'}
                            </button>
                          </>
                        )}
                        {row.locked ? (
                          <button
                            type="button"
                            className="button"
                            disabled={busy}
                            onClick={() => unlock(row)}
                          >
                            Unlock
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className="button"
                          disabled={busy}
                          onClick={() => resetPassword(row)}
                        >
                          Reset password
                        </button>
                        {self ? null : (
                          <button
                            type="button"
                            className="button danger"
                            disabled={busy}
                            onClick={() => remove(row)}
                          >
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
              {users.length === 0 ? (
                <tr>
                  <td colSpan={7} className="muted">
                    No users found.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        {total > PAGE_SIZE ? (
          <div className="row" style={{ marginTop: 12 }}>
            <button
              type="button"
              className="button"
              disabled={page === 0}
              onClick={() => setPage((value) => Math.max(0, value - 1))}
            >
              Previous
            </button>
            <span className="muted">
              Page {page + 1} of {lastPage + 1}
            </span>
            <button
              type="button"
              className="button"
              disabled={page >= lastPage}
              onClick={() => setPage((value) => Math.min(lastPage, value + 1))}
            >
              Next
            </button>
          </div>
        ) : null}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Recent activity</h2>
        <div style={{ overflowX: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>What</th>
                <th>Target</th>
                <th>Address</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id}>
                  <td>{formatDate(event.created_at)}</td>
                  <td>{event.actor || '—'}</td>
                  <td>
                    {event.action}
                    {event.detail ? ` (${event.detail})` : ''}
                  </td>
                  <td>{event.target || '—'}</td>
                  <td>{event.ip || '—'}</td>
                </tr>
              ))}
              {events.length === 0 ? (
                <tr>
                  <td colSpan={5} className="muted">
                    Nothing recorded yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
