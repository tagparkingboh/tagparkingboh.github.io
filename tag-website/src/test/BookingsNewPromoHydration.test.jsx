/**
 * HUEB regression: after Stripe asks for a page refresh, older sessions can
 * restore FREEWEEK as discount=100 with the default percentage type. The
 * booking page must rehydrate the real backend discount_type before mounting
 * StripePayment, otherwise a 7d+1m airport quote becomes a free booking.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import BookingsNew from '../BookingsNew'

let stripeProps = null
let validateCalls = 0

vi.mock('../components/StripePayment', () => ({
  default: (props) => {
    stripeProps = props
    return <div data-testid="stripe-payment">Stripe payment</div>
  },
}))

function seedStaleFreeWeekRefreshState() {
  sessionStorage.clear()
  sessionStorage.setItem('booking_step', JSON.stringify(4))
  sessionStorage.setItem('booking_customerId', JSON.stringify(42))
  sessionStorage.setItem('booking_vehicleId', JSON.stringify(7))
  sessionStorage.setItem('booking_savedEmail', JSON.stringify('qa.orca.contact@gmail.com'))
  sessionStorage.setItem('booking_heardAboutUsAnswered', JSON.stringify(true))
  sessionStorage.setItem('booking_promoCode', JSON.stringify('FREEWEEK'))
  sessionStorage.setItem('booking_promoCodeValid', JSON.stringify(true))
  sessionStorage.setItem('booking_promoCodeMessage', JSON.stringify('Promo code applied'))
  sessionStorage.setItem('booking_promoCodeDiscount', JSON.stringify(100))
  sessionStorage.setItem('booking_promoCodeType', JSON.stringify('percentage'))
  sessionStorage.setItem('booking_pricingInfo', JSON.stringify({
    price: 108,
    price_pence: 10800,
    duration_days: 8,
    week1_price: 60,
    airport_quote_snapshot_id: 365,
  }))
  sessionStorage.setItem('booking_airportQuote', JSON.stringify({
    quoteId: 365,
    tagPricePence: 10800,
    billing_days: 8,
  }))
  sessionStorage.setItem('booking_formData', JSON.stringify({
    dropoffDate: '2026-08-03T00:00:00.000Z',
    pickupDate: '2026-08-10T00:00:00.000Z',
    dropoffAirline: 'U2',
    dropoffFlight: '12:00|AQ340',
    dropoffSlot: '120',
    pickupFlightTime: '09:31|AQ341',
    registration: 'AA19MOT',
    make: 'Audi',
    colour: 'White',
    firstName: 'Mark',
    lastName: 'Testing',
    email: 'qa.orca.contact@gmail.com',
    phone: '+447700900123',
    package: 'airport_quote',
    billingAddress1: '1 Test Street',
    billingCity: 'Bournemouth',
    billingPostcode: 'BH1 1AA',
    billingCountry: 'United Kingdom',
    terms: true,
  }))
  sessionStorage.setItem('booking_manualDepartureData', JSON.stringify({
    flightTime: '12:00',
    dropoffSlot: '120',
    airlineCode: 'U2',
    airlineName: 'easyJet',
    destinationCode: 'PMI',
    destinationName: 'Palma',
  }))
  sessionStorage.setItem('booking_manualArrivalData', JSON.stringify({
    flightTime: '09:31',
    airlineCode: 'U2',
    airlineName: 'easyJet',
    originCode: 'PMI',
    originName: 'Palma',
  }))
}

function installFetchMocks() {
  validateCalls = 0
  global.fetch = vi.fn((url, opts) => {
    const u = String(url)
    if (u.includes('/api/promo/validate')) {
      validateCalls += 1
      expect(JSON.parse(opts.body)).toEqual({ code: 'FREEWEEK' })
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          valid: true,
          discount_percent: 100,
          discount_type: 'free_week',
          message: '1 Week Free Parking',
        }),
      })
    }
    if (u.includes('/api/airport-parking/quote')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          quoteId: 365,
          tagPrice: 108,
          tagPricePence: 10800,
          billing_days: 8,
          pricingInfo: {
            price: 108,
            price_pence: 10800,
            duration_days: 8,
            week1_price: 60,
            airport_quote_snapshot_id: 365,
          },
          airportPrices: [{ name: 'BOH', pricePence: 13500 }],
        }),
      })
    }

    const arrayEndpoints = [
      '/api/booking/destinations',
      '/api/booking/airlines',
      '/api/flights/arrivals',
      '/api/flights/departures',
      '/api/blocked-dates/check',
      '/api/capacity/daily',
    ]
    const body = arrayEndpoints.some((endpoint) => u.includes(endpoint)) ? [] : {}
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) })
  })
}

describe('BookingsNew - stale FREEWEEK refresh hydration', () => {
  beforeEach(() => {
    stripeProps = null
    seedStaleFreeWeekRefreshState()
    installFetchMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
  })

  it('rehydrates discount_type before mounting StripePayment for an 8 billing-day FREEWEEK quote', async () => {
    render(
      <MemoryRouter>
        <BookingsNew />
      </MemoryRouter>
    )

    expect(screen.getByText('Loading secure payment...')).toBeInTheDocument()

    await waitFor(() => {
      expect(stripeProps?.promoCodeType).toBe('free_week')
    }, { timeout: 5000 })

    expect(validateCalls).toBe(1)
    expect(stripeProps.promoCode).toBe('FREEWEEK')
    expect(stripeProps.promoCodeDiscount).toBe(100)
    expect(stripeProps.pricingInfo.duration_days).toBe(8)
    expect(screen.getAllByText('1 Week Free Parking').length).toBeGreaterThan(0)
    expect(screen.getAllByText('£48.00').length).toBeGreaterThan(0)
  })
})
