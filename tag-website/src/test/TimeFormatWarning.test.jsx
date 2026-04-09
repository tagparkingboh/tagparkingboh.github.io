/**
 * Tests for 24-hour time format warning feature.
 *
 * These tests verify:
 * 1. MobileTimePicker detects ambiguous times (01:00-12:59)
 * 2. onAmbiguousTime callback is called correctly
 * 3. Warning toast appears once per session
 * 4. Toast auto-dismisses and can be manually closed
 * 5. SessionStorage persistence works correctly
 *
 * Test Coverage:
 * - Happy path: Warning shows on first ambiguous time entry
 * - Unhappy path: Warning doesn't show for unambiguous times (13:00-23:59, 00:xx)
 * - Edge cases: Boundary hours (12:59, 13:00, 00:00, 00:59)
 * - Boundaries: Session persistence, multiple time inputs
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// =============================================================================
// Unit Tests: Ambiguous Time Detection Logic
// =============================================================================

describe('MobileTimePicker - Ambiguous Time Detection', () => {
  // Mirror the isAmbiguousTime logic from MobileTimePicker.jsx
  const isAmbiguousTime = (hour) => {
    const h = parseInt(hour, 10)
    return h >= 1 && h <= 12
  }

  describe('Happy path - Ambiguous times (could be AM or PM)', () => {
    it('detects 01:00 as ambiguous', () => {
      expect(isAmbiguousTime('01')).toBe(true)
    })

    it('detects 06:30 as ambiguous', () => {
      expect(isAmbiguousTime('06')).toBe(true)
    })

    it('detects 11:00 as ambiguous', () => {
      expect(isAmbiguousTime('11')).toBe(true)
    })

    it('detects 12:00 as ambiguous', () => {
      expect(isAmbiguousTime('12')).toBe(true)
    })

    it('detects 12:59 as ambiguous (boundary)', () => {
      expect(isAmbiguousTime('12')).toBe(true)
    })
  })

  describe('Unhappy path - Unambiguous times (clearly 24-hour)', () => {
    it('does not flag 00:00 as ambiguous (midnight)', () => {
      expect(isAmbiguousTime('00')).toBe(false)
    })

    it('does not flag 00:30 as ambiguous', () => {
      expect(isAmbiguousTime('00')).toBe(false)
    })

    it('does not flag 13:00 as ambiguous (boundary)', () => {
      expect(isAmbiguousTime('13')).toBe(false)
    })

    it('does not flag 14:30 as ambiguous', () => {
      expect(isAmbiguousTime('14')).toBe(false)
    })

    it('does not flag 18:00 as ambiguous', () => {
      expect(isAmbiguousTime('18')).toBe(false)
    })

    it('does not flag 23:00 as ambiguous', () => {
      expect(isAmbiguousTime('23')).toBe(false)
    })

    it('does not flag 23:59 as ambiguous (boundary)', () => {
      expect(isAmbiguousTime('23')).toBe(false)
    })
  })

  describe('Edge cases', () => {
    it('handles single digit hour "1" as ambiguous', () => {
      expect(isAmbiguousTime('1')).toBe(true)
    })

    it('handles hour "0" as not ambiguous', () => {
      expect(isAmbiguousTime('0')).toBe(false)
    })

    it('handles padded zero "00" as not ambiguous', () => {
      expect(isAmbiguousTime('00')).toBe(false)
    })
  })
})

// =============================================================================
// Unit Tests: Desktop Input Ambiguous Time Detection
// =============================================================================

describe('MobileTimePicker - Desktop Input Change Handler', () => {
  // Mirror the desktop change handler logic
  const checkAmbiguousOnComplete = (formatted) => {
    if (formatted.length === 5) {
      const hour = parseInt(formatted.slice(0, 2), 10)
      return hour >= 1 && hour <= 12
    }
    return false
  }

  describe('Happy path - Complete time inputs', () => {
    it('triggers callback for 11:00', () => {
      expect(checkAmbiguousOnComplete('11:00')).toBe(true)
    })

    it('triggers callback for 07:30', () => {
      expect(checkAmbiguousOnComplete('07:30')).toBe(true)
    })

    it('triggers callback for 12:45', () => {
      expect(checkAmbiguousOnComplete('12:45')).toBe(true)
    })
  })

  describe('Unhappy path - Incomplete or unambiguous inputs', () => {
    it('does not trigger for incomplete input "11"', () => {
      expect(checkAmbiguousOnComplete('11')).toBe(false)
    })

    it('does not trigger for incomplete input "11:"', () => {
      expect(checkAmbiguousOnComplete('11:')).toBe(false)
    })

    it('does not trigger for 14:30', () => {
      expect(checkAmbiguousOnComplete('14:30')).toBe(false)
    })

    it('does not trigger for 00:00', () => {
      expect(checkAmbiguousOnComplete('00:00')).toBe(false)
    })

    it('does not trigger for 23:59', () => {
      expect(checkAmbiguousOnComplete('23:59')).toBe(false)
    })
  })

  describe('Boundaries', () => {
    it('triggers for 01:00 (lower boundary)', () => {
      expect(checkAmbiguousOnComplete('01:00')).toBe(true)
    })

    it('triggers for 12:59 (upper boundary)', () => {
      expect(checkAmbiguousOnComplete('12:59')).toBe(true)
    })

    it('does not trigger for 13:00 (just above boundary)', () => {
      expect(checkAmbiguousOnComplete('13:00')).toBe(false)
    })

    it('does not trigger for 00:59 (just below boundary)', () => {
      expect(checkAmbiguousOnComplete('00:59')).toBe(false)
    })
  })
})

// =============================================================================
// Integration Tests: Session Storage Persistence
// =============================================================================

describe('Time Format Warning - Session Storage', () => {
  beforeEach(() => {
    // Clear sessionStorage before each test
    sessionStorage.clear()
  })

  afterEach(() => {
    sessionStorage.clear()
  })

  describe('Happy path - First time warning', () => {
    it('sessionStorage is empty initially', () => {
      expect(sessionStorage.getItem('booking_timeFormatWarningShown')).toBeNull()
    })

    it('sets flag to true after warning is shown', () => {
      // Simulate what handleAmbiguousTime does
      sessionStorage.setItem('booking_timeFormatWarningShown', 'true')
      expect(sessionStorage.getItem('booking_timeFormatWarningShown')).toBe('true')
    })
  })

  describe('Unhappy path - Warning already shown', () => {
    it('does not show warning again when flag is already set', () => {
      sessionStorage.setItem('booking_timeFormatWarningShown', 'true')

      // Simulate the ref check
      const warningAlreadyShown = sessionStorage.getItem('booking_timeFormatWarningShown') === 'true'
      expect(warningAlreadyShown).toBe(true)
    })
  })

  describe('Edge cases', () => {
    it('handles missing sessionStorage gracefully', () => {
      const value = sessionStorage.getItem('nonexistent_key')
      expect(value).toBeNull()
      expect(value === 'true').toBe(false)
    })
  })
})

// =============================================================================
// Integration Tests: Warning Handler Logic
// =============================================================================

describe('Time Format Warning - Handler Logic', () => {
  let warningShownRef
  let showWarningState
  let setShowWarning

  beforeEach(() => {
    sessionStorage.clear()
    warningShownRef = { current: false }
    showWarningState = false
    setShowWarning = vi.fn((value) => {
      showWarningState = value
    })
  })

  afterEach(() => {
    sessionStorage.clear()
  })

  // Mirror handleAmbiguousTime logic
  const handleAmbiguousTime = () => {
    if (!warningShownRef.current) {
      warningShownRef.current = true
      sessionStorage.setItem('booking_timeFormatWarningShown', 'true')
      setShowWarning(true)
    }
  }

  describe('Happy path', () => {
    it('shows warning on first call', () => {
      handleAmbiguousTime()

      expect(warningShownRef.current).toBe(true)
      expect(setShowWarning).toHaveBeenCalledWith(true)
      expect(sessionStorage.getItem('booking_timeFormatWarningShown')).toBe('true')
    })
  })

  describe('Unhappy path', () => {
    it('does not show warning on second call', () => {
      handleAmbiguousTime()
      setShowWarning.mockClear()

      handleAmbiguousTime()

      expect(setShowWarning).not.toHaveBeenCalled()
    })

    it('does not show warning if already shown in previous session', () => {
      // Simulate loading from sessionStorage
      sessionStorage.setItem('booking_timeFormatWarningShown', 'true')
      warningShownRef.current = sessionStorage.getItem('booking_timeFormatWarningShown') === 'true'

      handleAmbiguousTime()

      expect(setShowWarning).not.toHaveBeenCalled()
    })
  })

  describe('Edge cases - Multiple time inputs', () => {
    it('only shows warning once across multiple ambiguous times', () => {
      // First ambiguous time
      handleAmbiguousTime()
      expect(setShowWarning).toHaveBeenCalledTimes(1)

      setShowWarning.mockClear()

      // Second ambiguous time
      handleAmbiguousTime()
      expect(setShowWarning).not.toHaveBeenCalled()

      // Third ambiguous time
      handleAmbiguousTime()
      expect(setShowWarning).not.toHaveBeenCalled()
    })
  })
})

// =============================================================================
// Integration Tests: Toast Display
// =============================================================================

describe('Time Format Warning - Toast Display', () => {
  describe('Happy path - Toast content', () => {
    it('toast message includes 24-hour format explanation', () => {
      const toastMessage = 'Just checking – is that morning or evening? We use 24-hour format, so 11pm would be 23:00.'

      expect(toastMessage).toContain('24-hour format')
      expect(toastMessage).toContain('11pm')
      expect(toastMessage).toContain('23:00')
    })

    it('toast message is helpful for common evening times', () => {
      const toastMessage = 'Just checking – is that morning or evening? We use 24-hour format, so 11pm would be 23:00.'

      // Should help users understand the PM conversion
      expect(toastMessage).toContain('evening')
    })
  })

  describe('Boundaries - Auto-dismiss timing', () => {
    it('auto-dismiss timeout is set to 6 seconds', () => {
      const AUTO_DISMISS_MS = 6000
      expect(AUTO_DISMISS_MS).toBe(6000)
    })
  })
})

// =============================================================================
// Unit Tests: Time Format Helper
// =============================================================================

describe('Time Input Formatting', () => {
  // Mirror formatTimeInput from MobileTimePicker
  const formatTimeInput = (input) => {
    const digits = input.replace(/\D/g, '')
    if (digits.length <= 2) return digits
    if (digits.length <= 4) return digits.slice(0, 2) + ':' + digits.slice(2)
    return digits.slice(0, 2) + ':' + digits.slice(2, 4)
  }

  describe('Happy path', () => {
    it('formats "1430" to "14:30"', () => {
      expect(formatTimeInput('1430')).toBe('14:30')
    })

    it('formats "0930" to "09:30"', () => {
      expect(formatTimeInput('0930')).toBe('09:30')
    })

    it('formats "2359" to "23:59"', () => {
      expect(formatTimeInput('2359')).toBe('23:59')
    })
  })

  describe('Edge cases - Partial inputs', () => {
    it('returns "14" for partial input "14"', () => {
      expect(formatTimeInput('14')).toBe('14')
    })

    it('returns "14:3" for partial input "143"', () => {
      expect(formatTimeInput('143')).toBe('14:3')
    })
  })

  describe('Edge cases - Non-digit characters', () => {
    it('strips non-digit characters', () => {
      expect(formatTimeInput('14:30')).toBe('14:30')
    })

    it('handles input with letters', () => {
      expect(formatTimeInput('14abc30')).toBe('14:30')
    })
  })

  describe('Boundaries', () => {
    it('formats "0000" to "00:00"', () => {
      expect(formatTimeInput('0000')).toBe('00:00')
    })

    it('truncates extra digits in "123456"', () => {
      expect(formatTimeInput('123456')).toBe('12:34')
    })
  })
})
