import { useState, useEffect, useCallback } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from './AuthContext'
import BookingCalendar from './components/BookingCalendar'
import SignaturePad from './components/SignaturePad'
import './Employee.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const PHOTO_SLOTS = [
  { key: 'front', label: 'Front', required: true },
  { key: 'rear', label: 'Rear', required: true },
  { key: 'driver_side', label: 'Driver Side', required: true },
  { key: 'passenger_side', label: 'Passenger Side', required: true },
  { key: 'additional_1', label: 'Additional 1', required: false },
  { key: 'additional_2', label: 'Additional 2', required: false },
]

const REQUIRED_PHOTO_KEYS = PHOTO_SLOTS.filter(s => s.required).map(s => s.key)

function Employee() {
  const { user, token, loading, isAuthenticated, logout } = useAuth()
  const navigate = useNavigate()

  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [inspections, setInspections] = useState({}) // { bookingId: [inspections] }
  const [error, setError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')

  // Inspection modal state
  const [showInspectionModal, setShowInspectionModal] = useState(false)
  const [inspectionBooking, setInspectionBooking] = useState(null)
  const [inspectionType, setInspectionType] = useState(null) // 'dropoff' or 'pickup'
  const [editingInspection, setEditingInspection] = useState(null)
  const [inspectionNotes, setInspectionNotes] = useState('')
  const [inspectionPhotos, setInspectionPhotos] = useState({}) // { front: 'base64...', ... }
  const [customerName, setCustomerName] = useState('')
  const [signedDate, setSignedDate] = useState('')
  const [savingInspection, setSavingInspection] = useState(false)
  const [inspectionPage, setInspectionPage] = useState(1) // 1 = form, 2 = view document
  const [vehicleInspectionRead, setVehicleInspectionRead] = useState(false)
  const [signature, setSignature] = useState(null) // base64 signature image

  // Complete modal state
  const [showCompleteModal, setShowCompleteModal] = useState(false)
  const [completingBooking, setCompletingBooking] = useState(null)
  const [completing, setCompleting] = useState(false)

  // Expanded image viewer state
  const [expandedImage, setExpandedImage] = useState(null) // { src: 'base64...', label: 'Front' }

  // Redirect if not authenticated
  useEffect(() => {
    if (!loading && !isAuthenticated) {
      navigate('/login?redirect=/employee', { replace: true })
    }
  }, [loading, isAuthenticated, navigate])

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  const triggerRefresh = () => setRefreshTrigger(prev => prev + 1)

  // Fetch inspections for a booking
  const fetchInspections = async (bookingId) => {
    try {
      const response = await fetch(`${API_URL}/api/employee/inspections/${bookingId}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setInspections(prev => ({ ...prev, [bookingId]: data.inspections || [] }))
      }
    } catch (err) {
      // Silently fail - inspections just won't show status
    }
  }

  // Open inspection modal
  const openInspection = (booking, type) => {
    const bookingInspections = inspections[booking.id] || []
    const existing = bookingInspections.find(i => i.inspection_type === type)

    setInspectionBooking(booking)
    setInspectionType(type)

    if (existing) {
      setEditingInspection(existing)
      setInspectionNotes(existing.notes || '')
      // Handle both old array format and new object format
      const photos = existing.photos || {}
      setInspectionPhotos(Array.isArray(photos) ? {} : photos)
      setCustomerName(existing.customer_name || '')
      setSignedDate(existing.signed_date || '')
      setVehicleInspectionRead(existing.vehicle_inspection_read || false)
      setSignature(existing.signature || null)
    } else {
      setEditingInspection(null)
      setInspectionNotes('')
      setInspectionPhotos({})
      setCustomerName('')
      setSignedDate(new Date().toISOString().split('T')[0])
      setVehicleInspectionRead(false)
      setSignature(null)
    }
    setInspectionPage(1)
    setShowInspectionModal(true)
  }

  // Handle photo capture for a specific slot
  const handlePhotoCapture = (slotKey, e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onloadend = () => {
      setInspectionPhotos(prev => ({ ...prev, [slotKey]: reader.result }))
    }
    reader.readAsDataURL(file)
    e.target.value = '' // Reset input so same slot can retake
  }

  const removePhoto = (slotKey) => {
    setInspectionPhotos(prev => {
      const updated = { ...prev }
      delete updated[slotKey]
      return updated
    })
  }

  // Save inspection
  const handleSaveInspection = async () => {
    // Validate required photos
    const missingPhotos = REQUIRED_PHOTO_KEYS.filter(key => !inspectionPhotos[key])
    if (missingPhotos.length > 0) {
      const labels = missingPhotos.map(key => PHOTO_SLOTS.find(s => s.key === key)?.label)
      setError(`Required photos missing: ${labels.join(', ')}`)
      return
    }

    setSavingInspection(true)
    setError('')
    try {
      const url = editingInspection
        ? `${API_URL}/api/employee/inspections/${editingInspection.id}`
        : `${API_URL}/api/employee/inspections`
      const method = editingInspection ? 'PUT' : 'POST'
      const body = editingInspection
        ? { notes: inspectionNotes, photos: inspectionPhotos, customer_name: customerName, signed_date: signedDate, signature: signature, vehicle_inspection_read: vehicleInspectionRead }
        : { booking_id: inspectionBooking.id, inspection_type: inspectionType, notes: inspectionNotes, photos: inspectionPhotos, customer_name: customerName, signed_date: signedDate, signature: signature, vehicle_inspection_read: vehicleInspectionRead }

      const response = await fetch(url, {
        method,
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      })
      if (response.ok) {
        setShowInspectionModal(false)
        setSuccessMessage(`${inspectionType === 'dropoff' ? 'Drop-off' : 'Return'} inspection saved`)
        setTimeout(() => setSuccessMessage(''), 3000)
        fetchInspections(inspectionBooking.id)
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to save inspection')
        setTimeout(() => setError(''), 5000)
      }
    } catch (err) {
      setError('Network error saving inspection')
      setTimeout(() => setError(''), 5000)
    } finally {
      setSavingInspection(false)
    }
  }

  // Complete booking
  const handleCompleteBooking = async () => {
    if (!completingBooking) return
    setCompleting(true)
    try {
      const response = await fetch(`${API_URL}/api/employee/bookings/${completingBooking.id}/complete`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        setShowCompleteModal(false)
        setCompletingBooking(null)
        setSuccessMessage(`Booking ${completingBooking.reference} marked as completed`)
        setTimeout(() => setSuccessMessage(''), 3000)
        triggerRefresh()
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to complete booking')
        setTimeout(() => setError(''), 5000)
      }
    } catch (err) {
      setError('Network error completing booking')
      setTimeout(() => setError(''), 5000)
    } finally {
      setCompleting(false)
    }
  }

  // Render action buttons for each booking in the calendar
  const renderBookingActions = useCallback((booking, type) => {
    // Fetch inspections if we haven't yet
    if (!inspections[booking.id]) {
      fetchInspections(booking.id)
    }

    const bookingInspections = inspections[booking.id] || []
    const hasInspection = bookingInspections.some(i => i.inspection_type === type)
    const isCompleted = booking.status === 'completed'

    if (type === 'dropoff') {
      return (
        <div className="booking-actions-row">
          <button
            className={`inspection-btn ${hasInspection ? 'inspection-done' : ''}`}
            onClick={(e) => { e.stopPropagation(); openInspection(booking, 'dropoff') }}
          >
            {hasInspection ? 'View/Edit Inspection' : 'Vehicle Inspection'}
          </button>
        </div>
      )
    }

    if (type === 'pickup') {
      return (
        <div className="booking-actions-row">
          <button
            className={`inspection-btn ${hasInspection ? 'inspection-done' : ''}`}
            onClick={(e) => { e.stopPropagation(); openInspection(booking, 'pickup') }}
          >
            {hasInspection ? 'View/Edit Inspection' : 'Return Inspection'}
          </button>
          {isCompleted ? (
            <span className="completed-badge">Completed</span>
          ) : (
            <button
              className="complete-btn"
              onClick={(e) => { e.stopPropagation(); setCompletingBooking(booking); setShowCompleteModal(true) }}
            >
              Complete Booking
            </button>
          )}
        </div>
      )
    }

    return null
  }, [inspections, token])

  if (loading) {
    return (
      <div className="employee-loading">
        <div className="spinner"></div>
        <p>Loading...</p>
      </div>
    )
  }

  if (!isAuthenticated) {
    return null
  }

  return (
    <div className="employee-container">
      <header className="employee-header">
        <div className="employee-header-left">
          <Link to="/">
            <img src="/assets/logo.svg" alt="TAG Parking" className="employee-logo" />
          </Link>
          <h1>Employee Portal</h1>
        </div>
        <div className="employee-header-right">
          <span className="employee-user">
            {user?.first_name} {user?.last_name}
          </span>
          <button onClick={handleLogout} className="employee-logout">
            Logout
          </button>
        </div>
      </header>

      <main className="employee-content">
        {successMessage && <div className="employee-success">{successMessage}</div>}
        {error && <div className="employee-error">{error}</div>}

        <BookingCalendar
          token={token}
          renderBookingActions={renderBookingActions}
          refreshTrigger={refreshTrigger}
          apiEndpoint="/api/employee/bookings"
        />
      </main>

      {/* Inspection Modal */}
      {showInspectionModal && inspectionBooking && (
        <div className="modal-overlay" onClick={() => setShowInspectionModal(false)}>
          <div className="modal-content inspection-modal" onClick={e => e.stopPropagation()}>

            {/* Page 1: Inspection Form */}
            {inspectionPage === 1 && (
              <>
                <h3>{editingInspection ? 'Edit' : 'New'} {inspectionType === 'dropoff' ? 'Drop-off' : 'Return'} Inspection</h3>
                <div className="inspection-booking-info">
                  <span className="inspection-ref">{inspectionBooking.reference}</span>
                  <span>{inspectionBooking.customer?.first_name || inspectionBooking.customer_first_name} {inspectionBooking.customer?.last_name || inspectionBooking.customer_last_name}</span>
                  <span>{inspectionBooking.vehicle?.registration || inspectionBooking.vehicle_registration}</span>
                </div>

                <div className="inspection-form">
                  <div className="inspection-field">
                    <label>Notes</label>
                    <textarea
                      value={inspectionNotes}
                      onChange={e => setInspectionNotes(e.target.value)}
                      placeholder="Add inspection notes..."
                      rows={4}
                    />
                  </div>

                  <div className="inspection-field">
                    <label>Vehicle Photos</label>
                    <div className="photo-slots-grid">
                      {PHOTO_SLOTS.map(slot => (
                        <div key={slot.key} className={`photo-slot ${slot.required && !inspectionPhotos[slot.key] ? 'photo-slot-required' : ''}`}>
                          <span className="photo-slot-label">
                            {slot.label} {slot.required ? <span className="required">*</span> : <span className="optional">(optional)</span>}
                          </span>
                          {inspectionPhotos[slot.key] ? (
                            <div className="photo-slot-preview">
                              <img
                                src={inspectionPhotos[slot.key]}
                                alt={slot.label}
                                onClick={() => setExpandedImage({ src: inspectionPhotos[slot.key], label: slot.label })}
                                className="photo-slot-img-clickable"
                              />
                              <button
                                className="photo-slot-retake"
                                onClick={() => removePhoto(slot.key)}
                              >
                                Retake
                              </button>
                            </div>
                          ) : (
                            <label className="photo-slot-capture" htmlFor={`photo-${slot.key}`}>
                              <span className="photo-slot-icon">&#128247;</span>
                              <span>Tap to capture</span>
                              <input
                                type="file"
                                accept="image/*"
                                capture="environment"
                                onChange={(e) => handlePhotoCapture(slot.key, e)}
                                id={`photo-${slot.key}`}
                                className="photo-input-hidden"
                              />
                            </label>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="inspection-acknowledgement">
                  <h4>Customer Acknowledgement</h4>

                  {/* Vehicle Inspection Read Checkbox */}
                  <div className="vehicle-inspection-checkbox">
                    <label className="checkbox-label-inline">
                      <input
                        type="checkbox"
                        checked={vehicleInspectionRead}
                        onChange={e => setVehicleInspectionRead(e.target.checked)}
                      />
                      <span>I have read the </span>
                      <button
                        type="button"
                        className="view-document-link"
                        onClick={() => setInspectionPage(2)}
                      >
                        Vehicle Inspection Terms
                      </button>
                    </label>
                  </div>

                  <p className="acknowledgement-text">
                    I confirm that I have reviewed the vehicle condition and agree with the inspection findings.
                  </p>

                  <div className="acknowledgement-fields">
                    <div className="inspection-field">
                      <label>Customer Name</label>
                      <input
                        type="text"
                        value={customerName}
                        onChange={e => setCustomerName(e.target.value)}
                        placeholder="Enter full name"
                        className="acknowledgement-input"
                      />
                    </div>
                    <div className="inspection-field">
                      <label>Date</label>
                      <input
                        type="date"
                        value={signedDate}
                        onChange={e => setSignedDate(e.target.value)}
                        className="acknowledgement-input"
                      />
                    </div>
                  </div>

                  {/* Signature Pad */}
                  <div className="inspection-field signature-field">
                    <label>Customer Signature <span className="required">*</span></label>
                    <SignaturePad
                      onSignatureChange={setSignature}
                      initialSignature={signature}
                    />
                  </div>
                </div>

                <div className="modal-actions">
                  <button className="modal-btn modal-btn-secondary" onClick={() => setShowInspectionModal(false)}>Cancel</button>
                  <button
                    className="modal-btn modal-btn-primary"
                    onClick={handleSaveInspection}
                    disabled={savingInspection || !signature || !vehicleInspectionRead}
                  >
                    {savingInspection ? 'Saving...' : 'Save Inspection'}
                  </button>
                </div>
              </>
            )}

            {/* Page 2: Vehicle Inspection Document */}
            {inspectionPage === 2 && (
              <>
                <div className="inspection-document-header">
                  <button
                    type="button"
                    className="back-to-form-btn"
                    onClick={() => setInspectionPage(1)}
                  >
                    &larr; Back to Inspection
                  </button>
                  <h3>Vehicle Inspection Terms</h3>
                </div>

                <div className="inspection-document-content">
                  <div className="document-logo">
                    <img src="/assets/logo.svg" alt="TAG" />
                  </div>

                  <h2>Meet & Greet Vehicle Inspection – Terms & Conditions</h2>

                  <p className="document-intro">
                    These Terms & Conditions apply to meet and greet vehicle inspection services (the "Services") provided by TAG Parking ("we", "us") to the customer ("you"). By booking our Services, you agree to these terms.
                  </p>

                  <h4>1. Scope of Services</h4>
                  <p>1.1 We provide a visual, non-invasive inspection of a vehicle at an agreed location and time.</p>
                  <p>1.2 Inspections are limited to externally observable conditions only at the time of inspection.</p>
                  <p>1.3 The inspection is not a mechanical, diagnostic, roadworthiness, or safety test.</p>

                  <h4>2. What the Inspection Includes</h4>
                  <ul>
                    <li>Exterior condition (bodywork, paint, glass, lights, tyres).</li>
                    <li>Visual checks of easily accessible items only.</li>
                    <li>Photographs and/or a brief written summary where included in your booking.</li>
                  </ul>

                  <h4>3. What the Inspection Does Not Include</h4>
                  <ul>
                    <li>Interior inspection or assessment.</li>
                    <li>Under-bonnet, engine, gearbox, electrical, or electronic inspection.</li>
                    <li>Hidden, latent, intermittent, or future faults.</li>
                    <li>Valuation, price negotiation, or legal advice.</li>
                    <li>MOT, safety certification, or warranty validation.</li>
                  </ul>

                  <h4>4. Customer Responsibilities</h4>
                  <p>4.1 You must ensure the vehicle is accessible, safe to inspect, and available at the agreed time.</p>
                  <p>4.2 You are responsible for obtaining permission from the vehicle owner or seller.</p>
                  <p>4.3 Any delays or access issues may limit the inspection or result in cancellation.</p>

                  <h4>5. Fees, Cancellations & Refunds</h4>
                  <p>5.1 Fees are as agreed at booking and payable in advance unless otherwise stated.</p>
                  <p>5.2 Cancellations made 24 hours before the appointment may be refunded or rescheduled.</p>
                  <p>5.3 Late cancellations or no-shows may be charged in full.</p>
                  <p>5.4 Fees are non-refundable once the inspection has started.</p>

                  <h4>6. Reports & Reliance</h4>
                  <p>6.1 Any feedback or report is provided for your personal use only.</p>
                  <p>6.2 Reports reflect our opinion based on a visual inspection at a single point in time.</p>
                  <p>6.3 Vehicles may develop faults after inspection for which we are not responsible.</p>

                  <h4>7. Limitation of Liability</h4>
                  <p>7.1 To the maximum extent permitted by law, we are not liable for indirect or consequential loss, or for defects outside the stated scope.</p>
                  <p>7.2 Our total liability is limited to the fee paid for the Services.</p>

                  <h4>8. Health & Safety</h4>
                  <p>8.1 We may refuse or stop an inspection if conditions are unsafe.</p>
                  <p>8.2 We accept no responsibility for hazards at the inspection location.</p>

                  <h4>9. Data & Intellectual Property</h4>
                  <p>9.1 Inspection reports and photographs remain our intellectual property.</p>
                  <p>9.2 Personal data will be handled in accordance with applicable data protection laws.</p>

                  <h4>10. Governing Law</h4>
                  <p>10.1 These Terms & Conditions are governed by the laws of England & Wales.</p>

                  <div className="document-footer">
                    <p><strong>Business Name:</strong> TAG Parking</p>
                    <p><strong>Contact:</strong> info@tagparking.co.uk</p>
                  </div>
                </div>

                <div className="modal-actions">
                  <button
                    className="modal-btn modal-btn-primary"
                    onClick={() => setInspectionPage(1)}
                  >
                    Back to Inspection
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Complete Booking Modal */}
      {showCompleteModal && completingBooking && (
        <div className="modal-overlay" onClick={() => setShowCompleteModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <h3>Complete Booking</h3>
            <p>Mark booking <strong>{completingBooking.reference}</strong> as completed?</p>
            <p className="modal-subtext">
              {completingBooking.customer?.first_name || completingBooking.customer_first_name} {completingBooking.customer?.last_name || completingBooking.customer_last_name} — {completingBooking.vehicle?.registration || completingBooking.vehicle_registration}
            </p>
            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={() => setShowCompleteModal(false)}>Cancel</button>
              <button className="modal-btn modal-btn-success" onClick={handleCompleteBooking} disabled={completing}>
                {completing ? 'Completing...' : 'Confirm Complete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Fullscreen Image Viewer */}
      {expandedImage && (
        <div className="image-viewer-overlay" onClick={() => setExpandedImage(null)}>
          <button className="image-viewer-close" onClick={() => setExpandedImage(null)}>
            &times;
          </button>
          <div className="image-viewer-label">{expandedImage.label}</div>
          <img
            src={expandedImage.src}
            alt={expandedImage.label}
            className="image-viewer-img"
            onClick={e => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  )
}

export default Employee
