import { useState, useEffect, useMemo } from 'react'
import { useAuth } from '../../AuthContext'
import { API_URL } from '../adminUtils'
import '../adminStyles.css'

// Photo slots - must match Employee.jsx
const PHOTO_SLOTS = [
  { key: 'front', label: 'Front' },
  { key: 'rear', label: 'Rear' },
  { key: 'driver_side', label: 'Driver Side' },
  { key: 'passenger_side', label: 'Passenger Side' },
  { key: 'additional_1', label: 'Additional 1' },
  { key: 'additional_2', label: 'Additional 2' },
]

// UK date format helpers (DD/MM/YYYY)
const isoToUkDate = (isoDate) => {
  if (!isoDate) return ''
  const [year, month, day] = isoDate.split('-')
  return `${day}/${month}/${year}`
}

const ukToIsoDate = (ukDate) => {
  if (!ukDate) return ''
  const parts = ukDate.split('/')
  if (parts.length !== 3) return ''
  const [day, month, year] = parts
  return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`
}

// Test email domains to filter out
const testEmailDomains = ['yopmail.com', 'mailinator.com', 'guerrillamail.com', 'tempmail.com', 'fakeinbox.com', 'test.com', 'example.com', 'staging.tag.com']

const isTestEmail = (email) => {
  if (!email) return false
  const domain = email.toLowerCase().split('@')[1]
  return testEmailDomains.includes(domain) || domain?.includes('test') || domain?.includes('staging')
}

function BookingsPage() {
  const { token } = useAuth()

  // Bookings state
  const [bookings, setBookings] = useState([])
  const [loadingData, setLoadingData] = useState(false)
  const [error, setError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [sortAsc, setSortAsc] = useState(true)
  const [hideTestEmails, setHideTestEmails] = useState(true)
  const [expandedBookingId, setExpandedBookingId] = useState(null)
  const [collapsedStatusSections, setCollapsedStatusSections] = useState({
    confirmed: false,
    completed: true,
    pending: false,
    cancelled: true
  })
  const [expandedBookingMonths, setExpandedBookingMonths] = useState({})

  // Cancel booking state
  const [cancellingId, setCancellingId] = useState(null)
  const [showCancelModal, setShowCancelModal] = useState(false)
  const [bookingToCancel, setBookingToCancel] = useState(null)

  // Mark paid state
  const [markingPaidId, setMarkingPaidId] = useState(null)

  // Delete booking state
  const [deletingId, setDeletingId] = useState(null)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [bookingToDelete, setBookingToDelete] = useState(null)

  // Edit booking state
  const [showEditModal, setShowEditModal] = useState(false)
  const [bookingToEdit, setBookingToEdit] = useState(null)
  const [savingEdit, setSavingEdit] = useState(false)
  const [editForm, setEditForm] = useState({
    dropoff_time: '',
    flight_departure_time: '',
    dropoff_airline_name: '',
    dropoff_flight_number: '',
    dropoff_destination: '',
    pickup_date: '',
    flight_arrival_time: '',
    pickup_airline_name: '',
    pickup_flight_number: '',
    pickup_origin: '',
  })

  // Resend email state
  const [resendingEmailId, setResendingEmailId] = useState(null)
  const [showResendModal, setShowResendModal] = useState(false)
  const [bookingToResend, setBookingToResend] = useState(null)

  // Cancellation email state
  const [sendingCancellationEmailId, setSendingCancellationEmailId] = useState(null)
  const [showCancellationEmailModal, setShowCancellationEmailModal] = useState(false)
  const [bookingForCancellationEmail, setBookingForCancellationEmail] = useState(null)

  // Refund email state
  const [sendingRefundEmailId, setSendingRefundEmailId] = useState(null)
  const [showRefundEmailModal, setShowRefundEmailModal] = useState(false)
  const [bookingForRefundEmail, setBookingForRefundEmail] = useState(null)

  // Founder email state
  const [sendingFounderEmailId, setSendingFounderEmailId] = useState(null)
  const [showFounderEmailModal, setShowFounderEmailModal] = useState(false)
  const [bookingForFounderEmail, setBookingForFounderEmail] = useState(null)

  // Return Vehicle Inspection modal state
  const [showReturnInspectionModal, setShowReturnInspectionModal] = useState(false)
  const [bookingForInspection, setBookingForInspection] = useState(null)
  const [returnInspectionData, setReturnInspectionData] = useState(null)
  const [loadingReturnInspection, setLoadingReturnInspection] = useState(false)

  // Drop-off Vehicle Inspection modal state
  const [showDropoffInspectionModal, setShowDropoffInspectionModal] = useState(false)
  const [bookingForDropoffInspection, setBookingForDropoffInspection] = useState(null)
  const [dropoffInspectionData, setDropoffInspectionData] = useState(null)
  const [loadingDropoffInspection, setLoadingDropoffInspection] = useState(false)

  // Fetch bookings on mount
  useEffect(() => {
    if (token) {
      fetchBookings()
    }
  }, [token])

  const fetchBookings = async () => {
    setLoadingData(true)
    setError('')
    try {
      const response = await fetch(`${API_URL}/api/admin/bookings`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setBookings(data.bookings || data || [])
      } else {
        setError('Failed to load bookings')
      }
    } catch (err) {
      setError('Network error')
    } finally {
      setLoadingData(false)
    }
  }

  // Filter and sort bookings
  const filteredBookings = useMemo(() => {
    let filtered = [...bookings]

    // Hide test emails by default
    if (hideTestEmails) {
      filtered = filtered.filter(b => !isTestEmail(b.customer?.email))
    }

    // Apply status filter
    if (statusFilter !== 'all') {
      filtered = filtered.filter(b => b.status?.toLowerCase() === statusFilter)
    }

    // Apply search filter
    if (searchTerm.trim()) {
      const search = searchTerm.toLowerCase().trim()
      filtered = filtered.filter(b =>
        b.reference?.toLowerCase().includes(search) ||
        b.customer?.first_name?.toLowerCase().includes(search) ||
        b.customer?.last_name?.toLowerCase().includes(search) ||
        b.customer?.email?.toLowerCase().includes(search) ||
        b.vehicle?.registration?.toLowerCase().includes(search) ||
        `${b.customer?.first_name} ${b.customer?.last_name}`.toLowerCase().includes(search)
      )
    }

    // Sort by dropoff date
    filtered.sort((a, b) => {
      const dateA = new Date(a.dropoff_date)
      const dateB = new Date(b.dropoff_date)
      return sortAsc ? dateA - dateB : dateB - dateA
    })

    return filtered
  }, [bookings, searchTerm, statusFilter, hideTestEmails, sortAsc])

  // Recent 10 bookings (sorted by ID descending - newest first)
  const recentBookings = useMemo(() => {
    let recent = [...bookings]

    // Hide test emails
    if (hideTestEmails) {
      recent = recent.filter(b => !isTestEmail(b.customer?.email))
    }

    // Sort by ID descending (newest first)
    recent.sort((a, b) => b.id - a.id)

    // Take top 10 most recent
    return recent.slice(0, 10)
  }, [bookings, hideTestEmails])

  // Group bookings by status
  const bookingsByStatus = useMemo(() => {
    const groups = {
      confirmed: [],
      completed: [],
      pending: [],
      cancelled: []
    }

    filteredBookings.forEach(booking => {
      const status = (booking.status || 'pending').toLowerCase()
      if (groups[status]) {
        groups[status].push(booking)
      } else {
        // Handle refunded or other statuses - put in cancelled
        groups.cancelled.push(booking)
      }
    })

    return groups
  }, [filteredBookings])

  const toggleStatusSection = (status) => {
    setCollapsedStatusSections(prev => ({
      ...prev,
      [status]: !prev[status]
    }))
  }

  // Helper to group bookings by month (for confirmed/completed)
  const groupBookingsByMonth = (bookingsList) => {
    const groups = {}
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                        'July', 'August', 'September', 'October', 'November', 'December']

    bookingsList.forEach(booking => {
      if (!booking.dropoff_date) return
      const monthKey = booking.dropoff_date.substring(0, 7) // YYYY-MM
      if (!groups[monthKey]) {
        const [year, month] = monthKey.split('-')
        groups[monthKey] = {
          label: `${monthNames[parseInt(month) - 1]} ${year}`,
          bookings: []
        }
      }
      groups[monthKey].bookings.push(booking)
    })

    return groups
  }

  const toggleBookingMonth = (statusKey, monthKey) => {
    const key = `${statusKey}-${monthKey}`
    setExpandedBookingMonths(prev => ({
      ...prev,
      [key]: !prev[key]
    }))
  }

  const toggleBookingExpanded = (bookingId) => {
    setExpandedBookingId(expandedBookingId === bookingId ? null : bookingId)
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return '-'
    const [year, month, day] = dateStr.split('-')
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    const date = new Date(Number(year), Number(month) - 1, Number(day))
    return `${days[date.getDay()]}, ${day} ${months[Number(month) - 1]} ${year}`
  }

  const formatTime = (timeStr) => {
    if (!timeStr) return ''
    return timeStr.substring(0, 5)
  }

  const formatDateTimeUK = (dateStr) => {
    if (!dateStr) return '-'
    const date = new Date(dateStr)
    return date.toLocaleString('en-GB', { timeZone: 'Europe/London' })
  }

  // Cancel booking handlers
  const handleCancelClick = (booking, e) => {
    e.stopPropagation()
    setBookingToCancel(booking)
    setShowCancelModal(true)
  }

  const handleConfirmCancel = async () => {
    if (!bookingToCancel) return

    setCancellingId(bookingToCancel.id)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/${bookingToCancel.id}/cancel`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        await fetchBookings()
        setShowCancelModal(false)
        setBookingToCancel(null)
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to cancel booking')
      }
    } catch (err) {
      setError('Network error while cancelling booking')
    } finally {
      setCancellingId(null)
    }
  }

  // Mark paid handler
  const handleMarkPaid = async (booking, e) => {
    e.stopPropagation()
    setMarkingPaidId(booking.id)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/${booking.id}/mark-paid`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
      })

      const data = await response.json()

      if (response.ok) {
        fetchBookings()
      } else {
        setError(data.detail || 'Failed to mark booking as paid')
      }
    } catch (err) {
      setError('Network error while updating booking')
    } finally {
      setMarkingPaidId(null)
    }
  }

  // Delete booking handlers
  const handleDeleteClick = (booking, e) => {
    e.stopPropagation()
    setBookingToDelete(booking)
    setShowDeleteModal(true)
  }

  const confirmDeleteBooking = async () => {
    if (!bookingToDelete) return

    setDeletingId(bookingToDelete.id)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/${bookingToDelete.id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })

      const data = await response.json()

      if (response.ok) {
        setSuccessMessage(data.message || 'Booking deleted successfully')
        fetchBookings()
        setTimeout(() => setSuccessMessage(''), 5000)
      } else {
        setError(data.detail || 'Failed to delete booking')
      }
    } catch (err) {
      setError('Network error while deleting booking')
    } finally {
      setDeletingId(null)
      setShowDeleteModal(false)
      setBookingToDelete(null)
    }
  }

  // Edit booking handlers
  const handleEditBookingClick = (booking, e) => {
    e.stopPropagation()
    setBookingToEdit(booking)
    setEditForm({
      dropoff_time: booking.dropoff_time || '',
      flight_departure_time: booking.flight_departure_time || '',
      dropoff_airline_name: booking.dropoff_airline_name || '',
      dropoff_flight_number: booking.dropoff_flight_number || '',
      dropoff_destination: booking.dropoff_destination || '',
      pickup_date: isoToUkDate(booking.pickup_date) || '',
      flight_arrival_time: booking.flight_arrival_time || '',
      pickup_airline_name: booking.pickup_airline_name || '',
      pickup_flight_number: booking.pickup_flight_number || '',
      pickup_origin: booking.pickup_origin || '',
    })
    setShowEditModal(true)
  }

  const confirmEditBooking = async () => {
    if (!bookingToEdit) return

    setSavingEdit(true)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/${bookingToEdit.id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          dropoff_time: editForm.dropoff_time || null,
          flight_departure_time: editForm.flight_departure_time || null,
          dropoff_airline_name: editForm.dropoff_airline_name || null,
          dropoff_flight_number: editForm.dropoff_flight_number || null,
          dropoff_destination: editForm.dropoff_destination || null,
          pickup_date: ukToIsoDate(editForm.pickup_date) || null,
          flight_arrival_time: editForm.flight_arrival_time || null,
          pickup_airline_name: editForm.pickup_airline_name || null,
          pickup_flight_number: editForm.pickup_flight_number || null,
          pickup_origin: editForm.pickup_origin || null,
        }),
      })

      const data = await response.json()

      if (response.ok) {
        setSuccessMessage(data.message || 'Booking updated successfully')
        fetchBookings()
        setTimeout(() => setSuccessMessage(''), 5000)
        setShowEditModal(false)
        setBookingToEdit(null)
      } else {
        setError(data.detail || 'Failed to update booking')
      }
    } catch (err) {
      setError('Network error while updating booking')
    } finally {
      setSavingEdit(false)
    }
  }

  // Refund handler (opens Stripe dashboard)
  const handleRefundClick = (booking, e) => {
    e.stopPropagation()
    const paymentIntentId = booking.payment?.stripe_payment_intent_id
    if (paymentIntentId) {
      const stripeUrl = `https://dashboard.stripe.com/payments/${paymentIntentId}`
      window.open(stripeUrl, '_blank')
    } else {
      setError('No payment found for this booking')
    }
  }

  // Resend email handlers
  const handleResendEmailClick = (booking, e) => {
    e.stopPropagation()
    setBookingToResend(booking)
    setShowResendModal(true)
  }

  const handleConfirmResendEmail = async () => {
    if (!bookingToResend) return

    setResendingEmailId(bookingToResend.id)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/${bookingToResend.id}/resend-email`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        setShowResendModal(false)
        setBookingToResend(null)
        setError('')
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to send confirmation email')
      }
    } catch (err) {
      setError('Network error while sending email')
    } finally {
      setResendingEmailId(null)
    }
  }

  // Cancellation email handlers
  const handleSendCancellationEmailClick = (booking, e) => {
    e.stopPropagation()
    setBookingForCancellationEmail(booking)
    setShowCancellationEmailModal(true)
  }

  const handleConfirmSendCancellationEmail = async () => {
    if (!bookingForCancellationEmail) return

    setSendingCancellationEmailId(bookingForCancellationEmail.id)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/${bookingForCancellationEmail.id}/send-cancellation-email`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        setShowCancellationEmailModal(false)
        setSuccessMessage(`Cancellation email sent to ${bookingForCancellationEmail.customer?.email}`)
        setBookingForCancellationEmail(null)
        await fetchBookings()
        setTimeout(() => setSuccessMessage(''), 5000)
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to send cancellation email')
      }
    } catch (err) {
      setError('Network error while sending cancellation email')
    } finally {
      setSendingCancellationEmailId(null)
    }
  }

  // Refund email handlers
  const handleSendRefundEmailClick = (booking, e) => {
    e.stopPropagation()
    setBookingForRefundEmail(booking)
    setShowRefundEmailModal(true)
  }

  const handleConfirmSendRefundEmail = async () => {
    if (!bookingForRefundEmail) return

    setSendingRefundEmailId(bookingForRefundEmail.id)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/${bookingForRefundEmail.id}/send-refund-email`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        setShowRefundEmailModal(false)
        setSuccessMessage(`Refund email sent to ${bookingForRefundEmail.customer?.email}`)
        setBookingForRefundEmail(null)
        await fetchBookings()
        setTimeout(() => setSuccessMessage(''), 5000)
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to send refund email')
      }
    } catch (err) {
      setError('Network error while sending refund email')
    } finally {
      setSendingRefundEmailId(null)
    }
  }

  // Founder email handlers
  const handleSendFounderEmailClick = (booking, e) => {
    e.stopPropagation()
    setBookingForFounderEmail(booking)
    setShowFounderEmailModal(true)
  }

  const handleConfirmSendFounderEmail = async () => {
    if (!bookingForFounderEmail) return

    setSendingFounderEmailId(bookingForFounderEmail.id)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/${bookingForFounderEmail.id}/send-founder-email`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        setShowFounderEmailModal(false)
        setSuccessMessage(`Founder email sent to ${bookingForFounderEmail.customer?.email}`)
        setBookingForFounderEmail(null)
        await fetchBookings()
        setTimeout(() => setSuccessMessage(''), 5000)
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to send founder email')
      }
    } catch (err) {
      setError('Network error while sending founder email')
    } finally {
      setSendingFounderEmailId(null)
    }
  }

  // Return Vehicle Inspection handlers
  const handleViewReturnInspectionClick = async (booking, e) => {
    e.stopPropagation()
    setBookingForInspection(booking)
    setShowReturnInspectionModal(true)
    setLoadingReturnInspection(true)
    setReturnInspectionData(null)

    try {
      const response = await fetch(`${API_URL}/api/employee/inspections/${booking.id}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })

      if (response.ok) {
        const data = await response.json()
        const inspections = Array.isArray(data) ? data : (data.inspections || [])
        const returnInspection = inspections.find(i => i.inspection_type === 'pickup')
        setReturnInspectionData(returnInspection || null)
      } else {
        setReturnInspectionData(null)
      }
    } catch (err) {
      console.error('Error fetching return inspection:', err)
      setReturnInspectionData(null)
    } finally {
      setLoadingReturnInspection(false)
    }
  }

  const closeReturnInspectionModal = () => {
    setShowReturnInspectionModal(false)
    setBookingForInspection(null)
    setReturnInspectionData(null)
  }

  // Drop-off Vehicle Inspection handlers
  const handleViewDropoffInspectionClick = async (booking, e) => {
    e.stopPropagation()
    setBookingForDropoffInspection(booking)
    setShowDropoffInspectionModal(true)
    setLoadingDropoffInspection(true)
    setDropoffInspectionData(null)

    try {
      const response = await fetch(`${API_URL}/api/employee/inspections/${booking.id}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })

      if (response.ok) {
        const data = await response.json()
        const inspections = Array.isArray(data) ? data : (data.inspections || [])
        const dropoffInspection = inspections.find(i => i.inspection_type === 'dropoff')
        setDropoffInspectionData(dropoffInspection || null)
      } else {
        setDropoffInspectionData(null)
      }
    } catch (err) {
      console.error('Error fetching drop-off inspection:', err)
      setDropoffInspectionData(null)
    } finally {
      setLoadingDropoffInspection(false)
    }
  }

  const closeDropoffInspectionModal = () => {
    setShowDropoffInspectionModal(false)
    setBookingForDropoffInspection(null)
    setDropoffInspectionData(null)
  }

  // Render a single booking card
  const renderBookingCard = (booking) => (
    <div
      key={booking.id || booking.reference}
      data-booking-id={booking.id}
      className={`booking-card ${expandedBookingId === booking.id ? 'expanded' : ''} booking-status-${booking.status?.toLowerCase() || 'pending'}`}
    >
      {/* Collapsed Header Row */}
      <div
        className="booking-card-header booking-header-stacked"
        onClick={() => toggleBookingExpanded(booking.id)}
      >
        <div className="booking-header-info">
          <div className="booking-header-top">
            <span className="booking-ref-large">{booking.reference}</span>
            {booking.booking_source === 'manual' && (
              <span className="booking-source-badge manual">Manual</span>
            )}
          </div>
          <span className="booking-customer-name">
            {booking.customer?.first_name} {booking.customer?.last_name}
          </span>
        </div>
      </div>

      {/* Expanded Content */}
      {expandedBookingId === booking.id && (
        <div className="booking-card-body">
          {/* Contact Details Section */}
          <div className="booking-section">
            <h4>Contact Details</h4>
            <div className="booking-section-content">
              <div className="booking-detail">
                <span className="detail-label">Name</span>
                <span className="detail-value">
                  {booking.customer?.first_name} {booking.customer?.last_name}
                </span>
              </div>
              <div className="booking-detail">
                <span className="detail-label">Email</span>
                <span className="detail-value">{booking.customer?.email}</span>
              </div>
              {booking.customer?.phone && (
                <div className="booking-detail">
                  <span className="detail-label">Phone</span>
                  <span className="detail-value">{booking.customer?.phone}</span>
                </div>
              )}
              {/* Billing Address */}
              {booking.customer?.billing_address1 && (
                <div className="booking-detail billing-address-detail">
                  <span className="detail-label">Billing Address</span>
                  <span className="detail-value billing-address">
                    {booking.customer.billing_address1}
                    {booking.customer.billing_address2 && <><br />{booking.customer.billing_address2}</>}
                    <br />
                    {booking.customer.billing_city}
                    {booking.customer.billing_county && `, ${booking.customer.billing_county}`}
                    <br />
                    {booking.customer.billing_postcode}
                    {booking.customer.billing_country && booking.customer.billing_country !== 'United Kingdom' && (
                      <><br />{booking.customer.billing_country}</>
                    )}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Booking Information Section */}
          <div className="booking-section">
            <h4>Booking Information</h4>
            <div className="booking-section-content">
              <div className="booking-detail-row">
                <div className="booking-detail">
                  <span className="detail-label">Booking Reference</span>
                  <span className="detail-value booking-ref">{booking.reference}</span>
                </div>
                <div className="booking-detail">
                  <span className="detail-label">Source</span>
                  <span className="detail-value">
                    <span className={`source-badge ${booking.booking_source || 'online'}`}>
                      {booking.booking_source === 'manual' ? 'Manual Booking' :
                       booking.booking_source === 'admin' ? 'Admin' :
                       booking.booking_source === 'phone' ? 'Phone' :
                       'Online'}
                    </span>
                  </span>
                </div>
                <div className="booking-detail">
                  <span className="detail-label">Duration</span>
                  <span className="detail-value">
                    {(() => {
                      if (booking.dropoff_date && booking.pickup_date) {
                        const days = Math.round((new Date(booking.pickup_date) - new Date(booking.dropoff_date)) / (1000 * 60 * 60 * 24));
                        return `${days} Day${days !== 1 ? 's' : ''}`;
                      }
                      return booking.package === 'quick' ? '1-7 Days' :
                             booking.package === 'longer' ? '8-14 Days' :
                             booking.package || 'N/A';
                    })()}
                  </span>
                </div>
                <div className="booking-detail">
                  <span className="detail-label">Vehicle</span>
                  <span className="detail-value">
                    <span className="vehicle-reg">{booking.vehicle?.registration}</span>
                    {' '}
                    {booking.vehicle?.colour} {booking.vehicle?.make} {booking.vehicle?.model}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Drop-off / Departure Section */}
          <div className="booking-section">
            <h4>Drop-off / Departure</h4>
            <div className="booking-section-content">
              <div className="booking-detail-row">
                <div className="booking-detail">
                  <span className="detail-label">Drop-off Date</span>
                  <span className="detail-value">{formatDate(booking.dropoff_date)}</span>
                </div>
                <div className="booking-detail">
                  <span className="detail-label">Drop-off Time</span>
                  <span className="detail-value">{formatTime(booking.dropoff_time)}</span>
                </div>
                <div className="booking-detail">
                  <span className="detail-label">Flight Departs</span>
                  <span className="detail-value">{booking.flight_departure_time || '-'}</span>
                </div>
                <div className="booking-detail">
                  <span className="detail-label">Flight</span>
                  <span className="detail-value">
                    {booking.dropoff_airline_name && (
                      <span className="airline-name">{booking.dropoff_airline_name}</span>
                    )}
                    {booking.dropoff_flight_number && booking.dropoff_flight_number !== 'Unknown' && (
                      <span className="flight-number">{booking.dropoff_flight_number}</span>
                    )}
                    {!booking.dropoff_airline_name && (!booking.dropoff_flight_number || booking.dropoff_flight_number === 'Unknown') && '-'}
                  </span>
                </div>
                <div className="booking-detail">
                  <span className="detail-label">Destination</span>
                  <span className="detail-value">{booking.dropoff_destination || '-'}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Pick-up / Return Section */}
          <div className="booking-section">
            <h4>Pick-up / Return</h4>
            <div className="booking-section-content">
              <div className="booking-detail-row">
                <div className="booking-detail">
                  <span className="detail-label">Pick-up Date</span>
                  <span className="detail-value">{formatDate(booking.pickup_date)}</span>
                </div>
                <div className="booking-detail">
                  <span className="detail-label">Pick-up Time</span>
                  <span className="detail-value">
                    {booking.pickup_time
                      ? `From ${booking.pickup_time} onwards`
                      : '-'}
                  </span>
                </div>
                <div className="booking-detail">
                  <span className="detail-label">Flight Arrives</span>
                  <span className="detail-value">{booking.flight_arrival_time || '-'}</span>
                </div>
                <div className="booking-detail">
                  <span className="detail-label">Flight</span>
                  <span className="detail-value">
                    {booking.pickup_airline_name && (
                      <span className="airline-name">{booking.pickup_airline_name}</span>
                    )}
                    {booking.pickup_flight_number && booking.pickup_flight_number !== 'Unknown' && (
                      <span className="flight-number">{booking.pickup_flight_number}</span>
                    )}
                    {!booking.pickup_airline_name && (!booking.pickup_flight_number || booking.pickup_flight_number === 'Unknown') && '-'}
                  </span>
                </div>
                <div className="booking-detail">
                  <span className="detail-label">Origin</span>
                  <span className="detail-value">{booking.pickup_origin || '-'}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Status & Payment Section */}
          <div className="booking-section">
            <h4>Status & Payment</h4>
            <div className="booking-section-content">
              <div className="booking-detail-row">
                <div className="booking-detail">
                  <span className="detail-label">Booking Status</span>
                  <span className={`status-badge status-${booking.status?.toLowerCase()}`}>
                    {booking.status}
                  </span>
                </div>
                <div className="booking-detail">
                  <span className="detail-label">Payment Status</span>
                  <span className={`status-badge payment-${booking.payment?.status?.toLowerCase()}`}>
                    {booking.payment?.status || 'N/A'}
                  </span>
                </div>
                {booking.payment?.amount_pence && (
                  <div className="booking-detail">
                    <span className="detail-label">Amount</span>
                    <span className="detail-value">
                      £{(booking.payment.amount_pence / 100).toFixed(2)}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Actions Section */}
          <div className="booking-section booking-actions-section">
            <h4>Actions</h4>
            <div className="booking-actions">
              {booking.status?.toLowerCase() !== 'completed' && (
                <button
                  className="action-btn edit-btn"
                  onClick={(e) => handleEditBookingClick(booking, e)}
                >
                  Edit Booking Details
                </button>
              )}
              {booking.status?.toLowerCase() !== 'completed' && (
                <button
                  className="action-btn email-btn"
                  onClick={(e) => handleResendEmailClick(booking, e)}
                  disabled={resendingEmailId === booking.id}
                >
                  {resendingEmailId === booking.id ? 'Sending...' : 'Resend Confirmation Email'}
                </button>
              )}
              {booking.status?.toLowerCase() === 'cancelled' && (
                <button
                  className="action-btn email-btn"
                  onClick={(e) => handleSendCancellationEmailClick(booking, e)}
                  disabled={sendingCancellationEmailId === booking.id}
                >
                  {sendingCancellationEmailId === booking.id ? 'Sending...' : 'Send Cancellation Email'}
                </button>
              )}
              {booking.status?.toLowerCase() === 'cancelled' && (
                <button
                  className="action-btn email-btn"
                  onClick={(e) => handleSendRefundEmailClick(booking, e)}
                  disabled={sendingRefundEmailId === booking.id}
                >
                  {sendingRefundEmailId === booking.id ? 'Sending...' : 'Send Refund Email'}
                </button>
              )}
              {booking.payment?.stripe_payment_intent_id &&
               booking.payment?.status?.toLowerCase() === 'succeeded' &&
               booking.status?.toLowerCase() !== 'refunded' &&
               booking.status?.toLowerCase() !== 'completed' && (
                <button
                  className="action-btn refund-btn"
                  onClick={(e) => handleRefundClick(booking, e)}
                >
                  Process Refund
                </button>
              )}
              {booking.status?.toLowerCase() !== 'cancelled' &&
               booking.status?.toLowerCase() !== 'refunded' &&
               booking.status?.toLowerCase() !== 'completed' && (
                <button
                  className="action-btn cancel-btn"
                  onClick={(e) => handleCancelClick(booking, e)}
                  disabled={cancellingId === booking.id}
                >
                  {cancellingId === booking.id ? 'Cancelling...' : 'Cancel Booking'}
                </button>
              )}
              {booking.booking_source === 'manual' &&
               booking.status?.toLowerCase() === 'pending' && (
                <button
                  className="action-btn paid-btn"
                  onClick={(e) => handleMarkPaid(booking, e)}
                  disabled={markingPaidId === booking.id}
                >
                  {markingPaidId === booking.id ? 'Updating...' : 'Mark as Paid'}
                </button>
              )}
              {booking.status?.toLowerCase() === 'pending' && (
                <button
                  className="action-btn email-btn"
                  onClick={(e) => handleSendFounderEmailClick(booking, e)}
                  disabled={sendingFounderEmailId === booking.id || booking.customer?.founder_followup_sent}
                  title={booking.customer?.founder_followup_sent ? 'Founder email already sent' : 'Send personal follow-up email from founder'}
                >
                  {sendingFounderEmailId === booking.id ? 'Sending...' :
                   booking.customer?.founder_followup_sent ? 'Founder Email Sent ✓' : 'Send Founder Email'}
                </button>
              )}
              {booking.status?.toLowerCase() === 'completed' && booking.id && (
                <button
                  className="action-btn view-inspection-btn"
                  onClick={(e) => handleViewDropoffInspectionClick(booking, e)}
                >
                  View Drop-off Inspection
                </button>
              )}
              {booking.status?.toLowerCase() === 'completed' && booking.id && (
                <button
                  className="action-btn view-inspection-btn"
                  onClick={(e) => handleViewReturnInspectionClick(booking, e)}
                >
                  View Return Inspection
                </button>
              )}
              {['pending', 'cancelled'].includes(booking.status?.toLowerCase()) && (
                <button
                  className="action-btn delete-btn"
                  onClick={(e) => handleDeleteClick(booking, e)}
                  disabled={deletingId === booking.id}
                >
                  {deletingId === booking.id ? 'Deleting...' : 'Delete'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h2>Bookings</h2>
        <button onClick={fetchBookings} className="btn-secondary" disabled={loadingData}>
          {loadingData ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {error && <div className="admin-error">{error}</div>}
      {successMessage && <div className="admin-success">{successMessage}</div>}

      {/* Recent 10 Bookings */}
      {recentBookings.length > 0 && (
        <div className="recent-bookings-container">
          <h3 className="recent-bookings-title">Recent Bookings</h3>
          <div className="recent-bookings-grid">
            {recentBookings.map((booking) => (
              <div
                key={booking.id || booking.reference}
                className={`recent-booking-card booking-status-${booking.status?.toLowerCase() || 'pending'}`}
                onClick={() => {
                  setExpandedBookingId(booking.id)
                  setTimeout(() => {
                    const element = document.querySelector(`.booking-card[data-booking-id="${booking.id}"]`)
                    if (element) {
                      element.scrollIntoView({ behavior: 'smooth', block: 'center' })
                    }
                  }, 100)
                }}
              >
                <div className="recent-booking-ref">{booking.reference}</div>
                <div className="recent-booking-name">
                  {booking.customer?.first_name} {booking.customer?.last_name}
                </div>
                <div className="recent-booking-date">
                  {new Date(booking.dropoff_date + 'T12:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'Europe/London' })}
                </div>
                <div className={`recent-booking-status status-${booking.status?.toLowerCase() || 'pending'}`}>
                  {booking.status || 'Pending'}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Search and Filter Controls */}
      <div className="admin-filters">
        <div className="admin-search">
          <input
            type="text"
            placeholder="Search by reference, name, email, or registration..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="admin-search-input"
          />
          {searchTerm && (
            <button
              className="admin-search-clear"
              onClick={() => setSearchTerm('')}
            >
              &times;
            </button>
          )}
        </div>
        <div className="admin-filter-group">
          <label>Status:</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="admin-filter-select"
          >
            <option value="all">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="confirmed">Confirmed</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
            <option value="refunded">Refunded</option>
          </select>
        </div>
        <label className="admin-checkbox-label">
          <input
            type="checkbox"
            checked={hideTestEmails}
            onChange={(e) => setHideTestEmails(e.target.checked)}
          />
          Hide test emails
        </label>
        <button
          className="admin-sort-btn"
          onClick={() => setSortAsc(!sortAsc)}
          title={sortAsc ? 'Sorted by drop-off date (earliest first)' : 'Sorted by drop-off date (latest first)'}
        >
          Drop-off {sortAsc ? '↑' : '↓'}
        </button>
        <div className="admin-filter-count">
          Showing {filteredBookings.length} of {bookings.length} bookings
        </div>
      </div>

      {loadingData ? (
        <div className="admin-loading-inline">
          <div className="spinner-small"></div>
          <span>Loading bookings...</span>
        </div>
      ) : filteredBookings.length === 0 ? (
        <p className="admin-empty">
          {bookings.length === 0 ? 'No bookings found' : 'No bookings match your search'}
        </p>
      ) : (
        <div className="bookings-by-status">
          {/* Render each status section in order: Confirmed, Completed, Pending, Cancelled */}
          {[
            { key: 'confirmed', label: 'Confirmed', color: '#28a745' },
            { key: 'completed', label: 'Completed', color: '#6c757d' },
            { key: 'pending', label: 'Pending', color: '#ffc107' },
            { key: 'cancelled', label: 'Cancelled', color: '#dc3545' }
          ].map(({ key: statusKey, label, color }) => {
            const statusBookings = bookingsByStatus[statusKey]
            if (statusBookings.length === 0) return null

            return (
              <div key={statusKey} className={`status-section status-section-${statusKey}`}>
                <div
                  className="status-section-header"
                  onClick={() => toggleStatusSection(statusKey)}
                  style={{ borderLeftColor: color }}
                >
                  <div className="status-section-title">
                    <span className="status-section-indicator" style={{ backgroundColor: color }}></span>
                    <h3>{label}</h3>
                    <span className="status-section-count">{statusBookings.length}</span>
                  </div>
                  <span className={`status-section-toggle ${collapsedStatusSections[statusKey] ? 'collapsed' : ''}`}>
                    {collapsedStatusSections[statusKey] ? '+' : '-'}
                  </span>
                </div>

                {!collapsedStatusSections[statusKey] && (
                  <div className="booking-accordion">
                    {/* For confirmed and completed, group by month */}
                    {(statusKey === 'confirmed' || statusKey === 'completed') ? (
                      (() => {
                        const monthlyGroups = groupBookingsByMonth(statusBookings)
                        const sortedMonths = Object.keys(monthlyGroups).sort()

                        return sortedMonths.map(monthKey => {
                          const { label, bookings: monthBookings } = monthlyGroups[monthKey]
                          const expandKey = `${statusKey}-${monthKey}`
                          const isExpanded = expandedBookingMonths[expandKey]

                          return (
                            <div key={monthKey} className="leads-month-container">
                              <div
                                className="leads-month-header"
                                onClick={() => toggleBookingMonth(statusKey, monthKey)}
                              >
                                <span className="expand-icon">{isExpanded ? '▼' : '▶'}</span>
                                <span className="month-name">{label}</span>
                                <span className="month-total">{monthBookings.length} booking{monthBookings.length !== 1 ? 's' : ''}</span>
                              </div>
                              {isExpanded && (
                                <div className="leads-month-content">
                                  {monthBookings.map(booking => renderBookingCard(booking))}
                                </div>
                              )}
                            </div>
                          )
                        })
                      })()
                    ) : (
                      /* For pending and cancelled, show flat list */
                      statusBookings.map(booking => renderBookingCard(booking))
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Cancel Confirmation Modal */}
      {showCancelModal && bookingToCancel && (
        <div className="modal-overlay" onClick={() => setShowCancelModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Cancel Booking</h3>
            <p>Are you sure you want to cancel this booking?</p>
            <div className="modal-booking-info">
              <p><strong>Reference:</strong> {bookingToCancel.reference}</p>
              <p><strong>Customer:</strong> {bookingToCancel.customer?.first_name} {bookingToCancel.customer?.last_name}</p>
              <p><strong>Drop-off:</strong> {formatDate(bookingToCancel.dropoff_date)}</p>
            </div>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowCancelModal(false)}
              >
                Keep Booking
              </button>
              <button
                className="modal-btn modal-btn-danger"
                onClick={handleConfirmCancel}
                disabled={cancellingId}
              >
                {cancellingId ? 'Cancelling...' : 'Yes, Cancel Booking'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Pending Booking Modal */}
      {showDeleteModal && bookingToDelete && (
        <div className="modal-overlay" onClick={() => setShowDeleteModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Delete Pending Booking</h3>
            <p>Are you sure you want to permanently delete this booking? This action cannot be undone.</p>
            <div className="modal-booking-info">
              <p><strong>Reference:</strong> {bookingToDelete.reference}</p>
              <p><strong>Customer:</strong> {bookingToDelete.customer?.first_name} {bookingToDelete.customer?.last_name}</p>
              <p><strong>Drop-off:</strong> {formatDate(bookingToDelete.dropoff_date)}</p>
            </div>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowDeleteModal(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-danger"
                onClick={confirmDeleteBooking}
                disabled={deletingId}
              >
                {deletingId ? 'Deleting...' : 'Yes, Delete Booking'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Booking Details Modal */}
      {showEditModal && bookingToEdit && (
        <div className="modal-overlay" onClick={() => setShowEditModal(false)}>
          <div className="modal-content modal-content-wide" onClick={(e) => e.stopPropagation()}>
            <h3>Edit Booking Details</h3>
            <div className="modal-booking-info">
              <p><strong>Reference:</strong> {bookingToEdit.reference}</p>
              <p><strong>Customer:</strong> {bookingToEdit.customer?.first_name} {bookingToEdit.customer?.last_name}</p>
            </div>
            <div className="modal-form">
              <h4 className="modal-section-title">Drop-off / Departure</h4>
              <div className="modal-form-row">
                <div className="modal-form-group">
                  <label>Drop-off Time (24hr)</label>
                  <input
                    type="text"
                    placeholder="HH:MM"
                    pattern="([01]?[0-9]|2[0-3]):[0-5][0-9]"
                    value={editForm.dropoff_time}
                    onChange={(e) => setEditForm({ ...editForm, dropoff_time: e.target.value })}
                  />
                </div>
                <div className="modal-form-group">
                  <label>Flight Departure Time (24hr)</label>
                  <input
                    type="text"
                    placeholder="HH:MM"
                    pattern="([01]?[0-9]|2[0-3]):[0-5][0-9]"
                    value={editForm.flight_departure_time}
                    onChange={(e) => setEditForm({ ...editForm, flight_departure_time: e.target.value })}
                  />
                </div>
                <div className="modal-form-group">
                  <label>Airline</label>
                  <input
                    type="text"
                    placeholder="e.g. Jet2"
                    value={editForm.dropoff_airline_name}
                    onChange={(e) => setEditForm({ ...editForm, dropoff_airline_name: e.target.value })}
                  />
                </div>
                <div className="modal-form-group">
                  <label>Flight Number</label>
                  <input
                    type="text"
                    placeholder="e.g. BY1234"
                    value={editForm.dropoff_flight_number}
                    onChange={(e) => setEditForm({ ...editForm, dropoff_flight_number: e.target.value })}
                  />
                </div>
                <div className="modal-form-group">
                  <label>Destination</label>
                  <input
                    type="text"
                    placeholder="e.g. Malaga Airport"
                    value={editForm.dropoff_destination}
                    onChange={(e) => setEditForm({ ...editForm, dropoff_destination: e.target.value })}
                  />
                </div>
              </div>

              <h4 className="modal-section-title">Pick-up / Return</h4>
              <div className="modal-form-row">
                <div className="modal-form-group">
                  <label>Pickup Date (DD/MM/YYYY)</label>
                  <input
                    type="text"
                    placeholder="DD/MM/YYYY"
                    pattern="\d{2}/\d{2}/\d{4}"
                    value={editForm.pickup_date}
                    onChange={(e) => setEditForm({ ...editForm, pickup_date: e.target.value })}
                  />
                </div>
                <div className="modal-form-group">
                  <label>Arrival Time (24hr)</label>
                  <input
                    type="text"
                    placeholder="HH:MM"
                    pattern="([01]?[0-9]|2[0-3]):[0-5][0-9]"
                    value={editForm.flight_arrival_time}
                    onChange={(e) => setEditForm({ ...editForm, flight_arrival_time: e.target.value })}
                  />
                  <p className="modal-form-hint">Pickup time = arrival + 30 min</p>
                </div>
                <div className="modal-form-group">
                  <label>Airline</label>
                  <input
                    type="text"
                    placeholder="e.g. Jet2"
                    value={editForm.pickup_airline_name}
                    onChange={(e) => setEditForm({ ...editForm, pickup_airline_name: e.target.value })}
                  />
                </div>
                <div className="modal-form-group">
                  <label>Flight Number</label>
                  <input
                    type="text"
                    placeholder="e.g. BY1235"
                    value={editForm.pickup_flight_number}
                    onChange={(e) => setEditForm({ ...editForm, pickup_flight_number: e.target.value })}
                  />
                </div>
                <div className="modal-form-group">
                  <label>Origin</label>
                  <input
                    type="text"
                    placeholder="e.g. Malaga Airport"
                    value={editForm.pickup_origin}
                    onChange={(e) => setEditForm({ ...editForm, pickup_origin: e.target.value })}
                  />
                </div>
              </div>
            </div>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowEditModal(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={confirmEditBooking}
                disabled={savingEdit}
              >
                {savingEdit ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Resend Email Confirmation Modal */}
      {showResendModal && bookingToResend && (
        <div className="modal-overlay" onClick={() => setShowResendModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Resend Confirmation Email</h3>
            <p>Are you sure you want to resend the booking confirmation email?</p>
            <div className="modal-booking-info">
              <p><strong>Reference:</strong> {bookingToResend.reference}</p>
              <p><strong>Customer:</strong> {bookingToResend.customer?.first_name} {bookingToResend.customer?.last_name}</p>
              <p><strong>Email:</strong> {bookingToResend.customer?.email}</p>
            </div>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowResendModal(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={handleConfirmResendEmail}
                disabled={resendingEmailId}
              >
                {resendingEmailId ? 'Sending...' : 'Yes, Send Email'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Send Cancellation Email Modal */}
      {showCancellationEmailModal && bookingForCancellationEmail && (
        <div className="modal-overlay" onClick={() => setShowCancellationEmailModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Send Cancellation Email</h3>
            <p>Are you sure you want to send the cancellation email to the customer?</p>
            <div className="modal-booking-info">
              <p><strong>Reference:</strong> {bookingForCancellationEmail.reference}</p>
              <p><strong>Customer:</strong> {bookingForCancellationEmail.customer?.first_name} {bookingForCancellationEmail.customer?.last_name}</p>
              <p><strong>Email:</strong> {bookingForCancellationEmail.customer?.email}</p>
            </div>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowCancellationEmailModal(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={handleConfirmSendCancellationEmail}
                disabled={sendingCancellationEmailId}
              >
                {sendingCancellationEmailId ? 'Sending...' : 'Yes, Send Email'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Send Refund Email Modal */}
      {showRefundEmailModal && bookingForRefundEmail && (
        <div className="modal-overlay" onClick={() => setShowRefundEmailModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Send Refund Email</h3>
            <p>Are you sure you want to send the refund confirmation email to the customer?</p>
            <div className="modal-booking-info">
              <p><strong>Reference:</strong> {bookingForRefundEmail.reference}</p>
              <p><strong>Customer:</strong> {bookingForRefundEmail.customer?.first_name} {bookingForRefundEmail.customer?.last_name}</p>
              <p><strong>Email:</strong> {bookingForRefundEmail.customer?.email}</p>
              {bookingForRefundEmail.payment?.refund_amount_pence && (
                <p><strong>Refund Amount:</strong> £{(bookingForRefundEmail.payment.refund_amount_pence / 100).toFixed(2)}</p>
              )}
            </div>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowRefundEmailModal(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={handleConfirmSendRefundEmail}
                disabled={sendingRefundEmailId}
              >
                {sendingRefundEmailId ? 'Sending...' : 'Yes, Send Email'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Send Founder Email Confirmation Modal */}
      {showFounderEmailModal && bookingForFounderEmail && (
        <div className="modal-overlay" onClick={() => setShowFounderEmailModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Send Founder Email</h3>
            <p>This will send a personal follow-up email from Kristian to the customer about their incomplete booking.</p>
            <div className="modal-booking-info">
              <p><strong>Reference:</strong> {bookingForFounderEmail.reference}</p>
              <p><strong>Customer:</strong> {bookingForFounderEmail.customer?.first_name} {bookingForFounderEmail.customer?.last_name}</p>
              <p><strong>Email:</strong> {bookingForFounderEmail.customer?.email}</p>
            </div>
            <p className="modal-warning">
              The email will be CC'd to Kristian so he can see and respond to any replies.
            </p>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowFounderEmailModal(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={handleConfirmSendFounderEmail}
                disabled={sendingFounderEmailId}
              >
                {sendingFounderEmailId ? 'Sending...' : 'Yes, Send Email'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Return Vehicle Inspection Modal */}
      {showReturnInspectionModal && bookingForInspection && (
        <div className="modal-overlay" onClick={closeReturnInspectionModal}>
          <div className="modal-content modal-content-wide" onClick={(e) => e.stopPropagation()}>
            <h3>Return Vehicle Inspection</h3>
            <div className="modal-booking-info">
              <p><strong>Booking:</strong> {bookingForInspection.reference}</p>
              <p><strong>Customer:</strong> {bookingForInspection.customer?.first_name} {bookingForInspection.customer?.last_name}</p>
              <p><strong>Vehicle:</strong> {bookingForInspection.vehicle?.registration} - {bookingForInspection.vehicle?.make} {bookingForInspection.vehicle?.model}</p>
            </div>

            {loadingReturnInspection ? (
              <div className="inspection-loading">
                <div className="spinner"></div>
                <p>Loading inspection data...</p>
              </div>
            ) : returnInspectionData ? (
              <div className="inspection-details">
                <div className="inspection-section">
                  <h4>Inspection Details</h4>
                  <div className="inspection-grid">
                    <div className="inspection-item">
                      <span className="inspection-label">Customer Name</span>
                      <span className="inspection-value">{returnInspectionData.customer_name || 'Not recorded'}</span>
                    </div>
                    <div className="inspection-item">
                      <span className="inspection-label">Signed Date</span>
                      <span className="inspection-value">{returnInspectionData.signed_date ? formatDateTimeUK(returnInspectionData.signed_date) : '-'}</span>
                    </div>
                    <div className="inspection-item">
                      <span className="inspection-label">Mileage</span>
                      <span className="inspection-value">{returnInspectionData.mileage ? `${returnInspectionData.mileage.toLocaleString()} miles` : 'Not recorded'}</span>
                    </div>
                    <div className="inspection-item">
                      <span className="inspection-label">Recorded</span>
                      <span className="inspection-value">{returnInspectionData.created_at ? formatDateTimeUK(returnInspectionData.created_at) : '-'}</span>
                    </div>
                  </div>
                </div>

                {returnInspectionData.declined ? (
                  <div className="inspection-section inspection-declined">
                    <h4>Inspection Declined</h4>
                    <p>The customer declined this return inspection.</p>
                    {returnInspectionData.declined_reason && (
                      <p><strong>Reason:</strong> {returnInspectionData.declined_reason}</p>
                    )}
                  </div>
                ) : (
                  <>
                    {returnInspectionData.notes && (
                      <div className="inspection-section">
                        <h4>Notes</h4>
                        <p className="inspection-notes">{returnInspectionData.notes}</p>
                      </div>
                    )}

                    {returnInspectionData.photos && Object.keys(returnInspectionData.photos).length > 0 && (
                      <div className="inspection-section">
                        <h4>Photos</h4>
                        <div className="inspection-photos">
                          {PHOTO_SLOTS.map(slot => (
                            returnInspectionData.photos[slot.key] && (
                              <div key={slot.key} className="inspection-photo">
                                <span className="photo-label">{slot.label}</span>
                                <img src={returnInspectionData.photos[slot.key]} alt={slot.label} />
                              </div>
                            )
                          ))}
                        </div>
                      </div>
                    )}

                    {returnInspectionData.signature && (
                      <div className="inspection-section">
                        <h4>Customer Signature</h4>
                        <div className="inspection-signature">
                          <img src={returnInspectionData.signature} alt="Customer Signature" />
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            ) : (
              <div className="inspection-empty">
                <p>No return vehicle inspection found for this booking.</p>
                <p className="inspection-empty-hint">The return inspection may not have been completed yet.</p>
              </div>
            )}

            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={closeReturnInspectionModal}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Drop-off Vehicle Inspection Modal */}
      {showDropoffInspectionModal && bookingForDropoffInspection && (
        <div className="modal-overlay" onClick={closeDropoffInspectionModal}>
          <div className="modal-content modal-content-wide" onClick={(e) => e.stopPropagation()}>
            <h3>Drop-off Vehicle Inspection</h3>
            <div className="modal-booking-info">
              <p><strong>Booking:</strong> {bookingForDropoffInspection.reference}</p>
              <p><strong>Customer:</strong> {bookingForDropoffInspection.customer?.first_name} {bookingForDropoffInspection.customer?.last_name}</p>
              <p><strong>Vehicle:</strong> {bookingForDropoffInspection.vehicle?.registration} - {bookingForDropoffInspection.vehicle?.make} {bookingForDropoffInspection.vehicle?.model}</p>
            </div>

            {loadingDropoffInspection ? (
              <div className="inspection-loading">
                <div className="spinner"></div>
                <p>Loading inspection data...</p>
              </div>
            ) : dropoffInspectionData ? (
              <div className="inspection-details">
                <div className="inspection-section">
                  <h4>Inspection Details</h4>
                  <div className="inspection-grid">
                    <div className="inspection-item">
                      <span className="inspection-label">Customer Name</span>
                      <span className="inspection-value">{dropoffInspectionData.customer_name || 'Not recorded'}</span>
                    </div>
                    <div className="inspection-item">
                      <span className="inspection-label">Signed Date</span>
                      <span className="inspection-value">{dropoffInspectionData.signed_date ? formatDateTimeUK(dropoffInspectionData.signed_date) : '-'}</span>
                    </div>
                    <div className="inspection-item">
                      <span className="inspection-label">Mileage</span>
                      <span className="inspection-value">{dropoffInspectionData.mileage ? `${dropoffInspectionData.mileage.toLocaleString()} miles` : 'Not recorded'}</span>
                    </div>
                    <div className="inspection-item">
                      <span className="inspection-label">Recorded</span>
                      <span className="inspection-value">{dropoffInspectionData.created_at ? formatDateTimeUK(dropoffInspectionData.created_at) : '-'}</span>
                    </div>
                  </div>
                </div>

                {dropoffInspectionData.vehicle_inspection_read && (
                  <div className="inspection-section">
                    <h4>Terms Acknowledgement</h4>
                    <p className="inspection-acknowledged">Customer confirmed they read the vehicle inspection terms.</p>
                  </div>
                )}

                {dropoffInspectionData.notes && (
                  <div className="inspection-section">
                    <h4>Notes</h4>
                    <p className="inspection-notes">{dropoffInspectionData.notes}</p>
                  </div>
                )}

                {dropoffInspectionData.photos && Object.keys(dropoffInspectionData.photos).length > 0 && (
                  <div className="inspection-section">
                    <h4>Photos</h4>
                    <div className="inspection-photos">
                      {PHOTO_SLOTS.map(slot => (
                        dropoffInspectionData.photos[slot.key] && (
                          <div key={slot.key} className="inspection-photo">
                            <span className="photo-label">{slot.label}</span>
                            <img src={dropoffInspectionData.photos[slot.key]} alt={slot.label} />
                          </div>
                        )
                      ))}
                    </div>
                  </div>
                )}

                {dropoffInspectionData.signature && (
                  <div className="inspection-section">
                    <h4>Customer Signature</h4>
                    <div className="inspection-signature">
                      <img src={dropoffInspectionData.signature} alt="Customer Signature" />
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="inspection-empty">
                <p>No drop-off vehicle inspection found for this booking.</p>
                <p className="inspection-empty-hint">The drop-off inspection may not have been completed yet.</p>
              </div>
            )}

            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={closeDropoffInspectionModal}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default BookingsPage
