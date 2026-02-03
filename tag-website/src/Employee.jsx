import { useState, useEffect, useCallback } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from './AuthContext'
import BookingCalendar from './components/BookingCalendar'
import './Employee.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

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
  const [inspectionPhotos, setInspectionPhotos] = useState([]) // base64 strings
  const [customerName, setCustomerName] = useState('')
  const [signedDate, setSignedDate] = useState('')
  const [savingInspection, setSavingInspection] = useState(false)

  // Complete modal state
  const [showCompleteModal, setShowCompleteModal] = useState(false)
  const [completingBooking, setCompletingBooking] = useState(null)
  const [completing, setCompleting] = useState(false)

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
      setInspectionPhotos(existing.photos || [])
      setCustomerName(existing.customer_name || '')
      setSignedDate(existing.signed_date || '')
    } else {
      setEditingInspection(null)
      setInspectionNotes('')
      setInspectionPhotos([])
      setCustomerName('')
      setSignedDate(new Date().toISOString().split('T')[0])
    }
    setShowInspectionModal(true)
  }

  // Handle photo file selection
  const handlePhotoSelect = (e) => {
    const files = Array.from(e.target.files)
    files.forEach(file => {
      const reader = new FileReader()
      reader.onloadend = () => {
        setInspectionPhotos(prev => [...prev, reader.result])
      }
      reader.readAsDataURL(file)
    })
    e.target.value = '' // Reset input
  }

  const removePhoto = (index) => {
    setInspectionPhotos(prev => prev.filter((_, i) => i !== index))
  }

  // Save inspection
  const handleSaveInspection = async () => {
    setSavingInspection(true)
    setError('')
    try {
      const url = editingInspection
        ? `${API_URL}/api/employee/inspections/${editingInspection.id}`
        : `${API_URL}/api/employee/inspections`
      const method = editingInspection ? 'PUT' : 'POST'
      const body = editingInspection
        ? { notes: inspectionNotes, photos: inspectionPhotos, customer_name: customerName, signed_date: signedDate }
        : { booking_id: inspectionBooking.id, inspection_type: inspectionType, notes: inspectionNotes, photos: inspectionPhotos, customer_name: customerName, signed_date: signedDate }

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
        />
      </main>

      {/* Inspection Modal */}
      {showInspectionModal && inspectionBooking && (
        <div className="modal-overlay" onClick={() => setShowInspectionModal(false)}>
          <div className="modal-content inspection-modal" onClick={e => e.stopPropagation()}>
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
                <label>Photos</label>
                <div className="photo-upload-area">
                  <input
                    type="file"
                    accept="image/*"
                    multiple
                    capture="environment"
                    onChange={handlePhotoSelect}
                    id="photo-input"
                    className="photo-input-hidden"
                  />
                  <label htmlFor="photo-input" className="photo-upload-btn">
                    + Add Photos
                  </label>
                </div>
                {inspectionPhotos.length > 0 && (
                  <div className="photo-previews">
                    {inspectionPhotos.map((photo, index) => (
                      <div key={index} className="photo-preview">
                        <img src={photo} alt={`Inspection photo ${index + 1}`} />
                        <button className="photo-remove" onClick={() => removePhoto(index)}>&times;</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="inspection-acknowledgement">
              <h4>Customer Acknowledgement</h4>
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
            </div>

            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={() => setShowInspectionModal(false)}>Cancel</button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={handleSaveInspection}
                disabled={savingInspection}
              >
                {savingInspection ? 'Saving...' : 'Save Inspection'}
              </button>
            </div>
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
    </div>
  )
}

export default Employee
