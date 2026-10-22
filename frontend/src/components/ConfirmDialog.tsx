import type { ReactNode } from 'react'
import type { Problem } from '../services/api.ts'
import ErrorNotice from './ErrorNotice.tsx'
import Modal from './Modal.tsx'

interface ConfirmDialogProps {
  title: string
  confirmLabel?: string
  danger?: boolean
  busy?: boolean
  error?: Problem
  onConfirm: () => void
  onCancel: () => void
  children?: ReactNode
}

export default function ConfirmDialog({
  title,
  confirmLabel = 'Confirm',
  danger = false,
  busy = false,
  error = null,
  onConfirm,
  onCancel,
  children,
}: ConfirmDialogProps) {
  return (
    <Modal title={title} onClose={onCancel} busy={busy}>
      <div className="modal-body">{children}</div>
      <ErrorNotice error={error} />
      <div className="modal-actions">
        <button type="button" className="button" onClick={onCancel} disabled={busy} data-autofocus>
          Cancel
        </button>
        <button
          type="button"
          className={danger ? 'button danger' : 'button primary'}
          onClick={onConfirm}
          disabled={busy}
        >
          {busy ? 'Please wait…' : confirmLabel}
        </button>
      </div>
    </Modal>
  )
}
