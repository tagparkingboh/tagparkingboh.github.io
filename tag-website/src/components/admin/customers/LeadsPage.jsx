import LeadsSection from '../LeadsSection'

const LeadsPage = ({
  fetchLeads,
  loadingLeads,
  leadSearchTerm,
  setLeadSearchTerm,
  leads,
  leadDateFrom,
  setLeadDateFrom,
  leadDateTo,
  setLeadDateTo,
  expandedLeadMonths,
  setExpandedLeadMonths,
  expandedLeadId,
  setExpandedLeadId,
}) => (
  <LeadsSection
    fetchLeads={fetchLeads}
    loadingLeads={loadingLeads}
    leadSearchTerm={leadSearchTerm}
    setLeadSearchTerm={setLeadSearchTerm}
    leads={leads}
    leadDateFrom={leadDateFrom}
    setLeadDateFrom={setLeadDateFrom}
    leadDateTo={leadDateTo}
    setLeadDateTo={setLeadDateTo}
    expandedLeadMonths={expandedLeadMonths}
    setExpandedLeadMonths={setExpandedLeadMonths}
    expandedLeadId={expandedLeadId}
    setExpandedLeadId={setExpandedLeadId}
  />
)

export default LeadsPage
