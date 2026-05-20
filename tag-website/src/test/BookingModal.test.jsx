/**
 * Tests for BookingModal — the modal wrapper around the /tag-it booking flow.
 *
 * Covers:
 *   1. Renders nothing when closed.
 *   2. When open: renders the welcome card (first thing BookingsNew shows).
 *   3. Close button calls onClose.
 *   4. Escape key calls onClose.
 *   5. Clicking the overlay or dialog does NOT call onClose (close is keyboard/button only).
 *   6. Body scroll is locked while open and restored on close.
 *   7. "Back to home" inside the welcome card calls onClose (not navigate).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import BookingModal from '../components/BookingModal.jsx'

// Smoke-mock the Stripe payment component pulled in by BookingsNew so the
// modal can mount in jsdom without loading Stripe.
vi.mock('../components/StripePayment', () => ({
  default: () => null,
}))

const renderModal = (props = {}) => {
  return render(
    <MemoryRouter>
      <BookingModal open onClose={vi.fn()} {...props} />
    </MemoryRouter>
  )
}

describe('BookingModal', () => {
  beforeEach(() => {
    sessionStorage.clear()
    document.body.style.overflow = ''
  })

  afterEach(() => {
    cleanup()
    document.body.style.overflow = ''
  })

  it('renders nothing when open=false', () => {
    const { container } = render(
      <MemoryRouter>
        <BookingModal open={false} onClose={vi.fn()} />
      </MemoryRouter>
    )
    expect(container.querySelector('.booking-modal-overlay')).toBeNull()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('renders the booking flow with welcome card when open', () => {
    renderModal()
    expect(screen.getByRole('dialog', { name: /book your parking/i })).toBeInTheDocument()
    expect(screen.getByText(/Booking's a breeze/i)).toBeInTheDocument()
  })

  it('calls onClose when the close button is clicked', () => {
    const onClose = vi.fn()
    renderModal({ onClose })
    fireEvent.click(screen.getByRole('button', { name: /close booking/i }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when Escape is pressed', () => {
    const onClose = vi.fn()
    renderModal({ onClose })
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('does NOT call onClose when the overlay or dialog is clicked', () => {
    const onClose = vi.fn()
    const { container } = renderModal({ onClose })

    const overlay = container.ownerDocument.querySelector('.booking-modal-overlay')
    const dialog = container.ownerDocument.querySelector('.booking-modal-dialog')

    fireEvent.click(dialog)
    expect(onClose).not.toHaveBeenCalled()

    fireEvent.click(overlay)
    expect(onClose).not.toHaveBeenCalled()
  })

  it('locks body scroll while open and restores it on unmount', () => {
    document.body.style.overflow = 'auto'
    const { unmount } = renderModal()
    expect(document.body.style.overflow).toBe('hidden')
    unmount()
    expect(document.body.style.overflow).toBe('auto')
  })

  it('hides the in-page nav when rendered inside the modal', () => {
    const { container } = renderModal()
    // The in-page <nav class="bookings-new-nav"> should NOT render in modal mode.
    expect(container.ownerDocument.querySelector('.bookings-new-nav')).toBeNull()
    expect(container.ownerDocument.querySelector('.bookings-new-footer')).toBeNull()
    // But the page wrapper should carry the modal-mode class.
    expect(container.ownerDocument.querySelector('.bookings-new-page--modal')).not.toBeNull()
  })

  it('routes the welcome card "Back to home" button through onClose', () => {
    const onClose = vi.fn()
    renderModal({ onClose })
    fireEvent.click(screen.getByRole('button', { name: /back to home/i }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
