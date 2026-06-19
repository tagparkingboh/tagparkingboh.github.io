import DatePicker from 'react-datepicker'

const CustomersSection = ({
  customers,
  filteredCustomers,
  loadingCustomers,
  customerSearchTerm,
  setCustomerSearchTerm,
  customerDateFrom,
  setCustomerDateFrom,
  customerDateTo,
  setCustomerDateTo,
  fetchCustomers,
  customerMessage,
  expandedCustomerMonths,
  setExpandedCustomerMonths,
  formatMarketingSource,
  openCustomerModal,
  showCustomerModal,
  selectedCustomer,
  loadingCustomerDetail,
  closeCustomerModal,
  editingCustomerId,
  setEditingCustomerId,
  editCustomerForm,
  setEditCustomerForm,
  saveEditFromModal,
  savingCustomer,
  startEditFromModal,
  deleteCustomerFromModal,
  deletingCustomerId,
  showAddVehicleForm,
  setShowAddVehicleForm,
  newVehicleForm,
  setNewVehicleForm,
  vehicleLookupLoading,
  handleVehicleLookup,
  handleAddVehicle,
  addingVehicle,
  onViewReferralDetails,
}) => {
  const safeCustomers = customers || []
  const safeFilteredCustomers = filteredCustomers || []

  const formatDateForFilename = (date) => {
    const day = String(date.getDate()).padStart(2, '0')
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const year = date.getFullYear()
    return `${day}-${month}-${year}`
  }

  const handleDownloadCsv = () => {
    const csvRows = [['First Name', 'Last Name', 'Phone', 'Email', 'Post Code', 'Date Signed Up']]
    safeFilteredCustomers.forEach(cust => {
      const dateSignedUp = cust.created_at
        ? new Date(cust.created_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London' })
        : ''
      csvRows.push([
        cust.first_name || '',
        cust.last_name || '',
        cust.phone || '',
        cust.email || '',
        cust.billing_postcode || '',
        dateSignedUp,
      ])
    })
    const csvContent = csvRows.map(row => row.map(cell => `"${(cell || '').replace(/"/g, '""')}"`).join(',')).join('\n')
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.setAttribute('href', url)

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

  const monthlyGroups = {}
  safeFilteredCustomers.forEach(customer => {
    const date = customer.created_at ? new Date(customer.created_at) : null
    if (date) {
      const monthKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
      if (!monthlyGroups[monthKey]) monthlyGroups[monthKey] = []
      monthlyGroups[monthKey].push(customer)
    }
  })

  const sortedMonths = Object.keys(monthlyGroups).sort().reverse()
  const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

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
            onClick={handleDownloadCsv}
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
            onClick={() => {
              setCustomerDateFrom(null)
              setCustomerDateTo(null)
            }}
          >
            × Clear
          </button>
        )}
        <div className="leads-filter-count">
          Showing {safeFilteredCustomers.length} of {safeCustomers.length} customers
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
      ) : safeFilteredCustomers.length === 0 ? (
        <p className="admin-no-data">
          {safeCustomers.length === 0 ? 'No customers found' : 'No customers match your search'}
        </p>
      ) : (
        <>
          {sortedMonths.length === 0 ? (
            <p className="admin-no-data">No customers found</p>
          ) : sortedMonths.map(monthKey => {
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
                        </tr>
                      </thead>
                      <tbody>
                        {monthCustomers.map((customer) => (
                          <tr
                            key={customer.id}
                            className="clickable-row"
                            onClick={() => openCustomerModal(customer)}
                          >
                            <td className="customer-name-cell">{customer.first_name} {customer.last_name}</td>
                            <td>{customer.phone || '-'}</td>
                            <td>{customer.email || '-'}</td>
                            <td>{customer.billing_postcode || '-'}</td>
                            <td>{formatMarketingSource(customer.marketing_source)}</td>
                            <td>
                              {customer.created_at
                                ? new Date(customer.created_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London' })
                                : '-'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )
          })}
        </>
      )}

      {showCustomerModal && (
        <div className="modal-overlay" onClick={closeCustomerModal}>
          <div className="modal-content customer-detail-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Customer Details</h3>
              <button className="modal-close" onClick={closeCustomerModal}>&times;</button>
            </div>
            <div className="modal-body">
              {loadingCustomerDetail ? (
                <div className="admin-loading-inline">
                  <div className="spinner-small"></div>
                  <span>Loading customer details...</span>
                </div>
              ) : selectedCustomer ? (
                <>
                  <div className="customer-detail-section">
                    <h4>Contact Information</h4>
                    {editingCustomerId === selectedCustomer.id ? (
                      <div className="customer-edit-form">
                        <div className="form-row">
                          <label>Name:</label>
                          <span>{selectedCustomer.first_name} {selectedCustomer.last_name}</span>
                        </div>
                        <div className="form-row">
                          <label>Phone:</label>
                          <input
                            type="text"
                            value={editCustomerForm.phone}
                            onChange={(e) => setEditCustomerForm({ ...editCustomerForm, phone: e.target.value })}
                            className="form-input"
                          />
                        </div>
                        <div className="form-row">
                          <label>Email:</label>
                          <input
                            type="email"
                            value={editCustomerForm.email}
                            onChange={(e) => setEditCustomerForm({ ...editCustomerForm, email: e.target.value })}
                            className="form-input"
                          />
                        </div>
                        <div className="form-actions">
                          <button className="btn-primary" onClick={saveEditFromModal} disabled={savingCustomer}>
                            {savingCustomer ? 'Saving...' : 'Save'}
                          </button>
                          <button
                            className="btn-secondary"
                            onClick={() => {
                              setEditingCustomerId(null)
                              setEditCustomerForm({ email: '', phone: '' })
                            }}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="customer-info-grid">
                        <div className="info-row">
                          <span className="info-label">Name:</span>
                          <span className="info-value">{selectedCustomer.first_name} {selectedCustomer.last_name}</span>
                        </div>
                        <div className="info-row">
                          <span className="info-label">Phone:</span>
                          <span className="info-value">{selectedCustomer.phone || '-'}</span>
                        </div>
                        <div className="info-row">
                          <span className="info-label">Email:</span>
                          <span className="info-value">{selectedCustomer.email || '-'}</span>
                        </div>
                        <div className="info-row">
                          <span className="info-label">Postcode:</span>
                          <span className="info-value">{selectedCustomer.billing_postcode || '-'}</span>
                        </div>
                        <div className="info-row">
                          <span className="info-label">Source:</span>
                          <span className="info-value">{formatMarketingSource(selectedCustomer.marketing_source)}</span>
                        </div>
                        <div className="info-row">
                          <span className="info-label">Signed Up:</span>
                          <span className="info-value">
                            {selectedCustomer.created_at
                              ? new Date(selectedCustomer.created_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London' })
                              : '-'}
                          </span>
                        </div>
                        <div className="info-row">
                          <span className="info-label">Bookings:</span>
                          <span className="info-value">{selectedCustomer.booking_count || 0}</span>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="customer-detail-section">
                    <div className="section-header">
                      <h4>Referral</h4>
                    </div>
                    {selectedCustomer.referral_program ? (
                      <div className="referral-summary-line">
                        <span>{selectedCustomer.referral_program.status?.replace(/_/g, ' ') || '-'}</span>
                        <span>{selectedCustomer.referral_program.referral_code || 'No code'}</span>
                        <span>{selectedCustomer.referral_program.qualified_referral_count ?? 0} qualified</span>
                        <button
                          type="button"
                          className="link-button"
                          onClick={onViewReferralDetails}
                        >
                          View referral details
                        </button>
                      </div>
                    ) : (
                      <p className="no-data-text">No referral program record</p>
                    )}
                  </div>

                  <div className="customer-detail-section">
                    <div className="section-header">
                      <h4>Vehicles ({selectedCustomer.vehicles?.length || 0})</h4>
                      {!showAddVehicleForm && (
                        <button className="btn-primary btn-small" onClick={() => setShowAddVehicleForm(true)}>
                          + Add Vehicle
                        </button>
                      )}
                    </div>

                    {showAddVehicleForm && (
                      <div className="add-vehicle-form">
                        <div className="form-row">
                          <label>Registration:</label>
                          <div className="reg-lookup-row">
                            <input
                              type="text"
                              value={newVehicleForm.registration}
                              onChange={(e) => setNewVehicleForm({ ...newVehicleForm, registration: e.target.value.toUpperCase() })}
                              className="form-input"
                              placeholder="AB12 CDE"
                            />
                            <button
                              className="btn-secondary btn-small"
                              onClick={handleVehicleLookup}
                              disabled={vehicleLookupLoading || !newVehicleForm.registration}
                            >
                              {vehicleLookupLoading ? '...' : 'Lookup'}
                            </button>
                          </div>
                        </div>
                        <div className="form-row">
                          <label>Make:</label>
                          <input
                            type="text"
                            value={newVehicleForm.make}
                            onChange={(e) => setNewVehicleForm({ ...newVehicleForm, make: e.target.value })}
                            className="form-input"
                            placeholder="e.g. Ford"
                          />
                        </div>
                        <div className="form-row">
                          <label>Colour:</label>
                          <input
                            type="text"
                            value={newVehicleForm.colour}
                            onChange={(e) => setNewVehicleForm({ ...newVehicleForm, colour: e.target.value })}
                            className="form-input"
                            placeholder="e.g. Blue"
                          />
                        </div>
                        <div className="form-actions">
                          <button
                            className="btn-primary"
                            onClick={handleAddVehicle}
                            disabled={addingVehicle || !newVehicleForm.registration || !newVehicleForm.make || !newVehicleForm.colour}
                          >
                            {addingVehicle ? 'Adding...' : 'Add Vehicle'}
                          </button>
                          <button
                            className="btn-secondary"
                            onClick={() => {
                              setShowAddVehicleForm(false)
                              setNewVehicleForm({ registration: '', make: '', model: '', colour: '' })
                            }}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}

                    {selectedCustomer.vehicles?.length > 0 ? (
                      <div className="vehicles-list">
                        {selectedCustomer.vehicles.map(vehicle => (
                          <div key={vehicle.id} className="vehicle-card">
                            <div className="vehicle-reg">{vehicle.registration}</div>
                            <div className="vehicle-details">
                              {vehicle.colour} {vehicle.make} {vehicle.model || ''}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="no-data-text">No vehicles registered</p>
                    )}
                  </div>

                  {editingCustomerId !== selectedCustomer.id && (
                    <div className="modal-actions">
                      <button className="btn-secondary" onClick={startEditFromModal}>
                        Edit Customer
                      </button>
                      <button
                        className="btn-danger"
                        onClick={deleteCustomerFromModal}
                        disabled={deletingCustomerId === selectedCustomer.id || selectedCustomer.booking_count > 0}
                        title={selectedCustomer.booking_count > 0 ? 'Cannot delete customer with bookings' : ''}
                      >
                        {deletingCustomerId === selectedCustomer.id ? 'Deleting...' : 'Delete Customer'}
                      </button>
                    </div>
                  )}
                </>
              ) : (
                <p>Customer not found</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default CustomersSection
