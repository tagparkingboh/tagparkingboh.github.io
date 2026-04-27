/**
 * Unit tests for RosterCalendar's date helpers + bookings grouping.
 *
 * Covers the two recent regressions:
 * 1. prevIsoDate must use UTC math so DST and leap years don't drift.
 * 2. computeBookingsByDate must re-bucket post-midnight events back to
 *    the previous day when an overnight shift on that day extends past
 *    the event's time, and sort each day's events chronologically by
 *    real datetime (not by time-of-day alone).
 */
import { describe, it, expect } from 'vitest'
import {
  prevIsoDate,
  computeOvernightTailEndByDate,
  computeBookingsByDate,
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

describe('computeOvernightTailEndByDate', () => {
  it('captures overnight shifts (end_date != date)', () => {
    const shifts = [
      { date: '2026-05-09', end_date: '2026-05-10', start_time: '22:50', end_time: '00:50' },
    ]
    expect(computeOvernightTailEndByDate(shifts)).toEqual({ '2026-05-09': '00:50' })
  })

  it('ignores same-day shifts', () => {
    const shifts = [
      { date: '2026-05-09', end_date: '2026-05-09', start_time: '08:00', end_time: '16:00' },
    ]
    expect(computeOvernightTailEndByDate(shifts)).toEqual({})
  })

  it('takes the latest end_time when multiple overnight shifts share a start date', () => {
    const shifts = [
      { date: '2026-05-09', end_date: '2026-05-10', start_time: '22:50', end_time: '00:50' },
      { date: '2026-05-09', end_date: '2026-05-10', start_time: '23:00', end_time: '02:00' },
    ]
    expect(computeOvernightTailEndByDate(shifts)).toEqual({ '2026-05-09': '02:00' })
  })

  it('skips shifts missing end_date or end_time', () => {
    const shifts = [
      { date: '2026-05-09', end_date: null, start_time: '08:00', end_time: '16:00' },
      { date: '2026-05-09', end_date: '2026-05-10', start_time: '22:50', end_time: null },
    ]
    expect(computeOvernightTailEndByDate(shifts)).toEqual({})
  })
})

describe('computeBookingsByDate', () => {
  // The canonical fixture from the bug report: a 22:50–00:50 overnight
  // shift on the 9th, plus an 00:25 pickup on the 10th. The 00:25 belongs
  // to the 9th's operational day.
  const overnightShift = {
    date: '2026-05-09',
    end_date: '2026-05-10',
    start_time: '22:50',
    end_time: '00:50',
  }

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

  it('re-buckets a post-midnight pickup to the previous day when an overnight shift covers it', () => {
    const bookings = [mkPickup(1, '2026-05-10', '00:25')]
    const grouped = computeBookingsByDate(bookings, [overnightShift])

    // 00:25 < 00:50 cutoff for the 9th → claimed by the 9th.
    expect(grouped['2026-05-09']?.pickups).toHaveLength(1)
    expect(grouped['2026-05-09'].pickups[0].id).toBe(1)
    // …and removed from the 10th.
    expect(grouped['2026-05-10']?.pickups ?? []).toHaveLength(0)
  })

  it('does NOT re-bucket a pickup that falls AFTER the overnight shift ends', () => {
    const bookings = [mkPickup(1, '2026-05-10', '01:30')]
    const grouped = computeBookingsByDate(bookings, [overnightShift])

    // 01:30 > 00:50 cutoff → stays on the 10th.
    expect(grouped['2026-05-09']?.pickups ?? []).toHaveLength(0)
    expect(grouped['2026-05-10']?.pickups).toHaveLength(1)
    expect(grouped['2026-05-10'].pickups[0].id).toBe(1)
  })

  it('sorts re-bucketed events AFTER the same day\'s late evening events (chronological)', () => {
    const bookings = [
      mkPickup(1, '2026-05-09', '08:15'),
      mkPickup(2, '2026-05-09', '16:10'),
      mkPickup(3, '2026-05-09', '23:55'),
      mkPickup(4, '2026-05-10', '00:25'),  // re-bucketed onto the 9th
    ]
    const grouped = computeBookingsByDate(bookings, [overnightShift])

    expect(grouped['2026-05-09'].pickups.map((b) => b.id)).toEqual([1, 2, 3, 4])
  })

  it('drop-offs follow the same re-bucketing rule', () => {
    const bookings = [mkDropoff(99, '2026-05-10', '00:30')]
    const grouped = computeBookingsByDate(bookings, [overnightShift])

    expect(grouped['2026-05-09']?.dropoffs).toHaveLength(1)
    expect(grouped['2026-05-09'].dropoffs[0].id).toBe(99)
    expect(grouped['2026-05-10']?.dropoffs ?? []).toHaveLength(0)
  })

  it('ignores non-confirmed bookings', () => {
    const bookings = [
      mkPickup(1, '2026-05-09', '08:15', 'pending'),
      mkPickup(2, '2026-05-09', '12:00', 'cancelled'),
      mkPickup(3, '2026-05-09', '16:00'),
    ]
    const grouped = computeBookingsByDate(bookings, [])
    expect(grouped['2026-05-09'].pickups.map((b) => b.id)).toEqual([3])
  })

  it('handles an empty shifts array (no re-bucketing)', () => {
    const bookings = [mkPickup(1, '2026-05-10', '00:25')]
    const grouped = computeBookingsByDate(bookings, [])
    // No overnight shift → 00:25 stays on the 10th.
    expect(grouped['2026-05-09']?.pickups ?? []).toHaveLength(0)
    expect(grouped['2026-05-10'].pickups).toHaveLength(1)
  })

  it('does not re-bucket when the overnight cutoff is earlier than the event time', () => {
    // KW finishes at 00:30; a 00:45 pickup the next day stays on day 2.
    const earlyEnd = { ...overnightShift, end_time: '00:30' }
    const bookings = [mkPickup(1, '2026-05-10', '00:45')]
    const grouped = computeBookingsByDate(bookings, [earlyEnd])
    expect(grouped['2026-05-09']?.pickups ?? []).toHaveLength(0)
    expect(grouped['2026-05-10'].pickups).toHaveLength(1)
  })
})
