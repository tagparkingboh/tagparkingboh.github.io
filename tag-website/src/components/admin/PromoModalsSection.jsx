const PromoModalsSection = ({
  promoModals,
  loadingPromoModals,
  fetchPromoModals,
  promoModalSuccessMessage,
  setEditingPromoModal,
  setPromoModalForm,
  setPromoCodeIsMultiUse,
  setSelectedPromoCodeInfo,
  setShowPromoModalForm,
  fetchPromoCodesForModal,
  openEditPromoModal,
  handleTogglePromoModalStatus,
  setPromoModalToDelete,
  setShowDeletePromoModal,
}) => {
  const safePromoModals = promoModals || []

  const setInfoModalForm = () => {
    setEditingPromoModal(null)
    setPromoModalForm({
      type: 'info_modal',
      title: '',
      message: '',
      button_text: 'Subscribe',
      button_action: 'subscribe',
      button_link: '',
      start_date: '',
      end_date: '',
      background_color: '#343434',
      text_color: '#d9ff00',
      button_color: '#d9ff00',
      button_text_color: '#343434',
      status: 'inactive',
      max_subscribers: '',
      promo_code: '',
    })
    setPromoCodeIsMultiUse(false)
    setSelectedPromoCodeInfo(null)
    setShowPromoModalForm(true)
  }

  const setSectionForm = () => {
    setEditingPromoModal(null)
    setPromoModalForm({
      type: 'promo_section',
      title: '',
      message: '',
      button_text: '',
      button_action: 'close',
      button_link: '',
      start_date: '',
      end_date: '',
      background_color: '#343434',
      text_color: '#d9ff00',
      button_color: '#d9ff00',
      button_text_color: '#343434',
      status: 'inactive',
      max_subscribers: '',
      promo_code: '',
    })
    setPromoCodeIsMultiUse(false)
    setSelectedPromoCodeInfo(null)
    fetchPromoCodesForModal()
    setShowPromoModalForm(true)
  }

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2>Info Modals & Promo Sections</h2>
        <div className="admin-header-actions">
          <button onClick={setInfoModalForm} className="admin-btn admin-btn-primary">
            + Add Info Modal
          </button>
          <button onClick={setSectionForm} className="admin-btn admin-btn-primary">
            + Add Promo Section
          </button>
          <button onClick={fetchPromoModals} className="admin-refresh" disabled={loadingPromoModals}>
            {loadingPromoModals ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>

      {promoModalSuccessMessage && (
        <div className="admin-success">{promoModalSuccessMessage}</div>
      )}

      <p className="reports-description">
        <strong>Info Modal:</strong> A popup that appears when users first visit the site (title + message + button).
        <br />
        <strong>Promo Section:</strong> A section on the homepage showing a promo code (title + message + copyable code).
      </p>

      {loadingPromoModals ? (
        <div className="admin-loading-inline">
          <div className="spinner-small"></div>
          <span>Loading promo modals...</span>
        </div>
      ) : safePromoModals.length === 0 ? (
        <div className="admin-empty">No promo modals created yet.</div>
      ) : (
        <table className="admin-table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Title</th>
              <th>Status</th>
              <th>Date Range</th>
              <th>Views</th>
              <th>Clicks</th>
              <th>CTR</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {safePromoModals.map(modal => {
              const ctr = modal.viewCount > 0 ? ((modal.clickCount / modal.viewCount) * 100).toFixed(1) : '0.0'
              const typeLabel = modal.type === 'promo_section' ? 'Promo Section' : 'Info Modal'
              const typeColor = modal.type === 'promo_section' ? '#16a34a' : '#3b82f6'
              return (
                <tr key={modal.id}>
                  <td>
                    <span style={{
                      backgroundColor: typeColor,
                      color: '#fff',
                      padding: '2px 8px',
                      borderRadius: '4px',
                      fontSize: '0.75rem',
                      fontWeight: '600'
                    }}>
                      {typeLabel}
                    </span>
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span
                        style={{
                          width: '12px',
                          height: '12px',
                          borderRadius: '2px',
                          backgroundColor: modal.backgroundColor,
                          border: '1px solid #ccc'
                        }}
                      />
                      {modal.title}
                    </div>
                  </td>
                  <td>
                    <span className={`status-badge status-${modal.status}`}>
                      {modal.status}
                    </span>
                  </td>
                  <td>
                    {modal.startDate && modal.endDate
                      ? `${modal.startDate} - ${modal.endDate}`
                      : modal.startDate
                        ? `From ${modal.startDate}`
                        : modal.endDate
                          ? `Until ${modal.endDate}`
                          : 'No date limit'}
                  </td>
                  <td>{modal.viewCount}</td>
                  <td>{modal.clickCount}</td>
                  <td>{ctr}%</td>
                  <td className="actions-cell">
                    <button
                      className="action-btn edit-btn"
                      onClick={() => openEditPromoModal(modal)}
                    >
                      Edit
                    </button>
                    <button
                      className="action-btn"
                      onClick={() => handleTogglePromoModalStatus(modal)}
                      style={{ backgroundColor: modal.status === 'active' ? '#f59e0b' : '#22c55e', color: '#fff' }}
                    >
                      {modal.status === 'active' ? 'Deactivate' : 'Activate'}
                    </button>
                    <button
                      className="action-btn cancel-btn"
                      onClick={() => {
                        setPromoModalToDelete(modal)
                        setShowDeletePromoModal(true)
                      }}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default PromoModalsSection
