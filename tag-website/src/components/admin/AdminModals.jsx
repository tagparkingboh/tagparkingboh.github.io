import { useState, useEffect, useRef } from 'react'
import DatePicker from 'react-datepicker'

const PHOTO_SLOTS = [
  { key: 'front', label: 'Front' },
  { key: 'rear', label: 'Rear' },
  { key: 'driver_side', label: 'Driver Side' },
  { key: 'passenger_side', label: 'Passenger Side' },
  { key: 'additional_1', label: 'Additional 1' },
  { key: 'additional_2', label: 'Additional 2' },
]

const AdminModals = ({
  showCancelModal,
  setShowCancelModal,
  bookingToCancel,
  handleConfirmCancel,
  cancellingId,
  formatDate,
  showDeleteModal,
  setShowDeleteModal,
  bookingToDelete,
  confirmDeleteBooking,
  deletingId,
  showEditModal,
  setShowEditModal,
  bookingToEdit,
  editForm,
  setEditForm,
  formatDateInput,
  parseUkDate,
  dateToUkString,
  confirmEditBooking,
  savingEdit,
  showResendModal,
  setShowResendModal,
  bookingToResend,
  handleConfirmResendEmail,
  resendingEmailId,
  showRefundModal,
  setShowRefundModal,
  bookingToRefund,
  processingRefund,
  refundReason,
  setRefundReason,
  refundModalError,
  handleConfirmRefundBooking,
  showSwapVehicleModal,
  bookingForSwap,
  closeSwapVehicleModal,
  loadingCustomerVehicles,
  customerVehiclesForSwap,
  handleSelectVehicleForSwap,
  setSwapConfirmVehicle,
  swapConfirmVehicle,
  handleConfirmSwapVehicle,
  swappingVehicle,
  showCancellationEmailModal,
  setShowCancellationEmailModal,
  bookingForCancellationEmail,
  handleConfirmSendCancellationEmail,
  sendingCancellationEmailId,
  showRefundEmailModal,
  setShowRefundEmailModal,
  bookingForRefundEmail,
  handleConfirmSendRefundEmail,
  sendingRefundEmailId,
  showFounderEmailModal,
  setShowFounderEmailModal,
  bookingForFounderEmail,
  handleConfirmSendFounderEmail,
  sendingFounderEmailId,
  showPromoModal,
  setShowPromoModal,
  promoToSend,
  confirmSendPromo,
  sendingPromoId,
  setPromoToSend,
  showSubscriberFounderModal,
  setShowSubscriberFounderModal,
  founderEmailToSend,
  confirmSendFounderEmail,
  setFounderEmailToSend,
  showReturnInspectionModal,
  closeReturnInspectionModal,
  bookingForInspection,
  loadingReturnInspection,
  returnInspectionData,
  formatDateTimeUK,
  showDropoffInspectionModal,
  closeDropoffInspectionModal,
  bookingForDropoffInspection,
  loadingDropoffInspection,
  dropoffInspectionData,
}) => {
  // Expand + rotate for inspection photos (view-only; the stored photo is never modified).
  const [expandedPhoto, setExpandedPhoto] = useState(null) // { src, label, key }
  const [photoRotations, setPhotoRotations] = useState({}) // { [key]: degrees }
  const rotatePhoto = (key) => setPhotoRotations(prev => ({ ...prev, [key]: ((prev[key] || 0) + 90) % 360 }))
  const rotationStyle = (key) => ({ transform: `rotate(${photoRotations[key] || 0}deg)` })
  const imageViewerRef = useRef(null)

  // Request real browser fullscreen for the expanded photo (mirrors /employee)
  // so the address bar / browser chrome hides too. iPhone Safari doesn't support
  // fullscreen on non-video elements; the dvh-sized overlay is the fallback.
  useEffect(() => {
    if (!expandedPhoto) return
    const el = imageViewerRef.current
    if (!el) return

    const req = el.requestFullscreen || el.webkitRequestFullscreen
    if (req) Promise.resolve(req.call(el)).catch(() => {})

    const onFsChange = () => {
      const fsEl = document.fullscreenElement || document.webkitFullscreenElement
      if (!fsEl) setExpandedPhoto(null)
    }
    document.addEventListener('fullscreenchange', onFsChange)
    document.addEventListener('webkitfullscreenchange', onFsChange)

    return () => {
      document.removeEventListener('fullscreenchange', onFsChange)
      document.removeEventListener('webkitfullscreenchange', onFsChange)
      const fsEl = document.fullscreenElement || document.webkitFullscreenElement
      if (fsEl) {
        const exit = document.exitFullscreen || document.webkitExitFullscreen
        if (exit) Promise.resolve(exit.call(document)).catch(() => {})
      }
    }
  }, [expandedPhoto])

  return (
    <>
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
                  <label>Drop-off Date</label>
                  <div style={{ display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
                    <input
                      type="text"
                      placeholder="DD/MM/YYYY"
                      value={editForm.dropoff_date}
                      onChange={(e) => setEditForm({ ...editForm, dropoff_date: formatDateInput(e.target.value) })}
                      maxLength={10}
                      style={{ width: '125px' }}
                    />
                    <DatePicker
                      selected={parseUkDate(editForm.dropoff_date)}
                      onChange={(date) => setEditForm({ ...editForm, dropoff_date: dateToUkString(date) })}
                      dateFormat="dd/MM/yyyy"
                      customInput={<button type="button" className="date-picker-btn">📅</button>}
                    />
                  </div>
                </div>
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
                  <label>Arrival Date</label>
                  <div style={{ display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
                    <input
                      type="text"
                      placeholder="DD/MM/YYYY"
                      pattern="\d{2}/\d{2}/\d{4}"
                      value={editForm.flight_arrival_date}
                      onChange={(e) => setEditForm({ ...editForm, flight_arrival_date: formatDateInput(e.target.value) })}
                      maxLength={10}
                      style={{ width: '125px' }}
                    />
                    <DatePicker
                      selected={parseUkDate(editForm.flight_arrival_date)}
                      onChange={(date) => setEditForm({ ...editForm, flight_arrival_date: dateToUkString(date) })}
                      dateFormat="dd/MM/yyyy"
                      customInput={<button type="button" className="date-picker-btn">📅</button>}
                    />
                  </div>
                </div>
                <div className="modal-form-group">
                  <label>Pickup Date</label>
                  <div style={{ display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
                    <input
                      type="text"
                      placeholder="DD/MM/YYYY"
                      pattern="\d{2}/\d{2}/\d{4}"
                      value={editForm.pickup_date}
                      onChange={(e) => setEditForm({ ...editForm, pickup_date: formatDateInput(e.target.value) })}
                      maxLength={10}
                      style={{ width: '125px' }}
                    />
                    <DatePicker
                      selected={parseUkDate(editForm.pickup_date)}
                      onChange={(date) => setEditForm({ ...editForm, pickup_date: dateToUkString(date) })}
                      dateFormat="dd/MM/yyyy"
                      customInput={<button type="button" className="date-picker-btn">📅</button>}
                    />
                  </div>
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

      {/* Refund Booking Modal */}
      {showRefundModal && bookingToRefund && (
        <div className="modal-overlay" onClick={() => !processingRefund && setShowRefundModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Refund Booking</h3>
            <p>
              This issues a <strong>full refund of £{((bookingToRefund.payment?.amount_pence || 0) / 100).toFixed(2)}</strong> via
              Stripe. It cannot be undone. Financials updates automatically;
              the refund email stays a separate manual step.
            </p>
            <div className="modal-booking-info">
              <p><strong>Reference:</strong> {bookingToRefund.reference}</p>
              <p><strong>Customer:</strong> {bookingToRefund.customer?.first_name} {bookingToRefund.customer?.last_name}</p>
            </div>
            <div className="modal-form-group" style={{ margin: '12px 0' }}>
              <label>Reason</label>
              <select
                value={refundReason}
                onChange={(e) => setRefundReason(e.target.value)}
                disabled={processingRefund}
              >
                <option value="requested_by_customer">Customer request</option>
                <option value="duplicate">Duplicate payment</option>
                <option value="fraudulent">Fraudulent</option>
              </select>
            </div>
            {refundModalError && (
              <p style={{ color: '#ef4444', fontSize: '13px' }}>{refundModalError}</p>
            )}
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowRefundModal(false)}
                disabled={processingRefund}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={handleConfirmRefundBooking}
                disabled={processingRefund}
              >
                {processingRefund
                  ? 'Refunding...'
                  : `Refund £${((bookingToRefund.payment?.amount_pence || 0) / 100).toFixed(2)}`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Swap Vehicle Modal */}
      {showSwapVehicleModal && bookingForSwap && (
        <div className="modal-overlay" onClick={closeSwapVehicleModal}>
          <div className="modal-content swap-vehicle-modal" onClick={(e) => e.stopPropagation()}>
            {!swapConfirmVehicle ? (
              <>
                <h3>Swap Vehicle</h3>
                <div className="modal-booking-info">
                  <p><strong>Booking:</strong> {bookingForSwap.reference}</p>
                  <p><strong>Current Vehicle:</strong> {bookingForSwap.vehicle?.registration} ({bookingForSwap.vehicle?.make} {bookingForSwap.vehicle?.colour})</p>
                </div>

                {loadingCustomerVehicles ? (
                  <div className="loading-spinner">Loading vehicles...</div>
                ) : customerVehiclesForSwap.length === 0 ? (
                  <div className="no-vehicles-message">
                    <p>No other vehicles found for this customer.</p>
                    <p className="hint">Add vehicles in the customer's profile first.</p>
                  </div>
                ) : (
                  <>
                    <p className="swap-instruction">Select a vehicle to swap to:</p>
                    <div className="swap-vehicles-list">
                      {customerVehiclesForSwap.map(vehicle => (
                        <div
                          key={vehicle.id}
                          className="swap-vehicle-card"
                          onClick={() => handleSelectVehicleForSwap(vehicle)}
                        >
                          <div className="swap-vehicle-reg">{vehicle.registration}</div>
                          <div className="swap-vehicle-details">
                            {vehicle.make} {vehicle.model && `${vehicle.model} `}- {vehicle.colour}
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}

                <div className="modal-actions">
                  <button
                    className="modal-btn modal-btn-secondary"
                    onClick={closeSwapVehicleModal}
                  >
                    Cancel
                  </button>
                </div>
              </>
            ) : (
              <>
                <h3>Confirm Vehicle Swap</h3>
                <div className="swap-confirm-info">
                  <div className="swap-from">
                    <span className="swap-label">From:</span>
                    <span className="swap-reg">{bookingForSwap.vehicle?.registration}</span>
                    <span className="swap-details">{bookingForSwap.vehicle?.make} {bookingForSwap.vehicle?.colour}</span>
                  </div>
                  <div className="swap-arrow">→</div>
                  <div className="swap-to">
                    <span className="swap-label">To:</span>
                    <span className="swap-reg">{swapConfirmVehicle.registration}</span>
                    <span className="swap-details">{swapConfirmVehicle.make} {swapConfirmVehicle.model && `${swapConfirmVehicle.model} `}{swapConfirmVehicle.colour}</span>
                  </div>
                </div>
                <p className="swap-warning">This will update the vehicle for booking {bookingForSwap.reference}.</p>
                <div className="modal-actions">
                  <button
                    className="modal-btn modal-btn-secondary"
                    onClick={() => setSwapConfirmVehicle(null)}
                  >
                    Back
                  </button>
                  <button
                    className="modal-btn modal-btn-primary"
                    onClick={handleConfirmSwapVehicle}
                    disabled={swappingVehicle}
                  >
                    {swappingVehicle ? 'Swapping...' : 'Confirm Swap'}
                  </button>
                </div>
              </>
            )}
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

      {/* Send Promo Code Confirmation Modal */}
      {showPromoModal && promoToSend && (
        <div className="modal-overlay" onClick={() => { setShowPromoModal(false); setPromoToSend(null); }}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Send {promoToSend.discountPercent === 100 ? 'FREE Parking' : '10% Off'} Promo</h3>
            <p>Are you sure you want to send this promo code?</p>
            <div className="modal-booking-info">
              <p><strong>Subscriber:</strong> {promoToSend.subscriber.first_name} {promoToSend.subscriber.last_name}</p>
              <p><strong>Email:</strong> {promoToSend.subscriber.email}</p>
              <p><strong>Discount:</strong> {promoToSend.discountPercent === 100 ? 'FREE Parking (100% off)' : '10% Off'}</p>
            </div>
            <p className="modal-warning">
              This will generate a unique promo code and send an email to the subscriber.
            </p>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => { setShowPromoModal(false); setPromoToSend(null); }}
              >
                Cancel
              </button>
              <button
                className={`modal-btn ${promoToSend.discountPercent === 100 ? 'modal-btn-success' : 'modal-btn-primary'}`}
                onClick={confirmSendPromo}
                disabled={sendingPromoId}
              >
                {sendingPromoId ? 'Sending...' : `Yes, Send ${promoToSend.discountPercent === 100 ? 'FREE' : '10% Off'} Code`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Send Founder Thank You Email Confirmation Modal (for Marketing Subscribers) */}
      {showSubscriberFounderModal && founderEmailToSend && (
        <div className="modal-overlay" onClick={() => { setShowSubscriberFounderModal(false); setFounderEmailToSend(null); }}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Send Founder Thank You Email</h3>
            <p>Are you sure you want to send this personal thank you email from Kristian?</p>
            <div className="modal-booking-info">
              <p><strong>Subscriber:</strong> {founderEmailToSend.subscriber.first_name} {founderEmailToSend.subscriber.last_name}</p>
              <p><strong>Email:</strong> {founderEmailToSend.subscriber.email}</p>
            </div>
            <p className="modal-warning">
              This will generate a unique 10% promo code and send a personal thank you email from Kristian.
              The email will be CC'd to Kristian so he can see and respond to any replies.
            </p>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => { setShowSubscriberFounderModal(false); setFounderEmailToSend(null); }}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={confirmSendFounderEmail}
                disabled={sendingFounderEmailId}
              >
                {sendingFounderEmailId ? 'Sending...' : 'Yes, Send Founder Email'}
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
              <p><strong>Vehicle:</strong> {bookingForInspection.vehicle?.registration} - {bookingForInspection.vehicle?.colour} {bookingForInspection.vehicle?.make}</p>
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
                                <img
                                  src={returnInspectionData.photos[slot.key]}
                                  alt={slot.label}
                                  style={rotationStyle(`ret-${slot.key}`)}
                                />
                                <div className="inspection-photo-actions">
                                  <button type="button" className="inspection-photo-btn" onClick={() => rotatePhoto(`ret-${slot.key}`)}>↻ Rotate</button>
                                  <button type="button" className="inspection-photo-btn" onClick={() => setExpandedPhoto({ src: returnInspectionData.photos[slot.key], label: slot.label, key: `ret-${slot.key}` })}>⤢ Expand</button>
                                </div>
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
              <p><strong>Vehicle:</strong> {bookingForDropoffInspection.vehicle?.registration} - {bookingForDropoffInspection.vehicle?.colour} {bookingForDropoffInspection.vehicle?.make}</p>
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
                            <img
                              src={dropoffInspectionData.photos[slot.key]}
                              alt={slot.label}
                              style={rotationStyle(`drop-${slot.key}`)}
                            />
                            <div className="inspection-photo-actions">
                              <button type="button" className="inspection-photo-btn" onClick={() => rotatePhoto(`drop-${slot.key}`)}>↻ Rotate</button>
                              <button type="button" className="inspection-photo-btn" onClick={() => setExpandedPhoto({ src: dropoffInspectionData.photos[slot.key], label: slot.label, key: `drop-${slot.key}` })}>⤢ Expand</button>
                            </div>
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

      {expandedPhoto && (
        <div className="image-viewer-overlay" ref={imageViewerRef} onClick={() => setExpandedPhoto(null)}>
          <button className="image-viewer-close" onClick={() => setExpandedPhoto(null)}>&times;</button>
          <div className="image-viewer-label">{expandedPhoto.label}</div>
          <img
            src={expandedPhoto.src}
            alt={expandedPhoto.label}
            className="image-viewer-img"
            style={rotationStyle(expandedPhoto.key)}
            onClick={e => e.stopPropagation()}
          />
          <button
            type="button"
            className="image-viewer-rotate"
            onClick={(e) => { e.stopPropagation(); rotatePhoto(expandedPhoto.key) }}
          >
            ↻ Rotate
          </button>
        </div>
      )}
    </>
  )
}

export default AdminModals
