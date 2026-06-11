// Customer-facing capacity helpers. Pure functions so they can be unit-tested
// in isolation and reused across the booking flow + admin tools.
//
// `dailyOccupancy` is a map of ISO date string ('YYYY-MM-DD') → count of
// bookings overlapping that operational day. The customer-form fetches this
// via `/api/capacity/daily?from=...&to=...` and stores it in component state.
//
// `onlineCapacity` is the public online cap. The backend returns a
// date-effective `daily_capacity` map from `/api/capacity/daily`; when that
// has not loaded yet, helpers fall back to the production default below.

export const DEFAULT_ONLINE_CAPACITY = 73
export const SOFT_CAP = DEFAULT_ONLINE_CAPACITY

// Format a Date as 'YYYY-MM-DD' using LOCAL fields. Using toISOString() would
// shift across midnight in any non-UTC timezone; UK is BST in summer so this
// matters. Mirror the convention dailyOccupancy keys are written in.
export const isoDate = (date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`

export const getOnlineCapacityForDate = (date, dailyCapacity, fallback = SOFT_CAP) => {
  if (!date) return fallback
  if (typeof dailyCapacity === 'number') return dailyCapacity
  if (!dailyCapacity) return fallback
  const capacity = dailyCapacity[isoDate(date)]
  return capacity?.online_spaces || capacity?.online_capacity || fallback
}

// True if `date` is at or above the public online cap.
export const isAtCapacity = (date, dailyOccupancy, dailyCapacity = SOFT_CAP) => {
  if (!date) return false
  if (!dailyOccupancy) return false
  const onlineCapacity = getOnlineCapacityForDate(date, dailyCapacity)
  return (dailyOccupancy[isoDate(date)] || 0) >= onlineCapacity
}

// Occupancy % for a single date, rounded to the nearest integer. Drives the
// "we're getting full" early-warning modal in the booking flow — fires in
// the 80-99% band where the lot still has room but is filling up. Returns
// 0 for null/missing inputs so the JSX gate can do a simple `>= 80` check.
export const getDayOccupancyPercent = (date, dailyOccupancy, dailyCapacity = SOFT_CAP) => {
  if (!date || !dailyOccupancy) return 0
  const onlineCapacity = getOnlineCapacityForDate(date, dailyCapacity)
  if (!onlineCapacity) return 0
  const count = dailyOccupancy[isoDate(date)] || 0
  return Math.round((count / onlineCapacity) * 100)
}

// True if `date` falls inside any manual BlockedDate row. blockedDates is a
// list of `{ start_date, end_date, ... }` ISO-string ranges; the test is
// inclusive on both ends.
export const isManuallyBlocked = (date, blockedDates) => {
  if (!date) return false
  if (!blockedDates || blockedDates.length === 0) return false
  const ds = isoDate(date)
  return blockedDates.some((bd) => ds >= bd.start_date && ds <= bd.end_date)
}

// Walk the stay range (dropoff..pickup, inclusive both ends) and return the
// first date that's either manually blocked or at the soft cap. Returns
// { date: Date, reason: 'manual'|'cap' } or null if every day is fine.
//
// "Straddle" case: dropoff D-2, pickup D+2, day D at cap → fires for day D
// even though neither boundary date itself is blocked.
export const findBlockedDateInStay = (
  dropoffDate,
  pickupDate,
  dailyOccupancy,
  blockedDates,
  dailyCapacity = SOFT_CAP,
) => {
  if (!dropoffDate || !pickupDate) return null
  const cursor = new Date(dropoffDate)
  const end = new Date(pickupDate)
  // Walk inclusively on both ends — pickup day is also "you have a car parked"
  // from the operational POV so we don't want to silently skip it.
  while (cursor <= end) {
    if (isManuallyBlocked(cursor, blockedDates)) {
      return { date: new Date(cursor), reason: 'manual' }
    }
    if (isAtCapacity(cursor, dailyOccupancy, dailyCapacity)) {
      return { date: new Date(cursor), reason: 'cap' }
    }
    cursor.setDate(cursor.getDate() + 1)
  }
  return null
}
