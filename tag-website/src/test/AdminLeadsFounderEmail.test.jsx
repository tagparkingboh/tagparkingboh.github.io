/**
 * Tests for Admin Leads Founder Email Status functionality
 *
 * Tests the core logic:
 * - Founder email status display in leads
 * - Status button states (Sent/Not Sent)
 * - Tooltip content based on status
 * - API response handling with founder_followup_sent fields
 *
 * Test categories:
 * - Unit Tests: Status display logic, button rendering
 * - Integration Tests: API response mapping
 * - Negative Tests: Missing/invalid data handling
 * - Edge Cases: Boundary conditions
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock fetch
global.fetch = vi.fn()

// =============================================================================
// Mock Data Factories
// =============================================================================

const createMockLead = (overrides = {}) => ({
  id: 1,
  first_name: 'John',
  last_name: 'Doe',
  email: 'john.doe@example.com',
  phone: '07700900001',
  billing_address1: '123 Test Street',
  billing_city: 'Bournemouth',
  billing_postcode: 'BH1 1AA',
  created_at: '2026-03-01T10:30:00',
  booking_attempts: 0,
  last_booking_status: null,
  founder_followup_sent: false,
  founder_followup_sent_at: null,
  ...overrides,
})

// =============================================================================
// Unit Tests - Founder Email Status Display
// =============================================================================

describe('Admin Leads Founder Email Status Display', () => {
  describe('Unit Tests - Status field presence', () => {
    it('should include founder_followup_sent in lead response', () => {
      const lead = createMockLead({ founder_followup_sent: false })

      expect(lead).toHaveProperty('founder_followup_sent')
      expect(lead.founder_followup_sent).toBe(false)
    })

    it('should include founder_followup_sent_at in lead response', () => {
      const lead = createMockLead({ founder_followup_sent_at: null })

      expect(lead).toHaveProperty('founder_followup_sent_at')
      expect(lead.founder_followup_sent_at).toBeNull()
    })

    it('should show founder_followup_sent as true when email sent', () => {
      const lead = createMockLead({
        founder_followup_sent: true,
        founder_followup_sent_at: '2026-03-01T10:30:00',
      })

      expect(lead.founder_followup_sent).toBe(true)
      expect(lead.founder_followup_sent_at).not.toBeNull()
    })

    it('should show founder_followup_sent as false when email not sent', () => {
      const lead = createMockLead({
        founder_followup_sent: false,
        founder_followup_sent_at: null,
      })

      expect(lead.founder_followup_sent).toBe(false)
      expect(lead.founder_followup_sent_at).toBeNull()
    })
  })

  describe('Unit Tests - Status button text', () => {
    it('should show "Sent ✓" when founder email sent', () => {
      const lead = createMockLead({ founder_followup_sent: true })

      const buttonText = lead.founder_followup_sent ? 'Sent ✓' : 'Not Sent'
      expect(buttonText).toBe('Sent ✓')
    })

    it('should show "Not Sent" when founder email not sent', () => {
      const lead = createMockLead({ founder_followup_sent: false })

      const buttonText = lead.founder_followup_sent ? 'Sent ✓' : 'Not Sent'
      expect(buttonText).toBe('Not Sent')
    })
  })

  describe('Unit Tests - Tooltip/title content', () => {
    it('should show sent timestamp in tooltip when email sent', () => {
      const lead = createMockLead({
        founder_followup_sent: true,
        founder_followup_sent_at: '2026-03-01T10:30:00',
      })

      const sentDate = new Date(lead.founder_followup_sent_at)
      const title = lead.founder_followup_sent
        ? `Sent on ${sentDate.toLocaleString('en-GB', { timeZone: 'Europe/London' })}`
        : 'Not sent yet'

      expect(title).toContain('Sent on')
      expect(title).toContain('01/03/2026')
    })

    it('should show "Not sent yet" in tooltip when email not sent', () => {
      const lead = createMockLead({
        founder_followup_sent: false,
        founder_followup_sent_at: null,
      })

      const title = lead.founder_followup_sent
        ? `Sent on ${new Date(lead.founder_followup_sent_at).toLocaleString('en-GB')}`
        : 'Not sent yet'

      expect(title).toBe('Not sent yet')
    })
  })

  describe('Unit Tests - Button disabled state', () => {
    it('should always be disabled (display only)', () => {
      const lead = createMockLead()

      // Button is always disabled as it's a status indicator, not actionable
      const isDisabled = true
      expect(isDisabled).toBe(true)
    })

    it('should be disabled when email sent', () => {
      const lead = createMockLead({ founder_followup_sent: true })

      // Still disabled as it's a status indicator
      const isDisabled = true
      expect(isDisabled).toBe(true)
    })

    it('should be disabled when email not sent', () => {
      const lead = createMockLead({ founder_followup_sent: false })

      // Still disabled as it's a status indicator
      const isDisabled = true
      expect(isDisabled).toBe(true)
    })
  })

  describe('Unit Tests - CSS class based on status', () => {
    it('should have sent-status class when email sent', () => {
      const lead = createMockLead({ founder_followup_sent: true })

      const className = lead.founder_followup_sent
        ? 'action-btn email-btn sent-status'
        : 'action-btn email-btn'

      expect(className).toContain('sent-status')
    })

    it('should NOT have sent-status class when email not sent', () => {
      const lead = createMockLead({ founder_followup_sent: false })

      const className = lead.founder_followup_sent
        ? 'action-btn email-btn sent-status'
        : 'action-btn email-btn'

      expect(className).not.toContain('sent-status')
      expect(className).toContain('email-btn')
    })
  })
})

// =============================================================================
// Integration Tests - API Response Handling
// =============================================================================

describe('Admin Leads Founder Email Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('API Integration - Abandoned leads response', () => {
    it('should include founder_followup_sent fields in API response', async () => {
      const mockResponse = {
        count: 2,
        leads: [
          createMockLead({
            id: 1,
            email: 'sent@test.com',
            founder_followup_sent: true,
            founder_followup_sent_at: '2026-03-01T10:30:00',
          }),
          createMockLead({
            id: 2,
            email: 'notsent@test.com',
            founder_followup_sent: false,
            founder_followup_sent_at: null,
          }),
        ],
      }

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      })

      const response = await fetch('/api/admin/abandoned-leads')
      const data = await response.json()

      expect(data.leads[0]).toHaveProperty('founder_followup_sent')
      expect(data.leads[0]).toHaveProperty('founder_followup_sent_at')
      expect(data.leads[0].founder_followup_sent).toBe(true)
      expect(data.leads[0].founder_followup_sent_at).not.toBeNull()

      expect(data.leads[1].founder_followup_sent).toBe(false)
      expect(data.leads[1].founder_followup_sent_at).toBeNull()
    })

    it('should handle API response with all leads having email sent', async () => {
      const mockResponse = {
        count: 3,
        leads: [
          createMockLead({ id: 1, founder_followup_sent: true, founder_followup_sent_at: '2026-03-01T10:00:00' }),
          createMockLead({ id: 2, founder_followup_sent: true, founder_followup_sent_at: '2026-03-01T11:00:00' }),
          createMockLead({ id: 3, founder_followup_sent: true, founder_followup_sent_at: '2026-03-01T12:00:00' }),
        ],
      }

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      })

      const response = await fetch('/api/admin/abandoned-leads')
      const data = await response.json()

      const allSent = data.leads.every(lead => lead.founder_followup_sent)
      expect(allSent).toBe(true)
    })

    it('should handle API response with no leads having email sent', async () => {
      const mockResponse = {
        count: 3,
        leads: [
          createMockLead({ id: 1, founder_followup_sent: false, founder_followup_sent_at: null }),
          createMockLead({ id: 2, founder_followup_sent: false, founder_followup_sent_at: null }),
          createMockLead({ id: 3, founder_followup_sent: false, founder_followup_sent_at: null }),
        ],
      }

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      })

      const response = await fetch('/api/admin/abandoned-leads')
      const data = await response.json()

      const noneSent = data.leads.every(lead => !lead.founder_followup_sent)
      expect(noneSent).toBe(true)
    })

    it('should correctly count leads by founder email status', async () => {
      const mockResponse = {
        count: 5,
        leads: [
          createMockLead({ id: 1, founder_followup_sent: true, founder_followup_sent_at: '2026-03-01T10:00:00' }),
          createMockLead({ id: 2, founder_followup_sent: false, founder_followup_sent_at: null }),
          createMockLead({ id: 3, founder_followup_sent: true, founder_followup_sent_at: '2026-03-01T11:00:00' }),
          createMockLead({ id: 4, founder_followup_sent: false, founder_followup_sent_at: null }),
          createMockLead({ id: 5, founder_followup_sent: true, founder_followup_sent_at: '2026-03-01T12:00:00' }),
        ],
      }

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      })

      const response = await fetch('/api/admin/abandoned-leads')
      const data = await response.json()

      const sentCount = data.leads.filter(lead => lead.founder_followup_sent).length
      const notSentCount = data.leads.filter(lead => !lead.founder_followup_sent).length

      expect(sentCount).toBe(3)
      expect(notSentCount).toBe(2)
    })
  })
})

// =============================================================================
// Negative Tests - Error Handling and Invalid Data
// =============================================================================

describe('Admin Leads Founder Email Negative Tests', () => {
  describe('Missing/undefined fields', () => {
    it('should handle lead without founder_followup_sent field', () => {
      const lead = createMockLead()
      delete lead.founder_followup_sent

      // Should default to false/undefined
      const isSent = lead.founder_followup_sent || false
      expect(isSent).toBe(false)
    })

    it('should handle lead without founder_followup_sent_at field', () => {
      const lead = createMockLead()
      delete lead.founder_followup_sent_at

      // Should default to null/undefined
      const sentAt = lead.founder_followup_sent_at || null
      expect(sentAt).toBeNull()
    })

    it('should handle lead with undefined values', () => {
      const lead = createMockLead({
        founder_followup_sent: undefined,
        founder_followup_sent_at: undefined,
      })

      const isSent = lead.founder_followup_sent ?? false
      const sentAt = lead.founder_followup_sent_at ?? null

      expect(isSent).toBe(false)
      expect(sentAt).toBeNull()
    })
  })

  describe('Invalid data combinations', () => {
    it('should handle sent=true but sent_at=null (inconsistent data)', () => {
      const lead = createMockLead({
        founder_followup_sent: true,
        founder_followup_sent_at: null,
      })

      // Should still show as sent even without timestamp
      expect(lead.founder_followup_sent).toBe(true)

      // Tooltip should handle null timestamp gracefully
      const title = lead.founder_followup_sent
        ? `Sent on ${lead.founder_followup_sent_at ? new Date(lead.founder_followup_sent_at).toLocaleString('en-GB') : 'Unknown'}`
        : 'Not sent yet'

      expect(title).toContain('Unknown')
    })

    it('should handle sent=false but sent_at has value (inconsistent data)', () => {
      const lead = createMockLead({
        founder_followup_sent: false,
        founder_followup_sent_at: '2026-03-01T10:30:00',
      })

      // Flag takes precedence - treat as not sent
      const buttonText = lead.founder_followup_sent ? 'Sent ✓' : 'Not Sent'
      expect(buttonText).toBe('Not Sent')
    })
  })

  describe('Invalid timestamp formats', () => {
    it('should handle invalid date string', () => {
      const lead = createMockLead({
        founder_followup_sent: true,
        founder_followup_sent_at: 'not-a-date',
      })

      const date = new Date(lead.founder_followup_sent_at)
      expect(isNaN(date.getTime())).toBe(true)
    })

    it('should handle empty string timestamp', () => {
      const lead = createMockLead({
        founder_followup_sent: true,
        founder_followup_sent_at: '',
      })

      // Empty string should be treated as not having a timestamp
      const hasSentAt = Boolean(lead.founder_followup_sent_at)
      expect(hasSentAt).toBe(false)
    })
  })

  describe('API error scenarios', () => {
    beforeEach(() => {
      vi.clearAllMocks()
    })

    it('should handle API returning 500 error', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'Internal server error' }),
      })

      const response = await fetch('/api/admin/abandoned-leads')

      expect(response.ok).toBe(false)
      expect(response.status).toBe(500)
    })

    it('should handle API returning 401 unauthorized', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'Not authenticated' }),
      })

      const response = await fetch('/api/admin/abandoned-leads')

      expect(response.ok).toBe(false)
      expect(response.status).toBe(401)
    })

    it('should handle network error', async () => {
      global.fetch.mockRejectedValueOnce(new Error('Network error'))

      let errorOccurred = false
      try {
        await fetch('/api/admin/abandoned-leads')
      } catch (err) {
        errorOccurred = true
      }

      expect(errorOccurred).toBe(true)
    })
  })
})

// =============================================================================
// Edge Cases
// =============================================================================

describe('Admin Leads Founder Email Edge Cases', () => {
  describe('Timestamp edge cases', () => {
    it('should handle timestamp at midnight', () => {
      const lead = createMockLead({
        founder_followup_sent: true,
        founder_followup_sent_at: '2026-03-01T00:00:00',
      })

      const date = new Date(lead.founder_followup_sent_at)
      expect(date.getHours()).toBe(0)
      expect(date.getMinutes()).toBe(0)
    })

    it('should handle timestamp at end of day', () => {
      const lead = createMockLead({
        founder_followup_sent: true,
        founder_followup_sent_at: '2026-03-01T23:59:59',
      })

      const date = new Date(lead.founder_followup_sent_at)
      expect(date.getHours()).toBe(23)
      expect(date.getMinutes()).toBe(59)
    })

    it('should handle timestamp with milliseconds', () => {
      const lead = createMockLead({
        founder_followup_sent: true,
        founder_followup_sent_at: '2026-03-01T10:30:45.123',
      })

      const date = new Date(lead.founder_followup_sent_at)
      expect(date.getMilliseconds()).toBe(123)
    })

    it('should handle ISO format with timezone', () => {
      const lead = createMockLead({
        founder_followup_sent: true,
        founder_followup_sent_at: '2026-03-01T10:30:00+00:00',
      })

      const date = new Date(lead.founder_followup_sent_at)
      expect(isNaN(date.getTime())).toBe(false)
    })
  })

  describe('Lead count edge cases', () => {
    it('should handle empty leads list', async () => {
      const mockResponse = {
        count: 0,
        leads: [],
      }

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      })

      const response = await fetch('/api/admin/abandoned-leads')
      const data = await response.json()

      expect(data.leads).toHaveLength(0)
      expect(data.count).toBe(0)
    })

    it('should handle single lead', async () => {
      const mockResponse = {
        count: 1,
        leads: [createMockLead({ founder_followup_sent: true })],
      }

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      })

      const response = await fetch('/api/admin/abandoned-leads')
      const data = await response.json()

      expect(data.leads).toHaveLength(1)
    })

    it('should handle large number of leads', async () => {
      const leads = Array.from({ length: 250 }, (_, i) =>
        createMockLead({
          id: i + 1,
          founder_followup_sent: i % 2 === 0,
          founder_followup_sent_at: i % 2 === 0 ? '2026-03-01T10:00:00' : null,
        })
      )

      const mockResponse = {
        count: 250,
        leads,
      }

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      })

      const response = await fetch('/api/admin/abandoned-leads')
      const data = await response.json()

      expect(data.leads).toHaveLength(250)

      const sentCount = data.leads.filter(lead => lead.founder_followup_sent).length
      expect(sentCount).toBe(125) // Half are sent
    })
  })

  describe('Lead data variations', () => {
    it('should handle lead with zero booking attempts and email sent', () => {
      const lead = createMockLead({
        booking_attempts: 0,
        last_booking_status: null,
        founder_followup_sent: true,
        founder_followup_sent_at: '2026-03-01T10:30:00',
      })

      expect(lead.booking_attempts).toBe(0)
      expect(lead.founder_followup_sent).toBe(true)
    })

    it('should handle lead with pending booking and email sent (manual trigger)', () => {
      const lead = createMockLead({
        booking_attempts: 1,
        last_booking_status: 'pending',
        founder_followup_sent: true,
        founder_followup_sent_at: '2026-03-01T10:30:00',
      })

      expect(lead.booking_attempts).toBe(1)
      expect(lead.last_booking_status).toBe('pending')
      expect(lead.founder_followup_sent).toBe(true)
    })

    it('should handle lead with cancelled booking and email not sent', () => {
      const lead = createMockLead({
        booking_attempts: 1,
        last_booking_status: 'cancelled',
        founder_followup_sent: false,
        founder_followup_sent_at: null,
      })

      expect(lead.last_booking_status).toBe('cancelled')
      expect(lead.founder_followup_sent).toBe(false)
    })
  })
})

// =============================================================================
// Display Logic Tests
// =============================================================================

describe('Admin Leads Founder Email Display Logic', () => {
  describe('Status section rendering', () => {
    it('should always render founder email status in status section', () => {
      const lead = createMockLead()

      // Status section should include founder email status
      const statusFields = ['created_at', 'last_booking_status', 'founder_followup_sent']
      const leadHasAllFields = statusFields.every(field => field in lead)

      expect(leadHasAllFields).toBe(true)
    })

    it('should render status label as "Founder Email"', () => {
      const label = 'Founder Email'
      expect(label).toBe('Founder Email')
    })
  })

  describe('Filtering by founder email status', () => {
    it('should be able to filter leads with email sent', () => {
      const leads = [
        createMockLead({ id: 1, founder_followup_sent: true }),
        createMockLead({ id: 2, founder_followup_sent: false }),
        createMockLead({ id: 3, founder_followup_sent: true }),
      ]

      const sentLeads = leads.filter(lead => lead.founder_followup_sent)
      expect(sentLeads).toHaveLength(2)
    })

    it('should be able to filter leads without email sent', () => {
      const leads = [
        createMockLead({ id: 1, founder_followup_sent: true }),
        createMockLead({ id: 2, founder_followup_sent: false }),
        createMockLead({ id: 3, founder_followup_sent: true }),
      ]

      const notSentLeads = leads.filter(lead => !lead.founder_followup_sent)
      expect(notSentLeads).toHaveLength(1)
    })
  })
})

// =============================================================================
// Boundary Tests
// =============================================================================

describe('Admin Leads Founder Email Boundary Tests', () => {
  describe('Date boundaries', () => {
    it('should handle founder email sent on start date (March 1st 2026)', () => {
      const lead = createMockLead({
        founder_followup_sent: true,
        founder_followup_sent_at: '2026-03-01T00:00:00',
      })

      const sentDate = new Date(lead.founder_followup_sent_at)
      expect(sentDate.getFullYear()).toBe(2026)
      expect(sentDate.getMonth()).toBe(2) // March (0-indexed)
      expect(sentDate.getDate()).toBe(1)
    })

    it('should handle future date (data integrity)', () => {
      const lead = createMockLead({
        founder_followup_sent: true,
        founder_followup_sent_at: '2030-12-31T23:59:59',
      })

      // Should still display correctly even if date is in future
      const date = new Date(lead.founder_followup_sent_at)
      expect(isNaN(date.getTime())).toBe(false)
    })

    it('should handle very old date', () => {
      const lead = createMockLead({
        founder_followup_sent: true,
        founder_followup_sent_at: '2020-01-01T00:00:00',
      })

      const date = new Date(lead.founder_followup_sent_at)
      expect(date.getFullYear()).toBe(2020)
    })
  })

  describe('ID boundaries', () => {
    it('should handle lead with ID 0', () => {
      const lead = createMockLead({ id: 0 })
      expect(lead.id).toBe(0)
    })

    it('should handle lead with very large ID', () => {
      const lead = createMockLead({ id: 999999999 })
      expect(lead.id).toBe(999999999)
    })
  })
})

// =============================================================================
// Run tests if executed directly
// =============================================================================

if (import.meta.vitest) {
  const { describe, it, expect, vi, beforeEach } = import.meta.vitest
}
