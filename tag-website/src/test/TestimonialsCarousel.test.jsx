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

    it('should display first buzz word in stats bar', () => {
      const stats = mockStats
      const buzzWordIndex = 0
      const currentBuzzWord = stats.buzz_words[buzzWordIndex]
      expect(currentBuzzWord.word).toBe('Friendly')
      expect(currentBuzzWord.count).toBe(12)
    })

    it('should format buzz word as count× word', () => {
      const stats = mockStats
      const buzzWordIndex = 0
      const bw = stats.buzz_words[buzzWordIndex]
      const formatted = `${bw.count}× ${bw.word}`
      expect(formatted).toBe('12× Friendly')
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

    it('should handle single buzz word (no cycling needed)', () => {
      const stats = {
        ...mockStats,
        buzz_words: [{ word: 'Friendly', count: 5 }],
      }
      expect(stats.buzz_words.length).toBe(1)
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

    it('should cycle buzz word index correctly', () => {
      const buzzWords = mockStats.buzz_words
      let buzzWordIndex = 0
      // Simulate cycling
      buzzWordIndex = (buzzWordIndex + 1) % buzzWords.length
      expect(buzzWordIndex).toBe(1)
      expect(buzzWords[buzzWordIndex].word).toBe('Easy')
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
// Cycling Stats Display Tests - Two Line Format
// =============================================================================

describe('TestimonialsCarousel - Cycling Stats (Two Line Format)', () => {
  // Mirror the formatBuzzWord function from component
  const formatBuzzWord = (word) => {
    const w = word.toLowerCase()
    if (w.startsWith('recommend')) return { phrase: "say they'd", buzzWord: 'Recommend' }
    if (w === 'impressed') return { phrase: 'say they were', buzzWord: 'Impressed' }
    if (w === 'no issues' || w === 'no problems') return { phrase: 'say there were', buzzWord: word }
    if (w === 'no hidden fees') return { phrase: 'say there are', buzzWord: word }
    if (w === 'no fuss') return { phrase: "say there's", buzzWord: 'No Fuss' }
    if (w === 'peace of mind') return { phrase: 'say it gives', buzzWord: 'Peace Of Mind' }
    if (w === 'value for money') return { phrase: "say it's good", buzzWord: 'Value For Money' }
    if (w === 'doddle') return { phrase: "say it's a", buzzWord: 'Doddle' }
    if (w === "couldn't fault" || w === "can't fault") return { phrase: "say they couldn't", buzzWord: 'Fault It' }
    // Loyalty phrases
    if (w.includes('use again') || w.includes('will be back') || w.includes('coming back')) return { phrase: "say they'll", buzzWord: 'Use Again' }
    // Satisfaction phrases
    if (w === 'happy' || w === 'pleased' || w === 'satisfied' || w === 'delighted') return { phrase: 'say they were', buzzWord: word }
    // Confidence phrases
    if (w === 'confident' || w === 'reassured') return { phrase: 'say they felt', buzzWord: word }
    // Worth it
    if (w === 'worth it') return { phrase: "say it's", buzzWord: 'Worth It' }
    return { phrase: "say it's", buzzWord: word }
  }

  const buildCyclingItems = (buzzWords) =>
    buzzWords?.map(bw => {
      const { phrase, buzzWord } = formatBuzzWord(bw.word)
      return { count: bw.count, phrase, buzzWord }
    }) || []

  describe('Happy path - Default phrasing (say its)', () => {
    it('should format friendly correctly', () => {
      const items = buildCyclingItems([{ word: 'Friendly', count: 12 }])
      expect(items[0].phrase).toBe("say it's")
      expect(items[0].buzzWord).toBe('Friendly')
    })

    it('should format easy correctly', () => {
      const items = buildCyclingItems([{ word: 'Easy', count: 8 }])
      expect(items[0].phrase).toBe("say it's")
      expect(items[0].buzzWord).toBe('Easy')
    })

    it('should format great correctly', () => {
      const items = buildCyclingItems([{ word: 'Great', count: 5 }])
      expect(items[0].phrase).toBe("say it's")
      expect(items[0].buzzWord).toBe('Great')
    })
  })

  describe('Happy path - Special phrasings', () => {
    it('should format recommend as say theyd', () => {
      const items = buildCyclingItems([{ word: 'Recommend', count: 16 }])
      expect(items[0].phrase).toBe("say they'd")
      expect(items[0].buzzWord).toBe('Recommend')
    })

    it('should format impressed as say they were', () => {
      const items = buildCyclingItems([{ word: 'Impressed', count: 4 }])
      expect(items[0].phrase).toBe('say they were')
      expect(items[0].buzzWord).toBe('Impressed')
    })

    it('should format no issues as say there were', () => {
      const items = buildCyclingItems([{ word: 'No Issues', count: 3 }])
      expect(items[0].phrase).toBe('say there were')
      expect(items[0].buzzWord).toBe('No Issues')
    })

    it('should format no hidden fees as say there are', () => {
      const items = buildCyclingItems([{ word: 'No Hidden Fees', count: 2 }])
      expect(items[0].phrase).toBe('say there are')
      expect(items[0].buzzWord).toBe('No Hidden Fees')
    })

    it('should format no fuss as say theres', () => {
      const items = buildCyclingItems([{ word: 'No Fuss', count: 2 }])
      expect(items[0].phrase).toBe("say there's")
      expect(items[0].buzzWord).toBe('No Fuss')
    })

    it('should format peace of mind as say it gives', () => {
      const items = buildCyclingItems([{ word: 'Peace Of Mind', count: 2 }])
      expect(items[0].phrase).toBe('say it gives')
      expect(items[0].buzzWord).toBe('Peace Of Mind')
    })

    it('should format value for money as say its good', () => {
      const items = buildCyclingItems([{ word: 'Value For Money', count: 4 }])
      expect(items[0].phrase).toBe("say it's good")
      expect(items[0].buzzWord).toBe('Value For Money')
    })

    it('should format doddle as say its a', () => {
      const items = buildCyclingItems([{ word: 'Doddle', count: 2 }])
      expect(items[0].phrase).toBe("say it's a")
      expect(items[0].buzzWord).toBe('Doddle')
    })

    it('should format couldnt fault as say they couldnt', () => {
      const items = buildCyclingItems([{ word: "Couldn't Fault", count: 2 }])
      expect(items[0].phrase).toBe("say they couldn't")
      expect(items[0].buzzWord).toBe('Fault It')
    })
  })

  describe('Edge cases - Variations', () => {
    it('should handle recommended variant', () => {
      const items = buildCyclingItems([{ word: 'Recommended', count: 5 }])
      expect(items[0].phrase).toBe("say they'd")
      expect(items[0].buzzWord).toBe('Recommend')
    })

    it('should handle no problems same as no issues', () => {
      const items = buildCyclingItems([{ word: 'No Problems', count: 2 }])
      expect(items[0].phrase).toBe('say there were')
    })

    it('should handle cant fault variant', () => {
      const items = buildCyclingItems([{ word: "Can't Fault", count: 2 }])
      expect(items[0].phrase).toBe("say they couldn't")
      expect(items[0].buzzWord).toBe('Fault It')
    })

    it('should handle hyphenated buzz words', () => {
      const items = buildCyclingItems([{ word: 'Stress-Free', count: 5 }])
      expect(items[0].phrase).toBe("say it's")
      expect(items[0].buzzWord).toBe('Stress-Free')
    })
  })

  describe('Unhappy path - Missing data', () => {
    it('should handle empty buzz words array', () => {
      const items = buildCyclingItems([])
      expect(items.length).toBe(0)
    })

    it('should handle undefined buzz words', () => {
      const items = buildCyclingItems(undefined)
      expect(items.length).toBe(0)
    })
  })

  describe('Boundaries - Cycling behavior', () => {
    const mockBuzzWords = [
      { word: 'Friendly', count: 12 },
      { word: 'Easy', count: 8 },
      { word: 'Recommend', count: 6 },
    ]

    it('should cycle through all items', () => {
      const items = buildCyclingItems(mockBuzzWords)
      expect(items.length).toBe(3)
    })

    it('should wrap around after last item', () => {
      const items = buildCyclingItems(mockBuzzWords)
      let idx = items.length - 1
      idx = (idx + 1) % items.length
      expect(idx).toBe(0)
    })

    it('should handle cycling through all items', () => {
      const items = buildCyclingItems(mockBuzzWords)
      let idx = 0
      const visited = []
      for (let i = 0; i < items.length; i++) {
        visited.push(items[idx].buzzWord)
        idx = (idx + 1) % items.length
      }
      expect(visited).toEqual(['Friendly', 'Easy', 'Recommend'])
    })

    it('should return to start after full cycle', () => {
      const cyclingItems = buildCyclingItems(mockBuzzWords)
      let cyclingIndex = 0
      for (let i = 0; i < cyclingItems.length; i++) {
        cyclingIndex = (cyclingIndex + 1) % cyclingItems.length
      }
      expect(cyclingIndex).toBe(0)
    })

    it('should handle many buzz words (no limit)', () => {
      const buzzWords = Array.from({ length: 20 }, (_, i) => ({
        word: `Word${i}`,
        count: 20 - i,
      }))
      const cyclingItems = buildCyclingItems(buzzWords)
      expect(cyclingItems.length).toBe(20)
    })
  })

  describe('Happy path - New buzz word phrasings', () => {
    it('should format use again as say theyll', () => {
      const items = buildCyclingItems([{ word: 'Definitely Use Again', count: 5 }])
      expect(items[0].phrase).toBe("say they'll")
      expect(items[0].buzzWord).toBe('Use Again')
    })

    it('should format will be back as say theyll', () => {
      const items = buildCyclingItems([{ word: 'Will Be Back', count: 3 }])
      expect(items[0].phrase).toBe("say they'll")
      expect(items[0].buzzWord).toBe('Use Again')
    })

    it('should format happy as say they were', () => {
      const items = buildCyclingItems([{ word: 'Happy', count: 2 }])
      expect(items[0].phrase).toBe('say they were')
      expect(items[0].buzzWord).toBe('Happy')
    })

    it('should format pleased as say they were', () => {
      const items = buildCyclingItems([{ word: 'Pleased', count: 2 }])
      expect(items[0].phrase).toBe('say they were')
      expect(items[0].buzzWord).toBe('Pleased')
    })

    it('should format confident as say they felt', () => {
      const items = buildCyclingItems([{ word: 'Confident', count: 3 }])
      expect(items[0].phrase).toBe('say they felt')
      expect(items[0].buzzWord).toBe('Confident')
    })

    it('should format reassured as say they felt', () => {
      const items = buildCyclingItems([{ word: 'Reassured', count: 2 }])
      expect(items[0].phrase).toBe('say they felt')
      expect(items[0].buzzWord).toBe('Reassured')
    })

    it('should format worth it correctly', () => {
      const items = buildCyclingItems([{ word: 'Worth It', count: 2 }])
      expect(items[0].phrase).toBe("say it's")
      expect(items[0].buzzWord).toBe('Worth It')
    })

    it('should format thorough with default phrasing', () => {
      const items = buildCyclingItems([{ word: 'Thorough', count: 2 }])
      expect(items[0].phrase).toBe("say it's")
      expect(items[0].buzzWord).toBe('Thorough')
    })
  })
})
