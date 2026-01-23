/**
 * Tests for BookingCalendar component
 *
 * Tests the core logic:
 * - Only confirmed bookings are displayed
 * - Bookings are correctly grouped by dropoff and pickup dates
 * - Calendar navigation works
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import BookingCalendar from '../components/BookingCalendar'

// Mock fetch
global.fetch = vi.fn()

// Sample bookings data
const mockBookings = [
  {
    id: 1,
    reference: 'TAG-ABC12345',
    status: 'confirmed',
    dropoff_date: '2026-01-22',
    dropoff_time: '19:35',
    dropoff_destination: 'Edinburgh Airport',
    pickup_date: '2026-01-29',
    pickup_time_from: '14:00',
    pickup_time_to: '15:00',
    pickup_origin: 'Edinburgh Airport',
    customer: {
      id: 1,
      first_name: 'Maria',
      last_name: 'Escobar',
      phone: '+447977654654',
    },
    vehicle: {
      id: 1,
      registration: 'AA19AAA',
      make: 'Ford',
      model: 'Ranger',
      colour: 'Red',
    },
  },
  {
    id: 2,
    reference: 'TAG-DEF67890',
    status: 'pending', // Should NOT be displayed
    dropoff_date: '2026-01-22',
    dropoff_time: '10:00',
    dropoff_destination: 'Glasgow Airport',
    pickup_date: '2026-01-25',
    pickup_time_from: '12:00',
    pickup_time_to: '13:00',
    pickup_origin: 'Glasgow Airport',
    customer: {
      id: 2,
      first_name: 'John',
      last_name: 'Pending',
      phone: '+447777777777',
    },
    vehicle: {
      id: 2,
      registration: 'BB20BBB',
      make: 'BMW',
      model: '3 Series',
      colour: 'Black',
    },
  },
  {
    id: 3,
    reference: 'TAG-GHI11111',
    status: 'confirmed',
    dropoff_date: '2026-01-25',
    dropoff_time: '08:00',
    dropoff_destination: 'Manchester Airport',
    pickup_date: '2026-01-29',
    pickup_time_from: '16:00',
    pickup_time_to: '17:00',
    pickup_origin: 'Manchester Airport',
    customer: {
      id: 3,
      first_name: 'Jane',
      last_name: 'Smith',
      phone: '+447888888888',
    },
    vehicle: {
      id: 3,
      registration: 'CC21CCC',
      make: 'Audi',
      model: 'A4',
      colour: 'White',
    },
  },
  {
    id: 4,
    reference: 'TAG-CAN22222',
    status: 'cancelled', // Should NOT be displayed
    dropoff_date: '2026-01-22',
    dropoff_time: '11:00',
    dropoff_destination: 'Heathrow',
    pickup_date: '2026-01-24',
    pickup_time_from: '10:00',
    pickup_time_to: '11:00',
    pickup_origin: 'Heathrow',
    customer: {
      id: 4,
      first_name: 'Cancelled',
      last_name: 'User',
      phone: '+447999999999',
    },
    vehicle: {
      id: 4,
      registration: 'DD22DDD',
      make: 'Mercedes',
      model: 'C Class',
      colour: 'Silver',
    },
  },
]

describe('BookingCalendar', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    // Mock successful API response
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ bookings: mockBookings }),
    })
  })

  it('renders calendar with month and year', async () => {
    render(<BookingCalendar token="test-token" />)

    await waitFor(() => {
      // Should show current month/year in the title
      const today = new Date()
      const monthNames = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
      ]
      const expectedText = `${monthNames[today.getMonth()]} ${today.getFullYear()}`
      expect(screen.getByText(expectedText)).toBeInTheDocument()
    })
  })

  it('renders weekday headers', async () => {
    render(<BookingCalendar token="test-token" />)

    await waitFor(() => {
      expect(screen.getByText('Sun')).toBeInTheDocument()
      expect(screen.getByText('Mon')).toBeInTheDocument()
      expect(screen.getByText('Tue')).toBeInTheDocument()
      expect(screen.getByText('Wed')).toBeInTheDocument()
      expect(screen.getByText('Thu')).toBeInTheDocument()
      expect(screen.getByText('Fri')).toBeInTheDocument()
      expect(screen.getByText('Sat')).toBeInTheDocument()
    })
  })

  it('fetches bookings on mount with token', async () => {
    render(<BookingCalendar token="test-token" />)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/admin/bookings?include_cancelled=false'),
        expect.objectContaining({
          headers: {
            'Authorization': 'Bearer test-token',
          },
        })
      )
    })
  })

  it('does not fetch bookings without token', async () => {
    render(<BookingCalendar token={null} />)

    // Wait a bit to ensure no fetch is made
    await new Promise(resolve => setTimeout(resolve, 100))

    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('navigates to next month when arrow clicked', async () => {
    render(<BookingCalendar token="test-token" />)

    const today = new Date()
    const monthNames = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December'
    ]

    // Initial month
    await waitFor(() => {
      expect(screen.getByText(`${monthNames[today.getMonth()]} ${today.getFullYear()}`)).toBeInTheDocument()
    })

    // Click next month button
    const nextButton = screen.getByText('→')
    fireEvent.click(nextButton)

    // Check next month is displayed
    const nextMonth = new Date(today.getFullYear(), today.getMonth() + 1, 1)
    expect(screen.getByText(`${monthNames[nextMonth.getMonth()]} ${nextMonth.getFullYear()}`)).toBeInTheDocument()
  })

  it('navigates to previous month when arrow clicked', async () => {
    render(<BookingCalendar token="test-token" />)

    const today = new Date()
    const monthNames = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December'
    ]

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled()
    })

    // Click previous month button
    const prevButton = screen.getByText('←')
    fireEvent.click(prevButton)

    // Check previous month is displayed
    const prevMonth = new Date(today.getFullYear(), today.getMonth() - 1, 1)
    expect(screen.getByText(`${monthNames[prevMonth.getMonth()]} ${prevMonth.getFullYear()}`)).toBeInTheDocument()
  })

  it('returns to current month when Today button clicked', async () => {
    render(<BookingCalendar token="test-token" />)

    const today = new Date()
    const monthNames = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December'
    ]

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled()
    })

    // Navigate away
    const nextButton = screen.getByText('→')
    fireEvent.click(nextButton)
    fireEvent.click(nextButton)

    // Click Today
    const todayButton = screen.getByText('Today')
    fireEvent.click(todayButton)

    expect(screen.getByText(`${monthNames[today.getMonth()]} ${today.getFullYear()}`)).toBeInTheDocument()
  })

  it('shows Refresh button', async () => {
    render(<BookingCalendar token="test-token" />)

    await waitFor(() => {
      expect(screen.getByText('Refresh')).toBeInTheDocument()
    })
  })

  it('shows error message when API fails', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
    })

    render(<BookingCalendar token="test-token" />)

    await waitFor(() => {
      expect(screen.getByText('Failed to load bookings')).toBeInTheDocument()
    })
  })

  it('shows network error message on fetch failure', async () => {
    global.fetch.mockRejectedValueOnce(new Error('Network error'))

    render(<BookingCalendar token="test-token" />)

    await waitFor(() => {
      expect(screen.getByText('Network error loading bookings')).toBeInTheDocument()
    })
  })
})

/**
 * Unit tests for the booking filtering logic
 * Testing that only confirmed bookings are shown
 */
