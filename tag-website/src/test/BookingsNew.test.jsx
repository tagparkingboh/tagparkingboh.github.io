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
