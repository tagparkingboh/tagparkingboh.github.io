import { useState, useEffect, useMemo, useCallback } from 'react'
import { useAuth } from '../AuthContext'
import { DEFAULT_ONLINE_CAPACITY, getOnlineCapacityForDate } from '../utils/capacity'
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

const getBookingRegistration = (booking) => (
  booking?.vehicle_registration || booking?.vehicle?.registration || ''
).toUpperCase()

export const getUKDateKey = (date = new Date()) => {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/London',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date).reduce((acc, part) => {
    acc[part.type] = part.value
    return acc
  }, {})

  return `${parts.year}-${parts.month}-${parts.day}`
}

export const currentAndFutureDateKeysForUK = (dateKeys = [], date = new Date()) => {
  const todayKey = getUKDateKey(date)
  return (dateKeys || []).filter((dateKey) => dateKey && dateKey >= todayKey)
}

export const isPastDateKeyUK = (dateKey, date = new Date()) => Boolean(
  dateKey && dateKey < getUKDateKey(date)
)

export const getUKDateTimeParts = (date = new Date()) => {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/London',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date).reduce((acc, part) => {
    acc[part.type] = part.value
    return acc
  }, {})

  return {
    dateKey: `${parts.year}-${parts.month}-${parts.day}`,
    minutes: (Number(parts.hour) || 0) * 60 + (Number(parts.minute) || 0),
  }
}

export const getAutoShiftShapeState = (shift) => {
  if (!shift || shift.created_source !== 'auto') return null

  const isAdminShaped = Boolean(shift.admin_shaped_at)
  return {
    isAdminShaped,
    className: isAdminShaped ? 'auto-shaped' : 'auto-original',
    detailLabel: isAdminShaped ? 'Auto ✓ Edited' : 'Auto',
    chipLabel: isAdminShaped ? '✓' : '',
    title: isAdminShaped
      ? 'Auto shift edited, duplicated, split, or merged by admin'
      : 'Original auto shift',
  }
}

export const canShowRosterGenerateCta = ({ isAdmin, selectedDate, reviewIssueCount, gate }) => !!(
  isAdmin &&
  selectedDate &&
  reviewIssueCount > 0 &&
  gate?.can_generate_roster
)

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

