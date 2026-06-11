/**
 * HUEB tests for src/utils/capacity.js — `isAtCapacity`, `isManuallyBlocked`,
 * and `findBlockedDateInStay`.
 *
 * Background (2026-05-21 UX bug): customer picked a drop-off date that was
 * at the soft cap. The form silently let them keep filling in
 * airline/destination — the only "we're full" signal was an amber tint on
 * the calendar popup, gone the moment they closed it. Helpers existed but
 * the JSX didn't surface them as a banner. Fix added a banner; this suite
 * pins the underlying logic.
 *
 * Coverage:
 *   Happy    — single-date at cap returns true; un-capped date returns false
 *   Unhappy  — null inputs / empty maps don't crash
 *   Edge     — online cap boundary at default 73, custom cap overrides
 *   Boundary — straddle dates (dropoff and pickup themselves fine, day in
 *              the middle at cap) → findBlockedDateInStay catches it
 */
import { describe, it, expect } from 'vitest'
import {
  isoDate,
  isAtCapacity,
  isManuallyBlocked,
  findBlockedDateInStay,
  getDayOccupancyPercent,
  getOnlineCapacityForDate,
  DEFAULT_ONLINE_CAPACITY,
  SOFT_CAP,
} from '../utils/capacity'

// Local-time Date helper so tests aren't TZ-sensitive.
const D = (y, m, d) => new Date(y, m - 1, d)

// =============================================================================
// isAtCapacity
// =============================================================================

describe('isAtCapacity', () => {
  // --- HAPPY ---------------------------------------------------------------

  it('H: date at the online cap returns true', () => {
    expect(isAtCapacity(D(2026, 5, 26), { '2026-05-26': 73 })).toBe(true)
  })

  it('H: date well above the online cap returns true', () => {
    expect(isAtCapacity(D(2026, 5, 26), { '2026-05-26': 75 })).toBe(true)
  })

  it('H: date below the online cap returns false', () => {
    expect(isAtCapacity(D(2026, 5, 26), { '2026-05-26': 12 })).toBe(false)
  })

  // --- UNHAPPY -------------------------------------------------------------

  it('U: null date returns false (no crash)', () => {
    expect(isAtCapacity(null, { '2026-05-26': 73 })).toBe(false)
  })

  it('U: missing dailyOccupancy returns false', () => {
    expect(isAtCapacity(D(2026, 5, 26), null)).toBe(false)
  })

  it('U: empty dailyOccupancy returns false', () => {
    expect(isAtCapacity(D(2026, 5, 26), {})).toBe(false)
  })

  it('U: date with no entry in dailyOccupancy treated as 0 (not full)', () => {
    expect(isAtCapacity(D(2026, 5, 26), { '2026-05-27': 73 })).toBe(false)
  })

  // --- EDGE ----------------------------------------------------------------

  it('E: explicit softCap override below default still respected', () => {
    expect(isAtCapacity(D(2026, 5, 26), { '2026-05-26': 40 }, 40)).toBe(true)
    expect(isAtCapacity(D(2026, 5, 26), { '2026-05-26': 39 }, 40)).toBe(false)
  })

  it('E: default online capacity is 73', () => {
    expect(SOFT_CAP).toBe(73)
    expect(DEFAULT_ONLINE_CAPACITY).toBe(73)
  })

  // --- BOUNDARY ------------------------------------------------------------

  it('B: exactly 72 cars → not at cap (one slot left)', () => {
    expect(isAtCapacity(D(2026, 5, 26), { '2026-05-26': 72 })).toBe(false)
  })

  it('B: exactly 73 cars → AT cap (no online slot left)', () => {
    expect(isAtCapacity(D(2026, 5, 26), { '2026-05-26': 73 })).toBe(true)
  })

    it('B: 74 cars → AT cap (manual reserve territory)', () => {
      expect(isAtCapacity(D(2026, 5, 26), { '2026-05-26': 74 })).toBe(true)
    })

  it('B: date-effective capacity map overrides the fallback', () => {
    const capacity = { '2026-05-26': { online_spaces: 88 } }
    expect(getOnlineCapacityForDate(D(2026, 5, 26), capacity)).toBe(88)
    expect(isAtCapacity(D(2026, 5, 26), { '2026-05-26': 87 }, capacity)).toBe(false)
    expect(isAtCapacity(D(2026, 5, 26), { '2026-05-26': 88 }, capacity)).toBe(true)
  })
})

