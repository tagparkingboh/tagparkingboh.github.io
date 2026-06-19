import ConnectionPoolSection from './ConnectionPoolSection'

const ConnectionPoolPage = ({
  loadingDbHealth,
  loadingPoolHistory,
  fetchDbHealth,
  fetchDbPoolHistory,
  dbHealth,
  dbPoolHistory,
}) => (
  <ConnectionPoolSection
    loadingDbHealth={loadingDbHealth}
    loadingPoolHistory={loadingPoolHistory}
    fetchDbHealth={fetchDbHealth}
    fetchDbPoolHistory={fetchDbPoolHistory}
    dbHealth={dbHealth}
    dbPoolHistory={dbPoolHistory}
  />
)

export default ConnectionPoolPage
