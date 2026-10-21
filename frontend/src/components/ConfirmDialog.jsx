import ErrorNotice from './ErrorNotice.jsx'
import Modal from './Modal.jsx'

export default function ConfirmDialog({
  title,
  confirmLabel = 'Confirm',
  danger = false,
  busy = false,
  error = null,
  onConfirm,
  onCancel,
  children,
}) {
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
