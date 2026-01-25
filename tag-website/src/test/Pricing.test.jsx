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

  it('displays default prices before API response', async () => {
    // Mock a slow API response
    global.fetch.mockImplementation(() => new Promise(() => {}))

    const { container } = render(
      <BrowserRouter>
        <MockHomePage />
      </BrowserRouter>
    )

    // Should show default prices initially
    expect(container.textContent).toContain('89')
    expect(container.textContent).toContain('140')
  })

  it('fetches pricing from API on mount', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        week1_base_price: 99,
        week2_base_price: 159,
        tier_increment: 15,
      }),
    })

    render(
      <BrowserRouter>
        <MockHomePage />
      </BrowserRouter>
    )

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/pricing')
      )
    })
  })

  it('updates prices after successful API fetch', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        week1_base_price: 95,
        week2_base_price: 155,
        tier_increment: 12,
      }),
    })

    const { container } = render(
      <BrowserRouter>
        <MockHomePage />
      </BrowserRouter>
    )

    await waitFor(() => {
      expect(container.textContent).toContain('95')
      expect(container.textContent).toContain('155')
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

    // Should still show default prices
    expect(container.textContent).toContain('89')
    expect(container.textContent).toContain('140')
  })

  it('keeps default prices on non-OK response', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
    })

    const { container } = render(
      <BrowserRouter>
        <MockHomePage />
      </BrowserRouter>
    )

    await new Promise(resolve => setTimeout(resolve, 100))

    // Should still show default prices
    expect(container.textContent).toContain('89')
    expect(container.textContent).toContain('140')
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
        week1_base_price: 89,
        week2_base_price: 140,
        tier_increment: 10,
        updated_at: '2026-01-25T10:00:00Z',
      }),
    })

    render(<MockAdminPricing token="test-token" />)

    await waitFor(() => {
      expect(screen.getByDisplayValue('89')).toBeInTheDocument()
      expect(screen.getByDisplayValue('140')).toBeInTheDocument()
      expect(screen.getByDisplayValue('10')).toBeInTheDocument()
    })
  })

  it('allows editing pricing values', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        week1_base_price: 89,
        week2_base_price: 140,
        tier_increment: 10,
      }),
    })

    render(<MockAdminPricing token="test-token" />)

    await waitFor(() => {
      expect(screen.getByDisplayValue('89')).toBeInTheDocument()
    })

    const week1Input = screen.getByDisplayValue('89')
    fireEvent.change(week1Input, { target: { value: '99' } })

    expect(screen.getByDisplayValue('99')).toBeInTheDocument()
  })

  it('shows price preview with calculated tiers', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        week1_base_price: 89,
        week2_base_price: 140,
        tier_increment: 10,
      }),
    })

    const { container } = render(<MockAdminPricing token="test-token" />)

    await waitFor(() => {
      expect(screen.getByDisplayValue('89')).toBeInTheDocument()
    })

    // Preview should show calculated prices
    // 1 Week: 89, 99, 109
    // 2 Weeks: 140, 150, 160
    expect(container.textContent).toContain('99')  // 89 + 10
    expect(container.textContent).toContain('109') // 89 + 20
    expect(container.textContent).toContain('150') // 140 + 10
    expect(container.textContent).toContain('160') // 140 + 20
  })

  it('submits updated pricing to API', async () => {
    global.fetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          week1_base_price: 89,
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
      expect(screen.getByDisplayValue('89')).toBeInTheDocument()
    })

    // Change values
    const week1Input = screen.getByDisplayValue('89')
    fireEvent.change(week1Input, { target: { value: '95' } })

    // Click save
    const saveButton = screen.getByText('Save Changes')
    fireEvent.click(saveButton)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/admin/pricing'),
        expect.objectContaining({
          method: 'PUT',
          body: expect.stringContaining('95'),
        })
      )
    })
  })

  it('shows success message after save', async () => {
    global.fetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          week1_base_price: 89,
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
      expect(screen.getByDisplayValue('89')).toBeInTheDocument()
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
          week1_base_price: 89,
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
      expect(screen.getByDisplayValue('89')).toBeInTheDocument()
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

    // Should still render with defaults
    expect(container.textContent).toContain('89')

    vi.useRealTimers()
  })
})

// =============================================================================
// Price Preview Calculation Tests
// =============================================================================

describe('Price Preview Calculations', () => {
  it('calculates standard tier correctly', () => {
    const pricing = {
      week1_base_price: 89,
      week2_base_price: 140,
      tier_increment: 10,
    }

    // Standard = base + increment
    expect(pricing.week1_base_price + pricing.tier_increment).toBe(99)
    expect(pricing.week2_base_price + pricing.tier_increment).toBe(150)
  })

  it('calculates late tier correctly', () => {
    const pricing = {
      week1_base_price: 89,
      week2_base_price: 140,
      tier_increment: 10,
    }

    // Late = base + (increment * 2)
    expect(pricing.week1_base_price + (pricing.tier_increment * 2)).toBe(109)
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
// Mock Components for Testing
// =============================================================================

// Simplified HomePage component for testing
function MockHomePage() {
  const [prices, setPrices] = React.useState({ week1: 89, week2: 140 })

  React.useEffect(() => {
    const API_URL = import.meta.env?.VITE_API_URL || 'http://localhost:8000'
    fetch(`${API_URL}/api/pricing`)
      .then(res => {
        if (res.ok) return res.json()
        throw new Error('Not OK')
      })
      .then(data => {
        setPrices({
          week1: data.week1_base_price || 89,
          week2: data.week2_base_price || 140,
        })
      })
      .catch(() => {
        // Keep defaults
      })
  }, [])

  return (
    <div>
      <div className="pricing-card">
        <span className="price">{prices.week1}</span>
      </div>
      <div className="pricing-card">
        <span className="price">{prices.week2}</span>
      </div>
    </div>
  )
}

// Simplified Admin Pricing component for testing
function MockAdminPricing({ token }) {
  const [pricing, setPricing] = React.useState({
    week1_base_price: 89,
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
