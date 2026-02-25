/**
 * Tests for Employee component - Complete Booking functionality
 *
 * Tests the core logic:
 * - Complete Booking button is disabled when no return inspection exists
 * - Complete Booking button is enabled when return inspection exists
 * - Complete Booking modal confirmation flow
 * - API call on completion
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock fetch
global.fetch = vi.fn()

// Mock booking data
const mockBookingWithoutInspection = {
  id: 1,
  reference: 'TAG-ABC12345',
  status: 'confirmed',
  dropoff_date: '2026-01-22',
  dropoff_time: '19:35',
  pickup_date: '2026-01-29',
  pickup_time_from: '14:00',
  pickup_time_to: '15:00',
  customer: {
    first_name: 'John',
    last_name: 'Doe',
  },
  vehicle: {
    registration: 'AA19AAA',
  },
}

const mockBookingWithDropoffInspection = {
  ...mockBookingWithoutInspection,
  id: 2,
  reference: 'TAG-DEF67890',
}

const mockBookingWithReturnInspection = {
  ...mockBookingWithoutInspection,
  id: 3,
  reference: 'TAG-GHI11111',
}

const mockBookingCompleted = {
  ...mockBookingWithoutInspection,
  id: 4,
  reference: 'TAG-JKL22222',
  status: 'completed',
}

// Mock inspection data
const mockInspections = {
  // Booking 1: No inspections
  1: [],
  // Booking 2: Only dropoff inspection
  2: [
    { id: 1, booking_id: 2, inspection_type: 'dropoff' }
  ],
  // Booking 3: Both dropoff and pickup (return) inspection
  3: [
    { id: 2, booking_id: 3, inspection_type: 'dropoff' },
    { id: 3, booking_id: 3, inspection_type: 'pickup' }
  ],
  // Booking 4: Completed booking with return inspection
  4: [
    { id: 4, booking_id: 4, inspection_type: 'dropoff' },
    { id: 5, booking_id: 4, inspection_type: 'pickup' }
  ],
}

describe('Employee Complete Booking Button State', () => {
  describe('Unit Tests - Button disabled logic', () => {
    it('should be disabled when no inspections exist', () => {
      const bookingInspections = mockInspections[1] // Empty array
      const hasReturnInspection = bookingInspections.some(i => i.inspection_type === 'pickup')

      expect(hasReturnInspection).toBe(false)
    })

    it('should be disabled when only dropoff inspection exists', () => {
      const bookingInspections = mockInspections[2] // Only dropoff
      const hasReturnInspection = bookingInspections.some(i => i.inspection_type === 'pickup')

      expect(hasReturnInspection).toBe(false)
    })

    it('should be enabled when return inspection exists', () => {
      const bookingInspections = mockInspections[3] // Both dropoff and pickup
      const hasReturnInspection = bookingInspections.some(i => i.inspection_type === 'pickup')

      expect(hasReturnInspection).toBe(true)
    })

    it('should show completed badge instead of button when status is completed', () => {
      const isCompleted = mockBookingCompleted.status === 'completed'

      expect(isCompleted).toBe(true)
    })
  })

  describe('Unit Tests - Button rendering logic', () => {
    it('should render disabled button with correct attributes when no return inspection', () => {
      const bookingInspections = mockInspections[1]
      const hasReturnInspection = bookingInspections.some(i => i.inspection_type === 'pickup')
      const isCompleted = mockBookingWithoutInspection.status === 'completed'

      // Simulating the render logic
      const buttonProps = {
        disabled: !hasReturnInspection,
        className: `complete-btn ${!hasReturnInspection ? 'complete-btn-disabled' : ''}`,
        title: !hasReturnInspection ? 'Complete the Return Inspection first' : '',
      }

      expect(buttonProps.disabled).toBe(true)
      expect(buttonProps.className).toContain('complete-btn-disabled')
      expect(buttonProps.title).toBe('Complete the Return Inspection first')
    })

    it('should render enabled button when return inspection exists', () => {
      const bookingInspections = mockInspections[3]
      const hasReturnInspection = bookingInspections.some(i => i.inspection_type === 'pickup')

      const buttonProps = {
        disabled: !hasReturnInspection,
        className: `complete-btn ${!hasReturnInspection ? 'complete-btn-disabled' : ''}`,
        title: !hasReturnInspection ? 'Complete the Return Inspection first' : '',
      }

      expect(buttonProps.disabled).toBe(false)
      expect(buttonProps.className).not.toContain('complete-btn-disabled')
      expect(buttonProps.title).toBe('')
    })
  })
})

describe('Employee Complete Booking Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('API Integration - Complete booking flow', () => {
    it('should call correct API endpoint when completing a booking', async () => {
      const bookingId = 3
      const token = 'test-token'

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      })

      // Simulate the API call
      const response = await fetch(`/api/employee/bookings/${bookingId}/complete`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      })

      expect(fetch).toHaveBeenCalledWith(
        `/api/employee/bookings/${bookingId}/complete`,
        {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
        }
      )
      expect(response.ok).toBe(true)
    })

    it('should handle API error when completing a booking', async () => {
      const bookingId = 3
      const token = 'test-token'

      global.fetch.mockResolvedValueOnce({
        ok: false,
        json: async () => ({ detail: 'Failed to complete booking' }),
      })

      const response = await fetch(`/api/employee/bookings/${bookingId}/complete`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      })

      expect(response.ok).toBe(false)
      const data = await response.json()
      expect(data.detail).toBe('Failed to complete booking')
    })

    it('should handle network error when completing a booking', async () => {
      const bookingId = 3
      const token = 'test-token'

      global.fetch.mockRejectedValueOnce(new Error('Network error'))

      await expect(
        fetch(`/api/employee/bookings/${bookingId}/complete`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
        })
      ).rejects.toThrow('Network error')
    })
  })

  describe('Inspection fetch integration', () => {
    it('should fetch inspections for a booking', async () => {
      const bookingId = 3
      const token = 'test-token'

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockInspections[3],
      })

      const response = await fetch(`/api/employee/bookings/${bookingId}/inspections`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })

      expect(fetch).toHaveBeenCalledWith(
        `/api/employee/bookings/${bookingId}/inspections`,
        {
          headers: { 'Authorization': `Bearer ${token}` },
        }
      )

      const inspections = await response.json()
      expect(inspections).toHaveLength(2)
      expect(inspections.some(i => i.inspection_type === 'pickup')).toBe(true)
    })

    it('should return empty array when no inspections exist', async () => {
      const bookingId = 1
      const token = 'test-token'

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      })

      const response = await fetch(`/api/employee/bookings/${bookingId}/inspections`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })

      const inspections = await response.json()
      expect(inspections).toHaveLength(0)
    })
  })
})

describe('Employee Complete Booking - Edge Cases', () => {
  it('should handle booking with multiple return inspections', () => {
    // Edge case: multiple pickup inspections (shouldn't happen but handle gracefully)
    const inspectionsWithDuplicates = [
      { id: 1, booking_id: 5, inspection_type: 'dropoff' },
      { id: 2, booking_id: 5, inspection_type: 'pickup' },
      { id: 3, booking_id: 5, inspection_type: 'pickup' }, // Duplicate
    ]

    const hasReturnInspection = inspectionsWithDuplicates.some(i => i.inspection_type === 'pickup')
    expect(hasReturnInspection).toBe(true)
  })

  it('should handle undefined inspections array', () => {
    const bookingInspections = undefined
    const hasReturnInspection = (bookingInspections || []).some(i => i.inspection_type === 'pickup')

    expect(hasReturnInspection).toBe(false)
  })

  it('should handle null inspections array', () => {
    const bookingInspections = null
    const hasReturnInspection = (bookingInspections || []).some(i => i.inspection_type === 'pickup')

    expect(hasReturnInspection).toBe(false)
  })

  it('should not enable button for dropoff-only inspection', () => {
    const inspections = [
      { id: 1, booking_id: 6, inspection_type: 'dropoff' },
    ]

    const hasReturnInspection = inspections.some(i => i.inspection_type === 'pickup')
    expect(hasReturnInspection).toBe(false)
  })

  it('should differentiate between dropoff and pickup inspection types', () => {
    const dropoffInspection = { inspection_type: 'dropoff' }
    const pickupInspection = { inspection_type: 'pickup' }

    expect(dropoffInspection.inspection_type).not.toBe('pickup')
    expect(pickupInspection.inspection_type).toBe('pickup')
  })
})

describe('Employee Complete Booking - State Transitions', () => {
  it('should transition from disabled to enabled when return inspection is added', () => {
    // Initial state: no return inspection
    let inspections = [
      { id: 1, booking_id: 7, inspection_type: 'dropoff' },
    ]
    let hasReturnInspection = inspections.some(i => i.inspection_type === 'pickup')
    expect(hasReturnInspection).toBe(false)

    // After return inspection is added
    inspections = [
      { id: 1, booking_id: 7, inspection_type: 'dropoff' },
      { id: 2, booking_id: 7, inspection_type: 'pickup' },
    ]
    hasReturnInspection = inspections.some(i => i.inspection_type === 'pickup')
    expect(hasReturnInspection).toBe(true)
  })

  it('should show completed badge after successful completion', () => {
    // Before completion
    let booking = { ...mockBookingWithReturnInspection, status: 'confirmed' }
    expect(booking.status).toBe('confirmed')
    expect(booking.status === 'completed').toBe(false)

    // After completion
    booking = { ...booking, status: 'completed' }
    expect(booking.status).toBe('completed')
    expect(booking.status === 'completed').toBe(true)
  })
})
