import DatePicker from 'react-datepicker'

const TestimonialsModals = ({
  showTestimonialModal,
  setShowTestimonialModal,
  testimonialForm,
  setTestimonialForm,
  detectedTestimonialThemes,
  editingTestimonial,
  handleSaveTestimonial,
  savingTestimonial,
  showDeleteTestimonialModal,
  setShowDeleteTestimonialModal,
  testimonialToDelete,
  handleDeleteTestimonial,
  deletingTestimonial,
}) => {
  return (
    <>
      {/* Testimonial Add/Edit Modal */}
      {showTestimonialModal && (
        <div className="modal-overlay" onClick={() => setShowTestimonialModal(false)}>
          <div className="modal-content modal-content-wide" onClick={(e) => e.stopPropagation()}>
            <h3>{editingTestimonial ? 'Edit Testimonial' : 'Add Testimonial'}</h3>

            <div className="modal-form">
              <div className="form-group">
                <label>Customer Name *</label>
                <input
                  type="text"
                  value={testimonialForm.customer_name}
                  onChange={(e) => setTestimonialForm({ ...testimonialForm, customer_name: e.target.value })}
                  placeholder="e.g. John Smith"
                  maxLength={100}
                />
              </div>

              <div className="form-group">
                <label>Review Text *</label>
                <textarea
                  value={testimonialForm.review_text}
                  onChange={(e) => setTestimonialForm({ ...testimonialForm, review_text: e.target.value })}
                  placeholder="Enter the customer's review..."
                  rows={4}
                />
                {detectedTestimonialThemes.length > 0 && (
                  <div className="testimonial-theme-preview" aria-label="Detected testimonial themes">
                    <span className="testimonial-theme-preview-label">Themes</span>
                    <div className="testimonial-theme-pills">
                      {detectedTestimonialThemes.map(theme => (
                        <span key={theme} className="testimonial-theme-pill">{theme}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Star Rating (optional for LinkedIn/FB)</label>
                  <div className="star-selector">
                    {[1, 2, 3, 4, 5].map(star => (
                      <button
                        key={star}
                        type="button"
                        className={`star-btn ${testimonialForm.star_rating >= star ? 'selected' : ''}`}
                        onClick={() => setTestimonialForm({
                          ...testimonialForm,
                          star_rating: testimonialForm.star_rating === star ? null : star,
                        })}
                      >
                        {testimonialForm.star_rating >= star ? '★' : '☆'}
                      </button>
                    ))}
                    {testimonialForm.star_rating && (
                      <button
                        type="button"
                        className="clear-rating-btn"
                        onClick={() => setTestimonialForm({ ...testimonialForm, star_rating: null })}
                      >
                        Clear
                      </button>
                    )}
                  </div>
                </div>

                <div className="form-group">
                  <label>Source</label>
                  <input
                    type="text"
                    value={testimonialForm.source}
                    onChange={(e) => setTestimonialForm({ ...testimonialForm, source: e.target.value })}
                    placeholder="e.g. Google, TrustPilot, LinkedIn"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Date of Travel</label>
                  <DatePicker
                    selected={testimonialForm.date_of_travel ? new Date(testimonialForm.date_of_travel) : null}
                    onChange={(date) => setTestimonialForm({
                      ...testimonialForm,
                      date_of_travel: date ? date.toISOString().split('T')[0] : ''
                    })}
                    dateFormat="dd/MM/yyyy"
                    placeholderText="dd/mm/yyyy"
                    className="admin-input"
                  />
                </div>

                <div className="form-group">
                  <label>Status</label>
                  <select
                    value={testimonialForm.status}
                    onChange={(e) => setTestimonialForm({ ...testimonialForm, status: e.target.value })}
                  >
                    <option value="inactive">Inactive (Draft)</option>
                    <option value="active">Active (Published)</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={testimonialForm.is_featured}
                    onChange={(e) => setTestimonialForm({ ...testimonialForm, is_featured: e.target.checked })}
                  />
                  Mark as Featured (appears more frequently in rotation)
                </label>
              </div>
            </div>

            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowTestimonialModal(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={handleSaveTestimonial}
                disabled={savingTestimonial || !testimonialForm.customer_name || !testimonialForm.review_text}
              >
                {savingTestimonial ? 'Saving...' : (editingTestimonial ? 'Update' : 'Save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Testimonial Modal */}
      {showDeleteTestimonialModal && testimonialToDelete && (
        <div className="modal-overlay" onClick={() => setShowDeleteTestimonialModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Delete Testimonial</h3>
            <p>Are you sure you want to delete this review? This action cannot be undone.</p>
            <div className="modal-booking-info">
              <p><strong>Customer:</strong> {testimonialToDelete.customer_name}</p>
              <p><strong>Review:</strong> {testimonialToDelete.review_text.substring(0, 80)}...</p>
            </div>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowDeleteTestimonialModal(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-danger"
                onClick={handleDeleteTestimonial}
                disabled={deletingTestimonial}
              >
                {deletingTestimonial ? 'Deleting...' : 'Yes, Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default TestimonialsModals
