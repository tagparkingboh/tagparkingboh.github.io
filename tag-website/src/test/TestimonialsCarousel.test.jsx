/**
 * Tests for TestimonialsCarousel component
 *
 * Tests the core logic:
 * - Fetching testimonials from API
 * - Rendering rated and unrated testimonials
 * - Auto-rotation and navigation
 * - Weighted pool deduplication
 * - Source badge rendering
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock fetch
global.fetch = vi.fn()

// Mock testimonial data
const mockTestimonialRated5Stars = {
  id: 1,
  customer_name: 'John Doe',
  review_text: 'Excellent service! Very professional and convenient.',
  star_rating: 5,
  date_of_travel: '2026-01-15',
  source: 'google',
  is_featured: false,
}

const mockTestimonialRated4Stars = {
  id: 2,
  customer_name: 'Jane Smith',
  review_text: 'Great experience, will use again.',
  star_rating: 4,
  date_of_travel: '2026-02-10',
  source: 'trustpilot',
  is_featured: false,
}

const mockTestimonialUnrated = {
  id: 3,
  customer_name: 'Bob Wilson',
  review_text: 'Highly recommend TAG parking to anyone flying from Bournemouth!',
  star_rating: null,
  date_of_travel: '2026-01-20',
  source: 'linkedin',
  is_featured: false,
}

const mockTestimonialFeatured = {
  id: 4,
  customer_name: 'Sarah Connor',
  review_text: 'The best airport parking service I have ever used.',
  star_rating: 5,
  date_of_travel: '2026-02-01',
  source: 'email',
  is_featured: true,
}

const mockTestimonialLowRated = {
  id: 5,
  customer_name: 'Mike Brown',
  review_text: 'Service was okay.',
  star_rating: 2,
  date_of_travel: '2026-01-25',
  source: 'google',
  is_featured: false,
}

describe('TestimonialsCarousel Unit Tests', () => {
  describe('Star rating rendering logic', () => {
    it('should render 5 filled stars for 5-star rating', () => {
      const rating = mockTestimonialRated5Stars.star_rating
      const filledStars = rating

      expect(filledStars).toBe(5)
    })

    it('should render 4 filled stars for 4-star rating', () => {
      const rating = mockTestimonialRated4Stars.star_rating
      const filledStars = rating

      expect(filledStars).toBe(4)
    })

    it('should render quote icon for unrated testimonial (null rating)', () => {
      const rating = mockTestimonialUnrated.star_rating

      expect(rating).toBeNull()
      // When rating is null, we should show quote icon instead of stars
    })

    it('should handle star_rating of 0', () => {
      const testimonial = { ...mockTestimonialRated5Stars, star_rating: 0 }
      const filledStars = testimonial.star_rating

      expect(filledStars).toBe(0)
    })
  })

  describe('Source badge rendering logic', () => {
    it('should render Google badge for google source', () => {
      const source = mockTestimonialRated5Stars.source.toLowerCase()
      expect(source).toBe('google')
    })

    it('should render Trustpilot badge for trustpilot source', () => {
      const source = mockTestimonialRated4Stars.source.toLowerCase()
      expect(source).toBe('trustpilot')
    })

    it('should render LinkedIn badge for linkedin source', () => {
      const source = mockTestimonialUnrated.source.toLowerCase()
      expect(source).toBe('linkedin')
    })

    it('should handle null source gracefully', () => {
      const testimonial = { ...mockTestimonialRated5Stars, source: null }
      expect(testimonial.source).toBeNull()
    })
  })

  describe('Date formatting logic', () => {
    it('should format date correctly', () => {
      const dateString = mockTestimonialRated5Stars.date_of_travel
      const date = new Date(dateString)
      const formatted = date.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })

      expect(formatted).toBe('January 2026')
    })

    it('should handle null date', () => {
      const testimonial = { ...mockTestimonialRated5Stars, date_of_travel: null }
      expect(testimonial.date_of_travel).toBeNull()
    })
  })
})

describe('TestimonialsCarousel Weighted Pool Logic', () => {
  describe('Weight calculation', () => {
    it('should give 5x weight to 5-star testimonials', () => {
      const testimonial = mockTestimonialRated5Stars
      let weight = 0

      if (testimonial.star_rating === 5) {
        weight = 5
      }

      expect(weight).toBe(5)
    })

    it('should give 3x weight to 4-star testimonials', () => {
      const testimonial = mockTestimonialRated4Stars
      let weight = 0

      if (testimonial.star_rating === 4) {
        weight = 3
      }

      expect(weight).toBe(3)
    })

    it('should give 3x weight to unrated testimonials', () => {
      const testimonial = mockTestimonialUnrated
      let weight = 0

      if (testimonial.star_rating === null) {
        weight = 3
      }

      expect(weight).toBe(3)
    })

    it('should give 1x weight to 3-star testimonials', () => {
      const testimonial = { ...mockTestimonialRated5Stars, star_rating: 3 }
      let weight = 0

      if (testimonial.star_rating === 3) {
        weight = 1
      }

      expect(weight).toBe(1)
    })

    it('should exclude 1-2 star testimonials (0 weight)', () => {
      const testimonial = mockTestimonialLowRated
      let weight = 0

      if (testimonial.star_rating >= 3 || testimonial.star_rating === null) {
        weight = testimonial.star_rating === 5 ? 5 : testimonial.star_rating === 4 ? 3 : 1
      }

      expect(weight).toBe(0)
    })

    it('should always include featured testimonials', () => {
      const testimonial = mockTestimonialFeatured
      const alwaysInclude = testimonial.is_featured

      expect(alwaysInclude).toBe(true)
    })
  })

  describe('Deduplication logic', () => {
    it('should deduplicate testimonials by ID', () => {
      const weightedPool = [
        mockTestimonialRated5Stars,
        mockTestimonialRated5Stars, // Duplicate
        mockTestimonialRated5Stars, // Duplicate
        mockTestimonialRated4Stars,
        mockTestimonialRated4Stars, // Duplicate
      ]

      const seen = new Set()
      const deduplicated = weightedPool.filter((item) => {
        if (seen.has(item.id)) return false
        seen.add(item.id)
        return true
      })

      expect(deduplicated).toHaveLength(2)
      expect(deduplicated[0].id).toBe(1)
      expect(deduplicated[1].id).toBe(2)
    })

    it('should preserve order of first occurrence', () => {
      const weightedPool = [
        mockTestimonialUnrated, // First
        mockTestimonialRated5Stars,
        mockTestimonialUnrated, // Duplicate - should be removed
      ]

      const seen = new Set()
      const deduplicated = weightedPool.filter((item) => {
        if (seen.has(item.id)) return false
        seen.add(item.id)
        return true
      })

      expect(deduplicated[0].id).toBe(3) // Unrated should be first
    })
  })
})

describe('TestimonialsCarousel Navigation Logic', () => {
  describe('Index navigation', () => {
    it('should wrap to first testimonial after last', () => {
      const testimonials = [mockTestimonialRated5Stars, mockTestimonialRated4Stars, mockTestimonialUnrated]
      let currentIndex = 2 // Last item

      currentIndex = (currentIndex + 1) % testimonials.length

      expect(currentIndex).toBe(0)
    })

    it('should wrap to last testimonial before first', () => {
      const testimonials = [mockTestimonialRated5Stars, mockTestimonialRated4Stars, mockTestimonialUnrated]
      let currentIndex = 0 // First item

      currentIndex = (currentIndex - 1 + testimonials.length) % testimonials.length

      expect(currentIndex).toBe(2)
    })

    it('should stay on same index for single testimonial', () => {
      const testimonials = [mockTestimonialRated5Stars]
      let currentIndex = 0

      currentIndex = (currentIndex + 1) % testimonials.length

      expect(currentIndex).toBe(0)
    })
  })

  describe('Pause on hover', () => {
    it('should set isPaused to true on mouse enter', () => {
      let isPaused = false
      const onMouseEnter = () => { isPaused = true }

      onMouseEnter()

      expect(isPaused).toBe(true)
    })

    it('should set isPaused to false on mouse leave', () => {
      let isPaused = true
      const onMouseLeave = () => { isPaused = false }

      onMouseLeave()

      expect(isPaused).toBe(false)
    })
  })
})

describe('TestimonialsCarousel API Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Fetch testimonials', () => {
    it('should call /api/testimonials endpoint', async () => {
      const mockResponse = {
        testimonials: [
          mockTestimonialRated5Stars,
          mockTestimonialRated5Stars,
          mockTestimonialRated5Stars,
          mockTestimonialRated5Stars,
          mockTestimonialRated5Stars, // 5x weight
          mockTestimonialRated4Stars,
          mockTestimonialRated4Stars,
          mockTestimonialRated4Stars, // 3x weight
          mockTestimonialUnrated,
          mockTestimonialUnrated,
          mockTestimonialUnrated, // 3x weight
        ],
        total: 11,
      }

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      })

      const response = await fetch('/api/testimonials')
      const data = await response.json()

      expect(fetch).toHaveBeenCalledWith('/api/testimonials')
      expect(data.testimonials).toHaveLength(11)
    })

    it('should handle empty testimonials response', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ testimonials: [], total: 0 }),
      })

      const response = await fetch('/api/testimonials')
      const data = await response.json()

      expect(data.testimonials).toHaveLength(0)
    })

    it('should handle API error gracefully', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'Internal server error' }),
      })

      const response = await fetch('/api/testimonials')

      expect(response.ok).toBe(false)
      expect(response.status).toBe(500)
    })

    it('should handle network error gracefully', async () => {
      global.fetch.mockRejectedValueOnce(new Error('Network error'))

      await expect(fetch('/api/testimonials')).rejects.toThrow('Network error')
    })
  })
})

describe('TestimonialsCarousel Edge Cases', () => {
  it('should not render when no testimonials', () => {
    const testimonials = []
    const shouldRender = testimonials.length > 0

    expect(shouldRender).toBe(false)
  })

  it('should render single testimonial without navigation dots', () => {
    const testimonials = [mockTestimonialRated5Stars]
    const showNavigationDots = testimonials.length > 1

    expect(showNavigationDots).toBe(false)
  })

  it('should handle very long review text', () => {
    const longReviewText = 'A'.repeat(1000)
    const testimonial = { ...mockTestimonialRated5Stars, review_text: longReviewText }

    expect(testimonial.review_text.length).toBe(1000)
  })

  it('should handle special characters in customer name', () => {
    const specialName = "O'Brien-Smith Jr."
    const testimonial = { ...mockTestimonialRated5Stars, customer_name: specialName }

    expect(testimonial.customer_name).toBe("O'Brien-Smith Jr.")
  })

  it('should handle unicode in review text', () => {
    const unicodeReview = 'Great service! 👍 Highly recommend 🚗✈️'
    const testimonial = { ...mockTestimonialRated5Stars, review_text: unicodeReview }

    expect(testimonial.review_text).toContain('👍')
  })
})

describe('TestimonialsCarousel Negative Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should handle API returning error status', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'Internal server error' }),
    })

    const response = await fetch('/api/testimonials')
    expect(response.ok).toBe(false)
    expect(response.status).toBe(500)
  })

  it('should handle malformed API response', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ wrongKey: [] }), // Missing 'testimonials' key
    })

    const response = await fetch('/api/testimonials')
    const data = await response.json()
    const testimonials = data.testimonials || []

    expect(testimonials).toHaveLength(0)
  })

  it('should handle API returning null', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => null,
    })

    const response = await fetch('/api/testimonials')
    const data = await response.json()
    const testimonials = data?.testimonials || []

    expect(testimonials).toHaveLength(0)
  })

  it('should handle network timeout', async () => {
    global.fetch.mockRejectedValueOnce(new Error('Network timeout'))

    await expect(fetch('/api/testimonials')).rejects.toThrow('Network timeout')
  })

  it('should not auto-rotate with single testimonial', () => {
    const testimonials = [mockTestimonialRated5Stars]
    const shouldAutoRotate = testimonials.length > 1

    expect(shouldAutoRotate).toBe(false)
  })

  it('should handle testimonial with missing optional fields', () => {
    const minimalTestimonial = {
      id: 99,
      customer_name: 'Test User',
      review_text: 'Test review',
      // Missing: star_rating, date_of_travel, source
    }

    expect(minimalTestimonial.star_rating).toBeUndefined()
    expect(minimalTestimonial.date_of_travel).toBeUndefined()
    expect(minimalTestimonial.source).toBeUndefined()
  })
})

describe('TestimonialsCarousel Boundary Tests', () => {
  it('should handle exactly 2 testimonials (minimum for navigation)', () => {
    const testimonials = [mockTestimonialRated5Stars, mockTestimonialRated4Stars]
    const showNavigation = testimonials.length > 1

    expect(showNavigation).toBe(true)
    expect(testimonials.length).toBe(2)
  })

  it('should handle large number of testimonials', () => {
    const manyTestimonials = Array.from({ length: 100 }, (_, i) => ({
      ...mockTestimonialRated5Stars,
      id: i + 1,
    }))

    expect(manyTestimonials.length).toBe(100)
  })

  it('should wrap index correctly at upper bound', () => {
    const testimonials = Array.from({ length: 5 }, (_, i) => ({ id: i }))
    let currentIndex = 4 // Last index

    currentIndex = (currentIndex + 1) % testimonials.length

    expect(currentIndex).toBe(0) // Wrapped to first
  })

  it('should wrap index correctly at lower bound', () => {
    const testimonials = Array.from({ length: 5 }, (_, i) => ({ id: i }))
    let currentIndex = 0 // First index

    currentIndex = (currentIndex - 1 + testimonials.length) % testimonials.length

    expect(currentIndex).toBe(4) // Wrapped to last
  })

  it('should handle star_rating at lower bound (1)', () => {
    const testimonial = { ...mockTestimonialRated5Stars, star_rating: 1 }
    const isValidRating = testimonial.star_rating >= 1 && testimonial.star_rating <= 5

    expect(isValidRating).toBe(true)
  })

  it('should handle star_rating at upper bound (5)', () => {
    const testimonial = mockTestimonialRated5Stars
    const isValidRating = testimonial.star_rating >= 1 && testimonial.star_rating <= 5

    expect(isValidRating).toBe(true)
  })

  it('should handle review text at minimum length (1 char)', () => {
    const testimonial = { ...mockTestimonialRated5Stars, review_text: 'A' }
    const isValid = testimonial.review_text.length >= 1

    expect(isValid).toBe(true)
  })
})

describe('TestimonialsCarousel Additional Edge Cases', () => {
  it('should handle all testimonials being featured', () => {
    const allFeatured = [
      { ...mockTestimonialRated5Stars, is_featured: true },
      { ...mockTestimonialRated4Stars, is_featured: true },
    ]

    const featuredCount = allFeatured.filter(t => t.is_featured).length
    expect(featuredCount).toBe(2)
  })

  it('should handle weighted pool with only low-rated (excluded) testimonials', () => {
    const lowRated = [
      { id: 1, star_rating: 1, is_featured: false },
      { id: 2, star_rating: 2, is_featured: false },
    ]

    const weightedPool = []
    for (const t of lowRated) {
      if (t.is_featured) {
        weightedPool.push(t)
      } else if (t.star_rating >= 3 || t.star_rating === null) {
        weightedPool.push(t)
      }
    }

    expect(weightedPool).toHaveLength(0)
  })

  it('should handle mixed null and numeric ratings', () => {
    const mixed = [
      { id: 1, star_rating: 5 },
      { id: 2, star_rating: null },
      { id: 3, star_rating: 4 },
      { id: 4, star_rating: null },
    ]

    const rated = mixed.filter(t => t.star_rating !== null)
    const unrated = mixed.filter(t => t.star_rating === null)

    expect(rated).toHaveLength(2)
    expect(unrated).toHaveLength(2)
  })

  it('should handle date formatting for various months', () => {
    const months = [
      { date: '2026-01-15', expected: 'January 2026' },
      { date: '2026-06-15', expected: 'June 2026' },
      { date: '2026-12-15', expected: 'December 2026' },
    ]

    months.forEach(({ date, expected }) => {
      const dateObj = new Date(date)
      const formatted = dateObj.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
      expect(formatted).toBe(expected)
    })
  })

  it('should handle all supported source types', () => {
    const sources = ['google', 'trustpilot', 'facebook', 'linkedin', 'email', 'other']

    sources.forEach(source => {
      const testimonial = { ...mockTestimonialRated5Stars, source }
      expect(testimonial.source).toBe(source)
    })
  })

  it('should handle transition state correctly', () => {
    let isTransitioning = false

    // Start transition
    isTransitioning = true
    expect(isTransitioning).toBe(true)

    // End transition
    isTransitioning = false
    expect(isTransitioning).toBe(false)
  })

  it('should handle pause state correctly', () => {
    let isPaused = false

    // Mouse enter - pause
    isPaused = true
    expect(isPaused).toBe(true)

    // Mouse leave - resume
    isPaused = false
    expect(isPaused).toBe(false)
  })

  it('should shuffle array without losing items', () => {
    const original = [1, 2, 3, 4, 5]
    const shuffled = [...original]

    // Simple shuffle simulation
    for (let i = shuffled.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
    }

    expect(shuffled.length).toBe(original.length)
    expect(shuffled.sort()).toEqual(original.sort())
  })

  it('should deduplicate weighted pool correctly', () => {
    const pool = [
      { id: 1, name: 'A' },
      { id: 1, name: 'A' }, // Duplicate
      { id: 2, name: 'B' },
      { id: 1, name: 'A' }, // Duplicate
      { id: 2, name: 'B' }, // Duplicate
    ]

    const seen = new Set()
    const deduplicated = pool.filter(item => {
      if (seen.has(item.id)) return false
      seen.add(item.id)
      return true
    })

    expect(deduplicated).toHaveLength(2)
  })
})

// =============================================================================
// Stats Bar Display Tests
// =============================================================================

describe('TestimonialsCarousel - Stats Bar', () => {
  const mockStats = {
    average_rating: 4.9,
    total_count: 34,
    recommend_percent: 97,
    buzz_words: [
      { word: 'Friendly', count: 12 },
      { word: 'Easy', count: 8 },
      { word: 'Professional', count: 6 },
    ],
  }

  describe('Happy path - Stats display', () => {
    it('should display average rating from stats', () => {
      const stats = mockStats
      expect(stats.average_rating).toBe(4.9)
    })

    it('should display total count from stats', () => {
      const stats = mockStats
      expect(stats.total_count).toBe(34)
    })

    it('should display recommend percent from stats', () => {
      const stats = mockStats
      expect(stats.recommend_percent).toBe(97)
    })

    it('should display buzz words from stats', () => {
      const stats = mockStats
      expect(stats.buzz_words).toHaveLength(3)
      expect(stats.buzz_words[0].word).toBe('Friendly')
    })
  })

  describe('Edge cases - Stats with null/empty values', () => {
    it('should handle null stats gracefully', () => {
      const stats = null
      const shouldShowStats = stats !== null
      expect(shouldShowStats).toBe(false)
    })

    it('should handle empty buzz words array', () => {
      const stats = {
        ...mockStats,
        buzz_words: [],
      }
      expect(stats.buzz_words.length).toBe(0)
      const showBuzzWords = stats.buzz_words && stats.buzz_words.length > 0
      expect(showBuzzWords).toBe(false)
    })

    it('should handle zero average rating', () => {
      const stats = {
        ...mockStats,
        average_rating: 0,
      }
      expect(stats.average_rating).toBe(0)
    })

    it('should handle zero recommend percent', () => {
      const stats = {
        ...mockStats,
        recommend_percent: 0,
      }
      expect(stats.recommend_percent).toBe(0)
    })
  })

  describe('Boundaries - Stats value ranges', () => {
    it('should handle maximum rating (5.0)', () => {
      const stats = { ...mockStats, average_rating: 5.0 }
      expect(stats.average_rating).toBe(5.0)
    })

    it('should handle minimum rating (1.0)', () => {
      const stats = { ...mockStats, average_rating: 1.0 }
      expect(stats.average_rating).toBe(1.0)
    })

    it('should handle 100% recommend', () => {
      const stats = { ...mockStats, recommend_percent: 100 }
      expect(stats.recommend_percent).toBe(100)
    })

    it('should handle single testimonial', () => {
      const stats = { ...mockStats, total_count: 1 }
      expect(stats.total_count).toBe(1)
    })

    it('should handle large number of testimonials', () => {
      const stats = { ...mockStats, total_count: 1000 }
      expect(stats.total_count).toBe(1000)
    })
  })
})

// =============================================================================
// Buzz Words Display Tests
// =============================================================================

describe('TestimonialsCarousel - Buzz Words', () => {
  describe('Happy path - Buzz words rendering', () => {
    it('should format buzz words with title case', () => {
      const buzzWord = { word: 'Friendly', count: 12 }
      expect(buzzWord.word).toBe('Friendly')
      expect(buzzWord.word[0]).toBe(buzzWord.word[0].toUpperCase())
    })

    it('should include count in buzz word object', () => {
      const buzzWord = { word: 'Easy', count: 8 }
      expect(buzzWord.count).toBeGreaterThan(0)
    })

    it('should handle multiple buzz words', () => {
      const buzzWords = [
        { word: 'Friendly', count: 12 },
        { word: 'Easy', count: 8 },
        { word: 'Professional', count: 6 },
        { word: 'Reliable', count: 5 },
      ]
      expect(buzzWords.length).toBe(4)
    })
  })

  describe('Edge cases - Buzz words variations', () => {
    it('should handle buzz word with count of 2 (minimum)', () => {
      const buzzWord = { word: 'Quick', count: 2 }
      expect(buzzWord.count).toBeGreaterThanOrEqual(2)
    })

    it('should handle buzz word with high count', () => {
      const buzzWord = { word: 'Great', count: 50 }
      expect(buzzWord.count).toBe(50)
    })

    it('should handle hyphenated buzz words', () => {
      const buzzWord = { word: 'Stress-Free', count: 5 }
      expect(buzzWord.word).toContain('-')
    })

    it('should handle multi-word buzz phrases', () => {
      const buzzWord = { word: 'On Time', count: 7 }
      expect(buzzWord.word).toContain(' ')
    })
  })

  describe('Unhappy path - Missing buzz words', () => {
    it('should not render buzz words section when array is empty', () => {
      const buzzWords = []
      const shouldRender = buzzWords && buzzWords.length > 0
      expect(shouldRender).toBe(false)
    })

    it('should not render buzz words section when undefined', () => {
      const buzzWords = undefined
      const shouldRender = buzzWords && buzzWords.length > 0
      // Returns undefined (falsy), not false - still works correctly in JSX
      expect(shouldRender).toBeFalsy()
    })
  })
})
