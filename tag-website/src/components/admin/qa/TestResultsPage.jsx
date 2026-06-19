import TestResultsSection from './TestResultsSection'

const TestResultsPage = ({
  loadingTestResults,
  fetchTestResults,
  latestTestRun,
  testResults,
}) => (
  <TestResultsSection
    loadingTestResults={loadingTestResults}
    fetchTestResults={fetchTestResults}
    latestTestRun={latestTestRun}
    testResults={testResults}
  />
)

export default TestResultsPage
