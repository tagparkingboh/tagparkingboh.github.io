function ConnectionPoolSection({
  loadingDbHealth,
  loadingPoolHistory,
  fetchDbHealth,
  fetchDbPoolHistory,
  dbHealth,
  dbPoolHistory,
}) {
  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2>Connection Pool</h2>
        <button
          onClick={() => {
            fetchDbHealth()
            fetchDbPoolHistory()
          }}
          className="admin-refresh"
          disabled={loadingDbHealth || loadingPoolHistory}
        >
          {loadingDbHealth || loadingPoolHistory ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      <div className="qa-db-health">
        <div className="qa-db-health-header">
          <h4>Database Connection Pool</h4>
          <button onClick={fetchDbHealth} className="admin-refresh-small" disabled={loadingDbHealth}>
            {loadingDbHealth ? '...' : 'Refresh'}
          </button>
        </div>
        {dbHealth ? (
          <div className="stats-summary-cards">
            <div className={`stats-card ${dbHealth.health === 'healthy' ? 'status-confirmed' : dbHealth.health === 'warning' ? 'status-pending' : 'status-cancelled'}`}>
              <div className="stats-card-value" style={{ textTransform: 'uppercase' }}>
                {dbHealth.health}
              </div>
              <div className="stats-card-label">Status</div>
            </div>
            <div className="stats-card">
              <div className="stats-card-value" style={{ color: dbHealth.usage_percent >= 70 ? (dbHealth.usage_percent >= 90 ? '#ef4444' : '#f59e0b') : '#22c55e' }}>
                {dbHealth.usage_percent}%
              </div>
              <div className="stats-card-label">Pool Usage</div>
            </div>
            <div className="stats-card">
              <div className="stats-card-value">{dbHealth.checked_out}</div>
              <div className="stats-card-label">Active</div>
            </div>
            <div className="stats-card">
              <div className="stats-card-value">{dbHealth.overflow}</div>
              <div className="stats-card-label">Overflow</div>
            </div>
            <div className="stats-card">
              <div className="stats-card-value">{dbHealth.max_connections}</div>
              <div className="stats-card-label">Max</div>
            </div>
          </div>
        ) : (
          <p className="admin-empty">Unable to fetch database health</p>
        )}
      </div>

      <div className="qa-history">
        <div className="qa-db-health-header">
          <h4>Connection Pool History</h4>
          <button onClick={() => fetchDbPoolHistory()} className="admin-refresh-small" disabled={loadingPoolHistory}>
            {loadingPoolHistory ? '...' : 'Refresh'}
          </button>
        </div>
        {dbPoolHistory?.circuit_breaker && (
          <div className="circuit-breaker-status" style={{ marginBottom: '16px', padding: '12px', background: '#f8fafc', borderRadius: '6px', fontSize: '13px' }}>
            <strong>Circuit Breaker:</strong>{' '}
            <span style={{
              color: dbPoolHistory.circuit_breaker.state === 'CLOSED' ? '#22c55e' :
                     dbPoolHistory.circuit_breaker.state === 'HALF_OPEN' ? '#f59e0b' : '#ef4444',
              fontWeight: 600
            }}>
              {dbPoolHistory.circuit_breaker.state}
            </span>
            {dbPoolHistory.circuit_breaker.rejected_count > 0 && (
              <span style={{ marginLeft: '16px', color: '#6b7280' }}>
                Rejected: {dbPoolHistory.circuit_breaker.rejected_count} requests
              </span>
            )}
          </div>
        )}
        {!dbPoolHistory || dbPoolHistory.snapshots?.length === 0 ? (
          <p className="admin-empty">No pool history recorded yet. Snapshots are taken every minute.</p>
        ) : (
          <table className="admin-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Status</th>
                <th>Usage</th>
                <th>Active</th>
                <th>Overflow</th>
                <th>Available</th>
                <th>Trigger</th>
              </tr>
            </thead>
            <tbody>
              {dbPoolHistory.snapshots?.slice(0, 50).map((snapshot) => (
                <tr key={snapshot.id} className={snapshot.health_status !== 'healthy' ? 'row-warning' : ''}>
                  <td>{new Date(snapshot.timestamp).toLocaleString()}</td>
                  <td>
                    <span className={`status-badge status-${snapshot.health_status === 'healthy' ? 'confirmed' : snapshot.health_status === 'warning' ? 'pending' : 'cancelled'}`}>
                      {snapshot.health_status}
                    </span>
                  </td>
                  <td style={{ color: snapshot.usage_percent >= 70 ? (snapshot.usage_percent >= 90 ? '#ef4444' : '#f59e0b') : '#22c55e', fontWeight: 600 }}>
                    {snapshot.usage_percent}%
                  </td>
                  <td>{snapshot.checked_out}</td>
                  <td style={{ color: snapshot.overflow > 0 ? '#f59e0b' : 'inherit' }}>{snapshot.overflow}</td>
                  <td>{snapshot.checked_in}</td>
                  <td style={{ fontSize: '12px', color: '#6b7280' }}>{snapshot.trigger}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {dbPoolHistory?.snapshot_count > 50 && (
          <p style={{ fontSize: '12px', color: '#6b7280', marginTop: '8px' }}>
            Showing 50 of {dbPoolHistory.snapshot_count} snapshots from the last 24 hours
          </p>
        )}
      </div>
    </div>
  )
}

export default ConnectionPoolSection
