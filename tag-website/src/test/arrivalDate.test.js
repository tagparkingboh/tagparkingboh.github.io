/**
 * HUEB tests for resolveArrivalDate (src/utils/arrivalDate.js).
 *
 * This util resolves the customer's canonical landing date for a booking.
 * The bug it exists to prevent (TAG-MNF73277 staging incident 2026-05-21):
 * a late-night arrival's pickup_date is rolled forward by one day; naively
 * defaulting flight_arrival_date to pickup_date would silently save the
 * wrong landing day. The rollover-aware fallback walks one day back when
 * arrival_time + 30 ≥ 24:00.
 *
 * H/U/E/B per SPEC.md:
 *   Happy    — flight_arrival_date set → return it verbatim
 *   Unhappy  — no pickup_date / unparseable arrival_time → return null /
 *              pickup_date
 *   Edge     — pickup_date present but no arrival_time → return pickup_date
 *   Boundary — arrival_time = 23:29 (no rollover) vs 23:30 (rollover) vs
 *              23:31 (rollover) — the t-ε / t / t+ε guards on the +30 min
 *              wrap-around (per feedback_test_boundaries_times_days_dates).
 */
import { describe, it, expect } from 'vitest'
import { resolveArrivalDate } from '../utils/arrivalDate'

describe('resolveArrivalDate', () => {
  // --- HAPPY ---------------------------------------------------------------

  it('H: returns flight_arrival_date verbatim when set (canonical column)', () => {
    const got = resolveArrivalDate({
      flight_arrival_date: '2026-07-08',
      pickup_date: '2026-07-09',
      flight_arrival_time: '23:30:00',
    })
    expect(got).toBe('2026-07-08')
  })

  it('H: daytime arrival on a legacy row returns pickup_date (no rollover)', () => {
    const got = resolveArrivalDate({
      flight_arrival_date: null,
      pickup_date: '2026-07-08',
      flight_arrival_time: '14:30',
    })
    expect(got).toBe('2026-07-08')
  })

  // --- UNHAPPY -------------------------------------------------------------

  it('U: returns null when booking is null/undefined', () => {
    expect(resolveArrivalDate(null)).toBe(null)
    expect(resolveArrivalDate(undefined)).toBe(null)
  })

  it('U: returns null when there is no pickup_date and no flight_arrival_date', () => {
    expect(resolveArrivalDate({ flight_arrival_time: '23:30' })).toBe(null)
  })

  it('U: unparseable arrival_time falls back to pickup_date (no day shift)', () => {
    // garbage time string → regex skips the rollover branch
    const got = resolveArrivalDate({
      flight_arrival_date: null,
      pickup_date: '2026-07-08',
      flight_arrival_time: 'not-a-time',
    })
    expect(got).toBe('2026-07-08')
  })

  // --- EDGE ----------------------------------------------------------------

  it('E: pickup_date set but no flight_arrival_time → returns pickup_date', () => {
    const got = resolveArrivalDate({
      flight_arrival_date: null,
      pickup_date: '2026-07-08',
      flight_arrival_time: null,
    })
    expect(got).toBe('2026-07-08')
  })

  it('E: flight_arrival_date wins even when arrival_time would imply a rollover', () => {
    // If the canonical field disagrees with the heuristic, trust the column.
    const got = resolveArrivalDate({
      flight_arrival_date: '2026-07-08',
      pickup_date: '2026-07-09',
      flight_arrival_time: '23:30',
    })
    expect(got).toBe('2026-07-08')
  })

  it('E: early-AM arrival (e.g. 01:30) on a legacy row returns pickup_date (no roll)', () => {
    // Early-AM is the pickup_date the customer entered — pickup_time = 02:00
    // doesn't cross midnight, so no back-date.
    const got = resolveArrivalDate({
      flight_arrival_date: null,
      pickup_date: '2026-07-09',
      flight_arrival_time: '01:30',
    })
    expect(got).toBe('2026-07-09')
  })

  // --- BOUNDARY ------------------------------------------------------------
  // The rollover trips when arrival_time + 30 ≥ 1440 minutes (24:00).
  // 23:29 is t-ε (no roll), 23:30 is t (roll), 23:31 is t+ε (roll).

  it('B: 23:29 — t-ε of the rollover, no day shift', () => {
    const got = resolveArrivalDate({
      flight_arrival_date: null,
      pickup_date: '2026-07-09',
      flight_arrival_time: '23:29',
    })
    expect(got).toBe('2026-07-09')
  })

  it('B: 23:30 — t, rollover fires, walk back one day', () => {
    const got = resolveArrivalDate({
      flight_arrival_date: null,
      pickup_date: '2026-07-09',
      flight_arrival_time: '23:30',
    })
    expect(got).toBe('2026-07-08')
  })

  it('B: 23:31 — t+ε, rollover still fires, walk back one day', () => {
    const got = resolveArrivalDate({
      flight_arrival_date: null,
      pickup_date: '2026-07-09',
      flight_arrival_time: '23:31',
    })
    expect(got).toBe('2026-07-08')
  })

  it('B: 23:59 — late-evening upper boundary, rollover fires', () => {
    const got = resolveArrivalDate({
      flight_arrival_date: null,
      pickup_date: '2026-07-09',
      flight_arrival_time: '23:59',
    })
    expect(got).toBe('2026-07-08')
  })

  it('B: month boundary — rollover from 1 Aug back to 31 Jul', () => {
    const got = resolveArrivalDate({
      flight_arrival_date: null,
      pickup_date: '2026-08-01',
      flight_arrival_time: '23:45',
    })
    expect(got).toBe('2026-07-31')
  })

  it('B: year boundary — rollover from 1 Jan 2027 back to 31 Dec 2026', () => {
    const got = resolveArrivalDate({
      flight_arrival_date: null,
      pickup_date: '2027-01-01',
      flight_arrival_time: '23:45',
    })
    expect(got).toBe('2026-12-31')
  })

  it('B: time string with seconds (HH:MM:SS) still parses correctly', () => {
    // DB rows render as "23:58:00" — the regex must match the prefix.
    const got = resolveArrivalDate({
      flight_arrival_date: null,
      pickup_date: '2026-05-01',
      flight_arrival_time: '23:58:00',
    })
    expect(got).toBe('2026-04-30')
  })
})