// =============================================================================
// isoDate
// =============================================================================

describe('isoDate (local-time formatter)', () => {
  it('formats single-digit month + day with leading zeros', () => {
    expect(isoDate(D(2026, 1, 9))).toBe('2026-01-09')
  })

  it('preserves the local calendar day across UTC offsets', () => {
    // Using LOCAL fields means BST-summer / GMT-winter don't shift the date.
    // (toISOString() would shift D(2026, 5, 26, 0, 0) → 2026-05-25 in BST.)
    expect(isoDate(D(2026, 5, 26))).toBe('2026-05-26')
  })
})

// =============================================================================
// getDayOccupancyPercent — drives the "we're getting full" early-warning
// modal. 80-89% = amber, 90-99% = red, >= 100% is already hard-blocked by
// isAtCapacity so the modal never fires there.
// =============================================================================

describe('getDayOccupancyPercent', () => {
  // --- HAPPY ---------------------------------------------------------------

  it('H: returns rounded integer percent for a populated date', () => {
    expect(getDayOccupancyPercent(D(2026, 5, 26), { '2026-05-26': 55 })).toBe(75)
  })

  it('H: 59 / 73 rounds to 81% (amber band lower edge)', () => {
    expect(getDayOccupancyPercent(D(2026, 5, 26), { '2026-05-26': 59 })).toBe(81)
  })

  it('H: 66 / 73 rounds to 90% (red band lower edge)', () => {
    expect(getDayOccupancyPercent(D(2026, 5, 26), { '2026-05-26': 66 })).toBe(90)
  })

  // --- UNHAPPY -------------------------------------------------------------

  it('U: null date returns 0', () => {
    expect(getDayOccupancyPercent(null, { '2026-05-26': 48 })).toBe(0)
  })

  it('U: missing dailyOccupancy returns 0', () => {
    expect(getDayOccupancyPercent(D(2026, 5, 26), null)).toBe(0)
  })

  it('U: date with no entry treated as 0% (empty day)', () => {
    expect(getDayOccupancyPercent(D(2026, 5, 26), { '2026-05-27': 50 })).toBe(0)
  })

  it('U: softCap of 0 returns 0 (no divide-by-zero crash)', () => {
    expect(getDayOccupancyPercent(D(2026, 5, 26), { '2026-05-26': 30 }, 0)).toBe(0)
  })

  // --- BOUNDARY ------------------------------------------------------------

  it('B: empty lot → 0%', () => {
    expect(getDayOccupancyPercent(D(2026, 5, 26), { '2026-05-26': 0 })).toBe(0)
  })

  it('B: at cap (73) → 100%', () => {
    expect(getDayOccupancyPercent(D(2026, 5, 26), { '2026-05-26': 73 })).toBe(100)
  })

  it('B: 58 / 73 rounds to 79% (top of "no warning" band)', () => {
    expect(getDayOccupancyPercent(D(2026, 5, 26), { '2026-05-26': 58 })).toBe(79)
  })

  it('B: 65 / 73 rounds to 89% (top of amber band)', () => {
    expect(getDayOccupancyPercent(D(2026, 5, 26), { '2026-05-26': 65 })).toBe(89)
  })

  it('B: 72 / 73 rounds to 99% (top of red band, one slot left)', () => {
    expect(getDayOccupancyPercent(D(2026, 5, 26), { '2026-05-26': 72 })).toBe(99)
  })

  // --- EDGE ----------------------------------------------------------------

  it('E: custom softCap of 40, 32 cars → 80%', () => {
    expect(getDayOccupancyPercent(D(2026, 5, 26), { '2026-05-26': 32 }, 40)).toBe(80)
  })
})

