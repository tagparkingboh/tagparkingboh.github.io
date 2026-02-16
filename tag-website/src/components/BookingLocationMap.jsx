import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// Fix for default marker icons in Leaflet with bundlers
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
})

// Custom TAG-branded marker
const tagIcon = new L.Icon({
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
})

function BookingLocationMap({ locations = [] }) {
  // Center on Bournemouth
  const center = [50.7192, -1.8808]
  const zoom = 9

  if (locations.length === 0) {
    return (
      <div className="map-empty">
        <p>No booking locations to display</p>
      </div>
    )
  }

  return (
    <div className="booking-map-container">
      <MapContainer
        center={center}
        zoom={zoom}
        style={{ height: '500px', width: '100%', borderRadius: '8px' }}
        scrollWheelZoom={true}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {locations.map((location) => (
          <Marker
            key={location.id}
            position={[location.lat, location.lng]}
            icon={tagIcon}
          >
            <Popup>
              <div className="map-popup">
                <strong>{location.reference}</strong>
                <p>{location.customer_name}</p>
                <p className="popup-location">{location.city || location.postcode}</p>
                <p className="popup-date">
                  {location.dropoff_date && new Date(location.dropoff_date).toLocaleDateString('en-GB', {
                    day: 'numeric',
                    month: 'short',
                    year: 'numeric'
                  })}
                </p>
                <span className={`popup-status status-${location.status}`}>
                  {location.status}
                </span>
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
      <p className="map-count">{locations.length} bookings displayed</p>
    </div>
  )
}

export default BookingLocationMap
