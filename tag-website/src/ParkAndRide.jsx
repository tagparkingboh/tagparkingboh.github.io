import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import DatePicker from 'react-datepicker'
import { format } from 'date-fns'
import PhoneInput, { isValidPhoneNumber } from 'react-phone-number-input'
import 'react-phone-number-input/style.css'
import MobileTimePicker from './components/MobileTimePicker'
import StripePayment from './components/StripePayment'
import 'react-datepicker/dist/react-datepicker.css'
import './BookingsNew.css'
import './BookingWelcome.css'

// Hard-coded P&R price for the placeholder flow. Real pricing logic
// (per-day, peak-day, etc.) lands in a later slice.
const PR_PRICE_GBP = 40

function parseHHMM(value) {
  if (!value || !/^\d{2}:\d{2}$/.test(value)) return null
  const [h, m] = value.split(':').map(Number)
  if (h > 23 || m > 59) return null
  return h * 60 + m
}

function combineDateAndTime(date, hhmm) {
  const minutes = parseHHMM(hhmm)
  if (!date || minutes === null) return null
  const out = new Date(date)
  out.setHours(Math.floor(minutes / 60), minutes % 60, 0, 0)
  return out
}

function isAmbiguous(hhmm) {
  return /^(0[1-9]|1[0-2]):[0-5][0-9]$/.test(hhmm)
}

function daysBetween(a, b) {
  if (!a || !b) return 1
  return Math.max(1, Math.ceil((b.getTime() - a.getTime()) / (1000 * 60 * 60 * 24)))
}

