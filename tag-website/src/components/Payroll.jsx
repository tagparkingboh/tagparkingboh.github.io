import { useState, useEffect, useCallback } from 'react'
import './Payroll.css'

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

// Format time input - allows entering "2300" and formats to "23:00"
const formatTimeInput = (value) => {
  // Remove any non-digit characters
  const digits = value.replace(/\D/g, '')

  if (digits.length === 0) return ''

  // Handle different input lengths
  if (digits.length <= 2) {
    // Just hours (e.g., "23" or "9")
    return digits
  } else if (digits.length === 3) {
    // e.g., "930" -> "9:30" or "230" -> "2:30"
    return `${digits.slice(0, 1)}:${digits.slice(1)}`
  } else if (digits.length >= 4) {
    // e.g., "2300" -> "23:00" or "0930" -> "09:30"
    const hours = digits.slice(0, 2)
    const mins = digits.slice(2, 4)
    return `${hours}:${mins}`
  }

  return value
}

// Validate time format HH:MM
const isValidTime = (timeStr) => {
  if (!timeStr) return false
  const match = timeStr.match(/^(\d{1,2}):(\d{2})$/)
  if (!match) return false
  const hours = parseInt(match[1], 10)
  const mins = parseInt(match[2], 10)
  return hours >= 0 && hours <= 23 && mins >= 0 && mins <= 59
}

// Ensure time is in HH:MM format (pad hours if needed)
const normalizeTime = (timeStr) => {
  if (!timeStr) return ''
  const match = timeStr.match(/^(\d{1,2}):(\d{2})$/)
  if (!match) return timeStr
  const hours = match[1].padStart(2, '0')
  const mins = match[2]
  return `${hours}:${mins}`
}

