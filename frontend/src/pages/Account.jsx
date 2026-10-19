import { useState } from 'react'
import { useAuth } from '../auth/AuthContext.jsx'
import { changePassword, deleteAccount } from '../services/authService.js'
import { exportUrl } from '../services/analysisService.js'

export default function Account() {
  const { user, info, endSession } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [passwordMessage, setPasswordMessage] = useState(null)
  const [passwordError, setPasswordError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState('')
  const [deleteError, setDeleteError] = useState(null)

  const submitPassword = async (event) => {
    event.preventDefault()
    setPasswordMessage(null)
    setPasswordError(null)
    if (next !== repeat) {
      setPasswordError('The new passwords do not match.')
      return
    }
    setBusy(true)
    try {
      await changePassword(current, next)
      setPasswordMessage('Password changed. Your other sessions were signed out.')
      setCurrent('')
      setNext('')
      setRepeat('')
    } catch (err) {
      setPasswordError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const submitDelete = async (event) => {
    event.preventDefault()
    setDeleteError(null)
    if (!window.confirm('Delete your account and all of your games, mistakes and progress?')) return
    setBusy(true)
    try {
      await deleteAccount(confirmDelete)
      endSession()
    } catch (err) {
      setDeleteError(err.message)
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Account</h1>
          <p className="subtitle">
            Signed in as <strong>{user?.username}</strong>
            {user?.is_admin ? ' (administrator)' : ''}.
          </p>
        </div>
      </div>

      <form className="card" onSubmit={submitPassword}>
        <h2>Change password</h2>
        <div className="filters">
          <div className="field">
            <label htmlFor="current-password">Current password</label>
            <input
              id="current-password"
              type="password"
              autoComplete="current-password"
              required
              value={current}
              onChange={(event) => setCurrent(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="new-password">New password</label>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={info.min_password_length}
              maxLength={128}
              value={next}
              onChange={(event) => setNext(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="repeat-password">Repeat new password</label>
            <input
              id="repeat-password"
              type="password"
              autoComplete="new-password"
              required
              maxLength={128}
              value={repeat}
              onChange={(event) => setRepeat(event.target.value)}
            />
          </div>
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <button type="submit" className="button primary" disabled={busy}>
            Change password
          </button>
        </div>
        {passwordError ? (
          <div className="notice error" style={{ marginTop: 12 }}>
            {passwordError}
          </div>
        ) : null}
        {passwordMessage ? (
          <div className="notice good" style={{ marginTop: 12 }}>
            {passwordMessage}
          </div>
        ) : null}
      </form>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Your data</h2>
        <p className="subtitle">Download every mistake that was found in your games.</p>
        <div className="row">
          <a className="button" href={exportUrl('csv')}>
            Download CSV
          </a>
          <a className="button" href={exportUrl('json')}>
            Download JSON
          </a>
        </div>
      </div>

      <form className="card" style={{ marginTop: 16 }} onSubmit={submitDelete}>
        <h2>Delete account</h2>
        <p className="subtitle">
          This permanently removes your account, games, analysis and training progress.
        </p>
        <div className="filters">
          <div className="field">
            <label htmlFor="delete-password">Confirm with your password</label>
            <input
              id="delete-password"
              type="password"
              autoComplete="current-password"
              required
              value={confirmDelete}
              onChange={(event) => setConfirmDelete(event.target.value)}
            />
          </div>
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <button type="submit" className="button danger" disabled={busy}>
            Delete my account
          </button>
        </div>
        {deleteError ? (
          <div className="notice error" style={{ marginTop: 12 }}>
            {deleteError}
          </div>
        ) : null}
      </form>
    </div>
  )
}
