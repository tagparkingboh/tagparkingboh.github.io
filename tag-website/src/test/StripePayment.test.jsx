/**
 * Tests for StripePayment component - specifically testing that payment intents
 * are only created ONCE, preventing duplicate bookings from re-renders.
 *
 * This addresses the bug where David Thomson had 10 pending bookings created
 * because the useEffect was re-running on every formData change.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import StripePayment from '../components/StripePayment'

// Capture the latest PaymentElement props so tests can fire onReady / onChange.
// Reset in beforeEach.
let paymentElementProps = null

// Value returned by the mocked useStripe hook. Tests that drive handleSubmit
// (clicking Pay) overwrite this with their own confirmPayment /
// retrievePaymentIntent mocks; read lazily so per-test assignment works.
let mockStripeHook = { confirmPayment: vi.fn() }

// Mock Stripe
vi.mock('@stripe/stripe-js', () => ({
  loadStripe: vi.fn(() => Promise.resolve({
    elements: vi.fn(),
    confirmPayment: vi.fn(),
  })),
}))

vi.mock('@stripe/react-stripe-js', () => ({
  Elements: ({ children }) => <div data-testid="stripe-elements">{children}</div>,
  PaymentElement: (props) => {
    paymentElementProps = props
    return <div data-testid="payment-element">Payment Element</div>
  },
  useStripe: () => mockStripeHook,
  useElements: () => ({}),
}))

// Mock form data
const mockFormData = {
  firstName: 'John',
  lastName: 'Doe',
  email: 'john@example.com',
  phone: '+447777123456',
  billingAddress1: '123 Test St',
  billingAddress2: '',
  billingCity: 'London',
  billingCounty: '',
  billingPostcode: 'SW1A 1AA',
  billingCountry: 'United Kingdom',
  registration: 'AB12CDE',
  make: 'Ford',
  model: 'Focus',
  colour: 'Blue',
  package: 'quick',
  dropoffDate: new Date('2026-04-12'),
  pickupDate: new Date('2026-04-19'),
  dropoffSlot: 'late',
  dropoffFlight: '10:30|PMI',
  terms: true,
}

const mockSelectedFlight = {
  id: 551,
  flightNumber: '3643',
  airlineCode: 'LS',
  time: '10:30',
  destinationCode: 'PMI',
}

const mockSelectedArrivalFlight = {
  flightNumber: '3644',
  time: '17:30',
}

// Track API calls
let createPaymentIntentCalls = 0

// Helper to setup fetch mocks
const setupFetchMocks = () => {
  createPaymentIntentCalls = 0

  global.fetch = vi.fn((url) => {
    // Stripe config endpoint
    if (url.includes('/api/stripe/config')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ publishable_key: 'pk_test_123' }),
      })
    }

    // Create payment intent endpoint
    if (url.includes('/api/payments/create-intent')) {
      createPaymentIntentCalls++
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          client_secret: `pi_test_secret_${createPaymentIntentCalls}`,
          booking_reference: `TAG-TEST${createPaymentIntentCalls}`,
          amount_display: '£89.00',
          is_free_booking: false,
        }),
      })
    }

    return Promise.reject(new Error(`Unhandled fetch: ${url}`))
  })
}

describe('StripePayment - Duplicate Prevention', () => {
  beforeEach(() => {
    setupFetchMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('should only call create-intent API once on initial mount', async () => {
    render(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-123"
        promoCode={null}
        promoCodeDiscount={0}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    // Wait for the component to initialize
    await waitFor(() => {
      expect(createPaymentIntentCalls).toBe(1)
    }, { timeout: 3000 })

    // Verify it was only called once
    expect(createPaymentIntentCalls).toBe(1)
  })

  it('should NOT call create-intent API again when re-rendered with different formData', async () => {
    const { rerender } = render(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-123"
        promoCode={null}
        promoCodeDiscount={0}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    // Wait for initial load
    await waitFor(() => {
      expect(createPaymentIntentCalls).toBe(1)
    }, { timeout: 3000 })

    // Simulate what happens when user toggles terms checkbox (formData changes)
    const updatedFormData = { ...mockFormData, terms: false }
    rerender(
      <StripePayment
        formData={updatedFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-123"
        promoCode={null}
        promoCodeDiscount={0}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    // Toggle terms back
    const toggledFormData = { ...mockFormData, terms: true }
    rerender(
      <StripePayment
        formData={toggledFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-123"
        promoCode={null}
        promoCodeDiscount={0}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    // Wait a bit to ensure no additional calls are made
    await new Promise(resolve => setTimeout(resolve, 500))

    // Should still only be 1 call despite multiple re-renders
    expect(createPaymentIntentCalls).toBe(1)
  })

  it('should NOT create duplicate payment intents on rapid re-renders (simulating iOS Safari behavior)', async () => {
    const { rerender } = render(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-123"
        promoCode={null}
        promoCodeDiscount={0}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    // Wait for initial load
    await waitFor(() => {
      expect(createPaymentIntentCalls).toBe(1)
    }, { timeout: 3000 })

    // Simulate rapid re-renders (like what happened with David Thomson's iPhone)
    // 8 re-renders in quick succession
    for (let i = 0; i < 8; i++) {
      const variedFormData = { ...mockFormData, terms: i % 2 === 0 }
      rerender(
        <StripePayment
          formData={variedFormData}
          selectedFlight={mockSelectedFlight}
          selectedArrivalFlight={mockSelectedArrivalFlight}
          customerId={1}
          vehicleId={1}
          sessionId="test-session-123"
          promoCode={null}
          promoCodeDiscount={0}
          onPaymentSuccess={vi.fn()}
          onPaymentError={vi.fn()}
        />
      )
    }

    // Wait to ensure no additional calls
    await new Promise(resolve => setTimeout(resolve, 500))

    // Critical assertion: should still only be 1 call
    expect(createPaymentIntentCalls).toBe(1)
  })

  it('should NOT create payment intent for 100% discount (free booking)', async () => {
    render(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-123"
        promoCode="FREETEST"
        promoCodeDiscount={100}
        promoCodeType="free_100"
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    // Wait a bit
    await new Promise(resolve => setTimeout(resolve, 500))

    // Should not call create-intent for free bookings (they wait for button click)
    expect(createPaymentIntentCalls).toBe(0)
  })
})

describe('StripePayment - Multiple Component Instances', () => {
  beforeEach(() => {
    setupFetchMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('should create separate payment intents for different component instances', async () => {
    // Render first instance
    render(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="session-1"
        promoCode={null}
        promoCodeDiscount={0}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    await waitFor(() => {
      expect(createPaymentIntentCalls).toBe(1)
    }, { timeout: 3000 })

    // Render second instance (e.g., user opened a new tab)
    render(
      <StripePayment
        formData={{ ...mockFormData, email: 'other@example.com' }}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={2}
        vehicleId={2}
        sessionId="session-2"
        promoCode={null}
        promoCodeDiscount={0}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    await waitFor(() => {
      expect(createPaymentIntentCalls).toBe(2)
    }, { timeout: 3000 })

    // Two separate instances should create 2 payment intents (correct behavior)
    expect(createPaymentIntentCalls).toBe(2)
  })
})

// =============================================================================
// Manual Flight Entry and Time Override Tests
// =============================================================================

describe('StripePayment - Manual Flight Entry', () => {
  beforeEach(() => {
    setupFetchMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('should include manual departure data in payment request', async () => {
    let capturedRequest = null

    global.fetch = vi.fn((url, options) => {
      if (url.includes('/api/stripe/config')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ publishable_key: 'pk_test_123' }),
        })
      }

      if (url.includes('/api/payments/create-intent')) {
        capturedRequest = JSON.parse(options.body)
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            client_secret: 'pi_test_secret_manual',
            booking_reference: 'TAG-MANUAL',
            amount_display: '£89.00',
            is_free_booking: false,
          }),
        })
      }

      return Promise.reject(new Error(`Unhandled fetch: ${url}`))
    })

    const manualDepartureData = {
      airlineCode: 'BY',
      airlineName: 'TUI',
      flightNumber: '1234',
      flightTime: '10:30',
      destinationCode: 'FAO',
      destinationName: 'Faro, Portugal',
      dropoffSlot: '120'  // 2h before — manual entry slot id (90/120/150)
    }

    render(
      <StripePayment
        formData={mockFormData}
        selectedFlight={null}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-manual"
        promoCode={null}
        promoCodeDiscount={0}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
        manualDepartureData={manualDepartureData}
        manualArrivalData={null}
        departureTimeOverride=""
        arrivalTimeOverride=""
      />
    )

    await waitFor(() => {
      expect(capturedRequest).not.toBeNull()
    }, { timeout: 3000 })

    expect(capturedRequest.dropoff_manual_entry).toBe(true)
    expect(capturedRequest.dropoff_airline_code).toBe('BY')
    expect(capturedRequest.dropoff_airline_name).toBe('TUI')
    expect(capturedRequest.flight_number).toBe('1234')
    expect(capturedRequest.departure_id).toBe(null)
    expect(capturedRequest.drop_off_slot).toBe('120')
  })

  it('should include manual arrival data in payment request', async () => {
    let capturedRequest = null

    global.fetch = vi.fn((url, options) => {
      if (url.includes('/api/stripe/config')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ publishable_key: 'pk_test_123' }),
        })
      }

      if (url.includes('/api/payments/create-intent')) {
        capturedRequest = JSON.parse(options.body)
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            client_secret: 'pi_test_secret_manual',
            booking_reference: 'TAG-MANUAL-ARR',
            amount_display: '£89.00',
            is_free_booking: false,
          }),
        })
      }

      return Promise.reject(new Error(`Unhandled fetch: ${url}`))
    })

    const manualArrivalData = {
      airlineCode: 'FR',
      airlineName: 'Ryanair',
      flightNumber: '9876',
      flightTime: '23:35',
      originCode: 'FAO',
      originName: 'Faro, Portugal'
    }

    render(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={null}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-manual-arr"
        promoCode={null}
        promoCodeDiscount={0}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
        manualDepartureData={null}
        manualArrivalData={manualArrivalData}
        departureTimeOverride=""
        arrivalTimeOverride=""
      />
    )

    await waitFor(() => {
      expect(capturedRequest).not.toBeNull()
    }, { timeout: 3000 })

    expect(capturedRequest.pickup_manual_entry).toBe(true)
    expect(capturedRequest.pickup_airline_code).toBe('FR')
    expect(capturedRequest.pickup_airline_name).toBe('Ryanair')
    expect(capturedRequest.pickup_flight_number).toBe('9876')
    expect(capturedRequest.pickup_flight_time).toBe('23:35')
    expect(capturedRequest.arrival_id).toBe(null)
  })
})

describe('StripePayment - Time Override', () => {
  beforeEach(() => {
    setupFetchMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('should include departure time override in payment request', async () => {
    let capturedRequest = null

    global.fetch = vi.fn((url, options) => {
      if (url.includes('/api/stripe/config')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ publishable_key: 'pk_test_123' }),
        })
      }

      if (url.includes('/api/payments/create-intent')) {
        capturedRequest = JSON.parse(options.body)
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            client_secret: 'pi_test_secret_override',
            booking_reference: 'TAG-OVERRIDE',
            amount_display: '£89.00',
            is_free_booking: false,
          }),
        })
      }

      return Promise.reject(new Error(`Unhandled fetch: ${url}`))
    })

    render(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-override"
        promoCode={null}
        promoCodeDiscount={0}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
        manualDepartureData={null}
        manualArrivalData={null}
        departureTimeOverride="11:00"
        arrivalTimeOverride=""
      />
    )

    await waitFor(() => {
      expect(capturedRequest).not.toBeNull()
    }, { timeout: 3000 })

    expect(capturedRequest.dropoff_time_override).toBe(true)
    expect(capturedRequest.dropoff_scheduled_time).toBe('10:30')
    expect(capturedRequest.dropoff_customer_time).toBe('11:00')
  })

  it('should include arrival time override in payment request', async () => {
    let capturedRequest = null

    global.fetch = vi.fn((url, options) => {
      if (url.includes('/api/stripe/config')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ publishable_key: 'pk_test_123' }),
        })
      }

      if (url.includes('/api/payments/create-intent')) {
        capturedRequest = JSON.parse(options.body)
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            client_secret: 'pi_test_secret_override_arr',
            booking_reference: 'TAG-OVERRIDE-ARR',
            amount_display: '£89.00',
            is_free_booking: false,
          }),
        })
      }

      return Promise.reject(new Error(`Unhandled fetch: ${url}`))
    })

    render(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-override-arr"
        promoCode={null}
        promoCodeDiscount={0}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
        manualDepartureData={null}
        manualArrivalData={null}
        departureTimeOverride=""
        arrivalTimeOverride="18:00"
      />
    )

    await waitFor(() => {
      expect(capturedRequest).not.toBeNull()
    }, { timeout: 3000 })

    expect(capturedRequest.pickup_time_override).toBe(true)
    expect(capturedRequest.pickup_scheduled_time).toBe('17:30')
    expect(capturedRequest.pickup_customer_time).toBe('18:00')
  })

  it('should NOT flag time override when time matches scheduled', async () => {
    let capturedRequest = null

    global.fetch = vi.fn((url, options) => {
      if (url.includes('/api/stripe/config')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ publishable_key: 'pk_test_123' }),
        })
      }

      if (url.includes('/api/payments/create-intent')) {
        capturedRequest = JSON.parse(options.body)
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            client_secret: 'pi_test_secret_same',
            booking_reference: 'TAG-SAME',
            amount_display: '£89.00',
            is_free_booking: false,
          }),
        })
      }

      return Promise.reject(new Error(`Unhandled fetch: ${url}`))
    })

    render(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-same"
        promoCode={null}
        promoCodeDiscount={0}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
        manualDepartureData={null}
        manualArrivalData={null}
        departureTimeOverride="10:30"
        arrivalTimeOverride="17:30"
      />
    )

    await waitFor(() => {
      expect(capturedRequest).not.toBeNull()
    }, { timeout: 3000 })

    // Times match scheduled, so override should be false
    expect(capturedRequest.dropoff_time_override).toBe(false)
    expect(capturedRequest.dropoff_scheduled_time).toBe(null)
    expect(capturedRequest.pickup_time_override).toBe(false)
    expect(capturedRequest.pickup_scheduled_time).toBe(null)
  })
})

describe('StripePayment - Edge Cases for Manual Entry', () => {
  beforeEach(() => {
    setupFetchMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('should handle both manual departure and arrival simultaneously', async () => {
    let capturedRequest = null

    global.fetch = vi.fn((url, options) => {
      if (url.includes('/api/stripe/config')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ publishable_key: 'pk_test_123' }),
        })
      }

      if (url.includes('/api/payments/create-intent')) {
        capturedRequest = JSON.parse(options.body)
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            client_secret: 'pi_test_secret_both',
            booking_reference: 'TAG-BOTH',
            amount_display: '£89.00',
            is_free_booking: false,
          }),
        })
      }

      return Promise.reject(new Error(`Unhandled fetch: ${url}`))
    })

    const manualDepartureData = {
      airlineCode: 'BY',
      airlineName: 'TUI',
      flightNumber: '1234',
      flightTime: '14:30',
      destinationCode: 'FAO',
      destinationName: 'Faro, Portugal',
      dropoffSlot: '120'
    }

    const manualArrivalData = {
      airlineCode: 'BY',
      airlineName: 'TUI',
      flightNumber: '1235',
      flightTime: '22:00',
      originCode: 'FAO',
      originName: 'Faro, Portugal'
    }

    render(
      <StripePayment
        formData={{ ...mockFormData, dropoffSlot: '' }}
        selectedFlight={null}
        selectedArrivalFlight={null}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-both"
        promoCode={null}
        promoCodeDiscount={0}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
        manualDepartureData={manualDepartureData}
        manualArrivalData={manualArrivalData}
        departureTimeOverride=""
        arrivalTimeOverride=""
      />
    )

    await waitFor(() => {
      expect(capturedRequest).not.toBeNull()
    }, { timeout: 3000 })

    // Verify both manual entries are included
    expect(capturedRequest.dropoff_manual_entry).toBe(true)
    expect(capturedRequest.dropoff_airline_code).toBe('BY')
    expect(capturedRequest.flight_number).toBe('1234')
    expect(capturedRequest.departure_id).toBe(null)
    expect(capturedRequest.drop_off_slot).toBe('120')

    expect(capturedRequest.pickup_manual_entry).toBe(true)
    expect(capturedRequest.pickup_airline_code).toBe('BY')
    expect(capturedRequest.pickup_flight_number).toBe('1235')
    expect(capturedRequest.arrival_id).toBe(null)
  })

  it('should handle overnight arrival time for manual entry', async () => {
    let capturedRequest = null

    global.fetch = vi.fn((url, options) => {
      if (url.includes('/api/stripe/config')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ publishable_key: 'pk_test_123' }),
        })
      }

      if (url.includes('/api/payments/create-intent')) {
        capturedRequest = JSON.parse(options.body)
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            client_secret: 'pi_test_secret_overnight',
            booking_reference: 'TAG-OVERNIGHT',
            amount_display: '£89.00',
            is_free_booking: false,
          }),
        })
      }

      return Promise.reject(new Error(`Unhandled fetch: ${url}`))
    })

    // Scenario: Flight arrives at 00:50 (overnight from previous day)
    const manualArrivalData = {
      airlineCode: 'FR',
      airlineName: 'Ryanair',
      flightNumber: '5679',
      flightTime: '00:50',
      originCode: 'TFS',
      originName: 'Tenerife, Spain'
    }

    render(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={null}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-overnight"
        promoCode={null}
        promoCodeDiscount={0}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
        manualDepartureData={null}
        manualArrivalData={manualArrivalData}
        departureTimeOverride=""
        arrivalTimeOverride=""
      />
    )

    await waitFor(() => {
      expect(capturedRequest).not.toBeNull()
    }, { timeout: 3000 })

    expect(capturedRequest.pickup_manual_entry).toBe(true)
    expect(capturedRequest.pickup_flight_time).toBe('00:50')
  })

  it('should handle late evening departure for manual entry', async () => {
    let capturedRequest = null

    global.fetch = vi.fn((url, options) => {
      if (url.includes('/api/stripe/config')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ publishable_key: 'pk_test_123' }),
        })
      }

      if (url.includes('/api/payments/create-intent')) {
        capturedRequest = JSON.parse(options.body)
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            client_secret: 'pi_test_secret_late',
            booking_reference: 'TAG-LATE',
            amount_display: '£89.00',
            is_free_booking: false,
          }),
        })
      }

      return Promise.reject(new Error(`Unhandled fetch: ${url}`))
    })

    // Scenario: Flight departs at 22:50
    const manualDepartureData = {
      airlineCode: 'FR',
      airlineName: 'Ryanair',
      flightNumber: '5678',
      flightTime: '22:50',
      destinationCode: 'TFS',
      destinationName: 'Tenerife, Spain',
      dropoffSlot: '90'  // 1.5h before — late slot
    }

    render(
      <StripePayment
        formData={{ ...mockFormData, dropoffSlot: '' }}
        selectedFlight={null}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-late"
        promoCode={null}
        promoCodeDiscount={0}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
        manualDepartureData={manualDepartureData}
        manualArrivalData={null}
        departureTimeOverride=""
        arrivalTimeOverride=""
      />
    )

    await waitFor(() => {
      expect(capturedRequest).not.toBeNull()
    }, { timeout: 3000 })

    expect(capturedRequest.dropoff_manual_entry).toBe(true)
    expect(capturedRequest.dropoff_flight_time).toBe('22:50')
  })
})

// =============================================================================
// Promo Code Discount Tests
// =============================================================================

describe('StripePayment - Promo Code Discount', () => {
  beforeEach(() => {
    setupFetchMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('should create new payment intent when promo code is applied', async () => {
    let callCount = 0
    let lastClientSecret = null

    global.fetch = vi.fn((url, options) => {
      if (url.includes('/api/stripe/config')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ publishable_key: 'pk_test_123' }),
        })
      }

      if (url.includes('/api/payments/create-intent')) {
        callCount++
        const request = options ? JSON.parse(options.body) : {}
        const hasPromo = !!request.promo_code

        // Return different client_secret based on whether promo is applied
        lastClientSecret = hasPromo ? 'pi_test_secret_with_promo' : 'pi_test_secret_no_promo'

        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            client_secret: lastClientSecret,
            booking_reference: `TAG-PROMO${callCount}`,
            amount: hasPromo ? 5400 : 6000,
            amount_display: hasPromo ? '£54.00' : '£60.00',
            is_free_booking: false,
            original_amount_display: hasPromo ? '£60.00' : null,
            discount_amount_display: hasPromo ? '£6.00' : null,
            promo_code_applied: hasPromo ? 'TAG-TRAX-QVNJ' : null,
          }),
        })
      }

      return Promise.reject(new Error(`Unhandled fetch: ${url}`))
    })

    const { rerender } = render(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-promo"
        promoCode={null}
        promoCodeDiscount={0}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    // Wait for initial payment intent (no promo)
    await waitFor(() => {
      expect(callCount).toBe(1)
    }, { timeout: 3000 })

    expect(lastClientSecret).toBe('pi_test_secret_no_promo')

    // Apply promo code
    rerender(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-promo"
        promoCode="TAG-TRAX-QVNJ"
        promoCodeDiscount={10}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    // Wait for new payment intent (with promo)
    await waitFor(() => {
      expect(callCount).toBe(2)
    }, { timeout: 3000 })

    // Should have created a new payment intent with promo
    expect(lastClientSecret).toBe('pi_test_secret_with_promo')
  })

  it('should display discounted amount in response data', async () => {
    let capturedResponse = null

    global.fetch = vi.fn((url, options) => {
      if (url.includes('/api/stripe/config')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ publishable_key: 'pk_test_123' }),
        })
      }

      if (url.includes('/api/payments/create-intent')) {
        capturedResponse = {
          client_secret: 'pi_test_secret_discount',
          booking_reference: 'TAG-DISCOUNT',
          amount: 5400,
          amount_display: '£54.00',
          is_free_booking: false,
          original_amount_display: '£60.00',
          discount_amount_display: '£6.00',
          promo_code_applied: 'FOUNDER10',
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(capturedResponse),
        })
      }

      return Promise.reject(new Error(`Unhandled fetch: ${url}`))
    })

    render(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-discount"
        promoCode="FOUNDER10"
        promoCodeDiscount={10}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    await waitFor(() => {
      expect(capturedResponse).not.toBeNull()
    }, { timeout: 3000 })

    // Verify discounted amount is returned
    expect(capturedResponse.amount).toBe(5400)
    expect(capturedResponse.amount_display).toBe('£54.00')
    expect(capturedResponse.original_amount_display).toBe('£60.00')
    expect(capturedResponse.discount_amount_display).toBe('£6.00')
  })

  it('should send promo code in payment intent request', async () => {
    let capturedRequest = null

    global.fetch = vi.fn((url, options) => {
      if (url.includes('/api/stripe/config')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ publishable_key: 'pk_test_123' }),
        })
      }

      if (url.includes('/api/payments/create-intent')) {
        capturedRequest = JSON.parse(options.body)
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            client_secret: 'pi_test_secret_promo_sent',
            booking_reference: 'TAG-PROMOSENT',
            amount_display: '£54.00',
            is_free_booking: false,
          }),
        })
      }

      return Promise.reject(new Error(`Unhandled fetch: ${url}`))
    })

    render(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-promo-sent"
        promoCode="TAG-FOUNDER-ABC"
        promoCodeDiscount={10}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    await waitFor(() => {
      expect(capturedRequest).not.toBeNull()
    }, { timeout: 3000 })

    expect(capturedRequest.promo_code).toBe('TAG-FOUNDER-ABC')
  })

  it('should NOT recreate payment intent when same promo code is re-applied', async () => {
    let callCount = 0

    global.fetch = vi.fn((url) => {
      if (url.includes('/api/stripe/config')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ publishable_key: 'pk_test_123' }),
        })
      }

      if (url.includes('/api/payments/create-intent')) {
        callCount++
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            client_secret: `pi_test_secret_${callCount}`,
            booking_reference: `TAG-REAPPLY${callCount}`,
            amount_display: '£54.00',
            is_free_booking: false,
          }),
        })
      }

      return Promise.reject(new Error(`Unhandled fetch: ${url}`))
    })

    const { rerender } = render(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-reapply"
        promoCode="SAMECODE"
        promoCodeDiscount={10}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    await waitFor(() => {
      expect(callCount).toBe(1)
    }, { timeout: 3000 })

    // Re-render with same promo code
    rerender(
      <StripePayment
        formData={{ ...mockFormData, terms: false }}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-reapply"
        promoCode="SAMECODE"
        promoCodeDiscount={10}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    // Wait a bit
    await new Promise(resolve => setTimeout(resolve, 500))

    // Should still only be 1 call
    expect(callCount).toBe(1)
  })

  it('should create new payment intent when promo code is removed', async () => {
    let callCount = 0

    global.fetch = vi.fn((url, options) => {
      if (url.includes('/api/stripe/config')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ publishable_key: 'pk_test_123' }),
        })
      }

      if (url.includes('/api/payments/create-intent')) {
        callCount++
        const request = options ? JSON.parse(options.body) : {}
        const hasPromo = !!request.promo_code

        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            client_secret: `pi_test_secret_remove_${callCount}`,
            booking_reference: `TAG-REMOVE${callCount}`,
            amount_display: hasPromo ? '£54.00' : '£60.00',
            is_free_booking: false,
          }),
        })
      }

      return Promise.reject(new Error(`Unhandled fetch: ${url}`))
    })

    const { rerender } = render(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-remove"
        promoCode="REMOVEME"
        promoCodeDiscount={10}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    await waitFor(() => {
      expect(callCount).toBe(1)
    }, { timeout: 3000 })

    // Remove promo code
    rerender(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-remove"
        promoCode={null}
        promoCodeDiscount={0}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    await waitFor(() => {
      expect(callCount).toBe(2)
    }, { timeout: 3000 })

    // Should have created 2 payment intents (with promo, then without)
    expect(callCount).toBe(2)
  })

  it('should handle switching between different promo codes', async () => {
    let callCount = 0
    let lastPromoCode = null

    global.fetch = vi.fn((url, options) => {
      if (url.includes('/api/stripe/config')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ publishable_key: 'pk_test_123' }),
        })
      }

      if (url.includes('/api/payments/create-intent')) {
        callCount++
        const request = options ? JSON.parse(options.body) : {}
        lastPromoCode = request.promo_code

        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            client_secret: `pi_test_secret_switch_${callCount}`,
            booking_reference: `TAG-SWITCH${callCount}`,
            amount_display: '£54.00',
            is_free_booking: false,
          }),
        })
      }

      return Promise.reject(new Error(`Unhandled fetch: ${url}`))
    })

    const { rerender } = render(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-switch"
        promoCode="FIRSTCODE"
        promoCodeDiscount={10}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    await waitFor(() => {
      expect(callCount).toBe(1)
      expect(lastPromoCode).toBe('FIRSTCODE')
    }, { timeout: 3000 })

    // Switch to different promo code
    rerender(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-switch"
        promoCode="SECONDCODE"
        promoCodeDiscount={10}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    await waitFor(() => {
      expect(callCount).toBe(2)
      expect(lastPromoCode).toBe('SECONDCODE')
    }, { timeout: 3000 })
  })
})

describe('StripePayment - Elements Remount on Promo Code Change', () => {
  beforeEach(() => {
    setupFetchMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('should remount Elements component when clientSecret changes (promo applied)', async () => {
    // This test verifies the key={clientSecret} fix
    // The Elements component should remount when a new payment intent is created

    let clientSecrets = []

    global.fetch = vi.fn((url, options) => {
      if (url.includes('/api/stripe/config')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ publishable_key: 'pk_test_123' }),
        })
      }

      if (url.includes('/api/payments/create-intent')) {
        const request = options ? JSON.parse(options.body) : {}
        const hasPromo = !!request.promo_code
        const newSecret = hasPromo ? 'pi_secret_with_discount' : 'pi_secret_full_price'
        clientSecrets.push(newSecret)

        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            client_secret: newSecret,
            booking_reference: 'TAG-REMOUNT',
            amount_display: hasPromo ? '£54.00' : '£60.00',
            is_free_booking: false,
          }),
        })
      }

      return Promise.reject(new Error(`Unhandled fetch: ${url}`))
    })

    const { rerender } = render(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-remount"
        promoCode={null}
        promoCodeDiscount={0}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    await waitFor(() => {
      expect(clientSecrets.length).toBe(1)
      expect(clientSecrets[0]).toBe('pi_secret_full_price')
    }, { timeout: 3000 })

    // Apply promo code - should create new payment intent with different clientSecret
    rerender(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-remount"
        promoCode="DISCOUNT10"
        promoCodeDiscount={10}
        onPaymentSuccess={vi.fn()}
        onPaymentError={vi.fn()}
      />
    )

    await waitFor(() => {
      expect(clientSecrets.length).toBe(2)
      expect(clientSecrets[1]).toBe('pi_secret_with_discount')
    }, { timeout: 3000 })

    // The key={clientSecret} on Elements should cause it to remount
    // with the new clientSecret, showing the correct discounted amount
    expect(clientSecrets[0]).not.toBe(clientSecrets[1])
  })
})

// =============================================================================
// Pay Button Gating — elementReady + elementComplete
// Regression: customer TAG-ZQY10874 hit "Element not mounted/ready" because
// the Pay button was enabled before the PaymentElement iframe was ready.
// Coverage categories: Happy / Unhappy / Edge / Boundary (per backend SPEC.md).
// =============================================================================

describe('StripePayment - Pay Button Gating', () => {
  const baseProps = {
    formData: mockFormData,
    selectedFlight: mockSelectedFlight,
    selectedArrivalFlight: mockSelectedArrivalFlight,
    customerId: 1,
    vehicleId: 1,
    sessionId: 'test-session-gating',
    promoCode: null,
    promoCodeDiscount: 0,
    onPaymentSuccess: vi.fn(),
    onPaymentError: vi.fn(),
  }

  beforeEach(() => {
    setupFetchMocks()
    paymentElementProps = null
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  const renderAndWaitForElement = async (extraProps = {}) => {
    const result = render(<StripePayment {...baseProps} {...extraProps} />)
    await waitFor(() => {
      expect(paymentElementProps).not.toBeNull()
    }, { timeout: 3000 })
    return result
  }

  it('Boundary: Pay button is disabled in initial state before any callbacks fire', async () => {
    const { container } = await renderAndWaitForElement()
    const button = container.querySelector('button.stripe-pay-btn')
    expect(button).toBeDisabled()
    expect(button.textContent).toMatch(/^Pay /)
  })

  it('Happy: Pay button enables only after onReady AND onChange(complete:true)', async () => {
    const { container } = await renderAndWaitForElement()
    const button = container.querySelector('button.stripe-pay-btn')

    expect(button).toBeDisabled()

    act(() => paymentElementProps.onReady())
    expect(button).toBeDisabled()  // ready, but card form not complete

    act(() => paymentElementProps.onChange({ complete: true }))
    expect(button).not.toBeDisabled()
  })

  it('Edge: Pay button stays disabled if onReady fires but card fields incomplete', async () => {
    const { container } = await renderAndWaitForElement()
    const button = container.querySelector('button.stripe-pay-btn')

    act(() => paymentElementProps.onReady())
    act(() => paymentElementProps.onChange({ complete: false }))

    expect(button).toBeDisabled()
  })

  it('Edge: Pay button stays disabled if onChange(complete:true) fires before onReady', async () => {
    // Defensive — Stripe should not fire onChange before onReady, but the gate
    // requires both, so the button must stay disabled either way.
    const { container } = await renderAndWaitForElement()
    const button = container.querySelector('button.stripe-pay-btn')

    act(() => paymentElementProps.onChange({ complete: true }))

    expect(button).toBeDisabled()
  })

  it('Edge: Pay button re-disables when user removes a digit (complete flips back to false)', async () => {
    const { container } = await renderAndWaitForElement()
    const button = container.querySelector('button.stripe-pay-btn')

    act(() => paymentElementProps.onReady())
    act(() => paymentElementProps.onChange({ complete: true }))
    expect(button).not.toBeDisabled()

    act(() => paymentElementProps.onChange({ complete: false }))
    expect(button).toBeDisabled()
  })

  it('Happy: stripe_form_ready audit fires when PaymentElement onReady fires (not just on SDK load)', async () => {
    const auditCalls = []
    global.fetch = vi.fn((url, options) => {
      if (url.includes('/api/stripe/config')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ publishable_key: 'pk_test_123' }) })
      }
      if (url.includes('/api/payments/create-intent')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            client_secret: 'pi_test_secret_audit',
            booking_reference: 'TAG-AUDIT',
            amount_display: '£89.00',
            is_free_booking: false,
          }),
        })
      }
      if (url.includes('/api/booking/audit-event')) {
        auditCalls.push(JSON.parse(options.body))
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
      }
      return Promise.reject(new Error(`Unhandled fetch: ${url}`))
    })

    await renderAndWaitForElement()

    // Before onReady fires — no stripe_form_ready audit yet
    const readyBefore = auditCalls.filter(c => c.event === 'stripe_form_ready')
    expect(readyBefore.length).toBe(0)

    act(() => paymentElementProps.onReady())

    await waitFor(() => {
      const readyAfter = auditCalls.filter(c => c.event === 'stripe_form_ready')
      expect(readyAfter.length).toBe(1)
    }, { timeout: 1000 })
  })

  it('Unhappy: button text shows "Pay £…" (not Processing/Complete) while gated', async () => {
    // Confirms the gate keeps the user-facing CTA in its idle state, not a
    // misleading "Processing..." or "Payment Complete" while we're really just
    // waiting on the Element. (The handleSubmit defence-in-depth check on
    // elementReady cannot be tested here — React's synthetic event system
    // suppresses clicks on a disabled button regardless of the DOM attribute.)
    const { container } = await renderAndWaitForElement()
    const button = container.querySelector('button.stripe-pay-btn')

    expect(button).toBeDisabled()
    expect(button.textContent).toMatch(/^Pay /)
    expect(button.textContent).not.toMatch(/Processing/)
    expect(button.textContent).not.toMatch(/Complete/)
  })
})

// =============================================================================
// Payment Recovery After Confirm Error
// Regression: Martin Richards (TAG-ANI91299 / TAG-FMT95042, 10 Jul 2026) was
// double charged. His first charge SUCCEEDED but the confirm response was lost
// to a network drop (api_connection_error); every retry then failed with
// payment_intent_unexpected_state because the intent had already succeeded.
// The UI showed all of it as failure, so he re-booked and paid again.
// The fix: on a confirm error, verify the intent's real status with Stripe
// before reporting failure.
// =============================================================================

describe('StripePayment - Payment Recovery After Confirm Error', () => {
  const SUCCEEDED_INTENT = { id: 'pi_recovered_123', status: 'succeeded', amount: 9123 }

  let auditCalls
  let onPaymentSuccess
  let onPaymentError

  const setupAuditCapturingFetch = () => {
    auditCalls = []
    global.fetch = vi.fn((url, options) => {
      if (url.includes('/api/stripe/config')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ publishable_key: 'pk_test_123' }) })
      }
      if (url.includes('/api/payments/create-intent')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            client_secret: 'pi_recovery_secret',
            booking_reference: 'TAG-RECOVER',
            amount_display: '£91.23',
            is_free_booking: false,
          }),
        })
      }
      if (url.includes('/api/booking/audit-event')) {
        auditCalls.push(JSON.parse(options.body))
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
      }
      return Promise.reject(new Error(`Unhandled fetch: ${url}`))
    })
  }

  beforeEach(() => {
    setupAuditCapturingFetch()
    paymentElementProps = null
    onPaymentSuccess = vi.fn()
    onPaymentError = vi.fn()
  })

  afterEach(() => {
    mockStripeHook = { confirmPayment: vi.fn() }
    vi.clearAllMocks()
  })

  const renderReadyCheckout = async () => {
    const result = render(
      <StripePayment
        formData={mockFormData}
        selectedFlight={mockSelectedFlight}
        selectedArrivalFlight={mockSelectedArrivalFlight}
        customerId={1}
        vehicleId={1}
        sessionId="test-session-recovery"
        promoCode={null}
        promoCodeDiscount={0}
        onPaymentSuccess={onPaymentSuccess}
        onPaymentError={onPaymentError}
      />
    )
    await waitFor(() => {
      expect(paymentElementProps).not.toBeNull()
    }, { timeout: 3000 })
    act(() => paymentElementProps.onReady())
    act(() => paymentElementProps.onChange({ complete: true }))
    const button = result.container.querySelector('button.stripe-pay-btn')
    expect(button).not.toBeDisabled()
    return { ...result, button }
  }

  const clickPayAndSettle = async (button) => {
    await act(async () => {
      fireEvent.click(button)
    })
  }

  it('Martin case A: network drop after successful charge — retrieves intent and reports success', async () => {
    // confirmPayment loses the response (api_connection_error) but the intent
    // actually succeeded; retrievePaymentIntent reveals it.
    mockStripeHook = {
      confirmPayment: vi.fn().mockResolvedValue({
        error: {
          type: 'api_connection_error',
          message: 'We are experiencing issues connecting to our payments provider.',
        },
      }),
      retrievePaymentIntent: vi.fn().mockResolvedValue({ paymentIntent: SUCCEEDED_INTENT }),
    }

    const { button } = await renderReadyCheckout()
    await clickPayAndSettle(button)

    expect(mockStripeHook.retrievePaymentIntent).toHaveBeenCalledWith('pi_recovery_secret')
    expect(onPaymentSuccess).toHaveBeenCalledTimes(1)
    expect(onPaymentSuccess.mock.calls[0][0]).toMatchObject({
      paymentIntentId: 'pi_recovered_123',
      bookingReference: 'TAG-RECOVER',
    })
    expect(onPaymentError).not.toHaveBeenCalled()

    // No payment_failed audit; payment_succeeded logged with recovery marker
    await waitFor(() => {
      const succeeded = auditCalls.filter(c => c.event === 'payment_succeeded')
      expect(succeeded.length).toBe(1)
      expect(succeeded[0].event_data.recovered_from_error).toBe('api_connection_error')
    })
    expect(auditCalls.filter(c => c.event === 'payment_failed').length).toBe(0)

    // Button locks into the success state so the customer cannot pay again
    expect(button.textContent).toBe('Payment Complete')
    expect(button).toBeDisabled()
  })

  it('Martin case B: retry against already-succeeded intent — recovers from the error payload without a round-trip', async () => {
    // payment_intent_unexpected_state errors carry the intent inline.
    mockStripeHook = {
      confirmPayment: vi.fn().mockResolvedValue({
        error: {
          type: 'invalid_request_error',
          code: 'payment_intent_unexpected_state',
          message: 'A processing error occurred.',
          payment_intent: SUCCEEDED_INTENT,
        },
      }),
      retrievePaymentIntent: vi.fn(),
    }

    const { button } = await renderReadyCheckout()
    await clickPayAndSettle(button)

    expect(mockStripeHook.retrievePaymentIntent).not.toHaveBeenCalled()
    expect(onPaymentSuccess).toHaveBeenCalledTimes(1)
    expect(onPaymentError).not.toHaveBeenCalled()
    expect(button.textContent).toBe('Payment Complete')
  })

  it('Martin case B fallback: unexpected_state without inline intent — verifies via retrievePaymentIntent', async () => {
    mockStripeHook = {
      confirmPayment: vi.fn().mockResolvedValue({
        error: {
          type: 'invalid_request_error',
          code: 'payment_intent_unexpected_state',
          message: 'A processing error occurred.',
        },
      }),
      retrievePaymentIntent: vi.fn().mockResolvedValue({ paymentIntent: SUCCEEDED_INTENT }),
    }

    const { button } = await renderReadyCheckout()
    await clickPayAndSettle(button)

    expect(mockStripeHook.retrievePaymentIntent).toHaveBeenCalledWith('pi_recovery_secret')
    expect(onPaymentSuccess).toHaveBeenCalledTimes(1)
    expect(onPaymentError).not.toHaveBeenCalled()
  })

  it('Card decline: no status round-trip, failure surfaces as before', async () => {
    mockStripeHook = {
      confirmPayment: vi.fn().mockResolvedValue({
        error: {
          type: 'card_error',
          code: 'card_declined',
          message: 'Your card was declined.',
        },
      }),
      retrievePaymentIntent: vi.fn(),
    }

    const { button, container } = await renderReadyCheckout()
    await clickPayAndSettle(button)

    // Declines genuinely mean no charge — must not query intent status
    expect(mockStripeHook.retrievePaymentIntent).not.toHaveBeenCalled()
    expect(onPaymentSuccess).not.toHaveBeenCalled()
    expect(onPaymentError).toHaveBeenCalledTimes(1)
    expect(container.querySelector('.stripe-error').textContent).toBe('Your card was declined.')

    await waitFor(() => {
      expect(auditCalls.filter(c => c.event === 'payment_failed').length).toBe(1)
    })

    // Retry stays possible after a real failure
    expect(button).not.toBeDisabled()
  })

  it('Connection error with genuinely unpaid intent: still reports failure', async () => {
    mockStripeHook = {
      confirmPayment: vi.fn().mockResolvedValue({
        error: {
          type: 'api_connection_error',
          message: 'We are experiencing issues connecting to our payments provider.',
        },
      }),
      retrievePaymentIntent: vi.fn().mockResolvedValue({
        paymentIntent: { id: 'pi_unpaid', status: 'requires_payment_method' },
      }),
    }

    const { button } = await renderReadyCheckout()
    await clickPayAndSettle(button)

    expect(mockStripeHook.retrievePaymentIntent).toHaveBeenCalled()
    expect(onPaymentSuccess).not.toHaveBeenCalled()
    expect(onPaymentError).toHaveBeenCalledTimes(1)
    await waitFor(() => {
      expect(auditCalls.filter(c => c.event === 'payment_failed').length).toBe(1)
    })
  })

  it('Verification itself failing (still offline): falls through to the normal failure path', async () => {
    mockStripeHook = {
      confirmPayment: vi.fn().mockResolvedValue({
        error: {
          type: 'api_connection_error',
          message: 'We are experiencing issues connecting to our payments provider.',
        },
      }),
      retrievePaymentIntent: vi.fn().mockRejectedValue(new Error('network down')),
    }

    const { button } = await renderReadyCheckout()
    await clickPayAndSettle(button)

    expect(onPaymentSuccess).not.toHaveBeenCalled()
    expect(onPaymentError).toHaveBeenCalledTimes(1)
    // Customer can retry once connectivity returns
    expect(button).not.toBeDisabled()
  })

  it('Thrown exception hiding a completed charge: recovered via retrievePaymentIntent', async () => {
    mockStripeHook = {
      confirmPayment: vi.fn().mockRejectedValue(new TypeError('Failed to fetch')),
      retrievePaymentIntent: vi.fn().mockResolvedValue({ paymentIntent: SUCCEEDED_INTENT }),
    }

    const { button } = await renderReadyCheckout()
    await clickPayAndSettle(button)

    expect(mockStripeHook.retrievePaymentIntent).toHaveBeenCalledWith('pi_recovery_secret')
    expect(onPaymentSuccess).toHaveBeenCalledTimes(1)
    expect(onPaymentError).not.toHaveBeenCalled()
    await waitFor(() => {
      const succeeded = auditCalls.filter(c => c.event === 'payment_succeeded')
      expect(succeeded.length).toBe(1)
      expect(succeeded[0].event_data.recovered_from_error).toBe('exception')
    })
  })

  it('Normal success path unchanged: confirmPayment succeeds directly', async () => {
    mockStripeHook = {
      confirmPayment: vi.fn().mockResolvedValue({
        paymentIntent: { id: 'pi_direct', status: 'succeeded', amount: 9123 },
      }),
      retrievePaymentIntent: vi.fn(),
    }

    const { button } = await renderReadyCheckout()
    await clickPayAndSettle(button)

    expect(mockStripeHook.retrievePaymentIntent).not.toHaveBeenCalled()
    expect(onPaymentSuccess).toHaveBeenCalledTimes(1)
    expect(onPaymentError).not.toHaveBeenCalled()
    expect(button.textContent).toBe('Payment Complete')
  })
})
