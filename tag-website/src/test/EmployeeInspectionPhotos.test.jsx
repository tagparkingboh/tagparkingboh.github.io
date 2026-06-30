/**
 * Tests for the inspection photo slots + compulsory-corner rules
 * (Employee.jsx). The four corners (Front/Rear Left/Right) are required on
 * BOTH drop-off and return inspections; the original four remain drop-off only.
 */
import { describe, it, expect } from 'vitest'
import { PHOTO_SLOTS, requiredPhotoKeysForType } from '../Employee'

const CORNERS = ['front_left', 'front_right', 'rear_left', 'rear_right']

describe('Inspection photo slots — compulsory corners', () => {
  it('includes the four corner slots flagged required on both types', () => {
    CORNERS.forEach(key => {
      const slot = PHOTO_SLOTS.find(s => s.key === key)
      expect(slot).toBeDefined()
      expect(slot.required).toBe(true)
      expect(slot.bothTypes).toBe(true)
    })
  })

  it('labels corners Front Left / Front Right / Rear Left / Rear Right', () => {
    expect(PHOTO_SLOTS.find(s => s.key === 'front_left').label).toBe('Front Left')
    expect(PHOTO_SLOTS.find(s => s.key === 'front_right').label).toBe('Front Right')
    expect(PHOTO_SLOTS.find(s => s.key === 'rear_left').label).toBe('Rear Left')
    expect(PHOTO_SLOTS.find(s => s.key === 'rear_right').label).toBe('Rear Right')
  })

  it('drop-off requires the original four plus the four corners', () => {
    expect(requiredPhotoKeysForType('dropoff')).toEqual([
      'front', 'rear', 'driver_side', 'passenger_side',
      'front_left', 'front_right', 'rear_left', 'rear_right',
    ])
  })

  it('return (pickup) requires only the four corners', () => {
    expect(requiredPhotoKeysForType('pickup')).toEqual(CORNERS)
  })

  it('additional photos are never required on either type', () => {
    expect(requiredPhotoKeysForType('dropoff')).not.toContain('additional_1')
    expect(requiredPhotoKeysForType('dropoff')).not.toContain('additional_2')
    expect(requiredPhotoKeysForType('pickup')).not.toContain('additional_1')
  })
})
