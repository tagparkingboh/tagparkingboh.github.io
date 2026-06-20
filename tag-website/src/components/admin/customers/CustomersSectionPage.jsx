import CustomersPage from './CustomersPage'
import LeadsPage from './LeadsPage'

const CustomersSectionPage = ({
  activeTab,
  customersPageProps,
  leadsPageProps,
}) => {
  if (activeTab === 'customers') {
    return <CustomersPage {...customersPageProps} />
  }

  if (activeTab === 'leads') {
    return <LeadsPage {...leadsPageProps} />
  }

  return null
}

export default CustomersSectionPage
