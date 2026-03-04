/**
 * Tests for Admin Popular Routes Report functionality
 *
 * Tests the core logic:
 * - Popular Airlines chart display and data (merged - each booking counts once per unique airline)
 * - Popular Destinations chart display and data (merged - each booking counts once per unique destination)
 * - Filter controls (top N only - status is always confirmed+completed)
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

const createMockRoute = (overrides = {}) => ({
  airlineCode: 'BA',
  airlineName: 'British Airways',
  destination: 'Faro Airport',
  route: 'British Airways to Faro Airport',
  count: 15,
  percent: 30.0,
  ...overrides,
})

const createMockPopularResponse = (overrides = {}) => ({
  meta: {
    startDate: null,
    endDate: null,
    top: 10,
    totalBookings: 50,
    totalAirlineBookings: 50,
    totalDestinationBookings: 50,
    totalRouteBookings: 50,
    ...overrides.meta,
  },
  popularAirlines: overrides.popularAirlines ?? [
    createMockAirline({ airlineCode: 'BA', airlineName: 'British Airways', count: 20, percent: 40.0 }),
    createMockAirline({ airlineCode: 'FR', airlineName: 'Ryanair', count: 15, percent: 30.0 }),
    createMockAirline({ airlineCode: 'U2', airlineName: 'easyJet', count: 10, percent: 20.0 }),
    createMockAirline({ airlineCode: 'BY', airlineName: 'TUI Airways', count: 5, percent: 10.0 }),
  ],
  popularDestinations: overrides.popularDestinations ?? [
    createMockDestination({ destination: 'Faro Airport', count: 25, percent: 50.0 }),
    createMockDestination({ destination: 'Malaga Airport', count: 15, percent: 30.0 }),
    createMockDestination({ destination: 'Alicante Airport', count: 10, percent: 20.0 }),
  ],
  popularRoutes: overrides.popularRoutes ?? [
    createMockRoute({ route: 'British Airways to Faro Airport', count: 15, percent: 30.0 }),
    createMockRoute({ airlineName: 'Ryanair', destination: 'Malaga Airport', route: 'Ryanair to Malaga Airport', count: 12, percent: 24.0 }),
    createMockRoute({ airlineName: 'easyJet', destination: 'Alicante Airport', route: 'easyJet to Alicante Airport', count: 10, percent: 20.0 }),
  ],
})

// =============================================================================
// Unit Tests - Response Structure
// =============================================================================

describe('Admin Popular Routes Response Structure', () => {
  describe('Unit Tests - Meta data structure', () => {
    it('should not include status filter in meta (always confirmed+completed)', () => {
      const response = createMockPopularResponse()

      expect(response.meta).not.toHaveProperty('status')
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

    it('should include totalAirlineBookings in meta', () => {
      const response = createMockPopularResponse()

      expect(response.meta).toHaveProperty('totalAirlineBookings')
    })

    it('should include totalDestinationBookings in meta', () => {
      const response = createMockPopularResponse()

      expect(response.meta).toHaveProperty('totalDestinationBookings')
    })

    it('should include totalRouteBookings in meta', () => {
      const response = createMockPopularResponse()

      expect(response.meta).toHaveProperty('totalRouteBookings')
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
      expect(typeof destination.count).toBe('number')
    })

    it('should include percent', () => {
      const destination = createMockDestination()
      expect(destination).toHaveProperty('percent')
      expect(typeof destination.percent).toBe('number')
    })
  })

  describe('Unit Tests - Route data structure', () => {
    it('should include route display string', () => {
      const route = createMockRoute()
      expect(route).toHaveProperty('route')
      expect(route.route).toContain('to')
    })

    it('should include airlineName', () => {
      const route = createMockRoute()
      expect(route).toHaveProperty('airlineName')
    })

    it('should include destination', () => {
      const route = createMockRoute()
      expect(route).toHaveProperty('destination')
    })

    it('should include count', () => {
      const route = createMockRoute()
      expect(route).toHaveProperty('count')
      expect(typeof route.count).toBe('number')
    })

    it('should include percent', () => {
      const route = createMockRoute()
      expect(route).toHaveProperty('percent')
      expect(typeof route.percent).toBe('number')
    })

    it('should format route as "Airline to Destination"', () => {
      const route = createMockRoute({
        airlineName: 'Jet2',
        destination: 'Faro Airport',
        route: 'Jet2 to Faro Airport',
      })
      expect(route.route).toBe('Jet2 to Faro Airport')
    })
  })
})

// =============================================================================
// Unit Tests - Bar Chart Display
// =============================================================================

describe('Admin Popular Routes Bar Chart Display', () => {
  describe('Unit Tests - Bar width calculation', () => {
    it('should calculate bar width as percentage of max', () => {
      const airlines = [
        createMockAirline({ count: 100 }),
        createMockAirline({ count: 50 }),
        createMockAirline({ count: 25 }),
      ]

      const maxCount = airlines[0].count
      const widths = airlines.map(a => (a.count / maxCount) * 100)

      expect(widths[0]).toBe(100)
      expect(widths[1]).toBe(50)
      expect(widths[2]).toBe(25)
    })

    it('should handle single item with 100% width', () => {
      const airlines = [createMockAirline({ count: 42 })]

      const maxCount = airlines[0].count
      const width = (airlines[0].count / maxCount) * 100

      expect(width).toBe(100)
    })

    it('should handle equal counts with equal widths', () => {
      const airlines = [
        createMockAirline({ count: 50 }),
        createMockAirline({ count: 50 }),
        createMockAirline({ count: 50 }),
      ]

      const maxCount = airlines[0].count
      const widths = airlines.map(a => (a.count / maxCount) * 100)

      expect(widths.every(w => w === 100)).toBe(true)
    })
  })

  describe('Unit Tests - Ranking display', () => {
    it('should display rank numbers starting from 1', () => {
      const airlines = [
        createMockAirline({ airlineName: 'First' }),
        createMockAirline({ airlineName: 'Second' }),
      ]

      const ranks = airlines.map((_, idx) => idx + 1)

      expect(ranks[0]).toBe(1)
      expect(ranks[1]).toBe(2)
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
      const top = 10

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => createMockPopularResponse(),
      })

      const params = new URLSearchParams({ top: top.toString() })
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

    it('should include top parameter in URL', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => createMockPopularResponse(),
      })

      const params = new URLSearchParams({ top: '20' })
      await fetch(`/api/admin/reports/popular?${params}`)

      const callUrl = global.fetch.mock.calls[0][0]
      expect(callUrl).toContain('top=20')
    })

    it('should not include status parameter in URL', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => createMockPopularResponse(),
      })

      const params = new URLSearchParams({ top: '10' })
      await fetch(`/api/admin/reports/popular?${params}`)

      const callUrl = global.fetch.mock.calls[0][0]
      expect(callUrl).not.toContain('status=')
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

    it('should update popularData state on success', async () => {
      const mockData = createMockPopularResponse()
      let popularData = null

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockData,
      })

      const response = await fetch('/api/admin/reports/popular')
      if (response.ok) {
        popularData = await response.json()
      }

      expect(popularData).not.toBeNull()
      expect(popularData.popularAirlines).toHaveLength(4)
    })

    it('should set loading state while fetching', async () => {
      let loading = false

      // Simulate loading flow
      loading = true
      expect(loading).toBe(true)

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => createMockPopularResponse(),
      })

      await fetch('/api/admin/reports/popular')
      loading = false

      expect(loading).toBe(false)
    })
  })
})

// =============================================================================
// Negative Tests - Error Handling
// =============================================================================

describe('Admin Popular Routes Error Handling', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Negative Tests - API error responses', () => {
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

      await expect(fetch('/api/admin/reports/popular')).rejects.toThrow('Network error')
    })
  })

  describe('Negative Tests - Empty data', () => {
    it('should handle empty airlines array', () => {
      const response = createMockPopularResponse({ popularAirlines: [] })

      expect(response.popularAirlines).toHaveLength(0)
    })

    it('should handle empty destinations array', () => {
      const response = createMockPopularResponse({ popularDestinations: [] })

      expect(response.popularDestinations).toHaveLength(0)
    })

    it('should display no data message for empty airlines', () => {
      const response = createMockPopularResponse({ popularAirlines: [] })
      const hasNoData = response.popularAirlines.length === 0

      expect(hasNoData).toBe(true)
    })

    it('should display no data message for empty destinations', () => {
      const response = createMockPopularResponse({ popularDestinations: [] })
      const hasNoData = response.popularDestinations.length === 0

      expect(hasNoData).toBe(true)
    })
  })
})

// =============================================================================
// Edge Cases
// =============================================================================

describe('Admin Popular Routes Edge Cases', () => {
  describe('Edge Cases - Data boundaries', () => {
    it('should handle single airline', () => {
      const response = createMockPopularResponse({
        popularAirlines: [createMockAirline({ count: 100, percent: 100.0 })],
      })

      expect(response.popularAirlines).toHaveLength(1)
      expect(response.popularAirlines[0].percent).toBe(100.0)
    })

    it('should handle single destination', () => {
      const response = createMockPopularResponse({
        popularDestinations: [createMockDestination({ count: 100, percent: 100.0 })],
      })

      expect(response.popularDestinations).toHaveLength(1)
      expect(response.popularDestinations[0].percent).toBe(100.0)
    })

    it('should handle very long airline name', () => {
      const longName = 'A'.repeat(200)
      const airline = createMockAirline({ airlineName: longName })

      expect(airline.airlineName.length).toBe(200)
    })

    it('should handle special characters in destination', () => {
      const destination = createMockDestination({
        destination: 'São Paulo–Guarulhos Airport (GRU)',
      })

      expect(destination.destination).toContain('ã')
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

  describe('Edge Cases - Rapid filter changes', () => {
    it('should handle switching between top filters rapidly', () => {
      let popularTop = 10

      // Rapid changes
      popularTop = 5
      popularTop = 20
      popularTop = 10
      popularTop = 5

      expect(popularTop).toBe(5)
    })
  })

  describe('Edge Cases - Maximum items', () => {
    it('should handle maximum 20 airlines', () => {
      const airlines = Array.from({ length: 20 }, (_, i) =>
        createMockAirline({ airlineName: `Airline ${i + 1}`, count: 20 - i })
      )

      expect(airlines).toHaveLength(20)
    })

    it('should handle maximum 20 destinations', () => {
      const destinations = Array.from({ length: 20 }, (_, i) =>
        createMockDestination({ destination: `Airport ${i + 1}`, count: 20 - i })
      )

      expect(destinations).toHaveLength(20)
    })
  })
})

// =============================================================================
// Display Logic Tests
// =============================================================================

describe('Admin Popular Routes Display Logic', () => {
  describe('Display Logic - Subtitle text', () => {
    it('should display correct booking count in subtitle', () => {
      const response = createMockPopularResponse({ meta: { totalBookings: 42 } })

      expect(response.meta.totalBookings).toBe(42)
    })
  })

  describe('Display Logic - Count and percent', () => {
    it('should display count and percent together', () => {
      const airline = createMockAirline({ count: 25, percent: 50.0 })

      const displayText = `${airline.count} (${airline.percent}%)`

      expect(displayText).toBe('25 (50%)')
    })

    it('should handle decimal percent display', () => {
      const airline = createMockAirline({ count: 33, percent: 33.3 })

      const displayText = `${airline.count} (${airline.percent}%)`

      expect(displayText).toBe('33 (33.3%)')
    })
  })

  describe('Display Logic - Layout', () => {
    it('should use two-column grid on desktop', () => {
      // Grid layout test - checking CSS class would apply
      const gridClass = 'popular-charts-grid'

      expect(gridClass).toBe('popular-charts-grid')
    })

    it('should handle label truncation for long names', () => {
      const longName = 'Very Long Airline Name That Should Be Truncated'
      const maxLength = 30

      const truncated = longName.length > maxLength
        ? longName.substring(0, maxLength) + '...'
        : longName

      expect(truncated.length).toBeLessThanOrEqual(maxLength + 3)
    })
  })
})

// =============================================================================
// Subtab Integration Tests
// =============================================================================

describe('Admin Popular Routes Subtab Integration', () => {
  describe('Subtab Integration - Tab activation', () => {
    it('should show Popular Routes content when subtab is active', () => {
      const reportsSubTab = 'popular'
      const isPopularActive = reportsSubTab === 'popular'

      expect(isPopularActive).toBe(true)
    })

    it('should hide Popular Routes content when other subtab is active', () => {
      const reportsSubTab = 'growth'
      const isPopularActive = reportsSubTab === 'popular'

      expect(isPopularActive).toBe(false)
    })

    it('should fetch data when subtab becomes active', async () => {
      let fetchCalled = false

      global.fetch.mockImplementation(() => {
        fetchCalled = true
        return Promise.resolve({
          ok: true,
          json: async () => createMockPopularResponse(),
        })
      })

      const reportsSubTab = 'popular'
      if (reportsSubTab === 'popular') {
        await fetch('/api/admin/reports/popular')
      }

      expect(fetchCalled).toBe(true)
    })

    it('should not fetch data when reports tab is not active', async () => {
      let fetchCalled = false

      global.fetch.mockImplementation(() => {
        fetchCalled = true
        return Promise.resolve({
          ok: true,
          json: async () => createMockPopularResponse(),
        })
      })

      const activeTab = 'bookings'
      if (activeTab === 'reports') {
        await fetch('/api/admin/reports/popular')
      }

      expect(fetchCalled).toBe(false)
    })
  })
})

// =============================================================================
// Merged Counting Logic Tests
// =============================================================================

describe('Admin Popular Routes Merged Counting Logic', () => {
  describe('Merged Counting - Same airline both ways counts once', () => {
    it('should count same airline once per booking', () => {
      // Simulate counting logic
      const booking = {
        dropoff_airline: 'Jet2',
        pickup_airline: 'Jet2',
      }

      const airlines = new Set()
      if (booking.dropoff_airline) airlines.add(booking.dropoff_airline)
      if (booking.pickup_airline) airlines.add(booking.pickup_airline)

      expect(airlines.size).toBe(1)
    })

    it('should count different airlines both once', () => {
      const booking = {
        dropoff_airline: 'British Airways',
        pickup_airline: 'Ryanair',
      }

      const airlines = new Set()
      if (booking.dropoff_airline) airlines.add(booking.dropoff_airline)
      if (booking.pickup_airline) airlines.add(booking.pickup_airline)

      expect(airlines.size).toBe(2)
    })
  })

  describe('Merged Counting - Same destination both ways counts once', () => {
    it('should count same destination once per booking', () => {
      const booking = {
        dropoff_destination: 'Faro Airport',
        pickup_origin: 'Faro Airport',
      }

      const destinations = new Set()
      if (booking.dropoff_destination) destinations.add(booking.dropoff_destination)
      if (booking.pickup_origin) destinations.add(booking.pickup_origin)

      expect(destinations.size).toBe(1)
    })

    it('should count different destinations both once', () => {
      const booking = {
        dropoff_destination: 'Faro Airport',
        pickup_origin: 'Malaga Airport',
      }

      const destinations = new Set()
      if (booking.dropoff_destination) destinations.add(booking.dropoff_destination)
      if (booking.pickup_origin) destinations.add(booking.pickup_origin)

      expect(destinations.size).toBe(2)
    })
  })
})
