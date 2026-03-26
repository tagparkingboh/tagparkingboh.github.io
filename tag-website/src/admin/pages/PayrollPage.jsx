import { useAuth } from '../../AuthContext'
import Payroll from '../../components/Payroll'

function PayrollPage() {
  const { token } = useAuth()

  return (
    <div className="admin-page">
      <Payroll token={token} />
    </div>
  )
}

export default PayrollPage
