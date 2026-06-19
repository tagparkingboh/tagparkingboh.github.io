import { Fragment } from 'react'

const formatUkLogTime = (value) => {
  const parsed = new Date(value)
  return `${parsed.toLocaleString('en-GB', {
    timeZone: 'Europe/London',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })} UK`
}

const parseEventData = (raw) => {
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw || '{}')
    } catch (error) {
      return {}
    }
  }
  return raw || {}
}

const AuditLogsSection = ({
  auditLogs,
  loadingAuditLogs,
  auditLogsTotalCount,
  fetchAuditLogs,
  auditLogsFilters,
  setAuditLogsFilters,
  auditEventTypes,
  auditLogsAutoRefresh,
  setAuditLogsAutoRefresh,
  expandedAuditLog,
  setExpandedAuditLog,
  auditLogsOffset,
  setAuditLogsOffset,
}) => {
  const clearFilters = () => setAuditLogsFilters({ search: '', booking_reference: '', event: '', date_from: '', date_to: '' })
  const safeFilters = auditLogsFilters || { search: '', booking_reference: '', event: '', date_from: '', date_to: '' }

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2>Audit Logs</h2>
        <div className="audit-logs-actions">
          <label className="auto-refresh-toggle">
            <span className="toggle-label">Auto-refresh</span>
            <div className="toggle-switch">
              <input
                type="checkbox"
                checked={auditLogsAutoRefresh}
                onChange={(e) => setAuditLogsAutoRefresh(e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </div>
          </label>
          <button onClick={() => fetchAuditLogs(true)} className="admin-refresh" disabled={loadingAuditLogs}>
            {loadingAuditLogs ? 'Loading...' : '↻ Refresh'}
          </button>
        </div>
      </div>

      <div className="qa-logs-filters">
        <input
          type="text"
          placeholder="Search (email, name, session)..."
          value={safeFilters.search}
          onChange={(e) => setAuditLogsFilters({ ...safeFilters, search: e.target.value })}
          className="admin-filter-input"
        />
        <input
          type="text"
          placeholder="Booking Reference..."
          value={safeFilters.booking_reference}
          onChange={(e) => setAuditLogsFilters({ ...safeFilters, booking_reference: e.target.value })}
          className="admin-filter-input"
        />
        <select
          value={safeFilters.event}
          onChange={(e) => setAuditLogsFilters({ ...safeFilters, event: e.target.value })}
          className="admin-filter-select"
        >
          <option value="">All Events</option>
          {(auditEventTypes || []).map((evt) => (
            <option key={evt} value={evt}>{evt}</option>
          ))}
        </select>
        <input
          type="text"
          placeholder="From: DD/MM/YYYY HH:MM"
          value={safeFilters.date_from}
          onChange={(e) => setAuditLogsFilters({ ...safeFilters, date_from: e.target.value })}
          className="admin-filter-input datetime-uk"
          title="From Date (UK timezone)"
        />
        <input
          type="text"
          placeholder="To: DD/MM/YYYY HH:MM"
          value={safeFilters.date_to}
          onChange={(e) => setAuditLogsFilters({ ...safeFilters, date_to: e.target.value })}
          className="admin-filter-input datetime-uk"
          title="To Date"
        />
        <button onClick={clearFilters} className="admin-btn">
          Clear
        </button>
      </div>

      <p className="qa-logs-count">Showing {auditLogs.length} of {auditLogsTotalCount} logs</p>

      {loadingAuditLogs ? (
        <div className="admin-loading-inline">
          <div className="spinner-small"></div>
          <span>Loading audit logs...</span>
        </div>
      ) : auditLogs.length === 0 ? (
        <p className="admin-empty">No audit logs found.</p>
      ) : (
        <>
          <table className="admin-table qa-logs-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Event</th>
                <th>Booking Ref</th>
                <th>Session</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {auditLogs.map((log) => {
                const eventData = parseEventData(log.event_data)
                const email = eventData.customer_email || eventData.email || ''
                const isExpanded = expandedAuditLog === log.id
                return (
                  <Fragment key={log.id}>
                    <tr onClick={() => setExpandedAuditLog(isExpanded ? null : log.id)} className="qa-log-row">
                      <td>{formatUkLogTime(log.created_at)}</td>
                      <td><span className="qa-event-badge">{log.event}</span></td>
                      <td>{log.booking_reference || '-'}</td>
                      <td className="qa-session-cell">{log.session_id ? log.session_id.substring(0, 20) + '...' : '-'}</td>
                      <td>{email || (eventData.amount ? `£${(eventData.amount / 100).toFixed(2)}` : '-')}</td>
                    </tr>
                    {isExpanded && (
                      <tr className="qa-log-expanded">
                        <td colSpan="5">
                          <div className="qa-log-details">
                            <pre>{JSON.stringify(eventData, null, 2)}</pre>
                            {log.ip_address && <p><strong>IP:</strong> {log.ip_address}</p>}
                            {log.user_agent && <p><strong>User Agent:</strong> {log.user_agent}</p>}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>

          <div className="qa-logs-pagination">
            <button
              onClick={() => {
                const newOffset = Math.max(0, auditLogsOffset - 50)
                setAuditLogsOffset(newOffset)
                fetchAuditLogs(false, newOffset)
              }}
              disabled={auditLogsOffset === 0 || loadingAuditLogs}
              className="admin-btn"
            >
              Previous
            </button>
            <span>Page {Math.floor(auditLogsOffset / 50) + 1} of {Math.ceil(auditLogsTotalCount / 50)}</span>
            <button
              onClick={() => {
                const newOffset = auditLogsOffset + 50
                setAuditLogsOffset(newOffset)
                fetchAuditLogs(false, newOffset)
              }}
              disabled={auditLogsOffset + 50 >= auditLogsTotalCount || loadingAuditLogs}
              className="admin-btn"
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  )
}

export default AuditLogsSection
