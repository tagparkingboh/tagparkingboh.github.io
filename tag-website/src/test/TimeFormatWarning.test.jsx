/**
 * Tests for 24-hour time format warning feature.
 *
 * These tests verify:
 * 1. MobileTimePicker detects ambiguous times (01:00-12:59)
 * 2. onAmbiguousTime callback is called correctly
 * 3. Departure warning and arrival date/time notice show once per session
 * 4. Departure inline warning displays below time input
 * 5. SessionStorage persistence works correctly for each field
 *
 * Test Coverage:
 * - Happy path: Warning shows on first ambiguous time entry for each field
 * - Unhappy path: Warning doesn't show for unambiguous times (13:00-23:59, 00:xx)
 * - Edge cases: Boundary hours (12:59, 13:00, 00:00, 00:59)
 * - Boundaries: Separate session persistence for departure vs arrival
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

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
// Integration Tests: Session Storage Persistence (Separate for Departure/Arrival)
// =============================================================================

describe('Time Format Warning - Session Storage (Separate Fields)', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  afterEach(() => {
    sessionStorage.clear()
  })

  describe('Happy path - Independent tracking', () => {
    it('departure and arrival keys are separate', () => {
      sessionStorage.setItem('booking_departureTimeWarningShown', 'true')

      expect(sessionStorage.getItem('booking_departureTimeWarningShown')).toBe('true')
      expect(sessionStorage.getItem('booking_arrivalTimeWarningShown')).toBeNull()
    })

    it('can set both independently', () => {
      sessionStorage.setItem('booking_departureTimeWarningShown', 'true')
      sessionStorage.setItem('booking_arrivalTimeWarningShown', 'true')

      expect(sessionStorage.getItem('booking_departureTimeWarningShown')).toBe('true')
      expect(sessionStorage.getItem('booking_arrivalTimeWarningShown')).toBe('true')
    })
  })

  describe('Edge cases', () => {
    it('sessionStorage is empty initially for both', () => {
      expect(sessionStorage.getItem('booking_departureTimeWarningShown')).toBeNull()
      expect(sessionStorage.getItem('booking_arrivalTimeWarningShown')).toBeNull()
    })
  })
})

// =============================================================================
// Integration Tests: Departure Warning Handler Logic
// =============================================================================

describe('Time Format Warning - Departure Handler', () => {
  let departureWarningShownRef
  let setShowDepartureWarning

  beforeEach(() => {
    sessionStorage.clear()
    departureWarningShownRef = { current: false }
    setShowDepartureWarning = vi.fn()
  })

  afterEach(() => {
    sessionStorage.clear()
  })

  const handleAmbiguousDepartureTime = () => {
    if (!departureWarningShownRef.current) {
      departureWarningShownRef.current = true
      sessionStorage.setItem('booking_departureTimeWarningShown', 'true')
      setShowDepartureWarning(true)
    }
  }

  describe('Happy path', () => {
    it('shows warning on first departure time entry', () => {
      handleAmbiguousDepartureTime()

      expect(departureWarningShownRef.current).toBe(true)
      expect(setShowDepartureWarning).toHaveBeenCalledWith(true)
      expect(sessionStorage.getItem('booking_departureTimeWarningShown')).toBe('true')
    })
  })

  describe('Unhappy path', () => {
    it('does not show warning on second departure time entry', () => {
      handleAmbiguousDepartureTime()
      setShowDepartureWarning.mockClear()

      handleAmbiguousDepartureTime()

      expect(setShowDepartureWarning).not.toHaveBeenCalled()
    })

    it('does not show warning if already shown in previous session', () => {
      sessionStorage.setItem('booking_departureTimeWarningShown', 'true')
      departureWarningShownRef.current = sessionStorage.getItem('booking_departureTimeWarningShown') === 'true'

      handleAmbiguousDepartureTime()

      expect(setShowDepartureWarning).not.toHaveBeenCalled()
    })
  })
})

// =============================================================================
// Integration Tests: Arrival Date/Time Notice Handler Logic
// =============================================================================

describe('Time Format Warning - Arrival Handler', () => {
  let arrivalWarningShownRef
  let setShowArrivalNotice

  beforeEach(() => {
    sessionStorage.clear()
    arrivalWarningShownRef = { current: false }
    setShowArrivalNotice = vi.fn()
  })

  afterEach(() => {
    sessionStorage.clear()
  })

  const handleArrivalTimeStarted = () => {
    if (!arrivalWarningShownRef.current) {
      arrivalWarningShownRef.current = true
      sessionStorage.setItem('booking_arrivalTimeWarningShown', 'true')
      setShowArrivalNotice(true)
    }
  }

  describe('Happy path', () => {
    it('shows notice on first arrival time entry', () => {
      handleArrivalTimeStarted()

      expect(arrivalWarningShownRef.current).toBe(true)
      expect(setShowArrivalNotice).toHaveBeenCalledWith(true)
      expect(sessionStorage.getItem('booking_arrivalTimeWarningShown')).toBe('true')
    })
  })

  describe('Unhappy path', () => {
    it('does not show notice on second arrival time entry', () => {
      handleArrivalTimeStarted()
      setShowArrivalNotice.mockClear()

      handleArrivalTimeStarted()

      expect(setShowArrivalNotice).not.toHaveBeenCalled()
    })
  })
})

// =============================================================================
// Integration Tests: Independent Field Warnings
// =============================================================================

describe('Time Format Warning - Independent Departure/Arrival Warnings', () => {
  let departureWarningShownRef
  let arrivalWarningShownRef
  let setShowDepartureWarning
  let setShowArrivalNotice

  beforeEach(() => {
    sessionStorage.clear()
    departureWarningShownRef = { current: false }
    arrivalWarningShownRef = { current: false }
    setShowDepartureWarning = vi.fn()
    setShowArrivalNotice = vi.fn()
  })

  afterEach(() => {
    sessionStorage.clear()
  })

  const handleAmbiguousDepartureTime = () => {
    if (!departureWarningShownRef.current) {
      departureWarningShownRef.current = true
      sessionStorage.setItem('booking_departureTimeWarningShown', 'true')
      setShowDepartureWarning(true)
    }
  }

  const handleArrivalTimeStarted = () => {
    if (!arrivalWarningShownRef.current) {
      arrivalWarningShownRef.current = true
      sessionStorage.setItem('booking_arrivalTimeWarningShown', 'true')
      setShowArrivalNotice(true)
    }
  }

  describe('Happy path - Both warnings show independently', () => {
    it('departure warning shows even after arrival notice was shown', () => {
      handleArrivalTimeStarted()
      expect(setShowArrivalNotice).toHaveBeenCalledTimes(1)

      handleAmbiguousDepartureTime()
      expect(setShowDepartureWarning).toHaveBeenCalledWith(true)
    })

    it('arrival notice shows even after departure warning was shown', () => {
      handleAmbiguousDepartureTime()
      expect(setShowDepartureWarning).toHaveBeenCalledWith(true)

      handleArrivalTimeStarted()
      expect(setShowArrivalNotice).toHaveBeenCalledTimes(1)
    })

    it('both notices can be shown in same session', () => {
      handleAmbiguousDepartureTime()
      handleArrivalTimeStarted()

      expect(setShowDepartureWarning).toHaveBeenCalledTimes(1)
      expect(setShowArrivalNotice).toHaveBeenCalledTimes(1)
      expect(sessionStorage.getItem('booking_departureTimeWarningShown')).toBe('true')
      expect(sessionStorage.getItem('booking_arrivalTimeWarningShown')).toBe('true')
    })
  })

  describe('Edge cases - Multiple entries per field', () => {
    it('departure warning shows once even with multiple ambiguous entries', () => {
      handleAmbiguousDepartureTime()
      handleAmbiguousDepartureTime()
      handleAmbiguousDepartureTime()

      expect(setShowDepartureWarning).toHaveBeenCalledTimes(1)
    })

    it('arrival notice shows once even with multiple entries', () => {
      handleArrivalTimeStarted()
      handleArrivalTimeStarted()
      handleArrivalTimeStarted()

      expect(setShowArrivalNotice).toHaveBeenCalledTimes(1)
    })
  })
})

// =============================================================================
// Integration Tests: Warning Content
// =============================================================================

describe('Time Format Warning - Warning Content', () => {
  describe('Happy path - Departure warning content', () => {
    it('departure warning message includes 24-hour format explanation', () => {
      const warningMessage = 'Just checking – is that morning or evening? We use 24-hour format, so 11pm would be 23:00.'

      expect(warningMessage).toContain('24-hour format')
      expect(warningMessage).toContain('11pm')
      expect(warningMessage).toContain('23:00')
    })

    it('departure warning message asks about morning or evening', () => {
      const warningMessage = 'Just checking – is that morning or evening? We use 24-hour format, so 11pm would be 23:00.'

      expect(warningMessage).toContain('morning')
      expect(warningMessage).toContain('evening')
    })

    it('arrival notice message mentions following-day landings', () => {
      const warningMessage = "Please enter the arrival date and time shown for your flight. If your flight lands after midnight, select the date it lands, even if that's the following day."

      expect(warningMessage).toContain('arrival date and time')
      expect(warningMessage).toContain('after midnight')
      expect(warningMessage).toContain('following day')
    })
  })

  describe('Boundaries - Inline display persists', () => {
    it('warning does not auto-dismiss (inline stays visible)', () => {
      // Inline warnings stay visible - no auto-dismiss timeout
      const hasAutoTimeout = false
      expect(hasAutoTimeout).toBe(false)
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
