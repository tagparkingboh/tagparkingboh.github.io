/**
 * Unit tests for RosterCalendar's date helpers + bookings grouping.
 *
 * Covers the two regressions:
 * 1. prevIsoDate must use UTC math so DST and leap years don't drift.
 * 2. computeBookingsByDate must re-bucket post-midnight pickups (and
 *    only pickups — never drop-offs) when the arrival is strictly before
 *    ARRIVAL_OVERNIGHT_CUTOFF, and each day's list must sort by real
 *    datetime so re-bucketed events land last.
 */
import { describe, it, expect } from 'vitest'
import {
  prevIsoDate,
  computeBookingsByDate,
  ARRIVAL_OVERNIGHT_CUTOFF,
  shiftSortMinutes,
  sourceParamFor,
} from '../components/RosterCalendar'

describe('prevIsoDate', () => {
  it('returns the previous calendar day', () => {
    expect(prevIsoDate('2026-05-10')).toBe('2026-05-09')
  })

  it('crosses month boundary correctly', () => {
    expect(prevIsoDate('2026-05-01')).toBe('2026-04-30')
  })

  it('crosses year boundary correctly', () => {
    expect(prevIsoDate('2027-01-01')).toBe('2026-12-31')
  })

  it('handles leap-day correctly (2024-03-01 → 2024-02-29)', () => {
    expect(prevIsoDate('2024-03-01')).toBe('2024-02-29')
  })

  it('handles non-leap February (2026-03-01 → 2026-02-28)', () => {
    expect(prevIsoDate('2026-03-01')).toBe('2026-02-28')
  })

  it('does not drift across UK DST forward (29 Mar 2026, BST starts)', () => {
    expect(prevIsoDate('2026-03-30')).toBe('2026-03-29')
  })

  it('does not drift across UK DST back (25 Oct 2026, GMT resumes)', () => {
    expect(prevIsoDate('2026-10-26')).toBe('2026-10-25')
  })

  it('returns empty string for missing input', () => {
    expect(prevIsoDate('')).toBe('')
    expect(prevIsoDate(undefined)).toBe('')
  })
})

describe('ARRIVAL_OVERNIGHT_CUTOFF', () => {
  it('is 02:00 UK time', () => {
    expect(ARRIVAL_OVERNIGHT_CUTOFF).toBe('02:00')
  })
})

