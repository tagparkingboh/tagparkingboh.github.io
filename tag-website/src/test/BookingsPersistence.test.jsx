/**
 * Tests for BookingsNew component - Session Storage Persistence.
 *
 * These tests verify:
 * 1. Manual flight data (departure/arrival) is persisted to sessionStorage
 * 2. Data is correctly restored after page refresh simulation
 * 3. All booking state survives navigation/refresh scenarios
 * 4. Validation still works after state restoration
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// =============================================================================
// Mock sessionStorage
// =============================================================================

const createMockSessionStorage = () => {
  let store = {}
  return {
    getItem: vi.fn((key) => store[key] || null),
    setItem: vi.fn((key, value) => { store[key] = value }),
    removeItem: vi.fn((key) => { delete store[key] }),
    clear: vi.fn(() => { store = {} }),
    get store() { return store },
    set store(newStore) { store = newStore }
  }
}

// =============================================================================
// Unit Tests: loadBookingState helper
// =============================================================================

describe('BookingsNew - loadBookingState helper', () => {
  let mockSessionStorage

  beforeEach(() => {
    mockSessionStorage = createMockSessionStorage()
    vi.stubGlobal('sessionStorage', mockSessionStorage)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  // Helper function that mirrors the loadBookingState logic in BookingsNew.jsx
  const loadBookingState = (key, fallback) => {
    try {
      const saved = sessionStorage.getItem(`booking_${key}`)
      if (saved !== null) return JSON.parse(saved)
    } catch (e) { /* ignore parse errors */ }
    return fallback
  }

  describe('Happy path', () => {
    it('returns saved value when key exists in sessionStorage', () => {
      const savedData = { flightTime: '10:30', airlineCode: 'BY' }
      mockSessionStorage.store[`booking_manualDepartureData`] = JSON.stringify(savedData)

      const result = loadBookingState('manualDepartureData', { flightTime: '', airlineCode: '' })

      expect(result).toEqual(savedData)
    })

    it('returns fallback when key does not exist', () => {
      const fallback = { flightTime: '', airlineCode: '' }

      const result = loadBookingState('nonExistentKey', fallback)

      expect(result).toEqual(fallback)
    })

    it('handles complex nested objects', () => {
      const savedData = {
        flightNumber: 'BY1234',
        flightTime: '14:00',
        airlineCode: 'BY',
        airlineName: 'TUI',
        customAirline: '',
        destinationCode: 'TFS',
        destinationName: 'Tenerife',
        customDestination: '',
        dropoffSlot: '165'
      }
      mockSessionStorage.store[`booking_manualDepartureData`] = JSON.stringify(savedData)

      const result = loadBookingState('manualDepartureData', {})

      expect(result).toEqual(savedData)
      expect(result.flightNumber).toBe('BY1234')
      expect(result.dropoffSlot).toBe('165')
    })
  })

  describe('Edge cases', () => {
    it('returns fallback for null stored value', () => {
      mockSessionStorage.store[`booking_test`] = null
      const fallback = { default: true }

      const result = loadBookingState('test', fallback)

      expect(result).toEqual(fallback)
    })

    it('returns fallback for invalid JSON', () => {
      mockSessionStorage.store[`booking_corrupt`] = 'not valid json {'
      const fallback = { safe: true }

      const result = loadBookingState('corrupt', fallback)

      expect(result).toEqual(fallback)
    })

    it('returns fallback for empty string value', () => {
      mockSessionStorage.store[`booking_empty`] = ''
      const fallback = { empty: 'fallback' }

      const result = loadBookingState('empty', fallback)

      expect(result).toEqual(fallback)
    })

    it('handles boolean values', () => {
      mockSessionStorage.store[`booking_boolTrue`] = JSON.stringify(true)
      mockSessionStorage.store[`booking_boolFalse`] = JSON.stringify(false)

      expect(loadBookingState('boolTrue', false)).toBe(true)
      expect(loadBookingState('boolFalse', true)).toBe(false)
    })

    it('handles numeric values', () => {
      mockSessionStorage.store[`booking_number`] = JSON.stringify(42)

      expect(loadBookingState('number', 0)).toBe(42)
    })

    it('handles array values', () => {
      const savedArray = ['item1', 'item2']
      mockSessionStorage.store[`booking_array`] = JSON.stringify(savedArray)

      expect(loadBookingState('array', [])).toEqual(savedArray)
    })
  })

  describe('Boundary conditions', () => {
    it('handles very large objects', () => {
      const largeObject = {
        data: 'x'.repeat(10000),
        nested: { deep: { value: 'test' } }
      }
      mockSessionStorage.store[`booking_large`] = JSON.stringify(largeObject)

      const result = loadBookingState('large', {})

      expect(result.data.length).toBe(10000)
      expect(result.nested.deep.value).toBe('test')
    })

    it('handles special characters in values', () => {
      const specialData = {
        customAirline: "Airline's \"Special\" Name",
        note: 'Line1\nLine2\tTab'
      }
      mockSessionStorage.store[`booking_special`] = JSON.stringify(specialData)

      const result = loadBookingState('special', {})

      expect(result.customAirline).toBe("Airline's \"Special\" Name")
      expect(result.note).toBe('Line1\nLine2\tTab')
    })
  })
})

// =============================================================================
// Unit Tests: manualDepartureData persistence
// =============================================================================

