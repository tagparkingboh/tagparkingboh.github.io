/**
 * Unit tests for RosterCalendar's date helpers + bookings grouping.
 *
 * Covers the two regressions:
 * 1. prevIsoDate must use UTC math so DST and leap years don't drift.
 * 2. computeBookingsByDate must re-bucket post-midnight pickups (and
 *    only pickups — never drop-offs) when the time is strictly before
 *    PICKUP_OVERNIGHT_CUTOFF, and each day's list must sort by real
 *    datetime so re-bucketed events land last.
 */
import { describe, it, expect } from 'vitest'
import {
  prevIsoDate,
  computeBookingsByDate,
  PICKUP_OVERNIGHT_CUTOFF,
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

describe('PICKUP_OVERNIGHT_CUTOFF', () => {
  it('is 02:30 UK time', () => {
    expect(PICKUP_OVERNIGHT_CUTOFF).toBe('02:30')
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

  it('ignores non-confirmed bookings', () => {
    const grouped = computeBookingsByDate([
      mkPickup(1, '2026-05-09', '08:15', 'pending'),
      mkPickup(2, '2026-05-09', '12:00', 'cancelled'),
      mkPickup(3, '2026-05-09', '16:00'),
    ])
    expect(grouped['2026-05-09'].pickups.map((b) => b.id)).toEqual([3])
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
})
