import { useState, useEffect, useCallback } from 'react'
import './EmployeePayroll.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Month names for display
const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
]

// Format date for display (DD Mon YYYY) - parse directly to avoid timezone issues
const formatDateDisplay = (isoDate) => {
  if (!isoDate) return ''
  // Parse YYYY-MM-DD directly to avoid timezone conversion
  const parts = isoDate.split('-')
  if (parts.length !== 3) return isoDate
  const year = parts[0]
  const monthIndex = parseInt(parts[1], 10) - 1
  const day = parts[2]
  return `${day} ${MONTH_NAMES[monthIndex].substring(0, 3)} ${year}`
}

// Get last day of month (handles leap years)
const getLastDayOfMonth = (year, month) => {
  // month is 1-based (1 = January)
  // new Date(year, month, 0) gives last day of previous month
  // So new Date(year, month, 0) where month is 1-based gives last day of that month
  return new Date(year, month, 0).getDate()
}

// Check if current date is on or after the last day of the selected month
const canDownloadPayslip = (year, month) => {
  const today = new Date()
  const lastDayOfMonth = getLastDayOfMonth(year, month)
  const lastDateOfMonth = new Date(year, month - 1, lastDayOfMonth) // month - 1 because Date uses 0-based months

  // Set time to end of day for comparison
  lastDateOfMonth.setHours(0, 0, 0, 0)
  today.setHours(0, 0, 0, 0)

  return today >= lastDateOfMonth
}

