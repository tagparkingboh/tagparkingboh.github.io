const TestimonialsSection = ({
  testimonials,
  loadingTestimonials,
  fetchTestimonials,
  testimonialSuccessMessage,
  testimonialFilter,
  setTestimonialFilter,
  testimonialSort,
  setTestimonialSort,
  openAddTestimonialModal,
  renderStars,
  openEditTestimonialModal,
  handleToggleTestimonialStatus,
  setTestimonialToDelete,
  setShowDeleteTestimonialModal,
}) => {
  const safeFilter = testimonialFilter || { star_rating: '', status: '' }
  const safeSort = testimonialSort || { field: 'date_added', order: 'desc' }

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2>Testimonials</h2>
        <div className="admin-header-actions">
          <button onClick={openAddTestimonialModal} className="admin-btn admin-btn-primary">
            + Add Testimonial
          </button>
          <button onClick={fetchTestimonials} className="admin-refresh" disabled={loadingTestimonials}>
            {loadingTestimonials ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>

      {testimonialSuccessMessage && (
        <div className="admin-success">{testimonialSuccessMessage}</div>
      )}

      <div className="admin-filters" style={{ marginBottom: '1rem' }}>
        <select
          value={safeFilter.star_rating}
          onChange={(e) => setTestimonialFilter({ ...safeFilter, star_rating: e.target.value })}
          className="admin-filter-select"
        >
          <option value="">All Ratings</option>
          <option value="5">5★ Only</option>
          <option value="4">4★ Only</option>
          <option value="3">3★ Only</option>
          <option value="2">2★ Only</option>
          <option value="1">1★ Only</option>
        </select>
        <select
          value={safeFilter.status}
          onChange={(e) => setTestimonialFilter({ ...safeFilter, status: e.target.value })}
          className="admin-filter-select"
        >
          <option value="">All Status</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
        <select
          value={`${safeSort.field}-${safeSort.order}`}
          onChange={(e) => {
            const [field, order] = e.target.value.split('-')
            setTestimonialSort({ field, order })
          }}
          className="admin-filter-select"
        >
          <option value="date_added-desc">Newest First</option>
          <option value="date_added-asc">Oldest First</option>
          <option value="star_rating-desc">Highest Rated</option>
          <option value="star_rating-asc">Lowest Rated</option>
        </select>
      </div>

      {loadingTestimonials ? (
        <div className="admin-loading-inline">
          <div className="spinner-small"></div>
          <span>Loading testimonials...</span>
        </div>
      ) : testimonials.length === 0 ? (
        <p className="admin-empty">No testimonials found. Click "Add Testimonial" to create one.</p>
      ) : (
        <table className="admin-table">
          <thead>
            <tr>
              <th>Customer</th>
              <th>Rating</th>
              <th>Review</th>
              <th>Source</th>
              <th>Date Added</th>
              <th>Status</th>
              <th>Featured</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {testimonials.map((t) => (
              <tr key={t.id} className={t.is_featured ? 'row-featured' : ''}>
                <td>{t.customer_name}</td>
                <td>{renderStars(t.star_rating)}</td>
                <td className="review-cell">
                  {t.review_text.length > 80
                    ? t.review_text.substring(0, 80) + '...'
                    : t.review_text}
                </td>
                <td>{t.source || '-'}</td>
                <td>{t.date_added ? new Date(t.date_added).toLocaleDateString('en-GB') : '-'}</td>
                <td>
                  <span className={`status-badge status-${t.status === 'active' ? 'confirmed' : 'pending'}`}>
                    {t.status}
                  </span>
                </td>
                <td>{t.is_featured ? '✓' : '-'}</td>
                <td className="actions-cell">
                  <button
                    className="action-btn edit-btn"
                    onClick={() => openEditTestimonialModal(t)}
                  >
                    Edit
                  </button>
                  <button
                    className="action-btn"
                    onClick={() => handleToggleTestimonialStatus(t)}
                    style={{ backgroundColor: t.status === 'active' ? '#f59e0b' : '#22c55e', color: '#fff' }}
                  >
                    {t.status === 'active' ? 'Deactivate' : 'Activate'}
                  </button>
                  <button
                    className="action-btn cancel-btn"
                    onClick={() => {
                      setTestimonialToDelete(t)
                      setShowDeleteTestimonialModal(true)
                    }}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default TestimonialsSection
