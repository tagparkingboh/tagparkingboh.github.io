import { useState, useEffect } from 'react'
import { useAuth } from '../../AuthContext'
import { API_URL, formatMarketingSource } from '../adminUtils'
import '../adminStyles.css'

function SourcesPage() {
  const { token } = useAuth()
  const [sourcesData, setSourcesData] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (token) fetchSources()
  }, [token])

  const fetchSources = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/marketing-sources/summary`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        const data = await response.json()
        setSourcesData(data)
      }
    } catch (err) {
      console.error('Failed to fetch sources:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h2>Marketing Sources</h2>
        <button className="btn-secondary" onClick={fetchSources} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {loading ? (
        <div className="admin-loading-inline">Loading sources...</div>
      ) : !sourcesData ? (
        <p className="admin-empty">No data available</p>
      ) : (
        <>
          {/* Summary */}
          <div style={{ display: 'flex', gap: '20px', marginBottom: '20px', flexWrap: 'wrap' }}>
            {sourcesData.summary?.map(item => (
              <div key={item.source} style={{
                background: '#f5f5f5',
                padding: '15px 20px',
                borderRadius: '8px',
                minWidth: '120px'
              }}>
                <div style={{ fontSize: '24px', fontWeight: '600', color: '#333' }}>{item.count}</div>
                <div style={{ fontSize: '14px', color: '#666' }}>{formatMarketingSource(item.source)}</div>
              </div>
            ))}
          </div>

          {/* Monthly Breakdown */}
          {sourcesData.monthly && sourcesData.monthly.length > 0 && (
            <div className="admin-table-container">
              <h3 style={{ marginBottom: '15px' }}>Monthly Breakdown</h3>
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Month</th>
                    {Object.keys(sourcesData.monthly[0] || {}).filter(k => k !== 'month').map(source => (
                      <th key={source}>{formatMarketingSource(source)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sourcesData.monthly.map(row => (
                    <tr key={row.month}>
                      <td><strong>{row.month}</strong></td>
                      {Object.entries(row).filter(([k]) => k !== 'month').map(([source, count]) => (
                        <td key={source}>{count}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default SourcesPage
