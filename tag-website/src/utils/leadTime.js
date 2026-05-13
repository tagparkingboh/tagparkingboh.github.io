/**
 * Lead-time gate utilities — pure functions, no DOM access, no module-level
 * `Date.now()`. Every helper takes a `now: Date` so tests can pin the clock
 * with `vi.setSystemTime(...)` and the gate stays deterministic.
 *
 * Rule (locked 2026-05-12):
 *   - Same-day drop-offs are blocked outright.
 *   - Bookings placed past 20:00 UK can't have a drop-off the next day.
 *     "Past 20:00" = minutes-from-midnight > 20*60, so 20:00:00..20:00:59
 *     still allow tomorrow; 20:01:00 onwards blocks it.
 *
 * Re-check window (19:50..20:10 UK) is when a long-dwelling booking page
 * needs to re-evaluate the gate live, because the cutoff flips during this
 * span. Outside the window the gate's initial value is correct for the rest
 * of the session.
 */

export const LATE_CUTOFF_UK_MINUTES = 20 * 60          // 20:00 (last accepted minute)
export const RECHECK_WINDOW_START_MINUTES = 19 * 60 + 50  // 19:50
export const RECHECK_WINDOW_END_MINUTES = 20 * 60 + 10    // 20:10

/**
 * Calendar date in Europe/London at `now`, as a local Date at 00:00. Date
 * comparisons (`>=`, `>`, `<`) work because all returned values are local
 * midnight.
 */
export function ukDateAtMidnight(now) {
  const ukDateStr = now.toLocaleDateString('en-GB', { timeZone: 'Europe/London' })
  const [day, month, year] = ukDateStr.split('/')
  return new Date(Number(year), Number(month) - 1, Number(day))
}

/**
 * Minutes from midnight UK at `now`. Truncates seconds (matches the gate's
 * minute-resolution behaviour, e.g. 20:00:59 → 1200, not 1200.98).
 */
export function ukMinutesFromMidnight(now) {
  const ukTimeStr = now.toLocaleTimeString('en-GB', {
    timeZone: 'Europe/London',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
  const [hours, minutes] = ukTimeStr.split(':').map(Number)
  return hours * 60 + minutes
}

/**
 * Earliest bookable drop-off Date at `now`:
 *   - At or before 20:00 → tomorrow
 *   - Past 20:00         → day after tomorrow
 */
export function computeEarliestBookableDate(now) {
  const today = ukDateAtMidnight(now)
  const m = ukMinutesFromMidnight(now)
  const addDays = m > LATE_CUTOFF_UK_MINUTES ? 2 : 1
  const earliest = new Date(today)
  earliest.setDate(earliest.getDate() + addDays)
  return earliest
}

/**
 * Does `dropoffDate` (a local Date) clear the lead-time rule at `now`?
 * A null/undefined dropoffDate returns true — nothing to gate yet.
 */
export function isLeadTimeAllowedFor(dropoffDate, now) {
  if (!dropoffDate) return true
  return dropoffDate >= computeEarliestBookableDate(now)
}

/**
 * Is `now` inside the daily 19:50→20:10 re-check window? The booking page
 * polls every minute inside this window so the gate flips live without
 * waiting for a user-driven re-render.
 */
export function inLeadTimeRecheckWindow(now) {
  const m = ukMinutesFromMidnight(now)
  return m >= RECHECK_WINDOW_START_MINUTES && m <= RECHECK_WINDOW_END_MINUTES
}
