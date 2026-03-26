import { useState, useEffect } from 'react'
import { useAuth } from '../../AuthContext'
import { API_URL } from '../adminUtils'
import '../adminStyles.css'

function OccupancyPage() {
  const { token } = useAuth()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [view, setView] = useState('daily')

  useEffect(() => {
    if (token) fetchOccupancy()
  }, [token, view])

  const fetchOccupancy = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/reports/occupancy?view=${view}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        const result = await response.json()
        setData(result)
      }
    } catch (err) {
      console.error('Failed to fetch occupancy:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h2>Occupancy Report</h2>
        <button className="btn-secondary" onClick={fetchOccupancy} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      <div className="admin-subtabs">
        <button
          className={`admin-subtab ${view === 'daily' ? 'active' : ''}`}
          onClick={() => setView('daily')}
        >
          Daily
        </button>
        <button
          className={`admin-subtab ${view === 'weekly' ? 'active' : ''}`}
          onClick={() => setView('weekly')}
        >
          Weekly
        </button>
        <button
          className={`admin-subtab ${view === 'monthly' ? 'active' : ''}`}
          onClick={() => setView('monthly')}
        >
          Monthly
        </button>
      </div>

      {loading ? (
        <div className="admin-loading-inline">Loading occupancy data...</div>
      ) : !data || !data.data || data.data.length === 0 ? (
        <p className="admin-empty">No occupancy data available</p>
      ) : (
        <div className="admin-table-container">
          <table className="admin-table">
            <thead>
              <tr>
                <th>{view === 'daily' ? 'Date' : view === 'weekly' ? 'Week' : 'Month'}</th>
                <th>Cars</th>
                <th>Capacity</th>
                <th>Occupancy</th>
              </tr>
            </thead>
            <tbody>
              {data.data.slice(0, 50).map((row, idx) => (
                <tr key={idx}>
                  <td><strong>{row.label || row.date || row.week || row.month}</strong></td>
                  <td>{row.cars || row.count || 0}</td>
                  <td>{row.capacity || data.capacity || 50}</td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div style={{
                        width: '100px',
                        height: '8px',
                        background: '#e0e0e0',
                        borderRadius: '4px',
                        overflow: 'hidden'
                      }}>
                        <div style={{
                          width: `${Math.min(100, (row.occupancy_percent || 0))}%`,
                          height: '100%',
                          background: row.occupancy_percent > 80 ? '#dc3545' : row.occupancy_percent > 50 ? '#ffc107' : '#28a745',
                          borderRadius: '4px'
                        }} />
                      </div>
                      <span>{row.occupancy_percent?.toFixed(0) || 0}%</span>
                    </div>
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

export default OccupancyPage