describe('computeBookingsByDate', () => {
  const mkPickup = (id, pickup_date, pickup_time, status = 'confirmed') => ({
    id,
    status,
    pickup_date,
    pickup_time,
  })

  const mkDropoff = (id, dropoff_date, dropoff_time, status = 'confirmed') => ({
    id,
    status,
    dropoff_date,
    dropoff_time,
  })

  it('re-buckets a post-midnight pickup (00:25) to the previous calendar day', () => {
    const grouped = computeBookingsByDate([
      mkPickup(1, '2026-05-10', '00:25'),
    ])

    expect(grouped['2026-05-09']?.pickups).toHaveLength(1)
    expect(grouped['2026-05-09'].pickups[0].id).toBe(1)
    expect(grouped['2026-05-10']?.pickups ?? []).toHaveLength(0)
  })

  it('re-buckets a 02:29 pickup but NOT a 02:30 pickup (cutoff is exclusive)', () => {
    const grouped = computeBookingsByDate([
      mkPickup(1, '2026-05-10', '02:29'),
      mkPickup(2, '2026-05-10', '02:30'),
    ])

    expect(grouped['2026-05-09']?.pickups.map((b) => b.id)).toEqual([1])
    expect(grouped['2026-05-10']?.pickups.map((b) => b.id)).toEqual([2])
  })

  it('sorts re-bucketed pickups AFTER the same day\'s late evening pickups', () => {
    const grouped = computeBookingsByDate([
      mkPickup(1, '2026-05-09', '08:15'),
      mkPickup(2, '2026-05-09', '16:10'),
      mkPickup(3, '2026-05-09', '23:55'),
      mkPickup(4, '2026-05-10', '00:25'),  // re-bucketed onto the 9th
    ])

    expect(grouped['2026-05-09'].pickups.map((b) => b.id)).toEqual([1, 2, 3, 4])
  })

  it('does NOT re-bucket drop-offs — only pickups have an overnight cutoff', () => {
    const grouped = computeBookingsByDate([
      mkDropoff(99, '2026-05-10', '00:30'),
    ])

    // Drop-off stays on its calendar date regardless of time.
    expect(grouped['2026-05-09']?.dropoffs ?? []).toHaveLength(0)
    expect(grouped['2026-05-10']?.dropoffs).toHaveLength(1)
    expect(grouped['2026-05-10'].dropoffs[0].id).toBe(99)
  })

  it('ignores pending and cancelled bookings (but keeps confirmed and refunded)', () => {
    const grouped = computeBookingsByDate([
      mkPickup(1, '2026-05-09', '08:15', 'pending'),
      mkPickup(2, '2026-05-09', '12:00', 'cancelled'),
      mkPickup(3, '2026-05-09', '16:00'),
      mkPickup(4, '2026-05-09', '18:00', 'refunded'),
    ])
    expect(grouped['2026-05-09'].pickups.map((b) => b.id)).toEqual([3, 4])
  })

  it('includes refunded bookings so operators see them on the calendar', () => {
    const grouped = computeBookingsByDate([
      mkDropoff(1, '2026-05-09', '07:00', 'refunded'),
      mkPickup(2, '2026-05-09', '17:00', 'refunded'),
    ])
    expect(grouped['2026-05-09'].dropoffs.map((b) => b.id)).toEqual([1])
    expect(grouped['2026-05-09'].pickups.map((b) => b.id)).toEqual([2])
  })

  it('handles missing pickup_time as no-op (no re-bucketing)', () => {
    const grouped = computeBookingsByDate([
      mkPickup(1, '2026-05-10', null),
    ])
    expect(grouped['2026-05-10']?.pickups).toHaveLength(1)
    expect(grouped['2026-05-09']?.pickups ?? []).toHaveLength(0)
  })

  it('returns empty object for empty / missing bookings input', () => {
    expect(computeBookingsByDate([])).toEqual({})
    expect(computeBookingsByDate(undefined)).toEqual({})
  })

  // ----------------------------------------------------------------------
  // Pickup-event-date bucketing (post-2026-05-21)
  // ----------------------------------------------------------------------
  // When flight_arrival_date is set on a booking, it's the canonical
  // landing day and the bucketing must use it — pickup_date may be stale
  // (e.g. admin edited arrival but left pickup alone, the TAG-KNL95826
  // staging incident). Legacy rows (flight_arrival_date=null) synthesise
  // arrival from (pickup_date, pickup_time) by subtracting 30 minutes as
  // a real datetime, then apply the same ARRIVAL_OVERNIGHT_CUTOFF (02:00).

  const mkPickupArrival = (id, opts) => ({
    id,
    status: opts.status || 'confirmed',
    flight_arrival_date: opts.flight_arrival_date ?? null,
    flight_arrival_time: opts.flight_arrival_time ?? null,
    pickup_date: opts.pickup_date ?? null,
    pickup_time: opts.pickup_time ?? null,
  })

  it('H: buckets via flight_arrival_date when set, even if pickup_date differs', () => {
    const grouped = computeBookingsByDate([
      mkPickupArrival(1286, {
        flight_arrival_date: '2026-07-04',
        flight_arrival_time: '17:00',
        pickup_date: '2026-07-03',  // stale — admin edited arrival only
        pickup_time: '17:30',
      }),
    ])
    expect(grouped['2026-07-04']?.pickups.map((b) => b.id)).toEqual([1286])
    expect(grouped['2026-07-03']?.pickups ?? []).toHaveLength(0)
  })

  it('E: legacy row (no flight_arrival_date) synthesises arrival from pickup - 30m and applies the cutoff', () => {
    const grouped = computeBookingsByDate([
      mkPickupArrival(1, {
        flight_arrival_date: null,
        pickup_date: '2026-07-10',
        pickup_time: '00:25',  // synth arrival = 7/9 23:55 → operational 7/9
      }),
      mkPickupArrival(2, {
        flight_arrival_date: null,
        pickup_date: '2026-07-10',
        pickup_time: '14:00',  // synth arrival = 7/10 13:30 → operational 7/10
      }),
    ])
    expect(grouped['2026-07-09']?.pickups.map((b) => b.id)).toEqual([1])
    expect(grouped['2026-07-10']?.pickups.map((b) => b.id)).toEqual([2])
  })

  it('B: flight_arrival_date wins over the synthetic-pickup fallback when both apply', () => {
    // arrival on 7/4 23:55, pickup rolled to 7/5 00:25 — flight_arrival_date
    // is 7/4 (canonical landing day). The old rule would also bucket onto 7/4
    // via prevIsoDate('2026-07-05'); the new rule bypasses the heuristic and
    // uses the column directly. Both produce the same result for THIS case,
    // but the test pins the source-of-truth (no longer dependent on
    // pickup_date being correctly rolled).
    const grouped = computeBookingsByDate([
      mkPickupArrival(7, {
        flight_arrival_date: '2026-07-04',
        flight_arrival_time: '23:55',
        pickup_date: '2026-07-05',
        pickup_time: '00:25',
      }),
    ])
    expect(grouped['2026-07-04']?.pickups.map((b) => b.id)).toEqual([7])
  })

  it('B: pickup-side sort uses arrival_time when set so the booking lands chronologically', () => {
    // Without sorting on the arrival timestamp, TAG-KNL95826 (arrival 17:00
    // on 7/4) would sort against its stale pickup_date (7/3) and end up
    // out of place. Confirm it sorts alongside another 7/4 17:00 booking.
    const grouped = computeBookingsByDate([
      mkPickupArrival(20, {
        flight_arrival_date: '2026-07-04',
        flight_arrival_time: '17:00',
        pickup_date: '2026-07-03',
        pickup_time: '17:30',
      }),
      mkPickupArrival(10, {
        flight_arrival_date: '2026-07-04',
        flight_arrival_time: '08:00',
        pickup_date: '2026-07-04',
        pickup_time: '08:30',
      }),
      mkPickupArrival(30, {
        flight_arrival_date: '2026-07-04',
        flight_arrival_time: '22:00',
        pickup_date: '2026-07-04',
        pickup_time: '22:30',
      }),
    ])
    // Chronological by arrival_time within 7/4.
    expect(grouped['2026-07-04']?.pickups.map((b) => b.id)).toEqual([10, 20, 30])
  })

  it('U: booking with neither pickup_date nor flight_arrival_date is skipped on pickup side', () => {
    const grouped = computeBookingsByDate([
      mkPickupArrival(1, {
        flight_arrival_date: null,
        pickup_date: null,
        pickup_time: null,
      }),
    ])
    // No day key should have a pickup for this booking.
    Object.values(grouped).forEach((day) => {
      expect(day.pickups).not.toContainEqual(expect.objectContaining({ id: 1 }))
    })
  })

  // ----------------------------------------------------------------------
  // Post-midnight arrival_time re-bucketing with flight_arrival_date set
  // (post-2026-05-21 fix)
  // ----------------------------------------------------------------------
  // Caught on TAG-QTX08991 (Rana Gioutzesoi): flight lands 00:50 on Tue
  // 2026-06-23 with `flight_arrival_date=2026-06-23`. Operationally it's
  // Mon 2026-06-22's late-shift pickup (the shift spans 23:10 Mon to
  // 01:35 Tue). The pre-fix logic returned flight_arrival_date directly,
  // bypassing the cutoff, so the day tile placed her on Tue. The fix
  // preserves "flight_arrival_date is canonical" but re-applies the
  // ARRIVAL_OVERNIGHT_CUTOFF (02:00) on top.

  it('H: post-midnight arrival (00:50) with flight_arrival_date re-buckets to D-1', () => {
    // Real case: TAG-QTX08991 Rana Gioutzesoi, Antalya → BOH at 00:50 Tue 6/23.
    const grouped = computeBookingsByDate([
      mkPickupArrival(1, {
        flight_arrival_date: '2026-06-23',
        flight_arrival_time: '00:50',
        pickup_date: '2026-06-23',
        pickup_time: '01:20',
      }),
    ])
    expect(grouped['2026-06-22']?.pickups.map((b) => b.id)).toEqual([1])
    expect(grouped['2026-06-23']?.pickups ?? []).toHaveLength(0)
  })

  it('E: daytime arrival (14:00) with flight_arrival_date stays on the canonical day', () => {
    // Cutoff only fires for post-midnight times. 14:00 is well past it, so
    // arrival on 6/23 stays on 6/23 regardless of any pickup_date drift.
    const grouped = computeBookingsByDate([
      mkPickupArrival(1, {
        flight_arrival_date: '2026-06-23',
        flight_arrival_time: '14:00',
        pickup_date: '2026-06-23',
        pickup_time: '14:30',
      }),
    ])
    expect(grouped['2026-06-23']?.pickups.map((b) => b.id)).toEqual([1])
    expect(grouped['2026-06-22']?.pickups ?? []).toHaveLength(0)
  })

  it('B: arrival_time 01:59 re-buckets, 02:00 does NOT (cutoff exclusive) when flight_arrival_date is set', () => {
    // Boundary on the arrival-canonical path. ARRIVAL_OVERNIGHT_CUTOFF is
    // 02:00 (exclusive) — an arrival at 01:59 belongs to the prior day's
    // evening shift; 02:00 stays on its own day.
    const grouped = computeBookingsByDate([
      mkPickupArrival(1, {
        flight_arrival_date: '2026-06-23',
        flight_arrival_time: '01:59',
        pickup_date: '2026-06-23',
        pickup_time: '02:29',
      }),
      mkPickupArrival(2, {
        flight_arrival_date: '2026-06-23',
        flight_arrival_time: '02:00',
        pickup_date: '2026-06-23',
        pickup_time: '02:30',
      }),
    ])
    expect(grouped['2026-06-22']?.pickups.map((b) => b.id)).toEqual([1])
    expect(grouped['2026-06-23']?.pickups.map((b) => b.id)).toEqual([2])
  })

  it('U: flight_arrival_date set, flight_arrival_time null — cutoff falls back to pickup_time', () => {
    // Defensive: in normal data flight_arrival_time accompanies the date,
    // but if the time column is null the bucketing must not silently skip
    // the cutoff and place a 00:55 pickup on the wrong operational day.
    const grouped = computeBookingsByDate([
      mkPickupArrival(1, {
        flight_arrival_date: '2026-06-23',
        flight_arrival_time: null,
        pickup_date: '2026-06-23',
        pickup_time: '00:55',
      }),
    ])
    expect(grouped['2026-06-22']?.pickups.map((b) => b.id)).toEqual([1])
  })

  it('B: arrival 23:55 + pickup_time 00:25 (rolled) still buckets on the arrival day, not D-1', () => {
    // Regression fence: the existing test at line ~197 pinned this, but
    // re-asserting under the new code path is cheap and locks the boundary
    // behaviour — 23:55 is > 02:00 so the cutoff does NOT fire, and the
    // flight_arrival_date (the actual landing day) wins.
    const grouped = computeBookingsByDate([
      mkPickupArrival(1, {
        flight_arrival_date: '2026-07-04',
        flight_arrival_time: '23:55',
        pickup_date: '2026-07-05',
        pickup_time: '00:25',
      }),
    ])
    expect(grouped['2026-07-04']?.pickups.map((b) => b.id)).toEqual([1])
    expect(grouped['2026-07-05']?.pickups ?? []).toHaveLength(0)
  })
})

