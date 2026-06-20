import { useEffect, useMemo, useState } from 'react'
import CustomersSection from '../CustomersSection'
import { useLocation, useNavigate } from 'react-router-dom'

const CustomersPage = ({
  API_URL,
  token,
  formatMarketingSource,
  onViewReferralDetails,
  onRefreshBookings,
}) => {
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
  const [selectedCustomer, setSelectedCustomer] = useState(null)
  const [showCustomerModal, setShowCustomerModal] = useState(false)
  const [loadingCustomerDetail, setLoadingCustomerDetail] = useState(false)
  const [addingVehicle, setAddingVehicle] = useState(false)
  const [showAddVehicleForm, setShowAddVehicleForm] = useState(false)
  const [newVehicleForm, setNewVehicleForm] = useState({ registration: '', make: '', model: '', colour: '' })
  const [vehicleLookupLoading, setVehicleLookupLoading] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const locationOpenCustomerId = location.state?.openCustomerId

  const fetchCustomers = async () => {
    if (!token) return

    setLoadingCustomers(true)
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
        setCustomerMessage('Failed to load customers')
      }
    } catch (err) {
      setCustomerMessage('Network error loading customers')
    } finally {
      setLoadingCustomers(false)
    }
  }

  // Open customer detail modal
  const openCustomerModal = async (customer) => {
    setShowCustomerModal(true)
    setLoadingCustomerDetail(true)
    setSelectedCustomer(null)
    setShowAddVehicleForm(false)
    setNewVehicleForm({ registration: '', make: '', model: '', colour: '' })

    try {
      const response = await fetch(`${API_URL}/api/admin/customers/${customer.id}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setSelectedCustomer(data)
      } else {
        setCustomerMessage('Failed to load customer details')
        setShowCustomerModal(false)
      }
    } catch (err) {
      setCustomerMessage('Network error loading customer details')
      setShowCustomerModal(false)
    } finally {
      setLoadingCustomerDetail(false)
    }
  }

  const closeCustomerModal = () => {
    setShowCustomerModal(false)
    setSelectedCustomer(null)
    setShowAddVehicleForm(false)
    setNewVehicleForm({ registration: '', make: '', model: '', colour: '' })
  }

  // DVLA vehicle lookup for customer modal
  const handleVehicleLookup = async () => {
    const reg = newVehicleForm.registration.toUpperCase().replace(/\s/g, '')
    if (!reg) return

    setVehicleLookupLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/vehicles/dvla-lookup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ registration: reg }),
      })
      if (response.ok) {
        const data = await response.json()
        setNewVehicleForm(prev => ({
          ...prev,
          registration: reg,
          make: data.make || '',
          colour: data.colour || '',
          tax_status: data.tax_status || null,
          mot_status: data.mot_status || null,
          tax_due_date: data.tax_due_date || null,
          mot_expiry_date: data.mot_expiry_date || null,
        }))
      } else {
        setCustomerMessage('Vehicle not found - please enter details manually')
        setTimeout(() => setCustomerMessage(''), 3000)
      }
    } catch (err) {
      setCustomerMessage('Error looking up vehicle')
      setTimeout(() => setCustomerMessage(''), 3000)
    } finally {
      setVehicleLookupLoading(false)
    }
  }

  // Add vehicle to customer
  const handleAddVehicle = async () => {
    if (!selectedCustomer || !newVehicleForm.registration || !newVehicleForm.make || !newVehicleForm.colour) {
      setCustomerMessage('Please fill in registration, make, and colour')
      setTimeout(() => setCustomerMessage(''), 3000)
      return
    }

    setAddingVehicle(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/customers/${selectedCustomer.id}/vehicles`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(newVehicleForm),
      })

      if (response.ok) {
        const data = await response.json()
        setSelectedCustomer(prev => ({
          ...prev,
          vehicles: [...prev.vehicles, data.vehicle],
        }))
        setShowAddVehicleForm(false)
        setNewVehicleForm({ registration: '', make: '', model: '', colour: '' })
        setCustomerMessage('Vehicle added successfully')
        setTimeout(() => setCustomerMessage(''), 3000)
      } else {
        const error = await response.json()
        setCustomerMessage(`Error: ${error.detail || 'Failed to add vehicle'}`)
        setTimeout(() => setCustomerMessage(''), 5000)
      }
    } catch (err) {
      setCustomerMessage('Network error adding vehicle')
      setTimeout(() => setCustomerMessage(''), 3000)
    } finally {
      setAddingVehicle(false)
    }
  }

  // Delete customer from modal
  const deleteCustomerFromModal = async () => {
    if (!selectedCustomer) return

    setDeletingCustomerId(selectedCustomer.id)
    try {
      const response = await fetch(`${API_URL}/api/admin/customers/${selectedCustomer.id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })

      if (response.ok) {
        setCustomers(prev => prev.filter(c => c.id !== selectedCustomer.id))
        closeCustomerModal()
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

  // Start editing from modal
  const startEditFromModal = () => {
    if (!selectedCustomer) return
    setEditingCustomerId(selectedCustomer.id)
    setEditCustomerForm({ email: selectedCustomer.email || '', phone: selectedCustomer.phone || '' })
  }

  // Save edit from modal
  const saveEditFromModal = async () => {
    if (!selectedCustomer) return

    setSavingCustomer(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/customers/${selectedCustomer.id}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(editCustomerForm),
      })

      if (response.ok) {
        const data = await response.json()
        setCustomers(prev => prev.map(c =>
          c.id === selectedCustomer.id ? data.customer : c
        ))
        setSelectedCustomer(prev => ({
          ...prev,
          email: data.customer.email,
          phone: data.customer.phone,
        }))
        setEditingCustomerId(null)
        setEditCustomerForm({ email: '', phone: '' })
        setCustomerMessage('Customer updated successfully')
        setTimeout(() => setCustomerMessage(''), 3000)
        if (onRefreshBookings) {
          onRefreshBookings()
        }
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

  useEffect(() => {
    fetchCustomers()
  }, [token])

  useEffect(() => {
    if (!locationOpenCustomerId) return
    const customerId = Number(locationOpenCustomerId)
    if (!Number.isFinite(customerId)) return
    openCustomerModal({ id: customerId })
    navigate(`${location.pathname}${location.search}`, { replace: true, state: null })
  }, [location.pathname, location.search, locationOpenCustomerId, openCustomerModal, navigate])

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

export default CustomersPage
