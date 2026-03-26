import { useState, useEffect } from 'react'
import { useAuth } from '../../AuthContext'
import { API_URL } from '../adminUtils'
import '../adminStyles.css'

function QAPage() {
  const { token } = useAuth()
  const [testResults, setTestResults] = useState([])
  const [latestRun, setLatestRun] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (token) fetchTestResults()
  }, [token])

  const fetchTestResults = async () => {
    setLoading(true)
    try {
      const [resultsRes, latestRes] = await Promise.all([
        fetch(`${API_URL}/api/admin/test-results?limit=20`, {
          headers: { 'Authorization': `Bearer ${token}` }
        }),
        fetch(`${API_URL}/api/admin/test-results/latest?environment=production`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
      ])
      if (resultsRes.ok) {
        const data = await resultsRes.json()
        setTestResults(data.test_runs || [])
      }
      if (latestRes.ok) {
        const data = await latestRes.json()
        setLatestRun(data.test_run)
      }
    } catch (err) {
      console.error('Failed to fetch test results:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h2>QA Dashboard</h2>
        <button className="btn-secondary" onClick={fetchTestResults} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {/* Latest Run Summary */}
      {latestRun && (
        <div style={{
          background: latestRun.passed === latestRun.total ? '#d4edda' : '#fff3cd',
          padding: '20px',
          borderRadius: '8px',
          marginBottom: '20px'
        }}>
          <h3 style={{ margin: '0 0 10px 0' }}>Latest Production Run</h3>
          <div style={{ display: 'flex', gap: '30px', flexWrap: 'wrap' }}>
            <div>
              <strong>Status:</strong> {latestRun.passed === latestRun.total ? 'All Passed' : 'Some Failed'}
            </div>
            <div>
              <strong>Passed:</strong> {latestRun.passed} / {latestRun.total}
            </div>
            <div>
              <strong>Run at:</strong> {new Date(latestRun.timestamp).toLocaleString('en-GB')}
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="admin-loading-inline">Loading test results...</div>
      ) : testResults.length === 0 ? (
        <p className="admin-empty">No test results found</p>
      ) : (
        <div className="admin-table-container">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Environment</th>
                <th>Passed</th>
                <th>Failed</th>
                <th>Total</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {testResults.map(run => (
                <tr key={run.id}>
                  <td>{new Date(run.timestamp).toLocaleString('en-GB')}</td>
                  <td>{run.environment}</td>
                  <td style={{ color: '#28a745' }}>{run.passed}</td>
                  <td style={{ color: run.failed > 0 ? '#dc3545' : '#666' }}>{run.failed}</td>
                  <td>{run.total}</td>
                  <td>
                    <span style={{
                      padding: '4px 8px',
                      borderRadius: '4px',
                      fontSize: '12px',
                      background: run.passed === run.total ? '#d4edda' : '#f8d7da',
                      color: run.passed === run.total ? '#155724' : '#721c24'
                    }}>
                      {run.passed === run.total ? 'Passed' : 'Failed'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default QAPage
