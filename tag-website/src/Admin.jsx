import { useState, useEffect, useMemo } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from './AuthContext'
import './Admin.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function Admin() {
  const { user, token, loading, isAuthenticated, isAdmin, logout } = useAuth()
  const navigate = useNavigate()

  const [activeTab, setActiveTab] = useState('bookings')
  const [bookings, setBookings] = useState([])
  const [loadingData, setLoadingData] = useState(false)
  const [error, setError] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [expandedBookingId, setExpandedBookingId] = useState(null)
  const [cancellingId, setCancellingId] = useState(null)
  const [showCancelModal, setShowCancelModal] = useState(false)
  const [bookingToCancel, setBookingToCancel] = useState(null)
  const [resendingEmailId, setResendingEmailId] = useState(null)
  const [showResendModal, setShowResendModal] = useState(false)
  const [bookingToResend, setBookingToResend] = useState(null)

  // Redirect if not authenticated or not admin
  useEffect(() => {
    if (!loading) {
      if (!isAuthenticated) {
        navigate('/login?redirect=/admin', { replace: true })
      } else if (!isAdmin) {
        navigate('/employee', { replace: true })
      }
    }
  }, [loading, isAuthenticated, isAdmin, navigate])

  // Fetch bookings when tab is active
  useEffect(() => {
    if (activeTab === 'bookings' && token) {
      fetchBookings()
    }
  }, [activeTab, token])

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

    // Sort by dropoff date ASC (earliest first)
    filtered.sort((a, b) => {
      const dateA = new Date(a.dropoff_date)
      const dateB = new Date(b.dropoff_date)
      return dateA - dateB
    })

    return filtered
  }, [bookings, searchTerm, statusFilter])

  const toggleBookingExpanded = (bookingId) => {
    setExpandedBookingId(expandedBookingId === bookingId ? null : bookingId)
  }

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
        // Refresh bookings list
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

  const handleRefundClick = (booking, e) => {
    e.stopPropagation()
    // Open Stripe dashboard to the payment intent
    const paymentIntentId = booking.payment?.stripe_payment_intent_id
    if (paymentIntentId) {
      // Stripe dashboard URL for payment intent
      const stripeUrl = `https://dashboard.stripe.com/payments/${paymentIntentId}`
      window.open(stripeUrl, '_blank')
    } else {
      setError('No payment found for this booking')
    }
  }

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
        // Show success (could use a toast, but we'll just clear error)
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

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return '-'
    const date = new Date(dateStr)
    return date.toLocaleDateString('en-GB', {
      weekday: 'short',
      day: '2-digit',
      month: 'short',
      year: 'numeric'
    })
  }

  const formatTime = (timeStr) => {
    if (!timeStr) return ''
    // Handle both "HH:MM:SS" and "HH:MM" formats
    return timeStr.substring(0, 5)
  }

  if (loading) {
    return (
      <div className="admin-loading">
        <div className="spinner"></div>
        <p>Loading...</p>
      </div>
    )
  }

  if (!isAuthenticated || !isAdmin) {
    return null
  }

  return (
    <div className="admin-container">
      <header className="admin-header">
        <div className="admin-header-left">
          <Link to="/">
            <img src="/assets/logo.svg" alt="TAG Parking" className="admin-logo" />
          </Link>
          <h1>Admin Dashboard</h1>
        </div>
        <div className="admin-header-right">
          <span className="admin-user">
            {user?.first_name} {user?.last_name}
          </span>
          <button onClick={handleLogout} className="admin-logout">
            Logout
          </button>
        </div>
      </header>

      <nav className="admin-nav">
        <button
          className={`admin-nav-item ${activeTab === 'bookings' ? 'active' : ''}`}
          onClick={() => setActiveTab('bookings')}
        >
          Bookings
        </button>
        <button
          className={`admin-nav-item ${activeTab === 'users' ? 'active' : ''}`}
          onClick={() => setActiveTab('users')}
        >
          Users
        </button>
        <button
          className={`admin-nav-item ${activeTab === 'flights' ? 'active' : ''}`}
          onClick={() => setActiveTab('flights')}
        >
          Flights
        </button>
        <button
          className={`admin-nav-item ${activeTab === 'reports' ? 'active' : ''}`}
          onClick={() => setActiveTab('reports')}
        >
          Reports
        </button>
      </nav>

      <main className="admin-content">
        {error && <div className="admin-error">{error}</div>}

        {activeTab === 'bookings' && (
          <div className="admin-section">
            <div className="admin-section-header">
              <h2>Bookings</h2>
              <button onClick={fetchBookings} className="admin-refresh" disabled={loadingData}>
                {loadingData ? 'Loading...' : 'Refresh'}
              </button>
            </div>

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
              <div className="booking-accordion">
                {filteredBookings.map((booking) => (
                  <div
                    key={booking.id || booking.reference}
                    className={`booking-card ${expandedBookingId === booking.id ? 'expanded' : ''}`}
                  >
                    {/* Collapsed Header Row */}
                    <div
                      className="booking-card-header"
                      onClick={() => toggleBookingExpanded(booking.id)}
                    >
                      <div className="booking-header-main">
                        <span className="booking-ref">{booking.reference}</span>
                        <span className="booking-name">
                          {booking.customer?.first_name} {booking.customer?.last_name}
                        </span>
                        <span className="booking-date">{formatDate(booking.dropoff_date)}</span>
                        <span className={`status-badge status-${booking.status?.toLowerCase()}`}>
                          {booking.status}
                        </span>
                      </div>
                      <div className="booking-expand-icon">
                        {expandedBookingId === booking.id ? '−' : '+'}
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
                                <span className="detail-label">Package</span>
                                <span className="detail-value">
                                  {booking.package === 'quick' ? '1 Week' : '2 Weeks'}
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
                                <span className="detail-label">Flight Number</span>
                                <span className="detail-value flight-number">{booking.dropoff_flight_number || '-'}</span>
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
                                <span className="detail-label">Pick-up Window</span>
                                <span className="detail-value">
                                  {booking.pickup_time_from && booking.pickup_time_to
                                    ? `${formatTime(booking.pickup_time_from)} - ${formatTime(booking.pickup_time_to)}`
                                    : '-'}
                                </span>
                              </div>
                              <div className="booking-detail">
                                <span className="detail-label">Flight Number</span>
                                <span className="detail-value flight-number">{booking.pickup_flight_number || '-'}</span>
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
                            <button
                              className="action-btn email-btn"
                              onClick={(e) => handleResendEmailClick(booking, e)}
                              disabled={resendingEmailId === booking.id}
                            >
                              {resendingEmailId === booking.id ? 'Sending...' : 'Resend Confirmation Email'}
                            </button>
                            {booking.payment?.stripe_payment_intent_id &&
                             booking.payment?.status?.toLowerCase() === 'succeeded' &&
                             booking.status?.toLowerCase() !== 'refunded' && (
                              <button
                                className="action-btn refund-btn"
                                onClick={(e) => handleRefundClick(booking, e)}
                              >
                                Process Refund
                              </button>
                            )}
                            {booking.status?.toLowerCase() !== 'cancelled' &&
                             booking.status?.toLowerCase() !== 'refunded' && (
                              <button
                                className="action-btn cancel-btn"
                                onClick={(e) => handleCancelClick(booking, e)}
                                disabled={cancellingId === booking.id}
                              >
                                {cancellingId === booking.id ? 'Cancelling...' : 'Cancel Booking'}
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'users' && (
          <div className="admin-section">
            <h2>User Management</h2>
            <p className="admin-coming-soon">User management coming soon...</p>
          </div>
        )}

        {activeTab === 'flights' && (
          <div className="admin-section">
            <h2>Flight Schedule</h2>
            <p className="admin-coming-soon">Flight management coming soon...</p>
          </div>
        )}

        {activeTab === 'reports' && (
          <div className="admin-section">
            <h2>Reports</h2>
            <p className="admin-coming-soon">Reports coming soon...</p>
          </div>
        )}
      </main>

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
    </div>
  )
}

export default Admin
