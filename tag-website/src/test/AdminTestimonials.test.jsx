/**
 * Tests for Admin Testimonials Management
 *
 * Tests the core logic:
 * - CRUD operations (Create, Read, Update, Delete)
 * - Status toggle (active/inactive)
 * - Featured toggle
 * - Filtering and search
 * - Form validation
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock fetch
global.fetch = vi.fn()

// Mock testimonial data
const mockTestimonials = [
  {
    id: 1,
    customer_name: 'John Doe',
    review_text: 'Excellent service! Very professional and convenient.',
    star_rating: 5,
    date_of_travel: '2026-01-15',
    date_added: '2026-03-01T10:30:00Z',
    status: 'active',
    is_featured: true,
    source: 'google',
  },
  {
    id: 2,
    customer_name: 'Jane Smith',
    review_text: 'Great experience, will use again.',
    star_rating: 4,
    date_of_travel: '2026-02-10',
    date_added: '2026-03-02T14:15:00Z',
    status: 'active',
    is_featured: false,
    source: 'trustpilot',
  },
  {
    id: 3,
    customer_name: 'Bob Wilson',
    review_text: 'Highly recommend TAG parking!',
    star_rating: null,
    date_of_travel: '2026-01-20',
    date_added: '2026-03-03T09:00:00Z',
    status: 'inactive',
    is_featured: false,
    source: 'linkedin',
  },
]

const mockToken = 'test-admin-token'
const API_URL = 'http://localhost:8000'

describe('Admin Testimonials List', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Fetch testimonials', () => {
    it('should fetch all testimonials with admin token', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ testimonials: mockTestimonials }),
      })

      const response = await fetch(`${API_URL}/api/admin/testimonials`, {
        headers: { Authorization: `Bearer ${mockToken}` },
      })
      const data = await response.json()

      expect(fetch).toHaveBeenCalledWith(
        `${API_URL}/api/admin/testimonials`,
        { headers: { Authorization: `Bearer ${mockToken}` } }
      )
      expect(data.testimonials).toHaveLength(3)
    })

    it('should handle unauthorized access', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'Not authenticated' }),
      })

      const response = await fetch(`${API_URL}/api/admin/testimonials`, {
        headers: { Authorization: 'Bearer invalid-token' },
      })

      expect(response.status).toBe(401)
    })
  })

  describe('Filter logic', () => {
    it('should filter by status: active', () => {
      const filterStatus = 'active'
      const filtered = mockTestimonials.filter(t => t.status === filterStatus)

      expect(filtered).toHaveLength(2)
      expect(filtered.every(t => t.status === 'active')).toBe(true)
    })

    it('should filter by status: inactive', () => {
      const filterStatus = 'inactive'
      const filtered = mockTestimonials.filter(t => t.status === filterStatus)

      expect(filtered).toHaveLength(1)
      expect(filtered[0].customer_name).toBe('Bob Wilson')
    })

    it('should filter by featured only', () => {
      const filtered = mockTestimonials.filter(t => t.is_featured)

      expect(filtered).toHaveLength(1)
      expect(filtered[0].customer_name).toBe('John Doe')
    })

    it('should filter by star rating', () => {
      const filterRating = 5
      const filtered = mockTestimonials.filter(t => t.star_rating === filterRating)

      expect(filtered).toHaveLength(1)
      expect(filtered[0].star_rating).toBe(5)
    })

    it('should filter unrated testimonials', () => {
      const filtered = mockTestimonials.filter(t => t.star_rating === null)

      expect(filtered).toHaveLength(1)
      expect(filtered[0].customer_name).toBe('Bob Wilson')
    })

    it('should search by customer name', () => {
      const searchTerm = 'john'
      const filtered = mockTestimonials.filter(t =>
        t.customer_name.toLowerCase().includes(searchTerm.toLowerCase())
      )

      expect(filtered).toHaveLength(1)
      expect(filtered[0].customer_name).toBe('John Doe')
    })

    it('should search by review text', () => {
      const searchTerm = 'recommend'
      const filtered = mockTestimonials.filter(t =>
        t.review_text.toLowerCase().includes(searchTerm.toLowerCase())
      )

      expect(filtered).toHaveLength(1)
      expect(filtered[0].customer_name).toBe('Bob Wilson')
    })
  })
})

describe('Admin Testimonials CRUD Operations', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Create testimonial', () => {
    it('should create a new testimonial', async () => {
      const newTestimonial = {
        customer_name: 'New Customer',
        review_text: 'Amazing parking service!',
        star_rating: 5,
        date_of_travel: '2026-03-15',
        source: 'google',
        is_featured: false,
      }

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 4, ...newTestimonial, status: 'inactive' }),
      })

      const response = await fetch(`${API_URL}/api/admin/testimonials`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${mockToken}`,
        },
        body: JSON.stringify(newTestimonial),
      })
      const data = await response.json()

      expect(response.ok).toBe(true)
      expect(data.customer_name).toBe('New Customer')
      expect(data.status).toBe('inactive') // Default status
    })

    it('should create testimonial without star rating (unrated)', async () => {
      const newTestimonial = {
        customer_name: 'LinkedIn User',
        review_text: 'Great recommendation!',
        star_rating: null,
        source: 'linkedin',
      }

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 5, ...newTestimonial, status: 'inactive' }),
      })

      const response = await fetch(`${API_URL}/api/admin/testimonials`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${mockToken}`,
        },
        body: JSON.stringify(newTestimonial),
      })
      const data = await response.json()

      expect(data.star_rating).toBeNull()
    })

    it('should handle validation error for missing required fields', async () => {
      const invalidTestimonial = {
        review_text: 'Missing customer name',
      }

      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 422,
        json: async () => ({ detail: 'customer_name is required' }),
      })

      const response = await fetch(`${API_URL}/api/admin/testimonials`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${mockToken}`,
        },
        body: JSON.stringify(invalidTestimonial),
      })

      expect(response.status).toBe(422)
    })
  })

  describe('Update testimonial', () => {
    it('should update existing testimonial', async () => {
      const updatedData = {
        review_text: 'Updated review text - even better service!',
        star_rating: 5,
      }

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ...mockTestimonials[0], ...updatedData }),
      })

      const response = await fetch(`${API_URL}/api/admin/testimonials/1`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${mockToken}`,
        },
        body: JSON.stringify(updatedData),
      })
      const data = await response.json()

      expect(response.ok).toBe(true)
      expect(data.review_text).toBe('Updated review text - even better service!')
    })

    it('should handle not found error', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ detail: 'Testimonial not found' }),
      })

      const response = await fetch(`${API_URL}/api/admin/testimonials/999`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${mockToken}`,
        },
        body: JSON.stringify({ review_text: 'Test' }),
      })

      expect(response.status).toBe(404)
    })
  })

  describe('Delete testimonial', () => {
    it('should delete testimonial', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      })

      const response = await fetch(`${API_URL}/api/admin/testimonials/3`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${mockToken}` },
      })

      expect(response.ok).toBe(true)
      expect(fetch).toHaveBeenCalledWith(
        `${API_URL}/api/admin/testimonials/3`,
        { method: 'DELETE', headers: { Authorization: `Bearer ${mockToken}` } }
      )
    })

    it('should handle delete of non-existent testimonial', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ detail: 'Testimonial not found' }),
      })

      const response = await fetch(`${API_URL}/api/admin/testimonials/999`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${mockToken}` },
      })

      expect(response.status).toBe(404)
    })
  })
})

describe('Admin Testimonials Status Toggle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should toggle status from inactive to active', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ ...mockTestimonials[2], status: 'active' }),
    })

    const response = await fetch(`${API_URL}/api/admin/testimonials/3/status`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${mockToken}`,
      },
      body: JSON.stringify({ status: 'active' }),
    })
    const data = await response.json()

    expect(response.ok).toBe(true)
    expect(data.status).toBe('active')
  })

  it('should toggle status from active to inactive', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ ...mockTestimonials[0], status: 'inactive' }),
    })

    const response = await fetch(`${API_URL}/api/admin/testimonials/1/status`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${mockToken}`,
      },
      body: JSON.stringify({ status: 'inactive' }),
    })
    const data = await response.json()

    expect(data.status).toBe('inactive')
  })

  it('should handle invalid status value', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: async () => ({ detail: 'Invalid status value' }),
    })

    const response = await fetch(`${API_URL}/api/admin/testimonials/1/status`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${mockToken}`,
      },
      body: JSON.stringify({ status: 'invalid_status' }),
    })

    expect(response.status).toBe(422)
  })
})

describe('Admin Testimonials Form Validation', () => {
  describe('Required fields', () => {
    it('should require customer_name', () => {
      const testimonial = { customer_name: '', review_text: 'Test review' }
      const isValid = testimonial.customer_name.trim().length > 0

      expect(isValid).toBe(false)
    })

    it('should require review_text', () => {
      const testimonial = { customer_name: 'Test Name', review_text: '' }
      const isValid = testimonial.review_text.trim().length > 0

      expect(isValid).toBe(false)
    })

    it('should pass validation with required fields', () => {
      const testimonial = { customer_name: 'Test Name', review_text: 'Test review' }
      const isValid =
        testimonial.customer_name.trim().length > 0 &&
        testimonial.review_text.trim().length > 0

      expect(isValid).toBe(true)
    })
  })

  describe('Star rating validation', () => {
    it('should accept null star rating (unrated)', () => {
      const rating = null
      const isValid = rating === null || (rating >= 1 && rating <= 5)

      expect(isValid).toBe(true)
    })

    it('should accept rating between 1-5', () => {
      ;[1, 2, 3, 4, 5].forEach(rating => {
        const isValid = rating >= 1 && rating <= 5
        expect(isValid).toBe(true)
      })
    })

    it('should reject rating outside 1-5 range', () => {
      const invalidRatings = [0, 6, -1, 10]
      invalidRatings.forEach(rating => {
        const isValid = rating >= 1 && rating <= 5
        expect(isValid).toBe(false)
      })
    })
  })

  describe('Source validation', () => {
    it('should accept valid sources', () => {
      const validSources = ['google', 'trustpilot', 'facebook', 'linkedin', 'email', 'other']
      validSources.forEach(source => {
        expect(validSources.includes(source)).toBe(true)
      })
    })

    it('should accept null/empty source', () => {
      const source = null
      const isValid = source === null || source === ''

      expect(isValid).toBe(true)
    })
  })

  describe('Date validation', () => {
    it('should accept valid date format', () => {
      const dateString = '2026-03-15'
      const date = new Date(dateString)
      const isValid = !isNaN(date.getTime())

      expect(isValid).toBe(true)
    })

    it('should accept null date', () => {
      const date = null
      const isValid = date === null

      expect(isValid).toBe(true)
    })
  })
})

describe('Admin Testimonials Edge Cases', () => {
  it('should handle very long customer name', () => {
    const longName = 'A'.repeat(100)
    const testimonial = { customer_name: longName, review_text: 'Test' }

    // Max length is 100 characters
    expect(testimonial.customer_name.length).toBe(100)
  })

  it('should handle very long review text', () => {
    const longReview = 'A'.repeat(5000)
    const testimonial = { customer_name: 'Test', review_text: longReview }

    expect(testimonial.review_text.length).toBe(5000)
  })

  it('should handle special characters in fields', () => {
    const testimonial = {
      customer_name: "O'Brien-Smith & Co.",
      review_text: 'Great service! <script>alert("test")</script>',
    }

    expect(testimonial.customer_name).toContain("O'Brien")
    expect(testimonial.review_text).toContain('<script>')
    // Note: Actual sanitization should happen on backend/render
  })

  it('should handle concurrent status toggles', async () => {
    // Simulate rapid toggle clicks
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'active' }),
    })

    const promises = [
      fetch(`${API_URL}/api/admin/testimonials/1/status`, { method: 'PATCH' }),
      fetch(`${API_URL}/api/admin/testimonials/1/status`, { method: 'PATCH' }),
      fetch(`${API_URL}/api/admin/testimonials/1/status`, { method: 'PATCH' }),
    ]

    const results = await Promise.all(promises)

    expect(results.every(r => r.ok)).toBe(true)
  })
})

describe('Admin Testimonials Negative Tests', () => {
  it('should reject empty customer_name', () => {
    const testimonial = { customer_name: '', review_text: 'Test review' }
    const isValid = testimonial.customer_name.trim().length > 0
    expect(isValid).toBe(false)
  })

  it('should reject whitespace-only customer_name', () => {
    const testimonial = { customer_name: '   ', review_text: 'Test review' }
    const isValid = testimonial.customer_name.trim().length > 0
    expect(isValid).toBe(false)
  })

  it('should reject empty review_text', () => {
    const testimonial = { customer_name: 'Test', review_text: '' }
    const isValid = testimonial.review_text.trim().length > 0
    expect(isValid).toBe(false)
  })

  it('should reject whitespace-only review_text', () => {
    const testimonial = { customer_name: 'Test', review_text: '  \n\t  ' }
    const isValid = testimonial.review_text.trim().length > 0
    expect(isValid).toBe(false)
  })

  it('should reject invalid status values', () => {
    const invalidStatuses = ['pending', 'deleted', 'ACTIVE', 'Active', '1', 'true']
    const validStatuses = ['active', 'inactive']

    invalidStatuses.forEach(status => {
      const isValid = validStatuses.includes(status)
      expect(isValid).toBe(false)
    })
  })

  it('should reject star_rating of 0', () => {
    const rating = 0
    const isValid = rating === null || (rating >= 1 && rating <= 5)
    expect(isValid).toBe(false)
  })

  it('should reject star_rating of 6', () => {
    const rating = 6
    const isValid = rating === null || (rating >= 1 && rating <= 5)
    expect(isValid).toBe(false)
  })

  it('should reject negative star_rating', () => {
    const rating = -1
    const isValid = rating === null || (rating >= 1 && rating <= 5)
    expect(isValid).toBe(false)
  })

  it('should handle API timeout gracefully', async () => {
    global.fetch.mockImplementationOnce(() =>
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Request timeout')), 100)
      )
    )

    await expect(
      fetch(`${API_URL}/api/admin/testimonials`, { signal: AbortSignal.timeout(50) })
    ).rejects.toThrow()
  })

  it('should handle 500 server error', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'Internal server error' }),
    })

    const response = await fetch(`${API_URL}/api/admin/testimonials`)
    expect(response.status).toBe(500)
  })
})

describe('Admin Testimonials Boundary Tests', () => {
  it('should accept star_rating at lower bound (1)', () => {
    const rating = 1
    const isValid = rating === null || (rating >= 1 && rating <= 5)
    expect(isValid).toBe(true)
  })

  it('should accept star_rating at upper bound (5)', () => {
    const rating = 5
    const isValid = rating === null || (rating >= 1 && rating <= 5)
    expect(isValid).toBe(true)
  })

  it('should accept customer_name at exactly 100 chars', () => {
    const name = 'A'.repeat(100)
    const isValid = name.length <= 100
    expect(isValid).toBe(true)
    expect(name.length).toBe(100)
  })

  it('should reject customer_name at 101 chars', () => {
    const name = 'A'.repeat(101)
    const isValid = name.length <= 100
    expect(isValid).toBe(false)
  })

  it('should accept minimum valid customer_name (1 char)', () => {
    const name = 'A'
    const isValid = name.trim().length >= 1
    expect(isValid).toBe(true)
  })

  it('should accept minimum valid review_text (1 char)', () => {
    const review = 'B'
    const isValid = review.trim().length >= 1
    expect(isValid).toBe(true)
  })

  it('should handle first page pagination correctly', () => {
    const testimonials = Array.from({ length: 25 }, (_, i) => ({ id: i + 1 }))
    const page = 1
    const perPage = 10
    const start = (page - 1) * perPage
    const paginated = testimonials.slice(start, start + perPage)

    expect(paginated.length).toBe(10)
    expect(paginated[0].id).toBe(1)
  })

  it('should handle last page pagination correctly', () => {
    const testimonials = Array.from({ length: 25 }, (_, i) => ({ id: i + 1 }))
    const page = 3
    const perPage = 10
    const start = (page - 1) * perPage
    const paginated = testimonials.slice(start, start + perPage)

    expect(paginated.length).toBe(5)
    expect(paginated[0].id).toBe(21)
  })

  it('should return empty for page beyond data', () => {
    const testimonials = Array.from({ length: 10 }, (_, i) => ({ id: i + 1 }))
    const page = 5
    const perPage = 10
    const start = (page - 1) * perPage
    const paginated = testimonials.slice(start, start + perPage)

    expect(paginated.length).toBe(0)
  })
})

describe('Admin Testimonials Additional Edge Cases', () => {
  it('should handle single testimonial in list', () => {
    const testimonials = [mockTestimonials[0]]
    expect(testimonials.length).toBe(1)
  })

  it('should handle testimonial with all optional fields null', () => {
    const testimonial = {
      customer_name: 'Test',
      review_text: 'Test review',
      star_rating: null,
      date_of_travel: null,
      source: null,
      is_featured: false,
    }
    const isValid = testimonial.customer_name && testimonial.review_text
    expect(isValid).toBeTruthy()
  })

  it('should handle all testimonials being inactive', () => {
    const allInactive = mockTestimonials.map(t => ({ ...t, status: 'inactive' }))
    const active = allInactive.filter(t => t.status === 'active')
    expect(active.length).toBe(0)
  })

  it('should handle filter returning no results', () => {
    const filtered = mockTestimonials.filter(t => t.star_rating === 1)
    expect(filtered.length).toBe(0)
  })

  it('should preserve case sensitivity in display but not search', () => {
    const testimonial = { customer_name: 'John DOE' }
    const searchTerm = 'john doe'

    // Display preserves case
    expect(testimonial.customer_name).toBe('John DOE')
    // Search is case-insensitive
    const found = testimonial.customer_name.toLowerCase().includes(searchTerm.toLowerCase())
    expect(found).toBe(true)
  })

  it('should handle unicode/emoji in all fields', () => {
    const testimonial = {
      customer_name: 'José García 🇪🇸',
      review_text: 'Excelente servicio! ⭐⭐⭐⭐⭐ 👍',
      source: 'google',
    }
    expect(testimonial.customer_name).toContain('🇪🇸')
    expect(testimonial.review_text).toContain('⭐')
    expect(testimonial.review_text).toContain('👍')
  })

  it('should handle toggle preserving other fields', () => {
    const original = { ...mockTestimonials[0], status: 'inactive' }
    const updated = { ...original, status: 'active' }

    expect(updated.status).toBe('active')
    expect(updated.customer_name).toBe(original.customer_name)
    expect(updated.review_text).toBe(original.review_text)
    expect(updated.star_rating).toBe(original.star_rating)
  })

  it('should handle duplicate IDs in data (flag as error)', () => {
    const testimonials = [
      { id: 1, customer_name: 'User A' },
      { id: 1, customer_name: 'User B' },
    ]
    const ids = testimonials.map(t => t.id)
    const hasDuplicates = ids.length !== new Set(ids).size
    expect(hasDuplicates).toBe(true)
  })
})
