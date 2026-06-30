/**
 * Tests for the inspection photo slots + compulsory-photo rules (Employee.jsx).
 * All 8 photos (Front/Rear/Driver/Passenger + the four corners) are required on
 * BOTH drop-off and return inspections; the two Additional slots stay optional.
 */
import { describe, it, expect } from 'vitest'
import { PHOTO_SLOTS, REQUIRED_PHOTO_KEYS } from '../Employee'

const CORNERS = ['front_left', 'front_right', 'rear_left', 'rear_right']

describe('Inspection photo slots — compulsory corners', () => {
  it('includes the four corner slots flagged required', () => {
    CORNERS.forEach(key => {
      const slot = PHOTO_SLOTS.find(s => s.key === key)
      expect(slot).toBeDefined()
      expect(slot.required).toBe(true)
    })
  })

  it('labels corners Front Left / Front Right / Rear Left / Rear Right', () => {
    expect(PHOTO_SLOTS.find(s => s.key === 'front_left').label).toBe('Front Left')
    expect(PHOTO_SLOTS.find(s => s.key === 'front_right').label).toBe('Front Right')
    expect(PHOTO_SLOTS.find(s => s.key === 'rear_left').label).toBe('Rear Left')
    expect(PHOTO_SLOTS.find(s => s.key === 'rear_right').label).toBe('Rear Right')
  })

  it('requires all 8 photos (originals + corners) — same set for both inspection types', () => {
    expect(REQUIRED_PHOTO_KEYS).toEqual([
      'front', 'rear', 'driver_side', 'passenger_side',
      'front_left', 'front_right', 'rear_left', 'rear_right',
    ])
  })

  it('does not require the additional photos', () => {
    expect(REQUIRED_PHOTO_KEYS).not.toContain('additional_1')
    expect(REQUIRED_PHOTO_KEYS).not.toContain('additional_2')
  })
})
