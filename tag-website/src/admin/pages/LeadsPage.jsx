import { useState, useEffect, useMemo } from 'react'
import { useAuth } from '../../AuthContext'
import { API_URL, isTestEmail, formatDateDisplay } from '../adminUtils'
import '../adminStyles.css'

function LeadsPage() {
  const { token } = useAuth()
  const [leads, setLeads] = useState([])
  const [loading, setLoading] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [hideTestEmails, setHideTestEmails] = useState(true)

  useEffect(() => {
    if (token) fetchLeads()
  }, [token])

  const fetchLeads = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/abandoned-leads`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        const data = await response.json()
        setLeads(data.leads || [])
      }
    } catch (err) {
      console.error('Failed to fetch leads:', err)
    } finally {
      setLoading(false)
    }
  }

  const filteredLeads = useMemo(() => {
    let filtered = leads

    if (searchTerm) {
      const term = searchTerm.toLowerCase()
      filtered = filtered.filter(l =>
        (l.first_name || '').toLowerCase().includes(term) ||
        (l.last_name || '').toLowerCase().includes(term) ||
        (l.email || '').toLowerCase().includes(term)
      )
    }

    if (hideTestEmails) {
      filtered = filtered.filter(l => !isTestEmail(l.email))
    }

    return filtered
  }, [leads, searchTerm, hideTestEmails])

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h2>Abandoned Leads</h2>
        <button className="btn-secondary" onClick={fetchLeads} disabled={loading}>
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
        <span className="admin-filter-count">{filteredLeads.length} leads</span>
      </div>

      {loading ? (
        <div className="admin-loading-inline">Loading leads...</div>
      ) : filteredLeads.length === 0 ? (
        <p className="admin-empty">No leads found</p>
      ) : (
        <div className="admin-table-container">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Drop-off</th>
                <th>Pickup</th>
                <th>Step</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {filteredLeads.slice(0, 50).map(lead => (
                <tr key={lead.id}>
                  <td>{lead.first_name} {lead.last_name}</td>
                  <td>{lead.email}</td>
                  <td>{formatDateDisplay(lead.dropoff_date)}</td>
                  <td>{formatDateDisplay(lead.pickup_date)}</td>
                  <td>{lead.abandoned_step || '-'}</td>
                  <td>{formatDateDisplay(lead.created_at?.split('T')[0])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default LeadsPage
