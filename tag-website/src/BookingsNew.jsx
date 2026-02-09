import { useState, useMemo, useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import DatePicker from 'react-datepicker'
import { format } from 'date-fns'
import { getMakes, getModels } from 'car-info'
import PhoneInput, { isValidPhoneNumber } from 'react-phone-number-input'
import 'react-phone-number-input/style.css'
import StripePayment from './components/StripePayment'
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

// Normalize airline names (merge Ryanair UK into Ryanair)
const normalizeAirlineName = (name) => {
  if (name === 'Ryanair UK') return 'Ryanair'
  return name
}

// Helper to load booking state from sessionStorage
function loadBookingState(key, fallback) {
  try {
    const saved = sessionStorage.getItem(`booking_${key}`)
    if (saved !== null) return JSON.parse(saved)
  } catch (e) { /* ignore parse errors */ }
  return fallback
}

function Bookings() {
  const navigate = useNavigate()
  const [currentStep, setCurrentStep] = useState(() => loadBookingState('step', 1))
  const [paymentComplete, setPaymentComplete] = useState(false)
  const [bookingConfirmation, setBookingConfirmation] = useState(null)
  const [customerId, setCustomerId] = useState(() => loadBookingState('customerId', null))
  const [vehicleId, setVehicleId] = useState(() => loadBookingState('vehicleId', null))
  const [saving, setSaving] = useState(false)
  // Welcome modal state - shown when user clicks Continue from Step 1
  const [showWelcomeModal, setShowWelcomeModal] = useState(false)

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
    // Bookings only available from 16th Feb 2026 (UK time)
    const MIN_BOOKING_DATE = new Date(2026, 1, 16) // month is 0-indexed
    let dropoffDate = saved.dropoffDate ? new Date(saved.dropoffDate) : null
    let pickupDate = saved.pickupDate ? new Date(saved.pickupDate) : null

    // Clear saved dates if they're before the minimum allowed date
    if (dropoffDate && dropoffDate < MIN_BOOKING_DATE) {
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

      return {
        ...f,
        flightKey: `${f.time}|${f.destinationCode}`,
        displayText: `${f.time} ${f.airlineCode}${f.flightNumber} → ${displayDestination}`
      }
    }).sort((a, b) => a.time.localeCompare(b.time))
  }, [flightsForAirline])

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

    const [hours, minutes] = selectedDropoffFlight.time.split(':').map(Number)
    const departureMinutes = hours * 60 + minutes

    const slots = []

    // Early slot: 2¾ hours before (165 minutes) - show if slots available
    const earlyAvailable = selectedDropoffFlight.early_slots_available ??
      (selectedDropoffFlight.is_slot_1_booked === false ? 1 : 0)
    if (earlyAvailable > 0) {
      slots.push({
        id: '165',
        label: '2¾ hours before',
        time: formatMinutesToTime(departureMinutes - 165),
        available: earlyAvailable,
        isLastSlot: selectedDropoffFlight.early_is_last_slot || selectedDropoffFlight.is_last_slot
      })
    }

    // Late slot: 2 hours before (120 minutes) - show if slots available
    const lateAvailable = selectedDropoffFlight.late_slots_available ??
      (selectedDropoffFlight.is_slot_2_booked === false ? 1 : 0)
    if (lateAvailable > 0) {
      slots.push({
        id: '120',
        label: '2 hours before',
        time: formatMinutesToTime(departureMinutes - 120),
        available: lateAvailable,
        isLastSlot: selectedDropoffFlight.late_is_last_slot || selectedDropoffFlight.is_last_slot
      })
    }

    return slots
  }, [selectedDropoffFlight, isCallUsOnly])

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

  // Filter arrivals by airline and destination, then find the best matching return flight
  const filteredArrivalsForDate = useMemo(() => {
    if (!formData.dropoffAirline || !selectedDropoffFlight) return []

    // Filter by same airline (normalized) and origin matching the departure destination
    const matchingFlights = arrivalsForDate.filter(f =>
      normalizeAirlineName(f.airlineName) === formData.dropoffAirline &&
      f.originCode === selectedDropoffFlight.destinationCode
    )

    // If only one or no flights, return as-is
    if (matchingFlights.length <= 1) return matchingFlights

    // Find the best matching return flight based on flight number similarity
    // e.g., departure U22697 should match return U22696 (typically ±1)
    const departureNumeric = parseInt(selectedDropoffFlight.flightNumber.replace(/\D/g, ''), 10)

    // Score each flight by how close the flight number is to the departure
    const scoredFlights = matchingFlights.map(f => {
      const arrivalNumeric = parseInt(f.flightNumber.replace(/\D/g, ''), 10)
      const numDiff = Math.abs(arrivalNumeric - departureNumeric)
      return { ...f, score: numDiff }
    })

    // Sort by score (closest flight number first) and return only the best match
    scoredFlights.sort((a, b) => a.score - b.score)
    return [scoredFlights[0]]
  }, [arrivalsForDate, formData.dropoffAirline, selectedDropoffFlight])

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

      return {
        ...f,
        flightKey: `${f.time}|${f.flightNumber}`,
        isOvernight,
        displayText: `${f.airlineCode}${f.flightNumber} from ${displayOrigin} → arrives ${f.time}${isOvernight ? ' +1' : ''}`
      }
    }).sort((a, b) => a.time.localeCompare(b.time))
  }, [filteredArrivalsForDate])

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
        console.log('Customer saved:', data.customer_id)
      }
      return data.success
    } catch (error) {
      console.error('Error saving customer:', error)
      return false
    }
  }

  const saveVehicle = async () => {
    if (!customerId) return false
    try {
      const response = await fetch(`${API_BASE_URL}/api/vehicles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_id: customerId,
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
        console.log('Vehicle saved:', data.vehicle_id)
      }
      return data.success
    } catch (error) {
      console.error('Error saving vehicle:', error)
      return false
    }
  }

  const saveBillingAddress = async () => {
    if (!customerId) return false
    try {
      const response = await fetch(`${API_BASE_URL}/api/customers/${customerId}/billing`, {
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

      // Build street address (building number + thoroughfare)
      let streetParts = []
      if (selectedAddress.building_number) {
        streetParts.push(selectedAddress.building_number)
      }
      if (selectedAddress.thoroughfare) {
        streetParts.push(selectedAddress.thoroughfare)
      }
      const streetAddress = streetParts.join(' ')

      // If there's a building name (e.g., "Flat 6"), put it on line 1, street on line 2
      if (selectedAddress.building_name) {
        address1 = selectedAddress.building_name
        address2 = streetAddress
      } else {
        // No building name - just use street address on line 1
        address1 = streetAddress
      }

      // If no structured data, fall back to parsing the address string
      if (!address1) {
        const parts = selectedAddress.address.split(', ')
        address1 = parts[0] || ''
        address2 = parts.length > 2 ? parts.slice(1, -2).join(', ') : ''
      }

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

  const nextStep = async () => {
    setSaving(true)
    try {
      // Save data based on current step
      // Save data based on current step
      // Step 1: Your Details (Contact + Vehicle) - save customer, then vehicle
      if (currentStep === 1) {
        await saveCustomer()
        await saveVehicle()
      } else if (currentStep === 3) {
        // Step 4: Payment - save billing address before payment
        await saveBillingAddress()
      }

      // Track booking flow progress in GA
      const stepNames = {
        1: 'continue_to_details',      // Your Details → Trip Details
        2: 'continue_to_details',      // Trip Details → Package
        3: 'continue_to_package_selection'  // Package → Payment
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

  // Step 1: Your Details (Contact + Vehicle)
  const isPhoneValid = formData.phone && isValidPhoneNumber(formData.phone)
  const isEmailValid = formData.email && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)
  const isMakeComplete = formData.make && (formData.make !== 'Other' || formData.customMake)
  const isModelComplete = formData.make === 'Other' ? formData.customModel : (formData.model && (formData.model !== 'Other' || formData.customModel))
  const isStep1Complete = formData.firstName && formData.lastName && isEmailValid && isPhoneValid && formData.registration && isMakeComplete && isModelComplete && formData.colour
  // Step 2: Trip Details
  const isStep2Complete = formData.dropoffDate && formData.dropoffAirline && formData.dropoffFlight && formData.dropoffSlot && formData.pickupDate && formData.pickupFlightTime && isCapacityAvailable
  // Step 3: Package
  const isStep3Complete = formData.package
  // Step 4: Payment (Billing + Payment)
  const isBillingComplete = formData.billingAddress1 && formData.billingCity && formData.billingPostcode && formData.billingCountry
  const isStep4Complete = formData.terms && isBillingComplete

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
      {/* Welcome Modal - shown when user clicks Continue from Step 1 to Step 2 */}
      {showWelcomeModal && (
        <div className="welcome-modal-overlay">
          <div className="welcome-modal">
            <div className="welcome-modal-icon">
              <img src="/assets/departure-icon.webp" alt="Departure" />
            </div>
            <h2>Flight schedules can change.</h2>
            <p>
              Airlines regularly adjust flight times due to demand and seasonal changes. While we do our best to keep the flight information for your trip accurate and up to date, occasional changes can be missed.
            </p>
            <p>
              If any of your flight details change or you're unsure about anything, please get in touch — we're happy to help and make sure everything is aligned for your trip.
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
                    window.gtag('event', 'continue_to_details', {
                      event_category: 'booking_flow',
                      event_label: 'welcome_modal',
                      step_number: 1
                    })
                  }
                  setShowWelcomeModal(false)
                  nextStep()
                }}
              >
                Continue to Trip Details
              </button>
              <button
                type="button"
                className="welcome-modal-back-btn"
                onClick={() => setShowWelcomeModal(false)}
              >
                Go back
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
                  {step === 1 && 'Details'}
                  {step === 2 && 'Trip'}
                  {step === 3 && 'Package'}
                  {step === 4 && 'Payment'}
                </span>
              </div>
            ))}
          </div>
        </div>

        <form className="bookings-new-form" onSubmit={handleSubmit}>
          {/* Step 1: Your Details (Contact + Vehicle) */}
          {currentStep === 1 && (
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
                    required
                  />
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
                    required
                  />
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
                  className={formData.email && !isEmailValid ? 'input-error' : ''}
                  required
                />
                {formData.email && !isEmailValid && (
                  <span className="field-error">Please enter a valid email address</span>
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
                  className={`phone-input ${formData.phone && !isPhoneValid ? 'invalid' : ''}`}
                />
                {formData.phone && !isPhoneValid && (
                  <span className="field-error">Please enter a valid phone number</span>
                )}
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
                      required
                    >
                      <option value="">Select make</option>
                      {carMakes.map(make => (
                        <option key={make} value={make}>{make}</option>
                      ))}
                      <option value="Other">Other</option>
                    </select>
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
                      required
                    />
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
                    required
                  >
                    <option value="">Select model</option>
                    {carModels.map(model => (
                      <option key={model} value={model}>{model}</option>
                    ))}
                    <option value="Other">Other</option>
                  </select>
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
                <button
                  type="button"
                  className="next-btn"
                  onClick={() => setShowWelcomeModal(true)}
                  disabled={!isStep1Complete || saving}
                >
                  {saving ? 'Saving...' : 'Continue to Trip Details'}
                </button>
              </div>
            </div>
          )}

          {/* Step 2: Trip Details */}
          {currentStep === 2 && (
            <div className="form-section">
              <h2>Trip Details</h2>

              <h3 className="section-subtitle">Departure Flight</h3>

              <div className="form-group">
                <label htmlFor="dropoffDate">Drop-off Date</label>
                <DatePicker
                  selected={formData.dropoffDate}
                  onChange={(date) => handleDateChange(date, 'dropoffDate')}
                  dateFormat="dd/MM/yyyy"
                  minDate={new Date(2026, 1, 16)}
                  placeholderText="Select date"
                  className="date-picker-input"
                  id="dropoffDate"
                  popperPlacement="bottom-start"
                  calendarClassName="fixed-height-calendar"
                  onFocus={(e) => e.target.readOnly = true}
                />
                <p className="date-info">Online bookings available from 16th February 2026</p>
              </div>

              {formData.dropoffDate && loadingFlights && (
                <div className="form-group fade-in">
                  <p className="loading-message">Loading available flights...</p>
                </div>
              )}

              {formData.dropoffDate && !loadingFlights && airlinesForDropoff.length === 0 && (
                <div className="form-group fade-in">
                  <p className="no-flights-message">No departure flights available on this date.</p>
                </div>
              )}

              {formData.dropoffDate && !loadingFlights && airlinesForDropoff.length > 0 && (
                <div className="form-group fade-in">
                  <div className="label-with-help">
                    <label htmlFor="dropoffAirline">Select Airline</label>
                    <div className="help-icon-wrapper">
                      <span className="help-icon">?</span>
                      <div className="help-tooltip">
                        Can't find your flight? We're adding more regularly. Email <a href="mailto:sales@tagparking.co.uk">sales@tagparking.co.uk</a> and we'll do our best to help.
                      </div>
                    </div>
                  </div>
                  <select
                    id="dropoffAirline"
                    name="dropoffAirline"
                    value={formData.dropoffAirline}
                    onChange={handleChange}
                  >
                    <option value="">Select airline</option>
                    {airlinesForDropoff.map(airline => (
                      <option key={airline} value={airline}>{airline}</option>
                    ))}
                  </select>
                </div>
              )}

              {formData.dropoffAirline && flightsForDropoff.length > 0 && (
                <div className="form-group fade-in">
                  <label htmlFor="dropoffFlight">Flight</label>
                  <select
                    id="dropoffFlight"
                    name="dropoffFlight"
                    value={formData.dropoffFlight}
                    onChange={handleChange}
                  >
                    <option value="">Select flight</option>
                    {flightsForDropoff.map(flight => (
                      <option key={flight.flightKey} value={flight.flightKey}>
                        {flight.displayText}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {formData.dropoffFlight && isFlightFullyBooked && !isCallUsOnly && (
                <div className="form-group fade-in">
                  <div className="fully-booked-banner">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/>
                    </svg>
                    <div className="fully-booked-content">
                      <strong>Sold out</strong>
                      <p>All online slots for this flight have been booked. Email <a href="mailto:sales@tagparking.co.uk" className="contact-link">sales@tagparking.co.uk</a> and we may still be able to help.</p>
                    </div>
                  </div>
                </div>
              )}

              {formData.dropoffFlight && isCallUsOnly && (
                <div className="form-group fade-in">
                  <div className="fully-booked-banner">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/>
                    </svg>
                    <div className="fully-booked-content">
                      <strong>Online booking not available</strong>
                      <p>We don't offer online booking for this flight yet and we may still be able to accommodate you. Get in touch and we'll do our best to help.</p>
                      <div className="contact-details">
                        <a href="mailto:sales@tagparking.co.uk" className="contact-link">sales@tagparking.co.uk</a>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {formData.dropoffFlight && !isCallUsOnly && !isFlightFullyBooked && dropoffSlots.length > 0 && (
                <div className="form-group fade-in">
                  <label>Select Drop-off Time</label>
                  <div className="dropoff-slots">
                    {dropoffSlots.map(slot => (
                      <label key={slot.id} className="dropoff-slot">
                        <input
                          type="radio"
                          name="dropoffSlot"
                          value={slot.id}
                          checked={formData.dropoffSlot === slot.id}
                          onChange={handleChange}
                        />
                        <div className={`slot-card ${slot.isLastSlot ? 'last-slot' : ''}`}>
                          <div className="slot-info">
                            <span className="slot-time">{slot.time}</span>
                            <span className="slot-label">{slot.label}</span>
                          </div>
                          {slot.isLastSlot && (
                            <span className="last-slot-badge">Last slot available</span>
                          )}
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {formData.dropoffSlot && (
                <>
                  <h3 className="section-subtitle">Return Flight</h3>
                  <p className="return-flight-info">
                    {selectedDropoffFlight && (() => {
                      const parts = selectedDropoffFlight.destinationName.split(', ')
                      if (parts.length > 1) {
                        const countryCode = parts[parts.length - 1]
                        const cityName = parts.slice(0, -1).join(', ')
                        const country = countryNames[countryCode] || countryCode
                        return `${formData.dropoffAirline} from ${cityName}, ${country}`
                      }
                      return `${formData.dropoffAirline} from ${selectedDropoffFlight.destinationName}`
                    })()}
                  </p>

                  <div className="form-group fade-in">
                    <label>Select Return Date</label>
                    <p className="return-date-hint">Choose your return flight date (1-14 days from departure)</p>
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
                          maxDate.setDate(maxDate.getDate() + 14)
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
                          {arrivalFlightsForPickup.length > 0 && pricingLoading && (
                            <span className="return-date-price loading">Calculating price...</span>
                          )}
                          {arrivalFlightsForPickup.length > 0 && !pricingLoading && pricingInfo && (
                            <span className="return-date-price">From £{pricingInfo.price.toFixed(0)}</span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}

              {formData.pickupDate && arrivalFlightsForPickup.length > 0 && (
                <div className="form-group fade-in">
                  <label htmlFor="pickupFlightTime">Return Flight</label>
                  <select
                    id="pickupFlightTime"
                    name="pickupFlightTime"
                    value={formData.pickupFlightTime}
                    onChange={handleChange}
                  >
                    <option value="">Select flight</option>
                    {arrivalFlightsForPickup.map(flight => (
                      <option key={flight.flightKey} value={flight.flightKey}>{flight.displayText}</option>
                    ))}
                  </select>
                </div>
              )}

              {formData.pickupDate && arrivalFlightsForPickup.length === 0 && (
                <div className="form-group fade-in">
                  <div className="fully-booked-banner">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/>
                    </svg>
                    <div className="fully-booked-content">
                      <strong>No return flights available</strong>
                      <p>This route may be seasonal or doesn't operate on your selected return date. Please try a different date or get in touch.</p>
                      <div className="contact-details">
                        <a href="mailto:sales@tagparking.co.uk" className="contact-link">sales@tagparking.co.uk</a>
                      </div>
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
                <button type="button" className="back-btn" onClick={prevStep}>
                  Back
                </button>
                <button
                  type="button"
                  className="next-btn"
                  onClick={nextStep}
                  disabled={!isStep2Complete}
                >
                  Continue to Package Selection
                </button>
              </div>
            </div>
          )}

          {/* Step 3: Your Package & Price */}
          {currentStep === 3 && (
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
                  onClick={nextStep}
                  disabled={!isStep3Complete}
                >
                  Continue to Payment
                </button>
              </div>
            </div>
          )}

          {/* Step 4: Payment (Billing + Payment) */}
          {currentStep === 4 && (
            <div className="form-section">
              <h2>Payment</h2>

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
                  required
                />
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
                    required
                  />
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
                      // pickupFlightTime is a flightKey in format "time|destinationCode"
                      const flightTime = formData.pickupFlightTime.split('|')[0]
                      const [hours, minutes] = flightTime.split(':').map(Number)
                      const landingMinutes = hours * 60 + minutes
                      const pickupTime = formatMinutesToTime(landingMinutes + 45)
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

              <div className="form-group checkbox-group">
                <label className={`checkbox-label ${!isBillingComplete ? 'disabled' : ''}`}>
                  <input
                    type="checkbox"
                    name="terms"
                    checked={formData.terms}
                    onChange={handleChange}
                    disabled={!isBillingComplete}
                    required
                  />
                  <span>I agree to the <Link to="/terms-conditions" target="_blank">Terms & Conditions</Link> and <Link to="/privacy-policy" target="_blank">Privacy Policy</Link></span>
                </label>
                {!isBillingComplete && (
                  <p className="field-hint">Please complete your billing address above first</p>
                )}
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
                <StripePayment
                  formData={formData}
                  selectedFlight={selectedDropoffFlight}
                  selectedArrivalFlight={selectedArrivalFlight}
                  customerId={customerId}
                  vehicleId={vehicleId}
                  sessionId={sessionIdRef.current}
                  promoCode={promoCodeValid ? promoCode : null}
                  promoCodeDiscount={promoCodeValid ? promoCodeDiscount : 0}
                  pricingInfo={pricingInfo}
                  onPaymentSuccess={handlePaymentSuccess}
                  onPaymentError={handlePaymentError}
                />
              ) : (
                <div className="terms-required">
                  {!isBillingComplete && formData.terms && (
                    <p>Please complete your billing address to proceed with payment</p>
                  )}
                  {!formData.terms && (
                    <p>Please accept the Terms & Conditions to proceed with payment</p>
                  )}
                </div>
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
