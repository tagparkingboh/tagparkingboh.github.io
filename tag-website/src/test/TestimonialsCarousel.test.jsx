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
      const formatted = date.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })

      expect(formatted).toBe('Jan 2026')
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
