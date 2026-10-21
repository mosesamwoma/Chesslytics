import { useCallback, useEffect, useRef, useState } from 'react'
import ErrorNotice from '../components/ErrorNotice.jsx'
import Modal from '../components/Modal.jsx'
import StatTile from '../components/StatTile.jsx'
import { useAuth } from '../auth/AuthContext.jsx'
import {
  createResetLink,
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

function formatLifetime(seconds) {
  if (seconds >= 3600) return `${Math.round(seconds / 3600)} hour(s)`
  return `${Math.max(1, Math.round(seconds / 60))} minute(s)`
}

function PasswordDialog({ row, minLength, busy, error, onSubmit, onCancel }) {
  const [password, setPassword] = useState('')
  const [repeat, setRepeat] = useState('')
  const [mismatch, setMismatch] = useState(false)

  const submit = (event) => {
    event.preventDefault()
    if (password !== repeat) {
      setMismatch(true)
      return
    }
    setMismatch(false)
    onSubmit(password)
  }

  return (
    <Modal title={`Set a new password for ${row.username}`} onClose={onCancel} busy={busy}>
      <form onSubmit={submit}>
        <p className="muted">
          They will be signed out everywhere. Share the new password privately, or use a reset
          link instead so you never see it.
        </p>
        <div className="field">
          <label htmlFor="admin-new-password">New password</label>
          <input
            id="admin-new-password"
            type="password"
            autoComplete="new-password"
            required
            minLength={minLength}
            maxLength={128}
            data-autofocus
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="admin-repeat-password">Repeat new password</label>
          <input
            id="admin-repeat-password"
            type="password"
            autoComplete="new-password"
            required
            maxLength={128}
            value={repeat}
            onChange={(event) => setRepeat(event.target.value)}
          />
          <span className="muted">At least {minLength} characters.</span>
        </div>
        {mismatch ? <div className="notice error">The two passwords do not match.</div> : null}
        <ErrorNotice error={error} />
        <div className="modal-actions">
          <button type="button" className="button" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="button primary" disabled={busy}>
            {busy ? 'Please wait…' : 'Set password'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function LinkDialog({ row, link, onClose }) {
  const field = useRef(null)
  const [copied, setCopied] = useState(false)
  const url = `${window.location.origin}${link.path}`

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
    } catch {
      if (field.current) field.current.select()
    }
  }

  return (
    <Modal title={`Reset link for ${row.username}`} onClose={onClose}>
      <p className="muted">
        Send this link to {row.username} privately. It works once and expires in{' '}
        {formatLifetime(link.expires_in)}. Anyone who opens it can choose a new password for the
        account, so treat it like a password.
      </p>
      <div className="field">
        <label htmlFor="reset-link">One-time link</label>
        <input
          id="reset-link"
          ref={field}
          type="text"
          readOnly
          value={url}
          data-autofocus
          onFocus={(event) => event.target.select()}
        />
      </div>
      <div className="modal-actions">
        <button type="button" className="button" onClick={copy}>
          {copied ? 'Copied' : 'Copy link'}
        </button>
        <button type="button" className="button primary" onClick={onClose}>
          Done
        </button>
      </div>
    </Modal>
  )
}

function DeleteDialog({ row, busy, error, onConfirm, onCancel }) {
  const [typed, setTyped] = useState('')
  const matches = typed.trim().toLowerCase() === row.username.toLowerCase()

  return (
    <Modal title={`Delete ${row.username}?`} onClose={onCancel} busy={busy}>
      <p>
        This permanently removes <strong>{row.username}</strong> together with their games,
        analysis, puzzles and progress. It cannot be undone.
      </p>
      <div className="field">
        <label htmlFor="delete-confirm">Type the username to confirm</label>
        <input
          id="delete-confirm"
          type="text"
          autoComplete="off"
          data-autofocus
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
        />
      </div>
      <ErrorNotice error={error} />
      <div className="modal-actions">
        <button type="button" className="button" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
        <button
          type="button"
          className="button danger"
          disabled={busy || !matches}
          onClick={onConfirm}
        >
          {busy ? 'Please wait…' : 'Delete user'}
        </button>
      </div>
    </Modal>
  )
}

export default function Admin() {
  const { user: me, info } = useAuth()
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
  const [dialog, setDialog] = useState(null)
  const [dialogError, setDialogError] = useState(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const [statPayload, userPayload, auditPayload] = await Promise.all([
        getStats(),
        listUsers({ q: search, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
        getAudit(50),
      ])
      const last = Math.max(0, Math.ceil(userPayload.total / PAGE_SIZE) - 1)
      if (page > last) {
        setPage(last)
        return
      }
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

  const closeDialog = () => {
    setDialog(null)
    setDialogError(null)
  }

  const dialogWork = async (work, success) => {
    setBusy(true)
    setDialogError(null)
    try {
      await work()
      setDialog(null)
      setNotice(success)
      await load()
    } catch (err) {
      setDialogError(err)
    } finally {
      setBusy(false)
    }
  }

  const makeLink = async (row) => {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const link = await createResetLink(row.id)
      setDialog({ type: 'link', row, link })
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
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

      <ErrorNotice error={error} />
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
                        {self ? null : (
                          <>
                            <button
                              type="button"
                              className="button"
                              disabled={busy}
                              onClick={() => makeLink(row)}
                            >
                              Reset link
                            </button>
                            <button
                              type="button"
                              className="button"
                              disabled={busy}
                              onClick={() => setDialog({ type: 'password', row })}
                            >
                              Set password
                            </button>
                            <button
                              type="button"
                              className="button danger"
                              disabled={busy}
                              onClick={() => setDialog({ type: 'delete', row })}
                            >
                              Delete
                            </button>
                          </>
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

      {dialog && dialog.type === 'password' ? (
        <PasswordDialog
          row={dialog.row}
          minLength={info.min_password_length}
          busy={busy}
          error={dialogError}
          onCancel={closeDialog}
          onSubmit={(value) =>
            dialogWork(
              () => resetUserPassword(dialog.row.id, value),
              `Password reset for ${dialog.row.username}.`,
            )
          }
        />
      ) : null}
      {dialog && dialog.type === 'link' ? (
        <LinkDialog row={dialog.row} link={dialog.link} onClose={closeDialog} />
      ) : null}
      {dialog && dialog.type === 'delete' ? (
        <DeleteDialog
          row={dialog.row}
          busy={busy}
          error={dialogError}
          onCancel={closeDialog}
          onConfirm={() =>
            dialogWork(() => deleteUser(dialog.row.id), `${dialog.row.username} was deleted.`)
          }
        />
      ) : null}
    </div>
  )
}
