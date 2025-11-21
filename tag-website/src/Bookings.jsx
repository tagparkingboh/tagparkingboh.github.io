import { useState } from 'react'
import { Link } from 'react-router-dom'
import DatePicker from 'react-datepicker'
import { format } from 'date-fns'
import 'react-datepicker/dist/react-datepicker.css'
import './Bookings.css'

function Bookings() {
  const [currentStep, setCurrentStep] = useState(1)
  const [formData, setFormData] = useState({
    dropoffDate: null,
    dropoffFlight: '',
    pickupDate: null,
    pickupTime: '',
    registration: '',
    make: '',
    model: '',
    colour: '',
    firstName: '',
    lastName: '',
    email: '',
    phone: '',
    flightNumber: '',
    package: 'quick',
    terms: false
  })

  // UK popular car makes and their models
  const carData = {
    'Audi': ['A1', 'A3', 'A4', 'A5', 'A6', 'Q2', 'Q3', 'Q5', 'Q7', 'TT', 'e-tron'],
    'BMW': ['1 Series', '2 Series', '3 Series', '4 Series', '5 Series', 'X1', 'X3', 'X5', 'iX', 'i4'],
    'Citroen': ['C1', 'C3', 'C4', 'C5 X', 'Berlingo', 'e-C4'],
    'Dacia': ['Sandero', 'Duster', 'Jogger', 'Spring'],
    'Fiat': ['500', 'Panda', 'Tipo', '500X'],
    'Ford': ['Fiesta', 'Focus', 'Puma', 'Kuga', 'Mustang Mach-E', 'Ranger'],
    'Honda': ['Civic', 'Jazz', 'HR-V', 'CR-V', 'ZR-V', 'e'],
    'Hyundai': ['i10', 'i20', 'i30', 'Tucson', 'Kona', 'Ioniq 5', 'Ioniq 6'],
    'Jaguar': ['XE', 'XF', 'F-Pace', 'E-Pace', 'I-Pace'],
    'Kia': ['Picanto', 'Rio', 'Ceed', 'Sportage', 'Niro', 'EV6', 'EV9'],
    'Land Rover': ['Defender', 'Discovery', 'Discovery Sport', 'Range Rover', 'Range Rover Sport', 'Range Rover Evoque'],
    'Lexus': ['UX', 'NX', 'RX', 'ES', 'IS'],
    'Mazda': ['2', '3', 'CX-3', 'CX-30', 'CX-5', 'MX-5', 'CX-60'],
    'Mercedes-Benz': ['A-Class', 'B-Class', 'C-Class', 'E-Class', 'GLA', 'GLC', 'GLE', 'EQA', 'EQC'],
    'Mini': ['Hatch', 'Clubman', 'Countryman', 'Electric'],
    'Nissan': ['Micra', 'Juke', 'Qashqai', 'X-Trail', 'Leaf', 'Ariya'],
    'Peugeot': ['208', '308', '2008', '3008', '5008', 'e-208', 'e-2008'],
    'Renault': ['Clio', 'Captur', 'Megane', 'Arkana', 'Zoe', 'Megane E-Tech'],
    'Seat': ['Ibiza', 'Leon', 'Arona', 'Ateca', 'Tarraco'],
    'Skoda': ['Fabia', 'Scala', 'Octavia', 'Superb', 'Kamiq', 'Karoq', 'Kodiaq', 'Enyaq'],
    'Tesla': ['Model 3', 'Model Y', 'Model S', 'Model X'],
    'Toyota': ['Yaris', 'Corolla', 'C-HR', 'RAV4', 'Prius', 'bZ4X', 'Yaris Cross'],
    'Vauxhall': ['Corsa', 'Astra', 'Mokka', 'Grandland', 'Crossland'],
    'Volkswagen': ['Polo', 'Golf', 'T-Roc', 'Tiguan', 'ID.3', 'ID.4', 'ID.5', 'Passat'],
    'Volvo': ['XC40', 'XC60', 'XC90', 'V60', 'S60', 'C40 Recharge']
  }

  const carMakes = Object.keys(carData).sort()
  const carModels = formData.make ? carData[formData.make] || [] : []

  const flightSlots = [
    { id: 'early', label: 'Early Morning', time: '05:00 - 09:00' },
    { id: 'midday', label: 'Midday', time: '09:00 - 14:00' },
    { id: 'afternoon', label: 'Afternoon/Evening', time: '14:00 - 21:00' }
  ]

  const pickupTimes = [
    { id: '45', label: '45 minutes after landing' },
    { id: '60', label: '60 minutes after landing' },
    { id: '75', label: '75 minutes after landing' }
  ]

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }))

    // Reset model when make changes
    if (name === 'make') {
      setFormData(prev => ({
        ...prev,
        make: value,
        model: ''
      }))
    }
  }

  const handleDateChange = (date, field) => {
    setFormData(prev => ({
      ...prev,
      [field]: date
    }))
  }

  const nextStep = () => {
    setCurrentStep(prev => Math.min(prev + 1, 5))
    window.scrollTo(0, 0)
  }

  const prevStep = () => {
    setCurrentStep(prev => Math.max(prev - 1, 1))
    window.scrollTo(0, 0)
  }

  const isStep1Complete = formData.dropoffDate && formData.dropoffFlight && formData.pickupDate && formData.pickupTime
  const isStep2Complete = formData.registration && formData.make && formData.model && formData.colour
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
          <img src="/logo.svg" alt="TAG - Book it. Bag it. Tag it." className="logo-svg" />
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

              {formData.dropoffDate && (
                <div className="form-group fade-in">
                  <label>Select Your Flight Time</label>
                  <div className="flight-slots">
                    {flightSlots.map(slot => (
                      <label key={slot.id} className="flight-slot">
                        <input
                          type="radio"
                          name="dropoffFlight"
                          value={slot.id}
                          checked={formData.dropoffFlight === slot.id}
                          onChange={handleChange}
                        />
                        <div className="slot-card">
                          <span className="slot-label">{slot.label}</span>
                          <span className="slot-time">{slot.time}</span>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {formData.dropoffFlight && (
                <div className="form-group fade-in">
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
              )}

              {formData.pickupDate && (
                <div className="form-group fade-in">
                  <label>Pick-up Time (after your flight lands)</label>
                  <div className="pickup-times">
                    {pickupTimes.map(time => (
                      <label key={time.id} className="pickup-time">
                        <input
                          type="radio"
                          name="pickupTime"
                          value={time.id}
                          checked={formData.pickupTime === time.id}
                          onChange={handleChange}
                        />
                        <div className="time-card">
                          <span>{time.label}</span>
                        </div>
                      </label>
                    ))}
                  </div>
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
                  </select>
                </div>
              )}

              {formData.make && (
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
                  </select>
                </div>
              )}

              {formData.model && (
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
                  <span>{formData.colour} {formData.make} {formData.model}</span>
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
        <p>© 2025 TAG Parking. All rights reserved.</p>
      </footer>
    </div>
  )
}

export default Bookings
