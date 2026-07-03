/**
 * RosterCalendar Full/Busy badge split (2026-07-02).
 *
 * With a time-aware backend gate (time_aware_gate echo true), "⛔ Full" is
 * reserved for days whose THROUGH-stay count is at cap — the day genuinely
 * cannot take another car. A touch-at-cap turnover day (heavy workload,
 * but the booking flow still sells the gaps) downgrades to "🚗 Busy".
 * Gate off/absent → legacy touch-count "Full", exactly as before.
 *
 * N in both badges is the TOUCHING count (the ops workload number).
 * Harness pattern from RosterCalendarGenerateCta.test.jsx.
 */
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import RosterCalendar from '../components/RosterCalendar'

const mockAuthFetch = vi.hoisted(() => vi.fn())

vi.mock('../AuthContext', () => ({
  useAuth: () => ({ authFetch: mockAuthFetch }),
}))

const jsonResponse = (body) => Promise.resolve({ ok: true, status: 200, json: async () => body })

// A future day in the CURRENT month (the calendar's default view); clamp
// away from month-end so day+1 stays in month, and use tomorrow at minimum
// so the cell isn't a compacted past day.
const now = new Date()
const targetDay = Math.min(now.getDate() + 1, 28)
const DATE_KEY = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(targetDay).padStart(2, '0')}`

// Default online cap is 73 (no daily_capacity map provided).
const CAP = 73

const setupApi = ({ touch, through, gate }) => {
  mockAuthFetch.mockImplementation((url) => {
    const u = String(url)
    if (u.includes('/api/capacity/daily')) {
      return jsonResponse({
        daily_occupancy: { [DATE_KEY]: touch },
        daily_through_occupancy: { [DATE_KEY]: through },
        daily_capacity: {},
        time_aware_gate: gate,
      })
    }
    if (u.includes('/api/admin/bookings')) return jsonResponse({ bookings: [] })
    if (u.includes('/api/roster/shift-exceptions')) return jsonResponse([])
    if (u.includes('/api/roster?')) return jsonResponse([])
    if (u.includes('/api/admin/roster/review-generate-gates')) {
      return jsonResponse({ gates: [] })
    }
    if (u.includes('/api/admin/blocked-dates')) return jsonResponse({ blocked_dates: [] })
    if (u.includes('/api/holidays')) return jsonResponse([])
    if (u.includes('/api/staff')) return jsonResponse([])
    if (u.includes('/api/roster/monthly-hours')) return jsonResponse({ employees: [] })
    return jsonResponse({})
  })
}

const mount = () => render(<RosterCalendar token="test-token" isAdmin defaultSourceFilter="all" />)

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('RosterCalendar — Full vs Busy capacity badges', () => {
  it('gate on + through at cap → Full badge with the touching count', async () => {
    setupApi({ touch: CAP + 2, through: CAP, gate: true })
    mount()

    await waitFor(() => {
      expect(screen.getByText(`⛔ Full (${CAP + 2})`)).toBeInTheDocument()
    })
    expect(screen.queryByText(/🚗 Busy/)).not.toBeInTheDocument()
  })

  it('gate on + touch at cap but through below → Busy badge, not Full', async () => {
    setupApi({ touch: CAP + 2, through: 60, gate: true })
    mount()

    await waitFor(() => {
      expect(screen.getByText(`🚗 Busy (${CAP + 2})`)).toBeInTheDocument()
    })
    expect(screen.queryByText(/⛔ Full/)).not.toBeInTheDocument()
  })

  it('gate off + touch at cap → legacy Full badge (no Busy downgrade)', async () => {
    setupApi({ touch: CAP + 2, through: 60, gate: false })
    mount()

    await waitFor(() => {
      expect(screen.getByText(`⛔ Full (${CAP + 2})`)).toBeInTheDocument()
    })
    expect(screen.queryByText(/🚗 Busy/)).not.toBeInTheDocument()
  })

  it('gate on + touch below cap → neither badge', async () => {
    setupApi({ touch: 60, through: 40, gate: true })
    mount()

    // Wait for the capacity fetch to land, then assert absence.
    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/capacity/daily'), expect.anything())
    })
    expect(screen.queryByText(/⛔ Full/)).not.toBeInTheDocument()
    expect(screen.queryByText(/🚗 Busy/)).not.toBeInTheDocument()
  })

  it('boundary: through exactly at cap-1 stays Busy; exactly at cap flips to Full (gate on)', async () => {
    setupApi({ touch: CAP, through: CAP - 1, gate: true })
    const { unmount } = mount()
    await waitFor(() => {
      expect(screen.getByText(`🚗 Busy (${CAP})`)).toBeInTheDocument()
    })
    unmount()

    setupApi({ touch: CAP, through: CAP, gate: true })
    mount()
    await waitFor(() => {
      expect(screen.getByText(`⛔ Full (${CAP})`)).toBeInTheDocument()
    })
  })
})
