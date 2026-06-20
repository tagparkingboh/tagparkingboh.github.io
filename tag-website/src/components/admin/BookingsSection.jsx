import { formatDestination } from '../../utils/formatDestination'
import { resolveArrivalDate } from '../../utils/arrivalDate'
import { taxStatusClass, motStatusClass, shouldShowAlert, formatIsoDateUk } from '../../dvlaCompliance'

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
        bookings: [],
      }
    }
    groups[monthKey].bookings.push(booking)
  })

  return groups
}

const BookingCard = ({
  booking,
  expandedBookingId,
  toggleBookingExpanded,
  bookingActionHandlers,
  bookingActionState,
  formatDate,
  formatTime,
}) => {
  const {
    handleEditBookingClick,
    handleResendEmailClick,
    handleSwapVehicleClick,
    handleSendCancellationEmailClick,
    handleSendRefundEmailClick,
    handleRefundBookingClick,
    handleRefundClick,
    handleCancelClick,
    handleMarkPaid,
    handleSendFounderEmailClick,
    handleDeleteClick,
    handleViewDropoffInspectionClick,
    handleViewReturnInspectionClick,
    handleSendParkingUpdate,
    getParkingUpdateStatus,
    getParkingUpdateTitle,
    getParkingUpdateLabel,
  } = bookingActionHandlers

  const {
    cancellingId,
    resendingEmailId,
    deletingId,
    markingPaidId,
    sendingParkingUpdateId,
    sendingFounderEmailId,
    sendingCancellationEmailId,
    sendingRefundEmailId,
  } = bookingActionState

  return (
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
              {/* Billing Address - show for confirmed/completed bookings */}
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
                {booking.secondary_carpark && (
                  <div className="booking-detail">
                    <span className="detail-label">Car Park</span>
                    <span className="detail-value" title={booking.secondary_carpark.reason}>
                      {booking.secondary_carpark.assigned_carpark === 'secondary'
                        ? `Secondary (qualified — ${booking.secondary_carpark.reason})`
                        : `Main (${booking.secondary_carpark.reason})`}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Vehicle Information Section */}
          <div className="booking-section">
            <h4>Vehicle Information</h4>
            <div className="booking-section-content">
              <div className="booking-detail-row">
                <div className="booking-detail">
                  <span className="detail-label">Vehicle</span>
                  <span className="detail-value">
                    <span className="vehicle-reg">{booking.vehicle?.registration}</span>
                    {' '}
                    {booking.vehicle?.colour} {booking.vehicle?.make}
                    {shouldShowAlert(booking.vehicle?.tax_status, booking.vehicle?.mot_status) && (
                      <span
                        className="dvla-alert-badge"
                        title="Vehicle tax/MOT compliance alert"
                        aria-label="Vehicle compliance alert"
                      >
                        ⚠
                      </span>
                    )}
                  </span>
                </div>
                {(() => {
                  // Expiry dates only render for confirmed/refunded bookings
                  // (locked rule — these are the only statuses where we
                  // care about live compliance).
                  const status = booking.status?.toLowerCase()
                  const showDates = status === 'confirmed' || status === 'refunded'
                  return (
                    <>
                      <div className="booking-detail">
                        <span className="detail-label">Tax</span>
                        <span
                          className={`detail-value dvla-status dvla-status-${taxStatusClass(booking.vehicle?.tax_status)}`}
                          data-testid="dvla-tax-status"
                        >
                          {booking.vehicle?.tax_status || '—'}
                        </span>
                        {showDates && booking.vehicle?.tax_due_date && (
                          <span className="dvla-expiry-date">
                            Due {formatIsoDateUk(booking.vehicle.tax_due_date)}
                          </span>
                        )}
                      </div>
                      <div className="booking-detail">
                        <span className="detail-label">MOT</span>
                        <span
                          className={`detail-value dvla-status dvla-status-${motStatusClass(booking.vehicle?.mot_status)}`}
                          data-testid="dvla-mot-status"
                        >
                          {booking.vehicle?.mot_status || '—'}
                        </span>
                        {showDates && booking.vehicle?.mot_expiry_date && (
                          <span className="dvla-expiry-date">
                            Expires {formatIsoDateUk(booking.vehicle.mot_expiry_date)}
                          </span>
                        )}
                      </div>
                    </>
                  )
                })()}
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
                  <span className="detail-value">{formatDestination(booking.dropoff_destination) || '-'}</span>
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
                  <span className="detail-label">Arrival Date</span>
                  <span className="detail-value">{formatDate(resolveArrivalDate(booking))}</span>
                </div>
                <div className="booking-detail">
                  <span className="detail-label">Arrival Time</span>
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
                  <span className="detail-value">{formatDestination(booking.pickup_origin) || '-'}</span>
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

          {/* Refunded Section — shown whenever the payment row carries refund
              metadata, regardless of booking.status. This way the refund
              history stays visible after a `refunded → completed` transition
              (TAG-initiated goodwill refund + customer still parks). */}
          {booking.payment?.refund_amount_pence > 0 && (
            <div className="booking-section booking-refund-section">
              <h4>Refunded</h4>
              <div className="booking-section-content">
                <div className="booking-detail-row">
                  <div className="booking-detail">
                    <span className="detail-label">Refund Amount</span>
                    <span className="detail-value" style={{ color: '#ef4444', fontWeight: 600 }}>
                      −£{(booking.payment.refund_amount_pence / 100).toFixed(2)}
                    </span>
                  </div>
                  {booking.payment.refunded_at && (
                    <div className="booking-detail">
                      <span className="detail-label">Refunded At</span>
                      <span className="detail-value">
                        {new Date(booking.payment.refunded_at).toLocaleString('en-GB', {
                          day: '2-digit', month: '2-digit', year: 'numeric',
                          hour: '2-digit', minute: '2-digit',
                          timeZone: 'Europe/London',
                        })}
                      </span>
                    </div>
                  )}
                  {booking.payment.refund_reason && (
                    <div className="booking-detail">
                      <span className="detail-label">Reason</span>
                      <span className="detail-value">{booking.payment.refund_reason}</span>
                    </div>
                  )}
                  {booking.payment.refund_id && (
                    <div className="booking-detail">
                      <span className="detail-label">Stripe Refund ID</span>
                      <span className="detail-value" style={{ fontFamily: 'monospace', fontSize: '0.85em' }}>
                        {booking.payment.refund_id}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

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
              {/* Swap Vehicle button - only show if not completed and customer has multiple vehicles */}
              {booking.status?.toLowerCase() !== 'completed' && (booking.customer?.vehicle_count || 0) > 1 && (
                <button
                  className="action-btn swap-btn"
                  onClick={(e) => handleSwapVehicleClick(booking, e)}
                >
                  Swap Vehicle
                </button>
              )}
              {/* Show cancellation email button only when status is cancelled */}
              {booking.status?.toLowerCase() === 'cancelled' && (
                <button
                  className="action-btn email-btn"
                  onClick={(e) => handleSendCancellationEmailClick(booking, e)}
                  disabled={sendingCancellationEmailId === booking.id}
                >
                  {sendingCancellationEmailId === booking.id ? 'Sending...' : 'Send Cancellation Email'}
                </button>
              )}
              {/* Show refund email button only when status is cancelled */}
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
                <>
                  <button
                    className="action-btn refund-btn"
                    onClick={(e) => handleRefundBookingClick(booking, e)}
                  >
                    Refund Booking
                  </button>
                  <button
                    className="action-btn"
                    onClick={(e) => handleRefundClick(booking, e)}
                    title="Open this payment in the Stripe dashboard (inspection or partial refunds)"
                  >
                    Open in Stripe ↗
                  </button>
                </>
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
              {/* Mark as Paid button for manual bookings with pending status */}
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
              {/* Send Founder Email button for pending bookings */}
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
              {/* View Drop-off Vehicle Inspection button for completed bookings */}
              {booking.status?.toLowerCase() === 'completed' && booking.id && (
                <button
                  className="action-btn view-inspection-btn"
                  onClick={(e) => handleViewDropoffInspectionClick(booking, e)}
                >
                  View Drop-off Inspection
                </button>
              )}
              {/* View Return Vehicle Inspection button for completed bookings */}
              {booking.status?.toLowerCase() === 'completed' && booking.id && (
                <button
                  className="action-btn view-inspection-btn"
                  onClick={(e) => handleViewReturnInspectionClick(booking, e)}
                >
                  View Return Inspection
                </button>
              )}
              {/* Delete button for pending and cancelled bookings */}
              {['pending', 'cancelled'].includes(booking.status?.toLowerCase()) && (
                <button
                  className="action-btn delete-btn"
                  onClick={(e) => handleDeleteClick(booking, e)}
                  disabled={deletingId === booking.id}
                >
                  {deletingId === booking.id ? 'Deleting...' : 'Delete'}
                </button>
              )}

              {/* Confirmation Email Status Indicator */}
              <div className="reminder-status-indicator">
                <span className="reminder-label">Confirmation</span>
                <span className={`reminder-badge ${booking.confirmation_email_sent ? 'sent' : 'pending'}`}>
                  {booking.confirmation_email_sent ? 'Sent ✓' : 'Pending'}
                </span>
              </div>

              {/* Parking Update Status Indicator */}
              <button
                type="button"
                className="reminder-status-indicator reminder-status-button"
                onClick={(e) => handleSendParkingUpdate(booking, e)}
                disabled={sendingParkingUpdateId === booking.id}
                title={getParkingUpdateTitle(booking)}
              >
                <span className="reminder-label">Parking Update</span>
                <span className={`reminder-badge ${getParkingUpdateStatus(booking)}`}>
                  {sendingParkingUpdateId === booking.id
                    ? 'Sending...'
                    : getParkingUpdateLabel(booking)}
                </span>
              </button>

              {/* 2-Day Reminder Status Indicator */}
              <div className="reminder-status-indicator">
                <span className="reminder-label">2-Day Reminder</span>
                <span className={`reminder-badge ${booking.reminder_2day_sent ? 'sent' : 'pending'}`}>
                  {booking.reminder_2day_sent ? 'Sent ✓' : 'Pending'}
                </span>
              </div>

              {/* Thank You Email Status Indicator - only for completed bookings */}
              {booking.status?.toLowerCase() === 'completed' && (
                <div className="reminder-status-indicator">
                  <span className="reminder-label">Thank You</span>
                  <span className={`reminder-badge ${booking.thank_you_email_sent ? 'sent' : 'pending'}`}>
                    {booking.thank_you_email_sent ? 'Sent ✓' : 'Pending'}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const BookingsSection = ({
  bookings,
  bookingsLoadAll,
  loadingData,
  fetchBookings,
  todaysBookings,
  filteredBookings,
  bookingsByStatus,
  searchTerm,
  setSearchTerm,
  statusFilter,
  setStatusFilter,
  hideTestEmails,
  setHideTestEmails,
  sortAsc,
  setSortAsc,
  collapsedStatusSections,
  setCollapsedStatusSections,
  expandedBookingMonths,
  setExpandedBookingMonths,
  expandedBookingId,
  setExpandedBookingId,
  formatDate,
  formatTime,
  bookingActionHandlers,
  bookingActionState,
}) => {
  const toggleBookingExpanded = (bookingId) => {
    const isClosing = expandedBookingId === bookingId
    setExpandedBookingId(isClosing ? null : bookingId)

    if (!isClosing) {
      window.requestAnimationFrame(() => {
        const element = document.querySelector(`.booking-card[data-booking-id="${bookingId}"]`)
        element?.scrollIntoView({ behavior: 'auto', block: 'start' })
      })
    }
  }

  const toggleBookingMonth = (statusKey, monthKey) => {
    const key = `${statusKey}-${monthKey}`
    setExpandedBookingMonths(prev => ({
      ...prev,
      [key]: !prev[key],
    }))
  }

  const toggleStatusSection = (status) => {
    setCollapsedStatusSections(prev => ({
      ...prev,
      [status]: !prev[status]
    }))
  }

  const onTodayBookingClick = (booking) => {
    const statusKey = (booking.status || 'pending').toLowerCase()

    setCollapsedStatusSections(prev => ({
      ...prev,
      [statusKey]: false,
    }))

    if (statusKey === 'confirmed' || statusKey === 'completed') {
      const dropoffDate = new Date(`${booking.dropoff_date}T12:00:00`)
      const monthKey = `${dropoffDate.getFullYear()}-${String(dropoffDate.getMonth() + 1).padStart(2, '0')}`
      const expandKey = `${statusKey}-${monthKey}`
      setExpandedBookingMonths(prev => ({
        ...prev,
        [expandKey]: true,
      }))
    }

    setExpandedBookingId(booking.id)

    setTimeout(() => {
      const element = document.querySelector(`.booking-card[data-booking-id="${booking.id}"]`)
      if (element) {
        element.scrollIntoView({ behavior: 'auto', block: 'start' })
      }
    }, 300)
  }

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2>Bookings {!bookingsLoadAll && <span className="filter-badge">Last 30 days</span>}</h2>
        <div style={{ display: 'flex', gap: '8px' }}>
          {!bookingsLoadAll && (
            <button onClick={() => fetchBookings(true)} className="admin-refresh" disabled={loadingData}>
              {loadingData ? 'Loading...' : 'Load All'}
            </button>
          )}
          {bookingsLoadAll && (
            <button onClick={() => fetchBookings(false)} className="admin-refresh" disabled={loadingData}>
              {loadingData ? 'Loading...' : 'Last 30 Days'}
            </button>
          )}
          <button onClick={() => fetchBookings(bookingsLoadAll)} className="admin-refresh" disabled={loadingData}>
            {loadingData ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Today's Bookings */}
      {todaysBookings.length > 0 && (
        <div className="recent-bookings-container">
          <h3 className="recent-bookings-title">Today's Bookings - {new Date().toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'long', timeZone: 'Europe/London' })}</h3>
          <div className="recent-bookings-grid">
            {todaysBookings.map((booking) => (
              <div
                key={booking.id || booking.reference}
                className={`recent-booking-card booking-status-${booking.status?.toLowerCase() || 'pending'}`}
                onClick={() => onTodayBookingClick(booking)}
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
          {/* Render each status section in order: Confirmed, Completed, Pending, Cancelled, Refunded.
              Cancelled and Refunded are deliberately separate — Cancelled is customer-initiated
              ("can't travel"); Refunded is TAG-initiated when we've messed up the experience. */}
          {[
            { key: 'confirmed', label: 'Confirmed', color: '#28a745' },
            { key: 'completed', label: 'Completed', color: '#6c757d' },
            { key: 'pending', label: 'Pending', color: '#ffc107' },
            { key: 'cancelled', label: 'Cancelled', color: '#dc3545' },
            { key: 'refunded', label: 'Refunded', color: '#f97316' },
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
                        const sortedMonths = Object.keys(monthlyGroups).sort() // ASC order (oldest first)

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
                                  {monthBookings.map((booking) => (
                                    <BookingCard
                                      key={booking.id || booking.reference}
                                      booking={booking}
                                      expandedBookingId={expandedBookingId}
                                      bookingActionState={bookingActionState}
                                        bookingActionHandlers={bookingActionHandlers}
                                        formatDate={formatDate}
                                        formatTime={formatTime}
                                        toggleBookingExpanded={toggleBookingExpanded}
                                      />
                                  ))}
                                </div>
                              )}
                            </div>
                          )
                        })
                      })()
                    ) : (
                      /* For pending, cancelled, and refunded, show flat list */
                      statusBookings.map((booking) => (
                                  <BookingCard
                                    key={booking.id || booking.reference}
                                    booking={booking}
                                    expandedBookingId={expandedBookingId}
                                    bookingActionState={bookingActionState}
                                    bookingActionHandlers={bookingActionHandlers}
                                    formatDate={formatDate}
                                    formatTime={formatTime}
                                    toggleBookingExpanded={toggleBookingExpanded}
                                  />
                      ))
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default BookingsSection
