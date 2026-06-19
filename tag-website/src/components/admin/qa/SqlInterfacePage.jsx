import SqlInterfaceSection from './SqlInterfaceSection'

const SqlInterfacePage = ({
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
}) => (
  <SqlInterfaceSection
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

export default SqlInterfacePage
