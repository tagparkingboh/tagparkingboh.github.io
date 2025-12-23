import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from './AuthContext'
import './Employee.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function Employee() {
  const { user, token, loading, isAuthenticated, logout } = useAuth()
  const navigate = useNavigate()

  const [activeTab, setActiveTab] = useState('today')
  const [bookings, setBookings] = useState([])
  const [loadingData, setLoadingData] = useState(false)
  const [error, setError] = useState('')
  const [selectedDate, setSelectedDate] = useState(() => {
    const today = new Date()
    return today.toISOString().split('T')[0]
  })

  // Redirect if not authenticated
  useEffect(() => {
    if (!loading && !isAuthenticated) {
      navigate('/login?redirect=/employee', { replace: true })
    }
  }, [loading, isAuthenticated, navigate])

  // Fetch bookings when date changes
  useEffect(() => {
    if (token && selectedDate) {
      fetchBookingsForDate(selectedDate)
    }
  }, [token, selectedDate])

  const fetchBookingsForDate = async (date) => {
    setLoadingData(true)
    setError('')
    try {
      const response = await fetch(`${API_URL}/api/admin/occupancy/${date}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setBookings(data.bookings || [])
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

  const formatDate = (dateStr) => {
    const date = new Date(dateStr)
    return date.toLocaleDateString('en-GB', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    })
  }

  const goToToday = () => {
    const today = new Date().toISOString().split('T')[0]
    setSelectedDate(today)
    setActiveTab('today')
  }

  const goToPrevDay = () => {
    const current = new Date(selectedDate)
    current.setDate(current.getDate() - 1)
    setSelectedDate(current.toISOString().split('T')[0])
    setActiveTab('custom')
  }

  const goToNextDay = () => {
    const current = new Date(selectedDate)
    current.setDate(current.getDate() + 1)
    setSelectedDate(current.toISOString().split('T')[0])
    setActiveTab('custom')
  }

  if (loading) {
    return (
      <div className="employee-loading">
        <div className="spinner"></div>
        <p>Loading...</p>
      </div>
    )
  }

  if (!isAuthenticated) {
    return null
  }

  // Separate drop-offs and pick-ups
  const dropOffs = bookings.filter((b) => b.type === 'dropoff' || b.dropoff_date === selectedDate)
  const pickUps = bookings.filter((b) => b.type === 'pickup' || b.pickup_date === selectedDate)

  return (
    <div className="employee-container">
      <header className="employee-header">
        <div className="employee-header-left">
          <img src="/images/tag-logo.png" alt="TAG Parking" className="employee-logo" />
          <h1>Daily Operations</h1>
        </div>
        <div className="employee-header-right">
          <span className="employee-user">
            {user?.first_name} {user?.last_name}
          </span>
          <button onClick={handleLogout} className="employee-logout">
            Logout
          </button>
        </div>
      </header>

      <div className="employee-date-nav">
        <button onClick={goToPrevDay} className="date-nav-btn">
          &larr; Previous
        </button>
        <div className="date-display">
          <button onClick={goToToday} className="today-btn">
            Today
          </button>
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => {
              setSelectedDate(e.target.value)
              setActiveTab('custom')
            }}
            className="date-picker"
          />
          <span className="date-text">{formatDate(selectedDate)}</span>
        </div>
        <button onClick={goToNextDay} className="date-nav-btn">
          Next &rarr;
        </button>
      </div>

      <main className="employee-content">
        {error && <div className="employee-error">{error}</div>}

        <div className="employee-grid">
          {/* Drop-offs Section */}
          <div className="employee-section">
            <div className="section-header dropoff">
              <h2>Drop-offs</h2>
              <span className="section-count">{dropOffs.length}</span>
            </div>
            {loadingData ? (
              <div className="employee-loading-inline">
                <div className="spinner-small"></div>
              </div>
            ) : dropOffs.length === 0 ? (
              <p className="employee-empty">No drop-offs scheduled</p>
            ) : (
              <div className="booking-list">
                {dropOffs.map((booking, index) => (
                  <div key={booking.reference || index} className="booking-card">
                    <div className="booking-time">
                      {booking.dropoff_time || booking.time}
                    </div>
                    <div className="booking-details">
                      <div className="booking-ref">{booking.reference}</div>
                      <div className="booking-customer">
                        {booking.customer?.first_name} {booking.customer?.last_name}
                      </div>
                      <div className="booking-vehicle">
                        <span className="vehicle-reg">{booking.vehicle?.registration}</span>
                        <span className="vehicle-info">
                          {booking.vehicle?.colour} {booking.vehicle?.make} {booking.vehicle?.model}
                        </span>
                      </div>
                      {booking.dropoff_flight_number && (
                        <div className="booking-flight">
                          Flight: {booking.dropoff_flight_number}
                        </div>
                      )}
                    </div>
                    <div className="booking-status">
                      <span className={`status-badge status-${booking.status?.toLowerCase()}`}>
                        {booking.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Pick-ups Section */}
          <div className="employee-section">
            <div className="section-header pickup">
              <h2>Pick-ups</h2>
              <span className="section-count">{pickUps.length}</span>
            </div>
            {loadingData ? (
              <div className="employee-loading-inline">
                <div className="spinner-small"></div>
              </div>
            ) : pickUps.length === 0 ? (
              <p className="employee-empty">No pick-ups scheduled</p>
            ) : (
              <div className="booking-list">
                {pickUps.map((booking, index) => (
                  <div key={booking.reference || index} className="booking-card">
                    <div className="booking-time">
                      {booking.pickup_time_from} - {booking.pickup_time_to}
                    </div>
                    <div className="booking-details">
                      <div className="booking-ref">{booking.reference}</div>
                      <div className="booking-customer">
                        {booking.customer?.first_name} {booking.customer?.last_name}
                      </div>
                      <div className="booking-vehicle">
                        <span className="vehicle-reg">{booking.vehicle?.registration}</span>
                        <span className="vehicle-info">
                          {booking.vehicle?.colour} {booking.vehicle?.make} {booking.vehicle?.model}
                        </span>
                      </div>
                      {booking.pickup_flight_number && (
                        <div className="booking-flight">
                          Flight: {booking.pickup_flight_number}
                        </div>
                      )}
                    </div>
                    <div className="booking-status">
                      <span className={`status-badge status-${booking.status?.toLowerCase()}`}>
                        {booking.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}

export default Employee
