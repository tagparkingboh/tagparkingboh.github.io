import { useState, useEffect, useMemo, useCallback } from 'react'
import './RosterCalendar.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Shift type display config - Part-time and Full-time slots
const SHIFT_TYPE_CONFIG = {
  // Part-time slots (~3-4 hours each)
  early_morning: { label: 'Early Morning', color: '#1e3a5f', icon: '🌙', time: '03:50 - 07:00' },
  morning: { label: 'Morning', color: '#4a90e2', icon: '🌅', time: '07:00 - 11:00' },
  midday: { label: 'Midday', color: '#f5a623', icon: '☀️', time: '11:00 - 14:00' },
  afternoon: { label: 'Afternoon', color: '#e67e22', icon: '🌤️', time: '14:00 - 17:30' },
  late_afternoon: { label: 'Late Afternoon', color: '#9b59b6', icon: '🌇', time: '17:30 - 21:00' },
  evening: { label: 'Evening', color: '#2c3e50', icon: '🌃', time: '21:00 - 01:20' },
  // Full-time slots (~7 hours each)
  full_morning: { label: 'Full Morning', color: '#27ae60', icon: '🌄', time: '03:50 - 14:00' },
  full_afternoon: { label: 'Full Afternoon', color: '#e74c3c', icon: '🏙️', time: '11:00 - 21:00' },
  full_evening: { label: 'Full Evening', color: '#34495e', icon: '🌆', time: '17:30 - 01:20' },
}

// Shift status display config
const SHIFT_STATUS_CONFIG = {
  scheduled: { label: 'Scheduled', color: '#888' },
  confirmed: { label: 'Confirmed', color: '#4a90e2' },
  in_progress: { label: 'In Progress', color: '#f5a623' },
  completed: { label: 'Completed', color: '#50c878' },
  cancelled: { label: 'Cancelled', color: '#e74c3c' },
  no_show: { label: 'No Show', color: '#e74c3c' },
}

// Date format helpers
const formatDateUK = (isoDate) => {
  if (!isoDate) return ''
  const parts = isoDate.split('-')
  if (parts.length !== 3) return isoDate
  return `${parts[2]}/${parts[1]}/${parts[0]}`
}

const formatDateISO = (date) => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

// Convert UK date (DD/MM/YYYY) to ISO (YYYY-MM-DD)
const ukToISO = (ukDate) => {
  if (!ukDate) return ''
  const parts = ukDate.split('/')
  if (parts.length !== 3) return ukDate
  return `${parts[2]}-${parts[1]}-${parts[0]}`
}

// Format time for display (HH:MM)
const formatTime = (timeStr) => {
  if (!timeStr) return ''
  // Handle both "HH:MM" and "HH:MM:SS" formats
  return timeStr.substring(0, 5)
}

