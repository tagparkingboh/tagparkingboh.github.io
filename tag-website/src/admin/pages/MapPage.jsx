import { useState, useEffect } from 'react'
import { useAuth } from '../../AuthContext'
import { API_URL } from '../adminUtils'
import BookingLocationMap from '../../components/BookingLocationMap'
import '../adminStyles.css'

function MapPage() {
  const { token } = useAuth()
  const [mapType, setMapType] = useState('bookings')
  const [locations, setLocations] = useState([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)

  useEffect(() => {
    if (token) fetchLocations()
  }, [token, mapType])

  const fetchLocations = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/reports/booking-locations?map_type=${mapType}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        const data = await response.json()
        setLocations(data.locations || [])
        setTotal(mapType === 'origins' ? data.total_customers : data.total_bookings)
      }
    } catch (err) {
      console.error('Failed to fetch locations:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h2>Location Map</h2>
        <button className="btn-secondary" onClick={fetchLocations} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      <div className="admin-subtabs">
        <button
          className={`admin-subtab ${mapType === 'bookings' ? 'active' : ''}`}
          onClick={() => setMapType('bookings')}
        >
          Booking Locations
        </button>
        <button
          className={`admin-subtab ${mapType === 'origins' ? 'active' : ''}`}
          onClick={() => setMapType('origins')}
        >
          Customer Origins
        </button>
      </div>

      <div style={{ marginBottom: '15px', color: '#666' }}>
        {loading ? 'Loading...' : `${locations.length} locations from ${total} ${mapType === 'origins' ? 'customers' : 'bookings'}`}
      </div>

      {locations.length > 0 ? (
        <div style={{ height: '500px', borderRadius: '8px', overflow: 'hidden' }}>
          <BookingLocationMap locations={locations} mapType={mapType} />
        </div>
      ) : (
        <p className="admin-empty">No location data available</p>
      )}
    </div>
  )
}

export default MapPage
