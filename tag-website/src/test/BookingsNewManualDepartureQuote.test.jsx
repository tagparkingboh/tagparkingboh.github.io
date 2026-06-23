/**
 * Regression: the BOH airport-quote request must fire in the MANUAL departure
 * flow with `entryTime` taken from the manual drop-off slot — even when the
 * normal flight-picker `formData.dropoffSlot` is empty.
 *
 * The fetch uses `effectiveDropoffTime = dropoffTime || manualDropoffTime`
 * (BookingsNew.jsx). If that fallback ever breaks, the manual flow would send
 * a null entryTime and the quote would silently never fire. `showManualDeparture`
 * defaults to true, so seeding sessionStorage lands the component straight in
 * the manual flow on mount; the quote useEffect then fires.
 *
 * manual flightTime 14:00 with the "2 hours before" slot ('120') => drop-off
 * 12:00, which must be the entryTime sent to /api/airport-parking/quote.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import BookingsNew from '../BookingsNew'

let capturedQuoteBody = null

function installFetch(quotePayload = {}) {
  capturedQuoteBody = null
  global.fetch = vi.fn((url, opts) => {
    const u = String(url)
    if (u.includes('/api/airport-parking/quote')) {
      capturedQuoteBody = JSON.parse(opts.body)
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          tagPrice: 99.0,
          tagPricePence: 9900,
          pricingInfo: { price: 99.0, price_pence: 9900, duration_days: 7, week1_price: 108.0 },
          airportPrices: [],
          billing_days: 7,
          source: 'live',
          quotedAt: '2026-06-22T12:00:00Z',
          ...quotePayload,
        }),
      })
    }
    // List endpoints expect arrays; everything else an object. Nothing else is
    // load-bearing for this assertion — we only need a clean mount.
    const arrayEndpoints = [
      '/api/booking/destinations', '/api/booking/airlines',
      '/api/flights/arrivals', '/api/flights/departures',
      '/api/blocked-dates/check', '/api/capacity/daily',
    ]
    const body = arrayEndpoints.some((e) => u.includes(e)) ? [] : {}
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) })
  })
}

function seedManualDepartureScenario() {
  sessionStorage.clear()
  // Future dates (today is 2026-06-22) so BookingsNew doesn't clear past dates.
  sessionStorage.setItem('booking_formData', JSON.stringify({
    dropoffDate: '2026-12-15',
    pickupDate: '2026-12-22',
    dropoffSlot: '',          // normal flight-picker slot EMPTY -> must fall back to manual
    dropoffAirline: '',
  }))
  sessionStorage.setItem('booking_manualDepartureData', JSON.stringify({
    flightTime: '14:00',
    dropoffSlot: '120',       // "2 hours before" -> 12:00
    destinationName: 'Alicante',
    destinationCode: 'ALC',
    customDestination: '',
    airlineName: 'Jet2',
  }))
  sessionStorage.setItem('booking_manualArrivalData', JSON.stringify({
    flightTime: '18:00',      // arrival present -> pickup time derivable
  }))
}

describe('BookingsNew — airport quote fires from the manual departure flow', () => {
  beforeEach(() => {
    installFetch()
    seedManualDepartureScenario()
  })

  afterEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
  })

  it('POSTs /api/airport-parking/quote with entryTime = the manual slot time (flightTime - 120m)', async () => {
    render(
      <MemoryRouter>
        <BookingsNew />
      </MemoryRouter>
    )

    await waitFor(() => expect(capturedQuoteBody).not.toBeNull(), { timeout: 5000 })

    // The regression target: manual slot drives entryTime even with empty formData.dropoffSlot.
    expect(capturedQuoteBody.entryTime).toBe('12:00')
    expect(typeof capturedQuoteBody.entryDate).toBe('string')
  })

  it('shows floored per-product cheaper pills against the current TAG quote', async () => {
    installFetch({
      tagPrice: 117.6,
      tagPricePence: 11760,
      pricingInfo: { price: 117.6, price_pence: 11760, duration_days: 7, week1_price: 108.0 },
      airportPrices: [
        { name: 'Car Park 3', pricePence: 16800, priceText: '£168.00' },
        { name: 'Car Park 1', pricePence: 19000, priceText: '£190.00' },
      ],
    })
    sessionStorage.setItem('booking_step', JSON.stringify(2))

    render(
      <MemoryRouter>
        <BookingsNew />
      </MemoryRouter>
    )

    await waitFor(() => expect(capturedQuoteBody).not.toBeNull(), { timeout: 5000 })

    expect(await screen.findByText('30% cheaper')).toBeInTheDocument()
    expect(screen.getByText('38% cheaper')).toBeInTheDocument()
    expect(screen.queryByText('0% cheaper')).not.toBeInTheDocument()
  })
})
