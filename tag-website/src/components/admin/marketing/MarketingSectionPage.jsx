import DatePicker from 'react-datepicker'

const MarketingSectionPage = ({
  REFERRALS_PAGE_SIZE_OPTIONS,
  activeTab,
  addManualRecipient,
  addRecipient,
  availablePromoCodes,
  campaignConfirm,
  campaignPreview,
  campaignToast,
  campaigns,
  closeCampaignModal,
  createCampaign,
  createPromotion,
  creatingCampaign,
  creatingPromotion,
  deleteCampaign,
  deletePromotion,
  deletingCampaignId,
  deletingPromotionId,
  editingCampaignId,
  editingPromotion,
  expandedPromotionId,
  expandedSubscriberId,
  expandedSubscriberMonths,
  expiryDate,
  expiryModalData,
  expiryTime,
  exportMarketingSourcesCSV,
  fetchCampaigns,
  fetchMarketingOtherDetails,
  fetchMarketingSources,
  fetchPromotionDetails,
  fetchReferralsDashboard,
  fetchSubscribers,
  filteredReferralCustomers,
  filteredReferralUsage,
  filteredSubscribers,
  formatDateTimeUK,
  formatDateUK,
  formatPence,
  generateCodesCount,
  generateCodesExpiryDate,
  generateCodesExpiryTime,
  generateCodesMaxUses,
  generateCodesPromotion,
  generateMoreCodes,
  generatingCodes,
  handleManualReferralInvite,
  handleReferralDashboardAction,
  hideTestEmails,
  loadingCampaigns,
  loadingMarketingOther,
  loadingMarketingSources,
  loadingPromotions,
  loadingReferrals,
  loadingSubscribers,
  manualRecipient,
  manualReferralInvite,
  manualReferralInviteMessage,
  marketingExportFromDate,
  marketingExportToDate,
  marketingOtherDetails,
  marketingOtherMonth,
  marketingSourcesData,
  marketingSubTab,
  newCampaign,
  newPromotion,
  openCampaignForEdit,
  openCustomerModal,
  openExpiryModal,
  openFounderEmailModal,
  openGenerateCodesModal,
  openSendPromoEmailModal,
  performDeleteCampaign,
  performSendCampaign,
  previewCampaign,
  promoEmailBody,
  promoEmailRecipients,
  promoEmailSubject,
  promoSuccessMessage,
  promotionDetails,
  promotionMessage,
  promotions,
  recipientSearchResults,
  recipientSearchTerm,
  referralCustomerEnd,
  referralCustomerStart,
  referralCustomerTotal,
  referralDashboardAction,
  referralUsageEnd,
  referralUsageStart,
  referralUsageTableRef,
  referralUsageTotal,
  referralsCustomerOffset,
  referralsCustomerPageSize,
  referralsCustomerSearch,
  referralsDashboard,
  referralsDashboardHasLoaded,
  referralsFilter,
  referralsUsageFilter,
  referralsUsageOffset,
  referralsUsagePageSize,
  referralsUsageSearch,
  refreshPromotions,
  removeRecipient,
  searchRecipients,
  searchingRecipients,
  selectedCodes,
  sendCampaign,
  sendPromo10Reminder,
  sendPromoEmailData,
  sendPromoEmails,
  sendPromoFreeReminder,
  sendingCampaign,
  sendingManualReferralInvite,
  sendingPromoEmails,
  onSelectAdminItem,
  setCampaignConfirm,
  setCampaignToast,
  setEditingPromotion,
  setExpandedPromotionId,
  setExpandedSubscriberId,
  setExpandedSubscriberMonths,
  setExpiryDate,
  setExpiryModalData,
  setExpiryTime,
  setGenerateCodesCount,
  setGenerateCodesExpiryDate,
  setGenerateCodesExpiryTime,
  setGenerateCodesMaxUses,
  setHideTestEmails,
  setManualRecipient,
  setManualReferralInvite,
  setMarketingExportFromDate,
  setMarketingExportToDate,
  setNewCampaign,
  setNewPromotion,
  setPromoEmailBody,
  setPromoEmailSubject,
  setPromotionMessage,
  setRecipientSearchTerm,
  setReferralsCustomerOffset,
  setReferralsCustomerPageSize,
  setReferralsCustomerSearch,
  setReferralsFilter,
  setReferralsUsageFilter,
  setReferralsUsageOffset,
  setReferralsUsagePageSize,
  setReferralsUsageSearch,
  setSearchTerm,
  setSelectedCodes,
  setShowCreateCampaign,
  setShowCreatePromotion,
  setShowExpiryModal,
  setShowGenerateCodesModal,
  setShowMarketingOtherModal,
  setShowSendPromoEmailModal,
  setSubscriberDateFrom,
  setSubscriberDateTo,
  setSubscriberSearchTerm,
  setSubscriberStatusFilter,
  showCreateCampaign,
  showCreatePromotion,
  showExpiryModal,
  showGenerateCodesModal,
  showMarketingOtherModal,
  showSendPromoEmailModal,
  subscriberDateFrom,
  subscriberDateTo,
  subscriberSearchTerm,
  subscriberStatusFilter,
  subscribers,
  toggleSharedOnSocials,
  toggleSharedPrivately,
  updatePromoCodeExpiry,
  updatePromotion,
  updatingExpiry,
}) => {
  if (activeTab !== 'marketing') {
    return null
  }

  return (
    <>
  <div className="admin-section">
    <h2>
      {marketingSubTab === 'subscribers' && 'Subscribers'}
      {marketingSubTab === 'promotions' && 'Promotions'}
      {marketingSubTab === 'campaigns' && 'Email Campaigns'}
      {marketingSubTab === 'referrals' && 'Referrals'}
      {marketingSubTab === 'sources' && 'Sources'}
    </h2>

    {/* Promotions Success/Error Message */}
    {promotionMessage && (
      <div className={`success-banner ${promotionMessage.startsWith('Error') ? 'error-banner' : ''}`}>
        {promotionMessage}
        <button onClick={() => setPromotionMessage('')} style={{ marginLeft: '10px', background: 'none', border: 'none', cursor: 'pointer' }}>&times;</button>
      </div>
    )}

    {/* Subscribers Sub-tab */}
    {marketingSubTab === 'subscribers' && (
      <>
    <div className="admin-section-header">
      <h2>Marketing Subscribers</h2>
      <div className="flights-header-actions">
        <button
          className="btn-secondary"
          onClick={fetchSubscribers}
          disabled={loadingSubscribers}
        >
          {loadingSubscribers ? 'Loading...' : '↻ Refresh'}
        </button>
        <button
          className="btn-primary"
          onClick={() => {
            // Generate CSV from filtered subscribers
            const csvRows = [['First Name', 'Last Name', 'Email', 'Date Subscribed', 'Status', '10% Code', 'Free Code', 'Founder Thank You Email']]
            filteredSubscribers.forEach(sub => {
              const dateSubscribed = sub.subscribed_at
                ? new Date(sub.subscribed_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London' })
                : ''
              let status = 'Pending'
              if (sub.unsubscribed) status = 'Unsubscribed'
              else if (sub.promo_10_used || sub.promo_free_used) status = 'Code Used'
              else if (sub.promo_10_sent || sub.promo_free_sent) status = 'Code Sent'
              const founderEmailStatus = sub.founder_email_sent ? 'Sent' : 'Not Sent'
              csvRows.push([
                sub.first_name || '',
                sub.last_name || '',
                sub.email || '',
                dateSubscribed,
                status,
                sub.promo_10_code || '',
                sub.promo_free_code || '',
                founderEmailStatus
              ])
            })
            const csvContent = csvRows.map(row => row.map(cell => `"${(cell || '').replace(/"/g, '""')}"`).join(',')).join('\n')
            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
            const url = URL.createObjectURL(blob)
            const link = document.createElement('a')
            link.setAttribute('href', url)
            // Build descriptive filename based on filters
            const formatDateForFilename = (date) => {
              const day = String(date.getDate()).padStart(2, '0')
              const month = String(date.getMonth() + 1).padStart(2, '0')
              const year = date.getFullYear()
              return `${day}-${month}-${year}`
            }
            let filename = 'subscribers'
            if (subscriberDateFrom && subscriberDateTo) {
              filename = `subscribers_${formatDateForFilename(subscriberDateFrom)}_to_${formatDateForFilename(subscriberDateTo)}`
            } else if (subscriberDateFrom) {
              filename = `subscribers_from_${formatDateForFilename(subscriberDateFrom)}`
            } else if (subscriberDateTo) {
              filename = `subscribers_to_${formatDateForFilename(subscriberDateTo)}`
            } else {
              filename = `subscribers_all_${formatDateForFilename(new Date())}`
            }
            link.setAttribute('download', `${filename}.csv`)
            link.click()
            URL.revokeObjectURL(url)
          }}
          disabled={loadingSubscribers}
        >
          ↓ Download CSV
        </button>
      </div>
    </div>

    {/* Success Message Banner */}
    {promoSuccessMessage && (
      <div className="success-banner">
        {promoSuccessMessage}
      </div>
    )}

    {/* Search and Filter Controls - matching Bookings style */}
    <div className="admin-filters">
      <div className="admin-search">
        <input
          type="text"
          placeholder="Search by name, email, or promo code..."
          value={subscriberSearchTerm}
          onChange={(e) => setSubscriberSearchTerm(e.target.value)}
          className="admin-search-input"
        />
        {subscriberSearchTerm && (
          <button
            className="admin-search-clear"
            onClick={() => setSubscriberSearchTerm('')}
          >
            &times;
          </button>
        )}
      </div>
      <div className="admin-filter-group">
        <label>Status:</label>
        <select
          value={subscriberStatusFilter}
          onChange={(e) => setSubscriberStatusFilter(e.target.value)}
          className="admin-filter-select"
        >
          <option value="all">All Statuses</option>
          <option value="pending">Pending</option>
          <option value="sent">Code Sent</option>
          <option value="used">Code Used</option>
          <option value="unsubscribed">Unsubscribed</option>
        </select>
      </div>
      <div className="flight-filter-group leads-date-picker">
        <label>From:</label>
        <DatePicker
          selected={subscriberDateFrom}
          onChange={(date) => setSubscriberDateFrom(date)}
          dateFormat="dd/MM/yyyy"
          placeholderText="DD/MM/YYYY"
          className="flight-date-input"
          isClearable
        />
      </div>
      <div className="flight-filter-group leads-date-picker">
        <label>To:</label>
        <DatePicker
          selected={subscriberDateTo}
          onChange={(date) => setSubscriberDateTo(date)}
          dateFormat="dd/MM/yyyy"
          placeholderText="DD/MM/YYYY"
          className="flight-date-input"
          isClearable
        />
      </div>
      <label className="admin-checkbox-label">
        <input
          type="checkbox"
          checked={hideTestEmails}
          onChange={(e) => setHideTestEmails(e.target.checked)}
        />
        Hide test emails
      </label>
      <div className="admin-filter-count">
        Showing {filteredSubscribers.length} of {subscribers.length} subscribers
      </div>
    </div>

    {loadingSubscribers ? (
      <div className="admin-loading-inline">
        <div className="spinner-small"></div>
        <span>Loading subscribers...</span>
      </div>
    ) : filteredSubscribers.length === 0 ? (
      <p className="admin-empty">
        {subscribers.length === 0 ? 'No subscribers found' : 'No subscribers match your search'}
      </p>
    ) : (() => {
      // Group by month
      const monthlyGroups = {}
      filteredSubscribers.forEach(subscriber => {
        const date = subscriber.subscribed_at ? new Date(subscriber.subscribed_at) : null
        if (date) {
          const monthKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
          if (!monthlyGroups[monthKey]) monthlyGroups[monthKey] = []
          monthlyGroups[monthKey].push(subscriber)
        }
      })

      const sortedMonths = Object.keys(monthlyGroups).sort().reverse()
      const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

      if (sortedMonths.length === 0) {
        return <p className="admin-no-data">No subscribers found</p>
      }

      return sortedMonths.map(monthKey => {
        const [year, month] = monthKey.split('-')
        const monthName = `${monthNames[parseInt(month, 10) - 1]} ${year}`
        const monthSubscribers = monthlyGroups[monthKey]
        const isExpanded = expandedSubscriberMonths[monthKey]

        return (
          <div key={monthKey} className="subscribers-month-container">
            <div
              className="subscribers-month-header"
              onClick={() => setExpandedSubscriberMonths(prev => ({
                ...prev,
                [monthKey]: !prev[monthKey]
              }))}
            >
              <span className="expand-icon">{isExpanded ? '▼' : '▶'}</span>
              <span className="month-name">{monthName}</span>
              <span className="month-total">{monthSubscribers.length} subscriber{monthSubscribers.length !== 1 ? 's' : ''}</span>
            </div>
            {isExpanded && (
              <div className="subscribers-month-content">
                {monthSubscribers.map((subscriber) => (
                  <div
                    key={subscriber.id}
                    className={`booking-card ${expandedSubscriberId === subscriber.id ? 'expanded' : ''} ${subscriber.unsubscribed ? 'unsubscribed' : ''}`}
                  >
                    {/* Collapsed Header Row */}
                    <div
                      className="booking-card-header subscriber-header"
                      onClick={() => setExpandedSubscriberId(expandedSubscriberId === subscriber.id ? null : subscriber.id)}
                    >
                      <div className="subscriber-info">
                        <span className="subscriber-name">{subscriber.first_name} {subscriber.last_name}</span>
                        <span className="subscriber-email">{subscriber.email}</span>
                      </div>
                    </div>

                    {/* Expanded Content */}
                    {expandedSubscriberId === subscriber.id && (
                      <div className="booking-card-body">
                        {/* Welcome Email Section */}
                        <div className="booking-section">
                          <h4>Welcome Email</h4>
                          <div className="booking-section-content">
                            <div className="booking-detail-row">
                              <div className="booking-detail">
                                <span className="detail-label">Subscribed</span>
                                <span className="detail-value">
                                  {formatDateUK(subscriber.subscribed_at)}
                                </span>
                              </div>
                              <div className="booking-detail">
                                <span className="detail-label">Status</span>
                                <span className="detail-value">
                                  <span className={`status-badge ${subscriber.welcome_email_sent ? 'sent' : 'pending'}`}>
                                    {subscriber.welcome_email_sent ? 'Sent' : 'Pending'}
                                  </span>
                                </span>
                              </div>
                              <div className="booking-detail">
                                <span className="detail-label">Sent At</span>
                                <span className="detail-value">
                                  {formatDateTimeUK(subscriber.welcome_email_sent_at)}
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>

                        {/* 10% OFF Promo Section */}
                        <div className="booking-section">
                          <div className="section-header-with-action">
                            <h4>10% Off Promo</h4>
                            <div style={{ display: 'flex', gap: '8px' }}>
                              {!subscriber.unsubscribed && !subscriber.promo_10_used && (
                                <button
                                  className={`action-btn promo-btn ${subscriber.promo_10_sent ? 'sent' : 'disabled'}`}
                                  onClick={(e) => { e.stopPropagation(); if (!subscriber.promo_10_sent) alert('This promo has ended.'); }}
                                  disabled={subscriber.promo_10_sent}
                                >
                                  {subscriber.promo_10_sent ? 'Sent ✓' : 'Send 10% Off'}
                                </button>
                              )}
                              {/* Send Reminder button - only show if promo sent, not used, and reminder not already sent */}
                              {subscriber.promo_10_sent && !subscriber.promo_10_used && !subscriber.unsubscribed && (
                                <button
                                  className={`action-btn promo-btn ${subscriber.promo_10_reminder_sent ? 'sent' : ''}`}
                                  onClick={(e) => { e.stopPropagation(); if (!subscriber.promo_10_reminder_sent) sendPromo10Reminder(subscriber); }}
                                  disabled={subscriber.promo_10_reminder_sent}
                                >
                                  {subscriber.promo_10_reminder_sent ? 'Reminder Sent ✓' : 'Send Reminder'}
                                </button>
                              )}
                            </div>
                          </div>
                          <div className="booking-section-content">
                            {subscriber.promo_10_code ? (
                            <>
                              <div className="booking-detail-row">
                                <div className="booking-detail">
                                  <span className="detail-label">Code</span>
                                  <span className="detail-value">
                                    <span className="promo-code-display">{subscriber.promo_10_code}</span>
                                  </span>
                                </div>
                                <div className="booking-detail">
                                  <span className="detail-label">Status</span>
                                  <span className="detail-value">
                                    <span className={`status-badge ${subscriber.promo_10_used ? 'used' : 'sent'}`}>
                                      {subscriber.promo_10_used ? 'Used' : 'Sent'}
                                    </span>
                                  </span>
                                </div>
                                <div className="booking-detail">
                                  <span className="detail-label">Sent At</span>
                                  <span className="detail-value">
                                    {formatDateTimeUK(subscriber.promo_10_sent_at)}
                                  </span>
                                </div>
                              </div>
                              {/* Reminder Row - aligned under Status and Sent At */}
                              {subscriber.promo_10_reminder_sent && (
                                <div className="booking-detail-row" style={{ marginTop: '8px' }}>
                                  <div className="booking-detail">
                                    {/* Empty spacer to align with Code column */}
                                  </div>
                                  <div className="booking-detail">
                                    <span className="detail-label">Reminder</span>
                                    <span className="detail-value">
                                      <span className="status-badge sent">Sent</span>
                                    </span>
                                  </div>
                                  <div className="booking-detail">
                                    <span className="detail-label">Reminder Sent At</span>
                                    <span className="detail-value">
                                      {formatDateTimeUK(subscriber.promo_10_reminder_sent_at)}
                                    </span>
                                  </div>
                                </div>
                              )}
                            </>
                            ) : (
                              <p className="section-empty">Not sent yet</p>
                            )}
                          </div>
                        </div>

                        {/* FREE Parking Promo Section */}
                        <div className="booking-section">
                          <div className="section-header-with-action">
                            <h4>FREE Parking Promo</h4>
                            {!subscriber.unsubscribed && !subscriber.promo_free_used && (
                              <button
                                className={`action-btn promo-btn free ${subscriber.promo_free_sent ? 'sent' : 'disabled'}`}
                                onClick={(e) => { e.stopPropagation(); if (!subscriber.promo_free_sent) alert('This promo has ended.'); }}
                                disabled={subscriber.promo_free_sent}
                              >
                                {subscriber.promo_free_sent ? 'Sent ✓' : 'Send FREE'}
                              </button>
                            )}
                            {/* Send Reminder button - only show if promo sent, not used, and reminder not already sent */}
                            {subscriber.promo_free_sent && !subscriber.promo_free_used && !subscriber.unsubscribed && (
                              <button
                                className={`action-btn promo-btn ${subscriber.promo_free_reminder_sent ? 'sent' : ''}`}
                                onClick={(e) => { e.stopPropagation(); if (!subscriber.promo_free_reminder_sent) sendPromoFreeReminder(subscriber); }}
                                disabled={subscriber.promo_free_reminder_sent}
                              >
                                {subscriber.promo_free_reminder_sent ? 'Reminder Sent ✓' : 'Send Reminder'}
                              </button>
                            )}
                          </div>
                          <div className="booking-section-content">
                            {subscriber.promo_free_code ? (
                            <>
                              <div className="booking-detail-row">
                                <div className="booking-detail">
                                  <span className="detail-label">Code</span>
                                  <span className="detail-value">
                                    <span className="promo-code-display">{subscriber.promo_free_code}</span>
                                  </span>
                                </div>
                                <div className="booking-detail">
                                  <span className="detail-label">Status</span>
                                  <span className="detail-value">
                                    <span className={`status-badge ${subscriber.promo_free_used ? 'used' : 'sent'}`}>
                                      {subscriber.promo_free_used ? 'Used' : 'Sent'}
                                    </span>
                                  </span>
                                </div>
                                <div className="booking-detail">
                                  <span className="detail-label">Sent At</span>
                                  <span className="detail-value">
                                    {formatDateTimeUK(subscriber.promo_free_sent_at)}
                                  </span>
                                </div>
                              </div>
                              {/* Reminder Row - aligned under Status and Sent At */}
                              {subscriber.promo_free_reminder_sent && (
                                <div className="booking-detail-row" style={{ marginTop: '8px' }}>
                                  <div className="booking-detail">
                                    {/* Empty spacer to align with Code column */}
                                  </div>
                                  <div className="booking-detail">
                                    <span className="detail-label">Reminder</span>
                                    <span className="detail-value">
                                      <span className="status-badge sent">Sent</span>
                                    </span>
                                  </div>
                                  <div className="booking-detail">
                                    <span className="detail-label">Reminder Sent At</span>
                                    <span className="detail-value">
                                      {formatDateTimeUK(subscriber.promo_free_reminder_sent_at)}
                                    </span>
                                  </div>
                                </div>
                              )}
                            </>
                            ) : (
                              <p className="section-empty">Not sent yet</p>
                            )}
                          </div>
                        </div>

                        {/* Founder Thank You Email Section */}
                        <div className="booking-section">
                          <div className="section-header-with-action">
                            <h4>Founder Thank You Email</h4>
                            {!subscriber.unsubscribed && !subscriber.founder_promo_used && (
                              <button
                                className={`action-btn promo-btn founder ${subscriber.founder_email_sent ? 'sent' : ''}`}
                                onClick={(e) => { e.stopPropagation(); if (!subscriber.founder_email_sent) openFounderEmailModal(subscriber); }}
                                disabled={subscriber.founder_email_sent}
                              >
                                {subscriber.founder_email_sent ? 'Sent ✓' : 'Send Founder Email'}
                              </button>
                            )}
                          </div>
                          <div className="booking-section-content">
                            {subscriber.founder_promo_code ? (
                              <div className="booking-detail-row">
                                <div className="booking-detail">
                                  <span className="detail-label">Code</span>
                                  <span className="detail-value">
                                    <span className="promo-code-display">{subscriber.founder_promo_code}</span>
                                  </span>
                                </div>
                                <div className="booking-detail">
                                  <span className="detail-label">Status</span>
                                  <span className="detail-value">
                                    <span className={`status-badge ${subscriber.founder_promo_used ? 'used' : 'sent'}`}>
                                      {subscriber.founder_promo_used ? 'Used' : 'Sent'}
                                    </span>
                                  </span>
                                </div>
                                <div className="booking-detail">
                                  <span className="detail-label">Sent At</span>
                                  <span className="detail-value">
                                    {formatDateTimeUK(subscriber.founder_email_sent_at)}
                                  </span>
                                </div>
                              </div>
                            ) : (
                              <p className="section-empty">Not sent yet</p>
                            )}
                          </div>
                        </div>

                        {subscriber.unsubscribed && (
                          <div className="subscriber-unsubscribed-notice">
                            Unsubscribed on {formatDateUK(subscriber.unsubscribed_at)}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })
    })()}
      </>
    )}

    {/* Promotions Sub-tab */}
    {marketingSubTab === 'promotions' && (
      <div className="admin-promotions-section">
        <div className="admin-section-header" style={{ justifyContent: 'flex-end' }}>
          <div className="flights-header-actions">
            <button
              className="btn-secondary"
              onClick={refreshPromotions}
              disabled={loadingPromotions}
            >
              {loadingPromotions ? 'Loading...' : '↻ Refresh'}
            </button>
            <button
              className="btn-primary"
              onClick={() => setShowCreatePromotion(true)}
            >
              + New Promotion
            </button>
          </div>
        </div>

        {/* Create Promotion Form */}
        {showCreatePromotion && (
          <div className="create-promotion-form" style={{ background: '#f5f5f5', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
            <h3>Create New Promotion</h3>
            <div className="form-row" style={{ display: 'flex', gap: '15px', flexWrap: 'wrap', marginBottom: '15px' }}>
              <div className="form-group" style={{ flex: '2', minWidth: '200px' }}>
                <label>Promotion Name</label>
                <input
                  type="text"
                  value={newPromotion.name}
                  onChange={(e) => setNewPromotion(prev => ({ ...prev, name: e.target.value }))}
                  placeholder="e.g., Spring Sale 2026"
                  className="admin-input"
                />
              </div>
              <div className="form-group" style={{ flex: '1', minWidth: '120px' }}>
                <label>Discount %</label>
                <select
                  value={newPromotion.discount_percent === 100 ? (newPromotion.discount_type === 'free_week' ? '100_week' : '100_full') : String(newPromotion.discount_percent)}
                  onChange={(e) => {
                    const v = e.target.value
                    if (v === '100_full') {
                      setNewPromotion(prev => ({ ...prev, discount_percent: 100, discount_type: 'free_100' }))
                    } else if (v === '100_week') {
                      setNewPromotion(prev => ({ ...prev, discount_percent: 100, discount_type: 'free_week' }))
                    } else {
                      setNewPromotion(prev => ({ ...prev, discount_percent: parseInt(v), discount_type: null }))
                    }
                  }}
                  className="admin-select"
                >
                  <option value="10">10%</option>
                  <option value="15">15%</option>
                  <option value="20">20%</option>
                  <option value="25">25%</option>
                  <option value="50">50%</option>
                  <option value="100_full">100% (Free)</option>
                  <option value="100_week">1 Week Free</option>
                </select>
              </div>
              {!newPromotion.custom_code && (
                <div className="form-group" style={{ flex: '1', minWidth: '120px' }}>
                  <label>Number of Codes</label>
                  <input
                    type="number"
                    value={newPromotion.total_codes}
                    onChange={(e) => setNewPromotion(prev => ({ ...prev, total_codes: parseInt(e.target.value) || 1 }))}
                    min="1"
                    max="1000"
                    className="admin-input"
                  />
                </div>
              )}
            </div>
            <div className="form-row" style={{ display: 'flex', gap: '15px', flexWrap: 'wrap', marginBottom: '15px' }}>
              <div className="form-group" style={{ flex: '1', minWidth: '200px' }}>
                <label>Custom Code (e.g., SUMMER10)</label>
                <input
                  type="text"
                  value={newPromotion.custom_code}
                  onChange={(e) => setNewPromotion(prev => ({ ...prev, custom_code: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 20), total_codes: e.target.value ? 1 : prev.total_codes }))}
                  placeholder="Leave empty for auto-generated codes"
                  className="admin-input"
                  maxLength="20"
                  disabled={newPromotion.total_codes > 1 && !newPromotion.custom_code}
                />
                <small style={{ color: '#666', fontSize: '12px' }}>
                  {newPromotion.custom_code ? `Code will be: ${newPromotion.custom_code}` : 'Or use Code Prefix below for auto-generated codes'}
                </small>
              </div>
            </div>
            {!newPromotion.custom_code && (
              <div className="form-row" style={{ display: 'flex', gap: '15px', flexWrap: 'wrap', marginBottom: '15px' }}>
                <div className="form-group" style={{ flex: '1', minWidth: '200px' }}>
                  <label>Code Prefix (optional)</label>
                  <input
                    type="text"
                    value={newPromotion.code_prefix}
                    onChange={(e) => setNewPromotion(prev => ({ ...prev, code_prefix: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 10) }))}
                    placeholder="e.g., SPRING"
                    className="admin-input"
                    maxLength="10"
                  />
                  <small style={{ color: '#666', fontSize: '12px' }}>
                    Codes will be: {newPromotion.code_prefix || 'TAG'}-XXXX-XXXX
                  </small>
                </div>
              </div>
            )}
            <div className="form-row" style={{ display: 'flex', gap: '15px', flexWrap: 'wrap', marginBottom: '15px', padding: '15px', background: '#f8f9fa', borderRadius: '8px', border: '1px solid #e9ecef' }}>
              <div style={{ width: '100%', marginBottom: '5px' }}>
                <label style={{ fontWeight: '600', color: '#495057' }}>⏰ Code Expiry (optional)</label>
                <small style={{ display: 'block', color: '#666', fontSize: '12px' }}>Set an expiry for all generated codes - great for flash sales!</small>
              </div>
              <div className="form-group" style={{ flex: '1', minWidth: '140px' }}>
                <label>Expiry Date</label>
                <input
                  type="text"
                  value={newPromotion.expiry_date}
                  onChange={(e) => setNewPromotion(prev => ({ ...prev, expiry_date: e.target.value }))}
                  placeholder="DD/MM/YYYY"
                  className="admin-input"
                />
              </div>
              <div className="form-group" style={{ flex: '1', minWidth: '140px' }}>
                <label>Expiry Time (UK)</label>
                <input
                  type="text"
                  value={newPromotion.expiry_time}
                  onChange={(e) => setNewPromotion(prev => ({ ...prev, expiry_time: e.target.value }))}
                  placeholder="HH:MM (24hr)"
                  className="admin-input"
                />
              </div>
            </div>
            <div className="form-row" style={{ display: 'flex', gap: '15px', flexWrap: 'wrap', marginBottom: '15px', padding: '15px', background: newPromotion.max_uses === '0' ? '#e8f5e9' : '#f8f9fa', borderRadius: '8px', border: newPromotion.max_uses === '0' ? '1px solid #c8e6c9' : '1px solid #e9ecef' }}>
              <div style={{ width: '100%' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', fontWeight: '600', color: newPromotion.max_uses === '0' ? '#2e7d32' : '#495057' }}>
                  <input
                    type="checkbox"
                    checked={newPromotion.max_uses === '0'}
                    onChange={(e) => setNewPromotion(prev => ({ ...prev, max_uses: e.target.checked ? '0' : '' }))}
                    style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                  />
                  🔄 Unlimited Uses (multi-use code)
                </label>
                <small style={{ display: 'block', color: '#666', fontSize: '12px', marginTop: '5px', marginLeft: '28px' }}>
                  {newPromotion.max_uses === '0'
                    ? 'This code can be used unlimited times by multiple customers'
                    : 'Default: single-use code (one customer only)'}
                </small>
              </div>
            </div>
            <div className="form-group" style={{ marginBottom: '15px' }}>
              <label>Description (optional)</label>
              <textarea
                value={newPromotion.description}
                onChange={(e) => setNewPromotion(prev => ({ ...prev, description: e.target.value }))}
                placeholder="Internal notes about this promotion"
                className="admin-input"
                rows="2"
                style={{ width: '100%', resize: 'vertical' }}
              />
            </div>
            <div className="form-actions" style={{ display: 'flex', gap: '10px' }}>
              <button
                className="btn-secondary"
                onClick={() => { setShowCreatePromotion(false); setNewPromotion({ name: '', description: '', discount_percent: 10, discount_type: null, total_codes: 10, code_prefix: '', custom_code: '', expiry_date: '', expiry_time: '', max_uses: '' }); }}
              >
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={createPromotion}
                disabled={creatingPromotion || !newPromotion.name || !newPromotion.total_codes}
              >
                {creatingPromotion ? 'Creating...' : 'Create Promotion'}
              </button>
            </div>
          </div>
        )}

        {/* Promotions List */}
        {loadingPromotions ? (
          <div className="loading-spinner">
            <span>Loading promotions...</span>
          </div>
        ) : promotions.length === 0 ? (
          <div className="no-data">
            <p>No promotions yet. Create your first promotion to generate promo codes.</p>
          </div>
        ) : (
          <div className="promotions-list">
            {promotions.map(promo => (
              <div key={promo.id} className="promotion-card" style={{ border: '1px solid #ddd', borderRadius: '8px', marginBottom: '15px', overflow: 'hidden' }}>
                <div
                  className="promotion-header"
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '15px 20px',
                    background: '#f9f9f9',
                    cursor: 'pointer',
                  }}
                  onClick={() => {
                    if (expandedPromotionId === promo.id) {
                      setExpandedPromotionId(null)
                    } else {
                      setExpandedPromotionId(promo.id)
                      if (!promotionDetails[promo.id]) {
                        fetchPromotionDetails(promo.id)
                      }
                    }
                  }}
                >
                  <div className="promotion-info">
                    {editingPromotion?.id === promo.id ? (
                      <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '5px' }} onClick={(e) => e.stopPropagation()}>
                        <input
                          type="text"
                          value={editingPromotion.name}
                          onChange={(e) => setEditingPromotion({ ...editingPromotion, name: e.target.value })}
                          style={{ padding: '5px 10px', fontSize: '16px', fontWeight: 'bold', border: '1px solid #ccc', borderRadius: '4px' }}
                          autoFocus
                        />
                        <button
                          className="btn-primary"
                          onClick={() => updatePromotion(promo.id, editingPromotion.name)}
                          style={{ fontSize: '12px', padding: '5px 10px' }}
                        >
                          Save
                        </button>
                        <button
                          className="btn-secondary"
                          onClick={() => setEditingPromotion(null)}
                          style={{ fontSize: '12px', padding: '5px 10px' }}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <h3 style={{ margin: 0, marginBottom: '5px' }}>{promo.name}</h3>
                    )}
                    <div style={{ display: 'flex', gap: '15px', fontSize: '14px', color: '#666' }}>
                      <span><strong>{promo.discount_percent}%</strong> off</span>
                      <span>|</span>
                      <span>{promo.total_codes} codes</span>
                      <span>|</span>
                      <span>{promo.codes_sent} sent</span>
                      <span>|</span>
                      <span>{promo.codes_used} used</span>
                      <span>|</span>
                      <span style={{ color: promo.codes_available > 0 ? '#28a745' : '#dc3545' }}>
                        {promo.codes_available} available
                      </span>
                    </div>
                  </div>
                  <div className="promotion-actions" style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                    <button
                      className="btn-secondary"
                      onClick={(e) => { e.stopPropagation(); setEditingPromotion({ id: promo.id, name: promo.name }); }}
                      style={{ fontSize: '12px', padding: '6px 12px' }}
                      title="Edit promotion name"
                    >
                      ✏️
                    </button>
                    <button
                      className="btn-secondary"
                      onClick={(e) => { e.stopPropagation(); deletePromotion(promo.id); }}
                      disabled={promo.codes_sent > 0 || promo.codes_used > 0 || promo.codes_shared_on_socials > 0 || promo.codes_shared_privately > 0 || deletingPromotionId === promo.id}
                      style={{ fontSize: '12px', padding: '6px 12px', opacity: (promo.codes_sent > 0 || promo.codes_used > 0 || promo.codes_shared_on_socials > 0 || promo.codes_shared_privately > 0) ? 0.5 : 1 }}
                      title={
                        promo.codes_sent > 0 ? 'Cannot delete - emails have been sent' :
                        promo.codes_used > 0 ? 'Cannot delete - codes have been used' :
                        promo.codes_shared_on_socials > 0 ? 'Cannot delete - codes have been shared on socials' :
                        promo.codes_shared_privately > 0 ? 'Cannot delete - codes have been shared privately' :
                        'Delete promotion'
                      }
                    >
                      {deletingPromotionId === promo.id ? '...' : '🗑️'}
                    </button>
                    <button
                      className="btn-primary"
                      onClick={(e) => { e.stopPropagation(); openSendPromoEmailModal(promo); }}
                      disabled={promo.codes_available === 0}
                      style={{ fontSize: '14px', padding: '8px 15px' }}
                    >
                      📧 Send Codes
                    </button>
                    {promo.codes_available === 0 && (
                      <button
                        className="btn-secondary"
                        onClick={(e) => { e.stopPropagation(); openGenerateCodesModal(promo); }}
                        style={{ fontSize: '14px', padding: '8px 15px' }}
                        title="Generate more promo codes for this promotion"
                      >
                        + Generate Codes
                      </button>
                    )}
                    <span style={{ fontSize: '20px', color: '#666' }}>
                      {expandedPromotionId === promo.id ? '▼' : '▶'}
                    </span>
                  </div>
                </div>

                {/* Expanded Details */}
                {expandedPromotionId === promo.id && (
                  <div className="promotion-details" style={{ padding: '20px', borderTop: '1px solid #eee' }}>
                    {promo.description && (
                      <p style={{ color: '#666', marginBottom: '15px', fontStyle: 'italic' }}>{promo.description}</p>
                    )}
                    <p style={{ fontSize: '12px', color: '#999', marginBottom: '15px' }}>
                      Created: {new Date(promo.created_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London' })}
                    </p>

                    {promotionDetails[promo.id]?.loading ? (
                      <div className="loading-spinner"><span>Loading codes...</span></div>
                    ) : promotionDetails[promo.id]?.codes?.length > 0 ? (
                      <div className="promo-codes-table" style={{ overflowX: 'auto' }}>
                        {/* Bulk Actions Bar */}
                        {selectedCodes[promo.id]?.size > 0 && (
                          <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '15px',
                            padding: '10px 15px',
                            marginBottom: '10px',
                            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                            borderRadius: '8px',
                            color: 'white'
                          }}>
                            <span style={{ fontWeight: '600' }}>
                              {selectedCodes[promo.id].size} code{selectedCodes[promo.id].size > 1 ? 's' : ''} selected
                            </span>
                            <button
                              onClick={() => {
                                setExpiryModalData({
                                  promotionId: promo.id,
                                  codeIds: Array.from(selectedCodes[promo.id]),
                                  isBulk: true
                                })
                                setExpiryDate('')
                                setExpiryTime('')
                                setShowExpiryModal(true)
                              }}
                              style={{
                                background: 'white',
                                color: '#667eea',
                                border: 'none',
                                padding: '6px 12px',
                                borderRadius: '6px',
                                fontWeight: '600',
                                fontSize: '12px',
                                cursor: 'pointer'
                              }}
                            >
                              ⏰ Set Expiry
                            </button>
                            <button
                              onClick={() => setSelectedCodes(prev => ({ ...prev, [promo.id]: new Set() }))}
                              style={{
                                background: 'rgba(255,255,255,0.2)',
                                color: 'white',
                                border: 'none',
                                padding: '6px 12px',
                                borderRadius: '6px',
                                fontWeight: '600',
                                fontSize: '12px',
                                cursor: 'pointer'
                              }}
                            >
                              Clear Selection
                            </button>
                          </div>
                        )}
                        {/* Copy Available Codes Button */}
                        <div style={{ marginBottom: '10px', display: 'flex', gap: '10px' }}>
                          <button
                            onClick={() => {
                              const codes = promotionDetails[promo.id]?.codes || []
                              const availableCodes = codes.filter(c => !c.is_used && !c.email_sent && !c.shared_on_socials && !c.shared_privately)
                              const codeStrings = availableCodes.map(c => c.code).join('\n')
                              navigator.clipboard.writeText(codeStrings).then(() => {
                                setPromotionMessage(`Copied ${availableCodes.length} available codes to clipboard`)
                              }).catch(() => {
                                setPromotionMessage('Failed to copy to clipboard')
                              })
                            }}
                            disabled={!(promotionDetails[promo.id]?.codes || []).some(c => !c.is_used && !c.email_sent && !c.shared_on_socials && !c.shared_privately)}
                            style={{
                              background: '#e9ecef',
                              color: '#495057',
                              border: 'none',
                              padding: '6px 12px',
                              borderRadius: '6px',
                              fontWeight: '500',
                              fontSize: '12px',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '6px',
                              opacity: (promotionDetails[promo.id]?.codes || []).some(c => !c.is_used && !c.email_sent && !c.shared_on_socials && !c.shared_privately) ? 1 : 0.5
                            }}
                          >
                            📋 Copy Available Codes ({(promotionDetails[promo.id]?.codes || []).filter(c => !c.is_used && !c.email_sent && !c.shared_on_socials && !c.shared_privately).length})
                          </button>
                        </div>
                        <table className="admin-table" style={{ width: '100%', fontSize: '13px' }}>
                          <thead>
                            <tr>
                              <th style={{ width: '40px', textAlign: 'center' }}>
                                <input
                                  type="checkbox"
                                  checked={promotionDetails[promo.id]?.codes?.length > 0 &&
                                    promotionDetails[promo.id].codes.every(c => selectedCodes[promo.id]?.has(c.id))}
                                  onChange={(e) => {
                                    const codes = promotionDetails[promo.id]?.codes || []
                                    if (e.target.checked) {
                                      setSelectedCodes(prev => ({
                                        ...prev,
                                        [promo.id]: new Set(codes.map(c => c.id))
                                      }))
                                    } else {
                                      setSelectedCodes(prev => ({
                                        ...prev,
                                        [promo.id]: new Set()
                                      }))
                                    }
                                  }}
                                  title="Select all codes"
                                  style={{ cursor: 'pointer' }}
                                />
                              </th>
                              <th>Code</th>
                              <th>Recipient</th>
                              <th>Shared on Socials</th>
                              <th>Shared Privately</th>
                              <th>Expiry</th>
                              <th>Status</th>
                              <th>Booking</th>
                            </tr>
                          </thead>
                          <tbody>
                            {promotionDetails[promo.id].codes.map(code => (
                              <tr key={code.id} style={{ background: selectedCodes[promo.id]?.has(code.id) ? '#f0f7ff' : 'transparent' }}>
                                <td style={{ textAlign: 'center' }}>
                                  <input
                                    type="checkbox"
                                    checked={selectedCodes[promo.id]?.has(code.id) || false}
                                    onChange={(e) => {
                                      setSelectedCodes(prev => {
                                        const currentSet = prev[promo.id] ? new Set(prev[promo.id]) : new Set()
                                        if (e.target.checked) {
                                          currentSet.add(code.id)
                                        } else {
                                          currentSet.delete(code.id)
                                        }
                                        return { ...prev, [promo.id]: currentSet }
                                      })
                                    }}
                                    style={{ cursor: 'pointer' }}
                                  />
                                </td>
                                <td><code style={{ background: '#f0f0f0', padding: '2px 6px', borderRadius: '3px' }}>{code.code}</code></td>
                                <td>
                                  {/* Recipient: show email if sent, Social Media badge if shared on socials, Private badge if shared privately, otherwise blank */}
                                  {code.recipient_email ? (
                                    <span>
                                      {code.recipient_first_name} {code.recipient_last_name || ''}<br />
                                      <small style={{ color: '#666' }}>{code.recipient_email}</small>
                                    </span>
                                  ) : code.shared_on_socials ? (
                                    <span style={{
                                      display: 'inline-flex',
                                      alignItems: 'center',
                                      gap: '6px',
                                      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                                      color: 'white',
                                      padding: '4px 10px',
                                      borderRadius: '12px',
                                      fontSize: '11px',
                                      fontWeight: '600'
                                    }}>
                                      <span style={{ fontSize: '13px' }}>📱</span> Social Media
                                    </span>
                                  ) : code.shared_privately ? (
                                    <span style={{
                                      display: 'inline-flex',
                                      alignItems: 'center',
                                      gap: '6px',
                                      background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
                                      color: 'white',
                                      padding: '4px 10px',
                                      borderRadius: '12px',
                                      fontSize: '11px',
                                      fontWeight: '600'
                                    }}>
                                      <span style={{ fontSize: '13px' }}>💬</span> Private Share
                                    </span>
                                  ) : (
                                    <span style={{ color: '#999' }}>-</span>
                                  )}
                                </td>
                                <td>
                                  {/* Shared on Socials: toggle button for social codes, dash for emailed/privately shared codes */}
                                  {code.recipient_email ? (
                                    <span style={{ color: '#999' }}>-</span>
                                  ) : code.shared_privately && !code.shared_on_socials ? (
                                    /* Cannot share on socials if already shared privately (mutually exclusive) */
                                    <span style={{ color: '#999' }}>-</span>
                                  ) : code.is_used && !code.shared_on_socials ? (
                                    /* Used codes cannot be marked as shared (but can show shared status if already was) */
                                    <span style={{ color: '#999' }}>-</span>
                                  ) : (
                                    <button
                                      onClick={() => toggleSharedOnSocials(promo.id, code.id)}
                                      disabled={code.is_used && !code.shared_on_socials}
                                      style={{
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        gap: '6px',
                                        padding: '4px 10px',
                                        borderRadius: '12px',
                                        fontSize: '11px',
                                        fontWeight: '600',
                                        border: 'none',
                                        cursor: code.is_used && !code.shared_on_socials ? 'not-allowed' : 'pointer',
                                        background: code.shared_on_socials
                                          ? 'linear-gradient(135deg, #28a745 0%, #20c997 100%)'
                                          : '#e9ecef',
                                        color: code.shared_on_socials ? 'white' : '#666',
                                        opacity: code.is_used && !code.shared_on_socials ? 0.5 : 1,
                                        transition: 'all 0.2s ease'
                                      }}
                                      title={code.shared_on_socials
                                        ? `Shared on ${new Date(code.shared_on_socials_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London' })}`
                                        : code.is_used ? 'Cannot mark used code as shared' : 'Click to mark as shared on socials'
                                      }
                                    >
                                      {code.shared_on_socials ? '✓ Shared' : 'Mark Shared'}
                                    </button>
                                  )}
                                </td>
                                <td>
                                  {/* Shared Privately: toggle button for private sharing, dash for emailed/socially shared codes */}
                                  {code.recipient_email ? (
                                    <span style={{ color: '#999' }}>-</span>
                                  ) : code.shared_on_socials && !code.shared_privately ? (
                                    /* Cannot share privately if already shared on socials (mutually exclusive) */
                                    <span style={{ color: '#999' }}>-</span>
                                  ) : code.is_used && !code.shared_privately ? (
                                    /* Used codes cannot be marked as shared (but can show shared status if already was) */
                                    <span style={{ color: '#999' }}>-</span>
                                  ) : (
                                    <button
                                      onClick={() => toggleSharedPrivately(promo.id, code.id)}
                                      disabled={code.is_used && !code.shared_privately}
                                      style={{
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        gap: '6px',
                                        padding: '4px 10px',
                                        borderRadius: '12px',
                                        fontSize: '11px',
                                        fontWeight: '600',
                                        border: 'none',
                                        cursor: code.is_used && !code.shared_privately ? 'not-allowed' : 'pointer',
                                        background: code.shared_privately
                                          ? 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)'
                                          : '#e9ecef',
                                        color: code.shared_privately ? 'white' : '#666',
                                        opacity: code.is_used && !code.shared_privately ? 0.5 : 1,
                                        transition: 'all 0.2s ease'
                                      }}
                                      title={code.shared_privately
                                        ? `Shared on ${new Date(code.shared_privately_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London' })}`
                                        : code.is_used ? 'Cannot mark used code as shared' : 'Click to mark as shared privately'
                                      }
                                    >
                                      {code.shared_privately ? '✓ Shared' : 'Mark Shared'}
                                    </button>
                                  )}
                                </td>
                                <td>
                                  {/* Expiry: clickable to set/edit, shows status */}
                                  <button
                                    onClick={() => openExpiryModal(promo.id, code)}
                                    style={{
                                      display: 'inline-flex',
                                      alignItems: 'center',
                                      gap: '6px',
                                      padding: '4px 10px',
                                      borderRadius: '12px',
                                      fontSize: '11px',
                                      fontWeight: '600',
                                      border: 'none',
                                      cursor: 'pointer',
                                      background: code.is_expired
                                        ? 'linear-gradient(135deg, #dc3545 0%, #c82333 100%)'
                                        : code.expires_at
                                          ? 'linear-gradient(135deg, #ffc107 0%, #e0a800 100%)'
                                          : '#e9ecef',
                                      color: code.is_expired || code.expires_at ? 'white' : '#666',
                                      transition: 'all 0.2s ease'
                                    }}
                                    title={code.expires_at
                                      ? `Expires: ${new Date(code.expires_at).toLocaleString('en-GB', { timeZone: 'Europe/London', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}`
                                      : 'Click to set expiry'
                                    }
                                  >
                                    {code.is_expired ? (
                                      <>⏰ Expired</>
                                    ) : code.expires_at ? (
                                      <>⏰ {new Date(code.expires_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London', day: '2-digit', month: '2-digit' })} {new Date(code.expires_at).toLocaleTimeString('en-GB', { timeZone: 'Europe/London', hour: '2-digit', minute: '2-digit' })}</>
                                    ) : (
                                      <>Set Expiry</>
                                    )}
                                  </button>
                                </td>
                                <td>
                                  <span className={`status-badge ${code.is_used ? 'used' : code.is_expired ? 'expired' : (code.email_sent || code.shared_on_socials || code.shared_privately) ? 'sent' : 'pending'}`}>
                                    {code.is_multi_use ? (
                                      // Multi-use code - show usage count
                                      code.max_uses === 0 ? (
                                        // Unlimited uses
                                        <span>∞ {code.use_count} {code.use_count === 1 ? 'use' : 'uses'}</span>
                                      ) : (
                                        // Limited uses
                                        <span>{code.use_count}/{code.max_uses} uses</span>
                                      )
                                    ) : (
                                      // Single-use code
                                      code.is_used ? 'Used' : code.is_expired ? 'Expired' : (code.email_sent || code.shared_on_socials || code.shared_privately) ? 'Shared' : 'Available'
                                    )}
                                  </span>
                                </td>
                                <td>
                                  {code.booking_references && code.booking_references.length > 0 ? (
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                                      {code.booking_references.map((ref, idx) => (
                                        <code key={idx} style={{ background: '#f0f0f0', padding: '2px 6px', borderRadius: '3px', fontSize: '0.85em' }}>{ref}</code>
                                      ))}
                                    </div>
                                  ) : code.booking_reference ? (
                                    <code style={{ background: '#f0f0f0', padding: '2px 6px', borderRadius: '3px' }}>{code.booking_reference}</code>
                                  ) : (
                                    <span style={{ color: '#999' }}>-</span>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p style={{ color: '#666' }}>No codes to display.</p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    )}

    {/* Email Campaigns Sub-tab */}
    {marketingSubTab === 'campaigns' && (
      <div className="email-campaigns-section">
        <div className="admin-section-header" style={{ justifyContent: 'flex-end' }}>
          <div className="flights-header-actions">
            <button
              className="btn-secondary"
              onClick={fetchCampaigns}
              disabled={loadingCampaigns}
            >
              {loadingCampaigns ? 'Loading...' : '↻ Refresh'}
            </button>
            <button
              className="btn-primary"
              onClick={() => setShowCreateCampaign(true)}
            >
              + New Campaign
            </button>
          </div>
        </div>

        {/* Campaign List */}
        {loadingCampaigns ? (
          <div className="loading-spinner">Loading campaigns...</div>
        ) : campaigns.length === 0 ? (
          <div className="no-data-message">
            <p>No email campaigns yet. Create your first campaign to send marketing emails to subscribers.</p>
          </div>
        ) : (
          <table className="admin-table">
            <thead>
              <tr>
                <th>Subject</th>
                <th>Status</th>
                <th>Recipients</th>
                <th>Sent</th>
                <th>Failed</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.map(campaign => (
                <tr key={campaign.id}>
                  <td>
                    <strong>{campaign.subject}</strong>
                    {campaign.promo_code && (
                      <span className="promo-badge" style={{ marginLeft: '8px', background: '#CCFF00', color: '#1A1A1A', padding: '2px 6px', borderRadius: '4px', fontSize: '12px' }}>
                        {campaign.promo_code}
                      </span>
                    )}
                  </td>
                  <td>
                    <span className={`status-badge status-${campaign.status}`}>
                      {campaign.status}
                    </span>
                  </td>
                  <td>{campaign.total_recipients}</td>
                  <td>{campaign.sent_count}</td>
                  <td>{campaign.failed_count}</td>
                  <td>{campaign.created_at ? new Date(campaign.created_at).toLocaleDateString('en-GB') : '-'}</td>
                  <td>
                    {campaign.status === 'draft' && (
                      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                        <button
                          onClick={() => openCampaignForEdit(campaign.id)}
                          style={{ padding: '6px 14px', fontSize: '0.8rem', fontWeight: '600', borderRadius: '20px', background: '#f0f0f0', color: '#333', border: 'none', cursor: 'pointer' }}
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => deleteCampaign(campaign.id)}
                          disabled={deletingCampaignId === campaign.id}
                          style={{ padding: '6px 14px', fontSize: '0.8rem', fontWeight: '600', borderRadius: '20px', background: '#f0f0f0', color: '#c53030', border: 'none', cursor: 'pointer', opacity: deletingCampaignId === campaign.id ? 0.6 : 1 }}
                        >
                          {deletingCampaignId === campaign.id ? 'Deleting...' : 'Delete'}
                        </button>
                        <button
                          onClick={() => sendCampaign(campaign.id)}
                          disabled={sendingCampaign}
                          style={{ padding: '6px 14px', fontSize: '0.8rem', fontWeight: '600', borderRadius: '20px', background: '#f7b32b', color: '#1a1a2e', border: 'none', cursor: 'pointer', opacity: sendingCampaign ? 0.6 : 1 }}
                        >
                          {sendingCampaign ? 'Sending...' : 'Send'}
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Create Campaign Modal */}
        {showCreateCampaign && (
          <div className="modal-overlay" onClick={closeCampaignModal}>
            <div className="modal-content" style={{ maxWidth: '1200px', width: '95%' }} onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <h3>{editingCampaignId ? 'Edit Email Campaign' : 'Create Email Campaign'}</h3>
                <button className="modal-close" onClick={closeCampaignModal}>×</button>
              </div>
              <div className="modal-body">
                {/* Campaign Details Section */}
                <div style={{ background: '#f9f9f9', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
                  <h4 style={{ margin: '0 0 4px 0', fontSize: '16px', fontWeight: '600' }}>Campaign Details</h4>
                  <div style={{ height: '3px', background: '#D4AF37', width: '120px', marginBottom: '20px' }}></div>

                  <div className="form-group">
                    <label>Subject Line *</label>
                    <input
                      type="text"
                      value={newCampaign.subject}
                      onChange={(e) => setNewCampaign({ ...newCampaign, subject: e.target.value })}
                      placeholder="e.g., Your exclusive 15% off code inside"
                      style={{ width: '100%' }}
                    />
                    <small style={{ color: '#666' }}>
                      Short and specific works best — this is what subscribers see in their inbox.
                    </small>
                  </div>

                  <div className="form-group">
                    <label>Message *</label>
                    <textarea
                      rows={8}
                      value={newCampaign.message}
                      onChange={(e) => setNewCampaign({ ...newCampaign, message: e.target.value })}
                      placeholder={`Write the body of the email — no need for a greeting or sign-off.\n\nThe template automatically adds:\n  • "Hi [first name]," at the top\n  • "Best, [founder name]" at the bottom\n\nExample:\nWe're running a spring offer this month — 15% off any booking over 5 days. Use the code below at checkout. It's our way of saying thanks for booking with us.`}
                      style={{ width: '100%' }}
                    />
                    <small style={{ color: '#666' }}>
                      Tip: keep it short, warm, and conversational. Preview before sending.
                    </small>
                  </div>

                  <div className="form-group">
                    <label>Promo Code (optional)</label>
                    <select
                      value={newCampaign.promo_code_id || ''}
                      onChange={(e) => setNewCampaign({ ...newCampaign, promo_code_id: e.target.value ? parseInt(e.target.value) : null })}
                      style={{ width: '100%' }}
                    >
                      <option value="">No promo code</option>
                      {availablePromoCodes.map(code => (
                        <option key={code.id} value={code.id}>
                          {code.code} ({code.discount_percent}% off, {code.use_count}/{code.max_uses === 0 ? '∞' : code.max_uses} used)
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Recipients Section */}
                <div style={{ background: '#f9f9f9', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
                  <h4 style={{ margin: '0 0 4px 0', fontSize: '16px', fontWeight: '600' }}>Recipients</h4>
                  <div style={{ height: '3px', background: '#D4AF37', width: '80px', marginBottom: '20px' }}></div>

                  <div style={{ display: 'flex', gap: '10px', marginBottom: '15px', flexWrap: 'wrap', alignItems: 'center' }}>
                    <input
                      type="text"
                      placeholder="Search subscribers..."
                      value={newCampaign.searchFilter || ''}
                      onChange={(e) => setNewCampaign({ ...newCampaign, searchFilter: e.target.value })}
                      style={{ flex: '1', minWidth: '200px', padding: '8px 14px', borderRadius: '20px', border: '1px solid #ddd' }}
                    />
                    <button
                      type="button"
                      onClick={() => {
                        const allIds = subscribers.filter(s => !s.unsubscribed).map(s => s.id)
                        setNewCampaign({ ...newCampaign, subscriber_ids: allIds })
                      }}
                      style={{ padding: '8px 16px', fontSize: '0.8rem', fontWeight: '600', borderRadius: '20px', background: '#f0f0f0', color: '#333', border: 'none', cursor: 'pointer', flexShrink: 0 }}
                    >
                      Select All ({subscribers.filter(s => !s.unsubscribed).length})
                    </button>
                    <button
                      type="button"
                      onClick={() => setNewCampaign({ ...newCampaign, subscriber_ids: [] })}
                      style={{ padding: '8px 16px', fontSize: '0.8rem', fontWeight: '600', borderRadius: '20px', background: '#f0f0f0', color: '#333', border: 'none', cursor: 'pointer', flexShrink: 0 }}
                    >
                      Clear
                    </button>
                  </div>

                  <div style={{ maxHeight: '250px', overflow: 'auto', border: '1px solid #ddd', borderRadius: '8px', background: 'white' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead>
                        <tr style={{ background: '#f5f5f5', position: 'sticky', top: 0 }}>
                          <th style={{ padding: '10px 15px', textAlign: 'left', width: '40px' }}></th>
                          <th style={{ padding: '10px 15px', textAlign: 'left' }}>Name</th>
                          <th style={{ padding: '10px 15px', textAlign: 'left' }}>Email</th>
                        </tr>
                      </thead>
                      <tbody>
                        {subscribers
                          .filter(s => !s.unsubscribed)
                          .filter(s => {
                            const search = (newCampaign.searchFilter || '').toLowerCase()
                            if (!search) return true
                            return (
                              (s.first_name || '').toLowerCase().includes(search) ||
                              (s.last_name || '').toLowerCase().includes(search) ||
                              (s.email || '').toLowerCase().includes(search)
                            )
                          })
                          .map(subscriber => (
                            <tr
                              key={subscriber.id}
                              style={{
                                borderBottom: '1px solid #eee',
                                cursor: 'pointer',
                                background: newCampaign.subscriber_ids.includes(subscriber.id) ? '#fff9e6' : 'transparent'
                              }}
                              onClick={() => {
                                if (newCampaign.subscriber_ids.includes(subscriber.id)) {
                                  setNewCampaign({ ...newCampaign, subscriber_ids: newCampaign.subscriber_ids.filter(id => id !== subscriber.id) })
                                } else {
                                  setNewCampaign({ ...newCampaign, subscriber_ids: [...newCampaign.subscriber_ids, subscriber.id] })
                                }
                              }}
                            >
                              <td style={{ padding: '10px 15px' }}>
                                <input
                                  type="checkbox"
                                  checked={newCampaign.subscriber_ids.includes(subscriber.id)}
                                  onChange={() => {}}
                                  style={{ cursor: 'pointer' }}
                                />
                              </td>
                              <td style={{ padding: '10px 15px', fontWeight: '500' }}>
                                {subscriber.first_name} {subscriber.last_name}
                              </td>
                              <td style={{ padding: '10px 15px', color: '#666' }}>
                                {subscriber.email}
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                  <div style={{ marginTop: '10px', color: '#666', fontSize: '14px' }}>
                    <strong>{newCampaign.subscriber_ids.length}</strong> recipient(s) selected
                  </div>
                </div>

                {/* Preview Section */}
                {campaignPreview && (
                  <div style={{ background: '#f0f7ff', padding: '20px', borderRadius: '8px', marginBottom: '10px' }}>
                    <h4 style={{ margin: '0 0 4px 0', fontSize: '16px', fontWeight: '600' }}>Preview</h4>
                    <div style={{ height: '3px', background: '#4a90d9', width: '60px', marginBottom: '15px' }}></div>
                    <p><strong>Subject:</strong> {campaignPreview.subject}</p>
                    <div style={{ whiteSpace: 'pre-wrap', background: 'white', padding: '15px', borderRadius: '6px', border: '1px solid #ddd' }}>
                      {campaignPreview.message}
                    </div>
                    {campaignPreview.promo_code && (
                      <p style={{ marginTop: '10px' }}><strong>Promo Code:</strong> <span style={{ background: '#D4AF37', color: 'white', padding: '2px 8px', borderRadius: '4px' }}>{campaignPreview.promo_code}</span></p>
                    )}
                  </div>
                )}
              </div>

              <div className="modal-actions" style={{ borderTop: '1px solid #eee', paddingTop: '20px', marginTop: '10px', flexWrap: 'wrap' }}>
                <button
                  className="modal-btn modal-btn-secondary"
                  onClick={closeCampaignModal}
                  style={{ borderRadius: '20px' }}
                >
                  Cancel
                </button>
                <button
                  className="modal-btn modal-btn-secondary"
                  onClick={previewCampaign}
                  disabled={!newCampaign.subject || !newCampaign.message}
                  style={{ borderRadius: '20px' }}
                >
                  Preview
                </button>
                <button
                  className="modal-btn modal-btn-primary"
                  onClick={createCampaign}
                  disabled={creatingCampaign || !newCampaign.subject || !newCampaign.message || newCampaign.subscriber_ids.length === 0}
                  style={{ borderRadius: '20px' }}
                >
                  {creatingCampaign
                    ? (editingCampaignId ? 'Saving...' : 'Creating...')
                    : (editingCampaignId ? 'Save Changes' : 'Create Campaign')}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Campaign Toast */}
        {campaignToast && (
          <div
            style={{
              position: 'fixed',
              bottom: '24px',
              right: '24px',
              zIndex: 10000,
              background: campaignToast.type === 'success' ? '#276749' : '#c53030',
              color: 'white',
              padding: '14px 20px',
              borderRadius: '12px',
              boxShadow: '0 8px 24px rgba(0,0,0,0.2)',
              fontSize: '14px',
              fontWeight: '500',
              maxWidth: '360px',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
            }}
          >
            <span>{campaignToast.type === 'success' ? '✓' : '!'}</span>
            <span>{campaignToast.message}</span>
            <button
              onClick={() => setCampaignToast(null)}
              style={{ background: 'transparent', border: 'none', color: 'white', cursor: 'pointer', fontSize: '18px', lineHeight: 1, padding: 0, marginLeft: 'auto' }}
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        )}

        {/* Campaign Confirm Modal (Delete / Send) */}
        {campaignConfirm && (
          <div className="modal-overlay" onClick={() => setCampaignConfirm(null)}>
            <div className="modal-content" style={{ maxWidth: '440px', width: '90%' }} onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <h3>
                  {campaignConfirm.action === 'delete' ? 'Delete draft campaign?' : 'Send campaign?'}
                </h3>
                <button className="modal-close" onClick={() => setCampaignConfirm(null)}>×</button>
              </div>
              <div className="modal-body">
                <p style={{ margin: 0, color: '#444' }}>
                  {campaignConfirm.action === 'delete'
                    ? 'This will permanently remove the draft and its selected recipients. This cannot be undone.'
                    : 'This will email every selected recipient immediately. This cannot be undone.'}
                </p>
              </div>
              <div className="modal-actions" style={{ borderTop: '1px solid #eee', paddingTop: '16px', marginTop: '10px' }}>
                <button
                  className="modal-btn modal-btn-secondary"
                  onClick={() => setCampaignConfirm(null)}
                  style={{ borderRadius: '20px' }}
                >
                  Cancel
                </button>
                <button
                  className={campaignConfirm.action === 'delete' ? 'modal-btn modal-btn-danger' : 'modal-btn modal-btn-primary'}
                  onClick={() => {
                    const { action, id } = campaignConfirm
                    setCampaignConfirm(null)
                    if (action === 'delete') {
                      performDeleteCampaign(id)
                    } else {
                      performSendCampaign(id)
                    }
                  }}
                  style={{ borderRadius: '20px', color: campaignConfirm.action === 'delete' ? 'white' : undefined }}
                >
                  {campaignConfirm.action === 'delete' ? 'Delete' : 'Send Campaign'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    )}

    {marketingSubTab === 'referrals' && (
      <div className="referrals-dashboard">
        <div className="admin-section-header">
          <h2>Referral Program</h2>
          <button
            className="referrals-refresh-button"
            onClick={fetchReferralsDashboard}
            disabled={loadingReferrals}
            type="button"
            aria-label="Refresh referrals dashboard"
          >
            <span className={loadingReferrals ? 'referrals-refresh-icon spinning' : 'referrals-refresh-icon'} aria-hidden="true">↻</span>
            <span>{loadingReferrals ? 'Refreshing' : 'Refresh'}</span>
          </button>
        </div>

        <form className="manual-referral-invite-panel" onSubmit={handleManualReferralInvite}>
          <div className="manual-referral-invite-heading">
            <h3>Social referral invite</h3>
          </div>
          <div className="manual-referral-invite-fields">
            <label className="referrals-control">
              <span>First name</span>
              <input
                type="text"
                value={manualReferralInvite.first_name}
                onChange={(e) => setManualReferralInvite(prev => ({ ...prev, first_name: e.target.value }))}
                required
              />
            </label>
            <label className="referrals-control">
              <span>Last name</span>
              <input
                type="text"
                value={manualReferralInvite.last_name}
                onChange={(e) => setManualReferralInvite(prev => ({ ...prev, last_name: e.target.value }))}
                required
              />
            </label>
            <label className="referrals-control referrals-control-wide">
              <span>Email</span>
              <input
                type="email"
                value={manualReferralInvite.email}
                onChange={(e) => setManualReferralInvite(prev => ({ ...prev, email: e.target.value }))}
                required
              />
            </label>
            <button
              type="submit"
              className="referrals-send-button"
              disabled={
                sendingManualReferralInvite ||
                !manualReferralInvite.first_name.trim() ||
                !manualReferralInvite.last_name.trim() ||
                !manualReferralInvite.email.trim()
              }
            >
              {sendingManualReferralInvite ? 'Sending...' : 'Send Invite'}
            </button>
          </div>
          {manualReferralInviteMessage && (
            <div className="manual-referral-invite-message">{manualReferralInviteMessage}</div>
          )}
        </form>

        {loadingReferrals && !referralsDashboardHasLoaded ? (
          <div className="loading-state">Loading referrals...</div>
        ) : (
          <div className="referrals-dashboard-content" aria-busy={loadingReferrals ? 'true' : 'false'}>
            <div className="referral-stats-grid">
              {[
                ['Invites sent', referralsDashboard.stats.invites_sent, 'blue'],
                ['Awaiting response', referralsDashboard.stats.awaiting_response, 'amber'],
                ['Opted in', referralsDashboard.stats.opted_in, 'green'],
                ['Opted out', referralsDashboard.stats.opted_out, 'rose'],
                ['Response opt-in rate', `${referralsDashboard.stats.opt_in_rate || 0}%`, 'teal'],
                ['Codes generated', referralsDashboard.stats.referral_codes_generated, 'indigo'],
                ['Code bookings', referralsDashboard.stats.referral_code_bookings_created, 'violet'],
                ['Qualified referrals', referralsDashboard.stats.completed_qualified_referrals, 'emerald'],
                ['Self-use / disqualified', referralsDashboard.stats.self_use_disqualified_referrals, 'orange'],
                ['Rewards earned', referralsDashboard.stats.rewards_earned, 'cyan'],
                ['Rewards sent', referralsDashboard.stats.rewards_sent, 'slate'],
              ].map(([label, value, tone]) => (
                <div className={`stats-card referral-stat-card referral-stat-card-${tone}`} key={label}>
                  <div className="stats-card-value">{value ?? 0}</div>
                  <div className="stats-card-label">{label}</div>
                </div>
              ))}
            </div>

            <div className="referrals-panel">
              <div className="referrals-panel-header">
                <h3>Referral Customers</h3>
                <div className="referrals-control-group">
                  <label className="referrals-control">
                    <span>Filter</span>
                    <select
                      value={referralsFilter}
                      onChange={(e) => {
                        setReferralsFilter(e.target.value)
                        setReferralsCustomerOffset(0)
                      }}
                    >
                      <option value="all">All</option>
                      <option value="awaiting_response">Awaiting response</option>
                      <option value="opted_in">Opted in</option>
                      <option value="opted_out">Opted out</option>
                      <option value="has_code_usage">Has code usage</option>
                      <option value="has_qualified">Has qualified referrals</option>
                      <option value="reward_earned">Reward earned</option>
                      <option value="self_use_only">Self-use only</option>
                      <option value="disqualified_usage">Disqualified usage</option>
                    </select>
                  </label>
                  <label className="referrals-control referrals-control-wide">
                    <span>Search</span>
                    <input
                      type="text"
                      className="referrals-search"
                      placeholder="Customer, email, code"
                      value={referralsCustomerSearch}
                      onChange={(e) => setReferralsCustomerSearch(e.target.value)}
                    />
                  </label>
                </div>
              </div>
              <div className="admin-table-container">
                <table className="admin-table referrals-table">
                  <thead>
                    <tr>
                      <th>Customer</th>
                      <th>Email</th>
                      <th>Status</th>
                      <th>Source</th>
                      <th>Code</th>
                      <th>Uses</th>
                      <th>Qualified</th>
                      <th>Reward</th>
                      <th>Invite Sent</th>
                      <th>Code Email Sent</th>
                      <th>Reminder Sent</th>
                      <th>Responded</th>
                      <th>Reward Earned</th>
                      <th>Reward Email Sent</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredReferralCustomers.map(row => (
                      <tr key={row.program_id}>
                        <td>{row.customer_name || '-'}</td>
                        <td>{row.email || '-'}</td>
                        <td><span className={`status-badge ${row.status}`}>{row.status_label}</span></td>
                        <td><span className={`referral-source-pill ${row.invite_source || 'booking'}`}>{row.invite_source_label || 'Booking'}</span></td>
                        <td><span className="promo-code-display">{row.code || '-'}</span></td>
                        <td>{row.uses || 0}</td>
                        <td>{row.qualified || 0}</td>
                        <td>{row.reward_code || (row.reward_earned ? 'Earned' : '-')}</td>
                        <td>{formatDateTimeUK(row.invite_sent_at)}</td>
                        <td>{formatDateTimeUK(row.code_email_sent_at)}</td>
                        <td>{formatDateTimeUK(row.reminder_sent_at)}</td>
                        <td>{formatDateTimeUK(row.responded_at)}</td>
                        <td>{formatDateTimeUK(row.reward_earned_at)}</td>
                        <td>{formatDateTimeUK(row.reward_email_sent_at)}</td>
                        <td>
                          <div className="referral-action-row">
                            <button
                              className="referral-action-button referral-action-button-neutral"
                              onClick={() => openCustomerModal({ id: row.customer_id })}
                            >
                              View Customer
                            </button>
                            {row.code && (
                              <button
                                className="referral-action-button referral-action-button-neutral"
                                onClick={() => {
                                  setReferralsUsageFilter('all')
                                  setReferralsUsageSearch(row.code)
                                  setReferralsUsageOffset(0)
                                  setTimeout(() => {
                                    referralUsageTableRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                                  }, 0)
                                }}
                              >
                                View Bookings
                              </button>
                            )}
                            <button
                              className="referral-action-button referral-action-button-success"
                              onClick={() => handleReferralDashboardAction(row, 'resend-code')}
                              disabled={!!referralDashboardAction || !row.code || !row.code_active}
                            >
                              {referralDashboardAction === `${row.customer_id}:resend-code` ? 'Resending...' : 'Resend Code'}
                            </button>
                            <button
                              className="referral-action-button referral-action-button-success"
                              onClick={() => handleReferralDashboardAction(row, 'generate-new-code')}
                              disabled={!!referralDashboardAction}
                            >
                              {referralDashboardAction === `${row.customer_id}:generate-new-code` ? 'Generating...' : 'Generate Code'}
                            </button>
                            <button
                              className="referral-action-button referral-action-button-danger"
                              onClick={() => handleReferralDashboardAction(row, 'cancel-code')}
                              disabled={!!referralDashboardAction || !row.code || !row.code_active}
                            >
                              {referralDashboardAction === `${row.customer_id}:cancel-code` ? 'Cancelling...' : 'Cancel Code'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {filteredReferralCustomers.length === 0 && (
                      <tr><td colSpan="15" className="no-data">No referral customers match this filter.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div className="referrals-pagination">
                <span>
                  Showing {referralCustomerStart}-{referralCustomerEnd} of {referralCustomerTotal} customers
                </span>
                <div className="referrals-pagination-controls">
                  <label className="referrals-page-size">
                    <span>Rows</span>
                    <select
                      value={referralsCustomerPageSize}
                      onChange={(e) => {
                        setReferralsCustomerPageSize(Number(e.target.value))
                        setReferralsCustomerOffset(0)
                      }}
                    >
                      {REFERRALS_PAGE_SIZE_OPTIONS.map(size => (
                        <option key={size} value={size}>{size}</option>
                      ))}
                    </select>
                  </label>
                  <button
                    className="referrals-page-button"
                    disabled={loadingReferrals || referralsCustomerOffset === 0}
                    onClick={() => setReferralsCustomerOffset(Math.max(0, referralsCustomerOffset - referralsCustomerPageSize))}
                  >
                    Previous
                  </button>
                  <button
                    className="referrals-page-button"
                    disabled={loadingReferrals || referralCustomerEnd >= referralCustomerTotal}
                    onClick={() => setReferralsCustomerOffset(referralsCustomerOffset + referralsCustomerPageSize)}
                  >
                    Next
                  </button>
                </div>
              </div>
            </div>

            <div className="referrals-panel" ref={referralUsageTableRef}>
              <div className="referrals-panel-header">
                <h3>Code Usage / Bookings</h3>
                <div className="referrals-control-group">
                  <label className="referrals-control referrals-control-wide">
                    <span>Search</span>
                    <input
                      type="text"
                      className="referrals-usage-search"
                      placeholder="Code, booking, referrer"
                      value={referralsUsageSearch}
                      onChange={(e) => setReferralsUsageSearch(e.target.value)}
                    />
                  </label>
                  <label className="referrals-control">
                    <span>Filter</span>
                    <select
                      value={referralsUsageFilter}
                      onChange={(e) => {
                        setReferralsUsageFilter(e.target.value)
                        setReferralsUsageOffset(0)
                      }}
                    >
                      <option value="all">All</option>
                      <option value="open_bookings">Pending / confirmed bookings</option>
                      <option value="completed">Completed bookings</option>
                      <option value="pending">Pending attribution</option>
                      <option value="qualified">Qualified</option>
                      <option value="disqualified">Disqualified</option>
                      <option value="self_use">Self-use</option>
                    </select>
                  </label>
                </div>
              </div>
              <div className="admin-table-container">
                <table className="admin-table referrals-table">
                  <thead>
                    <tr>
                      <th>Referrer</th>
                      <th>Code</th>
                      <th>Used By</th>
                      <th>Booking</th>
                      <th>Booking Status</th>
                      <th>Discount</th>
                      <th>Self-use</th>
                      <th>Attribution</th>
                      <th>Completed At</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredReferralUsage.map(row => (
                      <tr key={row.usage_id}>
                        <td>{row.referrer || '-'}</td>
                        <td><span className="promo-code-display">{row.code || '-'}</span></td>
                        <td>{row.used_by || '-'}</td>
                        <td>
                          {row.booking_reference ? (
                            <button
                              type="button"
                              className="link-button"
                              onClick={() => {
                                onSelectAdminItem('bookings')
                                setSearchTerm(row.booking_reference)
                              }}
                            >
                              {row.booking_reference}
                            </button>
                          ) : '-'}
                        </td>
                        <td><span className={`status-badge ${row.booking_status || 'pending'}`}>{row.booking_status || '-'}</span></td>
                        <td>{row.discount_percent}% {row.discount_amount_pence ? `(${formatPence(row.discount_amount_pence)})` : ''}</td>
                        <td>{row.self_use ? 'Yes' : 'No'}</td>
                        <td><span className={`status-badge ${row.attribution_status}`}>{row.attribution_status}</span></td>
                        <td>{formatDateTimeUK(row.completed_at)}</td>
                      </tr>
                    ))}
                    {filteredReferralUsage.length === 0 && (
                      <tr><td colSpan="9" className="no-data">No referral code usage matches this filter.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div className="referrals-pagination">
                <span>
                  Showing {referralUsageStart}-{referralUsageEnd} of {referralUsageTotal} code usages
                </span>
                <div className="referrals-pagination-controls">
                  <label className="referrals-page-size">
                    <span>Rows</span>
                    <select
                      value={referralsUsagePageSize}
                      onChange={(e) => {
                        setReferralsUsagePageSize(Number(e.target.value))
                        setReferralsUsageOffset(0)
                      }}
                    >
                      {REFERRALS_PAGE_SIZE_OPTIONS.map(size => (
                        <option key={size} value={size}>{size}</option>
                      ))}
                    </select>
                  </label>
                  <button
                    className="referrals-page-button"
                    disabled={loadingReferrals || referralsUsageOffset === 0}
                    onClick={() => setReferralsUsageOffset(Math.max(0, referralsUsageOffset - referralsUsagePageSize))}
                  >
                    Previous
                  </button>
                  <button
                    className="referrals-page-button"
                    disabled={loadingReferrals || referralUsageEnd >= referralUsageTotal}
                    onClick={() => setReferralsUsageOffset(referralsUsageOffset + referralsUsagePageSize)}
                  >
                    Next
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    )}

    {/* Sources Sub-tab (Marketing Sources) */}
    {marketingSubTab === 'sources' && (
      <div className="marketing-sources-section">
        <div className="admin-section-header">
          <h2>Marketing Sources</h2>
          <div className="flights-header-actions">
            <button
              className="btn-secondary"
              onClick={fetchMarketingSources}
              disabled={loadingMarketingSources}
            >
              ↻ Refresh
            </button>
            <button
              className="btn-primary"
              onClick={exportMarketingSourcesCSV}
            >
              ↓ Download CSV
            </button>
          </div>
        </div>
        <p className="admin-subtitle">
          Where customers heard about TAG Parking (based on Page 4 attribution question)
        </p>

        <div className="flights-filters">
          <div className="flight-filter-group leads-date-picker">
            <label>From:</label>
            <DatePicker
              selected={marketingExportFromDate}
              onChange={(date) => setMarketingExportFromDate(date)}
              dateFormat="dd/MM/yyyy"
              placeholderText="DD/MM/YYYY"
              className="flight-date-input"
              isClearable
            />
          </div>
          <div className="flight-filter-group leads-date-picker">
            <label>To:</label>
            <DatePicker
              selected={marketingExportToDate}
              onChange={(date) => setMarketingExportToDate(date)}
              dateFormat="dd/MM/yyyy"
              placeholderText="DD/MM/YYYY"
              className="flight-date-input"
              isClearable
            />
          </div>
          {(marketingExportFromDate || marketingExportToDate) && (
            <button
              className="btn-secondary clear-dates-btn"
              onClick={() => { setMarketingExportFromDate(null); setMarketingExportToDate(null); }}
            >
              × Clear
            </button>
          )}
          {marketingSourcesData && (
            <div className="leads-filter-count">
              Showing {marketingSourcesData.total_responses} responses
            </div>
          )}
        </div>

        {loadingMarketingSources ? (
          <div className="admin-loading-inline">
            <div className="spinner-small"></div>
            <span>Loading marketing sources...</span>
          </div>
        ) : marketingSourcesData ? (
          <>
            {/* Total Summary */}
            <div className="marketing-total-summary">
              <div className="stats-card">
                <div className="stats-card-value">{marketingSourcesData.total_responses}</div>
                <div className="stats-card-label">Total Responses</div>
              </div>
            </div>

            {/* Monthly Breakdown */}
            <h4>Monthly Breakdown</h4>
            {marketingSourcesData.monthly_data && marketingSourcesData.monthly_data.length > 0 ? (
              <div className="marketing-monthly-table">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>Month</th>
                      {[
                        { key: 'google', label: 'Google', icon: 'bi bi-google' },
                        { key: 'facebook', label: 'Facebook', icon: 'bi bi-facebook' },
                        { key: 'instagram', label: 'Instagram', icon: 'bi bi-instagram' },
                        { key: 'word_of_mouth', label: 'Word of Mouth', icon: null },
                        { key: 'leaflet', label: 'Leaflet', icon: 'bi bi-file-text' },
                        { key: 'tv', label: 'TV', icon: 'bi bi-tv' },
                        { key: 'radio', label: 'Radio', icon: 'bi bi-broadcast' },
                        { key: 'newspaper', label: 'Newspaper', icon: 'bi bi-newspaper' },
                        { key: 'linkedin', label: 'LinkedIn', icon: 'bi bi-linkedin' },
                        { key: 'afc_bournemouth', label: 'AFCB', icon: null },
                        { key: 'expectations_travel', label: 'Expect.', icon: null },
                        { key: 'other', label: 'Other', icon: null }
                      ].map(source => (
                        <th key={source.key} title={source.label}>
                          {source.icon ? <i className={source.icon}></i> : source.label}
                        </th>
                      ))}
                      <th>Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {marketingSourcesData.monthly_data.map((month, idx) => {
                      const total = Object.values(month.sources).reduce((a, b) => a + b, 0)
                      return (
                        <tr key={idx}>
                          <td>{month.year_month.split('-').reverse().join('/')}</td>
                          {['google', 'facebook', 'instagram', 'word_of_mouth', 'leaflet', 'tv', 'radio', 'newspaper', 'linkedin', 'afc_bournemouth', 'expectations_travel', 'other'].map(source => (
                            <td key={source}>
                              {month.sources[source] || 0}
                              {source === 'other' && month.sources.other > 0 && (
                                <button
                                  className="view-other-details"
                                  onClick={() => fetchMarketingOtherDetails(month.year_month)}
                                  title={`View 'Other' details for ${month.year_month}`}
                                >
                                  ?
                                </button>
                              )}
                            </td>
                          ))}
                          <td><strong>{total}</strong></td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="no-data">No marketing source data yet.</p>
            )}

            {/* Source Totals */}
            <h4>All-Time Totals by Source</h4>
            <div className="marketing-source-totals">
              {marketingSourcesData.source_totals && Object.entries(marketingSourcesData.source_totals)
                .sort(([, a], [, b]) => b - a)
                .map(([source, count]) => {
                  const sourceLabels = {
                    google: 'Google',
                    facebook: 'Facebook',
                    instagram: 'Instagram',
                    word_of_mouth: 'Word of Mouth',
                    leaflet: 'Leaflet',
                    tv: 'TV',
                    radio: 'Radio',
                    newspaper: 'Newspaper',
                    linkedin: 'LinkedIn',
                    afc_bournemouth: 'AFC Bournemouth',
                    expectations_travel: 'Expectations Travel',
                    other: 'Other'
                  }
                  const percentage = marketingSourcesData.total_responses > 0
                    ? ((count / marketingSourcesData.total_responses) * 100).toFixed(1)
                    : 0
                  return (
                    <div key={source} className="source-total-item">
                      <span className="source-name">{sourceLabels[source] || source}</span>
                      <span className="source-count">{count}</span>
                      <span className="source-percentage">{percentage}%</span>
                      <div className="source-bar" style={{ width: `${percentage}%` }}></div>
                    </div>
                  )
                })}
            </div>

            {/* Percentage Breakdown */}
            <h4>Percentage Breakdown</h4>
            <div className="marketing-percentage-grid">
              {marketingSourcesData.source_totals && Object.entries(marketingSourcesData.source_totals)
                .sort(([, a], [, b]) => b - a)
                .map(([source, count]) => {
                  const sourceLabels = {
                    google: 'Google',
                    facebook: 'Facebook',
                    instagram: 'Instagram',
                    word_of_mouth: 'Word of Mouth',
                    leaflet: 'Leaflet',
                    tv: 'TV',
                    radio: 'Radio',
                    newspaper: 'Newspaper',
                    linkedin: 'LinkedIn',
                    afc_bournemouth: 'AFC Bournemouth',
                    expectations_travel: 'Expectations Travel',
                    other: 'Other'
                  }
                  const percentage = marketingSourcesData.total_responses > 0
                    ? ((count / marketingSourcesData.total_responses) * 100).toFixed(1)
                    : 0
                  return (
                    <div key={source} className="percentage-card">
                      <div className="percentage-value">{percentage}%</div>
                      <div className="percentage-label">{sourceLabels[source] || source}</div>
                      <div className="percentage-count">{count} response{count !== 1 ? 's' : ''}</div>
                    </div>
                  )
                })}
            </div>
          </>
        ) : (
          <p className="no-data">No marketing source data available.</p>
        )}
      </div>
    )}

    {/* Marketing "Other" Details Modal */}
    {showMarketingOtherModal && (
      <div className="modal-overlay" onClick={() => setShowMarketingOtherModal(false)}>
        <div className="modal-content marketing-other-modal" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h3>"Other" Source Details {marketingOtherMonth && `- ${(() => {
                const [year, month] = marketingOtherMonth.split('-')
                return new Date(year, month - 1, 15).toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
              })()}`}</h3>
            <button className="modal-close" onClick={() => setShowMarketingOtherModal(false)}>&times;</button>
          </div>
          <div className="modal-body marketing-other-modal-body">
            {loadingMarketingOther ? (
              <div className="admin-loading-inline">
                <div className="spinner-small"></div>
                <span>Loading...</span>
              </div>
            ) : marketingOtherDetails && marketingOtherDetails.length > 0 ? (
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Customer</th>
                    <th>Detail</th>
                    <th>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {marketingOtherDetails.map((item, idx) => (
                    <tr key={idx}>
                      <td>{item.customer_name || item.customer_email}</td>
                      <td>{item.source_detail}</td>
                      <td>{new Date(item.created_at).toLocaleDateString('en-GB')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p>No "Other" details recorded.</p>
            )}
          </div>
        </div>
      </div>
    )}

    {/* Generate More Codes Modal */}
    {showGenerateCodesModal && generateCodesPromotion && (
      <div className="modal-overlay" onClick={() => setShowGenerateCodesModal(false)}>
        <div className="modal-content" style={{ maxWidth: '400px' }} onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h3>Generate More Codes</h3>
            <button className="modal-close" onClick={() => setShowGenerateCodesModal(false)}>&times;</button>
          </div>
          <div className="modal-body">
            <p style={{ marginBottom: '15px', color: '#666' }}>
              Add more codes to <strong>{generateCodesPromotion.name}</strong>
            </p>
            <p style={{ marginBottom: '15px', fontSize: '14px', color: '#999' }}>
              Current: {generateCodesPromotion.total_codes} codes ({generateCodesPromotion.codes_available} available)
            </p>
            <div className="form-group" style={{ marginBottom: '15px' }}>
              <label>Number of codes to generate</label>
              <input
                type="number"
                value={generateCodesCount}
                onChange={(e) => setGenerateCodesCount(Math.max(1, Math.min(1000, parseInt(e.target.value) || 1)))}
                min="1"
                max="1000"
                className="admin-input"
                style={{ width: '100%' }}
              />
            </div>
            <div style={{ padding: '15px', background: '#f8f9fa', borderRadius: '8px', border: '1px solid #e9ecef', marginBottom: '15px' }}>
              <label style={{ fontWeight: '600', color: '#495057', marginBottom: '10px', display: 'block' }}>⏰ Code Expiry (optional)</label>
              <div style={{ display: 'flex', gap: '10px' }}>
                <div className="form-group" style={{ flex: 1 }}>
                  <label style={{ fontSize: '12px' }}>Date (DD/MM/YYYY)</label>
                  <input
                    type="text"
                    value={generateCodesExpiryDate}
                    onChange={(e) => setGenerateCodesExpiryDate(e.target.value)}
                    placeholder="28/03/2026"
                    className="admin-input"
                    style={{ width: '100%' }}
                  />
                </div>
                <div className="form-group" style={{ flex: 1 }}>
                  <label style={{ fontSize: '12px' }}>Time (HH:MM UK)</label>
                  <input
                    type="text"
                    value={generateCodesExpiryTime}
                    onChange={(e) => setGenerateCodesExpiryTime(e.target.value)}
                    placeholder="14:30"
                    className="admin-input"
                    style={{ width: '100%' }}
                  />
                </div>
              </div>
            </div>
            <div style={{ padding: '15px', background: generateCodesMaxUses === '0' ? '#e8f5e9' : '#f8f9fa', borderRadius: '8px', border: generateCodesMaxUses === '0' ? '1px solid #c8e6c9' : '1px solid #e9ecef' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', fontWeight: '600', color: generateCodesMaxUses === '0' ? '#2e7d32' : '#495057' }}>
                <input
                  type="checkbox"
                  checked={generateCodesMaxUses === '0'}
                  onChange={(e) => setGenerateCodesMaxUses(e.target.checked ? '0' : '')}
                  style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                />
                🔄 Unlimited Uses (multi-use code)
              </label>
              <small style={{ color: '#666', fontSize: '11px', marginTop: '5px', display: 'block', marginLeft: '28px' }}>
                {generateCodesMaxUses === '0'
                  ? 'This code can be used unlimited times'
                  : 'Default: single-use code'}
              </small>
            </div>
          </div>
          <div className="modal-actions">
            <button
              className="modal-btn modal-btn-secondary"
              onClick={() => { setShowGenerateCodesModal(false); setGenerateCodesExpiryDate(''); setGenerateCodesExpiryTime(''); }}
            >
              Cancel
            </button>
            <button
              className="modal-btn modal-btn-primary"
              onClick={generateMoreCodes}
              disabled={generatingCodes}
            >
              {generatingCodes ? 'Generating...' : `Generate ${generateCodesCount} Codes`}
            </button>
          </div>
        </div>
      </div>
    )}

    {/* Send Promo Email Modal */}
    {showSendPromoEmailModal && sendPromoEmailData && (
      <div className="modal-overlay" onClick={() => setShowSendPromoEmailModal(false)}>
        <div className="modal-content" style={{ maxWidth: '700px', maxHeight: '90vh', overflow: 'auto' }} onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h3>Send Promo Emails - {sendPromoEmailData.promotion.name}</h3>
            <button className="modal-close" onClick={() => setShowSendPromoEmailModal(false)}>&times;</button>
          </div>
          <div className="modal-body">
            <p style={{ marginBottom: '15px', color: '#666' }}>
              <strong>{sendPromoEmailData.availableCodes.length}</strong> codes available to send
            </p>

            {/* Recipient Search */}
            <div className="form-group" style={{ marginBottom: '20px' }}>
              <label>Search Customers & Subscribers</label>
              <input
                type="text"
                value={recipientSearchTerm}
                onChange={(e) => {
                  setRecipientSearchTerm(e.target.value)
                  searchRecipients(e.target.value)
                }}
                placeholder="Search by name or email..."
                className="admin-input"
                style={{ width: '100%' }}
              />
              {searchingRecipients && <small>Searching...</small>}
              {recipientSearchResults.length > 0 && (
                <div className="search-results" style={{ border: '1px solid #ddd', borderRadius: '4px', marginTop: '5px', maxHeight: '150px', overflowY: 'auto' }}>
                  {recipientSearchResults.map((r, idx) => (
                    <div
                      key={idx}
                      style={{ padding: '8px 12px', borderBottom: '1px solid #eee', cursor: 'pointer', display: 'flex', justifyContent: 'space-between' }}
                      onClick={() => addRecipient(r)}
                    >
                      <span>{r.first_name} {r.last_name || ''} - {r.email}</span>
                      <small style={{ color: '#666' }}>{r.source}</small>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Manual Entry */}
            <div className="form-group" style={{ marginBottom: '20px' }}>
              <label>Or Add Manually (family/friends)</label>
              <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                <input
                  type="email"
                  value={manualRecipient.email}
                  onChange={(e) => setManualRecipient(prev => ({ ...prev, email: e.target.value }))}
                  placeholder="Email"
                  className="admin-input"
                  style={{ flex: '2', minWidth: '180px' }}
                />
                <input
                  type="text"
                  value={manualRecipient.first_name}
                  onChange={(e) => setManualRecipient(prev => ({ ...prev, first_name: e.target.value }))}
                  placeholder="First Name"
                  className="admin-input"
                  style={{ flex: '1', minWidth: '100px' }}
                />
                <input
                  type="text"
                  value={manualRecipient.last_name}
                  onChange={(e) => setManualRecipient(prev => ({ ...prev, last_name: e.target.value }))}
                  placeholder="Last Name"
                  className="admin-input"
                  style={{ flex: '1', minWidth: '100px' }}
                />
                <button
                  className="btn-secondary"
                  onClick={addManualRecipient}
                  disabled={!manualRecipient.email || !manualRecipient.first_name}
                  style={{ padding: '8px 15px' }}
                >
                  + Add
                </button>
              </div>
            </div>

            {/* Selected Recipients */}
            <div className="form-group" style={{ marginBottom: '20px' }}>
              <label>Recipients ({promoEmailRecipients.length})</label>
              {promoEmailRecipients.length === 0 ? (
                <p style={{ color: '#999', fontStyle: 'italic' }}>No recipients selected</p>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {promoEmailRecipients.map((r, idx) => (
                    <span
                      key={idx}
                      style={{
                        background: '#e9ecef',
                        padding: '5px 10px',
                        borderRadius: '15px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        fontSize: '13px',
                      }}
                    >
                      {r.first_name} ({r.email})
                      <button
                        onClick={() => removeRecipient(r.email)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc3545', fontWeight: 'bold' }}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
              {promoEmailRecipients.length > sendPromoEmailData.availableCodes.length && (
                <p style={{ color: '#dc3545', marginTop: '10px' }}>
                  ⚠️ More recipients than available codes!
                </p>
              )}
            </div>

            {/* Email Subject */}
            <div className="form-group" style={{ marginBottom: '15px' }}>
              <label>Email Subject</label>
              <input
                type="text"
                value={promoEmailSubject}
                onChange={(e) => setPromoEmailSubject(e.target.value)}
                className="admin-input"
                style={{ width: '100%' }}
              />
              <small style={{ color: '#666' }}>Use {'{{FIRST_NAME}}'} for personalization</small>
            </div>

            {/* Email Body */}
            <div className="form-group" style={{ marginBottom: '15px' }}>
              <label>Email Body (HTML)</label>
              <textarea
                value={promoEmailBody}
                onChange={(e) => setPromoEmailBody(e.target.value)}
                className="admin-input"
                rows="10"
                style={{ width: '100%', fontFamily: 'monospace', fontSize: '12px' }}
              />
              <small style={{ color: '#666' }}>
                Use {'{{FIRST_NAME}}'} and {'{{PROMO_CODE}}'} placeholders
              </small>
            </div>
          </div>
          <div className="modal-actions">
            <button className="modal-btn modal-btn-secondary" onClick={() => setShowSendPromoEmailModal(false)}>
              Cancel
            </button>
            <button
              className="modal-btn modal-btn-primary"
              onClick={sendPromoEmails}
              disabled={sendingPromoEmails || promoEmailRecipients.length === 0 || promoEmailRecipients.length > sendPromoEmailData.availableCodes.length}
            >
              {sendingPromoEmails ? 'Sending...' : `Send ${promoEmailRecipients.length} Email${promoEmailRecipients.length !== 1 ? 's' : ''}`}
            </button>
          </div>
        </div>
      </div>
    )}

    {/* Set Expiry Modal */}
    {showExpiryModal && expiryModalData && (
      <div className="modal-overlay" onClick={() => setShowExpiryModal(false)}>
        <div className="modal-content" style={{ maxWidth: '400px' }} onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h3>{expiryModalData.isBulk ? 'Set Expiry for Selected Codes' : 'Set Code Expiry'}</h3>
            <button className="modal-close" onClick={() => setShowExpiryModal(false)}>&times;</button>
          </div>
          <div className="modal-body">
            {expiryModalData.isBulk ? (
              <p style={{ marginBottom: '15px', color: '#666' }}>
                Setting expiry for <strong>{expiryModalData.codeIds?.length}</strong> selected code{expiryModalData.codeIds?.length > 1 ? 's' : ''}
              </p>
            ) : (
              <>
                <p style={{ marginBottom: '15px', color: '#666' }}>
                  Code: <code style={{ background: '#f0f0f0', padding: '2px 6px', borderRadius: '3px' }}>{expiryModalData.code?.code}</code>
                </p>
                {expiryModalData.code?.is_expired && (
                  <p style={{ marginBottom: '15px', color: '#dc3545', fontWeight: '600' }}>
                    This code has expired
                  </p>
                )}
              </>
            )}
            <div className="form-group" style={{ marginBottom: '15px' }}>
              <label>Expiry Date (DD/MM/YYYY)</label>
              <input
                type="text"
                value={expiryDate}
                onChange={(e) => setExpiryDate(e.target.value)}
                placeholder="28/03/2026"
                className="admin-input"
                style={{ width: '100%' }}
              />
            </div>
            <div className="form-group" style={{ marginBottom: '15px' }}>
              <label>Expiry Time (HH:MM - 24hr UK time)</label>
              <input
                type="text"
                value={expiryTime}
                onChange={(e) => setExpiryTime(e.target.value)}
                placeholder="14:30"
                className="admin-input"
                style={{ width: '100%' }}
              />
            </div>
            <p style={{ fontSize: '12px', color: '#999' }}>
              Leave both fields empty to remove expiry (code{expiryModalData.isBulk ? 's' : ''} never expire{expiryModalData.isBulk ? '' : 's'})
            </p>
          </div>
          <div className="modal-actions">
            <button
              className="modal-btn modal-btn-secondary"
              onClick={() => setShowExpiryModal(false)}
            >
              Cancel
            </button>
            <button
              className="modal-btn modal-btn-primary"
              onClick={updatePromoCodeExpiry}
              disabled={updatingExpiry}
            >
              {updatingExpiry ? 'Saving...' : (expiryModalData.isBulk ? `Update ${expiryModalData.codeIds?.length} Codes` : 'Save Expiry')}
            </button>
          </div>
        </div>
      </div>
    )}
  </div>
    </>
  )
}

export default MarketingSectionPage
