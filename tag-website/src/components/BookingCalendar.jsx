import { useState, useEffect, useMemo } from 'react'
import './BookingCalendar.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function BookingCalendar({ token }) {
  const [currentDate, setCurrentDate] = useState(new Date())
  const [bookings, setBookings] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedDate, setSelectedDate] = useState(null)
  const [viewMode, setViewMode] = useState('month') // 'month', 'week', 'day'

  // Fetch bookings for the current month view
  useEffect(() => {
    if (token) {
      fetchBookings()
    }
  }, [token, currentDate])

  const fetchBookings = async () => {
    setLoading(true)
    setError('')
    try {
      // Get bookings - we'll filter client-side for the calendar view
      const response = await fetch(`${API_URL}/api/admin/bookings?include_cancelled=false`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setBookings(data.bookings || [])
      } else {
        setError('Failed to load bookings')
      }
    } catch (err) {
      setError('Network error loading bookings')
    } finally {
      setLoading(false)
    }
  }

  // Calendar navigation
  const goToPrevMonth = () => {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1))
    setSelectedDate(null)
  }

  const goToNextMonth = () => {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1))
    setSelectedDate(null)
  }

  const goToToday = () => {
    setCurrentDate(new Date())
    setSelectedDate(null)
  }

  // Get calendar grid data
  const calendarData = useMemo(() => {
    const year = currentDate.getFullYear()
    const month = currentDate.getMonth()

    // First day of month and how many days
    const firstDay = new Date(year, month, 1)
    const lastDay = new Date(year, month + 1, 0)
    const daysInMonth = lastDay.getDate()

    // What day of week does the month start on (0 = Sunday)
    const startDayOfWeek = firstDay.getDay()

    // Build calendar grid (6 weeks max)
    const weeks = []
    let currentDay = 1 - startDayOfWeek // May start negative for prev month days

    for (let week = 0; week < 6; week++) {
      const days = []
      for (let dayOfWeek = 0; dayOfWeek < 7; dayOfWeek++) {
        if (currentDay < 1 || currentDay > daysInMonth) {
          days.push(null) // Empty cell
        } else {
          days.push(currentDay)
        }
        currentDay++
      }
      // Only add week if it has at least one day from current month
      if (days.some(d => d !== null)) {
        weeks.push(days)
      }
    }

    return { year, month, weeks, daysInMonth }
  }, [currentDate])

  // Group bookings by date (only confirmed bookings)
  const bookingsByDate = useMemo(() => {
    const grouped = {}

    // Filter to only include confirmed bookings
    const confirmedBookings = bookings.filter(b => b.status === 'confirmed')

    confirmedBookings.forEach(booking => {
      // Add to dropoff date
      if (booking.dropoff_date) {
        const dropoffKey = booking.dropoff_date
        if (!grouped[dropoffKey]) {
          grouped[dropoffKey] = { dropoffs: [], pickups: [] }
        }
        grouped[dropoffKey].dropoffs.push(booking)
      }

      // Add to pickup date
      if (booking.pickup_date) {
        const pickupKey = booking.pickup_date
        if (!grouped[pickupKey]) {
          grouped[pickupKey] = { dropoffs: [], pickups: [] }
        }
        grouped[pickupKey].pickups.push(booking)
      }
    })

    return grouped
  }, [bookings])

  // Format date key for lookup
  const getDateKey = (day) => {
    if (!day) return null
    const year = calendarData.year
    const month = String(calendarData.month + 1).padStart(2, '0')
    const dayStr = String(day).padStart(2, '0')
    return `${year}-${month}-${dayStr}`
  }

  // Get bookings for a specific day
  const getBookingsForDay = (day) => {
    const dateKey = getDateKey(day)
    return bookingsByDate[dateKey] || { dropoffs: [], pickups: [] }
  }

  // Check if date is today
  const isToday = (day) => {
    if (!day) return false
    const today = new Date()
    return (
      day === today.getDate() &&
      calendarData.month === today.getMonth() &&
      calendarData.year === today.getFullYear()
    )
  }

  // Check if date is selected
  const isSelected = (day) => {
    if (!day || !selectedDate) return false
    return getDateKey(day) === selectedDate
  }

  // Format time for display
  const formatTime = (timeStr) => {
    if (!timeStr) return ''
    // Handle both "HH:MM:SS" and "HH:MM" formats
    const parts = timeStr.split(':')
    return `${parts[0]}:${parts[1]}`
  }

  // Get month name
  const monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ]

  const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

  // Get selected day's bookings
  const selectedDayBookings = selectedDate ? bookingsByDate[selectedDate] : null

  return (
    <div className="booking-calendar">
      {/* Calendar Header */}
      <div className="calendar-header">
        <div className="calendar-nav">
          <button onClick={goToPrevMonth} className="calendar-nav-btn">
            &larr;
          </button>
          <h2 className="calendar-title">
            {monthNames[calendarData.month]} {calendarData.year}
          </h2>
          <button onClick={goToNextMonth} className="calendar-nav-btn">
            &rarr;
          </button>
        </div>
        <div className="calendar-actions">
          <button onClick={goToToday} className="calendar-today-btn">
            Today
          </button>
          <button onClick={fetchBookings} className="calendar-refresh-btn" disabled={loading}>
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>

      {error && <div className="calendar-error">{error}</div>}

      {/* Calendar Grid */}
      <div className="calendar-grid">
        {/* Day headers */}
        <div className="calendar-weekdays">
          {dayNames.map(day => (
            <div key={day} className="calendar-weekday">{day}</div>
          ))}
        </div>

        {/* Calendar weeks */}
        <div className="calendar-weeks">
          {calendarData.weeks.map((week, weekIndex) => (
            <div key={weekIndex} className="calendar-week">
              {week.map((day, dayIndex) => {
                const dayBookings = getBookingsForDay(day)
                const hasDropoffs = dayBookings.dropoffs.length > 0
                const hasPickups = dayBookings.pickups.length > 0
                const hasBookings = hasDropoffs || hasPickups

                return (
                  <div
                    key={dayIndex}
                    className={`calendar-day ${!day ? 'empty' : ''} ${isToday(day) ? 'today' : ''} ${isSelected(day) ? 'selected' : ''} ${hasBookings ? 'has-bookings' : ''}`}
                    onClick={() => day && setSelectedDate(getDateKey(day))}
                  >
                    {day && (
                      <>
                        <span className="day-number">{day}</span>
                        {hasBookings && (
                          <div className="day-badges">
                            {hasDropoffs && (
                              <span className="badge dropoff" title="Drop-offs">
                                🚗 {dayBookings.dropoffs.length}
                              </span>
                            )}
                            {hasPickups && (
                              <span className="badge pickup" title="Pick-ups">
                                🛬 {dayBookings.pickups.length}
                              </span>
                            )}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Selected Day Detail Panel */}
      {selectedDate && selectedDayBookings && (
        <div className="calendar-detail-panel">
          <div className="detail-header">
            <h3>
              {new Date(selectedDate + 'T00:00:00').toLocaleDateString('en-GB', {
                weekday: 'long',
                day: 'numeric',
                month: 'long',
                year: 'numeric'
              })}
            </h3>
            <button
              className="detail-close"
              onClick={() => setSelectedDate(null)}
            >
              &times;
            </button>
          </div>

          <div className="detail-content">
            {/* Drop-offs */}
            {selectedDayBookings.dropoffs.length > 0 && (
              <div className="detail-section">
                <h4 className="detail-section-title dropoff">
                  🚗 Drop-offs ({selectedDayBookings.dropoffs.length})
                </h4>
                <div className="detail-bookings">
                  {selectedDayBookings.dropoffs
                    .sort((a, b) => (a.dropoff_time || '').localeCompare(b.dropoff_time || ''))
                    .map(booking => (
                      <div key={booking.id} className="detail-booking-card">
                        <div className="booking-header-row">
                          <div className="booking-time">
                            {formatTime(booking.dropoff_time)}
                          </div>
                          <div className="booking-destination">
                            → {booking.dropoff_destination || 'Unknown'}
                          </div>
                          <div className="booking-ref">
                            {booking.reference}
                          </div>
                        </div>
                        <div className="booking-details-row">
                          {booking.customer?.first_name || booking.customer_first_name} {booking.customer?.last_name || booking.customer_last_name}
                          <span>|</span>
                          <a href={`tel:${booking.customer?.phone}`} className="phone-link">
                            {booking.customer?.phone || 'N/A'}
                          </a>
                          <span>|</span>
                          {booking.vehicle?.colour} {booking.vehicle?.make} {booking.vehicle?.model}
                          <span>|</span>
                          <span className="reg-plate">{booking.vehicle?.registration || booking.vehicle_registration}</span>
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* Pick-ups */}
            {selectedDayBookings.pickups.length > 0 && (
              <div className="detail-section">
                <h4 className="detail-section-title pickup">
                  🛬 Pick-ups ({selectedDayBookings.pickups.length})
                </h4>
                <div className="detail-bookings">
                  {selectedDayBookings.pickups
                    .sort((a, b) => (a.pickup_time_from || a.pickup_time || '').localeCompare(b.pickup_time_from || b.pickup_time || ''))
                    .map(booking => (
                      <div key={booking.id} className="detail-booking-card">
                        <div className="booking-header-row">
                          <div className="booking-time">
                            {booking.pickup_time_from && booking.pickup_time_to
                              ? `${formatTime(booking.pickup_time_from)}-${formatTime(booking.pickup_time_to)}`
                              : formatTime(booking.pickup_time)
                            }
                          </div>
                          <div className="booking-destination">
                            ← {booking.pickup_origin || 'Unknown'}
                          </div>
                          <div className="booking-ref">
                            {booking.reference}
                          </div>
                        </div>
                        <div className="booking-details-row">
                          {booking.customer?.first_name || booking.customer_first_name} {booking.customer?.last_name || booking.customer_last_name}
                          <span>|</span>
                          <a href={`tel:${booking.customer?.phone}`} className="phone-link">
                            {booking.customer?.phone || 'N/A'}
                          </a>
                          <span>|</span>
                          {booking.vehicle?.colour} {booking.vehicle?.make} {booking.vehicle?.model}
                          <span>|</span>
                          <span className="reg-plate">{booking.vehicle?.registration || booking.vehicle_registration}</span>
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* No bookings message */}
            {selectedDayBookings.dropoffs.length === 0 && selectedDayBookings.pickups.length === 0 && (
              <p className="no-bookings">No bookings for this day</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default BookingCalendar
