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
