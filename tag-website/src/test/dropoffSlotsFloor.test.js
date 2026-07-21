/* 04:00 drop-off floor (2026-07-22) — frontend twin of the backend clamp
 * in time_slots.py. Boundary tests either side of the floor line and the
 * 90-minute clamp guard, plus the post-midnight exemption. */
import { describe, it, expect } from 'vitest'
import { buildDropoffSlots } from '../utils/dropoffSlots'

const minutes = (h, m) => h * 60 + m
const times = (slots) => slots.map((s) => s.time)

describe('buildDropoffSlots 04:00 floor', () => {
  it('clamps the motivating case: 06:20 departure shows 04:00, not 03:35', () => {
    const slots = buildDropoffSlots(minutes(6, 20))
    expect(times(slots)).toEqual(['04:00', '04:20', '04:50'])
    expect(slots[0].label).toBe('Earliest drop-off')
    expect(slots[1].label).toBe('2 hours before')
    expect(slots[0].id).toBe('165') // slot identity preserved for the backend
  })

  it('boundary: 06:44 departure (03:59) clamps', () => {
    const slots = buildDropoffSlots(minutes(6, 44))
    expect(slots[0].time).toBe('04:00')
    expect(slots[0].label).toBe('Earliest drop-off')
  })

  it('boundary: 06:45 departure lands exactly on 04:00 without relabelling', () => {
    const slots = buildDropoffSlots(minutes(6, 45))
    expect(slots[0].time).toBe('04:00')
    expect(slots[0].label).toBe('2¾ hours before') // not clamped, no rename
  })

  it('boundary: 06:46 departure (04:01) is untouched', () => {
    expect(buildDropoffSlots(minutes(6, 46))[0].time).toBe('04:01')
  })

  it('merges duplicate slots when two clamp to 04:00 (05:40 departure)', () => {
    const slots = buildDropoffSlots(minutes(5, 40))
    expect(times(slots)).toEqual(['04:00', '04:10'])
    expect(slots.length).toBe(2)
  })

  it('clamp guard boundary: 05:30 departure clamps to exactly 90 min before', () => {
    expect(buildDropoffSlots(minutes(5, 30))[0].time).toBe('04:00')
  })

  it('clamp guard boundary: 05:29 departure keeps original small-hours times', () => {
    expect(times(buildDropoffSlots(minutes(5, 29)))).toEqual(['02:44', '03:29', '03:59'])
  })

  it('post-midnight flight keeps previous-evening times (00:35 departure)', () => {
    expect(times(buildDropoffSlots(minutes(0, 35)))).toEqual(['21:50', '22:35', '23:05'])
  })

  it('normal daytime flight is completely unaffected (14:30 departure)', () => {
    const slots = buildDropoffSlots(minutes(14, 30))
    expect(times(slots)).toEqual(['11:45', '12:30', '13:00'])
    expect(slots.map((s) => s.label)).toEqual(['2¾ hours before', '2 hours before', '1½ hours before'])
  })
})
