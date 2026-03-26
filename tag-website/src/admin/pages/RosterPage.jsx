import { useAuth } from '../../AuthContext'
import RosterCalendar from '../../components/RosterCalendar'

function RosterPage() {
  const { token } = useAuth()

  return (
    <div className="admin-page">
      <RosterCalendar token={token} isAdmin={true} />
    </div>
  )
}

export default RosterPage
