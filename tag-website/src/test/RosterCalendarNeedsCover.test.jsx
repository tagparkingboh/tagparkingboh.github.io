/* Roster v4 phase 4 — needs-cover badge counting. */
import { describe, it, expect } from 'vitest'
import { countNeedsCoverShifts } from '../components/RosterCalendar'

describe('countNeedsCoverShifts', () => {
  it('counts unassigned shifts stamped needs_cover_at', () => {
    expect(countNeedsCoverShifts([
      { id: 1, staff_id: null, needs_cover_at: '2026-07-22T10:00:00Z' },
      { id: 2, staff_id: null, needs_cover_at: '2026-07-22T11:00:00Z' },
    ])).toBe(2)
  })

  it('ignores shifts without the stamp and re-covered shifts', () => {
    expect(countNeedsCoverShifts([
      { id: 1, staff_id: null, needs_cover_at: null },      // never released
      { id: 2, staff_id: 7, needs_cover_at: '2026-07-22T10:00:00Z' }, // stale stamp, re-covered
      { id: 3, staff_id: 9, needs_cover_at: null },          // normal assigned
    ])).toBe(0)
  })

  it('handles empty and missing input', () => {
    expect(countNeedsCoverShifts([])).toBe(0)
    expect(countNeedsCoverShifts()).toBe(0)
    expect(countNeedsCoverShifts([null, undefined])).toBe(0)
  })
})