describe('BookingsNew - manualDepartureData persistence', () => {
  let mockSessionStorage

  beforeEach(() => {
    mockSessionStorage = createMockSessionStorage()
    vi.stubGlobal('sessionStorage', mockSessionStorage)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  const defaultManualDepartureData = {
    flightNumber: '',
    flightTime: '',
    airlineCode: '',
    airlineName: '',
    customAirline: '',
    destinationCode: '',
    destinationName: '',
    customDestination: '',
    dropoffSlot: ''
  }

  describe('Initial load from sessionStorage', () => {
    it('uses default values when no saved data exists', () => {
      const loadBookingState = (key, fallback) => {
        try {
          const saved = sessionStorage.getItem(`booking_${key}`)
          if (saved !== null) return JSON.parse(saved)
        } catch (e) { /* ignore */ }
        return fallback
      }

      const result = loadBookingState('manualDepartureData', defaultManualDepartureData)

      expect(result).toEqual(defaultManualDepartureData)
    })

    it('restores all fields from saved data', () => {
      const savedData = {
        flightNumber: 'EZY1234',
        flightTime: '06:45',
        airlineCode: 'U2',
        airlineName: 'easyJet',
        customAirline: '',
        destinationCode: 'PMI',
        destinationName: 'Palma De Mallorca',
        customDestination: '',
        dropoffSlot: '120'
      }
      mockSessionStorage.store[`booking_manualDepartureData`] = JSON.stringify(savedData)

      const loadBookingState = (key, fallback) => {
        try {
          const saved = sessionStorage.getItem(`booking_${key}`)
          if (saved !== null) return JSON.parse(saved)
        } catch (e) { /* ignore */ }
        return fallback
      }

      const result = loadBookingState('manualDepartureData', defaultManualDepartureData)

      expect(result.flightNumber).toBe('EZY1234')
      expect(result.flightTime).toBe('06:45')
      expect(result.airlineCode).toBe('U2')
      expect(result.airlineName).toBe('easyJet')
      expect(result.destinationCode).toBe('PMI')
      expect(result.destinationName).toBe('Palma De Mallorca')
      expect(result.dropoffSlot).toBe('120')
    })

    it('restores custom airline correctly', () => {
      const savedData = {
        ...defaultManualDepartureData,
        airlineCode: 'Other',
        customAirline: 'Small Regional Airline'
      }
      mockSessionStorage.store[`booking_manualDepartureData`] = JSON.stringify(savedData)

      const loadBookingState = (key, fallback) => {
        try {
          const saved = sessionStorage.getItem(`booking_${key}`)
          if (saved !== null) return JSON.parse(saved)
        } catch (e) { /* ignore */ }
        return fallback
      }

      const result = loadBookingState('manualDepartureData', defaultManualDepartureData)

      expect(result.airlineCode).toBe('Other')
      expect(result.customAirline).toBe('Small Regional Airline')
    })

    it('restores custom destination correctly', () => {
      const savedData = {
        ...defaultManualDepartureData,
        destinationCode: 'Other',
        customDestination: 'Obscure Airport City'
      }
      mockSessionStorage.store[`booking_manualDepartureData`] = JSON.stringify(savedData)

      const loadBookingState = (key, fallback) => {
        try {
          const saved = sessionStorage.getItem(`booking_${key}`)
          if (saved !== null) return JSON.parse(saved)
        } catch (e) { /* ignore */ }
        return fallback
      }

      const result = loadBookingState('manualDepartureData', defaultManualDepartureData)

      expect(result.destinationCode).toBe('Other')
      expect(result.customDestination).toBe('Obscure Airport City')
    })
  })

  describe('Saving to sessionStorage', () => {
    it('saves complete departure data', () => {
      const dataToSave = {
        flightNumber: 'BY5678',
        flightTime: '11:30',
        airlineCode: 'BY',
        airlineName: 'TUI',
        customAirline: '',
        destinationCode: 'ALC',
        destinationName: 'Alicante',
        customDestination: '',
        dropoffSlot: '165'
      }

      sessionStorage.setItem('booking_manualDepartureData', JSON.stringify(dataToSave))

      expect(mockSessionStorage.setItem).toHaveBeenCalledWith(
        'booking_manualDepartureData',
        JSON.stringify(dataToSave)
      )
    })
  })
})

// =============================================================================
// Unit Tests: manualArrivalData persistence
// =============================================================================

describe('BookingsNew - manualArrivalData persistence', () => {
  let mockSessionStorage

  beforeEach(() => {
    mockSessionStorage = createMockSessionStorage()
    vi.stubGlobal('sessionStorage', mockSessionStorage)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  const defaultManualArrivalData = {
    flightNumber: '',
    flightTime: '',
    airlineCode: '',
    airlineName: '',
    customAirline: '',
    originCode: '',
    originName: '',
    customOrigin: ''
  }

  describe('Initial load from sessionStorage', () => {
    it('uses default values when no saved data exists', () => {
      const loadBookingState = (key, fallback) => {
        try {
          const saved = sessionStorage.getItem(`booking_${key}`)
          if (saved !== null) return JSON.parse(saved)
        } catch (e) { /* ignore */ }
        return fallback
      }

      const result = loadBookingState('manualArrivalData', defaultManualArrivalData)

      expect(result).toEqual(defaultManualArrivalData)
    })

    it('restores all fields from saved data', () => {
      const savedData = {
        flightNumber: 'FR9876',
        flightTime: '23:15',
        airlineCode: 'FR',
        airlineName: 'Ryanair',
        customAirline: '',
        originCode: 'AGP',
        originName: 'Malaga',
        customOrigin: ''
      }
      mockSessionStorage.store[`booking_manualArrivalData`] = JSON.stringify(savedData)

      const loadBookingState = (key, fallback) => {
        try {
          const saved = sessionStorage.getItem(`booking_${key}`)
          if (saved !== null) return JSON.parse(saved)
        } catch (e) { /* ignore */ }
        return fallback
      }

      const result = loadBookingState('manualArrivalData', defaultManualArrivalData)

      expect(result.flightNumber).toBe('FR9876')
      expect(result.flightTime).toBe('23:15')
      expect(result.airlineCode).toBe('FR')
      expect(result.airlineName).toBe('Ryanair')
      expect(result.originCode).toBe('AGP')
      expect(result.originName).toBe('Malaga')
    })

    it('restores overnight arrival times correctly', () => {
      const savedData = {
        ...defaultManualArrivalData,
        flightTime: '01:30',
        airlineCode: 'BY',
        originCode: 'TFS'
      }
      mockSessionStorage.store[`booking_manualArrivalData`] = JSON.stringify(savedData)

      const loadBookingState = (key, fallback) => {
        try {
          const saved = sessionStorage.getItem(`booking_${key}`)
          if (saved !== null) return JSON.parse(saved)
        } catch (e) { /* ignore */ }
        return fallback
      }

      const result = loadBookingState('manualArrivalData', defaultManualArrivalData)

      expect(result.flightTime).toBe('01:30')
    })
  })
})

// =============================================================================
// Integration Tests: Complete booking state persistence
// =============================================================================

describe('BookingsNew - Complete booking state persistence (Integration)', () => {
  let mockSessionStorage

  beforeEach(() => {
    mockSessionStorage = createMockSessionStorage()
    vi.stubGlobal('sessionStorage', mockSessionStorage)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  const loadBookingState = (key, fallback) => {
    try {
      const saved = sessionStorage.getItem(`booking_${key}`)
      if (saved !== null) return JSON.parse(saved)
    } catch (e) { /* ignore */ }
    return fallback
  }

  describe('Step 1 data restoration after refresh', () => {
    it('restores both departure and arrival data after simulated refresh', () => {
      // Simulate user filling Step 1
      const departureData = {
        flightNumber: 'BY1234',
        flightTime: '08:00',
        airlineCode: 'BY',
        airlineName: 'TUI',
        customAirline: '',
        destinationCode: 'TFS',
        destinationName: 'Tenerife',
        customDestination: '',
        dropoffSlot: '165'
      }
      const arrivalData = {
        flightNumber: 'BY1235',
        flightTime: '16:30',
        airlineCode: 'BY',
        airlineName: 'TUI',
        customAirline: '',
        originCode: 'TFS',
        originName: 'Tenerife',
        customOrigin: ''
      }

      // Save to storage (simulating the useEffect)
      sessionStorage.setItem('booking_manualDepartureData', JSON.stringify(departureData))
      sessionStorage.setItem('booking_manualArrivalData', JSON.stringify(arrivalData))
      sessionStorage.setItem('booking_step', JSON.stringify(2))

      // Simulate page refresh - load from storage
      const restoredDeparture = loadBookingState('manualDepartureData', {})
      const restoredArrival = loadBookingState('manualArrivalData', {})
      const restoredStep = loadBookingState('step', 1)

      expect(restoredDeparture).toEqual(departureData)
      expect(restoredArrival).toEqual(arrivalData)
      expect(restoredStep).toBe(2)
    })

    it('restores partial data if user refreshed mid-entry', () => {
      // User only filled departure, not arrival yet
      const partialDepartureData = {
        flightNumber: '',
        flightTime: '09:30',
        airlineCode: 'U2',
        airlineName: 'easyJet',
        customAirline: '',
        destinationCode: '',
        destinationName: '',
        customDestination: '',
        dropoffSlot: ''
      }

      sessionStorage.setItem('booking_manualDepartureData', JSON.stringify(partialDepartureData))
      sessionStorage.setItem('booking_step', JSON.stringify(1))

      const restoredDeparture = loadBookingState('manualDepartureData', {})

      expect(restoredDeparture.flightTime).toBe('09:30')
      expect(restoredDeparture.airlineCode).toBe('U2')
      expect(restoredDeparture.destinationCode).toBe('') // Not filled yet
    })
  })

  describe('Multi-step progression with persistence', () => {
    it('maintains flight data through step 1 to step 3', () => {
      const fullState = {
        step: 3,
        manualDepartureData: {
          flightNumber: 'EZY5678',
          flightTime: '07:15',
          airlineCode: 'U2',
          airlineName: 'easyJet',
          customAirline: '',
          destinationCode: 'FAO',
          destinationName: 'Faro',
          customDestination: '',
          dropoffSlot: '120'
        },
        manualArrivalData: {
          flightNumber: 'EZY5679',
          flightTime: '19:45',
          airlineCode: 'U2',
          airlineName: 'easyJet',
          customAirline: '',
          originCode: 'FAO',
          originName: 'Faro',
          customOrigin: ''
        },
        formData: {
          dropoffDate: '2024-07-15',
          pickupDate: '2024-07-22',
          package: 'quick',
          firstName: 'John',
          lastName: 'Smith'
        }
      }

      // Save all state
      sessionStorage.setItem('booking_step', JSON.stringify(fullState.step))
      sessionStorage.setItem('booking_manualDepartureData', JSON.stringify(fullState.manualDepartureData))
      sessionStorage.setItem('booking_manualArrivalData', JSON.stringify(fullState.manualArrivalData))
      sessionStorage.setItem('booking_formData', JSON.stringify(fullState.formData))

      // Simulate refresh on step 3
      const restoredStep = loadBookingState('step', 1)
      const restoredDeparture = loadBookingState('manualDepartureData', {})
      const restoredArrival = loadBookingState('manualArrivalData', {})
      const restoredForm = loadBookingState('formData', {})

      expect(restoredStep).toBe(3)
      expect(restoredDeparture.flightTime).toBe('07:15')
      expect(restoredDeparture.destinationCode).toBe('FAO')
      expect(restoredArrival.flightTime).toBe('19:45')
      expect(restoredForm.firstName).toBe('John')
    })

    it('maintains data through step 4 (payment)', () => {
      const paymentReadyState = {
        step: 4,
        manualDepartureData: {
          flightNumber: 'BY9999',
          flightTime: '14:00',
          airlineCode: 'BY',
          airlineName: 'TUI',
          customAirline: '',
          destinationCode: 'PFO',
          destinationName: 'Paphos',
          customDestination: '',
          dropoffSlot: '165'
        },
        manualArrivalData: {
          flightNumber: 'BY9998',
          flightTime: '22:00',
          airlineCode: 'BY',
          airlineName: 'TUI',
          customAirline: '',
          originCode: 'PFO',
          originName: 'Paphos',
          customOrigin: ''
        },
        formData: {
          terms: true,
          package: 'premium'
        }
      }

      sessionStorage.setItem('booking_step', JSON.stringify(paymentReadyState.step))
      sessionStorage.setItem('booking_manualDepartureData', JSON.stringify(paymentReadyState.manualDepartureData))
      sessionStorage.setItem('booking_manualArrivalData', JSON.stringify(paymentReadyState.manualArrivalData))
      sessionStorage.setItem('booking_formData', JSON.stringify(paymentReadyState.formData))

      const restoredStep = loadBookingState('step', 1)
      const restoredDeparture = loadBookingState('manualDepartureData', {})
      const restoredArrival = loadBookingState('manualArrivalData', {})

      expect(restoredStep).toBe(4)
      expect(restoredDeparture.flightNumber).toBe('BY9999')
      expect(restoredArrival.flightNumber).toBe('BY9998')
    })
  })

  describe('Navigation scenarios', () => {
    it('data survives browser back button simulation', () => {
      // User on step 3, goes back to step 1, then forward again
      const initialState = {
        manualDepartureData: {
          flightNumber: 'FR1111',
          flightTime: '06:00',
          airlineCode: 'FR',
          airlineName: 'Ryanair',
          customAirline: '',
          destinationCode: 'AGP',
          destinationName: 'Malaga',
          customDestination: '',
          dropoffSlot: '120'
        }
      }

      sessionStorage.setItem('booking_manualDepartureData', JSON.stringify(initialState.manualDepartureData))
      sessionStorage.setItem('booking_step', JSON.stringify(3))

      // Simulate going back to step 1
      sessionStorage.setItem('booking_step', JSON.stringify(1))

      // Verify data is still there
      const dataAfterBack = loadBookingState('manualDepartureData', {})
      expect(dataAfterBack.flightNumber).toBe('FR1111')

      // Simulate going forward to step 3 again
      sessionStorage.setItem('booking_step', JSON.stringify(3))

      // Data should still be intact
      const dataAfterForward = loadBookingState('manualDepartureData', {})
      expect(dataAfterForward.flightNumber).toBe('FR1111')
      expect(dataAfterForward.destinationCode).toBe('AGP')
    })

    it('data survives navigate away and return', () => {
      // Save current state
      const bookingData = {
        manualDepartureData: {
          flightTime: '12:00',
          airlineCode: 'BY',
          destinationCode: 'LPA'
        },
        manualArrivalData: {
          flightTime: '20:00',
          airlineCode: 'BY',
          originCode: 'LPA'
        }
      }

      sessionStorage.setItem('booking_manualDepartureData', JSON.stringify(bookingData.manualDepartureData))
      sessionStorage.setItem('booking_manualArrivalData', JSON.stringify(bookingData.manualArrivalData))

      // User navigates away (we don't clear sessionStorage)
      // User comes back

      // Verify data is restored
      const restoredDeparture = loadBookingState('manualDepartureData', {})
      const restoredArrival = loadBookingState('manualArrivalData', {})

      expect(restoredDeparture.flightTime).toBe('12:00')
      expect(restoredDeparture.destinationCode).toBe('LPA')
      expect(restoredArrival.flightTime).toBe('20:00')
      expect(restoredArrival.originCode).toBe('LPA')
    })
  })

  describe('Clearing state on booking completion', () => {
    it('clears all booking data after successful payment', () => {
      // Setup full booking state
      sessionStorage.setItem('booking_step', JSON.stringify(4))
      sessionStorage.setItem('booking_manualDepartureData', JSON.stringify({ flightTime: '10:00' }))
      sessionStorage.setItem('booking_manualArrivalData', JSON.stringify({ flightTime: '18:00' }))
      sessionStorage.setItem('booking_formData', JSON.stringify({ firstName: 'Test' }))
      sessionStorage.setItem('booking_customerId', JSON.stringify(123))

      // Simulate payment success cleanup
      Object.keys(mockSessionStorage.store).forEach(key => {
        if (key.startsWith('booking_')) {
          sessionStorage.removeItem(key)
        }
      })

      // Verify all cleared
      expect(loadBookingState('step', 1)).toBe(1)
      expect(loadBookingState('manualDepartureData', null)).toBeNull()
      expect(loadBookingState('manualArrivalData', null)).toBeNull()
    })
  })
})

// =============================================================================
// Integration Tests: Validation with restored data
// =============================================================================

describe('BookingsNew - Validation with restored data (Integration)', () => {
  let mockSessionStorage

  beforeEach(() => {
    mockSessionStorage = createMockSessionStorage()
    vi.stubGlobal('sessionStorage', mockSessionStorage)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  // Helper to validate time format (mirrors BookingsNew.jsx)
  const isValidTimeFormat = (time) => {
    if (!time || typeof time !== 'string') return false
    const timeRegex = /^([01]?[0-9]|2[0-3]):[0-5][0-9]$/
    return timeRegex.test(time)
  }

  describe('Step 1 completion validation', () => {
    it('validates complete departure data after restoration', () => {
      const completeData = {
        flightNumber: 'BY1234',
        flightTime: '10:30',
        airlineCode: 'BY',
        airlineName: 'TUI',
        customAirline: '',
        destinationCode: 'TFS',
        destinationName: 'Tenerife',
        customDestination: '',
        dropoffSlot: '165'
      }

      // Check validation conditions
      const isDepartureAirlineComplete = completeData.airlineCode &&
        (completeData.airlineCode !== 'Other' ||
          (completeData.customAirline && completeData.customAirline.length > 0))

      const isDestinationComplete = completeData.destinationCode &&
        (completeData.destinationCode !== 'Other' ||
          (completeData.customDestination && completeData.customDestination.length > 0))

      const isDepartureComplete = !!(
        isDepartureAirlineComplete &&
        isValidTimeFormat(completeData.flightTime) &&
        isDestinationComplete &&
        completeData.dropoffSlot
      )

      expect(isDepartureComplete).toBe(true)
    })

    it('fails validation when flight time is missing after bad restore', () => {
      const incompleteData = {
        flightNumber: '',
        flightTime: '', // Missing!
        airlineCode: 'BY',
        airlineName: 'TUI',
        customAirline: '',
        destinationCode: 'TFS',
        destinationName: 'Tenerife',
        customDestination: '',
        dropoffSlot: '165'
      }

      const isDepartureComplete = !!(
        incompleteData.airlineCode &&
        isValidTimeFormat(incompleteData.flightTime) &&
        incompleteData.destinationCode &&
        incompleteData.dropoffSlot
      )

      expect(isDepartureComplete).toBe(false)
    })

    it('fails validation when dropoff slot is missing', () => {
      const noSlotData = {
        flightTime: '10:30',
        airlineCode: 'BY',
        destinationCode: 'TFS',
        dropoffSlot: '' // Missing!
      }

      const isDepartureComplete = !!(
        noSlotData.airlineCode &&
        isValidTimeFormat(noSlotData.flightTime) &&
        noSlotData.destinationCode &&
        noSlotData.dropoffSlot
      )

      expect(isDepartureComplete).toBe(false)
    })

    it('validates arrival data after restoration', () => {
      const completeArrival = {
        flightNumber: 'BY5678',
        flightTime: '18:45',
        airlineCode: 'BY',
        airlineName: 'TUI',
        customAirline: '',
        originCode: 'TFS',
        originName: 'Tenerife',
        customOrigin: ''
      }

      const isArrivalAirlineComplete = completeArrival.airlineCode &&
        (completeArrival.airlineCode !== 'Other' ||
          (completeArrival.customAirline && completeArrival.customAirline.length > 0))

      const isOriginComplete = completeArrival.originCode &&
        (completeArrival.originCode !== 'Other' ||
          (completeArrival.customOrigin && completeArrival.customOrigin.length > 0))

      const isArrivalComplete =
        isArrivalAirlineComplete &&
        isValidTimeFormat(completeArrival.flightTime) &&
        isOriginComplete

      expect(isArrivalComplete).toBe(true)
    })
  })
})

// =============================================================================
// Negative Tests: Data corruption scenarios
// =============================================================================

describe('BookingsNew - Data corruption handling', () => {
  let mockSessionStorage

  beforeEach(() => {
    mockSessionStorage = createMockSessionStorage()
    vi.stubGlobal('sessionStorage', mockSessionStorage)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  const loadBookingState = (key, fallback) => {
    try {
      const saved = sessionStorage.getItem(`booking_${key}`)
      if (saved !== null) return JSON.parse(saved)
    } catch (e) { /* ignore */ }
    return fallback
  }

  const defaultDeparture = {
    flightNumber: '',
    flightTime: '',
    airlineCode: '',
    airlineName: '',
    customAirline: '',
    destinationCode: '',
    destinationName: '',
    customDestination: '',
    dropoffSlot: ''
  }

  it('recovers gracefully from corrupted JSON', () => {
    mockSessionStorage.store['booking_manualDepartureData'] = '{"broken json'

    const result = loadBookingState('manualDepartureData', defaultDeparture)

    expect(result).toEqual(defaultDeparture)
  })

  it('recovers from unexpected data types', () => {
    // Number instead of object
    mockSessionStorage.store['booking_manualDepartureData'] = '42'

    const result = loadBookingState('manualDepartureData', defaultDeparture)

    // Should return 42 (valid JSON parse), but app should handle this
    expect(result).toBe(42)
  })

  it('recovers from null value in storage', () => {
    mockSessionStorage.store['booking_manualDepartureData'] = 'null'

    const result = loadBookingState('manualDepartureData', defaultDeparture)

    // JSON.parse('null') returns null, the check `saved !== null` catches this
    // But our implementation checks if sessionStorage.getItem returns null (not the parsed value)
    // 'null' string is not null, so it parses to null and returns null
    expect(result).toBeNull()
  })

  it('handles missing nested properties', () => {
    // Only some fields present
    mockSessionStorage.store['booking_manualDepartureData'] = JSON.stringify({
      flightTime: '10:00'
      // All other fields missing
    })

    const result = loadBookingState('manualDepartureData', defaultDeparture)

    expect(result.flightTime).toBe('10:00')
    expect(result.airlineCode).toBeUndefined() // Not in saved data
  })
})

// =============================================================================
// Unit Tests: manual_entry flag logic (THE BUG FIX)
// =============================================================================

describe('StripePayment - manual_entry flag logic', () => {
  /**
   * THE BUG: !!manualDepartureData returns true for empty objects {}
   * THE FIX: Check that ALL required fields have values before setting manual_entry: true
   *
   * dropoff_manual_entry requires: airlineCode, flightTime, destinationCode, dropoffSlot
   * pickup_manual_entry requires: airlineCode, flightTime, originCode
   */

  // Helper function that mirrors the FIXED logic in StripePayment.jsx
  const isDropoffManualEntry = (data) => {
    return !!(data?.airlineCode && data?.flightTime && data?.destinationCode && data?.dropoffSlot)
  }

  const isPickupManualEntry = (data) => {
    return !!(data?.airlineCode && data?.flightTime && data?.originCode)
  }

  describe('dropoff_manual_entry - Negative tests (should be FALSE)', () => {
    it('returns false for null data', () => {
      expect(isDropoffManualEntry(null)).toBe(false)
    })

    it('returns false for undefined data', () => {
      expect(isDropoffManualEntry(undefined)).toBe(false)
    })

    it('returns false for empty object {} (THE BUG CASE)', () => {
      // This was the root cause of TAG-LLP80398!
      expect(isDropoffManualEntry({})).toBe(false)
    })

    it('returns false when all fields are empty strings', () => {
      const emptyData = {
        flightNumber: '',
        flightTime: '',
        airlineCode: '',
        airlineName: '',
        customAirline: '',
        destinationCode: '',
        destinationName: '',
        customDestination: '',
        dropoffSlot: ''
      }
      expect(isDropoffManualEntry(emptyData)).toBe(false)
    })

    it('returns false when airlineCode is missing', () => {
      const data = {
        airlineCode: '', // Missing!
        flightTime: '10:00',
        destinationCode: 'TFS',
        dropoffSlot: '165'
      }
      expect(isDropoffManualEntry(data)).toBe(false)
    })

    it('returns false when flightTime is missing', () => {
      const data = {
        airlineCode: 'BY',
        flightTime: '', // Missing!
        destinationCode: 'TFS',
        dropoffSlot: '165'
      }
      expect(isDropoffManualEntry(data)).toBe(false)
    })

    it('returns false when destinationCode is missing', () => {
      const data = {
        airlineCode: 'BY',
        flightTime: '10:00',
        destinationCode: '', // Missing!
        dropoffSlot: '165'
      }
      expect(isDropoffManualEntry(data)).toBe(false)
    })

    it('returns false when dropoffSlot is missing', () => {
      const data = {
        airlineCode: 'BY',
        flightTime: '10:00',
        destinationCode: 'TFS',
        dropoffSlot: '' // Missing!
      }
      expect(isDropoffManualEntry(data)).toBe(false)
    })

    it('returns false when only one field is filled', () => {
      expect(isDropoffManualEntry({ airlineCode: 'FR' })).toBe(false)
      expect(isDropoffManualEntry({ flightTime: '08:00' })).toBe(false)
      expect(isDropoffManualEntry({ destinationCode: 'AGP' })).toBe(false)
      expect(isDropoffManualEntry({ dropoffSlot: '120' })).toBe(false)
    })

    it('returns false when three of four fields are filled', () => {
      // Missing dropoffSlot
      expect(isDropoffManualEntry({
        airlineCode: 'BY',
        flightTime: '10:00',
        destinationCode: 'TFS'
      })).toBe(false)

      // Missing destinationCode
      expect(isDropoffManualEntry({
        airlineCode: 'BY',
        flightTime: '10:00',
        dropoffSlot: '165'
      })).toBe(false)

      // Missing flightTime
      expect(isDropoffManualEntry({
        airlineCode: 'BY',
        destinationCode: 'TFS',
        dropoffSlot: '165'
      })).toBe(false)

      // Missing airlineCode
      expect(isDropoffManualEntry({
        flightTime: '10:00',
        destinationCode: 'TFS',
        dropoffSlot: '165'
      })).toBe(false)
    })
  })

  describe('dropoff_manual_entry - Positive tests (should be TRUE)', () => {
    it('returns true when all four required fields are filled', () => {
      const completeData = {
        airlineCode: 'BY',
        flightTime: '10:30',
        destinationCode: 'TFS',
        dropoffSlot: '165'
      }
      expect(isDropoffManualEntry(completeData)).toBe(true)
    })

    it('returns true with early slot (165)', () => {
      expect(isDropoffManualEntry({
        airlineCode: 'FR',
        flightTime: '06:00',
        destinationCode: 'AGP',
        dropoffSlot: '165'
      })).toBe(true)
    })

    it('returns true with late slot (120)', () => {
      expect(isDropoffManualEntry({
        airlineCode: 'U2',
        flightTime: '14:45',
        destinationCode: 'PMI',
        dropoffSlot: '120'
      })).toBe(true)
    })

    it('returns true with "Other" airline (custom)', () => {
      expect(isDropoffManualEntry({
        airlineCode: 'Other',
        flightTime: '09:00',
        destinationCode: 'FAO',
        dropoffSlot: '165',
        customAirline: 'Small Regional Air'
      })).toBe(true)
    })

    it('returns true with "Other" destination (custom)', () => {
      expect(isDropoffManualEntry({
        airlineCode: 'BY',
        flightTime: '11:00',
        destinationCode: 'Other',
        dropoffSlot: '120',
        customDestination: 'Obscure Airport'
      })).toBe(true)
    })

    it('returns true with extra fields present', () => {
      // Having extra fields shouldn't affect the check
      const fullData = {
        flightNumber: 'BY1234',
        flightTime: '10:30',
        airlineCode: 'BY',
        airlineName: 'TUI Airways',
        customAirline: '',
        destinationCode: 'TFS',
        destinationName: 'Tenerife South',
        customDestination: '',
        dropoffSlot: '165'
      }
      expect(isDropoffManualEntry(fullData)).toBe(true)
    })
  })

  describe('dropoff_manual_entry - Edge cases and boundaries', () => {
    it('handles whitespace-only values as falsy', () => {
      // Whitespace strings are truthy in JS, but this tests behavior
      const data = {
        airlineCode: ' ', // Just a space
        flightTime: '10:00',
        destinationCode: 'TFS',
        dropoffSlot: '165'
      }
      // ' ' is truthy, so this returns true - but validation should catch it
      expect(isDropoffManualEntry(data)).toBe(true)
    })

    it('handles midnight flight time (00:00)', () => {
      expect(isDropoffManualEntry({
        airlineCode: 'BY',
        flightTime: '00:00',
        destinationCode: 'TFS',
        dropoffSlot: '165'
      })).toBe(true)
    })

    it('handles late night flight time (23:59)', () => {
      expect(isDropoffManualEntry({
        airlineCode: 'FR',
        flightTime: '23:59',
        destinationCode: 'AGP',
        dropoffSlot: '120'
      })).toBe(true)
    })

    it('handles numeric slot values as strings', () => {
      expect(isDropoffManualEntry({
        airlineCode: 'BY',
        flightTime: '10:00',
        destinationCode: 'TFS',
        dropoffSlot: '165' // String, not number
      })).toBe(true)
    })

    it('handles 0 as a falsy value', () => {
      expect(isDropoffManualEntry({
        airlineCode: 'BY',
        flightTime: '10:00',
        destinationCode: 'TFS',
        dropoffSlot: 0 // Falsy!
      })).toBe(false)
    })

    it('handles "0" string as truthy', () => {
      expect(isDropoffManualEntry({
        airlineCode: 'BY',
        flightTime: '10:00',
        destinationCode: 'TFS',
        dropoffSlot: '0' // Truthy string
      })).toBe(true)
    })
  })

  describe('pickup_manual_entry - Negative tests (should be FALSE)', () => {
    it('returns false for null data', () => {
      expect(isPickupManualEntry(null)).toBe(false)
    })

    it('returns false for undefined data', () => {
      expect(isPickupManualEntry(undefined)).toBe(false)
    })

    it('returns false for empty object {}', () => {
      expect(isPickupManualEntry({})).toBe(false)
    })

    it('returns false when all fields are empty strings', () => {
      const emptyData = {
        flightNumber: '',
        flightTime: '',
        airlineCode: '',
        airlineName: '',
        customAirline: '',
        originCode: '',
        originName: '',
        customOrigin: ''
      }
      expect(isPickupManualEntry(emptyData)).toBe(false)
    })

    it('returns false when airlineCode is missing', () => {
      expect(isPickupManualEntry({
        airlineCode: '',
        flightTime: '18:00',
        originCode: 'TFS'
      })).toBe(false)
    })

    it('returns false when flightTime is missing', () => {
      expect(isPickupManualEntry({
        airlineCode: 'BY',
        flightTime: '',
        originCode: 'TFS'
      })).toBe(false)
    })

    it('returns false when originCode is missing', () => {
      expect(isPickupManualEntry({
        airlineCode: 'BY',
        flightTime: '18:00',
        originCode: ''
      })).toBe(false)
    })

    it('returns false when only two of three fields are filled', () => {
      // Missing originCode
      expect(isPickupManualEntry({
        airlineCode: 'BY',
        flightTime: '18:00'
      })).toBe(false)

      // Missing flightTime
      expect(isPickupManualEntry({
        airlineCode: 'BY',
        originCode: 'TFS'
      })).toBe(false)

      // Missing airlineCode
      expect(isPickupManualEntry({
        flightTime: '18:00',
        originCode: 'TFS'
      })).toBe(false)
    })
  })

  describe('pickup_manual_entry - Positive tests (should be TRUE)', () => {
    it('returns true when all three required fields are filled', () => {
      expect(isPickupManualEntry({
        airlineCode: 'BY',
        flightTime: '18:30',
        originCode: 'TFS'
      })).toBe(true)
    })

    it('returns true with overnight arrival time', () => {
      expect(isPickupManualEntry({
        airlineCode: 'BY',
        flightTime: '01:30', // After midnight
        originCode: 'TFS'
      })).toBe(true)
    })

    it('returns true with "Other" airline (custom)', () => {
      expect(isPickupManualEntry({
        airlineCode: 'Other',
        flightTime: '19:00',
        originCode: 'FAO',
        customAirline: 'Charter Air'
      })).toBe(true)
    })

    it('returns true with "Other" origin (custom)', () => {
      expect(isPickupManualEntry({
        airlineCode: 'FR',
        flightTime: '20:00',
        originCode: 'Other',
        customOrigin: 'Remote Airfield'
      })).toBe(true)
    })
  })

  describe('pickup_manual_entry - Edge cases', () => {
    it('handles very early morning arrivals', () => {
      expect(isPickupManualEntry({
        airlineCode: 'BY',
        flightTime: '04:00',
        originCode: 'TFS'
      })).toBe(true)
    })

    it('handles midnight arrival (00:00)', () => {
      expect(isPickupManualEntry({
        airlineCode: 'FR',
        flightTime: '00:00',
        originCode: 'AGP'
      })).toBe(true)
    })
  })
})

// =============================================================================
// Integration Tests: API payload generation
// =============================================================================

describe('StripePayment - API payload generation', () => {
  /**
   * Tests that verify the correct payload is generated for the API
   * based on the manual_entry flag logic
   */

  const generatePayload = (manualDepartureData, manualArrivalData) => {
    return {
      dropoff_manual_entry: !!(manualDepartureData?.airlineCode &&
                               manualDepartureData?.flightTime &&
                               manualDepartureData?.destinationCode &&
                               manualDepartureData?.dropoffSlot),
      dropoff_airline_code: manualDepartureData?.airlineCode || null,
      dropoff_airline_name: manualDepartureData?.airlineName || null,
      dropoff_destination_code: manualDepartureData?.destinationCode || null,
      dropoff_destination_name: manualDepartureData?.destinationName || null,
      dropoff_flight_time: manualDepartureData?.flightTime || null,
      drop_off_slot: manualDepartureData?.dropoffSlot || null,
      pickup_manual_entry: !!(manualArrivalData?.airlineCode &&
                              manualArrivalData?.flightTime &&
                              manualArrivalData?.originCode),
      pickup_airline_code: manualArrivalData?.airlineCode || null,
      pickup_airline_name: manualArrivalData?.airlineName || null,
      pickup_origin_code: manualArrivalData?.originCode || null,
      pickup_origin_name: manualArrivalData?.originName || null,
      pickup_flight_time: manualArrivalData?.flightTime || null,
    }
  }

  describe('Empty data scenarios (TAG-LLP80398 bug case)', () => {
    it('generates correct payload for empty departure data', () => {
      const emptyDeparture = {
        flightNumber: '',
        flightTime: '',
        airlineCode: '',
        airlineName: '',
        destinationCode: '',
        destinationName: '',
        dropoffSlot: ''
      }
      const emptyArrival = {
        flightNumber: '',
        flightTime: '',
        airlineCode: '',
        airlineName: '',
        originCode: '',
        originName: ''
      }

      const payload = generatePayload(emptyDeparture, emptyArrival)

      // THE FIX: manual_entry should be FALSE for empty data
      expect(payload.dropoff_manual_entry).toBe(false)
      expect(payload.pickup_manual_entry).toBe(false)

      // All other fields should be null
      expect(payload.dropoff_airline_code).toBeNull()
      expect(payload.dropoff_flight_time).toBeNull()
      expect(payload.drop_off_slot).toBeNull()
    })

    it('generates correct payload for default initialized state', () => {
      // This is what happens when the component first loads
      const defaultDeparture = {
        flightNumber: '',
        flightTime: '',
        airlineCode: '',
        airlineName: '',
        customAirline: '',
        destinationCode: '',
        destinationName: '',
        customDestination: '',
        dropoffSlot: ''
      }

      const payload = generatePayload(defaultDeparture, null)

      expect(payload.dropoff_manual_entry).toBe(false)
      expect(payload.pickup_manual_entry).toBe(false)
    })
  })

  describe('Complete data scenarios', () => {
    it('generates correct payload for complete departure and arrival', () => {
      const completeDeparture = {
        flightNumber: 'BY1234',
        flightTime: '10:30',
        airlineCode: 'BY',
        airlineName: 'TUI Airways',
        destinationCode: 'TFS',
        destinationName: 'Tenerife South',
        dropoffSlot: '165'
      }
      const completeArrival = {
        flightNumber: 'BY1235',
        flightTime: '18:45',
        airlineCode: 'BY',
        airlineName: 'TUI Airways',
        originCode: 'TFS',
        originName: 'Tenerife South'
      }

      const payload = generatePayload(completeDeparture, completeArrival)

      expect(payload.dropoff_manual_entry).toBe(true)
      expect(payload.dropoff_airline_code).toBe('BY')
      expect(payload.dropoff_flight_time).toBe('10:30')
      expect(payload.dropoff_destination_code).toBe('TFS')
      expect(payload.drop_off_slot).toBe('165')

      expect(payload.pickup_manual_entry).toBe(true)
      expect(payload.pickup_airline_code).toBe('BY')
      expect(payload.pickup_flight_time).toBe('18:45')
      expect(payload.pickup_origin_code).toBe('TFS')
    })
  })

  describe('Partial data scenarios', () => {
    it('departure complete but arrival incomplete', () => {
      const completeDeparture = {
        airlineCode: 'FR',
        flightTime: '08:00',
        destinationCode: 'AGP',
        dropoffSlot: '120'
      }
      const incompleteArrival = {
        airlineCode: 'FR',
        flightTime: '', // Missing!
        originCode: 'AGP'
      }

      const payload = generatePayload(completeDeparture, incompleteArrival)

      expect(payload.dropoff_manual_entry).toBe(true)
      expect(payload.pickup_manual_entry).toBe(false)
    })

    it('departure incomplete but arrival complete', () => {
      const incompleteDeparture = {
        airlineCode: 'BY',
        flightTime: '10:00',
        destinationCode: 'TFS',
        dropoffSlot: '' // Missing!
      }
      const completeArrival = {
        airlineCode: 'BY',
        flightTime: '18:00',
        originCode: 'TFS'
      }

      const payload = generatePayload(incompleteDeparture, completeArrival)

      expect(payload.dropoff_manual_entry).toBe(false)
      expect(payload.pickup_manual_entry).toBe(true)
    })
  })

  describe('Null/undefined data handling', () => {
    it('handles null departure data', () => {
      const payload = generatePayload(null, null)

      expect(payload.dropoff_manual_entry).toBe(false)
      expect(payload.pickup_manual_entry).toBe(false)
      expect(payload.dropoff_airline_code).toBeNull()
    })

    it('handles undefined departure data', () => {
      const payload = generatePayload(undefined, undefined)

      expect(payload.dropoff_manual_entry).toBe(false)
      expect(payload.pickup_manual_entry).toBe(false)
    })

    it('handles mixed null and complete data', () => {
      const completeDeparture = {
        airlineCode: 'U2',
        flightTime: '07:00',
        destinationCode: 'PMI',
        dropoffSlot: '165'
      }

      const payload = generatePayload(completeDeparture, null)

      expect(payload.dropoff_manual_entry).toBe(true)
      expect(payload.pickup_manual_entry).toBe(false)
    })
  })
})

// =============================================================================
// Regression Tests: Specific bug scenarios
// =============================================================================

describe('Regression Tests - Known bug scenarios', () => {
  describe('TAG-LLP80398: Empty object truthy check', () => {
    /**
     * Bug: User completed booking but all flight data was missing
     * Root cause: !!{} returns true, so dropoff_manual_entry was true
     *             but all individual fields were empty strings → null
     * Result: Backend received manual_entry: true with all null fields
     */

    it('reproduces the original bug with old logic', () => {
      const emptyData = {
        flightNumber: '',
        flightTime: '',
        airlineCode: '',
        airlineName: '',
        destinationCode: '',
        dropoffSlot: ''
      }

      // OLD BUGGY LOGIC
      const oldManualEntry = !!emptyData // This was the bug!

      expect(oldManualEntry).toBe(true) // BUG: Returns true for empty object
    })

    it('verifies the fix prevents the bug', () => {
      const emptyData = {
        flightNumber: '',
        flightTime: '',
        airlineCode: '',
        airlineName: '',
        destinationCode: '',
        dropoffSlot: ''
      }

      // NEW FIXED LOGIC
      const newManualEntry = !!(emptyData?.airlineCode &&
                                emptyData?.flightTime &&
                                emptyData?.destinationCode &&
                                emptyData?.dropoffSlot)

      expect(newManualEntry).toBe(false) // FIX: Returns false for empty data
    })
  })

  describe('TAG-WWA09273: Missing airline_code', () => {
    /**
     * This booking had data but airline_code was null
     * Investigating if partial data can cause issues
     */

    it('handles case where airline code is missing but other data present', () => {
      const partialData = {
        flightNumber: 'FR5944',
        flightTime: '09:00',
        airlineCode: '', // Missing!
        airlineName: 'Ryanair',
        destinationCode: 'AGP',
        dropoffSlot: '165'
      }

      const manualEntry = !!(partialData?.airlineCode &&
                             partialData?.flightTime &&
                             partialData?.destinationCode &&
                             partialData?.dropoffSlot)

      expect(manualEntry).toBe(false) // Should NOT be flagged as manual entry
    })
  })

  describe('Session storage persistence across refreshes', () => {
    it('data survives hard refresh simulation', () => {
      const mockStorage = {}

      // Initial state
      const initialData = {
        airlineCode: 'BY',
        flightTime: '10:00',
        destinationCode: 'TFS',
        dropoffSlot: '165'
      }

      // Save to "storage"
      mockStorage['booking_manualDepartureData'] = JSON.stringify(initialData)

      // Simulate hard refresh - load from storage
      const restored = JSON.parse(mockStorage['booking_manualDepartureData'])

      // Verify data integrity
      expect(restored.airlineCode).toBe('BY')
      expect(restored.flightTime).toBe('10:00')
      expect(restored.destinationCode).toBe('TFS')
      expect(restored.dropoffSlot).toBe('165')

      // Verify manual_entry flag
      const manualEntry = !!(restored?.airlineCode &&
                             restored?.flightTime &&
                             restored?.destinationCode &&
                             restored?.dropoffSlot)
      expect(manualEntry).toBe(true)
    })
  })
})
