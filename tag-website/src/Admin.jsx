import { useState, useEffect, useMemo } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from './AuthContext'
import ManualBooking from './components/ManualBooking'
import BookingCalendar from './components/BookingCalendar'
import './Admin.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function Admin() {
  const { user, token, loading, isAuthenticated, isAdmin, logout } = useAuth()
  const navigate = useNavigate()

  const [activeTab, setActiveTab] = useState('bookings')
  const [bookings, setBookings] = useState([])
  const [loadingData, setLoadingData] = useState(false)
  const [error, setError] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [sortAsc, setSortAsc] = useState(true)
  const [expandedBookingId, setExpandedBookingId] = useState(null)
  const [cancellingId, setCancellingId] = useState(null)
  const [showCancelModal, setShowCancelModal] = useState(false)
  const [bookingToCancel, setBookingToCancel] = useState(null)
  const [markingPaidId, setMarkingPaidId] = useState(null)
  const [resendingEmailId, setResendingEmailId] = useState(null)
  const [showResendModal, setShowResendModal] = useState(false)
  const [bookingToResend, setBookingToResend] = useState(null)
  const [sendingCancellationEmailId, setSendingCancellationEmailId] = useState(null)
  const [showCancellationEmailModal, setShowCancellationEmailModal] = useState(false)
  const [bookingForCancellationEmail, setBookingForCancellationEmail] = useState(null)
  const [sendingRefundEmailId, setSendingRefundEmailId] = useState(null)
  const [showRefundEmailModal, setShowRefundEmailModal] = useState(false)
  const [bookingForRefundEmail, setBookingForRefundEmail] = useState(null)
  const [successMessage, setSuccessMessage] = useState('')

  // Marketing subscribers state
  const [subscribers, setSubscribers] = useState([])
  const [loadingSubscribers, setLoadingSubscribers] = useState(false)
  const [sendingPromoId, setSendingPromoId] = useState(null)
  const [subscriberSearchTerm, setSubscriberSearchTerm] = useState('')
  const [subscriberStatusFilter, setSubscriberStatusFilter] = useState('all')
  const [hideTestEmails, setHideTestEmails] = useState(true)
  const [expandedSubscriberId, setExpandedSubscriberId] = useState(null)
  const [showPromoModal, setShowPromoModal] = useState(false)
  const [promoToSend, setPromoToSend] = useState(null) // { subscriber, discountPercent }
  const [promoSuccessMessage, setPromoSuccessMessage] = useState('')

  // Abandoned leads state
  const [leads, setLeads] = useState([])
  const [loadingLeads, setLoadingLeads] = useState(false)
  const [leadSearchTerm, setLeadSearchTerm] = useState('')
  const [expandedLeadId, setExpandedLeadId] = useState(null)

  // Pricing settings state - all duration tiers
  const [pricing, setPricing] = useState({
    days_1_4_price: 60,
    days_5_6_price: 72,
    week1_base_price: 79,    // 7 days
    days_8_9_price: 99,
    days_10_11_price: 119,
    days_12_13_price: 130,
    week2_base_price: 140,   // 14 days
    tier_increment: 10,
  })
  const [loadingPricing, setLoadingPricing] = useState(false)
  const [savingPricing, setSavingPricing] = useState(false)
  const [pricingMessage, setPricingMessage] = useState('')

  // Users management state
  const [users, setUsers] = useState([])
  const [loadingUsers, setLoadingUsers] = useState(false)
  const [userSearchTerm, setUserSearchTerm] = useState('')
  const [showUserModal, setShowUserModal] = useState(false)
  const [editingUser, setEditingUser] = useState(null)
  const [userForm, setUserForm] = useState({ first_name: '', last_name: '', email: '', phone: '', is_admin: false, is_active: true })
  const [savingUser, setSavingUser] = useState(false)
  const [showDeleteUserModal, setShowDeleteUserModal] = useState(false)
  const [userToDelete, setUserToDelete] = useState(null)
  const [deletingUser, setDeletingUser] = useState(false)
  const [userSuccessMessage, setUserSuccessMessage] = useState('')

  // Flights management state
  const [flightsSubTab, setFlightsSubTab] = useState('departures')
  const [departures, setDepartures] = useState([])
  const [arrivals, setArrivals] = useState([])
  const [loadingFlights, setLoadingFlights] = useState(false)
  const [flightsSortAsc, setFlightsSortAsc] = useState(true)
  const [flightFilters, setFlightFilters] = useState({ airlines: [], destinations: [], origins: [], months: [] })
  const [flightDestFilter, setFlightDestFilter] = useState('')
  const [flightOriginFilter, setFlightOriginFilter] = useState('')
  const [flightAirlineFilter, setFlightAirlineFilter] = useState('')
  const [flightMonthFilter, setFlightMonthFilter] = useState('')
  const [editingFlightId, setEditingFlightId] = useState(null)
  const [editFlightForm, setEditFlightForm] = useState({})
  const [savingFlight, setSavingFlight] = useState(false)
  const [flightsMessage, setFlightsMessage] = useState('')
  const [exportingFlights, setExportingFlights] = useState(false)

  // Test email domains to filter out
  const testEmailDomains = ['yopmail.com', 'mailinator.com', 'guerrillamail.com', 'tempmail.com', 'fakeinbox.com', 'test.com', 'example.com', 'staging.tag.com']

  const isTestEmail = (email) => {
    if (!email) return false
    const domain = email.toLowerCase().split('@')[1]
    return testEmailDomains.includes(domain) || domain?.includes('test') || domain?.includes('staging')
  }

  // Redirect if not authenticated or not admin
  useEffect(() => {
    if (!loading) {
      if (!isAuthenticated) {
        navigate('/login?redirect=/admin', { replace: true })
      } else if (!isAdmin) {
        navigate('/employee', { replace: true })
      }
    }
  }, [loading, isAuthenticated, isAdmin, navigate])

  // Fetch bookings when tab is active
  useEffect(() => {
    if (activeTab === 'bookings' && token) {
      fetchBookings()
    }
  }, [activeTab, token])

  // Fetch subscribers when marketing tab is active
  useEffect(() => {
    if (activeTab === 'marketing' && token) {
      fetchSubscribers()
    }
  }, [activeTab, token])

  // Fetch leads when leads tab is active
  useEffect(() => {
    if (activeTab === 'leads' && token) {
      fetchLeads()
    }
  }, [activeTab, token])

  // Fetch pricing when pricing tab is active
  useEffect(() => {
    if (activeTab === 'pricing' && token) {
      fetchPricing()
    }
  }, [activeTab, token])

  // Fetch users when users tab is active
  useEffect(() => {
    if (activeTab === 'users' && token) {
      fetchUsers()
    }
  }, [activeTab, token])

  // Fetch flights when flights tab is active
  useEffect(() => {
    if (activeTab === 'flights' && token) {
      fetchFlightFilters()
      fetchFlights()
    }
  }, [activeTab, token])

  // Re-fetch flights when sub-tab or filters change
  useEffect(() => {
    if (activeTab === 'flights' && token) {
      fetchFlights()
    }
  }, [flightsSubTab, flightsSortAsc, flightDestFilter, flightOriginFilter, flightAirlineFilter, flightMonthFilter])

  const fetchSubscribers = async () => {
    setLoadingSubscribers(true)
    setError('')
    try {
      const response = await fetch(`${API_URL}/api/admin/marketing-subscribers`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setSubscribers(data.subscribers || [])
      } else {
        setError('Failed to load subscribers')
      }
    } catch (err) {
      setError('Network error loading subscribers')
    } finally {
      setLoadingSubscribers(false)
    }
  }

  const fetchUsers = async () => {
    setLoadingUsers(true)
    setError('')
    try {
      const response = await fetch(`${API_URL}/api/admin/users`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setUsers(data.users || [])
      } else {
        setError('Failed to load users')
      }
    } catch (err) {
      setError('Network error loading users')
    } finally {
      setLoadingUsers(false)
    }
  }

  // Flights management functions
  const fetchFlightFilters = async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/flights/filters`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setFlightFilters(data)
      }
    } catch (err) {
      console.error('Failed to fetch flight filters:', err)
    }
  }

  const fetchFlights = async () => {
    setLoadingFlights(true)
    setError('')
    try {
      const params = new URLSearchParams()
      params.append('sort_order', flightsSortAsc ? 'asc' : 'desc')
      if (flightAirlineFilter) params.append('airline', flightAirlineFilter)
      if (flightMonthFilter) {
        const [year, month] = flightMonthFilter.split('-')
        params.append('year', year)
        params.append('month', month)
      }

      if (flightsSubTab === 'departures') {
        if (flightDestFilter) params.append('destination', flightDestFilter)
        const response = await fetch(`${API_URL}/api/admin/flights/departures?${params}`, {
          headers: { 'Authorization': `Bearer ${token}` },
        })
        if (response.ok) {
          const data = await response.json()
          setDepartures(data.departures || [])
        }
      } else {
        if (flightOriginFilter) params.append('origin', flightOriginFilter)
        const response = await fetch(`${API_URL}/api/admin/flights/arrivals?${params}`, {
          headers: { 'Authorization': `Bearer ${token}` },
        })
        if (response.ok) {
          const data = await response.json()
          setArrivals(data.arrivals || [])
        }
      }
    } catch (err) {
      setError('Network error loading flights')
    } finally {
      setLoadingFlights(false)
    }
  }

  const startEditFlight = (flight) => {
    setEditingFlightId(flight.id)
    setEditFlightForm({ ...flight })
  }

  const cancelEditFlight = () => {
    setEditingFlightId(null)
    setEditFlightForm({})
  }

  const saveFlightEdit = async () => {
    setSavingFlight(true)
    setFlightsMessage('')
    try {
      const endpoint = flightsSubTab === 'departures'
        ? `${API_URL}/api/admin/flights/departures/${editingFlightId}`
        : `${API_URL}/api/admin/flights/arrivals/${editingFlightId}`

      const response = await fetch(endpoint, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(editFlightForm),
      })

      if (response.ok) {
        const data = await response.json()
        if (data.warnings && data.warnings.length > 0) {
          setFlightsMessage(`Saved with warnings: ${data.warnings.join(', ')}`)
        } else {
          setFlightsMessage('Flight updated successfully')
        }
        setEditingFlightId(null)
        setEditFlightForm({})
        fetchFlights()
        setTimeout(() => setFlightsMessage(''), 3000)
      } else {
        const err = await response.json()
        setFlightsMessage(`Error: ${err.detail || 'Failed to save'}`)
      }
    } catch (err) {
      setFlightsMessage('Network error saving flight')
    } finally {
      setSavingFlight(false)
    }
  }

  const exportFlights = async () => {
    setExportingFlights(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/flights/export?flight_type=all`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `flights-export-${new Date().toISOString().split('T')[0]}.json`
        a.click()
        URL.revokeObjectURL(url)
        setFlightsMessage('Export downloaded successfully')
        setTimeout(() => setFlightsMessage(''), 3000)
      }
    } catch (err) {
      setFlightsMessage('Error exporting flights')
    } finally {
      setExportingFlights(false)
    }
  }

  const openAddUserModal = () => {
    setEditingUser(null)
    setUserForm({ first_name: '', last_name: '', email: '', phone: '', is_admin: false, is_active: true })
    setShowUserModal(true)
  }

  const openEditUserModal = (u) => {
    setEditingUser(u)
    setUserForm({
      first_name: u.first_name || '',
      last_name: u.last_name || '',
      email: u.email || '',
      phone: u.phone || '',
      is_admin: u.is_admin,
      is_active: u.is_active,
    })
    setShowUserModal(true)
  }

  const handleSaveUser = async () => {
    setSavingUser(true)
    setError('')
    try {
      const url = editingUser
        ? `${API_URL}/api/admin/users/${editingUser.id}`
        : `${API_URL}/api/admin/users`
      const method = editingUser ? 'PUT' : 'POST'
      const response = await fetch(url, {
        method,
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(userForm),
      })
      if (response.ok) {
        setShowUserModal(false)
        setUserSuccessMessage(editingUser ? 'User updated successfully' : 'User created successfully')
        setTimeout(() => setUserSuccessMessage(''), 3000)
        fetchUsers()
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to save user')
      }
    } catch (err) {
      setError('Network error saving user')
    } finally {
      setSavingUser(false)
    }
  }

  const handleToggleUserField = async (u, field) => {
    try {
      const response = await fetch(`${API_URL}/api/admin/users/${u.id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ [field]: !u[field] }),
      })
      if (response.ok) {
        fetchUsers()
      } else {
        const data = await response.json()
        setError(data.detail || `Failed to update ${field}`)
        setTimeout(() => setError(''), 3000)
      }
    } catch (err) {
      setError(`Network error updating ${field}`)
    }
  }

  const handleDeleteUser = async () => {
    if (!userToDelete) return
    setDeletingUser(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/users/${userToDelete.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        setShowDeleteUserModal(false)
        setUserToDelete(null)
        setUserSuccessMessage('User deleted successfully')
        setTimeout(() => setUserSuccessMessage(''), 3000)
        fetchUsers()
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to delete user')
      }
    } catch (err) {
      setError('Network error deleting user')
    } finally {
      setDeletingUser(false)
    }
  }

  const filteredUsers = useMemo(() => {
    if (!userSearchTerm) return users
    const term = userSearchTerm.toLowerCase()
    return users.filter(u =>
      (u.first_name || '').toLowerCase().includes(term) ||
      (u.last_name || '').toLowerCase().includes(term) ||
      (u.email || '').toLowerCase().includes(term)
    )
  }, [users, userSearchTerm])

  const fetchLeads = async () => {
    setLoadingLeads(true)
    setError('')
    try {
      const response = await fetch(`${API_URL}/api/admin/abandoned-leads`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setLeads(data.leads || [])
      } else {
        setError('Failed to load leads')
      }
    } catch (err) {
      setError('Network error loading leads')
    } finally {
      setLoadingLeads(false)
    }
  }

  const fetchPricing = async () => {
    setLoadingPricing(true)
    setPricingMessage('')
    try {
      const response = await fetch(`${API_URL}/api/admin/pricing`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setPricing({
          days_1_4_price: data.days_1_4_price ?? 60,
          days_5_6_price: data.days_5_6_price ?? 72,
          week1_base_price: data.week1_base_price ?? 79,
          days_8_9_price: data.days_8_9_price ?? 99,
          days_10_11_price: data.days_10_11_price ?? 119,
          days_12_13_price: data.days_12_13_price ?? 130,
          week2_base_price: data.week2_base_price ?? 140,
          tier_increment: data.tier_increment ?? 10,
        })
      } else {
        setError('Failed to load pricing settings')
      }
    } catch (err) {
      setError('Network error loading pricing')
    } finally {
      setLoadingPricing(false)
    }
  }

  const savePricing = async () => {
    setSavingPricing(true)
    setPricingMessage('')
    setError('')
    try {
      const response = await fetch(`${API_URL}/api/admin/pricing`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(pricing),
      })
      if (response.ok) {
        const data = await response.json()
        setPricingMessage('Pricing updated successfully')
        setTimeout(() => setPricingMessage(''), 5000)
        // Notify other tabs (e.g., HomePage) that pricing was updated
        const channel = new BroadcastChannel('pricing-updates')
        channel.postMessage('pricing-updated')
        channel.close()
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to save pricing')
      }
    } catch (err) {
      setError('Network error saving pricing')
    } finally {
      setSavingPricing(false)
    }
  }

  const openPromoModal = (subscriber, discountPercent) => {
    setPromoToSend({ subscriber, discountPercent })
    setShowPromoModal(true)
  }

  const confirmSendPromo = async () => {
    if (!promoToSend) return

    const { subscriber, discountPercent } = promoToSend
    setSendingPromoId(subscriber.id)
    setError('')

    try {
      const response = await fetch(
        `${API_URL}/api/admin/marketing-subscribers/${subscriber.id}/send-promo?discount_percent=${discountPercent}`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      )

      const data = await response.json()

      if (response.ok) {
        // Show success message
        const promoType = discountPercent === 100 ? 'FREE Parking' : '10% Off'
        setPromoSuccessMessage(`${promoType} promo code sent to ${subscriber.email}`)
        setTimeout(() => setPromoSuccessMessage(''), 5000) // Clear after 5 seconds
        // Refresh subscribers list
        fetchSubscribers()
        setShowPromoModal(false)
        setPromoToSend(null)
      } else {
        setError(data.detail || 'Failed to send promo email')
      }
    } catch (err) {
      setError('Network error sending promo email')
    } finally {
      setSendingPromoId(null)
    }
  }

  const fetchBookings = async () => {
    setLoadingData(true)
    setError('')
    try {
      const response = await fetch(`${API_URL}/api/admin/bookings`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setBookings(data.bookings || data || [])
      } else {
        setError('Failed to load bookings')
      }
    } catch (err) {
      setError('Network error')
    } finally {
      setLoadingData(false)
    }
  }

  // Filter and sort bookings
  const filteredBookings = useMemo(() => {
    let filtered = [...bookings]

    // Hide test emails by default
    if (hideTestEmails) {
      filtered = filtered.filter(b => !isTestEmail(b.customer?.email))
    }

    // Apply status filter
    if (statusFilter !== 'all') {
      filtered = filtered.filter(b => b.status?.toLowerCase() === statusFilter)
    }

    // Apply search filter
    if (searchTerm.trim()) {
      const search = searchTerm.toLowerCase().trim()
      filtered = filtered.filter(b =>
        b.reference?.toLowerCase().includes(search) ||
        b.customer?.first_name?.toLowerCase().includes(search) ||
        b.customer?.last_name?.toLowerCase().includes(search) ||
        b.customer?.email?.toLowerCase().includes(search) ||
        b.vehicle?.registration?.toLowerCase().includes(search) ||
        `${b.customer?.first_name} ${b.customer?.last_name}`.toLowerCase().includes(search)
      )
    }

    // Sort by dropoff date
    filtered.sort((a, b) => {
      const dateA = new Date(a.dropoff_date)
      const dateB = new Date(b.dropoff_date)
      return sortAsc ? dateA - dateB : dateB - dateA
    })

    return filtered
  }, [bookings, searchTerm, statusFilter, hideTestEmails, sortAsc])

  // Filter subscribers
  const filteredSubscribers = useMemo(() => {
    let filtered = [...subscribers]

    // Hide test emails by default
    if (hideTestEmails) {
      filtered = filtered.filter(s => !isTestEmail(s.email))
    }

    // Apply status filter
    if (subscriberStatusFilter !== 'all') {
      filtered = filtered.filter(s => {
        if (subscriberStatusFilter === 'pending') return !s.promo_10_sent && !s.promo_free_sent && !s.unsubscribed
        if (subscriberStatusFilter === 'sent') return (s.promo_10_sent || s.promo_free_sent) && !s.promo_10_used && !s.promo_free_used && !s.unsubscribed
        if (subscriberStatusFilter === 'used') return s.promo_10_used || s.promo_free_used
        if (subscriberStatusFilter === 'unsubscribed') return s.unsubscribed
        return true
      })
    }

    // Apply search filter
    if (subscriberSearchTerm.trim()) {
      const search = subscriberSearchTerm.toLowerCase().trim()
      filtered = filtered.filter(s =>
        s.first_name?.toLowerCase().includes(search) ||
        s.last_name?.toLowerCase().includes(search) ||
        s.email?.toLowerCase().includes(search) ||
        s.promo_code?.toLowerCase().includes(search) ||
        s.promo_10_code?.toLowerCase().includes(search) ||
        s.promo_free_code?.toLowerCase().includes(search) ||
        `${s.first_name} ${s.last_name}`.toLowerCase().includes(search)
      )
    }

    return filtered
  }, [subscribers, subscriberSearchTerm, subscriberStatusFilter, hideTestEmails])

  const toggleBookingExpanded = (bookingId) => {
    setExpandedBookingId(expandedBookingId === bookingId ? null : bookingId)
  }

  const handleCancelClick = (booking, e) => {
    e.stopPropagation()
    setBookingToCancel(booking)
    setShowCancelModal(true)
  }

  const handleConfirmCancel = async () => {
    if (!bookingToCancel) return

    setCancellingId(bookingToCancel.id)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/${bookingToCancel.id}/cancel`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        // Refresh bookings list
        await fetchBookings()
        setShowCancelModal(false)
        setBookingToCancel(null)
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to cancel booking')
      }
    } catch (err) {
      setError('Network error while cancelling booking')
    } finally {
      setCancellingId(null)
    }
  }

  const handleMarkPaid = async (booking, e) => {
    e.stopPropagation()
    setMarkingPaidId(booking.id)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/${booking.id}/mark-paid`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
      })

      const data = await response.json()

      if (response.ok) {
        // Refresh bookings list
        fetchBookings()
      } else {
        setError(data.detail || 'Failed to mark booking as paid')
      }
    } catch (err) {
      setError('Network error while updating booking')
    } finally {
      setMarkingPaidId(null)
    }
  }

  const handleRefundClick = (booking, e) => {
    e.stopPropagation()
    // Open Stripe dashboard to the payment intent
    const paymentIntentId = booking.payment?.stripe_payment_intent_id
    if (paymentIntentId) {
      // Stripe dashboard URL for payment intent
      const stripeUrl = `https://dashboard.stripe.com/payments/${paymentIntentId}`
      window.open(stripeUrl, '_blank')
    } else {
      setError('No payment found for this booking')
    }
  }

  const handleResendEmailClick = (booking, e) => {
    e.stopPropagation()
    setBookingToResend(booking)
    setShowResendModal(true)
  }

  const handleConfirmResendEmail = async () => {
    if (!bookingToResend) return

    setResendingEmailId(bookingToResend.id)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/${bookingToResend.id}/resend-email`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        setShowResendModal(false)
        setBookingToResend(null)
        // Show success (could use a toast, but we'll just clear error)
        setError('')
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to send confirmation email')
      }
    } catch (err) {
      setError('Network error while sending email')
    } finally {
      setResendingEmailId(null)
    }
  }

  const handleSendCancellationEmailClick = (booking, e) => {
    e.stopPropagation()
    setBookingForCancellationEmail(booking)
    setShowCancellationEmailModal(true)
  }

  const handleConfirmSendCancellationEmail = async () => {
    if (!bookingForCancellationEmail) return

    setSendingCancellationEmailId(bookingForCancellationEmail.id)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/${bookingForCancellationEmail.id}/send-cancellation-email`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        setShowCancellationEmailModal(false)
        setSuccessMessage(`Cancellation email sent to ${bookingForCancellationEmail.customer?.email}`)
        setBookingForCancellationEmail(null)
        // Refresh bookings to update email sent status
        await fetchBookings()
        // Clear success message after 5 seconds
        setTimeout(() => setSuccessMessage(''), 5000)
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to send cancellation email')
      }
    } catch (err) {
      setError('Network error while sending cancellation email')
    } finally {
      setSendingCancellationEmailId(null)
    }
  }

  const handleSendRefundEmailClick = (booking, e) => {
    e.stopPropagation()
    setBookingForRefundEmail(booking)
    setShowRefundEmailModal(true)
  }

  const handleConfirmSendRefundEmail = async () => {
    if (!bookingForRefundEmail) return

    setSendingRefundEmailId(bookingForRefundEmail.id)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/${bookingForRefundEmail.id}/send-refund-email`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        setShowRefundEmailModal(false)
        setSuccessMessage(`Refund email sent to ${bookingForRefundEmail.customer?.email}`)
        setBookingForRefundEmail(null)
        // Refresh bookings to update email sent status
        await fetchBookings()
        // Clear success message after 5 seconds
        setTimeout(() => setSuccessMessage(''), 5000)
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to send refund email')
      }
    } catch (err) {
      setError('Network error while sending refund email')
    } finally {
      setSendingRefundEmailId(null)
    }
  }

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return '-'
    // Parse date parts manually to avoid timezone conversion issues
    // dateStr format: "YYYY-MM-DD" from API
    const [year, month, day] = dateStr.split('-')
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    // Create date in local timezone for weekday calculation
    const date = new Date(Number(year), Number(month) - 1, Number(day))
    return `${days[date.getDay()]}, ${day} ${months[Number(month) - 1]} ${year}`
  }

  const formatTime = (timeStr) => {
    if (!timeStr) return ''
    // Handle both "HH:MM:SS" and "HH:MM" formats
    return timeStr.substring(0, 5)
  }

  if (loading) {
    return (
      <div className="admin-loading">
        <div className="spinner"></div>
        <p>Loading...</p>
      </div>
    )
  }

  if (!isAuthenticated || !isAdmin) {
    return null
  }

  return (
    <div className="admin-container">
      <header className="admin-header">
        <div className="admin-header-left">
          <Link to="/">
            <img src="/assets/logo.svg" alt="TAG Parking" className="admin-logo" />
          </Link>
          <h1>Admin Dashboard</h1>
        </div>
        <div className="admin-header-right">
          <span className="admin-user">
            {user?.first_name} {user?.last_name}
          </span>
          <button onClick={handleLogout} className="admin-logout">
            Logout
          </button>
        </div>
      </header>

      <nav className="admin-nav">
        <button
          className={`admin-nav-item ${activeTab === 'bookings' ? 'active' : ''}`}
          onClick={() => setActiveTab('bookings')}
        >
          Bookings
        </button>
        <button
          className={`admin-nav-item ${activeTab === 'calendar' ? 'active' : ''}`}
          onClick={() => setActiveTab('calendar')}
        >
          Calendar
        </button>
        <button
          className={`admin-nav-item ${activeTab === 'manual-booking' ? 'active' : ''}`}
          onClick={() => setActiveTab('manual-booking')}
        >
          Manual Booking
        </button>
        <button
          className={`admin-nav-item ${activeTab === 'users' ? 'active' : ''}`}
          onClick={() => setActiveTab('users')}
        >
          Users
        </button>
        <button
          className={`admin-nav-item ${activeTab === 'flights' ? 'active' : ''}`}
          onClick={() => setActiveTab('flights')}
        >
          Flights
        </button>
        <button
          className={`admin-nav-item ${activeTab === 'marketing' ? 'active' : ''}`}
          onClick={() => setActiveTab('marketing')}
        >
          Marketing
        </button>
        <button
          className={`admin-nav-item ${activeTab === 'leads' ? 'active' : ''}`}
          onClick={() => setActiveTab('leads')}
        >
          Leads
        </button>
        <button
          className={`admin-nav-item ${activeTab === 'pricing' ? 'active' : ''}`}
          onClick={() => setActiveTab('pricing')}
        >
          Pricing
        </button>
        <button
          className={`admin-nav-item ${activeTab === 'reports' ? 'active' : ''}`}
          onClick={() => setActiveTab('reports')}
        >
          Reports
        </button>
      </nav>

      <main className="admin-content">
        {error && <div className="admin-error">{error}</div>}
        {successMessage && <div className="admin-success">{successMessage}</div>}

        {activeTab === 'bookings' && (
          <div className="admin-section">
            <div className="admin-section-header">
              <h2>Bookings</h2>
              <button onClick={fetchBookings} className="admin-refresh" disabled={loadingData}>
                {loadingData ? 'Loading...' : 'Refresh'}
              </button>
            </div>

            {/* Search and Filter Controls */}
            <div className="admin-filters">
              <div className="admin-search">
                <input
                  type="text"
                  placeholder="Search by reference, name, email, or registration..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="admin-search-input"
                />
                {searchTerm && (
                  <button
                    className="admin-search-clear"
                    onClick={() => setSearchTerm('')}
                  >
                    &times;
                  </button>
                )}
              </div>
              <div className="admin-filter-group">
                <label>Status:</label>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="admin-filter-select"
                >
                  <option value="all">All Statuses</option>
                  <option value="pending">Pending</option>
                  <option value="confirmed">Confirmed</option>
                  <option value="completed">Completed</option>
                  <option value="cancelled">Cancelled</option>
                  <option value="refunded">Refunded</option>
                </select>
              </div>
              <label className="admin-checkbox-label">
                <input
                  type="checkbox"
                  checked={hideTestEmails}
                  onChange={(e) => setHideTestEmails(e.target.checked)}
                />
                Hide test emails
              </label>
              <button
                className="admin-sort-btn"
                onClick={() => setSortAsc(!sortAsc)}
                title={sortAsc ? 'Sorted by drop-off date (earliest first)' : 'Sorted by drop-off date (latest first)'}
              >
                Drop-off {sortAsc ? '↑' : '↓'}
              </button>
              <div className="admin-filter-count">
                Showing {filteredBookings.length} of {bookings.length} bookings
              </div>
            </div>

            {loadingData ? (
              <div className="admin-loading-inline">
                <div className="spinner-small"></div>
                <span>Loading bookings...</span>
              </div>
            ) : filteredBookings.length === 0 ? (
              <p className="admin-empty">
                {bookings.length === 0 ? 'No bookings found' : 'No bookings match your search'}
              </p>
            ) : (
              <div className="booking-accordion">
                {filteredBookings.map((booking) => (
                  <div
                    key={booking.id || booking.reference}
                    className={`booking-card ${expandedBookingId === booking.id ? 'expanded' : ''} booking-status-${booking.status?.toLowerCase() || 'pending'}`}
                  >
                    {/* Collapsed Header Row */}
                    <div
                      className="booking-card-header booking-header-stacked"
                      onClick={() => toggleBookingExpanded(booking.id)}
                    >
                      <div className="booking-header-info">
                        <div className="booking-header-top">
                          <span className="booking-ref-large">{booking.reference}</span>
                          {booking.booking_source === 'manual' && (
                            <span className="booking-source-badge manual">Manual</span>
                          )}
                        </div>
                        <span className="booking-customer-name">
                          {booking.customer?.first_name} {booking.customer?.last_name}
                        </span>
                      </div>
                    </div>

                    {/* Expanded Content */}
                    {expandedBookingId === booking.id && (
                      <div className="booking-card-body">
                        {/* Contact Details Section */}
                        <div className="booking-section">
                          <h4>Contact Details</h4>
                          <div className="booking-section-content">
                            <div className="booking-detail">
                              <span className="detail-label">Name</span>
                              <span className="detail-value">
                                {booking.customer?.first_name} {booking.customer?.last_name}
                              </span>
                            </div>
                            <div className="booking-detail">
                              <span className="detail-label">Email</span>
                              <span className="detail-value">{booking.customer?.email}</span>
                            </div>
                            {booking.customer?.phone && (
                              <div className="booking-detail">
                                <span className="detail-label">Phone</span>
                                <span className="detail-value">{booking.customer?.phone}</span>
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Booking Information Section */}
                        <div className="booking-section">
                          <h4>Booking Information</h4>
                          <div className="booking-section-content">
                            <div className="booking-detail-row">
                              <div className="booking-detail">
                                <span className="detail-label">Booking Reference</span>
                                <span className="detail-value booking-ref">{booking.reference}</span>
                              </div>
                              <div className="booking-detail">
                                <span className="detail-label">Source</span>
                                <span className="detail-value">
                                  <span className={`source-badge ${booking.booking_source || 'online'}`}>
                                    {booking.booking_source === 'manual' ? 'Manual Booking' :
                                     booking.booking_source === 'admin' ? 'Admin' :
                                     booking.booking_source === 'phone' ? 'Phone' :
                                     'Online'}
                                  </span>
                                </span>
                              </div>
                              <div className="booking-detail">
                                <span className="detail-label">Package</span>
                                <span className="detail-value">
                                  {booking.package === 'quick' ? '1 Week' :
                                   booking.package === 'longer' ? '2 Weeks' :
                                   booking.package || 'N/A'}
                                </span>
                              </div>
                              <div className="booking-detail">
                                <span className="detail-label">Vehicle</span>
                                <span className="detail-value">
                                  <span className="vehicle-reg">{booking.vehicle?.registration}</span>
                                  {' '}
                                  {booking.vehicle?.colour} {booking.vehicle?.make} {booking.vehicle?.model}
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>

                        {/* Drop-off / Departure Section */}
                        <div className="booking-section">
                          <h4>Drop-off / Departure</h4>
                          <div className="booking-section-content">
                            <div className="booking-detail-row">
                              <div className="booking-detail">
                                <span className="detail-label">Drop-off Date</span>
                                <span className="detail-value">{formatDate(booking.dropoff_date)}</span>
                              </div>
                              <div className="booking-detail">
                                <span className="detail-label">Drop-off Time</span>
                                <span className="detail-value">{formatTime(booking.dropoff_time)}</span>
                              </div>
                              <div className="booking-detail">
                                <span className="detail-label">Flight</span>
                                <span className="detail-value">
                                  {booking.dropoff_airline_name && (
                                    <span className="airline-name">{booking.dropoff_airline_name}</span>
                                  )}
                                  <span className="flight-number">{booking.dropoff_flight_number || '-'}</span>
                                </span>
                              </div>
                              <div className="booking-detail">
                                <span className="detail-label">Destination</span>
                                <span className="detail-value">{booking.dropoff_destination || '-'}</span>
                              </div>
                            </div>
                          </div>
                        </div>

                        {/* Pick-up / Return Section */}
                        <div className="booking-section">
                          <h4>Pick-up / Return</h4>
                          <div className="booking-section-content">
                            <div className="booking-detail-row">
                              <div className="booking-detail">
                                <span className="detail-label">Pick-up Date</span>
                                <span className="detail-value">{formatDate(booking.pickup_date)}</span>
                              </div>
                              <div className="booking-detail">
                                <span className="detail-label">Pick-up Time</span>
                                <span className="detail-value">
                                  {booking.booking_source === 'manual'
                                    ? (booking.pickup_time || '-')
                                    : (booking.pickup_collection_time
                                        ? `From ${booking.pickup_collection_time} onwards`
                                        : '-')}
                                </span>
                              </div>
                              <div className="booking-detail">
                                <span className="detail-label">Flight</span>
                                <span className="detail-value">
                                  <span className="flight-number">{booking.pickup_flight_number || '-'}</span>
                                </span>
                              </div>
                              <div className="booking-detail">
                                <span className="detail-label">Origin</span>
                                <span className="detail-value">{booking.pickup_origin || '-'}</span>
                              </div>
                            </div>
                          </div>
                        </div>

                        {/* Status & Payment Section */}
                        <div className="booking-section">
                          <h4>Status & Payment</h4>
                          <div className="booking-section-content">
                            <div className="booking-detail-row">
                              <div className="booking-detail">
                                <span className="detail-label">Booking Status</span>
                                <span className={`status-badge status-${booking.status?.toLowerCase()}`}>
                                  {booking.status}
                                </span>
                              </div>
                              <div className="booking-detail">
                                <span className="detail-label">Payment Status</span>
                                <span className={`status-badge payment-${booking.payment?.status?.toLowerCase()}`}>
                                  {booking.payment?.status || 'N/A'}
                                </span>
                              </div>
                              {booking.payment?.amount_pence && (
                                <div className="booking-detail">
                                  <span className="detail-label">Amount</span>
                                  <span className="detail-value">
                                    £{(booking.payment.amount_pence / 100).toFixed(2)}
                                  </span>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Actions Section */}
                        <div className="booking-section booking-actions-section">
                          <h4>Actions</h4>
                          <div className="booking-actions">
                            <button
                              className="action-btn email-btn"
                              onClick={(e) => handleResendEmailClick(booking, e)}
                              disabled={resendingEmailId === booking.id}
                            >
                              {resendingEmailId === booking.id ? 'Sending...' : 'Resend Confirmation Email'}
                            </button>
                            {/* Show cancellation email button only when status is cancelled */}
                            {booking.status?.toLowerCase() === 'cancelled' && (
                              <button
                                className="action-btn email-btn"
                                onClick={(e) => handleSendCancellationEmailClick(booking, e)}
                                disabled={sendingCancellationEmailId === booking.id}
                              >
                                {sendingCancellationEmailId === booking.id ? 'Sending...' : 'Send Cancellation Email'}
                              </button>
                            )}
                            {/* Show refund email button only when status is cancelled */}
                            {booking.status?.toLowerCase() === 'cancelled' && (
                              <button
                                className="action-btn email-btn"
                                onClick={(e) => handleSendRefundEmailClick(booking, e)}
                                disabled={sendingRefundEmailId === booking.id}
                              >
                                {sendingRefundEmailId === booking.id ? 'Sending...' : 'Send Refund Email'}
                              </button>
                            )}
                            {booking.payment?.stripe_payment_intent_id &&
                             booking.payment?.status?.toLowerCase() === 'succeeded' &&
                             booking.status?.toLowerCase() !== 'refunded' && (
                              <button
                                className="action-btn refund-btn"
                                onClick={(e) => handleRefundClick(booking, e)}
                              >
                                Process Refund
                              </button>
                            )}
                            {booking.status?.toLowerCase() !== 'cancelled' &&
                             booking.status?.toLowerCase() !== 'refunded' && (
                              <button
                                className="action-btn cancel-btn"
                                onClick={(e) => handleCancelClick(booking, e)}
                                disabled={cancellingId === booking.id}
                              >
                                {cancellingId === booking.id ? 'Cancelling...' : 'Cancel Booking'}
                              </button>
                            )}
                            {/* Mark as Paid button for manual bookings with pending status */}
                            {booking.booking_source === 'manual' &&
                             booking.status?.toLowerCase() === 'pending' && (
                              <button
                                className="action-btn paid-btn"
                                onClick={(e) => handleMarkPaid(booking, e)}
                                disabled={markingPaidId === booking.id}
                              >
                                {markingPaidId === booking.id ? 'Updating...' : 'Mark as Paid'}
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'calendar' && (
          <div className="admin-section">
            <BookingCalendar token={token} />
          </div>
        )}

        {activeTab === 'manual-booking' && (
          <div className="admin-section">
            <ManualBooking token={token} />
          </div>
        )}

        {activeTab === 'users' && (
          <div className="admin-section">
            <div className="admin-section-header">
              <h2>User Management</h2>
              <button className="action-btn paid-btn" onClick={openAddUserModal}>+ Add User</button>
            </div>

            {userSuccessMessage && (
              <div className="success-banner">{userSuccessMessage}</div>
            )}

            {error && <div className="admin-error">{error}</div>}

            <div className="admin-filters">
              <div className="admin-search">
                <input
                  type="text"
                  className="admin-search-input"
                  placeholder="Search by name or email..."
                  value={userSearchTerm}
                  onChange={(e) => setUserSearchTerm(e.target.value)}
                />
                {userSearchTerm && (
                  <button className="admin-search-clear" onClick={() => setUserSearchTerm('')}>&times;</button>
                )}
              </div>
              <span className="admin-filter-count">{filteredUsers.length} user{filteredUsers.length !== 1 ? 's' : ''}</span>
            </div>

            {loadingUsers ? (
              <div className="admin-loading-inline"><div className="spinner-small"></div> Loading users...</div>
            ) : filteredUsers.length === 0 ? (
              <p className="admin-empty">No users found</p>
            ) : (
              <div className="admin-table-container">
                <table className="admin-table users-table">
                  <thead>
                    <tr>
                      <th>First Name</th>
                      <th>Last Name</th>
                      <th>Email</th>
                      <th>Admin</th>
                      <th>Active</th>
                      <th>Last Login</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredUsers.map(u => (
                      <tr key={u.id} className={!u.is_active ? 'user-inactive' : ''}>
                        <td>{u.first_name}</td>
                        <td>{u.last_name}</td>
                        <td>{u.email}</td>
                        <td>
                          <button
                            className={`toggle-btn ${u.is_admin ? 'toggle-on' : 'toggle-off'}`}
                            onClick={() => handleToggleUserField(u, 'is_admin')}
                            title={u.is_admin ? 'Remove admin' : 'Make admin'}
                          >
                            {u.is_admin ? 'Yes' : 'No'}
                          </button>
                        </td>
                        <td>
                          <button
                            className={`toggle-btn ${u.is_active ? 'toggle-on' : 'toggle-off'}`}
                            onClick={() => handleToggleUserField(u, 'is_active')}
                            title={u.is_active ? 'Deactivate' : 'Activate'}
                          >
                            {u.is_active ? 'Yes' : 'No'}
                          </button>
                        </td>
                        <td className="small-text">{u.last_login ? new Date(u.last_login).toLocaleDateString('en-GB') : 'Never'}</td>
                        <td className="actions-cell">
                          <button className="action-btn email-btn" onClick={() => openEditUserModal(u)}>Edit</button>
                          <button className="action-btn cancel-btn" onClick={() => { setUserToDelete(u); setShowDeleteUserModal(true) }}>Delete</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Add/Edit User Modal */}
            {showUserModal && (
              <div className="modal-overlay" onClick={() => setShowUserModal(false)}>
                <div className="modal-content" onClick={e => e.stopPropagation()}>
                  <h3>{editingUser ? 'Edit User' : 'Add User'}</h3>
                  <div className="user-form">
                    <div className="user-form-row">
                      <div className="user-form-field">
                        <label>First Name</label>
                        <input type="text" value={userForm.first_name} onChange={e => setUserForm({...userForm, first_name: e.target.value})} />
                      </div>
                      <div className="user-form-field">
                        <label>Last Name</label>
                        <input type="text" value={userForm.last_name} onChange={e => setUserForm({...userForm, last_name: e.target.value})} />
                      </div>
                    </div>
                    <div className="user-form-field">
                      <label>Email</label>
                      <input type="email" value={userForm.email} onChange={e => setUserForm({...userForm, email: e.target.value})} />
                    </div>
                    <div className="user-form-field">
                      <label>Phone</label>
                      <input type="text" value={userForm.phone} onChange={e => setUserForm({...userForm, phone: e.target.value})} />
                    </div>
                    <div className="user-form-toggles">
                      <label className="admin-checkbox-label">
                        <input type="checkbox" checked={userForm.is_admin} onChange={e => setUserForm({...userForm, is_admin: e.target.checked})} />
                        Admin
                      </label>
                      <label className="admin-checkbox-label">
                        <input type="checkbox" checked={userForm.is_active} onChange={e => setUserForm({...userForm, is_active: e.target.checked})} />
                        Active
                      </label>
                    </div>
                  </div>
                  <div className="modal-actions">
                    <button className="modal-btn modal-btn-secondary" onClick={() => setShowUserModal(false)}>Cancel</button>
                    <button
                      className="modal-btn modal-btn-primary"
                      onClick={handleSaveUser}
                      disabled={savingUser || !userForm.first_name.trim() || !userForm.last_name.trim() || !userForm.email.trim()}
                    >
                      {savingUser ? 'Saving...' : (editingUser ? 'Update' : 'Create')}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Delete User Confirmation Modal */}
            {showDeleteUserModal && userToDelete && (
              <div className="modal-overlay" onClick={() => setShowDeleteUserModal(false)}>
                <div className="modal-content" onClick={e => e.stopPropagation()}>
                  <h3>Delete User</h3>
                  <p>Are you sure you want to delete <strong>{userToDelete.first_name} {userToDelete.last_name}</strong> ({userToDelete.email})?</p>
                  <div className="modal-actions">
                    <button className="modal-btn modal-btn-secondary" onClick={() => setShowDeleteUserModal(false)}>Cancel</button>
                    <button className="modal-btn modal-btn-danger" onClick={handleDeleteUser} disabled={deletingUser}>
                      {deletingUser ? 'Deleting...' : 'Delete'}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'flights' && (
          <div className="admin-section">
            <div className="flights-header">
              <h2>Flight Schedule</h2>
              <div className="flights-header-actions">
                <button
                  className="btn-secondary"
                  onClick={() => fetchFlights()}
                  disabled={loadingFlights}
                >
                  ↻ Refresh
                </button>
                <button
                  className="btn-primary"
                  onClick={exportFlights}
                  disabled={exportingFlights}
                >
                  {exportingFlights ? 'Exporting...' : '↓ Export JSON'}
                </button>
              </div>
            </div>

            {flightsMessage && (
              <div className={`flights-message ${flightsMessage.includes('Error') || flightsMessage.includes('Warning') ? 'warning' : 'success'}`}>
                {flightsMessage}
              </div>
            )}

            {/* Sub-tabs */}
            <div className="flights-subtabs">
              <button
                className={`flights-subtab ${flightsSubTab === 'departures' ? 'active' : ''}`}
                onClick={() => setFlightsSubTab('departures')}
              >
                Departures ({departures.length})
              </button>
              <button
                className={`flights-subtab ${flightsSubTab === 'arrivals' ? 'active' : ''}`}
                onClick={() => setFlightsSubTab('arrivals')}
              >
                Arrivals ({arrivals.length})
              </button>
            </div>

            {/* Filters */}
            <div className="flights-filters">
              <div className="flight-filter-group">
                <label>Airline:</label>
                <select
                  value={flightAirlineFilter}
                  onChange={(e) => setFlightAirlineFilter(e.target.value)}
                >
                  <option value="">All Airlines</option>
                  {flightFilters.airlines?.map(a => (
                    <option key={a.code} value={a.code}>{a.code} - {a.name}</option>
                  ))}
                </select>
              </div>

              {flightsSubTab === 'departures' ? (
                <div className="flight-filter-group">
                  <label>Destination:</label>
                  <select
                    value={flightDestFilter}
                    onChange={(e) => setFlightDestFilter(e.target.value)}
                  >
                    <option value="">All Destinations</option>
                    {flightFilters.destinations?.map(d => (
                      <option key={d.code} value={d.code}>{d.code} - {d.name}</option>
                    ))}
                  </select>
                </div>
              ) : (
                <div className="flight-filter-group">
                  <label>Origin:</label>
                  <select
                    value={flightOriginFilter}
                    onChange={(e) => setFlightOriginFilter(e.target.value)}
                  >
                    <option value="">All Origins</option>
                    {flightFilters.origins?.map(o => (
                      <option key={o.code} value={o.code}>{o.code} - {o.name}</option>
                    ))}
                  </select>
                </div>
              )}

              <div className="flight-filter-group">
                <label>Month:</label>
                <select
                  value={flightMonthFilter}
                  onChange={(e) => setFlightMonthFilter(e.target.value)}
                >
                  <option value="">All Months</option>
                  {flightFilters.months?.map(m => (
                    <option key={`${m.year}-${m.month}`} value={`${m.year}-${m.month}`}>{m.label}</option>
                  ))}
                </select>
              </div>

              <button
                className="sort-toggle-btn"
                onClick={() => setFlightsSortAsc(!flightsSortAsc)}
                title={flightsSortAsc ? 'Sorted oldest first' : 'Sorted newest first'}
              >
                Date {flightsSortAsc ? '↑' : '↓'}
              </button>
            </div>

            {/* Data Table */}
            {loadingFlights ? (
              <p className="loading-text">Loading flights...</p>
            ) : flightsSubTab === 'departures' ? (
              <div className="flights-table-wrapper">
                <table className="flights-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Flight</th>
                      <th>Airline</th>
                      <th>Time</th>
                      <th>Destination</th>
                      <th>Capacity</th>
                      <th>Early</th>
                      <th>Late</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {departures.map(d => (
                      <tr key={d.id} className={editingFlightId === d.id ? 'editing' : ''}>
                        {editingFlightId === d.id ? (
                          <>
                            <td>
                              <input
                                type="date"
                                value={editFlightForm.date || ''}
                                onChange={(e) => setEditFlightForm({...editFlightForm, date: e.target.value})}
                                className="flight-edit-input"
                              />
                            </td>
                            <td>
                              <input
                                type="text"
                                value={editFlightForm.flight_number || ''}
                                onChange={(e) => setEditFlightForm({...editFlightForm, flight_number: e.target.value})}
                                className="flight-edit-input small"
                              />
                            </td>
                            <td>
                              <input
                                type="text"
                                value={editFlightForm.airline_code || ''}
                                onChange={(e) => setEditFlightForm({...editFlightForm, airline_code: e.target.value})}
                                className="flight-edit-input small"
                              />
                            </td>
                            <td>
                              <input
                                type="time"
                                value={editFlightForm.departure_time || ''}
                                onChange={(e) => setEditFlightForm({...editFlightForm, departure_time: e.target.value})}
                                className="flight-edit-input"
                              />
                            </td>
                            <td>
                              <input
                                type="text"
                                value={editFlightForm.destination_code || ''}
                                onChange={(e) => setEditFlightForm({...editFlightForm, destination_code: e.target.value})}
                                className="flight-edit-input small"
                              />
                            </td>
                            <td>
                              <select
                                value={editFlightForm.capacity_tier ?? ''}
                                onChange={(e) => setEditFlightForm({...editFlightForm, capacity_tier: parseInt(e.target.value)})}
                                className="flight-edit-input"
                              >
                                <option value="0">0 (Call Us)</option>
                                <option value="2">2 (1+1)</option>
                                <option value="4">4 (2+2)</option>
                                <option value="6">6 (3+3)</option>
                                <option value="8">8 (4+4)</option>
                              </select>
                            </td>
                            <td>
                              <input
                                type="number"
                                min="0"
                                value={editFlightForm.slots_booked_early ?? ''}
                                onChange={(e) => setEditFlightForm({...editFlightForm, slots_booked_early: parseInt(e.target.value) || 0})}
                                className="flight-edit-input tiny"
                              />
                            </td>
                            <td>
                              <input
                                type="number"
                                min="0"
                                value={editFlightForm.slots_booked_late ?? ''}
                                onChange={(e) => setEditFlightForm({...editFlightForm, slots_booked_late: parseInt(e.target.value) || 0})}
                                className="flight-edit-input tiny"
                              />
                            </td>
                            <td className="flight-actions">
                              <button className="btn-save" onClick={saveFlightEdit} disabled={savingFlight}>
                                {savingFlight ? '...' : '✓'}
                              </button>
                              <button className="btn-cancel" onClick={cancelEditFlight}>✕</button>
                            </td>
                          </>
                        ) : (
                          <>
                            <td>{d.date}</td>
                            <td>{d.flight_number}</td>
                            <td>{d.airline_code}</td>
                            <td>{d.departure_time}</td>
                            <td>{d.destination_code}</td>
                            <td>
                              <span className={`capacity-badge tier-${d.capacity_tier}`}>
                                {d.capacity_tier === 0 ? 'Call' : d.capacity_tier}
                              </span>
                            </td>
                            <td>
                              <span className="slots-display">
                                {d.slots_booked_early}/{d.max_slots_per_time}
                              </span>
                            </td>
                            <td>
                              <span className="slots-display">
                                {d.slots_booked_late}/{d.max_slots_per_time}
                              </span>
                            </td>
                            <td className="flight-actions">
                              <button className="btn-edit" onClick={() => startEditFlight(d)}>Edit</button>
                            </td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {departures.length === 0 && <p className="no-data">No departures found</p>}
              </div>
            ) : (
              <div className="flights-table-wrapper">
                <table className="flights-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Flight</th>
                      <th>Airline</th>
                      <th>Dep Time</th>
                      <th>Arr Time</th>
                      <th>Origin</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {arrivals.map(a => (
                      <tr key={a.id} className={editingFlightId === a.id ? 'editing' : ''}>
                        {editingFlightId === a.id ? (
                          <>
                            <td>
                              <input
                                type="date"
                                value={editFlightForm.date || ''}
                                onChange={(e) => setEditFlightForm({...editFlightForm, date: e.target.value})}
                                className="flight-edit-input"
                              />
                            </td>
                            <td>
                              <input
                                type="text"
                                value={editFlightForm.flight_number || ''}
                                onChange={(e) => setEditFlightForm({...editFlightForm, flight_number: e.target.value})}
                                className="flight-edit-input small"
                              />
                            </td>
                            <td>
                              <input
                                type="text"
                                value={editFlightForm.airline_code || ''}
                                onChange={(e) => setEditFlightForm({...editFlightForm, airline_code: e.target.value})}
                                className="flight-edit-input small"
                              />
                            </td>
                            <td>
                              <input
                                type="time"
                                value={editFlightForm.departure_time || ''}
                                onChange={(e) => setEditFlightForm({...editFlightForm, departure_time: e.target.value})}
                                className="flight-edit-input"
                              />
                            </td>
                            <td>
                              <input
                                type="time"
                                value={editFlightForm.arrival_time || ''}
                                onChange={(e) => setEditFlightForm({...editFlightForm, arrival_time: e.target.value})}
                                className="flight-edit-input"
                              />
                            </td>
                            <td>
                              <input
                                type="text"
                                value={editFlightForm.origin_code || ''}
                                onChange={(e) => setEditFlightForm({...editFlightForm, origin_code: e.target.value})}
                                className="flight-edit-input small"
                              />
                            </td>
                            <td className="flight-actions">
                              <button className="btn-save" onClick={saveFlightEdit} disabled={savingFlight}>
                                {savingFlight ? '...' : '✓'}
                              </button>
                              <button className="btn-cancel" onClick={cancelEditFlight}>✕</button>
                            </td>
                          </>
                        ) : (
                          <>
                            <td>{a.date}</td>
                            <td>{a.flight_number}</td>
                            <td>{a.airline_code}</td>
                            <td>{a.departure_time || '-'}</td>
                            <td>{a.arrival_time}</td>
                            <td>{a.origin_code}</td>
                            <td className="flight-actions">
                              <button className="btn-edit" onClick={() => startEditFlight(a)}>Edit</button>
                            </td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {arrivals.length === 0 && <p className="no-data">No arrivals found</p>}
              </div>
            )}
          </div>
        )}

        {activeTab === 'marketing' && (
          <div className="admin-section">
            <h2>Marketing Subscribers</h2>

            {/* Success Message Banner */}
            {promoSuccessMessage && (
              <div className="success-banner">
                {promoSuccessMessage}
              </div>
            )}

            {/* Search and Filter Controls - matching Bookings style */}
            <div className="admin-filters">
              <div className="admin-search">
                <input
                  type="text"
                  placeholder="Search by name, email, or promo code..."
                  value={subscriberSearchTerm}
                  onChange={(e) => setSubscriberSearchTerm(e.target.value)}
                  className="admin-search-input"
                />
                {subscriberSearchTerm && (
                  <button
                    className="admin-search-clear"
                    onClick={() => setSubscriberSearchTerm('')}
                  >
                    &times;
                  </button>
                )}
              </div>
              <div className="admin-filter-group">
                <label>Status:</label>
                <select
                  value={subscriberStatusFilter}
                  onChange={(e) => setSubscriberStatusFilter(e.target.value)}
                  className="admin-filter-select"
                >
                  <option value="all">All Statuses</option>
                  <option value="pending">Pending</option>
                  <option value="sent">Code Sent</option>
                  <option value="used">Code Used</option>
                  <option value="unsubscribed">Unsubscribed</option>
                </select>
              </div>
              <label className="admin-checkbox-label">
                <input
                  type="checkbox"
                  checked={hideTestEmails}
                  onChange={(e) => setHideTestEmails(e.target.checked)}
                />
                Hide test emails
              </label>
              <div className="admin-filter-count">
                Showing {filteredSubscribers.length} of {subscribers.length} subscribers
              </div>
            </div>

            {loadingSubscribers ? (
              <div className="admin-loading-inline">
                <div className="spinner-small"></div>
                <span>Loading subscribers...</span>
              </div>
            ) : filteredSubscribers.length === 0 ? (
              <p className="admin-empty">
                {subscribers.length === 0 ? 'No subscribers found' : 'No subscribers match your search'}
              </p>
            ) : (
              <div className="booking-accordion">
                {filteredSubscribers.map((subscriber) => (
                  <div
                    key={subscriber.id}
                    className={`booking-card ${expandedSubscriberId === subscriber.id ? 'expanded' : ''} ${subscriber.unsubscribed ? 'unsubscribed' : ''}`}
                  >
                    {/* Collapsed Header Row */}
                    <div
                      className="booking-card-header subscriber-header"
                      onClick={() => setExpandedSubscriberId(expandedSubscriberId === subscriber.id ? null : subscriber.id)}
                    >
                      <div className="subscriber-info">
                        <span className="subscriber-name">{subscriber.first_name} {subscriber.last_name}</span>
                        <span className="subscriber-email">{subscriber.email}</span>
                      </div>
                    </div>

                    {/* Expanded Content */}
                    {expandedSubscriberId === subscriber.id && (
                      <div className="booking-card-body">
                        {/* Welcome Email Section */}
                        <div className="booking-section">
                          <h4>Welcome Email</h4>
                          <div className="booking-section-content">
                            <div className="booking-detail-row">
                              <div className="booking-detail">
                                <span className="detail-label">Subscribed</span>
                                <span className="detail-value">
                                  {subscriber.subscribed_at ? new Date(subscriber.subscribed_at).toLocaleDateString() : '-'}
                                </span>
                              </div>
                              <div className="booking-detail">
                                <span className="detail-label">Status</span>
                                <span className="detail-value">
                                  <span className={`status-badge ${subscriber.welcome_email_sent ? 'sent' : 'pending'}`}>
                                    {subscriber.welcome_email_sent ? 'Sent' : 'Pending'}
                                  </span>
                                </span>
                              </div>
                              <div className="booking-detail">
                                <span className="detail-label">Sent At</span>
                                <span className="detail-value">
                                  {subscriber.welcome_email_sent_at ? new Date(subscriber.welcome_email_sent_at).toLocaleString() : '-'}
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>

                        {/* 10% OFF Promo Section */}
                        <div className="booking-section">
                          <div className="section-header-with-action">
                            <h4>10% Off Promo</h4>
                            {!subscriber.unsubscribed && !subscriber.promo_10_used && !subscriber.promo_10_sent && (
                              <button
                                className="action-btn promo-btn"
                                onClick={(e) => { e.stopPropagation(); openPromoModal(subscriber, 10); }}
                              >
                                Send 10% Off
                              </button>
                            )}
                          </div>
                          <div className="booking-section-content">
                            {subscriber.promo_10_code ? (
                              <div className="booking-detail-row">
                                <div className="booking-detail">
                                  <span className="detail-label">Code</span>
                                  <span className="detail-value">
                                    <span className="promo-code-display">{subscriber.promo_10_code}</span>
                                  </span>
                                </div>
                                <div className="booking-detail">
                                  <span className="detail-label">Status</span>
                                  <span className="detail-value">
                                    <span className={`status-badge ${subscriber.promo_10_used ? 'used' : 'sent'}`}>
                                      {subscriber.promo_10_used ? 'Used' : 'Sent'}
                                    </span>
                                  </span>
                                </div>
                                <div className="booking-detail">
                                  <span className="detail-label">Sent At</span>
                                  <span className="detail-value">
                                    {subscriber.promo_10_sent_at ? new Date(subscriber.promo_10_sent_at).toLocaleString() : '-'}
                                  </span>
                                </div>
                              </div>
                            ) : (
                              <p className="section-empty">Not sent yet</p>
                            )}
                          </div>
                        </div>

                        {/* FREE Parking Promo Section */}
                        <div className="booking-section">
                          <div className="section-header-with-action">
                            <h4>FREE Parking Promo</h4>
                            {!subscriber.unsubscribed && !subscriber.promo_free_used && !subscriber.promo_free_sent && (
                              <button
                                className="action-btn promo-btn free"
                                onClick={(e) => { e.stopPropagation(); openPromoModal(subscriber, 100); }}
                              >
                                Send FREE
                              </button>
                            )}
                          </div>
                          <div className="booking-section-content">
                            {subscriber.promo_free_code ? (
                              <div className="booking-detail-row">
                                <div className="booking-detail">
                                  <span className="detail-label">Code</span>
                                  <span className="detail-value">
                                    <span className="promo-code-display">{subscriber.promo_free_code}</span>
                                  </span>
                                </div>
                                <div className="booking-detail">
                                  <span className="detail-label">Status</span>
                                  <span className="detail-value">
                                    <span className={`status-badge ${subscriber.promo_free_used ? 'used' : 'sent'}`}>
                                      {subscriber.promo_free_used ? 'Used' : 'Sent'}
                                    </span>
                                  </span>
                                </div>
                                <div className="booking-detail">
                                  <span className="detail-label">Sent At</span>
                                  <span className="detail-value">
                                    {subscriber.promo_free_sent_at ? new Date(subscriber.promo_free_sent_at).toLocaleString() : '-'}
                                  </span>
                                </div>
                              </div>
                            ) : (
                              <p className="section-empty">Not sent yet</p>
                            )}
                          </div>
                        </div>

                        {subscriber.unsubscribed && (
                          <div className="subscriber-unsubscribed-notice">
                            Unsubscribed on {subscriber.unsubscribed_at ? new Date(subscriber.unsubscribed_at).toLocaleDateString() : 'unknown date'}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'leads' && (
          <div className="admin-section">
            <div className="admin-section-header">
              <h2>Abandoned Leads</h2>
              <button onClick={fetchLeads} className="admin-refresh" disabled={loadingLeads}>
                {loadingLeads ? 'Loading...' : 'Refresh'}
              </button>
            </div>
            <p className="admin-subtitle">Customers who started booking but didn't complete payment</p>

            <div className="admin-filters">
              <div className="admin-search">
                <input
                  type="text"
                  placeholder="Search by name, email, or phone..."
                  value={leadSearchTerm}
                  onChange={(e) => setLeadSearchTerm(e.target.value)}
                  className="admin-search-input"
                />
                {leadSearchTerm && (
                  <button
                    className="admin-search-clear"
                    onClick={() => setLeadSearchTerm('')}
                  >
                    &times;
                  </button>
                )}
              </div>
              <div className="admin-filter-count">
                Showing {leads.filter(lead => {
                  if (!leadSearchTerm) return true
                  const search = leadSearchTerm.toLowerCase()
                  return (
                    lead.first_name?.toLowerCase().includes(search) ||
                    lead.last_name?.toLowerCase().includes(search) ||
                    lead.email?.toLowerCase().includes(search) ||
                    lead.phone?.includes(search)
                  )
                }).length} of {leads.length} leads
              </div>
            </div>

            {loadingLeads ? (
              <div className="admin-loading-inline">
                <div className="loading-spinner-small"></div>
                <span>Loading leads...</span>
              </div>
            ) : (
              <div className="booking-accordion">
                {leads
                  .filter(lead => {
                    if (!leadSearchTerm) return true
                    const search = leadSearchTerm.toLowerCase()
                    return (
                      lead.first_name?.toLowerCase().includes(search) ||
                      lead.last_name?.toLowerCase().includes(search) ||
                      lead.email?.toLowerCase().includes(search) ||
                      lead.phone?.includes(search)
                    )
                  })
                  .map(lead => (
                  <div
                    key={lead.id}
                    className={`booking-card ${expandedLeadId === lead.id ? 'expanded' : ''}`}
                  >
                    <div
                      className="booking-card-header booking-header-stacked"
                      onClick={() => setExpandedLeadId(expandedLeadId === lead.id ? null : lead.id)}
                    >
                      <div className="booking-header-info">
                        <div className="booking-header-top">
                          <span className="booking-customer-name">
                            {lead.first_name} {lead.last_name}
                          </span>
                          {lead.booking_attempts > 0 && (
                            <span className="booking-source-badge manual">
                              {lead.booking_attempts} attempt{lead.booking_attempts > 1 ? 's' : ''}
                            </span>
                          )}
                        </div>
                        <span className="booking-date">
                          {lead.created_at ? new Date(lead.created_at).toLocaleDateString() : 'Unknown'}
                        </span>
                      </div>
                    </div>

                    {expandedLeadId === lead.id && (
                      <div className="booking-card-body">
                        <div className="booking-section">
                          <h4>Contact Details</h4>
                          <div className="booking-section-content">
                            <div className="booking-detail-row">
                              <div className="booking-detail">
                                <span className="detail-label">Email</span>
                                <span className="detail-value">
                                  <a href={`mailto:${lead.email}`}>{lead.email}</a>
                                </span>
                              </div>
                              <div className="booking-detail">
                                <span className="detail-label">Phone</span>
                                <span className="detail-value">
                                  <a href={`tel:${lead.phone}`}>{lead.phone}</a>
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>

                        {(lead.billing_address1 || lead.billing_city || lead.billing_postcode) && (
                          <div className="booking-section">
                            <h4>Billing Address</h4>
                            <div className="booking-section-content">
                              <div className="booking-detail">
                                <span className="detail-value">
                                  {[lead.billing_address1, lead.billing_city, lead.billing_postcode].filter(Boolean).join(', ')}
                                </span>
                              </div>
                            </div>
                          </div>
                        )}

                        <div className="booking-section">
                          <h4>Status</h4>
                          <div className="booking-section-content">
                            <div className="booking-detail-row">
                              <div className="booking-detail">
                                <span className="detail-label">Started</span>
                                <span className="detail-value">
                                  {lead.created_at ? new Date(lead.created_at).toLocaleString() : 'Unknown'}
                                </span>
                              </div>
                              {lead.last_booking_status && (
                                <div className="booking-detail">
                                  <span className="detail-label">Last Booking Status</span>
                                  <span className="detail-value">{lead.last_booking_status}</span>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
                {leads.length === 0 && !loadingLeads && (
                  <p className="admin-no-data">No abandoned leads found</p>
                )}
              </div>
            )}
          </div>
        )}

        {activeTab === 'pricing' && (
          <div className="admin-section">
            <div className="admin-section-header">
              <h2>Pricing Settings</h2>
              <button onClick={fetchPricing} className="admin-refresh" disabled={loadingPricing}>
                {loadingPricing ? 'Loading...' : 'Refresh'}
              </button>
            </div>

            {pricingMessage && <div className="admin-success">{pricingMessage}</div>}

            {loadingPricing ? (
              <div className="admin-loading-inline">
                <div className="spinner-small"></div>
                <span>Loading pricing settings...</span>
              </div>
            ) : (
              <div className="pricing-settings-form">
                <div className="admin-pricing-section">
                  <h3>Base Prices (Early Booking Tier)</h3>
                  <p className="pricing-hint">These are the prices when customers book 14+ days in advance. Standard tier adds the increment once, Late tier adds it twice.</p>

                  <div className="pricing-inputs pricing-inputs-grid">
                    <div className="pricing-input-group">
                      <label>1-4 Days</label>
                      <div className="price-input-wrapper">
                        <span className="currency-symbol">£</span>
                        <input
                          type="text"
                          inputMode="decimal"
                          value={pricing.days_1_4_price}
                          onChange={(e) => {
                            const val = e.target.value.replace(/[^0-9.]/g, '')
                            setPricing({ ...pricing, days_1_4_price: parseFloat(val) || 0 })
                          }}
                        />
                      </div>
                    </div>

                    <div className="pricing-input-group">
                      <label>5-6 Days</label>
                      <div className="price-input-wrapper">
                        <span className="currency-symbol">£</span>
                        <input
                          type="text"
                          inputMode="decimal"
                          value={pricing.days_5_6_price}
                          onChange={(e) => {
                            const val = e.target.value.replace(/[^0-9.]/g, '')
                            setPricing({ ...pricing, days_5_6_price: parseFloat(val) || 0 })
                          }}
                        />
                      </div>
                    </div>

                    <div className="pricing-input-group">
                      <label>1 Week Trip</label>
                      <div className="price-input-wrapper">
                        <span className="currency-symbol">£</span>
                        <input
                          type="text"
                          inputMode="decimal"
                          value={pricing.week1_base_price}
                          onChange={(e) => {
                            const val = e.target.value.replace(/[^0-9.]/g, '')
                            setPricing({ ...pricing, week1_base_price: parseFloat(val) || 0 })
                          }}
                        />
                      </div>
                    </div>

                    <div className="pricing-input-group">
                      <label>8-9 Days</label>
                      <div className="price-input-wrapper">
                        <span className="currency-symbol">£</span>
                        <input
                          type="text"
                          inputMode="decimal"
                          value={pricing.days_8_9_price}
                          onChange={(e) => {
                            const val = e.target.value.replace(/[^0-9.]/g, '')
                            setPricing({ ...pricing, days_8_9_price: parseFloat(val) || 0 })
                          }}
                        />
                      </div>
                    </div>

                    <div className="pricing-input-group">
                      <label>10-11 Days</label>
                      <div className="price-input-wrapper">
                        <span className="currency-symbol">£</span>
                        <input
                          type="text"
                          inputMode="decimal"
                          value={pricing.days_10_11_price}
                          onChange={(e) => {
                            const val = e.target.value.replace(/[^0-9.]/g, '')
                            setPricing({ ...pricing, days_10_11_price: parseFloat(val) || 0 })
                          }}
                        />
                      </div>
                    </div>

                    <div className="pricing-input-group">
                      <label>12-13 Days</label>
                      <div className="price-input-wrapper">
                        <span className="currency-symbol">£</span>
                        <input
                          type="text"
                          inputMode="decimal"
                          value={pricing.days_12_13_price}
                          onChange={(e) => {
                            const val = e.target.value.replace(/[^0-9.]/g, '')
                            setPricing({ ...pricing, days_12_13_price: parseFloat(val) || 0 })
                          }}
                        />
                      </div>
                    </div>

                    <div className="pricing-input-group">
                      <label>2 Week Trip</label>
                      <div className="price-input-wrapper">
                        <span className="currency-symbol">£</span>
                        <input
                          type="text"
                          inputMode="decimal"
                          value={pricing.week2_base_price}
                          onChange={(e) => {
                            const val = e.target.value.replace(/[^0-9.]/g, '')
                            setPricing({ ...pricing, week2_base_price: parseFloat(val) || 0 })
                          }}
                        />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="admin-pricing-section tier-increment-section">
                  <h3>Tier Increment</h3>
                  <p className="pricing-hint">This amount is added for Standard tier (+1x) and Late tier (+2x) bookings.</p>
                  <div className="pricing-inputs">
                    <div className="pricing-input-group pricing-input-highlight">
                      <label>Increment Amount</label>
                      <div className="price-input-wrapper">
                        <span className="currency-symbol">£</span>
                        <input
                          type="text"
                          inputMode="decimal"
                          value={pricing.tier_increment}
                          onChange={(e) => {
                            const val = e.target.value.replace(/[^0-9.]/g, '')
                            setPricing({ ...pricing, tier_increment: parseFloat(val) || 0 })
                          }}
                        />
                      </div>
                      <span className="pricing-input-hint">per tier level</span>
                    </div>
                  </div>
                </div>

                <div className="pricing-preview">
                  <h3>Price Preview</h3>
                  <table className="pricing-preview-table">
                    <thead>
                      <tr>
                        <th>Duration</th>
                        <th>Early (14+ days)</th>
                        <th>Standard (7-13 days)</th>
                        <th>Late (&lt;7 days)</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>1-4 Days</td>
                        <td>£{pricing.days_1_4_price}</td>
                        <td>£{pricing.days_1_4_price + pricing.tier_increment}</td>
                        <td>£{pricing.days_1_4_price + (pricing.tier_increment * 2)}</td>
                      </tr>
                      <tr>
                        <td>5-6 Days</td>
                        <td>£{pricing.days_5_6_price}</td>
                        <td>£{pricing.days_5_6_price + pricing.tier_increment}</td>
                        <td>£{pricing.days_5_6_price + (pricing.tier_increment * 2)}</td>
                      </tr>
                      <tr>
                        <td>1 Week Trip</td>
                        <td>£{pricing.week1_base_price}</td>
                        <td>£{pricing.week1_base_price + pricing.tier_increment}</td>
                        <td>£{pricing.week1_base_price + (pricing.tier_increment * 2)}</td>
                      </tr>
                      <tr>
                        <td>8-9 Days</td>
                        <td>£{pricing.days_8_9_price}</td>
                        <td>£{pricing.days_8_9_price + pricing.tier_increment}</td>
                        <td>£{pricing.days_8_9_price + (pricing.tier_increment * 2)}</td>
                      </tr>
                      <tr>
                        <td>10-11 Days</td>
                        <td>£{pricing.days_10_11_price}</td>
                        <td>£{pricing.days_10_11_price + pricing.tier_increment}</td>
                        <td>£{pricing.days_10_11_price + (pricing.tier_increment * 2)}</td>
                      </tr>
                      <tr>
                        <td>12-13 Days</td>
                        <td>£{pricing.days_12_13_price}</td>
                        <td>£{pricing.days_12_13_price + pricing.tier_increment}</td>
                        <td>£{pricing.days_12_13_price + (pricing.tier_increment * 2)}</td>
                      </tr>
                      <tr>
                        <td>2 Week Trip</td>
                        <td>£{pricing.week2_base_price}</td>
                        <td>£{pricing.week2_base_price + pricing.tier_increment}</td>
                        <td>£{pricing.week2_base_price + (pricing.tier_increment * 2)}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <div className="pricing-actions">
                  <button
                    className="pricing-save-btn"
                    onClick={savePricing}
                    disabled={savingPricing}
                  >
                    {savingPricing ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'reports' && (
          <div className="admin-section">
            <h2>Reports</h2>
            <p className="admin-coming-soon">Reports coming soon...</p>
          </div>
        )}
      </main>

      {/* Cancel Confirmation Modal */}
      {showCancelModal && bookingToCancel && (
        <div className="modal-overlay" onClick={() => setShowCancelModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Cancel Booking</h3>
            <p>Are you sure you want to cancel this booking?</p>
            <div className="modal-booking-info">
              <p><strong>Reference:</strong> {bookingToCancel.reference}</p>
              <p><strong>Customer:</strong> {bookingToCancel.customer?.first_name} {bookingToCancel.customer?.last_name}</p>
              <p><strong>Drop-off:</strong> {formatDate(bookingToCancel.dropoff_date)}</p>
            </div>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowCancelModal(false)}
              >
                Keep Booking
              </button>
              <button
                className="modal-btn modal-btn-danger"
                onClick={handleConfirmCancel}
                disabled={cancellingId}
              >
                {cancellingId ? 'Cancelling...' : 'Yes, Cancel Booking'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Resend Email Confirmation Modal */}
      {showResendModal && bookingToResend && (
        <div className="modal-overlay" onClick={() => setShowResendModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Resend Confirmation Email</h3>
            <p>Are you sure you want to resend the booking confirmation email?</p>
            <div className="modal-booking-info">
              <p><strong>Reference:</strong> {bookingToResend.reference}</p>
              <p><strong>Customer:</strong> {bookingToResend.customer?.first_name} {bookingToResend.customer?.last_name}</p>
              <p><strong>Email:</strong> {bookingToResend.customer?.email}</p>
            </div>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowResendModal(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={handleConfirmResendEmail}
                disabled={resendingEmailId}
              >
                {resendingEmailId ? 'Sending...' : 'Yes, Send Email'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Send Cancellation Email Modal */}
      {showCancellationEmailModal && bookingForCancellationEmail && (
        <div className="modal-overlay" onClick={() => setShowCancellationEmailModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Send Cancellation Email</h3>
            <p>Are you sure you want to send the cancellation email to the customer?</p>
            <div className="modal-booking-info">
              <p><strong>Reference:</strong> {bookingForCancellationEmail.reference}</p>
              <p><strong>Customer:</strong> {bookingForCancellationEmail.customer?.first_name} {bookingForCancellationEmail.customer?.last_name}</p>
              <p><strong>Email:</strong> {bookingForCancellationEmail.customer?.email}</p>
            </div>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowCancellationEmailModal(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={handleConfirmSendCancellationEmail}
                disabled={sendingCancellationEmailId}
              >
                {sendingCancellationEmailId ? 'Sending...' : 'Yes, Send Email'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Send Refund Email Modal */}
      {showRefundEmailModal && bookingForRefundEmail && (
        <div className="modal-overlay" onClick={() => setShowRefundEmailModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Send Refund Email</h3>
            <p>Are you sure you want to send the refund confirmation email to the customer?</p>
            <div className="modal-booking-info">
              <p><strong>Reference:</strong> {bookingForRefundEmail.reference}</p>
              <p><strong>Customer:</strong> {bookingForRefundEmail.customer?.first_name} {bookingForRefundEmail.customer?.last_name}</p>
              <p><strong>Email:</strong> {bookingForRefundEmail.customer?.email}</p>
              {bookingForRefundEmail.payment?.refund_amount_pence && (
                <p><strong>Refund Amount:</strong> £{(bookingForRefundEmail.payment.refund_amount_pence / 100).toFixed(2)}</p>
              )}
            </div>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowRefundEmailModal(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={handleConfirmSendRefundEmail}
                disabled={sendingRefundEmailId}
              >
                {sendingRefundEmailId ? 'Sending...' : 'Yes, Send Email'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Send Promo Code Confirmation Modal */}
      {showPromoModal && promoToSend && (
        <div className="modal-overlay" onClick={() => { setShowPromoModal(false); setPromoToSend(null); }}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Send {promoToSend.discountPercent === 100 ? 'FREE Parking' : '10% Off'} Promo</h3>
            <p>Are you sure you want to send this promo code?</p>
            <div className="modal-booking-info">
              <p><strong>Subscriber:</strong> {promoToSend.subscriber.first_name} {promoToSend.subscriber.last_name}</p>
              <p><strong>Email:</strong> {promoToSend.subscriber.email}</p>
              <p><strong>Discount:</strong> {promoToSend.discountPercent === 100 ? 'FREE Parking (100% off)' : '10% Off'}</p>
            </div>
            <p className="modal-warning">
              This will generate a unique promo code and send an email to the subscriber.
            </p>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => { setShowPromoModal(false); setPromoToSend(null); }}
              >
                Cancel
              </button>
              <button
                className={`modal-btn ${promoToSend.discountPercent === 100 ? 'modal-btn-success' : 'modal-btn-primary'}`}
                onClick={confirmSendPromo}
                disabled={sendingPromoId}
              >
                {sendingPromoId ? 'Sending...' : `Yes, Send ${promoToSend.discountPercent === 100 ? 'FREE' : '10% Off'} Code`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Admin
