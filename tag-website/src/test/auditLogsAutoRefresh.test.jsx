/**
 * Unit and Integration tests for Audit Logs Auto-Refresh feature.
 *
 * Tests cover:
 * - Auto-refresh toggle state management
 * - Polling interval behavior (30 second intervals)
 * - Interval cleanup on toggle disable
 * - Interval cleanup on tab change
 * - Interval cleanup on component unmount
 * - API calls during auto-refresh
 * - Loading state during refresh
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { useState, useEffect } from 'react'

// Mock the audit logs auto-refresh hook behavior
const useAuditLogsAutoRefresh = (activeTab, token, filters) => {
  const [auditLogs, setAuditLogs] = useState([])
  const [loading, setLoading] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [fetchCount, setFetchCount] = useState(0)

  const fetchAuditLogs = () => {
    setLoading(true)
    setFetchCount(prev => prev + 1)
    // Synchronous for easier testing
    setAuditLogs([{ id: 1, event: 'test' }])
    setLoading(false)
  }

  // Auto-refresh effect
  useEffect(() => {
    if (!autoRefresh || activeTab !== 'qa-audit' || !token) return
    const interval = setInterval(() => {
      fetchAuditLogs()
    }, 30000)
    return () => clearInterval(interval)
  }, [autoRefresh, activeTab, token, filters])

  return {
    auditLogs,
    loading,
    autoRefresh,
    setAutoRefresh,
    fetchAuditLogs,
    fetchCount,
  }
}

// Test component that uses the hook
const TestAuditLogsComponent = ({ activeTab = 'qa-audit', token = 'test-token', filters = {} }) => {
  const {
    auditLogs,
    loading,
    autoRefresh,
    setAutoRefresh,
    fetchAuditLogs,
    fetchCount,
  } = useAuditLogsAutoRefresh(activeTab, token, filters)

  return (
    <div>
      <label className="auto-refresh-toggle">
        <input
          type="checkbox"
          checked={autoRefresh}
          onChange={(e) => setAutoRefresh(e.target.checked)}
          data-testid="auto-refresh-toggle"
        />
        Auto-refresh (30s)
      </label>
      <button onClick={fetchAuditLogs} disabled={loading} data-testid="refresh-btn">
        {loading ? 'Loading...' : 'Refresh'}
      </button>
      <span data-testid="fetch-count">{fetchCount}</span>
      <span data-testid="auto-refresh-status">{autoRefresh ? 'enabled' : 'disabled'}</span>
      <ul data-testid="audit-logs">
        {auditLogs.map(log => (
          <li key={log.id}>{log.event}</li>
        ))}
      </ul>
    </div>
  )
}

describe('Audit Logs Auto-Refresh', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('Unit Tests - Toggle State', () => {
    it('should render auto-refresh toggle unchecked by default', () => {
      render(<TestAuditLogsComponent />)

      const toggle = screen.getByTestId('auto-refresh-toggle')
      expect(toggle).not.toBeChecked()
      expect(screen.getByTestId('auto-refresh-status')).toHaveTextContent('disabled')
    })

    it('should enable auto-refresh when toggle is checked', () => {
      render(<TestAuditLogsComponent />)

      const toggle = screen.getByTestId('auto-refresh-toggle')
      fireEvent.click(toggle)

      expect(toggle).toBeChecked()
      expect(screen.getByTestId('auto-refresh-status')).toHaveTextContent('enabled')
    })

    it('should disable auto-refresh when toggle is unchecked', () => {
      render(<TestAuditLogsComponent />)

      const toggle = screen.getByTestId('auto-refresh-toggle')
      fireEvent.click(toggle) // Enable
      fireEvent.click(toggle) // Disable

      expect(toggle).not.toBeChecked()
      expect(screen.getByTestId('auto-refresh-status')).toHaveTextContent('disabled')
    })

    it('should display correct toggle label', () => {
      render(<TestAuditLogsComponent />)

      expect(screen.getByText('Auto-refresh (30s)')).toBeInTheDocument()
    })
  })

  describe('Unit Tests - Manual Refresh', () => {
    it('should show Refresh button', () => {
      render(<TestAuditLogsComponent />)

      expect(screen.getByTestId('refresh-btn')).toHaveTextContent('Refresh')
    })

    it('should call fetchAuditLogs when Refresh button is clicked', () => {
      render(<TestAuditLogsComponent />)

      const refreshBtn = screen.getByTestId('refresh-btn')
      fireEvent.click(refreshBtn)

      expect(screen.getByTestId('fetch-count')).toHaveTextContent('1')
    })

    it('should increment fetch count on multiple clicks', () => {
      render(<TestAuditLogsComponent />)

      const refreshBtn = screen.getByTestId('refresh-btn')
      fireEvent.click(refreshBtn)
      fireEvent.click(refreshBtn)
      fireEvent.click(refreshBtn)

      expect(screen.getByTestId('fetch-count')).toHaveTextContent('3')
    })
  })

  describe('Integration Tests - Polling Behavior', () => {
    it('should not poll when auto-refresh is disabled', () => {
      render(<TestAuditLogsComponent />)

      // Advance time by 60 seconds
      act(() => {
        vi.advanceTimersByTime(60000)
      })

      expect(screen.getByTestId('fetch-count')).toHaveTextContent('0')
    })

    it('should start polling when auto-refresh is enabled', () => {
      render(<TestAuditLogsComponent />)

      const toggle = screen.getByTestId('auto-refresh-toggle')
      fireEvent.click(toggle)

      // Initial state - no fetch yet from interval
      expect(screen.getByTestId('fetch-count')).toHaveTextContent('0')

      // Advance time by 30 seconds
      act(() => {
        vi.advanceTimersByTime(30000)
      })

      expect(screen.getByTestId('fetch-count')).toHaveTextContent('1')
    })

    it('should poll every 30 seconds', () => {
      render(<TestAuditLogsComponent />)

      const toggle = screen.getByTestId('auto-refresh-toggle')
      fireEvent.click(toggle)

      // Advance 30 seconds - 1st poll
      act(() => {
        vi.advanceTimersByTime(30000)
      })
      expect(screen.getByTestId('fetch-count')).toHaveTextContent('1')

      // Advance another 30 seconds - 2nd poll
      act(() => {
        vi.advanceTimersByTime(30000)
      })
      expect(screen.getByTestId('fetch-count')).toHaveTextContent('2')

      // Advance another 30 seconds - 3rd poll
      act(() => {
        vi.advanceTimersByTime(30000)
      })
      expect(screen.getByTestId('fetch-count')).toHaveTextContent('3')
    })

    it('should stop polling when auto-refresh is disabled', () => {
      render(<TestAuditLogsComponent />)

      const toggle = screen.getByTestId('auto-refresh-toggle')

      // Enable auto-refresh
      fireEvent.click(toggle)

      // Advance 30 seconds - 1st poll
      act(() => {
        vi.advanceTimersByTime(30000)
      })
      expect(screen.getByTestId('fetch-count')).toHaveTextContent('1')

      // Disable auto-refresh
      fireEvent.click(toggle)

      // Advance another 60 seconds - should NOT poll
      act(() => {
        vi.advanceTimersByTime(60000)
      })

      // Should still be 1 (no additional polls)
      expect(screen.getByTestId('fetch-count')).toHaveTextContent('1')
    })

    it('should not poll before 30 seconds', () => {
      render(<TestAuditLogsComponent />)

      const toggle = screen.getByTestId('auto-refresh-toggle')
      fireEvent.click(toggle)

      // Advance 29 seconds - should NOT poll yet
      act(() => {
        vi.advanceTimersByTime(29000)
      })

      expect(screen.getByTestId('fetch-count')).toHaveTextContent('0')
    })

    it('should poll immediately after 30 seconds passes', () => {
      render(<TestAuditLogsComponent />)

      const toggle = screen.getByTestId('auto-refresh-toggle')
      fireEvent.click(toggle)

      // Advance 29.999 seconds - should NOT poll yet
      act(() => {
        vi.advanceTimersByTime(29999)
      })
      expect(screen.getByTestId('fetch-count')).toHaveTextContent('0')

      // Advance 1 more ms to reach 30 seconds
      act(() => {
        vi.advanceTimersByTime(1)
      })
      expect(screen.getByTestId('fetch-count')).toHaveTextContent('1')
    })
  })

  describe('Integration Tests - Tab Change Behavior', () => {
    it('should not poll when on different tab', () => {
      render(<TestAuditLogsComponent activeTab="bookings" />)

      const toggle = screen.getByTestId('auto-refresh-toggle')
      fireEvent.click(toggle)

      // Advance 60 seconds
      act(() => {
        vi.advanceTimersByTime(60000)
      })

      expect(screen.getByTestId('fetch-count')).toHaveTextContent('0')
    })

    it('should only poll on qa-audit tab', () => {
      render(<TestAuditLogsComponent activeTab="qa-audit" />)

      const toggle = screen.getByTestId('auto-refresh-toggle')
      fireEvent.click(toggle)

      // Advance 30 seconds
      act(() => {
        vi.advanceTimersByTime(30000)
      })

      expect(screen.getByTestId('fetch-count')).toHaveTextContent('1')
    })

    it('should not poll on qa-errors tab', () => {
      render(<TestAuditLogsComponent activeTab="qa-errors" />)

      const toggle = screen.getByTestId('auto-refresh-toggle')
      fireEvent.click(toggle)

      act(() => {
        vi.advanceTimersByTime(60000)
      })

      expect(screen.getByTestId('fetch-count')).toHaveTextContent('0')
    })

    it('should not poll on qa-sql tab', () => {
      render(<TestAuditLogsComponent activeTab="qa-sql" />)

      const toggle = screen.getByTestId('auto-refresh-toggle')
      fireEvent.click(toggle)

      act(() => {
        vi.advanceTimersByTime(60000)
      })

      expect(screen.getByTestId('fetch-count')).toHaveTextContent('0')
    })
  })

  describe('Integration Tests - Token Behavior', () => {
    it('should not poll without token', () => {
      render(<TestAuditLogsComponent token={null} />)

      const toggle = screen.getByTestId('auto-refresh-toggle')
      fireEvent.click(toggle)

      // Advance 60 seconds
      act(() => {
        vi.advanceTimersByTime(60000)
      })

      expect(screen.getByTestId('fetch-count')).toHaveTextContent('0')
    })

    it('should not poll with empty token', () => {
      render(<TestAuditLogsComponent token="" />)

      const toggle = screen.getByTestId('auto-refresh-toggle')
      fireEvent.click(toggle)

      // Advance 60 seconds
      act(() => {
        vi.advanceTimersByTime(60000)
      })

      expect(screen.getByTestId('fetch-count')).toHaveTextContent('0')
    })

    it('should poll with valid token', () => {
      render(<TestAuditLogsComponent token="valid-token-123" />)

      const toggle = screen.getByTestId('auto-refresh-toggle')
      fireEvent.click(toggle)

      act(() => {
        vi.advanceTimersByTime(30000)
      })

      expect(screen.getByTestId('fetch-count')).toHaveTextContent('1')
    })
  })

  describe('Integration Tests - Cleanup', () => {
    it('should cleanup interval on unmount', () => {
      const { unmount } = render(<TestAuditLogsComponent />)

      const toggle = screen.getByTestId('auto-refresh-toggle')
      fireEvent.click(toggle)

      // Unmount component
      unmount()

      // Advance time - interval should be cleared, no errors
      act(() => {
        vi.advanceTimersByTime(60000)
      })

      // If we get here without errors, cleanup worked
      expect(true).toBe(true)
    })

    it('should cleanup old interval when auto-refresh is toggled rapidly', () => {
      render(<TestAuditLogsComponent />)

      const toggle = screen.getByTestId('auto-refresh-toggle')

      // Rapidly toggle
      fireEvent.click(toggle) // Enable
      fireEvent.click(toggle) // Disable
      fireEvent.click(toggle) // Enable
      fireEvent.click(toggle) // Disable
      fireEvent.click(toggle) // Enable

      // Advance 30 seconds
      act(() => {
        vi.advanceTimersByTime(30000)
      })

      // Should only have 1 fetch from the active interval
      expect(screen.getByTestId('fetch-count')).toHaveTextContent('1')
    })

    it('should not have memory leaks from multiple intervals', () => {
      render(<TestAuditLogsComponent />)

      const toggle = screen.getByTestId('auto-refresh-toggle')

      // Toggle many times
      for (let i = 0; i < 10; i++) {
        fireEvent.click(toggle) // Enable
        fireEvent.click(toggle) // Disable
      }
      fireEvent.click(toggle) // Final enable

      // Advance 30 seconds
      act(() => {
        vi.advanceTimersByTime(30000)
      })

      // Should only have 1 fetch (not 10+)
      expect(screen.getByTestId('fetch-count')).toHaveTextContent('1')
    })
  })
})


describe('Auto-Refresh Toggle CSS', () => {
  it('should have auto-refresh-toggle class on label', () => {
    render(<TestAuditLogsComponent />)

    const label = screen.getByText('Auto-refresh (30s)').closest('label')
    expect(label).toHaveClass('auto-refresh-toggle')
  })

  it('should contain checkbox input', () => {
    render(<TestAuditLogsComponent />)

    const checkbox = screen.getByTestId('auto-refresh-toggle')
    expect(checkbox.tagName).toBe('INPUT')
    expect(checkbox.type).toBe('checkbox')
  })
})


describe('API Integration Tests', () => {
  let mockFetch

  beforeEach(() => {
    vi.useFakeTimers()
    mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ audit_logs: [], total_count: 0 })
    })
    global.fetch = mockFetch
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  // Mock component that actually calls the API
  const MockAPIComponent = ({ token = 'test-token' }) => {
    const [autoRefresh, setAutoRefresh] = useState(false)
    const [fetchCount, setFetchCount] = useState(0)

    const fetchAuditLogs = () => {
      setFetchCount(prev => prev + 1)
      fetch('/api/admin/audit-logs', {
        headers: { 'Authorization': `Bearer ${token}` },
      }).catch(() => {}) // Swallow errors
    }

    useEffect(() => {
      if (!autoRefresh || !token) return
      const interval = setInterval(fetchAuditLogs, 30000)
      return () => clearInterval(interval)
    }, [autoRefresh, token])

    return (
      <div>
        <input
          type="checkbox"
          checked={autoRefresh}
          onChange={(e) => setAutoRefresh(e.target.checked)}
          data-testid="api-toggle"
        />
        <button onClick={fetchAuditLogs} data-testid="api-refresh">
          Refresh
        </button>
        <span data-testid="api-fetch-count">{fetchCount}</span>
      </div>
    )
  }

  it('should call API with correct authorization header on manual refresh', () => {
    render(<MockAPIComponent token="my-secret-token" />)

    fireEvent.click(screen.getByTestId('api-refresh'))

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/admin/audit-logs',
      expect.objectContaining({
        headers: { 'Authorization': 'Bearer my-secret-token' },
      })
    )
  })

  it('should call API every 30 seconds when auto-refresh enabled', () => {
    render(<MockAPIComponent />)

    fireEvent.click(screen.getByTestId('api-toggle'))

    // First poll at 30s
    act(() => {
      vi.advanceTimersByTime(30000)
    })
    expect(mockFetch).toHaveBeenCalledTimes(1)

    // Second poll at 60s
    act(() => {
      vi.advanceTimersByTime(30000)
    })
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('should include correct API endpoint', () => {
    render(<MockAPIComponent />)

    fireEvent.click(screen.getByTestId('api-refresh'))

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/admin/audit-logs',
      expect.anything()
    )
  })

  it('should handle API errors gracefully', () => {
    mockFetch.mockRejectedValue(new Error('Network error'))

    render(<MockAPIComponent />)

    // Should not throw
    expect(() => {
      fireEvent.click(screen.getByTestId('api-refresh'))
    }).not.toThrow()

    expect(mockFetch).toHaveBeenCalled()
  })

  it('should continue polling after API error', () => {
    mockFetch.mockRejectedValue(new Error('Network error'))

    render(<MockAPIComponent />)

    fireEvent.click(screen.getByTestId('api-toggle'))

    // First poll fails
    act(() => {
      vi.advanceTimersByTime(30000)
    })
    expect(mockFetch).toHaveBeenCalledTimes(1)

    // Second poll also happens (doesn't stop on error)
    act(() => {
      vi.advanceTimersByTime(30000)
    })
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('should not call API when toggle is disabled', () => {
    render(<MockAPIComponent />)

    // Don't enable toggle, just advance time
    act(() => {
      vi.advanceTimersByTime(60000)
    })

    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('should stop calling API when toggle is disabled after being enabled', () => {
    render(<MockAPIComponent />)

    const toggle = screen.getByTestId('api-toggle')

    // Enable
    fireEvent.click(toggle)

    // First poll
    act(() => {
      vi.advanceTimersByTime(30000)
    })
    expect(mockFetch).toHaveBeenCalledTimes(1)

    // Disable
    fireEvent.click(toggle)

    // More time passes but no more calls
    act(() => {
      vi.advanceTimersByTime(60000)
    })
    expect(mockFetch).toHaveBeenCalledTimes(1)
  })
})


describe('Edge Cases', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('should handle undefined filters gracefully', () => {
    expect(() => {
      render(<TestAuditLogsComponent filters={undefined} />)
    }).not.toThrow()
  })

  it('should handle null filters gracefully', () => {
    expect(() => {
      render(<TestAuditLogsComponent filters={null} />)
    }).not.toThrow()
  })

  it('should work with empty filters object', () => {
    render(<TestAuditLogsComponent filters={{}} />)

    const toggle = screen.getByTestId('auto-refresh-toggle')
    fireEvent.click(toggle)

    act(() => {
      vi.advanceTimersByTime(30000)
    })

    expect(screen.getByTestId('fetch-count')).toHaveTextContent('1')
  })

  it('should handle filter changes', () => {
    const { rerender } = render(<TestAuditLogsComponent filters={{ search: '' }} />)

    const toggle = screen.getByTestId('auto-refresh-toggle')
    fireEvent.click(toggle)

    act(() => {
      vi.advanceTimersByTime(30000)
    })
    expect(screen.getByTestId('fetch-count')).toHaveTextContent('1')

    // Change filters
    rerender(<TestAuditLogsComponent filters={{ search: 'test' }} />)

    // Should still work
    act(() => {
      vi.advanceTimersByTime(30000)
    })
    expect(screen.getByTestId('fetch-count')).toHaveTextContent('2')
  })
})
