import { useState, useEffect, useMemo } from 'react'
import { useAuth } from '../../AuthContext'
import { API_URL, isTestEmail, formatDateDisplay } from '../adminUtils'
import '../adminStyles.css'

function BookingsPage() {
  const { token } = useAuth()

  const [bookings, setBookings] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [hideTestEmails, setHideTestEmails] = useState(true)
  const [sortAsc, setSortAsc] = useState(true)

  useEffect(() => {
    if (token) fetchBookings()
  }, [token])

  const fetchBookings = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${API_URL}/api/admin/bookings`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        const data = await response.json()
        setBookings(data.bookings || [])
      } else {
        setError('Failed to load bookings')
      }
    } catch (err) {
      setError('Network error loading bookings')
    } finally {
      setLoading(false)
    }
  }

  const filteredBookings = useMemo(() => {
    let filtered = bookings

    // Filter by search term
    if (searchTerm) {
      const term = searchTerm.toLowerCase()
      filtered = filtered.filter(b =>
        (b.reference || '').toLowerCase().includes(term) ||
        (b.customer?.first_name || '').toLowerCase().includes(term) ||
        (b.customer?.last_name || '').toLowerCase().includes(term) ||
        (b.customer?.email || '').toLowerCase().includes(term) ||
        (b.vehicle_registration || '').toLowerCase().includes(term)
      )
    }

    // Filter by status
    if (statusFilter !== 'all') {
      filtered = filtered.filter(b => (b.status || '').toLowerCase() === statusFilter)
    }

    // Filter out test emails
    if (hideTestEmails) {
      filtered = filtered.filter(b => !isTestEmail(b.customer?.email))
    }

    // Sort by dropoff date
    filtered.sort((a, b) => {
      const dateA = new Date(a.dropoff_date)
      const dateB = new Date(b.dropoff_date)
      return sortAsc ? dateA - dateB : dateB - dateA
    })

    return filtered
  }, [bookings, searchTerm, statusFilter, hideTestEmails, sortAsc])

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h2>Bookings</h2>
        <button className="btn-secondary" onClick={fetchBookings} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {error && <div className="admin-error">{error}</div>}

      <div className="admin-filters">
        <div className="admin-search">
          <input
            type="text"
            className="admin-search-input"
            placeholder="Search by reference, name, email, or registration..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          {searchTerm && (
            <button className="admin-search-clear" onClick={() => setSearchTerm('')}>&times;</button>
          )}
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="admin-select"
        >
          <option value="all">All Statuses</option>
          <option value="pending">Pending</option>
          <option value="confirmed">Confirmed</option>
          <option value="completed">Completed</option>
          <option value="cancelled">Cancelled</option>
          <option value="refunded">Refunded</option>
        </select>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={hideTestEmails}
            onChange={(e) => setHideTestEmails(e.target.checked)}
          />
          Hide test emails
        </label>
        <button
          className="btn-secondary btn-sm"
          onClick={() => setSortAsc(!sortAsc)}
          title={sortAsc ? 'Sorted by drop-off date (earliest first)' : 'Sorted by drop-off date (latest first)'}
        >
          Drop-off {sortAsc ? '↑' : '↓'}
        </button>
        <span className="admin-filter-count">
          Showing {filteredBookings.length} of {bookings.length} bookings
        </span>
      </div>

      {loading ? (
        <div className="admin-loading-inline">Loading bookings...</div>
      ) : filteredBookings.length === 0 ? (
        <p className="admin-empty">
          {bookings.length === 0 ? 'No bookings found' : 'No bookings match your search'}
        </p>
      ) : (
        <div className="admin-table-container">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Reference</th>
                <th>Customer</th>
                <th>Drop-off</th>
                <th>Pickup</th>
                <th>Vehicle</th>
                <th>Status</th>
                <th>Amount</th>
              </tr>
            </thead>
            <tbody>
              {filteredBookings.slice(0, 50).map(booking => (
                <tr key={booking.id}>
                  <td><strong>{booking.reference}</strong></td>
                  <td>
                    {booking.customer?.first_name} {booking.customer?.last_name}
                    <br />
                    <small style={{ color: '#666' }}>{booking.customer?.email}</small>
                  </td>
                  <td>{formatDateDisplay(booking.dropoff_date)}</td>
                  <td>{formatDateDisplay(booking.pickup_date)}</td>
                  <td>{booking.vehicle_registration || '-'}</td>
                  <td>
                    <span className={`status-badge status-${(booking.status || 'pending').toLowerCase()}`}>
                      {booking.status || 'Pending'}
                    </span>
                  </td>
                  <td>{booking.total_price ? `£${booking.total_price}` : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {filteredBookings.length > 50 && (
            <p style={{ textAlign: 'center', color: '#666', marginTop: '20px' }}>
              Showing first 50 of {filteredBookings.length} bookings
            </p>
          )}
        </div>
      )}

      <style>{`
        .status-badge {
          display: inline-block;
          padding: 4px 8px;
          border-radius: 4px;
          font-size: 12px;
          font-weight: 500;
        }
        .status-confirmed { background: #d4edda; color: #155724; }
        .status-completed { background: #e2e3e5; color: #383d41; }
        .status-pending { background: #fff3cd; color: #856404; }
        .status-cancelled { background: #f8d7da; color: #721c24; }
        .status-refunded { background: #d1ecf1; color: #0c5460; }
        .checkbox-label {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 14px;
          cursor: pointer;
        }
      `}</style>
    </div>
  )
}

export default BookingsPage
