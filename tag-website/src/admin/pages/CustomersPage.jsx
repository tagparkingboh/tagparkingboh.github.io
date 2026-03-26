import { useState, useEffect, useMemo } from 'react'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import { useAuth } from '../../AuthContext'
import { API_URL } from '../adminUtils'
import '../adminStyles.css'

// Format marketing source for display
const formatMarketingSource = (source) => {
  if (!source) return '-'
  const sourceMap = {
    'google': 'Google',
    'facebook': 'Facebook',
    'instagram': 'Instagram',
    'linkedin': 'LinkedIn',
    'newspaper': 'Newspaper',
    'afc_bournemouth': 'AFC Bournemouth',
    'word_of_mouth': 'Word of mouth',
    'other': 'Other',
  }
  return sourceMap[source] || source
}

function CustomersPage() {
  const { token } = useAuth()

  // Customers state (matching Admin.jsx lines 181-192)
  const [customers, setCustomers] = useState([])
  const [loadingCustomers, setLoadingCustomers] = useState(false)
  const [customerSearchTerm, setCustomerSearchTerm] = useState('')
  const [customerDateFrom, setCustomerDateFrom] = useState(null)
  const [customerDateTo, setCustomerDateTo] = useState(null)
  const [expandedCustomerMonths, setExpandedCustomerMonths] = useState({})
  const [editingCustomerId, setEditingCustomerId] = useState(null)
  const [editCustomerForm, setEditCustomerForm] = useState({ email: '', phone: '' })
  const [savingCustomer, setSavingCustomer] = useState(false)
  const [deletingCustomerId, setDeletingCustomerId] = useState(null)
  const [customerMessage, setCustomerMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (token) fetchCustomers()
  }, [token])

  const fetchCustomers = async () => {
    setLoadingCustomers(true)
    setError('')
    try {
      const response = await fetch(`${API_URL}/api/admin/customers`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setCustomers(data.customers || [])
      } else {
        setError('Failed to load customers')
      }
    } catch (err) {
      setError('Network error loading customers')
    } finally {
      setLoadingCustomers(false)
    }
  }

  const startEditCustomer = (customer) => {
    setEditingCustomerId(customer.id)
    setEditCustomerForm({ email: customer.email || '', phone: customer.phone || '' })
    setCustomerMessage('')
  }

  const cancelEditCustomer = () => {
    setEditingCustomerId(null)
    setEditCustomerForm({ email: '', phone: '' })
  }

  const saveCustomerEdit = async () => {
    if (!editingCustomerId) return

    setSavingCustomer(true)
    setCustomerMessage('')

    try {
      const response = await fetch(`${API_URL}/api/admin/customers/${editingCustomerId}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(editCustomerForm),
      })

      if (response.ok) {
        const data = await response.json()
        // Update customer in local state
        setCustomers(prev => prev.map(c =>
          c.id === editingCustomerId ? data.customer : c
        ))
        setEditingCustomerId(null)
        setEditCustomerForm({ email: '', phone: '' })
        setCustomerMessage('Customer updated successfully')
        setTimeout(() => setCustomerMessage(''), 3000)
      } else {
        const error = await response.json()
        setCustomerMessage(`Error: ${error.detail || 'Failed to update customer'}`)
      }
    } catch (err) {
      setCustomerMessage('Network error updating customer')
    } finally {
      setSavingCustomer(false)
    }
  }

  const deleteCustomer = async (customerId) => {
    if (!window.confirm('Are you sure you want to delete this customer?')) return

    setDeletingCustomerId(customerId)
    setCustomerMessage('')

    try {
      const response = await fetch(`${API_URL}/api/admin/customers/${customerId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })

      if (response.ok) {
        // Remove from local state
        setCustomers(prev => prev.filter(c => c.id !== customerId))
        setCustomerMessage('Customer deleted successfully')
        setTimeout(() => setCustomerMessage(''), 3000)
      } else {
        const error = await response.json()
        setCustomerMessage(`Error: ${error.detail || 'Failed to delete customer'}`)
      }
    } catch (err) {
      setCustomerMessage('Network error deleting customer')
    } finally {
      setDeletingCustomerId(null)
    }
  }

  const filteredCustomers = useMemo(() => {
    let filtered = [...customers]

    // Apply search filter
    if (customerSearchTerm.trim()) {
      const search = customerSearchTerm.toLowerCase().trim()
      filtered = filtered.filter(c =>
        c.first_name?.toLowerCase().includes(search) ||
        c.last_name?.toLowerCase().includes(search) ||
        c.email?.toLowerCase().includes(search) ||
        c.phone?.includes(search) ||
        c.billing_postcode?.toLowerCase().includes(search) ||
        `${c.first_name} ${c.last_name}`.toLowerCase().includes(search)
      )
    }

    // Apply date filter
    if (customerDateFrom || customerDateTo) {
      filtered = filtered.filter(c => {
        const custDate = c.created_at ? new Date(c.created_at) : null
        if (!custDate) return false
        if (customerDateFrom) {
          const fromDate = new Date(customerDateFrom)
          fromDate.setHours(0, 0, 0, 0)
          if (custDate < fromDate) return false
        }
        if (customerDateTo) {
          const toDate = new Date(customerDateTo)
          toDate.setHours(23, 59, 59, 999)
          if (custDate > toDate) return false
        }
        return true
      })
    }

    return filtered
  }, [customers, customerSearchTerm, customerDateFrom, customerDateTo])

  const downloadCSV = () => {
    // Generate CSV from filtered customers
    const csvRows = [['First Name', 'Last Name', 'Phone', 'Email', 'Post Code', 'Date Signed Up']]
    filteredCustomers.forEach(cust => {
      const dateSignedUp = cust.created_at
        ? new Date(cust.created_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London' })
        : ''
      csvRows.push([
        cust.first_name || '',
        cust.last_name || '',
        cust.phone || '',
        cust.email || '',
        cust.billing_postcode || '',
        dateSignedUp
      ])
    })
    const csvContent = csvRows.map(row => row.map(cell => `"${(cell || '').replace(/"/g, '""')}"`).join(',')).join('\n')
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.setAttribute('href', url)
    // Build descriptive filename based on filters
    const formatDateForFilename = (date) => {
      const day = String(date.getDate()).padStart(2, '0')
      const month = String(date.getMonth() + 1).padStart(2, '0')
      const year = date.getFullYear()
      return `${day}-${month}-${year}`
    }
    let filename = 'customers'
    if (customerDateFrom && customerDateTo) {
      filename = `customers_${formatDateForFilename(customerDateFrom)}_to_${formatDateForFilename(customerDateTo)}`
    } else if (customerDateFrom) {
      filename = `customers_from_${formatDateForFilename(customerDateFrom)}`
    } else if (customerDateTo) {
      filename = `customers_to_${formatDateForFilename(customerDateTo)}`
    } else {
      filename = `customers_all_${formatDateForFilename(new Date())}`
    }
    link.setAttribute('download', `${filename}.csv`)
    link.click()
    URL.revokeObjectURL(url)
  }

  // Group by month
  const renderCustomerTable = () => {
    const monthlyGroups = {}
    filteredCustomers.forEach(customer => {
      const date = customer.created_at ? new Date(customer.created_at) : null
      if (date) {
        const monthKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
        if (!monthlyGroups[monthKey]) monthlyGroups[monthKey] = []
        monthlyGroups[monthKey].push(customer)
      }
    })

    const sortedMonths = Object.keys(monthlyGroups).sort().reverse()  // DESC order
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

    if (sortedMonths.length === 0) {
      return <p className="admin-no-data">No customers found</p>
    }

    return sortedMonths.map(monthKey => {
      const [year, month] = monthKey.split('-')
      const monthName = `${monthNames[parseInt(month, 10) - 1]} ${year}`
      const monthCustomers = monthlyGroups[monthKey]
      const isExpanded = expandedCustomerMonths[monthKey]

      return (
        <div key={monthKey} className="leads-month-container">
          <div
            className="leads-month-header"
            onClick={() => setExpandedCustomerMonths(prev => ({
              ...prev,
              [monthKey]: !prev[monthKey]
            }))}
          >
            <span className="expand-icon">{isExpanded ? '▼' : '▶'}</span>
            <span className="month-name">{monthName}</span>
            <span className="month-total">{monthCustomers.length} customer{monthCustomers.length !== 1 ? 's' : ''}</span>
          </div>
          {isExpanded && (
            <div className="leads-month-content">
              <table className="admin-table leads-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Phone</th>
                    <th>Email</th>
                    <th>Post Code</th>
                    <th>Source</th>
                    <th>Date</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {monthCustomers.map((customer) => (
                    <tr key={customer.id} className={editingCustomerId === customer.id ? 'editing' : ''}>
                      {editingCustomerId === customer.id ? (
                        <>
                          <td>{customer.first_name} {customer.last_name}</td>
                          <td>
                            <input
                              type="text"
                              value={editCustomerForm.phone}
                              onChange={(e) => setEditCustomerForm({...editCustomerForm, phone: e.target.value})}
                              className="flight-edit-input"
                              placeholder="Phone"
                            />
                          </td>
                          <td>
                            <input
                              type="email"
                              value={editCustomerForm.email}
                              onChange={(e) => setEditCustomerForm({...editCustomerForm, email: e.target.value})}
                              className="flight-edit-input"
                              placeholder="Email"
                            />
                          </td>
                          <td>{customer.billing_postcode || '-'}</td>
                          <td>{formatMarketingSource(customer.marketing_source)}</td>
                          <td>
                            {customer.created_at
                              ? new Date(customer.created_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London' })
                              : '-'}
                          </td>
                          <td className="flight-actions">
                            <button className="btn-save" onClick={saveCustomerEdit} disabled={savingCustomer}>
                              {savingCustomer ? '...' : '✓'}
                            </button>
                            <button className="btn-cancel" onClick={cancelEditCustomer}>✕</button>
                          </td>
                        </>
                      ) : (
                        <>
                          <td>{customer.first_name} {customer.last_name}</td>
                          <td>{customer.phone || '-'}</td>
                          <td>{customer.email || '-'}</td>
                          <td>{customer.billing_postcode || '-'}</td>
                          <td>{formatMarketingSource(customer.marketing_source)}</td>
                          <td>
                            {customer.created_at
                              ? new Date(customer.created_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London' })
                              : '-'}
                          </td>
                          <td className="flight-actions">
                            <button className="btn-edit" onClick={() => startEditCustomer(customer)}>Edit</button>
                            <button
                              className="btn-delete"
                              onClick={() => deleteCustomer(customer.id)}
                              disabled={deletingCustomerId === customer.id}
                            >
                              {deletingCustomerId === customer.id ? '...' : 'Delete'}
                            </button>
                          </td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )
    })
  }

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2>Customers</h2>
        <div className="flights-header-actions">
          <button
            className="btn-secondary"
            onClick={fetchCustomers}
            disabled={loadingCustomers}
          >
            {loadingCustomers ? 'Loading...' : '↻ Refresh'}
          </button>
          <button
            className="btn-primary"
            onClick={downloadCSV}
            disabled={loadingCustomers}
          >
            ↓ Download CSV
          </button>
        </div>
      </div>

      <div className="flights-filters">
        <div className="flight-filter-group lead-search-group">
          <input
            type="text"
            placeholder="Search by name, email, phone, or postcode..."
            value={customerSearchTerm}
            onChange={(e) => setCustomerSearchTerm(e.target.value)}
            className="flight-number-input lead-search-input"
          />
          {customerSearchTerm && (
            <button
              className="lead-search-clear"
              onClick={() => setCustomerSearchTerm('')}
            >
              ×
            </button>
          )}
        </div>
        <div className="flight-filter-group leads-date-picker">
          <label>From:</label>
          <DatePicker
            selected={customerDateFrom}
            onChange={(date) => setCustomerDateFrom(date)}
            dateFormat="dd/MM/yyyy"
            placeholderText="DD/MM/YYYY"
            className="flight-date-input"
            isClearable
          />
        </div>
        <div className="flight-filter-group leads-date-picker">
          <label>To:</label>
          <DatePicker
            selected={customerDateTo}
            onChange={(date) => setCustomerDateTo(date)}
            dateFormat="dd/MM/yyyy"
            placeholderText="DD/MM/YYYY"
            className="flight-date-input"
            isClearable
          />
        </div>
        {(customerDateFrom || customerDateTo) && (
          <button
            className="btn-secondary clear-dates-btn"
            onClick={() => { setCustomerDateFrom(null); setCustomerDateTo(null); }}
          >
            × Clear
          </button>
        )}
        <div className="leads-filter-count">
          Showing {filteredCustomers.length} of {customers.length} customers
        </div>
      </div>

      {customerMessage && (
        <div className={`flights-message ${customerMessage.includes('Error') ? 'warning' : 'success'}`}>
          {customerMessage}
        </div>
      )}

      {loadingCustomers ? (
        <div className="admin-loading-inline">
          <div className="spinner-small"></div>
          <span>Loading customers...</span>
        </div>
      ) : filteredCustomers.length === 0 ? (
        <p className="admin-no-data">
          {customers.length === 0 ? 'No customers found' : 'No customers match your search'}
        </p>
      ) : (
        renderCustomerTable()
      )}
    </div>
  )
}

export default CustomersPage
