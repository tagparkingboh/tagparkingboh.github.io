import { useState, useMemo } from 'react'
import { getMakes, getModels } from 'car-info'
import DatePicker from 'react-datepicker'
import { format } from 'date-fns'
import 'react-datepicker/dist/react-datepicker.css'
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
    customMake: '',
    model: '',
    customModel: '',
    colour: '',
    // Trip
    dropoffDate: null,
    dropoffTime: null,
    pickupDate: null,
    pickupTime: null,
    // Payment
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

  // Get car makes and models from car-info library
  const carMakes = useMemo(() => getMakes().sort(), [])
  const carModels = useMemo(() => {
    if (!formData.make || formData.make === 'Other') return []
    return getModels(formData.make) || []
  }, [formData.make])

  // Convert string to Title Case
  const toTitleCase = (str) => {
    if (!str) return str
    return str.toLowerCase().replace(/\b\w/g, char => char.toUpperCase())
  }

  const titleCaseFields = ['colour', 'customMake', 'customModel', 'billingAddress1', 'billingAddress2', 'billingCity', 'billingCounty']

  const handleChange = (e) => {
    const { name, value } = e.target
    const processedValue = titleCaseFields.includes(name) ? toTitleCase(value) : value
    setFormData(prev => ({
      ...prev,
      [name]: processedValue
    }))

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
    setFormData(prev => ({
      ...prev,
      [field]: date
    }))
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

        const makeExists = carMakes.some(m => m.toUpperCase() === data.make.toUpperCase())

        setFormData(prev => ({
          ...prev,
          make: makeExists ? formattedMake : 'Other',
          customMake: makeExists ? '' : formattedMake,
          colour: formattedColour,
          model: '',
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

  // Handle address selection from dropdown
  const handleAddressSelect = (e) => {
    const selectedUprn = e.target.value
    if (!selectedUprn) return

    const selectedAddress = addressList.find(addr => addr.uprn === selectedUprn)
    if (selectedAddress) {
      let address1 = ''
      let address2 = ''

      let streetParts = []
      if (selectedAddress.building_number) {
        streetParts.push(selectedAddress.building_number)
      }
      if (selectedAddress.thoroughfare) {
        streetParts.push(selectedAddress.thoroughfare)
      }
      const streetAddress = streetParts.join(' ')

      if (selectedAddress.building_name) {
        address1 = selectedAddress.building_name
        address2 = streetAddress
      } else {
        address1 = streetAddress
      }

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

  // Form validation
  const isFormValid = () => {
    return (
      formData.firstName &&
      formData.lastName &&
      formData.email &&
      formData.billingAddress1 &&
      formData.billingCity &&
      formData.billingPostcode &&
      formData.registration &&
      (formData.make && (formData.make !== 'Other' || formData.customMake)) &&
      (formData.model && (formData.model !== 'Other' || formData.customModel)) &&
      formData.colour &&
      formData.dropoffDate &&
      formData.dropoffTime &&
      formData.pickupDate &&
      formData.pickupTime &&
      formData.stripePaymentLink &&
      formData.amount
    )
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

    try {
      const response = await fetch(`${API_URL}/api/admin/manual-booking`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
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
          make: formData.make === 'Other' ? formData.customMake : formData.make,
          model: formData.model === 'Other' ? formData.customModel : formData.model,
          colour: formData.colour,
          dropoff_date: format(formData.dropoffDate, 'yyyy-MM-dd'),
          dropoff_time: format(formData.dropoffTime, 'HH:mm'),
          pickup_date: format(formData.pickupDate, 'yyyy-MM-dd'),
          pickup_time: format(formData.pickupTime, 'HH:mm'),
          stripe_payment_link: formData.stripePaymentLink,
          amount_pence: Math.round(parseFloat(formData.amount) * 100),
          notes: formData.notes,
        }),
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
          customMake: '',
          model: '',
          customModel: '',
          colour: '',
          dropoffDate: null,
          dropoffTime: null,
          pickupDate: null,
          pickupTime: null,
          stripePaymentLink: '',
          amount: '',
          notes: '',
        })
        setDvlaVerified(false)
        setAddressList([])
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to create manual booking')
      }
    } catch (err) {
      setError('Network error. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="manual-booking">
      <h2>Create Manual Booking</h2>
      <p className="manual-booking-description">
        Create a booking and send a payment link to the customer via email.
      </p>

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
            {formData.make === 'Other' && (
              <div className="form-group">
                <label htmlFor="customMake">Custom Make <span className="required">*</span></label>
                <input
                  type="text"
                  id="customMake"
                  name="customMake"
                  value={formData.customMake}
                  onChange={handleChange}
                  required
                />
              </div>
            )}
          </div>

          <div className="form-row">
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
                  required
                />
              )}
            </div>
            <div className="form-group">
              <label htmlFor="model">Model <span className="required">*</span></label>
              {formData.make === 'Other' ? (
                <input
                  type="text"
                  id="customModel"
                  name="customModel"
                  value={formData.customModel}
                  onChange={handleChange}
                  placeholder="Enter model"
                  required
                />
              ) : (
                <select
                  id="model"
                  name="model"
                  value={formData.model}
                  onChange={handleChange}
                  required
                  disabled={!formData.make}
                >
                  <option value="">Select model</option>
                  {carModels.map(model => (
                    <option key={model} value={model}>{model}</option>
                  ))}
                  <option value="Other">Other</option>
                </select>
              )}
            </div>
          </div>
          {formData.model === 'Other' && formData.make !== 'Other' && (
            <div className="form-group">
              <label htmlFor="customModel">Custom Model <span className="required">*</span></label>
              <input
                type="text"
                id="customModel"
                name="customModel"
                value={formData.customModel}
                onChange={handleChange}
                required
              />
            </div>
          )}
        </div>

        {/* Trip Details Section */}
        <div className="manual-booking-section">
          <h3>Trip Details</h3>
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="dropoffDate">Drop-off Date <span className="required">*</span></label>
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
            <div className="form-group">
              <label htmlFor="dropoffTime">Drop-off Time <span className="required">*</span></label>
              <DatePicker
                selected={formData.dropoffTime}
                onChange={(time) => handleDateChange(time, 'dropoffTime')}
                showTimeSelect
                showTimeSelectOnly
                timeIntervals={15}
                timeCaption="Time"
                dateFormat="HH:mm"
                timeFormat="HH:mm"
                placeholderText="Select time"
                className="date-picker-input"
                id="dropoffTime"
              />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="pickupDate">Pick-up Date <span className="required">*</span></label>
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
            <div className="form-group">
              <label htmlFor="pickupTime">Pick-up Time <span className="required">*</span></label>
              <DatePicker
                selected={formData.pickupTime}
                onChange={(time) => handleDateChange(time, 'pickupTime')}
                showTimeSelect
                showTimeSelectOnly
                timeIntervals={15}
                timeCaption="Time"
                dateFormat="HH:mm"
                timeFormat="HH:mm"
                placeholderText="Select time"
                className="date-picker-input"
                id="pickupTime"
              />
            </div>
          </div>
        </div>

        {/* Payment Section */}
        <div className="manual-booking-section">
          <h3>Payment</h3>
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
                placeholder="99.00"
                required
              />
            </div>
            <div className="form-group">
              <label htmlFor="stripePaymentLink">Stripe Payment Link <span className="required">*</span></label>
              <input
                type="url"
                id="stripePaymentLink"
                name="stripePaymentLink"
                value={formData.stripePaymentLink}
                onChange={handleChange}
                placeholder="https://buy.stripe.com/..."
                required
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
                <li>Drop-off: {formatDate(formData.dropoffDate)} at {formData.dropoffTime ? format(formData.dropoffTime, 'HH:mm') : ''}</li>
                <li>Pick-up: {formatDate(formData.pickupDate)} at {formData.pickupTime ? format(formData.pickupTime, 'HH:mm') : ''}</li>
                <li>Vehicle: {formData.colour} {formData.make === 'Other' ? formData.customMake : formData.make} {formData.model === 'Other' ? formData.customModel : formData.model}</li>
                <li>Registration: {formData.registration.toUpperCase()}</li>
                <li>Total: £{parseFloat(formData.amount).toFixed(2)}</li>
              </ul>
              <p>Please complete your payment using the link below:</p>
              <p><a href={formData.stripePaymentLink}>{formData.stripePaymentLink}</a></p>
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
