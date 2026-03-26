import { useState, useEffect } from 'react'
import { useAuth } from '../../AuthContext'
import { API_URL } from '../adminUtils'
import '../adminStyles.css'

function PopularRoutesPage() {
  const { token } = useAuth()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [top, setTop] = useState(10)

  useEffect(() => {
    if (token) fetchPopular()
  }, [token, top])

  const fetchPopular = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/reports/popular?top=${top}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        const result = await response.json()
        setData(result)
      }
    } catch (err) {
      console.error('Failed to fetch popular:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h2>Popular Routes</h2>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <select value={top} onChange={(e) => setTop(Number(e.target.value))} className="admin-select">
            <option value={5}>Top 5</option>
            <option value={10}>Top 10</option>
            <option value={20}>Top 20</option>
          </select>
          <button className="btn-secondary" onClick={fetchPopular} disabled={loading}>
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="admin-loading-inline">Loading popular routes...</div>
      ) : !data ? (
        <p className="admin-empty">No data available</p>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '20px' }}>
          {/* Airlines */}
          {data.airlines && data.airlines.length > 0 && (
            <div>
              <h3 style={{ marginBottom: '15px' }}>Top Airlines</h3>
              <div className="admin-table-container">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Airline</th>
                      <th>Bookings</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.airlines.map((item, idx) => (
                      <tr key={item.airline}>
                        <td>{idx + 1}</td>
                        <td><strong>{item.airline}</strong></td>
                        <td>{item.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Destinations */}
          {data.destinations && data.destinations.length > 0 && (
            <div>
              <h3 style={{ marginBottom: '15px' }}>Top Destinations</h3>
              <div className="admin-table-container">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Destination</th>
                      <th>Bookings</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.destinations.map((item, idx) => (
                      <tr key={item.destination}>
                        <td>{idx + 1}</td>
                        <td><strong>{item.destination}</strong></td>
                        <td>{item.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default PopularRoutesPage
