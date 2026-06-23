import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import HomePage from '../HomePage'

class MockBroadcastChannel {
  constructor() {}
  postMessage() {}
  close() {}
}

describe('HomePage airport comparison', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    global.BroadcastChannel = MockBroadcastChannel
    global.fetch = vi.fn((url) => {
      const endpoint = String(url)
      if (endpoint.includes('/api/airport-parking/homepage-comparison')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            checkedAt: '2026-06-23T09:30:00+01:00',
            maxCheapestSavingPct: 25,
            maxPremiumSavingPct: 58,
            items: [
              {
                billingDays: 4,
                cheapestPence: 16800,
                premiumPence: 30000,
                tagPricePence: 12600,
                savingPct: 25,
                premiumSavingPct: 58,
                checkedAt: '2026-06-23T09:30:00+01:00',
                source: 'live',
              },
              {
                billingDays: 7,
                cheapestPence: 18000,
                premiumPence: 32000,
                tagPricePence: 13500,
                savingPct: 25,
                premiumSavingPct: 58,
                checkedAt: '2026-06-23T09:30:00+01:00',
                source: 'live',
              },
            ],
          }),
        })
      }
      if (endpoint.includes('/api/pricing')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            days_1_4_price: 65,
            week1_base_price: 89,
            week2_base_price: 140,
            tier_increment: 5,
            peak_day_increment: 0,
            show_price_range: false,
          }),
        })
      }
      if (endpoint.includes('/api/promo-section')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ promoSection: null }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders cached live airport comparison rows without scraping from the browser', async () => {
    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>
    )

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/airport-parking/homepage-comparison'),
        expect.objectContaining({ cache: 'no-store' })
      )
    })

    expect(await screen.findByText(/LIVE Bournemouth Airport prices/i)).toBeInTheDocument()
    expect(screen.getByText('4 DAYS')).toBeInTheDocument()
    expect(screen.getByText('7 DAYS')).toBeInTheDocument()
    expect(screen.getByText('Most popular')).toBeInTheDocument()
    expect(screen.getByText('£168.00')).toBeInTheDocument()
    expect(screen.getByText('£126.00')).toBeInTheDocument()
    expect(screen.queryByText('SAVE 25%')).not.toBeInTheDocument()
    expect(screen.getByText('Up to 30% off their cheapest · up to 70% off Premium Parking')).toBeInTheDocument()
  })
})
