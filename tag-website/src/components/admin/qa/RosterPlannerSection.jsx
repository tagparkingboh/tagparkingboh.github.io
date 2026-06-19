import PlannedRosterCalendar from '../../qa/PlannedRosterCalendar'

const RosterPlannerSection = ({ apiUrl, token }) => (
  <div className="admin-section">
    <PlannedRosterCalendar apiUrl={apiUrl} token={token} />
  </div>
)

export default RosterPlannerSection
