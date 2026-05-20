/**
 * Asserts the StripePayment create-intent payload carries the canonical
 * `flight_arrival_date`. Backend uses this to disambiguate "the day the
 * customer landed" from "the day they pick the car up" — without it,
 * pickup_date alone carries both meanings and the 2026-05-19 / 2026-05-20
 * rollover incidents can reappear under a new bug.
 *
 * H/U/E/B coverage in one file (lightweight — the heavy lifting is in
 * backend/tests/mocked/test_flight_arrival_date.py):
 *   Happy    — standard pickup → flight_arrival_date == formData.pickupDate
 *   Unhappy  — no pickupDate set → still sends the key (server will validate)
 *   Edge     — overnight arrival flight (+1) keeps flight_arrival_date on the
 *              ORIGINAL landing day even though pickup_date rolls forward
 *   Boundary — late-evening 23:30 arrival (matches the backend boundary grid)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import StripePayment from '../components/StripePayment'

let paymentElementProps = null

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
  useStripe: () => ({ confirmPayment: vi.fn() }),
  useElements: () => ({}),
}))

const baseFormData = {
  firstName: 'Test',
  lastName: 'ArrivalDate',
  email: 'test@example.com',
  phone: '+447000000000',
  billingAddress1: '1 Test St',
  billingAddress2: '',
  billingCity: 'Bournemouth',
  billingCounty: '',
  billingPostcode: 'BH1 1AA',
  billingCountry: 'United Kingdom',
  registration: 'AB12CDE',
  make: 'Ford',
  model: 'Focus',
  colour: 'Blue',
  package: 'quick',
  dropoffDate: new Date(2026, 5, 16), // Tue 16 Jun 2026 (local; matches formatDateLocal output)
  pickupDate: new Date(2026, 5, 23),  // Tue 23 Jun 2026
  dropoffSlot: 'late',
  dropoffFlight: '10:30|PMI',
  terms: true,
}

const departureFlight = {
  id: 551,
  flightNumber: '3643',
  airlineCode: 'LS',
  time: '10:30',
  destinationCode: 'PMI',
}

let capturedBody = null

const installFetchCapture = () => {
  capturedBody = null
  global.fetch = vi.fn((url, opts) => {
    if (url.includes('/api/stripe/config')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ publishable_key: 'pk_test_123' }),
      })
    }
    if (url.includes('/api/payments/create-intent')) {
      capturedBody = JSON.parse(opts.body)
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          client_secret: 'pi_test_secret',
          booking_reference: 'TAG-TEST0001',
          amount_display: '£89.00',
          is_free_booking: false,
        }),
      })
    }
    return Promise.reject(new Error(`Unhandled fetch: ${url}`))
  })
}

const renderPayment = (overrides = {}) =>
  render(
    <StripePayment
      formData={overrides.formData || baseFormData}
      selectedFlight={departureFlight}
      selectedArrivalFlight={overrides.selectedArrivalFlight || { flightNumber: '3644', time: '17:30' }}
      manualArrivalData={overrides.manualArrivalData || null}
      manualDepartureData={null}
      customerId={1}
      vehicleId={1}
      sessionId="test-session-123"
      promoCode={null}
      promoCodeDiscount={0}
      onPaymentSuccess={vi.fn()}
      onPaymentError={vi.fn()}
    />
  )

describe('StripePayment create-intent payload — flight_arrival_date', () => {
  beforeEach(() => {
    paymentElementProps = null
    installFetchCapture()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  // Happy: typical daytime pickup, no overnight roll
  it('sends flight_arrival_date matching the pickupDate the customer selected', async () => {
    renderPayment()
    await waitFor(() => expect(capturedBody).not.toBeNull(), { timeout: 3000 })
    expect(capturedBody).toHaveProperty('flight_arrival_date')
    expect(capturedBody.flight_arrival_date).toBe('2026-06-23')
    expect(capturedBody.pickup_date).toBe('2026-06-23')
  })

  // Edge: overnight flag adds +1 to pickup_date, but the landing day didn't move
  it('keeps flight_arrival_date on the landing day even when overnight flight rolls pickup_date', async () => {
    renderPayment({
      selectedArrivalFlight: {
        flightNumber: '3644',
        time: '23:55',
        isOvernight: true,
      },
    })
    await waitFor(() => expect(capturedBody).not.toBeNull(), { timeout: 3000 })
    // pickup_date got rolled forward by one day …
    expect(capturedBody.pickup_date).toBe('2026-06-24')
    // … but the canonical arrival date is still the landing day
    expect(capturedBody.flight_arrival_date).toBe('2026-06-23')
  })

  // Boundary: 23:30 arrival is the exact moment the backend's +30min rollover
  // fires. Frontend sends both dates so the backend can audit the conflation.
  it('sends both pickup_date and flight_arrival_date at the 23:30 boundary', async () => {
    renderPayment({
      manualArrivalData: {
        flightTime: '23:30',
        flightNumber: '3644',
        airlineCode: 'LS',
        airlineName: 'Jet2',
        originCode: 'TFS',
        originName: 'Tenerife',
      },
      selectedArrivalFlight: null,
    })
    await waitFor(() => expect(capturedBody).not.toBeNull(), { timeout: 3000 })
    expect(capturedBody).toHaveProperty('flight_arrival_date', '2026-06-23')
    expect(capturedBody.pickup_date).toBe('2026-06-23')
    expect(capturedBody.pickup_flight_time).toBe('23:30')
    expect(capturedBody.flight_arrival_time).toBe('23:30')
  })

  // Unhappy: pickupDate missing → frontend still sends the key (as null/derived);
  // server is the source of truth for required-field validation.
  it('still includes flight_arrival_date in the payload shape when pickupDate is null', async () => {
    renderPayment({
      formData: { ...baseFormData, pickupDate: null },
    })
    await waitFor(() => expect(capturedBody).not.toBeNull(), { timeout: 3000 })
    expect(Object.prototype.hasOwnProperty.call(capturedBody, 'flight_arrival_date')).toBe(true)
  })
})