function EmployeePayroll({ token }) {
  const now = new Date()
  const [selectedYear, setSelectedYear] = useState(now.getFullYear())
  const [selectedMonth, setSelectedMonth] = useState(now.getMonth() + 1)
  const [payrollData, setPayrollData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState(false)
  const [downloadWarning, setDownloadWarning] = useState(null)

  // Check if payslip can be downloaded (on or after last day of month)
  const downloadAllowed = canDownloadPayslip(selectedYear, selectedMonth)

  // Handle download attempt - show warning if not allowed
  const handleDownloadClick = () => {
    if (!downloadAllowed) {
      const lastDay = getLastDayOfMonth(selectedYear, selectedMonth)
      setDownloadWarning(`Payslip will be available from ${lastDay} ${MONTH_NAMES[selectedMonth - 1]} ${selectedYear}`)
      // Auto-hide warning after 5 seconds
      setTimeout(() => setDownloadWarning(null), 5000)
      return
    }
    downloadPDF()
  }

  // Fetch payroll data for the current user
  const fetchPayroll = useCallback(async () => {
    if (!token) return

    setLoading(true)
    setError(null)

    try {
      const response = await fetch(
        `${API_URL}/api/employee/payroll/monthly?year=${selectedYear}&month=${selectedMonth}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      )

      if (!response.ok) {
        throw new Error('Failed to fetch payroll data')
      }

      const data = await response.json()
      setPayrollData(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [token, selectedYear, selectedMonth])

  useEffect(() => {
    fetchPayroll()
  }, [fetchPayroll])

  // Download PDF wage slip
  const downloadPDF = () => {
    if (!payrollData) return

    // Find max shifts per day to determine columns
    const maxShiftsPerDay = Math.max(
      ...payrollData.shifts_by_date.map(d => d.shifts.length),
      1
    )

    // Create shift columns headers
    const shiftHeaders = Array.from(
      { length: maxShiftsPerDay },
      (_, i) => `<th>Shift ${i + 1}</th>`
    ).join('')

    const content = `
      <!DOCTYPE html>
      <html>
      <head>
        <title>Timesheet - ${payrollData.employee_name} - ${payrollData.month_name} ${payrollData.year}</title>
        <style>
          body { font-family: Arial, sans-serif; padding: 40px; }
          h1 { color: #333; margin-bottom: 5px; }
          h2 { color: #666; font-size: 18px; margin-bottom: 5px; }
          h3 { color: #888; font-size: 14px; margin-bottom: 30px; }
          .summary { margin-bottom: 30px; padding: 15px; background: #f5f5f5; border-radius: 8px; }
          .summary span { margin-right: 30px; }
          table { width: 100%; border-collapse: collapse; margin-top: 20px; }
          th, td { border: 1px solid #ddd; padding: 10px; text-align: center; }
          th { background: #f5f5f5; font-weight: bold; }
          td:first-child { text-align: left; }
          .daily-total { font-weight: bold; background: #fafafa; }
          .footer { margin-top: 40px; font-size: 12px; color: #888; }
        </style>
      </head>
      <body>
        <h1>TAG Parking - Driver Timesheet</h1>
        <h2>${payrollData.employee_name}</h2>
        <h3>${payrollData.month_name} ${payrollData.year}</h3>

        <div class="summary">
          <span><strong>Total Shifts:</strong> ${payrollData.total_shifts}</span>
          <span><strong>Total Hours:</strong> ${payrollData.total_hours}</span>
        </div>

        ${payrollData.shifts_by_date.length > 0 ? `
        <table>
          <thead>
            <tr>
              <th>Date</th>
              ${shiftHeaders}
              <th>Hours</th>
            </tr>
          </thead>
          <tbody>
            ${payrollData.shifts_by_date.map(day => {
              const shiftCells = Array.from({ length: maxShiftsPerDay }, (_, i) => {
                const shift = day.shifts[i]
                return shift
                  ? `<td>${shift.start_time} - ${shift.end_time}</td>`
                  : '<td>-</td>'
              }).join('')

              return `
                <tr>
                  <td>${formatDateDisplay(day.date)}</td>
                  ${shiftCells}
                  <td class="daily-total">${day.daily_hours}</td>
                </tr>
              `
            }).join('')}
          </tbody>
        </table>
        ` : '<p>No shifts recorded for this month.</p>'}

        <div class="footer">Generated on ${new Date().toLocaleDateString('en-GB')}</div>
      </body>
      </html>
    `

    const printWindow = window.open('', '_blank')
    printWindow.document.write(content)
    printWindow.document.close()
    printWindow.print()
  }

  // Generate year options (current year and 2 years back)
  const yearOptions = []
  for (let y = now.getFullYear(); y >= now.getFullYear() - 2; y--) {
    yearOptions.push(y)
  }

  return (
    <div className="emp-payroll-container">
      <div className="emp-payroll-header" onClick={() => setExpanded(!expanded)}>
        <div className="emp-payroll-title">
          <span className={`emp-payroll-expand ${expanded ? 'expanded' : ''}`}>▶</span>
          <h3>My Payroll</h3>
        </div>
        {payrollData && !loading && (
          <div className="emp-payroll-quick-summary">
            <span>{payrollData.month_name} {payrollData.year}</span>
            <span className="emp-payroll-hours">{payrollData.total_hours} hrs</span>
          </div>
        )}
      </div>

      {expanded && (
        <div className="emp-payroll-content">
          <div className="emp-payroll-controls">
            <div className="emp-payroll-date-selector">
              <select
                value={selectedMonth}
                onChange={(e) => setSelectedMonth(parseInt(e.target.value))}
                className="emp-payroll-select"
              >
                {MONTH_NAMES.map((name, index) => (
                  <option key={index} value={index + 1}>{name}</option>
                ))}
              </select>

              <select
                value={selectedYear}
                onChange={(e) => setSelectedYear(parseInt(e.target.value))}
                className="emp-payroll-select"
              >
                {yearOptions.map(year => (
                  <option key={year} value={year}>{year}</option>
                ))}
              </select>
            </div>

            <div className="emp-payroll-download">
              <button
                onClick={handleDownloadClick}
                className={`emp-payroll-btn pdf ${!downloadAllowed ? 'not-yet' : ''}`}
                disabled={!payrollData || payrollData.total_shifts === 0}
              >
                Download PDF
              </button>
              {!downloadAllowed && (
                <span className="emp-payroll-download-note">
                  Available from {getLastDayOfMonth(selectedYear, selectedMonth)} {MONTH_NAMES[selectedMonth - 1].substring(0, 3)}
                </span>
              )}
            </div>
          </div>

          {error && <div className="emp-payroll-error">{error}</div>}

          {downloadWarning && (
            <div className="emp-payroll-warning">
              {downloadWarning}
            </div>
          )}

          {loading && <div className="emp-payroll-loading">Loading...</div>}

          {payrollData && !loading && (
            <>
              <div className="emp-payroll-summary">
                <div className="emp-payroll-summary-item">
                  <span className="label">Total Shifts</span>
                  <span className="value">{payrollData.total_shifts}</span>
                </div>
                <div className="emp-payroll-summary-item">
                  <span className="label">Total Hours</span>
                  <span className="value">{payrollData.total_hours}</span>
                </div>
              </div>

              {payrollData.shifts_by_date.length > 0 ? (
                <div className="emp-payroll-shifts">
                  <table className="emp-payroll-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Shifts</th>
                        <th>Hours</th>
                      </tr>
                    </thead>
                    <tbody>
                      {payrollData.shifts_by_date.map(day => (
                        <tr key={day.date}>
                          <td className="date-cell">{formatDateDisplay(day.date)}</td>
                          <td className="shifts-cell">
                            {day.shifts.map((shift, idx) => (
                              <span key={idx} className="shift-badge">
                                {shift.start_time} - {shift.end_time}
                              </span>
                            ))}
                          </td>
                          <td className="hours-cell">{day.daily_hours}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="emp-payroll-empty">
                  No shifts recorded for {payrollData.month_name} {payrollData.year}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

export default EmployeePayroll
