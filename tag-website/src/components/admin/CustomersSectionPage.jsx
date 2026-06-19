import CustomersSection from './CustomersSection'
import LeadsSection from './LeadsSection'

const CustomersSectionPage = ({
  activeTab,
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
  fetchLeads,
  loadingLeads,
  leadSearchTerm,
  setLeadSearchTerm,
  leads,
  leadDateFrom,
  setLeadDateFrom,
  leadDateTo,
  setLeadDateTo,
  expandedLeadMonths,
  setExpandedLeadMonths,
  expandedLeadId,
  setExpandedLeadId,
}) => {
  if (activeTab === 'customers') {
    return (
      <CustomersSection
        customers={customers}
        filteredCustomers={filteredCustomers}
        loadingCustomers={loadingCustomers}
        customerSearchTerm={customerSearchTerm}
        setCustomerSearchTerm={setCustomerSearchTerm}
        customerDateFrom={customerDateFrom}
        setCustomerDateFrom={setCustomerDateFrom}
        customerDateTo={customerDateTo}
        setCustomerDateTo={setCustomerDateTo}
        fetchCustomers={fetchCustomers}
        customerMessage={customerMessage}
        expandedCustomerMonths={expandedCustomerMonths}
        setExpandedCustomerMonths={setExpandedCustomerMonths}
        formatMarketingSource={formatMarketingSource}
        openCustomerModal={openCustomerModal}
        showCustomerModal={showCustomerModal}
        selectedCustomer={selectedCustomer}
        loadingCustomerDetail={loadingCustomerDetail}
        closeCustomerModal={closeCustomerModal}
        editingCustomerId={editingCustomerId}
        setEditingCustomerId={setEditingCustomerId}
        editCustomerForm={editCustomerForm}
        setEditCustomerForm={setEditCustomerForm}
        saveEditFromModal={saveEditFromModal}
        savingCustomer={savingCustomer}
        startEditFromModal={startEditFromModal}
        deleteCustomerFromModal={deleteCustomerFromModal}
        deletingCustomerId={deletingCustomerId}
        showAddVehicleForm={showAddVehicleForm}
        setShowAddVehicleForm={setShowAddVehicleForm}
        newVehicleForm={newVehicleForm}
        setNewVehicleForm={setNewVehicleForm}
        vehicleLookupLoading={vehicleLookupLoading}
        handleVehicleLookup={handleVehicleLookup}
        handleAddVehicle={handleAddVehicle}
        addingVehicle={addingVehicle}
        onViewReferralDetails={onViewReferralDetails}
      />
    )
  }

  if (activeTab !== 'leads') return null

  return (
    <LeadsSection
      fetchLeads={fetchLeads}
      loadingLeads={loadingLeads}
      leadSearchTerm={leadSearchTerm}
      setLeadSearchTerm={setLeadSearchTerm}
      leads={leads}
      leadDateFrom={leadDateFrom}
      setLeadDateFrom={setLeadDateFrom}
      leadDateTo={leadDateTo}
      setLeadDateTo={setLeadDateTo}
      expandedLeadMonths={expandedLeadMonths}
      setExpandedLeadMonths={setExpandedLeadMonths}
      expandedLeadId={expandedLeadId}
      setExpandedLeadId={setExpandedLeadId}
    />
  )
}

export default CustomersSectionPage

