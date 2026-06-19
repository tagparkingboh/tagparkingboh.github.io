import ErrorLogsSection from './ErrorLogsSection'

const ErrorLogsPage = ({
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
}) => (
  <ErrorLogsSection
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

export default ErrorLogsPage
