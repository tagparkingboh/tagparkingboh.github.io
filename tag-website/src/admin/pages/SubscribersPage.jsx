import { useState, useEffect, useMemo } from 'react'
import { useAuth } from '../../AuthContext'
import { API_URL, isTestEmail } from '../adminUtils'
import '../adminStyles.css'

function SubscribersPage() {
  const { token } = useAuth()
  const [subscribers, setSubscribers] = useState([])
  const [loading, setLoading] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [hideTestEmails, setHideTestEmails] = useState(true)

  useEffect(() => {
    if (token) fetchSubscribers()
  }, [token])

  const fetchSubscribers = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/marketing-subscribers`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        const data = await response.json()
        setSubscribers(data.subscribers || [])
      }
    } catch (err) {
      console.error('Failed to fetch subscribers:', err)
    } finally {
      setLoading(false)
    }
  }

  const filteredSubscribers = useMemo(() => {
    let filtered = subscribers

    if (searchTerm) {
      const term = searchTerm.toLowerCase()
      filtered = filtered.filter(s =>
        (s.first_name || '').toLowerCase().includes(term) ||
        (s.last_name || '').toLowerCase().includes(term) ||
        (s.email || '').toLowerCase().includes(term)
      )
    }

    if (hideTestEmails) {
      filtered = filtered.filter(s => !isTestEmail(s.email))
    }

    return filtered
  }, [subscribers, searchTerm, hideTestEmails])

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h2>Marketing Subscribers</h2>
        <button className="btn-secondary" onClick={fetchSubscribers} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      <div className="admin-filters">
        <div className="admin-search">
          <input
            type="text"
            className="admin-search-input"
            placeholder="Search by name or email..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          {searchTerm && (
            <button className="admin-search-clear" onClick={() => setSearchTerm('')}>&times;</button>
          )}
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '14px' }}>
          <input
            type="checkbox"
            checked={hideTestEmails}
            onChange={(e) => setHideTestEmails(e.target.checked)}
          />
          Hide test emails
        </label>
        <span className="admin-filter-count">{filteredSubscribers.length} subscribers</span>
      </div>

      {loading ? (
        <div className="admin-loading-inline">Loading subscribers...</div>
      ) : filteredSubscribers.length === 0 ? (
        <p className="admin-empty">No subscribers found</p>
      ) : (
        <div className="admin-table-container">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Status</th>
                <th>Subscribed</th>
              </tr>
            </thead>
            <tbody>
              {filteredSubscribers.slice(0, 50).map(sub => (
                <tr key={sub.id}>
                  <td>{sub.first_name} {sub.last_name}</td>
                  <td>{sub.email}</td>
                  <td>
                    <span style={{
                      padding: '4px 8px',
                      borderRadius: '4px',
                      fontSize: '12px',
                      background: sub.is_active ? '#d4edda' : '#f8d7da',
                      color: sub.is_active ? '#155724' : '#721c24'
                    }}>
                      {sub.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td>{sub.created_at ? new Date(sub.created_at).toLocaleDateString('en-GB') : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default SubscribersPage
