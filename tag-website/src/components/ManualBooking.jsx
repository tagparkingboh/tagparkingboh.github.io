import { useState, useMemo, useEffect } from 'react'
import DatePicker from 'react-datepicker'
import { format } from 'date-fns'
import 'react-datepicker/dist/react-datepicker.css'
import MobileTimePicker from './MobileTimePicker'
import './ManualBooking.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function ManualBooking({ token }) {
  const [formData, setFormData] = useState({
    firstName: '',
    lastName: '',
    email: '',
    phone: '',
    // Address
    billingPostcode: '',
    billingAddress1: '',
    billingAddress2: '',
    billingCity: '',
    billingCounty: '',
    billingCountry: 'United Kingdom',
    // Vehicle
    registration: '',
    make: '',
    colour: '',
    // Departure flight details
    dropoffDate: null,
    dropoffAirline: '',
    customDropoffAirline: '',
    dropoffDestination: '',
    customDropoffDestination: '',
    dropoffFlightNumber: '',
    departureTime: '',  // Flight departure time (HH:MM string)
    dropoffSlot: '',      // 'early' (2.75h), 'standard' (2h), or 'late' (1.5h)
    // Return flight details
    pickupDate: null,
    pickupAirline: '',
    customPickupAirline: '',
    pickupOrigin: '',
    customPickupOrigin: '',
    pickupFlightNumber: '',
    arrivalTime: '',    // Flight arrival time (HH:MM string)
    // Payment
    promoCode: '',
    stripePaymentLink: '',
    amount: '',
    notes: '',
  })

  const [submitting, setSubmitting] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState('')

  // DVLA lookup state
  const [dvlaLoading, setDvlaLoading] = useState(false)
  const [dvlaError, setDvlaError] = useState('')
  const [dvlaVerified, setDvlaVerified] = useState(false)

  // Address lookup state
  const [addressLoading, setAddressLoading] = useState(false)
  const [addressError, setAddressError] = useState('')
  const [addressList, setAddressList] = useState([])
  const [showAddressSelect, setShowAddressSelect] = useState(false)

  // Airlines and destinations from booking API
  const [availableAirlines, setAvailableAirlines] = useState([])
  const [availableDestinations, setAvailableDestinations] = useState([])

  // Auto-pricing state
  const [pricingLoading, setPricingLoading] = useState(false)
  const [calculatedPrice, setCalculatedPrice] = useState(null)

  // Promo code state
  const [promoValidating, setPromoValidating] = useState(false)
  const [promoValid, setPromoValid] = useState(null)
  const [promoDiscount, setPromoDiscount] = useState(null)
  const [promoMessage, setPromoMessage] = useState('')

  // Fetch airlines and destinations
  const fetchAirlinesAndDestinations = async () => {
    try {
      const [airlinesRes, destinationsRes] = await Promise.all([
        fetch(`${API_URL}/api/booking/airlines`),
        fetch(`${API_URL}/api/booking/destinations`)
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

  // Fetch on mount
  useEffect(() => {
    fetchAirlinesAndDestinations()
  }, [])

  // Refresh form - reset all fields and re-fetch data
  const handleRefresh = async () => {
    setFormData({
      firstName: '',
      lastName: '',
      email: '',
      phone: '',
      billingPostcode: '',
      billingAddress1: '',
      billingAddress2: '',
      billingCity: '',
      billingCounty: '',
      billingCountry: 'United Kingdom',
      registration: '',
      make: '',
      colour: '',
      dropoffDate: null,
      dropoffAirline: '',
      customDropoffAirline: '',
      dropoffDestination: '',
      customDropoffDestination: '',
      dropoffFlightNumber: '',
      departureTime: '',
      dropoffSlot: '',
      pickupDate: null,
      pickupAirline: '',
      customPickupAirline: '',
      pickupOrigin: '',
      customPickupOrigin: '',
      pickupFlightNumber: '',
      arrivalTime: '',
      promoCode: '',
      stripePaymentLink: '',
      amount: '',
      notes: '',
    })
    setSuccess(false)
    setError('')
    setDvlaVerified(false)
    setDvlaError('')
    setAddressList([])
    setShowAddressSelect(false)
    setAddressError('')
    setPromoValid(null)
    setPromoMessage('')
    setPromoDiscount(null)
    setCalculatedPrice(null)
    await fetchAirlinesAndDestinations()
  }

  // Auto-sync departure destination to pickup origin
  useEffect(() => {
    if (formData.dropoffDestination) {
      if (formData.dropoffDestination === 'Other') {
        setFormData(prev => ({
          ...prev,
          pickupOrigin: 'Other',
          customPickupOrigin: prev.customDropoffDestination || ''
        }))
      } else {
        setFormData(prev => ({
          ...prev,
          pickupOrigin: prev.dropoffDestination,
          customPickupOrigin: ''
        }))
      }
    }
  }, [formData.dropoffDestination, formData.customDropoffDestination])

  // Auto-sync departure airline to pickup airline
  useEffect(() => {
    if (formData.dropoffAirline) {
      if (formData.dropoffAirline === 'Other') {
        setFormData(prev => ({
          ...prev,
          pickupAirline: 'Other',
          customPickupAirline: prev.customDropoffAirline || ''
        }))
      } else {
        setFormData(prev => ({
          ...prev,
          pickupAirline: prev.dropoffAirline,
          customPickupAirline: ''
        }))
      }
    }
  }, [formData.dropoffAirline, formData.customDropoffAirline])

  // Auto-calculate price when both dates are set
  useEffect(() => {
    const calculatePrice = async () => {
      if (!formData.dropoffDate || !formData.pickupDate) {
        setCalculatedPrice(null)
        return
      }

      const duration = Math.round((formData.pickupDate - formData.dropoffDate) / (1000 * 60 * 60 * 24))
      if (duration < 1 || duration > 60) {
        setCalculatedPrice(null)
        return
      }

      setPricingLoading(true)
      try {
        const dropoffStr = format(formData.dropoffDate, 'yyyy-MM-dd')
        const pickupStr = format(formData.pickupDate, 'yyyy-MM-dd')

        // Customer-meet time = arrival + 30. Backend uses this to apply the
        // 02:30 cutoff (early-morning pickups bill as the previous day).
        let pickupTimeStr = null
        if (formData.arrivalTime) {
          const [h, m] = formData.arrivalTime.split(':').map(Number)
          if (Number.isInteger(h) && Number.isInteger(m)) {
            const totalMins = (h * 60 + m + 30) % (24 * 60)
            pickupTimeStr = `${String(Math.floor(totalMins / 60)).padStart(2, '0')}:${String(totalMins % 60).padStart(2, '0')}`
          }
        }

        const response = await fetch(`${API_URL}/api/pricing/calculate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            drop_off_date: dropoffStr,
            pickup_date: pickupStr,
            ...(pickupTimeStr ? { pickup_time: pickupTimeStr } : {}),
          }),
        })
        if (response.ok) {
          const data = await response.json()
          setCalculatedPrice(data.price)
          setFormData(prev => {
            if (!prev.amount || prev.amount === '' || prev.amount === String(calculatedPrice)) {
              return { ...prev, amount: String(data.price) }
            }
            return prev
          })
        }
      } catch (error) {
        console.error('Error calculating price:', error)
      } finally {
        setPricingLoading(false)
      }
    }

    calculatePrice()
  }, [formData.dropoffDate, formData.pickupDate, formData.arrivalTime])

  // Parse time string (HH:MM) to hours and minutes
  const parseTimeString = (timeStr) => {
    if (!timeStr || !timeStr.includes(':')) return null
    const [hours, minutes] = timeStr.split(':').map(Number)
    if (isNaN(hours) || isNaN(minutes)) return null
    return { hours, minutes }
  }

  // Helper to format minutes to time, handling overnight (negative) values
  const formatMinutesToTime = (totalMinutes) => {
    let mins = totalMinutes
    const isOvernight = mins < 0
    if (isOvernight) mins += 24 * 60 // Add 24 hours for previous day
    const hours = Math.floor(mins / 60) % 24
    const minutes = mins % 60
    return {
      time: `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`,
      isOvernight
    }
  }

  // Calculate drop-off slots based on departure time
  const dropoffSlots = useMemo(() => {
    const parsed = parseTimeString(formData.departureTime)
    if (!parsed) return []
    const depTotalMinutes = parsed.hours * 60 + parsed.minutes

    const slots = []

    // Early slot (2.75 hours = 165 minutes before departure)
    const earlyResult = formatMinutesToTime(depTotalMinutes - 165)
    slots.push({
      id: 'early',
      time: earlyResult.time,
      label: `Early - ${earlyResult.time} (2¾ hours before)${earlyResult.isOvernight ? ' *' : ''}`,
      isOvernight: earlyResult.isOvernight
    })

    // Standard slot (2 hours = 120 minutes before departure)
    const standardResult = formatMinutesToTime(depTotalMinutes - 120)
    slots.push({
      id: 'standard',
      time: standardResult.time,
      label: `Standard - ${standardResult.time} (2 hours before)${standardResult.isOvernight ? ' *' : ''}`,
      isOvernight: standardResult.isOvernight
    })

    // Late slot (1.5 hours = 90 minutes before departure)
    const lateResult = formatMinutesToTime(depTotalMinutes - 90)
    slots.push({
      id: 'late',
      time: lateResult.time,
      label: `Late - ${lateResult.time} (1½ hours before)${lateResult.isOvernight ? ' *' : ''}`,
      isOvernight: lateResult.isOvernight
    })

    return slots
  }, [formData.departureTime])

  // Calculate pickup time (arrival + 30 minutes)
  const calculatedPickupTime = useMemo(() => {
    const parsed = parseTimeString(formData.arrivalTime)
    if (!parsed) return null
    const totalMinutes = parsed.hours * 60 + parsed.minutes + 30
    const pickupHours = Math.floor(totalMinutes / 60) % 24
    const pickupMins = totalMinutes % 60
    return `${String(pickupHours).padStart(2, '0')}:${String(pickupMins).padStart(2, '0')}`
  }, [formData.arrivalTime])

  // Convert string to Title Case
  const toTitleCase = (str) => {
    if (!str) return str
    return str.toLowerCase().replace(/\b\w/g, char => char.toUpperCase())
  }

  const titleCaseFields = ['colour', 'make', 'billingAddress1', 'billingAddress2', 'billingCity', 'billingCounty', 'customDropoffAirline', 'customDropoffDestination', 'customPickupAirline', 'customPickupOrigin']

  const handleChange = (e) => {
    const { name, value } = e.target
    const processedValue = titleCaseFields.includes(name) ? toTitleCase(value) : value
    setFormData(prev => ({
      ...prev,
      [name]: processedValue
    }))
  }

  const handleDateChange = (date, field) => {
    setFormData(prev => ({
      ...prev,
      [field]: date
    }))

    // Reset slot when departure time changes
    if (field === 'departureTime') {
      setFormData(prev => ({
        ...prev,
        departureTime: date,
        dropoffSlot: ''
      }))
    }
  }

  // DVLA vehicle lookup
  const lookupVehicle = async () => {
    if (!formData.registration || formData.registration.length < 2) {
      setDvlaError('Please enter a valid registration number')
      return
    }

    setDvlaLoading(true)
    setDvlaError('')
    setDvlaVerified(false)

    try {
      const response = await fetch(`${API_URL}/api/vehicles/dvla-lookup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ registration: formData.registration }),
      })

      const data = await response.json()

      if (data.success && data.make) {
        const formattedMake = data.make.charAt(0).toUpperCase() + data.make.slice(1).toLowerCase()
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
      const response = await fetch(`${API_URL}/api/address/postcode-lookup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ postcode })
      })

      const data = await response.json()

      if (data.success && data.addresses.length > 0) {
        setAddressList(data.addresses)
        setShowAddressSelect(true)
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

  // Validate promo code
  const validatePromoCode = async () => {
    if (!formData.promoCode.trim()) {
      setPromoValid(null)
      setPromoMessage('')
      setPromoDiscount(null)
      return
    }

    setPromoValidating(true)
    setPromoMessage('')

    try {
      const response = await fetch(`${API_URL}/api/promo/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: formData.promoCode.trim() }),
      })

      const data = await response.json()

      if (data.valid) {
        setPromoValid(true)
        setPromoMessage(data.message)

        if (calculatedPrice && formData.dropoffDate && formData.pickupDate) {
          const duration = Math.round((formData.pickupDate - formData.dropoffDate) / (1000 * 60 * 60 * 24))

          if (data.discount_percent === 100) {
            if (duration <= 7) {
              setPromoDiscount({ percent: 100, amount: calculatedPrice, isFree: true })
              setFormData(prev => ({ ...prev, amount: '0' }))
            } else {
              const pricingResponse = await fetch(`${API_URL}/api/pricing`)
              const pricing = await pricingResponse.json()
              const week1Base = pricing.week1_base_price || 79
              const discountAmount = Math.min(week1Base, calculatedPrice)
              const finalPrice = calculatedPrice - discountAmount
              setPromoDiscount({ percent: 100, amount: discountAmount, isFree: false })
              setFormData(prev => ({ ...prev, amount: String(finalPrice) }))
            }
          } else {
            const discountAmount = calculatedPrice * data.discount_percent / 100
            const finalPrice = calculatedPrice - discountAmount
            setPromoDiscount({ percent: data.discount_percent, amount: discountAmount, isFree: false })
            setFormData(prev => ({ ...prev, amount: String(finalPrice.toFixed(2)) }))
          }
        }
      } else {
        setPromoValid(false)
        setPromoMessage(data.message || 'Invalid promo code')
        setPromoDiscount(null)
      }
    } catch (error) {
      console.error('Promo validation error:', error)
      setPromoValid(false)
      setPromoMessage('Unable to validate promo code')
      setPromoDiscount(null)
    } finally {
      setPromoValidating(false)
    }
  }

  // Remove promo code and reset price to original
  const removePromoCode = () => {
    setFormData(prev => ({
      ...prev,
      promoCode: '',
      amount: calculatedPrice ? String(calculatedPrice) : ''
    }))
    setPromoValid(null)
    setPromoMessage('')
    setPromoDiscount(null)
  }

  // Handle address selection
  const handleAddressSelect = (e) => {
    const selectedUprn = e.target.value
    if (!selectedUprn) return

    const selectedAddress = addressList.find(addr => addr.uprn === selectedUprn)
    if (selectedAddress) {
      let address1 = ''
      let address2 = ''

      const fullAddress = selectedAddress.address
      const postTown = selectedAddress.post_town
      const dependentLocality = selectedAddress.dependent_locality
      const postcode = selectedAddress.postcode

      let streetPortion = fullAddress
        .replace(new RegExp(`,?\\s*${postcode}\\s*$`, 'i'), '')
        .replace(new RegExp(`,?\\s*${postTown}\\s*$`, 'i'), '')
        .trim()

      if (dependentLocality) {
        address1 = streetPortion
          .replace(new RegExp(`,?\\s*${dependentLocality}\\s*$`, 'i'), '')
          .trim()
        address2 = dependentLocality
      } else {
        address1 = streetPortion
        address2 = ''
      }

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

  // Get airline name for display/submission
  const getDropoffAirlineName = () => {
    if (formData.dropoffAirline === 'Other') return formData.customDropoffAirline
    const airline = availableAirlines.find(a => a.code === formData.dropoffAirline)
    return airline?.name || formData.dropoffAirline
  }

  const getPickupAirlineName = () => {
    if (formData.pickupAirline === 'Other') return formData.customPickupAirline
    const airline = availableAirlines.find(a => a.code === formData.pickupAirline)
    return airline?.name || formData.pickupAirline
  }

  // Get destination/origin name for display/submission
  const getDropoffDestinationName = () => {
    if (formData.dropoffDestination === 'Other') return formData.customDropoffDestination
    const dest = availableDestinations.find(d => d.code === formData.dropoffDestination)
    return dest?.name || formData.dropoffDestination
  }

  const getPickupOriginName = () => {
    if (formData.pickupOrigin === 'Other') return formData.customPickupOrigin
    const dest = availableDestinations.find(d => d.code === formData.pickupOrigin)
    return dest?.name || formData.pickupOrigin
  }

  // Get selected dropoff time from slot
  const getDropoffTime = () => {
    const slot = dropoffSlots.find(s => s.id === formData.dropoffSlot)
    return slot ? slot.time : ''
  }

  // Form validation
  const isFormValid = () => {
    const isFreeBooking = promoDiscount?.isFree
    // If promo code is entered, it must be validated (promoValid must be true or false, not null)
    const promoCodeValid = !formData.promoCode.trim() || promoValid === true
    const baseValid = (
      formData.firstName &&
      formData.lastName &&
      formData.email &&
      formData.billingAddress1 &&
      formData.billingCity &&
      formData.billingPostcode &&
      formData.registration &&
      formData.make &&
      formData.colour &&
      // Departure flight details
      formData.dropoffDate &&
      (formData.dropoffAirline && (formData.dropoffAirline !== 'Other' || formData.customDropoffAirline)) &&
      (formData.dropoffDestination && (formData.dropoffDestination !== 'Other' || formData.customDropoffDestination)) &&
      formData.departureTime &&
      formData.dropoffSlot &&
      // Return flight details
      formData.pickupDate &&
      (formData.pickupAirline && (formData.pickupAirline !== 'Other' || formData.customPickupAirline)) &&
      (formData.pickupOrigin && (formData.pickupOrigin !== 'Other' || formData.customPickupOrigin)) &&
      formData.arrivalTime &&
      // Payment
      (isFreeBooking || formData.stripePaymentLink) &&
      formData.amount &&
      // Promo code must be validated if entered
      promoCodeValid
    )

    return baseValid
  }

  // Format date for display
  const formatDate = (date) => {
    if (!date) return ''
    return date.toLocaleDateString('en-GB', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric'
    })
  }

  // Submit manual booking
  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!isFormValid()) return

    setSubmitting(true)
    setError('')
    setSuccess(false)

    const isFreeBooking = promoDiscount?.isFree
    const requestBody = {
      first_name: formData.firstName,
      last_name: formData.lastName,
      email: formData.email,
      phone: formData.phone,
      billing_address1: formData.billingAddress1,
      billing_address2: formData.billingAddress2,
      billing_city: formData.billingCity,
      billing_county: formData.billingCounty,
      billing_postcode: formData.billingPostcode.toUpperCase(),
      billing_country: formData.billingCountry,
      registration: formData.registration.toUpperCase(),
      make: formData.make,
      colour: formData.colour,
      tax_status: formData.taxStatus || null,
      mot_status: formData.motStatus || null,
      tax_due_date: formData.taxDueDate || null,
      mot_expiry_date: formData.motExpiryDate || null,
      dropoff_date: format(formData.dropoffDate, 'yyyy-MM-dd'),
      dropoff_time: getDropoffTime(),
      pickup_date: format(formData.pickupDate, 'yyyy-MM-dd'),
      pickup_time: calculatedPickupTime,
      flight_arrival_date: format(formData.pickupDate, 'yyyy-MM-dd'),
      // Departure flight details
      dropoff_airline_name: getDropoffAirlineName(),
      dropoff_destination: getDropoffDestinationName(),
      dropoff_flight_number: formData.dropoffFlightNumber || 'Unknown',
      dropoff_slot: formData.dropoffSlot,
      // Return flight details
      pickup_airline_name: getPickupAirlineName(),
      pickup_origin: getPickupOriginName(),
      pickup_flight_number: formData.pickupFlightNumber || 'Unknown',
      // Payment
      stripe_payment_link: isFreeBooking ? '' : formData.stripePaymentLink,
      amount_pence: Math.round(parseFloat(formData.amount) * 100),
      notes: formData.notes,
      promo_code: promoValid ? formData.promoCode.trim().toUpperCase() : null,
      is_free_booking: isFreeBooking || false,
      // Actual flight times (for emails and display)
      flight_departure_time: formData.departureTime || null,
      flight_arrival_time: formData.arrivalTime || null,
    }

    // Debug logging for promo code
    console.log('Submit - promoValid:', promoValid)
    console.log('Submit - formData.promoCode:', formData.promoCode)
    console.log('Submit - promo_code being sent:', requestBody.promo_code)

    try {
      const response = await fetch(`${API_URL}/api/admin/manual-booking`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      })

      if (response.ok) {
        setSuccess(true)
        // Reset form
        setFormData({
          firstName: '',
          lastName: '',
          email: '',
          phone: '',
          billingPostcode: '',
          billingAddress1: '',
          billingAddress2: '',
          billingCity: '',
          billingCounty: '',
          billingCountry: 'United Kingdom',
          registration: '',
          make: '',
          colour: '',
          dropoffDate: null,
          dropoffAirline: '',
          customDropoffAirline: '',
          dropoffDestination: '',
          customDropoffDestination: '',
          dropoffFlightNumber: '',
          departureTime: null,
          dropoffSlot: '',
          pickupDate: null,
          pickupAirline: '',
          customPickupAirline: '',
          pickupOrigin: '',
          customPickupOrigin: '',
          pickupFlightNumber: '',
          arrivalTime: null,
          promoCode: '',
          stripePaymentLink: '',
          amount: '',
          notes: '',
        })
        setDvlaVerified(false)
        setAddressList([])
        setPromoValid(null)
        setPromoMessage('')
        setPromoDiscount(null)
        setCalculatedPrice(null)
      } else {
        const data = await response.json()
        let errorMsg = 'Failed to create manual booking'
        if (data.detail) {
          if (Array.isArray(data.detail)) {
            errorMsg = data.detail.map(err => err.msg || JSON.stringify(err)).join(', ')
          } else if (typeof data.detail === 'string') {
            errorMsg = data.detail
          }
        }
        setError(errorMsg)
      }
    } catch (err) {
      setError('Network error. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="manual-booking">
      <div className="manual-booking-header">
        <div>
          <h2>Create Manual Booking</h2>
          <p className="manual-booking-description">
            Create a booking and send a payment link to the customer via email.
          </p>
        </div>
        <button onClick={handleRefresh} className="admin-refresh" type="button">
          Refresh
        </button>
      </div>

      {success && (
        <div className="manual-booking-success">
          Booking created successfully! Payment link email has been sent to the customer.
        </div>
      )}

      {error && (
        <div className="manual-booking-error">{error}</div>
      )}

      <form onSubmit={handleSubmit} className="manual-booking-form">
        {/* Customer Details Section */}
        <div className="manual-booking-section">
          <h3>Customer Details</h3>
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="firstName">First Name <span className="required">*</span></label>
              <input
                type="text"
                id="firstName"
                name="firstName"
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
                value={formData.lastName}
                onChange={handleChange}
                required
              />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="email">Email Address <span className="required">*</span></label>
              <input
                type="email"
                id="email"
                name="email"
                value={formData.email}
                onChange={handleChange}
                required
              />
            </div>
            <div className="form-group">
              <label htmlFor="phone">Phone Number</label>
              <input
                type="tel"
                id="phone"
                name="phone"
                value={formData.phone}
                onChange={handleChange}
              />
            </div>
          </div>
        </div>

        {/* Address Section */}
        <div className="manual-booking-section">
          <h3>Billing Address</h3>
          <div className="form-group">
            <label htmlFor="billingPostcode">Postcode <span className="required">*</span></label>
            <div className="input-with-button">
              <input
                type="text"
                id="billingPostcode"
                name="billingPostcode"
                value={formData.billingPostcode}
                onChange={handleChange}
                style={{ textTransform: 'uppercase' }}
                required
              />
              <button
                type="button"
                className="lookup-btn"
                onClick={lookupAddress}
                disabled={addressLoading || !formData.billingPostcode.trim()}
              >
                {addressLoading ? 'Finding...' : 'Find Address'}
              </button>
            </div>
            {addressError && <span className="field-error">{addressError}</span>}
          </div>

          {showAddressSelect && addressList.length > 0 && (
            <div className="form-group">
              <label htmlFor="addressSelect">Select Address</label>
              <select
                id="addressSelect"
                onChange={handleAddressSelect}
                defaultValue=""
              >
                <option value="">-- Select an address ({addressList.length} found) --</option>
                {addressList.map((addr) => (
                  <option key={addr.uprn} value={addr.uprn}>
                    {addr.address}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="form-group">
            <label htmlFor="billingAddress1">Address Line 1 <span className="required">*</span></label>
            <input
              type="text"
              id="billingAddress1"
              name="billingAddress1"
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
                value={formData.billingCounty}
                onChange={handleChange}
              />
            </div>
          </div>
        </div>

        {/* Vehicle Section */}
        <div className="manual-booking-section">
          <h3>Vehicle Details</h3>
          <div className="form-group">
            <label htmlFor="registration">Registration <span className="required">*</span></label>
            <div className="input-with-button">
              <input
                type="text"
                id="registration"
                name="registration"
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
                className="lookup-btn"
                onClick={lookupVehicle}
                disabled={dvlaLoading || !formData.registration}
              >
                {dvlaLoading ? 'Looking up...' : 'Lookup'}
              </button>
            </div>
            {dvlaVerified && <span className="field-success">Vehicle found and verified</span>}
            {dvlaError && <span className="field-error">{dvlaError}</span>}
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="make">Make <span className="required">*</span></label>
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
                  value={formData.make}
                  onChange={handleChange}
                  placeholder="e.g. Ford"
                  required
                />
              )}
            </div>
            <div className="form-group">
              <label htmlFor="colour">Colour <span className="required">*</span></label>
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
                  value={formData.colour}
                  onChange={handleChange}
                  placeholder="e.g. Blue"
                  required
                />
              )}
            </div>
          </div>
        </div>

        {/* Trip Details Section */}
        <div className="manual-booking-section trip-details-section">
          <h3>Trip Details</h3>

          {/* Departure Flight Sub-section */}
          <div className="flight-subsection">
            <h4 className="flight-subsection-title">Departure Flight</h4>

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
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="dropoffAirline">Airline <span className="required">*</span></label>
              <select
                id="dropoffAirline"
                name="dropoffAirline"
                value={formData.dropoffAirline}
                onChange={(e) => setFormData(prev => ({
                  ...prev,
                  dropoffAirline: e.target.value,
                  customDropoffAirline: '',
                }))}
              >
                <option value="">Select airline</option>
                {availableAirlines.filter(a => a.code !== 'Other' && a.name !== 'Other').map(airline => (
                  <option key={airline.code} value={airline.code}>{airline.name}</option>
                ))}
                <option value="Other">Other</option>
              </select>
            </div>
            {formData.dropoffAirline === 'Other' && (
              <div className="form-group">
                <label htmlFor="customDropoffAirline">Custom Airline <span className="required">*</span></label>
                <input
                  type="text"
                  id="customDropoffAirline"
                  name="customDropoffAirline"
                  value={formData.customDropoffAirline}
                  onChange={handleChange}
                  placeholder="e.g., British Airways"
                  required
                />
              </div>
            )}
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="dropoffDestination">Destination <span className="required">*</span></label>
              <select
                id="dropoffDestination"
                name="dropoffDestination"
                value={formData.dropoffDestination}
                onChange={(e) => setFormData(prev => ({
                  ...prev,
                  dropoffDestination: e.target.value,
                  customDropoffDestination: '',
                }))}
              >
                <option value="">Select destination</option>
                {availableDestinations.filter(d => d.code !== 'Other' && d.name !== 'Other').map(dest => (
                  <option key={dest.code} value={dest.code}>{dest.name}</option>
                ))}
                <option value="Other">Other</option>
              </select>
            </div>
            {formData.dropoffDestination === 'Other' && (
              <div className="form-group">
                <label htmlFor="customDropoffDestination">Custom Destination <span className="required">*</span></label>
                <input
                  type="text"
                  id="customDropoffDestination"
                  name="customDropoffDestination"
                  value={formData.customDropoffDestination}
                  onChange={handleChange}
                  placeholder="e.g., Barcelona"
                  required
                />
              </div>
            )}
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="dropoffFlightNumber">Flight Number</label>
              <input
                type="text"
                id="dropoffFlightNumber"
                name="dropoffFlightNumber"
                value={formData.dropoffFlightNumber}
                onChange={handleChange}
                placeholder="e.g., 1234"
                style={{ textTransform: 'uppercase' }}
              />
            </div>
            <div className="form-group">
              <label htmlFor="departureTime">Departure Time <span className="required">*</span></label>
              <MobileTimePicker
                id="departureTime"
                value={formData.departureTime}
                onChange={(time) => setFormData(prev => ({ ...prev, departureTime: time }))}
                placeholder="e.g., 14:30"
                label="Departure Time"
              />
            </div>
          </div>

          {formData.departureTime && dropoffSlots.length > 0 && (
            <div className="form-group">
              <label htmlFor="dropoffSlot">Drop-off Slot <span className="required">*</span></label>
              <select
                id="dropoffSlot"
                name="dropoffSlot"
                value={formData.dropoffSlot}
                onChange={handleChange}
              >
                <option value="">Select drop-off slot</option>
                {dropoffSlots.map(slot => (
                  <option key={slot.id} value={slot.id}>
                    {slot.label}
                  </option>
                ))}
              </select>
              {dropoffSlots.some(s => s.isOvernight) && (
                <p className="overnight-note" style={{ color: '#e67e22', fontSize: '13px', marginTop: '6px' }}>
                  * Drop-off is on the <strong>day before</strong> the flight (early morning departure)
                </p>
              )}
              {formData.dropoffSlot && (
                <p className="slot-info">
                  Customer will drop off at <strong>{getDropoffTime()}</strong>
                </p>
              )}
            </div>
          )}
          </div>

          {/* Return Flight Sub-section */}
          <div className="flight-subsection">
            <h4 className="flight-subsection-title">Return Flight</h4>

            <div className="form-group">
              <label htmlFor="pickupDate">Pick-up Date</label>
            <DatePicker
              selected={formData.pickupDate}
              onChange={(date) => handleDateChange(date, 'pickupDate')}
              dateFormat="dd/MM/yyyy"
              minDate={formData.dropoffDate || new Date()}
              placeholderText="Select date"
              className="date-picker-input"
              id="pickupDate"
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="pickupAirline">Airline <span className="required">*</span></label>
              <select
                id="pickupAirline"
                name="pickupAirline"
                value={formData.pickupAirline}
                onChange={(e) => setFormData(prev => ({
                  ...prev,
                  pickupAirline: e.target.value,
                  customPickupAirline: '',
                }))}
              >
                <option value="">Select airline</option>
                {availableAirlines.filter(a => a.code !== 'Other' && a.name !== 'Other').map(airline => (
                  <option key={airline.code} value={airline.code}>{airline.name}</option>
                ))}
                <option value="Other">Other</option>
              </select>
            </div>
            {formData.pickupAirline === 'Other' && (
              <div className="form-group">
                <label htmlFor="customPickupAirline">Custom Airline <span className="required">*</span></label>
                <input
                  type="text"
                  id="customPickupAirline"
                  name="customPickupAirline"
                  value={formData.customPickupAirline}
                  onChange={handleChange}
                  placeholder="e.g., British Airways"
                  required
                />
              </div>
            )}
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="pickupOrigin">Origin <span className="required">*</span></label>
              <select
                id="pickupOrigin"
                name="pickupOrigin"
                value={formData.pickupOrigin}
                onChange={(e) => setFormData(prev => ({
                  ...prev,
                  pickupOrigin: e.target.value,
                  customPickupOrigin: '',
                }))}
              >
                <option value="">Select origin</option>
                {availableDestinations.filter(d => d.code !== 'Other' && d.name !== 'Other').map(dest => (
                  <option key={dest.code} value={dest.code}>{dest.name}</option>
                ))}
                <option value="Other">Other</option>
              </select>
            </div>
            {formData.pickupOrigin === 'Other' && (
              <div className="form-group">
                <label htmlFor="customPickupOrigin">Custom Origin <span className="required">*</span></label>
                <input
                  type="text"
                  id="customPickupOrigin"
                  name="customPickupOrigin"
                  value={formData.customPickupOrigin}
                  onChange={handleChange}
                  placeholder="e.g., Barcelona"
                  required
                />
              </div>
            )}
          </div>

          <div className="form-row" style={{ display: 'flex', gap: '12px' }}>
            <div className="form-group" style={{ flex: '1' }}>
              <label htmlFor="pickupFlightNumber">Flight Number</label>
              <input
                type="text"
                id="pickupFlightNumber"
                name="pickupFlightNumber"
                value={formData.pickupFlightNumber}
                onChange={handleChange}
                placeholder="e.g., 1235"
                style={{ textTransform: 'uppercase' }}
              />
            </div>
            <div className="form-group" style={{ flex: '1' }}>
              <label htmlFor="arrivalTime">Arrival Time <span className="required">*</span></label>
              <MobileTimePicker
                id="arrivalTime"
                value={formData.arrivalTime}
                onChange={(time) => setFormData(prev => ({ ...prev, arrivalTime: time }))}
                placeholder="e.g., 14:30"
                label="Arrival Time"
              />
            </div>
            <div className="form-group" style={{ flex: '1' }}>
              <label htmlFor="pickupTime">Pick-up Time</label>
              <input
                type="text"
                id="pickupTime"
                value={calculatedPickupTime || ''}
                readOnly
                disabled
                placeholder="Auto-calculated"
                style={{ backgroundColor: '#f5f5f5', cursor: 'not-allowed' }}
              />
            </div>
          </div>
          </div>
        </div>

        {/* Payment Section */}
        <div className="manual-booking-section">
          <h3>Payment</h3>
          {/* Auto-calculated price info */}
          {formData.dropoffDate && formData.pickupDate && (
            <div className="pricing-info-banner">
              {(() => {
                const days = Math.round((formData.pickupDate - formData.dropoffDate) / (1000 * 60 * 60 * 24))
                let tripLabel
                if (days === 7) {
                  tripLabel = '1 week trip'
                } else if (days === 14) {
                  tripLabel = '2 week trip'
                } else if (days === 21) {
                  tripLabel = '3 week trip'
                } else if (days === 28) {
                  tripLabel = '4 week trip'
                } else {
                  tripLabel = `${days} day${days !== 1 ? 's' : ''} trip`
                }
                return (
                  <>
                    <span className="trip-duration"><strong>{tripLabel}</strong></span>
                    {pricingLoading && <span className="calculated-price">Calculating...</span>}
                    {!pricingLoading && calculatedPrice && (
                      <span className="calculated-price">
                        Suggested price: <strong>£{calculatedPrice.toFixed(2)}</strong>
                      </span>
                    )}
                  </>
                )
              })()}
            </div>
          )}

          {/* Promo Code */}
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="promoCode">Promo Code (Optional)</label>
              <div className="input-with-button">
                <input
                  type="text"
                  id="promoCode"
                  name="promoCode"
                  value={formData.promoCode}
                  onChange={(e) => {
                    handleChange(e)
                    setPromoValid(null)
                    setPromoMessage('')
                    setPromoDiscount(null)
                  }}
                  placeholder="Enter promo code"
                  disabled={promoValid === true}
                />
                {promoValid === true ? (
                  <button
                    type="button"
                    className="lookup-btn remove-btn"
                    onClick={removePromoCode}
                    style={{ backgroundColor: '#dc3545', borderColor: '#dc3545' }}
                  >
                    Remove
                  </button>
                ) : (
                  <button
                    type="button"
                    className="lookup-btn"
                    onClick={validatePromoCode}
                    disabled={promoValidating || !formData.promoCode.trim() || !calculatedPrice}
                  >
                    {promoValidating ? 'Validating...' : 'Apply'}
                  </button>
                )}
              </div>
              {promoValid === true && (
                <p className="promo-success">
                  {promoMessage}
                  {promoDiscount && (
                    <span className="discount-applied">
                      {promoDiscount.isFree
                        ? ' — Booking is FREE!'
                        : ` — £${promoDiscount.amount.toFixed(2)} off`}
                    </span>
                  )}
                </p>
              )}
              {promoValid === false && (
                <p className="promo-error">{promoMessage}</p>
              )}
              {formData.promoCode.trim() && promoValid === null && (
                <p className="promo-warning">Please click "Apply" to validate the promo code before submitting</p>
              )}
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="amount">Amount (£) <span className="required">*</span></label>
              <input
                type="number"
                id="amount"
                name="amount"
                value={formData.amount}
                onChange={handleChange}
                min="0"
                step="0.01"
                placeholder={calculatedPrice ? calculatedPrice.toFixed(2) : "99.00"}
                required
              />
              {promoDiscount?.isFree && (
                <p className="free-booking-note">FREE booking - no payment required</p>
              )}
              {!promoDiscount?.isFree && calculatedPrice && formData.amount && parseFloat(formData.amount) !== calculatedPrice && (
                <p className="price-override-note">Custom price (suggested: £{calculatedPrice.toFixed(2)})</p>
              )}
            </div>
            <div className="form-group">
              <label htmlFor="stripePaymentLink">
                Stripe Payment Link {!promoDiscount?.isFree && <span className="required">*</span>}
              </label>
              <input
                type="url"
                id="stripePaymentLink"
                name="stripePaymentLink"
                value={formData.stripePaymentLink}
                onChange={handleChange}
                placeholder={promoDiscount?.isFree ? "Not required for free bookings" : "https://buy.stripe.com/..."}
                required={!promoDiscount?.isFree}
                disabled={promoDiscount?.isFree}
              />
            </div>
          </div>
          <div className="form-group">
            <label htmlFor="notes">Notes (Internal)</label>
            <textarea
              id="notes"
              name="notes"
              value={formData.notes}
              onChange={handleChange}
              rows={3}
              placeholder="Any additional notes about this booking..."
            />
          </div>
        </div>

        {/* Preview Section */}
        {isFormValid() && (
          <div className="manual-booking-section preview-section">
            <h3>Email Preview</h3>
            <div className="email-preview">
              <p><strong>To:</strong> {formData.email}</p>
              <p><strong>Subject:</strong> Complete Your TAG Parking Booking</p>
              <hr />
              <p>Dear {formData.firstName},</p>
              <p>Thank you for your booking with TAG Parking.</p>
              <p><strong>Booking Summary:</strong></p>
              <ul>
                <li>Drop-off: {formatDate(formData.dropoffDate)} at {getDropoffTime()}</li>
                <li>Pick-up: {formatDate(formData.pickupDate)} from {calculatedPickupTime}</li>
                <li>Outbound: {getDropoffAirlineName()} {formData.dropoffFlightNumber || ''} to {getDropoffDestinationName()}</li>
                <li>Return: {getPickupAirlineName()} {formData.pickupFlightNumber || ''} from {getPickupOriginName()}</li>
                <li>Vehicle: {formData.colour} {formData.make}</li>
                <li>Registration: {formData.registration.toUpperCase()}</li>
                <li>Total: £{parseFloat(formData.amount).toFixed(2)}</li>
              </ul>
              {!promoDiscount?.isFree && (
                <>
                  <p>Please complete your payment using the link below:</p>
                  <p><a href={formData.stripePaymentLink}>{formData.stripePaymentLink}</a></p>
                </>
              )}
            </div>
          </div>
        )}

        <div className="form-actions">
          <button
            type="submit"
            className="submit-btn"
            disabled={!isFormValid() || submitting}
          >
            {submitting ? 'Creating Booking...' : 'Create Booking & Send Email'}
          </button>
        </div>
      </form>
    </div>
  )
}

export default ManualBooking
