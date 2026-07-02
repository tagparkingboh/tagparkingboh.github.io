/**
 * Regression: overlapping airport-quote fetches must not let a STALE response
 * win. Rapid time edits fire the quote useEffect repeatedly; before the
 * AbortController guard, whichever response landed last set pricingInfo —
 * even if it belonged to old inputs. Payment then sent current form times
 * with the stale snapshot id and the backend 400'd with "Airport quote no
 * longer matches your booking" (live incidents 2026-07-02, sessions
 * sess_1782986473371_rnzlb8hbl / sess_1782991984701_142qx121g — snapshots
 * 890/891 landed 0.5s apart with different exit times).
 *
 * The test holds every quote response unresolved, changes the arrival time to
 * fire a second fetch, then resolves the NEW response first and the OLD one
 * last. The superseded run must be aborted and its late response discarded.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import BookingsNew from '../BookingsNew'

let quoteCalls = []

function quoteResponse(pricePence) {
  return {
    ok: true,
    json: () => Promise.resolve({
      tagPrice: pricePence / 100,
      tagPricePence: pricePence,
      pricingInfo: {
        price: pricePence / 100,
        price_pence: pricePence,
        duration_days: 7,
        week1_price: 108.0,
        airport_quote_snapshot_id: pricePence, // distinct per response
      },
      airportPrices: [],
      billing_days: 7,
      source: 'live',
      quotedAt: '2026-06-22T12:00:00Z',
    }),
  }
}

function installFetch() {
  quoteCalls = []
  global.fetch = vi.fn((url, opts) => {
    const u = String(url)
    if (u.includes('/api/airport-parking/quote')) {
      // Hold the response until the test resolves it explicitly.
      return new Promise((resolve) => {
        quoteCalls.push({
          body: JSON.parse(opts.body),
          signal: opts.signal,
          respond: (pricePence) => resolve(quoteResponse(pricePence)),
        })
      })
    }
    const arrayEndpoints = [
      '/api/booking/destinations', '/api/booking/airlines',
      '/api/flights/arrivals', '/api/flights/departures',
      '/api/blocked-dates/check', '/api/capacity/daily',
    ]
    const body = arrayEndpoints.some((e) => u.includes(e)) ? [] : {}
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) })
  })
}

function seedManualScenario() {
  sessionStorage.clear()
  sessionStorage.setItem('booking_formData', JSON.stringify({
    dropoffDate: '2026-12-15',
    pickupDate: '2026-12-22',
    dropoffSlot: '',
    dropoffAirline: '',
  }))
  sessionStorage.setItem('booking_manualDepartureData', JSON.stringify({
    flightTime: '14:00',
    dropoffSlot: '120',
    destinationName: 'Alicante',
    destinationCode: 'ALC',
    customDestination: '',
    airlineName: 'Jet2',
  }))
  sessionStorage.setItem('booking_manualArrivalData', JSON.stringify({
    flightTime: '18:00',
  }))
}

describe('BookingsNew — stale quote responses cannot overwrite the fresh one', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
    sessionStorage.clear()
  })

  it('aborts the superseded fetch and keeps the freshest pricingInfo', async () => {
    installFetch()
    seedManualScenario()

    const { container } = render(
      <MemoryRouter>
        <BookingsNew />
      </MemoryRouter>
    )

    await waitFor(() => expect(quoteCalls.length).toBeGreaterThanOrEqual(1), { timeout: 5000 })
    const initialCount = quoteCalls.length

    // Switch the drop-off slot (120 -> 90 min before the 14:00 flight):
    // quote effect re-runs with entryTime 12:30 -> new fetch.
    const lateSlot = container.querySelector('input[name="manualDropoffSlot"][value="90"]')
    expect(lateSlot).not.toBeNull()
    fireEvent.click(lateSlot)

    await waitFor(() => expect(quoteCalls.length).toBeGreaterThan(initialCount), { timeout: 5000 })
    expect(quoteCalls[quoteCalls.length - 1].body.entryTime).toBe('12:30')

    // Every superseded run must have been aborted by the effect cleanup.
    const superseded = quoteCalls.slice(0, -1)
    const fresh = quoteCalls[quoteCalls.length - 1]
    expect(superseded.every((c) => c.signal?.aborted)).toBe(true)
    expect(fresh.signal?.aborted).toBe(false)

    // Resolve the FRESH request first (£99.00), then the STALE ones (£55.00).
    fresh.respond(9900)
    await waitFor(() =>
      expect(JSON.parse(sessionStorage.getItem('booking_pricingInfo'))?.price).toBe(99)
    )
    superseded.forEach((c) => c.respond(5500))

    // The stale £55 responses landed last but must be discarded.
    await new Promise((r) => setTimeout(r, 50))
    expect(JSON.parse(sessionStorage.getItem('booking_pricingInfo'))?.price).toBe(99)
    expect(JSON.parse(sessionStorage.getItem('booking_pricingInfo'))?.airport_quote_snapshot_id).toBe(9900)
  })
})
