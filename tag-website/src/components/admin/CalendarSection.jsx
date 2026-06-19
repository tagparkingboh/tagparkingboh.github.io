import RosterCalendar from '../RosterCalendar'

const CalendarSection = ({ token }) => {
  return (
    <div className="admin-section">
      <RosterCalendar token={token} isAdmin={true} />
    </div>
  )
}

export default CalendarSection
