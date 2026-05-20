import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import BookingsNew from '../BookingsNew.jsx'
import './BookingModal.css'

const FOCUSABLE = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

function BookingModal({ open, onClose }) {
  const dialogRef = useRef(null)
  const previouslyFocused = useRef(null)

  useEffect(() => {
    if (!open) return

    previouslyFocused.current = document.activeElement
    const { body } = document
    const previousOverflow = body.style.overflow
    body.style.overflow = 'hidden'

    const dialog = dialogRef.current
    if (dialog) {
      const first = dialog.querySelector(FOCUSABLE)
      if (first) first.focus()
      else dialog.focus()
    }

    const onKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key === 'Tab' && dialog) {
        const focusables = Array.from(dialog.querySelectorAll(FOCUSABLE)).filter(el => !el.hasAttribute('aria-hidden'))
        if (focusables.length === 0) return
        const firstEl = focusables[0]
        const lastEl = focusables[focusables.length - 1]
        if (e.shiftKey && document.activeElement === firstEl) {
          e.preventDefault()
          lastEl.focus()
        } else if (!e.shiftKey && document.activeElement === lastEl) {
          e.preventDefault()
          firstEl.focus()
        }
      }
    }

    document.addEventListener('keydown', onKeyDown)

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      body.style.overflow = previousOverflow
      const prev = previouslyFocused.current
      if (prev && typeof prev.focus === 'function') prev.focus()
    }
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div className="booking-modal-overlay" role="presentation">
      <div
        ref={dialogRef}
        className="booking-modal-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Book your parking"
        tabIndex={-1}
      >
        <button
          type="button"
          className="booking-modal-close"
          aria-label="Close booking"
          onClick={onClose}
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
        <div className="booking-modal-body">
          <BookingsNew isModal onClose={onClose} />
        </div>
      </div>
    </div>,
    document.body
  )
}

export default BookingModal
