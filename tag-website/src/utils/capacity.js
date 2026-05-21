// Customer-facing capacity helpers. Pure functions so they can be unit-tested
// in isolation and reused across the booking flow + admin tools.
//
// `dailyOccupancy` is a map of ISO date string ('YYYY-MM-DD') → count of
// bookings overlapping that operational day. The customer-form fetches this
// via `/api/capacity/daily?from=...&to=...` and stores it in component state.
//
// `softCap` (default 60) is the public soft cap. The hard ceiling is 62 (admin
// override territory). At softCap the customer flow blocks new bookings; admin
// can still push past it via manual booking.

export const SOFT_CAP = 60

// Format a Date as 'YYYY-MM-DD' using LOCAL fields. Using toISOString() would
// shift across midnight in any non-UTC timezone; UK is BST in summer so this
// matters. Mirror the convention dailyOccupancy keys are written in.
export const isoDate = (date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`

// True if `date` is at or above the public soft cap.
export const isAtCapacity = (date, dailyOccupancy, softCap = SOFT_CAP) => {
  if (!date) return false
  if (!dailyOccupancy) return false
  return (dailyOccupancy[isoDate(date)] || 0) >= softCap
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
  softCap = SOFT_CAP,
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
    if (isAtCapacity(cursor, dailyOccupancy, softCap)) {
      return { date: new Date(cursor), reason: 'cap' }
    }
    cursor.setDate(cursor.getDate() + 1)
  }
  return null
}