// =============================================================================
// isManuallyBlocked
// =============================================================================

describe('isManuallyBlocked', () => {
  const blockedRanges = [
    { start_date: '2026-12-24', end_date: '2026-12-26', reason: 'Christmas' },
    { start_date: '2026-08-12', end_date: '2026-08-12', reason: 'Maintenance' },
  ]

  it('H: date inside a multi-day range returns true', () => {
    expect(isManuallyBlocked(D(2026, 12, 25), blockedRanges)).toBe(true)
  })

  it('H: date on either boundary of a range returns true (inclusive)', () => {
    expect(isManuallyBlocked(D(2026, 12, 24), blockedRanges)).toBe(true)
    expect(isManuallyBlocked(D(2026, 12, 26), blockedRanges)).toBe(true)
  })

  it('H: single-day range matches that exact day', () => {
    expect(isManuallyBlocked(D(2026, 8, 12), blockedRanges)).toBe(true)
  })

  it('U: outside any range returns false', () => {
    expect(isManuallyBlocked(D(2026, 6, 1), blockedRanges)).toBe(false)
  })

  it('U: null/undefined inputs return false (no crash)', () => {
    expect(isManuallyBlocked(null, blockedRanges)).toBe(false)
    expect(isManuallyBlocked(D(2026, 12, 25), null)).toBe(false)
    expect(isManuallyBlocked(D(2026, 12, 25), [])).toBe(false)
  })

  it('B: one day before range start → false', () => {
    expect(isManuallyBlocked(D(2026, 12, 23), blockedRanges)).toBe(false)
  })

  it('B: one day after range end → false', () => {
    expect(isManuallyBlocked(D(2026, 12, 27), blockedRanges)).toBe(false)
  })
})

// =============================================================================
// findBlockedDateInStay — the STRADDLE case is the regression we shipped
// =============================================================================

