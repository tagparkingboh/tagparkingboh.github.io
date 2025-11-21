import { useState } from 'react'
import { Link } from 'react-router-dom'
import './Bookings.css'

function Bookings() {
  const [currentStep, setCurrentStep] = useState(1)
  const [formData, setFormData] = useState({
    terminal: '',
    dropoffDate: '',
    dropoffFlight: '',
    pickupDate: '',
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

  const terminals = ['Terminal 1', 'Terminal 2']

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
  }

  const nextStep = () => {
    setCurrentStep(prev => Math.min(prev + 1, 5))
    window.scrollTo(0, 0)
  }

  const prevStep = () => {
    setCurrentStep(prev => Math.max(prev - 1, 1))
    window.scrollTo(0, 0)
  }

  const isStep1Complete = formData.terminal && formData.dropoffDate && formData.dropoffFlight && formData.pickupDate && formData.pickupTime
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
                <label htmlFor="terminal">Select Terminal</label>
                <select
                  id="terminal"
                  name="terminal"
                  value={formData.terminal}
                  onChange={handleChange}
                  required
                >
                  <option value="">Choose terminal</option>
                  {terminals.map(t => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>

              {formData.terminal && (
                <div className="form-group fade-in">
                  <label htmlFor="dropoffDate">Drop-off Date</label>
                  <input
                    type="date"
                    id="dropoffDate"
                    name="dropoffDate"
                    value={formData.dropoffDate}
                    onChange={handleChange}
                    min={new Date().toISOString().split('T')[0]}
                    required
                  />
                </div>
              )}

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
                  <input
                    type="date"
                    id="pickupDate"
                    name="pickupDate"
                    value={formData.pickupDate}
                    onChange={handleChange}
                    min={formData.dropoffDate}
                    required
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
                  required
                />
              </div>

              {formData.registration && (
                <div className="form-group fade-in">
                  <label htmlFor="make">Vehicle Make</label>
                  <input
                    type="text"
                    id="make"
                    name="make"
                    placeholder="e.g. BMW"
                    value={formData.make}
                    onChange={handleChange}
                    required
                  />
                </div>
              )}

              {formData.make && (
                <div className="form-group fade-in">
                  <label htmlFor="model">Vehicle Model</label>
                  <input
                    type="text"
                    id="model"
                    name="model"
                    placeholder="e.g. 3 Series"
                    value={formData.model}
                    onChange={handleChange}
                    required
                  />
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

              <div className="form-group">
                <label htmlFor="flightNumber">Flight Number (optional)</label>
                <input
                  type="text"
                  id="flightNumber"
                  name="flightNumber"
                  placeholder="e.g. BA123"
                  value={formData.flightNumber}
                  onChange={handleChange}
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
                  <span>Bournemouth (BOH) - {formData.terminal}</span>
                </div>
                <div className="summary-item">
                  <span>Drop-off</span>
                  <span>{formData.dropoffDate}</span>
                </div>
                <div className="summary-item">
                  <span>Pick-up</span>
                  <span>{formData.pickupDate}</span>
                </div>
                <div className="summary-item">
                  <span>Vehicle</span>
                  <span>{formData.colour} {formData.make} {formData.model}</span>
                </div>
                <div className="summary-item">
                  <span>Registration</span>
                  <span>{formData.registration}</span>
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
