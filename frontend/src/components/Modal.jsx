import { useEffect, useId, useRef } from 'react'
import { createPortal } from 'react-dom'

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'

export default function Modal({ title, onClose, busy = false, children }) {
  const titleId = useId()
  const dialog = useRef(null)
  const latest = useRef({ busy, onClose })
  latest.current = { busy, onClose }

  useEffect(() => {
    const node = dialog.current
    const previous = document.activeElement
    const first = node.querySelector('[data-autofocus]') || node.querySelector(FOCUSABLE)
    if (first) first.focus()

    const onKey = (event) => {
      if (event.key === 'Escape') {
        if (!latest.current.busy) {
          event.stopPropagation()
          latest.current.onClose()
        }
        return
      }
      if (event.key !== 'Tab') return
      const items = [...node.querySelectorAll(FOCUSABLE)]
      if (!items.length) return
      const head = items[0]
      const tail = items[items.length - 1]
      if (event.shiftKey && document.activeElement === head) {
        event.preventDefault()
        tail.focus()
      } else if (!event.shiftKey && document.activeElement === tail) {
        event.preventDefault()
        head.focus()
      }
    }

    document.addEventListener('keydown', onKey)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = overflow
      if (previous && previous.focus) previous.focus()
    }
  }, [])

  const backdrop = (event) => {
    if (event.target === event.currentTarget && !latest.current.busy) latest.current.onClose()
  }

  return createPortal(
    <div className="modal-backdrop" onMouseDown={backdrop}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={dialog}
      >
        <h2 id={titleId}>{title}</h2>
        {children}
      </div>
    </div>,
    document.body,
  )
}
