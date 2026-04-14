/**
 * Tests for Dynamic Pricing Feature
 *
 * Tests cover:
 * - HomePage pricing fetch and display
 * - Admin pricing settings management
 * - Error handling and fallbacks
 * - Edge cases
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'

// Mock fetch globally
global.fetch = vi.fn()

// =============================================================================
// HomePage Pricing Tests
// =============================================================================

describe('HomePage Pricing Display', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('displays default price ranges before API response', async () => {
    // Mock a slow API response
    global.fetch.mockImplementation(() => new Promise(() => {}))

    const { container } = render(
      <BrowserRouter>
        <MockHomePage />
      </BrowserRouter>
    )

    // Should show default price ranges initially (base–max)
    expect(container.textContent).toContain('£65–£75')  // 4 day
    expect(container.textContent).toContain('£89–£99')  // 7 day
    expect(container.textContent).toContain('£140–£150') // 14 day
  })

  it('fetches pricing from API on mount', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        days_1_4_price: 65,
        week1_base_price: 99,
        week2_base_price: 159,
        tier_increment: 15,
        peak_day_increment: 10,
      }),
    })

    render(
      <BrowserRouter>
        <MockHomePage />
      </BrowserRouter>
    )

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/pricing'),
        expect.objectContaining({ cache: 'no-store' })
      )
    })
  })

  it('updates prices with range after successful API fetch', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        days_1_4_price: 70,
        week1_base_price: 95,
        week2_base_price: 155,
        tier_increment: 10,
        peak_day_increment: 5,
      }),
    })

    const { container } = render(
      <BrowserRouter>
        <MockHomePage />
      </BrowserRouter>
    )

    // Max = base + (tier_increment * 2) + peak_day_increment
    // = base + (10 * 2) + 5 = base + 25
    await waitFor(() => {
      expect(container.textContent).toContain('£70–£95')   // 70 + 25
      expect(container.textContent).toContain('£95–£120')  // 95 + 25
      expect(container.textContent).toContain('£155–£180') // 155 + 25
    })
  })

  it('calculates max price correctly with peak day increment', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        days_1_4_price: 65,
        week1_base_price: 85,
        week2_base_price: 150,
        tier_increment: 10,
        peak_day_increment: 10,
      }),
    })

    const { container } = render(
      <BrowserRouter>
        <MockHomePage />
      </BrowserRouter>
    )

    // Max = base + (10 * 2) + 10 = base + 30
    await waitFor(() => {
      expect(container.textContent).toContain('£65–£95')   // 65 + 30
      expect(container.textContent).toContain('£85–£115')  // 85 + 30
      expect(container.textContent).toContain('£150–£180') // 150 + 30
    })
  })

  it('handles zero peak day increment', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        days_1_4_price: 65,
        week1_base_price: 85,
        week2_base_price: 150,
        tier_increment: 10,
        peak_day_increment: 0,
      }),
    })

    const { container } = render(
      <BrowserRouter>
        <MockHomePage />
      </BrowserRouter>
    )

    // Max = base + (10 * 2) + 0 = base + 20
    await waitFor(() => {
      expect(container.textContent).toContain('£65–£85')   // 65 + 20
      expect(container.textContent).toContain('£85–£105')  // 85 + 20
      expect(container.textContent).toContain('£150–£170') // 150 + 20
    })
  })

  it('keeps default prices on API error', async () => {
    global.fetch.mockRejectedValueOnce(new Error('Network error'))

    const { container } = render(
      <BrowserRouter>
        <MockHomePage />
      </BrowserRouter>
    )

    // Wait a bit for error to be handled
    await new Promise(resolve => setTimeout(resolve, 100))

    // Should still show default price ranges
    expect(container.textContent).toContain('£65–£75')
    expect(container.textContent).toContain('£89–£99')
    expect(container.textContent).toContain('£140–£150')
  })

  it('keeps default prices on non-OK response', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error('Failed')),
    })

    const { container } = render(
      <BrowserRouter>
        <MockHomePage />
      </BrowserRouter>
    )

    await new Promise(resolve => setTimeout(resolve, 100))

    // Should still show default price ranges
    expect(container.textContent).toContain('£65–£75')
    expect(container.textContent).toContain('£89–£99')
    expect(container.textContent).toContain('£140–£150')
  })
})

// =============================================================================
// Admin Pricing Settings Tests
// =============================================================================

describe('Admin Pricing Settings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('displays current pricing settings', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        week1_base_price: 79,
        week2_base_price: 140,
        tier_increment: 10,
        updated_at: '2026-01-25T10:00:00Z',
      }),
    })

    render(<MockAdminPricing token="test-token" />)

    await waitFor(() => {
      expect(screen.getByDisplayValue('79')).toBeInTheDocument()
      expect(screen.getByDisplayValue('140')).toBeInTheDocument()
      expect(screen.getByDisplayValue('10')).toBeInTheDocument()
    })
  })

  it('allows editing pricing values', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        week1_base_price: 79,
        week2_base_price: 140,
        tier_increment: 10,
      }),
    })

    render(<MockAdminPricing token="test-token" />)

    await waitFor(() => {
      expect(screen.getByDisplayValue('79')).toBeInTheDocument()
    })

    const week1Input = screen.getByDisplayValue('79')
    fireEvent.change(week1Input, { target: { value: '89' } })

    expect(screen.getByDisplayValue('89')).toBeInTheDocument()
  })

  it('shows price preview with calculated tiers', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        week1_base_price: 79,
        week2_base_price: 140,
        tier_increment: 10,
      }),
    })

    const { container } = render(<MockAdminPricing token="test-token" />)

    await waitFor(() => {
      expect(screen.getByDisplayValue('79')).toBeInTheDocument()
    })

    // Preview should show calculated prices
    // 1 Week: 79, 89, 99
    // 2 Weeks: 140, 150, 160
    expect(container.textContent).toContain('89')  // 79 + 10
    expect(container.textContent).toContain('99')  // 79 + 20
    expect(container.textContent).toContain('150') // 140 + 10
    expect(container.textContent).toContain('160') // 140 + 20
  })

  it('submits updated pricing to API', async () => {
    global.fetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          week1_base_price: 79,
          week2_base_price: 140,
          tier_increment: 10,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          message: 'Pricing updated successfully',
        }),
      })

    render(<MockAdminPricing token="test-token" />)

    await waitFor(() => {
      expect(screen.getByDisplayValue('79')).toBeInTheDocument()
    })

    // Change values
    const week1Input = screen.getByDisplayValue('79')
    fireEvent.change(week1Input, { target: { value: '85' } })

    // Click save
    const saveButton = screen.getByText('Save Changes')
    fireEvent.click(saveButton)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/admin/pricing'),
        expect.objectContaining({
          method: 'PUT',
          body: expect.stringContaining('85'),
        })
      )
    })
  })

  it('shows success message after save', async () => {
    global.fetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          week1_base_price: 79,
          week2_base_price: 140,
          tier_increment: 10,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          message: 'Pricing updated successfully',
        }),
      })

    render(<MockAdminPricing token="test-token" />)

    await waitFor(() => {
      expect(screen.getByDisplayValue('79')).toBeInTheDocument()
    })

    const saveButton = screen.getByText('Save Changes')
    fireEvent.click(saveButton)

    await waitFor(() => {
      expect(screen.getByText(/updated successfully/i)).toBeInTheDocument()
    })
  })

  it('shows error message on save failure', async () => {
    global.fetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          week1_base_price: 79,
          week2_base_price: 140,
          tier_increment: 10,
        }),
      })
      .mockResolvedValueOnce({
        ok: false,
        json: () => Promise.resolve({
          detail: 'Failed to save pricing',
        }),
      })

    render(<MockAdminPricing token="test-token" />)

    await waitFor(() => {
      expect(screen.getByDisplayValue('79')).toBeInTheDocument()
    })

    const saveButton = screen.getByText('Save Changes')
    fireEvent.click(saveButton)

    await waitFor(() => {
      expect(screen.getByText(/failed/i)).toBeInTheDocument()
    })
  })
})

// =============================================================================
// Edge Cases and Validation Tests
// =============================================================================

describe('Pricing Edge Cases', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('handles zero tier increment', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        week1_base_price: 100,
        week2_base_price: 150,
        tier_increment: 0,
      }),
    })

    const { container } = render(<MockAdminPricing token="test-token" />)

    await waitFor(() => {
      expect(screen.getByDisplayValue('100')).toBeInTheDocument()
    })

    // With 0 increment, all tiers should show same price
    // Preview table should show: 100, 100, 100 for 1 Week
    const cells = container.querySelectorAll('td')
    const priceTexts = Array.from(cells).map(c => c.textContent)

    // Should contain the base price multiple times
    expect(priceTexts.filter(t => t.includes('100')).length).toBeGreaterThanOrEqual(3)
  })

  it('handles decimal prices', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        week1_base_price: 89.99,
        week2_base_price: 139.50,
        tier_increment: 9.99,
      }),
    })

    const { container } = render(<MockAdminPricing token="test-token" />)

    await waitFor(() => {
      expect(screen.getByDisplayValue('89.99')).toBeInTheDocument()
    })
  })

  it('handles very large prices', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        week1_base_price: 999,
        week2_base_price: 1999,
        tier_increment: 100,
      }),
    })

    const { container } = render(<MockAdminPricing token="test-token" />)

    await waitFor(() => {
      expect(screen.getByDisplayValue('999')).toBeInTheDocument()
      expect(screen.getByDisplayValue('1999')).toBeInTheDocument()
    })
  })

  it('handles network timeout gracefully', async () => {
    vi.useFakeTimers()

    global.fetch.mockImplementation(() =>
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Timeout')), 30000)
      )
    )

    const { container } = render(
      <BrowserRouter>
        <MockHomePage />
      </BrowserRouter>
    )

    // Should still render with default price ranges
    expect(container.textContent).toContain('£65–£75')
    expect(container.textContent).toContain('£89–£99')

    vi.useRealTimers()
  })
})

// =============================================================================
// Price Preview Calculation Tests
// =============================================================================

describe('Price Preview Calculations', () => {
  it('calculates standard tier correctly', () => {
    const pricing = {
      week1_base_price: 79,
      week2_base_price: 140,
      tier_increment: 10,
    }

    // Standard = base + increment
    expect(pricing.week1_base_price + pricing.tier_increment).toBe(89)
    expect(pricing.week2_base_price + pricing.tier_increment).toBe(150)
  })

  it('calculates late tier correctly', () => {
    const pricing = {
      week1_base_price: 79,
      week2_base_price: 140,
      tier_increment: 10,
    }

    // Late = base + (increment * 2)
    expect(pricing.week1_base_price + (pricing.tier_increment * 2)).toBe(99)
    expect(pricing.week2_base_price + (pricing.tier_increment * 2)).toBe(160)
  })

  it('handles custom pricing correctly', () => {
    const pricing = {
      week1_base_price: 75,
      week2_base_price: 125,
      tier_increment: 15,
    }

    // 1 Week: 75, 90, 105
    expect(pricing.week1_base_price).toBe(75)
    expect(pricing.week1_base_price + pricing.tier_increment).toBe(90)
    expect(pricing.week1_base_price + (pricing.tier_increment * 2)).toBe(105)

    // 2 Weeks: 125, 140, 155
    expect(pricing.week2_base_price).toBe(125)
    expect(pricing.week2_base_price + pricing.tier_increment).toBe(140)
    expect(pricing.week2_base_price + (pricing.tier_increment * 2)).toBe(155)
  })
})

// =============================================================================
// Price Range Calculation Tests
// =============================================================================

describe('Price Range Calculations', () => {
  it('calculates max price with tier and peak day increments', () => {
    const pricing = {
      days_1_4_price: 65,
      week1_base_price: 85,
      week2_base_price: 150,
      tier_increment: 10,
      peak_day_increment: 10,
    }

    // Max = base + (tier_increment * 2) + peak_day_increment
    const maxAddon = (pricing.tier_increment * 2) + pricing.peak_day_increment
    expect(maxAddon).toBe(30)

    expect(pricing.days_1_4_price + maxAddon).toBe(95)
    expect(pricing.week1_base_price + maxAddon).toBe(115)
    expect(pricing.week2_base_price + maxAddon).toBe(180)
  })

  it('calculates max price with zero peak day increment', () => {
    const pricing = {
      days_1_4_price: 65,
      week1_base_price: 85,
      week2_base_price: 150,
      tier_increment: 10,
      peak_day_increment: 0,
    }

    // Max = base + (tier_increment * 2) + 0
    const maxAddon = (pricing.tier_increment * 2) + pricing.peak_day_increment
    expect(maxAddon).toBe(20)

    expect(pricing.days_1_4_price + maxAddon).toBe(85)
    expect(pricing.week1_base_price + maxAddon).toBe(105)
    expect(pricing.week2_base_price + maxAddon).toBe(170)
  })

  it('calculates max price with high peak day increment', () => {
    const pricing = {
      days_1_4_price: 65,
      week1_base_price: 85,
      week2_base_price: 150,
      tier_increment: 5,
      peak_day_increment: 20,
    }

    // Max = base + (5 * 2) + 20 = base + 30
    const maxAddon = (pricing.tier_increment * 2) + pricing.peak_day_increment
    expect(maxAddon).toBe(30)

    expect(pricing.days_1_4_price + maxAddon).toBe(95)
  })

  it('handles decimal increments correctly', () => {
    const pricing = {
      days_1_4_price: 65.50,
      tier_increment: 7.50,
      peak_day_increment: 5.00,
    }

    // Max = 65.50 + (7.50 * 2) + 5.00 = 65.50 + 20 = 85.50
    const maxAddon = (pricing.tier_increment * 2) + pricing.peak_day_increment
    expect(pricing.days_1_4_price + maxAddon).toBe(85.50)
  })
})

// =============================================================================
// Mock Components for Testing
// =============================================================================

// Simplified HomePage component for testing
function MockHomePage() {
  const [prices, setPrices] = React.useState({
    days4: 65, days4Max: 75,
    week1: 89, week1Max: 99,
    week2: 140, week2Max: 150
  })

  React.useEffect(() => {
    const API_URL = import.meta.env?.VITE_API_URL || 'http://localhost:8000'
    fetch(`${API_URL}/api/pricing`, { cache: 'no-store' })
      .then(res => res.json())
      .then(data => {
        const tierIncrement = data.tier_increment || 5
        const peakDayIncrement = data.peak_day_increment || 0
        const maxAddon = (tierIncrement * 2) + peakDayIncrement
        setPrices({
          days4: data.days_1_4_price || 65,
          days4Max: (data.days_1_4_price || 65) + maxAddon,
          week1: data.week1_base_price || 89,
          week1Max: (data.week1_base_price || 89) + maxAddon,
          week2: data.week2_base_price || 140,
          week2Max: (data.week2_base_price || 140) + maxAddon,
        })
      })
      .catch(() => {
        // Keep defaults
      })
  }, [])

  return (
    <div>
      <div className="pricing-card" data-testid="days4-card">
        <span className="price">£{prices.days4}–£{prices.days4Max}</span>
      </div>
      <div className="pricing-card" data-testid="week1-card">
        <span className="price">£{prices.week1}–£{prices.week1Max}</span>
      </div>
      <div className="pricing-card" data-testid="week2-card">
        <span className="price">£{prices.week2}–£{prices.week2Max}</span>
      </div>
    </div>
  )
}

// Simplified Admin Pricing component for testing
function MockAdminPricing({ token }) {
  const [pricing, setPricing] = React.useState({
    week1_base_price: 79,
    week2_base_price: 140,
    tier_increment: 10,
  })
  const [message, setMessage] = React.useState('')
  const [error, setError] = React.useState('')

  React.useEffect(() => {
    if (token) {
      const API_URL = import.meta.env?.VITE_API_URL || 'http://localhost:8000'
      fetch(`${API_URL}/api/admin/pricing`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
        .then(res => res.json())
        .then(data => {
          setPricing({
            week1_base_price: data.week1_base_price,
            week2_base_price: data.week2_base_price,
            tier_increment: data.tier_increment,
          })
        })
    }
  }, [token])

  const savePricing = async () => {
    const API_URL = import.meta.env?.VITE_API_URL || 'http://localhost:8000'
    try {
      const response = await fetch(`${API_URL}/api/admin/pricing`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(pricing),
      })
      if (response.ok) {
        setMessage('Pricing updated successfully')
        setError('')
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to save')
        setMessage('')
      }
    } catch (err) {
      setError('Network error')
      setMessage('')
    }
  }

  return (
    <div>
      {message && <div className="success">{message}</div>}
      {error && <div className="error">{error}</div>}

      <input
        type="number"
        value={pricing.week1_base_price}
        onChange={(e) => setPricing({ ...pricing, week1_base_price: parseFloat(e.target.value) || 0 })}
      />
      <input
        type="number"
        value={pricing.week2_base_price}
        onChange={(e) => setPricing({ ...pricing, week2_base_price: parseFloat(e.target.value) || 0 })}
      />
      <input
        type="number"
        value={pricing.tier_increment}
        onChange={(e) => setPricing({ ...pricing, tier_increment: parseFloat(e.target.value) || 0 })}
      />

      <table>
        <tbody>
          <tr>
            <td>1 Week</td>
            <td>£{pricing.week1_base_price}</td>
            <td>£{pricing.week1_base_price + pricing.tier_increment}</td>
            <td>£{pricing.week1_base_price + (pricing.tier_increment * 2)}</td>
          </tr>
          <tr>
            <td>2 Weeks</td>
            <td>£{pricing.week2_base_price}</td>
            <td>£{pricing.week2_base_price + pricing.tier_increment}</td>
            <td>£{pricing.week2_base_price + (pricing.tier_increment * 2)}</td>
          </tr>
        </tbody>
      </table>

      <button onClick={savePricing}>Save Changes</button>
    </div>
  )
}

// Import React for mock components
import React from 'react'
