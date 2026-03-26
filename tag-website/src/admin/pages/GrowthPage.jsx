import { useState, useEffect } from 'react'
import { useAuth } from '../../AuthContext'
import { API_URL } from '../adminUtils'
import '../adminStyles.css'

function GrowthPage() {
  const { token } = useAuth()
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (token) fetchStats()
  }, [token])

  const fetchStats = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/stats`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        const data = await response.json()
        setStats(data)
      }
    } catch (err) {
      console.error('Failed to fetch stats:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h2>Growth Reports</h2>
        <button className="btn-secondary" onClick={fetchStats} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {loading ? (
        <div className="admin-loading-inline">Loading stats...</div>
      ) : !stats ? (
        <p className="admin-empty">No data available</p>
      ) : (
        <>
          {/* Summary Cards */}
          <div style={{ display: 'flex', gap: '20px', marginBottom: '30px', flexWrap: 'wrap' }}>
            <div style={{ background: '#e3f2fd', padding: '20px', borderRadius: '8px', flex: '1', minWidth: '150px' }}>
              <div style={{ fontSize: '32px', fontWeight: '600', color: '#1976d2' }}>{stats.total_bookings || 0}</div>
              <div style={{ color: '#666' }}>Total Bookings</div>
            </div>
            <div style={{ background: '#e8f5e9', padding: '20px', borderRadius: '8px', flex: '1', minWidth: '150px' }}>
              <div style={{ fontSize: '32px', fontWeight: '600', color: '#388e3c' }}>{stats.confirmed_bookings || 0}</div>
              <div style={{ color: '#666' }}>Confirmed</div>
            </div>
            <div style={{ background: '#fff3e0', padding: '20px', borderRadius: '8px', flex: '1', minWidth: '150px' }}>
              <div style={{ fontSize: '32px', fontWeight: '600', color: '#f57c00' }}>
                {stats.total_revenue ? `£${stats.total_revenue.toLocaleString()}` : '£0'}
              </div>
              <div style={{ color: '#666' }}>Total Revenue</div>
            </div>
          </div>

          {/* Monthly Data */}
          {stats.monthly && stats.monthly.length > 0 && (
            <div className="admin-table-container">
              <h3 style={{ marginBottom: '15px' }}>Monthly Breakdown</h3>
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Month</th>
                    <th>Bookings</th>
                    <th>Revenue</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.monthly.map(row => (
                    <tr key={row.month}>
                      <td><strong>{row.month}</strong></td>
                      <td>{row.count}</td>
                      <td>£{row.revenue?.toLocaleString() || 0}</td>
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

export default GrowthPage
