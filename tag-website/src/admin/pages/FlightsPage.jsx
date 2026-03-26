import { useState, useEffect } from 'react'
import { useAuth } from '../../AuthContext'
import { API_URL } from '../adminUtils'
import '../adminStyles.css'

function FlightsPage() {
  const { token } = useAuth()
  const [subTab, setSubTab] = useState('departures')
  const [departures, setDepartures] = useState([])
  const [arrivals, setArrivals] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (token) fetchFlights()
  }, [token])

  const fetchFlights = async () => {
    setLoading(true)
    try {
      const [depRes, arrRes] = await Promise.all([
        fetch(`${API_URL}/api/admin/flights/departures`, {
          headers: { 'Authorization': `Bearer ${token}` }
        }),
        fetch(`${API_URL}/api/admin/flights/arrivals`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
      ])
      if (depRes.ok) {
        const data = await depRes.json()
        setDepartures(data.departures || [])
      }
      if (arrRes.ok) {
        const data = await arrRes.json()
        setArrivals(data.arrivals || [])
      }
    } catch (err) {
      console.error('Failed to fetch flights:', err)
    } finally {
      setLoading(false)
    }
  }

  const flights = subTab === 'departures' ? departures : arrivals

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h2>Flight Schedule</h2>
        <button className="btn-secondary" onClick={fetchFlights} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      <div className="admin-subtabs">
        <button
          className={`admin-subtab ${subTab === 'departures' ? 'active' : ''}`}
          onClick={() => setSubTab('departures')}
        >
          Departures ({departures.length})
        </button>
        <button
          className={`admin-subtab ${subTab === 'arrivals' ? 'active' : ''}`}
          onClick={() => setSubTab('arrivals')}
        >
          Arrivals ({arrivals.length})
        </button>
      </div>

      {loading ? (
        <div className="admin-loading-inline">Loading flights...</div>
      ) : flights.length === 0 ? (
        <p className="admin-empty">No {subTab} found</p>
      ) : (
        <div className="admin-table-container">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Flight</th>
                <th>Airline</th>
                <th>{subTab === 'departures' ? 'Destination' : 'Origin'}</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {flights.slice(0, 50).map((flight, idx) => (
                <tr key={flight.id || idx}>
                  <td>{flight.date}</td>
                  <td><strong>{flight.flight_number}</strong></td>
                  <td>{flight.airline_name || flight.airline_code}</td>
                  <td>
                    {subTab === 'departures'
                      ? (flight.destination_name || flight.destination_code)
                      : (flight.origin_name || flight.origin_code)}
                  </td>
                  <td>{subTab === 'departures' ? flight.departure_time : flight.arrival_time}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default FlightsPage