const addIsoDays = (isoDate, days) => {
  if (!isoDate) return ''
  const [y, m, d] = isoDate.split('-').map(Number)
  if (!y || !m || !d) return ''
  const dt = new Date(Date.UTC(y, m - 1, d))
  dt.setUTCDate(dt.getUTCDate() + days)
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

// Flights arriving strictly before this UK clock-time belong to the
// previous day's evening shift (e.g. a 00:50 arrival on the 10th is
// shown under the 9th, where the overnight shift covering it started).
// The rule is keyed on arrival_time, not pickup_time — pickup_time is
// being phased out as a primary field. For legacy rows without
// flight_arrival_time we synthesise arrival = pickup_time - 30 min
// as a real datetime so day-wrap is handled.
// Drop-offs are NOT re-bucketed — early-AM drop-offs aren't an
// operational reality in this business.
export const ARRIVAL_OVERNIGHT_CUTOFF = '02:00'

// Group confirmed and refunded bookings by operational day. Drop-offs key on
// `dropoff_date` directly. Pickups key on the operational arrival-day per
// claimPickupDate below. Each day's list is sorted by real datetime so
// re-bucketed events land at the bottom (chronologically later than 23:55
// of the same operational day).
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
  // Resolve the operational-day bucket for a booking's pickup event.
  // Canonical input is (flight_arrival_date, flight_arrival_time) — these
  // are populated on every row from 2026-05-20+ and `flight_arrival_date`
  // is the landing day even when pickup_date drifts (TAG-KNL95826 staging
  // 2026-05-21). When flight_arrival_time is null we synthesise arrival
  // from (pickup_date, pickup_time) by subtracting 30 minutes as a real
  // datetime so a 00:25 pickup wraps to 23:55 the previous day. The
  // ARRIVAL_OVERNIGHT_CUTOFF (02:00) is then compared against the
  // resulting arrival_time: strictly before → re-bucket to D-1.
  const claimPickupDate = (booking) => {
    if (!booking) return null
    let arrivalDate, arrivalTime
    if (booking.flight_arrival_time) {
      arrivalDate = booking.flight_arrival_date || booking.pickup_date
      arrivalTime = String(booking.flight_arrival_time).slice(0, 5)
    } else if (booking.pickup_date && booking.pickup_time) {
      const [y, m, d] = booking.pickup_date.split('-').map(Number)
      const [hh, mm] = String(booking.pickup_time).slice(0, 5).split(':').map(Number)
      if (!y || !m || !d || Number.isNaN(hh) || Number.isNaN(mm)) {
        return booking.flight_arrival_date || booking.pickup_date || null
      }
      const dt = new Date(Date.UTC(y, m - 1, d, hh, mm))
      dt.setUTCMinutes(dt.getUTCMinutes() - 30)
      const yy = dt.getUTCFullYear()
      const mo = String(dt.getUTCMonth() + 1).padStart(2, '0')
      const dd = String(dt.getUTCDate()).padStart(2, '0')
      arrivalDate = `${yy}-${mo}-${dd}`
      arrivalTime = `${String(dt.getUTCHours()).padStart(2, '0')}:${String(dt.getUTCMinutes()).padStart(2, '0')}`
    } else {
      return booking.flight_arrival_date || booking.pickup_date || null
    }
    if (!arrivalDate) return null
    if (arrivalTime < ARRIVAL_OVERNIGHT_CUTOFF) return prevIsoDate(arrivalDate)
    return arrivalDate
  }
  const sortKey = (date, time) =>
    `${date}T${time ? String(time).slice(0, 5) : '00:00'}`

  ;(bookings || [])
    .filter((b) => b && (b.status === 'confirmed' || b.status === 'refunded'))
    .forEach((booking) => {
      if (booking.dropoff_date) {
        ensureDay(booking.dropoff_date).dropoffs.push(booking)
      }
      if (booking.pickup_date || booking.flight_arrival_date) {
        const key = claimPickupDate(booking)
        if (key) ensureDay(key).pickups.push(booking)
      }
    })

  // Sort within each day by the time the jockey needs to be at the airport.
  // For pickups that's the canonical arrival moment (flight_arrival_date +
  // flight_arrival_time when set); legacy rows fall back to pickup_date +
  // pickup_time. Without this, TAG-KNL95826 (pickup_date=7/3, arrival=7/4)
  // sorted into the 7/4 day at a 7/3 sort key, ending up at the bottom of
  // the wrong day's pickup list.
  const pickupSortKey = (b) =>
    sortKey(
      b.flight_arrival_date || b.pickup_date,
      b.flight_arrival_time || b.pickup_time,
    )
  Object.values(grouped).forEach((day) => {
    day.dropoffs.sort((a, b) =>
      sortKey(a.dropoff_date, a.dropoff_time).localeCompare(
        sortKey(b.dropoff_date, b.dropoff_time)
      )
    )
    day.pickups.sort((a, b) =>
      pickupSortKey(a).localeCompare(pickupSortKey(b))
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

// Sort key (minutes-from-operational-day-start) for a shift entry in a
// day's shift list. Normal daytime + standard overnight shifts (start_time
// > end_time, crossing midnight) sort by start_time as-is. Re-bucketed
// overnights — date=D / end_date=D+1 with start_time < end_time (the
// entire wall-clock window sits after midnight on D+1) — get a +24h
// offset so they land at the bottom of D's list, where the work actually
// happens chronologically. Without this a 00:20-01:20 tail of Friday-
// evening work sorts ahead of Friday's afternoon 13:10 shift.
export const shiftSortMinutes = (shift) => {
  if (!shift) return 0
  const startStr = shift.displayStartTime || shift.start_time || '00:00'
  const endStr = shift.displayEndTime || shift.end_time || '00:00'
  const [h, m] = String(startStr).slice(0, 5).split(':').map(Number)
  const isOvernight = !!(shift.end_date && shift.end_date !== shift.date) || !!shift.isOvernight
  const isAfterMidnightTail = isOvernight && startStr < endStr
  return (h || 0) * 60 + (m || 0) + (isAfterMidnightTail ? 24 * 60 : 0)
}

// Sort bookings within a shift in true chronological order. For overnight
// shifts (start > end across midnight) any booking time before the shift
// start belongs to the next day, so add 24h before comparing — otherwise
// a 00:00 pickup would sort ahead of a 22:55 pickup on the same shift.
const sortBookingsForShift = (bookings, shift) => {
  if (!bookings || bookings.length === 0) return []
  const toMins = (t) => {
    if (!t) return 0
    const [h, m] = t.split(':').map(Number)
    return (h || 0) * 60 + (m || 0)
  }
  const startMins = toMins(shift?.start_time)
  const isOvernight = !!(shift?.end_date && shift.end_date !== shift.date)
  const wrappedMins = (t) => {
    const mins = toMins(t)
    return isOvernight && mins < startMins ? mins + 24 * 60 : mins
  }
  return [...bookings].sort((a, b) => wrappedMins(a.time) - wrappedMins(b.time))
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

// Map a v3 toggle value to the /api/roster ?source= query param.
// 'manual' → omit (backend default already excludes auto, includes manual+planner).
// 'auto' / 'all' → pass through.
export const sourceParamFor = (filter) => (filter === 'auto' || filter === 'all') ? filter : null

export const calculateHoursTotal = (employees = []) => employees.reduce((total, employee) => {
  const hours = Number(employee?.total_hours)
  return total + (Number.isFinite(hours) ? hours : 0)
}, 0)

export const calculateShiftTotal = (employees = []) => employees.reduce((total, employee) => {
  const shifts = Number(employee?.shift_count)
  return total + (Number.isFinite(shifts) ? shifts : 0)
}, 0)

const DEFAULT_COLLAPSED_SECTIONS = {
  dropoffs: true,
  pickups: true,
  shifts: true,
  availableShifts: true,
  holidays: true,
  unavailability: true,
}

const bookingCustomerName = (booking) => {
  const customer = booking?.customer
  return [
    customer?.first_name || booking?.customer_first_name,
    customer?.last_name || booking?.customer_last_name,
  ].filter(Boolean).join(' ').trim()
}

const bookingEventTime = (booking, type) => (
  type === 'dropoff'
    ? booking?.dropoff_time
    : booking?.flight_arrival_time || booking?.pickup_time
)

const bookingEventFlight = (booking, type) => (
  type === 'dropoff'
    ? booking?.dropoff_flight_number
    : booking?.pickup_flight_number
)

const bookingEventDestination = (booking, type) => (
  type === 'dropoff'
    ? booking?.dropoff_destination
    : booking?.pickup_origin
)

const bookingEventKey = (bookingId, type) => `${bookingId}:${type || 'unknown'}`

const bookingEventLabel = (type) => (type === 'dropoff' ? 'Drop-off' : 'Pick-up')

const reviewItemTimeMinutes = (item) => {
  const value = String(item?.time || item?.event_time || '').slice(0, 5)
  const [hours, minutes] = value.split(':').map(Number)
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return Number.MAX_SAFE_INTEGER
  return (hours * 60) + minutes
}

export const sortRosterReviewItems = (items = []) => (
  [...items].sort((a, b) => {
    const dateCompare = String(a?.date || '').localeCompare(String(b?.date || ''))
    if (dateCompare !== 0) return dateCompare

    const timeCompare = reviewItemTimeMinutes(a) - reviewItemTimeMinutes(b)
    if (timeCompare !== 0) return timeCompare

    const typeCompare = String(a?.event_type || '').localeCompare(String(b?.event_type || ''))
    if (typeCompare !== 0) return typeCompare

    return String(a?.booking_reference || '').localeCompare(String(b?.booking_reference || ''))
  })
)

const shiftLinkedBookings = (shift) => {
  if (Array.isArray(shift?.bookings) && shift.bookings.length > 0) return shift.bookings
  if (shift?.booking_id) {
    return [{
      id: shift.booking_id,
      reference: shift.booking_reference,
      type: shift.booking_type,
      customer_name: shift.booking_customer_name,
      time: shift.booking_time,
      flight_number: shift.booking_flight_number,
      destination: shift.booking_destination,
    }]
  }
  return []
}

const normaliseStaffId = (staffId) => {
  if (staffId === null || staffId === undefined || staffId === '') return null
  return staffId
}

const timeToMinutes = (time) => {
  if (!time) return 0
  const [hours, minutes] = String(time).slice(0, 5).split(':').map(Number)
  return (hours || 0) * 60 + (minutes || 0)
}

const DEMAND_DROPOFF_DAY_START = 8 * 60
const DEMAND_RETURN_DAY_START = timeToMinutes(ARRIVAL_OVERNIGHT_CUTOFF)
const DEMAND_RETURN_LATE_START = 17 * 60
export const PAST_DAY_OVERNIGHT_GRACE_MINUTES = 30

export const shiftKeepsPastDayVisible = (
  shift,
  dateKey,
  date = new Date(),
  graceMinutes = PAST_DAY_OVERNIGHT_GRACE_MINUTES,
) => {
  if (!shift || !dateKey) return false

  const startDate = shift.date || dateKey
  const endDateFromShift = shift.end_date || null
  const startTime = shift.displayStartTime || shift.start_time
  const endTime = shift.displayEndTime || shift.end_time
  if (!endTime) return false

  const startMinutes = timeToMinutes(startTime)
  const endMinutes = timeToMinutes(endTime)
  const crossesMidnight = Boolean(endDateFromShift && endDateFromShift !== startDate)
    || Boolean(shift.isOvernight)
    || endMinutes <= startMinutes
  const endDate = endDateFromShift || (crossesMidnight ? addIsoDays(startDate, 1) : startDate)

  if (!crossesMidnight || !endDate || endDate <= dateKey) return false

  const ukNow = getUKDateTimeParts(date)
  if (ukNow.dateKey < endDate) return true
  if (ukNow.dateKey > endDate) return false
  return ukNow.minutes < endMinutes + graceMinutes
}

const dayHasActiveOvernightShift = (dateKey, ...shiftGroups) => {
  if (!dateKey) return false
  return shiftGroups
    .flat()
    .some((shift) => shiftKeepsPastDayVisible(shift, dateKey))
}

const demandLevelFor = (total, maxTotal) => {
  if (!total || !maxTotal) return 0
  return Math.max(1, Math.ceil((total / maxTotal) * 4))
}

export const ROSTER_DEMAND_BUCKETS = [
  { key: 'early_dropoffs', label: 'Early', name: 'Early drop-offs' },
  { key: 'day_dropoffs', label: 'Drop', name: 'Day drop-offs' },
  { key: 'day_returns', label: 'Pick-up', name: 'Day pick-ups' },
  { key: 'late_returns', label: 'Late', name: 'Late pick-ups' },
]

export const getRosterDemandByDate = (bookingsByDate = {}, dateKeys = []) => {
  const keys = (dateKeys.length > 0 ? dateKeys : Object.keys(bookingsByDate).sort())
    .filter(Boolean)

  const rows = keys.map((dateKey) => {
    const day = bookingsByDate[dateKey] || { dropoffs: [], pickups: [] }
    const demand = {
      date: dateKey,
      dayLabel: formatDateUK(dateKey).slice(0, 5),
      early_dropoffs: 0,
      day_dropoffs: 0,
      day_returns: 0,
      late_returns: 0,
    }

    ;(day.dropoffs || []).forEach((booking) => {
      const minutes = timeToMinutes(booking?.dropoff_time)
      if (minutes < DEMAND_DROPOFF_DAY_START) {
        demand.early_dropoffs += 1
      } else {
        demand.day_dropoffs += 1
      }
    })

    ;(day.pickups || []).forEach((booking) => {
      const minutes = timeToMinutes(bookingEventTime(booking, 'pickup'))
      if (minutes < DEMAND_RETURN_DAY_START || minutes >= DEMAND_RETURN_LATE_START) {
        demand.late_returns += 1
      } else {
        demand.day_returns += 1
      }
    })

    const bucketValues = ROSTER_DEMAND_BUCKETS.map((bucket) => demand[bucket.key])
    const total = bucketValues.reduce((sum, count) => sum + count, 0)

    return {
      ...demand,
      total,
      maxBucket: Math.max(1, ...bucketValues),
    }
  })

  const maxTotal = Math.max(0, ...rows.map((row) => row.total))
  return rows.map((row) => ({
    ...row,
    level: demandLevelFor(row.total, maxTotal),
  }))
}

const shiftTimeRange = (shift) => {
  if (!shift) return { start: 0, end: 0 }
  let start = timeToMinutes(shift.displayStartTime || shift.start_time)
  let end = timeToMinutes(shift.displayEndTime || shift.end_time)
  const isAfterMidnightTail = !!(shift.end_date && shift.end_date !== shift.date) && start < end
  if (isAfterMidnightTail) {
    start += 24 * 60
    end += 24 * 60
  } else if (end <= start || !!(shift.end_date && shift.end_date !== shift.date)) {
    end += 24 * 60
  }
  return { start, end }
}

const shiftsOverlap = (a, b) => {
  const ar = shiftTimeRange(a)
  const br = shiftTimeRange(b)
  return ar.start < br.end && br.start < ar.end
}

const assignedShiftBlockersForAutoShift = (shift, dayShifts = []) => {
  if (shift?.created_source !== 'auto' || normaliseStaffId(shift?.staff_id) !== null) return []
  return dayShifts.filter((other) => (
    other?.id !== shift.id &&
    normaliseStaffId(other?.staff_id) !== null &&
    shiftsOverlap(shift, other)
  ))
}

export const getRosterCoverageReviewItems = (dayBookings = { dropoffs: [], pickups: [] }, dayShifts = []) => {
  const events = [
    ...(dayBookings.dropoffs || []).map((booking) => ({ booking, type: 'dropoff' })),
    ...(dayBookings.pickups || []).map((booking) => ({ booking, type: 'pickup' })),
  ].filter(({ booking }) => booking?.id)

  const linkedKeys = new Set()
  const shiftBookingsByKey = new Map()

  ;(dayShifts || []).forEach((shift) => {
    shiftLinkedBookings(shift).forEach((booking) => {
      if (!booking?.id || !booking?.type) return
      const key = bookingEventKey(booking.id, booking.type)
      linkedKeys.add(key)
      if (!shiftBookingsByKey.has(key)) shiftBookingsByKey.set(key, [])
      shiftBookingsByKey.get(key).push({ shift, booking })
    })
  })

  const missingShiftItems = events
    .filter(({ booking, type }) => !linkedKeys.has(bookingEventKey(booking.id, type)))
    .map(({ booking, type }) => ({
      key: `missing-${bookingEventKey(booking.id, type)}`,
      severity: 'warning',
      kind: 'missing-shift',
      message: `${bookingEventLabel(type)} ${booking.reference || `#${booking.id}`} is not linked to a shift.`,
      booking_reference: booking.reference,
      booking_id: booking.id,
      event_type: type,
      customer_name: bookingCustomerName(booking),
      time: bookingEventTime(booking, type),
      flight_number: bookingEventFlight(booking, type),
      destination: bookingEventDestination(booking, type),
    }))

  const unassignedShiftItems = []
  shiftBookingsByKey.forEach((linkedEntries, key) => {
    const unassignedEntries = linkedEntries
      .map((entry) => ({
        ...entry,
        blockers: assignedShiftBlockersForAutoShift(entry.shift, dayShifts),
      }))
      .filter(({ blockers }) => blockers.length > 0)
    if (unassignedEntries.length === 0) return
    const [first] = unassignedEntries
    const event = events.find(({ booking, type }) => bookingEventKey(booking.id, type) === key)
    const linkedBooking = first.booking || {}
    const booking = event?.booking || linkedBooking
    const type = event?.type || linkedBooking.type || 'unknown'
    const shiftSummaries = unassignedEntries.map(({ shift }) => (
      `${formatTime(shift.start_time)}-${formatTime(shift.end_time)}`
    ))
    const blockerSummaries = [
      ...new Set(unassignedEntries.flatMap(({ blockers }) => (
        blockers.map((shift) => `${formatTime(shift.start_time)}-${formatTime(shift.end_time)}`)
      ))),
    ]
    unassignedShiftItems.push({
      key: `unassigned-${key}`,
      severity: 'critical',
      kind: 'unassigned-linked-shift',
      message: `${bookingEventLabel(type)} ${booking.reference || linkedBooking.reference || `#${booking.id}`} is linked to an auto-created unstaffed shift.`,
      booking_reference: booking.reference || linkedBooking.reference,
      booking_id: booking.id || linkedBooking.id,
      event_type: type,
      customer_name: bookingCustomerName(booking) || linkedBooking.customer_name || '',
      time: bookingEventTime(booking, type) || linkedBooking.time,
      flight_number: bookingEventFlight(booking, type) || linkedBooking.flight_number,
      destination: bookingEventDestination(booking, type) || linkedBooking.destination,
      shift_times: shiftSummaries,
      blocking_shift_times: blockerSummaries,
      shift_ids: unassignedEntries.map(({ shift }) => shift.id).filter(Boolean),
    })
  })

  return sortRosterReviewItems([...missingShiftItems, ...unassignedShiftItems])
}

export const getRosterCoverageReviewItemsByDate = (bookingsByDate = {}, shiftsByDate = {}, dateKeys = []) => (
  sortRosterReviewItems((dateKeys.length > 0 ? dateKeys : Object.keys({ ...bookingsByDate, ...shiftsByDate }))
    .flatMap((dateKey) => (
      getRosterCoverageReviewItems(
        bookingsByDate[dateKey] || { dropoffs: [], pickups: [] },
        shiftsByDate[dateKey] || [],
      ).map((item) => ({
        ...item,
        date: dateKey,
        date_label: formatDateUK(dateKey),
      }))
    )))
)

const normaliseGateEventType = (eventType) => {
  if (eventType === 'drop_off') return 'dropoff'
  if (eventType === 'pick_up') return 'pickup'
  return eventType
}

export const getRosterCoverageReviewItemsFromGates = (gatesByDate = {}, dateKeys = []) => (
  sortRosterReviewItems((dateKeys.length > 0 ? dateKeys : Object.keys(gatesByDate).sort())
    .flatMap((dateKey) => {
      const gate = gatesByDate[dateKey]
      return (gate?.missing_events || []).map((event) => {
        const type = normaliseGateEventType(event.event_type)
        return {
          key: `missing-${event.booking_id}:${type}`,
          severity: 'warning',
          kind: 'missing-shift',
          message: `${bookingEventLabel(type)} ${event.booking_reference || `#${event.booking_id}`} is not linked to a shift.`,
          booking_reference: event.booking_reference,
          booking_id: event.booking_id,
          event_type: type,
          customer_name: event.customer_name || '',
          time: event.event_time,
          flight_number: event.flight_number,
          destination: event.destination,
          date: dateKey,
          date_label: formatDateUK(dateKey),
        }
      })
    }))
)

export const groupAutoOverlapReviewItems = (items = []) => {
  const groups = new Map()
  ;(items || []).forEach((item) => {
    if (item?.kind !== 'unassigned-linked-shift') return
    const shiftKey = item.shift_ids?.length
      ? [...item.shift_ids].sort((a, b) => String(a).localeCompare(String(b))).join(',')
      : (item.shift_times || []).join(',')
    const blockerKey = (item.blocking_shift_times || []).join(',')
    const key = `${item.date || ''}|${shiftKey}|${blockerKey}`
    if (!groups.has(key)) {
      groups.set(key, {
        key: `auto-overlap-${key}`,
        kind: 'unassigned-linked-shift',
        severity: 'critical',
        date: item.date,
        date_label: item.date_label,
        shift_ids: item.shift_ids || [],
        shift_times: item.shift_times || [],
        blocking_shift_times: item.blocking_shift_times || [],
        affected_items: [],
        affected_count: 0,
      })
    }
    const group = groups.get(key)
    group.affected_items.push(item)
    group.affected_count += 1
  })
  return [...groups.values()]
}

function RosterCalendar({
  token,
  isAdmin = false,
  employeeId = null,
  refreshTrigger = 0,
  renderBookingActions = null,
  defaultSourceFilter = 'manual',
  storageKey = 'rosterCalendar.source',
}) {
  // authFetch auto-attaches Bearer and clears auth state on 401 so a deleted
  // / expired session bounces the user to /login on the next render. The
  // existing `token` prop stays for callers that read it directly (e.g.
  // SignaturePad uploads); authFetch reads its token from AuthContext.
  const { authFetch } = useAuth()
  const [currentDate, setCurrentDate] = useState(new Date())
  const [shifts, setShifts] = useState([])
  // v3 admin source-filter toggle. Employees never see the toggle and always
  // get the default (Manual) — toggle UI is gated on isAdmin in the header.
  const [sourceFilter, setSourceFilter] = useState(() => {
    if (!isAdmin) return 'manual'
    try {
      const stored = typeof window !== 'undefined' ? window.localStorage.getItem(storageKey) : null
      if (stored === 'auto' || stored === 'manual' || stored === 'all') return stored
    } catch {}
    return defaultSourceFilter
  })
  const updateSourceFilter = useCallback((next) => {
    setSourceFilter(next)
    try { window.localStorage.setItem(storageKey, next) } catch {}
  }, [storageKey])
  const pastDaysStorageKey = `${storageKey}.showPastDays`
  const [showPastDays, setShowPastDays] = useState(() => {
    try {
      return typeof window !== 'undefined' && window.localStorage.getItem(pastDaysStorageKey) === 'true'
    } catch {
      return false
    }
  })
  const updateShowPastDays = useCallback((next) => {
    setShowPastDays(next)
    try { window.localStorage.setItem(pastDaysStorageKey, next ? 'true' : 'false') } catch {}
  }, [pastDaysStorageKey])
  // Teammates' shifts (view-only, employee mode only). Stripped shape from
  // /api/employee/team-shifts — no id, no staff_id, no shift_type.
  const [teamShifts, setTeamShifts] = useState([])
  const [teamShiftPopover, setTeamShiftPopover] = useState(null) // { initials, first_name, last_name, phone, date, end_date, start_time, end_time }
  const [bookings, setBookings] = useState([])
  const [employees, setEmployees] = useState([])
  const [shiftExceptions, setShiftExceptions] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedDate, setSelectedDate] = useState(null)
  const [showDetailModal, setShowDetailModal] = useState(false)
  const [successMessage, setSuccessMessage] = useState('')
  const [focusReview, setFocusReview] = useState(null) // { date, shiftId, bookingId }

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
  const [deletePreview, setDeletePreview] = useState(null)
  const [deletePreviewLoading, setDeletePreviewLoading] = useState(false)

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

  // v3 per-shift action modal state. Activated from the day-detail action
  // bar when exactly one shift is selected (Phase 2). Multi-select bulk
  // loops over these endpoints in Phase 3.
  const [duplicateModal, setDuplicateModal] = useState(null)  // { shift, mode, target_date, staff_ids, add_unassigned_jockey, add_unassigned_fleet }
  const [mergeModal, setMergeModal] = useState(null)          // { shift, neighbours, selectedNeighbourId }
  const [splitModal, setSplitModal] = useState(null)          // { shift, split_at_time }
  const [unassignModal, setUnassignModal] = useState(null)    // { shift }
  const [v3DeleteModal, setV3DeleteModal] = useState(null)    // { shift } — separate from per-card delete confirmation
  const [actionSubmitting, setActionSubmitting] = useState(false)
  const [actionError, setActionError] = useState('')
  // Phase 3 — bulk modals (multi-select). Each loops the Phase 2 single-shift
  // endpoint on the frontend so audit stays one-row-per-action and partial
  // failures are reported in a single banner without the server orchestrating.
  const [bulkDuplicateModal, setBulkDuplicateModal] = useState(null)  // { shifts, target_date }
  const [bulkUnassignModal, setBulkUnassignModal] = useState(null)    // { shifts }
  const [bulkDeleteModal, setBulkDeleteModal] = useState(null)        // { shifts }
  const [reviewGenerateGateByDate, setReviewGenerateGateByDate] = useState({})
  const [reviewGateRangeKey, setReviewGateRangeKey] = useState('')
  const [loadingReviewGenerateGate, setLoadingReviewGenerateGate] = useState(false)
  const [generatingRosterDate, setGeneratingRosterDate] = useState(null)

  // Monthly hours (for payroll)
  const [monthlyHours, setMonthlyHours] = useState(null)
  const [loadingMonthlyHours, setLoadingMonthlyHours] = useState(false)
  const [hoursExpanded, setHoursExpanded] = useState(false)  // Hours section collapsed by default
  const [expandedWeeks, setExpandedWeeks] = useState({})  // Track which weeks are expanded
  const [monthlyTotalsExpanded, setMonthlyTotalsExpanded] = useState(false)  // Monthly totals collapsed by default

  // Blocked dates state
  const [blockedDates, setBlockedDates] = useState([])
  // Daily occupancy/capacity maps for the visible month.
  // Drives the "Full" bar on at-cap days using the date-effective online cap.
  const [dailyOccupancy, setDailyOccupancy] = useState({})
  const [dailyCapacity, setDailyCapacity] = useState({})
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
  const [collapsedSections, setCollapsedSections] = useState(DEFAULT_COLLAPSED_SECTIONS)

  const toggleSection = (section) => {
    setCollapsedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }))
  }

  // Per-shift expand state. Default collapsed (empty set) so the shifts list
  // is a compact stack of headers until the user opens one.
  const [expandedShiftIds, setExpandedShiftIds] = useState(() => new Set())

  const toggleShiftExpanded = (shiftId) => {
    setExpandedShiftIds(prev => {
      const next = new Set(prev)
      if (next.has(shiftId)) next.delete(shiftId)
      else next.add(shiftId)
      return next
    })
  }

  // Fetch bookings
  const fetchBookings = useCallback(async () => {
    if (!token) return

    try {
      const endpoint = isAdmin ? '/api/admin/bookings' : '/api/employee/bookings'
      const response = await authFetch(`${API_URL}${endpoint}?include_cancelled=false`, {
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
      // v3 admin toggle drives the ?source= param. Employees stay on the
      // default (manual+planner, excludes auto) regardless of the prop.
      const sourceParam = isAdmin ? sourceParamFor(sourceFilter) : null
      if (sourceParam) {
        params.set('source', sourceParam)
      }

      const endpoint = isAdmin ? '/api/roster' : '/api/employee/shifts'
      const response = await authFetch(`${API_URL}${endpoint}?${params}`, {
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

  const fetchShiftExceptions = useCallback(async () => {
    if (!token || !isAdmin) {
      setShiftExceptions([])
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

      const response = await authFetch(`${API_URL}/api/roster/shift-exceptions?${params}`, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Cache-Control': 'no-cache',
        },
      })

      if (response.ok) {
        const data = await response.json()
        setShiftExceptions(Array.isArray(data) ? data : [])
      }
    } catch (err) {
      console.error('Failed to load shift exceptions:', err)
    }
  }, [token, currentDate, isAdmin])

  const fetchReviewGenerateGatesForMonth = useCallback(async () => {
    if (!token || !isAdmin) return

    const year = currentDate.getFullYear()
    const month = currentDate.getMonth()
    const startDate = new Date(year, month, 1)
    const endDate = new Date(year, month + 1, 0)
    const dateFrom = formatDateISO(startDate)
    const dateTo = formatDateISO(endDate)
    const rangeKey = `${dateFrom}:${dateTo}`

    try {
      const response = await authFetch(
        `${API_URL}/api/admin/roster/review-generate-gates?date_from=${dateFrom}&date_to=${dateTo}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
            'Cache-Control': 'no-cache',
          },
        },
      )

      if (response.ok) {
        const data = await response.json()
        const next = {}
        ;(data.gates || []).forEach((gate) => {
          if (gate?.date) next[gate.date] = gate
        })
        setReviewGenerateGateByDate(next)
        setReviewGateRangeKey(rangeKey)
      }
    } catch (err) {
      console.error('Failed to load roster review gates:', err)
    }
  }, [token, isAdmin, currentDate, authFetch])

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

      const response = await authFetch(`${API_URL}/api/employee/team-shifts?${params}`, {
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

      const response = await authFetch(endpoint, {
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

  // Fetch daily occupancy for the visible month. Public endpoint, no auth.
  const fetchDailyOccupancy = useCallback(async () => {
    try {
      const year = currentDate.getFullYear()
      const month = currentDate.getMonth()
      const startDate = new Date(year, month, 1)
      const endDate = new Date(year, month + 1, 0)
      const params = new URLSearchParams({
        date_from: formatDateISO(startDate),
        date_to: formatDateISO(endDate),
      })
      const response = await authFetch(`${API_URL}/api/capacity/daily?${params}`, {
        headers: { 'Cache-Control': 'no-cache' },
      })
      if (response.ok) {
        const data = await response.json()
        setDailyOccupancy(data.daily_occupancy || {})
        setDailyCapacity(data.daily_capacity || {})
      }
    } catch (err) {
      console.error('Failed to load daily occupancy:', err)
    }
  }, [currentDate])

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
      const response = await authFetch(`${API_URL}${endpoint}?${params}`, {
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

      const response = await authFetch(`${API_URL}/api/employee/unavailability?${params}`, {
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
      const response = await authFetch(`${API_URL}/api/employee/available-shifts`, {
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
      const response = await authFetch(`${API_URL}/api/employee/claim-shift/${shiftToClaim.id}`, {
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
      const response = await authFetch(`${API_URL}/api/employee/release-shift/${shiftToRelease.id}`, {
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
      await Promise.all([fetchBookings(), fetchShifts(), fetchShiftExceptions(), fetchReviewGenerateGatesForMonth(), fetchBlockedDates(), fetchDailyOccupancy(), fetchHolidays(), fetchAvailableShifts(), fetchUnavailabilities(), fetchTeamShifts()])
    } catch (err) {
      setError('Failed to load data')
    } finally {
      setLoading(false)
    }
  }, [fetchBookings, fetchShifts, fetchShiftExceptions, fetchReviewGenerateGatesForMonth, fetchBlockedDates, fetchDailyOccupancy, fetchHolidays, fetchAvailableShifts, fetchUnavailabilities, fetchTeamShifts])

  // Fetch all staff (admin only) - includes both admins and employees
  const fetchStaff = useCallback(async () => {
    if (!token || !isAdmin) return

    try {
      // Use /api/staff to get ALL users (admins + employees)
      const response = await authFetch(`${API_URL}/api/staff?is_active=true`, {
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
      // Hours panel mirrors the calendar grid's source filter. v3 toggle drives
      // both via the same state. Default 'manual' → no source param (existing payroll behaviour).
      const sourceParam = isAdmin ? sourceParamFor(sourceFilter) : null
      const sourceQs = sourceParam ? `&source=${encodeURIComponent(sourceParam)}` : ''
      const response = await authFetch(`${API_URL}${endpoint}?year=${year}&month=${month}${sourceQs}`, {
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
        setFocusReview(null)
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [showDetailModal])

  useEffect(() => {
    if (!focusReview || !showDetailModal || selectedDate !== focusReview.date) return
    if (!focusReview.shiftId) return
    const hasShift = shifts.some((shift) => shift.id === focusReview.shiftId)
    if (!hasShift) return

    setCollapsedSections(prev => ({ ...prev, shifts: false }))
    setExpandedShiftIds(prev => new Set([...prev, focusReview.shiftId]))

    window.setTimeout(() => {
      const target = document.querySelector(`[data-shift-id="${focusReview.shiftId}"]`)
      if (target) {
        target.scrollIntoView({ block: 'center', behavior: 'smooth' })
      }
    }, 80)
  }, [focusReview, showDetailModal, selectedDate, shifts])

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
      const response = await authFetch(`${API_URL}/api/roster/bookings-for-date?date=${isoDate}`, {
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
          const response2 = await authFetch(`${API_URL}/api/roster/bookings-for-date?date=${isoAdditionalDate}`, {
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

  const fetchReviewGenerateGate = useCallback(async (dateKey) => {
    if (!token || !isAdmin || !dateKey) return null

    setLoadingReviewGenerateGate(true)
    try {
      const response = await authFetch(`${API_URL}/api/admin/roster/review-generate-gate?date=${dateKey}`, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Cache-Control': 'no-cache',
        },
      })
      if (!response.ok) return null
      const data = await response.json()
      setReviewGenerateGateByDate((prev) => ({
        ...prev,
        [dateKey]: data,
      }))
      return data
    } catch (err) {
      console.error('Failed to load roster review gate:', err)
      return null
    } finally {
      setLoadingReviewGenerateGate(false)
    }
  }, [token, isAdmin, authFetch])

  const handleGenerateRosterForSelectedDate = async () => {
    if (!selectedDate || !token || !isAdmin) return

    const dateKey = selectedDate
    setGeneratingRosterDate(dateKey)
    setError('')
    try {
      const response = await authFetch(`${API_URL}/api/admin/roster/generate-date`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ date: dateKey }),
      })
      const data = await response.json().catch(() => ({}))
      if (response.ok) {
        if (data.after_gate) {
          setReviewGenerateGateByDate((prev) => ({
            ...prev,
            [dateKey]: data.after_gate,
          }))
        }
        await Promise.all([fetchBookings(), fetchShifts(), fetchShiftExceptions(), fetchReviewGenerateGatesForMonth()])
        setSuccessMessage(`Roster generated for ${formatDateUK(dateKey)}`)
        setTimeout(() => setSuccessMessage(''), 3000)
      } else {
        const detail = data.detail
        if (detail?.gate) {
          setReviewGenerateGateByDate((prev) => ({
            ...prev,
            [dateKey]: detail.gate,
          }))
        }
        setError(detail?.message || detail || 'Failed to generate roster')
        setTimeout(() => setError(''), 5000)
      }
    } catch (err) {
      setError('Network error generating roster')
      setTimeout(() => setError(''), 5000)
    } finally {
      setGeneratingRosterDate(null)
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

    // v3: when the toggle is "All" the day cell mixes manual + auto. Sort by
    // source first (manual / planner above auto) so admins see committed work
    // grouped at the top and auto-roster output as a clearly separate block;
    // then by operational start time, then by id ascending — so duplicated
    // shifts (same start/end as source, created later → higher id) sit
    // immediately under their source. When the toggle is "Manual" or "Auto"
    // only, this collapses to time-then-id.
    //
    // Sort by operational time: for re-bucketed overnight shifts (date=D,
    // end_date=D+1, start_time < end_time — the entire shift sits after
    // midnight on D+1) we offset the sort key by 24h so they land at the
    // bottom of D's list, where the work actually happens chronologically.
    // Without this, a 00:20-01:20 tail of Friday-evening work would sort
    // ahead of Friday's afternoon 13:10 shift.
    const sourceOrder = (s) => (s.created_source === 'auto' ? 1 : 0)
    Object.keys(grouped).forEach((date) => {
      grouped[date].sort((a, b) => {
        const so = sourceOrder(a) - sourceOrder(b)
        if (so !== 0) return so
        const t = shiftSortMinutes(a) - shiftSortMinutes(b)
        if (t !== 0) return t
        return (a.id || 0) - (b.id || 0)
      })
    })

    return grouped
  }, [shifts])

  const shiftExceptionsByDate = useMemo(() => {
    const grouped = {}
    ;(shiftExceptions || []).forEach((exception) => {
      if (!exception?.date) return
      if (!grouped[exception.date]) grouped[exception.date] = []
      grouped[exception.date].push(exception)
    })
    Object.keys(grouped).forEach((date) => {
      grouped[date].sort((a, b) => {
        const timeCompare = String(a.event_time || '').localeCompare(String(b.event_time || ''))
        if (timeCompare !== 0) return timeCompare
        return String(a.booking_reference || '').localeCompare(String(b.booking_reference || ''))
      })
    })
    return grouped
  }, [shiftExceptions])

  // Group teammates' view-only shifts by date (employee mode only).
  const teamShiftsByDate = useMemo(() => {
    const grouped = {}
    teamShifts.forEach((shift) => {
      const isOvernight = shift.end_date && shift.end_date !== shift.date
      const startKey = shift.date
      if (!grouped[startKey]) grouped[startKey] = []
      grouped[startKey].push({ ...shift, isOvernight })
    })
    // Same operational sort as shiftsByDate above.
    Object.keys(grouped).forEach((d) => {
      grouped[d].sort((a, b) => shiftSortMinutes(a) - shiftSortMinutes(b))
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

  // Occupancy for the day (cars parked, dropoff_date <= D <= pickup_date).
  // Returns the count from /api/capacity/daily — 0 if missing.
  const getOccupancyForDay = (day) => {
    if (!day) return 0
    return dailyOccupancy[getDateKey(day)] || 0
  }

  const getOnlineCapacityForDay = (day) => (
    getOnlineCapacityForDate(day ? new Date(currentDate.getFullYear(), currentDate.getMonth(), day) : null, dailyCapacity, DEFAULT_ONLINE_CAPACITY)
  )

  // Is today?
  const isToday = (day) => {
    if (!day) return false
    return getDateKey(day) === getUKDateKey()
  }

  const resetDetailDisclosure = () => {
    setCollapsedSections({ ...DEFAULT_COLLAPSED_SECTIONS })
    setExpandedShiftIds(new Set())
    setSelectedShiftIds([])
    setFocusReview(null)
  }

  const closeAdminActionModals = () => {
    setShowShiftModal(false)
    setEditingShift(null)
    setDateBookings([])
    setDuplicateMode(false)
    setAdditionalStaffIds([])
    setShowDeleteModal(false)
    setShiftToDelete(null)
    setShowBulkEditModal(false)
    setDuplicateModal(null)
    setMergeModal(null)
    setSplitModal(null)
    setUnassignModal(null)
    setV3DeleteModal(null)
    setBulkDuplicateModal(null)
    setBulkUnassignModal(null)
    setBulkDeleteModal(null)
    setActionError('')
  }

  // Handle date selection - always open a fresh collapsed day detail.
  const handleDateClick = (day) => {
    if (!day) return
    const dateKey = getDateKey(day)
    closeAdminActionModals()
    resetDetailDisclosure()
    setSelectedDate(dateKey)
    setShowDetailModal(true)
  }

  const openShiftExceptionReview = (exception) => {
    if (!exception?.date) return
    closeAdminActionModals()
    const suggestedShiftId = exception.suggested_shift?.id || null
    if (isAdmin && suggestedShiftId && sourceFilter !== 'all') {
      const visible = shifts.some((shift) => shift.id === suggestedShiftId)
      if (!visible) updateSourceFilter('all')
    }
    setSelectedDate(exception.date)
    setShowDetailModal(true)
    setCollapsedSections(prev => ({
      ...prev,
      shifts: false,
      dropoffs: exception.event_type === 'dropoff' ? false : prev.dropoffs,
      pickups: exception.event_type === 'pickup' ? false : prev.pickups,
    }))
    if (suggestedShiftId) {
      setExpandedShiftIds(prev => new Set([...prev, suggestedShiftId]))
    }
    setFocusReview({
      date: exception.date,
      shiftId: suggestedShiftId,
      bookingId: exception.booking_id,
    })
  }

  const openDetailForDate = (dateKey) => {
    if (!dateKey) return
    setSelectedDate(dateKey)
    setShowDetailModal(true)
  }

  // Close detail modal handler
  const closeDetailModal = () => {
    setShowDetailModal(false)
    setSelectedDate(null)
    resetDetailDisclosure()
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

        const response = await authFetch(`${API_URL}/api/roster/${editingShift.id}`, {
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
          fetchShiftExceptions()
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
            const response = await authFetch(`${API_URL}/api/roster`, {
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
          fetchShiftExceptions()
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

  const loadDeletePreview = async (shiftId) => {
    setDeletePreview(null)
    setDeletePreviewLoading(true)
    try {
      const r = await authFetch(`${API_URL}/api/roster/${shiftId}/delete-preview`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (r.ok) {
        setDeletePreview(await r.json())
      }
    } catch {
      setDeletePreview(null)
    } finally {
      setDeletePreviewLoading(false)
    }
  }

  const confirmDeleteShift = (shift) => {
    setShiftToDelete(shift)
    setShowDeleteModal(true)
    loadDeletePreview(shift.id)
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
            const response = await authFetch(`${API_URL}/api/roster/${shiftId}`, {
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
          fetchShiftExceptions()
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
            const response = await authFetch(`${API_URL}/api/roster/${shiftId}`, {
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
          fetchShiftExceptions()
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

  // ---------------------------------------------------------------------------
  // v3 per-shift action handlers (Phase 2 — locked 2026-05-04). Each modal
  // hits the corresponding /api/roster/{id}/{action} endpoint, then closes
  // the modal, refreshes shifts, and clears the selection on success.
  // ---------------------------------------------------------------------------

  const refreshAfterAction = () => {
    fetchShifts()
    fetchShiftExceptions()
    fetchMonthlyHours()
    clearShiftSelection()
  }

  const openDuplicateModal = (shift) => {
    setActionError('')
    setDuplicateModal({
      shift,
      mode: 'date_copy',
      // Prefill with the source's own date — most duplicates stay on the
      // same day (admin adding another jockey to the same shift). Admin
      // can edit if they actually want to copy to a different day.
      target_date: shift.date ? formatDateUK(shift.date) : '',
      staff_ids: [],
      add_unassigned_jockey: false,
      add_unassigned_fleet: false,
    })
  }

  const submitDuplicate = async () => {
    if (!duplicateModal) return
    const { shift, mode, target_date, staff_ids, add_unassigned_jockey, add_unassigned_fleet } = duplicateModal
    setActionError('')
    let body = {}
    if (mode === 'date_copy') {
      if (!target_date || target_date.length !== 10) {
        setActionError('Pick a target date.')
        return
      }
      body.target_date = ukToISO(target_date)
    } else {
      // staff_fanout
      if (staff_ids.length === 0 && !add_unassigned_jockey && !add_unassigned_fleet) {
        setActionError('Pick at least one target staff or an unassigned slot.')
        return
      }
      if (staff_ids.length > 0) body.staff_ids = staff_ids
      if (add_unassigned_jockey) body.add_unassigned_jockey = true
      if (add_unassigned_fleet) body.add_unassigned_fleet = true
    }
    setActionSubmitting(true)
    try {
      const r = await authFetch(`${API_URL}/api/roster/${shift.id}/duplicate`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!r.ok) {
        const err = await r.json().catch(() => ({}))
        setActionError(err.detail || `Failed (status ${r.status})`)
        return
      }
      const created = await r.json()
      setSuccessMessage(`Duplicated → ${created.length} new shift${created.length === 1 ? '' : 's'}`)
      setTimeout(() => setSuccessMessage(''), 3000)
      setDuplicateModal(null)
      refreshAfterAction()
    } catch (err) {
      setActionError('Network error')
    } finally {
      setActionSubmitting(false)
    }
  }

  // Find the immediate-previous and immediate-next shifts on the same
  // day for the Merge picker. Sorted by start_time; "previous" is the
  // largest start_time strictly before this shift's, "next" is the
  // smallest strictly after. No gap or overlap restriction (the backend
  // unions the windows). Skips siblings with the same start_time.
  const findMergeNeighbours = (shift) => {
    const dayShifts = (shiftsByDate[selectedDate] || []).filter((s) => s.id !== shift.id)
    const shiftStart = formatTime(shift.start_time)
    const before = dayShifts
      .filter((s) => formatTime(s.start_time) < shiftStart)
      .sort((a, b) => formatTime(b.start_time).localeCompare(formatTime(a.start_time)))
    const after = dayShifts
      .filter((s) => formatTime(s.start_time) > shiftStart)
      .sort((a, b) => formatTime(a.start_time).localeCompare(formatTime(b.start_time)))
    const neighbours = []
    if (before.length > 0) neighbours.push({ ...before[0], _direction: 'previous' })
    if (after.length > 0) neighbours.push({ ...after[0], _direction: 'next' })
    return neighbours
  }

  const openMergeModal = (shift) => {
    setActionError('')
    const neighbours = findMergeNeighbours(shift)
    setMergeModal({
      shift,
      neighbours,
      selectedNeighbourId: neighbours[0]?.id || null,
      // Staff conflict resolution. Initialised to the source shift's
      // staff_id so an admin who doesn't touch the picker still gets a
      // sane default. Only used when both shifts are assigned to
      // different drivers (UI gates the visibility on that).
      survivorStaffId: shift.staff_id != null ? String(shift.staff_id) : '',
    })
  }

  const submitMerge = async () => {
    if (!mergeModal || !mergeModal.selectedNeighbourId) {
      setActionError('Pick a neighbour to merge with.')
      return
    }
    const picked = mergeModal.neighbours.find((n) => n.id === mergeModal.selectedNeighbourId)
    const sourceStaff = mergeModal.shift.staff_id
    const pickedStaff = picked?.staff_id
    const conflict = sourceStaff != null && pickedStaff != null && sourceStaff !== pickedStaff
    // Only attach staff fields when there's an actual conflict — keeps
    // the request body identical to the old shape in the no-conflict
    // case so we don't churn any other callers.
    const body = { other_shift_id: mergeModal.selectedNeighbourId }
    if (conflict) {
      body.staff_choice_made = true
      body.survivor_staff_id = mergeModal.survivorStaffId === ''
        ? null
        : Number(mergeModal.survivorStaffId)
    }
    setActionSubmitting(true)
    try {
      const r = await authFetch(`${API_URL}/api/roster/${mergeModal.shift.id}/merge`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!r.ok) {
        const err = await r.json().catch(() => ({}))
        setActionError(err.detail || `Failed (status ${r.status})`)
        return
      }
      setSuccessMessage('Shifts merged')
      setTimeout(() => setSuccessMessage(''), 3000)
      setMergeModal(null)
      refreshAfterAction()
    } catch (err) {
      setActionError('Network error')
    } finally {
      setActionSubmitting(false)
    }
  }

  const openSplitModal = (shift) => {
    setActionError('')
    setSplitModal({ shift, split_at_time: '' })
  }

  const submitSplit = async () => {
    if (!splitModal || !splitModal.split_at_time || splitModal.split_at_time.length !== 5) {
      setActionError('Enter a split time (HH:MM).')
      return
    }
    setActionSubmitting(true)
    try {
      const r = await authFetch(`${API_URL}/api/roster/${splitModal.shift.id}/split`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ split_at_time: splitModal.split_at_time }),
      })
      if (!r.ok) {
        const err = await r.json().catch(() => ({}))
        setActionError(err.detail || `Failed (status ${r.status})`)
        return
      }
      setSuccessMessage('Shift split')
      setTimeout(() => setSuccessMessage(''), 3000)
      setSplitModal(null)
      refreshAfterAction()
    } catch (err) {
      setActionError('Network error')
    } finally {
      setActionSubmitting(false)
    }
  }

  const openUnassignModal = (shift) => {
    setActionError('')
    setUnassignModal({ shift })
  }

  const submitUnassign = async () => {
    if (!unassignModal) return
    setActionSubmitting(true)
    try {
      const r = await authFetch(`${API_URL}/api/roster/${unassignModal.shift.id}/unassign`, {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!r.ok) {
        const err = await r.json().catch(() => ({}))
        setActionError(err.detail || `Failed (status ${r.status})`)
        return
      }
      setSuccessMessage('Shift unassigned')
      setTimeout(() => setSuccessMessage(''), 3000)
      setUnassignModal(null)
      refreshAfterAction()
    } catch (err) {
      setActionError('Network error')
    } finally {
      setActionSubmitting(false)
    }
  }

  const openV3DeleteModal = (shift) => {
    setActionError('')
    setV3DeleteModal({ shift })
    loadDeletePreview(shift.id)
  }

  const submitV3Delete = async () => {
    if (!v3DeleteModal) return
    setActionSubmitting(true)
    try {
      const r = await authFetch(`${API_URL}/api/roster/${v3DeleteModal.shift.id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!r.ok) {
        const err = await r.json().catch(() => ({}))
        setActionError(err.detail || `Failed (status ${r.status})`)
        return
      }
      const body = await r.json().catch(() => ({}))
      setSuccessMessage(body.message || 'Shift deleted')
      setTimeout(() => setSuccessMessage(''), 3000)
      setV3DeleteModal(null)
      setDeletePreview(null)
      refreshAfterAction()
    } catch (err) {
      setActionError('Network error')
    } finally {
      setActionSubmitting(false)
    }
  }

  // ---------------------------------------------------------------------------
  // Phase 3 bulk handlers — loop Phase 2 endpoints. Per spec, multi-select
  // exposes only Duplicate / Unassign / Delete (Merge needs adjacency, Split
  // is single-shift). On partial failure, the toast summarises and the error
  // banner lists per-shift reasons.
  // ---------------------------------------------------------------------------

  const summariseBulkResult = (label, successCount, total, errors) => {
    if (errors.length === 0) {
      setSuccessMessage(`${label} ${successCount} of ${total} shifts`)
      setTimeout(() => setSuccessMessage(''), 3500)
      setActionError('')
    } else {
      setSuccessMessage(`${label} ${successCount} of ${total} — ${errors.length} failed`)
      setTimeout(() => setSuccessMessage(''), 5000)
      setActionError(errors.join('; '))
    }
  }

  const openBulkDuplicateModal = () => {
    setActionError('')
    const shifts = selectedDateShifts.filter((s) => selectedShiftIds.includes(s.id))
    // All selected shifts share the same calendar day (selection happens
    // inside one day-detail modal), so prefill the target date with that
    // day. Most duplicates stay on the same day (adding staff to existing
    // shifts) — admin edits this only when actually moving copies to
    // another date.
    const sourceDateUK = (selectedDate
      ? formatDateUK(selectedDate)
      : (shifts[0]?.date ? formatDateUK(shifts[0].date) : ''))
    setBulkDuplicateModal({
      shifts,
      target_date: sourceDateUK,
      // Optional staff fanout for bulk-staff-add (Phase 4 unblocked
      // 2026-05-05). When all empty → pure date copy preserving each
      // shift's source staff. When any picked → each source shift × each
      // picked staff = N×M copies on target_date.
      staff_ids: [],
      add_unassigned_jockey: false,
      add_unassigned_fleet: false,
    })
  }

  const submitBulkDuplicate = async () => {
    if (!bulkDuplicateModal) return
    const { shifts, target_date, staff_ids, add_unassigned_jockey, add_unassigned_fleet } = bulkDuplicateModal
    if (!target_date || target_date.length !== 10) {
      setActionError('Pick a target date (DD/MM/YYYY).')
      return
    }
    const isoDate = ukToISO(target_date)
    const hasStaffPick = staff_ids.length > 0 || add_unassigned_jockey || add_unassigned_fleet
    setActionSubmitting(true)
    let successCount = 0
    const errors = []
    for (const s of shifts) {
      const body = { target_date: isoDate }
      if (hasStaffPick) {
        if (staff_ids.length > 0) body.staff_ids = staff_ids
        if (add_unassigned_jockey) body.add_unassigned_jockey = true
        if (add_unassigned_fleet) body.add_unassigned_fleet = true
      }
      try {
        const r = await authFetch(`${API_URL}/api/roster/${s.id}/duplicate`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
        if (r.ok) {
          successCount++
        } else {
          const err = await r.json().catch(() => ({}))
          errors.push(`Shift ${s.id}: ${err.detail || `status ${r.status}`}`)
        }
      } catch (err) {
        errors.push(`Shift ${s.id}: network error`)
      }
    }
    setActionSubmitting(false)
    summariseBulkResult('Duplicated', successCount, shifts.length, errors)
    if (successCount > 0) {
      setBulkDuplicateModal(null)
      refreshAfterAction()
    }
  }

  const openBulkUnassignModal = () => {
    setActionError('')
    const shifts = selectedDateShifts.filter((s) => selectedShiftIds.includes(s.id))
    setBulkUnassignModal({ shifts })
  }

  const submitBulkUnassign = async () => {
    if (!bulkUnassignModal) return
    const { shifts } = bulkUnassignModal
    setActionSubmitting(true)
    let successCount = 0
    const errors = []
    for (const s of shifts) {
      try {
        const r = await authFetch(`${API_URL}/api/roster/${s.id}/unassign`, {
          method: 'PATCH',
          headers: { Authorization: `Bearer ${token}` },
        })
        if (r.ok) {
          successCount++
        } else {
          const err = await r.json().catch(() => ({}))
          errors.push(`Shift ${s.id}: ${err.detail || `status ${r.status}`}`)
        }
      } catch (err) {
        errors.push(`Shift ${s.id}: network error`)
      }
    }
    setActionSubmitting(false)
    summariseBulkResult('Unassigned', successCount, shifts.length, errors)
    if (successCount > 0) {
      setBulkUnassignModal(null)
      refreshAfterAction()
    }
  }

  const openBulkDeleteModal = () => {
    setActionError('')
    const shifts = selectedDateShifts.filter((s) => selectedShiftIds.includes(s.id))
    setBulkDeleteModal({ shifts })
  }

  const submitBulkDelete = async () => {
    if (!bulkDeleteModal) return
    const { shifts } = bulkDeleteModal
    setActionSubmitting(true)
    let successCount = 0
    const errors = []
    for (const s of shifts) {
      try {
        const r = await authFetch(`${API_URL}/api/roster/${s.id}`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${token}` },
        })
        if (r.ok) {
          successCount++
        } else {
          const err = await r.json().catch(() => ({}))
          errors.push(`Shift ${s.id}: ${err.detail || `status ${r.status}`}`)
        }
      } catch (err) {
        errors.push(`Shift ${s.id}: network error`)
      }
    }
    setActionSubmitting(false)
    summariseBulkResult('Deleted', successCount, shifts.length, errors)
    if (successCount > 0) {
      setBulkDeleteModal(null)
      refreshAfterAction()
    }
  }

  const deleteShift = async () => {
    if (!shiftToDelete) return

    setDeletingShift(true)
    setError('')

    try {
      const response = await authFetch(`${API_URL}/api/roster/${shiftToDelete.id}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${token}`,
          'Cache-Control': 'no-cache',
        },
      })

      if (response.ok) {
        const body = await response.json().catch(() => ({}))
        setSuccessMessage(body.message || 'Shift deleted')
        setTimeout(() => setSuccessMessage(''), 3000)
        setShowDeleteModal(false)
        setShiftToDelete(null)
        setDeletePreview(null)
        fetchShifts()
        fetchShiftExceptions()
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
      const response = await authFetch(
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

      const response = await authFetch(url, {
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
      const response = await authFetch(`${API_URL}/api/admin/blocked-time-slots/${slotId}`, {
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

      const response = await authFetch(url, {
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
      const response = await authFetch(`${API_URL}/api/admin/blocked-dates/${blockedDateId}`, {
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

      const response = await authFetch(url, {
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
      const response = await authFetch(`${API_URL}/api/holidays/${holidayId}`, {
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

      const response = await authFetch(`${API_URL}/api/employee/unavailability?${params}`, {
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
      const response = await authFetch(`${API_URL}/api/employee/unavailability/${unavailId}`, {
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
  const monthStartKey = formatDateISO(new Date(currentDate.getFullYear(), currentDate.getMonth(), 1))
  const monthEndKey = formatDateISO(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0))
  const currentReviewGateRangeKey = `${monthStartKey}:${monthEndKey}`
  const backendReviewGatesLoaded = reviewGateRangeKey === currentReviewGateRangeKey

  // Selected date data
  const selectedDateBookings = selectedDate ? (bookingsByDate[selectedDate] || { dropoffs: [], pickups: [] }) : { dropoffs: [], pickups: [] }
  const selectedDateShifts = selectedDate ? (shiftsByDate[selectedDate] || []) : []
  const selectedDateReviewItemsFromBackend = (
    backendReviewGatesLoaded && selectedDate
      ? getRosterCoverageReviewItemsFromGates(reviewGenerateGateByDate, [selectedDate])
      : []
  )
  const selectedDateReviewItems = selectedDateReviewItemsFromBackend
  const selectedMissingShiftReviewItems = selectedDateReviewItems.filter((item) => item.kind === 'missing-shift')
  const selectedReviewIssueCount = selectedMissingShiftReviewItems.length
  const selectedAffectedBookingEventCount = selectedMissingShiftReviewItems.length
  const selectedReviewGenerateGate = selectedDate ? reviewGenerateGateByDate[selectedDate] : null
  const canGenerateSelectedDateRoster = canShowRosterGenerateCta({
    isAdmin,
    selectedDate,
    reviewIssueCount: selectedReviewIssueCount,
    gate: selectedReviewGenerateGate,
  })
  const selectedDateHolidays = selectedDate ? getHolidaysForDate(selectedDate) : []
  const selectedDateShiftExceptions = selectedDate ? (shiftExceptionsByDate[selectedDate] || []) : []
  const visibleDateKeys = calendarData.weeks
    .flat()
    .filter(Boolean)
    .map((day) => getDateKey(day))
  const hasPastVisibleDays = visibleDateKeys.some((dateKey) => isPastDateKeyUK(dateKey))
  const currentAndFutureVisibleDateKeys = currentAndFutureDateKeysForUK(visibleDateKeys)
  const reviewDateKeys = showPastDays ? visibleDateKeys : currentAndFutureVisibleDateKeys
  const heatmapDateKeys = currentAndFutureDateKeysForUK(visibleDateKeys)
  const calendarDemandItems = getRosterDemandByDate(bookingsByDate, heatmapDateKeys)
  const calendarDemandTotal = calendarDemandItems.reduce((total, item) => total + item.total, 0)
  const calendarReviewItems = backendReviewGatesLoaded
    ? getRosterCoverageReviewItemsFromGates(reviewGenerateGateByDate, reviewDateKeys)
    : []
  const missingShiftReviewItems = calendarReviewItems.filter((item) => item.kind === 'missing-shift')
  const calendarReviewIssueCount = missingShiftReviewItems.length
  const calendarAffectedBookingEventCount = missingShiftReviewItems.length

  useEffect(() => {
    if (!isAdmin || !selectedDate || selectedReviewIssueCount <= 0) return
    fetchReviewGenerateGate(selectedDate)
  }, [isAdmin, selectedDate, selectedReviewIssueCount, fetchReviewGenerateGate])

  const renderCalendarHeader = (position = 'top') => (
    <div className={`roster-calendar-header roster-calendar-header-${position}`}>
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
        {isAdmin && (
          <div className="rc-source-toggle" role="group" aria-label={`Filter shifts by source (${position})`}>
            {['all', 'auto', 'manual'].map((opt) => (
              <button
                key={opt}
                type="button"
                className={`rc-source-toggle-btn ${sourceFilter === opt ? 'active' : ''}`}
                onClick={() => updateSourceFilter(opt)}
                aria-pressed={sourceFilter === opt}
              >
                {opt[0].toUpperCase() + opt.slice(1)}
              </button>
            ))}
          </div>
        )}
        <button className="calendar-today-btn" onClick={goToToday}>
          Today
        </button>
        {hasPastVisibleDays && (
          <button
            type="button"
            className={`calendar-past-toggle ${showPastDays ? 'active' : ''}`}
            onClick={() => updateShowPastDays(!showPastDays)}
            aria-pressed={showPastDays}
          >
            {showPastDays ? 'Hide past days' : 'Show past days'}
          </button>
        )}
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
  )

  return (
    <div className="roster-calendar">
      {/* Header */}
      {renderCalendarHeader('top')}

      {/* Messages */}
      {error && <div className="roster-error">{error}</div>}
      {successMessage && <div className="roster-success">{successMessage}</div>}

      {isAdmin && calendarReviewIssueCount > 0 && (
        <div className="roster-review-banner roster-review-banner-calendar" role="alert">
          <div className="roster-review-banner-header">
            <span className="roster-review-icon" aria-hidden="true">⚠️</span>
            <div>
              <strong>Roster review needed</strong>
              <p>
                {calendarReviewIssueCount} roster coverage issue{calendarReviewIssueCount === 1 ? '' : 's'} affecting {calendarAffectedBookingEventCount} booking event{calendarAffectedBookingEventCount === 1 ? '' : 's'}.
              </p>
            </div>
          </div>
          <div className="roster-review-scroll">
            {missingShiftReviewItems.length > 0 && (
              <section className="roster-review-group">
                <h4>Not linked to a shift</h4>
                <ul className="roster-review-list">
                  {missingShiftReviewItems.map((item) => (
                    <li key={`${item.date}-${item.key}`} className={`roster-review-item roster-review-${item.kind}`}>
                      <span className="roster-review-message">{item.date_label} · {item.message}</span>
                      <span className="roster-review-meta">
                        {[item.time && formatTime(item.time), item.customer_name, item.flight_number, item.destination]
                          .filter(Boolean)
                          .join(' · ')}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        </div>
      )}

      {isAdmin && calendarDemandItems.length > 0 && (
        <section className="roster-demand-heatmap" aria-label="Roster demand heatmap">
          <div className="roster-demand-heatmap-header">
            <h3>Demand</h3>
            <span className="roster-demand-heatmap-total">
              {calendarDemandTotal} event{calendarDemandTotal === 1 ? '' : 's'}
            </span>
          </div>
          <div className="roster-demand-legend">
            {ROSTER_DEMAND_BUCKETS.map((bucket) => (
              <span key={bucket.key} className="roster-demand-legend-item">
                <span
                  className={`roster-demand-legend-dot roster-demand-bar-${bucket.key}`}
                  aria-hidden="true"
                />
                {bucket.name}
              </span>
            ))}
          </div>
          <div className="roster-demand-heatmap-scroll">
            {calendarDemandItems.map((item) => (
              <button
                type="button"
                key={item.date}
                className={`roster-demand-day demand-level-${item.level}`}
                onClick={() => openDetailForDate(item.date)}
                title={`${formatDateUK(item.date)} - ${item.total} booking event${item.total === 1 ? '' : 's'}: ${ROSTER_DEMAND_BUCKETS.map((bucket) => `${bucket.name} ${item[bucket.key] || 0}`).join(', ')}`}
              >
                <span className="roster-demand-day-top">
                  <span className="roster-demand-date">{item.dayLabel}</span>
                  <span className="roster-demand-total">{item.total}</span>
                </span>
                <span className="roster-demand-bars">
                  {ROSTER_DEMAND_BUCKETS.map((bucket) => (
                    <span key={bucket.key} className="roster-demand-bar-group">
                      <span
                        className={`roster-demand-bar roster-demand-bar-${bucket.key}`}
                        style={{
                          '--demand-height': `${Math.round(((item[bucket.key] || 0) / item.maxBucket) * 22) + 2}px`,
                        }}
                        aria-hidden="true"
                      />
                      <span className="roster-demand-count" aria-label={`${bucket.name}: ${item[bucket.key] || 0}`}>
                        {item[bucket.key] || 0}
                      </span>
                    </span>
                  ))}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

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
                const dayShiftExceptions = dateKey ? (shiftExceptionsByDate[dateKey] || []) : []
                const isPastDay = isPastDateKeyUK(dateKey)
                const hasActiveOvernightShift = isPastDay && dayHasActiveOvernightShift(dateKey, dayShifts, dayTeamShifts)
                const shouldCompactPastDay = isPastDay && !showPastDays && !hasActiveOvernightShift
                const showDayContent = showPastDays || !isPastDay || hasActiveOvernightShift
                const blockedInfo = getBlockedInfoForDay(day)
                const dayOccupancy = getOccupancyForDay(day)
                const dayOnlineCapacity = getOnlineCapacityForDay(day)
                const isAtCap = dayOccupancy >= dayOnlineCapacity
                const dayHolidays = dateKey ? getHolidaysForDate(dateKey) : []
                const hasDropoffs = dayBookings.dropoffs.length > 0
                const hasPickups = dayBookings.pickups.length > 0
                const hasShifts = dayShifts.length > 0
                const hasTeamShifts = dayTeamShifts.length > 0
                const hasHolidays = dayHolidays.length > 0
                const hasShiftExceptions = dayShiftExceptions.length > 0
                const hasContent = hasDropoffs || hasPickups || hasShifts || hasTeamShifts || blockedInfo || hasHolidays || isAtCap || hasShiftExceptions

                return (
                  <div
                    key={dayIndex}
                    className={`calendar-day ${day ? '' : 'empty'} ${isToday(day) ? 'today' : ''} ${
                      selectedDate === dateKey ? 'selected' : ''
                    } ${hasContent ? 'has-content' : ''} ${isPastDay ? 'past-day' : ''} ${shouldCompactPastDay ? 'past-day-compact' : ''} ${blockedInfo ? 'blocked' : ''} ${isAtCap && !blockedInfo ? 'at-cap' : ''} ${hasShiftExceptions ? 'has-shift-exceptions' : ''}`}
                    onClick={() => handleDateClick(day)}
                  >
                    {day && (
                      <>
                        <span className="day-number">{day}</span>
                        {shouldCompactPastDay && (
                          <div className="day-content day-content-compact">
                            <div className="day-badge badge-past">Past</div>
                          </div>
                        )}
                        {showDayContent && (
                        <div className="day-content">
                          {/* Blocked date indicator (manual) */}
                          {blockedInfo && (
                            <div className="day-badge badge-blocked" title={blockedInfo.reason || 'Blocked'}>
                              🚫 {blockedInfo.time_slots && blockedInfo.time_slots.length > 0
                                ? `${blockedInfo.time_slots.length} slot${blockedInfo.time_slots.length > 1 ? 's' : ''}`
                                : (blockedInfo.block_dropoffs && blockedInfo.block_pickups ? 'Closed' :
                                    blockedInfo.block_dropoffs ? 'No Drop-offs' : 'No Pick-ups')}
                            </div>
                          )}
                          {/* At-capacity indicator (auto — driven by daily occupancy >= online cap). */}
                          {/* Shown only when not already manually blocked, since manual block trumps cap visually. */}
                          {!blockedInfo && isAtCap && (
                            <div className="day-badge badge-at-cap" title={`Full: ${dayOccupancy}/${dayOnlineCapacity} online spaces parked`}>
                              ⛔ Full ({dayOccupancy})
                            </div>
                          )}
                          {hasShiftExceptions && (
                            <div
                              className="day-badge badge-shift-exception"
                              title={`${dayShiftExceptions.length} booking${dayShiftExceptions.length === 1 ? '' : 's'} need shift review`}
                              onClick={(e) => {
                                e.stopPropagation()
                                openShiftExceptionReview(dayShiftExceptions[0])
                              }}
                            >
                              Review {dayShiftExceptions.length}
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
                          {/* Secondary car park count: qualifying bookings active on this day */}
                          {(() => {
                            const secondaryCount = [...dayBookings.dropoffs, ...dayBookings.pickups]
                              .filter(b => b.secondary_carpark?.qualifies).length
                            return secondaryCount > 0 ? (
                              <div className="day-badge badge-carpark" title="Bookings qualifying for the secondary car park (09:00–21:00 rule)">
                                P2 {secondaryCount}
                              </div>
                            ) : null
                          })()}
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
                          {hasShifts && dayShifts.map((shift, idx) => {
                            const autoShapeState = getAutoShiftShapeState(shift)
                            return (
                              <div
                                key={`${shift.id}-${shift.shiftPart || 'full'}`}
                                className={`day-shift-badge ${shift.isOvernight ? 'overnight' : ''} ${shift.shiftPart === 'end' ? 'overnight-end' : ''} ${shift.created_source === 'auto' ? 'source-auto' : 'source-manual'} ${autoShapeState?.className || ''}`}
                                title={`${shift.staff_first_name ? `${shift.staff_first_name} ${shift.staff_last_name}` : 'Unassigned'} · ${autoShapeState?.title || (shift.created_source === 'auto' ? 'Auto' : 'Manual')}`}
                              >
                                <span className="shift-time-mini">
                                  {formatTime(shift.displayStartTime)}-{formatTime(shift.displayEndTime)}
                                </span>
                                {shift.staff_initials && <span className="shift-initials">{shift.staff_initials}</span>}
                                {!shift.staff_initials && <span className="shift-unassigned-mini">?</span>}
                                {autoShapeState?.chipLabel && (
                                  <span className="shift-auto-shape-tick" aria-label={autoShapeState.title}>
                                    {autoShapeState.chipLabel}
                                  </span>
                                )}
                              </div>
                            )
                          })}
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

      {renderCalendarHeader('bottom')}

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
                            <>
                              <div className="weekly-hours-card total-hours-card">
                                <div className="employee-name">Weekly Total</div>
                                <div className="hours-summary">
                                  <span className="total-hours">
                                    {(week.total_hours ?? calculateHoursTotal(week.employees)).toFixed(1)}h
                                  </span>
                                  <span className="shift-count">
                                    ({week.shift_count ?? calculateShiftTotal(week.employees)} shifts)
                                  </span>
                                </div>
                              </div>
                              {week.employees.map((emp) => (
                                <div key={emp.employee_id} className="weekly-hours-card">
                                  <div className="employee-name">{emp.employee_name}</div>
                                  <div className="hours-summary">
                                    <span className="total-hours">{emp.total_hours.toFixed(1)}h</span>
                                    <span className="shift-count">({emp.shift_count} shifts)</span>
                                  </div>
                                </div>
                              ))}
                            </>
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
                          <>
                            <div className="weekly-hours-card total-hours-card">
                              <div className="employee-name">Monthly Total</div>
                              <div className="hours-summary">
                                <span className="total-hours">
                                  {(monthlyHours.total_hours ?? calculateHoursTotal(monthlyHours.employees)).toFixed(1)}h
                                </span>
                                <span className="shift-count">
                                  ({monthlyHours.shift_count ?? calculateShiftTotal(monthlyHours.employees)} shifts)
                                </span>
                              </div>
                            </div>
                            {monthlyHours.employees.map((emp) => (
                              <div key={emp.employee_id} className="weekly-hours-card">
                                <div className="employee-name">{emp.employee_name}</div>
                                <div className="hours-summary">
                                  <span className="total-hours">{emp.total_hours.toFixed(1)}h</span>
                                  <span className="shift-count">({emp.shift_count} shifts)</span>
                                </div>
                              </div>
                            ))}
                          </>
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
            {isAdmin && selectedDateShiftExceptions.length > 0 && (
              <div className="shift-exception-review-list">
                {selectedDateShiftExceptions.map((exception) => (
                  <button
                    key={`${exception.booking_id}-${exception.event_type}-${exception.event_time}`}
                    type="button"
                    className="shift-exception-review-item"
                    onClick={() => openShiftExceptionReview(exception)}
                  >
                    <span className="shift-exception-review-main">
                      <strong>{exception.booking_reference}</strong>
                      <span>{exception.event_type === 'dropoff' ? 'Drop-off' : 'Pick-up'} @ {formatTime(exception.event_time)}</span>
                      <span>{exception.booking_customer_name}</span>
                    </span>
                    <span className="shift-exception-review-detail">
                      {exception.suggested_shift
                        ? `Suggested shift ${formatTime(exception.suggested_shift.start_time)}-${formatTime(exception.suggested_shift.end_time)}`
                        : 'No covering shift'}
                    </span>
                  </button>
                ))}
              </div>
            )}

            {isAdmin && selectedReviewIssueCount > 0 && (
              <div className="roster-review-banner" role="alert">
                <div className="roster-review-banner-header">
                  <span className="roster-review-icon" aria-hidden="true">⚠️</span>
                  <div>
                    <strong>Roster review needed</strong>
                    <p>
                      {selectedReviewIssueCount} roster coverage issue{selectedReviewIssueCount === 1 ? '' : 's'} affecting {selectedAffectedBookingEventCount} booking event{selectedAffectedBookingEventCount === 1 ? '' : 's'}.
                    </p>
                  </div>
                </div>
                <ul className="roster-review-list">
                  {selectedMissingShiftReviewItems.map((item) => (
                    <li key={item.key} className={`roster-review-item roster-review-${item.kind}`}>
                      <span className="roster-review-message">{item.message}</span>
                      <span className="roster-review-meta">
                        {[item.time && formatTime(item.time), item.customer_name, item.flight_number, item.destination]
                          .filter(Boolean)
                          .join(' · ')}
                        {item.shift_times?.length > 0 && ` · Shift ${item.shift_times.join(', ')}`}
                      </span>
                    </li>
                  ))}
                </ul>
                {canGenerateSelectedDateRoster && (
                  <div className="roster-review-actions">
                    <button
                      type="button"
                      className="roster-review-generate-btn"
                      onClick={handleGenerateRosterForSelectedDate}
                      disabled={generatingRosterDate === selectedDate || loadingReviewGenerateGate}
                    >
                      {generatingRosterDate === selectedDate
                        ? 'Generating...'
                        : `Generate roster for ${formatDateUK(selectedDate)}`}
                    </button>
                  </div>
                )}
              </div>
            )}

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
                        {booking.secondary_carpark?.qualifies && (
                          <span
                            className="booking-carpark-badge"
                            title={`Secondary car park — ${booking.secondary_carpark.reason}`}
                          >
                            P2
                          </span>
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
                        {booking.secondary_carpark?.qualifies && (
                          <span
                            className="booking-carpark-badge"
                            title={`Secondary car park — ${booking.secondary_carpark.reason}`}
                          >
                            P2
                          </span>
                        )}
                        <div className="booking-header-row">
                          {/* pickup_time leading cell removed 2026-05-20 —
                              the row now leads with the airline. Arrival time
                              still surfaces via "Arrives:" below. */}
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
                  {isAdmin && selectedShiftIds.length === 1 && (() => {
                    // v3 single-select action bar — locked rules 2026-05-04.
                    const sel = selectedDateShifts.find((s) => s.id === selectedShiftIds[0])
                    if (!sel) return null
                    return (
                      <div className="bulk-actions-bar rc-actionbar rc-actionbar-single">
                        <button className="rc-action-btn rc-action-duplicate" onClick={() => openDuplicateModal(sel)}>Duplicate</button>
                        <button className="rc-action-btn rc-action-merge" onClick={() => openMergeModal(sel)}>Merge</button>
                        <button className="rc-action-btn rc-action-split" onClick={() => openSplitModal(sel)}>Split</button>
                        <button className="rc-action-btn rc-action-unassign" onClick={() => openUnassignModal(sel)}>Unassign</button>
                        <button className="rc-action-btn rc-action-delete" onClick={() => openV3DeleteModal(sel)}>Delete</button>
                        <button className="bulk-clear-btn" onClick={clearShiftSelection}>Clear</button>
                      </div>
                    )
                  })()}
                  {isAdmin && selectedShiftIds.length >= 2 && (
                    <div className="bulk-actions-bar rc-actionbar rc-actionbar-multi">
                      <span className="bulk-selection-count">{selectedShiftIds.length} selected</span>
                      <button className="rc-action-btn rc-action-duplicate" onClick={openBulkDuplicateModal}>Duplicate</button>
                      <button className="rc-action-btn rc-action-unassign" onClick={openBulkUnassignModal}>Unassign</button>
                      <button className="rc-action-btn rc-action-delete" onClick={openBulkDeleteModal}>Delete</button>
                      <button className="bulk-edit-btn" onClick={openBulkEditModal} title="Edit times / add bookings (legacy bulk editor)">
                        Edit…
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
                    const isShiftExpanded = expandedShiftIds.has(shift.id)
                    const autoShapeState = getAutoShiftShapeState(shift)

                    return (
                      <div
                        key={shift.id}
                        data-shift-id={shift.id}
                        className={`shift-card ${selectedShiftIds.includes(shift.id) ? 'selected' : ''} ${shift.created_source === 'auto' ? 'source-auto' : 'source-manual'} ${autoShapeState?.className || ''} ${isShiftExpanded ? 'expanded' : 'collapsed'} ${focusReview?.shiftId === shift.id ? 'shift-card-review-focus' : ''}`}
                      >
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
                        <div
                          className="shift-card-header clickable"
                          onClick={() => toggleShiftExpanded(shift.id)}
                        >
                          <span className="collapse-icon">{isShiftExpanded ? '▼' : '▶'}</span>
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
                          {autoShapeState && (
                            <div className={`shift-source-badge source-auto ${autoShapeState.className}`} title={autoShapeState.title}>
                              🤖 {autoShapeState.detailLabel}
                            </div>
                          )}
                        </div>

                        {isShiftExpanded && (
                        <>
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
                              {sortBookingsForShift(shift.bookings, shift).map((booking, idx) => (
                                <div key={booking.id} className="shift-booking-info">
                                  <div className="shift-booking-header">
                                    <span className={`shift-booking-type ${booking.type}`}>
                                      {booking.type === 'dropoff' ? '🚗' : '🛬'}
                                    </span>
                                    <span className="shift-booking-ref">{booking.reference}</span>
                                    {getBookingRegistration(booking) && (
                                      <span className="shift-booking-reg">
                                        {getBookingRegistration(booking)}
                                      </span>
                                    )}
                                    <span className="shift-booking-customer">{booking.customer_name}</span>
                                  </div>
                                  <div className="shift-booking-details">
                                    {booking.time && (
                                      <span className="shift-booking-time">
                                        @ {booking.time}
                                        {booking.type === 'pickup' && (
                                          <span className="shift-booking-time-label"> arrival</span>
                                        )}
                                      </span>
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
                        </>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Available Shifts Section (Employee only) */}
            {!isAdmin && (() => {
              // Filter + operational-time sort: re-bucketed early-AM tails
              // (date=D, end_date=D+1, start_time < end_time) land at the
              // bottom so Friday-afternoon claimable shifts surface above
              // the Friday-evening 00:20 tail.
              const availableForDate = availableShifts
                .filter(shift => shift.date === selectedDate)
                .slice()
                .sort((a, b) => shiftSortMinutes(a) - shiftSortMinutes(b))
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
                                {sortBookingsForShift(shift.bookings, shift).map((booking) => (
                                  <div key={booking.id} className="shift-booking-info">
                                    <div className="shift-booking-header">
                                      <span className={`shift-booking-type ${booking.type}`}>
                                        {booking.type === 'dropoff' ? '🚗' : '🛬'}
                                      </span>
                                      <span className="shift-booking-ref">{booking.reference}</span>
                                      {getBookingRegistration(booking) && (
                                        <span className="shift-booking-reg">
                                          {getBookingRegistration(booking)}
                                        </span>
                                      )}
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
        <div className="modal-overlay" onClick={() => {
          setShowDeleteModal(false)
          setDeletePreview(null)
        }}>
          <div className="modal-content delete-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Delete Shift</h3>
            <p>
              Are you sure you want to delete this shift on{' '}
              <strong>{formatDateUK(shiftToDelete.date)}</strong> at{' '}
              <strong>{formatTime(shiftToDelete.start_time)}</strong>?
            </p>
            {deletePreviewLoading && <p>Checking booking coverage...</p>}
            {deletePreview?.shift_id === shiftToDelete.id && deletePreview.warning && (
              <div className="rc-action-error">
                This shift covers {deletePreview.orphaned_booking_event_count} booking event{deletePreview.orphaned_booking_event_count === 1 ? '' : 's'} within 96 hours with no other live shift covering them. Auto-roster will suppress recreation after delete.
              </div>
            )}
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => {
                  setShowDeleteModal(false)
                  setDeletePreview(null)
                }}
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

      {/* v3 Phase 2 — per-shift action modals (locked 2026-05-04) */}
      {duplicateModal && isAdmin && (
        <div className="modal-overlay" onClick={() => !actionSubmitting && setDuplicateModal(null)}>
          <div className="modal-content rc-action-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Duplicate Shift</h3>
            <p className="rc-action-source">
              Source: <strong>{formatTime(duplicateModal.shift.start_time)}–{formatTime(duplicateModal.shift.end_time)}</strong>
              {duplicateModal.shift.staff_initials ? ` · ${duplicateModal.shift.staff_initials}` : ' · Unassigned'}
            </p>
            <div className="rc-action-mode-toggle" role="tablist" aria-label="Duplicate mode">
              <button
                type="button"
                role="tab"
                aria-selected={duplicateModal.mode === 'date_copy'}
                className={duplicateModal.mode === 'date_copy' ? 'active' : ''}
                onClick={() => setDuplicateModal({ ...duplicateModal, mode: 'date_copy' })}
              >
                <span className="rc-mode-icon" aria-hidden="true">📅</span>
                Copy to date
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={duplicateModal.mode === 'staff_fanout'}
                className={duplicateModal.mode === 'staff_fanout' ? 'active' : ''}
                onClick={() => setDuplicateModal({ ...duplicateModal, mode: 'staff_fanout' })}
              >
                <span className="rc-mode-icon" aria-hidden="true">👥</span>
                Add to staff
              </button>
            </div>
            {duplicateModal.mode === 'date_copy' ? (
              <div className="form-group">
                <label>Target date (DD/MM/YYYY)</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="DD/MM/YYYY"
                  value={duplicateModal.target_date}
                  onChange={(e) => setDuplicateModal({ ...duplicateModal, target_date: e.target.value })}
                  maxLength={10}
                />
              </div>
            ) : (
              <div className="rc-fanout-block">
                <div className="rc-fanout-label">Pick staff to fan out to</div>
                <div className="rc-staff-checklist">
                  {employees.filter((u) => u.is_active && !u.is_admin && u.id !== duplicateModal.shift.staff_id).map((u) => (
                    <label key={u.id} className="rc-staff-row">
                      <input
                        type="checkbox"
                        checked={duplicateModal.staff_ids.includes(u.id)}
                        onChange={() => {
                          const next = duplicateModal.staff_ids.includes(u.id)
                            ? duplicateModal.staff_ids.filter((id) => id !== u.id)
                            : [...duplicateModal.staff_ids, u.id]
                          setDuplicateModal({ ...duplicateModal, staff_ids: next })
                        }}
                      />
                      <span className="rc-staff-row-name">{u.first_name} {u.last_name}</span>
                    </label>
                  ))}
                  <div className="rc-staff-divider" aria-hidden="true" />
                  <label className="rc-staff-row">
                    <input
                      type="checkbox"
                      checked={duplicateModal.add_unassigned_jockey}
                      onChange={(e) => setDuplicateModal({ ...duplicateModal, add_unassigned_jockey: e.target.checked })}
                    />
                    <span className="rc-staff-row-name">🏇 Unassigned Jockey</span>
                  </label>
                  <label className="rc-staff-row">
                    <input
                      type="checkbox"
                      checked={duplicateModal.add_unassigned_fleet}
                      onChange={(e) => setDuplicateModal({ ...duplicateModal, add_unassigned_fleet: e.target.checked })}
                    />
                    <span className="rc-staff-row-name">🚐 Unassigned Fleet</span>
                  </label>
                </div>
              </div>
            )}
            {actionError && <div className="rc-action-error">{actionError}</div>}
            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={() => setDuplicateModal(null)} disabled={actionSubmitting}>Cancel</button>
              <button className="modal-btn modal-btn-primary" onClick={submitDuplicate} disabled={actionSubmitting}>
                {actionSubmitting ? 'Duplicating…' : 'Duplicate'}
              </button>
            </div>
          </div>
        </div>
      )}

      {mergeModal && isAdmin && (() => {
        const picked = mergeModal.neighbours.find((n) => n.id === mergeModal.selectedNeighbourId)
        const sourceStaff = mergeModal.shift.staff_id
        const pickedStaff = picked?.staff_id
        const staffConflict = picked && sourceStaff != null && pickedStaff != null && sourceStaff !== pickedStaff
        return (
        <div className="modal-overlay" onClick={() => !actionSubmitting && setMergeModal(null)}>
          <div className="modal-content rc-action-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Merge Shift</h3>
            <p className="rc-action-source">
              This: <strong>{formatTime(mergeModal.shift.start_time)}–{formatTime(mergeModal.shift.end_time)}</strong>
              {mergeModal.shift.staff_initials && <> · {mergeModal.shift.staff_initials}</>}
            </p>
            {mergeModal.neighbours.length === 0 ? (
              <p className="rc-action-empty">No other shift on this day to merge with.</p>
            ) : (
              <>
                <div className="rc-fanout-block">
                  <div className="rc-fanout-label">Merge into</div>
                  <div className="rc-staff-checklist">
                    {mergeModal.neighbours.map((n) => (
                      <label key={n.id} className="rc-staff-row">
                        <input
                          type="radio"
                          name="merge-neighbour"
                          checked={mergeModal.selectedNeighbourId === n.id}
                          onChange={() => setMergeModal({ ...mergeModal, selectedNeighbourId: n.id })}
                        />
                        <span className="rc-staff-row-name">
                          {n._direction === 'previous' ? 'Earlier' : 'Later'} shift · {formatTime(n.start_time)}–{formatTime(n.end_time)} · {n.staff_initials || 'Unassigned'}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
                {staffConflict && (
                  <div className="rc-fanout-block">
                    <div className="rc-fanout-label">Staff for merged shift</div>
                    <div className="rc-staff-checklist">
                      <label className="rc-staff-row">
                        <input
                          type="radio"
                          name="merge-staff"
                          checked={mergeModal.survivorStaffId === String(sourceStaff)}
                          onChange={() => setMergeModal({ ...mergeModal, survivorStaffId: String(sourceStaff) })}
                        />
                        <span className="rc-staff-row-name">{mergeModal.shift.staff_initials || `Staff #${sourceStaff}`}</span>
                      </label>
                      <label className="rc-staff-row">
                        <input
                          type="radio"
                          name="merge-staff"
                          checked={mergeModal.survivorStaffId === String(pickedStaff)}
                          onChange={() => setMergeModal({ ...mergeModal, survivorStaffId: String(pickedStaff) })}
                        />
                        <span className="rc-staff-row-name">{picked.staff_initials || `Staff #${pickedStaff}`}</span>
                      </label>
                      <label className="rc-staff-row">
                        <input
                          type="radio"
                          name="merge-staff"
                          checked={mergeModal.survivorStaffId === ''}
                          onChange={() => setMergeModal({ ...mergeModal, survivorStaffId: '' })}
                        />
                        <span className="rc-staff-row-name">Unassigned</span>
                      </label>
                    </div>
                  </div>
                )}
              </>
            )}
            {actionError && <div className="rc-action-error">{actionError}</div>}
            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={() => setMergeModal(null)} disabled={actionSubmitting}>Cancel</button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={submitMerge}
                disabled={actionSubmitting || mergeModal.neighbours.length === 0}
              >
                {actionSubmitting ? 'Merging…' : 'Merge'}
              </button>
            </div>
          </div>
        </div>
        )
      })()}

      {splitModal && isAdmin && (
        <div className="modal-overlay" onClick={() => !actionSubmitting && setSplitModal(null)}>
          <div className="modal-content rc-action-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Split Shift</h3>
            <p className="rc-action-source">
              Source: <strong>{formatTime(splitModal.shift.start_time)}–{formatTime(splitModal.shift.end_time)}</strong>
            </p>
            <div className="form-group">
              <label>Split at (HH:MM, must be strictly between start and end)</label>
              <input
                type="text"
                className="form-input"
                placeholder="HH:MM"
                value={splitModal.split_at_time}
                onChange={(e) => setSplitModal({ ...splitModal, split_at_time: formatTimeInput24h(e.target.value, splitModal.split_at_time) })}
                maxLength={5}
              />
            </div>
            {actionError && <div className="rc-action-error">{actionError}</div>}
            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={() => setSplitModal(null)} disabled={actionSubmitting}>Cancel</button>
              <button className="modal-btn modal-btn-primary" onClick={submitSplit} disabled={actionSubmitting}>
                {actionSubmitting ? 'Splitting…' : 'Split'}
              </button>
            </div>
          </div>
        </div>
      )}

      {unassignModal && isAdmin && (
        <div className="modal-overlay" onClick={() => !actionSubmitting && setUnassignModal(null)}>
          <div className="modal-content rc-action-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Unassign Shift</h3>
            <p>
              Clear the staff assignment on this shift?
              {unassignModal.shift.staff_first_name && (
                <> Currently assigned to <strong>{unassignModal.shift.staff_first_name} {unassignModal.shift.staff_last_name}</strong>.</>
              )}
            </p>
            {actionError && <div className="rc-action-error">{actionError}</div>}
            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={() => setUnassignModal(null)} disabled={actionSubmitting}>Cancel</button>
              <button className="modal-btn modal-btn-primary" onClick={submitUnassign} disabled={actionSubmitting}>
                {actionSubmitting ? 'Unassigning…' : 'Unassign'}
              </button>
            </div>
          </div>
        </div>
      )}

      {v3DeleteModal && isAdmin && (
        <div className="modal-overlay" onClick={() => {
          if (!actionSubmitting) {
            setV3DeleteModal(null)
            setDeletePreview(null)
          }
        }}>
          <div className="modal-content rc-action-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Delete Shift</h3>
            <p>
              Delete the shift <strong>{formatTime(v3DeleteModal.shift.start_time)}–{formatTime(v3DeleteModal.shift.end_time)}</strong>?
              This cannot be undone.
            </p>
            {deletePreviewLoading && <p>Checking booking coverage...</p>}
            {deletePreview?.shift_id === v3DeleteModal.shift.id && deletePreview.warning && (
              <div className="rc-action-error">
                This shift covers {deletePreview.orphaned_booking_event_count} booking event{deletePreview.orphaned_booking_event_count === 1 ? '' : 's'} within 96 hours with no other live shift covering them. Auto-roster will suppress recreation after delete.
              </div>
            )}
            {actionError && <div className="rc-action-error">{actionError}</div>}
            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={() => {
                setV3DeleteModal(null)
                setDeletePreview(null)
              }} disabled={actionSubmitting}>Cancel</button>
              <button className="modal-btn modal-btn-danger" onClick={submitV3Delete} disabled={actionSubmitting}>
                {actionSubmitting ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* v3 Phase 3 — bulk modals (locked 2026-05-04). Each loops the
          Phase 2 single-shift endpoint client-side. */}
      {bulkDuplicateModal && isAdmin && (() => {
        const m = bulkDuplicateModal
        const hasStaffPick = m.staff_ids.length > 0 || m.add_unassigned_jockey || m.add_unassigned_fleet
        const totalCopies = m.shifts.length * Math.max(1,
          m.staff_ids.length + (m.add_unassigned_jockey ? 1 : 0) + (m.add_unassigned_fleet ? 1 : 0)
        )
        return (
          <div className="modal-overlay" onClick={() => !actionSubmitting && setBulkDuplicateModal(null)}>
            <div className="modal-content rc-action-modal" onClick={(e) => e.stopPropagation()}>
              <h3>Duplicate {m.shifts.length} Shifts</h3>
              <p className="rc-action-source">
                {hasStaffPick
                  ? `Each shift × each picked staff = ${totalCopies} copies on the target date.`
                  : 'Each selected shift will be copied to the target date with the same staff and times.'}
              </p>
              <div className="form-group">
                <label>Target date (DD/MM/YYYY)</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="DD/MM/YYYY"
                  value={m.target_date}
                  onChange={(e) => setBulkDuplicateModal({ ...m, target_date: e.target.value })}
                  maxLength={10}
                />
              </div>
              <div className="rc-fanout-block">
                <div className="rc-fanout-label">Assign each copy to (optional — leave empty to preserve source staff)</div>
                <div className="rc-staff-checklist">
                  {employees.filter((u) => u.is_active && !u.is_admin).map((u) => (
                    <label key={u.id} className="rc-staff-row">
                      <input
                        type="checkbox"
                        checked={m.staff_ids.includes(u.id)}
                        onChange={() => {
                          const next = m.staff_ids.includes(u.id)
                            ? m.staff_ids.filter((id) => id !== u.id)
                            : [...m.staff_ids, u.id]
                          setBulkDuplicateModal({ ...m, staff_ids: next })
                        }}
                      />
                      <span className="rc-staff-row-name">{u.first_name} {u.last_name}</span>
                    </label>
                  ))}
                  <div className="rc-staff-divider" aria-hidden="true" />
                  <label className="rc-staff-row">
                    <input
                      type="checkbox"
                      checked={m.add_unassigned_jockey}
                      onChange={(e) => setBulkDuplicateModal({ ...m, add_unassigned_jockey: e.target.checked })}
                    />
                    <span className="rc-staff-row-name">🏇 Unassigned Jockey</span>
                  </label>
                  <label className="rc-staff-row">
                    <input
                      type="checkbox"
                      checked={m.add_unassigned_fleet}
                      onChange={(e) => setBulkDuplicateModal({ ...m, add_unassigned_fleet: e.target.checked })}
                    />
                    <span className="rc-staff-row-name">🚐 Unassigned Fleet</span>
                  </label>
                </div>
              </div>
              {actionError && <div className="rc-action-error">{actionError}</div>}
              <div className="modal-actions">
                <button className="modal-btn modal-btn-secondary" onClick={() => setBulkDuplicateModal(null)} disabled={actionSubmitting}>Cancel</button>
                <button className="modal-btn modal-btn-primary" onClick={submitBulkDuplicate} disabled={actionSubmitting}>
                  {actionSubmitting ? 'Duplicating…' : `Duplicate ${m.shifts.length}${hasStaffPick ? ` × ${totalCopies / m.shifts.length}` : ''}`}
                </button>
              </div>
            </div>
          </div>
        )
      })()}

      {bulkUnassignModal && isAdmin && (
        <div className="modal-overlay" onClick={() => !actionSubmitting && setBulkUnassignModal(null)}>
          <div className="modal-content rc-action-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Unassign {bulkUnassignModal.shifts.length} Shifts</h3>
            <p>
              Clear the staff assignment on these {bulkUnassignModal.shifts.length} shifts?
            </p>
            <ul className="rc-bulk-shift-list">
              {bulkUnassignModal.shifts.map((s) => (
                <li key={s.id}>
                  {formatTime(s.start_time)}–{formatTime(s.end_time)} · {s.staff_initials || 'Unassigned'}
                </li>
              ))}
            </ul>
            {actionError && <div className="rc-action-error">{actionError}</div>}
            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={() => setBulkUnassignModal(null)} disabled={actionSubmitting}>Cancel</button>
              <button className="modal-btn modal-btn-primary" onClick={submitBulkUnassign} disabled={actionSubmitting}>
                {actionSubmitting ? 'Unassigning…' : `Unassign ${bulkUnassignModal.shifts.length}`}
              </button>
            </div>
          </div>
        </div>
      )}

      {bulkDeleteModal && isAdmin && (
        <div className="modal-overlay" onClick={() => !actionSubmitting && setBulkDeleteModal(null)}>
          <div className="modal-content rc-action-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Delete {bulkDeleteModal.shifts.length} Shifts</h3>
            <p>
              These {bulkDeleteModal.shifts.length} shifts will be permanently deleted. This cannot be undone.
            </p>
            <ul className="rc-bulk-shift-list">
              {bulkDeleteModal.shifts.map((s) => (
                <li key={s.id}>
                  {formatTime(s.start_time)}–{formatTime(s.end_time)} · {s.staff_initials || 'Unassigned'}
                </li>
              ))}
            </ul>
            {actionError && <div className="rc-action-error">{actionError}</div>}
            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={() => setBulkDeleteModal(null)} disabled={actionSubmitting}>Cancel</button>
              <button className="modal-btn modal-btn-danger" onClick={submitBulkDelete} disabled={actionSubmitting}>
                {actionSubmitting ? 'Deleting…' : `Delete ${bulkDeleteModal.shifts.length}`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default RosterCalendar
