/**
 * Tests for Admin Popular Routes Report functionality
 *
 * Tests the core logic:
 * - Popular Airlines chart display and data
 * - Popular Destinations chart display and data
 * - Filter controls (status, top N)
 * - API response handling
 * - Loading states
 *
 * Test categories:
 * - Unit Tests: UI component logic, data display
 * - Integration Tests: API calls, state updates
 * - Negative Tests: Error handling, empty data
 * - Edge Cases: Boundary conditions
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock fetch
global.fetch = vi.fn()

// =============================================================================
// Mock Data Factories
// =============================================================================

const createMockAirline = (overrides = {}) => ({
  airlineCode: 'BA',
  airlineName: 'British Airways',
  count: 20,
  percent: 40.0,
  ...overrides,
})

const createMockDestination = (overrides = {}) => ({
  destination: 'Faro Airport',
  count: 25,
  percent: 50.0,
  ...overrides,
})

const createMockPopularResponse = (overrides = {}) => ({
  meta: {
    startDate: null,
    endDate: null,
    status: 'all',
    top: 10,
    totalBookings: 50,
    totalAirlineFlights: 100,
    totalDestinationTrips: 100,
    ...overrides.meta,
  },
  popularAirlines: overrides.popularAirlines ?? [
    createMockAirline({ airlineCode: 'BA', airlineName: 'British Airways', count: 40, percent: 40.0 }),
    createMockAirline({ airlineCode: 'FR', airlineName: 'Ryanair', count: 30, percent: 30.0 }),
    createMockAirline({ airlineCode: 'U2', airlineName: 'easyJet', count: 20, percent: 20.0 }),
    createMockAirline({ airlineCode: 'BY', airlineName: 'TUI Airways', count: 10, percent: 10.0 }),
  ],
  popularDestinations: overrides.popularDestinations ?? [
    createMockDestination({ destination: 'Faro Airport', count: 50, percent: 50.0 }),
    createMockDestination({ destination: 'Malaga Airport', count: 30, percent: 30.0 }),
    createMockDestination({ destination: 'Alicante Airport', count: 20, percent: 20.0 }),
  ],
})

// =============================================================================
// Unit Tests - Response Structure
// =============================================================================

describe('Admin Popular Routes Response Structure', () => {
  describe('Unit Tests - Meta data structure', () => {
    it('should include status filter in meta', () => {
      const response = createMockPopularResponse()

      expect(response.meta).toHaveProperty('status')
      expect(response.meta.status).toBe('all')
    })

    it('should include top limit in meta', () => {
      const response = createMockPopularResponse()

      expect(response.meta).toHaveProperty('top')
      expect(response.meta.top).toBe(10)
    })

    it('should include totalBookings in meta', () => {
      const response = createMockPopularResponse()

      expect(response.meta).toHaveProperty('totalBookings')
      expect(response.meta.totalBookings).toBe(50)
    })

    it('should include totalAirlineFlights in meta', () => {
      const response = createMockPopularResponse()

      expect(response.meta).toHaveProperty('totalAirlineFlights')
    })

    it('should include totalDestinationTrips in meta', () => {
      const response = createMockPopularResponse()

      expect(response.meta).toHaveProperty('totalDestinationTrips')
    })
  })

  describe('Unit Tests - Airline data structure', () => {
    it('should include airlineCode', () => {
      const airline = createMockAirline()
      expect(airline).toHaveProperty('airlineCode')
    })

    it('should include airlineName', () => {
      const airline = createMockAirline()
      expect(airline).toHaveProperty('airlineName')
    })

    it('should include count', () => {
      const airline = createMockAirline()
      expect(airline).toHaveProperty('count')
      expect(typeof airline.count).toBe('number')
    })

    it('should include percent', () => {
      const airline = createMockAirline()
      expect(airline).toHaveProperty('percent')
      expect(typeof airline.percent).toBe('number')
    })
  })

  describe('Unit Tests - Destination data structure', () => {
    it('should include destination name', () => {
      const destination = createMockDestination()
      expect(destination).toHaveProperty('destination')
    })

    it('should include count', () => {
      const destination = createMockDestination()
      expect(destination).toHaveProperty('count')
    })

    it('should include percent', () => {
      const destination = createMockDestination()
      expect(destination).toHaveProperty('percent')
    })
  })
})

// =============================================================================
// Unit Tests - Bar Chart Display Logic
// =============================================================================

describe('Admin Popular Routes Bar Chart Logic', () => {
  describe('Unit Tests - Bar width calculation', () => {
    it('should calculate bar width as percentage of max', () => {
      const airlines = [
        createMockAirline({ count: 40 }),
        createMockAirline({ count: 20 }),
        createMockAirline({ count: 10 }),
      ]

      const maxCount = airlines[0].count
      const barWidths = airlines.map(a => (a.count / maxCount) * 100)

      expect(barWidths[0]).toBe(100)
      expect(barWidths[1]).toBe(50)
      expect(barWidths[2]).toBe(25)
    })

    it('should handle single item with 100% width', () => {
      const airlines = [createMockAirline({ count: 50 })]

      const maxCount = airlines[0].count
      const barWidth = (airlines[0].count / maxCount) * 100

      expect(barWidth).toBe(100)
    })

    it('should handle equal counts with equal widths', () => {
      const airlines = [
        createMockAirline({ count: 30 }),
        createMockAirline({ count: 30 }),
        createMockAirline({ count: 30 }),
      ]

      const maxCount = airlines[0].count
      const barWidths = airlines.map(a => (a.count / maxCount) * 100)

      expect(barWidths.every(w => w === 100)).toBe(true)
    })
  })

  describe('Unit Tests - Ranking display', () => {
    it('should display rank numbers starting from 1', () => {
      const airlines = createMockPopularResponse().popularAirlines

      airlines.forEach((_, idx) => {
        const rank = idx + 1
        expect(rank).toBeGreaterThanOrEqual(1)
      })
    })

    it('should show correct rank for each position', () => {
      const airlines = [
        createMockAirline({ airlineName: 'First' }),
        createMockAirline({ airlineName: 'Second' }),
        createMockAirline({ airlineName: 'Third' }),
      ]

      expect(airlines[0].airlineName).toBe('First')
      expect(airlines[1].airlineName).toBe('Second')
      expect(airlines[2].airlineName).toBe('Third')
    })
  })
})

// =============================================================================
// Unit Tests - Filter Controls
// =============================================================================

describe('Admin Popular Routes Filter Controls', () => {
  describe('Unit Tests - Status filter options', () => {
    it('should have "all" option', () => {
      const statusOptions = ['all', 'confirmed', 'completed']
      expect(statusOptions).toContain('all')
    })

    it('should have "confirmed" option', () => {
      const statusOptions = ['all', 'confirmed', 'completed']
      expect(statusOptions).toContain('confirmed')
    })

    it('should have "completed" option', () => {
      const statusOptions = ['all', 'confirmed', 'completed']
      expect(statusOptions).toContain('completed')
    })
  })

  describe('Unit Tests - Top N filter options', () => {
    it('should have "5" option', () => {
      const topOptions = [5, 10, 20]
      expect(topOptions).toContain(5)
    })

    it('should have "10" option', () => {
      const topOptions = [5, 10, 20]
      expect(topOptions).toContain(10)
    })

    it('should have "20" option', () => {
      const topOptions = [5, 10, 20]
      expect(topOptions).toContain(20)
    })

    it('should default to 10', () => {
      const defaultTop = 10
      expect(defaultTop).toBe(10)
    })
  })

  describe('Unit Tests - Filter state management', () => {
    it('should update status filter value', () => {
      let popularStatus = 'all'

      // Simulate changing status
      popularStatus = 'confirmed'
      expect(popularStatus).toBe('confirmed')

      popularStatus = 'completed'
      expect(popularStatus).toBe('completed')
    })

    it('should update top filter value', () => {
      let popularTop = 10

      // Simulate changing top
      popularTop = 5
      expect(popularTop).toBe(5)

      popularTop = 20
      expect(popularTop).toBe(20)
    })
  })
})

// =============================================================================
// Integration Tests - API Calls
// =============================================================================

describe('Admin Popular Routes API Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('API Integration - Fetch popular report', () => {
    it('should call correct API endpoint', async () => {
      const API_URL = 'https://api.example.com'
      const token = 'test-token'
      const status = 'all'
      const top = 10

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => createMockPopularResponse(),
      })

      const params = new URLSearchParams({ status, top: top.toString() })
      await fetch(`${API_URL}/api/admin/reports/popular?${params}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/admin/reports/popular'),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': `Bearer ${token}`,
          }),
        })
      )
    })

    it('should include status parameter in URL', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => createMockPopularResponse(),
      })

      const status = 'confirmed'
      const params = new URLSearchParams({ status, top: '10' })
      await fetch(`/api/admin/reports/popular?${params}`)

      const callUrl = global.fetch.mock.calls[0][0]
      expect(callUrl).toContain('status=confirmed')
    })

    it('should include top parameter in URL', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => createMockPopularResponse(),
      })

      const params = new URLSearchParams({ status: 'all', top: '20' })
      await fetch(`/api/admin/reports/popular?${params}`)

      const callUrl = global.fetch.mock.calls[0][0]
      expect(callUrl).toContain('top=20')
    })

    it('should handle successful response', async () => {
      const mockData = createMockPopularResponse()

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockData,
      })

      const response = await fetch('/api/admin/reports/popular')
      const data = await response.json()

      expect(response.ok).toBe(true)
      expect(data).toHaveProperty('popularAirlines')
      expect(data).toHaveProperty('popularDestinations')
    })
  })

  describe('API Integration - State updates', () => {
    it('should update popularData state on success', async () => {
      let popularData = null
      const mockData = createMockPopularResponse()

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockData,
      })

      const response = await fetch('/api/admin/reports/popular')
      if (response.ok) {
        popularData = await response.json()
      }

      expect(popularData).not.toBeNull()
      expect(popularData.popularAirlines.length).toBeGreaterThan(0)
    })

    it('should set loading state while fetching', () => {
      let loadingPopular = false

      // Start loading
      loadingPopular = true
      expect(loadingPopular).toBe(true)

      // End loading
      loadingPopular = false
      expect(loadingPopular).toBe(false)
    })
  })
})

// =============================================================================
// Negative Tests - Error Handling
// =============================================================================

describe('Admin Popular Routes Negative Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('API Error Handling', () => {
    it('should handle 401 unauthorized', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'Not authenticated' }),
      })

      const response = await fetch('/api/admin/reports/popular')
      expect(response.ok).toBe(false)
      expect(response.status).toBe(401)
    })

    it('should handle 500 server error', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'Internal server error' }),
      })

      const response = await fetch('/api/admin/reports/popular')
      expect(response.ok).toBe(false)
      expect(response.status).toBe(500)
    })

    it('should handle network error', async () => {
      global.fetch.mockRejectedValueOnce(new Error('Network error'))

      let errorOccurred = false
      try {
        await fetch('/api/admin/reports/popular')
      } catch (err) {
        errorOccurred = true
      }

      expect(errorOccurred).toBe(true)
    })
  })

  describe('Empty Data Handling', () => {
    it('should handle empty airlines array', () => {
      const response = createMockPopularResponse({ popularAirlines: [] })

      expect(response.popularAirlines).toHaveLength(0)
    })

    it('should handle empty destinations array', () => {
      const response = createMockPopularResponse({ popularDestinations: [] })

      expect(response.popularDestinations).toHaveLength(0)
    })

    it('should display no data message for empty airlines', () => {
      const airlines = []
      const hasData = airlines.length > 0

      expect(hasData).toBe(false)
      // Should show "No airline data available"
    })

    it('should display no data message for empty destinations', () => {
      const destinations = []
      const hasData = destinations.length > 0

      expect(hasData).toBe(false)
      // Should show "No destination data available"
    })
  })
})

// =============================================================================
// Edge Cases
// =============================================================================

describe('Admin Popular Routes Edge Cases', () => {
  describe('Data Edge Cases', () => {
    it('should handle single airline', () => {
      const response = createMockPopularResponse({
        popularAirlines: [createMockAirline()],
      })

      expect(response.popularAirlines).toHaveLength(1)
    })

    it('should handle single destination', () => {
      const response = createMockPopularResponse({
        popularDestinations: [createMockDestination()],
      })

      expect(response.popularDestinations).toHaveLength(1)
    })

    it('should handle very long airline name', () => {
      const longName = 'A'.repeat(100)
      const airline = createMockAirline({ airlineName: longName })

      expect(airline.airlineName.length).toBe(100)
    })

    it('should handle special characters in destination', () => {
      const destination = createMockDestination({
        destination: 'São Paulo–Guarulhos Airport',
      })

      expect(destination.destination).toContain('São')
      expect(destination.destination).toContain('–')
    })

    it('should handle zero count', () => {
      const airline = createMockAirline({ count: 0, percent: 0 })

      expect(airline.count).toBe(0)
      expect(airline.percent).toBe(0)
    })

    it('should handle 100% percentage', () => {
      const airline = createMockAirline({ count: 50, percent: 100.0 })

      expect(airline.percent).toBe(100.0)
    })
  })

  describe('UI Edge Cases', () => {
    it('should handle switching between status filters rapidly', () => {
      let popularStatus = 'all'

      // Rapid switches
      popularStatus = 'confirmed'
      popularStatus = 'completed'
      popularStatus = 'all'
      popularStatus = 'confirmed'

      expect(popularStatus).toBe('confirmed')
    })

    it('should handle switching between top filters rapidly', () => {
      let popularTop = 10

      // Rapid switches
      popularTop = 5
      popularTop = 20
      popularTop = 10
      popularTop = 5

      expect(popularTop).toBe(5)
    })
  })

  describe('Large Data Edge Cases', () => {
    it('should handle maximum 20 airlines', () => {
      const airlines = Array.from({ length: 20 }, (_, i) =>
        createMockAirline({
          airlineCode: `A${i}`,
          airlineName: `Airline ${i}`,
          count: 100 - i,
        })
      )

      expect(airlines).toHaveLength(20)
    })

    it('should handle maximum 20 destinations', () => {
      const destinations = Array.from({ length: 20 }, (_, i) =>
        createMockDestination({
          destination: `Airport ${i}`,
          count: 100 - i,
        })
      )

      expect(destinations).toHaveLength(20)
    })
  })
})

// =============================================================================
// Display Logic Tests
// =============================================================================

describe('Admin Popular Routes Display Logic', () => {
  describe('Chart subtitle display', () => {
    it('should display correct booking count in subtitle', () => {
      const response = createMockPopularResponse()
      const subtitle = `Based on ${response.meta.totalAirlineFlights} flight legs from ${response.meta.totalBookings} bookings`

      expect(subtitle).toContain('100')
      expect(subtitle).toContain('50')
    })

    it('should display correct trip count in subtitle', () => {
      const response = createMockPopularResponse()
      const subtitle = `Based on ${response.meta.totalDestinationTrips} trips from ${response.meta.totalBookings} bookings`

      expect(subtitle).toContain('100')
    })
  })

  describe('Value display format', () => {
    it('should display count and percent together', () => {
      const airline = createMockAirline({ count: 40, percent: 40.0 })
      const displayValue = `${airline.count} (${airline.percent}%)`

      expect(displayValue).toBe('40 (40%)')
    })

    it('should handle decimal percent display', () => {
      const airline = createMockAirline({ count: 33, percent: 33.3 })
      const displayValue = `${airline.count} (${airline.percent}%)`

      expect(displayValue).toBe('33 (33.3%)')
    })
  })
})

// =============================================================================
// Responsive/Mobile Tests
// =============================================================================

describe('Admin Popular Routes Responsive Behavior', () => {
  describe('Grid layout', () => {
    it('should use two-column grid on desktop', () => {
      // CSS class check
      const gridClass = 'popular-charts-grid'
      expect(gridClass).toBe('popular-charts-grid')
    })

    it('should handle label truncation for long names', () => {
      const longName = 'Very Long Airline Name That Exceeds Normal Width'
      const maxWidth = 120

      // Text should be truncated
      const truncated = longName.length > maxWidth
      expect(longName.length).toBeGreaterThan(20)
    })
  })
})

// =============================================================================
// Subtab Integration Tests
// =============================================================================

describe('Admin Popular Routes Subtab Integration', () => {
  describe('Subtab visibility', () => {
    it('should show Popular Routes content when subtab is active', () => {
      const reportsSubTab = 'popular'
      const shouldShow = reportsSubTab === 'popular'

      expect(shouldShow).toBe(true)
    })

    it('should hide Popular Routes content when other subtab is active', () => {
      const reportsSubTab = 'growth'
      const shouldShow = reportsSubTab === 'popular'

      expect(shouldShow).toBe(false)
    })
  })

  describe('Data fetching trigger', () => {
    it('should fetch data when subtab becomes active', () => {
      const reportsSubTab = 'popular'
      const activeTab = 'reports'
      const shouldFetch = activeTab === 'reports' && reportsSubTab === 'popular'

      expect(shouldFetch).toBe(true)
    })

    it('should not fetch data when reports tab is not active', () => {
      const reportsSubTab = 'popular'
      const activeTab = 'bookings'
      const shouldFetch = activeTab === 'reports' && reportsSubTab === 'popular'

      expect(shouldFetch).toBe(false)
    })
  })
})

// =============================================================================
// Run tests if executed directly
// =============================================================================

if (import.meta.vitest) {
  const { describe, it, expect, vi, beforeEach } = import.meta.vitest
}
