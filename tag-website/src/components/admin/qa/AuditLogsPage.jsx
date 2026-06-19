import AuditLogsSection from './AuditLogsSection'

const AuditLogsPage = ({
  auditLogs,
  loadingAuditLogs,
  fetchAuditLogs,
  auditLogsTotalCount,
  auditLogsFilters,
  setAuditLogsFilters,
  auditEventTypes,
  auditLogsAutoRefresh,
  setAuditLogsAutoRefresh,
  expandedAuditLog,
  setExpandedAuditLog,
  auditLogsOffset,
  setAuditLogsOffset,
}) => (
  <AuditLogsSection
    auditLogs={auditLogs}
    loadingAuditLogs={loadingAuditLogs}
    fetchAuditLogs={fetchAuditLogs}
    auditLogsTotalCount={auditLogsTotalCount}
    auditLogsFilters={auditLogsFilters}
    setAuditLogsFilters={setAuditLogsFilters}
    auditEventTypes={auditEventTypes}
    auditLogsAutoRefresh={auditLogsAutoRefresh}
    setAuditLogsAutoRefresh={setAuditLogsAutoRefresh}
    expandedAuditLog={expandedAuditLog}
    setExpandedAuditLog={setExpandedAuditLog}
    auditLogsOffset={auditLogsOffset}
    setAuditLogsOffset={setAuditLogsOffset}
  />
)

export default AuditLogsPage