// =============================================================================
// shiftSortMinutes — operational-time sort key for shift cards
// =============================================================================
// Re-bucketed overnights (date=D, end_date=D+1, with the entire wall-clock
// window after midnight) must land at the bottom of D's shift list — the
// work happens chronologically AFTER same-day evening shifts. Without this,
// a 00:20-01:20 tail of Friday-evening work sorts ahead of Friday's 13:10
// afternoon shift just because '00:20' < '13:10' string-compares low.

describe('shiftSortMinutes', () => {
  it('returns minutes-from-midnight for a normal daytime shift', () => {
    expect(shiftSortMinutes({ start_time: '13:10', end_time: '16:55' })).toBe(13 * 60 + 10)
  })

  it('returns minutes-from-midnight for an early-morning shift (date == end_date)', () => {
    // No overnight flag — sort by its actual start_time.
    expect(shiftSortMinutes({ start_time: '03:50', end_time: '07:00', date: '2026-06-26' })).toBe(3 * 60 + 50)
  })

  it('treats a standard overnight (18:15 → 00:05) as a same-day evening shift', () => {
    // start_time > end_time → crosses midnight from same-day evening.
    // Sort by start_time as-is; this lands it at the evening's chronological slot.
    expect(shiftSortMinutes({
      start_time: '18:15', end_time: '00:05',
      date: '2026-06-25', end_date: '2026-06-26',
      isOvernight: true,
    })).toBe(18 * 60 + 15)
  })

  it('offsets re-bucketed entirely-after-midnight overnights by +24h', () => {
    // start_time < end_time AND end_date > date → the entire shift is on
    // the next calendar day; this is the "Friday-evening tail" pattern.
    // 00:20 + 24h = 24:20 → 1460 minutes.
    expect(shiftSortMinutes({
      start_time: '00:20', end_time: '01:20',
      date: '2026-06-26', end_date: '2026-06-27',
      isOvernight: true,
    })).toBe(24 * 60 + 20)
  })

  it('orders Friday afternoon BEFORE Friday-evening-tail (00:20 next day)', () => {
    // The user-visible bug: under naïve string sort, '00:20' < '13:10'
    // and the tail shift floats to the top of the day. Operational sort
    // pushes it to the bottom.
    const afternoon = { id: 1, start_time: '13:10', end_time: '16:55', date: '2026-06-26' }
    const tail = {
      id: 2, start_time: '00:20', end_time: '01:20',
      date: '2026-06-26', end_date: '2026-06-27',
      isOvernight: true,
    }
    expect(shiftSortMinutes(afternoon)).toBeLessThan(shiftSortMinutes(tail))
  })

  it('infers isOvernight from date/end_date when the flag is absent', () => {
    // Backend payload may not always set the derived isOvernight flag; the
    // helper must still detect re-bucketed tails from date + end_date alone.
    expect(shiftSortMinutes({
      start_time: '00:30', end_time: '01:30',
      date: '2026-06-26', end_date: '2026-06-27',
    })).toBe(24 * 60 + 30)
  })

  it('handles missing fields without throwing', () => {
    expect(shiftSortMinutes(null)).toBe(0)
    expect(shiftSortMinutes({})).toBe(0)
    expect(shiftSortMinutes({ start_time: null })).toBe(0)
  })
})

