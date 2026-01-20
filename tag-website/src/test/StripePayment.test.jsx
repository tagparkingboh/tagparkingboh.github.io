/**
 * Tests for StripePayment component - specifically testing that payment intents
 * are only created ONCE, preventing duplicate bookings from re-renders.
 *
 * This addresses the bug where David Thomson had 10 pending bookings created
 * because the useEffect was re-running on every formData change.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import StripePayment from '../components/StripePayment'

// Mock Stripe
vi.mock('@stripe/stripe-js', () => ({
  loadStripe: vi.fn(() => Promise.resolve({
    elements: vi.fn(),
    confirmPayment: vi.fn(),
  })),
}))

vi.mock('@stripe/react-stripe-js', () => ({
  Elements: ({ children }) => <div data-testid="stripe-elements">{children}</div>,
  PaymentElement: () => <div data-testid="payment-element">Payment Element</div>,
  useStripe: () => ({
    confirmPayment: vi.fn(),
  }),
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