function Payroll({ token }) {
  const now = new Date()
  const [selectedYear, setSelectedYear] = useState(now.getFullYear())
  const [selectedMonth, setSelectedMonth] = useState(now.getMonth() + 1)
  const [payrollData, setPayrollData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [expandedStaff, setExpandedStaff] = useState({})

  // Edit shift modal state
  const [editingShift, setEditingShift] = useState(null)
  const [editStartTime, setEditStartTime] = useState('')
  const [editEndTime, setEditEndTime] = useState('')
  const [editIsOvernight, setEditIsOvernight] = useState(false)
  const [editDate, setEditDate] = useState('')
  const [editEndDate, setEditEndDate] = useState('')
  const [editSaving, setEditSaving] = useState(false)

  // Delete confirmation state
  const [deletingShift, setDeletingShift] = useState(null)
  const [deleteConfirming, setDeleteConfirming] = useState(false)

  // Fetch payroll data
  const fetchPayroll = useCallback(async () => {
    if (!token) return

    setLoading(true)
    setError(null)

    try {
      const response = await fetch(
        `${API_URL}/api/payroll/monthly?year=${selectedYear}&month=${selectedMonth}`,
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

  // Toggle expanded state for a staff member
  const toggleExpanded = (staffId) => {
    setExpandedStaff(prev => ({
      ...prev,
      [staffId]: !prev[staffId]
    }))
  }

  // Open edit modal
  const openEditModal = (shift, staffName, shiftDate) => {
    setEditingShift({ ...shift, staffName, shiftDate })
    setEditStartTime(shift.start_time)
    setEditEndTime(shift.end_time)
    setEditIsOvernight(shift.is_overnight || false)
    setEditDate(shift.date || shiftDate)
    // For overnight shifts, calculate end_date (next day)
    if (shift.is_overnight) {
      const startDate = new Date(shift.date || shiftDate)
      const endDate = new Date(startDate)
      endDate.setDate(endDate.getDate() + 1)
      setEditEndDate(endDate.toISOString().split('T')[0])
    } else {
      setEditEndDate(shift.date || shiftDate)
    }
  }

  // Close edit modal
  const closeEditModal = () => {
    setEditingShift(null)
    setEditStartTime('')
    setEditEndTime('')
    setEditIsOvernight(false)
    setEditDate('')
    setEditEndDate('')
  }

  // Save shift edit
  const saveShiftEdit = async () => {
    if (!editingShift) return

    // Validate times
    const normalizedStart = normalizeTime(editStartTime)
    const normalizedEnd = normalizeTime(editEndTime)

    if (!isValidTime(normalizedStart)) {
      setError('Invalid start time. Use format HH:MM (e.g., 23:00)')
      return
    }
    if (!isValidTime(normalizedEnd)) {
      setError('Invalid end time. Use format HH:MM (e.g., 23:00)')
      return
    }

    setEditSaving(true)
    setError(null)

    try {
      // Build request body with dates for overnight shifts
      const requestBody = {
        start_time: normalizedStart,
        end_time: normalizedEnd,
        date: editDate
      }

      // Include end_date for overnight shifts
      if (editIsOvernight && editEndDate) {
        requestBody.end_date = editEndDate
      }

      const response = await fetch(`${API_URL}/api/roster/${editingShift.id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody)
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Failed to update shift')
      }

      closeEditModal()
      fetchPayroll() // Refresh data
    } catch (err) {
      setError(err.message)
    } finally {
      setEditSaving(false)
    }
  }

  // Open delete confirmation
  const openDeleteConfirm = (shift, staffName, shiftDate) => {
    setDeletingShift({ ...shift, staffName, shiftDate })
  }

  // Close delete confirmation
  const closeDeleteConfirm = () => {
    setDeletingShift(null)
  }

  // Delete shift
  const deleteShift = async () => {
    if (!deletingShift) return

    setDeleteConfirming(true)
    try {
      const response = await fetch(`${API_URL}/api/roster/${deletingShift.id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Failed to delete shift')
      }

      closeDeleteConfirm()
      fetchPayroll() // Refresh data
    } catch (err) {
      setError(err.message)
    } finally {
      setDeleteConfirming(false)
    }
  }

  // Download monthly summary as CSV
  const downloadCSV = () => {
    if (!payrollData) return

    const headers = ['Driver Name', 'Total Shifts', 'Total Hours']
    const rows = payrollData.staff
      .filter(s => s.total_shifts > 0)
      .map(s => [s.staff_name, s.total_shifts, s.total_hours])

    // Add totals row
    rows.push(['TOTAL', payrollData.totals.total_shifts, payrollData.totals.total_hours])

    const csvContent = [
      `Payroll Report - ${payrollData.month_name} ${payrollData.year}`,
      '',
      headers.join(','),
      ...rows.map(row => row.join(','))
    ].join('\n')

    const blob = new Blob([csvContent], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `payroll-${payrollData.year}-${String(payrollData.month).padStart(2, '0')}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  // Download monthly summary as PDF
  const downloadMonthlyPDF = () => {
    if (!payrollData) return

    // Create a simple HTML template for PDF
    const content = `
      <!DOCTYPE html>
      <html>
      <head>
        <title>Payroll Report - ${payrollData.month_name} ${payrollData.year}</title>
        <style>
          body { font-family: Arial, sans-serif; padding: 40px; }
          h1 { color: #333; margin-bottom: 10px; }
          h2 { color: #666; font-size: 16px; margin-bottom: 30px; }
          table { width: 100%; border-collapse: collapse; margin-top: 20px; }
          th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
          th { background: #f5f5f5; font-weight: bold; }
          .totals { background: #e8f5e9; font-weight: bold; }
          .footer { margin-top: 40px; font-size: 12px; color: #888; }
        </style>
      </head>
      <body>
        <h1>TAG Parking - Payroll Report</h1>
        <h2>${payrollData.month_name} ${payrollData.year}</h2>
        <table>
          <thead>
            <tr>
              <th>Driver Name</th>
              <th>Total Shifts</th>
              <th>Total Hours</th>
            </tr>
          </thead>
          <tbody>
            ${payrollData.staff
              .filter(s => s.total_shifts > 0)
              .map(s => `
                <tr>
                  <td>${s.staff_name}</td>
                  <td>${s.total_shifts}</td>
                  <td>${s.total_hours}</td>
                </tr>
              `).join('')}
            <tr class="totals">
              <td>TOTAL</td>
              <td>${payrollData.totals.total_shifts}</td>
              <td>${payrollData.totals.total_hours}</td>
            </tr>
          </tbody>
        </table>
        <div class="footer">Generated on ${new Date().toLocaleDateString('en-GB')}</div>
      </body>
      </html>
    `

    const printWindow = window.open('', '_blank')
    printWindow.document.write(content)
    printWindow.document.close()
    printWindow.print()
  }

  // Download individual staff PDF
  const downloadStaffPDF = (staffMember) => {
    // Find max shifts per day to determine columns
    const maxShiftsPerDay = Math.max(
      ...staffMember.shifts_by_date.map(d => d.shifts.length),
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
        <title>Payroll - ${staffMember.staff_name} - ${payrollData.month_name} ${payrollData.year}</title>
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
        <h2>${staffMember.staff_name}</h2>
        <h3>${payrollData.month_name} ${payrollData.year}</h3>

        <div class="summary">
          <span><strong>Total Shifts:</strong> ${staffMember.total_shifts}</span>
          <span><strong>Total Hours:</strong> ${staffMember.total_hours}</span>
        </div>

        <table>
          <thead>
            <tr>
              <th>Date</th>
              ${shiftHeaders}
              <th>Hours</th>
            </tr>
          </thead>
          <tbody>
            ${staffMember.shifts_by_date.map(day => {
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
    <div className="payroll-container">
      <div className="payroll-header">
        <h2>Payroll</h2>

        <div className="payroll-controls">
          <div className="payroll-date-selector">
            <select
              value={selectedMonth}
              onChange={(e) => setSelectedMonth(parseInt(e.target.value))}
              className="payroll-select"
            >
              {MONTH_NAMES.map((name, index) => (
                <option key={index} value={index + 1}>{name}</option>
              ))}
            </select>

            <select
              value={selectedYear}
              onChange={(e) => setSelectedYear(parseInt(e.target.value))}
              className="payroll-select"
            >
              {yearOptions.map(year => (
                <option key={year} value={year}>{year}</option>
              ))}
            </select>
          </div>

          <div className="payroll-actions">
            <button onClick={fetchPayroll} className="payroll-btn refresh" disabled={loading}>
              {loading ? 'Loading...' : 'Refresh'}
            </button>
            <button onClick={downloadCSV} className="payroll-btn csv" disabled={!payrollData}>
              Download CSV
            </button>
            <button onClick={downloadMonthlyPDF} className="payroll-btn pdf" disabled={!payrollData}>
              Download PDF
            </button>
          </div>
        </div>
      </div>

      {error && <div className="payroll-error">{error}</div>}

      {loading && <div className="payroll-loading">Loading payroll data...</div>}

      {payrollData && !loading && (
        <>
          <div className="payroll-summary">
            <div className="payroll-summary-item">
              <span className="label">Staff with shifts:</span>
              <span className="value">{payrollData.totals.total_staff_with_shifts}</span>
            </div>
            <div className="payroll-summary-item">
              <span className="label">Total shifts:</span>
              <span className="value">{payrollData.totals.total_shifts}</span>
            </div>
            <div className="payroll-summary-item">
              <span className="label">Total hours:</span>
              <span className="value">{payrollData.totals.total_hours}</span>
            </div>
          </div>

          <div className="payroll-table-container">
            <table className="payroll-table">
              <thead>
                <tr>
                  <th className="col-expand"></th>
                  <th className="col-name">Driver Name</th>
                  <th className="col-shifts">Shifts</th>
                  <th className="col-hours">Hours</th>
                  <th className="col-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                {payrollData.staff
                  .filter(s => s.total_shifts > 0)
                  .map(staffMember => (
                    <>
                      <tr key={staffMember.staff_id} className="payroll-row">
                        <td className="col-expand">
                          <button
                            className={`expand-btn ${expandedStaff[staffMember.staff_id] ? 'expanded' : ''}`}
                            onClick={() => toggleExpanded(staffMember.staff_id)}
                          >
                            ▶
                          </button>
                        </td>
                        <td className="col-name">{staffMember.staff_name}</td>
                        <td className="col-shifts">{staffMember.total_shifts}</td>
                        <td className="col-hours">{staffMember.total_hours}</td>
                        <td className="col-actions">
                          <button
                            className="payroll-btn-small pdf"
                            onClick={() => downloadStaffPDF(staffMember)}
                            title="Download PDF"
                          >
                            PDF
                          </button>
                        </td>
                      </tr>

                      {expandedStaff[staffMember.staff_id] && (
                        <tr key={`${staffMember.staff_id}-details`} className="payroll-details-row">
                          <td colSpan="5">
                            <div className="payroll-details">
                              <table className="payroll-shifts-table">
                                <thead>
                                  <tr>
                                    <th>Date</th>
                                    <th>Shifts</th>
                                    <th>Hours</th>
                                    <th>Actions</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {staffMember.shifts_by_date.map(day => (
                                    <tr key={day.date}>
                                      <td>{formatDateDisplay(day.date)}</td>
                                      <td>
                                        <div className="shifts-list">
                                          {day.shifts.map((shift, idx) => (
                                            <span key={shift.id} className="payroll-shift-time">
                                              {shift.start_time} - {shift.end_time}
                                              {shift.is_overnight && ' (overnight)'}
                                            </span>
                                          ))}
                                        </div>
                                      </td>
                                      <td className="hours-cell">{day.daily_hours}</td>
                                      <td className="actions-cell">
                                        {day.shifts.map(shift => (
                                          <div key={shift.id} className="shift-actions">
                                            <button
                                              className="action-btn edit"
                                              onClick={() => openEditModal(shift, staffMember.staff_name, day.date)}
                                              title="Edit shift"
                                            >
                                              ✏️
                                            </button>
                                            <button
                                              className="action-btn delete"
                                              onClick={() => openDeleteConfirm(shift, staffMember.staff_name, day.date)}
                                              title="Delete shift"
                                            >
                                              🗑️
                                            </button>
                                          </div>
                                        ))}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
              </tbody>
            </table>

            {payrollData.staff.filter(s => s.total_shifts > 0).length === 0 && (
              <div className="payroll-empty">No shifts recorded for {payrollData.month_name} {payrollData.year}</div>
            )}
          </div>
        </>
      )}

      {/* Edit Shift Modal */}
      {editingShift && (
        <div className="payroll-modal-overlay" onClick={closeEditModal}>
          <div className="payroll-modal" onClick={e => e.stopPropagation()}>
            <h3>Edit Shift</h3>
            <p className="modal-subtitle">
              {editingShift.staffName} - {formatDateDisplay(editingShift.shiftDate || editingShift.date)}
              {editIsOvernight && ' (overnight)'}
            </p>

            <div className="modal-form">
              <div className="form-row">
                <label>Start Time (24hr, e.g. 2300)</label>
                <input
                  type="text"
                  value={editStartTime}
                  onChange={(e) => setEditStartTime(formatTimeInput(e.target.value))}
                  placeholder="23:00"
                  maxLength={5}
                  className="time-input"
                />
              </div>
              <div className="form-row">
                <label>End Time (24hr, e.g. 0700)</label>
                <input
                  type="text"
                  value={editEndTime}
                  onChange={(e) => setEditEndTime(formatTimeInput(e.target.value))}
                  placeholder="07:00"
                  maxLength={5}
                  className="time-input"
                />
              </div>
              {editIsOvernight && (
                <div className="form-info overnight-info">
                  Overnight shift: {formatDateDisplay(editDate)} to {formatDateDisplay(editEndDate)}
                </div>
              )}
            </div>

            <div className="modal-actions">
              <button className="payroll-btn cancel" onClick={closeEditModal}>
                Cancel
              </button>
              <button
                className="payroll-btn save"
                onClick={saveShiftEdit}
                disabled={editSaving}
              >
                {editSaving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deletingShift && (
        <div className="payroll-modal-overlay" onClick={closeDeleteConfirm}>
          <div className="payroll-modal" onClick={e => e.stopPropagation()}>
            <h3>Delete Shift</h3>
            <p>Are you sure you want to delete this shift?</p>
            <p className="modal-shift-info">
              <strong>{deletingShift.staffName}</strong><br />
              {formatDateDisplay(deletingShift.date)}<br />
              {deletingShift.start_time} - {deletingShift.end_time}
            </p>

            <div className="modal-actions">
              <button className="payroll-btn cancel" onClick={closeDeleteConfirm}>
                Cancel
              </button>
              <button
                className="payroll-btn delete"
                onClick={deleteShift}
                disabled={deleteConfirming}
              >
                {deleteConfirming ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Payroll
