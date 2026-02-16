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

// Color markers from leaflet-color-markers CDN
const markerBaseUrl = 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img'

const createColorIcon = (color) => new L.Icon({
  iconUrl: `${markerBaseUrl}/marker-icon-2x-${color}.png`,
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
})

// Status-based marker colors
const statusIcons = {
  confirmed: createColorIcon('blue'),
  completed: createColorIcon('green'),
  cancelled: createColorIcon('red'),
  pending: createColorIcon('orange'),
  default: createColorIcon('grey'),
}

const getMarkerIcon = (status) => {
  return statusIcons[status] || statusIcons.default
}

function BookingLocationMap({ locations = [] }) {
  // Center higher to show south coast near bottom of map
  const center = [51.2, -1.3]
  const zoom = 8

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
        style={{ height: '650px', width: '100%', borderRadius: '8px' }}
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
            icon={getMarkerIcon(location.status)}
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
