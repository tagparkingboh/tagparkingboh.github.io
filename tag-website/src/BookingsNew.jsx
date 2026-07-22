import { useState, useMemo, useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import DatePicker from 'react-datepicker'
import { format, addDays } from 'date-fns'
import PhoneInput, { isValidPhoneNumber } from 'react-phone-number-input'
import 'react-phone-number-input/style.css'
import StripePayment from './components/StripePayment'
import MobileTimePicker from './components/MobileTimePicker'
import { buildDropoffSlots } from './utils/dropoffSlots'
import {
  computeEarliestBookableDate,
  inLeadTimeRecheckWindow,
} from './utils/leadTime'
import {
  isAtCapacity as isAtCapacityUtil,
  isManuallyBlocked as isManuallyBlockedUtil,
  findBlockedDateInStay as findBlockedDateInStayUtil,
  getDayOccupancyPercent as getDayOccupancyPercentUtil,
  getOnlineCapacityForDate,
  DEFAULT_ONLINE_CAPACITY,
  isoDate as isoDateUtil,
} from './utils/capacity'
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

const ARRIVAL_TIME_NOTICE = "Please enter the arrival date and time shown for your flight, using the 24-hour clock. If your flight lands after midnight, select the date it lands, even if that's the following day."

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

// Booking lead-time rule lives in utils/leadTime.js (testable pure helpers).

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

function Bookings({ isModal = false, onClose }) {
  const navigate = useNavigate()
  const closeOrHome = () => {
    if (isModal && onClose) onClose()
    else navigate('/')
  }
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
  // Confirmation modal for step 1
  const [showTimeConfirmModal, setShowTimeConfirmModal] = useState(false)

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

  // PR 4b + 4c: server-issued booking-draft token. Gates 8 customer-flow
  // endpoints (POST + PATCH customer, PATCH customer billing, POST +
  // PATCH vehicle, GET + POST heard-about-us, POST dvla-lookup) against
  // IDOR enumeration.
  // Stored in sessionStorage so it survives hard refresh inside the
  // same browser tab; 24h server-side TTL. Backend is in SOFT MODE
  // 2026-05-29 → 2026-06-12 — missing token is allowed but logged.
  const draftTokenRef = useRef(sessionStorage.getItem('booking_draftToken'))
  // In-flight POST /api/booking-drafts promise. Memoised so concurrent
  // ensureDraftToken() callers share the same fetch.
  const draftTokenPromiseRef = useRef(null)

  // Fetches a token if we don't have one. Memoises the in-flight
  // promise so a fast user can trigger PATCH /api/customers/{id}
  // before the bootstrap fetch lands without firing a second
  // POST /api/booking-drafts. Returns the token (or null on failure
  // — soft mode tolerates null; enforce mode will 401, which is the
  // user-visible signal that the rollout has flipped).
  const ensureDraftToken = () => {
    if (draftTokenRef.current) return Promise.resolve(draftTokenRef.current)
    if (draftTokenPromiseRef.current) return draftTokenPromiseRef.current
    draftTokenPromiseRef.current = Promise.resolve(
      fetch(
        `${API_BASE_URL}/api/booking-drafts`,
        { method: 'POST' },
      ),
    )
      .then((r) => (r?.ok ? r.json() : null))
      .then((data) => {
        if (data?.token) {
          draftTokenRef.current = data.token
          sessionStorage.setItem('booking_draftToken', data.token)
        }
        return draftTokenRef.current
      })
      .catch(() => null)
    return draftTokenPromiseRef.current
  }

  // Bootstrap on mount so most user actions find a ready token. The
  // ensureDraftToken() awaits in the 8 gated fetch paths cover the
  // race where the user submits faster than this fetch lands.
  useEffect(() => {
    ensureDraftToken()
  }, [])

  // Spread into fetch() options to attach the draft token header
  // when one exists. Sync helper — callers do
  //   await ensureDraftToken()
  // first if they need to guarantee presence (the 8 gated paths do).
  const draftHeaders = () =>
    draftTokenRef.current ? { 'X-Draft-Token': draftTokenRef.current } : {}

  // Discard the current draft token so the next ensureDraftToken()
  // call issues a fresh one. Used when the customer's checkout
  // identity changes mid-flow (currently: email-change in
  // saveCustomer). PR 4c review fix 2026-05-29: without this, a
  // draft already bound to the old email/customer_id would 403 the
  // create-new-customer POST that the email-change branch
  // explicitly takes.
  const resetDraftToken = () => {
    draftTokenRef.current = null
    draftTokenPromiseRef.current = null
    sessionStorage.removeItem('booking_draftToken')
  }

  const isDraftTokenError = async (response) => {
    if (response.status !== 401) return false
    try {
      const data = await response.clone().json()
      return typeof data?.detail === 'string' && data.detail.includes('X-Draft-Token')
    } catch {
      return false
    }
  }

  const fetchWithDraftToken = async (url, options = {}) => {
    await ensureDraftToken()
    const buildOptions = () => ({
      ...options,
      headers: {
        ...(options.headers || {}),
        ...draftHeaders(),
      },
    })

    let response = await fetch(url, buildOptions())
    if (await isDraftTokenError(response)) {
      resetDraftToken()
      await ensureDraftToken()
      response = await fetch(url, buildOptions())
    }
    return response
  }
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
  // Promo code type determines discount behavior:
  // - 'percentage': Standard percentage discount (e.g., 10% off)
  // - 'free_week': "1 Week Free Parking" - deducts week1_price (free for ≤7 days, partial for >7 days)
  // - 'free_100': "100% Off" - completely free regardless of trip length
  const [promoCodeType, setPromoCodeType] = useState(() => loadBookingState('promoCodeType', 'percentage'))
  const [promoTypeHydrating, setPromoTypeHydrating] = useState(false)
  const promoTypeHydratedRef = useRef(false)

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
  // 24-hour time format warning - shown once per field type per session
  const [showDepartureTimeWarning, setShowDepartureTimeWarning] = useState(false)
  const [showArrivalTimeNotice, setShowArrivalTimeNotice] = useState(false)
  const departureTimeWarningShownRef = useRef(
    sessionStorage.getItem('booking_departureTimeWarningShown') === 'true'
  )
  const arrivalTimeWarningShownRef = useRef(
    sessionStorage.getItem('booking_arrivalTimeWarningShown') === 'true'
  )
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

  // Helper to log funnel events (with deduplication via sessionStorage)
  const logFunnelEvent = (eventName, eventData) => {
    const flagKey = `funnel_${eventName}_logged`
    if (sessionStorage.getItem(flagKey)) {
      // Already logged this event for this session
      return
    }
    // Mark as logged immediately to prevent duplicate calls
    sessionStorage.setItem(flagKey, 'true')

    fetch(`${API_BASE_URL}/api/booking/audit-event`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionIdRef.current,
        event: eventName,
        event_data: {
          ...eventData,
          timestamp: new Date().toISOString()
        }
      })
    }).catch(err => console.error(`Failed to log ${eventName}:`, err))
  }

  // Flight data from API
  const [departuresForDate, setDeparturesForDate] = useState([])
  const [arrivalsForDate, setArrivalsForDate] = useState([])
  const [loadingFlights, setLoadingFlights] = useState(false)
  const [departuresLoaded, setDeparturesLoaded] = useState(false)
  const [arrivalsLoaded, setArrivalsLoaded] = useState(false)

  // Blocked dates state
  const [blockedDates, setBlockedDates] = useState([])
  // Daily occupancy/capacity maps for the next 90 days drive the date picker
  // tint, stay-span warning, and busy warning.
  const [dailyOccupancy, setDailyOccupancy] = useState({})
  // Strictly-through stays (cars parked all day): the "definitely full"
  // floor for hard blocks. dailyOccupancy (touching count) stays advisory.
  const [dailyThroughOccupancy, setDailyThroughOccupancy] = useState({})
  // Backend's CAPACITY_GATE_TIME_AWARE flag, echoed by /api/capacity/daily.
  // Hard blocks may only relax to the through-count while the backend gate
  // is time-aware; when false (or on an older backend that omits the
  // field) they stay on the touching count so the banner and the
  // create-intent 400 agree. Rollback = flip the flag back.
  const [timeAwareGate, setTimeAwareGate] = useState(false)
  const [dailyCapacity, setDailyCapacity] = useState({})
  const [onlineCapacity, setOnlineCapacity] = useState(DEFAULT_ONLINE_CAPACITY)
  // "We're getting full" early-warning modal. Fires for any date in the
  // 80-99% band — at-or-above 100% is already blocked by the existing
  // "Sorry, we're full" banners. Tracks dismissed ISO dates ONLY while
  // they remain selected; once a customer changes the dropoff/pickup
  // away from a date, that date drops out of the dismissed set so
  // returning to it later re-fires the popup (cleanup useEffect below).
  const [busyWarning, setBusyWarning] = useState(null)
  const dismissedBusyDatesRef = useRef(new Set())

  // Parking capacity management — time-aware. The backend computes peak
  // concurrent occupancy across the customer's [dropoff_dt, pickup_dt]
  // window so a 16:30 drop-off is allowed if another car is being picked
  // up at 16:00 the same day. Populated by the useEffect below once all
  // four inputs (dates + times) are set; null while we're still waiting.
    const [capacityCheck, setCapacityCheck] = useState(null)  // { allowed, peak, max_capacity }

  // Per-slot availability from the batched /api/capacity/check-slots call.
  // { key, timeAwareGate, byTime: { 'HH:MM': bool } } — key ties the answer
  // to the inputs it was computed for, so a stale response never filters a
  // fresher slot list. Only filters when the backend echoes its gate as
  // time-aware; otherwise slots we show could still 400 at create-intent.
  const [slotAvailability, setSlotAvailability] = useState(null)

  // Lead-time gate. Pure logic lives in utils/leadTime.js so it's testable
  // with vi.setSystemTime(). leadTimeTick is bumped once a minute inside the
  // 19:50→20:10 UK window so the gate flips live mid-flow — a customer who
  // starts a booking at 19:55 and submits at 20:03 sees the banner appear
  // before they click pay rather than getting a 400 from the backend.
  const [leadTimeTick, setLeadTimeTick] = useState(0)

  useEffect(() => {
    const id = setInterval(() => {
      if (inLeadTimeRecheckWindow(new Date())) {
        setLeadTimeTick((n) => n + 1)
      }
    }, 60_000)
    return () => clearInterval(id)
  }, [])

  const earliestBookableDate = useMemo(
    () => computeEarliestBookableDate(new Date()),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [leadTimeTick, formData.dropoffDate],
  )

  const isLeadTimeAllowed = useMemo(() => {
    if (!formData.dropoffDate) return true
    return formData.dropoffDate >= earliestBookableDate
  }, [formData.dropoffDate, earliestBookableDate])

  // Dynamic pricing state
  const [pricingInfo, setPricingInfo] = useState(() => loadBookingState('pricingInfo', null))
  const [airportQuote, setAirportQuote] = useState(() => loadBookingState('airportQuote', null))
  const [pricingError, setPricingError] = useState('')
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
    sessionStorage.setItem('booking_promoCodeType', JSON.stringify(promoCodeType))
  }, [promoCode, promoCodeValid, promoCodeMessage, promoCodeDiscount, promoCodeType])

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

  useEffect(() => {
    sessionStorage.setItem('booking_pricingInfo', JSON.stringify(pricingInfo))
  }, [pricingInfo])

  useEffect(() => {
    sessionStorage.setItem('booking_airportQuote', JSON.stringify(airportQuote))
  }, [airportQuote])

  // Log funnel event when both dates are selected
  useEffect(() => {
    if (formData.dropoffDate && formData.pickupDate) {
      logFunnelEvent('dates_selected', {
        dropoff_date: format(formData.dropoffDate, 'yyyy-MM-dd'),
        pickup_date: format(formData.pickupDate, 'yyyy-MM-dd'),
        days_parking: Math.ceil((formData.pickupDate - formData.dropoffDate) / (1000 * 60 * 60 * 24))
      })
    }
  }, [formData.dropoffDate, formData.pickupDate])

  // Capacity-check useEffect lives further down, after dropoffTime / pickupTime
  // are declared (they're derived from dropoffSlots / pickupFlightTime which
  // depend on flight data fetched after this point). Defining the effect here
  // would hit a TDZ on the deps array. Search for "capacity/check-slot".

  // Check heard-about-us status when customer ID is available and entering Step 4
  useEffect(() => {
    const checkHeardAboutUsStatus = async () => {
      if (!customerId || currentStep !== 4 || heardAboutUsAnswered) return

      setHeardAboutUsLoading(true)
      try {
        const response = await fetchWithDraftToken(
          `${API_BASE_URL}/api/customers/heard-about-us-status?email=${encodeURIComponent(formData.email)}`,
        )
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
      const response = await fetchWithDraftToken(`${API_BASE_URL}/api/customers/heard-about-us`, {
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

  // Time-aware availability. `null` (still loading or not enough info) and
  // `true` both let the user proceed — we only block when the backend
  // explicitly says peak + 1 > cap (capacityCheck.allowed === false).
  const isCapacityAvailable = capacityCheck === null ? true : capacityCheck.allowed !== false

  // Helper: Check if a time falls within a time slot
  const isTimeInSlot = (timeStr, slot) => {
    if (!timeStr || !slot) return false
    // Parse time (HH:MM format)
    const [checkH, checkM] = timeStr.split(':').map(Number)
    const [startH, startM] = slot.start_time.split(':').map(Number)
    const [endH, endM] = slot.end_time.split(':').map(Number)

    const checkMins = checkH * 60 + checkM
    const startMins = startH * 60 + startM
    const endMins = endH * 60 + endM

    // Start time is inclusive, end time is exclusive
    return checkMins >= startMins && checkMins < endMins
  }

  // Validate time format helper (24-hour clock with valid hours 00-23 and minutes 00-59)
  // Defined here before useMemo hooks that use it
  const isValidTimeFormat = (timeStr) => {
    if (!timeStr) return false
    const match = timeStr.match(/^(\d{1,2}):(\d{2})$/)
    if (!match) return false
    const hours = parseInt(match[1], 10)
    const minutes = parseInt(match[2], 10)
    return hours >= 0 && hours <= 23 && minutes >= 0 && minutes <= 59
  }

  // -- Day-level capacity helpers --------------------------------------
  // Pure logic lives in src/utils/capacity.js so it can be HUEB-tested. The
  // wrappers below thread the component's state (dailyOccupancy, dailyCapacity,
  // blockedDates) so the JSX call sites stay parameter-free.

  const isManuallyBlocked = (date) =>
    isManuallyBlockedUtil(date, blockedDates)

  const isAtCapacity = (date) =>
    isAtCapacityUtil(date, dailyOccupancy, dailyCapacity)

  // Hard fullness map. Time-aware backend gate: through-count (cars parked
  // straight through the day — can't be at cap while a booking could still
  // physically fit). Flag off: the touching count, mirroring the per-day
  // create-intent gate so the banner and the 400 agree.
  const hardFullOccupancy = timeAwareGate ? dailyThroughOccupancy : dailyOccupancy

  // The only signal allowed to say "Sorry, we're full".
  const isDayFull = (date) =>
    isAtCapacityUtil(date, hardFullOccupancy, dailyCapacity)

  // Tint helper for react-datepicker `dayClassName` prop. Advisory — keyed
  // off the touching count so busy turnover days still tint amber.
  const datePickerDayClass = (date) => {
    if (isManuallyBlocked(date)) return 'tag-day-blocked-manual'
    if (isAtCapacity(date)) return 'tag-day-blocked-cap'
    return ''
  }

  // Walk the stay range and return the first date that's blocked or full.
  // Catches the "straddle" case where dropoff + pickup themselves are fine
  // but a day inside the stay is full. Walks the hard-fullness map: with a
  // time-aware backend a turnover day with departures isn't "full" — the
  // create-intent gate has the final say once exact times are known.
    const findBlockedDateInStay = useMemo(
      () => findBlockedDateInStayUtil(
        formData.dropoffDate, formData.pickupDate, hardFullOccupancy, blockedDates, dailyCapacity,
      ),
    [formData.dropoffDate, formData.pickupDate, blockedDates, hardFullOccupancy, dailyCapacity],
  )

  // Check if a date/time is blocked for drop-offs
  // Returns true if ALL potential dropoff times are blocked (or full-day block)
  const isDropoffDateBlocked = useMemo(() => {
    if (!formData.dropoffDate || blockedDates.length === 0) return false

    // Format date inline to avoid external function reference issues
    const d = formData.dropoffDate
    const dateStr = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

    // Find any blocked date that covers this date
    const blockedDate = blockedDates.find(bd =>
      dateStr >= bd.start_date && dateStr <= bd.end_date
    )

    if (!blockedDate) return false

    // If blocked date has time slots, check if ALL slots would be blocked
    if (blockedDate.time_slots && blockedDate.time_slots.length > 0) {
      // Need flight time entered to check time slots
      if (!manualDepartureData.flightTime || !isValidTimeFormat(manualDepartureData.flightTime)) {
        return false
      }

      // Calculate the potential drop-off times (same builder as the slot
      // picker, so the 04:00 floor applies here too). Previous-evening
      // times (negative minutes) are excluded, matching the old behaviour.
      const [hours, minutes] = manualDepartureData.flightTime.split(':').map(Number)
      const departureMinutes = hours * 60 + minutes

      const potentialTimes = buildDropoffSlots(departureMinutes)
        .filter((slot, idx) => {
          const offsets = { '165': 165, '120': 120, '90': 90 }
          return departureMinutes - offsets[slot.id] >= 0
        })
        .map(slot => slot.time)

      if (potentialTimes.length === 0) return false

      // Check if ALL potential dropoff times are blocked (inline logic)
      const allBlocked = potentialTimes.every(timeStr => {
        return blockedDate.time_slots.some(slot => {
          if (!slot.block_dropoffs) return false
          const [checkH, checkM] = timeStr.split(':').map(Number)
          const [startH, startM] = slot.start_time.split(':').map(Number)
          const [endH, endM] = slot.end_time.split(':').map(Number)
          const checkMins = checkH * 60 + checkM
          const startMins = startH * 60 + startM
          const endMins = endH * 60 + endM
          return checkMins >= startMins && checkMins < endMins
        })
      })

      return allBlocked
    }

    // No time slots - use full day blocking
    return blockedDate.block_dropoffs
  }, [formData.dropoffDate, blockedDates, manualDepartureData.flightTime])

  // Check if a date/time is blocked for pick-ups
  const isPickupDateBlocked = useMemo(() => {
    if (!formData.pickupDate || blockedDates.length === 0) return false
    const dateStr = format(formData.pickupDate, 'yyyy-MM-dd')

    // Find any blocked date that covers this date
    const blockedDate = blockedDates.find(bd =>
      dateStr >= bd.start_date && dateStr <= bd.end_date
    )

    if (!blockedDate) return false

    // If blocked date has time slots, check against those
    if (blockedDate.time_slots && blockedDate.time_slots.length > 0) {
      const arrival = manualArrivalData.flightTime
      if (!arrival) {
        // No time selected yet - don't block, let user select time first
        return false
      }
      // Customer-meet time = arrival + 30 min. Block windows must be
      // checked against meet time, not raw arrival (mirrors backend
      // pickup_time_from_arrival).
      const [ah, am] = arrival.split(':').map(Number)
      if (Number.isNaN(ah) || Number.isNaN(am)) return false
      const pickupTime = formatMinutesToTime(ah * 60 + am + 30)
      return blockedDate.time_slots.some(slot =>
        slot.block_pickups && isTimeInSlot(pickupTime, slot)
      )
    }

    // No time slots - use full day blocking
    return blockedDate.block_pickups
  }, [formData.pickupDate, blockedDates, manualArrivalData.flightTime])

  // Get blocked date info for error messages
  const getBlockedDateInfo = (date, isDropoff, time = null) => {
    if (!date || blockedDates.length === 0) return null
    const dateStr = format(date, 'yyyy-MM-dd')

    const blockedDate = blockedDates.find(bd =>
      dateStr >= bd.start_date && dateStr <= bd.end_date
    )

    if (!blockedDate) return null

    // If time slots exist and time is provided, check specific slot
    if (blockedDate.time_slots && blockedDate.time_slots.length > 0 && time) {
      const slot = blockedDate.time_slots.find(slot =>
        (isDropoff ? slot.block_dropoffs : slot.block_pickups) &&
        isTimeInSlot(time, slot)
      )
      if (slot) {
        return {
          ...blockedDate,
          reason: slot.reason || blockedDate.reason,
          blocked_slot: slot
        }
      }
      return null
    }

    // Full day blocking
    if (isDropoff ? blockedDate.block_dropoffs : blockedDate.block_pickups) {
      return blockedDate
    }

    return null
  }

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

  // Fetch blocked dates on mount (get all future blocked dates for next 90 days)
  useEffect(() => {
    const fetchBlockedDates = async () => {
      try {
        // Get blocked dates from today to 90 days in the future
        const today = new Date()
        const futureDate = new Date()
        futureDate.setDate(futureDate.getDate() + 90)

        const params = new URLSearchParams({
          date_from: format(today, 'yyyy-MM-dd'),
          date_to: format(futureDate, 'yyyy-MM-dd'),
        })

        const response = await fetch(`${API_BASE_URL}/api/blocked-dates/check?${params}`)
        if (response.ok) {
          const data = await response.json()
          setBlockedDates(data.blocked_dates || [])
        }
      } catch (error) {
        console.error('Error fetching blocked dates:', error)
      }
    }
    fetchBlockedDates()
  }, [API_BASE_URL])

  // Fetch daily occupancy/capacity for the next 90 days. Drives:
  //   1. Amber tint on date pickers for days at the date-effective online cap.
  //   2. The stay-span "we're full" warning when a customer picks a range
  //      that crosses an over-cap day.
  useEffect(() => {
    const fetchDailyCapacity = async () => {
      try {
        const today = new Date()
        const futureDate = new Date()
        futureDate.setDate(futureDate.getDate() + 90)
        const params = new URLSearchParams({
          date_from: format(today, 'yyyy-MM-dd'),
          date_to: format(futureDate, 'yyyy-MM-dd'),
        })
        const response = await fetch(`${API_BASE_URL}/api/capacity/daily?${params}`)
        if (response.ok) {
          const data = await response.json()
          setDailyOccupancy(data.daily_occupancy || {})
          setDailyThroughOccupancy(data.daily_through_occupancy || {})
          setTimeAwareGate(data.time_aware_gate === true)
          setDailyCapacity(data.daily_capacity || {})
          setOnlineCapacity(data.online_capacity || data.max_capacity || DEFAULT_ONLINE_CAPACITY)
        }
      } catch (error) {
        console.error('Error fetching daily capacity:', error)
      }
    }
    fetchDailyCapacity()
  }, [API_BASE_URL])

  // Drop dismissed entries for dates that aren't currently selected. Lets
  // the customer leave a busy date and return to it later as a "fresh"
  // selection that re-fires the warning, while still suppressing re-pops
  // for a date that hasn't changed since they acknowledged it.
  useEffect(() => {
    const selected = new Set()
    if (formData.dropoffDate) selected.add(isoDateUtil(formData.dropoffDate))
    if (formData.pickupDate) selected.add(isoDateUtil(formData.pickupDate))
    for (const iso of [...dismissedBusyDatesRef.current]) {
      if (!selected.has(iso)) dismissedBusyDatesRef.current.delete(iso)
    }
  }, [formData.dropoffDate, formData.pickupDate])

  // "We're getting full" early-warning gate. When the customer has selected
  // a date (dropoff or pickup) that's not blocked and not at the cap but
  // sits in the 80-99% band, surface a modal so they have a chance to
  // pivot to a quieter day or commit faster. The existing "Sorry, we're
  // full" banner already handles >= 100%. Dismissals are scoped to dates
  // that remain selected (see cleanup effect above) — changing dates then
  // returning re-fires.
  useEffect(() => {
    if (busyWarning) return
    if (!dailyOccupancy || Object.keys(dailyOccupancy).length === 0) return

    const candidates = []
    if (formData.dropoffDate) candidates.push(formData.dropoffDate)
    if (
      formData.pickupDate
      && (!formData.dropoffDate
          || isoDateUtil(formData.pickupDate) !== isoDateUtil(formData.dropoffDate))
    ) {
      candidates.push(formData.pickupDate)
    }

    for (const candidate of candidates) {
      const iso = isoDateUtil(candidate)
      if (dismissedBusyDatesRef.current.has(iso)) continue
      if (isManuallyBlockedUtil(candidate, blockedDates)) continue
      // Skip days the hard "Sorry, we're full" banner owns. With a
      // time-aware backend that's through-count fullness only — a turnover
      // day whose touching count is at/over the cap still has room, so it
      // warns instead. Flag off: touch-at-cap days skip, exactly as before.
      if (isAtCapacityUtil(candidate, hardFullOccupancy, dailyCapacity)) continue
      const pct = getDayOccupancyPercentUtil(candidate, dailyOccupancy, dailyCapacity)
      if (pct >= 80) {
        const count = dailyOccupancy[iso] || 0
        const cap = getOnlineCapacityForDate(candidate, dailyCapacity, onlineCapacity)
        const spacesLeft = Math.max(0, cap - count)
        setBusyWarning({
          // Touching count can exceed the cap on turnover days; the day
          // isn't full (see the through-count skip above), so present it
          // as "almost full" rather than an impossible ">100% capacity".
          percent: Math.min(pct, 100),
          almostFull: pct >= 100,
          level: pct >= 90 ? 'red' : 'amber',
          dateISO: iso,
          formatted: format(candidate, 'EEEE d MMMM yyyy'),
          spacesLeft,
        })
        return
      }
    }
  }, [formData.dropoffDate, formData.pickupDate, dailyOccupancy, hardFullOccupancy, dailyCapacity, onlineCapacity, blockedDates, busyWarning])

  const dismissBusyWarning = () => {
    if (busyWarning?.dateISO) {
      dismissedBusyDatesRef.current.add(busyWarning.dateISO)
    }
    setBusyWarning(null)
  }

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

  // Calculate drop-off time slots (2¾h, 2h, 1½h before departure)
  // Flight Slot Capacity is old booking-system metadata; parking capacity is
  // governed by the date-effective online/manual capacity schedule.
  const dropoffSlots = useMemo(() => {
    if (!selectedDropoffFlight) return []

    // Use overridden departure time if set, otherwise use scheduled time
    const flightTime = departureTimeOverride || selectedDropoffFlight.time
    const [hours, minutes] = flightTime.split(':').map(Number)
    const departureMinutes = hours * 60 + minutes

    // Same-day filtering was removed 2026-05-12 — the new lead-time rule
    // (earliestBookableDate) gates the DATE picker itself, so by the time
    // we get here the drop-off is at least tomorrow and every slot is
    // valid by definition. Slots earlier than the 04:00 floor are clamped
    // up to 04:00 inside buildDropoffSlots.
    return buildDropoffSlots(departureMinutes)
  }, [selectedDropoffFlight, departureTimeOverride])

  // Customer's selected drop-off TIME (HH:MM) — derived from the dropoffSlot
  // id by looking up the matching slot. Drives the time-aware capacity gate.
  const dropoffTime = useMemo(() => {
    if (!formData.dropoffSlot) return null
    const slot = dropoffSlots.find((s) => s.id === formData.dropoffSlot)
    return slot?.time || null
  }, [formData.dropoffSlot, dropoffSlots])

  // Customer's pick-up TIME (HH:MM) — equals arrival_time + 30 min (standard
  // collection convention). Falls back to null if arrival time isn't set.
  const pickupTime = useMemo(() => {
    if (!formData.pickupFlightTime) return null
    const scheduledTime = formData.pickupFlightTime.split('|')[0]
    const arrivalTime = arrivalTimeOverride || scheduledTime
    if (!arrivalTime) return null
    const [hh, mm] = arrivalTime.split(':').map(Number)
    if (Number.isNaN(hh) || Number.isNaN(mm)) return null
    return formatMinutesToTime(hh * 60 + mm + 30)
  }, [formData.pickupFlightTime, arrivalTimeOverride])

  // Fire the time-aware capacity gate once all four inputs (dropoff/pickup
  // dates + times) are settled. Sits AFTER dropoffTime / pickupTime so the
  // dependency array doesn't TDZ them. The backend sweeps event boundaries
  // within the customer's stay and returns peak concurrent occupancy, so a
  // 16:30 drop-off after a 16:00 pickup correctly comes back as allowed.
  useEffect(() => {
    if (!formData.dropoffDate || !formData.pickupDate) {
      setCapacityCheck(null)
      return
    }
    if (formData.pickupDate < formData.dropoffDate) {
      setCapacityCheck(null)
      return
    }
    if (!dropoffTime || !pickupTime) {
      // Not enough info to run a time-aware check yet — clear stale answer.
      setCapacityCheck(null)
      return
    }
    const dropoffDateStr = format(formData.dropoffDate, 'yyyy-MM-dd')
    const pickupDateStr = format(formData.pickupDate, 'yyyy-MM-dd')
    const qs = new URLSearchParams({
      dropoff_date: dropoffDateStr,
      dropoff_time: dropoffTime,
      pickup_date: pickupDateStr,
      pickup_time: pickupTime,
    }).toString()
    let cancelled = false
    fetch(`${API_BASE_URL}/api/capacity/check-slot?${qs}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (cancelled || !data) return
        setCapacityCheck(data)
      })
      .catch(() => {
        // Network failure → leave capacityCheck untouched. Falling through
        // with the previous answer is preferable to flipping the gate
        // mid-flow on a transient hiccup.
      })
    return () => {
      cancelled = true
    }
  }, [formData.dropoffDate, formData.pickupDate, dropoffTime, pickupTime, API_BASE_URL])

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

  // Pricing useEffect lives below, after `selectedArrivalFlight` is declared,
  // because it needs the resolved arrival time to apply the 02:30 cutoff.

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

  // Calculate drop-off slots for manual departure entries
  // Filters out slots that fall within blocked time slots
  const manualDropoffSlots = useMemo(() => {
    if (!showManualDeparture) return []
    if (!isValidTimeFormat(manualDepartureData.flightTime)) return []

    const [hours, minutes] = manualDepartureData.flightTime.split(':').map(Number)
    const departureMinutes = hours * 60 + minutes

    // Same-day filtering was removed 2026-05-12 — earliestBookableDate gates
    // the drop-off date itself, so we no longer prune slots by 4-hour notice.
    // Blocked-date filtering (admin-defined time-slot blocks) still applies.
    const dropoffDateStr = formData.dropoffDate
      ? `${formData.dropoffDate.getFullYear()}-${String(formData.dropoffDate.getMonth() + 1).padStart(2, '0')}-${String(formData.dropoffDate.getDate()).padStart(2, '0')}`
      : ''

    // Find blocked date for this dropoff date
    let blockedDate = null
    if (formData.dropoffDate && blockedDates.length > 0) {
      blockedDate = blockedDates.find(bd =>
        dropoffDateStr >= bd.start_date && dropoffDateStr <= bd.end_date
      )
    }

    // Helper to check if a time is blocked (inline)
    const isTimeBlocked = (timeStr) => {
      if (!blockedDate) return false
      if (!blockedDate.time_slots || blockedDate.time_slots.length === 0) {
        return blockedDate.block_dropoffs
      }
      return blockedDate.time_slots.some(slot => {
        if (!slot.block_dropoffs) return false
        const [checkH, checkM] = timeStr.split(':').map(Number)
        const [startH, startM] = slot.start_time.split(':').map(Number)
        const [endH, endM] = slot.end_time.split(':').map(Number)
        const checkMins = checkH * 60 + checkM
        const startMins = startH * 60 + startM
        const endMins = endH * 60 + endM
        return checkMins >= startMins && checkMins < endMins
      })
    }

    // Shared builder applies the 04:00 floor (clamped slots show as a
    // selectable "Earliest drop-off · 04:00" card, duplicates merged);
    // admin time-slot blocks then filter the clamped display times.
    return buildDropoffSlots(departureMinutes)
      .filter((slot) => !(formData.dropoffDate && isTimeBlocked(slot.time)))
  }, [showManualDeparture, manualDepartureData.flightTime, formData.dropoffDate, blockedDates])

  // RAW landing time for the batched slot check — same priority chain as
  // the pricing fetch (override || manual entry || selected flight) so the
  // slot verdicts and the quote always agree on the return leg. Sent as-is:
  // the BACKEND derives the meet time (+30) and rolls the date past
  // midnight (_exit_window_from_arrival), so a 23:50 landing can't produce
  // a window that ends before the flight lands. The old pickupTime memo
  // only reads the removed flight-picker field and would leave manual
  // customers permanently worst-cased at 23:59.
  const slotCheckArrivalTime = useMemo(() => {
    const arrivalHHMM = arrivalTimeOverride || manualArrivalData.flightTime || selectedArrivalFlight?.time || null
    if (!arrivalHHMM || !isValidTimeFormat(arrivalHHMM)) return null
    return arrivalHHMM
  }, [arrivalTimeOverride, manualArrivalData.flightTime, selectedArrivalFlight])

  // Request key for the batched slot check — inputs that change the answer.
  const slotCheckKey = useMemo(() => {
    if (!formData.dropoffDate || !formData.pickupDate || manualDropoffSlots.length === 0) return null
    if (formData.pickupDate < formData.dropoffDate) return null
    return JSON.stringify({
      d: format(formData.dropoffDate, 'yyyy-MM-dd'),
      p: format(formData.pickupDate, 'yyyy-MM-dd'),
      at: slotCheckArrivalTime || null,
      ts: manualDropoffSlots.map((s) => s.time),
    })
  }, [formData.dropoffDate, formData.pickupDate, slotCheckArrivalTime, manualDropoffSlots])

  // Batched per-slot availability. Re-fires whenever journey details move
  // (return date / arrival time entered later can bring a hidden slot back).
  useEffect(() => {
    if (!slotCheckKey) {
      setSlotAvailability(null)
      return
    }
    const { d, p, at, ts } = JSON.parse(slotCheckKey)
    let cancelled = false
    fetch(`${API_BASE_URL}/api/capacity/check-slots`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dropoff_date: d,
        pickup_date: p,
        ...(at ? { arrival_time: at } : {}),
        dropoff_times: ts,
      }),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (cancelled || !data) return
        const byTime = {}
        for (const slot of data.slots || []) {
          byTime[slot.dropoff_time] = slot.available !== false
        }
        setSlotAvailability({
          key: slotCheckKey,
          timeAwareGate: data.time_aware_gate === true,
          // Whether this verdict used a real landing time or the 23:59
          // worst-case — decides how definitive the full-stop copy can be.
          hadArrivalTime: !!at,
          byTime,
        })
      })
      .catch(() => {
        // Network hiccup → keep whatever we had; the create-intent gate is
        // the backstop, and hiding nothing is the safe display direction.
      })
    return () => {
      cancelled = true
    }
  }, [slotCheckKey, API_BASE_URL])

  // Owner decision (2026-07-02): HIDE unavailable slots rather than show
  // them disabled — 86% of customers are first-time, so a missing option
  // carries no "it was there last time" confusion. Filtering only applies
  // when the answer matches the current inputs AND the backend gate is
  // live; otherwise show everything and let the existing gates decide.
  const visibleManualDropoffSlots = useMemo(() => {
    if (
      !slotAvailability
      || slotAvailability.key !== slotCheckKey
      || slotAvailability.timeAwareGate !== true
    ) {
      return manualDropoffSlots
    }
    return manualDropoffSlots.filter((s) => slotAvailability.byTime[s.time] !== false)
  }, [manualDropoffSlots, slotAvailability, slotCheckKey])

  // All candidate slots checked and none has room — the honest page-1 full
  // stop (replaces discovering it at checkout).
  const allDropoffSlotsFull =
    manualDropoffSlots.length > 0 && visibleManualDropoffSlots.length === 0

  // If the selected slot just got hidden (journey details changed), clear
  // the selection so the flow can't progress on an unavailable time.
  useEffect(() => {
    if (!manualDepartureData.dropoffSlot) return
    if (visibleManualDropoffSlots.some((s) => s.id === manualDepartureData.dropoffSlot)) return
    setManualDepartureData((prev) => ({ ...prev, dropoffSlot: '' }))
  }, [visibleManualDropoffSlots, manualDepartureData.dropoffSlot])

  // Fetch BOH comparison quote when dates and customer handover times change.
  // Lives here (rather than alongside other date useEffects) because it needs
  // selectedArrivalFlight, declared just above.
  useEffect(() => {
    // Abort superseded runs: rapid time edits fire overlapping quote fetches,
    // and a slow OLD response landing last would leave pricingInfo holding a
    // snapshot whose times no longer match the form — payment then 400s with
    // "Airport quote no longer matches" (live incidents 2026-07-02, sessions
    // sess_1782986473371 / sess_1782991984701).
    const abort = new AbortController()
    const fetchPricing = async () => {
      const manualDropoffTime = manualDropoffSlots.find(s => s.id === manualDepartureData.dropoffSlot)?.time || null
      const effectiveDropoffTime = dropoffTime || manualDropoffTime
      const arrivalHHMM = arrivalTimeOverride || manualArrivalData.flightTime || selectedArrivalFlight?.time || null
      let pickupTimeStr = null
      let pickupRollsPastMidnight = false
      if (arrivalHHMM) {
        const [h, m] = arrivalHHMM.split(':').map(Number)
        if (Number.isInteger(h) && Number.isInteger(m)) {
          const totalMins = h * 60 + m + 30
          pickupRollsPastMidnight = totalMins >= 24 * 60
          const displayMins = totalMins % (24 * 60)
          pickupTimeStr = `${String(Math.floor(displayMins / 60)).padStart(2, '0')}:${String(displayMins % 60).padStart(2, '0')}`
        }
      }

      const destination = manualDepartureData.destinationName || manualDepartureData.customDestination || ''

      if (!formData.dropoffDate || !formData.pickupDate || !effectiveDropoffTime || !pickupTimeStr) {
        setPricingInfo(null)
        setAirportQuote(null)
        setPricingError('')
        return
      }

      setPricingLoading(true)
      setPricingError('')
      try {
        const dropoffStr = format(formData.dropoffDate, 'yyyy-MM-dd')
        const quotePickupDate = new Date(actualPickupDate || formData.pickupDate)
        if (pickupRollsPastMidnight) {
          quotePickupDate.setDate(quotePickupDate.getDate() + 1)
        }
        const pickupStr = format(quotePickupDate, 'yyyy-MM-dd')

        const response = await fetch(`${API_BASE_URL}/api/airport-parking/quote`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            entryDate: dropoffStr,
            entryTime: effectiveDropoffTime,
            exitDate: pickupStr,
            exitTime: pickupTimeStr,
            destination,
          }),
          signal: abort.signal,
        })

        if (response.ok) {
          const data = await response.json()
          if (abort.signal.aborted) return
          setAirportQuote(data)
          setPricingInfo(data.pricingInfo)
          setFormData(prev => ({
            ...prev,
            package: 'airport_quote',
          }))
        } else {
          if (abort.signal.aborted) return
          setPricingInfo(null)
          setAirportQuote(null)
          setPricingError('Unable to load live comparison pricing. Please check your times and try again.')
        }
      } catch (error) {
        if (abort.signal.aborted) return
        console.error('Error fetching pricing:', error)
        setPricingInfo(null)
        setAirportQuote(null)
        setPricingError('Unable to load live comparison pricing. Please check your connection and try again.')
      } finally {
        if (!abort.signal.aborted) {
          setPricingLoading(false)
        }
      }
    }
    fetchPricing()
    return () => abort.abort()
  }, [
    formData.dropoffDate,
    formData.pickupDate,
    actualPickupDate,
    arrivalTimeOverride,
    manualArrivalData.flightTime,
    manualDepartureData.flightTime,
    manualDepartureData.dropoffSlot,
    manualDepartureData.destinationName,
    manualDepartureData.customDestination,
    dropoffTime,
    manualDropoffSlots,
    selectedArrivalFlight?.time,
    API_BASE_URL,
  ])

  // Helper function to format minutes to HH:MM
  function formatMinutesToTime(totalMinutes) {
    if (totalMinutes < 0) totalMinutes += 24 * 60 // Handle overnight
    const hours = Math.floor(totalMinutes / 60) % 24
    const mins = totalMinutes % 60
    return `${hours.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}`
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

  // Normalize time to HH:MM format
  const normalizeTime = (timeStr) => {
    if (!timeStr) return ''
    const parts = timeStr.split(':')
    if (parts.length !== 2) return timeStr
    const hours = parts[0].padStart(2, '0')
    const mins = parts[1].padStart(2, '0')
    return `${hours}:${mins}`
  }

  // Handle ambiguous departure time entry (01:00-12:59) - show warning once per session
  const handleAmbiguousDepartureTime = () => {
    if (!departureTimeWarningShownRef.current) {
      departureTimeWarningShownRef.current = true
      sessionStorage.setItem('booking_departureTimeWarningShown', 'true')
      setShowDepartureTimeWarning(true)
    }
  }

  // Remind customers to use the actual landing date/time, shown once per session.
  const handleArrivalTimeStarted = () => {
    if (!arrivalTimeWarningShownRef.current) {
      arrivalTimeWarningShownRef.current = true
      sessionStorage.setItem('booking_arrivalTimeWarningShown', 'true')
      setShowArrivalTimeNotice(true)
    }
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
  const titleCaseFields = ['colour', 'make', 'billingAddress1', 'billingAddress2', 'billingCity', 'billingCounty']

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target
    const processedValue = titleCaseFields.includes(name) ? toTitleCase(value) : value
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : processedValue
    }))

    // Log when T&C checkbox is checked/unchecked (for debugging checkout issues)
    if (name === 'terms') {
      fetch(`${API_BASE_URL}/api/booking/audit-event`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionIdRef.current,
          event: checked ? 'tnc_accepted' : 'tnc_unchecked',
          event_data: {
            customer_email: formData.email,
            customer_name: `${formData.firstName} ${formData.lastName}`,
            timestamp: new Date().toISOString()
          }
        })
      }).catch(err => console.error('Failed to log T&C event:', err))
    }

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

      const selectedFlight = flightsForDropoff.find(f => f.flightKey === value)
      if (selectedFlight && (selectedFlight.capacity_tier === 0 || selectedFlight.is_call_us_only)) {
        console.log('Legacy zero-capacity flight selected:', {
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
        const response = await fetchWithDraftToken(`${API_BASE_URL}/api/customers/${customerId}`, {
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

    // Email changed - reset vehicle since it's linked to old customer,
    // and reset the draft token so the new POST /api/customers below
    // doesn't 403 against the old draft.email / draft.customer_id
    // binding (PR 4c review fix 2026-05-29 — new email = new
    // checkout identity).
    if (emailChanged) {
      console.log('Email changed, creating new customer + resetting vehicle + draft')
      setVehicleId(null)
      resetDraftToken()
    }

    // Create new customer
    try {
      const response = await fetchWithDraftToken(`${API_BASE_URL}/api/customers`, {
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
        const response = await fetchWithDraftToken(`${API_BASE_URL}/api/vehicles/${vehicleId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            customer_id: customerIdToUse,
            registration: formData.registration.toUpperCase(),
            make: formData.make,
            colour: formData.colour,
            tax_status: formData.taxStatus || null,
            mot_status: formData.motStatus || null,
            tax_due_date: formData.taxDueDate || null,
            mot_expiry_date: formData.motExpiryDate || null,
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
      const response = await fetchWithDraftToken(`${API_BASE_URL}/api/vehicles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_id: customerIdToUse,
          registration: formData.registration.toUpperCase(),
          make: formData.make,
          colour: formData.colour,
          tax_status: formData.taxStatus || null,
          mot_status: formData.motStatus || null,
          tax_due_date: formData.taxDueDate || null,
          mot_expiry_date: formData.motExpiryDate || null,
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
      const response = await fetchWithDraftToken(`${API_BASE_URL}/api/customers/${customerIdToUse}/billing`, {
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
      const response = await fetchWithDraftToken(`${API_BASE_URL}/api/vehicles/dvla-lookup`, {
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

        setFormData(prev => ({
          ...prev,
          make: formattedMake,
          colour: formattedColour,
          taxStatus: data.tax_status || null,
          motStatus: data.mot_status || null,
          taxDueDate: data.tax_due_date || null,
          motExpiryDate: data.mot_expiry_date || null,
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

      // Log funnel event when completing Step 1 (flight info)
      if (currentStep === 1) {
        logFunnelEvent('flight_selected', {
          dropoff_date: formData.dropoffDate ? format(formData.dropoffDate, 'yyyy-MM-dd') : null,
          pickup_date: formData.pickupDate ? format(formData.pickupDate, 'yyyy-MM-dd') : null,
          departure_airline: manualDepartureData.airlineName || manualDepartureData.customAirline,
          departure_time: manualDepartureData.flightTime,
          departure_destination: manualDepartureData.destinationName || manualDepartureData.customDestination,
          arrival_airline: manualArrivalData.airlineName || manualArrivalData.customAirline,
          arrival_time: manualArrivalData.flightTime,
          arrival_origin: manualArrivalData.originName || manualArrivalData.customOrigin,
          dropoff_slot: manualDepartureData.dropoffSlot
        })
      }

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
  const isMakeComplete = !!formData.make  // Make comes from DVLA lookup

  // Step 3: Contact + Billing + Vehicle Information (Details page)
  const isStep3Complete = formData.firstName && formData.lastName && isEmailValid && isPhoneValid && isBillingComplete && formData.registration && isMakeComplete && formData.colour

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
  const isStep1Complete = formData.dropoffDate && isDepartureComplete && formData.pickupDate && isArrivalComplete && isCapacityAvailable && !isDropoffDateBlocked && !isPickupDateBlocked && isLeadTimeAllowed && !findBlockedDateInStay
  // Step 2: Package Selection
  const isStep2Complete = formData.package
  // Step 4: Payment
  const isStep4Complete = formData.terms
  const airportPriceValues = (airportQuote?.airportPrices || [])
    .map((product) => Number(product.pricePence))
    .filter((pricePence) => Number.isFinite(pricePence))
  const airportMinPricePence = airportPriceValues.length ? Math.min(...airportPriceValues) : null
  const airportMaxPricePence = airportPriceValues.length ? Math.max(...airportPriceValues) : null
  const airportPriceSummary = airportMinPricePence === null
    ? null
    : airportMinPricePence === airportMaxPricePence
      ? `£${(airportMinPricePence / 100).toFixed(2)}`
      : `£${(airportMinPricePence / 100).toFixed(2)} – £${(airportMaxPricePence / 100).toFixed(2)}`
  const tagPricePence = airportQuote?.tagPricePence ?? pricingInfo?.price_pence ?? (pricingInfo?.price ? Math.floor(pricingInfo.price * 100) : null)
  const airportSavingPct = (bohPricePence) => {
    if (!tagPricePence || !bohPricePence || tagPricePence >= bohPricePence) return null
    const pct = Math.floor(((bohPricePence - tagPricePence) / bohPricePence) * 100)
    return pct > 0 ? pct : null
  }

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
      // Step 3 (Details) validation order: firstName, lastName, email, phone, billingAddress1, billingCity, billingPostcode, registration, make, colour
      if (!formData.firstName) fieldId = 'firstName'
      else if (!formData.lastName) fieldId = 'lastName'
      else if (!isEmailValid) fieldId = 'email'
      else if (!isPhoneValid) fieldId = 'phone'
      else if (!formData.billingAddress1) fieldId = 'billingAddress1'
      else if (!formData.billingCity) fieldId = 'billingCity'
      else if (!formData.billingPostcode) fieldId = manualAddressEntry ? 'billingPostcodeManual' : 'billingPostcode'
      else if (!formData.registration) fieldId = 'registration'
      else if (!isMakeComplete) fieldId = 'registration' // Focus on registration to trigger DVLA lookup
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

    // Show styled confirmation modal to double-check times
    setShowTimeConfirmModal(true)
  }

  // Handle confirmation modal actions
  const handleTimeConfirmProceed = () => {
    setShowTimeConfirmModal(false)
    nextStep()
  }

  const handleTimeConfirmCancel = () => {
    setShowTimeConfirmModal(false)
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

  const validatePromoCodeAgainstBackend = async (code, { logAudit = true } = {}) => {
    const normalizedCode = code.trim()
    if (!normalizedCode) {
      setPromoCodeMessage('Please enter a promo code')
      setPromoCodeValid(false)
      return null
    }

    setPromoCodeValidating(true)
    setPromoCodeMessage('')

    try {
      const response = await fetch(`${import.meta.env.VITE_API_URL}/api/promo/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: normalizedCode }),
      })

      const data = await response.json()

      if (data.valid) {
        setPromoCodeValid(true)
        setPromoCodeDiscount(data.discount_percent)
        setPromoCodeMessage(data.message)
        // Set promo code type from backend response:
        // - 'percentage': Standard percentage discount (e.g., 10% off)
        // - 'free_week': "1 Week Free Parking" - deducts week1_price (free for ≤7 days, partial for >7 days)
        // - 'free_100': "100% Off" - completely free regardless of trip length
        // Fallback to 'free_week' for 100% if backend doesn't provide type
        const discountType = data.discount_type || (data.discount_percent === 100 ? 'free_week' : 'percentage')
        setPromoCodeType(discountType)
        if (logAudit) {
          // Log promo code added
          fetch(`${API_BASE_URL}/api/booking/audit-event`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              session_id: sessionIdRef.current,
              event: 'promo_code_added',
              event_data: {
                promo_code: normalizedCode.toUpperCase(),
                discount_percent: data.discount_percent,
                discount_type: discountType,
                customer_email: formData.email,
                timestamp: new Date().toISOString()
              }
            })
          }).catch(err => console.error('Failed to log promo code added:', err))
        }
        return data
      } else {
        setPromoCodeValid(false)
        setPromoCodeDiscount(0)
        setPromoCodeType('percentage')
        setPromoCodeMessage(data.message)
        return data
      }
    } catch (err) {
      setPromoCodeValid(false)
      setPromoCodeDiscount(0)
      setPromoCodeMessage('Failed to validate promo code')
      return null
    } finally {
      setPromoCodeValidating(false)
    }
  }

  // Promo code validation
  const validatePromoCode = async () => {
    await validatePromoCodeAgainstBackend(promoCode)
  }

  const needsPromoTypeHydration = Boolean(
    promoCodeValid &&
    promoCode.trim() &&
    promoCodeDiscount === 100 &&
    promoCodeType === 'percentage'
  )

  useEffect(() => {
    if (promoTypeHydratedRef.current) return
    promoTypeHydratedRef.current = true

    // Older sessions only stored discount=100 and the default "percentage"
    // type. Revalidate once after a hard refresh so FREEWEEK does not become
    // a full 100% discount on the payment step.
    if (!needsPromoTypeHydration) {
      return
    }

    let cancelled = false
    setPromoTypeHydrating(true)
    validatePromoCodeAgainstBackend(promoCode, { logAudit: false })
      .finally(() => {
        if (!cancelled) setPromoTypeHydrating(false)
      })

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const clearPromoCode = () => {
    // Log promo code removed (only if there was a valid promo code)
    if (promoCodeValid && promoCode.trim()) {
      fetch(`${API_BASE_URL}/api/booking/audit-event`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionIdRef.current,
          event: 'promo_code_removed',
          event_data: {
            promo_code: promoCode.trim().toUpperCase(),
            customer_email: formData.email,
            timestamp: new Date().toISOString()
          }
        })
      }).catch(err => console.error('Failed to log promo code removed:', err))
    }
    setPromoCode('')
    setPromoCodeValid(false)
    setPromoCodeMessage('')
    setPromoCodeDiscount(0)
    setPromoCodeType('percentage')
  }

  const formatDisplayDate = (date) => {
    if (!date) return ''
    return format(date, 'dd/MM/yyyy')
  }

  return (
    <div className={`bookings-new-page${isModal ? ' bookings-new-page--modal' : ''}`}>
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
              <li>Enter your arrival date and time for your flight, so we're ready when you land.</li>
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
                onClick={closeOrHome}
              >
                Back to home
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Time Confirmation Modal - shown before proceeding to step 2 */}
      {showTimeConfirmModal && (
        <div className="time-confirm-modal-overlay">
          <div className="time-confirm-modal">
            <div className="time-confirm-icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="#D9FF00">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
              </svg>
            </div>
            <h2>Please double-check your times</h2>
            <p>
              We rely on the accuracy of the information you provide to ensure a smooth meet and greet experience.
            </p>
            <div className="time-confirm-summary">
              <div className="time-confirm-section">
                <div className="time-confirm-section-title">Departure</div>
                <div className="time-confirm-row">
                  <span className="time-confirm-label">Date:</span>
                  <span className="time-confirm-value">
                    {formData.dropoffDate ? format(formData.dropoffDate, 'EEE, dd MMM yyyy') : '--'}
                  </span>
                </div>
                <div className="time-confirm-row">
                  <span className="time-confirm-label">Flight time:</span>
                  <span className="time-confirm-value">
                    {manualDepartureData.flightTime || '--:--'}
                  </span>
                </div>
                <div className="time-confirm-row">
                  <span className="time-confirm-label">Drop-off time:</span>
                  <span className="time-confirm-value">
                    {manualDepartureData.flightTime && manualDepartureData.dropoffSlot ? (() => {
                      // Same builder as the slot cards, so the confirm modal
                      // shows the clamped (04:00-floor) time the customer chose.
                      const [h, m] = manualDepartureData.flightTime.split(':').map(Number);
                      const slot = buildDropoffSlots(h * 60 + m)
                        .find((s) => s.id === manualDepartureData.dropoffSlot);
                      return slot?.time || '--:--';
                    })() : '--:--'}
                  </span>
                </div>
              </div>
              <div className="time-confirm-section">
                <div className="time-confirm-section-title">Return</div>
                <div className="time-confirm-row">
                  <span className="time-confirm-label">Arrival date:</span>
                  <span className="time-confirm-value">
                    {formData.pickupDate ? format(formData.pickupDate, 'EEE, dd MMM yyyy') : '--'}
                  </span>
                </div>
                <div className="time-confirm-row">
                  <span className="time-confirm-label">Arrival time:</span>
                  <span className="time-confirm-value">
                    {manualArrivalData.flightTime || '--:--'}
                  </span>
                </div>
              </div>
            </div>
            <div className="time-confirm-actions">
              <button
                type="button"
                className="time-confirm-btn-primary"
                onClick={handleTimeConfirmProceed}
              >
                Yes, times are correct
              </button>
              <button
                type="button"
                className="time-confirm-btn-secondary"
                onClick={handleTimeConfirmCancel}
              >
                Let me check again
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Availability warning modal — fires in the 80-99% occupancy band so
          customers know spaces are tight without being hard-blocked. Amber
          for 80-89% (informational), red for 90-99% (more urgent). */}
      {busyWarning && (
        <div className="busy-warning-modal-overlay" onClick={dismissBusyWarning}>
          <div
            className={`busy-warning-modal busy-warning-modal--${busyWarning.level}`}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="busy-warning-title"
          >
            <div className="busy-warning-icon" aria-hidden="true">
              <svg width="44" height="44" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2L1 21h22L12 2zm0 5.5L19.5 19h-15L12 7.5zM11 10v5h2v-5h-2zm0 6v2h2v-2h-2z" />
              </svg>
            </div>
            <h2 id="busy-warning-title">We're getting full</h2>
            {/* Owner copy direction (2026-07-02): a touching count at/over
                the cap reads "almost full" — availability there genuinely
                depends on times, so a definite "100%" would be a lie. The
                time-of-day hint stays generic: which hours are tight moves
                day to day. */}
            {busyWarning.almostFull ? (
              <p className="busy-warning-percent">
                {busyWarning.formatted} is <strong>almost full</strong>.
              </p>
            ) : (
              <p className="busy-warning-percent">
                {busyWarning.formatted} is at <strong>{busyWarning.percent}%</strong> capacity.
              </p>
            )}
            {/* Day-shape wording is safe here: owner's booking-time data
                shows a stable pattern — drop-offs cluster 04:00-07:00,
                pickups drain from noon with the peak wave 23:00-00:00. */}
            <p className="busy-warning-body">
              Availability depends on your journey times — early mornings are
              our busiest for drop-offs, and spaces free up later in the day.
              We suggest booking soon to avoid disappointment.
            </p>
            {/* On a 100%-busy turnover day the touching count leaves no
                "spaces left" to honestly report even though times can still
                fit — omit the line rather than claim 0 and offer Continue. */}
            {busyWarning.spacesLeft > 0 && (
              <p className="busy-warning-spaces">
                We have <strong>{busyWarning.spacesLeft}</strong>{' '}
                {busyWarning.spacesLeft === 1 ? 'space' : 'spaces'} left.
              </p>
            )}
            <button
              type="button"
              className="busy-warning-btn"
              onClick={dismissBusyWarning}
            >
              Continue
            </button>
          </div>
        </div>
      )}

      {!isModal && (
        <nav className="bookings-new-nav">
          <Link to="/" className="logo">
            <img src="/assets/logo.svg" alt="TAG - Book it. Bag it. Tag it." className="logo-svg" />
          </Link>
        </nav>
      )}

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
                  {step === 2 && 'Pricing'}
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

              {/* Vehicle Make - from DVLA lookup */}
              {(formData.registration && (dvlaVerified || dvlaError || formData.make)) && (
                <div className="form-group fade-in">
                  <label htmlFor="make">Vehicle Make <span className="required">*</span></label>
                  {dvlaVerified && formData.make ? (
                    <input
                      type="text"
                      id="make"
                      value={formData.make}
                      readOnly
                      className="readonly-input"
                    />
                  ) : (
                    <input
                      type="text"
                      id="make"
                      name="make"
                      placeholder="e.g. Ford"
                      value={formData.make}
                      onChange={handleChange}
                      className={step1Attempted && !formData.make ? 'input-error' : ''}
                      required
                    />
                  )}
                  {step1Attempted && !isMakeComplete && (
                    <span className="field-error">Vehicle make is required - use Check Reg button</span>
                  )}
                </div>
              )}

              {/* Vehicle Colour - from DVLA lookup or manual entry */}
              {formData.make && (
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
                  // minDate is today (not earliestBookableDate) on purpose:
                  // today / tomorrow stay clickable so the warning banner
                  // below can explain the lead-time rule and route the
                  // customer to the phone. Past dates remain unselectable.
                  minDate={getTodayUK()}
                  placeholderText="Select date"
                  className="date-picker-input"
                  id="dropoffDate"
                  popperPlacement="bottom-start"
                  calendarClassName="fixed-height-calendar"
                  dayClassName={datePickerDayClass}
                  onFocus={(e) => e.target.readOnly = true}
                />
                {!isLeadTimeAllowed && formData.dropoffDate && (() => {
                  const todayUK = getTodayUK()
                  const isSameDay = formData.dropoffDate.getTime() <= todayUK.getTime()
                  return (
                    <div className="blocked-date-message">
                      {isSameDay ? (
                        <p>
                          Sorry, we can't accept same-day bookings. Call{' '}
                          <a href="tel:01202 798710" className="contact-link">01202 798710</a>{' '}
                          and we will try our best to help!
                        </p>
                      ) : (
                        <p>
                          Sorry, bookings placed after 17:00 can't be made for
                          the next day. Call{' '}
                          <a href="tel:01202 798710" className="contact-link">01202 798710</a>{' '}
                          and we will try our best to help!
                        </p>
                      )}
                    </div>
                  )
                })()}
                {isDropoffDateBlocked && formData.dropoffDate && (
                  <div className="blocked-date-message">
                    {(() => {
                      // First potential drop-off for the error message — via the
                      // shared builder so the 04:00 floor applies here too.
                      let firstPotentialTime = null
                      if (manualDepartureData.flightTime && isValidTimeFormat(manualDepartureData.flightTime)) {
                        const [h, m] = manualDepartureData.flightTime.split(':').map(Number)
                        const earliest = buildDropoffSlots(h * 60 + m)[0]
                        if (earliest && (h * 60 + m) - 165 >= 0) {
                          firstPotentialTime = earliest.time
                        }
                      }
                      const blockedInfo = getBlockedDateInfo(formData.dropoffDate, true, firstPotentialTime)
                      if (blockedInfo?.blocked_slot) {
                        return (
                          <p>
                            Sorry, drop-offs are unavailable between {blockedInfo.blocked_slot.start_time} and {blockedInfo.blocked_slot.end_time}
                            {blockedInfo.blocked_slot.reason && ` (${blockedInfo.blocked_slot.reason})`}
                            . Call <a href="tel:01202 798710" className="contact-link">01202 798710</a> and we will try our best to help!
                          </p>
                        )
                      }
                      return (
                        <p>
                          Sorry, we have no availability for drop-offs on {format(formData.dropoffDate, 'EEEE d MMMM yyyy')}.
                          Call <a href="tel:01202 798710" className="contact-link">01202 798710</a> and we will try our best to help!
                        </p>
                      )
                    })()}
                  </div>
                )}
                {/* At-capacity (soft-cap) banner — fires before pickup_date is
                    selected. Until 2026-05-21 the soft cap only surfaced as
                    an amber tint inside the date-picker popup; once the
                    customer closed the picker there was no visible signal
                    and the form let them fill in airline/destination. Once
                    both dates exist, findBlockedDateInStay's stay-span
                    banner takes over (avoids double-rendering). */}
                {!isDropoffDateBlocked && formData.dropoffDate && isLeadTimeAllowed && !findBlockedDateInStay && isDayFull(formData.dropoffDate) && (
                  <div className="blocked-date-message">
                    <p>
                      Sorry, we're full on {format(formData.dropoffDate, 'EEEE d MMMM yyyy')}.
                      Call <a href="tel:01202 798710" className="contact-link">01202 798710</a> and we will try our best to help!
                    </p>
                  </div>
                )}
              </div>

              {/* Flight lookup removed - using direct entry flow */}

              {/* Departure Flight Entry Form. Visible once the customer has
                  picked a drop-off date that's reachable: not lead-time
                  blocked, and not an admin-blocked date where every valid
                  drop-off slot is unavailable (isDropoffDateBlocked is
                  defined as "ALL potential dropoff times are blocked OR
                  full-day block"). Either way the banner above asks them
                  to call; no point letting them fill in the rest. */}
              {showManualDeparture && formData.dropoffDate && isLeadTimeAllowed && !isDropoffDateBlocked && !findBlockedDateInStay && !isDayFull(formData.dropoffDate) && (
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
                        onAmbiguousTime={handleAmbiguousDepartureTime}
                      />
                      <p className="time-format-hint">
                        We use the 24-hour clock for bookings, e.g. 9pm is 21:00.
                      </p>
                      {showDepartureTimeWarning && (
                        <p className="time-format-warning">
                          Just checking – is that morning or evening? We use 24-hour format, so 11pm would be 23:00.
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Owner decision: unavailable slots are HIDDEN, not disabled.
                      All three full → honest page-1 full stop instead of a
                      dead-end at checkout. Definitive wording only when the
                      verdict used a real landing time — the 23:59 worst-case
                      can reopen slots once the arrival time is entered (the
                      arrival form below stays visible: it's gated on the
                      pickup date, not on a selected slot). */}
                  {allDropoffSlotsFull && (
                    <div className="blocked-date-message">
                      {slotAvailability?.hadArrivalTime ? (
                        <p>
                          Sorry, we have no space for this trip. Please call{' '}
                          <a href="tel:01202 798710" className="contact-link">01202 798710</a>{' '}
                          and we'll do our best to help.
                        </p>
                      ) : (
                        <p>
                          We can't see space for these dates yet — add your
                          return flight time below and we'll check your exact
                          times. Or call{' '}
                          <a href="tel:01202 798710" className="contact-link">01202 798710</a>{' '}
                          and we'll do our best to help.
                        </p>
                      )}
                    </div>
                  )}
                  {visibleManualDropoffSlots.length > 0 && (
                    <div className="form-group">
                      <label>Select Drop-off Time <span className="required">*</span></label>
                      <div className="dropoff-slots">
                        {visibleManualDropoffSlots.map(slot => (
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
                      {formData.pickupDate && !isPickupDateBlocked && (
                        <div className="return-date-summary">
                          <span className="return-date-formatted">
                            {format(formData.pickupDate, 'EEEE, d MMMM yyyy')}
                          </span>
                        </div>
                      )}
                      {/* Stay-span warning: dropoff + pickup are both fine, but a day
                          in the middle of the stay is fully booked or manually blocked.
                          Mirrors the server-side gate in /api/payments/create-intent. */}
                      {findBlockedDateInStay && !isDropoffDateBlocked && !isPickupDateBlocked && (
                        <div className="blocked-date-message">
                          <p>
                            Sorry, we're full on {format(findBlockedDateInStay.date, 'EEEE d MMMM yyyy')}, which falls within your selected stay.{' '}
                            Please call <a href="tel:01202 798710" className="contact-link">01202 798710</a> and we'll do our best to help.
                          </p>
                        </div>
                      )}
                      {/* Pickup at-capacity banner — mirrors the dropoff-side
                          soft-cap message added 2026-05-21. Fires for the
                          standalone "I selected a return date that's full"
                          case which findBlockedDateInStay also catches but
                          phrases as a stay-span warning. */}
                      {formData.pickupDate && !isPickupDateBlocked && !findBlockedDateInStay && isDayFull(formData.pickupDate) && (
                        <div className="blocked-date-message">
                          <p>
                            Sorry, we're full on {format(formData.pickupDate, 'EEEE d MMMM yyyy')}.
                            Call <a href="tel:01202 798710" className="contact-link">01202 798710</a> and we will try our best to help!
                          </p>
                        </div>
                      )}
                      {isPickupDateBlocked && formData.pickupDate && (
                        <div className="blocked-date-message">
                          {(() => {
                            const blockedInfo = (() => {
                              const arrival = manualArrivalData.flightTime
                              if (!arrival) return getBlockedDateInfo(formData.pickupDate, false, null)
                              const [ah, am] = arrival.split(':').map(Number)
                              if (Number.isNaN(ah) || Number.isNaN(am)) return getBlockedDateInfo(formData.pickupDate, false, arrival)
                              const meet = formatMinutesToTime(ah * 60 + am + 30)
                              return getBlockedDateInfo(formData.pickupDate, false, meet)
                            })()
                            if (blockedInfo?.blocked_slot) {
                              return (
                                <p>
                                  Sorry, pick-ups are unavailable between {blockedInfo.blocked_slot.start_time} and {blockedInfo.blocked_slot.end_time}
                                  {blockedInfo.blocked_slot.reason && ` (${blockedInfo.blocked_slot.reason})`}
                                </p>
                              )
                            }
                            return <p>Sorry, we have no availability for pick-ups on {format(formData.pickupDate, 'EEEE d MMMM yyyy')}</p>
                          })()}
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}

              {/* Flight-based arrival lookup removed - using direct entry */}

              {/* Return Flight Entry Form */}
              {showManualArrival && formData.pickupDate && !isPickupDateBlocked && !findBlockedDateInStay && !isDayFull(formData.pickupDate) && (
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
                      <div className="arrival-time-field">
                        <MobileTimePicker
                          id="manualArrivalFlightTime"
                          placeholder="e.g., 14:30"
                          value={manualArrivalData.flightTime}
                          label="Arrival Time"
                          onChange={(value) => setManualArrivalData(prev => ({
                            ...prev,
                            flightTime: value
                          }))}
                          onStartEntry={handleArrivalTimeStarted}
                        />
                        <p className="time-format-hint">
                          We use the 24-hour clock for bookings, e.g. 9pm is 21:00.
                        </p>
                        {showArrivalTimeNotice && (
                          <div className="arrival-time-notice" role="status">
                            <p>{ARRIVAL_TIME_NOTICE}</p>
                            <button
                              type="button"
                              className="arrival-time-notice-dismiss"
                              onClick={() => setShowArrivalTimeNotice(false)}
                            >
                              Got it
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                </div>
              )}

              {formData.pickupDate && !isCapacityAvailable && (
                <div className="form-group fade-in">
                  <div className="blocked-date-message">
                    <p>Sorry, we're at capacity around your selected drop-off and pick-up times. Try a different time or date, or email <a href="mailto:sales@tagparking.co.uk" className="contact-link">sales@tagparking.co.uk</a> and we'll do our best to help.</p>
                  </div>
                </div>
              )}

              <div className="form-actions">
                <button
                  type="button"
                  className={`next-btn ${!isStep1Complete ? 'disabled' : ''}`}
                  onClick={handleContinueStep1}
                  disabled={!isStep1Complete}
                >
                  Continue to Pricing
                </button>
              </div>
            </div>
          )}

          {/* Step 2: Package Selection */}
          {currentStep === 2 && (
            <div className="form-section">
              <h2>Pricing</h2>

              {pricingInfo ? (
                <div className="package-summary">
                  <div className="package-card selected tag-price-card">
                    <span className="price-owner-label">Our price</span>
                    <span className="package-price">£{pricingInfo.price.toFixed(2)}</span>
                    <span className="price-owner-note">Tag Meet & Greet</span>

                    <ul className="package-features">
                      <li>Meet & Greet at terminal</li>
                      <li>Secure storage facility</li>
                      <li>24/7 monitoring</li>
                      <li>No hidden fees</li>
                    </ul>
                  </div>
                  {airportQuote?.airportPrices?.length > 0 && (
                    <div className="airport-comparison">
                      <h3>Bournemouth Airport Prices</h3>
                      <p className="airport-comparison-note">
                        {airportPriceSummary || 'checked just now'}
                      </p>
                      <div className="airport-price-list">
                        {airportQuote.airportPrices.map((product) => {
                          const savingPct = airportSavingPct(Number(product.pricePence))
                          return (
                            <div className="airport-price-row" key={`${product.name}-${product.pricePence}`}>
                              <span>{product.name}</span>
                              <div className="airport-price-value">
                                {savingPct !== null && (
                                  <span className="airport-saving-pill">{savingPct}% cheaper</span>
                                )}
                                <strong>{product.priceText || `£${(product.pricePence / 100).toFixed(2)}`}</strong>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}
                </div>
              ) : pricingError ? (
                <div className="loading-message">{pricingError}</div>
              ) : pricingLoading ? (
                <div className="loading-message">Checking live airport prices...</div>
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
                  <span>{formData.colour} {formData.make}</span>
                </div>
                <div className="summary-item">
                  <span>Registration</span>
                  <span>{formData.registration.toUpperCase()}</span>
                </div>
                {promoCodeValid && promoCodeDiscount > 0 && (
                  <>
                    <div className="summary-item subtotal">
                      <span>Subtotal</span>
                      <span>£{pricingInfo ? pricingInfo.price.toFixed(2) : (formData.package === 'quick' ? '99.00' : '150.00')}</span>
                    </div>
                    <div className="summary-item discount">
                      <span>{(() => {
                        // Show different labels based on discount type
                        if (promoCodeType === 'free_100') {
                          return '100% Off'
                        } else if (promoCodeType === 'free_week') {
                          return '1 Week Free Parking'
                        } else {
                          return `Promo Discount (${promoCodeDiscount}%)`
                        }
                      })()}</span>
                      <span className="discount-amount">-£{(() => {
                        const basePrice = pricingInfo ? pricingInfo.price : 0
                        const durationDays = pricingInfo?.duration_days ?? Number.POSITIVE_INFINITY
                        // free_100: full discount regardless of duration
                        if (promoCodeType === 'free_100') {
                          return basePrice.toFixed(2)
                        }
                        // free_week: full discount for <=7 days, week1 price for longer trips
                        if (promoCodeType === 'free_week') {
                          if (durationDays <= 7) {
                            return basePrice.toFixed(2)
                          }
                          const week1BasePrice = pricingInfo?.week1_price || 0
                          return Math.min(week1BasePrice, basePrice).toFixed(2)
                        }
                        // percentage: standard percentage discount
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
                      const durationDays = pricingInfo?.duration_days ?? Number.POSITIVE_INFINITY
                      let discount = 0
                      if (promoCodeValid && promoCodeDiscount > 0) {
                        // free_100: full discount regardless of duration
                        if (promoCodeType === 'free_100') {
                          discount = basePrice
                        }
                        // free_week: full discount for <=7 days, week1 price for longer trips
                        else if (promoCodeType === 'free_week') {
                          if (durationDays <= 7) {
                            discount = basePrice
                          } else {
                            const week1BasePrice = pricingInfo?.week1_price || 0
                            discount = Math.min(week1BasePrice, basePrice)
                          }
                        }
                        // percentage: standard percentage discount
                        else {
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
                      <option value="expectations_travel">Expectations Travel</option>
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
                  <p className="spam-notice">
                    Can't find it after a few minutes? Check your <strong>Promotions</strong>,{' '}
                    <strong>Updates</strong>, and <strong>Spam/Junk</strong> folders, then add{' '}
                    <strong>no-reply@tagparking.co.uk</strong> to your contacts so future emails
                    arrive in your main inbox.
                  </p>
                  <button
                    type="button"
                    className="submit-btn"
                    onClick={() => navigate('/')}
                  >
                    Return to Home
                  </button>
                </div>
              ) : isStep4Complete ? (
                (formData.package === 'airport_quote' && !pricingInfo) || promoTypeHydrating || needsPromoTypeHydration ? (
                  <div className="stripe-loading">
                    <div className="spinner"></div>
                    <p>Loading secure payment...</p>
                  </div>
                ) : (
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
                    promoCodeType={promoCodeValid ? promoCodeType : 'percentage'}
                    pricingInfo={pricingInfo}
                    isLeadTimeAllowed={isLeadTimeAllowed}
                    onPaymentSuccess={handlePaymentSuccess}
                    onPaymentError={handlePaymentError}
                    departureTimeOverride={null}
                    arrivalTimeOverride={null}
                    manualDepartureData={manualDepartureData}
                    manualArrivalData={manualArrivalData}
                  />
                )
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

      {!isModal && (
        <footer className="bookings-new-footer">
          <img src="/assets/logo.svg" alt="TAG" className="footer-logo-small" />
          <p>© 2025 TAG Parking. All rights reserved.</p>
        </footer>
      )}
    </div>
  )
}

export default Bookings
