import ManualBooking from '../ManualBooking'

const ManualBookingSection = ({ token }) => {
  return (
    <div className="admin-section">
      <ManualBooking token={token} />
    </div>
  )
}

export default ManualBookingSection
