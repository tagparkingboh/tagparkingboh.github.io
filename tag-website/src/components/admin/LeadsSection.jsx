import DatePicker from 'react-datepicker'

const LeadsSection = ({
  fetchLeads,
  loadingLeads,
  leadSearchTerm,
  setLeadSearchTerm,
  leads,
  leadDateFrom,
  setLeadDateFrom,
  leadDateTo,
  setLeadDateTo,
  expandedLeadMonths,
  setExpandedLeadMonths,
  expandedLeadId,
  setExpandedLeadId,
}) => {
  const safeLeads = leads || []

  const isInDateFilter = (lead) => {
    if (!(leadDateFrom || leadDateTo)) return true
    const leadDate = lead.created_at ? new Date(lead.created_at) : null
    if (!leadDate) return false
    if (leadDateFrom) {
      const fromDate = new Date(leadDateFrom)
      fromDate.setHours(0, 0, 0, 0)
      if (leadDate < fromDate) return false
    }
    if (leadDateTo) {
      const toDate = new Date(leadDateTo)
      toDate.setHours(23, 59, 59, 999)
      if (leadDate > toDate) return false
    }
    return true
  }

  const isSearchMatch = (lead, search) => {
    if (!search) return true
    return (
      lead.first_name?.toLowerCase().includes(search) ||
      lead.last_name?.toLowerCase().includes(search) ||
      lead.email?.toLowerCase().includes(search) ||
      lead.phone?.includes(search)
    )
  }

  const getFilteredLeads = () => {
    const search = leadSearchTerm.toLowerCase()
    return safeLeads.filter(lead => isInDateFilter(lead) && isSearchMatch(lead, search))
  }

  const getGroupedLeads = (filteredLeads) => {
    const monthlyGroups = {}
    filteredLeads.forEach(lead => {
      const date = lead.created_at ? new Date(lead.created_at) : null
      if (date) {
        const monthKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
        if (!monthlyGroups[monthKey]) monthlyGroups[monthKey] = []
        monthlyGroups[monthKey].push(lead)
      }
    })
    return monthlyGroups
  }

  const handleDownloadCsv = () => {
    const csvRows = [['Name', 'Phone', 'Email', 'Date Added']]
    getFilteredLeads().forEach(lead => {
      const name = `${lead.first_name || ''} ${lead.last_name || ''}`.trim()
      const dateAdded = lead.created_at
        ? new Date(lead.created_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London' })
        : ''
      csvRows.push([name, lead.phone || '', lead.email || '', dateAdded])
    })
    const csvContent = csvRows.map(row => row.map(cell => `"${(cell || '').replace(/"/g, '""')}"`).join(',')).join('\n')
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.setAttribute('href', url)

    const formatDateForFilename = (date) => {
      const day = String(date.getDate()).padStart(2, '0')
      const month = String(date.getMonth() + 1).padStart(2, '0')
      const year = date.getFullYear()
      return `${day}-${month}-${year}`
    }

    let filename = 'leads'
    if (leadDateFrom && leadDateTo) {
      filename = `leads_${formatDateForFilename(leadDateFrom)}_to_${formatDateForFilename(leadDateTo)}`
    } else if (leadDateFrom) {
      filename = `leads_from_${formatDateForFilename(leadDateFrom)}`
    } else if (leadDateTo) {
      filename = `leads_to_${formatDateForFilename(leadDateTo)}`
    } else {
      filename = `leads_all_${formatDateForFilename(new Date())}`
    }

    link.setAttribute('download', `${filename}.csv`)
    link.click()
    URL.revokeObjectURL(url)
  }

  const filteredLeads = getFilteredLeads()
  const groupedLeads = getGroupedLeads(filteredLeads)
  const sortedMonths = Object.keys(groupedLeads).sort().reverse()
  const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2>Abandoned Leads</h2>
        <div className="flights-header-actions">
          <button className="btn-secondary" onClick={fetchLeads} disabled={loadingLeads}>
            {loadingLeads ? 'Loading...' : '↻ Refresh'}
          </button>
          <button className="btn-primary" onClick={handleDownloadCsv} disabled={loadingLeads}>
            ↓ Download CSV
          </button>
        </div>
      </div>
      <p className="admin-subtitle">Customers who started booking but didn't complete payment</p>

      <div className="flights-filters">
        <div className="flight-filter-group lead-search-group">
          <input
            type="text"
            placeholder="Search by name, email, or phone..."
            value={leadSearchTerm}
            onChange={(e) => setLeadSearchTerm(e.target.value)}
            className="flight-number-input lead-search-input"
          />
          {leadSearchTerm && (
            <button className="lead-search-clear" onClick={() => setLeadSearchTerm('')}>
              ×
            </button>
          )}
        </div>
        <div className="flight-filter-group leads-date-picker">
          <label>From:</label>
          <DatePicker
            selected={leadDateFrom}
            onChange={(date) => setLeadDateFrom(date)}
            dateFormat="dd/MM/yyyy"
            placeholderText="DD/MM/YYYY"
            className="flight-date-input"
            isClearable
          />
        </div>
        <div className="flight-filter-group leads-date-picker">
          <label>To:</label>
          <DatePicker
            selected={leadDateTo}
            onChange={(date) => setLeadDateTo(date)}
            dateFormat="dd/MM/yyyy"
            placeholderText="DD/MM/YYYY"
            className="flight-date-input"
            isClearable
          />
        </div>
        {(leadDateFrom || leadDateTo) && (
          <button
            className="btn-secondary clear-dates-btn"
            onClick={() => { setLeadDateFrom(null); setLeadDateTo(null) }}
          >
            × Clear
          </button>
        )}
        <div className="leads-filter-count">
          Showing {filteredLeads.length} of {safeLeads.length} leads
        </div>
      </div>

      {loadingLeads ? (
        <div className="admin-loading-inline">
          <div className="loading-spinner-small"></div>
          <span>Loading leads...</span>
        </div>
      ) : (
        <div className="booking-accordion">
          {(() => {
            if (sortedMonths.length === 0) {
              return <p className="admin-no-data">No abandoned leads found</p>
            }

            return sortedMonths.map(monthKey => {
              const [year, month] = monthKey.split('-')
              const monthName = `${monthNames[parseInt(month, 10) - 1]} ${year}`
              const monthLeads = groupedLeads[monthKey]
              const isExpanded = expandedLeadMonths[monthKey]

              return (
                <div key={monthKey} className="leads-month-container">
                  <div
                    className="leads-month-header"
                    onClick={() => setExpandedLeadMonths(prev => ({
                      ...prev,
                      [monthKey]: !prev[monthKey]
                    }))}
                  >
                    <span className="expand-icon">{isExpanded ? '▼' : '▶'}</span>
                    <span className="month-name">{monthName}</span>
                    <span className="month-total">{monthLeads.length} lead{monthLeads.length !== 1 ? 's' : ''}</span>
                  </div>
                  {isExpanded && (
                    <div className="leads-month-content">
                      {monthLeads.map(lead => (
                        <div
                          key={lead.id}
                          className={`booking-card ${expandedLeadId === lead.id ? 'expanded' : ''}`}
                        >
                          <div
                            className="booking-card-header booking-header-stacked"
                            onClick={() => setExpandedLeadId(expandedLeadId === lead.id ? null : lead.id)}
                          >
                            <div className="booking-header-info">
                              <div className="booking-header-top">
                                <span className="booking-customer-name">
                                  {lead.first_name} {lead.last_name}
                                </span>
                                {lead.booking_attempts > 0 && (
                                  <span className="booking-source-badge manual">
                                    {lead.booking_attempts} attempt{lead.booking_attempts > 1 ? 's' : ''}
                                  </span>
                                )}
                              </div>
                              <span className="booking-date">
                                {lead.created_at ? new Date(lead.created_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London' }) : 'Unknown'}
                              </span>
                            </div>
                          </div>

                          {expandedLeadId === lead.id && (
                            <div className="booking-card-body">
                              <div className="booking-section">
                                <h4>Contact Details</h4>
                                <div className="booking-section-content">
                                  <div className="booking-detail-row">
                                    <div className="booking-detail">
                                      <span className="detail-label">Email</span>
                                      <span className="detail-value">
                                        <a href={`mailto:${lead.email}`}>{lead.email}</a>
                                      </span>
                                    </div>
                                    <div className="booking-detail">
                                      <span className="detail-label">Phone</span>
                                      <span className="detail-value">
                                        <a href={`tel:${lead.phone}`}>{lead.phone}</a>
                                      </span>
                                    </div>
                                  </div>
                                </div>
                              </div>

                              {(lead.billing_address1 || lead.billing_city || lead.billing_postcode) && (
                                <div className="booking-section">
                                  <h4>Billing Address</h4>
                                  <div className="booking-section-content">
                                    <div className="booking-detail">
                                      <span className="detail-value">
                                        {[lead.billing_address1, lead.billing_city, lead.billing_postcode].filter(Boolean).join(', ')}
                                      </span>
                                    </div>
                                  </div>
                                </div>
                              )}

                              <div className="booking-section">
                                <h4>Status</h4>
                                <div className="booking-section-content">
                                  <div className="booking-detail-row">
                                    <div className="booking-detail">
                                      <span className="detail-label">Started</span>
                                      <span className="detail-value">
                                        {lead.created_at ? new Date(lead.created_at).toLocaleString('en-GB', { timeZone: 'Europe/London' }) : 'Unknown'}
                                      </span>
                                    </div>
                                    {lead.last_booking_status && (
                                      <div className="booking-detail">
                                        <span className="detail-label">Last Booking Status</span>
                                        <span className="detail-value">{lead.last_booking_status}</span>
                                      </div>
                                    )}
                                    <div className="booking-detail">
                                      <span className="detail-label">Founder Email</span>
                                      <span className="detail-value">
                                        <button
                                          className={`action-btn email-btn ${lead.founder_followup_sent ? 'sent-status' : ''}`}
                                          disabled={true}
                                          title={lead.founder_followup_sent
                                            ? `Sent on ${lead.founder_followup_sent_at ? new Date(lead.founder_followup_sent_at).toLocaleString('en-GB', { timeZone: 'Europe/London' }) : 'Unknown'}`
                                            : 'Not sent yet'}
                                        >
                                          {lead.founder_followup_sent ? 'Sent ✓' : 'Not Sent'}
                                        </button>
                                      </span>
                                    </div>
                                  </div>
                                </div>
                              </div>
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
        </div>
      )}
    </div>
  )
}

export default LeadsSection
