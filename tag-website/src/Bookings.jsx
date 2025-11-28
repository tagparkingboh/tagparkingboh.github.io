import { useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import DatePicker from 'react-datepicker'
import { format } from 'date-fns'
import { getMakes, getModels } from 'car-info'
import flightSchedule from './data/flightSchedule.json'
import 'react-datepicker/dist/react-datepicker.css'
import './Bookings.css'

function Bookings() {
  const [currentStep, setCurrentStep] = useState(1)
  const [formData, setFormData] = useState({
    dropoffDate: null,
    dropoffAirline: '',
    dropoffFlight: '', // Combined time|destination key
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
    package: 'quick',
    terms: false
  })

  // Parking capacity management
  const MAX_PARKING_SPOTS = 60

  // This would normally come from your database/API
  // For now, simulating with a placeholder
  const [bookedSpots, setBookedSpots] = useState({})

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

  // Filter departures for selected drop-off date
  const departuresForDate = useMemo(() => {
    if (!formData.dropoffDate) return []
    const dateStr = format(formData.dropoffDate, 'yyyy-MM-dd')
    return flightSchedule.filter(f => f.date === dateStr && f.type === 'departure')
  }, [formData.dropoffDate])

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
    return flightsForAirline.map(f => ({
      ...f,
      flightKey: `${f.time}|${f.destinationCode}`,
      displayText: `${f.time} → ${f.destinationName} (${f.destinationCode})`
    })).sort((a, b) => a.time.localeCompare(b.time))
  }, [flightsForAirline])

  // Get selected flight details
  const selectedDropoffFlight = useMemo(() => {
    if (!formData.dropoffFlight) return null
    return flightsForDropoff.find(f => f.flightKey === formData.dropoffFlight)
  }, [flightsForDropoff, formData.dropoffFlight])

  // Calculate drop-off time slots (3h, 2.5h, 2h before departure)
  const dropoffSlots = useMemo(() => {
    if (!selectedDropoffFlight) return []
    const [hours, minutes] = selectedDropoffFlight.time.split(':').map(Number)
    const departureMinutes = hours * 60 + minutes

    return [
      { id: '180', label: '3 hours before', time: formatMinutesToTime(departureMinutes - 180) },
      { id: '150', label: '2½ hours before', time: formatMinutesToTime(departureMinutes - 150) },
      { id: '120', label: '2 hours before', time: formatMinutesToTime(departureMinutes - 120) }
    ]
  }, [selectedDropoffFlight])

  // Filter arrivals for selected pick-up date - matching airline and destination
  const arrivalsForDate = useMemo(() => {
    if (!formData.pickupDate || !formData.dropoffAirline || !selectedDropoffFlight) return []
    const dateStr = format(formData.pickupDate, 'yyyy-MM-dd')
    // Filter by same airline and origin matching the departure destination
    return flightSchedule.filter(f =>
      f.date === dateStr &&
      f.type === 'arrival' &&
      f.airlineName === formData.dropoffAirline &&
      f.originCode === selectedDropoffFlight.destinationCode
    )
  }, [formData.pickupDate, formData.dropoffAirline, selectedDropoffFlight])

  // Get arrival times for matching return flights
  const arrivalTimesForPickup = useMemo(() => {
    const times = [...new Set(arrivalsForDate.map(f => f.time))]
    return times.sort()
  }, [arrivalsForDate])

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

  const nextStep = () => {
    setCurrentStep(prev => Math.min(prev + 1, 5))
    window.scrollTo(0, 0)
  }

  const prevStep = () => {
    setCurrentStep(prev => Math.max(prev - 1, 1))
    window.scrollTo(0, 0)
  }

  const isStep1Complete = formData.dropoffDate && formData.dropoffAirline && formData.dropoffFlight && formData.dropoffSlot && formData.pickupDate && formData.pickupFlightTime && isCapacityAvailable
  const isMakeComplete = formData.make && (formData.make !== 'Other' || formData.customMake)
  const isModelComplete = formData.model && (formData.model !== 'Other' || formData.customModel)
  const isStep2Complete = formData.registration && isMakeComplete && isModelComplete && formData.colour
  const isStep3Complete = formData.firstName && formData.lastName && formData.email && formData.phone
  const isStep4Complete = formData.package
  const isStep5Complete = formData.terms

  const handleSubmit = async (e) => {
    e.preventDefault()
    // Stripe integration will go here
    alert('Stripe payment integration coming soon! Your booking details have been captured.')
    console.log('Booking data:', formData)
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
            {[1, 2, 3, 4, 5].map(step => (
              <div
                key={step}
                className={`progress-step ${currentStep >= step ? 'active' : ''} ${currentStep > step ? 'completed' : ''}`}
              >
                <span className="step-number">{step}</span>
                <span className="step-label">
                  {step === 1 && 'Trip'}
                  {step === 2 && 'Vehicle'}
                  {step === 3 && 'Details'}
                  {step === 4 && 'Package'}
                  {step === 5 && 'Payment'}
                </span>
              </div>
            ))}
          </div>
        </div>

        <form className="bookings-form" onSubmit={handleSubmit}>
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
                  minDate={new Date()}
                  placeholderText="Select date"
                  className="date-picker-input"
                  id="dropoffDate"
                />
              </div>

              {formData.dropoffDate && airlinesForDropoff.length > 0 && (
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

              {formData.dropoffFlight && dropoffSlots.length > 0 && (
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
                    {formData.dropoffAirline} from {selectedDropoffFlight?.destinationName || ''}
                  </p>

                  <div className="form-group fade-in">
                    <label htmlFor="pickupDate">Pick-up Date</label>
                    <DatePicker
                      selected={formData.pickupDate}
                      onChange={(date) => handleDateChange(date, 'pickupDate')}
                      dateFormat="dd/MM/yyyy"
                      minDate={formData.dropoffDate ? new Date(formData.dropoffDate.getTime() + 86400000) : new Date()}
                      placeholderText="Select date"
                      className="date-picker-input"
                      id="pickupDate"
                    />
                  </div>
                </>
              )}

              {formData.pickupDate && arrivalTimesForPickup.length > 0 && (
                <div className="form-group fade-in">
                  <label htmlFor="pickupFlightTime">Arrival Time at BOH</label>
                  <select
                    id="pickupFlightTime"
                    name="pickupFlightTime"
                    value={formData.pickupFlightTime}
                    onChange={handleChange}
                  >
                    <option value="">Select time</option>
                    {arrivalTimesForPickup.map(time => (
                      <option key={time} value={time}>{time}</option>
                    ))}
                  </select>
                </div>
              )}

              {formData.pickupDate && arrivalTimesForPickup.length === 0 && (
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
                <button
                  type="button"
                  className="next-btn"
                  onClick={nextStep}
                  disabled={!isStep1Complete}
                >
                  Continue to Vehicle Details
                </button>
              </div>
            </div>
          )}

          {/* Step 2: Vehicle Details */}
          {currentStep === 2 && (
            <div className="form-section">
              <h2>Vehicle Details</h2>

              <div className="form-group">
                <label htmlFor="registration">Registration Number</label>
                <input
                  type="text"
                  id="registration"
                  name="registration"
                  placeholder="e.g. AB12 CDE"
                  value={formData.registration}
                  onChange={handleChange}
                  style={{ textTransform: 'uppercase' }}
                  required
                />
              </div>

              {formData.registration && (
                <div className="form-group fade-in">
                  <label htmlFor="make">Vehicle Make</label>
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

              {formData.make && formData.make !== 'Other' && (
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

              {formData.make === 'Other' && formData.customMake && (
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

              {((formData.model && formData.model !== 'Other') ||
                (formData.model === 'Other' && formData.customModel) ||
                (formData.make === 'Other' && formData.customModel)) && (
                <div className="form-group fade-in">
                  <label htmlFor="colour">Vehicle Colour</label>
                  <input
                    type="text"
                    id="colour"
                    name="colour"
                    placeholder="e.g. Black"
                    value={formData.colour}
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
                  disabled={!isStep2Complete}
                >
                  Continue to Your Details
                </button>
              </div>
            </div>
          )}

          {/* Step 3: Your Details */}
          {currentStep === 3 && (
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
                <input
                  type="tel"
                  id="phone"
                  name="phone"
                  placeholder="+44 7123 456789"
                  value={formData.phone}
                  onChange={handleChange}
                  required
                />
              </div>

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
                  Continue to Package Selection
                </button>
              </div>
            </div>
          )}

          {/* Step 4: Select Package */}
          {currentStep === 4 && (
            <div className="form-section">
              <h2>Select Package</h2>

              <div className="package-options">
                <label className="package-option">
                  <input
                    type="radio"
                    name="package"
                    value="quick"
                    checked={formData.package === 'quick'}
                    onChange={handleChange}
                  />
                  <div className="package-card">
                    <span className="package-label">QUICK TRIPS</span>
                    <span className="package-price">£99</span>
                    <span className="package-period">/ 1 week</span>
                    <ul className="package-features">
                      <li>Meet & Greet at terminal</li>
                      <li>Secure storage facility</li>
                      <li>24/7 monitoring</li>
                      <li>No hidden fees</li>
                    </ul>
                  </div>
                </label>
                <label className="package-option">
                  <input
                    type="radio"
                    name="package"
                    value="longer"
                    checked={formData.package === 'longer'}
                    onChange={handleChange}
                  />
                  <div className="package-card">
                    <span className="package-label">LONGER STAYS</span>
                    <span className="package-price">£135</span>
                    <span className="package-period">/ 2 weeks</span>
                    <ul className="package-features">
                      <li>Meet & Greet at terminal</li>
                      <li>Secure storage facility</li>
                      <li>24/7 monitoring</li>
                      <li>No hidden fees</li>
                    </ul>
                  </div>
                </label>
              </div>

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
                  Continue to Payment
                </button>
              </div>
            </div>
          )}

          {/* Step 5: Payment */}
          {currentStep === 5 && (
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
                  <span>{formatDisplayDate(formData.dropoffDate)}</span>
                </div>
                <div className="summary-item">
                  <span>Pick-up</span>
                  <span>{formatDisplayDate(formData.pickupDate)}</span>
                </div>
                <div className="summary-item">
                  <span>Vehicle</span>
                  <span>{formData.colour} {formData.make === 'Other' ? formData.customMake : formData.make} {formData.model === 'Other' ? formData.customModel : formData.model}</span>
                </div>
                <div className="summary-item">
                  <span>Registration</span>
                  <span>{formData.registration.toUpperCase()}</span>
                </div>
                <div className="summary-item total">
                  <span>Total</span>
                  <span>{formData.package === 'quick' ? '£99.00' : '£135.00'}</span>
                </div>
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
                  <span>I agree to the <a href="#terms">Terms & Conditions</a> and <a href="#privacy">Privacy Policy</a></span>
                </label>
              </div>

              <div className="stripe-placeholder">
                <p>Stripe payment form will appear here</p>
                <p className="stripe-note">Secure payment powered by Stripe</p>
              </div>

              <div className="form-actions">
                <button type="button" className="back-btn" onClick={prevStep}>
                  Back
                </button>
                <button
                  type="submit"
                  className="submit-btn"
                  disabled={!isStep5Complete}
                >
                  Pay {formData.package === 'quick' ? '£99.00' : '£135.00'}
                </button>
              </div>
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
