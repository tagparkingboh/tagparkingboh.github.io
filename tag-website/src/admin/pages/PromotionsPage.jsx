import { useState, useEffect } from 'react'
import { useAuth } from '../../AuthContext'
import { API_URL } from '../adminUtils'
import '../adminStyles.css'

function PromotionsPage() {
  const { token } = useAuth()
  const [promotions, setPromotions] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (token) fetchPromotions()
  }, [token])

  const fetchPromotions = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/promotions`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        const data = await response.json()
        setPromotions(data.promotions || [])
      }
    } catch (err) {
      console.error('Failed to fetch promotions:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h2>Promotions</h2>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button className="btn-secondary" onClick={fetchPromotions} disabled={loading}>
            {loading ? 'Loading...' : 'Refresh'}
          </button>
          <button className="btn-primary">+ Create Promotion</button>
        </div>
      </div>

      {loading ? (
        <div className="admin-loading-inline">Loading promotions...</div>
      ) : promotions.length === 0 ? (
        <p className="admin-empty">No promotions found</p>
      ) : (
        <div className="admin-table-container">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Discount</th>
                <th>Codes</th>
                <th>Used</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {promotions.map(promo => (
                <tr key={promo.id}>
                  <td><strong>{promo.name}</strong></td>
                  <td>{promo.discount_percent}%</td>
                  <td>{promo.total_codes || 0}</td>
                  <td>{promo.used_codes || 0}</td>
                  <td>
                    <span style={{
                      padding: '4px 8px',
                      borderRadius: '4px',
                      fontSize: '12px',
                      background: promo.is_active ? '#d4edda' : '#e2e3e5',
                      color: promo.is_active ? '#155724' : '#383d41'
                    }}>
                      {promo.is_active ? 'Active' : 'Inactive'}
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

export default PromotionsPage
