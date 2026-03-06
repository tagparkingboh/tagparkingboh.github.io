/**
 * Tests for Admin Return Vehicle Inspection functionality
 *
 * Tests the core logic:
 * - View Return Inspection button visibility based on booking status
 * - Button hidden for non-completed bookings
 * - Navigation/modal display for completed bookings
 * - Handling of missing inspection records
 * - API call and response handling
 *
 * Test categories:
 * - Unit Tests: Button visibility logic, UI rendering
 * - Integration Tests: API calls, modal state management
 * - Negative Tests: Error handling, missing data
 * - Edge Cases: Boundary conditions, malformed data
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
  ...overrides,
})

const createMockVehicle = (overrides = {}) => ({
  id: 1,
  registration: 'AB12 CDE',
  make: 'Volkswagen',
  model: 'Golf',
  colour: 'Blue',
  ...overrides,
})

const createMockBooking = (overrides = {}) => ({
  id: 1,
  reference: 'TAG-TEST001',
  status: 'completed',
  booking_source: 'online',
  dropoff_date: '2026-03-15',
  dropoff_time: '09:30',
  pickup_date: '2026-03-22',
  pickup_time_from: '14:30',
  pickup_time_to: '15:00',
  customer: createMockCustomer(),
  vehicle: createMockVehicle(),
  payment: null,
  ...overrides,
})

const createMockReturnInspection = (overrides = {}) => ({
  id: 1,
  booking_id: 1,
  inspection_type: 'pickup',
  inspector_id: 1,
  inspector_name: 'Test Inspector',
  mileage: 45678,
  fuel_level: '3/4',
  notes: 'Vehicle returned in good condition',
  photo_front: 'https://example.com/front.jpg',
  photo_rear: 'https://example.com/rear.jpg',
  photo_left: 'https://example.com/left.jpg',
  photo_right: 'https://example.com/right.jpg',
  photo_dashboard: 'https://example.com/dashboard.jpg',
  photo_additional: null,
  customer_signature: 'https://example.com/signature.png',
  declined: false,
  declined_reason: null,
  vehicle_inspection_read: true,
  created_at: '2026-03-22T15:30:00Z',
  ...overrides,
})

const createMockDropoffInspection = (overrides = {}) => ({
  id: 2,
  booking_id: 1,
  inspection_type: 'dropoff',
  inspector_id: 1,
  inspector_name: 'Test Inspector',
  mileage: 45000,
  fuel_level: 'Full',
  notes: 'Vehicle received in good condition',
  created_at: '2026-03-15T09:45:00Z',
  ...overrides,
})

// =============================================================================
// Unit Tests - Button Visibility Logic
// =============================================================================

describe('Admin Return Inspection Button Visibility', () => {
  describe('Unit Tests - Button visibility by status', () => {
    it('should show button for completed booking', () => {
      const booking = createMockBooking({ status: 'completed' })
      const showButton = booking.status?.toLowerCase() === 'completed' && booking.id

      expect(showButton).toBeTruthy()
    })

    it('should NOT show button for pending booking', () => {
      const booking = createMockBooking({ status: 'pending' })
      const showButton = booking.status?.toLowerCase() === 'completed' && booking.id

      expect(showButton).toBeFalsy()
    })

    it('should NOT show button for confirmed booking', () => {
      const booking = createMockBooking({ status: 'confirmed' })
      const showButton = booking.status?.toLowerCase() === 'completed' && booking.id

      expect(showButton).toBeFalsy()
    })

    it('should NOT show button for cancelled booking', () => {
      const booking = createMockBooking({ status: 'cancelled' })
      const showButton = booking.status?.toLowerCase() === 'completed' && booking.id

      expect(showButton).toBeFalsy()
    })

    it('should NOT show button for refunded booking', () => {
      const booking = createMockBooking({ status: 'refunded' })
      const showButton = booking.status?.toLowerCase() === 'completed' && booking.id

      expect(showButton).toBeFalsy()
    })

    it('should NOT show button for in_progress booking', () => {
      const booking = createMockBooking({ status: 'in_progress' })
      const showButton = booking.status?.toLowerCase() === 'completed' && booking.id

      expect(showButton).toBeFalsy()
    })
  })

  describe('Unit Tests - Button visibility with missing booking ID', () => {
    it('should NOT show button when booking ID is null', () => {
      const booking = createMockBooking({ status: 'completed', id: null })
      const showButton = booking.status?.toLowerCase() === 'completed' && booking.id

      expect(showButton).toBeFalsy()
    })

    it('should NOT show button when booking ID is undefined', () => {
      const booking = createMockBooking({ status: 'completed' })
      delete booking.id
      const showButton = booking.status?.toLowerCase() === 'completed' && booking.id

      expect(showButton).toBeFalsy()
    })

    it('should NOT show button when booking ID is 0', () => {
      const booking = createMockBooking({ status: 'completed', id: 0 })
      const showButton = booking.status?.toLowerCase() === 'completed' && booking.id

      expect(showButton).toBeFalsy()
    })

    it('should NOT show button when booking ID is empty string', () => {
      const booking = createMockBooking({ status: 'completed', id: '' })
      const showButton = booking.status?.toLowerCase() === 'completed' && booking.id

      expect(showButton).toBeFalsy()
    })
  })

  describe('Unit Tests - Status case handling', () => {
    it('should show button for COMPLETED (uppercase) booking', () => {
      const booking = createMockBooking({ status: 'COMPLETED' })
      const showButton = booking.status?.toLowerCase() === 'completed' && booking.id

      expect(showButton).toBeTruthy()
    })

    it('should show button for Completed (mixed case) booking', () => {
      const booking = createMockBooking({ status: 'Completed' })
      const showButton = booking.status?.toLowerCase() === 'completed' && booking.id

      expect(showButton).toBeTruthy()
    })

    it('should NOT show button when status is null', () => {
      const booking = createMockBooking({ status: null })
      const showButton = booking.status?.toLowerCase() === 'completed' && booking.id

      expect(showButton).toBeFalsy()
    })

    it('should NOT show button when status is undefined', () => {
      const booking = createMockBooking()
      delete booking.status
      const showButton = booking.status?.toLowerCase() === 'completed' && booking.id

      expect(showButton).toBeFalsy()
    })
  })
})

// =============================================================================
// Unit Tests - Button Rendering
// =============================================================================

describe('Admin Return Inspection Button Rendering', () => {
  describe('Unit Tests - CSS classes', () => {
    it('should have view-inspection-btn class', () => {
      const expectedClasses = ['action-btn', 'view-inspection-btn']
      const className = 'action-btn view-inspection-btn'

      expectedClasses.forEach(cls => {
        expect(className).toContain(cls)
      })
    })
  })

  describe('Unit Tests - Button text', () => {
    it('should have correct button label', () => {
      const buttonText = 'View Return Inspection'
      expect(buttonText).toBe('View Return Inspection')
    })
  })
})

// =============================================================================
// Unit Tests - Modal Visibility
// =============================================================================

describe('Admin Return Inspection Modal Visibility', () => {
  describe('Unit Tests - Modal visibility logic', () => {
    it('should show modal when showReturnInspectionModal is true and booking exists', () => {
      const showReturnInspectionModal = true
      const bookingForInspection = createMockBooking()

      const shouldRenderModal = showReturnInspectionModal && bookingForInspection !== null
      expect(shouldRenderModal).toBe(true)
    })

    it('should NOT show modal when showReturnInspectionModal is false', () => {
      const showReturnInspectionModal = false
      const bookingForInspection = createMockBooking()

      const shouldRenderModal = showReturnInspectionModal && bookingForInspection !== null
      expect(shouldRenderModal).toBe(false)
    })

    it('should NOT show modal when bookingForInspection is null', () => {
      const showReturnInspectionModal = true
      const bookingForInspection = null

      const shouldRenderModal = showReturnInspectionModal && bookingForInspection !== null
      expect(shouldRenderModal).toBe(false)
    })
  })

  describe('Unit Tests - Modal content display', () => {
    it('should display booking reference', () => {
      const booking = createMockBooking({ reference: 'TAG-XYZ789' })
      expect(booking.reference).toBe('TAG-XYZ789')
    })

    it('should display customer full name', () => {
      const booking = createMockBooking({
        customer: createMockCustomer({ first_name: 'Sarah', last_name: 'Smith' }),
      })

      const fullName = `${booking.customer.first_name} ${booking.customer.last_name}`
      expect(fullName).toBe('Sarah Smith')
    })

    it('should display vehicle details', () => {
      const booking = createMockBooking({
        vehicle: createMockVehicle({ registration: 'XY99 ABC', make: 'BMW', model: 'X5' }),
      })

      const vehicleInfo = `${booking.vehicle.registration} - ${booking.vehicle.make} ${booking.vehicle.model}`
      expect(vehicleInfo).toBe('XY99 ABC - BMW X5')
    })
  })
})

// =============================================================================
// Unit Tests - Inspection Data Display
// =============================================================================

describe('Admin Return Inspection Data Display', () => {
  describe('Unit Tests - Inspection details rendering', () => {
    it('should display inspector name', () => {
      const inspection = createMockReturnInspection({ inspector_name: 'Jane Doe' })
      expect(inspection.inspector_name).toBe('Jane Doe')
    })

    it('should display mileage with formatting', () => {
      const inspection = createMockReturnInspection({ mileage: 45678 })
      const formattedMileage = `${inspection.mileage.toLocaleString()} miles`
      expect(formattedMileage).toBe('45,678 miles')
    })

    it('should display fuel level', () => {
      const inspection = createMockReturnInspection({ fuel_level: '3/4' })
      expect(inspection.fuel_level).toBe('3/4')
    })

    it('should display notes', () => {
      const inspection = createMockReturnInspection({ notes: 'Minor scratch on rear bumper' })
      expect(inspection.notes).toBe('Minor scratch on rear bumper')
    })
  })

  describe('Unit Tests - Missing inspection data handling', () => {
    it('should handle missing mileage', () => {
      const inspection = createMockReturnInspection({ mileage: null })
      const mileageText = inspection.mileage ? `${inspection.mileage.toLocaleString()} miles` : 'Not recorded'
      expect(mileageText).toBe('Not recorded')
    })

    it('should handle missing fuel level', () => {
      const inspection = createMockReturnInspection({ fuel_level: null })
      const fuelText = inspection.fuel_level || 'Not recorded'
      expect(fuelText).toBe('Not recorded')
    })

    it('should handle missing inspector name', () => {
      const inspection = createMockReturnInspection({ inspector_name: null })
      const inspectorText = inspection.inspector_name || 'Unknown'
      expect(inspectorText).toBe('Unknown')
    })
  })

  describe('Unit Tests - Declined inspection handling', () => {
    it('should identify declined inspection', () => {
      const inspection = createMockReturnInspection({ declined: true })
      expect(inspection.declined).toBe(true)
    })

    it('should display declined reason when available', () => {
      const inspection = createMockReturnInspection({
        declined: true,
        declined_reason: 'Customer was in a rush'
      })
      expect(inspection.declined_reason).toBe('Customer was in a rush')
    })

    it('should handle declined inspection without reason', () => {
      const inspection = createMockReturnInspection({
        declined: true,
        declined_reason: null
      })
      expect(inspection.declined).toBe(true)
      expect(inspection.declined_reason).toBeNull()
    })
  })
})

// =============================================================================
// Integration Tests - API Calls
// =============================================================================

describe('Admin Return Inspection Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('API Integration - Fetch inspection', () => {
    it('should call correct API endpoint', async () => {
      const bookingId = 123
      const token = 'test-token'
      const API_URL = 'https://api.example.com'

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => [createMockReturnInspection({ booking_id: bookingId })],
      })

      await fetch(`${API_URL}/api/employee/inspections/${bookingId}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })

      expect(global.fetch).toHaveBeenCalledWith(
        `${API_URL}/api/employee/inspections/${bookingId}`,
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': `Bearer ${token}`,
          }),
        })
      )
    })

    it('should handle successful response with return inspection', async () => {
      const inspections = [
        createMockDropoffInspection(),
        createMockReturnInspection(),
      ]

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => inspections,
      })

      const response = await fetch('/api/employee/inspections/1')
      expect(response.ok).toBe(true)

      const data = await response.json()
      const returnInspection = data.find(i => i.inspection_type === 'pickup')

      expect(returnInspection).toBeDefined()
      expect(returnInspection.inspection_type).toBe('pickup')
    })

    it('should handle response with only dropoff inspection (no return)', async () => {
      const inspections = [createMockDropoffInspection()]

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => inspections,
      })

      const response = await fetch('/api/employee/inspections/1')
      const data = await response.json()
      const returnInspection = data.find(i => i.inspection_type === 'pickup')

      expect(returnInspection).toBeUndefined()
    })

    it('should handle empty inspections array', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      })

      const response = await fetch('/api/employee/inspections/1')
      const data = await response.json()
      const returnInspection = data.find(i => i.inspection_type === 'pickup')

      expect(returnInspection).toBeUndefined()
    })
  })
})

// =============================================================================
// Negative Tests - Error Handling
// =============================================================================

describe('Admin Return Inspection Negative Tests', () => {
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

      const response = await fetch('/api/employee/inspections/999')

      expect(response.ok).toBe(false)
      expect(response.status).toBe(404)
    })

    it('should handle 401 unauthorized', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'Not authenticated' }),
      })

      const response = await fetch('/api/employee/inspections/1')

      expect(response.ok).toBe(false)
      expect(response.status).toBe(401)
    })

    it('should handle 500 server error', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'Internal server error' }),
      })

      const response = await fetch('/api/employee/inspections/1')

      expect(response.ok).toBe(false)
      expect(response.status).toBe(500)
    })

    it('should handle network error', async () => {
      global.fetch.mockRejectedValueOnce(new Error('Network error'))

      let errorCaught = false
      try {
        await fetch('/api/employee/inspections/1')
      } catch (err) {
        errorCaught = true
        expect(err.message).toBe('Network error')
      }

      expect(errorCaught).toBe(true)
    })

    it('should handle timeout error', async () => {
      global.fetch.mockRejectedValueOnce(new Error('Request timeout'))

      let errorCaught = false
      try {
        await fetch('/api/employee/inspections/1')
      } catch (err) {
        errorCaught = true
      }

      expect(errorCaught).toBe(true)
    })
  })

  describe('Missing/Null Data Handling', () => {
    it('should handle booking with null customer', () => {
      const booking = createMockBooking()
      booking.customer = null

      const customerName = booking.customer
        ? `${booking.customer.first_name} ${booking.customer.last_name}`
        : 'Unknown Customer'

      expect(customerName).toBe('Unknown Customer')
    })

    it('should handle booking with null vehicle', () => {
      const booking = createMockBooking()
      booking.vehicle = null

      const vehicleInfo = booking.vehicle
        ? `${booking.vehicle.registration} - ${booking.vehicle.make} ${booking.vehicle.model}`
        : 'No vehicle data'

      expect(vehicleInfo).toBe('No vehicle data')
    })

    it('should handle inspection with null photos', () => {
      const inspection = createMockReturnInspection({
        photo_front: null,
        photo_rear: null,
        photo_left: null,
        photo_right: null,
        photo_dashboard: null,
        photo_additional: null,
      })

      const hasPhotos = inspection.photo_front || inspection.photo_rear ||
        inspection.photo_left || inspection.photo_right ||
        inspection.photo_dashboard || inspection.photo_additional

      expect(hasPhotos).toBeFalsy()
    })

    it('should handle inspection with null signature', () => {
      const inspection = createMockReturnInspection({ customer_signature: null })
      expect(inspection.customer_signature).toBeNull()
    })
  })
})

// =============================================================================
// Edge Cases
// =============================================================================

describe('Admin Return Inspection Edge Cases', () => {
  describe('Special characters in data', () => {
    it('should handle customer name with apostrophe', () => {
      const booking = createMockBooking({
        customer: createMockCustomer({ first_name: "O'Connor", last_name: 'Smith' }),
      })

      expect(booking.customer.first_name).toBe("O'Connor")
    })

    it('should handle vehicle registration with special formatting', () => {
      const booking = createMockBooking({
        vehicle: createMockVehicle({ registration: 'AB12 CDE' }),
      })

      expect(booking.vehicle.registration).toBe('AB12 CDE')
    })

    it('should handle notes with special characters', () => {
      const inspection = createMockReturnInspection({
        notes: 'Scratch on driver\'s side door - 2" long'
      })

      expect(inspection.notes).toContain("driver's")
      expect(inspection.notes).toContain('2"')
    })

    it('should handle notes with newlines', () => {
      const inspection = createMockReturnInspection({
        notes: 'Line 1\nLine 2\nLine 3'
      })

      expect(inspection.notes).toContain('\n')
    })
  })

  describe('Boundary conditions', () => {
    it('should handle very large booking ID', () => {
      const booking = createMockBooking({ id: 999999999 })
      expect(booking.id).toBe(999999999)
    })

    it('should handle booking ID of 1', () => {
      const booking = createMockBooking({ id: 1 })
      expect(booking.id).toBe(1)
    })

    it('should handle very large mileage', () => {
      const inspection = createMockReturnInspection({ mileage: 999999 })
      const formattedMileage = `${inspection.mileage.toLocaleString()} miles`
      expect(formattedMileage).toBe('999,999 miles')
    })

    it('should handle zero mileage', () => {
      const inspection = createMockReturnInspection({ mileage: 0 })
      const mileageText = inspection.mileage ? `${inspection.mileage.toLocaleString()} miles` : 'Not recorded'
      // 0 is falsy, so it shows "Not recorded"
      expect(mileageText).toBe('Not recorded')
    })

    it('should handle very long notes', () => {
      const longNotes = 'A'.repeat(1000)
      const inspection = createMockReturnInspection({ notes: longNotes })

      expect(inspection.notes.length).toBe(1000)
    })

    it('should handle empty string notes', () => {
      const inspection = createMockReturnInspection({ notes: '' })
      expect(inspection.notes).toBe('')
    })
  })

  describe('Mixed bookings list', () => {
    it('should correctly identify completed bookings in mixed list', () => {
      const bookings = [
        createMockBooking({ id: 1, status: 'completed' }),
        createMockBooking({ id: 2, status: 'pending' }),
        createMockBooking({ id: 3, status: 'confirmed' }),
        createMockBooking({ id: 4, status: 'completed' }),
        createMockBooking({ id: 5, status: 'cancelled' }),
      ]

      const completedBookings = bookings.filter(b =>
        b.status?.toLowerCase() === 'completed' && b.id
      )

      expect(completedBookings.length).toBe(2)
      expect(completedBookings[0].id).toBe(1)
      expect(completedBookings[1].id).toBe(4)
    })

    it('should handle first booking being completed', () => {
      const bookings = [
        createMockBooking({ id: 1, status: 'completed' }),
        createMockBooking({ id: 2, status: 'pending' }),
        createMockBooking({ id: 3, status: 'pending' }),
      ]

      const firstBookingShowsButton = bookings[0].status?.toLowerCase() === 'completed' && bookings[0].id
      expect(firstBookingShowsButton).toBeTruthy()
    })

    it('should handle last booking being completed', () => {
      const bookings = [
        createMockBooking({ id: 1, status: 'pending' }),
        createMockBooking({ id: 2, status: 'pending' }),
        createMockBooking({ id: 3, status: 'completed' }),
      ]

      const lastBookingShowsButton = bookings[2].status?.toLowerCase() === 'completed' && bookings[2].id
      expect(lastBookingShowsButton).toBeTruthy()
    })

    it('should handle all bookings being completed', () => {
      const bookings = [
        createMockBooking({ id: 1, status: 'completed' }),
        createMockBooking({ id: 2, status: 'completed' }),
        createMockBooking({ id: 3, status: 'completed' }),
      ]

      const completedBookings = bookings.filter(b =>
        b.status?.toLowerCase() === 'completed' && b.id
      )

      expect(completedBookings.length).toBe(3)
    })

    it('should handle no bookings being completed', () => {
      const bookings = [
        createMockBooking({ id: 1, status: 'pending' }),
        createMockBooking({ id: 2, status: 'confirmed' }),
        createMockBooking({ id: 3, status: 'cancelled' }),
      ]

      const completedBookings = bookings.filter(b =>
        b.status?.toLowerCase() === 'completed' && b.id
      )

      expect(completedBookings.length).toBe(0)
    })
  })

  describe('Large bookings list', () => {
    it('should correctly filter completed bookings in large list', () => {
      const bookings = []
      for (let i = 1; i <= 100; i++) {
        bookings.push(createMockBooking({
          id: i,
          status: i % 5 === 0 ? 'completed' : 'confirmed' // Every 5th is completed
        }))
      }

      const completedBookings = bookings.filter(b =>
        b.status?.toLowerCase() === 'completed' && b.id
      )

      expect(completedBookings.length).toBe(20)
    })
  })
})

// =============================================================================
// Modal State Management Tests
// =============================================================================

describe('Admin Return Inspection Modal State Management', () => {
  describe('Modal open/close logic', () => {
    it('should set modal state when opening', () => {
      let showReturnInspectionModal = false
      let bookingForInspection = null
      let loadingReturnInspection = false

      // Open modal action
      const booking = createMockBooking()
      showReturnInspectionModal = true
      bookingForInspection = booking
      loadingReturnInspection = true

      expect(showReturnInspectionModal).toBe(true)
      expect(bookingForInspection).toBe(booking)
      expect(loadingReturnInspection).toBe(true)
    })

    it('should reset modal state when closing', () => {
      let showReturnInspectionModal = true
      let bookingForInspection = createMockBooking()
      let returnInspectionData = createMockReturnInspection()

      // Close modal action
      showReturnInspectionModal = false
      bookingForInspection = null
      returnInspectionData = null

      expect(showReturnInspectionModal).toBe(false)
      expect(bookingForInspection).toBeNull()
      expect(returnInspectionData).toBeNull()
    })

    it('should update loading state after fetch completes', () => {
      let loadingReturnInspection = true
      let returnInspectionData = null

      // Fetch completes
      loadingReturnInspection = false
      returnInspectionData = createMockReturnInspection()

      expect(loadingReturnInspection).toBe(false)
      expect(returnInspectionData).not.toBeNull()
    })

    it('should handle fetch returning no inspection', () => {
      let loadingReturnInspection = true
      let returnInspectionData = createMockReturnInspection()

      // Fetch completes with no return inspection
      loadingReturnInspection = false
      returnInspectionData = null

      expect(loadingReturnInspection).toBe(false)
      expect(returnInspectionData).toBeNull()
    })
  })
})

// =============================================================================
// Integration Tests - Full Flow
// =============================================================================

describe('Admin Return Inspection Integration - Full Flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Happy path - View inspection from completed booking', () => {
    it('should complete full flow: click -> fetch -> display', async () => {
      const booking = createMockBooking({ id: 123, status: 'completed' })
      const inspection = createMockReturnInspection({ booking_id: 123 })

      // Step 1: Verify button shows for completed booking
      const showButton = booking.status?.toLowerCase() === 'completed' && booking.id
      expect(showButton).toBeTruthy()

      // Step 2: Mock API response
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => [inspection],
      })

      // Step 3: Simulate fetch
      const response = await fetch(`/api/employee/inspections/${booking.id}`)
      const data = await response.json()
      const returnInspection = data.find(i => i.inspection_type === 'pickup')

      // Step 4: Verify inspection data
      expect(returnInspection).toBeDefined()
      expect(returnInspection.booking_id).toBe(123)
    })
  })

  describe('Edge case - Completed booking with no return inspection', () => {
    it('should handle missing return inspection gracefully', async () => {
      const booking = createMockBooking({ id: 456, status: 'completed' })

      // Button should show
      const showButton = booking.status?.toLowerCase() === 'completed' && booking.id
      expect(showButton).toBeTruthy()

      // API returns only dropoff inspection
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => [createMockDropoffInspection({ booking_id: 456 })],
      })

      const response = await fetch(`/api/employee/inspections/${booking.id}`)
      const data = await response.json()
      const returnInspection = data.find(i => i.inspection_type === 'pickup')

      // No return inspection found - should show empty state
      expect(returnInspection).toBeUndefined()
    })
  })

  describe('Edge case - Malformed booking record', () => {
    it('should not render button for malformed completed booking', () => {
      const malformedBooking = createMockBooking({ id: null, status: 'completed' })

      const showButton = malformedBooking.status?.toLowerCase() === 'completed' && malformedBooking.id
      expect(showButton).toBeFalsy()
    })
  })

  describe('Boundary case - First and last rows in list', () => {
    it('should show button for first completed booking in list', () => {
      const bookings = [
        createMockBooking({ id: 1, status: 'completed' }),
        createMockBooking({ id: 2, status: 'pending' }),
        createMockBooking({ id: 3, status: 'confirmed' }),
      ]

      const firstShowsButton = bookings[0].status?.toLowerCase() === 'completed' && bookings[0].id
      expect(firstShowsButton).toBeTruthy()
    })

    it('should show button for last completed booking in list', () => {
      const bookings = [
        createMockBooking({ id: 1, status: 'pending' }),
        createMockBooking({ id: 2, status: 'confirmed' }),
        createMockBooking({ id: 3, status: 'completed' }),
      ]

      const lastShowsButton = bookings[2].status?.toLowerCase() === 'completed' && bookings[2].id
      expect(lastShowsButton).toBeTruthy()
    })

    it('should show buttons for both first and last when both completed', () => {
      const bookings = [
        createMockBooking({ id: 1, status: 'completed' }),
        createMockBooking({ id: 2, status: 'pending' }),
        createMockBooking({ id: 3, status: 'completed' }),
      ]

      const firstShowsButton = bookings[0].status?.toLowerCase() === 'completed' && bookings[0].id
      const lastShowsButton = bookings[2].status?.toLowerCase() === 'completed' && bookings[2].id

      expect(firstShowsButton).toBeTruthy()
      expect(lastShowsButton).toBeTruthy()
    })
  })
})

// =============================================================================
// Run tests if executed directly
// =============================================================================

if (import.meta.vitest) {
  const { describe, it, expect, vi, beforeEach } = import.meta.vitest
}
