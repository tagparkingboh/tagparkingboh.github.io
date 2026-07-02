/**
 * Render tests for the /employee live flight board (EmployeeFlightBoard.jsx).
 *
 * The board shows the latest scraped BOH arrivals/departures snapshot:
 *  - arrivals render by default, the Departures tab switches lists
 *  - live status text is colour-classed (landed/departed/expected/alert)
 *  - freshness stamp with a stale warning when the snapshot is old
 *  - Refresh refetches from OUR backend only (never the airport site)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, fireEvent, waitFor, cleanup } from '@testing-library/react'
import EmployeeFlightBoard, { flightStatusClass } from '../components/EmployeeFlightBoard'

vi.mock('../AuthContext', () => ({
  useAuth: () => ({ authFetch: (...args) => global.fetch(...args) }),
}))

const boardPayload = (overrides = {}) => ({
  available: true,
  scraped_at: '2026-07-02T17:30:00+00:00',
  age_minutes: 12,
  stale: false,
  arrivals: [
    { place: 'Kefalonia', airline: 'TUI', flight: 'TOM6457', date: '02/07', scheduled: '14:25', status: 'Landed 14:41' },
    { place: 'Faro', airline: 'Ryanair', flight: 'FR3945', date: '02/07', scheduled: '20:20', status: 'Expected 20:00' },
  ],
  departures: [
    { place: 'Heraklion', airline: 'TUI', flight: 'TOM6472', date: '02/07', scheduled: '13:45', status: 'Departed 13:47' },
    { place: 'Faro', airline: 'Ryanair', flight: 'FR3944', date: '02/07', scheduled: '20:45', status: 'Wait In Lounge' },
  ],
  ...overrides,
})

function installFetch(payload) {
  global.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(payload) })
  )
}

describe('EmployeeFlightBoard', () => {
  beforeEach(() => vi.useRealTimers())
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('renders arrivals by default and switches to departures', async () => {
    installFetch(boardPayload())
    const { getByText, queryByText } = render(<EmployeeFlightBoard />)

    await waitFor(() => expect(getByText('TOM6457')).toBeTruthy())
    expect(getByText('Kefalonia')).toBeTruthy()
    expect(queryByText('TOM6472')).toBeNull()

    fireEvent.click(getByText('Departures'))
    expect(getByText('TOM6472')).toBeTruthy()
    expect(getByText('Wait In Lounge')).toBeTruthy()
    expect(queryByText('TOM6457')).toBeNull()
  })

  it('shows the freshness stamp and flags stale data', async () => {
    installFetch(boardPayload({ age_minutes: 95, stale: true }))
    const { container, getByText } = render(<EmployeeFlightBoard />)

    await waitFor(() => expect(getByText('TOM6457')).toBeTruthy())
    const stamp = container.querySelector('.flight-board-updated')
    expect(stamp.textContent).toContain('95 min ago')
    expect(stamp.textContent).toContain('may be out of date')
    expect(stamp.className).toContain('flight-board-stale')
  })

  it('shows the empty state before any snapshot exists', async () => {
    installFetch({ available: false, arrivals: [], departures: [], scraped_at: null, age_minutes: null, stale: true })
    const { getByText } = render(<EmployeeFlightBoard />)

    await waitFor(() =>
      expect(getByText(/No flight data yet/)).toBeTruthy()
    )
  })

  it('Refresh refetches from the backend endpoint', async () => {
    installFetch(boardPayload())
    const { getByText } = render(<EmployeeFlightBoard />)
    await waitFor(() => expect(getByText('TOM6457')).toBeTruthy())

    const callsBefore = global.fetch.mock.calls.length
    fireEvent.click(getByText('Refresh'))
    await waitFor(() =>
      expect(global.fetch.mock.calls.length).toBeGreaterThan(callsBefore)
    )
    expect(String(global.fetch.mock.calls.at(-1)[0])).toContain('/api/employee/flight-board')
  })

  it('classifies live statuses into colour classes', () => {
    expect(flightStatusClass('Landed 14:41')).toBe('fb-status-done')
    expect(flightStatusClass('Departed 13:47')).toBe('fb-status-done')
    expect(flightStatusClass('Expected 20:00')).toBe('fb-status-expected')
    expect(flightStatusClass('Delayed 21:10')).toBe('fb-status-alert')
    expect(flightStatusClass('Cancelled')).toBe('fb-status-alert')
    expect(flightStatusClass('Wait In Lounge')).toBe('fb-status-active')
    expect(flightStatusClass('As Scheduled')).toBe('fb-status-scheduled')
    expect(flightStatusClass(null)).toBe('fb-status-scheduled')
  })
})
