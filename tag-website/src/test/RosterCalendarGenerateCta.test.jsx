import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import RosterCalendar, { isPastDateKeyUK } from '../components/RosterCalendar'

const mockAuthFetch = vi.hoisted(() => vi.fn())

vi.mock('../AuthContext', () => ({
  useAuth: () => ({ authFetch: mockAuthFetch }),
}))

const makeJsonResponse = (body, ok = true, status = 200) => ({
  ok,
  status,
  json: async () => body,
})

const jsonResponse = (body, ok = true, status = 200) => Promise.resolve(makeJsonResponse(body, ok, status))

const missingBooking = {
  id: 2401,
  reference: 'TAG-GATE2401',
  status: 'confirmed',
  service_type: 'meet_greet',
  customer_first_name: 'Gate',
  customer_last_name: 'Case',
  dropoff_date: '2026-06-24',
  dropoff_time: '10:40',
  dropoff_flight_number: 'FR123',
  dropoff_destination: 'Murcia Airport',
  pickup_date: null,
  pickup_time: null,
}

const allowedGate = {
  date: '2026-06-24',
  missing_review_count: 1,
  blocked_by_suppressed: false,
  suppressed_blocker_count: 0,
  suppressed_shift_ids: [],
  suppressed_booking_references: [],
  can_generate_roster: true,
  missing_events: [{
    booking_id: 2401,
    booking_reference: 'TAG-GATE2401',
    event_type: 'drop_off',
    event_time: '10:40',
    customer_name: 'Gate Case',
    flight_number: 'FR123',
    destination: 'Murcia Airport',
  }],
}

const blockedGate = {
  ...allowedGate,
  blocked_by_suppressed: true,
  suppressed_blocker_count: 1,
  suppressed_shift_ids: [5422],
  suppressed_booking_references: ['TAG-GATE2401'],
  can_generate_roster: false,
}

const pastBooking = {
  ...missingBooking,
  id: 2402,
  reference: 'TAG-PAST2402',
  customer_first_name: 'Past',
  customer_last_name: 'Case',
  dropoff_date: '2026-06-01',
  dropoff_time: '03:45',
  dropoff_flight_number: 'FR456',
  dropoff_destination: 'Alicante Airport',
}

const pastGate = {
  ...allowedGate,
  date: '2026-06-01',
  missing_events: [{
    booking_id: 2402,
    booking_reference: 'TAG-PAST2402',
    event_type: 'drop_off',
    event_time: '03:45',
    customer_name: 'Past Case',
    flight_number: 'FR456',
    destination: 'Alicante Airport',
  }],
}

const gateRangeResponse = (gates) => ({
  date_from: '2026-06-01',
  date_to: '2026-06-30',
  gates,
})

const setupApi = ({
  gate = allowedGate,
  gates,
  bookings = [missingBooking],
  reviewGatesResponse = null,
} = {}) => {
  const generateCalls = []
  const monthGates = gates || [gate]
  mockAuthFetch.mockImplementation((url, options = {}) => {
    const requestUrl = String(url)

    if (requestUrl.includes('/api/admin/bookings')) {
      return jsonResponse({ bookings })
    }
    if (requestUrl.includes('/api/roster?')) {
      return jsonResponse([])
    }
    if (requestUrl.includes('/api/admin/roster/review-generate-gates')) {
      return reviewGatesResponse || jsonResponse(gateRangeResponse(monthGates))
    }
    if (requestUrl.includes('/api/admin/roster/review-generate-gate')) {
      return jsonResponse(gate)
    }
    if (requestUrl.includes('/api/admin/roster/generate-date')) {
      generateCalls.push({ url: requestUrl, options })
      return jsonResponse({
        date: '2026-06-24',
        deleted: 0,
        created: 1,
        bookings_processed: 1,
        dates_covered: 1,
        before_gate: gate,
        after_gate: { ...gate, missing_review_count: 0, can_generate_roster: false },
      })
    }
    if (requestUrl.includes('/api/admin/blocked-dates')) {
      return jsonResponse({ blocked_dates: [] })
    }
    if (requestUrl.includes('/api/capacity/daily')) {
      return jsonResponse({ daily_occupancy: {} })
    }
    if (requestUrl.includes('/api/holidays')) {
      return jsonResponse([])
    }
    if (requestUrl.includes('/api/staff')) {
      return jsonResponse([])
    }
    if (requestUrl.includes('/api/roster/monthly-hours')) {
      return jsonResponse({ employees: [] })
    }

    return jsonResponse({})
  })
  return { generateCalls }
}

const getCalendarDayCell = (dayNumber) => Array.from(document.querySelectorAll('.calendar-day:not(.empty)'))
  .find((cell) => cell.querySelector('.day-number')?.textContent === String(dayNumber))

const openJune24Modal = async () => {
  render(<RosterCalendar token="test-token" isAdmin defaultSourceFilter="all" />)
  await screen.findByText(/TAG-GATE2401 is not linked to a shift/)
  const dayCell = screen.getAllByText('24')
    .map((el) => el.closest('.calendar-day'))
    .find(Boolean)
  fireEvent.click(dayCell)
  await waitFor(() => expect(screen.getAllByText('Roster review needed')).toHaveLength(2))
}

