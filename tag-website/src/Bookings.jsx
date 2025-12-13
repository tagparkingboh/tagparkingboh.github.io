import { useState, useMemo, useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import DatePicker from 'react-datepicker'
import { format } from 'date-fns'
import { getMakes, getModels } from 'car-info'
import PhoneInput from 'react-phone-number-input'
import 'react-phone-number-input/style.css'
import StripePayment from './components/StripePayment'
import 'react-datepicker/dist/react-datepicker.css'
import './Bookings.css'

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

function Bookings() {
  const navigate = useNavigate()
  const [currentStep, setCurrentStep] = useState(1)
  const [paymentComplete, setPaymentComplete] = useState(false)
  const [bookingConfirmation, setBookingConfirmation] = useState(null)
  const [customerId, setCustomerId] = useState(null)
  const [vehicleId, setVehicleId] = useState(null)
  const [saving, setSaving] = useState(false)

  // Session ID for audit trail - persists across the booking flow
  const sessionIdRef = useRef(generateSessionId())
  // DVLA lookup state
  const [dvlaLoading, setDvlaLoading] = useState(false)
  const [dvlaError, setDvlaError] = useState('')
  const [dvlaVerified, setDvlaVerified] = useState(false)
  // Address lookup state
  const [addressLoading, setAddressLoading] = useState(false)
  const [addressError, setAddressError] = useState('')
  const [addressList, setAddressList] = useState([])
  const [showAddressSelect, setShowAddressSelect] = useState(false)
  const [postcodeSearched, setPostcodeSearched] = useState('')
  const [manualAddressEntry, setManualAddressEntry] = useState(false)
  // Promo code state
  const [promoCode, setPromoCode] = useState('')
  const [promoCodeValidating, setPromoCodeValidating] = useState(false)
  const [promoCodeValid, setPromoCodeValid] = useState(false)
  const [promoCodeMessage, setPromoCodeMessage] = useState('')
  const [promoCodeDiscount, setPromoCodeDiscount] = useState(0) // Discount percentage (10)
  const [formData, setFormData] = useState({
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
  })

  // API base URL
  const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

  // Flight data from API
  const [departuresForDate, setDeparturesForDate] = useState([])
  const [arrivalsForDate, setArrivalsForDate] = useState([])
  const [loadingFlights, setLoadingFlights] = useState(false)

  // Parking capacity management
  const MAX_PARKING_SPOTS = 60

  // This would normally come from your database/API
  // For now, simulating with a placeholder
  const [bookedSpots, setBookedSpots] = useState({})

  // Dynamic pricing state
  const [pricingInfo, setPricingInfo] = useState(null)
  const [pricingLoading, setPricingLoading] = useState(false)

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
        return
      }
      setLoadingFlights(true)
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
      }
    }
    fetchDepartures()
  }, [formData.dropoffDate, API_BASE_URL])

  // Get unique airlines for selected date
  const airlinesForDropoff = useMemo(() => {
    const airlines = [...new Set(departuresForDate.map(f => f.airlineName))]
    return airlines.sort()
  }, [departuresForDate])

  // Filter flights by selected airline
  const flightsForAirline = useMemo(() => {
    if (!formData.dropoffAirline) return []
    return departuresForDate.filter(f => f.airlineName === formData.dropoffAirline)
  }, [departuresForDate, formData.dropoffAirline])

  // Get flights with time and destination combined for selected airline
  const flightsForDropoff = useMemo(() => {
    return flightsForAirline.map(f => {
      // Parse destinationName to extract city and country code (e.g., "Faro, PT" or "Edinburgh, SC, GB")
      const parts = f.destinationName.split(', ')
      const countryCode = parts[parts.length - 1]
      let cityName = parts.slice(0, -1).join(', ')
      // Shorten Tenerife-Reinasofia to Tenerife
      if (cityName === 'Tenerife-Reinasofia') cityName = 'Tenerife'
      const countryName = countryNames[countryCode] || countryCode

      return {
        ...f,
        flightKey: `${f.time}|${f.destinationCode}`,
        displayText: `${f.time} ${f.airlineCode}${f.flightNumber} → ${cityName} (${f.destinationCode}), ${countryName}`
      }
    }).sort((a, b) => a.time.localeCompare(b.time))
  }, [flightsForAirline])

  // Get selected flight details
  const selectedDropoffFlight = useMemo(() => {
    if (!formData.dropoffFlight) return null
    return flightsForDropoff.find(f => f.flightKey === formData.dropoffFlight)
  }, [flightsForDropoff, formData.dropoffFlight])

  // Calculate drop-off time slots (2¾h, 2h before departure)
  // Only show available slots (not already booked)
  const dropoffSlots = useMemo(() => {
    if (!selectedDropoffFlight) return []

    const [hours, minutes] = selectedDropoffFlight.time.split(':').map(Number)
    const departureMinutes = hours * 60 + minutes

    const slots = []

    // Slot 1: 2¾ hours before (165 minutes)
    if (!selectedDropoffFlight.is_slot_1_booked) {
      slots.push({ id: '165', label: '2¾ hours before', time: formatMinutesToTime(departureMinutes - 165) })
    }

    // Slot 2: 2 hours before (120 minutes)
    if (!selectedDropoffFlight.is_slot_2_booked) {
      slots.push({ id: '120', label: '2 hours before', time: formatMinutesToTime(departureMinutes - 120) })
    }

    return slots
  }, [selectedDropoffFlight])

  // Check if flight is fully booked (both slots taken)
  const isFlightFullyBooked = useMemo(() => {
    if (!selectedDropoffFlight) return false
    return selectedDropoffFlight.is_slot_1_booked && selectedDropoffFlight.is_slot_2_booked
  }, [selectedDropoffFlight])

  // Fetch arrivals when pick-up date changes
  useEffect(() => {
    const fetchArrivals = async () => {
      if (!formData.pickupDate) {
        setArrivalsForDate([])
        return
      }
      try {
        const dateStr = format(formData.pickupDate, 'yyyy-MM-dd')
        const response = await fetch(`${API_BASE_URL}/api/flights/arrivals/${dateStr}`)
        const data = await response.json()
        setArrivalsForDate(data)
      } catch (error) {
        console.error('Error fetching arrivals:', error)
        setArrivalsForDate([])
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

  // Filter arrivals by airline and destination (from fetched data)
  const filteredArrivalsForDate = useMemo(() => {
    if (!formData.dropoffAirline || !selectedDropoffFlight) return []
    // Filter by same airline and origin matching the departure destination
    return arrivalsForDate.filter(f =>
      f.airlineName === formData.dropoffAirline &&
      f.originCode === selectedDropoffFlight.destinationCode
    )
  }, [arrivalsForDate, formData.dropoffAirline, selectedDropoffFlight])

  // Get arrival flights for pickup with display details (filtered by airline and destination)
  const arrivalFlightsForPickup = useMemo(() => {
    return filteredArrivalsForDate.map(f => {
      // Parse originName to get city
      const parts = f.originName.split(', ')
      let cityName = parts.slice(0, -1).join(', ')
      // Shorten Tenerife-Reinasofia to Tenerife
      if (cityName === 'Tenerife-Reinasofia') cityName = 'Tenerife'

      return {
        ...f,
        flightKey: `${f.time}|${f.flightNumber}`,
        displayText: `${f.airlineCode}${f.flightNumber} from ${cityName} (${f.originCode}) → arrives ${f.time}`
      }
    }).sort((a, b) => a.time.localeCompare(b.time))
  }, [filteredArrivalsForDate])

  // Get selected arrival/return flight details
  const selectedArrivalFlight = useMemo(() => {
    if (!formData.pickupFlightTime) return null
    return arrivalFlightsForPickup.find(f => f.flightKey === formData.pickupFlightTime)
  }, [arrivalFlightsForPickup, formData.pickupFlightTime])

  // Helper function to format minutes to HH:MM
  function formatMinutesToTime(totalMinutes) {
    if (totalMinutes < 0) totalMinutes += 24 * 60 // Handle overnight
    const hours = Math.floor(totalMinutes / 60) % 24
    const mins = totalMinutes % 60
    return `${hours.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}`
  }

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
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
      // Build Address Line 1: combine building name/number with thoroughfare
      let address1Parts = []

      if (selectedAddress.building_name) {
        address1Parts.push(selectedAddress.building_name)
      }
      if (selectedAddress.building_number) {
        address1Parts.push(selectedAddress.building_number)
      }
      if (selectedAddress.thoroughfare) {
        address1Parts.push(selectedAddress.thoroughfare)
      }

      // If no structured data, fall back to parsing the address string
      let address1 = address1Parts.join(' ')
      if (!address1) {
        const parts = selectedAddress.address.split(', ')
        address1 = parts.slice(0, -2).join(', ') // Everything except town and postcode
      }

      setFormData(prev => ({
        ...prev,
        billingAddress1: address1,
        billingAddress2: '', // Leave empty - user can fill if needed
        billingCity: selectedAddress.post_town,
        billingPostcode: selectedAddress.postcode,
        billingCounty: selectedAddress.county || '' // Use county from API
      }))

      setShowAddressSelect(false)
    }
  }

  const nextStep = async () => {
    setSaving(true)
    try {
      // Save data based on current step
      if (currentStep === 1) {
        await saveCustomer()
      } else if (currentStep === 3) {
        await saveVehicle()
      } else if (currentStep === 5) {
        await saveBillingAddress()
      }
      setCurrentStep(prev => Math.min(prev + 1, 6))
      window.scrollTo(0, 0)
    } finally {
      setSaving(false)
    }
  }

  const prevStep = () => {
    setCurrentStep(prev => Math.max(prev - 1, 1))
    window.scrollTo(0, 0)
  }

  // Step 1: Contact Details (first for lead capture)
  const isStep1Complete = formData.firstName && formData.lastName && formData.email && formData.phone
  // Step 2: Trip Details
  const isStep2Complete = formData.dropoffDate && formData.dropoffAirline && formData.dropoffFlight && formData.dropoffSlot && formData.pickupDate && formData.pickupFlightTime && isCapacityAvailable
  // Step 3: Vehicle Details
  const isMakeComplete = formData.make && (formData.make !== 'Other' || formData.customMake)
  const isModelComplete = formData.model && (formData.model !== 'Other' || formData.customModel)
  const isStep3Complete = formData.registration && isMakeComplete && isModelComplete && formData.colour
  // Step 4: Package
  const isStep4Complete = formData.package
  // Step 5: Billing Address
  const isStep5Complete = formData.billingAddress1 && formData.billingCity && formData.billingPostcode && formData.billingCountry
  // Step 6: Payment
  const isStep6Complete = formData.terms

  const handleSubmit = async (e) => {
    e.preventDefault()
    // Form submission is now handled by the StripePayment component
    // This is just a fallback
    console.log('Booking data:', formData)
  }

  const handlePaymentSuccess = (paymentData) => {
    console.log('Payment successful:', paymentData)
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
    <div className="bookings-page">
      <nav className="bookings-nav">
        <Link to="/" className="logo">
          <img src="/assets/logo.svg" alt="TAG - Book it. Bag it. Tag it." className="logo-svg" />
        </Link>
      </nav>

      <div className="bookings-container">
        <h1>Book your Tag</h1>
        <p className="bookings-subtitle">Bournemouth International Airport (BOH)</p>

        <div className="progress-bar">
          <div className="progress-steps">
            {[1, 2, 3, 4, 5, 6].map(step => (
              <div
                key={step}
                className={`progress-step ${currentStep >= step ? 'active' : ''} ${currentStep > step ? 'completed' : ''}`}
              >
                <span className="step-number">{step}</span>
                <span className="step-label">
                  {step === 1 && 'Contact'}
                  {step === 2 && 'Trip'}
                  {step === 3 && 'Vehicle'}
                  {step === 4 && 'Package'}
                  {step === 5 && 'Billing'}
                  {step === 6 && 'Payment'}
                </span>
              </div>
            ))}
          </div>
        </div>

        <form className="bookings-form" onSubmit={handleSubmit}>
          {/* Step 1: Contact Details (first for lead capture) */}
          {currentStep === 1 && (
            <div className="form-section">
              <h2>Your Details</h2>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="firstName">First Name</label>
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
                  <label htmlFor="lastName">Last Name</label>
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
                <label htmlFor="email">Email Address</label>
                <input
                  type="email"
                  id="email"
                  name="email"
                  placeholder="john@example.com"
                  value={formData.email}
                  onChange={handleChange}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="phone">Phone Number</label>
                <PhoneInput
                  international
                  defaultCountry="GB"
                  id="phone"
                  value={formData.phone}
                  onChange={(value) => setFormData(prev => ({ ...prev, phone: value || '' }))}
                  className="phone-input"
                />
              </div>

              <div className="form-actions">
                <button
                  type="button"
                  className="next-btn"
                  onClick={nextStep}
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
                  minDate={new Date()}
                  placeholderText="Select date"
                  className="date-picker-input"
                  id="dropoffDate"
                  popperPlacement="bottom-start"
                  calendarClassName="five-weeks"
                />
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
                  <label htmlFor="dropoffAirline">Select Airline</label>
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

              {formData.dropoffFlight && isFlightFullyBooked && (
                <div className="form-group fade-in">
                  <div className="fully-booked-banner">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
                    </svg>
                    <div className="fully-booked-content">
                      <strong>Drop-off slots fully reserved</strong>
                      <p>We may be able to accommodate your booking! Contact us and we'll see if we can find a drop-off time that suits your schedule.</p>
                      <div className="contact-details">
                        <a href="mailto:booking@tagparking.co.uk" className="contact-link">booking@tagparking.co.uk</a>
                        <a href="tel:+447739106145" className="contact-link">+44 (0)7739 106145</a>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {formData.dropoffFlight && !isFlightFullyBooked && dropoffSlots.length > 0 && (
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
                        <div className="slot-card">
                          <span className="slot-time">{slot.time}</span>
                          <span className="slot-label">{slot.label}</span>
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
                      const countryCode = parts[parts.length - 1]
                      const cityName = parts.slice(0, -1).join(', ')
                      const country = countryNames[countryCode] || countryCode
                      return `${formData.dropoffAirline} from ${cityName} (${selectedDropoffFlight.destinationCode}), ${country}`
                    })()}
                  </p>

                  <div className="form-group fade-in">
                    <label>Select Trip Duration</label>
                    <div className="duration-options">
                      {[
                        { days: 7, label: '1 Week' },
                        { days: 14, label: '2 Weeks' },
                      ].map(({ days, label }) => {
                        const pickupDate = new Date(formData.dropoffDate)
                        pickupDate.setDate(pickupDate.getDate() + days)
                        const isSelected = formData.pickupDate &&
                          format(formData.pickupDate, 'yyyy-MM-dd') === format(pickupDate, 'yyyy-MM-dd')

                        return (
                          <label key={days} className="duration-option">
                            <input
                              type="radio"
                              name="tripDuration"
                              value={days}
                              checked={isSelected}
                              onChange={() => handleDateChange(pickupDate, 'pickupDate')}
                            />
                            <div className={`duration-card ${isSelected ? 'selected' : ''}`}>
                              <span className="duration-label">{label}</span>
                              <span className="duration-date">Return: {format(pickupDate, 'EEE, d MMM yyyy')}</span>
                              {pricingLoading && isSelected && (
                                <span className="duration-price loading">Calculating...</span>
                              )}
                              {!pricingLoading && pricingInfo && isSelected && (
                                <span className="duration-price">From £{pricingInfo.price.toFixed(0)}</span>
                              )}
                            </div>
                          </label>
                        )
                      })}
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
                  <p className="no-flights-message">No return flights available on this date. Please select a different date.</p>
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
                  Continue to Vehicle Details
                </button>
              </div>
            </div>
          )}

          {/* Step 3: Vehicle Details */}
          {currentStep === 3 && (
            <div className="form-section">
              <h2>Vehicle Details</h2>

              <div className="form-group">
                <label htmlFor="registration">Registration Number</label>
                <div className="registration-input-group">
                  <input
                    type="text"
                    id="registration"
                    name="registration"
                    placeholder="e.g. AB12 CDE"
                    value={formData.registration}
                    onChange={(e) => {
                      handleChange(e)
                      // Reset DVLA state when registration changes
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
                  <label htmlFor="make">Vehicle Make</label>
                  {dvlaVerified && formData.make !== 'Other' ? (
                    <input
                      type="text"
                      id="make"
                      value={formData.make}
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

              {formData.make === 'Other' && (
                <div className="form-group fade-in">
                  <label htmlFor="customMake">Enter Vehicle Make</label>
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

              {/* Colour comes after Make (from DVLA or manual entry) */}
              {((formData.make && formData.make !== 'Other') || (formData.make === 'Other' && formData.customMake)) && (
                <div className="form-group fade-in">
                  <label htmlFor="colour">Vehicle Colour</label>
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

              {/* Model comes after Colour */}
              {formData.make && formData.make !== 'Other' && formData.colour && (
                <div className="form-group fade-in">
                  <label htmlFor="model">Vehicle Model</label>
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
                  <label htmlFor="customModel">Enter Vehicle Model</label>
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
                  <label htmlFor="customModel">Enter Vehicle Model</label>
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
                  onClick={nextStep}
                  disabled={!isStep3Complete || saving}
                >
                  {saving ? 'Saving...' : 'Continue to Package Selection'}
                </button>
              </div>
            </div>
          )}

          {/* Step 4: Your Package & Price */}
          {currentStep === 4 && (
            <div className="form-section">
              <h2>Your Package</h2>

              {pricingInfo ? (
                <div className="package-summary">
                  <div className="package-card selected">
                    <span className="package-label">
                      {pricingInfo.package_name.toUpperCase()}
                    </span>
                    <span className="package-price">£{pricingInfo.price.toFixed(0)}</span>
                    <span className="package-period">/ {pricingInfo.duration_days} days</span>

                    {pricingInfo.advance_tier === 'early' && (
                      <span className="price-badge early">Early Bird Price</span>
                    )}
                    {pricingInfo.advance_tier === 'standard' && (
                      <span className="price-badge standard">Standard Price</span>
                    )}
                    {pricingInfo.advance_tier === 'late' && (
                      <span className="price-badge late">Late Booking</span>
                    )}

                    <p className="price-tier-info">
                      Booking {pricingInfo.days_in_advance} days in advance
                    </p>

                    <ul className="package-features">
                      <li>Meet & Greet at terminal</li>
                      <li>Secure storage facility</li>
                      <li>24/7 monitoring</li>
                      <li>No hidden fees</li>
                    </ul>
                  </div>

                  <div className="pricing-tiers-info">
                    <h4>Pricing based on advance booking:</h4>
                    <div className="tier-list">
                      <div className={`tier ${pricingInfo.advance_tier === 'early' ? 'active' : ''}`}>
                        <span className="tier-label">14+ days ahead</span>
                        <span className="tier-price">£{pricingInfo.all_prices.early.toFixed(0)}</span>
                      </div>
                      <div className={`tier ${pricingInfo.advance_tier === 'standard' ? 'active' : ''}`}>
                        <span className="tier-label">7-13 days ahead</span>
                        <span className="tier-price">£{pricingInfo.all_prices.standard.toFixed(0)}</span>
                      </div>
                      <div className={`tier ${pricingInfo.advance_tier === 'late' ? 'active' : ''}`}>
                        <span className="tier-label">Under 7 days</span>
                        <span className="tier-price">£{pricingInfo.all_prices.late.toFixed(0)}</span>
                      </div>
                    </div>
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
                  disabled={!isStep4Complete}
                >
                  Continue to Billing Address
                </button>
              </div>
            </div>
          )}

          {/* Step 5: Billing Address */}
          {currentStep === 5 && (
            <div className="form-section">
              <h2>Billing Address</h2>
              <p className="section-info">This address will be used for payment verification.</p>

              {/* Postcode Lookup - show unless manual entry mode */}
              {!manualAddressEntry && (
                <>
                  <div className="form-group">
                    <label htmlFor="billingPostcode">Postcode</label>
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
                <label htmlFor="billingAddress1">Address Line 1</label>
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
                <label htmlFor="billingAddress2">Address Line 2 (optional)</label>
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
                  <label htmlFor="billingCity">City</label>
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
                  <label htmlFor="billingCounty">County (optional)</label>
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

              {/* Only show postcode input for manual entry if non-UK country */}
              {manualAddressEntry && formData.billingCountry !== 'United Kingdom' && (
                <div className="form-group">
                  <label htmlFor="billingPostcodeManual">Postcode / ZIP Code</label>
                  <input
                    type="text"
                    id="billingPostcodeManual"
                    name="billingPostcode"
                    placeholder="Enter postcode"
                    value={formData.billingPostcode}
                    onChange={handleChange}
                  />
                </div>
              )}

              <div className="form-group">
                <label htmlFor="billingCountry">Country</label>
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

              <div className="form-actions">
                <button type="button" className="back-btn" onClick={prevStep}>
                  Back
                </button>
                <button
                  type="button"
                  className="next-btn"
                  onClick={nextStep}
                  disabled={!isStep5Complete || saving}
                >
                  {saving ? 'Saving...' : 'Continue to Payment'}
                </button>
              </div>
            </div>
          )}

          {/* Step 6: Payment */}
          {currentStep === 6 && (
            <div className="form-section">
              <h2>Payment</h2>

              <div className="booking-summary">
                <h3>Booking Summary</h3>
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
                    {formatDisplayDate(formData.pickupDate)}
                    {formData.pickupFlightTime && (() => {
                      // pickupFlightTime is a flightKey in format "time|destinationCode"
                      const flightTime = formData.pickupFlightTime.split('|')[0]
                      const [hours, minutes] = flightTime.split(':').map(Number)
                      const landingMinutes = hours * 60 + minutes
                      const pickupStart = formatMinutesToTime(landingMinutes + 35)
                      const pickupEnd = formatMinutesToTime(landingMinutes + 60)
                      return <> between {pickupStart} - {pickupEnd}</>
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
                  <span>{pricingInfo?.package_name || (formData.package === 'quick' ? '1 Week' : '2 Weeks')}</span>
                </div>
                {promoCodeValid && promoCodeDiscount > 0 && (
                  <>
                    <div className="summary-item subtotal">
                      <span>Subtotal</span>
                      <span>£{pricingInfo ? pricingInfo.price.toFixed(2) : (formData.package === 'quick' ? '99.00' : '135.00')}</span>
                    </div>
                    <div className="summary-item discount">
                      <span>Promo Discount ({promoCodeDiscount}%)</span>
                      <span className="discount-amount">-£{((pricingInfo ? pricingInfo.price : (formData.package === 'quick' ? 99 : 135)) * promoCodeDiscount / 100).toFixed(2)}</span>
                    </div>
                  </>
                )}
                <div className="summary-item total">
                  <span>Total</span>
                  <span>
                    £{(() => {
                      const basePrice = pricingInfo ? pricingInfo.price : (formData.package === 'quick' ? 99 : 135)
                      const discount = promoCodeValid && promoCodeDiscount > 0 ? basePrice * promoCodeDiscount / 100 : 0
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
                  <button
                    type="button"
                    className="submit-btn"
                    onClick={() => navigate('/')}
                  >
                    Return to Home
                  </button>
                </div>
              ) : formData.terms ? (
                <StripePayment
                  formData={formData}
                  selectedFlight={selectedDropoffFlight}
                  selectedArrivalFlight={selectedArrivalFlight}
                  customerId={customerId}
                  vehicleId={vehicleId}
                  sessionId={sessionIdRef.current}
                  promoCode={promoCodeValid ? promoCode : null}
                  promoCodeDiscount={promoCodeValid ? promoCodeDiscount : 0}
                  onPaymentSuccess={handlePaymentSuccess}
                  onPaymentError={handlePaymentError}
                />
              ) : (
                <div className="terms-required">
                  <p>Please accept the Terms & Conditions to proceed with payment</p>
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

      <footer className="bookings-footer">
        <img src="/assets/logo.svg" alt="TAG" className="footer-logo-small" />
        <p>© 2025 TAG Parking. All rights reserved.</p>
      </footer>
    </div>
  )
}

export default Bookings
