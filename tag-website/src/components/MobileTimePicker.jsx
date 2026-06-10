import { useState, useRef, useEffect, useCallback } from 'react'
import './MobileTimePicker.css'

// Check if device is mobile/tablet
const isMobileOrTablet = () => {
  if (typeof window === 'undefined') return false
  return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
    (window.matchMedia && window.matchMedia('(max-width: 768px)').matches) ||
    ('ontouchstart' in window)
}

function MobileTimePicker({ value, onChange, id, placeholder, label, onAmbiguousTime, onStartEntry }) {
  const [showPicker, setShowPicker] = useState(false)
  const [hours, setHours] = useState('00')
  const [minutes, setMinutes] = useState('00')
  const [isMobile, setIsMobile] = useState(false)
  const pickerRef = useRef(null)
  const hoursRef = useRef(null)
  const minutesRef = useRef(null)

  // Check for mobile on mount
  useEffect(() => {
    setIsMobile(isMobileOrTablet())
    const handleResize = () => setIsMobile(isMobileOrTablet())
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  // Parse existing value when picker opens
  useEffect(() => {
    if (showPicker && value) {
      const parts = value.replace(':', '').padStart(4, '0')
      if (parts.length >= 4) {
        setHours(parts.slice(0, 2))
        setMinutes(parts.slice(2, 4))
      }
    }
  }, [showPicker, value])

  // Scroll to selected values when picker opens
  useEffect(() => {
    if (showPicker && hoursRef.current && minutesRef.current) {
      const hourNum = parseInt(hours) || 0
      const minNum = parseInt(minutes) || 0

      // Scroll to center the selected item (item height is 44px)
      const itemHeight = 44
      const containerHeight = hoursRef.current.clientHeight
      const centerOffset = (containerHeight - itemHeight) / 2

      hoursRef.current.scrollTop = hourNum * itemHeight - centerOffset
      minutesRef.current.scrollTop = minNum * itemHeight - centerOffset
    }
  }, [showPicker, hours, minutes])

  // Close picker when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (pickerRef.current && !pickerRef.current.contains(event.target)) {
        setShowPicker(false)
      }
    }
    if (showPicker) {
      document.addEventListener('mousedown', handleClickOutside)
      document.addEventListener('touchstart', handleClickOutside)
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('touchstart', handleClickOutside)
    }
  }, [showPicker])

  // Handle scroll snap for wheel selection
  const handleScroll = useCallback((ref, setter, max) => {
    if (!ref.current) return
    const itemHeight = 44
    const scrollTop = ref.current.scrollTop
    const containerHeight = ref.current.clientHeight
    const centerOffset = (containerHeight - itemHeight) / 2
    const selectedIndex = Math.round((scrollTop + centerOffset) / itemHeight)
    const clampedIndex = Math.max(0, Math.min(selectedIndex, max))
    setter(String(clampedIndex).padStart(2, '0'))
  }, [])

  // Debounced scroll handler
  const scrollTimeoutRef = useRef(null)
  const handleScrollEnd = useCallback((ref, setter, max) => {
    if (scrollTimeoutRef.current) {
      clearTimeout(scrollTimeoutRef.current)
    }
    scrollTimeoutRef.current = setTimeout(() => {
      handleScroll(ref, setter, max)
    }, 100)
  }, [handleScroll])

  // Check if time is ambiguous (01:00-12:59 could be AM or PM)
  const isAmbiguousTime = (hour) => {
    const h = parseInt(hour, 10)
    return h >= 1 && h <= 12
  }

  const handleConfirm = () => {
    const timeValue = `${hours}:${minutes}`
    onChange(timeValue)
    if (isAmbiguousTime(hours) && onAmbiguousTime) {
      onAmbiguousTime(timeValue)
    }
    setShowPicker(false)
  }

  const handleCancel = () => {
    setShowPicker(false)
  }

  // Generate hour options (00-23)
  const hourOptions = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0'))
  // Generate minute options (00-59)
  const minuteOptions = Array.from({ length: 60 }, (_, i) => String(i).padStart(2, '0'))

  // Handle desktop input change with ambiguous time detection
  const handleDesktopChange = (e) => {
    onStartEntry?.()
    const formatted = formatTimeInput(e.target.value)
    onChange(formatted)
    // Check for ambiguous time when input is complete (HH:MM format)
    if (formatted.length === 5 && onAmbiguousTime) {
      const hour = parseInt(formatted.slice(0, 2), 10)
      if (hour >= 1 && hour <= 12) {
        onAmbiguousTime(formatted)
      }
    }
  }

  // For desktop, use standard text input with formatting
  if (!isMobile) {
    return (
      <input
        type="text"
        id={id}
        placeholder={placeholder || "e.g., 1430"}
        maxLength={5}
        inputMode="numeric"
        value={value}
        onFocus={onStartEntry}
        onChange={handleDesktopChange}
      />
    )
  }

  // Mobile wheel picker
  return (
    <div className="mobile-time-picker-container">
      <input
        type="text"
        id={id}
        placeholder={placeholder || "Tap to select time"}
        value={value}
        readOnly
        onClick={() => {
          onStartEntry?.()
          setShowPicker(true)
        }}
        className="mobile-time-input"
      />

      {showPicker && (
        <div className="time-picker-overlay">
          <div className="time-picker-modal" ref={pickerRef}>
            <div className="time-picker-header">
              <button type="button" className="time-picker-cancel" onClick={handleCancel}>
                Cancel
              </button>
              <span className="time-picker-title">{label || 'Select Time'}</span>
              <button type="button" className="time-picker-confirm" onClick={handleConfirm}>
                Done
              </button>
            </div>

            <div className="time-picker-wheels">
              <div className="wheel-column">
                <div className="wheel-label">Hour</div>
                <div
                  className="wheel-scroll"
                  ref={hoursRef}
                  onScroll={() => handleScrollEnd(hoursRef, setHours, 23)}
                >
                  <div className="wheel-padding"></div>
                  {hourOptions.map((hour) => (
                    <div
                      key={hour}
                      className={`wheel-item ${hours === hour ? 'selected' : ''}`}
                      onClick={() => {
                        setHours(hour)
                        const itemHeight = 44
                        const containerHeight = hoursRef.current.clientHeight
                        const centerOffset = (containerHeight - itemHeight) / 2
                        hoursRef.current.scrollTop = parseInt(hour) * itemHeight - centerOffset
                      }}
                    >
                      {hour}
                    </div>
                  ))}
                  <div className="wheel-padding"></div>
                </div>
              </div>

              <div className="wheel-separator">:</div>

              <div className="wheel-column">
                <div className="wheel-label">Minute</div>
                <div
                  className="wheel-scroll"
                  ref={minutesRef}
                  onScroll={() => handleScrollEnd(minutesRef, setMinutes, 59)}
                >
                  <div className="wheel-padding"></div>
                  {minuteOptions.map((minute) => (
                    <div
                      key={minute}
                      className={`wheel-item ${minutes === minute ? 'selected' : ''}`}
                      onClick={() => {
                        setMinutes(minute)
                        const itemHeight = 44
                        const containerHeight = minutesRef.current.clientHeight
                        const centerOffset = (containerHeight - itemHeight) / 2
                        minutesRef.current.scrollTop = parseInt(minute) * itemHeight - centerOffset
                      }}
                    >
                      {minute}
                    </div>
                  ))}
                  <div className="wheel-padding"></div>
                </div>
              </div>
            </div>

            <div className="time-picker-preview">
              Selected: <strong>{hours}:{minutes}</strong>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// Format time input helper (same as in BookingsNew)
function formatTimeInput(input) {
  const digits = input.replace(/\D/g, '')
  if (digits.length <= 2) return digits
  if (digits.length <= 4) return digits.slice(0, 2) + ':' + digits.slice(2)
  return digits.slice(0, 2) + ':' + digits.slice(2, 4)
}

export default MobileTimePicker
