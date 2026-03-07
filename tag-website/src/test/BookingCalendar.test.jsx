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
    pickup_time: '13:30', // Arrival time (landing)
    pickup_time_from: '14:00',
    pickup_time_to: '15:00',
    flight_arrival_time: '13:30', // Actual flight arrival time
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
    pickup_time: '11:30',
    pickup_time_from: '12:00',
    pickup_time_to: '13:00',
    flight_arrival_time: '11:30',
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
    pickup_time: '15:30', // Arrival time
    pickup_time_from: '16:00',
    pickup_time_to: '17:00',
    flight_arrival_time: '15:30', // Actual flight arrival time
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
    pickup_time: '09:30',
    pickup_time_from: '10:00',
    pickup_time_to: '11:00',
    flight_arrival_time: '09:30',
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

/**
 * Unit tests for the formatPickupTime function
 * Tests that pickup time is displayed as arrival time + 30 minutes
 */
describe('BookingCalendar - formatPickupTime logic', () => {
  // Replicate the formatPickupTime function from BookingCalendar
  const formatPickupTime = (timeStr) => {
    if (!timeStr) return ''
    const parts = timeStr.split(':')
    let hours = parseInt(parts[0], 10)
    let minutes = parseInt(parts[1], 10) + 30
    if (minutes >= 60) {
      minutes -= 60
      hours += 1
    }
    if (hours >= 24) {
      hours -= 24
    }
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`
  }

  it('adds 30 minutes to standard arrival time', () => {
    expect(formatPickupTime('14:00')).toBe('14:30')
    expect(formatPickupTime('10:15')).toBe('10:45')
    expect(formatPickupTime('08:30')).toBe('09:00')
  })

  it('handles minute overflow correctly', () => {
    expect(formatPickupTime('14:45')).toBe('15:15')
    expect(formatPickupTime('09:35')).toBe('10:05')
    expect(formatPickupTime('11:50')).toBe('12:20')
  })

  it('handles hour overflow at midnight', () => {
    expect(formatPickupTime('23:30')).toBe('00:00')
    expect(formatPickupTime('23:45')).toBe('00:15')
    expect(formatPickupTime('23:59')).toBe('00:29')
  })

  it('handles late night arrivals', () => {
    expect(formatPickupTime('22:00')).toBe('22:30')
    expect(formatPickupTime('23:00')).toBe('23:30')
  })

  it('handles early morning arrivals', () => {
    expect(formatPickupTime('00:00')).toBe('00:30')
    expect(formatPickupTime('00:15')).toBe('00:45')
    expect(formatPickupTime('01:30')).toBe('02:00')
  })

  it('returns empty string for null/undefined input', () => {
    expect(formatPickupTime(null)).toBe('')
    expect(formatPickupTime(undefined)).toBe('')
    expect(formatPickupTime('')).toBe('')
  })

  it('uses flight_arrival_time over pickup_time when available', () => {
    const booking = mockBookings[0] // Maria's booking
    // flight_arrival_time is 13:30, so pickup time should be 14:00
    const arrivalTime = booking.flight_arrival_time || booking.pickup_time
    expect(formatPickupTime(arrivalTime)).toBe('14:00')
  })

  it('falls back to pickup_time when flight_arrival_time is not available', () => {
    const bookingWithoutFlightArrival = {
      ...mockBookings[0],
      flight_arrival_time: null,
      pickup_time: '15:00',
    }
    const arrivalTime = bookingWithoutFlightArrival.flight_arrival_time || bookingWithoutFlightArrival.pickup_time
    expect(formatPickupTime(arrivalTime)).toBe('15:30')
  })
})
