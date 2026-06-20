import PayrollPage from './PayrollPage'
import UsersPage from './UsersPage'

const StaffSectionPage = ({
  activeTab,
  staffPayrollPageProps,
  staffUsersPageProps,
}) => {
  if (activeTab === 'payroll') {
    return <PayrollPage {...staffPayrollPageProps} />
  }

  if (activeTab === 'users') {
    return <UsersPage {...staffUsersPageProps} />
  }

  return null
}

export default StaffSectionPage