describe('findBlockedDateInStay', () => {
  const fullDate = '2026-05-26'
  const dailyOccupancyFull = { [fullDate]: 73 }
  const blockedRanges = [
    { start_date: '2026-12-24', end_date: '2026-12-26', reason: 'Christmas' },
  ]

  // --- HAPPY ---------------------------------------------------------------

  it('H: stay entirely on clear days returns null', () => {
    expect(findBlockedDateInStay(
      D(2026, 6, 1), D(2026, 6, 8), {}, [],
    )).toBe(null)
  })

  it('H: stay where dropoff IS the capped day → returns that day, reason="cap"', () => {
    const got = findBlockedDateInStay(
      D(2026, 5, 26), D(2026, 5, 28), dailyOccupancyFull, [],
    )
    expect(got).not.toBe(null)
    expect(isoDate(got.date)).toBe('2026-05-26')
    expect(got.reason).toBe('cap')
  })

  it('H: stay where pickup IS the capped day → returns that day', () => {
    const got = findBlockedDateInStay(
      D(2026, 5, 24), D(2026, 5, 26), dailyOccupancyFull, [],
    )
    expect(got).not.toBe(null)
    expect(isoDate(got.date)).toBe('2026-05-26')
    expect(got.reason).toBe('cap')
  })

  // --- UNHAPPY -------------------------------------------------------------

  it('U: missing dropoffDate returns null (incomplete form state)', () => {
    expect(findBlockedDateInStay(null, D(2026, 6, 1), dailyOccupancyFull, [])).toBe(null)
  })

  it('U: missing pickupDate returns null', () => {
    expect(findBlockedDateInStay(D(2026, 6, 1), null, dailyOccupancyFull, [])).toBe(null)
  })

  // --- EDGE ----------------------------------------------------------------

  it('E: dropoff and pickup the same day, that day fine → null', () => {
    expect(findBlockedDateInStay(
      D(2026, 6, 1), D(2026, 6, 1), {}, [],
    )).toBe(null)
  })

  it('E: dropoff and pickup the same day, that day at cap → returns it', () => {
    const got = findBlockedDateInStay(
      D(2026, 5, 26), D(2026, 5, 26), dailyOccupancyFull, [],
    )
    expect(got).not.toBe(null)
    expect(isoDate(got.date)).toBe('2026-05-26')
  })

  it('E: manual block beats cap-block of the same day (manual checked first)', () => {
    // 2026-12-25 is both manually blocked AND at cap → returns 'manual'.
    const got = findBlockedDateInStay(
      D(2026, 12, 25), D(2026, 12, 25),
      { '2026-12-25': 73 }, blockedRanges,
    )
    expect(got.reason).toBe('manual')
  })

  // --- BOUNDARY: the STRADDLE case ----------------------------------------
  // Dropoff and pickup are both clear; an interior day is at cap. The
  // banner near the pickup date catches this and routes the customer to
  // the phone number.

  it('B: straddle — dropoff D-2, pickup D+2, day D at cap → returns D', () => {
    const got = findBlockedDateInStay(
      D(2026, 5, 24), D(2026, 5, 28), dailyOccupancyFull, [],
    )
    expect(got).not.toBe(null)
    expect(isoDate(got.date)).toBe('2026-05-26')
    expect(got.reason).toBe('cap')
  })

  it('B: straddle — dropoff D-1, pickup D+1, day D at cap → returns D', () => {
    const got = findBlockedDateInStay(
      D(2026, 5, 25), D(2026, 5, 27), dailyOccupancyFull, [],
    )
    expect(got).not.toBe(null)
    expect(isoDate(got.date)).toBe('2026-05-26')
  })

  it('B: straddle — two capped days inside the stay → returns the EARLIER one', () => {
    const got = findBlockedDateInStay(
      D(2026, 5, 24), D(2026, 5, 30),
      { '2026-05-26': 73, '2026-05-28': 73 }, [],
    )
    expect(isoDate(got.date)).toBe('2026-05-26')
  })

  it('B: straddle — manual block on an interior day → returns it with reason="manual"', () => {
    const got = findBlockedDateInStay(
      D(2026, 12, 22), D(2026, 12, 28),
      {}, blockedRanges,
    )
    expect(got).not.toBe(null)
    expect(isoDate(got.date)).toBe('2026-12-24')
    expect(got.reason).toBe('manual')
  })

  it('B: stay crosses month boundary; capped day is in the next month', () => {
    const got = findBlockedDateInStay(
      D(2026, 5, 30), D(2026, 6, 3),
      { '2026-06-01': 73 }, [],
    )
    expect(isoDate(got.date)).toBe('2026-06-01')
  })

  it('B: long stay (10 days) with capped day at the far end', () => {
    const got = findBlockedDateInStay(
      D(2026, 6, 1), D(2026, 6, 10),
      { '2026-06-09': 73 }, [],
    )
    expect(isoDate(got.date)).toBe('2026-06-09')
  })

  it('B: long stay where every day is clear → null', () => {
    const got = findBlockedDateInStay(
      D(2026, 6, 1), D(2026, 6, 14), {}, [],
    )
    expect(got).toBe(null)
  })

  it('B: custom softCap of 40 — day at 45 cars counts as cap-blocked in the stay', () => {
    const got = findBlockedDateInStay(
      D(2026, 5, 24), D(2026, 5, 28),
      { '2026-05-26': 45 }, [], 40,
    )
    expect(got).not.toBe(null)
    expect(isoDate(got.date)).toBe('2026-05-26')
    expect(got.reason).toBe('cap')
  })
})
