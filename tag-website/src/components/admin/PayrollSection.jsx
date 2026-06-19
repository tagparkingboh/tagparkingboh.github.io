import Payroll from '../Payroll'

const PayrollSection = ({ token }) => {
  return (
    <div className="admin-section">
      <Payroll token={token} />
    </div>
  )
}

export default PayrollSection
