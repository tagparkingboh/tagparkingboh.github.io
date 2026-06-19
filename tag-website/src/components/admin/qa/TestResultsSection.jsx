function TestResultsSection({
  loadingTestResults,
  fetchTestResults,
  latestTestRun,
  testResults,
}) {
  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2>Test Results</h2>
        <button onClick={fetchTestResults} className="admin-refresh" disabled={loadingTestResults}>
          {loadingTestResults ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {loadingTestResults ? (
        <div className="admin-loading-inline">
          <div className="spinner-small"></div>
          <span>Loading test results...</span>
        </div>
      ) : (
        <>
          <div className="qa-schedule-info">
            <h4>Scheduled Tests</h4>
            <p>Automated tests run 4 times per week:</p>
            <ul>
              <li>Monday at 5:00 AM UTC</li>
              <li>Wednesday at 5:00 AM UTC</li>
              <li>Friday at 5:00 AM UTC</li>
              <li>Saturday at 5:00 AM UTC</li>
            </ul>
            <p>Tests are run against the <strong>production</strong> environment.</p>
          </div>

          {latestTestRun && (
            <div className="qa-latest-run">
              <h4>Latest Test Run</h4>
              <div className="stats-summary-cards">
                <div className={`stats-card ${latestTestRun.status === 'passed' ? 'status-confirmed' : latestTestRun.status === 'failed' ? 'status-cancelled' : 'status-pending'}`}>
                  <div className="stats-card-value" style={{ textTransform: 'uppercase' }}>
                    {latestTestRun.status}
                  </div>
                  <div className="stats-card-label">Status</div>
                </div>
                <div className="stats-card">
                  <div className="stats-card-value" style={{ color: '#22c55e' }}>{latestTestRun.tests_passed}</div>
                  <div className="stats-card-label">Passed</div>
                </div>
                <div className="stats-card">
                  <div className="stats-card-value" style={{ color: latestTestRun.tests_failed > 0 ? '#ef4444' : '#22c55e' }}>{latestTestRun.tests_failed}</div>
                  <div className="stats-card-label">Failed</div>
                </div>
                <div className="stats-card">
                  <div className="stats-card-value">{latestTestRun.tests_skipped}</div>
                  <div className="stats-card-label">Skipped</div>
                </div>
                <div className="stats-card">
                  <div className="stats-card-value">{latestTestRun.pass_rate?.toFixed(1) || 0}%</div>
                  <div className="stats-card-label">Pass Rate</div>
                </div>
                {latestTestRun.coverage_percent !== null && (
                  <div className="stats-card">
                    <div className="stats-card-value">{latestTestRun.coverage_percent?.toFixed(1)}%</div>
                    <div className="stats-card-label">Coverage</div>
                  </div>
                )}
              </div>
              <div className="qa-run-details">
                <p><strong>Environment:</strong> {latestTestRun.environment}</p>
                <p><strong>Run Type:</strong> {latestTestRun.run_type}</p>
                <p><strong>Duration:</strong> {latestTestRun.duration_seconds ? `${latestTestRun.duration_seconds}s` : 'N/A'}</p>
                <p><strong>Started:</strong> {new Date(latestTestRun.started_at).toLocaleString()}</p>
                {latestTestRun.branch && <p><strong>Branch:</strong> {latestTestRun.branch}</p>}
                {latestTestRun.commit_sha && <p><strong>Commit:</strong> {latestTestRun.commit_sha.substring(0, 7)}</p>}
                {latestTestRun.logs_url && (
                  <p><a href={latestTestRun.logs_url} target="_blank" rel="noopener noreferrer" className="admin-link">View Logs</a></p>
                )}
              </div>
            </div>
          )}

          <div className="qa-history">
            <h4>Test Run History</h4>
            {testResults.length === 0 ? (
              <p className="admin-empty">No test runs recorded yet.</p>
            ) : (
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Status</th>
                    <th>Passed</th>
                    <th>Failed</th>
                    <th>Total</th>
                    <th>Pass Rate</th>
                    <th>Coverage</th>
                    <th>Duration</th>
                    <th>Branch</th>
                    <th>Logs</th>
                  </tr>
                </thead>
                <tbody>
                  {testResults.map((run) => (
                    <tr key={run.id} className={run.status === 'failed' ? 'row-warning' : ''}>
                      <td>{new Date(run.started_at).toLocaleDateString()}</td>
                      <td>
                        <span className={`status-badge status-${run.status === 'passed' ? 'confirmed' : run.status === 'failed' ? 'cancelled' : 'pending'}`}>
                          {run.status}
                        </span>
                      </td>
                      <td style={{ color: '#22c55e' }}>{run.tests_passed}</td>
                      <td style={{ color: run.tests_failed > 0 ? '#ef4444' : '#22c55e' }}>{run.tests_failed}</td>
                      <td>{run.tests_total}</td>
                      <td>{run.pass_rate?.toFixed(1) || 0}%</td>
                      <td>{run.coverage_percent !== null ? `${run.coverage_percent?.toFixed(1)}%` : '-'}</td>
                      <td>{run.duration_seconds ? `${run.duration_seconds}s` : '-'}</td>
                      <td>{run.branch || '-'}</td>
                      <td>
                        {run.logs_url ? (
                          <a href={run.logs_url} target="_blank" rel="noopener noreferrer" className="admin-link">View</a>
                        ) : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default TestResultsSection
