import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import RosterCalendar from '../components/RosterCalendar'

const mockAuthFetch = vi.hoisted(() => vi.fn())

vi.mock('../AuthContext', () => ({
  useAuth: () => ({ authFetch: mockAuthFetch }),
}))

const jsonResponse = (body, ok = true, status = 200) => Promise.resolve({
  ok,
  status,
  json: async () => body,
})

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
  missing_events: [],
}

const blockedGate = {
  ...allowedGate,
  blocked_by_suppressed: true,
  suppressed_blocker_count: 1,
  suppressed_shift_ids: [5422],
  suppressed_booking_references: ['TAG-GATE2401'],
  can_generate_roster: false,
}

const setupApi = ({ gate = allowedGate } = {}) => {
  const generateCalls = []
  mockAuthFetch.mockImplementation((url, options = {}) => {
    const requestUrl = String(url)

    if (requestUrl.includes('/api/admin/bookings')) {
      return jsonResponse({ bookings: [missingBooking] })
    }
    if (requestUrl.includes('/api/roster?')) {
      return jsonResponse([])
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
})
