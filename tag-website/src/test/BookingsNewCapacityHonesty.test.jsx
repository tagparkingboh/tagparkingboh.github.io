/**
 * Capacity honesty: hard "Sorry, we're full" states must be driven by the
 * through-count (cars parked straight across the day) while the advisory
 * amber/red busy warning stays on the touching count.
 *
 * Background (2026-07-02): prod Sat 04/07 had 80 bookings TOUCHING the day
 * (= cap) but only 68 concurrent cars — customers were told "we're full
 * between 4 July and 6 August" for a stay that physically fit. The fix
 * feeds a second map (daily_through_occupancy) from /api/capacity/daily
 * and reserves the full banners for through-count-at-cap days; the
 * stay-span banner now names the offending day instead of blaming the
 * whole range.
 *
 * Render-based (pattern from BookingsNewManualDepartureQuote.test.jsx):
 * seed sessionStorage, mock fetch, mount BookingsNew, assert on the DOM.
 * Dates are computed relative to "today" so lead-time gates always pass.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { format, addDays } from 'date-fns'
import BookingsNew from '../BookingsNew'

const CAP = 80

// Stay window: far enough out that lead-time rules never interfere.
const DROPOFF = addDays(new Date(), 30)
const MIDDLE = addDays(new Date(), 31)
const PICKUP = addDays(new Date(), 32)

const iso = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

function capacityBody({ occupancy = {}, through = {}, timeAwareGate = true }) {
  const capMap = {}
  for (const key of [...Object.keys(occupancy), ...Object.keys(through)]) {
    capMap[key] = { online_spaces: CAP, total_spaces: CAP + 2, manual_spaces: 2 }
  }
  return {
    daily_occupancy: occupancy,
    daily_through_occupancy: through,
    // These suites pin the flag-ON behaviour: the backend echoes its
    // CAPACITY_GATE_TIME_AWARE flag here, and the frontend only relaxes
    // hard blocks to the through-count while it's true (reviewer fix —
    // keeps banner and create-intent 400 in agreement during rollout).
    time_aware_gate: timeAwareGate,
    daily_capacity: capMap,
    online_capacity: CAP,
    total_capacity: CAP + 2,
    manual_capacity: 2,
    max_capacity: CAP,
  }
}

function installFetch({ occupancy = {}, through = {}, timeAwareGate = true }) {
  global.fetch = vi.fn((url) => {
    const u = String(url)
    if (u.includes('/api/capacity/daily')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(capacityBody({ occupancy, through, timeAwareGate })),
      })
    }
    const arrayEndpoints = [
      '/api/booking/destinations', '/api/booking/airlines',
      '/api/flights/arrivals', '/api/flights/departures',
      '/api/blocked-dates/check',
    ]
    const body = arrayEndpoints.some((e) => u.includes(e)) ? [] : {}
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) })
  })
}

function seedDates({ withPickup = true } = {}) {
  sessionStorage.clear()
  // 'YYYY-MM-DDT00:00:00' (no Z) parses as LOCAL midnight — a bare
  // 'YYYY-MM-DD' parses as UTC and shifts a day in non-UTC zones, which
  // would desync the formData dates from the occupancy map keys.
  sessionStorage.setItem('booking_formData', JSON.stringify({
    dropoffDate: `${iso(DROPOFF)}T00:00:00`,
    ...(withPickup ? { pickupDate: `${iso(PICKUP)}T00:00:00` } : {}),
    dropoffSlot: '',
    dropoffAirline: '',
  }))
  if (withPickup) {
    // The Return Flight section (home of the stay-span banner) only
    // renders once a departure slot exists — seed the manual flow like
    // BookingsNewManualDepartureQuote.test.jsx does.
    sessionStorage.setItem('booking_manualDepartureData', JSON.stringify({
      flightTime: '14:00',
      dropoffSlot: '120',
      destinationName: 'Alicante',
      destinationCode: 'ALC',
      customDestination: '',
      airlineName: 'Jet2',
    }))
  }
}

function mount() {
  return render(
    <MemoryRouter>
      <BookingsNew />
    </MemoryRouter>
  )
}

afterEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
})

describe('BookingsNew — hard blocks come from the through-count', () => {
  it('through-full drop-off day shows the "Sorry, we\'re full" banner', async () => {
    installFetch({
      occupancy: { [iso(DROPOFF)]: CAP },
      through: { [iso(DROPOFF)]: CAP },
    })
    seedDates({ withPickup: false })
    mount()

    await waitFor(() => {
      expect(
        screen.getByText(new RegExp(`Sorry, we're full on ${format(DROPOFF, 'EEEE d MMMM yyyy')}`))
      ).toBeInTheDocument()
    })
    // A genuinely-full day gets the hard banner ONLY — the advisory busy
    // modal must skip it (its skip condition follows hardFullOccupancy).
    expect(screen.queryByText("We're getting full")).not.toBeInTheDocument()
  })

  it('touch-at-cap but through-open day shows NO full banner (the 04/07 prod shape)', async () => {
    installFetch({
      occupancy: { [iso(DROPOFF)]: CAP },   // 80 touching = cap
      through: { [iso(DROPOFF)]: 68 },      // 68 through < cap → NOT full
    })
    seedDates({ withPickup: false })
    mount()

    // The busy modal (advisory) appears instead of any hard banner.
    await waitFor(() => {
      expect(screen.getByText("We're getting full")).toBeInTheDocument()
    })
    expect(screen.queryByText(/Sorry, we're full/)).not.toBeInTheDocument()
  })

  it('same shape with time_aware_gate=false keeps the legacy hard banner (rollout coupling)', async () => {
    // Reviewer fix: while the backend gate runs per-day (flag off), the
    // frontend must NOT relax to the through-count — otherwise the customer
    // passes the banner and dead-ends on the create-intent 400.
    installFetch({
      occupancy: { [iso(DROPOFF)]: CAP },
      through: { [iso(DROPOFF)]: 68 },
      timeAwareGate: false,
    })
    seedDates({ withPickup: false })
    mount()

    await waitFor(() => {
      expect(screen.getByText(/Sorry, we're full/)).toBeInTheDocument()
    })
    expect(screen.queryByText("We're getting full")).not.toBeInTheDocument()
  })

  it('stay-span banner names the offending middle day, not the whole range', async () => {
    installFetch({
      occupancy: { [iso(MIDDLE)]: CAP },
      through: { [iso(MIDDLE)]: CAP },      // middle day genuinely full
    })
    seedDates({ withPickup: true })
    mount()

    await waitFor(() => {
      expect(
        screen.getByText(new RegExp(`Sorry, we're full on ${format(MIDDLE, 'EEEE d MMMM yyyy')}, which falls within your selected stay`))
      ).toBeInTheDocument()
    })
    // The old phrasing blamed the whole dropoff–pickup range.
    expect(
      screen.queryByText(new RegExp(`between ${format(DROPOFF, 'EEEE d MMMM yyyy')}`))
    ).not.toBeInTheDocument()
  })

  it('through-full middle day does not fire when only touch-full (turnover straddle passes)', async () => {
    installFetch({
      occupancy: { [iso(MIDDLE)]: CAP + 3 },  // heavy turnover, touching > cap
      through: { [iso(MIDDLE)]: 61 },
    })
    seedDates({ withPickup: true })
    mount()

    // Give effects a tick; no hard banner may appear.
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled()
    })
    expect(screen.queryByText(/Sorry, we're full/)).not.toBeInTheDocument()
  })
})

describe('BookingsNew — busy warning modal stays on the touching count', () => {
  it('amber band (85%) fires with the spaces-left line', async () => {
    installFetch({
      occupancy: { [iso(DROPOFF)]: 68 },   // 68/80 = 85%
      through: { [iso(DROPOFF)]: 50 },
    })
    seedDates({ withPickup: false })
    mount()

    await waitFor(() => {
      expect(screen.getByText("We're getting full")).toBeInTheDocument()
    })
    expect(screen.getByText('85%')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument() // 80 − 68 spaces left
    expect(screen.getByText(/spaces left/)).toBeInTheDocument()
  })

  it('below the 80% band no modal fires', async () => {
    installFetch({
      occupancy: { [iso(DROPOFF)]: 63 },   // 63/80 = 79%
      through: { [iso(DROPOFF)]: 50 },
    })
    seedDates({ withPickup: false })
    mount()

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled()
    })
    expect(screen.queryByText("We're getting full")).not.toBeInTheDocument()
  })

  it('touch over cap clamps the percent at 100 and hides the spaces-left line', async () => {
    installFetch({
      occupancy: { [iso(DROPOFF)]: CAP + 4 },  // 84 touching → 105% raw
      through: { [iso(DROPOFF)]: 60 },         // but not actually full
    })
    seedDates({ withPickup: false })
    mount()

    await waitFor(() => {
      expect(screen.getByText("We're getting full")).toBeInTheDocument()
    })
    expect(screen.getByText('100%')).toBeInTheDocument()
    expect(screen.queryByText('105%')).not.toBeInTheDocument()
    expect(screen.queryByText(/spaces left/)).not.toBeInTheDocument()
    // Still dismissible — it's advisory, not a block.
    expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument()
  })

  it('boundary: exactly 80% fires amber, 90% fires red', async () => {
    installFetch({
      occupancy: { [iso(DROPOFF)]: 64 },  // 64/80 = exactly 80%
      through: { [iso(DROPOFF)]: 40 },
    })
    seedDates({ withPickup: false })
    const { unmount } = mount()
    await waitFor(() => {
      expect(screen.getByText("We're getting full")).toBeInTheDocument()
    })
    expect(document.querySelector('.busy-warning-modal--amber')).not.toBeNull()
    unmount()

    installFetch({
      occupancy: { [iso(DROPOFF)]: 72 },  // 72/80 = exactly 90%
      through: { [iso(DROPOFF)]: 40 },
    })
    seedDates({ withPickup: false })
    mount()
    await waitFor(() => {
      expect(screen.getByText("We're getting full")).toBeInTheDocument()
    })
    expect(document.querySelector('.busy-warning-modal--red')).not.toBeNull()
  })
})
