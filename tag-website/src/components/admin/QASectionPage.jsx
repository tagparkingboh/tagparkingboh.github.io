import TestResultsPage from './qa/TestResultsPage'
import ConnectionPoolPage from './qa/ConnectionPoolPage'
import AuditLogsPage from './qa/AuditLogsPage'
import ErrorLogsPage from './qa/ErrorLogsPage'
import SqlInterfacePage from './qa/SqlInterfacePage'
import RosterPlannerPage from './qa/RosterPlannerPage'

const QASectionPage = ({
  activeTab,
  API_URL,
  token,
  loadingTestResults,
  fetchTestResults,
  latestTestRun,
  testResults,
  loadingDbHealth,
  loadingPoolHistory,
  fetchDbHealth,
  fetchDbPoolHistory,
  dbHealth,
  dbPoolHistory,
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
  errorLogs,
  loadingErrorLogs,
  errorLogsTotalCount,
  fetchErrorLogs,
  errorLogsFilters,
  setErrorLogsFilters,
  errorSeverities,
  errorTypes,
  expandedErrorLog,
  setExpandedErrorLog,
  errorLogsOffset,
  setErrorLogsOffset,
  sqlSessionToken,
  sqlSessionExpires,
  logoutSqlSession,
  sqlPinModalOpen,
  setSqlPinModalOpen,
  sqlPin,
  setSqlPin,
  verifySqlPin,
  sqlPinError,
  sqlQuery,
  setSqlQuery,
  executeSqlQuery,
  sqlLoading,
  sqlError,
  setSqlError,
  sqlResults,
  setSqlResults,
  exportSqlResultsCSV,
  exportSqlResultsPDF,
  sqlHistory,
  sqlTemplates,
  sqlTemplatesExpanded,
  setSqlTemplatesExpanded,
}) => {
  if (activeTab === 'qa-tests') {
    return (
      <TestResultsPage
        loadingTestResults={loadingTestResults}
        fetchTestResults={fetchTestResults}
        latestTestRun={latestTestRun}
        testResults={testResults}
      />
    )
  }

  if (activeTab === 'qa-connection-pool') {
    return (
      <ConnectionPoolPage
        loadingDbHealth={loadingDbHealth}
        loadingPoolHistory={loadingPoolHistory}
        fetchDbHealth={fetchDbHealth}
        fetchDbPoolHistory={fetchDbPoolHistory}
        dbHealth={dbHealth}
        dbPoolHistory={dbPoolHistory}
      />
    )
  }

  if (activeTab === 'qa-audit') {
    return (
      <AuditLogsPage
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
  }

  if (activeTab === 'qa-errors') {
    return (
      <ErrorLogsPage
        errorLogs={errorLogs}
        loadingErrorLogs={loadingErrorLogs}
        errorLogsTotalCount={errorLogsTotalCount}
        fetchErrorLogs={fetchErrorLogs}
        errorLogsFilters={errorLogsFilters}
        setErrorLogsFilters={setErrorLogsFilters}
        errorSeverities={errorSeverities}
        errorTypes={errorTypes}
        expandedErrorLog={expandedErrorLog}
        setExpandedErrorLog={setExpandedErrorLog}
        errorLogsOffset={errorLogsOffset}
        setErrorLogsOffset={setErrorLogsOffset}
      />
    )
  }

  if (activeTab === 'qa-sql') {
    return (
      <SqlInterfacePage
        sqlSessionToken={sqlSessionToken}
        sqlSessionExpires={sqlSessionExpires}
        logoutSqlSession={logoutSqlSession}
        sqlPinModalOpen={sqlPinModalOpen}
        setSqlPinModalOpen={setSqlPinModalOpen}
        sqlPin={sqlPin}
        setSqlPin={setSqlPin}
        verifySqlPin={verifySqlPin}
        sqlPinError={sqlPinError}
        sqlQuery={sqlQuery}
        setSqlQuery={setSqlQuery}
        executeSqlQuery={executeSqlQuery}
        sqlLoading={sqlLoading}
        sqlError={sqlError}
        setSqlError={setSqlError}
        sqlResults={sqlResults}
        setSqlResults={setSqlResults}
        exportSqlResultsCSV={exportSqlResultsCSV}
        exportSqlResultsPDF={exportSqlResultsPDF}
        sqlHistory={sqlHistory}
        sqlTemplates={sqlTemplates}
        sqlTemplatesExpanded={sqlTemplatesExpanded}
        setSqlTemplatesExpanded={setSqlTemplatesExpanded}
      />
    )
  }

  if (activeTab === 'qa-roster-planner') {
    return <RosterPlannerPage apiUrl={API_URL} token={token} />
  }

  return null
}

export default QASectionPage