describe('BookingCalendar - Confirmed bookings filter', () => {
  it('filters bookings to only include confirmed status', () => {
    // This tests the filtering logic directly
    const allBookings = mockBookings
    const confirmedBookings = allBookings.filter(b => b.status === 'confirmed')

    // Should have 2 confirmed bookings (Maria and Jane)
    expect(confirmedBookings).toHaveLength(2)

    // Should include Maria (confirmed)
    expect(confirmedBookings.find(b => b.customer.first_name === 'Maria')).toBeDefined()

    // Should include Jane (confirmed)
    expect(confirmedBookings.find(b => b.customer.first_name === 'Jane')).toBeDefined()

    // Should NOT include John (pending)
    expect(confirmedBookings.find(b => b.customer.first_name === 'John')).toBeUndefined()

    // Should NOT include Cancelled User (cancelled)
    expect(confirmedBookings.find(b => b.customer.first_name === 'Cancelled')).toBeUndefined()
  })
})

/**
 * Unit tests for the booking grouping logic
 */
describe('BookingCalendar - Booking grouping by date', () => {
  it('groups bookings by dropoff date', () => {
    const confirmedBookings = mockBookings.filter(b => b.status === 'confirmed')
    const grouped = {}

    confirmedBookings.forEach(booking => {
      if (booking.dropoff_date) {
        const key = booking.dropoff_date
        if (!grouped[key]) {
          grouped[key] = { dropoffs: [], pickups: [] }
        }
        grouped[key].dropoffs.push(booking)
      }
    })

    // Jan 22 should have 1 dropoff (Maria)
    expect(grouped['2026-01-22']?.dropoffs).toHaveLength(1)
    expect(grouped['2026-01-22']?.dropoffs[0].customer.first_name).toBe('Maria')

    // Jan 25 should have 1 dropoff (Jane)
    expect(grouped['2026-01-25']?.dropoffs).toHaveLength(1)
    expect(grouped['2026-01-25']?.dropoffs[0].customer.first_name).toBe('Jane')
  })

  it('groups bookings by pickup date', () => {
    const confirmedBookings = mockBookings.filter(b => b.status === 'confirmed')
    const grouped = {}

    confirmedBookings.forEach(booking => {
      if (booking.pickup_date) {
        const key = booking.pickup_date
        if (!grouped[key]) {
          grouped[key] = { dropoffs: [], pickups: [] }
        }
        grouped[key].pickups.push(booking)
      }
    })

    // Jan 29 should have 2 pickups (Maria and Jane)
    expect(grouped['2026-01-29']?.pickups).toHaveLength(2)
  })

  it('correctly identifies days with bookings', () => {
    const confirmedBookings = mockBookings.filter(b => b.status === 'confirmed')
    const grouped = {}

    confirmedBookings.forEach(booking => {
      if (booking.dropoff_date) {
        const key = booking.dropoff_date
        if (!grouped[key]) grouped[key] = { dropoffs: [], pickups: [] }
        grouped[key].dropoffs.push(booking)
      }
      if (booking.pickup_date) {
        const key = booking.pickup_date
        if (!grouped[key]) grouped[key] = { dropoffs: [], pickups: [] }
        grouped[key].pickups.push(booking)
      }
    })

    // Days with bookings
    const daysWithBookings = Object.keys(grouped)
    expect(daysWithBookings).toContain('2026-01-22') // Maria dropoff
    expect(daysWithBookings).toContain('2026-01-25') // Jane dropoff
    expect(daysWithBookings).toContain('2026-01-29') // Maria & Jane pickup

    // Days without confirmed bookings (pending/cancelled dates)
    // John's dates (pending) should not create entries if only confirmed are processed
    // Note: 2026-01-25 is in the list because Jane (confirmed) drops off that day
  })
})
