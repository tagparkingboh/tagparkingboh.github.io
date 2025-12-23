import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from './AuthContext'
import './Admin.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function Admin() {
  const { user, token, loading, isAuthenticated, isAdmin, logout } = useAuth()
  const navigate = useNavigate()

  const [activeTab, setActiveTab] = useState('bookings')
  const [bookings, setBookings] = useState([])
  const [loadingData, setLoadingData] = useState(false)
  const [error, setError] = useState('')

  // Redirect if not authenticated or not admin
  useEffect(() => {
    if (!loading) {
      if (!isAuthenticated) {
        navigate('/login?redirect=/admin', { replace: true })
      } else if (!isAdmin) {
        navigate('/employee', { replace: true })
      }
    }
  }, [loading, isAuthenticated, isAdmin, navigate])

  // Fetch bookings when tab is active
  useEffect(() => {
    if (activeTab === 'bookings' && token) {
      fetchBookings()
    }
  }, [activeTab, token])

  const fetchBookings = async () => {
    setLoadingData(true)
    setError('')
    try {
      const response = await fetch(`${API_URL}/api/admin/bookings`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setBookings(data.bookings || data || [])
      } else {
        setError('Failed to load bookings')
      }
    } catch (err) {
      setError('Network error')
    } finally {
      setLoadingData(false)
    }
  }

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  if (loading) {
    return (
      <div className="admin-loading">
        <div className="spinner"></div>
        <p>Loading...</p>
      </div>
    )
  }

  if (!isAuthenticated || !isAdmin) {
    return null
  }

  return (
    <div className="admin-container">
      <header className="admin-header">
        <div className="admin-header-left">
          <img src="/images/tag-logo.png" alt="TAG Parking" className="admin-logo" />
          <h1>Admin Dashboard</h1>
        </div>
        <div className="admin-header-right">
          <span className="admin-user">
            {user?.first_name} {user?.last_name}
          </span>
          <button onClick={handleLogout} className="admin-logout">
            Logout
          </button>
        </div>
      </header>

      <nav className="admin-nav">
        <button
          className={`admin-nav-item ${activeTab === 'bookings' ? 'active' : ''}`}
          onClick={() => setActiveTab('bookings')}
        >
          Bookings
        </button>
        <button
          className={`admin-nav-item ${activeTab === 'users' ? 'active' : ''}`}
          onClick={() => setActiveTab('users')}
        >
          Users
        </button>
        <button
          className={`admin-nav-item ${activeTab === 'flights' ? 'active' : ''}`}
          onClick={() => setActiveTab('flights')}
        >
          Flights
        </button>
        <button
          className={`admin-nav-item ${activeTab === 'reports' ? 'active' : ''}`}
          onClick={() => setActiveTab('reports')}
        >
          Reports
        </button>
      </nav>

      <main className="admin-content">
        {error && <div className="admin-error">{error}</div>}

        {activeTab === 'bookings' && (
          <div className="admin-section">
            <div className="admin-section-header">
              <h2>Bookings</h2>
              <button onClick={fetchBookings} className="admin-refresh" disabled={loadingData}>
                {loadingData ? 'Loading...' : 'Refresh'}
              </button>
            </div>
            {loadingData ? (
              <div className="admin-loading-inline">
                <div className="spinner-small"></div>
                <span>Loading bookings...</span>
              </div>
            ) : bookings.length === 0 ? (
              <p className="admin-empty">No bookings found</p>
            ) : (
              <div className="admin-table-container">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>Reference</th>
                      <th>Customer</th>
                      <th>Vehicle</th>
                      <th>Drop-off</th>
                      <th>Pick-up</th>
                      <th>Status</th>
                      <th>Payment</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bookings.map((booking) => (
                      <tr key={booking.id || booking.reference}>
                        <td className="booking-ref">{booking.reference}</td>
                        <td>
                          {booking.customer?.first_name} {booking.customer?.last_name}
                          <br />
                          <span className="small-text">{booking.customer?.email}</span>
                        </td>
                        <td>
                          {booking.vehicle?.registration}
                          <br />
                          <span className="small-text">
                            {booking.vehicle?.make} {booking.vehicle?.model}
                          </span>
                        </td>
                        <td>
                          {booking.dropoff_date}
                          <br />
                          <span className="small-text">{booking.dropoff_time}</span>
                        </td>
                        <td>
                          {booking.pickup_date}
                          <br />
                          <span className="small-text">
                            {booking.pickup_time_from} - {booking.pickup_time_to}
                          </span>
                        </td>
                        <td>
                          <span className={`status-badge status-${booking.status?.toLowerCase()}`}>
                            {booking.status}
                          </span>
                        </td>
                        <td>
                          <span className={`status-badge payment-${booking.payment?.status?.toLowerCase()}`}>
                            {booking.payment?.status || 'N/A'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {activeTab === 'users' && (
          <div className="admin-section">
            <h2>User Management</h2>
            <p className="admin-coming-soon">User management coming soon...</p>
          </div>
        )}

        {activeTab === 'flights' && (
          <div className="admin-section">
            <h2>Flight Schedule</h2>
            <p className="admin-coming-soon">Flight management coming soon...</p>
          </div>
        )}

        {activeTab === 'reports' && (
          <div className="admin-section">
            <h2>Reports</h2>
            <p className="admin-coming-soon">Reports coming soon...</p>
          </div>
        )}
      </main>
    </div>
  )
}

export default Admin
