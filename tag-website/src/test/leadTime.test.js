/**
 * Tests for the booking lead-time gate (utils/leadTime.js).
 *
 * Rule (locked 2026-05-12):
 *   - Same-day drop-offs are blocked outright.
 *   - Bookings placed past 17:00 UK can't have a drop-off the next day.
 *     "Past 17:00" = ukMinutesFromMidnight > 17*60. So 17:00:00..17:00:59
 *     still allow tomorrow; 17:01:00 onwards blocks it.
 *   - Re-check window: 16:50..17:10 UK (the booking page polls every minute
 *     inside this span so a long-dwelling session sees the gate flip live).
 *
 * Boundary discipline per SPEC: each cutoff gets t-ε / t / t+ε tests on
 * every dimension (time-of-day, day-of-week, drop-off-date offset).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

import {
  LATE_CUTOFF_UK_MINUTES,
  RECHECK_WINDOW_START_MINUTES,
  RECHECK_WINDOW_END_MINUTES,
  ukDateAtMidnight,
  ukMinutesFromMidnight,
  computeEarliestBookableDate,
  isLeadTimeAllowedFor,
  inLeadTimeRecheckWindow,
} from '../utils/leadTime'

// Helpers — pin the wall clock to a specific UK wall-clock moment. May 2026
// is BST (UTC+1), so a UK "17:00" is "16:00 UTC". Date.UTC() handles negative
// hours correctly (UK 00:30 → UTC -1:30 → previous-day 23:30 UTC).
function fakeNowAt(ukHour, ukMinute, ukSecond = 0, ymd = '2026-05-12') {
  const [y, m, d] = ymd.split('-').map(Number)
  const utcMs = Date.UTC(y, m - 1, d, ukHour - 1, ukMinute, ukSecond)
  vi.setSystemTime(new Date(utcMs))
  return new Date()
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})


// ---------------------------------------------------------------------------
// Constants — locked values
// ---------------------------------------------------------------------------

describe('leadTime constants', () => {
  it('LATE_CUTOFF_UK_MINUTES is 17:00 (1020)', () => {
    expect(LATE_CUTOFF_UK_MINUTES).toBe(1020)
  })

  it('Re-check window spans 16:50→17:10 UK', () => {
    expect(RECHECK_WINDOW_START_MINUTES).toBe(16 * 60 + 50)
    expect(RECHECK_WINDOW_END_MINUTES).toBe(17 * 60 + 10)
  })
})


// ---------------------------------------------------------------------------
// ukMinutesFromMidnight — minute resolution, truncates seconds
// ---------------------------------------------------------------------------

describe('ukMinutesFromMidnight', () => {
  it('happy: 17:00:00 → 1020', () => {
    expect(ukMinutesFromMidnight(fakeNowAt(17, 0, 0))).toBe(1020)
  })

  it('boundary: 17:00:59 still resolves to 1020 (truncates seconds)', () => {
    expect(ukMinutesFromMidnight(fakeNowAt(17, 0, 59))).toBe(1020)
  })

  it('boundary: 17:01:00 → 1021', () => {
    expect(ukMinutesFromMidnight(fakeNowAt(17, 1, 0))).toBe(1021)
  })

  it('edge: 00:00 → 0', () => {
    expect(ukMinutesFromMidnight(fakeNowAt(0, 0, 0))).toBe(0)
  })

  it('edge: 23:59 → 1439', () => {
    expect(ukMinutesFromMidnight(fakeNowAt(23, 59, 0))).toBe(1439)
  })
})


// ---------------------------------------------------------------------------
// ukDateAtMidnight — local date at 00:00 in UK
// ---------------------------------------------------------------------------

describe('ukDateAtMidnight', () => {
  it('happy: returns the calendar date at local midnight', () => {
    const today = ukDateAtMidnight(fakeNowAt(10, 0, 0, '2026-05-12'))
    expect(today.getFullYear()).toBe(2026)
    expect(today.getMonth()).toBe(4)  // May (0-indexed)
    expect(today.getDate()).toBe(12)
    expect(today.getHours()).toBe(0)
    expect(today.getMinutes()).toBe(0)
  })

  it('boundary: BST 00:30 UK is still 12 May (not 11 May)', () => {
    // BST: 00:30 UK = 23:30 UTC PREVIOUS DAY. The helper must use the UK
    // calendar date, not the UTC one.
    const today = ukDateAtMidnight(fakeNowAt(0, 30, 0, '2026-05-12'))
    expect(today.getDate()).toBe(12)
  })

  it('boundary: BST 23:30 UK is still on the UK date, not next-day UTC', () => {
    const today = ukDateAtMidnight(fakeNowAt(23, 30, 0, '2026-05-12'))
    expect(today.getDate()).toBe(12)
  })
})


// ---------------------------------------------------------------------------
// computeEarliestBookableDate — tomorrow vs day-after at 17:00 boundary
// ---------------------------------------------------------------------------

describe('computeEarliestBookableDate', () => {
  function asDate(y, m, d) {
    return new Date(y, m - 1, d)
  }

  it('happy: 16:55 → earliest is tomorrow (today + 1)', () => {
    const earliest = computeEarliestBookableDate(fakeNowAt(16, 55, 0, '2026-05-12'))
    expect(earliest.getTime()).toBe(asDate(2026, 5, 13).getTime())
  })

  it('happy: 10:00 morning → earliest is tomorrow', () => {
    const earliest = computeEarliestBookableDate(fakeNowAt(10, 0, 0, '2026-05-12'))
    expect(earliest.getTime()).toBe(asDate(2026, 5, 13).getTime())
  })

  it('boundary: 16:59 UK → tomorrow (last full minute below cutoff)', () => {
    const earliest = computeEarliestBookableDate(fakeNowAt(16, 59, 0, '2026-05-12'))
    expect(earliest.getTime()).toBe(asDate(2026, 5, 13).getTime())
  })

  it('boundary: 17:00:00 UK → tomorrow (cutoff is exclusive of 17:00 itself)', () => {
    const earliest = computeEarliestBookableDate(fakeNowAt(17, 0, 0, '2026-05-12'))
    expect(earliest.getTime()).toBe(asDate(2026, 5, 13).getTime())
  })

  it('boundary: 17:00:59 UK → tomorrow (seconds truncate to minute 1020)', () => {
    const earliest = computeEarliestBookableDate(fakeNowAt(17, 0, 59, '2026-05-12'))
    expect(earliest.getTime()).toBe(asDate(2026, 5, 13).getTime())
  })

  it('boundary: 17:01:00 UK → day-after-tomorrow', () => {
    const earliest = computeEarliestBookableDate(fakeNowAt(17, 1, 0, '2026-05-12'))
    expect(earliest.getTime()).toBe(asDate(2026, 5, 14).getTime())
  })

  it('edge: 23:59 UK → still day-after-tomorrow', () => {
    const earliest = computeEarliestBookableDate(fakeNowAt(23, 59, 0, '2026-05-12'))
    expect(earliest.getTime()).toBe(asDate(2026, 5, 14).getTime())
  })

  it('edge: month-end wraps cleanly (31 May 18:00 → 2 June)', () => {
    const earliest = computeEarliestBookableDate(fakeNowAt(18, 0, 0, '2026-05-31'))
    expect(earliest.getTime()).toBe(asDate(2026, 6, 2).getTime())
  })
})


// ---------------------------------------------------------------------------
// isLeadTimeAllowedFor — the gate the UI consumes
// ---------------------------------------------------------------------------

describe('isLeadTimeAllowedFor', () => {
  function asDate(y, m, d) {
    return new Date(y, m - 1, d)
  }

  it('happy: null/undefined dropoff date is allowed (nothing chosen yet)', () => {
    const now = fakeNowAt(10, 0, 0, '2026-05-12')
    expect(isLeadTimeAllowedFor(null, now)).toBe(true)
    expect(isLeadTimeAllowedFor(undefined, now)).toBe(true)
  })

  it('happy: Wed 16:55 + Thu dropoff → allowed', () => {
    const now = fakeNowAt(16, 55, 0, '2026-05-13')  // Wed
    expect(isLeadTimeAllowedFor(asDate(2026, 5, 14), now)).toBe(true)
  })

  it('unhappy: Wed 17:01 + Thu dropoff → blocked', () => {
    const now = fakeNowAt(17, 1, 0, '2026-05-13')  // Wed
    expect(isLeadTimeAllowedFor(asDate(2026, 5, 14), now)).toBe(false)
  })

  it('happy: Wed 16:55 + Fri dropoff → allowed (day-after-tomorrow always passes)', () => {
    const now = fakeNowAt(16, 55, 0, '2026-05-13')
    expect(isLeadTimeAllowedFor(asDate(2026, 5, 15), now)).toBe(true)
  })

  it('happy: Wed 17:01 + Fri dropoff → allowed (cutoff only gates tomorrow)', () => {
    const now = fakeNowAt(17, 1, 0, '2026-05-13')
    expect(isLeadTimeAllowedFor(asDate(2026, 5, 15), now)).toBe(true)
  })

  it('unhappy: today is always blocked, even at 00:01', () => {
    const now = fakeNowAt(0, 1, 0, '2026-05-12')
    expect(isLeadTimeAllowedFor(asDate(2026, 5, 12), now)).toBe(false)
  })

  it('unhappy: yesterday (past) is blocked', () => {
    const now = fakeNowAt(10, 0, 0, '2026-05-12')
    expect(isLeadTimeAllowedFor(asDate(2026, 5, 11), now)).toBe(false)
  })

  it('boundary: exactly 17:00 + tomorrow → allowed (last minute before cutoff)', () => {
    const now = fakeNowAt(17, 0, 0, '2026-05-12')
    expect(isLeadTimeAllowedFor(asDate(2026, 5, 13), now)).toBe(true)
  })

  it('boundary: 17:01 + tomorrow → blocked (cutoff just crossed)', () => {
    const now = fakeNowAt(17, 1, 0, '2026-05-12')
    expect(isLeadTimeAllowedFor(asDate(2026, 5, 13), now)).toBe(false)
  })

  it("bathroom-break scenario: gate flips false between 16:55 and 17:03 for same dropoff", () => {
    const tomorrow = asDate(2026, 5, 13)
    // 16:55 — gate open
    expect(isLeadTimeAllowedFor(tomorrow, fakeNowAt(16, 55, 0, '2026-05-12'))).toBe(true)
    // 17:03 — gate closed
    expect(isLeadTimeAllowedFor(tomorrow, fakeNowAt(17, 3, 0, '2026-05-12'))).toBe(false)
  })
})


// ---------------------------------------------------------------------------
// inLeadTimeRecheckWindow — only poll within 16:50→17:10
// ---------------------------------------------------------------------------

describe('inLeadTimeRecheckWindow', () => {
  it('happy: 17:00 falls inside the window', () => {
    expect(inLeadTimeRecheckWindow(fakeNowAt(17, 0, 0))).toBe(true)
  })

  it('happy: 16:50:00 falls inside (inclusive on the lower bound)', () => {
    expect(inLeadTimeRecheckWindow(fakeNowAt(16, 50, 0))).toBe(true)
  })

  it('happy: 17:10:00 falls inside (inclusive on the upper bound)', () => {
    expect(inLeadTimeRecheckWindow(fakeNowAt(17, 10, 0))).toBe(true)
  })

  it('boundary: 16:49 is OUTSIDE the window', () => {
    expect(inLeadTimeRecheckWindow(fakeNowAt(16, 49, 0))).toBe(false)
  })

  it('boundary: 17:11 is OUTSIDE the window', () => {
    expect(inLeadTimeRecheckWindow(fakeNowAt(17, 11, 0))).toBe(false)
  })

  it('edge: 00:00 is OUTSIDE the window', () => {
    expect(inLeadTimeRecheckWindow(fakeNowAt(0, 0, 0))).toBe(false)
  })

  it('edge: 23:59 is OUTSIDE the window', () => {
    expect(inLeadTimeRecheckWindow(fakeNowAt(23, 59, 0))).toBe(false)
  })
})