describe('RosterCalendar generate roster CTA gate', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(new Date('2026-06-09T12:00:00Z'))
    window.localStorage.clear()
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('H: shows Generate roster CTA when Review exists and the backend gate allows generation', async () => {
    setupApi({ gate: allowedGate })

    await openJune24Modal()

    expect(await screen.findByRole('button', { name: 'Generate roster for 24/06/2026' })).toBeInTheDocument()
  })

  it('U: hides Generate roster CTA when Review is blocked by a suppressed auto shift', async () => {
    setupApi({ gate: blockedGate })

    await openJune24Modal()

    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/admin/roster/review-generate-gate?date=2026-06-24'),
        expect.any(Object),
      )
    })
    expect(screen.queryByRole('button', { name: 'Generate roster for 24/06/2026' })).not.toBeInTheDocument()
    expect(screen.getAllByText('Roster review needed')).toHaveLength(2)
  })

  it('B: posts only the selected date when Generate roster is clicked', async () => {
    const { generateCalls } = setupApi({ gate: allowedGate })

    await openJune24Modal()
    fireEvent.click(await screen.findByRole('button', { name: 'Generate roster for 24/06/2026' }))

    await waitFor(() => expect(generateCalls).toHaveLength(1))
    expect(JSON.parse(generateCalls[0].options.body)).toEqual({ date: '2026-06-24' })
  })

  it('H: surfaces backend-only missing pickup events in the calendar review', async () => {
    vi.setSystemTime(new Date('2026-07-01T12:00:00Z'))
    setupApi({
      bookings: [],
      gate: {
        ...allowedGate,
        date: '2026-07-14',
        missing_events: [{
          booking_id: 804,
          booking_reference: 'TAG-WLJ80128',
          event_type: 'pick_up',
          event_time: '18:00',
          customer_name: 'Daniel Beaumont',
          flight_number: 'TOM6222',
          destination: 'Bournemouth',
        }],
      },
    })

    render(<RosterCalendar token="test-token" isAdmin defaultSourceFilter="all" />)

    expect(await screen.findByText(/Pick-up TAG-WLJ80128 is not linked to a shift/)).toBeInTheDocument()
  })

  it('H: hides the calendar review banner until backend month gates finish loading', async () => {
    let resolveReviewGates
    const reviewGatesResponse = new Promise((resolve) => {
      resolveReviewGates = resolve
    })
    setupApi({ reviewGatesResponse })

    render(<RosterCalendar token="test-token" isAdmin defaultSourceFilter="all" />)

    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/admin/roster/review-generate-gates?date_from=2026-06-01&date_to=2026-06-30'),
        expect.any(Object),
      )
    })
    expect(screen.queryByText('Roster review needed')).not.toBeInTheDocument()

    resolveReviewGates(makeJsonResponse(gateRangeResponse([allowedGate])))

    expect(await screen.findByText(/Drop-off TAG-GATE2401 is not linked to a shift/)).toBeInTheDocument()
  })

  it('B: compacts UK-past days until Show past days is enabled', async () => {
    setupApi({ bookings: [pastBooking], gates: [] })

    render(<RosterCalendar token="test-token" isAdmin defaultSourceFilter="all" />)

    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/admin/bookings'),
        expect.any(Object),
      )
    })
    const dayOne = getCalendarDayCell(1)
    expect(dayOne).toHaveClass('past-day', 'past-day-compact')
    expect(dayOne.querySelector('.badge-past')).toHaveTextContent('Past')
    expect(dayOne.querySelector('.badge-dropoff')).toBeNull()

    const toggle = screen.getAllByRole('button', { name: 'Show past days' })[0]
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(toggle)

    await waitFor(() => expect(getCalendarDayCell(1).querySelector('.badge-dropoff')).toHaveTextContent('1'))
    expect(screen.getAllByRole('button', { name: 'Hide past days' })[0]).toHaveAttribute('aria-pressed', 'true')
    expect(getCalendarDayCell(1)).toHaveClass('past-day')
    expect(getCalendarDayCell(1)).not.toHaveClass('past-day-compact')
    expect(getCalendarDayCell(1).querySelector('.badge-past')).toBeNull()
  })

  it('B: hides the Show past days button when viewing a future month', async () => {
    setupApi({ bookings: [pastBooking], gates: [] })

    render(<RosterCalendar token="test-token" isAdmin defaultSourceFilter="all" />)

    expect(await screen.findAllByRole('button', { name: 'Show past days' })).toHaveLength(2)
    fireEvent.click(screen.getAllByRole('button', { name: '›' })[0])

    await waitFor(() => expect(screen.getAllByText('July 2026')).toHaveLength(2))
    expect(screen.queryByRole('button', { name: 'Show past days' })).not.toBeInTheDocument()
  })

  it('U: excludes UK-past review issues from the banner until past days are shown', async () => {
    setupApi({ bookings: [], gates: [pastGate] })

    render(<RosterCalendar token="test-token" isAdmin defaultSourceFilter="all" />)

    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/admin/roster/review-generate-gates?date_from=2026-06-01&date_to=2026-06-30'),
        expect.any(Object),
      )
    })
    await waitFor(() => expect(screen.queryByText('Roster review needed')).not.toBeInTheDocument())

    fireEvent.click(screen.getAllByRole('button', { name: 'Show past days' })[0])

    expect(await screen.findByText(/Drop-off TAG-PAST2402 is not linked to a shift/)).toBeInTheDocument()
  })

  it('E: uses the UK date boundary when deciding which days are past', () => {
    const ukJustAfterMidnight = new Date('2026-06-09T23:30:00Z')

    expect(isPastDateKeyUK('2026-06-09', ukJustAfterMidnight)).toBe(true)
    expect(isPastDateKeyUK('2026-06-10', ukJustAfterMidnight)).toBe(false)
  })
})
