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

const formatEventData = (value) => {
  if (typeof value === 'string') {
    try {
      return JSON.parse(value || '{}')
    } catch {
      return {}
    }
  }
  return value || {}
}

const ErrorLogsSection = ({
  errorLogs,
  loadingErrorLogs,
  errorLogsTotalCount,
  fetchErrorLogs,
  errorLogsFilters,
  setErrorLogsFilters,
  errorSeverities,
  errorTypes,
  expandedErrorLog,
  setExpandedErrorLog,
  errorLogsOffset,
  setErrorLogsOffset,
}) => {
  const safeFilters = errorLogsFilters || {
    search: '',
    booking_reference: '',
    severity: '',
    error_type: '',
    date_from: '',
    date_to: '',
  }

  const clearFilters = () => setErrorLogsFilters({
    search: '',
    booking_reference: '',
    severity: '',
    error_type: '',
    date_from: '',
    date_to: '',
  })

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2>Error Logs</h2>
        <button onClick={() => fetchErrorLogs(true)} className="admin-refresh" disabled={loadingErrorLogs}>
          {loadingErrorLogs ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      <div className="qa-logs-filters">
        <input
          type="text"
          placeholder="Search (message, endpoint, session)..."
          value={safeFilters.search}
          onChange={(e) => setErrorLogsFilters({ ...safeFilters, search: e.target.value })}
          className="admin-filter-input"
        />
        <input
          type="text"
          placeholder="Booking Reference..."
          value={safeFilters.booking_reference}
          onChange={(e) => setErrorLogsFilters({ ...safeFilters, booking_reference: e.target.value })}
          className="admin-filter-input"
        />
        <select
          value={safeFilters.severity}
          onChange={(e) => setErrorLogsFilters({ ...safeFilters, severity: e.target.value })}
          className="admin-filter-select"
        >
          <option value="">All Severities</option>
          {(errorSeverities || []).map((sev) => (
            <option key={sev} value={sev}>{sev}</option>
          ))}
        </select>
        <select
          value={safeFilters.error_type}
          onChange={(e) => setErrorLogsFilters({ ...safeFilters, error_type: e.target.value })}
          className="admin-filter-select"
        >
          <option value="">All Types</option>
          {(errorTypes || []).map((type) => (
            <option key={type} value={type}>{type}</option>
          ))}
        </select>
        <input
          type="text"
          placeholder="From: DD/MM/YYYY HH:MM"
          value={safeFilters.date_from}
          onChange={(e) => setErrorLogsFilters({ ...safeFilters, date_from: e.target.value })}
          className="admin-filter-input datetime-uk"
          title="From Date (UK timezone)"
        />
        <input
          type="text"
          placeholder="To: DD/MM/YYYY HH:MM"
          value={safeFilters.date_to}
          onChange={(e) => setErrorLogsFilters({ ...safeFilters, date_to: e.target.value })}
          className="admin-filter-input datetime-uk"
          title="To Date (UK timezone)"
        />
        <button onClick={clearFilters} className="admin-btn">
          Clear
        </button>
      </div>

      <p className="qa-logs-count">Showing {errorLogs.length} of {errorLogsTotalCount} logs</p>

      {loadingErrorLogs ? (
        <div className="admin-loading-inline">
          <div className="spinner-small"></div>
          <span>Loading error logs...</span>
        </div>
      ) : errorLogs.length === 0 ? (
        <p className="admin-empty">No error logs found.</p>
      ) : (
        <>
          <table className="admin-table qa-logs-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Severity</th>
                <th>Type</th>
                <th>Message</th>
                <th>Booking Ref</th>
              </tr>
            </thead>
            <tbody>
              {errorLogs.map((log) => {
                const isExpanded = expandedErrorLog === log.id
                const payload = formatEventData(log.request_data)
                return (
                  <Fragment key={log.id}>
                    <tr onClick={() => setExpandedErrorLog(isExpanded ? null : log.id)} className={`qa-log-row qa-severity-${log.severity}`}>
                      <td>{formatUkLogTime(log.created_at)}</td>
                      <td><span className={`qa-severity-badge qa-severity-${log.severity}`}>{log.severity}</span></td>
                      <td>{log.error_type || '-'}</td>
                      <td className="qa-message-cell">{log.message ? (log.message.length > 80 ? log.message.substring(0, 80) + '...' : log.message) : '-'}</td>
                      <td>{log.booking_reference || '-'}</td>
                    </tr>
                    {isExpanded && (
                      <tr className="qa-log-expanded">
                        <td colSpan="5">
                          <div className="qa-log-details">
                            <p><strong>Full Message:</strong></p>
                            <pre>{log.message}</pre>
                            {log.stack_trace && (
                              <>
                                <p><strong>Stack Trace:</strong></p>
                                <pre className="qa-stack-trace">{log.stack_trace}</pre>
                              </>
                            )}
                            {log.endpoint && <p><strong>Endpoint:</strong> {log.endpoint}</p>}
                            {log.error_code && <p><strong>Error Code:</strong> {log.error_code}</p>}
                            {log.session_id && <p><strong>Session:</strong> {log.session_id}</p>}
                            {log.ip_address && <p><strong>IP:</strong> {log.ip_address}</p>}
                            {log.request_data && (
                              <>
                                <p><strong>Request Data:</strong></p>
                                <pre>{typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2)}</pre>
                              </>
                            )}
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
                const newOffset = Math.max(0, errorLogsOffset - 50)
                setErrorLogsOffset(newOffset)
                fetchErrorLogs(false, newOffset)
              }}
              disabled={errorLogsOffset === 0 || loadingErrorLogs}
              className="admin-btn"
            >
              Previous
            </button>
            <span>Page {Math.floor(errorLogsOffset / 50) + 1} of {Math.ceil(errorLogsTotalCount / 50)}</span>
            <button
              onClick={() => {
                const newOffset = errorLogsOffset + 50
                setErrorLogsOffset(newOffset)
                fetchErrorLogs(false, newOffset)
              }}
              disabled={errorLogsOffset + 50 >= errorLogsTotalCount || loadingErrorLogs}
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

export default ErrorLogsSection