function ParkAndRide() {
  const navigate = useNavigate()
  const [showWelcomeModal, setShowWelcomeModal] = useState(true)
  const [step, setStep] = useState(1)

  // Step 1
  const [entryDate, setEntryDate] = useState(null)
  const [entryTime, setEntryTime] = useState('')
  const [exitDate, setExitDate] = useState(null)
  const [exitTime, setExitTime] = useState('')
  const [travellers, setTravellers] = useState(1)
  const [step1Error, setStep1Error] = useState('')

  // Step 3 — contact / billing / vehicle
  const [details, setDetails] = useState({
    firstName: '',
    lastName: '',
    email: '',
    phone: '',
    billingAddress1: '',
    billingAddress2: '',
    billingCity: '',
    billingCounty: '',
    billingPostcode: '',
    billingCountry: 'United Kingdom',
    registration: '',
    make: '',
    colour: '',
  })
  const [step3Attempted, setStep3Attempted] = useState(false)

  // Step 4 — once payment fires, lock the wizard
  const [paymentSuccess, setPaymentSuccess] = useState(null) // { reference, amount }
  const [paymentError, setPaymentError] = useState('')

  // Stable session id so backend can dedupe payment intents
  const [sessionId] = useState(
    () => `pr-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  )

  useEffect(() => {
    window.scrollTo(0, 0)
    if (window.gtag) {
      window.gtag('event', 'page_view', {
        page_path: '/tag-it/park-ride',
        page_title: 'Park & Ride — booking',
      })
    }
  }, [])

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [step])

  const entryDt = useMemo(() => combineDateAndTime(entryDate, entryTime), [entryDate, entryTime])
  const exitDt = useMemo(() => combineDateAndTime(exitDate, exitTime), [exitDate, exitTime])
  const durationDays = useMemo(() => daysBetween(entryDt, exitDt), [entryDt, exitDt])

  const isStep1Ready =
    entryDt !== null &&
    exitDt !== null &&
    exitDt > entryDt &&
    Number.isInteger(travellers) &&
    travellers >= 1

  const showEntryTime = entryDate !== null
  const showExitDate = parseHHMM(entryTime) !== null
  const showExitTime = exitDate !== null
  const showTravellers = parseHHMM(exitTime) !== null
  const showStep1Continue = showTravellers

  const isEmailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(details.email)
  const isPhoneValid = details.phone && isValidPhoneNumber(details.phone)

  const isStep3Ready =
    details.firstName.trim() &&
    details.lastName.trim() &&
    isEmailValid &&
    isPhoneValid &&
    details.billingAddress1.trim() &&
    details.billingCity.trim() &&
    details.billingPostcode.trim() &&
    details.registration.trim() &&
    details.make.trim() &&
    details.colour.trim()

  const setDetail = (name, value) => setDetails(prev => ({ ...prev, [name]: value }))
  const handleDetailChange = (e) => setDetail(e.target.name, e.target.value)

  const handleStep1Continue = () => {
    if (!entryDt) return setStep1Error('Please enter your arrival date and time.')
    if (!exitDt) return setStep1Error('Please enter your return date and time.')
    if (exitDt <= entryDt) return setStep1Error('Return must be after arrival.')
    if (!Number.isInteger(travellers) || travellers < 1) {
      return setStep1Error('Please enter at least 1 traveller.')
    }
    setStep1Error('')
    setStep(2)
  }

  const handleStep3Continue = () => {
    setStep3Attempted(true)
    if (!isStep3Ready) return
    setStep(4)
  }

  // Build the M&G-shaped formData StripePayment expects. Flight fields are
  // null since the system runs off the customer's manual times anyway
  // (project memory: flight number / departure_id are decorative).
  const stripeFormData = {
    firstName: details.firstName,
    lastName: details.lastName,
    email: details.email,
    phone: details.phone,
    billingAddress1: details.billingAddress1,
    billingAddress2: details.billingAddress2,
    billingCity: details.billingCity,
    billingCounty: details.billingCounty,
    billingPostcode: details.billingPostcode,
    billingCountry: details.billingCountry,
    registration: details.registration,
    make: details.make,
    customMake: '',
    model: '',
    customModel: '',
    colour: details.colour,
    package: 'park_ride',
    dropoffDate: entryDt,
    pickupDate: exitDt,
    dropoffSlot: null,
    dropoffFlight: '',
    pickupFlightTime: '',
  }

  const stripePricingInfo = {
    price: PR_PRICE_GBP,
    duration_days: durationDays,
    week1_price: PR_PRICE_GBP,
  }

  const handlePaymentSuccess = (paymentIntent, bookingReference) => {
    setPaymentSuccess({
      reference: bookingReference || paymentIntent?.id,
      amount: (paymentIntent?.amount || PR_PRICE_GBP * 100) / 100,
    })
  }

  const handlePaymentError = (err) => {
    setPaymentError(err?.message || 'Payment could not be initialised.')
  }

  return (
    <div className="bookings-new-page">
      {showWelcomeModal && (
        <div className="welcome-modal-overlay">
          <div className="welcome-modal">
            <div className="welcome-modal-icon">
              <img src="/assets/departure-icon.webp" alt="Park & Ride" />
            </div>
            <h2>Booking's a breeze</h2>
            <p>
              We've made things simpler: tell us when you're parking with us and we'll do the rest.
            </p>
            <p className="welcome-modal-options-intro">Here's how it works:</p>
            <ul className="welcome-modal-options">
              <li>Choose the date and time you'll arrive at our car park</li>
              <li>Tell us when you'll be back from your trip</li>
              <li>Let us know how many of you will be travelling on the shuttle</li>
            </ul>
            <p>
              Our system uses a <strong>24-hour clock</strong> — so 11pm is 23:00.
            </p>
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
                      event_label: 'pr_welcome_modal',
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
                onClick={() => navigate('/tag-it')}
              >
                Back
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
        <h1>Park &amp; Ride</h1>
        <p className="bookings-new-subtitle">Bournemouth International Airport (BOH)</p>

        <div className="progress-bar">
          <div className="progress-steps">
            {[1, 2, 3, 4].map(s => (
              <div
                key={s}
                className={`progress-step ${step >= s ? 'active' : ''} ${step > s ? 'completed' : ''}`}
              >
                <div className="step-number">{s}</div>
                <div className="step-label">
                  {s === 1 ? 'Trip' : s === 2 ? 'Price' : s === 3 ? 'Details' : 'Pay'}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Step 1 — date / time / travellers */}
        {step === 1 && (
          <div className="pr-form">
            <div className="form-group">
              <label htmlFor="pr-entry-date">Arrival date <span className="required">*</span></label>
              <DatePicker
                id="pr-entry-date"
                selected={entryDate}
                onChange={setEntryDate}
                dateFormat="dd/MM/yyyy"
                placeholderText="DD/MM/YYYY"
                minDate={new Date()}
                className="pr-input"
              />
            </div>

            {showEntryTime && (
              <div className="form-group pr-fade-in">
                <label htmlFor="pr-entry-time">Arrival time <span className="required">*</span></label>
                <MobileTimePicker
                  id="pr-entry-time"
                  placeholder="HH:MM"
                  value={entryTime}
                  label="Arrival time"
                  onChange={setEntryTime}
                />
                {isAmbiguous(entryTime) && (
                  <p className="time-format-warning">
                    Just checking — is that morning or evening? We use 24-hour format, so 11pm would be 23:00.
                  </p>
                )}
              </div>
            )}

            {showExitDate && (
              <div className="form-group pr-fade-in">
                <label htmlFor="pr-exit-date">Return date <span className="required">*</span></label>
                <DatePicker
                  id="pr-exit-date"
                  selected={exitDate}
                  onChange={setExitDate}
                  dateFormat="dd/MM/yyyy"
                  placeholderText="DD/MM/YYYY"
                  minDate={entryDate || new Date()}
                  className="pr-input"
                />
              </div>
            )}

            {showExitTime && (
              <div className="form-group pr-fade-in">
                <label htmlFor="pr-exit-time">Return time <span className="required">*</span></label>
                <MobileTimePicker
                  id="pr-exit-time"
                  placeholder="HH:MM"
                  value={exitTime}
                  label="Return time"
                  onChange={setExitTime}
                />
                {isAmbiguous(exitTime) && (
                  <p className="time-format-warning">
                    Just checking — is that morning or evening? We use 24-hour format, so 11pm would be 23:00.
                  </p>
                )}
              </div>
            )}

            {showTravellers && (
              <div className="form-group pr-fade-in">
                <label htmlFor="pr-travellers">Number of travellers (including driver) <span className="required">*</span></label>
                <input
                  id="pr-travellers"
                  type="number"
                  min="1"
                  max="8"
                  value={travellers}
                  onChange={(e) => {
                    const n = parseInt(e.target.value, 10)
                    setTravellers(Number.isFinite(n) ? n : 1)
                  }}
                  className="pr-input pr-input-narrow"
                />
              </div>
            )}

            {step1Error && <p className="pr-error">{step1Error}</p>}

            {showStep1Continue && (
              <div className="pr-actions pr-fade-in">
                <button
                  type="button"
                  className="welcome-modal-btn"
                  disabled={!isStep1Ready}
                  onClick={handleStep1Continue}
                >
                  Continue
                </button>
                <Link
                  to="/tag-it"
                  className="welcome-modal-back-btn"
                  style={{ display: 'inline-block', textAlign: 'center', textDecoration: 'none' }}
                >
                  Back
                </Link>
              </div>
            )}
          </div>
        )}

        {/* Step 2 — price preview */}
        {step === 2 && (
          <div className="form-section">
            <h2>Your Park &amp; Ride</h2>

            <div className="package-summary">
              <div className="package-card selected">
                <span className="package-price">£{PR_PRICE_GBP}</span>
                <span className="package-period">/ {durationDays} day{durationDays !== 1 ? 's' : ''}</span>
                <ul className="package-features">
                  <li>Self-park at our secure facility</li>
                  <li>Shuttle to and from the terminal</li>
                  <li>24/7 monitoring</li>
                  <li>No hidden fees</li>
                </ul>
              </div>
            </div>

            <div className="pr-summary-row">
              <span>Arrival</span>
              <span>{format(entryDt, 'dd/MM/yyyy HH:mm')}</span>
            </div>
            <div className="pr-summary-row">
              <span>Return</span>
              <span>{format(exitDt, 'dd/MM/yyyy HH:mm')}</span>
            </div>
            <div className="pr-summary-row">
              <span>Travellers</span>
              <span>{travellers}</span>
            </div>

            <div className="pr-actions">
              <button type="button" className="welcome-modal-btn" onClick={() => setStep(3)}>
                Continue to your details
              </button>
              <button
                type="button"
                className="welcome-modal-back-btn"
                onClick={() => setStep(1)}
              >
                Back
              </button>
            </div>
          </div>
        )}

        {/* Step 3 — contact / billing / vehicle */}
        {step === 3 && (
          <div className="form-section">
            <h2>Your details</h2>

            <h3 className="section-subtitle">Contact</h3>
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="firstName">First Name <span className="required">*</span></label>
                <input
                  type="text"
                  id="firstName"
                  name="firstName"
                  value={details.firstName}
                  onChange={handleDetailChange}
                  className={step3Attempted && !details.firstName ? 'input-error' : ''}
                />
              </div>
              <div className="form-group">
                <label htmlFor="lastName">Last Name <span className="required">*</span></label>
                <input
                  type="text"
                  id="lastName"
                  name="lastName"
                  value={details.lastName}
                  onChange={handleDetailChange}
                  className={step3Attempted && !details.lastName ? 'input-error' : ''}
                />
              </div>
            </div>
            <div className="form-group">
              <label htmlFor="email">Email <span className="required">*</span></label>
              <input
                type="email"
                id="email"
                name="email"
                value={details.email}
                onChange={handleDetailChange}
                className={step3Attempted && !isEmailValid ? 'input-error' : ''}
              />
              {step3Attempted && !isEmailValid && (
                <span className="field-error">Please enter a valid email address</span>
              )}
            </div>
            <div className="form-group">
              <label htmlFor="phone">Phone <span className="required">*</span></label>
              <PhoneInput
                international
                defaultCountry="GB"
                id="phone"
                value={details.phone}
                onChange={(v) => setDetail('phone', v || '')}
                className={`phone-input ${step3Attempted && !isPhoneValid ? 'invalid' : ''}`}
              />
              {step3Attempted && !isPhoneValid && (
                <span className="field-error">Please enter a valid phone number</span>
              )}
            </div>

            <h3 className="section-subtitle">Billing address</h3>
            <div className="form-group">
              <label htmlFor="billingAddress1">Address line 1 <span className="required">*</span></label>
              <input
                type="text"
                id="billingAddress1"
                name="billingAddress1"
                value={details.billingAddress1}
                onChange={handleDetailChange}
                className={step3Attempted && !details.billingAddress1 ? 'input-error' : ''}
              />
            </div>
            <div className="form-group">
              <label htmlFor="billingAddress2">Address line 2</label>
              <input
                type="text"
                id="billingAddress2"
                name="billingAddress2"
                value={details.billingAddress2}
                onChange={handleDetailChange}
              />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="billingCity">City <span className="required">*</span></label>
                <input
                  type="text"
                  id="billingCity"
                  name="billingCity"
                  value={details.billingCity}
                  onChange={handleDetailChange}
                  className={step3Attempted && !details.billingCity ? 'input-error' : ''}
                />
              </div>
              <div className="form-group">
                <label htmlFor="billingCounty">County</label>
                <input
                  type="text"
                  id="billingCounty"
                  name="billingCounty"
                  value={details.billingCounty}
                  onChange={handleDetailChange}
                />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="billingPostcode">Postcode <span className="required">*</span></label>
                <input
                  type="text"
                  id="billingPostcode"
                  name="billingPostcode"
                  value={details.billingPostcode}
                  onChange={handleDetailChange}
                  style={{ textTransform: 'uppercase' }}
                  className={step3Attempted && !details.billingPostcode ? 'input-error' : ''}
                />
              </div>
              <div className="form-group">
                <label htmlFor="billingCountry">Country</label>
                <input
                  type="text"
                  id="billingCountry"
                  name="billingCountry"
                  value={details.billingCountry}
                  onChange={handleDetailChange}
                />
              </div>
            </div>

            <h3 className="section-subtitle">Vehicle</h3>
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="registration">Registration <span className="required">*</span></label>
                <input
                  type="text"
                  id="registration"
                  name="registration"
                  value={details.registration}
                  onChange={(e) => setDetail('registration', e.target.value.toUpperCase())}
                  className={step3Attempted && !details.registration ? 'input-error' : ''}
                />
              </div>
              <div className="form-group">
                <label htmlFor="colour">Colour <span className="required">*</span></label>
                <input
                  type="text"
                  id="colour"
                  name="colour"
                  value={details.colour}
                  onChange={handleDetailChange}
                  className={step3Attempted && !details.colour ? 'input-error' : ''}
                />
              </div>
            </div>
            <div className="form-group">
              <label htmlFor="make">Make <span className="required">*</span></label>
              <input
                type="text"
                id="make"
                name="make"
                value={details.make}
                onChange={handleDetailChange}
                className={step3Attempted && !details.make ? 'input-error' : ''}
              />
            </div>

            {step3Attempted && !isStep3Ready && (
              <p className="pr-error">Please fill in all required fields.</p>
            )}

            <div className="pr-actions">
              <button
                type="button"
                className="welcome-modal-btn"
                onClick={handleStep3Continue}
              >
                Continue to payment
              </button>
              <button
                type="button"
                className="welcome-modal-back-btn"
                onClick={() => setStep(2)}
              >
                Back
              </button>
            </div>
          </div>
        )}

        {/* Step 4 — payment */}
        {step === 4 && (
          <div className="form-section">
            <h2>Payment</h2>

            {paymentSuccess ? (
              <div className="pr-success">
                <h3>Booking confirmed</h3>
                <p>Reference: <strong>{paymentSuccess.reference}</strong></p>
                <p>Amount paid: <strong>£{paymentSuccess.amount.toFixed(2)}</strong></p>
              </div>
            ) : (
              <>
                <h3 className="section-subtitle">Booking summary</h3>
                <div className="booking-summary">
                  <div className="summary-item">
                    <span>Service</span>
                    <span>Park &amp; Ride</span>
                  </div>
                  <div className="summary-item">
                    <span>Arrival</span>
                    <span>{format(entryDt, 'dd/MM/yyyy HH:mm')}</span>
                  </div>
                  <div className="summary-item">
                    <span>Return</span>
                    <span>{format(exitDt, 'dd/MM/yyyy HH:mm')}</span>
                  </div>
                  <div className="summary-item">
                    <span>Travellers</span>
                    <span>{travellers}</span>
                  </div>
                  <div className="summary-item">
                    <span>Vehicle</span>
                    <span>{details.colour} {details.make} ({details.registration})</span>
                  </div>
                  <div className="summary-item total">
                    <span>Total</span>
                    <span>£{PR_PRICE_GBP.toFixed(2)}</span>
                  </div>
                </div>

                {paymentError && <p className="pr-error">{paymentError}</p>}

                <StripePayment
                  formData={stripeFormData}
                  selectedFlight={null}
                  selectedArrivalFlight={null}
                  customerId={null}
                  vehicleId={null}
                  sessionId={sessionId}
                  promoCode={null}
                  promoCodeDiscount={0}
                  promoCodeType="percentage"
                  pricingInfo={stripePricingInfo}
                  onPaymentSuccess={handlePaymentSuccess}
                  onPaymentError={handlePaymentError}
                />

                <div className="pr-actions">
                  <button
                    type="button"
                    className="welcome-modal-back-btn"
                    onClick={() => setStep(3)}
                  >
                    Back to details
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default ParkAndRide
