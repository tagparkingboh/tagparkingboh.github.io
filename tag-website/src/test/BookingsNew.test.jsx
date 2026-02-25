/**
 * Tests for BookingsNew component - Online booking flow.
 *
 * These tests verify:
 * 1. Address parsing from Ideal Postcodes API
 * 2. Form field population after address selection
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// =============================================================================
// Address Parsing Tests (Ideal Postcodes API)
// =============================================================================

describe('BookingsNew - Address Parsing from Ideal Postcodes API', () => {
  // Helper function that mirrors the handleAddressSelect logic in BookingsNew.jsx
  const parseAddress = (selectedAddress) => {
    let address1 = ''
    let address2 = ''

    const fullAddress = selectedAddress.address
    const postTown = selectedAddress.post_town
    const dependentLocality = selectedAddress.dependent_locality
    const postcode = selectedAddress.postcode

    // Remove postcode and post_town from the end to get the street portion
    let streetPortion = fullAddress
      .replace(new RegExp(`,?\\s*${postcode}\\s*$`, 'i'), '')
      .replace(new RegExp(`,?\\s*${postTown}\\s*$`, 'i'), '')
      .trim()

    // If dependent_locality exists, it goes in address2
    if (dependentLocality) {
      address1 = streetPortion
        .replace(new RegExp(`,?\\s*${dependentLocality}\\s*$`, 'i'), '')
        .trim()
      address2 = dependentLocality
    } else {
      address1 = streetPortion
      address2 = ''
    }

    // Clean up any trailing commas
    address1 = address1.replace(/,\s*$/, '').trim()

    return {
      address1,
      address2,
      city: selectedAddress.post_town,
      county: selectedAddress.county || '',
      postcode: selectedAddress.postcode,
    }
  }

  describe('Rural addresses with dependent_locality', () => {
    it('parses address with village/locality correctly', () => {
      const address = {
        uprn: '1942015',
        address: '72 High Street, Sturminster Marshall, Wimborne, BH21 4AY',
        building_name: '',
        building_number: '72',
        thoroughfare: 'High Street',
        dependent_locality: 'Sturminster Marshall',
        post_town: 'Wimborne',
        postcode: 'BH21 4AY',
        county: 'Dorset',
      }

      const result = parseAddress(address)

      expect(result.address1).toBe('72 High Street')
      expect(result.address2).toBe('Sturminster Marshall')
      expect(result.city).toBe('Wimborne')
      expect(result.county).toBe('Dorset')
      expect(result.postcode).toBe('BH21 4AY')
    })

    it('parses address with building name and locality', () => {
      const address = {
        uprn: '1942014',
        address: 'Sturminster Marshall Pre School, Rear Of 78, High Street, Sturminster Marshall, Wimborne, BH21 4AY',
        building_name: 'Rear Of 78',
        building_number: '',
        thoroughfare: 'High Street',
        dependent_locality: 'Sturminster Marshall',
        post_town: 'Wimborne',
        postcode: 'BH21 4AY',
        county: 'Dorset',
      }

      const result = parseAddress(address)

      expect(result.address1).toBe('Sturminster Marshall Pre School, Rear Of 78, High Street')
      expect(result.address2).toBe('Sturminster Marshall')
      expect(result.city).toBe('Wimborne')
      expect(result.county).toBe('Dorset')
    })
  })

  describe('Urban addresses without dependent_locality', () => {
    it('parses simple numbered address correctly', () => {
      const address = {
        uprn: '1808427',
        address: '6 Ascham Road, Bournemouth, BH8 8LY',
        building_name: '',
        building_number: '6',
        thoroughfare: 'Ascham Road',
        dependent_locality: '',
        post_town: 'Bournemouth',
        postcode: 'BH8 8LY',
        county: 'Dorset',
      }

      const result = parseAddress(address)

      expect(result.address1).toBe('6 Ascham Road')
      expect(result.address2).toBe('')
      expect(result.city).toBe('Bournemouth')
      expect(result.county).toBe('Dorset')
    })

    it('parses flat in named building correctly', () => {
      const address = {
        uprn: '1808422',
        address: '1 Ascham Lodge, 11 Ascham Road, Bournemouth, BH8 8LY',
        building_name: 'Ascham Lodge',
        building_number: '11',
        thoroughfare: 'Ascham Road',
        dependent_locality: '',
        post_town: 'Bournemouth',
        postcode: 'BH8 8LY',
        county: 'Dorset',
      }

      const result = parseAddress(address)

      expect(result.address1).toBe('1 Ascham Lodge, 11 Ascham Road')
      expect(result.address2).toBe('')
      expect(result.city).toBe('Bournemouth')
      expect(result.county).toBe('Dorset')
    })

    it('parses flat with numbered format correctly', () => {
      const address = {
        uprn: '1808416',
        address: 'Flat 1, 13 Ascham Road, Bournemouth, BH8 8LY',
        building_name: 'Flat 1',
        building_number: '13',
        thoroughfare: 'Ascham Road',
        dependent_locality: '',
        post_town: 'Bournemouth',
        postcode: 'BH8 8LY',
        county: 'Dorset',
      }

      const result = parseAddress(address)

      expect(result.address1).toBe('Flat 1, 13 Ascham Road')
      expect(result.address2).toBe('')
      expect(result.city).toBe('Bournemouth')
    })

    it('parses building letter suffix correctly', () => {
      const address = {
        uprn: '1808424',
        address: '11b Ascham Road, Bournemouth, BH8 8LY',
        building_name: '11b',
        building_number: '',
        thoroughfare: 'Ascham Road',
        dependent_locality: '',
        post_town: 'Bournemouth',
        postcode: 'BH8 8LY',
        county: 'Dorset',
      }

      const result = parseAddress(address)

      expect(result.address1).toBe('11b Ascham Road')
      expect(result.address2).toBe('')
      expect(result.city).toBe('Bournemouth')
    })
  })

  describe('Business addresses', () => {
    it('parses business with named premises correctly', () => {
      const address = {
        uprn: '57850413',
        address: 'Post Office, 66 High Street, Sturminster Marshall, Wimborne, BH21 4AY',
        building_name: '',
        building_number: '66',
        thoroughfare: 'High Street',
        dependent_locality: 'Sturminster Marshall',
        post_town: 'Wimborne',
        postcode: 'BH21 4AY',
        county: 'Dorset',
      }

      const result = parseAddress(address)

      expect(result.address1).toBe('Post Office, 66 High Street')
      expect(result.address2).toBe('Sturminster Marshall')
      expect(result.city).toBe('Wimborne')
    })

    it('parses pharmacy correctly', () => {
      const address = {
        uprn: '50867993',
        address: 'Wellbeing Pharmacy, 66 High Street, Sturminster Marshall, Wimborne, BH21 4AY',
        building_name: '',
        building_number: '66',
        thoroughfare: 'High Street',
        dependent_locality: 'Sturminster Marshall',
        post_town: 'Wimborne',
        postcode: 'BH21 4AY',
        county: 'Dorset',
      }

      const result = parseAddress(address)

      expect(result.address1).toBe('Wellbeing Pharmacy, 66 High Street')
      expect(result.address2).toBe('Sturminster Marshall')
      expect(result.city).toBe('Wimborne')
    })
  })

  describe('Edge cases', () => {
    it('handles missing county gracefully', () => {
      const address = {
        uprn: '12345',
        address: '1 Test Street, Test Town, AB1 2CD',
        building_name: '',
        building_number: '1',
        thoroughfare: 'Test Street',
        dependent_locality: '',
        post_town: 'Test Town',
        postcode: 'AB1 2CD',
        county: '',
      }

      const result = parseAddress(address)

      expect(result.county).toBe('')
    })

    it('handles null county gracefully', () => {
      const address = {
        uprn: '12345',
        address: '1 Test Street, Test Town, AB1 2CD',
        building_name: '',
        building_number: '1',
        thoroughfare: 'Test Street',
        dependent_locality: '',
        post_town: 'Test Town',
        postcode: 'AB1 2CD',
        county: null,
      }

      const result = parseAddress(address)

      expect(result.county).toBe('')
    })

    it('handles London addresses correctly', () => {
      const address = {
        uprn: '99999999',
        address: '10 Downing Street, London, SW1A 2AA',
        building_name: '',
        building_number: '10',
        thoroughfare: 'Downing Street',
        dependent_locality: '',
        post_town: 'London',
        postcode: 'SW1A 2AA',
        county: 'London',
      }

      const result = parseAddress(address)

      expect(result.address1).toBe('10 Downing Street')
      expect(result.address2).toBe('')
      expect(result.city).toBe('London')
      expect(result.county).toBe('London')
    })

    it('handles school addresses correctly', () => {
      const address = {
        uprn: '1942013',
        address: 'Sturminster Marshall First School, 78 High Street, Sturminster Marshall, Wimborne, BH21 4AY',
        building_name: '',
        building_number: '78',
        thoroughfare: 'High Street',
        dependent_locality: 'Sturminster Marshall',
        post_town: 'Wimborne',
        postcode: 'BH21 4AY',
        county: 'Dorset',
      }

      const result = parseAddress(address)

      expect(result.address1).toBe('Sturminster Marshall First School, 78 High Street')
      expect(result.address2).toBe('Sturminster Marshall')
      expect(result.city).toBe('Wimborne')
    })
  })
})

// =============================================================================
// API Response Format Tests
// =============================================================================

describe('BookingsNew - Ideal Postcodes API Response Format', () => {
  it('validates expected API response structure', () => {
    const mockApiResponse = {
      success: true,
      postcode: 'BH21 4AY',
      addresses: [
        {
          uprn: '1942015',
          address: '72 High Street, Sturminster Marshall, Wimborne, BH21 4AY',
          building_name: '',
          building_number: '72',
          thoroughfare: 'High Street',
          dependent_locality: 'Sturminster Marshall',
          post_town: 'Wimborne',
          postcode: 'BH21 4AY',
          county: 'Dorset',
        },
      ],
      total_results: 1,
      error: null,
    }

    expect(mockApiResponse.success).toBe(true)
    expect(mockApiResponse.addresses).toHaveLength(1)
    expect(mockApiResponse.addresses[0]).toHaveProperty('uprn')
    expect(mockApiResponse.addresses[0]).toHaveProperty('address')
    expect(mockApiResponse.addresses[0]).toHaveProperty('dependent_locality')
    expect(mockApiResponse.addresses[0]).toHaveProperty('post_town')
    expect(mockApiResponse.addresses[0]).toHaveProperty('county')
  })

  it('validates postcode not found response', () => {
    const mockApiResponse = {
      success: false,
      postcode: 'ZZ99 9ZZ',
      addresses: [],
      total_results: 0,
      error: 'Postcode not found',
    }

    expect(mockApiResponse.success).toBe(false)
    expect(mockApiResponse.addresses).toHaveLength(0)
    expect(mockApiResponse.error).toBe('Postcode not found')
  })
})

// =============================================================================
// Manual Flight Entry and Time Override Tests
// =============================================================================

describe('BookingsNew - Time Format Validation', () => {
  // Helper function that mirrors the isValidTimeFormat logic in BookingsNew.jsx
  const isValidTimeFormat = (timeStr) => {
    if (!timeStr) return false
    return /^\d{1,2}:\d{2}$/.test(timeStr)
  }

  // Helper function that mirrors the normalizeTime logic in BookingsNew.jsx
  const normalizeTime = (timeStr) => {
    if (!timeStr) return ''
    const parts = timeStr.split(':')
    if (parts.length !== 2) return timeStr
    const hours = parts[0].padStart(2, '0')
    const mins = parts[1].padStart(2, '0')
    return `${hours}:${mins}`
  }

  describe('Happy Path - Valid Time Formats', () => {
    it('accepts standard HH:MM format (14:30)', () => {
      expect(isValidTimeFormat('14:30')).toBe(true)
    })

    it('accepts single-digit hour (8:30)', () => {
      expect(isValidTimeFormat('8:30')).toBe(true)
    })

    it('accepts midnight (00:00)', () => {
      expect(isValidTimeFormat('00:00')).toBe(true)
    })

    it('accepts late night (23:59)', () => {
      expect(isValidTimeFormat('23:59')).toBe(true)
    })

    it('accepts early morning (06:00)', () => {
      expect(isValidTimeFormat('06:00')).toBe(true)
    })
  })

  describe('Negative Path - Invalid Time Formats', () => {
    it('rejects empty string', () => {
      expect(isValidTimeFormat('')).toBe(false)
    })

    it('rejects null', () => {
      expect(isValidTimeFormat(null)).toBe(false)
    })

    it('rejects undefined', () => {
      expect(isValidTimeFormat(undefined)).toBe(false)
    })

    it('rejects time without colon', () => {
      expect(isValidTimeFormat('1430')).toBe(false)
    })

    it('rejects time with letters', () => {
      expect(isValidTimeFormat('14:3a')).toBe(false)
    })

    it('rejects AM/PM format', () => {
      expect(isValidTimeFormat('2:30 PM')).toBe(false)
    })

    it('rejects incomplete time', () => {
      expect(isValidTimeFormat('14:')).toBe(false)
    })

    it('rejects time with extra characters', () => {
      expect(isValidTimeFormat('14:30:00')).toBe(false)
    })
  })

  describe('Time Normalization', () => {
    it('normalizes single-digit hour to two digits', () => {
      expect(normalizeTime('8:30')).toBe('08:30')
    })

    it('normalizes 9:05 correctly', () => {
      expect(normalizeTime('9:05')).toBe('09:05')
    })

    it('keeps already normalized time unchanged', () => {
      expect(normalizeTime('14:30')).toBe('14:30')
    })

    it('handles midnight correctly', () => {
      expect(normalizeTime('0:00')).toBe('00:00')
    })

    it('returns empty string for empty input', () => {
      expect(normalizeTime('')).toBe('')
    })

    it('returns original string for invalid format', () => {
      expect(normalizeTime('invalid')).toBe('invalid')
    })
  })
})

describe('BookingsNew - Manual Entry Validation', () => {
  // Helper function that mirrors the isManualDepartureComplete validation
  const isManualDepartureComplete = (data, isValidTimeFormat) => {
    return !!(data.airlineCode &&
      data.flightNumber &&
      isValidTimeFormat(data.flightTime) &&
      data.destinationCode)
  }

  const isManualArrivalComplete = (data, isValidTimeFormat) => {
    return !!(data.airlineCode &&
      data.flightNumber &&
      isValidTimeFormat(data.flightTime) &&
      data.originCode)
  }

  const isValidTimeFormat = (timeStr) => {
    if (!timeStr) return false
    return /^\d{1,2}:\d{2}$/.test(timeStr)
  }

  describe('Happy Path - Complete Manual Departure Entry', () => {
    it('validates complete manual departure data', () => {
      const data = {
        airlineCode: 'BY',
        airlineName: 'TUI',
        flightNumber: '1234',
        flightTime: '14:30',
        destinationCode: 'FAO',
        destinationName: 'Faro, Portugal'
      }
      expect(isManualDepartureComplete(data, isValidTimeFormat)).toBe(true)
    })

    it('validates Ryanair manual entry', () => {
      const data = {
        airlineCode: 'FR',
        airlineName: 'Ryanair',
        flightNumber: '9876',
        flightTime: '06:00',
        destinationCode: 'AGP',
        destinationName: 'Malaga, Spain'
      }
      expect(isManualDepartureComplete(data, isValidTimeFormat)).toBe(true)
    })
  })

  describe('Happy Path - Complete Manual Arrival Entry', () => {
    it('validates complete manual arrival data', () => {
      const data = {
        airlineCode: 'BY',
        airlineName: 'TUI',
        flightNumber: '1235',
        flightTime: '23:35',
        originCode: 'FAO',
        originName: 'Faro, Portugal'
      }
      expect(isManualArrivalComplete(data, isValidTimeFormat)).toBe(true)
    })
  })

  describe('Negative Path - Incomplete Manual Entry', () => {
    it('fails when airline code is missing', () => {
      const data = {
        airlineCode: '',
        flightNumber: '1234',
        flightTime: '14:30',
        destinationCode: 'FAO'
      }
      expect(isManualDepartureComplete(data, isValidTimeFormat)).toBe(false)
    })

    it('fails when flight number is missing', () => {
      const data = {
        airlineCode: 'BY',
        flightNumber: '',
        flightTime: '14:30',
        destinationCode: 'FAO'
      }
      expect(isManualDepartureComplete(data, isValidTimeFormat)).toBe(false)
    })

    it('fails when flight time is missing', () => {
      const data = {
        airlineCode: 'BY',
        flightNumber: '1234',
        flightTime: '',
        destinationCode: 'FAO'
      }
      expect(isManualDepartureComplete(data, isValidTimeFormat)).toBe(false)
    })

    it('fails when flight time is invalid format', () => {
      const data = {
        airlineCode: 'BY',
        flightNumber: '1234',
        flightTime: '14.30',
        destinationCode: 'FAO'
      }
      expect(isManualDepartureComplete(data, isValidTimeFormat)).toBe(false)
    })

    it('fails when destination code is missing', () => {
      const data = {
        airlineCode: 'BY',
        flightNumber: '1234',
        flightTime: '14:30',
        destinationCode: ''
      }
      expect(isManualDepartureComplete(data, isValidTimeFormat)).toBe(false)
    })
  })

  describe('Edge Cases - Overnight Flights', () => {
    it('accepts late evening departure (22:50)', () => {
      const data = {
        airlineCode: 'FR',
        airlineName: 'Ryanair',
        flightNumber: '5678',
        flightTime: '22:50',
        destinationCode: 'TFS',
        destinationName: 'Tenerife, Spain'
      }
      expect(isManualDepartureComplete(data, isValidTimeFormat)).toBe(true)
    })

    it('accepts early morning arrival (00:50)', () => {
      const data = {
        airlineCode: 'FR',
        airlineName: 'Ryanair',
        flightNumber: '5679',
        flightTime: '00:50',
        originCode: 'TFS',
        originName: 'Tenerife, Spain'
      }
      expect(isManualArrivalComplete(data, isValidTimeFormat)).toBe(true)
    })

    it('accepts late night arrival (23:35)', () => {
      const data = {
        airlineCode: 'BY',
        airlineName: 'TUI',
        flightNumber: '1111',
        flightTime: '23:35',
        originCode: 'FAO',
        originName: 'Faro, Portugal'
      }
      expect(isManualArrivalComplete(data, isValidTimeFormat)).toBe(true)
    })
  })
})

describe('BookingsNew - Step 2 Completion Logic', () => {
  // Mirrors the isStep2Complete logic from BookingsNew.jsx
  const isStep2Complete = (formData, showManualDeparture, manualDepartureData, showManualArrival, manualArrivalData) => {
    const isValidTimeFormat = (timeStr) => {
      if (!timeStr) return false
      return /^\d{1,2}:\d{2}$/.test(timeStr)
    }

    const isManualDepartureComplete = !!(showManualDeparture &&
      manualDepartureData.airlineCode &&
      manualDepartureData.flightNumber &&
      isValidTimeFormat(manualDepartureData.flightTime) &&
      manualDepartureData.destinationCode)

    const isManualArrivalComplete = !!(showManualArrival &&
      manualArrivalData.airlineCode &&
      manualArrivalData.flightNumber &&
      isValidTimeFormat(manualArrivalData.flightTime) &&
      manualArrivalData.originCode)

    const isNormalDepartureComplete = !!(!showManualDeparture && formData.dropoffAirline && formData.dropoffFlight && formData.dropoffSlot)
    const isDepartureComplete = isNormalDepartureComplete || isManualDepartureComplete

    const isNormalArrivalComplete = !!(!showManualArrival && formData.pickupFlightTime)
    const isArrivalComplete = isNormalArrivalComplete || isManualArrivalComplete

    return !!(formData.dropoffDate && isDepartureComplete && formData.pickupDate && isArrivalComplete)
  }

  describe('Normal Flow (No Manual Entry)', () => {
    it('completes with normal flight selection', () => {
      const formData = {
        dropoffDate: new Date('2026-03-15'),
        dropoffAirline: 'Ryanair',
        dropoffFlight: '14:30|FAO',
        dropoffSlot: '165',
        pickupDate: new Date('2026-03-22'),
        pickupFlightTime: '18:00|1234'
      }
      const result = isStep2Complete(formData, false, {}, false, {})
      expect(result).toBe(true)
    })

    it('fails without dropoff date', () => {
      const formData = {
        dropoffDate: null,
        dropoffAirline: 'Ryanair',
        dropoffFlight: '14:30|FAO',
        dropoffSlot: '165',
        pickupDate: new Date('2026-03-22'),
        pickupFlightTime: '18:00|1234'
      }
      const result = isStep2Complete(formData, false, {}, false, {})
      expect(result).toBe(false)
    })

    it('fails without pickup date', () => {
      const formData = {
        dropoffDate: new Date('2026-03-15'),
        dropoffAirline: 'Ryanair',
        dropoffFlight: '14:30|FAO',
        dropoffSlot: '165',
        pickupDate: null,
        pickupFlightTime: '18:00|1234'
      }
      const result = isStep2Complete(formData, false, {}, false, {})
      expect(result).toBe(false)
    })
  })

  describe('Manual Departure Entry Flow', () => {
    it('completes with manual departure and normal arrival', () => {
      const formData = {
        dropoffDate: new Date('2026-03-15'),
        dropoffAirline: '',
        dropoffFlight: '',
        dropoffSlot: '',
        pickupDate: new Date('2026-03-22'),
        pickupFlightTime: '18:00|1234'
      }
      const manualDepartureData = {
        airlineCode: 'BY',
        flightNumber: '1234',
        flightTime: '14:30',
        destinationCode: 'FAO'
      }
      const result = isStep2Complete(formData, true, manualDepartureData, false, {})
      expect(result).toBe(true)
    })
  })

  describe('Manual Arrival Entry Flow', () => {
    it('completes with normal departure and manual arrival', () => {
      const formData = {
        dropoffDate: new Date('2026-03-15'),
        dropoffAirline: 'Ryanair',
        dropoffFlight: '14:30|FAO',
        dropoffSlot: '165',
        pickupDate: new Date('2026-03-22'),
        pickupFlightTime: ''
      }
      const manualArrivalData = {
        airlineCode: 'FR',
        flightNumber: '5678',
        flightTime: '18:00',
        originCode: 'FAO'
      }
      const result = isStep2Complete(formData, false, {}, true, manualArrivalData)
      expect(result).toBe(true)
    })
  })

  describe('Both Manual Entry Flow', () => {
    it('completes with both manual departure and manual arrival', () => {
      const formData = {
        dropoffDate: new Date('2026-03-15'),
        dropoffAirline: '',
        dropoffFlight: '',
        dropoffSlot: '',
        pickupDate: new Date('2026-03-22'),
        pickupFlightTime: ''
      }
      const manualDepartureData = {
        airlineCode: 'BY',
        flightNumber: '1234',
        flightTime: '14:30',
        destinationCode: 'FAO'
      }
      const manualArrivalData = {
        airlineCode: 'BY',
        flightNumber: '1235',
        flightTime: '18:00',
        originCode: 'FAO'
      }
      const result = isStep2Complete(formData, true, manualDepartureData, true, manualArrivalData)
      expect(result).toBe(true)
    })
  })
})

describe('BookingsNew - Stripe Payment Data Format', () => {
  // Mirrors the payment data formatting in StripePayment.jsx
  const formatPaymentData = (formData, selectedFlight, selectedArrivalFlight, manualDepartureData, manualArrivalData, departureTimeOverride, arrivalTimeOverride) => {
    // Only flag as override if time actually differs from scheduled
    const isActualDepartureOverride = !!departureTimeOverride && departureTimeOverride !== (selectedFlight?.time || '')
    const isActualArrivalOverride = !!arrivalTimeOverride && arrivalTimeOverride !== (selectedArrivalFlight?.time || '')

    return {
      flight_number: manualDepartureData?.flightNumber || selectedFlight?.flightNumber || 'Unknown',
      departure_id: manualDepartureData ? null : (selectedFlight?.id || null),
      drop_off_slot: manualDepartureData ? null : (formData.dropoffSlot || null),
      arrival_id: manualArrivalData ? null : (selectedArrivalFlight?.id || null),
      pickup_flight_time: manualArrivalData?.flightTime || selectedArrivalFlight?.time || null,
      pickup_flight_number: manualArrivalData?.flightNumber || selectedArrivalFlight?.flightNumber || null,
      dropoff_time_override: isActualDepartureOverride,
      dropoff_scheduled_time: isActualDepartureOverride ? (selectedFlight?.time || null) : null,
      dropoff_manual_entry: !!manualDepartureData,
      dropoff_airline_code: manualDepartureData?.airlineCode || null,
      dropoff_airline_name: manualDepartureData?.airlineName || null,
      pickup_time_override: isActualArrivalOverride,
      pickup_scheduled_time: isActualArrivalOverride ? (selectedArrivalFlight?.time || null) : null,
      pickup_manual_entry: !!manualArrivalData,
      pickup_airline_code: manualArrivalData?.airlineCode || null,
      pickup_airline_name: manualArrivalData?.airlineName || null,
    }
  }

  describe('Normal Flow - No Overrides', () => {
    it('formats data correctly for normal booking', () => {
      const formData = { dropoffSlot: '165' }
      const selectedFlight = { id: 123, flightNumber: '1234', time: '14:30' }
      const selectedArrivalFlight = { id: 456, flightNumber: '5678', time: '18:00' }

      const result = formatPaymentData(formData, selectedFlight, selectedArrivalFlight, null, null, '', '')

      expect(result.flight_number).toBe('1234')
      expect(result.departure_id).toBe(123)
      expect(result.drop_off_slot).toBe('165')
      expect(result.arrival_id).toBe(456)
      expect(result.dropoff_time_override).toBe(false)
      expect(result.dropoff_manual_entry).toBe(false)
      expect(result.pickup_time_override).toBe(false)
      expect(result.pickup_manual_entry).toBe(false)
    })
  })

  describe('Time Override Flow', () => {
    it('formats data correctly when departure time is overridden', () => {
      const formData = { dropoffSlot: '165' }
      const selectedFlight = { id: 123, flightNumber: '1234', time: '14:30' }
      const selectedArrivalFlight = { id: 456, flightNumber: '5678', time: '18:00' }

      const result = formatPaymentData(formData, selectedFlight, selectedArrivalFlight, null, null, '15:00', '')

      expect(result.dropoff_time_override).toBe(true)
      expect(result.dropoff_scheduled_time).toBe('14:30')
      expect(result.dropoff_manual_entry).toBe(false)
    })

    it('formats data correctly when arrival time is overridden', () => {
      const formData = { dropoffSlot: '165' }
      const selectedFlight = { id: 123, flightNumber: '1234', time: '14:30' }
      const selectedArrivalFlight = { id: 456, flightNumber: '5678', time: '18:00' }

      const result = formatPaymentData(formData, selectedFlight, selectedArrivalFlight, null, null, '', '19:00')

      expect(result.pickup_time_override).toBe(true)
      expect(result.pickup_scheduled_time).toBe('18:00')
      expect(result.pickup_manual_entry).toBe(false)
    })

    it('does not flag override when time matches scheduled', () => {
      const formData = { dropoffSlot: '165' }
      const selectedFlight = { id: 123, flightNumber: '1234', time: '14:30' }
      const selectedArrivalFlight = { id: 456, flightNumber: '5678', time: '18:00' }

      const result = formatPaymentData(formData, selectedFlight, selectedArrivalFlight, null, null, '14:30', '')

      expect(result.dropoff_time_override).toBe(false)
      expect(result.dropoff_scheduled_time).toBe(null)
    })
  })

  describe('Manual Entry Flow', () => {
    it('formats data correctly for manual departure entry', () => {
      const formData = { dropoffSlot: '' }
      const selectedFlight = null
      const selectedArrivalFlight = { id: 456, flightNumber: '5678', time: '18:00' }
      const manualDepartureData = {
        airlineCode: 'BY',
        airlineName: 'TUI',
        flightNumber: '9999',
        flightTime: '10:30',
        destinationCode: 'FAO',
        destinationName: 'Faro, Portugal'
      }

      const result = formatPaymentData(formData, selectedFlight, selectedArrivalFlight, manualDepartureData, null, '', '')

      expect(result.flight_number).toBe('9999')
      expect(result.departure_id).toBe(null)
      expect(result.drop_off_slot).toBe(null)
      expect(result.dropoff_manual_entry).toBe(true)
      expect(result.dropoff_airline_code).toBe('BY')
      expect(result.dropoff_airline_name).toBe('TUI')
    })

    it('formats data correctly for manual arrival entry', () => {
      const formData = { dropoffSlot: '165' }
      const selectedFlight = { id: 123, flightNumber: '1234', time: '14:30' }
      const selectedArrivalFlight = null
      const manualArrivalData = {
        airlineCode: 'FR',
        airlineName: 'Ryanair',
        flightNumber: '7777',
        flightTime: '20:00',
        originCode: 'AGP',
        originName: 'Malaga, Spain'
      }

      const result = formatPaymentData(formData, selectedFlight, selectedArrivalFlight, null, manualArrivalData, '', '')

      expect(result.arrival_id).toBe(null)
      expect(result.pickup_flight_number).toBe('7777')
      expect(result.pickup_flight_time).toBe('20:00')
      expect(result.pickup_manual_entry).toBe(true)
      expect(result.pickup_airline_code).toBe('FR')
      expect(result.pickup_airline_name).toBe('Ryanair')
    })
  })
})

// =============================================================================
// Flight Dropdown Display with Time Override Tests
// =============================================================================

describe('BookingsNew - Flight Dropdown Display with Time Override', () => {
  // Helper function that mirrors the flightsForDropoff useMemo logic
  const buildFlightsForDropoff = (flightsForAirline, departureTimeOverride, selectedFlightKey) => {
    const countryNames = {
      'PT': 'Portugal',
      'ES': 'Spain',
      'IT': 'Italy',
      'GR': 'Greece',
      'GB': 'United Kingdom',
      'FR': 'France'
    }

    return flightsForAirline.map(f => {
      // Parse destinationName to extract city and country code
      const parts = f.destinationName.split(', ')
      let displayDestination = f.destinationName
      if (parts.length > 1) {
        const countryCode = parts[parts.length - 1]
        let cityName = parts.slice(0, -1).join(', ')
        if (cityName === 'Tenerife-Reinasofia') cityName = 'Tenerife'
        const countryName = countryNames[countryCode] || countryCode
        displayDestination = `${cityName}, ${countryName}`
      }

      const flightKey = `${f.time}|${f.destinationCode}`

      // Use overridden time for the currently selected flight
      const isSelected = selectedFlightKey === flightKey
      const displayTime = (isSelected && departureTimeOverride) ? departureTimeOverride : f.time

      return {
        ...f,
        flightKey,
        displayText: `${displayTime} ${f.airlineCode}${f.flightNumber} → ${displayDestination}`
      }
    }).sort((a, b) => a.time.localeCompare(b.time))
  }

  const mockFlights = [
    {
      id: 1,
      time: '06:45',
      airlineCode: 'FR',
      flightNumber: '3944',
      destinationCode: 'FAO',
      destinationName: 'Faro, PT',
      capacity_tier: 4
    },
    {
      id: 2,
      time: '08:30',
      airlineCode: 'FR',
      flightNumber: '1234',
      destinationCode: 'AGP',
      destinationName: 'Malaga, ES',
      capacity_tier: 6
    },
    {
      id: 3,
      time: '14:00',
      airlineCode: 'FR',
      flightNumber: '5678',
      destinationCode: 'TFS',
      destinationName: 'Tenerife-Reinasofia, ES',
      capacity_tier: 4
    }
  ]

  describe('Without Time Override', () => {
    it('displays original scheduled time for all flights', () => {
      const result = buildFlightsForDropoff(mockFlights, '', null)

      expect(result[0].displayText).toBe('06:45 FR3944 → Faro, Portugal')
      expect(result[1].displayText).toBe('08:30 FR1234 → Malaga, Spain')
      expect(result[2].displayText).toBe('14:00 FR5678 → Tenerife, Spain')
    })

    it('displays original time when no flight is selected', () => {
      const result = buildFlightsForDropoff(mockFlights, '07:00', null)

      // No flight selected, so even with override set, all should show original times
      expect(result[0].displayText).toBe('06:45 FR3944 → Faro, Portugal')
      expect(result[1].displayText).toBe('08:30 FR1234 → Malaga, Spain')
    })
  })

  describe('With Time Override', () => {
    it('displays overridden time only for the selected flight', () => {
      const selectedFlightKey = '06:45|FAO'
      const result = buildFlightsForDropoff(mockFlights, '07:00', selectedFlightKey)

      // Selected flight shows overridden time
      expect(result[0].displayText).toBe('07:00 FR3944 → Faro, Portugal')
      // Other flights show original times
      expect(result[1].displayText).toBe('08:30 FR1234 → Malaga, Spain')
      expect(result[2].displayText).toBe('14:00 FR5678 → Tenerife, Spain')
    })

    it('updates display when different flight is selected with override', () => {
      const selectedFlightKey = '14:00|TFS'
      const result = buildFlightsForDropoff(mockFlights, '15:30', selectedFlightKey)

      // First two flights show original times
      expect(result[0].displayText).toBe('06:45 FR3944 → Faro, Portugal')
      expect(result[1].displayText).toBe('08:30 FR1234 → Malaga, Spain')
      // Selected flight shows overridden time
      expect(result[2].displayText).toBe('15:30 FR5678 → Tenerife, Spain')
    })

    it('shows original time when override is cleared', () => {
      const selectedFlightKey = '06:45|FAO'
      const result = buildFlightsForDropoff(mockFlights, '', selectedFlightKey)

      // All flights show original times when override is empty
      expect(result[0].displayText).toBe('06:45 FR3944 → Faro, Portugal')
      expect(result[1].displayText).toBe('08:30 FR1234 → Malaga, Spain')
    })
  })

  describe('Edge Cases', () => {
    it('handles early morning time override (before midnight)', () => {
      const selectedFlightKey = '06:45|FAO'
      const result = buildFlightsForDropoff(mockFlights, '05:00', selectedFlightKey)

      expect(result[0].displayText).toBe('05:00 FR3944 → Faro, Portugal')
    })

    it('handles late evening time override', () => {
      const selectedFlightKey = '14:00|TFS'
      const result = buildFlightsForDropoff(mockFlights, '23:30', selectedFlightKey)

      expect(result[2].displayText).toBe('23:30 FR5678 → Tenerife, Spain')
    })

    it('handles single-digit hour override', () => {
      const selectedFlightKey = '06:45|FAO'
      const result = buildFlightsForDropoff(mockFlights, '7:00', selectedFlightKey)

      expect(result[0].displayText).toBe('7:00 FR3944 → Faro, Portugal')
    })

    it('preserves original flight data properties', () => {
      const selectedFlightKey = '06:45|FAO'
      const result = buildFlightsForDropoff(mockFlights, '07:00', selectedFlightKey)

      // displayText shows override, but original time is preserved
      expect(result[0].time).toBe('06:45')
      expect(result[0].id).toBe(1)
      expect(result[0].capacity_tier).toBe(4)
    })

    it('shortens Tenerife-Reinasofia to Tenerife', () => {
      const result = buildFlightsForDropoff(mockFlights, '', null)

      const tenerifeFlight = result.find(f => f.destinationCode === 'TFS')
      expect(tenerifeFlight.displayText).toContain('Tenerife, Spain')
      expect(tenerifeFlight.displayText).not.toContain('Reinasofia')
    })
  })
})

// =============================================================================
// Drop-off Slot Calculation with Time Override Tests
// =============================================================================

describe('BookingsNew - Dropoff Slot Calculation with Time Override', () => {
  // Helper function that mirrors formatMinutesToTime in BookingsNew.jsx
  const formatMinutesToTime = (totalMinutes) => {
    let mins = totalMinutes
    while (mins < 0) mins += 1440
    while (mins >= 1440) mins -= 1440
    const h = Math.floor(mins / 60)
    const m = mins % 60
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`
  }

  // Helper function that mirrors dropoffSlots useMemo logic
  const calculateDropoffSlots = (selectedFlight, departureTimeOverride, isCallUsOnly = false) => {
    if (!selectedFlight) return []
    if (isCallUsOnly) return []

    // Use overridden time if set, otherwise use scheduled flight time
    const effectiveTime = departureTimeOverride || selectedFlight.time
    const [hours, minutes] = effectiveTime.split(':').map(Number)
    const departureMinutes = hours * 60 + minutes

    const slots = []

    // Early slot: 2¾ hours before (165 minutes)
    const earlyAvailable = selectedFlight.early_slots_available ?? 1
    if (earlyAvailable > 0) {
      slots.push({
        id: '165',
        label: '2¾ hours before',
        time: formatMinutesToTime(departureMinutes - 165),
        available: earlyAvailable
      })
    }

    // Late slot: 2 hours before (120 minutes)
    const lateAvailable = selectedFlight.late_slots_available ?? 1
    if (lateAvailable > 0) {
      slots.push({
        id: '120',
        label: '2 hours before',
        time: formatMinutesToTime(departureMinutes - 120),
        available: lateAvailable
      })
    }

    return slots
  }

  const mockFlight = {
    id: 1,
    time: '14:30',
    airlineCode: 'FR',
    flightNumber: '1234',
    destinationCode: 'FAO',
    early_slots_available: 2,
    late_slots_available: 2
  }

  describe('Without Time Override', () => {
    it('calculates slots based on scheduled departure time', () => {
      const slots = calculateDropoffSlots(mockFlight, '')

      // 14:30 - 165 minutes = 11:45
      expect(slots[0].time).toBe('11:45')
      // 14:30 - 120 minutes = 12:30
      expect(slots[1].time).toBe('12:30')
    })

    it('calculates early morning slots correctly', () => {
      const earlyFlight = { ...mockFlight, time: '06:00' }
      const slots = calculateDropoffSlots(earlyFlight, '')

      // 06:00 - 165 minutes = 03:15
      expect(slots[0].time).toBe('03:15')
      // 06:00 - 120 minutes = 04:00
      expect(slots[1].time).toBe('04:00')
    })

    it('calculates late evening slots correctly', () => {
      const lateFlight = { ...mockFlight, time: '22:00' }
      const slots = calculateDropoffSlots(lateFlight, '')

      // 22:00 - 165 minutes = 19:15
      expect(slots[0].time).toBe('19:15')
      // 22:00 - 120 minutes = 20:00
      expect(slots[1].time).toBe('20:00')
    })
  })

  describe('With Time Override', () => {
    it('calculates slots based on overridden time', () => {
      const slots = calculateDropoffSlots(mockFlight, '15:00')

      // 15:00 - 165 minutes = 12:15
      expect(slots[0].time).toBe('12:15')
      // 15:00 - 120 minutes = 13:00
      expect(slots[1].time).toBe('13:00')
    })

    it('recalculates when time is moved earlier', () => {
      const slots = calculateDropoffSlots(mockFlight, '12:00')

      // 12:00 - 165 minutes = 09:15
      expect(slots[0].time).toBe('09:15')
      // 12:00 - 120 minutes = 10:00
      expect(slots[1].time).toBe('10:00')
    })

    it('recalculates when time is moved later', () => {
      const slots = calculateDropoffSlots(mockFlight, '18:30')

      // 18:30 - 165 minutes = 15:45
      expect(slots[0].time).toBe('15:45')
      // 18:30 - 120 minutes = 16:30
      expect(slots[1].time).toBe('16:30')
    })

    it('handles early morning override correctly', () => {
      const slots = calculateDropoffSlots(mockFlight, '07:00')

      // 07:00 - 165 minutes = 04:15
      expect(slots[0].time).toBe('04:15')
      // 07:00 - 120 minutes = 05:00
      expect(slots[1].time).toBe('05:00')
    })
  })

  describe('Edge Cases - Overnight Calculations', () => {
    it('handles slots that cross midnight (early morning flight)', () => {
      const earlyFlight = { ...mockFlight, time: '02:00' }
      const slots = calculateDropoffSlots(earlyFlight, '')

      // 02:00 - 165 minutes = 23:15 (previous day)
      expect(slots[0].time).toBe('23:15')
      // 02:00 - 120 minutes = 00:00
      expect(slots[1].time).toBe('00:00')
    })

    it('handles override that creates overnight slots', () => {
      const slots = calculateDropoffSlots(mockFlight, '01:30')

      // 01:30 - 165 minutes = 22:45 (previous day)
      expect(slots[0].time).toBe('22:45')
      // 01:30 - 120 minutes = 23:30 (previous day)
      expect(slots[1].time).toBe('23:30')
    })
  })

  describe('Slot Availability', () => {
    it('returns empty array when flight is null', () => {
      const slots = calculateDropoffSlots(null, '')
      expect(slots).toEqual([])
    })

    it('returns empty array for Call Us Only flights', () => {
      const slots = calculateDropoffSlots(mockFlight, '', true)
      expect(slots).toEqual([])
    })

    it('excludes early slot when unavailable', () => {
      const noEarlyFlight = { ...mockFlight, early_slots_available: 0 }
      const slots = calculateDropoffSlots(noEarlyFlight, '')

      expect(slots).toHaveLength(1)
      expect(slots[0].id).toBe('120')
    })

    it('excludes late slot when unavailable', () => {
      const noLateFlight = { ...mockFlight, late_slots_available: 0 }
      const slots = calculateDropoffSlots(noLateFlight, '')

      expect(slots).toHaveLength(1)
      expect(slots[0].id).toBe('165')
    })

    it('returns empty array when both slots unavailable', () => {
      const fullyBookedFlight = {
        ...mockFlight,
        early_slots_available: 0,
        late_slots_available: 0
      }
      const slots = calculateDropoffSlots(fullyBookedFlight, '')

      expect(slots).toEqual([])
    })
  })

  describe('Time Format Handling', () => {
    it('handles single-digit hour in override', () => {
      const slots = calculateDropoffSlots(mockFlight, '8:30')

      // 8:30 - 165 minutes = 05:45
      expect(slots[0].time).toBe('05:45')
      // 8:30 - 120 minutes = 06:30
      expect(slots[1].time).toBe('06:30')
    })

    it('outputs times with leading zeros', () => {
      const earlyFlight = { ...mockFlight, time: '05:00' }
      const slots = calculateDropoffSlots(earlyFlight, '')

      expect(slots[0].time).toBe('02:15')
      expect(slots[1].time).toBe('03:00')
    })
  })
})

// =============================================================================
// Integration Tests - Time Override End-to-End Flow
// =============================================================================

describe('BookingsNew - Time Override Integration', () => {
  // Simulates the full flow of selecting a flight, overriding time, and verifying outputs

  const countryNames = {
    'PT': 'Portugal',
    'ES': 'Spain'
  }

  const formatMinutesToTime = (totalMinutes) => {
    let mins = totalMinutes
    while (mins < 0) mins += 1440
    while (mins >= 1440) mins -= 1440
    const h = Math.floor(mins / 60)
    const m = mins % 60
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`
  }

  const buildFlightsForDropdown = (flights, override, selectedKey) => {
    return flights.map(f => {
      const parts = f.destinationName.split(', ')
      let displayDestination = f.destinationName
      if (parts.length > 1) {
        const countryCode = parts[parts.length - 1]
        const cityName = parts.slice(0, -1).join(', ')
        const countryName = countryNames[countryCode] || countryCode
        displayDestination = `${cityName}, ${countryName}`
      }

      const flightKey = `${f.time}|${f.destinationCode}`
      const isSelected = selectedKey === flightKey
      const displayTime = (isSelected && override) ? override : f.time

      return {
        ...f,
        flightKey,
        displayText: `${displayTime} ${f.airlineCode}${f.flightNumber} → ${displayDestination}`
      }
    })
  }

  const calculateDropoffSlots = (flight, override) => {
    if (!flight) return []
    const effectiveTime = override || flight.time
    const [hours, minutes] = effectiveTime.split(':').map(Number)
    const departureMinutes = hours * 60 + minutes

    return [
      { id: '165', time: formatMinutesToTime(departureMinutes - 165) },
      { id: '120', time: formatMinutesToTime(departureMinutes - 120) }
    ]
  }

  it('simulates complete time override flow', () => {
    // Step 1: Initial state - flights loaded
    const flights = [
      {
        id: 101,
        time: '06:45',
        airlineCode: 'FR',
        flightNumber: '3944',
        destinationCode: 'FAO',
        destinationName: 'Faro, PT'
      }
    ]

    // Step 2: User selects flight
    const selectedFlightKey = '06:45|FAO'
    let departureTimeOverride = ''

    // Verify initial state
    let dropdownFlights = buildFlightsForDropdown(flights, departureTimeOverride, selectedFlightKey)
    let slots = calculateDropoffSlots(flights[0], departureTimeOverride)

    expect(dropdownFlights[0].displayText).toBe('06:45 FR3944 → Faro, Portugal')
    expect(slots[0].time).toBe('04:00') // 06:45 - 165 = 04:00
    expect(slots[1].time).toBe('04:45') // 06:45 - 120 = 04:45

    // Step 3: User clicks "My flight time has changed" and enters new time
    departureTimeOverride = '07:00'

    // Verify updated state
    dropdownFlights = buildFlightsForDropdown(flights, departureTimeOverride, selectedFlightKey)
    slots = calculateDropoffSlots(flights[0], departureTimeOverride)

    expect(dropdownFlights[0].displayText).toBe('07:00 FR3944 → Faro, Portugal')
    expect(slots[0].time).toBe('04:15') // 07:00 - 165 = 04:15
    expect(slots[1].time).toBe('05:00') // 07:00 - 120 = 05:00

    // Step 4: User changes time again
    departureTimeOverride = '08:30'

    dropdownFlights = buildFlightsForDropdown(flights, departureTimeOverride, selectedFlightKey)
    slots = calculateDropoffSlots(flights[0], departureTimeOverride)

    expect(dropdownFlights[0].displayText).toBe('08:30 FR3944 → Faro, Portugal')
    expect(slots[0].time).toBe('05:45') // 08:30 - 165 = 05:45
    expect(slots[1].time).toBe('06:30') // 08:30 - 120 = 06:30

    // Step 5: User clears override (reverts to scheduled time)
    departureTimeOverride = ''

    dropdownFlights = buildFlightsForDropdown(flights, departureTimeOverride, selectedFlightKey)
    slots = calculateDropoffSlots(flights[0], departureTimeOverride)

    expect(dropdownFlights[0].displayText).toBe('06:45 FR3944 → Faro, Portugal')
    expect(slots[0].time).toBe('04:00')
    expect(slots[1].time).toBe('04:45')
  })

  it('verifies dropdown and slots stay in sync', () => {
    const flight = {
      id: 200,
      time: '14:30',
      airlineCode: 'U2',
      flightNumber: '8888',
      destinationCode: 'AGP',
      destinationName: 'Malaga, ES'
    }
    const flights = [flight]
    const selectedFlightKey = '14:30|AGP'

    // Test multiple time overrides to ensure consistency
    const testCases = [
      { override: '', expectedDisplay: '14:30', expectedEarly: '11:45', expectedLate: '12:30' },
      { override: '15:00', expectedDisplay: '15:00', expectedEarly: '12:15', expectedLate: '13:00' },
      { override: '12:00', expectedDisplay: '12:00', expectedEarly: '09:15', expectedLate: '10:00' },
      { override: '06:00', expectedDisplay: '06:00', expectedEarly: '03:15', expectedLate: '04:00' },
      { override: '23:00', expectedDisplay: '23:00', expectedEarly: '20:15', expectedLate: '21:00' }
    ]

    testCases.forEach(({ override, expectedDisplay, expectedEarly, expectedLate }) => {
      const dropdownFlights = buildFlightsForDropdown(flights, override, selectedFlightKey)
      const slots = calculateDropoffSlots(flight, override)

      expect(dropdownFlights[0].displayText).toContain(expectedDisplay)
      expect(slots[0].time).toBe(expectedEarly)
      expect(slots[1].time).toBe(expectedLate)
    })
  })

  it('handles multiple flights with only selected one showing override', () => {
    const flights = [
      { id: 1, time: '06:00', airlineCode: 'FR', flightNumber: '1111', destinationCode: 'FAO', destinationName: 'Faro, PT' },
      { id: 2, time: '10:00', airlineCode: 'FR', flightNumber: '2222', destinationCode: 'AGP', destinationName: 'Malaga, ES' },
      { id: 3, time: '14:00', airlineCode: 'FR', flightNumber: '3333', destinationCode: 'FAO', destinationName: 'Faro, PT' }
    ]

    const selectedFlightKey = '10:00|AGP'
    const override = '11:30'

    const dropdownFlights = buildFlightsForDropdown(flights, override, selectedFlightKey)

    // Only the selected flight (10:00|AGP) should show the override
    expect(dropdownFlights[0].displayText).toContain('06:00') // Not selected
    expect(dropdownFlights[1].displayText).toContain('11:30') // Selected - shows override
    expect(dropdownFlights[2].displayText).toContain('14:00') // Not selected
  })
})

// =============================================================================
// Manual Departure Slot Selection Tests
// =============================================================================

describe('BookingsNew - Manual Departure Slot Calculation', () => {
  // Helper that mirrors formatMinutesToTime in BookingsNew.jsx
  const formatMinutesToTime = (totalMinutes) => {
    let mins = totalMinutes
    while (mins < 0) mins += 1440
    while (mins >= 1440) mins -= 1440
    const h = Math.floor(mins / 60)
    const m = mins % 60
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`
  }

  // Helper that mirrors isValidTimeFormat in BookingsNew.jsx
  const isValidTimeFormat = (timeStr) => {
    if (!timeStr) return false
    return /^\d{1,2}:\d{2}$/.test(timeStr)
  }

  // Helper that mirrors manualDropoffSlots useMemo logic
  const calculateManualDropoffSlots = (showManualDeparture, flightTime) => {
    if (!showManualDeparture) return []
    if (!isValidTimeFormat(flightTime)) return []

    const [hours, minutes] = flightTime.split(':').map(Number)
    const departureMinutes = hours * 60 + minutes

    return [
      {
        id: '165',
        label: '2¾ hours before',
        time: formatMinutesToTime(departureMinutes - 165)
      },
      {
        id: '120',
        label: '2 hours before',
        time: formatMinutesToTime(departureMinutes - 120)
      }
    ]
  }

  describe('Slot Generation', () => {
    it('returns empty array when manual departure is not shown', () => {
      const slots = calculateManualDropoffSlots(false, '14:30')
      expect(slots).toEqual([])
    })

    it('returns empty array when flight time is empty', () => {
      const slots = calculateManualDropoffSlots(true, '')
      expect(slots).toEqual([])
    })

    it('returns empty array when flight time is invalid', () => {
      const slots = calculateManualDropoffSlots(true, 'invalid')
      expect(slots).toEqual([])
    })

    it('generates both slots for valid time', () => {
      const slots = calculateManualDropoffSlots(true, '14:30')

      expect(slots).toHaveLength(2)
      expect(slots[0].id).toBe('165')
      expect(slots[0].label).toBe('2¾ hours before')
      expect(slots[1].id).toBe('120')
      expect(slots[1].label).toBe('2 hours before')
    })

    it('calculates correct slot times for afternoon departure', () => {
      const slots = calculateManualDropoffSlots(true, '14:30')

      // 14:30 - 165 min = 11:45
      expect(slots[0].time).toBe('11:45')
      // 14:30 - 120 min = 12:30
      expect(slots[1].time).toBe('12:30')
    })

    it('calculates correct slot times for morning departure', () => {
      const slots = calculateManualDropoffSlots(true, '08:00')

      // 08:00 - 165 min = 05:15
      expect(slots[0].time).toBe('05:15')
      // 08:00 - 120 min = 06:00
      expect(slots[1].time).toBe('06:00')
    })

    it('calculates correct slot times for early morning departure', () => {
      const slots = calculateManualDropoffSlots(true, '06:00')

      // 06:00 - 165 min = 03:15
      expect(slots[0].time).toBe('03:15')
      // 06:00 - 120 min = 04:00
      expect(slots[1].time).toBe('04:00')
    })

    it('calculates correct slot times for evening departure', () => {
      const slots = calculateManualDropoffSlots(true, '20:00')

      // 20:00 - 165 min = 17:15
      expect(slots[0].time).toBe('17:15')
      // 20:00 - 120 min = 18:00
      expect(slots[1].time).toBe('18:00')
    })

    it('handles overnight slot calculation (very early flight)', () => {
      const slots = calculateManualDropoffSlots(true, '02:00')

      // 02:00 - 165 min = 23:15 (previous day)
      expect(slots[0].time).toBe('23:15')
      // 02:00 - 120 min = 00:00
      expect(slots[1].time).toBe('00:00')
    })

    it('handles single-digit hour input', () => {
      const slots = calculateManualDropoffSlots(true, '7:30')

      // 7:30 - 165 min = 04:45
      expect(slots[0].time).toBe('04:45')
      // 7:30 - 120 min = 05:30
      expect(slots[1].time).toBe('05:30')
    })
  })
})

// =============================================================================
// Manual Departure Validation with Slot Tests
// =============================================================================

describe('BookingsNew - Manual Departure Validation with Slot', () => {
  const isValidTimeFormat = (timeStr) => {
    if (!timeStr) return false
    return /^\d{1,2}:\d{2}$/.test(timeStr)
  }

  // Updated validation that includes dropoffSlot requirement
  const isManualDepartureComplete = (showManualDeparture, data) => {
    return !!(showManualDeparture &&
      data.airlineCode &&
      isValidTimeFormat(data.flightTime) &&
      data.destinationCode &&
      data.dropoffSlot)
  }

  describe('Complete Manual Departure', () => {
    it('validates when all fields including slot are filled', () => {
      const data = {
        airlineCode: 'FR',
        airlineName: 'Ryanair',
        flightNumber: '1234',
        flightTime: '14:30',
        destinationCode: 'FAO',
        destinationName: 'Faro, Portugal',
        dropoffSlot: '165'
      }
      expect(isManualDepartureComplete(true, data)).toBe(true)
    })

    it('validates with late slot selected', () => {
      const data = {
        airlineCode: 'U2',
        airlineName: 'easyJet',
        flightNumber: '',
        flightTime: '08:00',
        destinationCode: 'AGP',
        destinationName: 'Malaga, Spain',
        dropoffSlot: '120'
      }
      expect(isManualDepartureComplete(true, data)).toBe(true)
    })

    it('validates without flight number (optional)', () => {
      const data = {
        airlineCode: 'BY',
        airlineName: 'TUI',
        flightNumber: '',
        flightTime: '17:35',
        destinationCode: 'EDI',
        destinationName: 'Edinburgh Airport',
        dropoffSlot: '165'
      }
      expect(isManualDepartureComplete(true, data)).toBe(true)
    })
  })

  describe('Incomplete Manual Departure', () => {
    it('fails when slot is not selected', () => {
      const data = {
        airlineCode: 'FR',
        flightTime: '14:30',
        destinationCode: 'FAO',
        dropoffSlot: ''
      }
      expect(isManualDepartureComplete(true, data)).toBe(false)
    })

    it('fails when slot is missing from data', () => {
      const data = {
        airlineCode: 'FR',
        flightTime: '14:30',
        destinationCode: 'FAO'
      }
      expect(isManualDepartureComplete(true, data)).toBe(false)
    })

    it('fails when airline is missing', () => {
      const data = {
        airlineCode: '',
        flightTime: '14:30',
        destinationCode: 'FAO',
        dropoffSlot: '165'
      }
      expect(isManualDepartureComplete(true, data)).toBe(false)
    })

    it('fails when time is invalid', () => {
      const data = {
        airlineCode: 'FR',
        flightTime: 'invalid',
        destinationCode: 'FAO',
        dropoffSlot: '165'
      }
      expect(isManualDepartureComplete(true, data)).toBe(false)
    })

    it('fails when destination is missing', () => {
      const data = {
        airlineCode: 'FR',
        flightTime: '14:30',
        destinationCode: '',
        dropoffSlot: '165'
      }
      expect(isManualDepartureComplete(true, data)).toBe(false)
    })

    it('fails when manual departure is not shown', () => {
      const data = {
        airlineCode: 'FR',
        flightTime: '14:30',
        destinationCode: 'FAO',
        dropoffSlot: '165'
      }
      expect(isManualDepartureComplete(false, data)).toBe(false)
    })
  })
})

// =============================================================================
// Integration Tests - Manual Departure Flow
// =============================================================================

describe('BookingsNew - Manual Departure Integration', () => {
  const formatMinutesToTime = (totalMinutes) => {
    let mins = totalMinutes
    while (mins < 0) mins += 1440
    while (mins >= 1440) mins -= 1440
    const h = Math.floor(mins / 60)
    const m = mins % 60
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`
  }

  const isValidTimeFormat = (timeStr) => {
    if (!timeStr) return false
    return /^\d{1,2}:\d{2}$/.test(timeStr)
  }

  const calculateManualDropoffSlots = (showManualDeparture, flightTime) => {
    if (!showManualDeparture) return []
    if (!isValidTimeFormat(flightTime)) return []

    const [hours, minutes] = flightTime.split(':').map(Number)
    const departureMinutes = hours * 60 + minutes

    return [
      { id: '165', label: '2¾ hours before', time: formatMinutesToTime(departureMinutes - 165) },
      { id: '120', label: '2 hours before', time: formatMinutesToTime(departureMinutes - 120) }
    ]
  }

  const isManualDepartureComplete = (showManualDeparture, data) => {
    return !!(showManualDeparture &&
      data.airlineCode &&
      isValidTimeFormat(data.flightTime) &&
      data.destinationCode &&
      data.dropoffSlot)
  }

  it('simulates complete manual departure flow', () => {
    // Step 1: User clicks "Add flight manually"
    const showManualDeparture = true
    let manualDepartureData = {
      airlineCode: '',
      airlineName: '',
      flightNumber: '',
      flightTime: '',
      destinationCode: '',
      destinationName: '',
      dropoffSlot: ''
    }

    // No slots yet - time not entered
    let slots = calculateManualDropoffSlots(showManualDeparture, manualDepartureData.flightTime)
    expect(slots).toEqual([])
    expect(isManualDepartureComplete(showManualDeparture, manualDepartureData)).toBe(false)

    // Step 2: User selects airline
    manualDepartureData = { ...manualDepartureData, airlineCode: 'RK', airlineName: 'Ryanair UK' }
    expect(isManualDepartureComplete(showManualDeparture, manualDepartureData)).toBe(false)

    // Step 3: User enters departure time
    manualDepartureData = { ...manualDepartureData, flightTime: '17:35' }
    slots = calculateManualDropoffSlots(showManualDeparture, manualDepartureData.flightTime)

    // Now slots should appear
    expect(slots).toHaveLength(2)
    expect(slots[0].time).toBe('14:50') // 17:35 - 165 = 14:50
    expect(slots[1].time).toBe('15:35') // 17:35 - 120 = 15:35
    expect(isManualDepartureComplete(showManualDeparture, manualDepartureData)).toBe(false)

    // Step 4: User selects destination
    manualDepartureData = { ...manualDepartureData, destinationCode: 'EDI', destinationName: 'Edinburgh Airport' }
    expect(isManualDepartureComplete(showManualDeparture, manualDepartureData)).toBe(false)

    // Step 5: User selects drop-off slot
    manualDepartureData = { ...manualDepartureData, dropoffSlot: '165' }
    expect(isManualDepartureComplete(showManualDeparture, manualDepartureData)).toBe(true)
  })

  it('recalculates slots when time is changed', () => {
    const showManualDeparture = true
    let manualDepartureData = {
      airlineCode: 'FR',
      flightTime: '10:00',
      destinationCode: 'FAO',
      dropoffSlot: '165'
    }

    let slots = calculateManualDropoffSlots(showManualDeparture, manualDepartureData.flightTime)
    expect(slots[0].time).toBe('07:15') // 10:00 - 165
    expect(slots[1].time).toBe('08:00') // 10:00 - 120

    // User changes time
    manualDepartureData = { ...manualDepartureData, flightTime: '14:00' }
    slots = calculateManualDropoffSlots(showManualDeparture, manualDepartureData.flightTime)
    expect(slots[0].time).toBe('11:15') // 14:00 - 165
    expect(slots[1].time).toBe('12:00') // 14:00 - 120
  })

  it('handles user selecting different slot options', () => {
    const showManualDeparture = true
    const baseData = {
      airlineCode: 'U2',
      flightTime: '12:00',
      destinationCode: 'AGP'
    }

    // User selects early slot
    let data = { ...baseData, dropoffSlot: '165' }
    expect(isManualDepartureComplete(showManualDeparture, data)).toBe(true)

    // User changes to late slot
    data = { ...baseData, dropoffSlot: '120' }
    expect(isManualDepartureComplete(showManualDeparture, data)).toBe(true)

    // User deselects slot (clears selection)
    data = { ...baseData, dropoffSlot: '' }
    expect(isManualDepartureComplete(showManualDeparture, data)).toBe(false)
  })
})