function RosterCalendar({ token, isAdmin = false, employeeId = null, refreshTrigger = 0, renderBookingActions = null }) {
  const [currentDate, setCurrentDate] = useState(new Date())
  const [shifts, setShifts] = useState([])
  const [bookings, setBookings] = useState([])
  const [employees, setEmployees] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedDate, setSelectedDate] = useState(null)
  const [successMessage, setSuccessMessage] = useState('')

  // Modal state
  const [showShiftModal, setShowShiftModal] = useState(false)
  const [editingShift, setEditingShift] = useState(null)
  const [shiftForm, setShiftForm] = useState({
    staff_id: '',
    booking_ids: [],  // Multiple bookings per shift
    date: '',
    end_date: '',  // For overnight shifts
    start_time: '',
    end_time: '',
    shift_type: 'morning',
    notes: '',
  })
  const [savingShift, setSavingShift] = useState(false)
  const [dateBookings, setDateBookings] = useState([])
  const [loadingDateBookings, setLoadingDateBookings] = useState(false)

  // Delete confirmation
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [shiftToDelete, setShiftToDelete] = useState(null)
  const [deletingShift, setDeletingShift] = useState(false)

  // Monthly hours (for payroll)
  const [monthlyHours, setMonthlyHours] = useState(null)
  const [loadingMonthlyHours, setLoadingMonthlyHours] = useState(false)

  // Fetch bookings
  const fetchBookings = useCallback(async () => {
    if (!token) return

    try {
      const endpoint = isAdmin ? '/api/admin/bookings' : '/api/employee/bookings'
      const response = await fetch(`${API_URL}${endpoint}?include_cancelled=false`, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Cache-Control': 'no-cache',
        },
      })

      if (response.ok) {
        const data = await response.json()
        setBookings(data.bookings || [])
      }
    } catch (err) {
      console.error('Failed to load bookings:', err)
    }
  }, [token, isAdmin])

  // Fetch shifts
  const fetchShifts = useCallback(async () => {
    if (!token) return

    try {
      const year = currentDate.getFullYear()
      const month = currentDate.getMonth()
      const startDate = new Date(year, month, 1)
      const endDate = new Date(year, month + 1, 0)

      // Send ISO format dates (YYYY-MM-DD) to backend
      const params = new URLSearchParams({
        date_from: formatDateISO(startDate),
        date_to: formatDateISO(endDate),
      })

      const endpoint = isAdmin ? '/api/roster' : '/api/employee/shifts'
      const response = await fetch(`${API_URL}${endpoint}?${params}`, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Cache-Control': 'no-cache',
        },
      })

      if (response.ok) {
        const data = await response.json()
        // API returns array directly, not { shifts: [...] }
        setShifts(Array.isArray(data) ? data : (data.shifts || []))
      }
    } catch (err) {
      console.error('Failed to load shifts:', err)
    }
  }, [token, currentDate, isAdmin])

  // Fetch all data
  const fetchData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      await Promise.all([fetchBookings(), fetchShifts()])
    } catch (err) {
      setError('Failed to load data')
    } finally {
      setLoading(false)
    }
  }, [fetchBookings, fetchShifts])

  // Fetch all staff (admin only) - includes both admins and employees
  const fetchStaff = useCallback(async () => {
    if (!token || !isAdmin) return

    try {
      // Use /api/staff to get ALL users (admins + employees)
      const response = await fetch(`${API_URL}/api/staff?is_active=true`, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Cache-Control': 'no-cache',
        },
      })

      if (response.ok) {
        const data = await response.json()
        // API returns array directly
        setEmployees(Array.isArray(data) ? data : [])
      }
    } catch (err) {
      console.error('Failed to load staff:', err)
    }
  }, [token, isAdmin])

  // Fetch monthly hours (for payroll)
  const fetchMonthlyHours = useCallback(async () => {
    if (!token) return

    try {
      setLoadingMonthlyHours(true)

      const year = currentDate.getFullYear()
      const month = currentDate.getMonth() + 1  // API expects 1-12, JS uses 0-11

      const endpoint = isAdmin ? '/api/roster/monthly-hours' : '/api/employee/monthly-hours'
      const response = await fetch(`${API_URL}${endpoint}?year=${year}&month=${month}`, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Cache-Control': 'no-cache',
        },
      })

      if (response.ok) {
        const data = await response.json()
        setMonthlyHours(data)
      }
    } catch (err) {
      console.error('Failed to load monthly hours:', err)
    } finally {
      setLoadingMonthlyHours(false)
    }
  }, [token, currentDate, isAdmin])

  useEffect(() => {
    fetchData()
  }, [fetchData, refreshTrigger])

  useEffect(() => {
    fetchStaff()
  }, [fetchStaff])

  useEffect(() => {
    fetchMonthlyHours()
  }, [fetchMonthlyHours])

  // Fetch bookings for a specific date (for shift assignment)
  const fetchBookingsForDate = useCallback(async (dateStr, additionalDateStr = null) => {
    if (!token || !dateStr) {
      setDateBookings([])
      return
    }

    setLoadingDateBookings(true)
    try {
      // Convert UK date (DD/MM/YYYY) to ISO (YYYY-MM-DD)
      const isoDate = ukToISO(dateStr)
      if (!isoDate || isoDate.length !== 10) {
        setDateBookings([])
        return
      }

      // Fetch bookings for start date
      const response = await fetch(`${API_URL}/api/roster/bookings-for-date?date=${isoDate}`, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Cache-Control': 'no-cache',
        },
      })

      let allBookings = []
      if (response.ok) {
        const data = await response.json()
        allBookings = Array.isArray(data) ? data : []
      }

      // If there's an additional date (end_date for overnight shifts), fetch those too
      if (additionalDateStr) {
        const isoAdditionalDate = ukToISO(additionalDateStr)
        if (isoAdditionalDate && isoAdditionalDate.length === 10 && isoAdditionalDate !== isoDate) {
          const response2 = await fetch(`${API_URL}/api/roster/bookings-for-date?date=${isoAdditionalDate}`, {
            headers: {
              Authorization: `Bearer ${token}`,
              'Cache-Control': 'no-cache',
            },
          })
          if (response2.ok) {
            const data2 = await response2.json()
            const additionalBookings = Array.isArray(data2) ? data2 : []
            // Merge and deduplicate by id
            const existingIds = new Set(allBookings.map(b => b.id))
            additionalBookings.forEach(b => {
              if (!existingIds.has(b.id)) {
                allBookings.push(b)
              }
            })
          }
        }
      }

      setDateBookings(allBookings)
    } catch (err) {
      console.error('Failed to load bookings for date:', err)
      setDateBookings([])
    } finally {
      setLoadingDateBookings(false)
    }
  }, [token])

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

    const firstDay = new Date(year, month, 1)
    const lastDay = new Date(year, month + 1, 0)
    const daysInMonth = lastDay.getDate()

    const startDayOfWeek = firstDay.getDay()

    const weeks = []
    let currentDay = 1 - startDayOfWeek

    for (let week = 0; week < 6; week++) {
      const days = []
      for (let dayOfWeek = 0; dayOfWeek < 7; dayOfWeek++) {
        if (currentDay < 1 || currentDay > daysInMonth) {
          days.push(null)
        } else {
          days.push(currentDay)
        }
        currentDay++
      }
      if (days.some((d) => d !== null)) {
        weeks.push(days)
      }
    }

    return { year, month, weeks, daysInMonth }
  }, [currentDate])

  // Group bookings by date
  const bookingsByDate = useMemo(() => {
    const grouped = {}
    const confirmedBookings = bookings.filter((b) => b.status === 'confirmed')

    confirmedBookings.forEach((booking) => {
      if (booking.dropoff_date) {
        const dropoffKey = booking.dropoff_date
        if (!grouped[dropoffKey]) {
          grouped[dropoffKey] = { dropoffs: [], pickups: [] }
        }
        grouped[dropoffKey].dropoffs.push(booking)
      }

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

  // Group shifts by date (overnight shifts appear on both dates with split times)
  const shiftsByDate = useMemo(() => {
    const grouped = {}

    shifts.forEach((shift) => {
      const isOvernight = shift.end_date && shift.end_date !== shift.date

      // Add to start date
      const startDateKey = shift.date
      if (!grouped[startDateKey]) {
        grouped[startDateKey] = []
      }
      grouped[startDateKey].push({
        ...shift,
        isOvernight,
        shiftPart: isOvernight ? 'start' : null,
        displayStartTime: shift.start_time,
        displayEndTime: isOvernight ? '23:59' : shift.end_time
      })

      // If overnight, also add to end date with the remaining time
      if (isOvernight) {
        const endDateKey = shift.end_date
        if (!grouped[endDateKey]) {
          grouped[endDateKey] = []
        }
        grouped[endDateKey].push({
          ...shift,
          isOvernight: true,
          shiftPart: 'end',
          displayStartTime: '00:00',
          displayEndTime: shift.end_time
        })
      }
    })

    Object.keys(grouped).forEach((date) => {
      grouped[date].sort((a, b) => (a.displayStartTime || a.start_time).localeCompare(b.displayStartTime || b.start_time))
    })

    return grouped
  }, [shifts])

  // Get data for a specific date
  const getDateKey = (day) => {
    if (!day) return null
    const year = calendarData.year
    const month = String(calendarData.month + 1).padStart(2, '0')
    const dayStr = String(day).padStart(2, '0')
    return `${year}-${month}-${dayStr}`
  }

  const getBookingsForDay = (day) => {
    const dateKey = getDateKey(day)
    return bookingsByDate[dateKey] || { dropoffs: [], pickups: [] }
  }

  const getShiftsForDay = (day) => {
    const dateKey = getDateKey(day)
    return shiftsByDate[dateKey] || []
  }

  // Is today?
  const isToday = (day) => {
    if (!day) return false
    const today = new Date()
    return (
      day === today.getDate() &&
      calendarData.month === today.getMonth() &&
      calendarData.year === today.getFullYear()
    )
  }

  // Handle date selection
  const handleDateClick = (day) => {
    if (!day) return
    const dateKey = getDateKey(day)
    if (selectedDate === dateKey) {
      setSelectedDate(null)
    } else {
      setSelectedDate(dateKey)
    }
  }

  // Modal handlers
  const openNewShiftModal = (date = null) => {
    setEditingShift(null)
    setShiftForm({
      staff_id: '',
      booking_ids: [],
      date: date || '',
      end_date: '',
      start_time: '',
      end_time: '',
      shift_type: 'morning',
      notes: '',
    })
    setDateBookings([])
    if (date) {
      fetchBookingsForDate(date)
    }
    setShowShiftModal(true)
  }

  const openEditShiftModal = (shift) => {
    setEditingShift(shift)
    const dateUK = formatDateUK(shift.date)
    const endDateUK = shift.end_date ? formatDateUK(shift.end_date) : ''
    // Get booking IDs from the bookings array
    const bookingIds = shift.bookings ? shift.bookings.map(b => b.id) : []
    setShiftForm({
      staff_id: shift.staff_id || '',
      booking_ids: bookingIds,
      date: dateUK,
      end_date: endDateUK !== dateUK ? endDateUK : '',  // Only show if different from start date
      start_time: formatTime(shift.start_time),
      end_time: formatTime(shift.end_time),
      shift_type: shift.shift_type,
      notes: shift.notes || '',
    })
    // Fetch bookings for both dates if overnight shift
    fetchBookingsForDate(dateUK, endDateUK !== dateUK ? endDateUK : null)
    setShowShiftModal(true)
  }

  const closeShiftModal = () => {
    setShowShiftModal(false)
    setEditingShift(null)
    setShiftForm({
      staff_id: '',
      booking_ids: [],
      date: '',
      end_date: '',
      start_time: '',
      end_time: '',
      shift_type: 'morning',
      notes: '',
    })
    setDateBookings([])
  }

  const handleShiftFormChange = (field, value) => {
    setShiftForm((prev) => {
      const newForm = { ...prev, [field]: value }

      // When date or end_date changes, fetch bookings for both dates
      if ((field === 'date' || field === 'end_date') && value && value.length === 10) {
        const startDate = field === 'date' ? value : prev.date
        const endDate = field === 'end_date' ? value : prev.end_date
        if (startDate && startDate.length === 10) {
          fetchBookingsForDate(startDate, endDate && endDate.length === 10 ? endDate : null)
        }
      }

      return newForm
    })
  }

  const saveShift = async () => {
    setSavingShift(true)
    setError('')

    try {
      // Convert UK date format to ISO for backend
      const isoDate = ukToISO(shiftForm.date)
      const isoEndDate = shiftForm.end_date ? ukToISO(shiftForm.end_date) : null

      const payload = {
        staff_id: shiftForm.staff_id ? parseInt(shiftForm.staff_id) : null,
        booking_ids: shiftForm.booking_ids.map(id => parseInt(id)),
        date: isoDate,
        end_date: isoEndDate,  // For overnight shifts
        start_time: shiftForm.start_time,
        end_time: shiftForm.end_time,
        shift_type: shiftForm.shift_type,
        notes: shiftForm.notes || null,
      }

      const url = editingShift
        ? `${API_URL}/api/roster/${editingShift.id}`
        : `${API_URL}/api/roster`

      const response = await fetch(url, {
        method: editingShift ? 'PUT' : 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
          'Cache-Control': 'no-cache',
        },
        body: JSON.stringify(payload),
      })

      if (response.ok) {
        setSuccessMessage(editingShift ? 'Shift updated' : 'Shift created')
        setTimeout(() => setSuccessMessage(''), 3000)
        closeShiftModal()
        fetchShifts()
        fetchMonthlyHours()
      } else {
        const errorData = await response.json().catch(() => ({}))
        setError(errorData.detail || 'Failed to save shift')
      }
    } catch (err) {
      setError('Network error saving shift')
    } finally {
      setSavingShift(false)
    }
  }

  const confirmDeleteShift = (shift) => {
    setShiftToDelete(shift)
    setShowDeleteModal(true)
  }

  const deleteShift = async () => {
    if (!shiftToDelete) return

    setDeletingShift(true)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/roster/${shiftToDelete.id}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${token}`,
          'Cache-Control': 'no-cache',
        },
      })

      if (response.ok) {
        setSuccessMessage('Shift deleted')
        setTimeout(() => setSuccessMessage(''), 3000)
        setShowDeleteModal(false)
        setShiftToDelete(null)
        fetchShifts()
        fetchMonthlyHours()
      } else {
        const errorData = await response.json().catch(() => ({}))
        setError(errorData.detail || 'Failed to delete shift')
      }
    } catch (err) {
      setError('Network error deleting shift')
    } finally {
      setDeletingShift(false)
    }
  }

  // Month names
  const monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ]

  // Selected date data
  const selectedDateBookings = selectedDate ? (bookingsByDate[selectedDate] || { dropoffs: [], pickups: [] }) : { dropoffs: [], pickups: [] }
  const selectedDateShifts = selectedDate ? (shiftsByDate[selectedDate] || []) : []

  return (
    <div className="roster-calendar">
      {/* Header */}
      <div className="roster-calendar-header">
        <div className="calendar-nav">
          <button className="calendar-nav-btn" onClick={goToPrevMonth}>
            ‹
          </button>
          <h2 className="calendar-title">
            {monthNames[calendarData.month]} {calendarData.year}
          </h2>
          <button className="calendar-nav-btn" onClick={goToNextMonth}>
            ›
          </button>
        </div>

        <div className="calendar-actions">
          <button className="calendar-today-btn" onClick={goToToday}>
            Today
          </button>
          <button className="calendar-refresh-btn" onClick={fetchData} disabled={loading}>
            {loading ? 'Loading...' : 'Refresh'}
          </button>
          {isAdmin && (
            <button className="roster-add-btn" onClick={() => openNewShiftModal()}>
              + Add Shift
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      {error && <div className="roster-error">{error}</div>}
      {successMessage && <div className="roster-success">{successMessage}</div>}

      {/* Calendar Grid */}
      <div className="calendar-grid">
        <div className="calendar-weekdays">
          {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((day) => (
            <div key={day} className="calendar-weekday">
              {day}
            </div>
          ))}
        </div>

        <div className="calendar-weeks">
          {calendarData.weeks.map((week, weekIndex) => (
            <div key={weekIndex} className="calendar-week">
              {week.map((day, dayIndex) => {
                const dayBookings = getBookingsForDay(day)
                const dayShifts = getShiftsForDay(day)
                const dateKey = getDateKey(day)
                const hasDropoffs = dayBookings.dropoffs.length > 0
                const hasPickups = dayBookings.pickups.length > 0
                const hasShifts = dayShifts.length > 0
                const hasContent = hasDropoffs || hasPickups || hasShifts

                return (
                  <div
                    key={dayIndex}
                    className={`calendar-day ${day ? '' : 'empty'} ${isToday(day) ? 'today' : ''} ${
                      selectedDate === dateKey ? 'selected' : ''
                    } ${hasContent ? 'has-content' : ''}`}
                    onClick={() => handleDateClick(day)}
                  >
                    {day && (
                      <>
                        <span className="day-number">{day}</span>
                        <div className="day-content">
                          {/* Booking badges */}
                          {hasDropoffs && (
                            <div className="day-badge badge-dropoff">
                              🚗 {dayBookings.dropoffs.length}
                            </div>
                          )}
                          {hasPickups && (
                            <div className="day-badge badge-pickup">
                              🛬 {dayBookings.pickups.length}
                            </div>
                          )}
                          {/* Shift indicators with details */}
                          {hasShifts && dayShifts.map((shift, idx) => (
                            <div
                              key={`${shift.id}-${shift.shiftPart || 'full'}`}
                              className={`day-shift-badge ${shift.isOvernight ? 'overnight' : ''} ${shift.shiftPart === 'end' ? 'overnight-end' : ''}`}
                              title={shift.staff_first_name ? `${shift.staff_first_name} ${shift.staff_last_name}` : 'Unassigned'}
                            >
                              <span className="shift-time-mini">
                                {formatTime(shift.displayStartTime)}-{formatTime(shift.displayEndTime)}
                              </span>
                              {shift.staff_initials && <span className="shift-initials">{shift.staff_initials}</span>}
                              {!shift.staff_initials && <span className="shift-unassigned-mini">?</span>}
                            </div>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Monthly Hours Summary (for payroll) */}
      {monthlyHours && (
        <div className="weekly-hours-section">
          <h3 className="weekly-hours-title">
            Monthly Hours <span className="week-range">({monthlyHours.month_name} {monthlyHours.year})</span>
          </h3>
          {loadingMonthlyHours ? (
            <div className="weekly-hours-loading">Loading...</div>
          ) : isAdmin ? (
            // Admin view: show all employees
            <div className="weekly-hours-grid">
              {monthlyHours.employees && monthlyHours.employees.length > 0 ? (
                monthlyHours.employees.map((emp) => (
                  <div key={emp.employee_id} className="weekly-hours-card">
                    <div className="employee-name">{emp.employee_name}</div>
                    <div className="hours-summary">
                      <span className="total-hours">{emp.total_hours.toFixed(1)}h</span>
                      <span className="shift-count">({emp.shift_count} shifts)</span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="no-hours">No shifts scheduled this month</div>
              )}
            </div>
          ) : (
            // Employee view: show only their own hours
            <div className="weekly-hours-grid">
              <div className="weekly-hours-card own-hours">
                <div className="employee-name">Your Hours</div>
                <div className="hours-summary">
                  <span className="total-hours">{monthlyHours.total_hours?.toFixed(1) || 0}h</span>
                  <span className="shift-count">({monthlyHours.shift_count || 0} shifts)</span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Detail Panel - Shows both bookings and shifts */}
      {selectedDate && (
        <div className="roster-detail-panel">
          <div className="detail-header">
            <h3>
              {new Date(selectedDate + 'T00:00:00').toLocaleDateString('en-GB', {
                weekday: 'long',
                day: 'numeric',
                month: 'long',
                year: 'numeric',
              })}
            </h3>
            <div className="detail-header-actions">
              {isAdmin && (
                <button
                  className="roster-add-btn-small"
                  onClick={() => openNewShiftModal(formatDateUK(selectedDate))}
                >
                  + Add Shift
                </button>
              )}
              <button className="detail-close" onClick={() => setSelectedDate(null)}>
                ×
              </button>
            </div>
          </div>

          <div className="detail-content">
            {/* Drop-offs Section */}
            {selectedDateBookings.dropoffs.length > 0 && (
              <div className="detail-section">
                <h4 className="detail-section-title dropoff">
                  🚗 Drop-offs ({selectedDateBookings.dropoffs.length})
                </h4>
                <div className="detail-bookings">
                  {selectedDateBookings.dropoffs
                    .sort((a, b) => (a.dropoff_time || '').localeCompare(b.dropoff_time || ''))
                    .map((booking) => (
                      <div key={booking.id} className="detail-booking-card">
                        <div className="booking-header-row">
                          <div className="booking-time">{formatTime(booking.dropoff_time)}</div>
                          <div className="booking-flight">
                            {booking.dropoff_airline_name && (
                              <span className="airline-name">{booking.dropoff_airline_name}</span>
                            )}
                            {booking.dropoff_flight_number && booking.dropoff_flight_number !== 'Unknown' && (
                              <span className="flight-number">{booking.dropoff_flight_number}</span>
                            )}
                          </div>
                          <div className="booking-destination">
                            → {booking.dropoff_destination || 'Unknown'}
                            {booking.flight_departure_time && (
                              <span className="flight-time-info">
                                Departs: {formatTime(booking.flight_departure_time)}
                              </span>
                            )}
                          </div>
                          <div className="booking-ref">{booking.reference}</div>
                        </div>
                        <div className="booking-details-row">
                          {booking.customer?.first_name || booking.customer_first_name}{' '}
                          {booking.customer?.last_name || booking.customer_last_name}
                          <span>|</span>
                          <a href={`tel:${booking.customer?.phone}`} className="phone-link">
                            {booking.customer?.phone || 'N/A'}
                          </a>
                          <span>|</span>
                          {booking.vehicle?.colour} {booking.vehicle?.make} {booking.vehicle?.model}
                          <span>|</span>
                          <span className="reg-plate">
                            {booking.vehicle?.registration || booking.vehicle_registration}
                          </span>
                        </div>
                        {renderBookingActions && renderBookingActions(booking, 'dropoff')}
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* Pick-ups Section */}
            {selectedDateBookings.pickups.length > 0 && (
              <div className="detail-section">
                <h4 className="detail-section-title pickup">
                  🛬 Pick-ups ({selectedDateBookings.pickups.length})
                </h4>
                <div className="detail-bookings">
                  {selectedDateBookings.pickups
                    .sort((a, b) => (a.pickup_time || '').localeCompare(b.pickup_time || ''))
                    .map((booking) => (
                      <div key={booking.id} className="detail-booking-card">
                        <div className="booking-header-row">
                          <div className="booking-time">{formatTime(booking.pickup_time)}</div>
                          <div className="booking-flight">
                            {booking.pickup_airline_name && (
                              <span className="airline-name">{booking.pickup_airline_name}</span>
                            )}
                            {booking.pickup_flight_number && booking.pickup_flight_number !== 'Unknown' && (
                              <span className="flight-number">{booking.pickup_flight_number}</span>
                            )}
                          </div>
                          <div className="booking-destination">
                            ← {booking.pickup_origin || 'Unknown'}
                            {booking.flight_arrival_time && (
                              <span className="flight-time-info">
                                Arrives: {formatTime(booking.flight_arrival_time)}
                              </span>
                            )}
                          </div>
                          <div className="booking-ref">{booking.reference}</div>
                        </div>
                        <div className="booking-details-row">
                          {booking.customer?.first_name || booking.customer_first_name}{' '}
                          {booking.customer?.last_name || booking.customer_last_name}
                          <span>|</span>
                          <a href={`tel:${booking.customer?.phone}`} className="phone-link">
                            {booking.customer?.phone || 'N/A'}
                          </a>
                          <span>|</span>
                          {booking.vehicle?.colour} {booking.vehicle?.make} {booking.vehicle?.model}
                          <span>|</span>
                          <span className="reg-plate">
                            {booking.vehicle?.registration || booking.vehicle_registration}
                          </span>
                        </div>
                        {renderBookingActions && renderBookingActions(booking, 'pickup')}
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* Shifts Section */}
            {selectedDateShifts.length > 0 && (
              <div className="detail-section">
                <h4 className="detail-section-title shifts">
                  📅 Shifts ({selectedDateShifts.length})
                </h4>
                <div className="shift-list">
                  {selectedDateShifts.map((shift) => {
                    const typeConfig = SHIFT_TYPE_CONFIG[shift.shift_type] || SHIFT_TYPE_CONFIG.other
                    const statusConfig = SHIFT_STATUS_CONFIG[shift.status] || SHIFT_STATUS_CONFIG.scheduled

                    return (
                      <div key={shift.id} className="shift-card">
                        <div className="shift-card-header">
                          <div className="shift-time-range">
                            <span className="shift-time">{formatTime(shift.start_time)}</span>
                            <span className="shift-time-separator">to</span>
                            <span className="shift-time">{formatTime(shift.end_time)}</span>
                          </div>
                          <div className="shift-type-badge" style={{ background: typeConfig.color }}>
                            {typeConfig.icon} {typeConfig.label}
                          </div>
                          <div
                            className="shift-status-badge"
                            style={{ borderColor: statusConfig.color, color: statusConfig.color }}
                          >
                            {statusConfig.label}
                          </div>
                          {shift.isOvernight && (
                            <div className="shift-overnight-badge" title="Overnight shift">
                              🌙 {new Date(shift.date + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} → {new Date(shift.end_date + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
                            </div>
                          )}
                        </div>

                        <div className="shift-card-body">
                          {shift.staff_first_name ? (
                            <div className="shift-staff">
                              <span className="shift-staff-initials">{shift.staff_initials}</span>
                              <span className="shift-staff-name">{shift.staff_first_name} {shift.staff_last_name}</span>
                            </div>
                          ) : (
                            <div className="shift-unassigned">Unassigned</div>
                          )}

                          {/* Show linked bookings */}
                          {shift.bookings && shift.bookings.length > 0 ? (
                            <div className="shift-bookings-list">
                              {shift.bookings.map((booking, idx) => (
                                <div key={booking.id} className="shift-booking-info">
                                  <div className="shift-booking-header">
                                    <span className={`shift-booking-type ${booking.type}`}>
                                      {booking.type === 'dropoff' ? '🚗' : '🛬'}
                                    </span>
                                    <span className="shift-booking-ref">{booking.reference}</span>
                                    <span className="shift-booking-customer">{booking.customer_name}</span>
                                  </div>
                                  <div className="shift-booking-details">
                                    {booking.time && (
                                      <span className="shift-booking-time">@ {booking.time}</span>
                                    )}
                                    {booking.flight_number && (
                                      <span className="shift-booking-flight">{booking.flight_number}</span>
                                    )}
                                    {booking.destination && (
                                      <span className="shift-booking-dest">
                                        {booking.type === 'dropoff' ? '→' : '←'} {booking.destination}
                                      </span>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="shift-no-bookings">No bookings linked</div>
                          )}

                          {shift.notes && <div className="shift-notes">{shift.notes}</div>}
                        </div>

                        {isAdmin && (
                          <div className="shift-card-actions">
                            <button className="shift-edit-btn" onClick={() => openEditShiftModal(shift)}>
                              Edit
                            </button>
                            <button className="shift-delete-btn" onClick={() => confirmDeleteShift(shift)}>
                              Delete
                            </button>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* No content message */}
            {selectedDateBookings.dropoffs.length === 0 &&
              selectedDateBookings.pickups.length === 0 &&
              selectedDateShifts.length === 0 && (
                <p className="no-content">No bookings or shifts scheduled for this date.</p>
              )}
          </div>
        </div>
      )}

      {/* Shift Modal (Admin only) */}
      {showShiftModal && isAdmin && (
        <div className="modal-overlay" onClick={closeShiftModal}>
          <div className="modal-content modal-content-wide" onClick={(e) => e.stopPropagation()}>
            <h3>{editingShift ? 'Edit Shift' : 'New Shift'}</h3>

            <div className="modal-form">
              <h4 className="modal-section-title">Shift Details</h4>
              <div className="modal-form-row">
                <div className="modal-form-group">
                  <label>Date (DD/MM/YYYY)</label>
                  <input
                    type="text"
                    value={shiftForm.date}
                    onChange={(e) => handleShiftFormChange('date', e.target.value)}
                    placeholder="DD/MM/YYYY"
                  />
                </div>
                <div className="modal-form-group">
                  <label>Start Time (24hr)</label>
                  <input
                    type="text"
                    value={shiftForm.start_time}
                    onChange={(e) => handleShiftFormChange('start_time', e.target.value)}
                    placeholder="HH:MM"
                    maxLength={5}
                  />
                </div>
                <div className="modal-form-group">
                  <label>End Time (24hr)</label>
                  <input
                    type="text"
                    value={shiftForm.end_time}
                    onChange={(e) => handleShiftFormChange('end_time', e.target.value)}
                    placeholder="HH:MM"
                    maxLength={5}
                  />
                </div>
                <div className="modal-form-group">
                  <label>End Date (overnight)</label>
                  <input
                    type="text"
                    value={shiftForm.end_date}
                    onChange={(e) => handleShiftFormChange('end_date', e.target.value)}
                    placeholder="DD/MM/YYYY"
                  />
                  <small style={{ color: '#888', fontSize: '0.75rem' }}>Leave blank for same-day shifts</small>
                </div>
              </div>

              <div className="modal-form-row">
                <div className="modal-form-group">
                  <label>Shift Type</label>
                  <select
                    value={shiftForm.shift_type}
                    onChange={(e) => handleShiftFormChange('shift_type', e.target.value)}
                  >
                    <optgroup label="Part-Time Shifts">
                      <option value="early_morning">Early Morning (03:50 - 07:00)</option>
                      <option value="morning">Morning (07:00 - 11:00)</option>
                      <option value="midday">Midday (11:00 - 14:00)</option>
                      <option value="afternoon">Afternoon (14:00 - 17:30)</option>
                      <option value="late_afternoon">Late Afternoon (17:30 - 21:00)</option>
                      <option value="evening">Evening (21:00 - 01:20)</option>
                    </optgroup>
                    <optgroup label="Full-Time Shifts">
                      <option value="full_morning">Full Morning (03:50 - 14:00)</option>
                      <option value="full_afternoon">Full Afternoon (11:00 - 21:00)</option>
                      <option value="full_evening">Full Evening (17:30 - 01:20)</option>
                    </optgroup>
                  </select>
                </div>
                <div className="modal-form-group">
                  <label>Assign Staff</label>
                  <select
                    value={shiftForm.staff_id}
                    onChange={(e) => handleShiftFormChange('staff_id', e.target.value)}
                  >
                    <option value="">Unassigned</option>
                    {employees.map((emp) => (
                      <option key={emp.id} value={emp.id}>
                        {emp.first_name} {emp.last_name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Link to Bookings - full width multi-select */}
              <div className="modal-form-group">
                <label>Link to Bookings {shiftForm.booking_ids.length > 0 && `(${shiftForm.booking_ids.length} selected)`}</label>
                {loadingDateBookings ? (
                  <div className="booking-checkboxes loading">Loading bookings...</div>
                ) : dateBookings.length === 0 ? (
                  <div className="booking-checkboxes empty">No bookings on this date</div>
                ) : (
                  <div className="booking-checkboxes">
                    {dateBookings.filter(b => b.type === 'dropoff').length > 0 && (
                      <div className="booking-group">
                        <div className="booking-group-label">🚗 Drop-offs</div>
                        {dateBookings.filter(b => b.type === 'dropoff').map((b) => (
                          <label key={`dropoff-${b.id}`} className="booking-checkbox">
                            <input
                              type="checkbox"
                              checked={shiftForm.booking_ids.includes(b.id)}
                              onChange={(e) => {
                                if (e.target.checked) {
                                  handleShiftFormChange('booking_ids', [...shiftForm.booking_ids, b.id])
                                } else {
                                  handleShiftFormChange('booking_ids', shiftForm.booking_ids.filter(id => id !== b.id))
                                }
                              }}
                            />
                            <span className="booking-info">
                              <span className="booking-time">{b.time}</span>
                              <span className="booking-ref">{b.reference}</span>
                              <span className="booking-customer">{b.customer_name}</span>
                            </span>
                          </label>
                        ))}
                      </div>
                    )}
                    {dateBookings.filter(b => b.type === 'pickup').length > 0 && (
                      <div className="booking-group">
                        <div className="booking-group-label">✈️ Pick-ups</div>
                        {dateBookings.filter(b => b.type === 'pickup').map((b) => (
                          <label key={`pickup-${b.id}`} className="booking-checkbox">
                            <input
                              type="checkbox"
                              checked={shiftForm.booking_ids.includes(b.id)}
                              onChange={(e) => {
                                if (e.target.checked) {
                                  handleShiftFormChange('booking_ids', [...shiftForm.booking_ids, b.id])
                                } else {
                                  handleShiftFormChange('booking_ids', shiftForm.booking_ids.filter(id => id !== b.id))
                                }
                              }}
                            />
                            <span className="booking-info">
                              <span className="booking-time">{b.time}</span>
                              <span className="booking-ref">{b.reference}</span>
                              <span className="booking-customer">{b.customer_name}</span>
                            </span>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="modal-form-group">
                <label>Notes</label>
                <textarea
                  value={shiftForm.notes}
                  onChange={(e) => handleShiftFormChange('notes', e.target.value)}
                  placeholder="Optional notes..."
                  rows={3}
                />
              </div>
            </div>

            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={closeShiftModal} disabled={savingShift}>
                Cancel
              </button>
              <button className="modal-btn modal-btn-primary" onClick={saveShift} disabled={savingShift}>
                {savingShift ? 'Saving...' : editingShift ? 'Save Changes' : 'Create Shift'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteModal && shiftToDelete && (
        <div className="modal-overlay" onClick={() => setShowDeleteModal(false)}>
          <div className="modal-content delete-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Delete Shift</h3>
            <p>
              Are you sure you want to delete this shift on{' '}
              <strong>{formatDateUK(shiftToDelete.date)}</strong> at{' '}
              <strong>{formatTime(shiftToDelete.start_time)}</strong>?
            </p>
            <div className="modal-actions">
              <button
                className="modal-cancel-btn"
                onClick={() => setShowDeleteModal(false)}
                disabled={deletingShift}
              >
                Cancel
              </button>
              <button className="modal-delete-btn" onClick={deleteShift} disabled={deletingShift}>
                {deletingShift ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default RosterCalendar
