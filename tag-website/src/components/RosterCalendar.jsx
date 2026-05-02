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

// Holiday type display config
const HOLIDAY_TYPE_CONFIG = {
  holiday: { label: 'Holiday', color: '#f5a623', icon: '🏖️' },
  sick: { label: 'Sick', color: '#e74c3c', icon: '🤒' },
  personal: { label: 'Personal', color: '#9b59b6', icon: '🏠' },
  other: { label: 'Other', color: '#888', icon: '📅' },
  unavailable: { label: 'Unavailable', color: '#95a5a6', icon: '🚫' },
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

// Previous day as ISO string. UTC math avoids any DST drift.
export const prevIsoDate = (isoDate) => {
  if (!isoDate) return ''
  const [y, m, d] = isoDate.split('-').map(Number)
  if (!y || !m || !d) return ''
  const dt = new Date(Date.UTC(y, m - 1, d))
  dt.setUTCDate(dt.getUTCDate() - 1)
  const yy = dt.getUTCFullYear()
  const mm = String(dt.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(dt.getUTCDate()).padStart(2, '0')
  return `${yy}-${mm}-${dd}`
}

// Convert UK date (DD/MM/YYYY) to ISO (YYYY-MM-DD)
const ukToISO = (ukDate) => {
  if (!ukDate) return ''
  const parts = ukDate.split('/')
  if (parts.length !== 3) return ukDate
  return `${parts[2]}-${parts[1]}-${parts[0]}`
}

// Pickups before this UK clock-time on date D+1 are bucketed back to
// date D's operational day (e.g. a 00:25 pickup on the 10th is shown
// under the 9th, where the overnight shift covering it started).
// Drop-offs are NOT re-bucketed — early-AM drop-offs aren't an
// operational reality in this business. Heuristic chosen over reading
// shifts data so the Employee page (which only has access to its own
// shifts) and the Admin page produce identical groupings.
export const PICKUP_OVERNIGHT_CUTOFF = '02:30'

// Group confirmed and refunded bookings by operational day. Drop-offs key on
// `dropoff_date` directly. Pickups key on `pickup_date` unless the
// pickup_time is strictly before PICKUP_OVERNIGHT_CUTOFF, in which
// case they're attributed to the previous calendar day. Each day's
// list is sorted by real datetime so re-bucketed events land at the
// bottom (chronologically later than 23:55 of the same operational day).
//
// Refunded bookings are surfaced too so operators have full visibility
// into TAG-initiated refund situations on the day; the rendering layer
// is responsible for visual differentiation.
export const computeBookingsByDate = (bookings) => {
  const grouped = {}
  const ensureDay = (key) => {
    if (!grouped[key]) grouped[key] = { dropoffs: [], pickups: [] }
    return grouped[key]
  }
  const claimPickupDate = (rawDate, rawTime) => {
    if (!rawDate) return null
    if (!rawTime) return rawDate
    const t = String(rawTime).slice(0, 5)
    if (t < PICKUP_OVERNIGHT_CUTOFF) return prevIsoDate(rawDate)
    return rawDate
  }
  const sortKey = (date, time) =>
    `${date}T${time ? String(time).slice(0, 5) : '00:00'}`

  ;(bookings || [])
    .filter((b) => b && (b.status === 'confirmed' || b.status === 'refunded'))
    .forEach((booking) => {
      if (booking.dropoff_date) {
        ensureDay(booking.dropoff_date).dropoffs.push(booking)
      }
      if (booking.pickup_date) {
        const key = claimPickupDate(booking.pickup_date, booking.pickup_time)
        if (key) ensureDay(key).pickups.push(booking)
      }
    })

  Object.values(grouped).forEach((day) => {
    day.dropoffs.sort((a, b) =>
      sortKey(a.dropoff_date, a.dropoff_time).localeCompare(
        sortKey(b.dropoff_date, b.dropoff_time)
      )
    )
    day.pickups.sort((a, b) =>
      sortKey(a.pickup_date, a.pickup_time).localeCompare(
        sortKey(b.pickup_date, b.pickup_time)
      )
    )
  })

  return grouped
}

// Format time for display (HH:MM)
const formatTime = (timeStr) => {
  if (!timeStr) return ''
  // Handle both "HH:MM" and "HH:MM:SS" formats
  return timeStr.substring(0, 5)
}

// Format time input to 24-hour format (HH:MM) with auto-colon insertion
const formatTimeInput24h = (input, previousValue = '') => {
  // Remove non-digits except colon
  const cleaned = input.replace(/[^\d:]/g, '')
  // Split on colon if present
  const parts = cleaned.split(':')

  if (parts.length === 1) {
    // No colon yet - just digits
    const digits = parts[0]
    if (digits.length <= 2) return digits
    // Auto-insert colon after 2 digits
    if (digits.length <= 4) return digits.slice(0, 2) + ':' + digits.slice(2)
    return digits.slice(0, 2) + ':' + digits.slice(2, 4)
  } else {
    // Has colon - format as HH:MM
    const hours = parts[0].slice(0, 2)
    const minutes = (parts[1] || '').slice(0, 2)
    return hours + ':' + minutes
  }
}

function RosterCalendar({ token, isAdmin = false, employeeId = null, refreshTrigger = 0, renderBookingActions = null, sourceFilter = null }) {
  const [currentDate, setCurrentDate] = useState(new Date())
  const [shifts, setShifts] = useState([])
  // Teammates' shifts (view-only, employee mode only). Stripped shape from
  // /api/employee/team-shifts — no id, no staff_id, no shift_type.
  const [teamShifts, setTeamShifts] = useState([])
  const [teamShiftPopover, setTeamShiftPopover] = useState(null) // { initials, first_name, last_name, phone, date, end_date, start_time, end_time }
  const [bookings, setBookings] = useState([])
  const [employees, setEmployees] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedDate, setSelectedDate] = useState(null)
  const [showDetailModal, setShowDetailModal] = useState(false)
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
    intended_driver_type: 'jockey',
  })
  const [savingShift, setSavingShift] = useState(false)
  const [dateBookings, setDateBookings] = useState([])
  const [loadingDateBookings, setLoadingDateBookings] = useState(false)

  // Duplicate shift state
  const [duplicateMode, setDuplicateMode] = useState(false)
  const [additionalStaffIds, setAdditionalStaffIds] = useState([])  // Up to 6 additional staff

  // Delete confirmation
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [shiftToDelete, setShiftToDelete] = useState(null)
  const [deletingShift, setDeletingShift] = useState(false)

  // Bulk edit state
  const [selectedShiftIds, setSelectedShiftIds] = useState([])
  const [showBulkEditModal, setShowBulkEditModal] = useState(false)
  const [bulkEditForm, setBulkEditForm] = useState({
    action: 'edit_times',  // 'edit_times', 'add_bookings', 'delete'
    start_time: '',
    end_time: '',
    booking_ids: [],
  })
  const [savingBulkEdit, setSavingBulkEdit] = useState(false)

  // Monthly hours (for payroll)
  const [monthlyHours, setMonthlyHours] = useState(null)
  const [loadingMonthlyHours, setLoadingMonthlyHours] = useState(false)
  const [hoursExpanded, setHoursExpanded] = useState(false)  // Hours section collapsed by default
  const [expandedWeeks, setExpandedWeeks] = useState({})  // Track which weeks are expanded
  const [monthlyTotalsExpanded, setMonthlyTotalsExpanded] = useState(false)  // Monthly totals collapsed by default

  // Blocked dates state
  const [blockedDates, setBlockedDates] = useState([])
  const [showBlockedDateModal, setShowBlockedDateModal] = useState(false)
  const [editingBlockedDate, setEditingBlockedDate] = useState(null)
  const [blockedDateForm, setBlockedDateForm] = useState({
    start_date: '',
    end_date: '',
    block_dropoffs: true,
    block_pickups: true,
    reason: '',
  })
  const [savingBlockedDate, setSavingBlockedDate] = useState(false)

  // Time slots state (for partial day blocking)
  const [timeSlots, setTimeSlots] = useState([])
  const [loadingTimeSlots, setLoadingTimeSlots] = useState(false)
  const [showTimeSlotForm, setShowTimeSlotForm] = useState(false)
  const [editingTimeSlot, setEditingTimeSlot] = useState(null)
  const [timeSlotForm, setTimeSlotForm] = useState({
    start_time: '',
    end_time: '',
    block_dropoffs: true,
    block_pickups: true,
    reason: '',
  })
  const [savingTimeSlot, setSavingTimeSlot] = useState(false)

  // Employee holidays state
  const [holidays, setHolidays] = useState([])
  const [showHolidayModal, setShowHolidayModal] = useState(false)
  const [editingHoliday, setEditingHoliday] = useState(null)
  const [holidayForm, setHolidayForm] = useState({
    staff_id: '',
    start_date: '',
    end_date: '',
    holiday_type: 'holiday',
    notes: '',
    start_time: '',  // For partial day unavailability
    end_time: '',    // For partial day unavailability
  })
  const [savingHoliday, setSavingHoliday] = useState(false)

  // Employee unavailability state (employee self-service)
  const [unavailabilities, setUnavailabilities] = useState([])
  const [showUnavailModal, setShowUnavailModal] = useState(false)
  const [unavailForm, setUnavailForm] = useState({
    start_date: '',
    end_date: '',
    start_time: '',  // HH:MM for partial day
    end_time: '',    // HH:MM for partial day
    notes: '',
  })
  const [savingUnavail, setSavingUnavail] = useState(false)

  // Available shifts state (employee self-service)
  const [availableShifts, setAvailableShifts] = useState([])
  const [loadingAvailableShifts, setLoadingAvailableShifts] = useState(false)
  const [showClaimModal, setShowClaimModal] = useState(false)
  const [shiftToClaim, setShiftToClaim] = useState(null)
  const [claimingShift, setClaimingShift] = useState(false)
  const [showReleaseModal, setShowReleaseModal] = useState(false)
  const [shiftToRelease, setShiftToRelease] = useState(null)
  const [releasingShift, setReleasingShift] = useState(false)

  // Collapsible sections state (collapsed by default)
  const [collapsedSections, setCollapsedSections] = useState({
    dropoffs: true,
    pickups: true,
    shifts: true,
    availableShifts: true,
    holidays: true,
    unavailability: true,
  })

  const toggleSection = (section) => {
    setCollapsedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }))
  }

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
      // Auto-roster Planner Calendar embed passes sourceFilter='auto' to
      // scope this calendar to auto-created shifts only. Default leaves
      // it off, preserving the regular admin Calendar's behaviour.
      if (sourceFilter && isAdmin) {
        params.set('source', sourceFilter)
      }

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
  }, [token, currentDate, isAdmin, sourceFilter])

  // Fetch teammates' shifts (view-only, employee mode only).
  const fetchTeamShifts = useCallback(async () => {
    if (!token || isAdmin) {
      setTeamShifts([])
      return
    }
    try {
      const year = currentDate.getFullYear()
      const month = currentDate.getMonth()
      const startDate = new Date(year, month, 1)
      const endDate = new Date(year, month + 1, 0)

      const params = new URLSearchParams({
        date_from: formatDateISO(startDate),
        date_to: formatDateISO(endDate),
      })

      const response = await fetch(`${API_URL}/api/employee/team-shifts?${params}`, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Cache-Control': 'no-cache',
        },
      })
      if (response.ok) {
        const data = await response.json()
        setTeamShifts(Array.isArray(data) ? data : [])
      }
    } catch (err) {
      console.error('Failed to load team shifts:', err)
    }
  }, [token, currentDate, isAdmin])

  // Fetch blocked dates (for both admin and employees)
  const fetchBlockedDates = useCallback(async () => {
    if (!token) return

    try {
      const year = currentDate.getFullYear()
      const month = currentDate.getMonth()
      const startDate = new Date(year, month, 1)
      const endDate = new Date(year, month + 1, 0)

      const params = new URLSearchParams({
        date_from: formatDateISO(startDate),
        date_to: formatDateISO(endDate),
      })

      // Use admin endpoint for admins (with full CRUD), public endpoint for employees (read-only)
      const endpoint = isAdmin
        ? `${API_URL}/api/admin/blocked-dates?${params}`
        : `${API_URL}/api/blocked-dates/check?${params}`

      const response = await fetch(endpoint, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Cache-Control': 'no-cache',
        },
      })

      if (response.ok) {
        const data = await response.json()
        setBlockedDates(data.blocked_dates || [])
      }
    } catch (err) {
      console.error('Failed to load blocked dates:', err)
    }
  }, [token, currentDate, isAdmin])

  // Fetch employee holidays (admin sees all, employee sees their own)
  const fetchHolidays = useCallback(async () => {
    if (!token) return

    try {
      const year = currentDate.getFullYear()
      const month = currentDate.getMonth()
      const startDate = new Date(year, month, 1)
      const endDate = new Date(year, month + 1, 0)

      const params = new URLSearchParams({
        date_from: formatDateISO(startDate),
        date_to: formatDateISO(endDate),
      })

      // Admin uses /api/holidays (all employees), employee uses /api/employee/holidays (own only)
      const endpoint = isAdmin ? '/api/holidays' : '/api/employee/holidays'
      const response = await fetch(`${API_URL}${endpoint}?${params}`, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Cache-Control': 'no-cache',
        },
      })

      if (response.ok) {
        const data = await response.json()
        setHolidays(Array.isArray(data) ? data : [])
      }
    } catch (err) {
      console.error('Failed to load holidays:', err)
    }
  }, [token, currentDate, isAdmin])

  // Fetch employee unavailability (employee only)
  const fetchUnavailabilities = useCallback(async () => {
    if (!token || isAdmin) return  // Only for employees

    try {
      const year = currentDate.getFullYear()
      const month = currentDate.getMonth()
      const startDate = new Date(year, month, 1)
      const endDate = new Date(year, month + 1, 0)

      const params = new URLSearchParams({
        date_from: formatDateISO(startDate),
        date_to: formatDateISO(endDate),
      })

      const response = await fetch(`${API_URL}/api/employee/unavailability?${params}`, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Cache-Control': 'no-cache',
        },
      })

      if (response.ok) {
        const data = await response.json()
        setUnavailabilities(Array.isArray(data) ? data : [])
      }
    } catch (err) {
      console.error('Failed to load unavailabilities:', err)
    }
  }, [token, currentDate, isAdmin])

  // Fetch available shifts (employee self-service)
  const fetchAvailableShifts = useCallback(async () => {
    if (!token || isAdmin) return  // Only for employees

    try {
      setLoadingAvailableShifts(true)
      const response = await fetch(`${API_URL}/api/employee/available-shifts`, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Cache-Control': 'no-cache',
        },
      })

      if (response.ok) {
        const data = await response.json()
        setAvailableShifts(Array.isArray(data) ? data : [])
      }
    } catch (err) {
      console.error('Failed to load available shifts:', err)
    } finally {
      setLoadingAvailableShifts(false)
    }
  }, [token, isAdmin])

  // Claim a shift
  const handleClaimShift = async () => {
    if (!shiftToClaim) return

    setClaimingShift(true)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/employee/claim-shift/${shiftToClaim.id}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })

      if (response.ok) {
        setSuccessMessage('Shift claimed successfully!')
        setShowClaimModal(false)
        setShiftToClaim(null)
        // Refresh data
        fetchShifts()
        fetchAvailableShifts()
        setTimeout(() => setSuccessMessage(''), 3000)
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to claim shift')
        setTimeout(() => setError(''), 5000)
      }
    } catch (err) {
      setError('Network error claiming shift')
      setTimeout(() => setError(''), 5000)
    } finally {
      setClaimingShift(false)
    }
  }

  // Release a shift
  const handleReleaseShift = async () => {
    if (!shiftToRelease) return

    setReleasingShift(true)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/employee/release-shift/${shiftToRelease.id}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })

      if (response.ok) {
        setSuccessMessage('Shift released successfully!')
        setShowReleaseModal(false)
        setShiftToRelease(null)
        // Refresh data
        fetchShifts()
        fetchAvailableShifts()
        setTimeout(() => setSuccessMessage(''), 3000)
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to release shift')
        setTimeout(() => setError(''), 5000)
      }
    } catch (err) {
      setError('Network error releasing shift')
      setTimeout(() => setError(''), 5000)
    } finally {
      setReleasingShift(false)
    }
  }

  // Calculate hours until shift (for release warning)
  const getHoursUntilShift = (shift) => {
    const now = new Date()
    const shiftStart = new Date(`${shift.date}T${shift.start_time}`)
    return Math.floor((shiftStart - now) / (1000 * 60 * 60))
  }

  // Open claim modal
  const openClaimModal = (shift) => {
    setShiftToClaim(shift)
    setShowClaimModal(true)
  }

  // Open release modal
  const openReleaseModal = (shift) => {
    setShiftToRelease(shift)
    setShowReleaseModal(true)
  }

  // Fetch all data
  const fetchData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      await Promise.all([fetchBookings(), fetchShifts(), fetchBlockedDates(), fetchHolidays(), fetchAvailableShifts(), fetchUnavailabilities(), fetchTeamShifts()])
    } catch (err) {
      setError('Failed to load data')
    } finally {
      setLoading(false)
    }
  }, [fetchBookings, fetchShifts, fetchBlockedDates, fetchHolidays, fetchAvailableShifts, fetchUnavailabilities, fetchTeamShifts])

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
      // When the calendar is filtered to a specific source (e.g. the Planner
      // page's auto-roster embed), the Hours panel should reflect that same
      // scope. Default leaves the param off → existing payroll behaviour.
      const sourceParam = sourceFilter && isAdmin ? `&source=${encodeURIComponent(sourceFilter)}` : ''
      const response = await fetch(`${API_URL}${endpoint}?year=${year}&month=${month}${sourceParam}`, {
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
  }, [token, currentDate, isAdmin, sourceFilter])

  useEffect(() => {
    fetchData()
  }, [fetchData, refreshTrigger])

  useEffect(() => {
    fetchStaff()
  }, [fetchStaff])

  useEffect(() => {
    fetchMonthlyHours()
  }, [fetchMonthlyHours])

  // Close detail modal on Escape key
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape' && showDetailModal) {
        setShowDetailModal(false)
        setSelectedDate(null)
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [showDetailModal])

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

    // Monday-first week: shift so Monday = 0 and Sunday = 6
    const startDayOfWeek = (firstDay.getDay() + 6) % 7

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

  // Per-operational-day grouping — see computeBookingsByDate above.
  // Pickups before 02:30 are bucketed back to the previous calendar
  // day, then each day is sorted chronologically.
  const bookingsByDate = useMemo(
    () => computeBookingsByDate(bookings),
    [bookings]
  )

  // Group shifts by date (overnight shifts show entirely on start date)
  const shiftsByDate = useMemo(() => {
    const grouped = {}

    shifts.forEach((shift) => {
      const isOvernight = shift.end_date && shift.end_date !== shift.date

      // Add to start date only - overnight shifts display with actual end time
      const startDateKey = shift.date
      if (!grouped[startDateKey]) {
        grouped[startDateKey] = []
      }
      grouped[startDateKey].push({
        ...shift,
        isOvernight,
        shiftPart: null,
        displayStartTime: shift.start_time,
        displayEndTime: shift.end_time  // Show actual end time (e.g., 00:45 next day)
      })
    })

    Object.keys(grouped).forEach((date) => {
      grouped[date].sort((a, b) => (a.displayStartTime || a.start_time).localeCompare(b.displayStartTime || b.start_time))
    })

    return grouped
  }, [shifts])

  // Group teammates' view-only shifts by date (employee mode only).
  const teamShiftsByDate = useMemo(() => {
    const grouped = {}
    teamShifts.forEach((shift) => {
      const isOvernight = shift.end_date && shift.end_date !== shift.date
      const startKey = shift.date
      if (!grouped[startKey]) grouped[startKey] = []
      grouped[startKey].push({ ...shift, isOvernight })
    })
    Object.keys(grouped).forEach((d) => {
      grouped[d].sort((a, b) => a.start_time.localeCompare(b.start_time))
    })
    return grouped
  }, [teamShifts])

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

  const getTeamShiftsForDay = (day) => {
    const dateKey = getDateKey(day)
    return teamShiftsByDate[dateKey] || []
  }

  const getShiftsForDay = (day) => {
    const dateKey = getDateKey(day)
    return shiftsByDate[dateKey] || []
  }

  // Check if date is blocked
  const getBlockedInfoForDay = (day) => {
    if (!day) return null
    const dateKey = getDateKey(day)
    // Find any blocked date that covers this day
    const blocked = blockedDates.find(bd => {
      return dateKey >= bd.start_date && dateKey <= bd.end_date
    })
    return blocked || null
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

  // Handle date selection - close modal if open, otherwise open modal
  const handleDateClick = (day) => {
    if (!day) return
    const dateKey = getDateKey(day)
    if (showDetailModal) {
      // Close modal first
      setShowDetailModal(false)
      setSelectedDate(null)
    } else {
      // Open modal for this date
      setSelectedDate(dateKey)
      setShowDetailModal(true)
    }
  }

  // Close detail modal handler
  const closeDetailModal = () => {
    setShowDetailModal(false)
    setSelectedDate(null)
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
    setDuplicateMode(false)
    setAdditionalStaffIds([])
    setError('')  // Clear any previous errors
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
      intended_driver_type: shift.intended_driver_type || 'jockey',
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
    setDuplicateMode(false)
    setAdditionalStaffIds([])
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

      const basePayload = {
        booking_ids: shiftForm.booking_ids.map(id => parseInt(id)),
        date: isoDate,
        end_date: isoEndDate,  // For overnight shifts
        start_time: shiftForm.start_time,
        end_time: shiftForm.end_time,
        shift_type: shiftForm.shift_type,
        notes: shiftForm.notes || null,
        // Backend overrides this with the assigned user's driver_type when
        // staff_id is set; for unassigned shifts it's the source of truth.
        intended_driver_type: shiftForm.intended_driver_type || 'jockey',
      }

      if (editingShift) {
        // Editing existing shift - single update
        const payload = {
          ...basePayload,
          staff_id: shiftForm.staff_id ? parseInt(shiftForm.staff_id) : null,
        }

        const response = await fetch(`${API_URL}/api/roster/${editingShift.id}`, {
          method: 'PUT',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
            'Cache-Control': 'no-cache',
          },
          body: JSON.stringify(payload),
        })

        if (response.ok) {
          setSuccessMessage('Shift updated')
          setTimeout(() => setSuccessMessage(''), 3000)
          closeShiftModal()
          fetchShifts()
          fetchMonthlyHours()
        } else {
          const errorData = await response.json().catch(() => ({}))
          setError(errorData.detail || 'Failed to save shift')
        }
      } else {
        // Creating new shift(s)
        // Collect all staff IDs to create shifts for
        const staffIdsToCreate = []
        if (shiftForm.staff_id) {
          staffIdsToCreate.push(parseInt(shiftForm.staff_id))
        }
        if (duplicateMode && additionalStaffIds.length > 0) {
          additionalStaffIds.forEach(id => {
            if (id && !staffIdsToCreate.includes(parseInt(id))) {
              staffIdsToCreate.push(parseInt(id))
            }
          })
        }

        // If no staff selected, create one unassigned shift
        if (staffIdsToCreate.length === 0) {
          staffIdsToCreate.push(null)
        }

        let successCount = 0
        let errorMessages = []

        // Create shifts for each staff member
        for (const staffId of staffIdsToCreate) {
          const payload = {
            ...basePayload,
            staff_id: staffId,
          }

          try {
            const response = await fetch(`${API_URL}/api/roster`, {
              method: 'POST',
              headers: {
                Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache',
              },
              body: JSON.stringify(payload),
            })

            if (response.ok) {
              successCount++
            } else {
              const errorData = await response.json().catch(() => ({}))
              const staffName = employees.find(e => e.id === staffId)
              const name = staffName ? `${staffName.first_name} ${staffName.last_name}` : 'Unknown'
              errorMessages.push(`${name}: ${errorData.detail || 'Failed'}`)
            }
          } catch (err) {
            errorMessages.push(`Network error`)
          }
        }

        if (successCount > 0) {
          setSuccessMessage(`${successCount} shift${successCount > 1 ? 's' : ''} created`)
          setTimeout(() => setSuccessMessage(''), 3000)
          closeShiftModal()
          fetchShifts()
          fetchMonthlyHours()
        }

        if (errorMessages.length > 0) {
          setError(errorMessages.join('; '))
        }
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

  // Bulk edit functions
  const toggleShiftSelection = (shiftId) => {
    setSelectedShiftIds(prev => {
      if (prev.includes(shiftId)) {
        return prev.filter(id => id !== shiftId)
      } else {
        return [...prev, shiftId]
      }
    })
  }

  const clearShiftSelection = () => {
    setSelectedShiftIds([])
  }

  const openBulkEditModal = () => {
    if (selectedShiftIds.length === 0) return
    setBulkEditForm({
      action: 'edit_times',
      start_time: '',
      end_time: '',
      booking_ids: [],
    })
    setError('')  // Clear any previous errors
    // Fetch bookings for the selected dates
    const selectedShifts = shifts.filter(s => selectedShiftIds.includes(s.id))
    const uniqueDates = [...new Set(selectedShifts.map(s => s.date))]
    if (uniqueDates.length === 1) {
      fetchBookingsForDate(formatDateUK(uniqueDates[0]))
    }
    setError('')
    setShowBulkEditModal(true)
  }

  const closeBulkEditModal = () => {
    setShowBulkEditModal(false)
    setBulkEditForm({
      action: 'edit_times',
      start_time: '',
      end_time: '',
      booking_ids: [],
    })
  }

  const executeBulkEdit = async () => {
    if (selectedShiftIds.length === 0) return

    setSavingBulkEdit(true)
    setError('')

    try {
      if (bulkEditForm.action === 'delete') {
        // Bulk delete
        let successCount = 0
        let errorMessages = []

        for (const shiftId of selectedShiftIds) {
          try {
            const response = await fetch(`${API_URL}/api/roster/${shiftId}`, {
              method: 'DELETE',
              headers: {
                Authorization: `Bearer ${token}`,
                'Cache-Control': 'no-cache',
              },
            })

            if (response.ok) {
              successCount++
            } else {
              const errorData = await response.json().catch(() => ({}))
              errorMessages.push(errorData.detail || `Failed to delete shift ${shiftId}`)
            }
          } catch (err) {
            errorMessages.push(`Network error deleting shift ${shiftId}`)
          }
        }

        if (successCount > 0) {
          setSuccessMessage(`${successCount} shift${successCount > 1 ? 's' : ''} deleted`)
          setTimeout(() => setSuccessMessage(''), 3000)
          setSelectedShiftIds([])
          closeBulkEditModal()
          fetchShifts()
          fetchMonthlyHours()
        }

        if (errorMessages.length > 0) {
          setError(errorMessages.join('; '))
        }
      } else {
        // Bulk edit times or add bookings
        let successCount = 0
        let errorMessages = []

        for (const shiftId of selectedShiftIds) {
          const payload = {}

          if (bulkEditForm.action === 'edit_times') {
            if (bulkEditForm.start_time) payload.start_time = bulkEditForm.start_time
            if (bulkEditForm.end_time) payload.end_time = bulkEditForm.end_time
          } else if (bulkEditForm.action === 'add_bookings') {
            // Get existing shift to merge booking_ids
            const existingShift = shifts.find(s => s.id === shiftId)
            const existingBookingIds = existingShift?.bookings?.map(b => b.id) || []
            const newBookingIds = [...new Set([...existingBookingIds, ...bulkEditForm.booking_ids])]
            payload.booking_ids = newBookingIds
          }

          // Only send if there's something to update
          if (Object.keys(payload).length === 0) continue

          try {
            const response = await fetch(`${API_URL}/api/roster/${shiftId}`, {
              method: 'PUT',
              headers: {
                Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache',
              },
              body: JSON.stringify(payload),
            })

            if (response.ok) {
              successCount++
            } else {
              const errorData = await response.json().catch(() => ({}))
              errorMessages.push(errorData.detail || `Failed to update shift ${shiftId}`)
            }
          } catch (err) {
            errorMessages.push(`Network error updating shift ${shiftId}`)
          }
        }

        if (successCount > 0) {
          setSuccessMessage(`${successCount} shift${successCount > 1 ? 's' : ''} updated`)
          setTimeout(() => setSuccessMessage(''), 3000)
          setSelectedShiftIds([])
          closeBulkEditModal()
          fetchShifts()
          fetchMonthlyHours()
        }

        if (errorMessages.length > 0) {
          setError(errorMessages.join('; '))
        }
      }
    } catch (err) {
      setError('Network error during bulk operation')
    } finally {
      setSavingBulkEdit(false)
    }
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

  // ==================== BLOCKED DATES MANAGEMENT ====================

  // Fetch time slots for a blocked date
  const fetchTimeSlots = useCallback(async (blockedDateId) => {
    if (!token || !blockedDateId) {
      setTimeSlots([])
      return
    }

    setLoadingTimeSlots(true)
    try {
      const response = await fetch(
        `${API_URL}/api/admin/blocked-dates/${blockedDateId}/time-slots`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
            'Cache-Control': 'no-cache',
          },
        }
      )

      if (response.ok) {
        const data = await response.json()
        setTimeSlots(data.time_slots || [])
      } else {
        setTimeSlots([])
      }
    } catch (err) {
      console.error('Failed to load time slots:', err)
      setTimeSlots([])
    } finally {
      setLoadingTimeSlots(false)
    }
  }, [token])

  // Open modal to create a blocked date for a specific date
  const openBlockedDateModal = (dateKey) => {
    setEditingBlockedDate(null)
    setBlockedDateForm({
      start_date: dateKey,
      end_date: dateKey,
      block_dropoffs: true,
      block_pickups: true,
      reason: '',
    })
    setTimeSlots([])
    setShowTimeSlotForm(false)
    setEditingTimeSlot(null)
    setShowBlockedDateModal(true)
  }

  // Open modal to edit an existing blocked date
  const openEditBlockedDateModal = (blockedDate) => {
    setEditingBlockedDate(blockedDate)
    setBlockedDateForm({
      start_date: blockedDate.start_date,
      end_date: blockedDate.end_date,
      block_dropoffs: blockedDate.block_dropoffs,
      block_pickups: blockedDate.block_pickups,
      reason: blockedDate.reason || '',
    })
    setShowTimeSlotForm(false)
    setEditingTimeSlot(null)
    fetchTimeSlots(blockedDate.id)
    setShowBlockedDateModal(true)
  }

  // Close blocked date modal
  const closeBlockedDateModal = () => {
    setShowBlockedDateModal(false)
    setEditingBlockedDate(null)
    setBlockedDateForm({
      start_date: '',
      end_date: '',
      block_dropoffs: true,
      block_pickups: true,
      reason: '',
    })
    setTimeSlots([])
    setShowTimeSlotForm(false)
    setEditingTimeSlot(null)
  }

  // ==================== TIME SLOTS MANAGEMENT ====================

  // Open time slot form for new slot
  const openNewTimeSlotForm = () => {
    setEditingTimeSlot(null)
    setTimeSlotForm({
      start_time: '',
      end_time: '',
      block_dropoffs: true,
      block_pickups: true,
      reason: '',
    })
    setShowTimeSlotForm(true)
  }

  // Open time slot form for editing
  const openEditTimeSlotForm = (slot) => {
    setEditingTimeSlot(slot)
    setTimeSlotForm({
      start_time: formatTime(slot.start_time),
      end_time: formatTime(slot.end_time),
      block_dropoffs: slot.block_dropoffs,
      block_pickups: slot.block_pickups,
      reason: slot.reason || '',
    })
    setShowTimeSlotForm(true)
  }

  // Cancel time slot form
  const cancelTimeSlotForm = () => {
    setShowTimeSlotForm(false)
    setEditingTimeSlot(null)
    setTimeSlotForm({
      start_time: '',
      end_time: '',
      block_dropoffs: true,
      block_pickups: true,
      reason: '',
    })
  }

  // Save time slot (create or update)
  const saveTimeSlot = async () => {
    if (!editingBlockedDate) return

    setSavingTimeSlot(true)
    setError('')

    try {
      const payload = {
        start_time: timeSlotForm.start_time,
        end_time: timeSlotForm.end_time,
        block_dropoffs: timeSlotForm.block_dropoffs,
        block_pickups: timeSlotForm.block_pickups,
        reason: timeSlotForm.reason || null,
      }

      const url = editingTimeSlot
        ? `${API_URL}/api/admin/blocked-time-slots/${editingTimeSlot.id}`
        : `${API_URL}/api/admin/blocked-dates/${editingBlockedDate.id}/time-slots`

      const response = await fetch(url, {
        method: editingTimeSlot ? 'PUT' : 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })

      if (response.ok) {
        setSuccessMessage(editingTimeSlot ? 'Time slot updated' : 'Time slot added')
        setTimeout(() => setSuccessMessage(''), 3000)
        cancelTimeSlotForm()
        fetchTimeSlots(editingBlockedDate.id)
      } else {
        const errorData = await response.json().catch(() => ({}))
        setError(errorData.detail || 'Failed to save time slot')
      }
    } catch (err) {
      setError('Network error saving time slot')
    } finally {
      setSavingTimeSlot(false)
    }
  }

  // Delete time slot
  const deleteTimeSlot = async (slotId) => {
    if (!window.confirm('Are you sure you want to delete this time slot?')) return

    setError('')

    try {
      const response = await fetch(`${API_URL}/api/admin/blocked-time-slots/${slotId}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })

      if (response.ok) {
        setSuccessMessage('Time slot deleted')
        setTimeout(() => setSuccessMessage(''), 3000)
        if (editingBlockedDate) {
          fetchTimeSlots(editingBlockedDate.id)
        }
      } else {
        const errorData = await response.json().catch(() => ({}))
        setError(errorData.detail || 'Failed to delete time slot')
      }
    } catch (err) {
      setError('Network error deleting time slot')
    }
  }

  // Save blocked date (create or update)
  const saveBlockedDate = async () => {
    setSavingBlockedDate(true)
    setError('')

    try {
      const payload = {
        start_date: blockedDateForm.start_date,
        end_date: blockedDateForm.end_date,
        block_dropoffs: blockedDateForm.block_dropoffs,
        block_pickups: blockedDateForm.block_pickups,
        reason: blockedDateForm.reason || null,
      }

      const url = editingBlockedDate
        ? `${API_URL}/api/admin/blocked-dates/${editingBlockedDate.id}`
        : `${API_URL}/api/admin/blocked-dates`

      const response = await fetch(url, {
        method: editingBlockedDate ? 'PUT' : 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })

      if (response.ok) {
        setSuccessMessage(editingBlockedDate ? 'Blocked date updated' : 'Date blocked')
        setTimeout(() => setSuccessMessage(''), 3000)
        closeBlockedDateModal()
        fetchBlockedDates()
      } else {
        const errorData = await response.json().catch(() => ({}))
        setError(errorData.detail || 'Failed to save blocked date')
      }
    } catch (err) {
      setError('Network error saving blocked date')
    } finally {
      setSavingBlockedDate(false)
    }
  }

  // Delete blocked date
  const deleteBlockedDate = async (blockedDateId) => {
    if (!window.confirm('Are you sure you want to unblock this date?')) return

    setError('')

    try {
      const response = await fetch(`${API_URL}/api/admin/blocked-dates/${blockedDateId}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })

      if (response.ok) {
        setSuccessMessage('Date unblocked')
        setTimeout(() => setSuccessMessage(''), 3000)
        fetchBlockedDates()
      } else {
        const errorData = await response.json().catch(() => ({}))
        setError(errorData.detail || 'Failed to unblock date')
      }
    } catch (err) {
      setError('Network error unblocking date')
    }
  }

  // Open holiday modal for new holiday
  const openNewHolidayModal = (dateStr = null) => {
    setEditingHoliday(null)
    // Convert ISO date to UK format (DD/MM/YYYY)
    const ukDate = dateStr ? formatDateUK(dateStr) : (selectedDate ? formatDateUK(selectedDate) : '')
    setHolidayForm({
      staff_id: '',
      start_date: ukDate,
      end_date: ukDate,
      holiday_type: 'holiday',
      notes: '',
      start_time: '',
      end_time: '',
    })
    setShowHolidayModal(true)
  }

  // Open holiday modal for editing
  const openEditHolidayModal = (holiday) => {
    setEditingHoliday(holiday)
    // Convert ISO dates from API to UK format (DD/MM/YYYY)
    setHolidayForm({
      staff_id: String(holiday.staff_id),
      start_date: formatDateUK(holiday.start_date),
      end_date: formatDateUK(holiday.end_date),
      holiday_type: holiday.holiday_type,
      notes: holiday.notes || '',
      start_time: formatTime(holiday.start_time) || '',
      end_time: formatTime(holiday.end_time) || '',
    })
    setShowHolidayModal(true)
  }

  // Close holiday modal
  const closeHolidayModal = () => {
    setShowHolidayModal(false)
    setEditingHoliday(null)
    setHolidayForm({
      staff_id: '',
      start_date: '',
      end_date: '',
      holiday_type: 'holiday',
      notes: '',
    })
  }

  // Save holiday (create or update)
  const saveHoliday = async () => {
    if (!holidayForm.staff_id || !holidayForm.start_date || !holidayForm.end_date) {
      setError('Please select a staff member and dates')
      return
    }

    // Convert UK dates (DD/MM/YYYY) to ISO (YYYY-MM-DD) for API
    const isoStartDate = ukToISO(holidayForm.start_date)
    const isoEndDate = ukToISO(holidayForm.end_date)

    if (!isoStartDate || isoStartDate.length !== 10 || !isoEndDate || isoEndDate.length !== 10) {
      setError('Please enter valid dates in DD/MM/YYYY format')
      return
    }

    setSavingHoliday(true)
    setError('')

    try {
      const params = new URLSearchParams({
        staff_id: holidayForm.staff_id,
        start_date: isoStartDate,
        end_date: isoEndDate,
        holiday_type: holidayForm.holiday_type,
      })
      if (holidayForm.notes) {
        params.append('notes', holidayForm.notes)
      }
      // For unavailability type, handle partial day times
      if (holidayForm.holiday_type === 'unavailable') {
        if (holidayForm.start_time) {
          params.append('start_time', holidayForm.start_time)
        }
        if (holidayForm.end_time) {
          params.append('end_time', holidayForm.end_time)
        }
        // If editing and times were cleared, signal to clear them
        if (editingHoliday && !holidayForm.start_time && !holidayForm.end_time) {
          params.append('clear_times', 'true')
        }
      }

      const url = editingHoliday
        ? `${API_URL}/api/holidays/${editingHoliday.id}?${params}`
        : `${API_URL}/api/holidays?${params}`

      const response = await fetch(url, {
        method: editingHoliday ? 'PUT' : 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })

      if (response.ok) {
        setSuccessMessage(editingHoliday ? 'Holiday updated' : 'Holiday added')
        setTimeout(() => setSuccessMessage(''), 3000)
        closeHolidayModal()
        fetchHolidays()
      } else {
        const errorData = await response.json().catch(() => ({}))
        setError(errorData.detail || 'Failed to save holiday')
      }
    } catch (err) {
      setError('Network error saving holiday')
    } finally {
      setSavingHoliday(false)
    }
  }

  // Delete holiday
  const deleteHoliday = async (holidayId) => {
    if (!window.confirm('Are you sure you want to delete this holiday?')) return

    setError('')

    try {
      const response = await fetch(`${API_URL}/api/holidays/${holidayId}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })

      if (response.ok) {
        setSuccessMessage('Holiday deleted')
        setTimeout(() => setSuccessMessage(''), 3000)
        fetchHolidays()
      } else {
        const errorData = await response.json().catch(() => ({}))
        setError(errorData.detail || 'Failed to delete holiday')
      }
    } catch (err) {
      setError('Network error deleting holiday')
    }
  }

  // Get holidays for a specific date
  const getHolidaysForDate = (dateStr) => {
    return holidays.filter(h => {
      const start = new Date(h.start_date)
      const end = new Date(h.end_date)
      const check = new Date(dateStr)
      return check >= start && check <= end
    })
  }

  // Get staff IDs on holiday for a specific date
  const getStaffOnHolidayForDate = (dateStr) => {
    const dateHolidays = getHolidaysForDate(dateStr)
    return new Set(dateHolidays.map(h => h.staff_id))
  }

  // ============= EMPLOYEE UNAVAILABILITY FUNCTIONS =============

  // Open unavailability modal
  const openNewUnavailModal = (dateStr = null) => {
    const today = new Date()
    const defaultDate = dateStr ? formatDateUK(dateStr) : formatDateUK(formatDateISO(today))
    setUnavailForm({
      start_date: defaultDate,
      end_date: defaultDate,
      start_time: '',
      end_time: '',
      notes: '',
    })
    setShowUnavailModal(true)
  }

  // Close unavailability modal
  const closeUnavailModal = () => {
    setShowUnavailModal(false)
    setUnavailForm({
      start_date: '',
      end_date: '',
      start_time: '',
      end_time: '',
      notes: '',
    })
  }

  // Save unavailability
  const saveUnavailability = async () => {
    if (!unavailForm.start_date || !unavailForm.end_date) {
      setError('Please enter start and end dates')
      return
    }

    // Validate UK date format (DD/MM/YYYY)
    const ukDateRegex = /^\d{2}\/\d{2}\/\d{4}$/
    if (!ukDateRegex.test(unavailForm.start_date) || !ukDateRegex.test(unavailForm.end_date)) {
      setError('Invalid date format. Use DD/MM/YYYY')
      return
    }

    setSavingUnavail(true)
    setError('')

    try {
      // Backend expects UK format (DD/MM/YYYY) - send as-is
      const params = new URLSearchParams({
        start_date: unavailForm.start_date,
        end_date: unavailForm.end_date,
      })
      if (unavailForm.start_time) {
        params.append('start_time', unavailForm.start_time)
      }
      if (unavailForm.end_time) {
        params.append('end_time', unavailForm.end_time)
      }
      if (unavailForm.notes) {
        params.append('notes', unavailForm.notes)
      }

      const response = await fetch(`${API_URL}/api/employee/unavailability?${params}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })

      if (response.ok) {
        setSuccessMessage('Unavailability added')
        setTimeout(() => setSuccessMessage(''), 3000)
        closeUnavailModal()
        fetchUnavailabilities()
        fetchHolidays()  // Refresh holidays too as they share display
      } else {
        const errorData = await response.json().catch(() => ({}))
        setError(errorData.detail || 'Failed to add unavailability')
      }
    } catch (err) {
      setError('Network error saving unavailability')
    } finally {
      setSavingUnavail(false)
    }
  }

  // Delete unavailability
  const deleteUnavailability = async (unavailId) => {
    if (!window.confirm('Are you sure you want to delete this unavailability?')) return

    setError('')

    try {
      const response = await fetch(`${API_URL}/api/employee/unavailability/${unavailId}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })

      if (response.ok) {
        setSuccessMessage('Unavailability deleted')
        setTimeout(() => setSuccessMessage(''), 3000)
        fetchUnavailabilities()
        fetchHolidays()  // Refresh holidays too
      } else {
        const errorData = await response.json().catch(() => ({}))
        setError(errorData.detail || 'Failed to delete unavailability')
      }
    } catch (err) {
      setError('Network error deleting unavailability')
    }
  }

  // Get unavailabilities for a specific date
  const getUnavailabilitiesForDate = (dateStr) => {
    return unavailabilities.filter(u => {
      const start = new Date(u.start_date)
      const end = new Date(u.end_date)
      const check = new Date(dateStr)
      return check >= start && check <= end
    })
  }

  // Get blocked date info for selected date
  const selectedDateBlockedInfo = selectedDate ? getBlockedInfoForDay(parseInt(selectedDate.split('-')[2])) : null

  // Month names
  const monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ]

  // Selected date data
  const selectedDateBookings = selectedDate ? (bookingsByDate[selectedDate] || { dropoffs: [], pickups: [] }) : { dropoffs: [], pickups: [] }
  const selectedDateShifts = selectedDate ? (shiftsByDate[selectedDate] || []) : []
  const selectedDateHolidays = selectedDate ? getHolidaysForDate(selectedDate) : []

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
            <>
              <button className="roster-add-btn" onClick={() => openNewShiftModal()}>
                + Add Shift
              </button>
              <button className="roster-add-holiday-btn" onClick={() => openNewHolidayModal()}>
                + Add Holiday
              </button>
            </>
          )}
          {!isAdmin && (
            <button className="roster-unavail-btn" onClick={() => openNewUnavailModal()}>
              + Mark Unavailable
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
          {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((day) => (
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
                const dayTeamShifts = !isAdmin ? getTeamShiftsForDay(day) : []
                const dateKey = getDateKey(day)
                const blockedInfo = getBlockedInfoForDay(day)
                const dayHolidays = dateKey ? getHolidaysForDate(dateKey) : []
                const hasDropoffs = dayBookings.dropoffs.length > 0
                const hasPickups = dayBookings.pickups.length > 0
                const hasShifts = dayShifts.length > 0
                const hasTeamShifts = dayTeamShifts.length > 0
                const hasHolidays = dayHolidays.length > 0
                const hasContent = hasDropoffs || hasPickups || hasShifts || hasTeamShifts || blockedInfo || hasHolidays

                return (
                  <div
                    key={dayIndex}
                    className={`calendar-day ${day ? '' : 'empty'} ${isToday(day) ? 'today' : ''} ${
                      selectedDate === dateKey ? 'selected' : ''
                    } ${hasContent ? 'has-content' : ''} ${blockedInfo ? 'blocked' : ''}`}
                    onClick={() => handleDateClick(day)}
                  >
                    {day && (
                      <>
                        <span className="day-number">{day}</span>
                        <div className="day-content">
                          {/* Blocked date indicator */}
                          {blockedInfo && (
                            <div className="day-badge badge-blocked" title={blockedInfo.reason || 'Blocked'}>
                              🚫 {blockedInfo.time_slots && blockedInfo.time_slots.length > 0
                                ? `${blockedInfo.time_slots.length} slot${blockedInfo.time_slots.length > 1 ? 's' : ''}`
                                : (blockedInfo.block_dropoffs && blockedInfo.block_pickups ? 'Closed' :
                                    blockedInfo.block_dropoffs ? 'No Drop-offs' : 'No Pick-ups')}
                            </div>
                          )}
                          {/* Holiday indicators */}
                          {hasHolidays && dayHolidays.map((holiday) => {
                            const typeConfig = HOLIDAY_TYPE_CONFIG[holiday.holiday_type] || HOLIDAY_TYPE_CONFIG.other
                            return (
                              <div
                                key={holiday.id}
                                className={`day-badge badge-holiday holiday-${holiday.holiday_type}`}
                                title={`${holiday.staff_first_name} ${holiday.staff_last_name} - ${typeConfig.label}`}
                              >
                                {typeConfig.icon} {holiday.staff_initials}
                              </div>
                            )
                          })}
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
                          {/* Available shifts indicator (employee view) */}
                          {(() => {
                            // For non-admin users, count available shifts from the separate availableShifts state
                            // For admin, count unassigned shifts from dayShifts
                            const availableCount = isAdmin
                              ? dayShifts.filter(s => !s.staff_id).length
                              : availableShifts.filter(s => s.date === dateKey).length
                            return availableCount > 0 ? (
                              <div className="day-badge badge-available" title={`${availableCount} available shift${availableCount > 1 ? 's' : ''}`}>
                                ✨ {availableCount}
                              </div>
                            ) : null
                          })()}
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
                          {/* Teammates' shifts (employee mode, view-only) */}
                          {hasTeamShifts && dayTeamShifts.map((tShift, idx) => (
                            <div
                              key={`team-${idx}-${tShift.start_time}`}
                              className={`day-shift-badge team-only ${tShift.isOvernight ? 'overnight' : ''}`}
                              title={`${tShift.first_name} ${tShift.last_name}`}
                              onClick={(e) => {
                                e.stopPropagation()
                                setTeamShiftPopover(tShift)
                              }}
                            >
                              <span className="shift-time-mini">
                                {formatTime(tShift.start_time)}-{formatTime(tShift.end_time)}
                              </span>
                              <span className="shift-initials">{tShift.initials}</span>
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

      {/* Monthly Hours Summary (for payroll) - with weekly breakdown */}
      {monthlyHours && (
        <div className="hours-breakdown-section">
          <h3
            className="hours-breakdown-title hours-breakdown-clickable"
            onClick={() => setHoursExpanded(!hoursExpanded)}
          >
            <span className={`hours-section-caret ${hoursExpanded ? 'expanded' : ''}`}>▶</span>
            Hours <span className="week-range">({monthlyHours.month_name} {monthlyHours.year})</span>
          </h3>
          {hoursExpanded && (loadingMonthlyHours ? (
            <div className="weekly-hours-loading">Loading...</div>
          ) : (
            <div className="hours-breakdown-container">
              {/* Weekly Breakdown */}
              {monthlyHours.weeks && monthlyHours.weeks.map((week, idx) => (
                <div key={week.week_number} className="hours-week-container">
                  <div
                    className="hours-week-header"
                    onClick={() => setExpandedWeeks(prev => ({
                      ...prev,
                      [idx]: !prev[idx]
                    }))}
                  >
                    <span className={`hours-caret ${expandedWeeks[idx] ? 'expanded' : ''}`}>▶</span>
                    <span className="hours-week-label">Week {week.week_number}</span>
                    <span className="hours-week-range">({week.week_label})</span>
                  </div>
                  {expandedWeeks[idx] && (
                    <div className="hours-week-content">
                      {isAdmin ? (
                        // Admin view: show all employees for this week
                        <div className="weekly-hours-grid">
                          {week.employees && week.employees.length > 0 ? (
                            week.employees.map((emp) => (
                              <div key={emp.employee_id} className="weekly-hours-card">
                                <div className="employee-name">{emp.employee_name}</div>
                                <div className="hours-summary">
                                  <span className="total-hours">{emp.total_hours.toFixed(1)}h</span>
                                  <span className="shift-count">({emp.shift_count} shifts)</span>
                                </div>
                              </div>
                            ))
                          ) : (
                            <div className="no-hours">No shifts this week</div>
                          )}
                        </div>
                      ) : (
                        // Employee view: show their hours for this week
                        <div className="weekly-hours-grid">
                          <div className="weekly-hours-card own-hours">
                            <div className="employee-name">Your Hours</div>
                            <div className="hours-summary">
                              <span className="total-hours">{week.total_hours?.toFixed(1) || 0}h</span>
                              <span className="shift-count">({week.shift_count || 0} shifts)</span>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}

              {/* Monthly Totals */}
              <div className="hours-week-container monthly-totals">
                <div
                  className="hours-week-header monthly-header"
                  onClick={() => setMonthlyTotalsExpanded(!monthlyTotalsExpanded)}
                >
                  <span className={`hours-caret ${monthlyTotalsExpanded ? 'expanded' : ''}`}>▶</span>
                  <span className="hours-week-label">Monthly Totals</span>
                </div>
                {monthlyTotalsExpanded && (
                  <div className="hours-week-content">
                    {isAdmin ? (
                      // Admin view: show all employees' monthly totals
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
                      // Employee view: show their monthly total
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
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Detail Modal - Shows both bookings and shifts */}
      {showDetailModal && selectedDate && (
        <div className="roster-detail-modal-overlay" onClick={closeDetailModal}>
          <div className="roster-detail-modal-content" onClick={(e) => e.stopPropagation()}>
          <div className="detail-header">
            <div className="detail-header-top">
              <h3>
                {new Date(selectedDate + 'T00:00:00').toLocaleDateString('en-GB', {
                  weekday: 'long',
                  day: 'numeric',
                  month: 'long',
                  year: 'numeric',
                })}
              </h3>
              <button className="detail-close" onClick={closeDetailModal}>
                ×
              </button>
            </div>
            {isAdmin && (
              <div className="detail-header-actions">
                <button
                  className="roster-add-btn-small"
                  onClick={() => openNewShiftModal(formatDateUK(selectedDate))}
                >
                  + Shift
                </button>
                <button
                  className="roster-add-holiday-btn-small"
                  onClick={() => openNewHolidayModal(selectedDate)}
                >
                  <span className="btn-text-full">+ Holiday</span>
                  <span className="btn-text-short">+ Holiday</span>
                </button>
                {!selectedDateBlockedInfo && (
                  <button
                    className="blocked-dates-btn"
                    onClick={() => openBlockedDateModal(selectedDate)}
                  >
                    <span className="btn-text-full">Block Date</span>
                    <span className="btn-text-short">Block</span>
                  </button>
                )}
              </div>
            )}
          </div>

          <div className="detail-content">
            {/* Blocked Date Section - visible to all users, but edit/delete only for admins */}
            {selectedDateBlockedInfo && (
              <div className="blocked-dates-section">
                <h4>🚫 Date Blocked</h4>
                <div className="blocked-date-info">
                  {/* Show time slots if they exist */}
                  {selectedDateBlockedInfo.time_slots && selectedDateBlockedInfo.time_slots.length > 0 ? (
                    <div className="blocked-time-slots-detail">
                      <div className="blocked-time-slots-label">Blocked time slots:</div>
                      {selectedDateBlockedInfo.time_slots.map((slot) => (
                        <div key={slot.id} className="blocked-time-slot-row">
                          <span className="slot-time-range">
                            {formatTime(slot.start_time)} - {formatTime(slot.end_time)}
                          </span>
                          <span className="slot-block-types">
                            {slot.block_dropoffs && slot.block_pickups ? 'All blocked' :
                              slot.block_dropoffs ? 'No drop-offs' : 'No pick-ups'}
                          </span>
                          {slot.reason && <span className="slot-reason">{slot.reason}</span>}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="blocked-date-type">
                      {selectedDateBlockedInfo.block_dropoffs && (
                        <span className="blocked-type-badge">No Drop-offs</span>
                      )}
                      {selectedDateBlockedInfo.block_pickups && (
                        <span className="blocked-type-badge">No Pick-ups</span>
                      )}
                    </div>
                  )}
                  {selectedDateBlockedInfo.reason && (
                    <div className="blocked-date-reason">
                      Reason: {selectedDateBlockedInfo.reason}
                    </div>
                  )}
                  {isAdmin && (
                    <div className="blocked-date-actions">
                      <button
                        className="blocked-date-edit-btn"
                        onClick={() => openEditBlockedDateModal(selectedDateBlockedInfo)}
                      >
                        Edit
                      </button>
                      <button
                        className="blocked-date-delete-btn"
                        onClick={() => deleteBlockedDate(selectedDateBlockedInfo.id)}
                      >
                        Unblock
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Holidays Section */}
            {selectedDateHolidays.length > 0 && (
              <div className={`holidays-section collapsible ${collapsedSections.holidays ? 'collapsed' : ''}`}>
                <h4
                  className="clickable"
                  onClick={() => toggleSection('holidays')}
                >
                  <span className="collapse-icon">{collapsedSections.holidays ? '▶' : '▼'}</span>
                  {isAdmin ? 'Staff on Leave' : 'Your Leave'} ({selectedDateHolidays.length})
                </h4>
                <div className={`holidays-list collapsible-content ${collapsedSections.holidays ? 'hidden' : ''}`}>
                  {selectedDateHolidays.map((holiday) => {
                    const typeConfig = HOLIDAY_TYPE_CONFIG[holiday.holiday_type] || HOLIDAY_TYPE_CONFIG.other
                    return (
                      <div key={holiday.id} className={`holiday-card holiday-${holiday.holiday_type}`}>
                        <div className="holiday-info">
                          <span className="holiday-icon">{typeConfig.icon}</span>
                          <span className="holiday-staff-name">
                            {holiday.staff_first_name} {holiday.staff_last_name}
                          </span>
                          <span className="holiday-type-badge" style={{ backgroundColor: typeConfig.color }}>
                            {typeConfig.label}
                          </span>
                        </div>
                        <div className="holiday-dates">
                          {holiday.start_date === holiday.end_date
                            ? formatDateUK(holiday.start_date)
                            : `${formatDateUK(holiday.start_date)} - ${formatDateUK(holiday.end_date)}`
                          }
                          {(holiday.start_time || holiday.end_time) && (
                            <span className="holiday-times">
                              {' '}({formatTime(holiday.start_time) || '00:00'} - {formatTime(holiday.end_time) || '23:59'})
                            </span>
                          )}
                        </div>
                        {holiday.notes && (
                          <div className="holiday-notes">{holiday.notes}</div>
                        )}
                        {isAdmin && (
                          <div className="holiday-actions">
                            <button
                              className="holiday-edit-btn"
                              onClick={() => openEditHolidayModal(holiday)}
                            >
                              Edit
                            </button>
                            <button
                              className="holiday-delete-btn"
                              onClick={() => deleteHoliday(holiday.id)}
                            >
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

            {/* Drop-offs Section */}
            {selectedDateBookings.dropoffs.length > 0 && (
              <div className={`detail-section collapsible ${collapsedSections.dropoffs ? 'collapsed' : ''}`}>
                <h4
                  className="detail-section-title dropoff clickable"
                  onClick={() => toggleSection('dropoffs')}
                >
                  <span className="collapse-icon">{collapsedSections.dropoffs ? '▶' : '▼'}</span>
                  🚗 Drop-offs ({selectedDateBookings.dropoffs.length})
                </h4>
                <div className={`detail-bookings collapsible-content ${collapsedSections.dropoffs ? 'hidden' : ''}`}>
                  {selectedDateBookings.dropoffs
                    .slice()
                    .sort((a, b) => {
                      // Real datetime — ensures overnight tail (e.g.
                      // 00:15 next day re-bucketed onto today) sorts AFTER
                      // today's 23:55, not before today's 08:00.
                      const ka = `${a.dropoff_date || ''}T${(a.dropoff_time || '').slice(0, 5)}`
                      const kb = `${b.dropoff_date || ''}T${(b.dropoff_time || '').slice(0, 5)}`
                      return ka.localeCompare(kb)
                    })
                    .map((booking) => (
                      <div key={booking.id} className={`detail-booking-card ${booking.status === 'refunded' ? 'detail-booking-refunded' : ''}`}>
                        {booking.status === 'refunded' && (
                          <span className="booking-refunded-badge" title="This booking was refunded — customer may not arrive">REFUNDED</span>
                        )}
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
                          {booking.vehicle?.colour} {booking.vehicle?.make}
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
              <div className={`detail-section collapsible ${collapsedSections.pickups ? 'collapsed' : ''}`}>
                <h4
                  className="detail-section-title pickup clickable"
                  onClick={() => toggleSection('pickups')}
                >
                  <span className="collapse-icon">{collapsedSections.pickups ? '▶' : '▼'}</span>
                  🛬 Pick-ups ({selectedDateBookings.pickups.length})
                </h4>
                <div className={`detail-bookings collapsible-content ${collapsedSections.pickups ? 'hidden' : ''}`}>
                  {selectedDateBookings.pickups
                    .slice()
                    .sort((a, b) => {
                      // Real datetime — ensures overnight tail (e.g.
                      // 00:25 next day re-bucketed onto today) sorts AFTER
                      // today's 23:55, not before today's 08:15.
                      const ka = `${a.pickup_date || ''}T${(a.pickup_time || '').slice(0, 5)}`
                      const kb = `${b.pickup_date || ''}T${(b.pickup_time || '').slice(0, 5)}`
                      return ka.localeCompare(kb)
                    })
                    .map((booking) => (
                      <div key={booking.id} className={`detail-booking-card ${booking.status === 'refunded' ? 'detail-booking-refunded' : ''}`}>
                        {booking.status === 'refunded' && (
                          <span className="booking-refunded-badge" title="This booking was refunded — customer may not arrive">REFUNDED</span>
                        )}
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
                          {booking.vehicle?.colour} {booking.vehicle?.make}
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
              <div className={`detail-section collapsible ${collapsedSections.shifts ? 'collapsed' : ''}`}>
                <div className="shifts-section-header">
                  <h4
                    className="detail-section-title shifts clickable"
                    onClick={() => toggleSection('shifts')}
                  >
                    <span className="collapse-icon">{collapsedSections.shifts ? '▶' : '▼'}</span>
                    📅 Shifts ({selectedDateShifts.length})
                  </h4>
                  {isAdmin && selectedShiftIds.length > 0 && (
                    <div className="bulk-actions-bar">
                      <span className="bulk-selection-count">{selectedShiftIds.length} selected</span>
                      <button className="bulk-edit-btn" onClick={openBulkEditModal}>
                        Bulk Edit
                      </button>
                      <button className="bulk-clear-btn" onClick={clearShiftSelection}>
                        Clear
                      </button>
                    </div>
                  )}
                </div>
                <div className={`shift-list collapsible-content ${collapsedSections.shifts ? 'hidden' : ''}`}>
                  {selectedDateShifts.map((shift) => {
                    const statusConfig = SHIFT_STATUS_CONFIG[shift.status] || SHIFT_STATUS_CONFIG.scheduled

                    return (
                      <div key={shift.id} className={`shift-card ${selectedShiftIds.includes(shift.id) ? 'selected' : ''}`}>
                        {isAdmin && (
                          <div className="shift-select-checkbox">
                            <input
                              type="checkbox"
                              checked={selectedShiftIds.includes(shift.id)}
                              onChange={() => toggleShiftSelection(shift.id)}
                              onClick={(e) => e.stopPropagation()}
                            />
                          </div>
                        )}
                        <div className="shift-card-header">
                          <div className="shift-time-range">
                            <span className="shift-time">{formatTime(shift.start_time)}</span>
                            <span className="shift-time-separator">to</span>
                            <span className="shift-time">{formatTime(shift.end_time)}</span>
                          </div>
                          {shift.intended_driver_type === 'fleet' ? (
                            <div className="driver-type-badge driver-type-fleet" title="Fleet driver shift">
                              🚐 Fleet
                            </div>
                          ) : (
                            <div className="driver-type-badge driver-type-jockey" title="Jockey shift">
                              🏇 Jockey
                            </div>
                          )}
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
                              {[...shift.bookings]
                                .sort((a, b) => (a.time || '').localeCompare(b.time || ''))
                                .map((booking, idx) => (
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

                        {/* Employee: Release own shift */}
                        {!isAdmin && shift.staff_id && (
                          <div className="shift-card-actions">
                            <button
                              className="shift-release-btn"
                              onClick={() => openReleaseModal(shift)}
                            >
                              {getHoursUntilShift(shift) < 48 ? 'Cannot Release' : 'Release Shift'}
                            </button>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Available Shifts Section (Employee only) */}
            {!isAdmin && (() => {
              // Filter available shifts for selected date
              const availableForDate = availableShifts.filter(shift => shift.date === selectedDate)
              if (availableForDate.length === 0) return null

              return (
                <div className={`detail-section collapsible ${collapsedSections.availableShifts ? 'collapsed' : ''}`}>
                  <h4
                    className="detail-section-title available-shifts clickable"
                    onClick={() => toggleSection('availableShifts')}
                  >
                    <span className="collapse-icon">{collapsedSections.availableShifts ? '▶' : '▼'}</span>
                    ✨ Available Shifts ({availableForDate.length})
                  </h4>
                  <div className={`shift-list available-shift-list collapsible-content ${collapsedSections.availableShifts ? 'hidden' : ''}`}>
                    {availableForDate.map((shift) => {
                      return (
                        <div key={shift.id} className="shift-card available-shift-card">
                          <div className="shift-card-header">
                            <div className="shift-time-range">
                              <span className="shift-time">{formatTime(shift.start_time)}</span>
                              <span className="shift-time-separator">to</span>
                              <span className="shift-time">{formatTime(shift.end_time)}</span>
                            </div>
                            <div className="shift-card-pills">
                              {shift.intended_driver_type === 'fleet' ? (
                                <div className="driver-type-badge driver-type-fleet" title="Fleet driver shift">
                                  🚐 Fleet
                                </div>
                              ) : (
                                <div className="driver-type-badge driver-type-jockey" title="Jockey shift">
                                  🏇 Jockey
                                </div>
                              )}
                            </div>
                          </div>

                          <div className="shift-card-body">
                            {shift.bookings && shift.bookings.length > 0 ? (
                              <div className="shift-bookings-list">
                                {[...shift.bookings]
                                  .sort((a, b) => (a.time || '').localeCompare(b.time || ''))
                                  .map((booking) => (
                                  <div key={booking.id} className="shift-booking-info">
                                    <div className="shift-booking-header">
                                      <span className={`shift-booking-type ${booking.type}`}>
                                        {booking.type === 'dropoff' ? '🚗' : '🛬'}
                                      </span>
                                      <span className="shift-booking-ref">{booking.reference}</span>
                                      <span className="shift-booking-customer">{booking.customer_name}</span>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <div className="shift-no-bookings">No bookings linked</div>
                            )}

                            {shift.notes && <div className="shift-notes">{shift.notes}</div>}
                          </div>

                          <div className="shift-card-actions">
                            <button
                              className="shift-claim-btn"
                              onClick={() => openClaimModal(shift)}
                            >
                              Claim Shift
                            </button>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })()}

            {/* Your Unavailability Section (Employee only) */}
            {!isAdmin && (() => {
              // Filter unavailabilities for selected date
              const unavailForDate = getUnavailabilitiesForDate(selectedDate)
              if (unavailForDate.length === 0) return null

              return (
                <div className="unavailability-section">
                  <h4
                    className="section-title collapsible-header"
                    onClick={() => toggleSection('unavailability')}
                  >
                    <span className="collapse-icon">{collapsedSections.unavailability ? '▶' : '▼'}</span>
                    🚫 Your Unavailability ({unavailForDate.length})
                  </h4>
                  <div className={`unavail-list collapsible-content ${collapsedSections.unavailability ? 'hidden' : ''}`}>
                    {unavailForDate.map((unavail) => (
                      <div key={unavail.id} className="unavail-card">
                        <div className="unavail-card-info">
                          <div className="unavail-dates">
                            {formatDateUK(unavail.start_date)}
                            {unavail.start_date !== unavail.end_date && ` - ${formatDateUK(unavail.end_date)}`}
                          </div>
                          {(unavail.start_time || unavail.end_time) && (
                            <div className="unavail-times">
                              {formatTime(unavail.start_time) || '00:00'} - {formatTime(unavail.end_time) || '23:59'}
                            </div>
                          )}
                          {unavail.notes && <div className="unavail-notes">{unavail.notes}</div>}
                        </div>
                        <div className="unavail-card-actions">
                          <button
                            className="unavail-delete-btn"
                            onClick={() => deleteUnavailability(unavail.id)}
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })()}

            {/* No content message */}
            {selectedDateBookings.dropoffs.length === 0 &&
              selectedDateBookings.pickups.length === 0 &&
              selectedDateShifts.length === 0 && (
                <p className="no-content">No bookings or shifts scheduled for this date.</p>
              )}
          </div>
          </div>
        </div>
      )}

      {/* Shift Modal (Admin only) */}
      {showShiftModal && isAdmin && (
        <div className="modal-overlay" onClick={closeShiftModal}>
          <div className="modal-content modal-content-wide" onClick={(e) => e.stopPropagation()}>
            <h3>{editingShift ? 'Edit Shift' : 'New Shift'}</h3>

            {error && <div className="modal-error">{error}</div>}

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
                    onChange={(e) => {
                      const formatted = formatTimeInput24h(e.target.value)
                      handleShiftFormChange('start_time', formatted)
                    }}
                    placeholder="HH:MM"
                    maxLength={5}
                  />
                </div>
                <div className="modal-form-group">
                  <label>End Time (24hr)</label>
                  <input
                    type="text"
                    value={shiftForm.end_time}
                    onChange={(e) => {
                      const formatted = formatTimeInput24h(e.target.value)
                      handleShiftFormChange('end_time', formatted)
                    }}
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
                  <label>Driver Type</label>
                  <select
                    value={shiftForm.intended_driver_type}
                    onChange={(e) => handleShiftFormChange('intended_driver_type', e.target.value)}
                    disabled={!!shiftForm.staff_id}
                    title={shiftForm.staff_id
                      ? "When assigned, the driver type follows the assigned user's record automatically."
                      : "Choose who can claim this shift if left unassigned."}
                  >
                    <option value="jockey">Jockey</option>
                    <option value="fleet">Fleet</option>
                  </select>
                  <small style={{ color: '#888', fontSize: '0.75rem' }}>
                    {shiftForm.staff_id
                      ? "Auto from assigned staff"
                      : "Jockey shifts visible to jockeys only · Fleet shifts visible to all drivers"}
                  </small>
                </div>
                <div className="modal-form-group">
                  <label>Assign Staff</label>
                  {(() => {
                    // Convert UK date to ISO for holiday check
                    const isoDate = shiftForm.date ? ukToISO(shiftForm.date) : null
                    const staffOnHolidaySet = isoDate && isoDate.length === 10 ? getStaffOnHolidayForDate(isoDate) : new Set()
                    const hasStaffOnHoliday = staffOnHolidaySet.size > 0

                    return (
                      <>
                        <select
                          value={shiftForm.staff_id}
                          onChange={(e) => {
                            const selectedId = parseInt(e.target.value)
                            if (selectedId && staffOnHolidaySet.has(selectedId)) {
                              return // Prevent selection
                            }
                            handleShiftFormChange('staff_id', e.target.value)
                          }}
                        >
                          <option value="">Unassigned</option>
                          {employees.map((emp) => {
                            const isOnHoliday = staffOnHolidaySet.has(emp.id)
                            return (
                              <option key={emp.id} value={emp.id} disabled={isOnHoliday}>
                                {isOnHoliday ? '🏖️ ' : ''}{emp.first_name} {emp.last_name}{isOnHoliday ? ' (On Leave)' : ''}
                              </option>
                            )
                          })}
                        </select>
                        {hasStaffOnHoliday && (
                          <div className="staff-on-holiday-warning">
                            ⚠️ Staff on leave are disabled and cannot be assigned
                          </div>
                        )}
                      </>
                    )
                  })()}
                </div>
              </div>

              {/* Duplicate Shift Feature - only show when creating new shift */}
              {!editingShift && (
                <div className="duplicate-shift-section">
                  <label className="duplicate-checkbox-label">
                    <input
                      type="checkbox"
                      checked={duplicateMode}
                      onChange={(e) => {
                        setDuplicateMode(e.target.checked)
                        if (!e.target.checked) {
                          setAdditionalStaffIds([])
                        }
                      }}
                    />
                    <span>Duplicate shift for additional staff</span>
                  </label>

                  {duplicateMode && (
                    <div className="additional-staff-section">
                      <label>Select staff members (up to 6):</label>
                      {(() => {
                        // Convert UK date to ISO for holiday check
                        const isoDate = shiftForm.date ? ukToISO(shiftForm.date) : null
                        const staffOnHolidaySet = isoDate && isoDate.length === 10 ? getStaffOnHolidayForDate(isoDate) : new Set()
                        const hasStaffOnHoliday = staffOnHolidaySet.size > 0

                        return (
                          <>
                            {hasStaffOnHoliday && (
                              <div className="staff-on-holiday-warning" style={{ marginBottom: '10px' }}>
                                ⚠️ Staff on leave (🏖️) are disabled and cannot be selected
                              </div>
                            )}
                            <div className="additional-staff-grid">
                              {employees.map((emp) => {
                                const isSelected = additionalStaffIds.includes(String(emp.id))
                                const isOnHoliday = staffOnHolidaySet.has(emp.id)
                                const isDisabled = isOnHoliday || (!isSelected && additionalStaffIds.length >= 6)
                                return (
                                  <label
                                    key={emp.id}
                                    className={`additional-staff-checkbox ${isSelected ? 'selected' : ''} ${isDisabled ? 'disabled' : ''} ${isOnHoliday ? 'on-holiday' : ''}`}
                                    title={isOnHoliday ? 'On leave - cannot be assigned' : ''}
                                  >
                                    <input
                                      type="checkbox"
                                      checked={isSelected}
                                      disabled={isDisabled}
                                      onChange={(e) => {
                                        if (e.target.checked) {
                                          setAdditionalStaffIds([...additionalStaffIds, String(emp.id)])
                                        } else {
                                          setAdditionalStaffIds(additionalStaffIds.filter(id => id !== String(emp.id)))
                                        }
                                      }}
                                    />
                                    <span className="staff-name">
                                      {isOnHoliday && <span className="holiday-indicator">🏖️</span>}
                                      {emp.first_name} {emp.last_name}
                                    </span>
                                  </label>
                                )
                              })}
                            </div>
                          </>
                        )
                      })()}
                      {additionalStaffIds.length > 0 && (
                        <div className="duplicate-summary">
                          Will create {additionalStaffIds.length} shift{additionalStaffIds.length > 1 ? 's' : ''} ({additionalStaffIds.length}/6 selected)
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

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

      {/* Bulk Edit Modal */}
      {showBulkEditModal && isAdmin && (
        <div className="modal-overlay" onClick={closeBulkEditModal}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Bulk Edit ({selectedShiftIds.length} shifts)</h3>

            {error && <div className="modal-error">{error}</div>}

            <div className="modal-form">
              <div className="modal-form-group">
                <label>Action</label>
                <select
                  value={bulkEditForm.action}
                  onChange={(e) => setBulkEditForm({ ...bulkEditForm, action: e.target.value })}
                >
                  <option value="edit_times">Edit Times</option>
                  <option value="add_bookings">Add Bookings</option>
                  <option value="delete">Delete All</option>
                </select>
              </div>

              {bulkEditForm.action === 'edit_times' && (
                <>
                  <div className="modal-form-row">
                    <div className="modal-form-group">
                      <label>New Start Time (leave blank to keep)</label>
                      <input
                        type="text"
                        value={bulkEditForm.start_time}
                        onChange={(e) => {
                          const formatted = formatTimeInput24h(e.target.value)
                          setBulkEditForm({ ...bulkEditForm, start_time: formatted })
                        }}
                        placeholder="HH:MM"
                        maxLength={5}
                      />
                    </div>
                    <div className="modal-form-group">
                      <label>New End Time (leave blank to keep)</label>
                      <input
                        type="text"
                        value={bulkEditForm.end_time}
                        onChange={(e) => {
                          const formatted = formatTimeInput24h(e.target.value)
                          setBulkEditForm({ ...bulkEditForm, end_time: formatted })
                        }}
                        placeholder="HH:MM"
                        maxLength={5}
                      />
                    </div>
                  </div>
                </>
              )}

              {bulkEditForm.action === 'add_bookings' && (
                <div className="modal-form-group">
                  <label>Select Bookings to Add</label>
                  {loadingDateBookings ? (
                    <div className="booking-checkboxes loading">Loading bookings...</div>
                  ) : dateBookings.length === 0 ? (
                    <div className="booking-checkboxes empty">No bookings available for selected date(s)</div>
                  ) : (
                    <div className="booking-checkboxes">
                      {dateBookings.filter(b => b.type === 'dropoff').length > 0 && (
                        <div className="booking-group">
                          <div className="booking-group-label">🚗 Drop-offs</div>
                          {dateBookings.filter(b => b.type === 'dropoff').map((b) => (
                            <label key={`dropoff-${b.id}`} className="booking-checkbox">
                              <input
                                type="checkbox"
                                checked={bulkEditForm.booking_ids.includes(b.id)}
                                onChange={(e) => {
                                  if (e.target.checked) {
                                    setBulkEditForm({ ...bulkEditForm, booking_ids: [...bulkEditForm.booking_ids, b.id] })
                                  } else {
                                    setBulkEditForm({ ...bulkEditForm, booking_ids: bulkEditForm.booking_ids.filter(id => id !== b.id) })
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
                                checked={bulkEditForm.booking_ids.includes(b.id)}
                                onChange={(e) => {
                                  if (e.target.checked) {
                                    setBulkEditForm({ ...bulkEditForm, booking_ids: [...bulkEditForm.booking_ids, b.id] })
                                  } else {
                                    setBulkEditForm({ ...bulkEditForm, booking_ids: bulkEditForm.booking_ids.filter(id => id !== b.id) })
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
              )}

              {bulkEditForm.action === 'delete' && (
                <div className="bulk-delete-warning">
                  <p>⚠️ Are you sure you want to delete {selectedShiftIds.length} shift{selectedShiftIds.length > 1 ? 's' : ''}?</p>
                  <p>This action cannot be undone.</p>
                </div>
              )}
            </div>

            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={closeBulkEditModal}
                disabled={savingBulkEdit}
              >
                Cancel
              </button>
              <button
                className={`modal-btn ${bulkEditForm.action === 'delete' ? 'modal-btn-danger' : 'modal-btn-primary'}`}
                onClick={executeBulkEdit}
                disabled={savingBulkEdit || (bulkEditForm.action === 'edit_times' && !bulkEditForm.start_time && !bulkEditForm.end_time) || (bulkEditForm.action === 'add_bookings' && bulkEditForm.booking_ids.length === 0)}
              >
                {savingBulkEdit ? 'Processing...' : bulkEditForm.action === 'delete' ? 'Delete All' : 'Apply Changes'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Blocked Date Modal */}
      {showBlockedDateModal && isAdmin && (
        <div className="modal-overlay" onClick={closeBlockedDateModal}>
          <div className="modal-content modal-content-wide" onClick={(e) => e.stopPropagation()}>
            <h3>{editingBlockedDate ? 'Edit Blocked Date' : 'Block Date'}</h3>

            <div className="modal-form">
              <div className="modal-form-row">
                <div className="modal-form-group">
                  <label>Start Date</label>
                  <input
                    type="date"
                    value={blockedDateForm.start_date}
                    onChange={(e) =>
                      setBlockedDateForm({ ...blockedDateForm, start_date: e.target.value })
                    }
                  />
                </div>
                <div className="modal-form-group">
                  <label>End Date</label>
                  <input
                    type="date"
                    value={blockedDateForm.end_date}
                    onChange={(e) =>
                      setBlockedDateForm({ ...blockedDateForm, end_date: e.target.value })
                    }
                  />
                </div>
              </div>

              {/* Full day blocking or time slots info */}
              <div className="modal-form-group">
                <label>Block Type {timeSlots.length > 0 && <span className="time-slots-info">(Time slots override full day settings)</span>}</label>
                <div className="checkbox-group" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <label className="checkbox-label" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <input
                      type="checkbox"
                      checked={blockedDateForm.block_dropoffs}
                      onChange={(e) =>
                        setBlockedDateForm({ ...blockedDateForm, block_dropoffs: e.target.checked })
                      }
                      disabled={timeSlots.length > 0}
                      style={{ width: '18px', height: '18px', flexShrink: 0 }}
                    />
                    Block Drop-offs {timeSlots.length > 0 && '(full day)'}
                  </label>
                  <label className="checkbox-label" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <input
                      type="checkbox"
                      checked={blockedDateForm.block_pickups}
                      onChange={(e) =>
                        setBlockedDateForm({ ...blockedDateForm, block_pickups: e.target.checked })
                      }
                      disabled={timeSlots.length > 0}
                      style={{ width: '18px', height: '18px', flexShrink: 0 }}
                    />
                    Block Pick-ups {timeSlots.length > 0 && '(full day)'}
                  </label>
                </div>
                {timeSlots.length > 0 && (
                  <p className="time-slots-note">
                    Time slots are configured - only specific hours will be blocked instead of the full day.
                  </p>
                )}
              </div>

              <div className="modal-form-group">
                <label>Reason (optional)</label>
                <input
                  type="text"
                  value={blockedDateForm.reason}
                  onChange={(e) =>
                    setBlockedDateForm({ ...blockedDateForm, reason: e.target.value })
                  }
                  placeholder="e.g., Bank Holiday, Staff Training, etc."
                />
              </div>

              {/* Time Slots Section - only show when editing existing blocked date */}
              {editingBlockedDate && (
                <div className="time-slots-section">
                  <div className="time-slots-header">
                    <h4>Time Slots (Partial Day Blocking)</h4>
                    {!showTimeSlotForm && (
                      <button
                        type="button"
                        className="time-slot-add-btn"
                        onClick={openNewTimeSlotForm}
                      >
                        + Add Time Slot
                      </button>
                    )}
                  </div>

                  <p className="time-slots-description">
                    Add specific time ranges to block instead of the entire day.
                    When time slots exist, only those hours are blocked.
                  </p>

                  {/* Time Slot Form */}
                  {showTimeSlotForm && (
                    <div className="time-slot-form">
                      <label className="time-slot-form-label">Block bookings from:</label>
                      <div className="time-slot-time-row">
                        <input
                          type="text"
                          placeholder="06:00"
                          maxLength={5}
                          className="time-input"
                          value={timeSlotForm.start_time}
                          onChange={(e) => {
                            const formatted = formatTimeInput24h(e.target.value)
                            setTimeSlotForm({ ...timeSlotForm, start_time: formatted })
                          }}
                        />
                        <span className="time-separator">to</span>
                        <input
                          type="text"
                          placeholder="14:00"
                          maxLength={5}
                          className="time-input"
                          value={timeSlotForm.end_time}
                          onChange={(e) => {
                            const formatted = formatTimeInput24h(e.target.value)
                            setTimeSlotForm({ ...timeSlotForm, end_time: formatted })
                          }}
                        />
                      </div>

                      <label className="time-slot-form-label">What to block:</label>
                      <div className="time-slot-block-options">
                        <label className={`block-option ${timeSlotForm.block_dropoffs && timeSlotForm.block_pickups ? 'selected' : ''}`}>
                          <input
                            type="radio"
                            name="blockType"
                            checked={timeSlotForm.block_dropoffs && timeSlotForm.block_pickups}
                            onChange={() => setTimeSlotForm({ ...timeSlotForm, block_dropoffs: true, block_pickups: true })}
                          />
                          <span className="option-icon">🚫</span>
                          <span className="option-text">Both</span>
                        </label>
                        <label className={`block-option ${timeSlotForm.block_dropoffs && !timeSlotForm.block_pickups ? 'selected' : ''}`}>
                          <input
                            type="radio"
                            name="blockType"
                            checked={timeSlotForm.block_dropoffs && !timeSlotForm.block_pickups}
                            onChange={() => setTimeSlotForm({ ...timeSlotForm, block_dropoffs: true, block_pickups: false })}
                          />
                          <span className="option-icon">🚗</span>
                          <span className="option-text">Drop-offs only</span>
                        </label>
                        <label className={`block-option ${!timeSlotForm.block_dropoffs && timeSlotForm.block_pickups ? 'selected' : ''}`}>
                          <input
                            type="radio"
                            name="blockType"
                            checked={!timeSlotForm.block_dropoffs && timeSlotForm.block_pickups}
                            onChange={() => setTimeSlotForm({ ...timeSlotForm, block_dropoffs: false, block_pickups: true })}
                          />
                          <span className="option-icon">🛬</span>
                          <span className="option-text">Pick-ups only</span>
                        </label>
                      </div>

                      <div className="modal-form-group">
                        <label>Reason (optional)</label>
                        <input
                          type="text"
                          value={timeSlotForm.reason}
                          onChange={(e) =>
                            setTimeSlotForm({ ...timeSlotForm, reason: e.target.value })
                          }
                          placeholder="e.g., Staff meeting, Maintenance"
                        />
                      </div>

                      {/* Preview */}
                      {timeSlotForm.start_time && timeSlotForm.end_time && (
                        <div className="time-slot-preview">
                          Blocking {timeSlotForm.block_dropoffs && timeSlotForm.block_pickups ? 'all bookings' :
                            timeSlotForm.block_dropoffs ? 'drop-offs' : 'pick-ups'} from <strong>{timeSlotForm.start_time}</strong> to <strong>{timeSlotForm.end_time}</strong>
                        </div>
                      )}
                      <div className="time-slot-form-actions">
                        <button
                          type="button"
                          className="modal-btn modal-btn-secondary"
                          onClick={cancelTimeSlotForm}
                          disabled={savingTimeSlot}
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          className="modal-btn modal-btn-primary"
                          onClick={saveTimeSlot}
                          disabled={savingTimeSlot || !timeSlotForm.start_time || !timeSlotForm.end_time || (!timeSlotForm.block_dropoffs && !timeSlotForm.block_pickups)}
                        >
                          {savingTimeSlot ? 'Saving...' : editingTimeSlot ? 'Update Slot' : 'Add Slot'}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Time Slots List */}
                  {loadingTimeSlots ? (
                    <div className="time-slots-loading">Loading time slots...</div>
                  ) : timeSlots.length > 0 ? (
                    <div className="time-slots-list">
                      {timeSlots.map((slot) => (
                        <div key={slot.id} className="time-slot-item">
                          <div className="time-slot-time">
                            {formatTime(slot.start_time)} - {formatTime(slot.end_time)}
                          </div>
                          <div className="time-slot-blocks">
                            {slot.block_dropoffs && <span className="block-badge dropoff">No Drop-offs</span>}
                            {slot.block_pickups && <span className="block-badge pickup">No Pick-ups</span>}
                          </div>
                          {slot.reason && <div className="time-slot-reason">{slot.reason}</div>}
                          <div className="time-slot-actions">
                            <button
                              type="button"
                              className="time-slot-edit-btn"
                              onClick={() => openEditTimeSlotForm(slot)}
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              className="time-slot-delete-btn"
                              onClick={() => deleteTimeSlot(slot.id)}
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="time-slots-empty">
                      No time slots configured. The entire day will be blocked based on settings above.
                    </div>
                  )}
                </div>
              )}

              {/* Warning about existing bookings */}
              {blockedDateForm.start_date && (
                (() => {
                  // Check for bookings in the date range being blocked
                  const startDate = blockedDateForm.start_date
                  const endDate = blockedDateForm.end_date || blockedDateForm.start_date
                  const affectedBookings = bookings.filter(b => {
                    if (b.status !== 'confirmed') return false
                    const hasDropoff = blockedDateForm.block_dropoffs &&
                      b.dropoff_date >= startDate && b.dropoff_date <= endDate
                    const hasPickup = blockedDateForm.block_pickups &&
                      b.pickup_date >= startDate && b.pickup_date <= endDate
                    return hasDropoff || hasPickup
                  })

                  if (affectedBookings.length > 0) {
                    const dropoffCount = affectedBookings.filter(b =>
                      blockedDateForm.block_dropoffs &&
                      b.dropoff_date >= startDate && b.dropoff_date <= endDate
                    ).length
                    const pickupCount = affectedBookings.filter(b =>
                      blockedDateForm.block_pickups &&
                      b.pickup_date >= startDate && b.pickup_date <= endDate
                    ).length

                    return (
                      <div className="blocked-date-warning">
                        <strong>Warning: Existing bookings found:</strong>
                        <p>
                          {dropoffCount > 0 && `${dropoffCount} drop-off${dropoffCount > 1 ? 's' : ''}`}
                          {dropoffCount > 0 && pickupCount > 0 && ' and '}
                          {pickupCount > 0 && `${pickupCount} pick-up${pickupCount > 1 ? 's' : ''}`}
                          {' '}scheduled during this period.
                        </p>
                        <p className="warning-note">These bookings will still need to be fulfilled. Blocking only prevents new bookings.</p>
                      </div>
                    )
                  }
                  return null
                })()
              )}
            </div>

            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={closeBlockedDateModal}>
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={saveBlockedDate}
                disabled={savingBlockedDate || (!blockedDateForm.block_dropoffs && !blockedDateForm.block_pickups && timeSlots.length === 0)}
              >
                {savingBlockedDate ? 'Saving...' : editingBlockedDate ? 'Update' : 'Block Date'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Holiday Modal */}
      {showHolidayModal && isAdmin && (
        <div className="modal-overlay" onClick={closeHolidayModal}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>{editingHoliday ? 'Edit Holiday' : 'Add Holiday'}</h3>

            <div className="modal-form">
              <div className="modal-form-group">
                <label>Staff Member *</label>
                <select
                  value={holidayForm.staff_id}
                  onChange={(e) => setHolidayForm({ ...holidayForm, staff_id: e.target.value })}
                  disabled={editingHoliday}
                >
                  <option value="">Select staff...</option>
                  {employees.map((emp) => (
                    <option key={emp.id} value={emp.id}>
                      {emp.first_name} {emp.last_name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="modal-form-row">
                <div className="modal-form-group">
                  <label>Start Date (DD/MM/YYYY) *</label>
                  <input
                    type="text"
                    value={holidayForm.start_date}
                    onChange={(e) => setHolidayForm({ ...holidayForm, start_date: e.target.value })}
                    placeholder="DD/MM/YYYY"
                  />
                </div>
                <div className="modal-form-group">
                  <label>End Date (DD/MM/YYYY) *</label>
                  <input
                    type="text"
                    value={holidayForm.end_date}
                    onChange={(e) => setHolidayForm({ ...holidayForm, end_date: e.target.value })}
                    placeholder="DD/MM/YYYY"
                  />
                </div>
              </div>

              <div className="modal-form-group">
                <label>Type</label>
                <select
                  value={holidayForm.holiday_type}
                  onChange={(e) => setHolidayForm({ ...holidayForm, holiday_type: e.target.value })}
                >
                  {Object.entries(HOLIDAY_TYPE_CONFIG).map(([value, config]) => (
                    <option key={value} value={value}>
                      {config.icon} {config.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Partial Day Times - only for unavailable type */}
              {holidayForm.holiday_type === 'unavailable' && (
                <div className="modal-form-row">
                  <div className="modal-form-group">
                    <label>Start Time (optional)</label>
                    <input
                      type="text"
                      value={holidayForm.start_time}
                      onChange={(e) => {
                        const formatted = formatTimeInput24h(e.target.value)
                        setHolidayForm({ ...holidayForm, start_time: formatted })
                      }}
                      placeholder="HH:MM (e.g., 09:00)"
                      maxLength={5}
                    />
                    <small style={{ color: '#555', fontSize: '0.75rem' }}>Leave blank for full day</small>
                  </div>
                  <div className="modal-form-group">
                    <label>End Time (optional)</label>
                    <input
                      type="text"
                      value={holidayForm.end_time}
                      onChange={(e) => {
                        const formatted = formatTimeInput24h(e.target.value)
                        setHolidayForm({ ...holidayForm, end_time: formatted })
                      }}
                      placeholder="HH:MM (e.g., 17:00)"
                      maxLength={5}
                    />
                    <small style={{ color: '#555', fontSize: '0.75rem' }}>Leave blank for full day</small>
                  </div>
                </div>
              )}

              <div className="modal-form-group">
                <label>Notes (optional)</label>
                <input
                  type="text"
                  value={holidayForm.notes}
                  onChange={(e) => setHolidayForm({ ...holidayForm, notes: e.target.value })}
                  placeholder="e.g., Family vacation, Doctor's appointment"
                />
              </div>
            </div>

            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={closeHolidayModal}>
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={saveHoliday}
                disabled={savingHoliday || !holidayForm.staff_id || !holidayForm.start_date || !holidayForm.end_date}
              >
                {savingHoliday ? 'Saving...' : editingHoliday ? 'Update' : 'Add Holiday'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Claim Shift Modal (Employee) */}
      {showClaimModal && shiftToClaim && !isAdmin && (
        <div className="modal-overlay" onClick={() => setShowClaimModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Claim Shift</h3>

            <div className="claim-shift-details">
              <div className="claim-shift-date">
                {new Date(shiftToClaim.date + 'T00:00:00').toLocaleDateString('en-GB', {
                  weekday: 'long',
                  day: 'numeric',
                  month: 'long',
                  year: 'numeric',
                })}
              </div>
              <div className="claim-shift-time">
                {formatTime(shiftToClaim.start_time)} - {formatTime(shiftToClaim.end_time)}
              </div>
              {shiftToClaim.bookings && shiftToClaim.bookings.length > 0 && (
                <div className="claim-shift-bookings">
                  <span className="claim-bookings-label">Linked Bookings:</span>
                  {shiftToClaim.bookings.map((booking) => (
                    <div key={booking.id} className="claim-booking-item">
                      <span className="booking-type-icon">{booking.type === 'dropoff' ? '🚗' : '🛬'}</span>
                      <span className="booking-ref">{booking.reference}</span>
                      <span className="booking-customer">{booking.customer_name}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <p className="claim-confirm-text">Are you sure you want to claim this shift?</p>

            {error && <div className="modal-error">{error}</div>}

            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowClaimModal(false)}
                disabled={claimingShift}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={handleClaimShift}
                disabled={claimingShift}
              >
                {claimingShift ? 'Claiming...' : 'Claim Shift'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Release Shift Modal (Employee) */}
      {showReleaseModal && shiftToRelease && !isAdmin && (
        <div className="modal-overlay" onClick={() => setShowReleaseModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Release Shift</h3>

            <div className="release-shift-details">
              <div className="release-shift-date">
                {new Date(shiftToRelease.date + 'T00:00:00').toLocaleDateString('en-GB', {
                  weekday: 'long',
                  day: 'numeric',
                  month: 'long',
                  year: 'numeric',
                })}
              </div>
              <div className="release-shift-time">
                {formatTime(shiftToRelease.start_time)} - {formatTime(shiftToRelease.end_time)}
              </div>

              {getHoursUntilShift(shiftToRelease) < 48 && (
                <div className="release-warning">
                  <strong>Less than 48 hours notice</strong>
                  <p>This shift starts in less than 48 hours. Please contact an administrator to release it.</p>
                </div>
              )}
            </div>

            <p className="release-confirm-text">
              {getHoursUntilShift(shiftToRelease) >= 48
                ? 'Are you sure you want to release this shift? It will become available for other employees.'
                : 'You cannot release this shift yourself. Please contact an administrator.'
              }
            </p>

            {error && <div className="modal-error">{error}</div>}

            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowReleaseModal(false)}
                disabled={releasingShift}
              >
                Cancel
              </button>
              {getHoursUntilShift(shiftToRelease) >= 48 && (
                <button
                  className="modal-btn modal-btn-danger"
                  onClick={handleReleaseShift}
                  disabled={releasingShift}
                >
                  {releasingShift ? 'Releasing...' : 'Release Shift'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Unavailability Modal (Employee only) */}
      {showUnavailModal && !isAdmin && (
        <div className="modal-overlay unavail-modal-overlay" onClick={closeUnavailModal}>
          <div className="modal-content unavail-modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Mark Unavailable</h3>

            <p className="unavail-info-text">
              Mark yourself as unavailable for specific dates or times. You cannot be assigned shifts during this period.
            </p>

            {error && <div className="modal-error">{error}</div>}

            <div className="modal-form">
              <div className="modal-form-row">
                <div className="modal-form-group">
                  <label>Start Date (DD/MM/YYYY) *</label>
                  <input
                    type="text"
                    value={unavailForm.start_date}
                    onChange={(e) => setUnavailForm({ ...unavailForm, start_date: e.target.value })}
                    placeholder="DD/MM/YYYY"
                  />
                </div>
                <div className="modal-form-group">
                  <label>End Date (DD/MM/YYYY) *</label>
                  <input
                    type="text"
                    value={unavailForm.end_date}
                    onChange={(e) => setUnavailForm({ ...unavailForm, end_date: e.target.value })}
                    placeholder="DD/MM/YYYY"
                  />
                </div>
              </div>

              <div className="modal-form-row">
                <div className="modal-form-group">
                  <label>Start Time (optional)</label>
                  <input
                    type="text"
                    value={unavailForm.start_time}
                    onChange={(e) => {
                      const formatted = formatTimeInput24h(e.target.value)
                      setUnavailForm({ ...unavailForm, start_time: formatted })
                    }}
                    placeholder="HH:MM (e.g., 09:00)"
                    maxLength={5}
                  />
                  <small style={{ color: '#555', fontSize: '0.75rem' }}>Leave blank for full day</small>
                </div>
                <div className="modal-form-group">
                  <label>End Time (optional)</label>
                  <input
                    type="text"
                    value={unavailForm.end_time}
                    onChange={(e) => {
                      const formatted = formatTimeInput24h(e.target.value)
                      setUnavailForm({ ...unavailForm, end_time: formatted })
                    }}
                    placeholder="HH:MM (e.g., 17:00)"
                    maxLength={5}
                  />
                  <small style={{ color: '#555', fontSize: '0.75rem' }}>Leave blank for full day</small>
                </div>
              </div>

              <div className="modal-form-group">
                <label>Notes (optional)</label>
                <input
                  type="text"
                  value={unavailForm.notes}
                  onChange={(e) => setUnavailForm({ ...unavailForm, notes: e.target.value })}
                  placeholder="e.g., Doctor's appointment, Personal commitment"
                />
              </div>
            </div>

            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={closeUnavailModal}>
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={saveUnavailability}
                disabled={savingUnavail || !unavailForm.start_date || !unavailForm.end_date}
              >
                {savingUnavail ? 'Saving...' : 'Mark Unavailable'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Team shift popover (view-only, employee mode) */}
      {teamShiftPopover && (
        <div className="modal-overlay" onClick={() => setTeamShiftPopover(null)}>
          <div className="modal-content team-shift-popover" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginTop: 0 }}>{teamShiftPopover.first_name} {teamShiftPopover.last_name}</h3>
            <div style={{ marginBottom: '0.75rem' }}>
              <strong>{formatDateUK(teamShiftPopover.date)}</strong>
              {teamShiftPopover.end_date && teamShiftPopover.end_date !== teamShiftPopover.date && (
                <> – {formatDateUK(teamShiftPopover.end_date)}</>
              )}
            </div>
            <div style={{ marginBottom: '0.75rem' }}>
              {formatTime(teamShiftPopover.start_time)} – {formatTime(teamShiftPopover.end_time)}
            </div>
            {teamShiftPopover.phone && (
              <div style={{ marginBottom: '0.75rem' }}>
                <a href={`tel:${teamShiftPopover.phone}`} className="team-shift-phone">
                  {teamShiftPopover.phone}
                </a>
              </div>
            )}
            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={() => setTeamShiftPopover(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default RosterCalendar
