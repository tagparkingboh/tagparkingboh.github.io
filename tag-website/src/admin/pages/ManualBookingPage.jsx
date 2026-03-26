import { useAuth } from '../../AuthContext'
import ManualBooking from '../../components/ManualBooking'

function ManualBookingPage() {
  const { token } = useAuth()

  return (
    <div className="admin-page">
      <ManualBooking token={token} />
    </div>
  )
}

export default ManualBookingPage
