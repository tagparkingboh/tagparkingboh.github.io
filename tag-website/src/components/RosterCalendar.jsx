import { useState, useEffect, useMemo, useCallback } from 'react'
import './RosterCalendar.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Shift type display config
const SHIFT_TYPE_CONFIG = {
  departure: { label: 'Departure', color: '#4a90e2', icon: '✈️' },
  arrival: { label: 'Arrival', color: '#50c878', icon: '🛬' },
  storage: { label: 'Storage', color: '#f5a623', icon: '🅿️' },
  admin: { label: 'Admin', color: '#9b59b6', icon: '📋' },
  other: { label: 'Other', color: '#888', icon: '📌' },
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

// UK date format helpers
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

// Format time for display (HH:MM)
const formatTime = (timeStr) => {
  if (!timeStr) return ''
  // Handle both "HH:MM" and "HH:MM:SS" formats
  return timeStr.substring(0, 5)
}

function RosterCalendar({ token, isAdmin = false, employeeId = null, refreshTrigger = 0 }) {
  const [currentDate, setCurrentDate] = useState(new Date())
  const [shifts, setShifts] = useState([])
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
    date: '',
    start_time: '',
    end_time: '',
    shift_type: 'departure',
    notes: '',
  })
  const [savingShift, setSavingShift] = useState(false)

  // Delete confirmation
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [shiftToDelete, setShiftToDelete] = useState(null)
  const [deletingShift, setDeletingShift] = useState(false)

  // Fetch shifts
  const fetchShifts = useCallback(async () => {
    if (!token) return

    setLoading(true)
    setError('')
    try {
      // Build query params based on current month view
      const year = currentDate.getFullYear()
      const month = currentDate.getMonth()
      const startDate = new Date(year, month, 1)
      const endDate = new Date(year, month + 1, 0)

      const params = new URLSearchParams({
        date_from: formatDateUK(formatDateISO(startDate)),
        date_to: formatDateUK(formatDateISO(endDate)),
      })

      const endpoint = isAdmin ? '/api/roster' : '/api/employee/shifts'
      const response = await fetch(`${API_URL}${endpoint}?${params}`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })

      if (response.ok) {
        const data = await response.json()
        setShifts(data.shifts || [])
      } else {
        const errorData = await response.json().catch(() => ({}))
        setError(errorData.detail || 'Failed to load shifts')
      }
    } catch (err) {
      setError('Network error loading shifts')
    } finally {
      setLoading(false)
    }
  }, [token, currentDate, isAdmin])

  // Fetch employees (admin only)
  const fetchEmployees = useCallback(async () => {
    if (!token || !isAdmin) return

    try {
      const response = await fetch(`${API_URL}/api/employees`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })

      if (response.ok) {
        const data = await response.json()
        setEmployees(data.employees || [])
      }
    } catch (err) {
      console.error('Failed to load employees:', err)
    }
  }, [token, isAdmin])

  useEffect(() => {
    fetchShifts()
  }, [fetchShifts, refreshTrigger])

  useEffect(() => {
    fetchEmployees()
  }, [fetchEmployees])

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

    // What day of week does the month start on (0 = Sunday)
    const startDayOfWeek = firstDay.getDay()

    // Build calendar grid
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

  // Group shifts by date
  const shiftsByDate = useMemo(() => {
    const grouped = {}

    shifts.forEach((shift) => {
      const dateKey = shift.date
      if (!grouped[dateKey]) {
        grouped[dateKey] = []
      }
      grouped[dateKey].push(shift)
    })

    // Sort shifts within each date by start time
    Object.keys(grouped).forEach((date) => {
      grouped[date].sort((a, b) => a.start_time.localeCompare(b.start_time))
    })

    return grouped
  }, [shifts])

  // Get shifts for a specific date
  const getShiftsForDay = (day) => {
    if (!day) return []
    const year = calendarData.year
    const month = String(calendarData.month + 1).padStart(2, '0')
    const dayStr = String(day).padStart(2, '0')
    const dateKey = `${year}-${month}-${dayStr}`
    return shiftsByDate[dateKey] || []
  }

  // Handle date selection
  const handleDateClick = (day) => {
    if (!day) return
    const year = calendarData.year
    const month = String(calendarData.month + 1).padStart(2, '0')
    const dayStr = String(day).padStart(2, '0')
    const dateKey = `${year}-${month}-${dayStr}`

    if (selectedDate === dateKey) {
      setSelectedDate(null)
    } else {
      setSelectedDate(dateKey)
    }
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

  // Modal handlers
  const openNewShiftModal = (date = null) => {
    setEditingShift(null)
    setShiftForm({
      staff_id: '',
      date: date || '',
      start_time: '',
      end_time: '',
      shift_type: 'departure',
      notes: '',
    })
    setShowShiftModal(true)
  }

  const openEditShiftModal = (shift) => {
    setEditingShift(shift)
    setShiftForm({
      staff_id: shift.staff_id || '',
      date: formatDateUK(shift.date),
      start_time: formatTime(shift.start_time),
      end_time: formatTime(shift.end_time),
      shift_type: shift.shift_type,
      notes: shift.notes || '',
    })
    setShowShiftModal(true)
  }

  const closeShiftModal = () => {
    setShowShiftModal(false)
    setEditingShift(null)
    setShiftForm({
      staff_id: '',
      date: '',
      start_time: '',
      end_time: '',
      shift_type: 'departure',
      notes: '',
    })
  }

  const handleShiftFormChange = (field, value) => {
    setShiftForm((prev) => ({ ...prev, [field]: value }))
  }

  const saveShift = async () => {
    setSavingShift(true)
    setError('')

    try {
      const payload = {
        staff_id: shiftForm.staff_id ? parseInt(shiftForm.staff_id) : null,
        date: shiftForm.date,
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
        },
        body: JSON.stringify(payload),
      })

      if (response.ok) {
        setSuccessMessage(editingShift ? 'Shift updated' : 'Shift created')
        setTimeout(() => setSuccessMessage(''), 3000)
        closeShiftModal()
        fetchShifts()
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
        },
      })

      if (response.ok) {
        setSuccessMessage('Shift deleted')
        setTimeout(() => setSuccessMessage(''), 3000)
        setShowDeleteModal(false)
        setShiftToDelete(null)
        fetchShifts()
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

  // Selected date shifts
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
          <button className="calendar-refresh-btn" onClick={fetchShifts} disabled={loading}>
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
                const dayShifts = getShiftsForDay(day)
                const year = calendarData.year
                const month = String(calendarData.month + 1).padStart(2, '0')
                const dayStr = day ? String(day).padStart(2, '0') : ''
                const dateKey = day ? `${year}-${month}-${dayStr}` : ''

                return (
                  <div
                    key={dayIndex}
                    className={`calendar-day ${day ? '' : 'empty'} ${isToday(day) ? 'today' : ''} ${
                      selectedDate === dateKey ? 'selected' : ''
                    } ${dayShifts.length > 0 ? 'has-shifts' : ''}`}
                    onClick={() => handleDateClick(day)}
                  >
                    {day && (
                      <>
                        <span className="day-number">{day}</span>
                        <div className="day-badges">
                          {dayShifts.slice(0, 3).map((shift, idx) => {
                            const typeConfig = SHIFT_TYPE_CONFIG[shift.shift_type] || SHIFT_TYPE_CONFIG.other
                            return (
                              <div
                                key={idx}
                                className="shift-badge"
                                style={{ borderLeftColor: typeConfig.color }}
                              >
                                <span className="shift-badge-time">{formatTime(shift.start_time)}</span>
                                {shift.staff_initials && (
                                  <span className="shift-badge-staff">{shift.staff_initials}</span>
                                )}
                              </div>
                            )
                          })}
                          {dayShifts.length > 3 && (
                            <div className="shift-badge-more">+{dayShifts.length - 3} more</div>
                          )}
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

      {/* Detail Panel */}
      {selectedDate && (
        <div className="roster-detail-panel">
          <div className="detail-header">
            <h3>{formatDateUK(selectedDate)}</h3>
            <div className="detail-header-actions">
              {isAdmin && (
                <button
                  className="roster-add-btn-small"
                  onClick={() => openNewShiftModal(formatDateUK(selectedDate))}
                >
                  + Add
                </button>
              )}
              <button className="detail-close" onClick={() => setSelectedDate(null)}>
                ×
              </button>
            </div>
          </div>

          <div className="detail-content">
            {selectedDateShifts.length === 0 ? (
              <p className="no-shifts">No shifts scheduled for this date.</p>
            ) : (
              <div className="shift-list">
                {selectedDateShifts.map((shift) => {
                  const typeConfig = SHIFT_TYPE_CONFIG[shift.shift_type] || SHIFT_TYPE_CONFIG.other
                  const statusConfig = SHIFT_STATUS_CONFIG[shift.status] || SHIFT_STATUS_CONFIG.scheduled

                  return (
                    <div key={shift.id} className="shift-card">
                      <div className="shift-card-header">
                        <div className="shift-time-range">
                          <span className="shift-time">{formatTime(shift.start_time)}</span>
                          <span className="shift-time-separator">-</span>
                          <span className="shift-time">{formatTime(shift.end_time)}</span>
                        </div>
                        <div
                          className="shift-type-badge"
                          style={{ background: typeConfig.color }}
                        >
                          {typeConfig.icon} {typeConfig.label}
                        </div>
                        <div
                          className="shift-status-badge"
                          style={{ borderColor: statusConfig.color, color: statusConfig.color }}
                        >
                          {statusConfig.label}
                        </div>
                      </div>

                      <div className="shift-card-body">
                        {shift.staff_name ? (
                          <div className="shift-staff">
                            <span className="shift-staff-initials">{shift.staff_initials}</span>
                            <span className="shift-staff-name">{shift.staff_name}</span>
                          </div>
                        ) : (
                          <div className="shift-unassigned">Unassigned</div>
                        )}

                        {shift.booking_reference && (
                          <div className="shift-booking">
                            <span className="shift-booking-label">Booking:</span>
                            <span className="shift-booking-ref">{shift.booking_reference}</span>
                          </div>
                        )}

                        {shift.notes && <div className="shift-notes">{shift.notes}</div>}
                      </div>

                      {isAdmin && (
                        <div className="shift-card-actions">
                          <button
                            className="shift-edit-btn"
                            onClick={() => openEditShiftModal(shift)}
                          >
                            Edit
                          </button>
                          <button
                            className="shift-delete-btn"
                            onClick={() => confirmDeleteShift(shift)}
                          >
                            Delete
                          </button>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Shift Modal (Admin only) */}
      {showShiftModal && isAdmin && (
        <div className="modal-overlay" onClick={closeShiftModal}>
          <div className="modal-content shift-modal" onClick={(e) => e.stopPropagation()}>
            <h3>{editingShift ? 'Edit Shift' : 'New Shift'}</h3>

            <div className="shift-form">
              <div className="form-row">
                <label>Date</label>
                <input
                  type="text"
                  value={shiftForm.date}
                  onChange={(e) => handleShiftFormChange('date', e.target.value)}
                  placeholder="DD/MM/YYYY"
                />
              </div>

              <div className="form-row form-row-double">
                <div className="form-field">
                  <label>Start Time</label>
                  <input
                    type="time"
                    value={shiftForm.start_time}
                    onChange={(e) => handleShiftFormChange('start_time', e.target.value)}
                  />
                </div>
                <div className="form-field">
                  <label>End Time</label>
                  <input
                    type="time"
                    value={shiftForm.end_time}
                    onChange={(e) => handleShiftFormChange('end_time', e.target.value)}
                  />
                </div>
              </div>

              <div className="form-row">
                <label>Shift Type</label>
                <select
                  value={shiftForm.shift_type}
                  onChange={(e) => handleShiftFormChange('shift_type', e.target.value)}
                >
                  {Object.entries(SHIFT_TYPE_CONFIG).map(([key, config]) => (
                    <option key={key} value={key}>
                      {config.icon} {config.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-row">
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

              <div className="form-row">
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
              <button className="modal-cancel-btn" onClick={closeShiftModal} disabled={savingShift}>
                Cancel
              </button>
              <button className="modal-save-btn" onClick={saveShift} disabled={savingShift}>
                {savingShift ? 'Saving...' : editingShift ? 'Update Shift' : 'Create Shift'}
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
