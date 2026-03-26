import { useState, useEffect, useMemo } from 'react'
import { useAuth } from '../../AuthContext'
import { API_URL, formatMarketingSource, isTestEmail } from '../adminUtils'
import '../adminStyles.css'

function CustomersPage() {
  const { token } = useAuth()
  const [customers, setCustomers] = useState([])
  const [loading, setLoading] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [hideTestEmails, setHideTestEmails] = useState(true)

  useEffect(() => {
    if (token) fetchCustomers()
  }, [token])

  const fetchCustomers = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/customers`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        const data = await response.json()
        setCustomers(data.customers || [])
      }
    } catch (err) {
      console.error('Failed to fetch customers:', err)
    } finally {
      setLoading(false)
    }
  }

  const filteredCustomers = useMemo(() => {
    let filtered = customers

    if (searchTerm) {
      const term = searchTerm.toLowerCase()
      filtered = filtered.filter(c =>
        (c.first_name || '').toLowerCase().includes(term) ||
        (c.last_name || '').toLowerCase().includes(term) ||
        (c.email || '').toLowerCase().includes(term)
      )
    }

    if (hideTestEmails) {
      filtered = filtered.filter(c => !isTestEmail(c.email))
    }

    return filtered
  }, [customers, searchTerm, hideTestEmails])

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h2>Customers</h2>
        <button className="btn-secondary" onClick={fetchCustomers} disabled={loading}>
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
        <span className="admin-filter-count">{filteredCustomers.length} customers</span>
      </div>

      {loading ? (
        <div className="admin-loading-inline">Loading customers...</div>
      ) : filteredCustomers.length === 0 ? (
        <p className="admin-empty">No customers found</p>
      ) : (
        <div className="admin-table-container">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Phone</th>
                <th>Bookings</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {filteredCustomers.slice(0, 50).map(customer => (
                <tr key={customer.id}>
                  <td>{customer.first_name} {customer.last_name}</td>
                  <td>{customer.email}</td>
                  <td>{customer.phone || '-'}</td>
                  <td>{customer.booking_count || 0}</td>
                  <td>{formatMarketingSource(customer.marketing_source)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default CustomersPage
