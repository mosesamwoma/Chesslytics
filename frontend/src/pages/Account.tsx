import { useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { useAuth } from '../auth/AuthContext.tsx'
import ErrorNotice from '../components/ErrorNotice.tsx'
import RecoveryCode from '../components/RecoveryCode.tsx'
import Modal from '../components/Modal.tsx'
import { useRetryAfter } from '../hooks/useRetryAfter.ts'
import {
  backupUrl,
  removeEmail,
  restoreBackup,
  resendVerification,
  newRecoveryCode,
  setDigest,
  setEmail,
} from '../services/accountService.ts'
import { exportUrl } from '../services/analysisService.ts'
import { toProblem } from '../services/api.ts'
import type { Problem } from '../services/api.ts'
import { changePassword, deleteAccount } from '../services/authService.ts'

interface DeleteDialogProps {
  busy: boolean
  error: Problem
  onConfirm: (password: string) => void
  onCancel: () => void
}

interface EmailDialogProps {
  title: string
  description: string
  confirmLabel: string
  busy: boolean
  error: Problem
  onSubmit: (address: string, password: string) => void
  onCancel: () => void
  withAddress?: boolean
}

type DialogState = { type: 'delete' | 'email' | 'remove-email' | 'recovery' } | null

function DeleteDialog({ busy, error, onConfirm, onCancel }: DeleteDialogProps) {
  const [password, setPassword] = useState('')

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    onConfirm(password)
  }

  return (
    <Modal title="Delete your account?" onClose={onCancel} busy={busy}>
      <form onSubmit={submit}>
        <p>
          This permanently removes your account, games, analysis and training progress. Download
          a backup first if you may want it later.
        </p>
        <div className="field">
          <label htmlFor="delete-password">Confirm with your password</label>
          <input
            id="delete-password"
            type="password"
            autoComplete="current-password"
            required
            data-autofocus
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        <ErrorNotice error={error} />
        <div className="modal-actions">
          <button type="button" className="button" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="button danger" disabled={busy}>
            {busy ? 'Please wait…' : 'Delete my account'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function EmailDialog({
  title,
  description,
  confirmLabel,
  busy,
  error,
  onSubmit,
  onCancel,
  withAddress = false,
}: EmailDialogProps) {
  const [address, setAddress] = useState('')
  const [password, setPassword] = useState('')

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    onSubmit(address.trim(), password)
  }

  return (
    <Modal title={title} onClose={onCancel} busy={busy}>
      <form onSubmit={submit}>
        <p className="muted">{description}</p>
        {withAddress ? (
          <div className="field">
            <label htmlFor="email-address">Email address</label>
            <input
              id="email-address"
              type="email"
              autoComplete="email"
              required
              maxLength={254}
              data-autofocus
              value={address}
              onChange={(event) => setAddress(event.target.value)}
            />
          </div>
        ) : null}
        <div className="field">
          <label htmlFor="email-password">Your password</label>
          <input
            id="email-password"
            type="password"
            autoComplete="current-password"
            required
            data-autofocus={withAddress ? undefined : true}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        <ErrorNotice error={error} />
        <div className="modal-actions">
          <button type="button" className="button" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="button primary" disabled={busy}>
            {busy ? 'Please wait…' : confirmLabel}
          </button>
        </div>
      </form>
    </Modal>
  )
}

export default function Account() {
  const { user, info, endSession, setUser } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null)
  const [passwordError, setPasswordError] = useState<Problem>(null)
  const [busy, setBusy] = useState(false)
  const [dialog, setDialog] = useState<DialogState>(null)
  const [dialogError, setDialogError] = useState<Problem>(null)
  const [freshCode, setFreshCode] = useState<string | null>(null)
  const [emailMessage, setEmailMessage] = useState<string | null>(null)
  const [emailError, setEmailError] = useState<Problem>(null)
  const [restoreMessage, setRestoreMessage] = useState<string | null>(null)
  const [restoreError, setRestoreError] = useState<Problem>(null)
  const [restoring, setRestoring] = useState(false)
  const fileInput = useRef<HTMLInputElement | null>(null)
  const passwordGate = useRetryAfter(passwordError)
  const restoreGate = useRetryAfter(restoreError)

  const closeDialog = () => {
    setDialog(null)
    setDialogError(null)
  }

  const submitPassword = async (event: FormEvent<HTMLFormElement>) => {
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
      setPasswordError(toProblem(err))
    } finally {
      setBusy(false)
    }
  }

  const confirmDelete = async (password: string) => {
    setBusy(true)
    setDialogError(null)
    try {
      await deleteAccount(password)
      endSession()
    } catch (err) {
      setDialogError(toProblem(err))
      setBusy(false)
    }
  }

  const saveEmail = async (address: string, password: string) => {
    setBusy(true)
    setDialogError(null)
    try {
      const result = await setEmail(address, password)
      setUser(result.user)
      setDialog(null)
      setEmailMessage(`We sent a confirmation link to ${result.user.email}. It is valid for 24 hours.`)
    } catch (err) {
      setDialogError(toProblem(err))
    } finally {
      setBusy(false)
    }
  }

  const dropEmail = async (_address: string, password: string) => {
    setBusy(true)
    setDialogError(null)
    try {
      const result = await removeEmail(password)
      setUser(result.user)
      setDialog(null)
      setEmailMessage('Your email address was removed.')
    } catch (err) {
      setDialogError(toProblem(err))
    } finally {
      setBusy(false)
    }
  }

  const makeRecoveryCode = async (_address: string, password: string) => {
    setBusy(true)
    setDialogError(null)
    try {
      const result = await newRecoveryCode(password)
      if (result.user) setUser(result.user)
      setDialog(null)
      setFreshCode(result.recovery_code)
    } catch (err) {
      setDialogError(toProblem(err))
    } finally {
      setBusy(false)
    }
  }

  const toggleDigest = async (enabled: boolean) => {
    setBusy(true)
    setEmailError(null)
    setEmailMessage(null)
    try {
      const result = await setDigest(enabled)
      setUser(result.user)
      setEmailMessage(
        enabled
          ? 'The weekly digest is on. Your first one arrives within a day.'
          : 'The weekly digest is off.',
      )
    } catch (err) {
      setEmailError(toProblem(err))
    } finally {
      setBusy(false)
    }
  }

  const resend = async () => {
    setBusy(true)
    setEmailError(null)
    setEmailMessage(null)
    try {
      await resendVerification()
      setEmailMessage(`We sent a new confirmation link to ${user?.email ?? 'your address'}.`)
    } catch (err) {
      setEmailError(toProblem(err))
    } finally {
      setBusy(false)
    }
  }

  const restore = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files && event.target.files[0]
    event.target.value = ''
    if (!file) return
    setRestoring(true)
    setRestoreError(null)
    setRestoreMessage(null)
    try {
      const result = await restoreBackup(file)
      const parts = [
        `${result.games_restored} ${result.games_restored === 1 ? 'game' : 'games'} restored`,
        `${result.mistakes_restored} mistakes`,
        `${result.attempts_restored} puzzle attempts`,
      ]
      if (result.games_already_present) parts.push(`${result.games_already_present} already present`)
      if (result.games_unreadable) parts.push(`${result.games_unreadable} unreadable`)
      setRestoreMessage(
        `${parts.join(' · ')}. Run an analysis on the Games page to rebuild the move-by-move view.`,
      )
    } catch (err) {
      setRestoreError(toProblem(err))
    } finally {
      setRestoring(false)
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
          <button type="submit" className="button primary" disabled={busy || passwordGate.blocked}>
            Change password
          </button>
        </div>
        <ErrorNotice error={passwordError} style={{ marginTop: 12 }} />
        {passwordMessage ? (
          <div className="notice good" style={{ marginTop: 12 }}>
            {passwordMessage}
          </div>
        ) : null}
      </form>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Recovery code</h2>
        <p className="subtitle">
          {user?.has_recovery_code
            ? 'You have a recovery code. If you forget your password, enter it on the reset page to set a new one yourself. Creating a new code replaces the old one.'
            : 'You do not have a recovery code yet. Create one so you can reset a forgotten password without email or an administrator.'}
        </p>
        <button
          type="button"
          className="button"
          disabled={busy}
          onClick={() => {
            setDialogError(null)
            setDialog({ type: 'recovery' })
          }}
        >
          {user?.has_recovery_code ? 'Create a new recovery code' : 'Create a recovery code'}
        </button>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Email</h2>
        {info.email_enabled ? (
          <>
            <p className="subtitle">
              {user?.email ? (
                <>
                  <strong>{user.email}</strong>{' '}
                  {user.email_verified ? '(confirmed)' : '(waiting for confirmation)'}.
                </>
              ) : (
                'No email address on this account.'
              )}{' '}
              A confirmed address lets you reset a forgotten password by email.
            </p>
            <div className="row">
              <button
                type="button"
                className="button"
                disabled={busy}
                onClick={() => setDialog({ type: 'email' })}
              >
                {user?.email ? 'Change address' : 'Add email address'}
              </button>
              {user?.email && !user.email_verified ? (
                <button type="button" className="button" disabled={busy} onClick={resend}>
                  Resend confirmation
                </button>
              ) : null}
              {user?.email ? (
                <button
                  type="button"
                  className="button"
                  disabled={busy}
                  onClick={() => setDialog({ type: 'remove-email' })}
                >
                  Remove address
                </button>
              ) : null}
            </div>
            <label className="row" style={{ marginTop: 12 }}>
              <input
                type="checkbox"
                checked={Boolean(user?.digest_enabled)}
                disabled={busy || !user?.email_verified}
                onChange={(event) => toggleDigest(event.target.checked)}
              />
              <span>
                Email me a weekly digest of my progress and puzzles due
                {user?.email_verified ? '' : ' (confirm your address first)'}
              </span>
            </label>
          </>
        ) : (
          <p className="subtitle">
            Email is not set up on this server. If you forget your password, ask the
            administrator for a reset link.
          </p>
        )}
        <ErrorNotice error={emailError} style={{ marginTop: 12 }} />
        {emailMessage ? (
          <div className="notice good" style={{ marginTop: 12 }}>
            {emailMessage}
          </div>
        ) : null}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Backup and restore</h2>
        <p className="subtitle">
          A backup holds your games, every mistake found, your puzzle attempts and your latest
          profile. Restoring adds games that are not already in your library; it never overwrites
          what you have.
        </p>
        <div className="row">
          <a className="button" href={backupUrl()}>
            Download backup (JSON)
          </a>
          <button
            type="button"
            className="button"
            disabled={restoring || restoreGate.blocked}
            onClick={() => fileInput.current && fileInput.current.click()}
          >
            {restoring ? 'Restoring…' : 'Restore from backup'}
          </button>
          <input
            ref={fileInput}
            type="file"
            accept=".json,application/json"
            hidden
            aria-label="Backup file"
            onChange={restore}
          />
        </div>
        <ErrorNotice error={restoreError} style={{ marginTop: 12 }} />
        {restoreMessage ? (
          <div className="notice good" style={{ marginTop: 12 }}>
            {restoreMessage}
          </div>
        ) : null}
        <h3 style={{ marginTop: 20 }}>Mistakes only</h3>
        <div className="row">
          <a className="button" href={exportUrl('csv')}>
            Download CSV
          </a>
          <a className="button" href={exportUrl('json')}>
            Download JSON
          </a>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Delete account</h2>
        <p className="subtitle">
          This permanently removes your account, games, analysis and training progress.
        </p>
        <div className="row">
          <button
            type="button"
            className="button danger"
            disabled={busy}
            onClick={() => setDialog({ type: 'delete' })}
          >
            Delete my account…
          </button>
        </div>
      </div>

      {dialog && dialog.type === 'recovery' ? (
        <EmailDialog
          title="Create a recovery code"
          description="Enter your password to create a new recovery code. Your current code, if you have one, stops working."
          confirmLabel="Create code"
          busy={busy}
          error={dialogError}
          onSubmit={makeRecoveryCode}
          onCancel={closeDialog}
        />
      ) : null}
      {freshCode ? (
        <div className="modal-backdrop">
          <RecoveryCode
            code={freshCode}
            heading="Your new recovery code"
            intro="Save it now. It is shown only once, and your previous code no longer works."
            continueLabel="Done"
            onDone={() => setFreshCode(null)}
          />
        </div>
      ) : null}
      {dialog && dialog.type === 'delete' ? (
        <DeleteDialog
          busy={busy}
          error={dialogError}
          onConfirm={confirmDelete}
          onCancel={closeDialog}
        />
      ) : null}
      {dialog && dialog.type === 'email' ? (
        <EmailDialog
          title={user?.email ? 'Change email address' : 'Add an email address'}
          description="We will send a confirmation link to the new address. The old address stops working for password resets until you confirm the new one."
          confirmLabel="Send confirmation"
          withAddress
          busy={busy}
          error={dialogError}
          onSubmit={saveEmail}
          onCancel={closeDialog}
        />
      ) : null}
      {dialog && dialog.type === 'remove-email' ? (
        <EmailDialog
          title="Remove your email address?"
          description="You will not be able to reset a forgotten password by email until you add one again."
          confirmLabel="Remove address"
          busy={busy}
          error={dialogError}
          onSubmit={dropEmail}
          onCancel={closeDialog}
        />
      ) : null}
    </div>
  )
}
