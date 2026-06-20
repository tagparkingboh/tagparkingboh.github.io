import DatePicker from 'react-datepicker'

const PromoModalsModals = ({
  showPromoModalForm,
  editingPromoModal,
  promoModalForm,
  setPromoModalForm,
  setShowPromoModalForm,
  formatDateInput,
  parseUkDate,
  dateToUkString,
  loadingPromoCodesForModal,
  promoCodesForModal,
  setPromoCodeIsMultiUse,
  setSelectedPromoCodeInfo,
  selectedPromoCodeInfo,
  handleSavePromoModal,
  savingPromoModal,
  showDeletePromoModal,
  promoModalToDelete,
  setShowDeletePromoModal,
  handleDeletePromoModal,
  deletingPromoModal,
}) => {
  const promoCodeGroups = [...new Set(promoCodesForModal.map(c => c.promotion_name))]

  return (
    <>
      {showPromoModalForm && (
        <div className="modal-overlay" onClick={() => setShowPromoModalForm(false)}>
          <div className="modal-content modal-content-wide" onClick={(e) => e.stopPropagation()}>
            <h3>{editingPromoModal ? `Edit ${promoModalForm.type === 'promo_section' ? 'Promo Section' : 'Info Modal'}` : `Add ${promoModalForm.type === 'promo_section' ? 'Promo Section' : 'Info Modal'}`}</h3>

            <div className="modal-form">
              {/* Common Settings */}
              <div style={{ background: '#f8f9fa', padding: '1rem', borderRadius: '8px', marginBottom: '1.5rem' }}>
                <h4 style={{ margin: '0 0 1rem 0', color: '#343434', fontSize: '1rem', borderBottom: '2px solid #d9ff00', paddingBottom: '0.5rem' }}>
                  {promoModalForm.type === 'promo_section' ? 'Promo Section Settings' : 'Info Modal Settings'}
                </h4>
                <p style={{ fontSize: '0.85rem', color: '#666', margin: '0 0 1rem 0' }}>
                  {promoModalForm.type === 'promo_section'
                    ? 'This appears as a section on the homepage with a copyable promo code'
                    : 'This appears as a popup when users first visit the site'}
                </p>

                <div className="form-group">
                  <label>Title *</label>
                  <input
                    type="text"
                    value={promoModalForm.title}
                    onChange={(e) => setPromoModalForm({ ...promoModalForm, title: e.target.value })}
                    placeholder="e.g. Spring Sale!"
                    maxLength={100}
                  />
                </div>

                <div className="form-group">
                  <label>Message *</label>
                  <textarea
                    value={promoModalForm.message}
                    onChange={(e) => setPromoModalForm({ ...promoModalForm, message: e.target.value })}
                    placeholder="Enter the promotional message..."
                    rows={4}
                  />
                </div>

                {/* Button fields - Info Modal only */}
                {promoModalForm.type === 'info_modal' && (
                  <>
                    <div className="form-row">
                      <div className="form-group">
                        <label>Button Text</label>
                        <input
                          type="text"
                          value={promoModalForm.button_text}
                          onChange={(e) => setPromoModalForm({ ...promoModalForm, button_text: e.target.value })}
                          placeholder="Subscribe"
                        />
                      </div>

                      <div className="form-group">
                        <label>Button Action</label>
                        <select
                          value={promoModalForm.button_action}
                          onChange={(e) => setPromoModalForm({ ...promoModalForm, button_action: e.target.value })}
                        >
                          <option value="promotions">Scroll to Promotions</option>
                          <option value="subscribe">Scroll to Subscribe</option>
                          <option value="link">Open Link</option>
                          <option value="close">Just Close</option>
                        </select>
                      </div>
                    </div>

                    {promoModalForm.button_action === 'link' && (
                      <div className="form-group">
                        <label>Button Link</label>
                        <input
                          type="url"
                          value={promoModalForm.button_link}
                          onChange={(e) => setPromoModalForm({ ...promoModalForm, button_link: e.target.value })}
                          placeholder="https://..."
                        />
                      </div>
                    )}
                  </>
                )}

                {/* Promo Code - Promo Section only */}
                {promoModalForm.type === 'promo_section' && (
                  <div className="form-group">
                    <label>Promo Code *</label>
                    <select
                      value={promoModalForm.promo_code}
                      onChange={(e) => {
                        const selectedCode = e.target.value
                        setPromoModalForm({ ...promoModalForm, promo_code: selectedCode })
                        const codeInfo = promoCodesForModal.find(c => c.code === selectedCode)
                        setSelectedPromoCodeInfo(codeInfo || null)
                        setPromoCodeIsMultiUse(codeInfo?.is_multi_use || false)
                      }}
                      style={{ width: '100%', padding: '0.5rem' }}
                    >
                      <option value="">-- Select a promo code --</option>
                      {loadingPromoCodesForModal ? (
                        <option disabled>Loading...</option>
                      ) : (
                        promoCodeGroups.map(promoName => (
                          <optgroup key={promoName} label={promoName}>
                            {promoCodesForModal
                              .filter(c => c.promotion_name === promoName)
                              .map(c => (
                                <option key={c.id} value={c.code}>
                                  {c.code} ({c.promotion_discount}% off{c.is_multi_use ? ', multi-use' : ''}{c.is_used && !c.is_multi_use ? ', USED' : ''})
                                </option>
                              ))}
                          </optgroup>
                        ))
                      )}
                    </select>
                    {selectedPromoCodeInfo && (
                      <small style={{ color: selectedPromoCodeInfo.is_multi_use ? '#16a34a' : '#666', fontSize: '0.8rem', display: 'block', marginTop: '0.25rem' }}>
                        {selectedPromoCodeInfo.is_multi_use
                          ? `Multi-use code (${selectedPromoCodeInfo.use_count || 0} uses) - section expires by end date`
                          : selectedPromoCodeInfo.is_used
                            ? 'This code has already been used'
                            : 'Single-use code - section hides when used'
                        }
                      </small>
                    )}
                  </div>
                )}
              </div>

              {/* Date & Status Settings */}
              <div style={{ background: '#f8f9fa', padding: '1rem', borderRadius: '8px', marginBottom: '1.5rem' }}>
                <h4 style={{ margin: '0 0 1rem 0', color: '#343434', fontSize: '1rem', borderBottom: '2px solid #d9ff00', paddingBottom: '0.5rem' }}>
                  Schedule & Status
                </h4>

                <div className="form-row">
                  <div className="form-group">
                    <label>Start Date</label>
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <input
                        type="text"
                        value={promoModalForm.start_date}
                        onChange={(e) => setPromoModalForm({ ...promoModalForm, start_date: formatDateInput(e.target.value) })}
                        placeholder="DD/MM/YYYY"
                        maxLength={10}
                        style={{ width: '125px' }}
                      />
                      <DatePicker
                        selected={parseUkDate(promoModalForm.start_date)}
                        onChange={(date) => setPromoModalForm({ ...promoModalForm, start_date: dateToUkString(date) })}
                        dateFormat="dd/MM/yyyy"
                        customInput={<button type="button" className="date-picker-btn">📅</button>}
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label>End Date</label>
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <input
                        type="text"
                        value={promoModalForm.end_date}
                        onChange={(e) => setPromoModalForm({ ...promoModalForm, end_date: formatDateInput(e.target.value) })}
                        placeholder="DD/MM/YYYY"
                        maxLength={10}
                        style={{ width: '125px' }}
                      />
                      <DatePicker
                        selected={parseUkDate(promoModalForm.end_date)}
                        onChange={(date) => setPromoModalForm({ ...promoModalForm, end_date: dateToUkString(date) })}
                        dateFormat="dd/MM/yyyy"
                        customInput={<button type="button" className="date-picker-btn">📅</button>}
                      />
                    </div>
                  </div>
                </div>

                {/* Color fields - only for Info Modal type */}
                {promoModalForm.type === 'info_modal' && (
                  <div className="form-row">
                    <div className="form-group">
                      <label>Background Color</label>
                      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                        <input
                          type="color"
                          value={promoModalForm.background_color}
                          onChange={(e) => setPromoModalForm({ ...promoModalForm, background_color: e.target.value })}
                          style={{ width: '50px', height: '35px', cursor: 'pointer' }}
                        />
                        <input
                          type="text"
                          value={promoModalForm.background_color}
                          onChange={(e) => setPromoModalForm({ ...promoModalForm, background_color: e.target.value })}
                          style={{ flex: 1 }}
                        />
                      </div>
                    </div>

                    <div className="form-group">
                      <label>Text Color</label>
                      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                        <input
                          type="color"
                          value={promoModalForm.text_color}
                          onChange={(e) => setPromoModalForm({ ...promoModalForm, text_color: e.target.value })}
                          style={{ width: '50px', height: '35px', cursor: 'pointer' }}
                        />
                        <input
                          type="text"
                          value={promoModalForm.text_color}
                          onChange={(e) => setPromoModalForm({ ...promoModalForm, text_color: e.target.value })}
                          style={{ flex: 1 }}
                        />
                      </div>
                    </div>

                    <div className="form-group">
                      <label>Button Color</label>
                      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                        <input
                          type="color"
                          value={promoModalForm.button_color}
                          onChange={(e) => setPromoModalForm({ ...promoModalForm, button_color: e.target.value })}
                          style={{ width: '50px', height: '35px', cursor: 'pointer' }}
                        />
                        <input
                          type="text"
                          value={promoModalForm.button_color}
                          onChange={(e) => setPromoModalForm({ ...promoModalForm, button_color: e.target.value })}
                          style={{ flex: 1 }}
                        />
                      </div>
                    </div>

                    <div className="form-group">
                      <label>Button Text Color</label>
                      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                        <input
                          type="color"
                          value={promoModalForm.button_text_color}
                          onChange={(e) => setPromoModalForm({ ...promoModalForm, button_text_color: e.target.value })}
                          style={{ width: '50px', height: '35px', cursor: 'pointer' }}
                        />
                        <input
                          type="text"
                          value={promoModalForm.button_text_color}
                          onChange={(e) => setPromoModalForm({ ...promoModalForm, button_text_color: e.target.value })}
                          style={{ flex: 1 }}
                        />
                      </div>
                    </div>
                  </div>
                )}

                <div className="form-row">
                  <div className="form-group">
                    <label>Status</label>
                    <select
                      value={promoModalForm.status}
                      onChange={(e) => setPromoModalForm({ ...promoModalForm, status: e.target.value })}
                    >
                      <option value="inactive">Inactive (Draft)</option>
                      <option value="active">Active (Live)</option>
                      <option value="scheduled">Scheduled</option>
                    </select>
                  </div>

                  {/* Max Subscribers - Info Modal only */}
                  {promoModalForm.type === 'info_modal' && (
                    <div className="form-group">
                      <label>Max Views</label>
                      <input
                        type="number"
                        min="1"
                        value={promoModalForm.max_subscribers}
                        onChange={(e) => setPromoModalForm({ ...promoModalForm, max_subscribers: e.target.value })}
                        placeholder="Leave empty for unlimited"
                      />
                      <small style={{ color: '#666', fontSize: '0.8rem' }}>
                        Auto-deactivates after this many views
                      </small>
                    </div>
                  )}
                </div>
              </div>

              {/* Previews - show only the relevant preview based on type */}
              <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                {/* Info Modal Preview - only for info_modal type */}
                {promoModalForm.type === 'info_modal' && (
                  <div className="form-group" style={{ flex: '1', minWidth: '250px' }}>
                    <label>Info Modal Preview</label>
                    <div
                      style={{
                        backgroundColor: promoModalForm.background_color,
                        color: promoModalForm.text_color,
                        padding: '1.5rem',
                        borderRadius: '8px',
                        textAlign: 'center',
                      }}
                    >
                      <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '1.25rem' }}>{promoModalForm.title || 'Title'}</h4>
                      <p style={{ margin: '0 0 1rem 0', opacity: 0.9, whiteSpace: 'pre-line', fontSize: '0.9rem' }}>{promoModalForm.message || 'Your message here...'}</p>
                      <button
                        style={{
                          backgroundColor: promoModalForm.button_color,
                          color: promoModalForm.button_text_color,
                          border: 'none',
                          padding: '0.5rem 1.5rem',
                          borderRadius: '4px',
                          cursor: 'pointer',
                        }}
                      >
                        {promoModalForm.button_text || 'Subscribe'}
                      </button>
                    </div>
                  </div>
                )}

                {/* Promotions Section Preview - only for promo_section type */}
                {promoModalForm.type === 'promo_section' && (
                  <div className="form-group" style={{ flex: '1', minWidth: '300px' }}>
                    <label>Promotions Section Preview</label>
                    <div
                      style={{
                        backgroundColor: '#343434',
                        color: '#d9ff00',
                        padding: '1.5rem',
                        borderRadius: '8px',
                        textAlign: 'center',
                      }}
                    >
                      <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '1.1rem' }}>{promoModalForm.title || 'Title'}</h4>
                      {promoModalForm.message && (
                        <p style={{ margin: '0 0 1rem 0', opacity: 0.9, whiteSpace: 'pre-line', fontSize: '0.85rem' }}>{promoModalForm.message}</p>
                      )}
                      {promoModalForm.promo_code && (
                        <div style={{
                          backgroundColor: '#fff',
                          color: '#343434',
                          padding: '0.75rem 1rem',
                          borderRadius: '6px',
                          marginTop: '0.5rem',
                          border: '2px dashed #d9ff00'
                        }}>
                          <div style={{ fontSize: '0.7rem', color: '#888' }}>USE CODE</div>
                          <div style={{ fontSize: '1.1rem', fontWeight: 'bold', letterSpacing: '1px' }}>{promoModalForm.promo_code}</div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowPromoModalForm(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={handleSavePromoModal}
                disabled={savingPromoModal || !promoModalForm.title || !promoModalForm.message}
              >
                {savingPromoModal ? 'Saving...' : (editingPromoModal ? 'Update' : 'Save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Promo Modal Confirmation */}
      {showDeletePromoModal && promoModalToDelete && (
        <div className="modal-overlay" onClick={() => setShowDeletePromoModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Delete Promo Modal</h3>
            <p>Are you sure you want to delete this promo modal?</p>
            <div className="modal-booking-info">
              <p><strong>Title:</strong> {promoModalToDelete.title}</p>
              <p><strong>Views:</strong> {promoModalToDelete.viewCount} | <strong>Clicks:</strong> {promoModalToDelete.clickCount}</p>
            </div>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowDeletePromoModal(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-danger"
                onClick={handleDeletePromoModal}
                disabled={deletingPromoModal}
              >
                {deletingPromoModal ? 'Deleting...' : 'Yes, Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default PromoModalsModals