// =============================================================================
// v3 source-filter toggle helper
// Maps the segmented control's UI value to the /api/roster ?source= query.
// 'manual' must omit the param so the backend's default ≠ auto branch fires
// — that's how the v3 Calendar default keeps today's behaviour exactly.
// =============================================================================

// =============================================================================
// Arrival-time → operational-day bucketing matrix
//
// Tue 2026-05-19 / Wed 2026-05-20. For each arrival_time the booking's
// stored (pickup_date, pickup_time) is derived using the +30-minute rule
// with date rollover at 24:00 (mirrors backend/main.py:10880-10896). Then
// computeBookingsByDate is asserted to bucket the booking on the expected
// operational day (Tue or Wed).
//
// Boundaries under test:
//  - 23:30 — pickup_time wraps to 00:00 next day (date rollover)
//  - 02:30 — calendar cutoff; pickup_time < 02:30 re-buckets to D-1
// =============================================================================

describe('arrival-time → operational-day bucketing matrix', () => {
  const TUE = '2026-05-19'
  const WED = '2026-05-20'

  // Mirror of backend rollover: arrival HH:MM on arrivalDate → expected
  // (pickup_date, pickup_time) the booking row should hold post-creation.
  const derivePickup = (arrivalDate, arrivalHHMM) => {
    const [h, m] = arrivalHHMM.split(':').map(Number)
    const total = h * 60 + m + 30
    const minsOfDay = total % (24 * 60)
    const pickup_time = `${String(Math.floor(minsOfDay / 60)).padStart(2, '0')}:${String(minsOfDay % 60).padStart(2, '0')}`
    let pickup_date = arrivalDate
    if (total >= 24 * 60) {
      const d = new Date(`${arrivalDate}T00:00:00Z`)
      d.setUTCDate(d.getUTCDate() + 1)
      pickup_date = d.toISOString().slice(0, 10)
    }
    return { pickup_date, pickup_time }
  }

  const CASES = [
    { arrival_date: TUE, arrival_time: '23:29', expected_day: TUE, label: '23:29 Tue → pickup 23:59 (no roll) → Tue' },
    { arrival_date: TUE, arrival_time: '23:30', expected_day: TUE, label: '23:30 Tue → pickup 00:00 Wed (roll) → re-bucket Tue' },
    { arrival_date: TUE, arrival_time: '23:31', expected_day: TUE, label: '23:31 Tue → pickup 00:01 Wed (roll) → re-bucket Tue' },
    { arrival_date: TUE, arrival_time: '23:59', expected_day: TUE, label: '23:59 Tue → pickup 00:29 Wed (roll) → re-bucket Tue' },
    { arrival_date: WED, arrival_time: '00:00', expected_day: TUE, label: '00:00 Wed → pickup 00:30 (no roll) → re-bucket Tue' },
    { arrival_date: WED, arrival_time: '00:01', expected_day: TUE, label: '00:01 Wed → pickup 00:31 → re-bucket Tue' },
    { arrival_date: WED, arrival_time: '01:58', expected_day: TUE, label: '01:58 Wed → pickup 02:28 → re-bucket Tue' },
    { arrival_date: WED, arrival_time: '01:59', expected_day: TUE, label: '01:59 Wed → pickup 02:29 → re-bucket Tue' },
    { arrival_date: WED, arrival_time: '02:00', expected_day: WED, label: '02:00 Wed → pickup 02:30 (cutoff, exclusive) → Wed' },
    { arrival_date: WED, arrival_time: '02:01', expected_day: WED, label: '02:01 Wed → pickup 02:31 → Wed' },
  ]

  CASES.forEach((c, idx) => {
    it(c.label, () => {
      const { pickup_date, pickup_time } = derivePickup(c.arrival_date, c.arrival_time)
      const booking = { id: idx + 1, status: 'confirmed', pickup_date, pickup_time }
      const grouped = computeBookingsByDate([booking])

      const otherDay = c.expected_day === TUE ? WED : TUE
      expect(grouped[c.expected_day]?.pickups.map((b) => b.id)).toEqual([idx + 1])
      expect(grouped[otherDay]?.pickups ?? []).toHaveLength(0)
    })
  })

  it('all 10 cases together: 8 land on Tue, 2 land on Wed', () => {
    const bookings = CASES.map((c, idx) => {
      const { pickup_date, pickup_time } = derivePickup(c.arrival_date, c.arrival_time)
      return { id: idx + 1, status: 'confirmed', pickup_date, pickup_time }
    })
    const grouped = computeBookingsByDate(bookings)

    expect(grouped[TUE]?.pickups).toHaveLength(8)
    expect(grouped[WED]?.pickups).toHaveLength(2)
    expect(grouped[TUE].pickups.map((b) => b.id)).toEqual([1, 2, 3, 4, 5, 6, 7, 8])
    expect(grouped[WED].pickups.map((b) => b.id)).toEqual([9, 10])
  })
})

describe('sourceParamFor', () => {
  it('passes through "auto"', () => {
    expect(sourceParamFor('auto')).toBe('auto')
  })

  it('passes through "all"', () => {
    expect(sourceParamFor('all')).toBe('all')
  })

  it('returns null for "manual" so the backend default fires (regression guard for Calendar default)', () => {
    expect(sourceParamFor('manual')).toBeNull()
  })

  it('returns null for unknown values', () => {
    expect(sourceParamFor(undefined)).toBeNull()
    expect(sourceParamFor(null)).toBeNull()
    expect(sourceParamFor('')).toBeNull()
    expect(sourceParamFor('garbage')).toBeNull()
  })
})
