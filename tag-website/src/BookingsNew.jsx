import { useState, useMemo, useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import DatePicker from 'react-datepicker'
import { format } from 'date-fns'
import { getMakes, getModels } from 'car-info'
import PhoneInput, { isValidPhoneNumber } from 'react-phone-number-input'
import 'react-phone-number-input/style.css'
import StripePayment from './components/StripePayment'
import MobileTimePicker from './components/MobileTimePicker'
import 'react-datepicker/dist/react-datepicker.css'
import './BookingsNew.css'

// Country code to full name mapping
const countryNames = {
  ES: 'Spain',
  PT: 'Portugal',
  GB: 'United Kingdom',
  CH: 'Switzerland',
  PL: 'Poland',
  MT: 'Malta',
  FR: 'France',
  IT: 'Italy',
  DE: 'Germany',
  GR: 'Greece',
  TR: 'Turkey',
  CY: 'Cyprus',
  HR: 'Croatia',
  NL: 'Netherlands',
  BE: 'Belgium',
  AT: 'Austria',
  IE: 'Ireland',
  SC: 'Scotland',
  IS: 'Iceland',
  CZ: 'Czech Republic',
  HU: 'Hungary',
  SI: 'Slovenia',
  LV: 'Latvia',
  LT: 'Lithuania',
  EE: 'Estonia',
  NO: 'Norway',
  SE: 'Sweden',
  DK: 'Denmark',
  FI: 'Finland',
  TN: 'Tunisia',
  MA: 'Morocco',
  EG: 'Egypt'
}

// Generate a unique session ID for tracking the booking flow
const generateSessionId = () => {
  return `sess_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`
}

// Get today's date in UK time (prevents selecting past dates)
const getTodayUK = () => {
  const now = new Date()
  // Convert to UK time string and parse back
  const ukDateStr = now.toLocaleDateString('en-GB', { timeZone: 'Europe/London' })
  const [day, month, year] = ukDateStr.split('/')
  return new Date(year, month - 1, day)
}

// Get current UK time in minutes since midnight
const getCurrentUKTimeMinutes = () => {
  const now = new Date()
  const ukTimeStr = now.toLocaleTimeString('en-GB', { timeZone: 'Europe/London', hour: '2-digit', minute: '2-digit', hour12: false })
  const [hours, minutes] = ukTimeStr.split(':').map(Number)
  return hours * 60 + minutes
}

// Minimum hours notice required for same-day bookings
const MIN_HOURS_NOTICE = 4

// Normalize airline names (merge Ryanair UK into Ryanair)
const normalizeAirlineName = (name) => {
  if (name === 'Ryanair UK') return 'Ryanair'
  return name
}

// Profanity filter for custom airline/destination entries
const profanityWords = [
  'fuck', 'shit', 'ass', 'bitch', 'damn', 'crap', 'piss', 'dick', 'cock',
  'pussy', 'asshole', 'bastard', 'slut', 'whore', 'cunt', 'wanker', 'bollocks',
  'twat', 'arse', 'bugger', 'bloody', 'sodding', 'shite', 'tosser', 'bellend',
  'minger', 'knob', 'prick', 'git', 'pillock', 'plonker', 'sod', 'slag'
]

const containsProfanity = (text) => {
  if (!text) return false
  const lowerText = text.toLowerCase().replace(/[^a-z]/g, '')
  return profanityWords.some(word => lowerText.includes(word))
}

// Helper to load booking state from sessionStorage
function loadBookingState(key, fallback) {
  try {
    const saved = sessionStorage.getItem(`booking_${key}`)
    if (saved !== null) {
      const parsed = JSON.parse(saved)
      console.log(`[loadBookingState] Loaded ${key}:`, parsed)
      return parsed
    }
    console.log(`[loadBookingState] No saved value for ${key}, using fallback`)
  } catch (e) {
    console.error(`[loadBookingState] Error parsing ${key}:`, e)
  }
  return fallback
}

function Bookings() {
  const navigate = useNavigate()
  const [currentStep, setCurrentStep] = useState(() => loadBookingState('step', 1))
  const [paymentComplete, setPaymentComplete] = useState(false)
  const [bookingConfirmation, setBookingConfirmation] = useState(null)
  const [customerId, setCustomerId] = useState(() => loadBookingState('customerId', null))
  const [savedEmail, setSavedEmail] = useState(() => loadBookingState('savedEmail', null))
  const [vehicleId, setVehicleId] = useState(() => loadBookingState('vehicleId', null))
  const [saving, setSaving] = useState(false)
  // Welcome modal state - shown first before any steps
  const [showWelcomeModal, setShowWelcomeModal] = useState(true)
  // Track when user has attempted to submit each step (to show validation errors)
  const [step1Attempted, setStep1Attempted] = useState(false)
  const [step2Attempted, setStep2Attempted] = useState(false)

  // Google Analytics page view tracking for SPA
  useEffect(() => {
    if (window.gtag) {
      window.gtag('config', 'G-RCP3538V5B', {
        page_path: '/tag-it',
        page_title: 'Book Parking - TAG'
      })
    }
  }, [])

  // Session ID for audit trail - persists across the booking flow (survives hard refresh)
  const sessionIdRef = useRef(
    sessionStorage.getItem('booking_sessionId') || (() => {
      const newId = generateSessionId()
      sessionStorage.setItem('booking_sessionId', newId)
      return newId
    })()
  )
  // DVLA lookup state
  const [dvlaLoading, setDvlaLoading] = useState(false)
  const [dvlaError, setDvlaError] = useState('')
  const [dvlaVerified, setDvlaVerified] = useState(() => loadBookingState('dvlaVerified', false))
  // Address lookup state
  const [addressLoading, setAddressLoading] = useState(false)
  const [addressError, setAddressError] = useState('')
  const [addressList, setAddressList] = useState([])
  const [showAddressSelect, setShowAddressSelect] = useState(false)
  const [postcodeSearched, setPostcodeSearched] = useState('')
  const [manualAddressEntry, setManualAddressEntry] = useState(false)
  // Promo code state
  const [promoCode, setPromoCode] = useState(() => loadBookingState('promoCode', ''))
  const [promoCodeValidating, setPromoCodeValidating] = useState(false)
  const [promoCodeValid, setPromoCodeValid] = useState(() => loadBookingState('promoCodeValid', false))
  const [promoCodeMessage, setPromoCodeMessage] = useState(() => loadBookingState('promoCodeMessage', ''))
  const [promoCodeDiscount, setPromoCodeDiscount] = useState(() => loadBookingState('promoCodeDiscount', 0))

  // "Where did you hear about us?" marketing attribution state
  const [heardAboutUsSource, setHeardAboutUsSource] = useState(() => loadBookingState('heardAboutUsSource', ''))
  const [heardAboutUsDetail, setHeardAboutUsDetail] = useState(() => loadBookingState('heardAboutUsDetail', ''))
  const [heardAboutUsAnswered, setHeardAboutUsAnswered] = useState(() => loadBookingState('heardAboutUsAnswered', false))
  const [heardAboutUsLoading, setHeardAboutUsLoading] = useState(false)
  const [heardAboutUsSubmitting, setHeardAboutUsSubmitting] = useState(false)

  // Manual flight entry and time override state
  const [showDepartureTimeOverride, setShowDepartureTimeOverride] = useState(() => loadBookingState('showDepartureTimeOverride', false))
  const [departureTimeOverride, setDepartureTimeOverride] = useState(() => loadBookingState('departureTimeOverride', ''))
  const [departureTimeValidating, setDepartureTimeValidating] = useState(false)
  const [departureTimeError, setDepartureTimeError] = useState('')
  const [showArrivalTimeOverride, setShowArrivalTimeOverride] = useState(() => loadBookingState('showArrivalTimeOverride', false))
  const [arrivalTimeOverride, setArrivalTimeOverride] = useState(() => loadBookingState('arrivalTimeOverride', ''))
  const [arrivalTimeValidating, setArrivalTimeValidating] = useState(false)
  const [arrivalTimeError, setArrivalTimeError] = useState('')
  // Manual entry is now the default (simplified booking flow)
  const [showManualDeparture, setShowManualDeparture] = useState(true)
  const [manualDepartureData, setManualDepartureData] = useState(() => loadBookingState('manualDepartureData', {
    flightNumber: '',
    flightTime: '',
    airlineCode: '',
    airlineName: '',
    customAirline: '',
    destinationCode: '',
    destinationName: '',
    customDestination: '',
    dropoffSlot: ''
  }))
  // Manual entry is now the default (simplified booking flow)
  const [showManualArrival, setShowManualArrival] = useState(true)
  const [manualArrivalData, setManualArrivalData] = useState(() => loadBookingState('manualArrivalData', {
    flightNumber: '',
    flightTime: '',
    airlineCode: '',
    airlineName: '',
    customAirline: '',
    originCode: '',
    originName: '',
    customOrigin: ''
  }))
  const [availableAirlines, setAvailableAirlines] = useState([])
  const [availableDestinations, setAvailableDestinations] = useState([])
  const [formData, setFormData] = useState(() => {
    const defaults = {
      dropoffDate: null,
      dropoffAirline: '',
      dropoffFlight: '',
      dropoffSlot: '',
      pickupDate: null,
      pickupFlightTime: '',
      registration: '',
      make: '',
      customMake: '',
      model: '',
      customModel: '',
      colour: '',
      firstName: '',
      lastName: '',
      email: '',
      phone: '',
      flightNumber: '',
      package: '',
      // Billing Address
      billingAddress1: '',
      billingAddress2: '',
      billingCity: '',
      billingCounty: '',
      billingPostcode: '',
      billingCountry: 'United Kingdom',
      terms: false
    }
    const saved = loadBookingState('formData', null)
    if (!saved) return defaults
    // Restore dates from ISO strings
    // Clear saved dates if they're in the past (UK time)
    const todayUK = getTodayUK()
    let dropoffDate = saved.dropoffDate ? new Date(saved.dropoffDate) : null
    let pickupDate = saved.pickupDate ? new Date(saved.pickupDate) : null

    // Clear saved dates if they're before today (UK time)
    if (dropoffDate && dropoffDate < todayUK) {
      dropoffDate = null
      pickupDate = null // Also clear pickup since it depends on dropoff
    }

    return {
      ...defaults,
      ...saved,
      dropoffDate,
      pickupDate,
    }
  })

  // API base URL
  const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

  // Flight data from API
  const [departuresForDate, setDeparturesForDate] = useState([])
  const [arrivalsForDate, setArrivalsForDate] = useState([])
  const [loadingFlights, setLoadingFlights] = useState(false)
  const [departuresLoaded, setDeparturesLoaded] = useState(false)
  const [arrivalsLoaded, setArrivalsLoaded] = useState(false)

  // Parking capacity management
  const MAX_PARKING_SPOTS = 60

  // This would normally come from your database/API
  // For now, simulating with a placeholder
  const [bookedSpots, setBookedSpots] = useState({})

  // Dynamic pricing state
  const [pricingInfo, setPricingInfo] = useState(null)
  const [pricingLoading, setPricingLoading] = useState(false)

  // Persist booking state to sessionStorage so hard refresh keeps the user on their current step
  useEffect(() => {
    sessionStorage.setItem('booking_step', JSON.stringify(currentStep))
  }, [currentStep])

  useEffect(() => {
    sessionStorage.setItem('booking_formData', JSON.stringify(formData))
  }, [formData])

  useEffect(() => {
    sessionStorage.setItem('booking_customerId', JSON.stringify(customerId))
  }, [customerId])

  useEffect(() => {
    sessionStorage.setItem('booking_savedEmail', JSON.stringify(savedEmail))
  }, [savedEmail])

  useEffect(() => {
    sessionStorage.setItem('booking_vehicleId', JSON.stringify(vehicleId))
  }, [vehicleId])

  useEffect(() => {
    sessionStorage.setItem('booking_promoCode', JSON.stringify(promoCode))
    sessionStorage.setItem('booking_promoCodeValid', JSON.stringify(promoCodeValid))
    sessionStorage.setItem('booking_promoCodeMessage', JSON.stringify(promoCodeMessage))
    sessionStorage.setItem('booking_promoCodeDiscount', JSON.stringify(promoCodeDiscount))
  }, [promoCode, promoCodeValid, promoCodeMessage, promoCodeDiscount])

  useEffect(() => {
    sessionStorage.setItem('booking_dvlaVerified', JSON.stringify(dvlaVerified))
  }, [dvlaVerified])

  useEffect(() => {
    sessionStorage.setItem('booking_departureTimeOverride', JSON.stringify(departureTimeOverride))
    sessionStorage.setItem('booking_showDepartureTimeOverride', JSON.stringify(showDepartureTimeOverride))
  }, [departureTimeOverride, showDepartureTimeOverride])

  useEffect(() => {
    sessionStorage.setItem('booking_arrivalTimeOverride', JSON.stringify(arrivalTimeOverride))
    sessionStorage.setItem('booking_showArrivalTimeOverride', JSON.stringify(showArrivalTimeOverride))
  }, [arrivalTimeOverride, showArrivalTimeOverride])

  useEffect(() => {
    console.log('[useEffect] Saving manualDepartureData to sessionStorage:', manualDepartureData)
    sessionStorage.setItem('booking_manualDepartureData', JSON.stringify(manualDepartureData))
  }, [manualDepartureData])

  useEffect(() => {
    console.log('[useEffect] Saving manualArrivalData to sessionStorage:', manualArrivalData)
    sessionStorage.setItem('booking_manualArrivalData', JSON.stringify(manualArrivalData))
  }, [manualArrivalData])

  // Persist heard-about-us state
  useEffect(() => {
    sessionStorage.setItem('booking_heardAboutUsSource', JSON.stringify(heardAboutUsSource))
    sessionStorage.setItem('booking_heardAboutUsDetail', JSON.stringify(heardAboutUsDetail))
    sessionStorage.setItem('booking_heardAboutUsAnswered', JSON.stringify(heardAboutUsAnswered))
  }, [heardAboutUsSource, heardAboutUsDetail, heardAboutUsAnswered])

  // Check heard-about-us status when customer ID is available and entering Step 4
  useEffect(() => {
    const checkHeardAboutUsStatus = async () => {
      if (!customerId || currentStep !== 4 || heardAboutUsAnswered) return

      setHeardAboutUsLoading(true)
      try {
        const response = await fetch(`${API_BASE_URL}/api/customers/heard-about-us-status?email=${encodeURIComponent(formData.email)}`)
        if (response.ok) {
          const data = await response.json()
          if (data.has_answered_heard_about_us) {
            // Already answered, skip the question
            setHeardAboutUsAnswered(true)
          }
        }
      } catch (error) {
        console.error('Error checking heard-about-us status:', error)
      } finally {
        setHeardAboutUsLoading(false)
      }
    }

    checkHeardAboutUsStatus()
  }, [customerId, currentStep, heardAboutUsAnswered, formData.email, API_BASE_URL])

  // Submit heard-about-us answer
  const submitHeardAboutUs = async () => {
    if (!heardAboutUsSource || heardAboutUsSubmitting) return

    // Validate "other" selection has detail
    if (heardAboutUsSource === 'other' && !heardAboutUsDetail.trim()) {
      return
    }

    setHeardAboutUsSubmitting(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/customers/heard-about-us`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: formData.email,
          source: heardAboutUsSource,
          source_detail: heardAboutUsSource === 'other' ? heardAboutUsDetail.trim() : null
        })
      })

      if (response.ok) {
        setHeardAboutUsAnswered(true)
      } else {
        console.error('Failed to submit heard-about-us:', await response.text())
      }
    } catch (error) {
      console.error('Error submitting heard-about-us:', error)
    } finally {
      setHeardAboutUsSubmitting(false)
    }
  }

  // Check availability for a date range
  const checkAvailability = (dropoffDate, pickupDate) => {
    // In production, this would fetch from your database
    // Returns true if spots are available for the entire date range
    if (!dropoffDate || !pickupDate) return true

    let currentDate = new Date(dropoffDate)
    const endDate = new Date(pickupDate)

    while (currentDate <= endDate) {
      const dateStr = format(currentDate, 'yyyy-MM-dd')
      const spotsBooked = bookedSpots[dateStr] || 0
      if (spotsBooked >= MAX_PARKING_SPOTS) {
        return false
      }
      currentDate.setDate(currentDate.getDate() + 1)
    }
    return true
  }

  const isCapacityAvailable = checkAvailability(formData.dropoffDate, formData.pickupDate)

  // Get car makes and models from car-info library
  const carMakes = useMemo(() => getMakes().sort(), [])
  const carModels = useMemo(() => {
    if (!formData.make) return []
    return getModels(formData.make) || []
  }, [formData.make])

  // Fetch available airlines and destinations for manual entry
  useEffect(() => {
    const fetchAirlinesAndDestinations = async () => {
      try {
        const [airlinesRes, destinationsRes] = await Promise.all([
          fetch(`${API_BASE_URL}/api/booking/airlines`),
          fetch(`${API_BASE_URL}/api/booking/destinations`)
        ])
        if (airlinesRes.ok) {
          const data = await airlinesRes.json()
          setAvailableAirlines(data.airlines || [])
        }
        if (destinationsRes.ok) {
          const data = await destinationsRes.json()
          setAvailableDestinations(data.destinations || [])
        }
      } catch (error) {
        console.error('Error fetching airlines/destinations:', error)
      }
    }
    fetchAirlinesAndDestinations()
  }, [API_BASE_URL])

  // Fetch departures when drop-off date changes
  useEffect(() => {
    const fetchDepartures = async () => {
      if (!formData.dropoffDate) {
        setDeparturesForDate([])
        setDeparturesLoaded(false)
        return
      }
      setLoadingFlights(true)
      setDeparturesLoaded(false)
      try {
        const dateStr = format(formData.dropoffDate, 'yyyy-MM-dd')
        const response = await fetch(`${API_BASE_URL}/api/flights/departures/${dateStr}`)
        const data = await response.json()
        setDeparturesForDate(data)
      } catch (error) {
        console.error('Error fetching departures:', error)
        setDeparturesForDate([])
      } finally {
        setLoadingFlights(false)
        setDeparturesLoaded(true)
      }
    }
    fetchDepartures()
  }, [formData.dropoffDate, API_BASE_URL])

  // Get unique airlines for selected date (normalized - Ryanair UK merged into Ryanair)
  const airlinesForDropoff = useMemo(() => {
    const airlines = [...new Set(departuresForDate.map(f => normalizeAirlineName(f.airlineName)))]
    return airlines.sort()
  }, [departuresForDate])

  // Filter flights by selected airline (matches normalized name)
  const flightsForAirline = useMemo(() => {
    if (!formData.dropoffAirline) return []
    return departuresForDate.filter(f => normalizeAirlineName(f.airlineName) === formData.dropoffAirline)
  }, [departuresForDate, formData.dropoffAirline])

  // Get flights with time and destination combined for selected airline
  const flightsForDropoff = useMemo(() => {
    return flightsForAirline.map(f => {
      // Parse destinationName to extract city and country code (e.g., "Faro, PT" or "Edinburgh, SC, GB")
      const parts = f.destinationName.split(', ')
      let displayDestination = f.destinationName
      if (parts.length > 1) {
        const countryCode = parts[parts.length - 1]
        let cityName = parts.slice(0, -1).join(', ')
        // Shorten Tenerife-Reinasofia to Tenerife
        if (cityName === 'Tenerife-Reinasofia') cityName = 'Tenerife'
        const countryName = countryNames[countryCode] || countryCode
        displayDestination = `${cityName}, ${countryName}`
      }

      const flightKey = `${f.time}|${f.destinationCode}`

      // Use overridden time for the currently selected flight
      const isSelected = formData.dropoffFlight === flightKey
      const displayTime = (isSelected && departureTimeOverride) ? departureTimeOverride : f.time

      return {
        ...f,
        flightKey,
        displayText: `${displayTime} ${f.airlineCode}${f.flightNumber} → ${displayDestination}`
      }
    }).sort((a, b) => a.time.localeCompare(b.time))
  }, [flightsForAirline, departureTimeOverride, formData.dropoffFlight])

  // Get selected flight details
  const selectedDropoffFlight = useMemo(() => {
    if (!formData.dropoffFlight) return null
    return flightsForDropoff.find(f => f.flightKey === formData.dropoffFlight)
  }, [flightsForDropoff, formData.dropoffFlight])

  // Check if flight is "Call Us only" (capacity_tier = 0)
  const isCallUsOnly = useMemo(() => {
    if (!selectedDropoffFlight) return false
    return selectedDropoffFlight.is_call_us_only || selectedDropoffFlight.capacity_tier === 0
  }, [selectedDropoffFlight])

  // Calculate drop-off time slots (2¾h, 2h before departure)
  // Shows slots based on capacity tier and remaining availability
  const dropoffSlots = useMemo(() => {
    if (!selectedDropoffFlight) return []

    // If this is a "Call Us only" flight, no slots available
    if (isCallUsOnly) return []

    // Use overridden departure time if set, otherwise use scheduled time
    const flightTime = departureTimeOverride || selectedDropoffFlight.time
    const [hours, minutes] = flightTime.split(':').map(Number)
    const departureMinutes = hours * 60 + minutes

    // Check if this is a same-day booking and enforce 4-hour minimum notice
    const isToday = formData.dropoffDate &&
      format(formData.dropoffDate, 'yyyy-MM-dd') === format(getTodayUK(), 'yyyy-MM-dd')
    const currentUKMinutes = isToday ? getCurrentUKTimeMinutes() : 0
    const minNoticeMinutes = MIN_HOURS_NOTICE * 60 // 4 hours = 240 minutes

    const slots = []

    // Early slot: 2¾ hours before (165 minutes) - show if slots available
    const earlyAvailable = selectedDropoffFlight.early_slots_available ??
      (selectedDropoffFlight.is_slot_1_booked === false ? 1 : 0)
    const earlySlotMinutes = departureMinutes - 165
    // For same-day: only show if slot time is at least 4 hours from now
    const earlySlotAllowed = !isToday || (earlySlotMinutes >= currentUKMinutes + minNoticeMinutes)
    if (earlyAvailable > 0 && earlySlotAllowed) {
      slots.push({
        id: '165',
        label: '2¾ hours before',
        time: formatMinutesToTime(earlySlotMinutes),
        available: earlyAvailable,
        isLastSlot: selectedDropoffFlight.early_is_last_slot || selectedDropoffFlight.is_last_slot
      })
    }

    // Late slot: 2 hours before (120 minutes) - show if slots available
    const lateAvailable = selectedDropoffFlight.late_slots_available ??
      (selectedDropoffFlight.is_slot_2_booked === false ? 1 : 0)
    const lateSlotMinutes = departureMinutes - 120
    // For same-day: only show if slot time is at least 4 hours from now
    const lateSlotAllowed = !isToday || (lateSlotMinutes >= currentUKMinutes + minNoticeMinutes)
    if (lateAvailable > 0 && lateSlotAllowed) {
      slots.push({
        id: '120',
        label: '2 hours before',
        time: formatMinutesToTime(lateSlotMinutes),
        available: lateAvailable,
        isLastSlot: selectedDropoffFlight.late_is_last_slot || selectedDropoffFlight.is_last_slot
      })
    }

    return slots
  }, [selectedDropoffFlight, isCallUsOnly, departureTimeOverride, formData.dropoffDate])

  // Check if flight is fully booked (all slots taken) or Call Us only
  const isFlightFullyBooked = useMemo(() => {
    if (!selectedDropoffFlight) return false
    // New capacity-based check
    if (selectedDropoffFlight.all_slots_booked !== undefined) {
      return selectedDropoffFlight.all_slots_booked
    }
    // Fallback for old data format
    return selectedDropoffFlight.is_slot_1_booked && selectedDropoffFlight.is_slot_2_booked
  }, [selectedDropoffFlight])

  // Fetch arrivals when pick-up date changes
  useEffect(() => {
    const fetchArrivals = async () => {
      if (!formData.pickupDate) {
        setArrivalsForDate([])
        setArrivalsLoaded(false)
        return
      }
      setArrivalsLoaded(false)
      try {
        const dateStr = format(formData.pickupDate, 'yyyy-MM-dd')
        const response = await fetch(`${API_BASE_URL}/api/flights/arrivals/${dateStr}`)
        const data = await response.json()
        setArrivalsForDate(data)
      } catch (error) {
        console.error('Error fetching arrivals:', error)
        setArrivalsForDate([])
      } finally {
        setArrivalsLoaded(true)
      }
    }
    fetchArrivals()
  }, [formData.pickupDate, API_BASE_URL])

  // Fetch dynamic pricing when dates change
  useEffect(() => {
    const fetchPricing = async () => {
      if (!formData.dropoffDate || !formData.pickupDate) {
        setPricingInfo(null)
        return
      }

      setPricingLoading(true)
      try {
        const dropoffStr = format(formData.dropoffDate, 'yyyy-MM-dd')
        const pickupStr = format(formData.pickupDate, 'yyyy-MM-dd')

        const response = await fetch(`${API_BASE_URL}/api/pricing/calculate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            drop_off_date: dropoffStr,
            pickup_date: pickupStr,
          }),
        })

        if (response.ok) {
          const data = await response.json()
          setPricingInfo(data)
          // Auto-set the package based on duration
          setFormData(prev => ({
            ...prev,
            package: data.package, // "quick" or "longer"
          }))
        } else {
          setPricingInfo(null)
        }
      } catch (error) {
        console.error('Error fetching pricing:', error)
        setPricingInfo(null)
      } finally {
        setPricingLoading(false)
      }
    }
    fetchPricing()
  }, [formData.dropoffDate, formData.pickupDate, API_BASE_URL])

  // Auto-select return origin based on departure destination
  useEffect(() => {
    if (manualDepartureData.destinationCode && !manualArrivalData.originCode) {
      if (manualDepartureData.destinationCode === 'Other') {
        // Custom destination - sync origin as "Other" too
        setManualArrivalData(prev => ({
          ...prev,
          originCode: 'Other',
          originName: manualDepartureData.customDestination || '',
          customOrigin: manualDepartureData.customDestination || ''
        }))
      } else {
        const dest = availableDestinations.find(d => d.code === manualDepartureData.destinationCode)
        if (dest) {
          setManualArrivalData(prev => ({
            ...prev,
            originCode: manualDepartureData.destinationCode,
            originName: dest.name,
            customOrigin: ''
          }))
        }
      }
    }
  }, [manualDepartureData.destinationCode, manualDepartureData.customDestination, availableDestinations])

  // Filter arrivals by airline and destination, then find the best matching return flight
  const filteredArrivalsForDate = useMemo(() => {
    // For normal departures, use selectedDropoffFlight
    // For manual departures, use manualDepartureData
    const airlineName = showManualDeparture ? manualDepartureData.airlineName : formData.dropoffAirline
    const destinationCode = showManualDeparture ? manualDepartureData.destinationCode : selectedDropoffFlight?.destinationCode

    if (!airlineName || !destinationCode) return []

    // Filter by same airline (normalized) and origin matching the departure destination
    const matchingFlights = arrivalsForDate.filter(f =>
      normalizeAirlineName(f.airlineName) === normalizeAirlineName(airlineName) &&
      f.originCode === destinationCode
    )

    // Return all matching flights (same airline, same origin)
    return matchingFlights
  }, [arrivalsForDate, formData.dropoffAirline, selectedDropoffFlight, showManualDeparture, manualDepartureData.airlineName, manualDepartureData.destinationCode])

  // Get arrival flights for pickup with display details (filtered by airline and destination)
  const arrivalFlightsForPickup = useMemo(() => {
    return filteredArrivalsForDate.map(f => {
      // Parse originName to get city
      const parts = f.originName.split(', ')
      let displayOrigin = f.originName
      if (parts.length > 1) {
        let cityName = parts.slice(0, -1).join(', ')
        // Shorten Tenerife-Reinasofia to Tenerife
        if (cityName === 'Tenerife-Reinasofia') cityName = 'Tenerife'
        displayOrigin = cityName
      }

      // Check if overnight flight (departs evening, arrives early morning)
      const isOvernight = f.departureTime &&
        parseInt(f.departureTime.split(':')[0]) >= 18 &&
        parseInt(f.time.split(':')[0]) < 6

      const flightKey = `${f.time}|${f.flightNumber}`

      // Use overridden time for the currently selected flight
      const isSelected = formData.pickupFlightTime === flightKey
      const displayTime = (isSelected && arrivalTimeOverride) ? arrivalTimeOverride : f.time

      return {
        ...f,
        flightKey,
        isOvernight,
        displayText: `${f.airlineCode}${f.flightNumber} from ${displayOrigin} → arrives ${displayTime}${isOvernight ? ' +1' : ''}`
      }
    }).sort((a, b) => a.time.localeCompare(b.time))
  }, [filteredArrivalsForDate, arrivalTimeOverride, formData.pickupFlightTime])

  // Clear pickupFlightTime when arrival flights change and current selection is invalid
  // Guard: wait until both departures and arrivals have loaded to avoid race condition
  // on page refresh where sessionStorage restores pickupFlightTime but flight data hasn't loaded yet
  useEffect(() => {
    if (!departuresLoaded || !arrivalsLoaded) return
    if (formData.pickupFlightTime && arrivalFlightsForPickup.length === 0) {
      // No valid return flights - clear the selection
      setFormData(prev => ({ ...prev, pickupFlightTime: '' }))
    } else if (formData.pickupFlightTime && arrivalFlightsForPickup.length > 0) {
      // Check if current selection is still valid
      const isValid = arrivalFlightsForPickup.some(f => f.flightKey === formData.pickupFlightTime)
      if (!isValid) {
        setFormData(prev => ({ ...prev, pickupFlightTime: '' }))
      }
    }
  }, [arrivalFlightsForPickup, formData.pickupFlightTime, departuresLoaded, arrivalsLoaded])

  // Get selected arrival/return flight details
  const selectedArrivalFlight = useMemo(() => {
    if (!formData.pickupFlightTime) return null
    return arrivalFlightsForPickup.find(f => f.flightKey === formData.pickupFlightTime)
  }, [arrivalFlightsForPickup, formData.pickupFlightTime])

  // Calculate actual pickup date (add 1 day for overnight flights)
  const actualPickupDate = useMemo(() => {
    if (!formData.pickupDate) return null
    if (selectedArrivalFlight?.isOvernight) {
      const nextDay = new Date(formData.pickupDate)
      nextDay.setDate(nextDay.getDate() + 1)
      return nextDay
    }
    return formData.pickupDate
  }, [formData.pickupDate, selectedArrivalFlight])

  // Helper function to format minutes to HH:MM
  function formatMinutesToTime(totalMinutes) {
    if (totalMinutes < 0) totalMinutes += 24 * 60 // Handle overnight
    const hours = Math.floor(totalMinutes / 60) % 24
    const mins = totalMinutes % 60
    return `${hours.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}`
  }

  // Validate time format helper (24-hour clock with valid hours 00-23 and minutes 00-59)
  const isValidTimeFormat = (timeStr) => {
    if (!timeStr) return false
    const match = timeStr.match(/^(\d{1,2}):(\d{2})$/)
    if (!match) return false
    const hours = parseInt(match[1], 10)
    const minutes = parseInt(match[2], 10)
    return hours >= 0 && hours <= 23 && minutes >= 0 && minutes <= 59
  }

  // Format time input - auto-insert colon, validate 24-hour format
  const formatTimeInput = (value) => {
    // Remove any non-digits
    const digits = value.replace(/\D/g, '')

    // Limit to 4 digits
    const limited = digits.slice(0, 4)

    if (limited.length <= 2) {
      // Just hours or partial hours
      return limited
    } else {
      // Insert colon after first 2 digits
      const hours = limited.slice(0, 2)
      const minutes = limited.slice(2)

      // Validate hours (00-23)
      const hoursNum = parseInt(hours, 10)
      if (hoursNum > 23) {
        return '23:' + minutes
      }

      // Validate minutes (00-59)
      if (minutes.length === 2) {
        const minsNum = parseInt(minutes, 10)
        if (minsNum > 59) {
          return hours + ':59'
        }
      }

      return hours + ':' + minutes
    }
  }

  // Calculate drop-off slots for manual departure entries
  const manualDropoffSlots = useMemo(() => {
    if (!showManualDeparture) return []
    if (!isValidTimeFormat(manualDepartureData.flightTime)) return []

    const [hours, minutes] = manualDepartureData.flightTime.split(':').map(Number)
    const departureMinutes = hours * 60 + minutes

    // Check if this is a same-day booking and enforce 4-hour minimum notice
    const isToday = formData.dropoffDate &&
      format(formData.dropoffDate, 'yyyy-MM-dd') === format(getTodayUK(), 'yyyy-MM-dd')
    const currentUKMinutes = isToday ? getCurrentUKTimeMinutes() : 0
    const minNoticeMinutes = MIN_HOURS_NOTICE * 60 // 4 hours = 240 minutes

    const slots = []

    const earlySlotMinutes = departureMinutes - 165
    if (!isToday || (earlySlotMinutes >= currentUKMinutes + minNoticeMinutes)) {
      slots.push({
        id: '165',
        label: '2¾ hours before',
        time: formatMinutesToTime(earlySlotMinutes)
      })
    }

    const lateSlotMinutes = departureMinutes - 120
    if (!isToday || (lateSlotMinutes >= currentUKMinutes + minNoticeMinutes)) {
      slots.push({
        id: '120',
        label: '2 hours before',
        time: formatMinutesToTime(lateSlotMinutes)
      })
    }

    return slots
  }, [showManualDeparture, manualDepartureData.flightTime, formData.dropoffDate])

  // Normalize time to HH:MM format
  const normalizeTime = (timeStr) => {
    if (!timeStr) return ''
    const parts = timeStr.split(':')
    if (parts.length !== 2) return timeStr
    const hours = parts[0].padStart(2, '0')
    const mins = parts[1].padStart(2, '0')
    return `${hours}:${mins}`
  }

  // Validate flight time via API
  const validateFlightTime = async (timeStr, flightType) => {
    if (!isValidTimeFormat(timeStr)) {
      return { valid: false, error: 'Please enter time in HH:MM format (e.g., 14:30)' }
    }
    try {
      const response = await fetch(`${API_BASE_URL}/api/booking/validate-flight-time`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          time: normalizeTime(timeStr),
          flight_type: flightType
        })
      })
      const data = await response.json()
      return { valid: data.valid, error: data.error, normalizedTime: data.normalized_time }
    } catch (error) {
      console.error('Time validation error:', error)
      return { valid: false, error: 'Unable to validate time. Please try again.' }
    }
  }

  // Handle departure time override submission
  const handleDepartureTimeOverride = async () => {
    setDepartureTimeValidating(true)
    setDepartureTimeError('')
    const result = await validateFlightTime(departureTimeOverride, 'departure')
    setDepartureTimeValidating(false)
    if (!result.valid) {
      setDepartureTimeError(result.error)
    } else {
      // Update the selected flight time - keep original time for reference
      setShowDepartureTimeOverride(false)
    }
  }

  // Handle arrival time override submission
  const handleArrivalTimeOverride = async () => {
    setArrivalTimeValidating(true)
    setArrivalTimeError('')
    const result = await validateFlightTime(arrivalTimeOverride, 'arrival')
    setArrivalTimeValidating(false)
    if (!result.valid) {
      setArrivalTimeError(result.error)
    } else {
      setShowArrivalTimeOverride(false)
    }
  }

  // Convert string to Title Case
  const toTitleCase = (str) => {
    if (!str) return str
    return str.toLowerCase().replace(/\b\w/g, char => char.toUpperCase())
  }

  // Fields that should be title case
  const titleCaseFields = ['colour', 'customMake', 'customModel', 'billingAddress1', 'billingAddress2', 'billingCity', 'billingCounty']

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target
    const processedValue = titleCaseFields.includes(name) ? toTitleCase(value) : value
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : processedValue
    }))

    // Reset dependent fields when parent changes
    if (name === 'dropoffAirline') {
      setFormData(prev => ({
        ...prev,
        dropoffAirline: value,
        dropoffFlight: '',
        dropoffSlot: ''
      }))
    }

    if (name === 'dropoffFlight') {
      setFormData(prev => ({
        ...prev,
        dropoffFlight: value,
        dropoffSlot: ''
      }))

      // Track when user selects a flight with 0 capacity
      if (value) {
        const selectedFlight = flightsForDropoff.find(f => f.flightKey === value)
        if (selectedFlight && (selectedFlight.capacity_tier === 0 || selectedFlight.is_call_us_only)) {
          console.log('Zero capacity flight selected:', {
            flight_number: `${selectedFlight.airlineCode}${selectedFlight.flightNumber}`,
            flight_date: formData.dropoffDate ? format(formData.dropoffDate, 'yyyy-MM-dd') : null,
            destination_airport: selectedFlight.destinationCode,
            departure_time: selectedFlight.time,
            gtag_available: !!window.gtag
          })
          if (window.gtag) {
            window.gtag('event', 'zero_capacity_flight_selected', {
              flight_number: `${selectedFlight.airlineCode}${selectedFlight.flightNumber}`,
              flight_date: formData.dropoffDate ? format(formData.dropoffDate, 'yyyy-MM-dd') : null,
              destination_airport: selectedFlight.destinationCode,
              departure_time: selectedFlight.time
            })
          }
        }
      }
    }


    // Reset model when make changes
    if (name === 'make') {
      setFormData(prev => ({
        ...prev,
        make: value,
        model: '',
        customMake: '',
        customModel: ''
      }))
    }

    // Reset custom model when model changes
    if (name === 'model') {
      setFormData(prev => ({
        ...prev,
        model: value,
        customModel: ''
      }))
    }
  }

  const handleDateChange = (date, field) => {
    if (field === 'dropoffDate') {
      setFormData(prev => ({
        ...prev,
        dropoffDate: date,
        dropoffAirline: '',
        dropoffFlight: '',
        dropoffSlot: ''
      }))
    } else if (field === 'pickupDate') {
      setFormData(prev => ({
        ...prev,
        pickupDate: date,
        pickupFlightTime: ''
      }))
    } else {
      setFormData(prev => ({
        ...prev,
        [field]: date
      }))
    }
  }

  // API functions for incremental saves
  const saveCustomer = async () => {
    // Check if email changed - if so, create new customer (different person)
    const emailChanged = savedEmail && formData.email.toLowerCase() !== savedEmail.toLowerCase()

    // If customer already exists and email hasn't changed, update instead of create
    if (customerId && !emailChanged) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/customers/${customerId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            first_name: formData.firstName,
            last_name: formData.lastName,
            email: formData.email,
            phone: formData.phone,
            session_id: sessionIdRef.current,
          }),
        })
        const data = await response.json()
        console.log('Customer updated:', customerId)
        setSavedEmail(formData.email)
        return { customerId: data.success ? customerId : null, isNewCustomer: false }
      } catch (error) {
        console.error('Error updating customer:', error)
        return { customerId: null, isNewCustomer: false }
      }
    }

    // Email changed - reset vehicle since it's linked to old customer
    if (emailChanged) {
      console.log('Email changed, creating new customer and resetting vehicle')
      setVehicleId(null)
    }

    // Create new customer
    try {
      const response = await fetch(`${API_BASE_URL}/api/customers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          first_name: formData.firstName,
          last_name: formData.lastName,
          email: formData.email,
          phone: formData.phone,
          session_id: sessionIdRef.current,
        }),
      })
      const data = await response.json()
      if (data.success) {
        setCustomerId(data.customer_id)
        setSavedEmail(formData.email)
        console.log('Customer created:', data.customer_id)
        return { customerId: data.customer_id, isNewCustomer: true }
      }
      return { customerId: null, isNewCustomer: false }
    } catch (error) {
      console.error('Error saving customer:', error)
      return { customerId: null, isNewCustomer: false }
    }
  }

  const saveVehicle = async (custId, forceCreate = false) => {
    const customerIdToUse = custId || customerId
    if (!customerIdToUse) return false

    // If vehicle already exists and not forcing create, update instead of create
    if (vehicleId && !forceCreate) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/vehicles/${vehicleId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            customer_id: customerIdToUse,
            registration: formData.registration.toUpperCase(),
            make: formData.make === 'Other' ? formData.customMake : formData.make,
            model: formData.model === 'Other' ? formData.customModel : formData.model,
            colour: formData.colour,
            session_id: sessionIdRef.current,
          }),
        })
        const data = await response.json()
        console.log('Vehicle updated:', vehicleId)
        return data.success
      } catch (error) {
        console.error('Error updating vehicle:', error)
        return false
      }
    }

    // Create new vehicle
    try {
      const response = await fetch(`${API_BASE_URL}/api/vehicles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_id: customerIdToUse,
          registration: formData.registration.toUpperCase(),
          make: formData.make === 'Other' ? formData.customMake : formData.make,
          model: formData.model === 'Other' ? formData.customModel : formData.model,
          colour: formData.colour,
          session_id: sessionIdRef.current,
        }),
      })
      const data = await response.json()
      if (data.success) {
        setVehicleId(data.vehicle_id)
        console.log('Vehicle created:', data.vehicle_id)
      }
      return data.success
    } catch (error) {
      console.error('Error saving vehicle:', error)
      return false
    }
  }

  const saveBillingAddress = async (custId) => {
    const customerIdToUse = custId || customerId
    if (!customerIdToUse) return false
    try {
      const response = await fetch(`${API_BASE_URL}/api/customers/${customerIdToUse}/billing`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          billing_address1: formData.billingAddress1,
          billing_address2: formData.billingAddress2,
          billing_city: formData.billingCity,
          billing_county: formData.billingCounty,
          billing_postcode: formData.billingPostcode.toUpperCase(),
          billing_country: formData.billingCountry,
          session_id: sessionIdRef.current,
        }),
      })
      const data = await response.json()
      console.log('Billing address saved:', data.success)
      return data.success
    } catch (error) {
      console.error('Error saving billing address:', error)
      return false
    }
  }

  // DVLA vehicle lookup function
  const lookupVehicle = async () => {
    if (!formData.registration || formData.registration.length < 2) {
      setDvlaError('Please enter a valid registration number')
      return
    }

    setDvlaLoading(true)
    setDvlaError('')
    setDvlaVerified(false)

    try {
      const response = await fetch(`${API_BASE_URL}/api/vehicles/dvla-lookup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ registration: formData.registration }),
      })

      const data = await response.json()

      if (data.success && data.make) {
        // Capitalize make properly (API returns uppercase)
        const formattedMake = data.make.charAt(0).toUpperCase() + data.make.slice(1).toLowerCase()
        // Capitalize colour properly
        const formattedColour = data.colour ?
          data.colour.charAt(0).toUpperCase() + data.colour.slice(1).toLowerCase() : ''

        // Check if make exists in car-info library
        const makeExists = carMakes.some(m => m.toUpperCase() === data.make.toUpperCase())

        setFormData(prev => ({
          ...prev,
          make: makeExists ? formattedMake : 'Other',
          customMake: makeExists ? '' : formattedMake,
          colour: formattedColour,
          model: '', // Reset model so user can select
          customModel: '',
        }))
        setDvlaVerified(true)
        setDvlaError('')
      } else {
        setDvlaError(data.error || 'Vehicle not found. Please enter details manually.')
        setDvlaVerified(false)
      }
    } catch (error) {
      console.error('DVLA lookup error:', error)
      setDvlaError('Unable to verify vehicle. Please enter details manually.')
      setDvlaVerified(false)
    } finally {
      setDvlaLoading(false)
    }
  }

  // Address lookup using OS Places API
  const lookupAddress = async () => {
    const postcode = formData.billingPostcode.trim()
    if (!postcode) {
      setAddressError('Please enter a postcode')
      return
    }

    setAddressLoading(true)
    setAddressError('')
    setAddressList([])
    setShowAddressSelect(false)

    try {
      const response = await fetch(`${API_BASE_URL}/api/address/postcode-lookup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ postcode })
      })

      const data = await response.json()

      if (data.success && data.addresses.length > 0) {
        setAddressList(data.addresses)
        setShowAddressSelect(true)
        setPostcodeSearched(data.postcode)
        setAddressError('')
      } else if (data.success && data.addresses.length === 0) {
        setAddressError('No addresses found for this postcode')
      } else {
        setAddressError(data.error || 'Unable to find addresses')
      }
    } catch (error) {
      console.error('Address lookup error:', error)
      setAddressError('Unable to lookup address. Please enter manually.')
    } finally {
      setAddressLoading(false)
    }
  }

  // Handle address selection from dropdown
  const handleAddressSelect = (e) => {
    const selectedUprn = e.target.value
    if (!selectedUprn) return

    const selectedAddress = addressList.find(addr => addr.uprn === selectedUprn)
    if (selectedAddress) {
      let address1 = ''
      let address2 = ''

      // Parse address from the full address string
      // Examples:
      // "84 High Street, Sturminster Marshall, Wimborne, BH21 4AY" -> Line1: "84 High Street", Line2: "Sturminster Marshall"
      // "1 Ascham Lodge, 11 Ascham Road, Bournemouth, BH8 8LY" -> Line1: "1 Ascham Lodge, 11 Ascham Road", Line2: ""
      const fullAddress = selectedAddress.address
      const postTown = selectedAddress.post_town
      const dependentLocality = selectedAddress.dependent_locality
      const postcode = selectedAddress.postcode

      // Remove postcode and post_town from the end to get the street portion
      let streetPortion = fullAddress
        .replace(new RegExp(`,?\\s*${postcode}\\s*$`, 'i'), '')
        .replace(new RegExp(`,?\\s*${postTown}\\s*$`, 'i'), '')
        .trim()

      // If dependent_locality exists, it goes in address2
      if (dependentLocality) {
        // Remove dependent_locality from street portion for address1
        address1 = streetPortion
          .replace(new RegExp(`,?\\s*${dependentLocality}\\s*$`, 'i'), '')
          .trim()
        address2 = dependentLocality
      } else {
        address1 = streetPortion
        address2 = ''
      }

      // Clean up any trailing commas
      address1 = address1.replace(/,\s*$/, '').trim()

      setFormData(prev => ({
        ...prev,
        billingAddress1: toTitleCase(address1),
        billingAddress2: toTitleCase(address2),
        billingCity: toTitleCase(selectedAddress.post_town),
        billingPostcode: selectedAddress.postcode,
        billingCounty: selectedAddress.county || ''
      }))

      setShowAddressSelect(false)
    }
  }

  // Save Step 3 data (Contact/Billing/Vehicle) and advance to Payment
  const saveStep3DataAndAdvance = async () => {
    console.log('[Step 3 → 4] Advancing to payment')
    console.log('[Step 3 → 4] manualDepartureData:', manualDepartureData)
    console.log('[Step 3 → 4] manualArrivalData:', manualArrivalData)
    setSaving(true)
    try {
      const { customerId: custId, isNewCustomer } = await saveCustomer()
      if (custId) {
        await saveBillingAddress(custId)
        await saveVehicle(custId, isNewCustomer)
      }
      // Data saved, advance to payment step
      setCurrentStep(4)
      window.scrollTo(0, 0)
    } catch (error) {
      console.error('Error saving step 3 data:', error)
    } finally {
      setSaving(false)
    }
  }

  const nextStep = async () => {
    console.log(`[Step ${currentStep} → ${currentStep + 1}] Advancing`)
    console.log(`[Step ${currentStep} → ${currentStep + 1}] manualDepartureData:`, manualDepartureData)
    console.log(`[Step ${currentStep} → ${currentStep + 1}] manualArrivalData:`, manualArrivalData)
    setSaving(true)
    try {
      // Step 3 data is saved via saveStep3DataAndAdvance
      // Steps 1, 2 don't need saves (just flight/package selection)

      // Track booking flow progress in GA
      const stepNames = {
        1: 'continue_to_package_selection', // Trip → Package
        2: 'continue_to_details'            // Package → Details
      }
      if (window.gtag && stepNames[currentStep]) {
        window.gtag('event', stepNames[currentStep], {
          event_category: 'booking_flow',
          event_label: `Step ${currentStep} to ${currentStep + 1}`,
          step_number: currentStep
        })
      }

      setCurrentStep(prev => Math.min(prev + 1, 4))
      window.scrollTo(0, 0)
    } finally {
      setSaving(false)
    }
  }

  const prevStep = () => {
    setCurrentStep(prev => Math.max(prev - 1, 1))
    window.scrollTo(0, 0)
  }

  // Validation helpers
  const isPhoneValid = formData.phone && isValidPhoneNumber(formData.phone)
  const isEmailValid = formData.email && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)
  const isBillingComplete = formData.billingAddress1 && formData.billingCity && formData.billingPostcode && formData.billingCountry
  const isMakeComplete = formData.make && (formData.make !== 'Other' || formData.customMake)
  const isModelComplete = formData.make === 'Other' ? formData.customModel : (formData.model && (formData.model !== 'Other' || formData.customModel))

  // Step 3: Contact + Billing + Vehicle Information (Details page)
  const isStep3Complete = formData.firstName && formData.lastName && isEmailValid && isPhoneValid && isBillingComplete && formData.registration && isMakeComplete && isModelComplete && formData.colour

  // Step 2: Trip Details - Direct entry validation
  const isDepartureAirlineComplete = manualDepartureData.airlineCode &&
    (manualDepartureData.airlineCode !== 'Other' ||
      (manualDepartureData.customAirline && !containsProfanity(manualDepartureData.customAirline)))

  const isDestinationComplete = manualDepartureData.destinationCode &&
    (manualDepartureData.destinationCode !== 'Other' ||
      (manualDepartureData.customDestination && !containsProfanity(manualDepartureData.customDestination)))

  const isArrivalAirlineComplete = manualArrivalData.airlineCode &&
    (manualArrivalData.airlineCode !== 'Other' ||
      (manualArrivalData.customAirline && !containsProfanity(manualArrivalData.customAirline)))

  const isOriginComplete = manualArrivalData.originCode &&
    (manualArrivalData.originCode !== 'Other' ||
      (manualArrivalData.customOrigin && !containsProfanity(manualArrivalData.customOrigin)))

  const isDepartureComplete =
    isDepartureAirlineComplete &&
    isValidTimeFormat(manualDepartureData.flightTime) &&
    isDestinationComplete &&
    manualDepartureData.dropoffSlot

  const isArrivalComplete =
    isArrivalAirlineComplete &&
    isValidTimeFormat(manualArrivalData.flightTime) &&
    isOriginComplete

  // Step 1: Trip Details
  const isStep1Complete = formData.dropoffDate && isDepartureComplete && formData.pickupDate && isArrivalComplete && isCapacityAvailable
  // Step 2: Package Selection
  const isStep2Complete = formData.package
  // Step 4: Payment
  const isStep4Complete = formData.terms

  // Scroll to first incomplete/invalid field for the current step
  const scrollToFirstError = (step) => {
    let fieldId = null
    let useNameSelector = false // For radio buttons that use name instead of id

    if (step === 1) {
      // Step 1 (Trip) validation order: dropoffDate, airline, customAirline, flightTime, destination, customDestination, dropoffSlot, pickupDate, arrivalAirline, arrivalFlightTime, origin
      if (!formData.dropoffDate) fieldId = 'dropoffDate'
      else if (!manualDepartureData.airlineCode) fieldId = 'manualAirline'
      else if (manualDepartureData.airlineCode === 'Other' && (!manualDepartureData.customAirline || containsProfanity(manualDepartureData.customAirline))) fieldId = 'customDepartureAirline'
      else if (!isValidTimeFormat(manualDepartureData.flightTime)) fieldId = 'manualFlightTime'
      else if (!manualDepartureData.destinationCode) fieldId = 'manualDestination'
      else if (manualDepartureData.destinationCode === 'Other' && (!manualDepartureData.customDestination || containsProfanity(manualDepartureData.customDestination))) fieldId = 'customDestination'
      else if (!manualDepartureData.dropoffSlot) { fieldId = 'manualDropoffSlot'; useNameSelector = true }
      else if (!formData.pickupDate) fieldId = 'pickupDate'
      else if (!manualArrivalData.airlineCode) fieldId = 'manualArrivalAirline'
      else if (manualArrivalData.airlineCode === 'Other' && (!manualArrivalData.customAirline || containsProfanity(manualArrivalData.customAirline))) fieldId = 'customArrivalAirline'
      else if (!isValidTimeFormat(manualArrivalData.flightTime)) fieldId = 'manualArrivalFlightTime'
      else if (!manualArrivalData.originCode) fieldId = 'manualArrivalOrigin'
      else if (manualArrivalData.originCode === 'Other' && (!manualArrivalData.customOrigin || containsProfanity(manualArrivalData.customOrigin))) fieldId = 'customOrigin'
    } else if (step === 3) {
      // Step 3 (Details) validation order: firstName, lastName, email, phone, billingAddress1, billingCity, billingPostcode, registration, make, model, colour
      if (!formData.firstName) fieldId = 'firstName'
      else if (!formData.lastName) fieldId = 'lastName'
      else if (!isEmailValid) fieldId = 'email'
      else if (!isPhoneValid) fieldId = 'phone'
      else if (!formData.billingAddress1) fieldId = 'billingAddress1'
      else if (!formData.billingCity) fieldId = 'billingCity'
      else if (!formData.billingPostcode) fieldId = manualAddressEntry ? 'billingPostcodeManual' : 'billingPostcode'
      else if (!formData.registration) fieldId = 'registration'
      else if (!isMakeComplete) fieldId = formData.make === 'Other' ? 'customMake' : 'make'
      else if (!isModelComplete) fieldId = formData.model === 'Other' || formData.make === 'Other' ? 'customModel' : 'model'
      else if (!formData.colour) fieldId = 'colour'
    }

    if (fieldId) {
      // For radio buttons, use name selector; otherwise use id
      const element = useNameSelector
        ? document.querySelector(`[name="${fieldId}"]`)
        : document.getElementById(fieldId)
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center' })
        // Focus the element after scroll animation
        setTimeout(() => element.focus(), 300)
        return true // Error found
      }
    }
    return false // No errors
  }

  // Handle Continue button click - scroll to first error if validation fails
  const handleContinueStep1 = () => {
    setStep1Attempted(true)
    if (!isStep1Complete) {
      scrollToFirstError(1)
      return
    }
    nextStep()
  }

  const handleContinueStep2 = () => {
    // Package step - just advance (package is auto-selected based on dates)
    nextStep()
  }

  const handleContinueStep3 = () => {
    setStep1Attempted(true) // Reuse step1Attempted for validation display
    if (!isStep3Complete) {
      scrollToFirstError(3)
      return
    }
    saveStep3DataAndAdvance()
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    // Form submission is now handled by the StripePayment component
    // This is just a fallback
    console.log('Booking data:', formData)
  }

  const handlePaymentSuccess = (paymentData) => {
    console.log('Payment successful:', paymentData)
    // Clear saved booking state - booking is complete
    Object.keys(sessionStorage).forEach(key => {
      if (key.startsWith('booking_')) sessionStorage.removeItem(key)
    })
    setPaymentComplete(true)
    setBookingConfirmation({
      reference: paymentData.bookingReference,
      amount: `£${(paymentData.amount / 100).toFixed(2)}`,
    })
  }

  const handlePaymentError = (error) => {
    console.error('Payment error:', error)
    // Error is handled within the StripePayment component
  }

  // Promo code validation
  const validatePromoCode = async () => {
    if (!promoCode.trim()) {
      setPromoCodeMessage('Please enter a promo code')
      setPromoCodeValid(false)
      return
    }

    setPromoCodeValidating(true)
    setPromoCodeMessage('')

    try {
      const response = await fetch(`${import.meta.env.VITE_API_URL}/api/promo/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: promoCode.trim() }),
      })

      const data = await response.json()

      if (data.valid) {
        setPromoCodeValid(true)
        setPromoCodeDiscount(data.discount_percent)
        setPromoCodeMessage(data.message)
      } else {
        setPromoCodeValid(false)
        setPromoCodeDiscount(0)
        setPromoCodeMessage(data.message)
      }
    } catch (err) {
      setPromoCodeValid(false)
      setPromoCodeDiscount(0)
      setPromoCodeMessage('Failed to validate promo code')
    } finally {
      setPromoCodeValidating(false)
    }
  }

  const clearPromoCode = () => {
    setPromoCode('')
    setPromoCodeValid(false)
    setPromoCodeMessage('')
    setPromoCodeDiscount(0)
  }

  const formatDisplayDate = (date) => {
    if (!date) return ''
    return format(date, 'dd/MM/yyyy')
  }

  return (
    <div className="bookings-new-page">
      {/* Welcome Modal - shown first when user lands on booking page */}
      {showWelcomeModal && (
        <div className="welcome-modal-overlay">
          <div className="welcome-modal">
            <div className="welcome-modal-icon">
              <img src="/assets/departure-icon.webp" alt="Departure" />
            </div>
            <h2>Booking's a breeze</h2>
            <p>
              We've made things simpler: tell us your flight details and we'll do the rest.
            </p>
            <p className="welcome-modal-options-intro">Here's how it works:</p>
            <ul className="welcome-modal-options">
              <li>Pick your airline and destination</li>
              <li>Enter your departure time and choose a drop-off slot</li>
              <li>Enter your return flight time so we're ready when you land</li>
            </ul>
            <p>
              And that's it! If you're unsure about anything, please get in touch.
            </p>
            <div className="welcome-modal-contact">
              <a href="mailto:sales@tagparking.co.uk" className="contact-link">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/>
                </svg>
                sales@tagparking.co.uk
              </a>
            </div>
            <div className="welcome-modal-actions">
              <button
                type="button"
                className="welcome-modal-btn"
                onClick={() => {
                  if (window.gtag) {
                    window.gtag('event', 'continue_to_booking', {
                      event_category: 'booking_flow',
                      event_label: 'welcome_modal'
                    })
                  }
                  setShowWelcomeModal(false)
                }}
              >
                Continue to booking
              </button>
              <button
                type="button"
                className="welcome-modal-back-btn"
                onClick={() => navigate('/')}
              >
                Back to home
              </button>
            </div>
          </div>
        </div>
      )}

      <nav className="bookings-new-nav">
        <Link to="/" className="logo">
          <img src="/assets/logo.svg" alt="TAG - Book it. Bag it. Tag it." className="logo-svg" />
        </Link>
      </nav>

      <div className="bookings-new-container">
        <h1>Book your parking</h1>
        <p className="bookings-new-subtitle">Bournemouth International Airport (BOH)</p>

        <div className="progress-bar">
          <div className="progress-steps">
            {[1, 2, 3, 4].map(step => (
              <div
                key={step}
                className={`progress-step ${currentStep >= step ? 'active' : ''} ${currentStep > step ? 'completed' : ''}`}
              >
                <span className="step-number">{step}</span>
                <span className="step-label">
                  {step === 1 && 'Trip'}
                  {step === 2 && 'Package'}
                  {step === 3 && 'Details'}
                  {step === 4 && 'Payment'}
                </span>
              </div>
            ))}
          </div>
        </div>

        <form className="bookings-new-form" onSubmit={handleSubmit}>
          {/* Step 3: Contact + Billing Information */}
          {currentStep === 3 && (
            <div className="form-section">
              <h2>Your Details</h2>

              <h3 className="section-subtitle">Contact Information</h3>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="firstName">First Name <span className="required">*</span></label>
                  <input
                    type="text"
                    id="firstName"
                    name="firstName"
                    placeholder="John"
                    value={formData.firstName}
                    onChange={handleChange}
                    className={step1Attempted && !formData.firstName ? 'input-error' : ''}
                    required
                  />
                  {step1Attempted && !formData.firstName && (
                    <span className="field-error">First name is required</span>
                  )}
                </div>
                <div className="form-group">
                  <label htmlFor="lastName">Last Name <span className="required">*</span></label>
                  <input
                    type="text"
                    id="lastName"
                    name="lastName"
                    placeholder="Smith"
                    value={formData.lastName}
                    onChange={handleChange}
                    className={step1Attempted && !formData.lastName ? 'input-error' : ''}
                    required
                  />
                  {step1Attempted && !formData.lastName && (
                    <span className="field-error">Last name is required</span>
                  )}
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="email">Email Address <span className="required">*</span></label>
                <input
                  type="email"
                  id="email"
                  name="email"
                  placeholder="john@example.com"
                  value={formData.email}
                  onChange={handleChange}
                  className={(formData.email && !isEmailValid) || (step1Attempted && !formData.email) ? 'input-error' : ''}
                  required
                />
                {formData.email && !isEmailValid && (
                  <span className="field-error">Please enter a valid email address</span>
                )}
                {step1Attempted && !formData.email && (
                  <span className="field-error">Email is required</span>
                )}
              </div>

              <div className="form-group">
                <label htmlFor="phone">Phone Number <span className="required">*</span></label>
                <PhoneInput
                  international
                  defaultCountry="GB"
                  id="phone"
                  value={formData.phone}
                  onChange={(value) => setFormData(prev => ({ ...prev, phone: value || '' }))}
                  className={`phone-input ${(formData.phone && !isPhoneValid) || (step1Attempted && !formData.phone) ? 'invalid' : ''}`}
                />
                {formData.phone && !isPhoneValid && (
                  <span className="field-error">Please enter a valid phone number</span>
                )}
                {step1Attempted && !formData.phone && (
                  <span className="field-error">Phone number is required</span>
                )}
              </div>

              <h3 className="section-subtitle">Billing Address</h3>
              <p className="section-info">This address will be used for payment verification.</p>

              {/* Postcode Lookup - show unless manual entry mode */}
              {!manualAddressEntry && (
                <>
                  <div className="form-group">
                    <label htmlFor="billingPostcode">Postcode <span className="required">*</span></label>
                    <div className="postcode-lookup-row">
                      <input
                        type="text"
                        id="billingPostcode"
                        name="billingPostcode"
                        placeholder="BH1 1AA"
                        value={formData.billingPostcode}
                        onChange={handleChange}
                        style={{ textTransform: 'uppercase' }}
                        required
                      />
                      <button
                        type="button"
                        className="find-address-btn"
                        onClick={lookupAddress}
                        disabled={addressLoading || !formData.billingPostcode.trim()}
                      >
                        {addressLoading ? 'Finding...' : 'Find Address'}
                      </button>
                    </div>
                    {addressError && (
                      <span className="error-text">
                        {addressError}
                        {' '}
                        <button
                          type="button"
                          className="manual-entry-link"
                          onClick={() => setManualAddressEntry(true)}
                        >
                          Enter address manually
                        </button>
                      </span>
                    )}
                  </div>

                  {/* Address Selection Dropdown */}
                  {showAddressSelect && addressList.length > 0 && (
                    <div className="form-group fade-in">
                      <label htmlFor="addressSelect">Select your address</label>
                      <select
                        id="addressSelect"
                        onChange={handleAddressSelect}
                        defaultValue=""
                        className="address-select"
                      >
                        <option value="">-- Select an address ({addressList.length} found) --</option>
                        {addressList.map((addr) => (
                          <option key={addr.uprn} value={addr.uprn}>
                            {addr.address}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        className="manual-entry-link"
                        onClick={() => setManualAddressEntry(true)}
                        style={{ marginTop: '0.5rem' }}
                      >
                        Can't find your address? Enter manually
                      </button>
                    </div>
                  )}
                </>
              )}

              {/* Manual Entry Mode Header */}
              {manualAddressEntry && (
                <div className="manual-entry-header">
                  <button
                    type="button"
                    className="back-to-lookup-link"
                    onClick={() => {
                      setManualAddressEntry(false)
                      setAddressError('')
                    }}
                  >
                    &larr; Back to postcode lookup
                  </button>
                </div>
              )}

              <div className="form-group">
                <label htmlFor="billingAddress1">Address Line 1 <span className="required">*</span></label>
                <input
                  type="text"
                  id="billingAddress1"
                  name="billingAddress1"
                  placeholder="123 High Street"
                  value={formData.billingAddress1}
                  onChange={handleChange}
                  className={step1Attempted && !formData.billingAddress1 ? 'input-error' : ''}
                  required
                />
                {step1Attempted && !formData.billingAddress1 && (
                  <span className="field-error">Address is required</span>
                )}
              </div>

              <div className="form-group">
                <label htmlFor="billingAddress2">Address Line 2</label>
                <input
                  type="text"
                  id="billingAddress2"
                  name="billingAddress2"
                  placeholder="Flat 4"
                  value={formData.billingAddress2}
                  onChange={handleChange}
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="billingCity">City <span className="required">*</span></label>
                  <input
                    type="text"
                    id="billingCity"
                    name="billingCity"
                    placeholder="Bournemouth"
                    value={formData.billingCity}
                    onChange={handleChange}
                    className={step1Attempted && !formData.billingCity ? 'input-error' : ''}
                    required
                  />
                  {step1Attempted && !formData.billingCity && (
                    <span className="field-error">City is required</span>
                  )}
                </div>
                <div className="form-group">
                  <label htmlFor="billingCounty">County</label>
                  <input
                    type="text"
                    id="billingCounty"
                    name="billingCounty"
                    placeholder="Dorset"
                    value={formData.billingCounty}
                    onChange={handleChange}
                  />
                </div>
              </div>

              {/* Show postcode input in manual entry mode */}
              {manualAddressEntry && (
                <div className="form-group">
                  <label htmlFor="billingPostcodeManual">
                    {formData.billingCountry === 'United Kingdom' ? 'Postcode' : 'Postcode / ZIP Code'} <span className="required">*</span>
                  </label>
                  <input
                    type="text"
                    id="billingPostcodeManual"
                    name="billingPostcode"
                    placeholder={formData.billingCountry === 'United Kingdom' ? 'BH1 1AA' : 'Enter postcode'}
                    value={formData.billingPostcode}
                    onChange={handleChange}
                    style={formData.billingCountry === 'United Kingdom' ? { textTransform: 'uppercase' } : {}}
                    required
                  />
                </div>
              )}

              <div className="form-group">
                <label htmlFor="billingCountry">Country <span className="required">*</span></label>
                <select
                  id="billingCountry"
                  name="billingCountry"
                  value={formData.billingCountry}
                  onChange={(e) => {
                    handleChange(e)
                    // Switch to manual entry for non-UK countries
                    if (e.target.value !== 'United Kingdom') {
                      setManualAddressEntry(true)
                    }
                  }}
                  required
                >
                  <option value="United Kingdom">United Kingdom</option>
                  <option value="Ireland">Ireland</option>
                  <option disabled>──── Europe ────</option>
                  <option value="Austria">Austria</option>
                  <option value="Belgium">Belgium</option>
                  <option value="Croatia">Croatia</option>
                  <option value="Cyprus">Cyprus</option>
                  <option value="Czech Republic">Czech Republic</option>
                  <option value="Denmark">Denmark</option>
                  <option value="Estonia">Estonia</option>
                  <option value="Finland">Finland</option>
                  <option value="France">France</option>
                  <option value="Germany">Germany</option>
                  <option value="Greece">Greece</option>
                  <option value="Hungary">Hungary</option>
                  <option value="Iceland">Iceland</option>
                  <option value="Italy">Italy</option>
                  <option value="Latvia">Latvia</option>
                  <option value="Lithuania">Lithuania</option>
                  <option value="Luxembourg">Luxembourg</option>
                  <option value="Malta">Malta</option>
                  <option value="Netherlands">Netherlands</option>
                  <option value="Norway">Norway</option>
                  <option value="Poland">Poland</option>
                  <option value="Portugal">Portugal</option>
                  <option value="Romania">Romania</option>
                  <option value="Slovakia">Slovakia</option>
                  <option value="Slovenia">Slovenia</option>
                  <option value="Spain">Spain</option>
                  <option value="Sweden">Sweden</option>
                  <option value="Switzerland">Switzerland</option>
                  <option value="Turkey">Turkey</option>
                  <option disabled>──── Other ────</option>
                  <option value="Australia">Australia</option>
                  <option value="Canada">Canada</option>
                  <option value="New Zealand">New Zealand</option>
                  <option value="United States">United States</option>
                  <option value="Other">Other</option>
                </select>
              </div>

              <h3 className="section-subtitle">Vehicle Information</h3>

              <div className="form-group">
                <label htmlFor="registration">Registration Number <span className="required">*</span></label>
                <div className="registration-input-group">
                  <input
                    type="text"
                    id="registration"
                    name="registration"
                    placeholder="e.g. AB12 CDE"
                    value={formData.registration}
                    onChange={(e) => {
                      handleChange(e)
                      setDvlaVerified(false)
                      setDvlaError('')
                    }}
                    style={{ textTransform: 'uppercase' }}
                    className={step1Attempted && !formData.registration ? 'input-error' : ''}
                    required
                  />
                  <button
                    type="button"
                    className="validate-btn"
                    onClick={lookupVehicle}
                    disabled={!formData.registration || dvlaLoading}
                  >
                    {dvlaLoading ? 'Looking up...' : 'Lookup'}
                  </button>
                </div>
                {dvlaVerified && (
                  <span className="dvla-success">Vehicle found and verified</span>
                )}
                {dvlaError && (
                  <span className="dvla-error">{dvlaError}</span>
                )}
                {step1Attempted && !formData.registration && (
                  <span className="field-error">Registration is required</span>
                )}
              </div>

              {(formData.registration && (dvlaVerified || dvlaError || formData.make)) && (
                <div className="form-group fade-in">
                  <label htmlFor="make">Vehicle Make <span className="required">*</span></label>
                  {dvlaVerified && (formData.make !== 'Other' || formData.customMake) ? (
                    <input
                      type="text"
                      id="make"
                      value={formData.make !== 'Other' ? formData.make : formData.customMake}
                      readOnly
                      className="readonly-input"
                    />
                  ) : (
                    <select
                      id="make"
                      name="make"
                      value={formData.make}
                      onChange={handleChange}
                      className={step1Attempted && !formData.make ? 'input-error' : ''}
                      required
                    >
                      <option value="">Select make</option>
                      {carMakes.map(make => (
                        <option key={make} value={make}>{make}</option>
                      ))}
                      <option value="Other">Other</option>
                    </select>
                  )}
                  {step1Attempted && !isMakeComplete && (
                    <span className="field-error">Vehicle make is required</span>
                  )}
                </div>
              )}

              {formData.make === 'Other' && !(dvlaVerified && formData.customMake) && (
                <div className="form-group fade-in">
                  <label htmlFor="customMake">Enter Vehicle Make <span className="required">*</span></label>
                  <input
                    type="text"
                    id="customMake"
                    name="customMake"
                    placeholder="e.g. Cupra"
                    value={formData.customMake}
                    onChange={handleChange}
                    required
                  />
                </div>
              )}

              {((formData.make && formData.make !== 'Other') || (formData.make === 'Other' && formData.customMake)) && (
                <div className="form-group fade-in">
                  <label htmlFor="colour">Vehicle Colour <span className="required">*</span></label>
                  {dvlaVerified && formData.colour ? (
                    <input
                      type="text"
                      id="colour"
                      value={formData.colour}
                      readOnly
                      className="readonly-input"
                    />
                  ) : (
                    <input
                      type="text"
                      id="colour"
                      name="colour"
                      placeholder="e.g. Black"
                      value={formData.colour}
                      onChange={handleChange}
                      className={step1Attempted && !formData.colour ? 'input-error' : ''}
                      required
                    />
                  )}
                  {step1Attempted && !formData.colour && (
                    <span className="field-error">Vehicle colour is required</span>
                  )}
                </div>
              )}

              {formData.make && formData.make !== 'Other' && formData.colour && (
                <div className="form-group fade-in">
                  <label htmlFor="model">Vehicle Model <span className="required">*</span></label>
                  <select
                    id="model"
                    name="model"
                    value={formData.model}
                    onChange={handleChange}
                    className={step1Attempted && !isModelComplete ? 'input-error' : ''}
                    required
                  >
                    <option value="">Select model</option>
                    {carModels.map(model => (
                      <option key={model} value={model}>{model}</option>
                    ))}
                    <option value="Other">Other</option>
                  </select>
                  {step1Attempted && !isModelComplete && (
                    <span className="field-error">Vehicle model is required</span>
                  )}
                </div>
              )}

              {formData.make === 'Other' && formData.customMake && formData.colour && (
                <div className="form-group fade-in">
                  <label htmlFor="customModel">Enter Vehicle Model <span className="required">*</span></label>
                  <input
                    type="text"
                    id="customModel"
                    name="customModel"
                    placeholder="e.g. Formentor"
                    value={formData.customModel}
                    onChange={handleChange}
                    required
                  />
                </div>
              )}

              {formData.model === 'Other' && formData.make !== 'Other' && (
                <div className="form-group fade-in">
                  <label htmlFor="customModel">Enter Vehicle Model <span className="required">*</span></label>
                  <input
                    type="text"
                    id="customModel"
                    name="customModel"
                    placeholder="e.g. Special Edition"
                    value={formData.customModel}
                    onChange={handleChange}
                    required
                  />
                </div>
              )}

              <div className="form-actions">
                <button type="button" className="back-btn" onClick={prevStep}>
                  Back
                </button>
                <button
                  type="button"
                  className="next-btn"
                  onClick={handleContinueStep3}
                  disabled={saving}
                >
                  {saving ? 'Saving...' : 'Continue to Payment'}
                </button>
              </div>
            </div>
          )}

          {/* Step 1: Trip Details */}
          {currentStep === 1 && (
            <div className="form-section">
              <h2>Trip Details</h2>

              <h3 className="section-subtitle">Departure Flight</h3>

              <div className="form-group">
                <label htmlFor="dropoffDate">Drop-off Date</label>
                <DatePicker
                  selected={formData.dropoffDate}
                  onChange={(date) => handleDateChange(date, 'dropoffDate')}
                  dateFormat="dd/MM/yyyy"
                  minDate={getTodayUK()}
                  placeholderText="Select date"
                  className="date-picker-input"
                  id="dropoffDate"
                  popperPlacement="bottom-start"
                  calendarClassName="fixed-height-calendar"
                  onFocus={(e) => e.target.readOnly = true}
                />
              </div>

              {/* Flight lookup removed - using direct entry flow */}

              {/* Departure Flight Entry Form */}
              {showManualDeparture && formData.dropoffDate && (
                <div className="form-group fade-in">
                  <div className="form-group">
                    <label htmlFor="manualAirline">Airline <span className="required">*</span></label>
                    <select
                      id="manualAirline"
                      value={manualDepartureData.airlineCode}
                      onChange={(e) => {
                        const airline = availableAirlines.find(a => a.code === e.target.value)
                        setManualDepartureData(prev => ({
                          ...prev,
                          airlineCode: e.target.value,
                          airlineName: airline?.name || '',
                          customAirline: e.target.value === 'Other' ? prev.customAirline : ''
                        }))
                        // Auto-sync to arrival airline
                        if (e.target.value === 'Other') {
                          setManualArrivalData(prev => ({
                            ...prev,
                            airlineCode: 'Other',
                            airlineName: ''
                          }))
                        } else if (airline) {
                          setManualArrivalData(prev => ({
                            ...prev,
                            airlineCode: e.target.value,
                            airlineName: airline.name,
                            customAirline: ''
                          }))
                        }
                      }}
                    >
                      <option value="">Select airline</option>
                      {availableAirlines.filter(a => a.code !== 'Other' && a.name !== 'Other').map(airline => (
                        <option key={airline.code} value={airline.code}>{airline.name}</option>
                      ))}
                      <option value="Other">Other</option>
                    </select>
                  </div>

                  {manualDepartureData.airlineCode === 'Other' && (
                    <div className="form-group">
                      <label htmlFor="customDepartureAirline">Enter Airline <span className="required">*</span></label>
                      <input
                        type="text"
                        id="customDepartureAirline"
                        placeholder="e.g., British Airways"
                        value={manualDepartureData.customAirline}
                        onChange={(e) => {
                          const value = e.target.value
                          setManualDepartureData(prev => ({
                            ...prev,
                            customAirline: value,
                            airlineName: value
                          }))
                          // Auto-sync to arrival airline
                          setManualArrivalData(prev => ({
                            ...prev,
                            airlineCode: 'Other',
                            customAirline: value,
                            airlineName: value
                          }))
                        }}
                        className={containsProfanity(manualDepartureData.customAirline) ? 'input-error' : ''}
                      />
                      {containsProfanity(manualDepartureData.customAirline) && (
                        <span className="error-message">Please enter a valid airline name</span>
                      )}
                    </div>
                  )}

                  <div className="form-group">
                    <label htmlFor="manualDestination">Destination <span className="required">*</span></label>
                    <select
                      id="manualDestination"
                      value={manualDepartureData.destinationCode}
                      onChange={(e) => {
                        const dest = availableDestinations.find(d => d.code === e.target.value)
                        setManualDepartureData(prev => ({
                          ...prev,
                          destinationCode: e.target.value,
                          destinationName: dest?.name || '',
                          customDestination: e.target.value === 'Other' ? prev.customDestination : ''
                        }))
                        // Auto-populate arrival origin with same destination
                        if (e.target.value === 'Other') {
                          setManualArrivalData(prev => ({
                            ...prev,
                            originCode: 'Other',
                            originName: ''
                          }))
                        } else if (dest) {
                          setManualArrivalData(prev => ({
                            ...prev,
                            originCode: e.target.value,
                            originName: dest.name,
                            customOrigin: ''
                          }))
                        }
                      }}
                    >
                      <option value="">Select destination</option>
                      {availableDestinations.filter(d => d.code !== 'Other' && d.name !== 'Other').map(dest => (
                        <option key={dest.code} value={dest.code}>{dest.name}</option>
                      ))}
                      <option value="Other">Other</option>
                    </select>
                  </div>

                  {manualDepartureData.destinationCode === 'Other' && (
                    <div className="form-group">
                      <label htmlFor="customDestination">Enter Destination <span className="required">*</span></label>
                      <input
                        type="text"
                        id="customDestination"
                        placeholder="e.g., Barcelona"
                        value={manualDepartureData.customDestination}
                        onChange={(e) => {
                          const value = e.target.value
                          setManualDepartureData(prev => ({
                            ...prev,
                            customDestination: value,
                            destinationName: value
                          }))
                          // Auto-sync to arrival origin
                          setManualArrivalData(prev => ({
                            ...prev,
                            customOrigin: value,
                            originName: value
                          }))
                        }}
                        className={containsProfanity(manualDepartureData.customDestination) ? 'input-error' : ''}
                      />
                      {containsProfanity(manualDepartureData.customDestination) && (
                        <span className="error-message">Please enter a valid destination name</span>
                      )}
                    </div>
                  )}

                  <div className="form-row">
                    <div className="form-group">
                      <label htmlFor="manualFlightNumber">Flight Number</label>
                      <input
                        type="text"
                        id="manualFlightNumber"
                        placeholder="e.g., 1234"
                        value={manualDepartureData.flightNumber}
                        onChange={(e) => setManualDepartureData(prev => ({
                          ...prev,
                          flightNumber: e.target.value.toUpperCase()
                        }))}
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor="manualFlightTime">Departure Time <span className="required">*</span></label>
                      <MobileTimePicker
                        id="manualFlightTime"
                        placeholder="e.g., 14:30"
                        value={manualDepartureData.flightTime}
                        label="Departure Time"
                        onChange={(value) => setManualDepartureData(prev => ({
                          ...prev,
                          flightTime: value
                        }))}
                      />
                    </div>
                  </div>

                  {manualDropoffSlots.length > 0 && (
                    <div className="form-group">
                      <label>Select Drop-off Time <span className="required">*</span></label>
                      <div className="dropoff-slots">
                        {manualDropoffSlots.map(slot => (
                          <label key={slot.id} className="dropoff-slot">
                            <input
                              type="radio"
                              name="manualDropoffSlot"
                              value={slot.id}
                              checked={manualDepartureData.dropoffSlot === slot.id}
                              onChange={(e) => setManualDepartureData(prev => ({
                                ...prev,
                                dropoffSlot: e.target.value
                              }))}
                            />
                            <div className="slot-card">
                              <div className="slot-info">
                                <span className="slot-time">{slot.time}</span>
                                <span className="slot-label">{slot.label}</span>
                              </div>
                            </div>
                          </label>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Flight-based slot selection removed - using direct entry */}

              {manualDepartureData.dropoffSlot && (
                <>
                  <h3 className="section-subtitle">Return Flight</h3>

                  <div className="form-group fade-in">
                    <label>Select Return Date</label>
                    <p className="return-date-hint">When does your return flight land at Bournemouth?</p>
                    <div className="return-date-picker">
                      <DatePicker
                        selected={formData.pickupDate}
                        onChange={(date) => handleDateChange(date, 'pickupDate')}
                        dateFormat="dd/MM/yyyy"
                        minDate={(() => {
                          const minDate = new Date(formData.dropoffDate)
                          minDate.setDate(minDate.getDate() + 1)
                          return minDate
                        })()}
                        maxDate={(() => {
                          const maxDate = new Date(formData.dropoffDate)
                          maxDate.setDate(maxDate.getDate() + 60)
                          return maxDate
                        })()}
                        placeholderText="Select return date"
                        className="date-picker-input"
                        popperPlacement="bottom-start"
                        calendarClassName="fixed-height-calendar"
                        onFocus={(e) => e.target.readOnly = true}
                      />
                      {formData.pickupDate && (
                        <div className="return-date-summary">
                          <span className="return-date-formatted">
                            {format(formData.pickupDate, 'EEEE, d MMMM yyyy')}
                          </span>
                          <span className="trip-duration-display">
                            {(() => {
                              const days = Math.round((formData.pickupDate - formData.dropoffDate) / (1000 * 60 * 60 * 24))
                              if (days === 7) return '(1 week trip)'
                              if (days === 14) return '(2 week trip)'
                              return `(${days} day${days !== 1 ? 's' : ''} trip)`
                            })()}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}

              {/* Flight-based arrival lookup removed - using direct entry */}

              {/* Return Flight Entry Form */}
              {showManualArrival && formData.pickupDate && (
                <div className="form-group fade-in">
                  <div className="form-group">
                    <label htmlFor="manualArrivalAirline">Airline <span className="required">*</span></label>
                    <select
                      id="manualArrivalAirline"
                      value={manualArrivalData.airlineCode}
                      onChange={(e) => {
                        const airline = availableAirlines.find(a => a.code === e.target.value)
                        setManualArrivalData(prev => ({
                          ...prev,
                          airlineCode: e.target.value,
                          airlineName: airline?.name || '',
                          customAirline: e.target.value === 'Other' ? prev.customAirline : ''
                        }))
                      }}
                    >
                      <option value="">Select airline</option>
                      {availableAirlines.filter(a => a.code !== 'Other' && a.name !== 'Other').map(airline => (
                        <option key={airline.code} value={airline.code}>{airline.name}</option>
                      ))}
                      <option value="Other">Other</option>
                    </select>
                  </div>

                  {manualArrivalData.airlineCode === 'Other' && (
                    <div className="form-group">
                      <label htmlFor="customArrivalAirline">Enter Airline <span className="required">*</span></label>
                      <input
                        type="text"
                        id="customArrivalAirline"
                        placeholder="e.g., British Airways"
                        value={manualArrivalData.customAirline}
                        onChange={(e) => {
                          const value = e.target.value
                          setManualArrivalData(prev => ({
                            ...prev,
                            customAirline: value,
                            airlineName: value
                          }))
                        }}
                        className={containsProfanity(manualArrivalData.customAirline) ? 'input-error' : ''}
                      />
                      {containsProfanity(manualArrivalData.customAirline) && (
                        <span className="error-message">Please enter a valid airline name</span>
                      )}
                    </div>
                  )}

                  <div className="form-group">
                    <label htmlFor="manualArrivalOrigin">Origin <span className="required">*</span></label>
                    <select
                      id="manualArrivalOrigin"
                      value={manualArrivalData.originCode}
                      onChange={(e) => {
                        const origin = availableDestinations.find(d => d.code === e.target.value)
                        setManualArrivalData(prev => ({
                          ...prev,
                          originCode: e.target.value,
                          originName: origin?.name || '',
                          customOrigin: e.target.value === 'Other' ? prev.customOrigin : ''
                        }))
                      }}
                    >
                      <option value="">Select origin</option>
                      {availableDestinations.filter(d => d.code !== 'Other' && d.name !== 'Other').map(dest => (
                        <option key={dest.code} value={dest.code}>{dest.name}</option>
                      ))}
                      <option value="Other">Other</option>
                    </select>
                  </div>

                  {manualArrivalData.originCode === 'Other' && (
                    <div className="form-group">
                      <label htmlFor="customOrigin">Enter Origin <span className="required">*</span></label>
                      <input
                        type="text"
                        id="customOrigin"
                        placeholder="e.g., Barcelona"
                        value={manualArrivalData.customOrigin}
                        onChange={(e) => {
                          const value = e.target.value
                          setManualArrivalData(prev => ({
                            ...prev,
                            customOrigin: value,
                            originName: value
                          }))
                        }}
                        className={containsProfanity(manualArrivalData.customOrigin) ? 'input-error' : ''}
                      />
                      {containsProfanity(manualArrivalData.customOrigin) && (
                        <span className="error-message">Please enter a valid origin name</span>
                      )}
                    </div>
                  )}

                  <div className="form-row">
                    <div className="form-group">
                      <label htmlFor="manualArrivalFlightNumber">Flight Number</label>
                      <input
                        type="text"
                        id="manualArrivalFlightNumber"
                        placeholder="e.g., 1234"
                        value={manualArrivalData.flightNumber}
                        onChange={(e) => setManualArrivalData(prev => ({
                          ...prev,
                          flightNumber: e.target.value.toUpperCase()
                        }))}
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor="manualArrivalFlightTime">Arrival Time <span className="required">*</span></label>
                      <MobileTimePicker
                        id="manualArrivalFlightTime"
                        placeholder="e.g., 14:30"
                        value={manualArrivalData.flightTime}
                        label="Arrival Time"
                        onChange={(value) => setManualArrivalData(prev => ({
                          ...prev,
                          flightTime: value
                        }))}
                      />
                      <p className="field-hint">Time your flight lands at Bournemouth. For overnight flights, select the landing date above.</p>
                    </div>
                  </div>

                </div>
              )}

              {formData.pickupDate && !isCapacityAvailable && (
                <div className="form-group fade-in">
                  <p className="no-flights-message">Sorry, we're fully booked for some dates in your selected range. Please try different dates.</p>
                </div>
              )}

              <div className="form-actions">
                <button
                  type="button"
                  className="next-btn"
                  onClick={handleContinueStep1}
                >
                  Continue to Package Selection
                </button>
              </div>
            </div>
          )}

          {/* Step 2: Package Selection */}
          {currentStep === 2 && (
            <div className="form-section">
              <h2>Your Package</h2>

              {pricingInfo ? (
                <div className="package-summary">
                  <div className="package-card selected">
                    <span className="package-price">£{pricingInfo.price.toFixed(0)}</span>
                    <span className="package-period">/ {pricingInfo.duration_days} days</span>

                    <ul className="package-features">
                      <li>Meet & Greet at terminal</li>
                      <li>Secure storage facility</li>
                      <li>24/7 monitoring</li>
                      <li>No hidden fees</li>
                    </ul>
                  </div>
                </div>
              ) : (
                <div className="loading-message">Loading pricing information...</div>
              )}

              <div className="form-actions">
                <button type="button" className="back-btn" onClick={prevStep}>
                  Back
                </button>
                <button
                  type="button"
                  className="next-btn"
                  onClick={handleContinueStep2}
                  disabled={!isStep2Complete}
                >
                  Continue to Your Details
                </button>
              </div>
            </div>
          )}

          {/* Step 4: Payment */}
          {currentStep === 4 && (
            <div className="form-section">
              <h2>Payment</h2>

              <h3 className="section-subtitle">Booking Summary</h3>
              <div className="booking-summary">
                <div className="summary-item">
                  <span>Airport</span>
                  <span>Bournemouth (BOH)</span>
                </div>
                <div className="summary-item">
                  <span>Drop-off</span>
                  <span>
                    {formatDisplayDate(formData.dropoffDate)}
                    {formData.dropoffSlot && dropoffSlots.find(s => s.id === formData.dropoffSlot) && (
                      <> at {dropoffSlots.find(s => s.id === formData.dropoffSlot).time}</>
                    )}
                  </span>
                </div>
                <div className="summary-item">
                  <span>Pick-up</span>
                  <span>
                    {formatDisplayDate(actualPickupDate || formData.pickupDate)}
                    {formData.pickupFlightTime && (() => {
                      // pickupFlightTime is a flightKey in format "time|flightNumber"
                      // Use overridden arrival time if set, otherwise use scheduled time
                      const scheduledTime = formData.pickupFlightTime.split('|')[0]
                      const flightTime = arrivalTimeOverride || scheduledTime
                      const [hours, minutes] = flightTime.split(':').map(Number)
                      const landingMinutes = hours * 60 + minutes
                      const pickupTime = formatMinutesToTime(landingMinutes + 30)
                      return <> from {pickupTime}</>
                    })()}
                  </span>
                </div>
                <div className="summary-item">
                  <span>Vehicle</span>
                  <span>{formData.colour} {formData.make === 'Other' ? formData.customMake : formData.make} {formData.model === 'Other' ? formData.customModel : formData.model}</span>
                </div>
                <div className="summary-item">
                  <span>Registration</span>
                  <span>{formData.registration.toUpperCase()}</span>
                </div>
                <div className="summary-item">
                  <span>Package</span>
                  <span>{pricingInfo ? `${pricingInfo.duration_days} Day${pricingInfo.duration_days !== 1 ? 's' : ''}` : (formData.package === 'quick' ? '1 Week' : '2 Weeks')}</span>
                </div>
                {promoCodeValid && promoCodeDiscount > 0 && (
                  <>
                    <div className="summary-item subtotal">
                      <span>Subtotal</span>
                      <span>£{pricingInfo ? pricingInfo.price.toFixed(2) : (formData.package === 'quick' ? '99.00' : '150.00')}</span>
                    </div>
                    <div className="summary-item discount">
                      <span>{promoCodeDiscount === 100 ? '1 Week Free Parking' : `Promo Discount (${promoCodeDiscount}%)`}</span>
                      <span className="discount-amount">-£{(() => {
                        const basePrice = pricingInfo ? pricingInfo.price : 0
                        if (promoCodeDiscount === 100) {
                          if (formData.package === 'quick') {
                            return basePrice.toFixed(2)
                          }
                          const week1BasePrice = pricingInfo?.week1_price || 0
                          return Math.min(week1BasePrice, basePrice).toFixed(2)
                        }
                        return (basePrice * promoCodeDiscount / 100).toFixed(2)
                      })()}</span>
                    </div>
                  </>
                )}
                <div className="summary-item total">
                  <span>Total</span>
                  <span>
                    £{(() => {
                      const basePrice = pricingInfo ? pricingInfo.price : 0
                      let discount = 0
                      if (promoCodeValid && promoCodeDiscount > 0) {
                        if (promoCodeDiscount === 100) {
                          if (formData.package === 'quick') {
                            discount = basePrice
                          } else {
                            const week1BasePrice = pricingInfo?.week1_price || 0
                            discount = Math.min(week1BasePrice, basePrice)
                          }
                        } else {
                          discount = basePrice * promoCodeDiscount / 100
                        }
                      }
                      return (basePrice - discount).toFixed(2)
                    })()}
                  </span>
                </div>
              </div>

              {/* Promo Code Section */}
              <div className="promo-code-section">
                <h4>Have a promo code?</h4>
                {promoCodeValid ? (
                  <div className="promo-code-applied">
                    <span className="promo-badge">{promoCode.toUpperCase()}</span>
                    <span className="promo-success">{promoCodeMessage}</span>
                    <button type="button" className="promo-remove" onClick={clearPromoCode}>Remove</button>
                  </div>
                ) : (
                  <div className="promo-code-input">
                    <input
                      type="text"
                      placeholder="Enter promo code"
                      value={promoCode}
                      onChange={(e) => setPromoCode(e.target.value.toUpperCase())}
                      disabled={promoCodeValidating}
                    />
                    <button
                      type="button"
                      onClick={validatePromoCode}
                      disabled={promoCodeValidating || !promoCode.trim()}
                      className="promo-apply-btn"
                    >
                      {promoCodeValidating ? 'Checking...' : 'Apply'}
                    </button>
                  </div>
                )}
                {promoCodeMessage && !promoCodeValid && (
                  <p className="promo-error">{promoCodeMessage}</p>
                )}
              </div>

              {/* Where did you hear about us? - Marketing Attribution */}
              {!heardAboutUsAnswered && !heardAboutUsLoading && (
                <div className="heard-about-us-section">
                  <h4>Where did you hear about us? <span className="required">*</span></h4>
                  <div className="heard-about-us-select">
                    <select
                      value={heardAboutUsSource}
                      onChange={(e) => {
                        setHeardAboutUsSource(e.target.value)
                        if (e.target.value !== 'other') {
                          setHeardAboutUsDetail('')
                        }
                      }}
                      className="form-control"
                    >
                      <option value="">Please select...</option>
                      <option value="google">Google</option>
                      <option value="facebook">Facebook</option>
                      <option value="instagram">Instagram</option>
                      <option value="word_of_mouth">Word of Mouth</option>
                      <option value="leaflet">Leaflet</option>
                      <option value="tv">TV</option>
                      <option value="radio">Radio</option>
                      <option value="newspaper">Newspaper</option>
                      <option value="linkedin">LinkedIn</option>
                      <option value="afc_bournemouth">AFC Bournemouth</option>
                      <option value="other">Other</option>
                    </select>
                  </div>
                  {heardAboutUsSource === 'other' && (
                    <div className="heard-about-us-detail">
                      <input
                        type="text"
                        placeholder="Please tell us where..."
                        value={heardAboutUsDetail}
                        onChange={(e) => setHeardAboutUsDetail(e.target.value)}
                        className="form-control"
                        maxLength={255}
                      />
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={submitHeardAboutUs}
                    disabled={!heardAboutUsSource || (heardAboutUsSource === 'other' && !heardAboutUsDetail.trim()) || heardAboutUsSubmitting}
                    className="heard-about-us-submit"
                  >
                    {heardAboutUsSubmitting ? 'Saving...' : 'Continue'}
                  </button>
                </div>
              )}

              {heardAboutUsLoading && (
                <div className="heard-about-us-loading">
                  <p>Loading...</p>
                </div>
              )}

              {heardAboutUsAnswered && (
                <>
                  <div className="form-group checkbox-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        name="terms"
                        checked={formData.terms}
                        onChange={handleChange}
                        required
                      />
                      <span>I agree to the <Link to="/terms-conditions" target="_blank">Terms & Conditions</Link> and <Link to="/privacy-policy" target="_blank">Privacy Policy</Link></span>
                    </label>
                  </div>

              {paymentComplete ? (
                <div className="payment-success">
                  <div className="success-icon">✓</div>
                  <h3>Payment Successful!</h3>
                  <p>Your booking reference is:</p>
                  <div className="booking-reference-display">
                    {bookingConfirmation?.reference}
                  </div>
                  <p>A confirmation email has been sent to {formData.email}</p>
                  <p className="spam-notice">Please check your spam/junk folder if you don't see it in your inbox.</p>
                  <button
                    type="button"
                    className="submit-btn"
                    onClick={() => navigate('/')}
                  >
                    Return to Home
                  </button>
                </div>
              ) : isStep4Complete ? (
                console.log('[Step 4] Rendering StripePayment with manualDepartureData:', manualDepartureData) ||
                console.log('[Step 4] Rendering StripePayment with manualArrivalData:', manualArrivalData) ||
                <StripePayment
                  formData={formData}
                  selectedFlight={null}
                  selectedArrivalFlight={null}
                  customerId={customerId}
                  vehicleId={vehicleId}
                  sessionId={sessionIdRef.current}
                  promoCode={promoCodeValid ? promoCode : null}
                  promoCodeDiscount={promoCodeValid ? promoCodeDiscount : 0}
                  pricingInfo={pricingInfo}
                  onPaymentSuccess={handlePaymentSuccess}
                  onPaymentError={handlePaymentError}
                  departureTimeOverride={null}
                  arrivalTimeOverride={null}
                  manualDepartureData={manualDepartureData}
                  manualArrivalData={manualArrivalData}
                />
              ) : (
                <div className="terms-required">
                  {!formData.terms && (
                    <p>Please accept the Terms & Conditions to proceed with payment</p>
                  )}
                </div>
              )}
                </>
              )}

              {!paymentComplete && (
                <div className="form-actions">
                  <button type="button" className="back-btn" onClick={prevStep}>
                    Back
                  </button>
                </div>
              )}
            </div>
          )}
        </form>
      </div>

      <footer className="bookings-new-footer">
        <img src="/assets/logo.svg" alt="TAG" className="footer-logo-small" />
        <p>© 2025 TAG Parking. All rights reserved.</p>
      </footer>
    </div>
  )
}

export default Bookings
