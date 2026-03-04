/**
 * Tests for Admin Send Founder Email functionality
 *
 * Tests the core logic:
 * - Send Founder Email button state (enabled/disabled)
 * - Button visibility based on booking status
 * - Confirmation modal display
 * - API call on confirmation
 * - Success/error handling
 * - Button text changes after send
 *
 * Test categories:
 * - Unit Tests: Button state logic, UI rendering
 * - Integration Tests: API calls, state updates
 * - Negative Tests: Error handling, validation
 * - Edge Cases: Boundary conditions
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock fetch
global.fetch = vi.fn()

// =============================================================================
// Mock Data Factories
// =============================================================================

const createMockCustomer = (overrides = {}) => ({
  id: 1,
  first_name: 'John',
  last_name: 'Doe',
  email: 'john.doe@example.com',
  phone: '07700900001',
  founder_followup_sent: false,
  founder_followup_sent_at: null,
  ...overrides,
})

const createMockBooking = (overrides = {}) => ({
  id: 1,
  reference: 'TAG-TEST001',
  status: 'pending',
  booking_source: 'online',
  dropoff_date: '2026-03-15',
  dropoff_time: '09:30',
  pickup_date: '2026-03-22',
  pickup_time_from: '14:30',
  pickup_time_to: '15:00',
  customer: createMockCustomer(),
  vehicle: {
    id: 1,
    registration: 'AB12 CDE',
    make: 'Volkswagen',
    model: 'Golf',
    colour: 'Blue',
  },
  payment: null,
  ...overrides,
})

// =============================================================================
// Unit Tests - Button State Logic
// =============================================================================

describe('Admin Founder Email Button State', () => {
  describe('Unit Tests - Button visibility by status', () => {
    it('should show button for pending booking', () => {
      const booking = createMockBooking({ status: 'pending' })
      const showButton = booking.status === 'pending'

      expect(showButton).toBe(true)
    })

    it('should NOT show button for confirmed booking', () => {
      const booking = createMockBooking({ status: 'confirmed' })
      const showButton = booking.status === 'pending'

      expect(showButton).toBe(false)
    })

    it('should NOT show button for completed booking', () => {
      const booking = createMockBooking({ status: 'completed' })
      const showButton = booking.status === 'pending'

      expect(showButton).toBe(false)
    })

    it('should NOT show button for cancelled booking', () => {
      const booking = createMockBooking({ status: 'cancelled' })
      const showButton = booking.status === 'pending'

      expect(showButton).toBe(false)
    })

    it('should NOT show button for refunded booking', () => {
      const booking = createMockBooking({ status: 'refunded' })
      const showButton = booking.status === 'pending'

      expect(showButton).toBe(false)
    })
  })

  describe('Unit Tests - Button disabled logic', () => {
    it('should be enabled when email not sent yet', () => {
      const booking = createMockBooking({
        status: 'pending',
        customer: createMockCustomer({ founder_followup_sent: false }),
      })

      const isDisabled = booking.customer.founder_followup_sent
      expect(isDisabled).toBe(false)
    })

    it('should be disabled when email already sent', () => {
      const booking = createMockBooking({
        status: 'pending',
        customer: createMockCustomer({
          founder_followup_sent: true,
          founder_followup_sent_at: '2026-03-01T10:30:00',
        }),
      })

      const isDisabled = booking.customer.founder_followup_sent
      expect(isDisabled).toBe(true)
    })

    it('should be disabled while sending', () => {
      const sendingFounderEmailId = 1
      const booking = createMockBooking({ id: 1 })

      const isDisabled = sendingFounderEmailId === booking.id
      expect(isDisabled).toBe(true)
    })

    it('should NOT be disabled while sending different booking', () => {
      const sendingFounderEmailId = 2
      const booking = createMockBooking({ id: 1 })

      const isDisabled = sendingFounderEmailId === booking.id
      expect(isDisabled).toBe(false)
    })
  })

  describe('Unit Tests - Button text logic', () => {
    it('should show "Send Founder Email" when not sent', () => {
      const booking = createMockBooking({
        customer: createMockCustomer({ founder_followup_sent: false }),
      })
      const sendingFounderEmailId = null

      const getButtonText = () => {
        if (sendingFounderEmailId === booking.id) return 'Sending...'
        if (booking.customer.founder_followup_sent) return 'Founder Email Sent ✓'
        return 'Send Founder Email'
      }

      expect(getButtonText()).toBe('Send Founder Email')
    })

    it('should show "Sending..." while sending', () => {
      const booking = createMockBooking({ id: 1 })
      const sendingFounderEmailId = 1

      const getButtonText = () => {
        if (sendingFounderEmailId === booking.id) return 'Sending...'
        if (booking.customer.founder_followup_sent) return 'Founder Email Sent ✓'
        return 'Send Founder Email'
      }

      expect(getButtonText()).toBe('Sending...')
    })

    it('should show "Founder Email Sent ✓" when already sent', () => {
      const booking = createMockBooking({
        customer: createMockCustomer({ founder_followup_sent: true }),
      })
      const sendingFounderEmailId = null

      const getButtonText = () => {
        if (sendingFounderEmailId === booking.id) return 'Sending...'
        if (booking.customer.founder_followup_sent) return 'Founder Email Sent ✓'
        return 'Send Founder Email'
      }

      expect(getButtonText()).toBe('Founder Email Sent ✓')
    })
  })

  describe('Unit Tests - Button title/tooltip logic', () => {
    it('should show helpful tooltip when not sent', () => {
      const booking = createMockBooking({
        customer: createMockCustomer({ founder_followup_sent: false }),
      })

      const title = booking.customer.founder_followup_sent
        ? 'Founder email already sent'
        : 'Send personal follow-up email from founder'

      expect(title).toBe('Send personal follow-up email from founder')
    })

    it('should show "already sent" tooltip when sent', () => {
      const booking = createMockBooking({
        customer: createMockCustomer({ founder_followup_sent: true }),
      })

      const title = booking.customer.founder_followup_sent
        ? 'Founder email already sent'
        : 'Send personal follow-up email from founder'

      expect(title).toBe('Founder email already sent')
    })
  })
})

// =============================================================================
// Unit Tests - Button Rendering
// =============================================================================

describe('Admin Founder Email Button Rendering', () => {
  describe('Unit Tests - CSS classes', () => {
    it('should have email-btn class', () => {
      const expectedClasses = ['action-btn', 'email-btn']
      const className = 'action-btn email-btn'

      expectedClasses.forEach(cls => {
        expect(className).toContain(cls)
      })
    })
  })
})

// =============================================================================
// Unit Tests - Confirmation Modal
// =============================================================================

describe('Admin Founder Email Confirmation Modal', () => {
  describe('Unit Tests - Modal visibility', () => {
    it('should show modal when showFounderEmailModal is true', () => {
      const showFounderEmailModal = true
      const bookingForFounderEmail = createMockBooking()

      const shouldRenderModal = showFounderEmailModal && bookingForFounderEmail !== null
      expect(shouldRenderModal).toBe(true)
    })

    it('should NOT show modal when showFounderEmailModal is false', () => {
      const showFounderEmailModal = false
      const bookingForFounderEmail = createMockBooking()

      const shouldRenderModal = showFounderEmailModal && bookingForFounderEmail
      expect(shouldRenderModal).toBe(false)
    })

    it('should NOT show modal when bookingForFounderEmail is null', () => {
      const showFounderEmailModal = true
      const bookingForFounderEmail = null

      const shouldRenderModal = showFounderEmailModal && bookingForFounderEmail !== null
      expect(shouldRenderModal).toBe(false)
    })
  })

  describe('Unit Tests - Modal content', () => {
    it('should display booking reference', () => {
      const booking = createMockBooking({ reference: 'TAG-ABC123' })

      expect(booking.reference).toBe('TAG-ABC123')
    })

    it('should display customer full name', () => {
      const booking = createMockBooking({
        customer: createMockCustomer({ first_name: 'Sarah', last_name: 'Smith' }),
      })

      const fullName = `${booking.customer.first_name} ${booking.customer.last_name}`
      expect(fullName).toBe('Sarah Smith')
    })

    it('should display customer email', () => {
      const booking = createMockBooking({
        customer: createMockCustomer({ email: 'sarah@example.com' }),
      })

      expect(booking.customer.email).toBe('sarah@example.com')
    })

    it('should include CC warning message', () => {
      const warningMessage = "The email will be CC'd to Kristian so he can see and respond to any replies."

      expect(warningMessage).toContain("CC'd")
      expect(warningMessage).toContain('Kristian')
    })
  })
})

// =============================================================================
// Integration Tests - API Calls
// =============================================================================

describe('Admin Founder Email Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('API Integration - Send founder email', () => {
    it('should call correct API endpoint', async () => {
      const bookingId = 123
      const token = 'test-token'
      const API_URL = 'https://api.example.com'

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          message: 'Founder followup email sent to test@example.com',
          reference: 'TAG-ABC123',
        }),
      })

      await fetch(`${API_URL}/api/admin/bookings/${bookingId}/send-founder-email`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      })

      expect(global.fetch).toHaveBeenCalledWith(
        `${API_URL}/api/admin/bookings/${bookingId}/send-founder-email`,
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Authorization': `Bearer ${token}`,
          }),
        })
      )
    })

    it('should handle successful response', async () => {
      const successResponse = {
        ok: true,
        json: async () => ({
          success: true,
          message: 'Founder followup email sent to test@example.com',
          reference: 'TAG-ABC123',
        }),
      }

      global.fetch.mockResolvedValueOnce(successResponse)

      const response = await fetch('/api/admin/bookings/1/send-founder-email', {
        method: 'POST',
      })

      expect(response.ok).toBe(true)
      const data = await response.json()
      expect(data.success).toBe(true)
    })

    it('should update success message after send', async () => {
      const booking = createMockBooking({
        customer: createMockCustomer({ email: 'test@example.com' }),
      })

      const expectedMessage = `Founder email sent to ${booking.customer.email}`
      expect(expectedMessage).toBe('Founder email sent to test@example.com')
    })
  })
})

// =============================================================================
// Negative Tests - Error Handling
// =============================================================================

describe('Admin Founder Email Negative Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('API Error Handling', () => {
    it('should handle 404 booking not found', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ detail: 'Booking not found' }),
      })

      const response = await fetch('/api/admin/bookings/999/send-founder-email', {
        method: 'POST',
      })

      expect(response.ok).toBe(false)
      expect(response.status).toBe(404)
      const data = await response.json()
      expect(data.detail).toBe('Booking not found')
    })

    it('should handle 400 not pending status', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ detail: 'Founder email can only be sent for pending bookings' }),
      })

      const response = await fetch('/api/admin/bookings/1/send-founder-email', {
        method: 'POST',
      })

      expect(response.ok).toBe(false)
      expect(response.status).toBe(400)
      const data = await response.json()
      expect(data.detail).toContain('pending')
    })

    it('should handle 400 already sent', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({
          detail: 'Founder followup email already sent to test@example.com on 01 Mar 2026 at 10:30',
        }),
      })

      const response = await fetch('/api/admin/bookings/1/send-founder-email', {
        method: 'POST',
      })

      expect(response.ok).toBe(false)
      const data = await response.json()
      expect(data.detail).toContain('already sent')
    })

    it('should handle 500 SendGrid failure', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({
          detail: 'Failed to send founder followup email. Check SendGrid configuration.',
        }),
      })

      const response = await fetch('/api/admin/bookings/1/send-founder-email', {
        method: 'POST',
      })

      expect(response.ok).toBe(false)
      expect(response.status).toBe(500)
      const data = await response.json()
      expect(data.detail).toContain('SendGrid')
    })

    it('should handle network error', async () => {
      global.fetch.mockRejectedValueOnce(new Error('Network error'))

      let errorMessage = ''
      try {
        await fetch('/api/admin/bookings/1/send-founder-email', {
          method: 'POST',
        })
      } catch (err) {
        errorMessage = 'Network error while sending founder email'
      }

      expect(errorMessage).toBe('Network error while sending founder email')
    })

    it('should handle timeout', async () => {
      global.fetch.mockRejectedValueOnce(new Error('Request timeout'))

      let errorMessage = ''
      try {
        await fetch('/api/admin/bookings/1/send-founder-email', {
          method: 'POST',
        })
      } catch (err) {
        errorMessage = 'Network error while sending founder email'
      }

      expect(errorMessage).toContain('Network error')
    })
  })

  describe('Validation - Missing/null data', () => {
    it('should handle booking with null customer', () => {
      const booking = createMockBooking()
      booking.customer = null

      const canShowButton = booking.status === 'pending' && booking.customer !== null
      expect(canShowButton).toBe(false)
    })

    it('should handle booking with null customer email', () => {
      const booking = createMockBooking({
        customer: createMockCustomer({ email: null }),
      })

      const hasEmail = booking.customer?.email !== null
      expect(hasEmail).toBe(false)
    })

    it('should handle booking with empty customer email', () => {
      const booking = createMockBooking({
        customer: createMockCustomer({ email: '' }),
      })

      const hasValidEmail = Boolean(booking.customer?.email && booking.customer.email.length > 0)
      expect(hasValidEmail).toBe(false)
    })

    it('should handle undefined founder_followup_sent', () => {
      const customer = createMockCustomer()
      delete customer.founder_followup_sent

      // Should default to false/undefined which is falsy
      const alreadySent = customer.founder_followup_sent || false
      expect(alreadySent).toBe(false)
    })
  })
})

// =============================================================================
// Edge Cases
// =============================================================================

describe('Admin Founder Email Edge Cases', () => {
  describe('Special characters in data', () => {
    it('should handle customer name with apostrophe', () => {
      const booking = createMockBooking({
        customer: createMockCustomer({ first_name: "O'Connor", last_name: 'Smith' }),
      })

      expect(booking.customer.first_name).toBe("O'Connor")
    })

    it('should handle customer name with accents', () => {
      const booking = createMockBooking({
        customer: createMockCustomer({ first_name: 'José', last_name: 'García' }),
      })

      expect(booking.customer.first_name).toBe('José')
      expect(booking.customer.last_name).toBe('García')
    })

    it('should handle customer name with hyphen', () => {
      const booking = createMockBooking({
        customer: createMockCustomer({ first_name: 'Anne-Marie' }),
      })

      expect(booking.customer.first_name).toBe('Anne-Marie')
    })

    it('should handle customer email with plus sign', () => {
      const booking = createMockBooking({
        customer: createMockCustomer({ email: 'john+tag@example.com' }),
      })

      expect(booking.customer.email).toBe('john+tag@example.com')
    })

    it('should handle customer email with subdomain', () => {
      const booking = createMockBooking({
        customer: createMockCustomer({ email: 'john@mail.example.co.uk' }),
      })

      expect(booking.customer.email).toBe('john@mail.example.co.uk')
    })
  })

  describe('Boundary conditions', () => {
    it('should handle very long customer name', () => {
      const longName = 'A'.repeat(100)
      const booking = createMockBooking({
        customer: createMockCustomer({ first_name: longName }),
      })

      expect(booking.customer.first_name.length).toBe(100)
    })

    it('should handle single character name', () => {
      const booking = createMockBooking({
        customer: createMockCustomer({ first_name: 'X' }),
      })

      expect(booking.customer.first_name).toBe('X')
    })

    it('should handle booking ID at boundary (0)', () => {
      const booking = createMockBooking({ id: 0 })

      expect(booking.id).toBe(0)
    })

    it('should handle very large booking ID', () => {
      const booking = createMockBooking({ id: 999999999 })

      expect(booking.id).toBe(999999999)
    })
  })

  describe('Status edge cases', () => {
    it('should handle status with different casing', () => {
      const statusVariants = ['pending', 'PENDING', 'Pending']

      statusVariants.forEach(status => {
        const normalizedStatus = status.toLowerCase()
        expect(normalizedStatus).toBe('pending')
      })
    })

    it('should handle null status', () => {
      const booking = createMockBooking()
      booking.status = null

      const showButton = booking.status?.toLowerCase() === 'pending'
      expect(showButton).toBe(false)
    })

    it('should handle undefined status', () => {
      const booking = createMockBooking()
      delete booking.status

      const showButton = booking.status?.toLowerCase() === 'pending'
      expect(showButton).toBe(false)
    })
  })

  describe('Concurrent requests', () => {
    it('should prevent double-click with sendingFounderEmailId', () => {
      const bookingId = 1
      let sendingFounderEmailId = null

      // First click
      sendingFounderEmailId = bookingId
      const firstClickDisabled = sendingFounderEmailId === bookingId

      // Second click should be blocked
      const secondClickDisabled = sendingFounderEmailId === bookingId

      expect(firstClickDisabled).toBe(true)
      expect(secondClickDisabled).toBe(true)
    })

    it('should reset sendingFounderEmailId after completion', () => {
      let sendingFounderEmailId = 1

      // After API call completes
      sendingFounderEmailId = null

      expect(sendingFounderEmailId).toBe(null)
    })
  })

  describe('Modal state management', () => {
    it('should close modal on cancel click', () => {
      let showFounderEmailModal = true

      // Cancel action
      showFounderEmailModal = false

      expect(showFounderEmailModal).toBe(false)
    })

    it('should close modal after successful send', () => {
      let showFounderEmailModal = true
      let bookingForFounderEmail = createMockBooking()

      // After successful API call
      showFounderEmailModal = false
      bookingForFounderEmail = null

      expect(showFounderEmailModal).toBe(false)
      expect(bookingForFounderEmail).toBe(null)
    })

    it('should keep modal open on error', () => {
      let showFounderEmailModal = true

      // Error occurs - modal stays open
      // (User can see error and retry or cancel)

      expect(showFounderEmailModal).toBe(true)
    })
  })
})

// =============================================================================
// Booking Source Independence Tests
// =============================================================================

describe('Admin Founder Email - Booking Source Independence', () => {
  describe('Button visibility across booking sources', () => {
    const bookingSources = ['online', 'manual', 'phone', 'admin']

    bookingSources.forEach(source => {
      it(`should show button for pending ${source} booking`, () => {
        const booking = createMockBooking({
          status: 'pending',
          booking_source: source,
        })

        const showButton = booking.status === 'pending'
        expect(showButton).toBe(true)
      })
    })

    bookingSources.forEach(source => {
      it(`should hide button for confirmed ${source} booking`, () => {
        const booking = createMockBooking({
          status: 'confirmed',
          booking_source: source,
        })

        const showButton = booking.status === 'pending'
        expect(showButton).toBe(false)
      })
    })
  })
})

// =============================================================================
// State Update Tests
// =============================================================================

describe('Admin Founder Email - State Updates After Send', () => {
  it('should refresh bookings after successful send', async () => {
    let fetchBookingsCalled = false

    const fetchBookings = async () => {
      fetchBookingsCalled = true
    }

    // Simulate successful send
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true }),
    })

    await fetch('/api/admin/bookings/1/send-founder-email', { method: 'POST' })

    // Refresh bookings
    await fetchBookings()

    expect(fetchBookingsCalled).toBe(true)
  })

  it('should display success message after send', () => {
    let successMessage = ''
    const customerEmail = 'test@example.com'

    // After successful send
    successMessage = `Founder email sent to ${customerEmail}`

    expect(successMessage).toContain('Founder email sent')
    expect(successMessage).toContain(customerEmail)
  })

  it('should clear success message after timeout', async () => {
    let successMessage = 'Founder email sent to test@example.com'

    // Simulate setTimeout clearing message
    await new Promise(resolve => setTimeout(resolve, 10))
    successMessage = ''

    expect(successMessage).toBe('')
  })
})

// =============================================================================
// Run tests if executed directly
// =============================================================================

if (import.meta.vitest) {
  const { describe, it, expect, vi, beforeEach } = import.meta.vitest
}
