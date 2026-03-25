import { useState, useEffect, useMemo } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from './AuthContext'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import ManualBooking from './components/ManualBooking'
import BookingCalendar from './components/BookingCalendar'
import BookingLocationMap from './components/BookingLocationMap'
import RosterCalendar from './components/RosterCalendar'
import './Admin.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Photo slots - must match Employee.jsx
const PHOTO_SLOTS = [
  { key: 'front', label: 'Front' },
  { key: 'rear', label: 'Rear' },
  { key: 'driver_side', label: 'Driver Side' },
  { key: 'passenger_side', label: 'Passenger Side' },
  { key: 'additional_1', label: 'Additional 1' },
  { key: 'additional_2', label: 'Additional 2' },
]

// UK date format helpers (DD/MM/YYYY)
const isoToUkDate = (isoDate) => {
  if (!isoDate) return ''
  const [year, month, day] = isoDate.split('-')
  return `${day}/${month}/${year}`
}

const ukToIsoDate = (ukDate) => {
  if (!ukDate) return ''
  const parts = ukDate.split('/')
  if (parts.length !== 3) return ''
  const [day, month, year] = parts
  return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`
}

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
  const [deletingId, setDeletingId] = useState(null)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [bookingToDelete, setBookingToDelete] = useState(null)
  const [showEditModal, setShowEditModal] = useState(false)
  const [bookingToEdit, setBookingToEdit] = useState(null)
  const [savingEdit, setSavingEdit] = useState(false)
  const [collapsedStatusSections, setCollapsedStatusSections] = useState({
    confirmed: false,
    completed: true,
    pending: false,
    cancelled: true
  })
  const [expandedBookingMonths, setExpandedBookingMonths] = useState({})
  const [editForm, setEditForm] = useState({
    // Dropoff/Departure details
    dropoff_time: '',
    flight_departure_time: '',
    dropoff_airline_name: '',
    dropoff_flight_number: '',
    dropoff_destination: '',
    // Pickup/Return details
    pickup_date: '',
    flight_arrival_time: '',
    pickup_airline_name: '',
    pickup_flight_number: '',
    pickup_origin: '',
  })
  const [resendingEmailId, setResendingEmailId] = useState(null)
  const [showResendModal, setShowResendModal] = useState(false)
  const [bookingToResend, setBookingToResend] = useState(null)
  const [sendingCancellationEmailId, setSendingCancellationEmailId] = useState(null)
  const [showCancellationEmailModal, setShowCancellationEmailModal] = useState(false)
  const [bookingForCancellationEmail, setBookingForCancellationEmail] = useState(null)
  const [sendingRefundEmailId, setSendingRefundEmailId] = useState(null)
  const [showRefundEmailModal, setShowRefundEmailModal] = useState(false)
  const [bookingForRefundEmail, setBookingForRefundEmail] = useState(null)
  const [sendingFounderEmailId, setSendingFounderEmailId] = useState(null)
  const [showFounderEmailModal, setShowFounderEmailModal] = useState(false)
  const [bookingForFounderEmail, setBookingForFounderEmail] = useState(null)
  const [successMessage, setSuccessMessage] = useState('')

  // Return Vehicle Inspection modal state
  const [showReturnInspectionModal, setShowReturnInspectionModal] = useState(false)
  const [bookingForInspection, setBookingForInspection] = useState(null)
  const [returnInspectionData, setReturnInspectionData] = useState(null)
  const [loadingReturnInspection, setLoadingReturnInspection] = useState(false)

  // Drop-off Vehicle Inspection modal state
  const [showDropoffInspectionModal, setShowDropoffInspectionModal] = useState(false)
  const [bookingForDropoffInspection, setBookingForDropoffInspection] = useState(null)
  const [dropoffInspectionData, setDropoffInspectionData] = useState(null)
  const [loadingDropoffInspection, setLoadingDropoffInspection] = useState(false)


  // Marketing subscribers state
  const [subscribers, setSubscribers] = useState([])
  const [loadingSubscribers, setLoadingSubscribers] = useState(false)
  const [sendingPromoId, setSendingPromoId] = useState(null)
  const [subscriberSearchTerm, setSubscriberSearchTerm] = useState('')
  const [subscriberStatusFilter, setSubscriberStatusFilter] = useState('all')
  const [hideTestEmails, setHideTestEmails] = useState(true)
  const [expandedSubscriberId, setExpandedSubscriberId] = useState(null)
  const [expandedSubscriberMonths, setExpandedSubscriberMonths] = useState({})
  const [showPromoModal, setShowPromoModal] = useState(false)
  const [promoToSend, setPromoToSend] = useState(null) // { subscriber, discountPercent }
  const [showSubscriberFounderModal, setShowSubscriberFounderModal] = useState(false)
  const [founderEmailToSend, setFounderEmailToSend] = useState(null) // { subscriber }
  const [promoSuccessMessage, setPromoSuccessMessage] = useState('')
  const [subscriberDateFrom, setSubscriberDateFrom] = useState(null)
  const [subscriberDateTo, setSubscriberDateTo] = useState(null)

  // Marketing sub-tab state
  const [marketingSubTab, setMarketingSubTab] = useState('subscribers') // 'subscribers', 'promotions', or 'sources'

  // Promotions state
  const [promotions, setPromotions] = useState([])
  const [loadingPromotions, setLoadingPromotions] = useState(false)
  const [showCreatePromotion, setShowCreatePromotion] = useState(false)
  const [newPromotion, setNewPromotion] = useState({ name: '', description: '', discount_percent: 10, total_codes: 10, code_prefix: '' })
  const [creatingPromotion, setCreatingPromotion] = useState(false)
  const [expandedPromotionId, setExpandedPromotionId] = useState(null)
  const [promotionDetails, setPromotionDetails] = useState({}) // { [id]: { codes, loading } }
  const [showSendPromoEmailModal, setShowSendPromoEmailModal] = useState(false)
  const [sendPromoEmailData, setSendPromoEmailData] = useState(null) // { promotion, availableCodes }
  const [promoEmailRecipients, setPromoEmailRecipients] = useState([])
  const [promoEmailSubject, setPromoEmailSubject] = useState('')
  const [promoEmailBody, setPromoEmailBody] = useState('')
  const [sendingPromoEmails, setSendingPromoEmails] = useState(false)
  const [recipientSearchTerm, setRecipientSearchTerm] = useState('')
  const [recipientSearchResults, setRecipientSearchResults] = useState([])
  const [searchingRecipients, setSearchingRecipients] = useState(false)
  const [manualRecipient, setManualRecipient] = useState({ email: '', first_name: '', last_name: '' })
  const [promotionMessage, setPromotionMessage] = useState('')
  const [editingPromotion, setEditingPromotion] = useState(null) // { id, name }
  const [deletingPromotionId, setDeletingPromotionId] = useState(null)
  const [showGenerateCodesModal, setShowGenerateCodesModal] = useState(false)
  const [generateCodesPromotion, setGenerateCodesPromotion] = useState(null)
  const [generateCodesCount, setGenerateCodesCount] = useState(10)
  const [generatingCodes, setGeneratingCodes] = useState(false)

  // Abandoned leads state
  const [leads, setLeads] = useState([])
  const [loadingLeads, setLoadingLeads] = useState(false)
  const [leadSearchTerm, setLeadSearchTerm] = useState('')
  const [expandedLeadId, setExpandedLeadId] = useState(null)
  const [leadDateFrom, setLeadDateFrom] = useState(null)
  const [leadDateTo, setLeadDateTo] = useState(null)
  const [expandedLeadMonths, setExpandedLeadMonths] = useState({})

  // Customers state
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

  // Pricing settings state - anchor pricing with daily increment
  const [pricing, setPricing] = useState({
    days_1_4_price: 65,       // 1-4 days anchor
    week1_base_price: 85,     // 7 days anchor
    week2_base_price: 150,    // 14 days anchor
    daily_increment: 8,       // Daily increment between anchors
    tier_increment: 5,        // Early -> Standard -> Late increment
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
  const [flightNumberFilter, setFlightNumberFilter] = useState('')
  const [editingFlightId, setEditingFlightId] = useState(null)
  const [editFlightForm, setEditFlightForm] = useState({})
  const [savingFlight, setSavingFlight] = useState(false)
  const [flightsMessage, setFlightsMessage] = useState('')
  const [exportingFlights, setExportingFlights] = useState(false)
  const [collapsedFlightMonths, setCollapsedFlightMonths] = useState({})
  const [showAddFlightModal, setShowAddFlightModal] = useState(false)
  const [addFlightForm, setAddFlightForm] = useState({
    date: '',
    flight_number: '',
    airline_code: '',
    airline_name: '',
    time: '', // departure_time for departures, arrival_time for arrivals
    destination_code: '',
    destination_name: '',
    origin_code: '',
    origin_name: '',
    capacity_tier: 0,
    departure_time: '', // For arrivals: when flight left origin
  })
  const [addingFlight, setAddingFlight] = useState(false)
  const [deletingFlightId, setDeletingFlightId] = useState(null)
  const [showDeleteFlightModal, setShowDeleteFlightModal] = useState(false)
  const [flightToDelete, setFlightToDelete] = useState(null)

  // Reports / Booking Locations state
  const [mapType, setMapType] = useState('bookings') // 'bookings' or 'origins'
  const [bookingLocations, setBookingLocations] = useState([])
  const [originLocations, setOriginLocations] = useState([])
  const [skippedBookings, setSkippedBookings] = useState([])
  const [totalBookings, setTotalBookings] = useState(0)
  const [totalCustomers, setTotalCustomers] = useState(0)
  const [loadingLocations, setLoadingLocations] = useState(false)

  // Booking stats state (for growth charts)
  const [reportsSubTab, setReportsSubTab] = useState('growth') // 'growth', 'map', or 'occupancy'
  const [bookingStats, setBookingStats] = useState(null)
  const [loadingStats, setLoadingStats] = useState(false)
  const [statsChartType, setStatsChartType] = useState('monthly') // 'daily', 'weekly', 'monthly', 'cumulative'
  const [weeklyPageIndex, setWeeklyPageIndex] = useState(0) // For weekly navigation (0 = most recent)
  const [expandedDailyMonths, setExpandedDailyMonths] = useState({}) // For daily collapsible months

  // Occupancy report state
  const [occupancyData, setOccupancyData] = useState(null)
  const [loadingOccupancy, setLoadingOccupancy] = useState(false)
  const [occupancyView, setOccupancyView] = useState('daily') // 'daily', 'weekly', 'monthly'
  const [occupancyChartOffset, setOccupancyChartOffset] = useState(0) // 0 = centered on today, negative = past, positive = future

  // Popular airlines/destinations report state
  const [popularData, setPopularData] = useState(null)
  const [loadingPopular, setLoadingPopular] = useState(false)
  const [popularTop, setPopularTop] = useState(10) // 5, 10, 20

  // Fun facts state
  const [funFacts, setFunFacts] = useState(null)
  const [loadingFunFacts, setLoadingFunFacts] = useState(false)

  // Marketing Sources report state
  const [marketingSourcesData, setMarketingSourcesData] = useState(null)
  const [loadingMarketingSources, setLoadingMarketingSources] = useState(false)
  const [marketingOtherDetails, setMarketingOtherDetails] = useState(null)
  const [loadingMarketingOther, setLoadingMarketingOther] = useState(false)
  const [showMarketingOtherModal, setShowMarketingOtherModal] = useState(false)
  const [marketingOtherMonth, setMarketingOtherMonth] = useState(null) // Selected month for "Other" details
  const [marketingExportFromDate, setMarketingExportFromDate] = useState(null)
  const [marketingExportToDate, setMarketingExportToDate] = useState(null)

  // QA Dashboard state
  const [testResults, setTestResults] = useState([])
  const [latestTestRun, setLatestTestRun] = useState(null)
  const [loadingTestResults, setLoadingTestResults] = useState(false)

  // Testimonials state
  const [testimonials, setTestimonials] = useState([])
  const [loadingTestimonials, setLoadingTestimonials] = useState(false)
  const [testimonialFilter, setTestimonialFilter] = useState({ star_rating: '', status: '' })
  const [testimonialSort, setTestimonialSort] = useState({ field: 'date_added', order: 'desc' })
  const [showTestimonialModal, setShowTestimonialModal] = useState(false)
  const [editingTestimonial, setEditingTestimonial] = useState(null)
  const [testimonialForm, setTestimonialForm] = useState({
    customer_name: '',
    review_text: '',
    star_rating: null,
    date_of_travel: '',
    status: 'inactive',
    is_featured: false,
    source: ''
  })
  const [savingTestimonial, setSavingTestimonial] = useState(false)
  const [showDeleteTestimonialModal, setShowDeleteTestimonialModal] = useState(false)
  const [testimonialToDelete, setTestimonialToDelete] = useState(null)
  const [deletingTestimonial, setDeletingTestimonial] = useState(false)
  const [testimonialSuccessMessage, setTestimonialSuccessMessage] = useState('')

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


  // Fetch subscribers when marketing tab is active with subscribers sub-tab
  useEffect(() => {
    if (activeTab === 'marketing' && token && marketingSubTab === 'subscribers') {
      fetchSubscribers()
    }
  }, [activeTab, token, marketingSubTab])

  // Fetch promotions when marketing tab is active with promotions sub-tab
  useEffect(() => {
    if (activeTab === 'marketing' && token && marketingSubTab === 'promotions') {
      fetchPromotions()
    }
  }, [activeTab, token, marketingSubTab])

  // Fetch marketing sources when marketing tab is active with sources sub-tab
  useEffect(() => {
    if (activeTab === 'marketing' && token && marketingSubTab === 'sources') {
      fetchMarketingSources()
    }
  }, [activeTab, token, marketingSubTab])

  // Fetch leads when leads tab is active
  useEffect(() => {
    if (activeTab === 'leads' && token) {
      fetchLeads()
    }
  }, [activeTab, token])

  // Fetch customers when customers tab is active
  useEffect(() => {
    if (activeTab === 'customers' && token) {
      fetchCustomers()
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
  }, [flightsSubTab, flightsSortAsc, flightDestFilter, flightOriginFilter, flightAirlineFilter, flightMonthFilter, flightNumberFilter])

  // Fetch booking locations when reports tab is active or map type changes
  useEffect(() => {
    if (activeTab === 'reports' && token) {
      if (reportsSubTab === 'map') {
        fetchBookingLocations(mapType)
      } else if (reportsSubTab === 'growth') {
        fetchBookingStats()
        fetchFunFacts()
      } else if (reportsSubTab === 'occupancy') {
        fetchOccupancyReport(occupancyView)
      } else if (reportsSubTab === 'popular') {
        fetchPopularReport()
      }
    }
  }, [activeTab, token, mapType, reportsSubTab, occupancyView, popularTop])

  // Fetch test results when QA tab is active
  useEffect(() => {
    if (activeTab === 'qa' && token) {
      fetchTestResults()
    }
  }, [activeTab, token])

  // Fetch testimonials when testimonials tab is active
  useEffect(() => {
    if (activeTab === 'testimonials' && token) {
      fetchTestimonials()
    }
  }, [activeTab, token, testimonialFilter, testimonialSort])

  const fetchTestimonials = async () => {
    setLoadingTestimonials(true)
    try {
      const params = new URLSearchParams()
      if (testimonialFilter.star_rating) params.append('star_rating', testimonialFilter.star_rating)
      if (testimonialFilter.status) params.append('status', testimonialFilter.status)
      params.append('sort', testimonialSort.field)
      params.append('order', testimonialSort.order)

      const response = await fetch(`${API_URL}/api/admin/testimonials?${params}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setTestimonials(data.testimonials || [])
      }
    } catch (err) {
      console.error('Failed to fetch testimonials:', err)
    } finally {
      setLoadingTestimonials(false)
    }
  }

  const handleSaveTestimonial = async () => {
    setSavingTestimonial(true)
    setTestimonialSuccessMessage('')
    try {
      const url = editingTestimonial
        ? `${API_URL}/api/admin/testimonials/${editingTestimonial.id}`
        : `${API_URL}/api/admin/testimonials`
      const method = editingTestimonial ? 'PUT' : 'POST'

      const response = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(testimonialForm),
      })

      if (response.ok) {
        setShowTestimonialModal(false)
        setEditingTestimonial(null)
        setTestimonialForm({
          customer_name: '',
          review_text: '',
          star_rating: null,
          date_of_travel: '',
          status: 'inactive',
          is_featured: false,
          source: ''
        })
        setTestimonialSuccessMessage(editingTestimonial ? 'Testimonial updated!' : 'Testimonial added!')
        fetchTestimonials()
        setTimeout(() => setTestimonialSuccessMessage(''), 3000)
      } else {
        const err = await response.json()
        alert(err.detail ? JSON.stringify(err.detail) : 'Failed to save testimonial')
      }
    } catch (err) {
      console.error('Error saving testimonial:', err)
      alert('Failed to save testimonial')
    } finally {
      setSavingTestimonial(false)
    }
  }

  const handleDeleteTestimonial = async () => {
    if (!testimonialToDelete) return
    setDeletingTestimonial(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/testimonials/${testimonialToDelete.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        setShowDeleteTestimonialModal(false)
        setTestimonialToDelete(null)
        setTestimonialSuccessMessage('Testimonial deleted!')
        fetchTestimonials()
        setTimeout(() => setTestimonialSuccessMessage(''), 3000)
      }
    } catch (err) {
      console.error('Error deleting testimonial:', err)
    } finally {
      setDeletingTestimonial(false)
    }
  }

  const handleToggleTestimonialStatus = async (testimonial) => {
    try {
      const response = await fetch(`${API_URL}/api/admin/testimonials/${testimonial.id}/status`, {
        method: 'PATCH',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        fetchTestimonials()
      }
    } catch (err) {
      console.error('Error toggling status:', err)
    }
  }

  const openEditTestimonialModal = (testimonial) => {
    setEditingTestimonial(testimonial)
    setTestimonialForm({
      customer_name: testimonial.customer_name,
      review_text: testimonial.review_text,
      star_rating: testimonial.star_rating,
      date_of_travel: testimonial.date_of_travel || '',
      status: testimonial.status,
      is_featured: testimonial.is_featured,
      source: testimonial.source || ''
    })
    setShowTestimonialModal(true)
  }

  const openAddTestimonialModal = () => {
    setEditingTestimonial(null)
    setTestimonialForm({
      customer_name: '',
      review_text: '',
      star_rating: null,
      date_of_travel: '',
      status: 'inactive',
      is_featured: false,
      source: ''
    })
    setShowTestimonialModal(true)
  }

  // Helper to render star rating display
  const renderStars = (rating) => {
    if (rating === null || rating === undefined) {
      return <span className="no-rating">No rating</span>
    }
    return (
      <span className="star-rating">
        {[1, 2, 3, 4, 5].map(star => (
          <span key={star} className={star <= rating ? 'star filled' : 'star empty'}>
            {star <= rating ? '★' : '☆'}
          </span>
        ))}
      </span>
    )
  }

  const fetchTestResults = async () => {
    setLoadingTestResults(true)
    try {
      const [resultsRes, latestRes] = await Promise.all([
        fetch(`${API_URL}/api/admin/test-results?limit=20`, {
          headers: { 'Authorization': `Bearer ${token}` },
        }),
        fetch(`${API_URL}/api/admin/test-results/latest?environment=production`, {
          headers: { 'Authorization': `Bearer ${token}` },
        }),
      ])
      if (resultsRes.ok) {
        const data = await resultsRes.json()
        setTestResults(data.test_runs || [])
      }
      if (latestRes.ok) {
        const data = await latestRes.json()
        setLatestTestRun(data.test_run)
      }
    } catch (err) {
      console.error('Failed to fetch test results:', err)
    } finally {
      setLoadingTestResults(false)
    }
  }

  const fetchBookingStats = async () => {
    setLoadingStats(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/stats`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setBookingStats(data)
      }
    } catch (err) {
      console.error('Failed to fetch booking stats:', err)
    } finally {
      setLoadingStats(false)
    }
  }

  const fetchFunFacts = async () => {
    setLoadingFunFacts(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/reports/fun-facts`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setFunFacts(data)
      }
    } catch (err) {
      console.error('Failed to fetch fun facts:', err)
    } finally {
      setLoadingFunFacts(false)
    }
  }

  const fetchOccupancyReport = async (view = 'daily') => {
    setLoadingOccupancy(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/reports/occupancy?view=${view}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setOccupancyData(data)
      }
    } catch (err) {
      console.error('Failed to fetch occupancy report:', err)
    } finally {
      setLoadingOccupancy(false)
    }
  }

  const fetchPopularReport = async () => {
    setLoadingPopular(true)
    try {
      const params = new URLSearchParams({
        top: popularTop.toString(),
      })
      const response = await fetch(`${API_URL}/api/admin/reports/popular?${params}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setPopularData(data)
      }
    } catch (err) {
      console.error('Failed to fetch popular report:', err)
    } finally {
      setLoadingPopular(false)
    }
  }

  const fetchMarketingSources = async () => {
    setLoadingMarketingSources(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/marketing-sources/summary`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setMarketingSourcesData(data)
      }
    } catch (err) {
      console.error('Failed to fetch marketing sources:', err)
    } finally {
      setLoadingMarketingSources(false)
    }
  }

  const fetchMarketingOtherDetails = async (yearMonth = null) => {
    setLoadingMarketingOther(true)
    setMarketingOtherMonth(yearMonth)
    try {
      const params = yearMonth ? `?year_month=${yearMonth}` : ''
      const response = await fetch(`${API_URL}/api/admin/marketing-sources/other${params}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setMarketingOtherDetails(data.details || [])
        setShowMarketingOtherModal(true)
      }
    } catch (err) {
      console.error('Failed to fetch marketing other details:', err)
    } finally {
      setLoadingMarketingOther(false)
    }
  }

  // Helper to format date as DD/MM/YYYY
  const formatDateDDMMYYYY = (date) => {
    if (!date) return null
    const day = String(date.getDate()).padStart(2, '0')
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const year = date.getFullYear()
    return `${day}/${month}/${year}`
  }

  const exportMarketingSourcesCSV = async () => {
    try {
      const params = new URLSearchParams()
      if (marketingExportFromDate) {
        params.append('from_date', formatDateDDMMYYYY(marketingExportFromDate))
      }
      if (marketingExportToDate) {
        params.append('to_date', formatDateDDMMYYYY(marketingExportToDate))
      }
      const queryString = params.toString()
      const url = `${API_URL}/api/admin/marketing-sources/export${queryString ? `?${queryString}` : ''}`

      const response = await fetch(url, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const blob = await response.blob()
        const blobUrl = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = blobUrl
        // Include date range in filename if filters are set
        let filename = 'marketing-sources'
        if (marketingExportFromDate || marketingExportToDate) {
          if (marketingExportFromDate) filename += `-from-${formatDateDDMMYYYY(marketingExportFromDate).replace(/\//g, '-')}`
          if (marketingExportToDate) filename += `-to-${formatDateDDMMYYYY(marketingExportToDate).replace(/\//g, '-')}`
        } else {
          filename += `-${new Date().toISOString().split('T')[0]}`
        }
        a.download = `${filename}.csv`
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(blobUrl)
        a.remove()
      }
    } catch (err) {
      console.error('Failed to export marketing sources:', err)
    }
  }

  const fetchBookingLocations = async (type = 'bookings') => {
    setLoadingLocations(true)
    setError('')
    try {
      const response = await fetch(`${API_URL}/api/admin/reports/booking-locations?map_type=${type}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        if (type === 'origins') {
          setOriginLocations(data.locations || [])
          setTotalCustomers(data.total_customers || 0)
        } else {
          setBookingLocations(data.locations || [])
          setTotalBookings(data.total_bookings || 0)
        }
        setSkippedBookings(data.skipped || [])
      } else {
        setError('Failed to load locations')
      }
    } catch (err) {
      setError('Network error loading locations')
    } finally {
      setLoadingLocations(false)
    }
  }

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

  // Promotions functions
  const fetchPromotions = async () => {
    setLoadingPromotions(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/promotions`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setPromotions(data.promotions || [])
      }
    } catch (err) {
      console.error('Failed to fetch promotions:', err)
    } finally {
      setLoadingPromotions(false)
    }
  }

  // Full refresh: clears cache and re-fetches everything including expanded promotion details
  const refreshPromotions = async () => {
    // Clear the promotion details cache to force fresh data
    setPromotionDetails({})
    // Fetch the promotions list
    await fetchPromotions()
    // If a promotion is expanded, re-fetch its details
    if (expandedPromotionId) {
      fetchPromotionDetails(expandedPromotionId)
    }
  }

  const createPromotion = async () => {
    setCreatingPromotion(true)
    setPromotionMessage('')
    try {
      const response = await fetch(`${API_URL}/api/admin/promotions`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(newPromotion),
      })
      if (response.ok) {
        const data = await response.json()
        setPromotionMessage(`Created promotion "${data.name}" with ${data.total_codes} codes`)
        setShowCreatePromotion(false)
        setNewPromotion({ name: '', description: '', discount_percent: 10, total_codes: 10, code_prefix: '' })
        fetchPromotions()
      } else {
        const error = await response.json()
        setPromotionMessage(`Error: ${error.detail || 'Failed to create promotion'}`)
      }
    } catch (err) {
      console.error('Error creating promotion:', err)
      setPromotionMessage('Network error creating promotion')
    } finally {
      setCreatingPromotion(false)
    }
  }

  const fetchPromotionDetails = async (promotionId) => {
    setPromotionDetails(prev => ({ ...prev, [promotionId]: { ...prev[promotionId], loading: true } }))
    try {
      const response = await fetch(`${API_URL}/api/admin/promotions/${promotionId}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setPromotionDetails(prev => ({
          ...prev,
          [promotionId]: { codes: data.codes || [], loading: false }
        }))
      }
    } catch (err) {
      console.error('Failed to fetch promotion details:', err)
      setPromotionDetails(prev => ({ ...prev, [promotionId]: { ...prev[promotionId], loading: false } }))
    }
  }

  const toggleSharedOnSocials = async (promotionId, codeId) => {
    try {
      const response = await fetch(`${API_URL}/api/admin/promo-codes/${codeId}/share-socials`, {
        method: 'PATCH',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        // Update the local state for codes table
        setPromotionDetails(prev => ({
          ...prev,
          [promotionId]: {
            ...prev[promotionId],
            codes: prev[promotionId].codes.map(code =>
              code.id === codeId
                ? { ...code, shared_on_socials: data.shared_on_socials, shared_on_socials_at: data.shared_on_socials_at }
                : code
            )
          }
        }))
        // Auto-refresh promotions list to update codes_available count
        fetchPromotions()
      }
    } catch (err) {
      console.error('Failed to toggle shared on socials:', err)
    }
  }

  const toggleSharedPrivately = async (promotionId, codeId) => {
    try {
      const response = await fetch(`${API_URL}/api/admin/promo-codes/${codeId}/share-privately`, {
        method: 'PATCH',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        // Update the local state for codes table
        setPromotionDetails(prev => ({
          ...prev,
          [promotionId]: {
            ...prev[promotionId],
            codes: prev[promotionId].codes.map(code =>
              code.id === codeId
                ? { ...code, shared_privately: data.shared_privately, shared_privately_at: data.shared_privately_at }
                : code
            )
          }
        }))
        // Auto-refresh promotions list to update codes_available count
        fetchPromotions()
      }
    } catch (err) {
      console.error('Failed to toggle shared privately:', err)
    }
  }

  const openSendPromoEmailModal = async (promotion) => {
    // Fetch available (unsent) codes for this promotion
    try {
      const response = await fetch(`${API_URL}/api/admin/promotions/${promotion.id}/available-codes`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setSendPromoEmailData({ promotion, availableCodes: data.codes || [] })
        setPromoEmailRecipients([])
        setPromoEmailSubject(`{{FIRST_NAME}}, here is your ${promotion.discount_percent}% off promo code`)
        setPromoEmailBody(`<p>Hi {{FIRST_NAME}},</p>
<p>Thank you for your interest in TAG Parking!</p>
<p>Here is your exclusive promo code for <strong>${promotion.discount_percent}% off</strong>:</p>
<p style="font-size: 24px; font-weight: bold; color: #007bff;">{{PROMO_CODE}}</p>
<p>Simply enter this code at checkout to apply your discount.</p>
<p>Best regards,<br>Kristian</p>`)
        setShowSendPromoEmailModal(true)
      }
    } catch (err) {
      console.error('Failed to fetch available codes:', err)
    }
  }

  const updatePromotion = async (promotionId, newName) => {
    try {
      const response = await fetch(`${API_URL}/api/admin/promotions/${promotionId}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name: newName }),
      })
      if (response.ok) {
        setPromotionMessage('Promotion updated successfully')
        setEditingPromotion(null)
        fetchPromotions()
      } else {
        const data = await response.json()
        setPromotionMessage(`Error: ${data.detail || 'Failed to update promotion'}`)
      }
    } catch (err) {
      setPromotionMessage('Network error updating promotion')
    }
  }

  const deletePromotion = async (promotionId) => {
    if (!window.confirm('Are you sure you want to delete this promotion? This cannot be undone.')) {
      return
    }
    setDeletingPromotionId(promotionId)
    try {
      const response = await fetch(`${API_URL}/api/admin/promotions/${promotionId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        setPromotionMessage('Promotion deleted successfully')
        fetchPromotions()
      } else {
        const data = await response.json()
        setPromotionMessage(`Error: ${data.detail || 'Failed to delete promotion'}`)
      }
    } catch (err) {
      setPromotionMessage('Network error deleting promotion')
    } finally {
      setDeletingPromotionId(null)
    }
  }

  const openGenerateCodesModal = (promotion) => {
    setGenerateCodesPromotion(promotion)
    setGenerateCodesCount(10)
    setShowGenerateCodesModal(true)
  }

  const generateMoreCodes = async () => {
    if (!generateCodesPromotion) return
    setGeneratingCodes(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/promotions/${generateCodesPromotion.id}/generate-codes`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ count: generateCodesCount }),
      })
      if (response.ok) {
        const data = await response.json()
        setPromotionMessage(`Successfully generated ${data.codes_created} new codes`)
        setShowGenerateCodesModal(false)
        setGenerateCodesPromotion(null)
        fetchPromotions()
        // Refresh details if expanded
        if (promotionDetails[generateCodesPromotion.id]) {
          fetchPromotionDetails(generateCodesPromotion.id)
        }
      } else {
        const data = await response.json()
        setPromotionMessage(`Error: ${data.detail || 'Failed to generate codes'}`)
      }
    } catch (err) {
      setPromotionMessage('Network error generating codes')
    } finally {
      setGeneratingCodes(false)
    }
  }

  const searchRecipients = async (searchTerm) => {
    if (!searchTerm || searchTerm.length < 2) {
      setRecipientSearchResults([])
      return
    }
    setSearchingRecipients(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/promotions/recipients/search?q=${encodeURIComponent(searchTerm)}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setRecipientSearchResults(data.recipients || [])
      }
    } catch (err) {
      console.error('Failed to search recipients:', err)
    } finally {
      setSearchingRecipients(false)
    }
  }

  const addRecipient = (recipient) => {
    // Check if already added
    if (promoEmailRecipients.some(r => r.email === recipient.email)) {
      return
    }
    setPromoEmailRecipients(prev => [...prev, recipient])
    setRecipientSearchTerm('')
    setRecipientSearchResults([])
  }

  const addManualRecipient = () => {
    if (!manualRecipient.email || !manualRecipient.first_name) {
      return
    }
    // Check if already added
    if (promoEmailRecipients.some(r => r.email === manualRecipient.email)) {
      setManualRecipient({ email: '', first_name: '', last_name: '' })
      return
    }
    setPromoEmailRecipients(prev => [...prev, {
      ...manualRecipient,
      source: 'new'
    }])
    setManualRecipient({ email: '', first_name: '', last_name: '' })
  }

  const removeRecipient = (email) => {
    setPromoEmailRecipients(prev => prev.filter(r => r.email !== email))
  }

  const sendPromoEmails = async () => {
    if (!sendPromoEmailData || promoEmailRecipients.length === 0) return

    // Check we have enough codes
    if (promoEmailRecipients.length > sendPromoEmailData.availableCodes.length) {
      setPromotionMessage(`Error: Not enough available codes (${sendPromoEmailData.availableCodes.length} available, ${promoEmailRecipients.length} needed)`)
      return
    }

    setSendingPromoEmails(true)
    setPromotionMessage('')
    try {
      const response = await fetch(`${API_URL}/api/admin/promotions/send-emails`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          promotion_id: sendPromoEmailData.promotion.id,
          recipients: promoEmailRecipients,
          email_subject: promoEmailSubject,
          email_body: promoEmailBody,
        }),
      })
      if (response.ok) {
        const data = await response.json()
        setPromotionMessage(`Successfully sent ${data.total_sent} promo emails`)
        setShowSendPromoEmailModal(false)
        fetchPromotions()
        // Refresh promotion details if expanded
        if (expandedPromotionId === sendPromoEmailData.promotion.id) {
          fetchPromotionDetails(sendPromoEmailData.promotion.id)
        }
      } else {
        const error = await response.json()
        setPromotionMessage(`Error: ${error.detail || 'Failed to send emails'}`)
      }
    } catch (err) {
      setPromotionMessage('Network error sending emails')
    } finally {
      setSendingPromoEmails(false)
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
      if (flightNumberFilter) params.append('flight_number', flightNumberFilter)

      // Backend now handles date filtering (start_date defaults to 2026-01-01)
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

      // Only send editable fields, not the entire flight object
      const editableFields = flightsSubTab === 'departures'
        ? { flight_number: editFlightForm.flight_number, departure_time: editFlightForm.departure_time, capacity_tier: editFlightForm.capacity_tier }
        : { flight_number: editFlightForm.flight_number, arrival_time: editFlightForm.arrival_time }

      const response = await fetch(endpoint, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(editableFields),
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
          days_1_4_price: data.days_1_4_price ?? 65,
          week1_base_price: data.week1_base_price ?? 85,
          week2_base_price: data.week2_base_price ?? 150,
          daily_increment: data.daily_increment ?? 8,
          tier_increment: data.tier_increment ?? 5,
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

  const sendPromo10Reminder = async (subscriber) => {
    setSendingPromoId(subscriber.id)
    setError('')

    try {
      const response = await fetch(
        `${API_URL}/api/admin/marketing-subscribers/${subscriber.id}/send-promo-10-reminder`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      )

      const data = await response.json()

      if (response.ok) {
        setPromoSuccessMessage(`10% promo reminder sent to ${subscriber.email}`)
        setTimeout(() => setPromoSuccessMessage(''), 5000)
        fetchSubscribers()
      } else {
        setError(data.detail || 'Failed to send promo reminder email')
      }
    } catch (err) {
      setError('Network error sending promo reminder email')
    } finally {
      setSendingPromoId(null)
    }
  }

  const sendPromoFreeReminder = async (subscriber) => {
    setSendingPromoId(subscriber.id)
    setError('')

    try {
      const response = await fetch(
        `${API_URL}/api/admin/marketing-subscribers/${subscriber.id}/send-promo-free-reminder`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      )

      const data = await response.json()

      if (response.ok) {
        setPromoSuccessMessage(`FREE parking promo reminder sent to ${subscriber.email}`)
        setTimeout(() => setPromoSuccessMessage(''), 5000)
        fetchSubscribers()
      } else {
        setError(data.detail || 'Failed to send FREE promo reminder email')
      }
    } catch (err) {
      setError('Network error sending FREE promo reminder email')
    } finally {
      setSendingPromoId(null)
    }
  }

  const openFounderEmailModal = (subscriber) => {
    setFounderEmailToSend({ subscriber })
    setShowSubscriberFounderModal(true)
  }

  const confirmSendFounderEmail = async () => {
    if (!founderEmailToSend) return

    const { subscriber } = founderEmailToSend
    setSendingFounderEmailId(subscriber.id)
    setError('')

    try {
      const response = await fetch(
        `${API_URL}/api/admin/marketing-subscribers/${subscriber.id}/send-founder-email`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      )

      const data = await response.json()

      if (response.ok) {
        setPromoSuccessMessage(`Founder thank you email sent to ${subscriber.email}`)
        setTimeout(() => setPromoSuccessMessage(''), 5000)
        fetchSubscribers()
        setShowSubscriberFounderModal(false)
        setFounderEmailToSend(null)
      } else {
        setError(data.detail || 'Failed to send founder email')
      }
    } catch (err) {
      setError('Network error sending founder email')
    } finally {
      setSendingFounderEmailId(null)
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

  // Recent 10 bookings (sorted by ID descending - newest first)
  const recentBookings = useMemo(() => {
    let recent = [...bookings]

    // Hide test emails
    if (hideTestEmails) {
      recent = recent.filter(b => !isTestEmail(b.customer?.email))
    }

    // Sort by ID descending (newest first)
    recent.sort((a, b) => b.id - a.id)

    // Take top 10 most recent
    return recent.slice(0, 10)
  }, [bookings, hideTestEmails])

  // Group bookings by status
  const bookingsByStatus = useMemo(() => {
    const groups = {
      confirmed: [],
      completed: [],
      pending: [],
      cancelled: []
    }

    filteredBookings.forEach(booking => {
      const status = (booking.status || 'pending').toLowerCase()
      if (groups[status]) {
        groups[status].push(booking)
      } else {
        // Handle refunded or other statuses - put in cancelled
        groups.cancelled.push(booking)
      }
    })

    return groups
  }, [filteredBookings])

  const toggleStatusSection = (status) => {
    setCollapsedStatusSections(prev => ({
      ...prev,
      [status]: !prev[status]
    }))
  }

  // Helper to group bookings by month (for confirmed/completed)
  const groupBookingsByMonth = (bookingsList) => {
    const groups = {}
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                        'July', 'August', 'September', 'October', 'November', 'December']

    bookingsList.forEach(booking => {
      if (!booking.dropoff_date) return
      const monthKey = booking.dropoff_date.substring(0, 7) // YYYY-MM
      if (!groups[monthKey]) {
        const [year, month] = monthKey.split('-')
        groups[monthKey] = {
          label: `${monthNames[parseInt(month) - 1]} ${year}`,
          bookings: []
        }
      }
      groups[monthKey].bookings.push(booking)
    })

    return groups
  }

  const toggleBookingMonth = (statusKey, monthKey) => {
    const key = `${statusKey}-${monthKey}`
    setExpandedBookingMonths(prev => ({
      ...prev,
      [key]: !prev[key]
    }))
  }

  // Render a single booking card (extracted for reuse)
  const renderBookingCard = (booking) => (
    <div
      key={booking.id || booking.reference}
      data-booking-id={booking.id}
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
              {/* Billing Address - show for confirmed/completed bookings */}
              {booking.customer?.billing_address1 && (
                <div className="booking-detail billing-address-detail">
                  <span className="detail-label">Billing Address</span>
                  <span className="detail-value billing-address">
                    {booking.customer.billing_address1}
                    {booking.customer.billing_address2 && <><br />{booking.customer.billing_address2}</>}
                    <br />
                    {booking.customer.billing_city}
                    {booking.customer.billing_county && `, ${booking.customer.billing_county}`}
                    <br />
                    {booking.customer.billing_postcode}
                    {booking.customer.billing_country && booking.customer.billing_country !== 'United Kingdom' && (
                      <><br />{booking.customer.billing_country}</>
                    )}
                  </span>
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
                  <span className="detail-label">Duration</span>
                  <span className="detail-value">
                    {(() => {
                      if (booking.dropoff_date && booking.pickup_date) {
                        const days = Math.round((new Date(booking.pickup_date) - new Date(booking.dropoff_date)) / (1000 * 60 * 60 * 24));
                        return `${days} Day${days !== 1 ? 's' : ''}`;
                      }
                      return booking.package === 'quick' ? '1-7 Days' :
                             booking.package === 'longer' ? '8-14 Days' :
                             booking.package || 'N/A';
                    })()}
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
                  <span className="detail-label">Flight Departs</span>
                  <span className="detail-value">{booking.flight_departure_time || '-'}</span>
                </div>
                <div className="booking-detail">
                  <span className="detail-label">Flight</span>
                  <span className="detail-value">
                    {booking.dropoff_airline_name && (
                      <span className="airline-name">{booking.dropoff_airline_name}</span>
                    )}
                    {booking.dropoff_flight_number && booking.dropoff_flight_number !== 'Unknown' && (
                      <span className="flight-number">{booking.dropoff_flight_number}</span>
                    )}
                    {!booking.dropoff_airline_name && (!booking.dropoff_flight_number || booking.dropoff_flight_number === 'Unknown') && '-'}
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
                    {booking.pickup_time
                      ? `From ${booking.pickup_time} onwards`
                      : '-'}
                  </span>
                </div>
                <div className="booking-detail">
                  <span className="detail-label">Flight Arrives</span>
                  <span className="detail-value">{booking.flight_arrival_time || '-'}</span>
                </div>
                <div className="booking-detail">
                  <span className="detail-label">Flight</span>
                  <span className="detail-value">
                    {booking.pickup_airline_name && (
                      <span className="airline-name">{booking.pickup_airline_name}</span>
                    )}
                    {booking.pickup_flight_number && booking.pickup_flight_number !== 'Unknown' && (
                      <span className="flight-number">{booking.pickup_flight_number}</span>
                    )}
                    {!booking.pickup_airline_name && (!booking.pickup_flight_number || booking.pickup_flight_number === 'Unknown') && '-'}
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
              {booking.status?.toLowerCase() !== 'completed' && (
                <button
                  className="action-btn edit-btn"
                  onClick={(e) => handleEditBookingClick(booking, e)}
                >
                  Edit Booking Details
                </button>
              )}
              {booking.status?.toLowerCase() !== 'completed' && (
                <button
                  className="action-btn email-btn"
                  onClick={(e) => handleResendEmailClick(booking, e)}
                  disabled={resendingEmailId === booking.id}
                >
                  {resendingEmailId === booking.id ? 'Sending...' : 'Resend Confirmation Email'}
                </button>
              )}
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
               booking.status?.toLowerCase() !== 'refunded' &&
               booking.status?.toLowerCase() !== 'completed' && (
                <button
                  className="action-btn refund-btn"
                  onClick={(e) => handleRefundClick(booking, e)}
                >
                  Process Refund
                </button>
              )}
              {booking.status?.toLowerCase() !== 'cancelled' &&
               booking.status?.toLowerCase() !== 'refunded' &&
               booking.status?.toLowerCase() !== 'completed' && (
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
              {/* Send Founder Email button for pending bookings */}
              {booking.status?.toLowerCase() === 'pending' && (
                <button
                  className="action-btn email-btn"
                  onClick={(e) => handleSendFounderEmailClick(booking, e)}
                  disabled={sendingFounderEmailId === booking.id || booking.customer?.founder_followup_sent}
                  title={booking.customer?.founder_followup_sent ? 'Founder email already sent' : 'Send personal follow-up email from founder'}
                >
                  {sendingFounderEmailId === booking.id ? 'Sending...' :
                   booking.customer?.founder_followup_sent ? 'Founder Email Sent ✓' : 'Send Founder Email'}
                </button>
              )}
              {/* View Drop-off Vehicle Inspection button for completed bookings */}
              {booking.status?.toLowerCase() === 'completed' && booking.id && (
                <button
                  className="action-btn view-inspection-btn"
                  onClick={(e) => handleViewDropoffInspectionClick(booking, e)}
                >
                  View Drop-off Inspection
                </button>
              )}
              {/* View Return Vehicle Inspection button for completed bookings */}
              {booking.status?.toLowerCase() === 'completed' && booking.id && (
                <button
                  className="action-btn view-inspection-btn"
                  onClick={(e) => handleViewReturnInspectionClick(booking, e)}
                >
                  View Return Inspection
                </button>
              )}
              {/* Delete button for pending and cancelled bookings */}
              {['pending', 'cancelled'].includes(booking.status?.toLowerCase()) && (
                <button
                  className="action-btn delete-btn"
                  onClick={(e) => handleDeleteClick(booking, e)}
                  disabled={deletingId === booking.id}
                >
                  {deletingId === booking.id ? 'Deleting...' : 'Delete'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )

  // Group flights by month (YYYY-MM format)
  const departuresByMonth = useMemo(() => {
    const groups = {}
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                        'July', 'August', 'September', 'October', 'November', 'December']

    departures.forEach(flight => {
      if (!flight.date) return
      const monthKey = flight.date.substring(0, 7) // YYYY-MM
      if (!groups[monthKey]) {
        const [year, month] = monthKey.split('-')
        groups[monthKey] = {
          label: `${monthNames[parseInt(month) - 1]} ${year}`,
          flights: []
        }
      }
      groups[monthKey].flights.push(flight)
    })

    // Sort month keys chronologically
    return Object.keys(groups)
      .sort()
      .reduce((acc, key) => {
        acc[key] = groups[key]
        return acc
      }, {})
  }, [departures])

  const arrivalsByMonth = useMemo(() => {
    const groups = {}
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                        'July', 'August', 'September', 'October', 'November', 'December']

    arrivals.forEach(flight => {
      if (!flight.date) return
      const monthKey = flight.date.substring(0, 7) // YYYY-MM
      if (!groups[monthKey]) {
        const [year, month] = monthKey.split('-')
        groups[monthKey] = {
          label: `${monthNames[parseInt(month) - 1]} ${year}`,
          flights: []
        }
      }
      groups[monthKey].flights.push(flight)
    })

    // Sort month keys chronologically
    return Object.keys(groups)
      .sort()
      .reduce((acc, key) => {
        acc[key] = groups[key]
        return acc
      }, {})
  }, [arrivals])

  const toggleFlightMonth = (monthKey) => {
    setCollapsedFlightMonths(prev => ({
      ...prev,
      [monthKey]: !prev[monthKey]
    }))
  }

  const resetAddFlightForm = () => {
    setAddFlightForm({
      date: '',
      flight_number: '',
      airline_code: '',
      airline_name: '',
      time: '',
      destination_code: '',
      destination_name: '',
      origin_code: '',
      origin_name: '',
      capacity_tier: 0,
      departure_time: '',
    })
  }

  const handleAddFlight = async () => {
    setAddingFlight(true)
    setFlightsMessage('')
    try {
      const isDeparture = flightsSubTab === 'departures'
      const endpoint = isDeparture
        ? `${API_URL}/api/admin/flights/departures`
        : `${API_URL}/api/admin/flights/arrivals`

      const payload = isDeparture
        ? {
            date: addFlightForm.date,
            flight_number: addFlightForm.flight_number,
            airline_code: addFlightForm.airline_code,
            airline_name: addFlightForm.airline_name,
            departure_time: addFlightForm.time,
            destination_code: addFlightForm.destination_code,
            destination_name: addFlightForm.destination_name || null,
            capacity_tier: parseInt(addFlightForm.capacity_tier) || 0,
          }
        : {
            date: addFlightForm.date,
            flight_number: addFlightForm.flight_number,
            airline_code: addFlightForm.airline_code,
            airline_name: addFlightForm.airline_name,
            arrival_time: addFlightForm.time,
            origin_code: addFlightForm.origin_code,
            origin_name: addFlightForm.origin_name || null,
            departure_time: addFlightForm.departure_time || null,
          }

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })

      if (response.ok) {
        setFlightsMessage(`Flight ${addFlightForm.flight_number} created successfully`)
        setShowAddFlightModal(false)
        resetAddFlightForm()
        fetchFlights()
      } else {
        const data = await response.json()
        setFlightsMessage(`Error: ${data.detail || 'Failed to create flight'}`)
      }
    } catch (err) {
      setFlightsMessage(`Error: ${err.message}`)
    } finally {
      setAddingFlight(false)
    }
  }

  const confirmDeleteFlight = (flight) => {
    setFlightToDelete(flight)
    setShowDeleteFlightModal(true)
  }

  const handleDeleteFlight = async () => {
    if (!flightToDelete) return
    setDeletingFlightId(flightToDelete.id)
    setFlightsMessage('')
    try {
      const isDeparture = flightsSubTab === 'departures'
      const endpoint = isDeparture
        ? `${API_URL}/api/admin/flights/departures/${flightToDelete.id}`
        : `${API_URL}/api/admin/flights/arrivals/${flightToDelete.id}`

      const response = await fetch(endpoint, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      })

      if (response.ok) {
        setFlightsMessage(`Flight ${flightToDelete.flight_number} deleted successfully`)
        setShowDeleteFlightModal(false)
        setFlightToDelete(null)
        fetchFlights()
      } else {
        const data = await response.json()
        setFlightsMessage(`Error: ${data.detail || 'Failed to delete flight'}`)
      }
    } catch (err) {
      setFlightsMessage(`Error: ${err.message}`)
    } finally {
      setDeletingFlightId(null)
    }
  }

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

    // Apply date filter
    if (subscriberDateFrom || subscriberDateTo) {
      filtered = filtered.filter(s => {
        const subDate = s.subscribed_at ? new Date(s.subscribed_at) : null
        if (!subDate) return false
        if (subscriberDateFrom) {
          const fromDate = new Date(subscriberDateFrom)
          fromDate.setHours(0, 0, 0, 0)
          if (subDate < fromDate) return false
        }
        if (subscriberDateTo) {
          const toDate = new Date(subscriberDateTo)
          toDate.setHours(23, 59, 59, 999)
          if (subDate > toDate) return false
        }
        return true
      })
    }

    return filtered
  }, [subscribers, subscriberSearchTerm, subscriberStatusFilter, hideTestEmails, subscriberDateFrom, subscriberDateTo])

  // Filter customers
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

  const handleDeleteClick = (booking, e) => {
    e.stopPropagation()
    setBookingToDelete(booking)
    setShowDeleteModal(true)
  }

  const confirmDeleteBooking = async () => {
    if (!bookingToDelete) return

    setDeletingId(bookingToDelete.id)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/${bookingToDelete.id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })

      const data = await response.json()

      if (response.ok) {
        setSuccessMessage(data.message || 'Booking deleted successfully')
        fetchBookings()
        setTimeout(() => setSuccessMessage(''), 5000)
      } else {
        setError(data.detail || 'Failed to delete booking')
      }
    } catch (err) {
      setError('Network error while deleting booking')
    } finally {
      setDeletingId(null)
      setShowDeleteModal(false)
      setBookingToDelete(null)
    }
  }

  const handleEditBookingClick = (booking, e) => {
    e.stopPropagation()
    setBookingToEdit(booking)
    setEditForm({
      // Dropoff/Departure details
      dropoff_time: booking.dropoff_time || '',
      flight_departure_time: booking.flight_departure_time || '',
      dropoff_airline_name: booking.dropoff_airline_name || '',
      dropoff_flight_number: booking.dropoff_flight_number || '',
      dropoff_destination: booking.dropoff_destination || '',
      // Pickup/Return details - convert ISO date to UK format for display
      pickup_date: isoToUkDate(booking.pickup_date) || '',
      flight_arrival_time: booking.flight_arrival_time || '',
      pickup_airline_name: booking.pickup_airline_name || '',
      pickup_flight_number: booking.pickup_flight_number || '',
      pickup_origin: booking.pickup_origin || '',
    })
    setShowEditModal(true)
  }

  const confirmEditBooking = async () => {
    if (!bookingToEdit) return

    setSavingEdit(true)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/${bookingToEdit.id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          // Dropoff/Departure details
          dropoff_time: editForm.dropoff_time || null,
          flight_departure_time: editForm.flight_departure_time || null,
          dropoff_airline_name: editForm.dropoff_airline_name || null,
          dropoff_flight_number: editForm.dropoff_flight_number || null,
          dropoff_destination: editForm.dropoff_destination || null,
          // Pickup/Return details - convert UK date back to ISO format for API
          pickup_date: ukToIsoDate(editForm.pickup_date) || null,
          flight_arrival_time: editForm.flight_arrival_time || null,
          pickup_airline_name: editForm.pickup_airline_name || null,
          pickup_flight_number: editForm.pickup_flight_number || null,
          pickup_origin: editForm.pickup_origin || null,
        }),
      })

      const data = await response.json()

      if (response.ok) {
        setSuccessMessage(data.message || 'Booking updated successfully')
        fetchBookings()
        setTimeout(() => setSuccessMessage(''), 5000)
        setShowEditModal(false)
        setBookingToEdit(null)
      } else {
        setError(data.detail || 'Failed to update booking')
      }
    } catch (err) {
      setError('Network error while updating booking')
    } finally {
      setSavingEdit(false)
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

  const handleSendFounderEmailClick = (booking, e) => {
    e.stopPropagation()
    setBookingForFounderEmail(booking)
    setShowFounderEmailModal(true)
  }

  const handleConfirmSendFounderEmail = async () => {
    if (!bookingForFounderEmail) return

    setSendingFounderEmailId(bookingForFounderEmail.id)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/${bookingForFounderEmail.id}/send-founder-email`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        setShowFounderEmailModal(false)
        setSuccessMessage(`Founder email sent to ${bookingForFounderEmail.customer?.email}`)
        setBookingForFounderEmail(null)
        // Refresh bookings to update email sent status
        await fetchBookings()
        // Clear success message after 5 seconds
        setTimeout(() => setSuccessMessage(''), 5000)
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to send founder email')
      }
    } catch (err) {
      setError('Network error while sending founder email')
    } finally {
      setSendingFounderEmailId(null)
    }
  }

  // Return Vehicle Inspection handlers
  const handleViewReturnInspectionClick = async (booking, e) => {
    e.stopPropagation()
    setBookingForInspection(booking)
    setShowReturnInspectionModal(true)
    setLoadingReturnInspection(true)
    setReturnInspectionData(null)

    try {
      const response = await fetch(`${API_URL}/api/employee/inspections/${booking.id}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })

      if (response.ok) {
        const data = await response.json()
        // API returns { inspections: [...] } or just [...]
        const inspections = Array.isArray(data) ? data : (data.inspections || [])
        // Find the pickup/return inspection
        const returnInspection = inspections.find(i => i.inspection_type === 'pickup')
        setReturnInspectionData(returnInspection || null)
      } else {
        setReturnInspectionData(null)
      }
    } catch (err) {
      console.error('Error fetching return inspection:', err)
      setReturnInspectionData(null)
    } finally {
      setLoadingReturnInspection(false)
    }
  }

  const closeReturnInspectionModal = () => {
    setShowReturnInspectionModal(false)
    setBookingForInspection(null)
    setReturnInspectionData(null)
  }

  // Drop-off Vehicle Inspection handlers
  const handleViewDropoffInspectionClick = async (booking, e) => {
    e.stopPropagation()
    setBookingForDropoffInspection(booking)
    setShowDropoffInspectionModal(true)
    setLoadingDropoffInspection(true)
    setDropoffInspectionData(null)

    try {
      const response = await fetch(`${API_URL}/api/employee/inspections/${booking.id}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })

      if (response.ok) {
        const data = await response.json()
        // API returns { inspections: [...] } or just [...]
        const inspections = Array.isArray(data) ? data : (data.inspections || [])
        // Find the dropoff inspection
        const dropoffInspection = inspections.find(i => i.inspection_type === 'dropoff')
        setDropoffInspectionData(dropoffInspection || null)
      } else {
        setDropoffInspectionData(null)
      }
    } catch (err) {
      console.error('Error fetching drop-off inspection:', err)
      setDropoffInspectionData(null)
    } finally {
      setLoadingDropoffInspection(false)
    }
  }

  const closeDropoffInspectionModal = () => {
    setShowDropoffInspectionModal(false)
    setBookingForDropoffInspection(null)
    setDropoffInspectionData(null)
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

  // UK date format: dd/mm/yyyy (in UK timezone)
  const formatDateUK = (dateStr) => {
    if (!dateStr) return '-'
    const date = new Date(dateStr)
    return date.toLocaleDateString('en-GB', { timeZone: 'Europe/London' })
  }

  // UK datetime format: dd/mm/yyyy, HH:mm:ss (in UK timezone)
  const formatDateTimeUK = (dateStr) => {
    if (!dateStr) return '-'
    const date = new Date(dateStr)
    return date.toLocaleString('en-GB', { timeZone: 'Europe/London' })
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
          className={`admin-nav-item ${activeTab === 'customers' ? 'active' : ''}`}
          onClick={() => setActiveTab('customers')}
        >
          Customers
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
        <button
          className={`admin-nav-item ${activeTab === 'qa' ? 'active' : ''}`}
          onClick={() => setActiveTab('qa')}
        >
          QA
        </button>
        <button
          className={`admin-nav-item ${activeTab === 'testimonials' ? 'active' : ''}`}
          onClick={() => setActiveTab('testimonials')}
        >
          Testimonials
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

            {/* Recent 10 Bookings */}
            {recentBookings.length > 0 && (
              <div className="recent-bookings-container">
                <h3 className="recent-bookings-title">Recent Bookings</h3>
                <div className="recent-bookings-grid">
                  {recentBookings.map((booking) => (
                    <div
                      key={booking.id || booking.reference}
                      className={`recent-booking-card booking-status-${booking.status?.toLowerCase() || 'pending'}`}
                      onClick={() => {
                        setExpandedBookingId(booking.id)
                        // Scroll to the booking in the main list
                        setTimeout(() => {
                          const element = document.querySelector(`.booking-card[data-booking-id="${booking.id}"]`)
                          if (element) {
                            element.scrollIntoView({ behavior: 'smooth', block: 'center' })
                          }
                        }, 100)
                      }}
                    >
                      <div className="recent-booking-ref">{booking.reference}</div>
                      <div className="recent-booking-name">
                        {booking.customer?.first_name} {booking.customer?.last_name}
                      </div>
                      <div className="recent-booking-date">
                        {new Date(booking.dropoff_date + 'T12:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'Europe/London' })}
                      </div>
                      <div className={`recent-booking-status status-${booking.status?.toLowerCase() || 'pending'}`}>
                        {booking.status || 'Pending'}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

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
              <div className="bookings-by-status">
                {/* Render each status section in order: Confirmed, Completed, Pending, Cancelled */}
                {[
                  { key: 'confirmed', label: 'Confirmed', color: '#28a745' },
                  { key: 'completed', label: 'Completed', color: '#6c757d' },
                  { key: 'pending', label: 'Pending', color: '#ffc107' },
                  { key: 'cancelled', label: 'Cancelled', color: '#dc3545' }
                ].map(({ key: statusKey, label, color }) => {
                  const statusBookings = bookingsByStatus[statusKey]
                  if (statusBookings.length === 0) return null

                  return (
                    <div key={statusKey} className={`status-section status-section-${statusKey}`}>
                      <div
                        className="status-section-header"
                        onClick={() => toggleStatusSection(statusKey)}
                        style={{ borderLeftColor: color }}
                      >
                        <div className="status-section-title">
                          <span className="status-section-indicator" style={{ backgroundColor: color }}></span>
                          <h3>{label}</h3>
                          <span className="status-section-count">{statusBookings.length}</span>
                        </div>
                        <span className={`status-section-toggle ${collapsedStatusSections[statusKey] ? 'collapsed' : ''}`}>
                          {collapsedStatusSections[statusKey] ? '+' : '-'}
                        </span>
                      </div>

                      {!collapsedStatusSections[statusKey] && (
                        <div className="booking-accordion">
                          {/* For confirmed and completed, group by month */}
                          {(statusKey === 'confirmed' || statusKey === 'completed') ? (
                            (() => {
                              const monthlyGroups = groupBookingsByMonth(statusBookings)
                              const sortedMonths = Object.keys(monthlyGroups).sort() // ASC order (oldest first)

                              return sortedMonths.map(monthKey => {
                                const { label, bookings: monthBookings } = monthlyGroups[monthKey]
                                const expandKey = `${statusKey}-${monthKey}`
                                const isExpanded = expandedBookingMonths[expandKey]

                                return (
                                  <div key={monthKey} className="leads-month-container">
                                    <div
                                      className="leads-month-header"
                                      onClick={() => toggleBookingMonth(statusKey, monthKey)}
                                    >
                                      <span className="expand-icon">{isExpanded ? '▼' : '▶'}</span>
                                      <span className="month-name">{label}</span>
                                      <span className="month-total">{monthBookings.length} booking{monthBookings.length !== 1 ? 's' : ''}</span>
                                    </div>
                                    {isExpanded && (
                                      <div className="leads-month-content">
                                        {monthBookings.map(booking => renderBookingCard(booking))}
                                      </div>
                                    )}
                                  </div>
                                )
                              })
                            })()
                          ) : (
                            /* For pending and cancelled, show flat list */
                            statusBookings.map(booking => renderBookingCard(booking))
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {activeTab === 'calendar' && (
          <div className="admin-section">
            <RosterCalendar token={token} isAdmin={true} />
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
                      <th>Phone</th>
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
                        <td>{u.phone || '-'}</td>
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
                        <td className="small-text">{u.last_login ? new Date(u.last_login).toLocaleDateString('en-GB', { timeZone: 'Europe/London' }) : 'Never'}</td>
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
                <button
                  className="btn-primary"
                  onClick={() => setShowAddFlightModal(true)}
                >
                  + Add Flight
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
                onClick={() => { setEditingFlightId(null); setFlightsSubTab('departures'); }}
              >
                Departures ({departures.length})
              </button>
              <button
                className={`flights-subtab ${flightsSubTab === 'arrivals' ? 'active' : ''}`}
                onClick={() => { setEditingFlightId(null); setFlightsSubTab('arrivals'); }}
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

              <div className="flight-filter-group">
                <label>Flight #:</label>
                <input
                  type="text"
                  value={flightNumberFilter}
                  onChange={(e) => setFlightNumberFilter(e.target.value.toUpperCase())}
                  placeholder="e.g. BA123"
                  className="flight-number-input"
                />
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

            {/* Data Table - Month Containers */}
            {loadingFlights ? (
              <p className="loading-text">Loading flights...</p>
            ) : flightsSubTab === 'departures' ? (
              <div className="flights-by-month">
                {Object.keys(departuresByMonth).length === 0 ? (
                  <p className="no-data">No departures found</p>
                ) : (
                  Object.entries(departuresByMonth).map(([monthKey, monthData]) => (
                    <div key={monthKey} className="flight-month-section">
                      <div
                        className="flight-month-header"
                        onClick={() => toggleFlightMonth(monthKey)}
                      >
                        <span className="collapse-icon">{collapsedFlightMonths[monthKey] ? '▶' : '▼'}</span>
                        <span className="month-label">{monthData.label}</span>
                        <span className="flight-count">({monthData.flights.length} flights)</span>
                      </div>
                      {!collapsedFlightMonths[monthKey] && (
                        <div className="flights-table-wrapper">
                          <table className="flights-table">
                            <thead>
                              <tr>
                                <th>Date</th>
                                <th>Airline</th>
                                <th>Flight #</th>
                                <th>Departure Time</th>
                                <th>Destination</th>
                                <th>Capacity Tier</th>
                                <th>Early</th>
                                <th>Late</th>
                                <th>Actions</th>
                              </tr>
                            </thead>
                            <tbody>
                              {monthData.flights.map(d => (
                                <tr key={d.id} className={editingFlightId === d.id ? 'editing' : ''}>
                                  {editingFlightId === d.id ? (
                                    <>
                                      <td>{d.date ? d.date.split('-').reverse().join('/') : ''}</td>
                                      <td>{d.airline_name}</td>
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
                                          pattern="[0-2][0-9]:[0-5][0-9]"
                                          placeholder="HH:MM"
                                          value={editFlightForm.departure_time || ''}
                                          onChange={(e) => setEditFlightForm({...editFlightForm, departure_time: e.target.value})}
                                          className="flight-edit-input time-24h"
                                        />
                                      </td>
                                      <td>{d.destination_name}</td>
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
                                        <button className="btn-save" onClick={saveFlightEdit} disabled={savingFlight}>
                                          {savingFlight ? '...' : '✓'}
                                        </button>
                                        <button className="btn-cancel" onClick={cancelEditFlight}>✕</button>
                                      </td>
                                    </>
                                  ) : (
                                    <>
                                      <td>{d.date ? d.date.split('-').reverse().join('/') : ''}</td>
                                      <td>{d.airline_name}</td>
                                      <td>{d.flight_number}</td>
                                      <td>{d.departure_time}</td>
                                      <td>{d.destination_name}</td>
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
                                        <button className="btn-delete" onClick={() => confirmDeleteFlight(d)}>Delete</button>
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
                  ))
                )}
              </div>
            ) : (
              <div className="flights-by-month">
                {Object.keys(arrivalsByMonth).length === 0 ? (
                  <p className="no-data">No arrivals found</p>
                ) : (
                  Object.entries(arrivalsByMonth).map(([monthKey, monthData]) => (
                    <div key={monthKey} className="flight-month-section">
                      <div
                        className="flight-month-header"
                        onClick={() => toggleFlightMonth(monthKey)}
                      >
                        <span className="collapse-icon">{collapsedFlightMonths[monthKey] ? '▶' : '▼'}</span>
                        <span className="month-label">{monthData.label}</span>
                        <span className="flight-count">({monthData.flights.length} flights)</span>
                      </div>
                      {!collapsedFlightMonths[monthKey] && (
                        <div className="flights-table-wrapper">
                          <table className="flights-table">
                            <thead>
                              <tr>
                                <th>Date</th>
                                <th>Airline</th>
                                <th>Flight #</th>
                                <th>Origin</th>
                                <th>Arrival Time</th>
                                <th>Actions</th>
                              </tr>
                            </thead>
                            <tbody>
                              {monthData.flights.map(a => (
                                <tr key={a.id} className={editingFlightId === a.id ? 'editing' : ''}>
                                  {editingFlightId === a.id ? (
                                    <>
                                      <td>{a.date ? a.date.split('-').reverse().join('/') : ''}</td>
                                      <td>{a.airline_name}</td>
                                      <td>
                                        <input
                                          type="text"
                                          value={editFlightForm.flight_number || ''}
                                          onChange={(e) => setEditFlightForm({...editFlightForm, flight_number: e.target.value})}
                                          className="flight-edit-input small"
                                        />
                                      </td>
                                      <td>{a.origin_name}</td>
                                      <td>
                                        <input
                                          type="text"
                                          pattern="[0-2][0-9]:[0-5][0-9]"
                                          placeholder="HH:MM"
                                          value={editFlightForm.arrival_time || ''}
                                          onChange={(e) => setEditFlightForm({...editFlightForm, arrival_time: e.target.value})}
                                          className="flight-edit-input time-24h"
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
                                      <td>{a.date ? a.date.split('-').reverse().join('/') : ''}</td>
                                      <td>{a.airline_name}</td>
                                      <td>{a.flight_number}</td>
                                      <td>{a.origin_name}</td>
                                      <td>{a.arrival_time}{a.departure_time && parseInt(a.departure_time.split(':')[0]) >= 18 && parseInt(a.arrival_time.split(':')[0]) < 6 ? ' +1' : ''}</td>
                                      <td className="flight-actions">
                                        <button className="btn-edit" onClick={() => startEditFlight(a)}>Edit</button>
                                        <button className="btn-delete" onClick={() => confirmDeleteFlight(a)}>Delete</button>
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
                  ))
                )}
              </div>
            )}

            {/* Add Flight Modal */}
            {showAddFlightModal && (
              <div className="modal-overlay" onClick={() => { setShowAddFlightModal(false); resetAddFlightForm(); }}>
                <div className="modal-content add-flight-modal" onClick={e => e.stopPropagation()}>
                  <h3>Add New {flightsSubTab === 'departures' ? 'Departure' : 'Arrival'}</h3>
                  <div className="add-flight-form">
                    <div className="form-row">
                      <label>Date:</label>
                      <input
                        type="date"
                        value={addFlightForm.date}
                        onChange={(e) => setAddFlightForm({...addFlightForm, date: e.target.value})}
                        min="2026-01-01"
                      />
                    </div>
                    <div className="form-row">
                      <label>Flight Number:</label>
                      <input
                        type="text"
                        value={addFlightForm.flight_number}
                        onChange={(e) => setAddFlightForm({...addFlightForm, flight_number: e.target.value.toUpperCase()})}
                        placeholder="e.g. FR1234"
                      />
                    </div>
                    <div className="form-row">
                      <label>Airline Code:</label>
                      <input
                        type="text"
                        value={addFlightForm.airline_code}
                        onChange={(e) => setAddFlightForm({...addFlightForm, airline_code: e.target.value.toUpperCase()})}
                        placeholder="e.g. FR"
                        maxLength={3}
                      />
                    </div>
                    <div className="form-row">
                      <label>Airline Name:</label>
                      <input
                        type="text"
                        value={addFlightForm.airline_name}
                        onChange={(e) => setAddFlightForm({...addFlightForm, airline_name: e.target.value})}
                        placeholder="e.g. Ryanair"
                      />
                    </div>
                    <div className="form-row">
                      <label>{flightsSubTab === 'departures' ? 'Departure' : 'Arrival'} Time:</label>
                      <input
                        type="text"
                        value={addFlightForm.time}
                        onChange={(e) => setAddFlightForm({...addFlightForm, time: e.target.value})}
                        placeholder="HH:MM (24hr)"
                        pattern="[0-2][0-9]:[0-5][0-9]"
                      />
                    </div>
                    {flightsSubTab === 'departures' ? (
                      <>
                        <div className="form-row">
                          <label>Destination Code:</label>
                          <input
                            type="text"
                            value={addFlightForm.destination_code}
                            onChange={(e) => setAddFlightForm({...addFlightForm, destination_code: e.target.value.toUpperCase()})}
                            placeholder="e.g. AGP"
                            maxLength={3}
                          />
                        </div>
                        <div className="form-row">
                          <label>Destination Name:</label>
                          <input
                            type="text"
                            value={addFlightForm.destination_name}
                            onChange={(e) => setAddFlightForm({...addFlightForm, destination_name: e.target.value})}
                            placeholder="e.g. Malaga (optional)"
                          />
                        </div>
                        <div className="form-row">
                          <label>Capacity Tier:</label>
                          <select
                            value={addFlightForm.capacity_tier}
                            onChange={(e) => setAddFlightForm({...addFlightForm, capacity_tier: parseInt(e.target.value)})}
                          >
                            <option value="0">0 (Call Us only)</option>
                            <option value="2">2 (1+1)</option>
                            <option value="4">4 (2+2)</option>
                            <option value="6">6 (3+3)</option>
                            <option value="8">8 (4+4)</option>
                          </select>
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="form-row">
                          <label>Origin Code:</label>
                          <input
                            type="text"
                            value={addFlightForm.origin_code}
                            onChange={(e) => setAddFlightForm({...addFlightForm, origin_code: e.target.value.toUpperCase()})}
                            placeholder="e.g. AGP"
                            maxLength={3}
                          />
                        </div>
                        <div className="form-row">
                          <label>Origin Name:</label>
                          <input
                            type="text"
                            value={addFlightForm.origin_name}
                            onChange={(e) => setAddFlightForm({...addFlightForm, origin_name: e.target.value})}
                            placeholder="e.g. Malaga (optional)"
                          />
                        </div>
                        <div className="form-row">
                          <label>Departure Time (from origin):</label>
                          <input
                            type="text"
                            value={addFlightForm.departure_time}
                            onChange={(e) => setAddFlightForm({...addFlightForm, departure_time: e.target.value})}
                            placeholder="HH:MM (optional)"
                            pattern="[0-2][0-9]:[0-5][0-9]"
                          />
                        </div>
                      </>
                    )}
                  </div>
                  <div className="modal-actions">
                    <button className="modal-btn modal-btn-secondary" onClick={() => { setShowAddFlightModal(false); resetAddFlightForm(); }}>Cancel</button>
                    <button
                      className="modal-btn modal-btn-primary"
                      onClick={handleAddFlight}
                      disabled={addingFlight || !addFlightForm.date || !addFlightForm.flight_number || !addFlightForm.airline_code || !addFlightForm.airline_name || !addFlightForm.time || (flightsSubTab === 'departures' ? !addFlightForm.destination_code : !addFlightForm.origin_code)}
                    >
                      {addingFlight ? 'Adding...' : 'Add Flight'}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Delete Flight Confirmation Modal */}
            {showDeleteFlightModal && flightToDelete && (
              <div className="modal-overlay" onClick={() => { setShowDeleteFlightModal(false); setFlightToDelete(null); }}>
                <div className="modal-content" onClick={e => e.stopPropagation()}>
                  <h3>Delete Flight</h3>
                  <p>Are you sure you want to delete flight <strong>{flightToDelete.flight_number}</strong> on {flightToDelete.date ? flightToDelete.date.split('-').reverse().join('/') : ''}?</p>
                  <p className="warning-text">This action cannot be undone.</p>
                  <div className="modal-actions">
                    <button className="modal-btn modal-btn-secondary" onClick={() => { setShowDeleteFlightModal(false); setFlightToDelete(null); }}>Cancel</button>
                    <button className="modal-btn modal-btn-danger" onClick={handleDeleteFlight} disabled={deletingFlightId}>
                      {deletingFlightId ? 'Deleting...' : 'Delete'}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'marketing' && (
          <div className="admin-section">
            {/* Marketing Sub-tabs */}
            <div className="reports-subtabs" style={{ marginBottom: '20px' }}>
              <button
                className={`reports-subtab ${marketingSubTab === 'subscribers' ? 'active' : ''}`}
                onClick={() => setMarketingSubTab('subscribers')}
              >
                Subscribers
              </button>
              <button
                className={`reports-subtab ${marketingSubTab === 'promotions' ? 'active' : ''}`}
                onClick={() => setMarketingSubTab('promotions')}
              >
                Promotions
              </button>
              <button
                className={`reports-subtab ${marketingSubTab === 'sources' ? 'active' : ''}`}
                onClick={() => setMarketingSubTab('sources')}
              >
                Sources
              </button>
            </div>

            {/* Promotions Success/Error Message */}
            {promotionMessage && (
              <div className={`success-banner ${promotionMessage.startsWith('Error') ? 'error-banner' : ''}`}>
                {promotionMessage}
                <button onClick={() => setPromotionMessage('')} style={{ marginLeft: '10px', background: 'none', border: 'none', cursor: 'pointer' }}>&times;</button>
              </div>
            )}

            {/* Subscribers Sub-tab */}
            {marketingSubTab === 'subscribers' && (
              <>
            <div className="admin-section-header">
              <h2>Marketing Subscribers</h2>
              <div className="flights-header-actions">
                <button
                  className="btn-secondary"
                  onClick={fetchSubscribers}
                  disabled={loadingSubscribers}
                >
                  {loadingSubscribers ? 'Loading...' : '↻ Refresh'}
                </button>
                <button
                  className="btn-primary"
                  onClick={() => {
                    // Generate CSV from filtered subscribers
                    const csvRows = [['First Name', 'Last Name', 'Email', 'Date Subscribed', 'Status', '10% Code', 'Free Code', 'Founder Thank You Email']]
                    filteredSubscribers.forEach(sub => {
                      const dateSubscribed = sub.subscribed_at
                        ? new Date(sub.subscribed_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London' })
                        : ''
                      let status = 'Pending'
                      if (sub.unsubscribed) status = 'Unsubscribed'
                      else if (sub.promo_10_used || sub.promo_free_used) status = 'Code Used'
                      else if (sub.promo_10_sent || sub.promo_free_sent) status = 'Code Sent'
                      const founderEmailStatus = sub.founder_email_sent ? 'Sent' : 'Not Sent'
                      csvRows.push([
                        sub.first_name || '',
                        sub.last_name || '',
                        sub.email || '',
                        dateSubscribed,
                        status,
                        sub.promo_10_code || '',
                        sub.promo_free_code || '',
                        founderEmailStatus
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
                    let filename = 'subscribers'
                    if (subscriberDateFrom && subscriberDateTo) {
                      filename = `subscribers_${formatDateForFilename(subscriberDateFrom)}_to_${formatDateForFilename(subscriberDateTo)}`
                    } else if (subscriberDateFrom) {
                      filename = `subscribers_from_${formatDateForFilename(subscriberDateFrom)}`
                    } else if (subscriberDateTo) {
                      filename = `subscribers_to_${formatDateForFilename(subscriberDateTo)}`
                    } else {
                      filename = `subscribers_all_${formatDateForFilename(new Date())}`
                    }
                    link.setAttribute('download', `${filename}.csv`)
                    link.click()
                    URL.revokeObjectURL(url)
                  }}
                  disabled={loadingSubscribers}
                >
                  ↓ Download CSV
                </button>
              </div>
            </div>

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
              <div className="flight-filter-group leads-date-picker">
                <label>From:</label>
                <DatePicker
                  selected={subscriberDateFrom}
                  onChange={(date) => setSubscriberDateFrom(date)}
                  dateFormat="dd/MM/yyyy"
                  placeholderText="DD/MM/YYYY"
                  className="flight-date-input"
                  isClearable
                />
              </div>
              <div className="flight-filter-group leads-date-picker">
                <label>To:</label>
                <DatePicker
                  selected={subscriberDateTo}
                  onChange={(date) => setSubscriberDateTo(date)}
                  dateFormat="dd/MM/yyyy"
                  placeholderText="DD/MM/YYYY"
                  className="flight-date-input"
                  isClearable
                />
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
            ) : (() => {
              // Group by month
              const monthlyGroups = {}
              filteredSubscribers.forEach(subscriber => {
                const date = subscriber.subscribed_at ? new Date(subscriber.subscribed_at) : null
                if (date) {
                  const monthKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
                  if (!monthlyGroups[monthKey]) monthlyGroups[monthKey] = []
                  monthlyGroups[monthKey].push(subscriber)
                }
              })

              const sortedMonths = Object.keys(monthlyGroups).sort().reverse()
              const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

              if (sortedMonths.length === 0) {
                return <p className="admin-no-data">No subscribers found</p>
              }

              return sortedMonths.map(monthKey => {
                const [year, month] = monthKey.split('-')
                const monthName = `${monthNames[parseInt(month, 10) - 1]} ${year}`
                const monthSubscribers = monthlyGroups[monthKey]
                const isExpanded = expandedSubscriberMonths[monthKey]

                return (
                  <div key={monthKey} className="subscribers-month-container">
                    <div
                      className="subscribers-month-header"
                      onClick={() => setExpandedSubscriberMonths(prev => ({
                        ...prev,
                        [monthKey]: !prev[monthKey]
                      }))}
                    >
                      <span className="expand-icon">{isExpanded ? '▼' : '▶'}</span>
                      <span className="month-name">{monthName}</span>
                      <span className="month-total">{monthSubscribers.length} subscriber{monthSubscribers.length !== 1 ? 's' : ''}</span>
                    </div>
                    {isExpanded && (
                      <div className="subscribers-month-content">
                        {monthSubscribers.map((subscriber) => (
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
                                          {formatDateUK(subscriber.subscribed_at)}
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
                                          {formatDateTimeUK(subscriber.welcome_email_sent_at)}
                                        </span>
                                      </div>
                                    </div>
                                  </div>
                                </div>

                                {/* 10% OFF Promo Section */}
                                <div className="booking-section">
                                  <div className="section-header-with-action">
                                    <h4>10% Off Promo</h4>
                                    <div style={{ display: 'flex', gap: '8px' }}>
                                      {!subscriber.unsubscribed && !subscriber.promo_10_used && (
                                        <button
                                          className={`action-btn promo-btn ${subscriber.promo_10_sent ? 'sent' : 'disabled'}`}
                                          onClick={(e) => { e.stopPropagation(); if (!subscriber.promo_10_sent) alert('This promo has ended.'); }}
                                          disabled={subscriber.promo_10_sent}
                                        >
                                          {subscriber.promo_10_sent ? 'Sent ✓' : 'Send 10% Off'}
                                        </button>
                                      )}
                                      {/* Send Reminder button - only show if promo sent, not used, and reminder not already sent */}
                                      {subscriber.promo_10_sent && !subscriber.promo_10_used && !subscriber.unsubscribed && (
                                        <button
                                          className={`action-btn promo-btn ${subscriber.promo_10_reminder_sent ? 'sent' : ''}`}
                                          onClick={(e) => { e.stopPropagation(); if (!subscriber.promo_10_reminder_sent) sendPromo10Reminder(subscriber); }}
                                          disabled={subscriber.promo_10_reminder_sent}
                                        >
                                          {subscriber.promo_10_reminder_sent ? 'Reminder Sent ✓' : 'Send Reminder'}
                                        </button>
                                      )}
                                    </div>
                                  </div>
                                  <div className="booking-section-content">
                                    {subscriber.promo_10_code ? (
                                    <>
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
                                            {formatDateTimeUK(subscriber.promo_10_sent_at)}
                                          </span>
                                        </div>
                                      </div>
                                      {/* Reminder Row - aligned under Status and Sent At */}
                                      {subscriber.promo_10_reminder_sent && (
                                        <div className="booking-detail-row" style={{ marginTop: '8px' }}>
                                          <div className="booking-detail">
                                            {/* Empty spacer to align with Code column */}
                                          </div>
                                          <div className="booking-detail">
                                            <span className="detail-label">Reminder</span>
                                            <span className="detail-value">
                                              <span className="status-badge sent">Sent</span>
                                            </span>
                                          </div>
                                          <div className="booking-detail">
                                            <span className="detail-label">Reminder Sent At</span>
                                            <span className="detail-value">
                                              {formatDateTimeUK(subscriber.promo_10_reminder_sent_at)}
                                            </span>
                                          </div>
                                        </div>
                                      )}
                                    </>
                                    ) : (
                                      <p className="section-empty">Not sent yet</p>
                                    )}
                                  </div>
                                </div>

                                {/* FREE Parking Promo Section */}
                                <div className="booking-section">
                                  <div className="section-header-with-action">
                                    <h4>FREE Parking Promo</h4>
                                    {!subscriber.unsubscribed && !subscriber.promo_free_used && (
                                      <button
                                        className={`action-btn promo-btn free ${subscriber.promo_free_sent ? 'sent' : 'disabled'}`}
                                        onClick={(e) => { e.stopPropagation(); if (!subscriber.promo_free_sent) alert('This promo has ended.'); }}
                                        disabled={subscriber.promo_free_sent}
                                      >
                                        {subscriber.promo_free_sent ? 'Sent ✓' : 'Send FREE'}
                                      </button>
                                    )}
                                    {/* Send Reminder button - only show if promo sent, not used, and reminder not already sent */}
                                    {subscriber.promo_free_sent && !subscriber.promo_free_used && !subscriber.unsubscribed && (
                                      <button
                                        className={`action-btn promo-btn ${subscriber.promo_free_reminder_sent ? 'sent' : ''}`}
                                        onClick={(e) => { e.stopPropagation(); if (!subscriber.promo_free_reminder_sent) sendPromoFreeReminder(subscriber); }}
                                        disabled={subscriber.promo_free_reminder_sent}
                                      >
                                        {subscriber.promo_free_reminder_sent ? 'Reminder Sent ✓' : 'Send Reminder'}
                                      </button>
                                    )}
                                  </div>
                                  <div className="booking-section-content">
                                    {subscriber.promo_free_code ? (
                                    <>
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
                                            {formatDateTimeUK(subscriber.promo_free_sent_at)}
                                          </span>
                                        </div>
                                      </div>
                                      {/* Reminder Row - aligned under Status and Sent At */}
                                      {subscriber.promo_free_reminder_sent && (
                                        <div className="booking-detail-row" style={{ marginTop: '8px' }}>
                                          <div className="booking-detail">
                                            {/* Empty spacer to align with Code column */}
                                          </div>
                                          <div className="booking-detail">
                                            <span className="detail-label">Reminder</span>
                                            <span className="detail-value">
                                              <span className="status-badge sent">Sent</span>
                                            </span>
                                          </div>
                                          <div className="booking-detail">
                                            <span className="detail-label">Reminder Sent At</span>
                                            <span className="detail-value">
                                              {formatDateTimeUK(subscriber.promo_free_reminder_sent_at)}
                                            </span>
                                          </div>
                                        </div>
                                      )}
                                    </>
                                    ) : (
                                      <p className="section-empty">Not sent yet</p>
                                    )}
                                  </div>
                                </div>

                                {/* Founder Thank You Email Section */}
                                <div className="booking-section">
                                  <div className="section-header-with-action">
                                    <h4>Founder Thank You Email</h4>
                                    {!subscriber.unsubscribed && !subscriber.founder_promo_used && (
                                      <button
                                        className={`action-btn promo-btn founder ${subscriber.founder_email_sent ? 'sent' : ''}`}
                                        onClick={(e) => { e.stopPropagation(); if (!subscriber.founder_email_sent) openFounderEmailModal(subscriber); }}
                                        disabled={subscriber.founder_email_sent}
                                      >
                                        {subscriber.founder_email_sent ? 'Sent ✓' : 'Send Founder Email'}
                                      </button>
                                    )}
                                  </div>
                                  <div className="booking-section-content">
                                    {subscriber.founder_promo_code ? (
                                      <div className="booking-detail-row">
                                        <div className="booking-detail">
                                          <span className="detail-label">Code</span>
                                          <span className="detail-value">
                                            <span className="promo-code-display">{subscriber.founder_promo_code}</span>
                                          </span>
                                        </div>
                                        <div className="booking-detail">
                                          <span className="detail-label">Status</span>
                                          <span className="detail-value">
                                            <span className={`status-badge ${subscriber.founder_promo_used ? 'used' : 'sent'}`}>
                                              {subscriber.founder_promo_used ? 'Used' : 'Sent'}
                                            </span>
                                          </span>
                                        </div>
                                        <div className="booking-detail">
                                          <span className="detail-label">Sent At</span>
                                          <span className="detail-value">
                                            {formatDateTimeUK(subscriber.founder_email_sent_at)}
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
                                    Unsubscribed on {formatDateUK(subscriber.unsubscribed_at)}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })
            })()}
              </>
            )}

            {/* Promotions Sub-tab */}
            {marketingSubTab === 'promotions' && (
              <div className="promotions-section">
                <div className="admin-section-header">
                  <h2>Promotions</h2>
                  <div className="flights-header-actions">
                    <button
                      className="btn-secondary"
                      onClick={refreshPromotions}
                      disabled={loadingPromotions}
                    >
                      {loadingPromotions ? 'Loading...' : '↻ Refresh'}
                    </button>
                    <button
                      className="btn-primary"
                      onClick={() => setShowCreatePromotion(true)}
                    >
                      + New Promotion
                    </button>
                  </div>
                </div>

                {/* Create Promotion Form */}
                {showCreatePromotion && (
                  <div className="create-promotion-form" style={{ background: '#f5f5f5', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
                    <h3>Create New Promotion</h3>
                    <div className="form-row" style={{ display: 'flex', gap: '15px', flexWrap: 'wrap', marginBottom: '15px' }}>
                      <div className="form-group" style={{ flex: '2', minWidth: '200px' }}>
                        <label>Promotion Name</label>
                        <input
                          type="text"
                          value={newPromotion.name}
                          onChange={(e) => setNewPromotion(prev => ({ ...prev, name: e.target.value }))}
                          placeholder="e.g., Spring Sale 2026"
                          className="admin-input"
                        />
                      </div>
                      <div className="form-group" style={{ flex: '1', minWidth: '120px' }}>
                        <label>Discount %</label>
                        <select
                          value={newPromotion.discount_percent}
                          onChange={(e) => setNewPromotion(prev => ({ ...prev, discount_percent: parseInt(e.target.value) }))}
                          className="admin-select"
                        >
                          <option value={10}>10%</option>
                          <option value={15}>15%</option>
                          <option value={20}>20%</option>
                          <option value={25}>25%</option>
                          <option value={50}>50%</option>
                          <option value={100}>100% (Free)</option>
                        </select>
                      </div>
                      <div className="form-group" style={{ flex: '1', minWidth: '120px' }}>
                        <label>Number of Codes</label>
                        <input
                          type="number"
                          value={newPromotion.total_codes}
                          onChange={(e) => setNewPromotion(prev => ({ ...prev, total_codes: parseInt(e.target.value) || 1 }))}
                          min="1"
                          max="1000"
                          className="admin-input"
                        />
                      </div>
                    </div>
                    <div className="form-row" style={{ display: 'flex', gap: '15px', flexWrap: 'wrap', marginBottom: '15px' }}>
                      <div className="form-group" style={{ flex: '1', minWidth: '200px' }}>
                        <label>Code Prefix (optional)</label>
                        <input
                          type="text"
                          value={newPromotion.code_prefix}
                          onChange={(e) => setNewPromotion(prev => ({ ...prev, code_prefix: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 10) }))}
                          placeholder="e.g., SPRING"
                          className="admin-input"
                          maxLength="10"
                        />
                        <small style={{ color: '#666', fontSize: '12px' }}>
                          Codes will be: {newPromotion.code_prefix || 'TAG'}-XXXX-XXXX
                        </small>
                      </div>
                    </div>
                    <div className="form-group" style={{ marginBottom: '15px' }}>
                      <label>Description (optional)</label>
                      <textarea
                        value={newPromotion.description}
                        onChange={(e) => setNewPromotion(prev => ({ ...prev, description: e.target.value }))}
                        placeholder="Internal notes about this promotion"
                        className="admin-input"
                        rows="2"
                        style={{ width: '100%', resize: 'vertical' }}
                      />
                    </div>
                    <div className="form-actions" style={{ display: 'flex', gap: '10px' }}>
                      <button
                        className="btn-secondary"
                        onClick={() => { setShowCreatePromotion(false); setNewPromotion({ name: '', description: '', discount_percent: 10, total_codes: 10, code_prefix: '' }); }}
                      >
                        Cancel
                      </button>
                      <button
                        className="btn-primary"
                        onClick={createPromotion}
                        disabled={creatingPromotion || !newPromotion.name || !newPromotion.total_codes}
                      >
                        {creatingPromotion ? 'Creating...' : 'Create Promotion'}
                      </button>
                    </div>
                  </div>
                )}

                {/* Promotions List */}
                {loadingPromotions ? (
                  <div className="loading-spinner">
                    <span>Loading promotions...</span>
                  </div>
                ) : promotions.length === 0 ? (
                  <div className="no-data">
                    <p>No promotions yet. Create your first promotion to generate promo codes.</p>
                  </div>
                ) : (
                  <div className="promotions-list">
                    {promotions.map(promo => (
                      <div key={promo.id} className="promotion-card" style={{ border: '1px solid #ddd', borderRadius: '8px', marginBottom: '15px', overflow: 'hidden' }}>
                        <div
                          className="promotion-header"
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            padding: '15px 20px',
                            background: '#f9f9f9',
                            cursor: 'pointer',
                          }}
                          onClick={() => {
                            if (expandedPromotionId === promo.id) {
                              setExpandedPromotionId(null)
                            } else {
                              setExpandedPromotionId(promo.id)
                              if (!promotionDetails[promo.id]) {
                                fetchPromotionDetails(promo.id)
                              }
                            }
                          }}
                        >
                          <div className="promotion-info">
                            {editingPromotion?.id === promo.id ? (
                              <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '5px' }} onClick={(e) => e.stopPropagation()}>
                                <input
                                  type="text"
                                  value={editingPromotion.name}
                                  onChange={(e) => setEditingPromotion({ ...editingPromotion, name: e.target.value })}
                                  style={{ padding: '5px 10px', fontSize: '16px', fontWeight: 'bold', border: '1px solid #ccc', borderRadius: '4px' }}
                                  autoFocus
                                />
                                <button
                                  className="btn-primary"
                                  onClick={() => updatePromotion(promo.id, editingPromotion.name)}
                                  style={{ fontSize: '12px', padding: '5px 10px' }}
                                >
                                  Save
                                </button>
                                <button
                                  className="btn-secondary"
                                  onClick={() => setEditingPromotion(null)}
                                  style={{ fontSize: '12px', padding: '5px 10px' }}
                                >
                                  Cancel
                                </button>
                              </div>
                            ) : (
                              <h3 style={{ margin: 0, marginBottom: '5px' }}>{promo.name}</h3>
                            )}
                            <div style={{ display: 'flex', gap: '15px', fontSize: '14px', color: '#666' }}>
                              <span><strong>{promo.discount_percent}%</strong> off</span>
                              <span>|</span>
                              <span>{promo.total_codes} codes</span>
                              <span>|</span>
                              <span>{promo.codes_sent} sent</span>
                              <span>|</span>
                              <span>{promo.codes_used} used</span>
                              <span>|</span>
                              <span style={{ color: promo.codes_available > 0 ? '#28a745' : '#dc3545' }}>
                                {promo.codes_available} available
                              </span>
                            </div>
                          </div>
                          <div className="promotion-actions" style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                            <button
                              className="btn-secondary"
                              onClick={(e) => { e.stopPropagation(); setEditingPromotion({ id: promo.id, name: promo.name }); }}
                              style={{ fontSize: '12px', padding: '6px 12px' }}
                              title="Edit promotion name"
                            >
                              ✏️
                            </button>
                            <button
                              className="btn-secondary"
                              onClick={(e) => { e.stopPropagation(); deletePromotion(promo.id); }}
                              disabled={promo.codes_sent > 0 || promo.codes_used > 0 || promo.codes_shared_on_socials > 0 || promo.codes_shared_privately > 0 || deletingPromotionId === promo.id}
                              style={{ fontSize: '12px', padding: '6px 12px', opacity: (promo.codes_sent > 0 || promo.codes_used > 0 || promo.codes_shared_on_socials > 0 || promo.codes_shared_privately > 0) ? 0.5 : 1 }}
                              title={
                                promo.codes_sent > 0 ? 'Cannot delete - emails have been sent' :
                                promo.codes_used > 0 ? 'Cannot delete - codes have been used' :
                                promo.codes_shared_on_socials > 0 ? 'Cannot delete - codes have been shared on socials' :
                                promo.codes_shared_privately > 0 ? 'Cannot delete - codes have been shared privately' :
                                'Delete promotion'
                              }
                            >
                              {deletingPromotionId === promo.id ? '...' : '🗑️'}
                            </button>
                            <button
                              className="btn-primary"
                              onClick={(e) => { e.stopPropagation(); openSendPromoEmailModal(promo); }}
                              disabled={promo.codes_available === 0}
                              style={{ fontSize: '14px', padding: '8px 15px' }}
                            >
                              📧 Send Codes
                            </button>
                            {promo.codes_available === 0 && (
                              <button
                                className="btn-secondary"
                                onClick={(e) => { e.stopPropagation(); openGenerateCodesModal(promo); }}
                                style={{ fontSize: '14px', padding: '8px 15px' }}
                                title="Generate more promo codes for this promotion"
                              >
                                + Generate Codes
                              </button>
                            )}
                            <span style={{ fontSize: '20px', color: '#666' }}>
                              {expandedPromotionId === promo.id ? '▼' : '▶'}
                            </span>
                          </div>
                        </div>

                        {/* Expanded Details */}
                        {expandedPromotionId === promo.id && (
                          <div className="promotion-details" style={{ padding: '20px', borderTop: '1px solid #eee' }}>
                            {promo.description && (
                              <p style={{ color: '#666', marginBottom: '15px', fontStyle: 'italic' }}>{promo.description}</p>
                            )}
                            <p style={{ fontSize: '12px', color: '#999', marginBottom: '15px' }}>
                              Created: {new Date(promo.created_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London' })}
                            </p>

                            {promotionDetails[promo.id]?.loading ? (
                              <div className="loading-spinner"><span>Loading codes...</span></div>
                            ) : promotionDetails[promo.id]?.codes?.length > 0 ? (
                              <div className="promo-codes-table" style={{ overflowX: 'auto' }}>
                                <table className="admin-table" style={{ width: '100%', fontSize: '13px' }}>
                                  <thead>
                                    <tr>
                                      <th>Code</th>
                                      <th>Recipient</th>
                                      <th>Shared on Socials</th>
                                      <th>Shared Privately</th>
                                      <th>Status</th>
                                      <th>Booking</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {promotionDetails[promo.id].codes.map(code => (
                                      <tr key={code.id}>
                                        <td><code style={{ background: '#f0f0f0', padding: '2px 6px', borderRadius: '3px' }}>{code.code}</code></td>
                                        <td>
                                          {/* Recipient: show email if sent, Social Media badge if shared on socials, Private badge if shared privately, otherwise blank */}
                                          {code.recipient_email ? (
                                            <span>
                                              {code.recipient_first_name} {code.recipient_last_name || ''}<br />
                                              <small style={{ color: '#666' }}>{code.recipient_email}</small>
                                            </span>
                                          ) : code.shared_on_socials ? (
                                            <span style={{
                                              display: 'inline-flex',
                                              alignItems: 'center',
                                              gap: '6px',
                                              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                                              color: 'white',
                                              padding: '4px 10px',
                                              borderRadius: '12px',
                                              fontSize: '11px',
                                              fontWeight: '600'
                                            }}>
                                              <span style={{ fontSize: '13px' }}>📱</span> Social Media
                                            </span>
                                          ) : code.shared_privately ? (
                                            <span style={{
                                              display: 'inline-flex',
                                              alignItems: 'center',
                                              gap: '6px',
                                              background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
                                              color: 'white',
                                              padding: '4px 10px',
                                              borderRadius: '12px',
                                              fontSize: '11px',
                                              fontWeight: '600'
                                            }}>
                                              <span style={{ fontSize: '13px' }}>💬</span> Private Share
                                            </span>
                                          ) : (
                                            <span style={{ color: '#999' }}>-</span>
                                          )}
                                        </td>
                                        <td>
                                          {/* Shared on Socials: toggle button for social codes, dash for emailed/privately shared codes */}
                                          {code.recipient_email ? (
                                            <span style={{ color: '#999' }}>-</span>
                                          ) : code.shared_privately && !code.shared_on_socials ? (
                                            /* Cannot share on socials if already shared privately (mutually exclusive) */
                                            <span style={{ color: '#999' }}>-</span>
                                          ) : code.is_used && !code.shared_on_socials ? (
                                            /* Used codes cannot be marked as shared (but can show shared status if already was) */
                                            <span style={{ color: '#999' }}>-</span>
                                          ) : (
                                            <button
                                              onClick={() => toggleSharedOnSocials(promo.id, code.id)}
                                              disabled={code.is_used && !code.shared_on_socials}
                                              style={{
                                                display: 'inline-flex',
                                                alignItems: 'center',
                                                gap: '6px',
                                                padding: '4px 10px',
                                                borderRadius: '12px',
                                                fontSize: '11px',
                                                fontWeight: '600',
                                                border: 'none',
                                                cursor: code.is_used && !code.shared_on_socials ? 'not-allowed' : 'pointer',
                                                background: code.shared_on_socials
                                                  ? 'linear-gradient(135deg, #28a745 0%, #20c997 100%)'
                                                  : '#e9ecef',
                                                color: code.shared_on_socials ? 'white' : '#666',
                                                opacity: code.is_used && !code.shared_on_socials ? 0.5 : 1,
                                                transition: 'all 0.2s ease'
                                              }}
                                              title={code.shared_on_socials
                                                ? `Shared on ${new Date(code.shared_on_socials_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London' })}`
                                                : code.is_used ? 'Cannot mark used code as shared' : 'Click to mark as shared on socials'
                                              }
                                            >
                                              {code.shared_on_socials ? '✓ Shared' : 'Mark Shared'}
                                            </button>
                                          )}
                                        </td>
                                        <td>
                                          {/* Shared Privately: toggle button for private sharing, dash for emailed/socially shared codes */}
                                          {code.recipient_email ? (
                                            <span style={{ color: '#999' }}>-</span>
                                          ) : code.shared_on_socials && !code.shared_privately ? (
                                            /* Cannot share privately if already shared on socials (mutually exclusive) */
                                            <span style={{ color: '#999' }}>-</span>
                                          ) : code.is_used && !code.shared_privately ? (
                                            /* Used codes cannot be marked as shared (but can show shared status if already was) */
                                            <span style={{ color: '#999' }}>-</span>
                                          ) : (
                                            <button
                                              onClick={() => toggleSharedPrivately(promo.id, code.id)}
                                              disabled={code.is_used && !code.shared_privately}
                                              style={{
                                                display: 'inline-flex',
                                                alignItems: 'center',
                                                gap: '6px',
                                                padding: '4px 10px',
                                                borderRadius: '12px',
                                                fontSize: '11px',
                                                fontWeight: '600',
                                                border: 'none',
                                                cursor: code.is_used && !code.shared_privately ? 'not-allowed' : 'pointer',
                                                background: code.shared_privately
                                                  ? 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)'
                                                  : '#e9ecef',
                                                color: code.shared_privately ? 'white' : '#666',
                                                opacity: code.is_used && !code.shared_privately ? 0.5 : 1,
                                                transition: 'all 0.2s ease'
                                              }}
                                              title={code.shared_privately
                                                ? `Shared on ${new Date(code.shared_privately_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London' })}`
                                                : code.is_used ? 'Cannot mark used code as shared' : 'Click to mark as shared privately'
                                              }
                                            >
                                              {code.shared_privately ? '✓ Shared' : 'Mark Shared'}
                                            </button>
                                          )}
                                        </td>
                                        <td>
                                          <span className={`status-badge ${code.is_used ? 'used' : (code.email_sent || code.shared_on_socials || code.shared_privately) ? 'sent' : 'pending'}`}>
                                            {code.is_used ? 'Used' : (code.email_sent || code.shared_on_socials || code.shared_privately) ? 'Shared' : 'Available'}
                                          </span>
                                        </td>
                                        <td>
                                          {code.booking_reference ? (
                                            <code style={{ background: '#f0f0f0', padding: '2px 6px', borderRadius: '3px' }}>{code.booking_reference}</code>
                                          ) : (
                                            <span style={{ color: '#999' }}>-</span>
                                          )}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            ) : (
                              <p style={{ color: '#666' }}>No codes to display.</p>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Sources Sub-tab (Marketing Sources) */}
            {marketingSubTab === 'sources' && (
              <div className="marketing-sources-section">
                <div className="admin-section-header">
                  <h2>Marketing Sources</h2>
                  <div className="flights-header-actions">
                    <button
                      className="btn-secondary"
                      onClick={fetchMarketingSources}
                      disabled={loadingMarketingSources}
                    >
                      ↻ Refresh
                    </button>
                    <button
                      className="btn-primary"
                      onClick={exportMarketingSourcesCSV}
                    >
                      ↓ Download CSV
                    </button>
                  </div>
                </div>
                <p className="admin-subtitle">
                  Where customers heard about TAG Parking (based on Page 4 attribution question)
                </p>

                <div className="flights-filters">
                  <div className="flight-filter-group leads-date-picker">
                    <label>From:</label>
                    <DatePicker
                      selected={marketingExportFromDate}
                      onChange={(date) => setMarketingExportFromDate(date)}
                      dateFormat="dd/MM/yyyy"
                      placeholderText="DD/MM/YYYY"
                      className="flight-date-input"
                      isClearable
                    />
                  </div>
                  <div className="flight-filter-group leads-date-picker">
                    <label>To:</label>
                    <DatePicker
                      selected={marketingExportToDate}
                      onChange={(date) => setMarketingExportToDate(date)}
                      dateFormat="dd/MM/yyyy"
                      placeholderText="DD/MM/YYYY"
                      className="flight-date-input"
                      isClearable
                    />
                  </div>
                  {(marketingExportFromDate || marketingExportToDate) && (
                    <button
                      className="btn-secondary clear-dates-btn"
                      onClick={() => { setMarketingExportFromDate(null); setMarketingExportToDate(null); }}
                    >
                      × Clear
                    </button>
                  )}
                  {marketingSourcesData && (
                    <div className="leads-filter-count">
                      Showing {marketingSourcesData.total_responses} responses
                    </div>
                  )}
                </div>

                {loadingMarketingSources ? (
                  <div className="admin-loading-inline">
                    <div className="spinner-small"></div>
                    <span>Loading marketing sources...</span>
                  </div>
                ) : marketingSourcesData ? (
                  <>
                    {/* Total Summary */}
                    <div className="marketing-total-summary">
                      <div className="stats-card">
                        <div className="stats-card-value">{marketingSourcesData.total_responses}</div>
                        <div className="stats-card-label">Total Responses</div>
                      </div>
                    </div>

                    {/* Monthly Breakdown */}
                    <h4>Monthly Breakdown</h4>
                    {marketingSourcesData.monthly_data && marketingSourcesData.monthly_data.length > 0 ? (
                      <div className="marketing-monthly-table">
                        <table className="admin-table">
                          <thead>
                            <tr>
                              <th>Month</th>
                              {[
                                { key: 'google', label: 'Google' },
                                { key: 'facebook', label: 'Facebook' },
                                { key: 'instagram', label: 'Instagram' },
                                { key: 'word_of_mouth', label: 'Word of Mouth' },
                                { key: 'leaflet', label: 'Leaflet' },
                                { key: 'tv', label: 'TV' },
                                { key: 'radio', label: 'Radio' },
                                { key: 'newspaper', label: 'Newspaper' },
                                { key: 'linkedin', label: 'LinkedIn' },
                                { key: 'afc_bournemouth', label: 'AFC Bournemouth' },
                                { key: 'other', label: 'Other' }
                              ].map(source => (
                                <th key={source.key}>{source.label}</th>
                              ))}
                              <th>Total</th>
                            </tr>
                          </thead>
                          <tbody>
                            {marketingSourcesData.monthly_data.map((month, idx) => {
                              const total = Object.values(month.sources).reduce((a, b) => a + b, 0)
                              return (
                                <tr key={idx}>
                                  <td>{month.year_month.split('-').reverse().join('/')}</td>
                                  {['google', 'facebook', 'instagram', 'word_of_mouth', 'leaflet', 'tv', 'radio', 'newspaper', 'linkedin', 'afc_bournemouth', 'other'].map(source => (
                                    <td key={source}>
                                      {month.sources[source] || 0}
                                      {source === 'other' && month.sources.other > 0 && (
                                        <button
                                          className="view-other-details"
                                          onClick={() => fetchMarketingOtherDetails(month.year_month)}
                                          title={`View 'Other' details for ${month.year_month}`}
                                        >
                                          ?
                                        </button>
                                      )}
                                    </td>
                                  ))}
                                  <td><strong>{total}</strong></td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className="no-data">No marketing source data yet.</p>
                    )}

                    {/* Source Totals */}
                    <h4>All-Time Totals by Source</h4>
                    <div className="marketing-source-totals">
                      {marketingSourcesData.source_totals && Object.entries(marketingSourcesData.source_totals)
                        .sort(([, a], [, b]) => b - a)
                        .map(([source, count]) => {
                          const sourceLabels = {
                            google: 'Google',
                            facebook: 'Facebook',
                            instagram: 'Instagram',
                            word_of_mouth: 'Word of Mouth',
                            leaflet: 'Leaflet',
                            tv: 'TV',
                            radio: 'Radio',
                            newspaper: 'Newspaper',
                            linkedin: 'LinkedIn',
                            afc_bournemouth: 'AFC Bournemouth',
                            other: 'Other'
                          }
                          const percentage = marketingSourcesData.total_responses > 0
                            ? ((count / marketingSourcesData.total_responses) * 100).toFixed(1)
                            : 0
                          return (
                            <div key={source} className="source-total-item">
                              <span className="source-name">{sourceLabels[source] || source}</span>
                              <span className="source-count">{count}</span>
                              <span className="source-percentage">{percentage}%</span>
                              <div className="source-bar" style={{ width: `${percentage}%` }}></div>
                            </div>
                          )
                        })}
                    </div>

                    {/* Percentage Breakdown */}
                    <h4>Percentage Breakdown</h4>
                    <div className="marketing-percentage-grid">
                      {marketingSourcesData.source_totals && Object.entries(marketingSourcesData.source_totals)
                        .sort(([, a], [, b]) => b - a)
                        .map(([source, count]) => {
                          const sourceLabels = {
                            google: 'Google',
                            facebook: 'Facebook',
                            instagram: 'Instagram',
                            word_of_mouth: 'Word of Mouth',
                            leaflet: 'Leaflet',
                            tv: 'TV',
                            radio: 'Radio',
                            newspaper: 'Newspaper',
                            linkedin: 'LinkedIn',
                            afc_bournemouth: 'AFC Bournemouth',
                            other: 'Other'
                          }
                          const percentage = marketingSourcesData.total_responses > 0
                            ? ((count / marketingSourcesData.total_responses) * 100).toFixed(1)
                            : 0
                          return (
                            <div key={source} className="percentage-card">
                              <div className="percentage-value">{percentage}%</div>
                              <div className="percentage-label">{sourceLabels[source] || source}</div>
                              <div className="percentage-count">{count} response{count !== 1 ? 's' : ''}</div>
                            </div>
                          )
                        })}
                    </div>
                  </>
                ) : (
                  <p className="no-data">No marketing source data available.</p>
                )}
              </div>
            )}

            {/* Marketing "Other" Details Modal */}
            {showMarketingOtherModal && (
              <div className="modal-overlay" onClick={() => setShowMarketingOtherModal(false)}>
                <div className="modal-content marketing-other-modal" onClick={(e) => e.stopPropagation()}>
                  <div className="modal-header">
                    <h3>"Other" Source Details {marketingOtherMonth && `- ${(() => {
                        const [year, month] = marketingOtherMonth.split('-')
                        return new Date(year, month - 1, 15).toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
                      })()}`}</h3>
                    <button className="modal-close" onClick={() => setShowMarketingOtherModal(false)}>&times;</button>
                  </div>
                  <div className="modal-body marketing-other-modal-body">
                    {loadingMarketingOther ? (
                      <div className="admin-loading-inline">
                        <div className="spinner-small"></div>
                        <span>Loading...</span>
                      </div>
                    ) : marketingOtherDetails && marketingOtherDetails.length > 0 ? (
                      <table className="admin-table">
                        <thead>
                          <tr>
                            <th>Customer</th>
                            <th>Detail</th>
                            <th>Date</th>
                          </tr>
                        </thead>
                        <tbody>
                          {marketingOtherDetails.map((item, idx) => (
                            <tr key={idx}>
                              <td>{item.customer_name || item.customer_email}</td>
                              <td>{item.source_detail}</td>
                              <td>{new Date(item.created_at).toLocaleDateString('en-GB')}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <p>No "Other" details recorded.</p>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Generate More Codes Modal */}
            {showGenerateCodesModal && generateCodesPromotion && (
              <div className="modal-overlay" onClick={() => setShowGenerateCodesModal(false)}>
                <div className="modal-content" style={{ maxWidth: '400px' }} onClick={(e) => e.stopPropagation()}>
                  <div className="modal-header">
                    <h3>Generate More Codes</h3>
                    <button className="modal-close" onClick={() => setShowGenerateCodesModal(false)}>&times;</button>
                  </div>
                  <div className="modal-body">
                    <p style={{ marginBottom: '15px', color: '#666' }}>
                      Add more codes to <strong>{generateCodesPromotion.name}</strong>
                    </p>
                    <p style={{ marginBottom: '15px', fontSize: '14px', color: '#999' }}>
                      Current: {generateCodesPromotion.total_codes} codes ({generateCodesPromotion.codes_available} available)
                    </p>
                    <div className="form-group">
                      <label>Number of codes to generate</label>
                      <input
                        type="number"
                        value={generateCodesCount}
                        onChange={(e) => setGenerateCodesCount(Math.max(1, Math.min(1000, parseInt(e.target.value) || 1)))}
                        min="1"
                        max="1000"
                        className="admin-input"
                        style={{ width: '100%' }}
                      />
                    </div>
                  </div>
                  <div className="modal-actions">
                    <button
                      className="modal-btn modal-btn-secondary"
                      onClick={() => setShowGenerateCodesModal(false)}
                    >
                      Cancel
                    </button>
                    <button
                      className="modal-btn modal-btn-primary"
                      onClick={generateMoreCodes}
                      disabled={generatingCodes}
                    >
                      {generatingCodes ? 'Generating...' : `Generate ${generateCodesCount} Codes`}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Send Promo Email Modal */}
            {showSendPromoEmailModal && sendPromoEmailData && (
              <div className="modal-overlay" onClick={() => setShowSendPromoEmailModal(false)}>
                <div className="modal-content" style={{ maxWidth: '700px', maxHeight: '90vh', overflow: 'auto' }} onClick={(e) => e.stopPropagation()}>
                  <div className="modal-header">
                    <h3>Send Promo Emails - {sendPromoEmailData.promotion.name}</h3>
                    <button className="modal-close" onClick={() => setShowSendPromoEmailModal(false)}>&times;</button>
                  </div>
                  <div className="modal-body">
                    <p style={{ marginBottom: '15px', color: '#666' }}>
                      <strong>{sendPromoEmailData.availableCodes.length}</strong> codes available to send
                    </p>

                    {/* Recipient Search */}
                    <div className="form-group" style={{ marginBottom: '20px' }}>
                      <label>Search Customers & Subscribers</label>
                      <input
                        type="text"
                        value={recipientSearchTerm}
                        onChange={(e) => {
                          setRecipientSearchTerm(e.target.value)
                          searchRecipients(e.target.value)
                        }}
                        placeholder="Search by name or email..."
                        className="admin-input"
                        style={{ width: '100%' }}
                      />
                      {searchingRecipients && <small>Searching...</small>}
                      {recipientSearchResults.length > 0 && (
                        <div className="search-results" style={{ border: '1px solid #ddd', borderRadius: '4px', marginTop: '5px', maxHeight: '150px', overflowY: 'auto' }}>
                          {recipientSearchResults.map((r, idx) => (
                            <div
                              key={idx}
                              style={{ padding: '8px 12px', borderBottom: '1px solid #eee', cursor: 'pointer', display: 'flex', justifyContent: 'space-between' }}
                              onClick={() => addRecipient(r)}
                            >
                              <span>{r.first_name} {r.last_name || ''} - {r.email}</span>
                              <small style={{ color: '#666' }}>{r.source}</small>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Manual Entry */}
                    <div className="form-group" style={{ marginBottom: '20px' }}>
                      <label>Or Add Manually (family/friends)</label>
                      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                        <input
                          type="email"
                          value={manualRecipient.email}
                          onChange={(e) => setManualRecipient(prev => ({ ...prev, email: e.target.value }))}
                          placeholder="Email"
                          className="admin-input"
                          style={{ flex: '2', minWidth: '180px' }}
                        />
                        <input
                          type="text"
                          value={manualRecipient.first_name}
                          onChange={(e) => setManualRecipient(prev => ({ ...prev, first_name: e.target.value }))}
                          placeholder="First Name"
                          className="admin-input"
                          style={{ flex: '1', minWidth: '100px' }}
                        />
                        <input
                          type="text"
                          value={manualRecipient.last_name}
                          onChange={(e) => setManualRecipient(prev => ({ ...prev, last_name: e.target.value }))}
                          placeholder="Last Name"
                          className="admin-input"
                          style={{ flex: '1', minWidth: '100px' }}
                        />
                        <button
                          className="btn-secondary"
                          onClick={addManualRecipient}
                          disabled={!manualRecipient.email || !manualRecipient.first_name}
                          style={{ padding: '8px 15px' }}
                        >
                          + Add
                        </button>
                      </div>
                    </div>

                    {/* Selected Recipients */}
                    <div className="form-group" style={{ marginBottom: '20px' }}>
                      <label>Recipients ({promoEmailRecipients.length})</label>
                      {promoEmailRecipients.length === 0 ? (
                        <p style={{ color: '#999', fontStyle: 'italic' }}>No recipients selected</p>
                      ) : (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                          {promoEmailRecipients.map((r, idx) => (
                            <span
                              key={idx}
                              style={{
                                background: '#e9ecef',
                                padding: '5px 10px',
                                borderRadius: '15px',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '8px',
                                fontSize: '13px',
                              }}
                            >
                              {r.first_name} ({r.email})
                              <button
                                onClick={() => removeRecipient(r.email)}
                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc3545', fontWeight: 'bold' }}
                              >
                                ×
                              </button>
                            </span>
                          ))}
                        </div>
                      )}
                      {promoEmailRecipients.length > sendPromoEmailData.availableCodes.length && (
                        <p style={{ color: '#dc3545', marginTop: '10px' }}>
                          ⚠️ More recipients than available codes!
                        </p>
                      )}
                    </div>

                    {/* Email Subject */}
                    <div className="form-group" style={{ marginBottom: '15px' }}>
                      <label>Email Subject</label>
                      <input
                        type="text"
                        value={promoEmailSubject}
                        onChange={(e) => setPromoEmailSubject(e.target.value)}
                        className="admin-input"
                        style={{ width: '100%' }}
                      />
                      <small style={{ color: '#666' }}>Use {'{{FIRST_NAME}}'} for personalization</small>
                    </div>

                    {/* Email Body */}
                    <div className="form-group" style={{ marginBottom: '15px' }}>
                      <label>Email Body (HTML)</label>
                      <textarea
                        value={promoEmailBody}
                        onChange={(e) => setPromoEmailBody(e.target.value)}
                        className="admin-input"
                        rows="10"
                        style={{ width: '100%', fontFamily: 'monospace', fontSize: '12px' }}
                      />
                      <small style={{ color: '#666' }}>
                        Use {'{{FIRST_NAME}}'} and {'{{PROMO_CODE}}'} placeholders
                      </small>
                    </div>
                  </div>
                  <div className="modal-actions">
                    <button className="modal-btn modal-btn-secondary" onClick={() => setShowSendPromoEmailModal(false)}>
                      Cancel
                    </button>
                    <button
                      className="modal-btn modal-btn-primary"
                      onClick={sendPromoEmails}
                      disabled={sendingPromoEmails || promoEmailRecipients.length === 0 || promoEmailRecipients.length > sendPromoEmailData.availableCodes.length}
                    >
                      {sendingPromoEmails ? 'Sending...' : `Send ${promoEmailRecipients.length} Email${promoEmailRecipients.length !== 1 ? 's' : ''}`}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'leads' && (
          <div className="admin-section">
            <div className="admin-section-header">
              <h2>Abandoned Leads</h2>
              <div className="flights-header-actions">
                <button
                  className="btn-secondary"
                  onClick={fetchLeads}
                  disabled={loadingLeads}
                >
                  {loadingLeads ? 'Loading...' : '↻ Refresh'}
                </button>
                <button
                  className="btn-primary"
                  onClick={() => {
                    // Filter leads based on current filters
                    const filteredLeads = leads.filter(lead => {
                      // Date filter (UK time)
                      if (leadDateFrom || leadDateTo) {
                        const leadDate = lead.created_at ? new Date(lead.created_at) : null
                        if (!leadDate) return false
                        if (leadDateFrom) {
                          const fromDate = new Date(leadDateFrom)
                          fromDate.setHours(0, 0, 0, 0)
                          if (leadDate < fromDate) return false
                        }
                        if (leadDateTo) {
                          const toDate = new Date(leadDateTo)
                          toDate.setHours(23, 59, 59, 999)
                          if (leadDate > toDate) return false
                        }
                      }
                      // Search filter
                      if (leadSearchTerm) {
                        const search = leadSearchTerm.toLowerCase()
                        return (
                          lead.first_name?.toLowerCase().includes(search) ||
                          lead.last_name?.toLowerCase().includes(search) ||
                          lead.email?.toLowerCase().includes(search) ||
                          lead.phone?.includes(search)
                        )
                      }
                      return true
                    })
                    // Generate CSV
                    const csvRows = [['Name', 'Phone', 'Email', 'Date Added']]
                    filteredLeads.forEach(lead => {
                      const name = `${lead.first_name || ''} ${lead.last_name || ''}`.trim()
                      const dateAdded = lead.created_at
                        ? new Date(lead.created_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London' })
                        : ''
                      csvRows.push([name, lead.phone || '', lead.email || '', dateAdded])
                    })
                    const csvContent = csvRows.map(row => row.map(cell => `"${(cell || '').replace(/"/g, '""')}"`).join(',')).join('\n')
                    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
                    const url = URL.createObjectURL(blob)
                    const link = document.createElement('a')
                    link.setAttribute('href', url)
                    // Build descriptive filename based on filters (DD-MM-YYYY format)
                    const formatDateForFilename = (date) => {
                      const day = String(date.getDate()).padStart(2, '0')
                      const month = String(date.getMonth() + 1).padStart(2, '0')
                      const year = date.getFullYear()
                      return `${day}-${month}-${year}`
                    }
                    let filename = 'leads'
                    if (leadDateFrom && leadDateTo) {
                      filename = `leads_${formatDateForFilename(leadDateFrom)}_to_${formatDateForFilename(leadDateTo)}`
                    } else if (leadDateFrom) {
                      filename = `leads_from_${formatDateForFilename(leadDateFrom)}`
                    } else if (leadDateTo) {
                      filename = `leads_to_${formatDateForFilename(leadDateTo)}`
                    } else {
                      filename = `leads_all_${formatDateForFilename(new Date())}`
                    }
                    link.setAttribute('download', `${filename}.csv`)
                    link.click()
                    URL.revokeObjectURL(url)
                  }}
                  disabled={loadingLeads}
                >
                  ↓ Download CSV
                </button>
              </div>
            </div>
            <p className="admin-subtitle">Customers who started booking but didn't complete payment</p>

            <div className="flights-filters">
              <div className="flight-filter-group lead-search-group">
                <input
                  type="text"
                  placeholder="Search by name, email, or phone..."
                  value={leadSearchTerm}
                  onChange={(e) => setLeadSearchTerm(e.target.value)}
                  className="flight-number-input lead-search-input"
                />
                {leadSearchTerm && (
                  <button
                    className="lead-search-clear"
                    onClick={() => setLeadSearchTerm('')}
                  >
                    ×
                  </button>
                )}
              </div>
              <div className="flight-filter-group leads-date-picker">
                <label>From:</label>
                <DatePicker
                  selected={leadDateFrom}
                  onChange={(date) => setLeadDateFrom(date)}
                  dateFormat="dd/MM/yyyy"
                  placeholderText="DD/MM/YYYY"
                  className="flight-date-input"
                  isClearable
                />
              </div>
              <div className="flight-filter-group leads-date-picker">
                <label>To:</label>
                <DatePicker
                  selected={leadDateTo}
                  onChange={(date) => setLeadDateTo(date)}
                  dateFormat="dd/MM/yyyy"
                  placeholderText="DD/MM/YYYY"
                  className="flight-date-input"
                  isClearable
                />
              </div>
              {(leadDateFrom || leadDateTo) && (
                <button
                  className="btn-secondary clear-dates-btn"
                  onClick={() => { setLeadDateFrom(null); setLeadDateTo(null); }}
                >
                  × Clear
                </button>
              )}
              <div className="leads-filter-count">
                Showing {leads.filter(lead => {
                  // Date filter (UK time)
                  if (leadDateFrom || leadDateTo) {
                    const leadDate = lead.created_at ? new Date(lead.created_at) : null
                    if (!leadDate) return false
                    if (leadDateFrom) {
                      const fromDate = new Date(leadDateFrom)
                      fromDate.setHours(0, 0, 0, 0)
                      if (leadDate < fromDate) return false
                    }
                    if (leadDateTo) {
                      const toDate = new Date(leadDateTo)
                      toDate.setHours(23, 59, 59, 999)
                      if (leadDate > toDate) return false
                    }
                  }
                  // Search filter
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
                {(() => {
                  // Filter leads first
                  const filteredLeads = leads.filter(lead => {
                    // Date filter (UK time)
                    if (leadDateFrom || leadDateTo) {
                      const leadDate = lead.created_at ? new Date(lead.created_at) : null
                      if (!leadDate) return false
                      if (leadDateFrom) {
                        const fromDate = new Date(leadDateFrom)
                        fromDate.setHours(0, 0, 0, 0)
                        if (leadDate < fromDate) return false
                      }
                      if (leadDateTo) {
                        const toDate = new Date(leadDateTo)
                        toDate.setHours(23, 59, 59, 999)
                        if (leadDate > toDate) return false
                      }
                    }
                    // Search filter
                    if (!leadSearchTerm) return true
                    const search = leadSearchTerm.toLowerCase()
                    return (
                      lead.first_name?.toLowerCase().includes(search) ||
                      lead.last_name?.toLowerCase().includes(search) ||
                      lead.email?.toLowerCase().includes(search) ||
                      lead.phone?.includes(search)
                    )
                  })

                  // Group by month
                  const monthlyGroups = {}
                  filteredLeads.forEach(lead => {
                    const date = lead.created_at ? new Date(lead.created_at) : null
                    if (date) {
                      const monthKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
                      if (!monthlyGroups[monthKey]) monthlyGroups[monthKey] = []
                      monthlyGroups[monthKey].push(lead)
                    }
                  })

                  const sortedMonths = Object.keys(monthlyGroups).sort().reverse()
                  const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

                  if (sortedMonths.length === 0) {
                    return <p className="admin-no-data">No abandoned leads found</p>
                  }

                  return sortedMonths.map(monthKey => {
                    const [year, month] = monthKey.split('-')
                    const monthName = `${monthNames[parseInt(month, 10) - 1]} ${year}`
                    const monthLeads = monthlyGroups[monthKey]
                    const isExpanded = expandedLeadMonths[monthKey]

                    return (
                      <div key={monthKey} className="leads-month-container">
                        <div
                          className="leads-month-header"
                          onClick={() => setExpandedLeadMonths(prev => ({
                            ...prev,
                            [monthKey]: !prev[monthKey]
                          }))}
                        >
                          <span className="expand-icon">{isExpanded ? '▼' : '▶'}</span>
                          <span className="month-name">{monthName}</span>
                          <span className="month-total">{monthLeads.length} lead{monthLeads.length !== 1 ? 's' : ''}</span>
                        </div>
                        {isExpanded && (
                          <div className="leads-month-content">
                            {monthLeads.map(lead => (
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
                                      {lead.created_at ? new Date(lead.created_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London' }) : 'Unknown'}
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
                                              {lead.created_at ? new Date(lead.created_at).toLocaleString('en-GB', { timeZone: 'Europe/London' }) : 'Unknown'}
                                            </span>
                                          </div>
                                          {lead.last_booking_status && (
                                            <div className="booking-detail">
                                              <span className="detail-label">Last Booking Status</span>
                                              <span className="detail-value">{lead.last_booking_status}</span>
                                            </div>
                                          )}
                                          <div className="booking-detail">
                                            <span className="detail-label">Founder Email</span>
                                            <span className="detail-value">
                                              <button
                                                className={`action-btn email-btn ${lead.founder_followup_sent ? 'sent-status' : ''}`}
                                                disabled={true}
                                                title={lead.founder_followup_sent
                                                  ? `Sent on ${lead.founder_followup_sent_at ? new Date(lead.founder_followup_sent_at).toLocaleString('en-GB', { timeZone: 'Europe/London' }) : 'Unknown'}`
                                                  : 'Not sent yet'}
                                              >
                                                {lead.founder_followup_sent ? 'Sent ✓' : 'Not Sent'}
                                              </button>
                                            </span>
                                          </div>
                                        </div>
                                      </div>
                                    </div>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })
                })()}
              </div>
            )}
          </div>
        )}

        {activeTab === 'customers' && (
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
                  onClick={() => {
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
                  }}
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
            ) : (() => {
              // Group by month
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
            })()}
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
                  <h3>Anchor Prices (Early Booking Tier)</h3>
                  <p className="pricing-hint">These are the base prices when customers book 14+ days in advance. Days between anchors use daily increments.</p>

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
                      <label>1 Week (7 Days)</label>
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
                      <label>2 Weeks (14 Days)</label>
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
                  <h3>Daily Increment</h3>
                  <p className="pricing-hint">Added per day for durations between anchors (5-6, 8-13, 15+ days).</p>
                  <div className="pricing-inputs">
                    <div className="pricing-input-group pricing-input-highlight">
                      <label>Daily Increment</label>
                      <div className="price-input-wrapper">
                        <span className="currency-symbol">£</span>
                        <input
                          type="text"
                          inputMode="decimal"
                          value={pricing.daily_increment}
                          onChange={(e) => {
                            const val = e.target.value.replace(/[^0-9.]/g, '')
                            setPricing({ ...pricing, daily_increment: parseFloat(val) || 0 })
                          }}
                        />
                      </div>
                      <span className="pricing-input-hint">per extra day</span>
                    </div>
                  </div>
                </div>

                <div className="admin-pricing-section tier-increment-section">
                  <h3>Tier Increment</h3>
                  <p className="pricing-hint">Added for Standard tier (+1x) and Late tier (+2x) bookings based on advance booking.</p>
                  <div className="pricing-inputs">
                    <div className="pricing-input-group pricing-input-highlight">
                      <label>Tier Increment</label>
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
                        <td>5 Days</td>
                        <td>£{pricing.days_1_4_price + pricing.daily_increment}</td>
                        <td>£{pricing.days_1_4_price + pricing.daily_increment + pricing.tier_increment}</td>
                        <td>£{pricing.days_1_4_price + pricing.daily_increment + (pricing.tier_increment * 2)}</td>
                      </tr>
                      <tr>
                        <td>6 Days</td>
                        <td>£{pricing.days_1_4_price + (pricing.daily_increment * 2)}</td>
                        <td>£{pricing.days_1_4_price + (pricing.daily_increment * 2) + pricing.tier_increment}</td>
                        <td>£{pricing.days_1_4_price + (pricing.daily_increment * 2) + (pricing.tier_increment * 2)}</td>
                      </tr>
                      <tr>
                        <td>7 Days (1 Week)</td>
                        <td>£{pricing.week1_base_price}</td>
                        <td>£{pricing.week1_base_price + pricing.tier_increment}</td>
                        <td>£{pricing.week1_base_price + (pricing.tier_increment * 2)}</td>
                      </tr>
                      <tr>
                        <td>8 Days</td>
                        <td>£{pricing.week1_base_price + pricing.daily_increment}</td>
                        <td>£{pricing.week1_base_price + pricing.daily_increment + pricing.tier_increment}</td>
                        <td>£{pricing.week1_base_price + pricing.daily_increment + (pricing.tier_increment * 2)}</td>
                      </tr>
                      <tr>
                        <td>9 Days</td>
                        <td>£{pricing.week1_base_price + (pricing.daily_increment * 2)}</td>
                        <td>£{pricing.week1_base_price + (pricing.daily_increment * 2) + pricing.tier_increment}</td>
                        <td>£{pricing.week1_base_price + (pricing.daily_increment * 2) + (pricing.tier_increment * 2)}</td>
                      </tr>
                      <tr>
                        <td>10 Days</td>
                        <td>£{pricing.week1_base_price + (pricing.daily_increment * 3)}</td>
                        <td>£{pricing.week1_base_price + (pricing.daily_increment * 3) + pricing.tier_increment}</td>
                        <td>£{pricing.week1_base_price + (pricing.daily_increment * 3) + (pricing.tier_increment * 2)}</td>
                      </tr>
                      <tr>
                        <td>11 Days</td>
                        <td>£{pricing.week1_base_price + (pricing.daily_increment * 4)}</td>
                        <td>£{pricing.week1_base_price + (pricing.daily_increment * 4) + pricing.tier_increment}</td>
                        <td>£{pricing.week1_base_price + (pricing.daily_increment * 4) + (pricing.tier_increment * 2)}</td>
                      </tr>
                      <tr>
                        <td>12 Days</td>
                        <td>£{pricing.week1_base_price + (pricing.daily_increment * 5)}</td>
                        <td>£{pricing.week1_base_price + (pricing.daily_increment * 5) + pricing.tier_increment}</td>
                        <td>£{pricing.week1_base_price + (pricing.daily_increment * 5) + (pricing.tier_increment * 2)}</td>
                      </tr>
                      <tr>
                        <td>13 Days</td>
                        <td>£{pricing.week1_base_price + (pricing.daily_increment * 6)}</td>
                        <td>£{pricing.week1_base_price + (pricing.daily_increment * 6) + pricing.tier_increment}</td>
                        <td>£{pricing.week1_base_price + (pricing.daily_increment * 6) + (pricing.tier_increment * 2)}</td>
                      </tr>
                      <tr>
                        <td>14 Days (2 Weeks)</td>
                        <td>£{pricing.week2_base_price}</td>
                        <td>£{pricing.week2_base_price + pricing.tier_increment}</td>
                        <td>£{pricing.week2_base_price + (pricing.tier_increment * 2)}</td>
                      </tr>
                      <tr>
                        <td>15 Days</td>
                        <td>£{pricing.week2_base_price + pricing.daily_increment}</td>
                        <td>£{pricing.week2_base_price + pricing.daily_increment + pricing.tier_increment}</td>
                        <td>£{pricing.week2_base_price + pricing.daily_increment + (pricing.tier_increment * 2)}</td>
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

            {/* Reports Sub-Tabs */}
            <div className="reports-subtabs">
              <button
                className={`reports-subtab ${reportsSubTab === 'growth' ? 'active' : ''}`}
                onClick={() => setReportsSubTab('growth')}
              >
                Booking Growth
              </button>
              <button
                className={`reports-subtab ${reportsSubTab === 'occupancy' ? 'active' : ''}`}
                onClick={() => setReportsSubTab('occupancy')}
              >
                Occupancy
              </button>
              <button
                className={`reports-subtab ${reportsSubTab === 'popular' ? 'active' : ''}`}
                onClick={() => setReportsSubTab('popular')}
              >
                Popular Routes
              </button>
              <button
                className={`reports-subtab ${reportsSubTab === 'map' ? 'active' : ''}`}
                onClick={() => setReportsSubTab('map')}
              >
                Location Maps
              </button>
            </div>

            {/* Booking Growth Charts */}
            {reportsSubTab === 'growth' && (
              <div className="booking-stats-section">
                {loadingStats ? (
                  <div className="admin-loading-inline">
                    <div className="spinner-small"></div>
                    <span>Loading booking statistics...</span>
                  </div>
                ) : bookingStats ? (
                  <>
                    {/* Section Header with Refresh */}
                    <div className="reports-section-header">
                      <button
                        className="refresh-page-btn"
                        onClick={() => { fetchBookingStats(); fetchFunFacts(); }}
                        disabled={loadingStats || loadingFunFacts}
                      >
                        {loadingStats || loadingFunFacts ? 'Refreshing...' : 'Refresh Page'}
                      </button>
                    </div>

                    {/* Summary Cards */}
                    <div className="stats-summary-cards">
                      <div className="stats-card">
                        <div className="stats-card-value">{bookingStats.total_successful}</div>
                        <div className="stats-card-label">Total Successful Bookings</div>
                      </div>
                      <div className="stats-card">
                        <div className="stats-card-value">{bookingStats.this_month}</div>
                        <div className="stats-card-label">This Month</div>
                        {bookingStats.last_month > 0 && (
                          <div className={`stats-card-change ${bookingStats.this_month >= bookingStats.last_month ? 'positive' : 'negative'}`}>
                            {bookingStats.this_month >= bookingStats.last_month ? '+' : ''}{bookingStats.this_month - bookingStats.last_month} vs last month
                          </div>
                        )}
                      </div>
                      <div className="stats-card">
                        <div className="stats-card-value">{bookingStats.this_week}</div>
                        <div className="stats-card-label">This Week</div>
                        {bookingStats.last_week > 0 && (
                          <div className={`stats-card-change ${bookingStats.this_week >= bookingStats.last_week ? 'positive' : 'negative'}`}>
                            {bookingStats.this_week >= bookingStats.last_week ? '+' : ''}{bookingStats.this_week - bookingStats.last_week} vs last week
                          </div>
                        )}
                      </div>
                      <div className="stats-card revenue-card">
                        <div className="stats-card-value">&pound;{bookingStats.avg_revenue_per_customer?.toFixed(2) || '0.00'}</div>
                        <div className="stats-card-label">Avg Revenue per Customer</div>
                        <div className="stats-card-subtext">
                          &pound;{bookingStats.total_revenue?.toFixed(2) || '0.00'} total from {bookingStats.paid_customer_count || 0} paid bookings
                        </div>
                      </div>
                    </div>

                    {/* Trip Insights */}
                    <div className="trip-insights-section">
                      <h3>Trip Insights</h3>
                      <div className="trip-insights-grid">
                        <div className="trip-insight-card">
                          <span className="trip-insight-icon">📊</span>
                          <div className="trip-insight-content">
                            <span className="trip-insight-label">Avg Trip Duration</span>
                            <span className="trip-insight-value">{bookingStats.avg_trip_duration || 0} days</span>
                          </div>
                        </div>
                        <div className="trip-insight-card">
                          <span className="trip-insight-icon">🚗</span>
                          <div className="trip-insight-content">
                            <span className="trip-insight-label">Drop-off Times</span>
                            <span className="trip-insight-value">
                              AM: {bookingStats.dropoff_range?.am || 0} | PM: {bookingStats.dropoff_range?.pm || 0}
                            </span>
                            {bookingStats.dropoff_range?.am_busiest?.length > 0 && (
                              <div className="trip-insight-busiest-section">
                                <span className="trip-insight-busiest-label">AM Busiest:</span>
                                {bookingStats.dropoff_range.am_busiest.map((h, i) => (
                                  <span key={i} className="trip-insight-busiest">
                                    {h.start} - {h.end} ({h.count})
                                  </span>
                                ))}
                              </div>
                            )}
                            {bookingStats.dropoff_range?.pm_busiest?.length > 0 && (
                              <div className="trip-insight-busiest-section">
                                <span className="trip-insight-busiest-label">PM Busiest:</span>
                                {bookingStats.dropoff_range.pm_busiest.map((h, i) => (
                                  <span key={i} className="trip-insight-busiest">
                                    {h.start} - {h.end} ({h.count})
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                        <div className="trip-insight-card">
                          <span className="trip-insight-icon">✈️</span>
                          <div className="trip-insight-content">
                            <span className="trip-insight-label">Pick-up Times</span>
                            <span className="trip-insight-value">
                              AM: {bookingStats.pickup_range?.am || 0} | PM: {bookingStats.pickup_range?.pm || 0}
                            </span>
                            {bookingStats.pickup_range?.am_busiest?.length > 0 && (
                              <div className="trip-insight-busiest-section">
                                <span className="trip-insight-busiest-label">AM Busiest:</span>
                                {bookingStats.pickup_range.am_busiest.map((h, i) => (
                                  <span key={i} className="trip-insight-busiest">
                                    {h.start} - {h.end} ({h.count})
                                  </span>
                                ))}
                              </div>
                            )}
                            {bookingStats.pickup_range?.pm_busiest?.length > 0 && (
                              <div className="trip-insight-busiest-section">
                                <span className="trip-insight-busiest-label">PM Busiest:</span>
                                {bookingStats.pickup_range.pm_busiest.map((h, i) => (
                                  <span key={i} className="trip-insight-busiest">
                                    {h.start} - {h.end} ({h.count})
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Fun Facts */}
                    {funFacts && (
                      <div className="fun-facts-section">
                        <h3>Fun Facts</h3>
                        <div className="fun-facts-grid">
                          {funFacts.busiestDay && (
                            <div className="fun-fact-card">
                              <span className="fun-fact-icon">📅</span>
                              <div className="fun-fact-content">
                                <span className="fun-fact-label">Busiest Day</span>
                                <span className="fun-fact-value">{funFacts.busiestDay.count} bookings</span>
                                <span className="fun-fact-detail">{funFacts.busiestDay.date}</span>
                              </div>
                            </div>
                          )}
                          {funFacts.busiestStreak && (
                            <div className="fun-fact-card">
                              <span className="fun-fact-icon">🔥</span>
                              <div className="fun-fact-content">
                                <span className="fun-fact-label">Busiest Streak</span>
                                <span className="fun-fact-value">{funFacts.busiestStreak.days} consecutive days</span>
                                <span className="fun-fact-detail">{funFacts.busiestStreak.startDate} - {funFacts.busiestStreak.endDate} ({funFacts.busiestStreak.bookings} bookings)</span>
                              </div>
                            </div>
                          )}
                          {funFacts.longestTrip && (
                            <div className="fun-fact-card">
                              <span className="fun-fact-icon">✈️</span>
                              <div className="fun-fact-content">
                                <span className="fun-fact-label">Longest Trip</span>
                                <span className="fun-fact-value">{funFacts.longestTrip.days} days</span>
                                <span className="fun-fact-detail">{funFacts.longestTrip.destination}</span>
                              </div>
                            </div>
                          )}
                          {funFacts.highestTransaction && (
                            <div className="fun-fact-card">
                              <span className="fun-fact-icon">💰</span>
                              <div className="fun-fact-content">
                                <span className="fun-fact-label">Highest Transaction</span>
                                <span className="fun-fact-value">{funFacts.highestTransaction.amount}</span>
                                <span className="fun-fact-detail">{funFacts.highestTransaction.days} day trip</span>
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Booking Targets */}
                    {bookingStats && (
                      <div className="booking-targets-section">
                        <h3>Booking Targets</h3>
                        <div className="booking-targets-grid">
                          <div className="booking-target-card">
                            <span className="booking-target-icon">📅</span>
                            <div className="booking-target-content">
                              <span className="booking-target-label">Daily Target</span>
                              <span className="booking-target-value">{bookingStats.confirmed_today || 0} confirmed today</span>
                              <div className="booking-target-milestones">
                                {[1, 3, 5, 7, 9].map(target => (
                                  <span key={target} className={`milestone ${(bookingStats.confirmed_today || 0) >= target ? 'achieved' : ''}`}>
                                    {target}
                                  </span>
                                ))}
                              </div>
                            </div>
                          </div>
                          <div className="booking-target-card">
                            <span className="booking-target-icon">📆</span>
                            <div className="booking-target-content">
                              <span className="booking-target-label">Weekly Target</span>
                              <span className="booking-target-value">{bookingStats.confirmed_this_week || 0} confirmed this week</span>
                              <div className="booking-target-milestones">
                                {[1, 5, 10, 20, 25, 30].map(target => (
                                  <span key={target} className={`milestone ${(bookingStats.confirmed_this_week || 0) >= target ? 'achieved' : ''}`}>
                                    {target}
                                  </span>
                                ))}
                              </div>
                            </div>
                          </div>
                          <div className="booking-target-card">
                            <span className="booking-target-icon">🗓️</span>
                            <div className="booking-target-content">
                              <span className="booking-target-label">Monthly Target</span>
                              <span className="booking-target-value">{bookingStats.confirmed_this_month || 0} confirmed this month</span>
                              <div className="booking-target-milestones">
                                {[1, 10, 25, 50, 75, 100].map(target => (
                                  <span key={target} className={`milestone ${(bookingStats.confirmed_this_month || 0) >= target ? 'achieved' : ''}`}>
                                    {target}
                                  </span>
                                ))}
                              </div>
                            </div>
                          </div>
                          <div className="booking-target-card">
                            <span className="booking-target-icon">🏆</span>
                            <div className="booking-target-content">
                              <span className="booking-target-label">Total Milestones</span>
                              <span className="booking-target-value">{bookingStats.total_successful || 0} total bookings</span>
                              <div className="booking-target-milestones milestones-wrap">
                                {[1, 10, 25, 50, 75, 100, 150, 250, 500, 1000].map(target => (
                                  <span key={target} className={`milestone ${(bookingStats.total_successful || 0) >= target ? 'achieved' : ''}`}>
                                    {target}
                                  </span>
                                ))}
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Status Breakdown */}
                    {bookingStats.status_totals && (
                      <div className="status-breakdown">
                        <h3>Status Breakdown</h3>
                        <div className="status-breakdown-grid">
                          <div className="status-item status-confirmed">
                            <span className="status-dot"></span>
                            <span className="status-label">Confirmed</span>
                            <span className="status-count">{bookingStats.status_totals.confirmed || 0}</span>
                          </div>
                          <div className="status-item status-completed">
                            <span className="status-dot"></span>
                            <span className="status-label">Completed</span>
                            <span className="status-count">{bookingStats.status_totals.completed || 0}</span>
                          </div>
                          <div className="status-item status-pending">
                            <span className="status-dot"></span>
                            <span className="status-label">Pending</span>
                            <span className="status-count">{bookingStats.status_totals.pending || 0}</span>
                          </div>
                          <div className="status-item status-cancelled">
                            <span className="status-dot"></span>
                            <span className="status-label">Cancelled</span>
                            <span className="status-count">{bookingStats.status_totals.cancelled || 0}</span>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Chart Type Selector */}
                    <div className="chart-controls">
                      <label>View:</label>
                      <select value={statsChartType} onChange={e => setStatsChartType(e.target.value)}>
                        <option value="monthly">Monthly</option>
                        <option value="weekly">Weekly</option>
                        <option value="daily">Daily</option>
                        <option value="cumulative">Cumulative Growth</option>
                      </select>
                      <button
                        className="refresh-stats-btn"
                        onClick={() => fetchBookingStats()}
                        disabled={loadingStats}
                      >
                        {loadingStats ? 'Refreshing...' : 'Refresh Data'}
                      </button>
                    </div>

                    {/* Stacked Bar Chart */}
                    <div className="booking-chart">
                      <h3>
                        {statsChartType === 'monthly' && 'Bookings by Month'}
                        {statsChartType === 'weekly' && 'Bookings by Week'}
                        {statsChartType === 'daily' && 'Bookings by Day'}
                        {statsChartType === 'cumulative' && 'Cumulative Growth'}
                      </h3>
                      <div className="chart-container">
                        {statsChartType === 'cumulative' ? (
                          <div className="line-chart">
                            {bookingStats.cumulative.length > 0 && (
                              <>
                                <div className="chart-y-axis">
                                  <span>{Math.max(...bookingStats.cumulative.map(d => d.total))}</span>
                                  <span>{Math.round(Math.max(...bookingStats.cumulative.map(d => d.total)) / 2)}</span>
                                  <span>0</span>
                                </div>
                                <div className="chart-area">
                                  <svg viewBox={`0 0 ${Math.min(bookingStats.cumulative.length * 30, 1200)} 200`} preserveAspectRatio="none">
                                    <defs>
                                      <linearGradient id="lineGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                                        <stop offset="0%" stopColor="#22c55e" stopOpacity="0.3"/>
                                        <stop offset="100%" stopColor="#22c55e" stopOpacity="0.05"/>
                                      </linearGradient>
                                    </defs>
                                    {(() => {
                                      const maxVal = Math.max(...bookingStats.cumulative.map(d => d.total))
                                      const width = Math.min(bookingStats.cumulative.length * 30, 1200)
                                      const points = bookingStats.cumulative.map((d, i) => {
                                        const x = (i / (bookingStats.cumulative.length - 1)) * width
                                        const y = 200 - (d.total / maxVal) * 180
                                        return `${x},${y}`
                                      }).join(' ')
                                      const areaPoints = `0,200 ${points} ${width},200`
                                      return (
                                        <>
                                          <polygon points={areaPoints} fill="url(#lineGradient)" />
                                          <polyline points={points} fill="none" stroke="#22c55e" strokeWidth="2" />
                                        </>
                                      )
                                    })()}
                                  </svg>
                                </div>
                              </>
                            )}
                          </div>
                        ) : statsChartType === 'weekly' ? (
                          /* Weekly view with navigation */
                          <div className="weekly-chart-container">
                            {(() => {
                              const data = bookingStats.weekly
                              const weeksPerPage = 8
                              const totalPages = Math.ceil(data.length / weeksPerPage)
                              const startIdx = Math.max(0, data.length - weeksPerPage - (weeklyPageIndex * weeksPerPage))
                              const endIdx = Math.min(data.length, startIdx + weeksPerPage)
                              const displayData = data.slice(startIdx, endIdx)
                              const maxTotal = Math.max(...data.map(d => d.total), 1)

                              return (
                                <>
                                  <div className="chart-navigation">
                                    <button
                                      className="nav-btn"
                                      onClick={() => setWeeklyPageIndex(prev => Math.min(prev + 1, totalPages - 1))}
                                      disabled={weeklyPageIndex >= totalPages - 1}
                                    >
                                      &larr; Older
                                    </button>
                                    <span className="nav-info">
                                      Showing weeks {startIdx + 1}-{endIdx} of {data.length}
                                    </span>
                                    <button
                                      className="nav-btn"
                                      onClick={() => setWeeklyPageIndex(prev => Math.max(prev - 1, 0))}
                                      disabled={weeklyPageIndex <= 0}
                                    >
                                      Newer &rarr;
                                    </button>
                                  </div>
                                  <div className="stacked-bar-chart">
                                    {displayData.map((item, idx) => (
                                      <div key={idx} className="bar-column">
                                        <div className="bar-stack" style={{ height: '150px' }}>
                                          {['cancelled', 'pending', 'completed', 'confirmed'].map(status => {
                                            const value = item[status] || 0
                                            const height = (value / maxTotal) * 100
                                            return value > 0 ? (
                                              <div
                                                key={status}
                                                className={`bar-segment bar-${status}`}
                                                style={{ height: `${height}%` }}
                                                title={`${status}: ${value}`}
                                              />
                                            ) : null
                                          })}
                                        </div>
                                        <div className="bar-label">
                                          {(() => {
                                            const match = (item.week || '').match(/(\d{4})-W(\d{2})/)
                                            if (!match) return item.week
                                            const [, year, week] = match
                                            const startDate = new Date(year, 0, 1 + (parseInt(week, 10) - 1) * 7)
                                            const dayOfWeek = startDate.getDay()
                                            const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
                                            startDate.setDate(startDate.getDate() + diff)
                                            const endDate = new Date(startDate)
                                            endDate.setDate(startDate.getDate() + 6)
                                            return `${startDate.getDate()}/${startDate.getMonth() + 1}-${endDate.getDate()}/${endDate.getMonth() + 1}`
                                          })()}
                                        </div>
                                        <div className="bar-total">{item.total}</div>
                                      </div>
                                    ))}
                                  </div>
                                </>
                              )
                            })()}
                          </div>
                        ) : statsChartType === 'daily' ? (
                          /* Daily view with monthly containers */
                          <div className="daily-chart-container">
                            {(() => {
                              const data = bookingStats.daily
                              // Group daily data by month
                              const monthlyGroups = {}
                              data.forEach(item => {
                                const monthKey = item.date?.slice(0, 7) // "2026-01"
                                if (monthKey) {
                                  if (!monthlyGroups[monthKey]) monthlyGroups[monthKey] = []
                                  monthlyGroups[monthKey].push(item)
                                }
                              })
                              const sortedMonths = Object.keys(monthlyGroups).sort().reverse()
                              const maxTotal = Math.max(...data.map(d => d.total), 1)
                              const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

                              return sortedMonths.map(monthKey => {
                                const [year, month] = monthKey.split('-')
                                const monthName = `${monthNames[parseInt(month, 10) - 1]} ${year}`
                                const monthData = monthlyGroups[monthKey]
                                const monthTotal = monthData.reduce((sum, d) => sum + d.total, 0)
                                const isExpanded = expandedDailyMonths[monthKey]

                                return (
                                  <div key={monthKey} className="daily-month-container">
                                    <div
                                      className="daily-month-header"
                                      onClick={() => setExpandedDailyMonths(prev => ({
                                        ...prev,
                                        [monthKey]: !prev[monthKey]
                                      }))}
                                    >
                                      <span className="expand-icon">{isExpanded ? '▼' : '▶'}</span>
                                      <span className="month-name">{monthName}</span>
                                      <span className="month-total">{monthTotal} bookings</span>
                                    </div>
                                    {isExpanded && (
                                      <div className="stacked-bar-chart daily-bars">
                                        {monthData.map((item, idx) => (
                                          <div key={idx} className="bar-column">
                                            <div className="bar-stack" style={{ height: '120px' }}>
                                              {['cancelled', 'pending', 'completed', 'confirmed'].map(status => {
                                                const value = item[status] || 0
                                                const height = (value / maxTotal) * 100
                                                return value > 0 ? (
                                                  <div
                                                    key={status}
                                                    className={`bar-segment bar-${status}`}
                                                    style={{ height: `${height}%` }}
                                                    title={`${status}: ${value}`}
                                                  />
                                                ) : null
                                              })}
                                            </div>
                                            <div className="bar-label">
                                              {(() => {
                                                const [, , day] = (item.date || '').split('-')
                                                return day || item.date
                                              })()}
                                            </div>
                                            <div className="bar-total">{item.total}</div>
                                          </div>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                )
                              })
                            })()}
                          </div>
                        ) : (
                          /* Monthly view (default) */
                          <div className="stacked-bar-chart">
                            {(() => {
                              const data = bookingStats.monthly
                              const maxTotal = Math.max(...data.map(d => d.total), 1)
                              const displayData = data.slice(-12) // Show last 12 months
                              return displayData.map((item, idx) => (
                                <div key={idx} className="bar-column">
                                  <div className="bar-stack" style={{ height: '150px' }}>
                                    {['cancelled', 'pending', 'completed', 'confirmed'].map(status => {
                                      const value = item[status] || 0
                                      const height = (value / maxTotal) * 100
                                      return value > 0 ? (
                                        <div
                                          key={status}
                                          className={`bar-segment bar-${status}`}
                                          style={{ height: `${height}%` }}
                                          title={`${status}: ${value}`}
                                        />
                                      ) : null
                                    })}
                                  </div>
                                  <div className="bar-label">
                                    {(() => {
                                      const [year, month] = (item.month || '').split('-')
                                      const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                                      return month ? `${monthNames[parseInt(month, 10) - 1]} ${year?.slice(2)}` : item.month
                                    })()}
                                  </div>
                                  <div className="bar-total">{item.total}</div>
                                </div>
                              ))
                            })()}
                          </div>
                        )}
                      </div>

                      {/* Chart Legend */}
                      {statsChartType !== 'cumulative' && (
                        <div className="chart-legend">
                          <div className="legend-item"><span className="legend-color legend-confirmed"></span> Confirmed</div>
                          <div className="legend-item"><span className="legend-color legend-completed"></span> Completed</div>
                          <div className="legend-item"><span className="legend-color legend-pending"></span> Pending</div>
                          <div className="legend-item"><span className="legend-color legend-cancelled"></span> Cancelled</div>
                        </div>
                      )}
                    </div>

                    {/* Data Table */}
                    <div className="stats-table-section">
                      <h3>
                        {statsChartType === 'monthly' && 'Monthly Breakdown'}
                        {statsChartType === 'weekly' && 'Weekly Breakdown'}
                        {statsChartType === 'daily' && 'Daily Breakdown'}
                        {statsChartType === 'cumulative' && 'Cumulative Totals'}
                      </h3>

                      {statsChartType === 'daily' ? (
                        /* Daily breakdown with collapsible monthly containers */
                        <div className="daily-table-containers">
                          {(() => {
                            const data = bookingStats.daily
                            const monthlyGroups = {}
                            data.forEach(item => {
                              const monthKey = item.date?.slice(0, 7)
                              if (monthKey) {
                                if (!monthlyGroups[monthKey]) monthlyGroups[monthKey] = []
                                monthlyGroups[monthKey].push(item)
                              }
                            })
                            const sortedMonths = Object.keys(monthlyGroups).sort().reverse()
                            const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

                            return sortedMonths.map(monthKey => {
                              const [year, month] = monthKey.split('-')
                              const monthName = `${monthNames[parseInt(month, 10) - 1]} ${year}`
                              const monthData = monthlyGroups[monthKey]
                              const monthTotal = monthData.reduce((sum, d) => sum + d.total, 0)
                              const isExpanded = expandedDailyMonths[monthKey]

                              return (
                                <div key={monthKey} className="daily-table-month">
                                  <div
                                    className="daily-table-month-header"
                                    onClick={() => setExpandedDailyMonths(prev => ({
                                      ...prev,
                                      [monthKey]: !prev[monthKey]
                                    }))}
                                  >
                                    <span className="expand-icon">{isExpanded ? '▼' : '▶'}</span>
                                    <span className="month-name">{monthName}</span>
                                    <span className="month-total">{monthTotal} bookings</span>
                                  </div>
                                  {isExpanded && (
                                    <div className="stats-table-wrapper">
                                      <table className="stats-table">
                                        <thead>
                                          <tr>
                                            <th>Date</th>
                                            <th className="status-col confirmed">Confirmed</th>
                                            <th className="status-col completed">Completed</th>
                                            <th className="status-col pending">Pending</th>
                                            <th className="status-col cancelled">Cancelled</th>
                                            <th>Total</th>
                                          </tr>
                                        </thead>
                                        <tbody>
                                          {monthData.slice().reverse().map((item, idx) => (
                                            <tr key={idx}>
                                              <td>{(() => {
                                                const [, , day] = (item.date || '').split('-')
                                                return day ? `${day}/${month}` : item.date
                                              })()}</td>
                                              <td className="status-col confirmed">{item.confirmed || 0}</td>
                                              <td className="status-col completed">{item.completed || 0}</td>
                                              <td className="status-col pending">{item.pending || 0}</td>
                                              <td className="status-col cancelled">{item.cancelled || 0}</td>
                                              <td><strong>{item.total}</strong></td>
                                            </tr>
                                          ))}
                                        </tbody>
                                      </table>
                                    </div>
                                  )}
                                </div>
                              )
                            })
                          })()}
                        </div>
                      ) : (
                        /* Regular table for monthly, weekly, cumulative */
                        <div className="stats-table-wrapper">
                          <table className="stats-table">
                            <thead>
                              <tr>
                                <th>{statsChartType === 'monthly' ? 'Month' : statsChartType === 'weekly' ? 'Week' : 'Date'}</th>
                                {statsChartType !== 'cumulative' && (
                                  <>
                                    <th className="status-col confirmed">Confirmed</th>
                                    <th className="status-col completed">Completed</th>
                                    <th className="status-col pending">Pending</th>
                                    <th className="status-col cancelled">Cancelled</th>
                                  </>
                                )}
                                <th>Total</th>
                              </tr>
                            </thead>
                            <tbody>
                              {(() => {
                                const data = statsChartType === 'cumulative' ? bookingStats.cumulative :
                                             statsChartType === 'monthly' ? bookingStats.monthly :
                                             bookingStats.weekly
                                return data.slice(-20).reverse().map((item, idx) => (
                                  <tr key={idx}>
                                    <td>{(() => {
                                      if (statsChartType === 'cumulative' && item.date) {
                                        const [year, month, day] = item.date.split('-')
                                        return `${day}/${month}/${year}`
                                      }
                                      if (item.month) {
                                        const [year, month] = item.month.split('-')
                                        return `${month}/${year}`
                                      }
                                      if (item.week) {
                                        const match = item.week.match(/(\d{4})-W(\d{2})/)
                                        if (!match) return item.week
                                        const [, year, week] = match
                                        const startDate = new Date(year, 0, 1 + (parseInt(week, 10) - 1) * 7)
                                        const dayOfWeek = startDate.getDay()
                                        const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
                                        startDate.setDate(startDate.getDate() + diff)
                                        const endDate = new Date(startDate)
                                        endDate.setDate(startDate.getDate() + 6)
                                        return `${startDate.getDate()}/${startDate.getMonth() + 1} to ${endDate.getDate()}/${endDate.getMonth() + 1}`
                                      }
                                      return ''
                                    })()}</td>
                                    {statsChartType !== 'cumulative' && (
                                      <>
                                        <td className="status-col confirmed">{item.confirmed || 0}</td>
                                        <td className="status-col completed">{item.completed || 0}</td>
                                        <td className="status-col pending">{item.pending || 0}</td>
                                        <td className="status-col cancelled">{item.cancelled || 0}</td>
                                      </>
                                    )}
                                    <td><strong>{item.total}</strong></td>
                                  </tr>
                                ))
                              })()}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  <p>No booking data available.</p>
                )}
              </div>
            )}

            {/* Occupancy Report */}
            {reportsSubTab === 'occupancy' && (
              <div className="occupancy-report-section">
                <h3>Parking Occupancy</h3>
                <p className="reports-description">
                  View parking space utilization across your 60 spaces. Shows historical and future occupancy based on confirmed and completed bookings.
                </p>

                {/* View Type Selector */}
                <div className="chart-controls">
                  <label>View:</label>
                  <select value={occupancyView} onChange={e => setOccupancyView(e.target.value)}>
                    <option value="daily">Daily</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                  </select>
                  <button
                    className="refresh-stats-btn"
                    onClick={() => fetchOccupancyReport(occupancyView)}
                    disabled={loadingOccupancy}
                  >
                    {loadingOccupancy ? 'Refreshing...' : 'Refresh Data'}
                  </button>
                </div>

                {loadingOccupancy ? (
                  <div className="admin-loading-inline">
                    <div className="spinner-small"></div>
                    <span>Loading occupancy data...</span>
                  </div>
                ) : occupancyData ? (
                  <>
                    {/* Summary Stats */}
                    <div className="occupancy-summary">
                      <div className="occupancy-stat">
                        <span className="occupancy-stat-value">{occupancyData.max_capacity}</span>
                        <span className="occupancy-stat-label">Total Spaces</span>
                      </div>
                      {occupancyData.data && occupancyData.data.length > 0 && (() => {
                        const todayEntry = occupancyData.data.find(d => d.is_today);
                        const currentEntry = occupancyData.data.find(d => d.is_current_week || d.is_current_month);
                        const displayEntry = todayEntry || currentEntry;
                        if (displayEntry) {
                          return (
                            <>
                              <div className="occupancy-stat">
                                <span className="occupancy-stat-value">{displayEntry.occupied || displayEntry.avg_occupied}</span>
                                <span className="occupancy-stat-label">{todayEntry ? 'Occupied Today' : 'Current Avg Occupied'}</span>
                              </div>
                              <div className="occupancy-stat">
                                <span className="occupancy-stat-value">{displayEntry.available || displayEntry.avg_available}</span>
                                <span className="occupancy-stat-label">{todayEntry ? 'Available Today' : 'Current Avg Available'}</span>
                              </div>
                              <div className="occupancy-stat">
                                <span className="occupancy-stat-value">{displayEntry.occupancy_percent || displayEntry.avg_occupancy_percent}%</span>
                                <span className="occupancy-stat-label">{todayEntry ? 'Utilization Today' : 'Current Utilization'}</span>
                              </div>
                            </>
                          );
                        }
                        return null;
                      })()}
                    </div>

                    {/* Occupancy Chart - Visual Bar Chart */}
                    <div className="occupancy-chart-container">
                      <div className="occupancy-chart-header">
                        <h4>
                          {occupancyView === 'daily' && 'Daily Occupancy'}
                          {occupancyView === 'weekly' && 'Weekly Average Occupancy'}
                          {occupancyView === 'monthly' && 'Monthly Average Occupancy'}
                        </h4>
                        <div className="occupancy-chart-controls">
                          <div className="occupancy-nav-buttons">
                            <button
                              className="occupancy-nav-btn"
                              onClick={() => setOccupancyChartOffset(prev => prev - 14)}
                              title="Previous 2 weeks"
                            >
                              ← Past
                            </button>
                            <button
                              className="occupancy-nav-btn today-btn"
                              onClick={() => setOccupancyChartOffset(0)}
                              disabled={occupancyChartOffset === 0}
                              title="Center on today"
                            >
                              Today
                            </button>
                            <button
                              className="occupancy-nav-btn"
                              onClick={() => setOccupancyChartOffset(prev => prev + 14)}
                              title="Next 2 weeks"
                            >
                              Future →
                            </button>
                          </div>
                          <span className="occupancy-capacity-badge">
                            Capacity: {occupancyData.max_capacity} spaces
                          </span>
                        </div>
                      </div>
                      <div className="occupancy-chart-wrapper">
                        {/* Y-axis labels */}
                        <div className="occupancy-y-axis">
                          <span className="y-axis-label">100%</span>
                          <span className="y-axis-label">75%</span>
                          <span className="y-axis-label">50%</span>
                          <span className="y-axis-label">25%</span>
                          <span className="y-axis-label">0%</span>
                        </div>
                        <div className="occupancy-chart-area">
                          {/* Horizontal gridlines */}
                          <div className="occupancy-gridlines">
                            <div className="gridline" style={{ bottom: '100%' }}></div>
                            <div className="gridline" style={{ bottom: '75%' }}></div>
                            <div className="gridline" style={{ bottom: '50%' }}></div>
                            <div className="gridline" style={{ bottom: '25%' }}></div>
                            <div className="gridline" style={{ bottom: '0%' }}></div>
                          </div>
                          <div className="occupancy-chart">
                            {occupancyData.data && (() => {
                              // Filter out dates before January 2026
                              const filteredData = occupancyData.data.filter(item => {
                                if (item.display_date) {
                                  const parts = item.display_date.split('/');
                                  if (parts.length >= 3) {
                                    const year = parseInt('20' + parts[2], 10);
                                    const month = parseInt(parts[1], 10);
                                    return year > 2026 || (year === 2026 && month >= 1);
                                  }
                                }
                                return true;
                              });

                              // Find today's index
                              const todayIndex = filteredData.findIndex(item => item.is_today);
                              const daysToShow = 21; // Show 3 weeks at a time

                              // Calculate start index: center on today + offset
                              let startIndex;
                              if (todayIndex >= 0) {
                                // Center today in the view, then apply offset
                                startIndex = todayIndex - Math.floor(daysToShow / 2) + occupancyChartOffset;
                              } else {
                                // No today found, start from end
                                startIndex = filteredData.length - daysToShow + occupancyChartOffset;
                              }

                              // Clamp to valid range
                              startIndex = Math.max(0, Math.min(startIndex, filteredData.length - daysToShow));

                              return filteredData.slice(startIndex, startIndex + daysToShow).map((item, index) => {
                              const percent = item.occupancy_percent || item.avg_occupancy_percent || 0;
                              const occupied = item.occupied || item.avg_occupied || 0;
                              const available = occupancyData.max_capacity - occupied;
                              const isHighlight = item.is_today || item.is_current_week || item.is_current_month;
                              const isPast = item.is_past;
                              let barClass = 'occupancy-bar';
                              if (percent >= 90) barClass += ' high';
                              else if (percent >= 70) barClass += ' medium';
                              else barClass += ' low';
                              if (isHighlight) barClass += ' current';
                              if (isPast) barClass += ' past';

                              // Get day name for daily view
                              const getDayName = (dateStr) => {
                                if (!dateStr) return '';
                                const parts = dateStr.split('/');
                                if (parts.length >= 3) {
                                  const date = new Date(`20${parts[2]}`, parts[1] - 1, parts[0]);
                                  return date.toLocaleDateString('en-US', { weekday: 'short' });
                                }
                                return '';
                              };

                              return (
                                <div key={index} className="occupancy-bar-wrapper">
                                  <div className="occupancy-tooltip">
                                    <div className="tooltip-date">
                                      {item.display_date || item.display_week || item.display_month}
                                    </div>
                                    <div className="tooltip-stats">
                                      <span className="tooltip-occupied">{occupied} cars parked</span>
                                      <span className="tooltip-available">{available} spaces free</span>
                                      <span className="tooltip-percent">{Math.round(percent)}% full</span>
                                    </div>
                                  </div>
                                  <div className={barClass} style={{ height: `${Math.max(percent, 3)}%` }}>
                                    <div className="occupancy-bar-content">
                                      <span className="occupancy-bar-percent">{Math.round(percent)}%</span>
                                      <span className="occupancy-bar-cars">{occupied}</span>
                                    </div>
                                  </div>
                                  <div className="occupancy-bar-labels">
                                    {occupancyView === 'daily' && (
                                      <>
                                        <span className="bar-label-day">{getDayName(item.display_date)}</span>
                                        <span className="bar-label-date">{item.display_date?.slice(0, 5)}</span>
                                      </>
                                    )}
                                    {occupancyView === 'weekly' && (
                                      <span className="bar-label-date">{item.display_week?.split(' - ')[0]}</span>
                                    )}
                                    {occupancyView === 'monthly' && (
                                      <span className="bar-label-date">{item.display_month?.slice(0, 3)}</span>
                                    )}
                                  </div>
                                </div>
                              );
                            });
                            })()}
                          </div>
                        </div>
                      </div>
                      <div className="occupancy-legend">
                        <span className="legend-item"><span className="legend-color low"></span> Low (&lt;70%)</span>
                        <span className="legend-item"><span className="legend-color medium"></span> Medium (70-89%)</span>
                        <span className="legend-item"><span className="legend-color high"></span> High (90%+)</span>
                        <span className="legend-item"><span className="legend-color current"></span> Today</span>
                      </div>
                    </div>

                    {/* Occupancy Table */}
                    <div className="occupancy-table-container">
                      <h4>Detailed Breakdown</h4>

                      {/* Daily view: Group by month with collapsible sections */}
                      {occupancyView === 'daily' && occupancyData.data && (() => {
                        // Filter out dates before January 2026
                        const filteredData = occupancyData.data.filter(item => {
                          if (item.display_date) {
                            const parts = item.display_date.split('/');
                            if (parts.length >= 3) {
                              const year = parseInt('20' + parts[2], 10);
                              const month = parseInt(parts[1], 10);
                              return year > 2026 || (year === 2026 && month >= 1);
                            }
                          }
                          return true;
                        });

                        // Group data by month
                        const groupedByMonth = {};
                        filteredData.forEach(item => {
                          const monthKey = item.display_date?.slice(3) || 'Unknown'; // Get MM/YYYY part
                          if (!groupedByMonth[monthKey]) {
                            groupedByMonth[monthKey] = [];
                          }
                          groupedByMonth[monthKey].push(item);
                        });

                        return Object.entries(groupedByMonth).map(([monthKey, items]) => {
                          const hasCurrentDay = items.some(item => item.is_today);
                          const monthLabel = (() => {
                            const parts = monthKey.split('/');
                            if (parts.length === 2) {
                              const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
                              const monthIndex = parseInt(parts[0], 10) - 1;
                              return `${monthNames[monthIndex]} ${parts[1]}`;
                            }
                            return monthKey;
                          })();
                          const avgOccupancy = items.reduce((sum, item) => sum + (item.occupancy_percent || 0), 0) / items.length;

                          return (
                            <details key={monthKey} className="occupancy-month-group" open={hasCurrentDay}>
                              <summary className="occupancy-month-header">
                                <span className="month-title">{monthLabel}</span>
                                <span className="month-stats">
                                  <span className="month-days">{items.length} days</span>
                                  <span className={`month-avg ${avgOccupancy >= 90 ? 'high' : avgOccupancy >= 70 ? 'medium' : 'low'}`}>
                                    Avg: {avgOccupancy.toFixed(1)}%
                                  </span>
                                </span>
                              </summary>
                              <div className="occupancy-table-wrapper">
                                <table className="occupancy-table">
                                  <thead>
                                    <tr>
                                      <th>Date</th>
                                      <th>Occupied</th>
                                      <th>Available</th>
                                      <th>Utilization</th>
                                      <th>Status</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {items.map((item, index) => {
                                      const occupied = item.occupied ?? item.avg_occupied;
                                      const available = item.available ?? item.avg_available;
                                      const percent = item.occupancy_percent ?? item.avg_occupancy_percent;
                                      const isHighlight = item.is_today;
                                      const isPast = item.is_past;

                                      return (
                                        <tr key={index} className={`${isHighlight ? 'highlight-row' : ''} ${isPast ? 'past-row' : ''}`}>
                                          <td className="date-cell">{item.display_date}</td>
                                          <td className="number-cell">{typeof occupied === 'number' ? occupied.toFixed(0) : '-'}</td>
                                          <td className="number-cell">{typeof available === 'number' ? available.toFixed(0) : '-'}</td>
                                          <td className="util-cell">
                                            <span className={`occupancy-percent ${percent >= 90 ? 'high' : percent >= 70 ? 'medium' : 'low'}`}>
                                              {typeof percent === 'number' ? `${percent.toFixed(1)}%` : '-'}
                                            </span>
                                          </td>
                                          <td className="status-cell">
                                            {isHighlight && <span className="status-badge current">Today</span>}
                                            {isPast && !isHighlight && <span className="status-badge past">Past</span>}
                                            {!isPast && !isHighlight && <span className="status-badge future">Future</span>}
                                          </td>
                                        </tr>
                                      );
                                    })}
                                  </tbody>
                                </table>
                              </div>
                            </details>
                          );
                        });
                      })()}

                      {/* Weekly/Monthly view: Standard table */}
                      {occupancyView !== 'daily' && (
                        <div className="occupancy-table-wrapper">
                          <table className="occupancy-table">
                            <thead>
                              <tr>
                                <th>{occupancyView === 'weekly' ? 'Week' : 'Month'}</th>
                                <th>Avg Occupied</th>
                                <th>Avg Available</th>
                                <th>Utilization</th>
                                <th>Status</th>
                              </tr>
                            </thead>
                            <tbody>
                              {occupancyData.data && occupancyData.data.map((item, index) => {
                                const occupied = item.avg_occupied;
                                const available = item.avg_available;
                                const percent = item.avg_occupancy_percent;
                                const isHighlight = item.is_current_week || item.is_current_month;
                                const isPast = item.is_past;

                                return (
                                  <tr key={index} className={`${isHighlight ? 'highlight-row' : ''} ${isPast ? 'past-row' : ''}`}>
                                    <td className="date-cell">{item.display_week || item.display_month}</td>
                                    <td className="number-cell">{typeof occupied === 'number' ? occupied.toFixed(1) : '-'}</td>
                                    <td className="number-cell">{typeof available === 'number' ? available.toFixed(1) : '-'}</td>
                                    <td className="util-cell">
                                      <span className={`occupancy-percent ${percent >= 90 ? 'high' : percent >= 70 ? 'medium' : 'low'}`}>
                                        {typeof percent === 'number' ? `${percent.toFixed(1)}%` : '-'}
                                      </span>
                                    </td>
                                    <td className="status-cell">
                                      {isHighlight && <span className="status-badge current">Current</span>}
                                      {isPast && !isHighlight && <span className="status-badge past">Past</span>}
                                      {!isPast && !isHighlight && <span className="status-badge future">Future</span>}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  <p>No occupancy data available.</p>
                )}
              </div>
            )}

            {/* Popular Airlines & Destinations */}
            {reportsSubTab === 'popular' && (
              <div className="popular-report-section">
                <h3>Popular Airlines & Destinations</h3>
                <p className="reports-description">
                  View the most popular airlines and destinations based on confirmed and completed bookings.
                </p>

                {/* Controls */}
                <div className="chart-controls">
                  <label>Show:</label>
                  <select value={popularTop} onChange={e => setPopularTop(Number(e.target.value))}>
                    <option value={5}>Top 5</option>
                    <option value={10}>Top 10</option>
                    <option value={20}>Top 20</option>
                  </select>
                </div>

                {loadingPopular ? (
                  <div className="admin-loading-inline">
                    <div className="spinner-small"></div>
                    <span>Loading popular routes...</span>
                  </div>
                ) : popularData ? (
                  <>
                  <div className="popular-charts-grid">
                    {/* Popular Airlines */}
                    <div className="popular-chart-container">
                      <h4>Top Airlines</h4>
                      <p className="chart-subtitle">Based on {popularData.meta.totalBookings} bookings</p>
                      <div className="popular-bar-chart">
                        {popularData.popularAirlines.length > 0 ? (
                          popularData.popularAirlines.map((airline, idx) => {
                            const maxCount = popularData.popularAirlines[0]?.count || 1
                            const barWidth = (airline.count / maxCount) * 100
                            return (
                              <div key={idx} className="popular-bar-row">
                                <div className="popular-bar-label">
                                  <span className="popular-rank">{idx + 1}</span>
                                  <span className="popular-name">{airline.airlineName}</span>
                                </div>
                                <div className="popular-bar-container">
                                  <div
                                    className="popular-bar popular-bar-airline"
                                    style={{ width: `${barWidth}%` }}
                                  />
                                  <span className="popular-bar-value">{airline.count} ({airline.percent}%)</span>
                                </div>
                              </div>
                            )
                          })
                        ) : (
                          <p className="no-data">No airline data available</p>
                        )}
                      </div>
                    </div>

                    {/* Popular Destinations */}
                    <div className="popular-chart-container">
                      <h4>Top Destinations</h4>
                      <p className="chart-subtitle">Based on {popularData.meta.totalBookings} bookings</p>
                      <div className="popular-bar-chart">
                        {popularData.popularDestinations.length > 0 ? (
                          popularData.popularDestinations.map((dest, idx) => {
                            const maxCount = popularData.popularDestinations[0]?.count || 1
                            const barWidth = (dest.count / maxCount) * 100
                            return (
                              <div key={idx} className="popular-bar-row">
                                <div className="popular-bar-label">
                                  <span className="popular-rank">{idx + 1}</span>
                                  <span className="popular-name">{dest.destination}</span>
                                </div>
                                <div className="popular-bar-container">
                                  <div
                                    className="popular-bar popular-bar-destination"
                                    style={{ width: `${barWidth}%` }}
                                  />
                                  <span className="popular-bar-value">{dest.count} ({dest.percent}%)</span>
                                </div>
                              </div>
                            )
                          })
                        ) : (
                          <p className="no-data">No destination data available</p>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Popular Routes - Full Width */}
                  <div className="popular-chart-container popular-chart-full-width">
                    <h4>Top Routes (Airline + Destination)</h4>
                    <p className="chart-subtitle">Based on {popularData.meta.totalBookings} bookings</p>
                    <div className="popular-bar-chart">
                      {popularData.popularRoutes && popularData.popularRoutes.length > 0 ? (
                        popularData.popularRoutes.map((route, idx) => {
                          const maxCount = popularData.popularRoutes[0]?.count || 1
                          const barWidth = (route.count / maxCount) * 100
                          return (
                            <div key={idx} className="popular-bar-row">
                              <div className="popular-bar-label popular-bar-label-wide">
                                <span className="popular-rank">{idx + 1}</span>
                                <span className="popular-name">{route.route}</span>
                              </div>
                              <div className="popular-bar-container">
                                <div
                                  className="popular-bar popular-bar-route"
                                  style={{ width: `${barWidth}%` }}
                                />
                                <span className="popular-bar-value">{route.count} ({route.percent}%)</span>
                              </div>
                            </div>
                          )
                        })
                      ) : (
                        <p className="no-data">No route data available</p>
                      )}
                    </div>
                  </div>
                  </>
                ) : (
                  <p>No data available. Try refreshing the page.</p>
                )}
              </div>
            )}

            {/* Location Maps */}
            {reportsSubTab === 'map' && (
              <>
                <div className="reports-section-header">
                  <button
                    className="refresh-page-btn"
                    onClick={() => fetchBookingLocations(mapType)}
                    disabled={loadingLocations}
                  >
                    {loadingLocations ? 'Refreshing...' : 'Refresh Page'}
                  </button>
                </div>

                <div className="map-type-tabs">
                  <button
                    className={`map-type-tab ${mapType === 'bookings' ? 'active' : ''}`}
                    onClick={() => setMapType('bookings')}
                  >
                    Bookings Map
                  </button>
                  <button
                    className={`map-type-tab ${mapType === 'origins' ? 'active' : ''}`}
                    onClick={() => setMapType('origins')}
                  >
                    Journey Origins
                  </button>
                </div>

                {mapType === 'bookings' && (
                  <>
                    <h3>Confirmed Booking Locations</h3>
                    <p className="reports-description">Map showing confirmed bookings based on billing postcodes.</p>
                  </>
                )}

                {mapType === 'origins' && (
                  <>
                    <h3>Journey Origins (All Leads)</h3>
                    <p className="reports-description">Map showing all customers who started the booking process (Page 1 data).</p>
                  </>
                )}

                {loadingLocations ? (
                  <div className="admin-loading-inline">
                    <div className="spinner-small"></div>
                    <span>Loading {mapType === 'origins' ? 'customer' : 'booking'} locations...</span>
                  </div>
                ) : (
                  <>
                    <BookingLocationMap
                      locations={mapType === 'origins' ? originLocations : bookingLocations}
                      mapType={mapType}
                    />
                    {skippedBookings.length > 0 && (
                      <div className="skipped-bookings">
                        <p className="skipped-summary">
                          {mapType === 'origins'
                            ? `${originLocations.length} of ${totalCustomers} customers mapped.`
                            : `${bookingLocations.length} of ${totalBookings} bookings mapped.`
                          }
                          {' '}{skippedBookings.length} skipped:
                        </p>
                        <ul className="skipped-list">
                          {skippedBookings.map((s, i) => (
                            <li key={i}>{s.reference || `Customer ${s.customer_id}`}: {s.reason}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </>
                )}
              </>
            )}
          </div>
        )}

        {activeTab === 'qa' && (
          <div className="admin-section">
            <div className="admin-section-header">
              <h2>QA Dashboard</h2>
              <button onClick={fetchTestResults} className="admin-refresh" disabled={loadingTestResults}>
                {loadingTestResults ? 'Loading...' : 'Refresh'}
              </button>
            </div>

            {loadingTestResults ? (
              <div className="admin-loading-inline">
                <div className="spinner-small"></div>
                <span>Loading test results...</span>
              </div>
            ) : (
              <>
                {/* Latest Run Summary */}
                {latestTestRun && (
                  <div className="qa-latest-run">
                    <h3>Latest Test Run</h3>
                    <div className="stats-summary-cards">
                      <div className={`stats-card ${latestTestRun.status === 'passed' ? 'status-confirmed' : latestTestRun.status === 'failed' ? 'status-cancelled' : 'status-pending'}`}>
                        <div className="stats-card-value" style={{ textTransform: 'uppercase' }}>
                          {latestTestRun.status}
                        </div>
                        <div className="stats-card-label">Status</div>
                      </div>
                      <div className="stats-card">
                        <div className="stats-card-value" style={{ color: '#22c55e' }}>{latestTestRun.tests_passed}</div>
                        <div className="stats-card-label">Passed</div>
                      </div>
                      <div className="stats-card">
                        <div className="stats-card-value" style={{ color: latestTestRun.tests_failed > 0 ? '#ef4444' : '#22c55e' }}>{latestTestRun.tests_failed}</div>
                        <div className="stats-card-label">Failed</div>
                      </div>
                      <div className="stats-card">
                        <div className="stats-card-value">{latestTestRun.tests_skipped}</div>
                        <div className="stats-card-label">Skipped</div>
                      </div>
                      <div className="stats-card">
                        <div className="stats-card-value">{latestTestRun.pass_rate?.toFixed(1) || 0}%</div>
                        <div className="stats-card-label">Pass Rate</div>
                      </div>
                      {latestTestRun.coverage_percent !== null && (
                        <div className="stats-card">
                          <div className="stats-card-value">{latestTestRun.coverage_percent?.toFixed(1)}%</div>
                          <div className="stats-card-label">Coverage</div>
                        </div>
                      )}
                    </div>
                    <div className="qa-run-details">
                      <p><strong>Environment:</strong> {latestTestRun.environment}</p>
                      <p><strong>Run Type:</strong> {latestTestRun.run_type}</p>
                      <p><strong>Duration:</strong> {latestTestRun.duration_seconds ? `${latestTestRun.duration_seconds}s` : 'N/A'}</p>
                      <p><strong>Started:</strong> {new Date(latestTestRun.started_at).toLocaleString()}</p>
                      {latestTestRun.branch && <p><strong>Branch:</strong> {latestTestRun.branch}</p>}
                      {latestTestRun.commit_sha && <p><strong>Commit:</strong> {latestTestRun.commit_sha.substring(0, 7)}</p>}
                      {latestTestRun.logs_url && (
                        <p><a href={latestTestRun.logs_url} target="_blank" rel="noopener noreferrer" className="admin-link">View Logs</a></p>
                      )}
                    </div>
                  </div>
                )}

                {/* Historical Results */}
                <div className="qa-history">
                  <h3>Test Run History</h3>
                  {testResults.length === 0 ? (
                    <p className="admin-empty">No test runs recorded yet.</p>
                  ) : (
                    <table className="admin-table">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Status</th>
                          <th>Passed</th>
                          <th>Failed</th>
                          <th>Total</th>
                          <th>Pass Rate</th>
                          <th>Coverage</th>
                          <th>Duration</th>
                          <th>Branch</th>
                          <th>Logs</th>
                        </tr>
                      </thead>
                      <tbody>
                        {testResults.map((run) => (
                          <tr key={run.id} className={run.status === 'failed' ? 'row-warning' : ''}>
                            <td>{new Date(run.started_at).toLocaleDateString()}</td>
                            <td>
                              <span className={`status-badge status-${run.status === 'passed' ? 'confirmed' : run.status === 'failed' ? 'cancelled' : 'pending'}`}>
                                {run.status}
                              </span>
                            </td>
                            <td style={{ color: '#22c55e' }}>{run.tests_passed}</td>
                            <td style={{ color: run.tests_failed > 0 ? '#ef4444' : '#22c55e' }}>{run.tests_failed}</td>
                            <td>{run.tests_total}</td>
                            <td>{run.pass_rate?.toFixed(1) || 0}%</td>
                            <td>{run.coverage_percent !== null ? `${run.coverage_percent?.toFixed(1)}%` : '-'}</td>
                            <td>{run.duration_seconds ? `${run.duration_seconds}s` : '-'}</td>
                            <td>{run.branch || '-'}</td>
                            <td>
                              {run.logs_url ? (
                                <a href={run.logs_url} target="_blank" rel="noopener noreferrer" className="admin-link">View</a>
                              ) : '-'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>

                {/* Schedule Info */}
                <div className="qa-schedule-info">
                  <h3>Scheduled Tests</h3>
                  <p>Automated tests run twice per week:</p>
                  <ul>
                    <li>Monday at 6:00 AM UTC</li>
                    <li>Thursday at 6:00 AM UTC</li>
                  </ul>
                  <p>Tests are run against the <strong>staging</strong> environment.</p>
                </div>
              </>
            )}
          </div>
        )}

        {/* Testimonials Section */}
        {activeTab === 'testimonials' && (
          <div className="admin-section">
            <div className="admin-section-header">
              <h2>Testimonials</h2>
              <div className="admin-header-actions">
                <button onClick={openAddTestimonialModal} className="admin-btn admin-btn-primary">
                  + Add Testimonial
                </button>
                <button onClick={fetchTestimonials} className="admin-refresh" disabled={loadingTestimonials}>
                  {loadingTestimonials ? 'Loading...' : 'Refresh'}
                </button>
              </div>
            </div>

            {testimonialSuccessMessage && (
              <div className="admin-success">{testimonialSuccessMessage}</div>
            )}

            {/* Filters */}
            <div className="admin-filters" style={{ marginBottom: '1rem' }}>
              <select
                value={testimonialFilter.star_rating}
                onChange={(e) => setTestimonialFilter({ ...testimonialFilter, star_rating: e.target.value })}
                className="admin-filter-select"
              >
                <option value="">All Ratings</option>
                <option value="5">5★ Only</option>
                <option value="4">4★ Only</option>
                <option value="3">3★ Only</option>
                <option value="2">2★ Only</option>
                <option value="1">1★ Only</option>
              </select>
              <select
                value={testimonialFilter.status}
                onChange={(e) => setTestimonialFilter({ ...testimonialFilter, status: e.target.value })}
                className="admin-filter-select"
              >
                <option value="">All Status</option>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
              <select
                value={`${testimonialSort.field}-${testimonialSort.order}`}
                onChange={(e) => {
                  const [field, order] = e.target.value.split('-')
                  setTestimonialSort({ field, order })
                }}
                className="admin-filter-select"
              >
                <option value="date_added-desc">Newest First</option>
                <option value="date_added-asc">Oldest First</option>
                <option value="star_rating-desc">Highest Rated</option>
                <option value="star_rating-asc">Lowest Rated</option>
              </select>
            </div>

            {loadingTestimonials ? (
              <div className="admin-loading-inline">
                <div className="spinner-small"></div>
                <span>Loading testimonials...</span>
              </div>
            ) : testimonials.length === 0 ? (
              <p className="admin-empty">No testimonials found. Click "Add Testimonial" to create one.</p>
            ) : (
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Customer</th>
                    <th>Rating</th>
                    <th>Review</th>
                    <th>Source</th>
                    <th>Date Added</th>
                    <th>Status</th>
                    <th>Featured</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {testimonials.map((t) => (
                    <tr key={t.id} className={t.is_featured ? 'row-featured' : ''}>
                      <td>{t.customer_name}</td>
                      <td>{renderStars(t.star_rating)}</td>
                      <td className="review-cell">
                        {t.review_text.length > 80
                          ? t.review_text.substring(0, 80) + '...'
                          : t.review_text}
                      </td>
                      <td>{t.source || '-'}</td>
                      <td>{t.date_added ? new Date(t.date_added).toLocaleDateString('en-GB') : '-'}</td>
                      <td>
                        <span className={`status-badge status-${t.status === 'active' ? 'confirmed' : 'pending'}`}>
                          {t.status}
                        </span>
                      </td>
                      <td>{t.is_featured ? '✓' : '-'}</td>
                      <td className="actions-cell">
                        <button
                          className="action-btn edit-btn"
                          onClick={() => openEditTestimonialModal(t)}
                        >
                          Edit
                        </button>
                        <button
                          className="action-btn"
                          onClick={() => handleToggleTestimonialStatus(t)}
                          style={{ backgroundColor: t.status === 'active' ? '#f59e0b' : '#22c55e', color: '#fff' }}
                        >
                          {t.status === 'active' ? 'Deactivate' : 'Activate'}
                        </button>
                        <button
                          className="action-btn cancel-btn"
                          onClick={() => {
                            setTestimonialToDelete(t)
                            setShowDeleteTestimonialModal(true)
                          }}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

      </main>

      {/* Testimonial Add/Edit Modal */}
      {showTestimonialModal && (
        <div className="modal-overlay" onClick={() => setShowTestimonialModal(false)}>
          <div className="modal-content modal-content-wide" onClick={(e) => e.stopPropagation()}>
            <h3>{editingTestimonial ? 'Edit Testimonial' : 'Add Testimonial'}</h3>

            <div className="modal-form">
              <div className="form-group">
                <label>Customer Name *</label>
                <input
                  type="text"
                  value={testimonialForm.customer_name}
                  onChange={(e) => setTestimonialForm({ ...testimonialForm, customer_name: e.target.value })}
                  placeholder="e.g. John Smith"
                  maxLength={100}
                />
              </div>

              <div className="form-group">
                <label>Review Text *</label>
                <textarea
                  value={testimonialForm.review_text}
                  onChange={(e) => setTestimonialForm({ ...testimonialForm, review_text: e.target.value })}
                  placeholder="Enter the customer's review..."
                  rows={4}
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Star Rating (optional for LinkedIn/FB)</label>
                  <div className="star-selector">
                    {[1, 2, 3, 4, 5].map(star => (
                      <button
                        key={star}
                        type="button"
                        className={`star-btn ${testimonialForm.star_rating >= star ? 'selected' : ''}`}
                        onClick={() => setTestimonialForm({
                          ...testimonialForm,
                          star_rating: testimonialForm.star_rating === star ? null : star
                        })}
                      >
                        {testimonialForm.star_rating >= star ? '★' : '☆'}
                      </button>
                    ))}
                    {testimonialForm.star_rating && (
                      <button
                        type="button"
                        className="clear-rating-btn"
                        onClick={() => setTestimonialForm({ ...testimonialForm, star_rating: null })}
                      >
                        Clear
                      </button>
                    )}
                  </div>
                </div>

                <div className="form-group">
                  <label>Source</label>
                  <input
                    type="text"
                    value={testimonialForm.source}
                    onChange={(e) => setTestimonialForm({ ...testimonialForm, source: e.target.value })}
                    placeholder="e.g. Google, TrustPilot, LinkedIn"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Date of Travel</label>
                  <DatePicker
                    selected={testimonialForm.date_of_travel ? new Date(testimonialForm.date_of_travel) : null}
                    onChange={(date) => setTestimonialForm({
                      ...testimonialForm,
                      date_of_travel: date ? date.toISOString().split('T')[0] : ''
                    })}
                    dateFormat="dd/MM/yyyy"
                    placeholderText="dd/mm/yyyy"
                    className="admin-input"
                  />
                </div>

                <div className="form-group">
                  <label>Status</label>
                  <select
                    value={testimonialForm.status}
                    onChange={(e) => setTestimonialForm({ ...testimonialForm, status: e.target.value })}
                  >
                    <option value="inactive">Inactive (Draft)</option>
                    <option value="active">Active (Published)</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={testimonialForm.is_featured}
                    onChange={(e) => setTestimonialForm({ ...testimonialForm, is_featured: e.target.checked })}
                  />
                  Mark as Featured (appears more frequently in rotation)
                </label>
              </div>
            </div>

            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowTestimonialModal(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={handleSaveTestimonial}
                disabled={savingTestimonial || !testimonialForm.customer_name || !testimonialForm.review_text}
              >
                {savingTestimonial ? 'Saving...' : (editingTestimonial ? 'Update' : 'Save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Testimonial Modal */}
      {showDeleteTestimonialModal && testimonialToDelete && (
        <div className="modal-overlay" onClick={() => setShowDeleteTestimonialModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Delete Testimonial</h3>
            <p>Are you sure you want to delete this review? This action cannot be undone.</p>
            <div className="modal-booking-info">
              <p><strong>Customer:</strong> {testimonialToDelete.customer_name}</p>
              <p><strong>Review:</strong> {testimonialToDelete.review_text.substring(0, 80)}...</p>
            </div>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowDeleteTestimonialModal(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-danger"
                onClick={handleDeleteTestimonial}
                disabled={deletingTestimonial}
              >
                {deletingTestimonial ? 'Deleting...' : 'Yes, Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

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

      {/* Delete Pending Booking Modal */}
      {showDeleteModal && bookingToDelete && (
        <div className="modal-overlay" onClick={() => setShowDeleteModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Delete Pending Booking</h3>
            <p>Are you sure you want to permanently delete this booking? This action cannot be undone.</p>
            <div className="modal-booking-info">
              <p><strong>Reference:</strong> {bookingToDelete.reference}</p>
              <p><strong>Customer:</strong> {bookingToDelete.customer?.first_name} {bookingToDelete.customer?.last_name}</p>
              <p><strong>Drop-off:</strong> {formatDate(bookingToDelete.dropoff_date)}</p>
            </div>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowDeleteModal(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-danger"
                onClick={confirmDeleteBooking}
                disabled={deletingId}
              >
                {deletingId ? 'Deleting...' : 'Yes, Delete Booking'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Booking Details Modal */}
      {showEditModal && bookingToEdit && (
        <div className="modal-overlay" onClick={() => setShowEditModal(false)}>
          <div className="modal-content modal-content-wide" onClick={(e) => e.stopPropagation()}>
            <h3>Edit Booking Details</h3>
            <div className="modal-booking-info">
              <p><strong>Reference:</strong> {bookingToEdit.reference}</p>
              <p><strong>Customer:</strong> {bookingToEdit.customer?.first_name} {bookingToEdit.customer?.last_name}</p>
            </div>
            <div className="modal-form">
              <h4 className="modal-section-title">Drop-off / Departure</h4>
              <div className="modal-form-row">
                <div className="modal-form-group">
                  <label>Drop-off Time (24hr)</label>
                  <input
                    type="text"
                    placeholder="HH:MM"
                    pattern="([01]?[0-9]|2[0-3]):[0-5][0-9]"
                    value={editForm.dropoff_time}
                    onChange={(e) => setEditForm({ ...editForm, dropoff_time: e.target.value })}
                  />
                </div>
                <div className="modal-form-group">
                  <label>Flight Departure Time (24hr)</label>
                  <input
                    type="text"
                    placeholder="HH:MM"
                    pattern="([01]?[0-9]|2[0-3]):[0-5][0-9]"
                    value={editForm.flight_departure_time}
                    onChange={(e) => setEditForm({ ...editForm, flight_departure_time: e.target.value })}
                  />
                </div>
                <div className="modal-form-group">
                  <label>Airline</label>
                  <input
                    type="text"
                    placeholder="e.g. Jet2"
                    value={editForm.dropoff_airline_name}
                    onChange={(e) => setEditForm({ ...editForm, dropoff_airline_name: e.target.value })}
                  />
                </div>
                <div className="modal-form-group">
                  <label>Flight Number</label>
                  <input
                    type="text"
                    placeholder="e.g. BY1234"
                    value={editForm.dropoff_flight_number}
                    onChange={(e) => setEditForm({ ...editForm, dropoff_flight_number: e.target.value })}
                  />
                </div>
                <div className="modal-form-group">
                  <label>Destination</label>
                  <input
                    type="text"
                    placeholder="e.g. Malaga Airport"
                    value={editForm.dropoff_destination}
                    onChange={(e) => setEditForm({ ...editForm, dropoff_destination: e.target.value })}
                  />
                </div>
              </div>

              <h4 className="modal-section-title">Pick-up / Return</h4>
              <div className="modal-form-row">
                <div className="modal-form-group">
                  <label>Pickup Date (DD/MM/YYYY)</label>
                  <input
                    type="text"
                    placeholder="DD/MM/YYYY"
                    pattern="\d{2}/\d{2}/\d{4}"
                    value={editForm.pickup_date}
                    onChange={(e) => setEditForm({ ...editForm, pickup_date: e.target.value })}
                  />
                </div>
                <div className="modal-form-group">
                  <label>Arrival Time (24hr)</label>
                  <input
                    type="text"
                    placeholder="HH:MM"
                    pattern="([01]?[0-9]|2[0-3]):[0-5][0-9]"
                    value={editForm.flight_arrival_time}
                    onChange={(e) => setEditForm({ ...editForm, flight_arrival_time: e.target.value })}
                  />
                  <p className="modal-form-hint">Pickup time = arrival + 30 min</p>
                </div>
                <div className="modal-form-group">
                  <label>Airline</label>
                  <input
                    type="text"
                    placeholder="e.g. Jet2"
                    value={editForm.pickup_airline_name}
                    onChange={(e) => setEditForm({ ...editForm, pickup_airline_name: e.target.value })}
                  />
                </div>
                <div className="modal-form-group">
                  <label>Flight Number</label>
                  <input
                    type="text"
                    placeholder="e.g. BY1235"
                    value={editForm.pickup_flight_number}
                    onChange={(e) => setEditForm({ ...editForm, pickup_flight_number: e.target.value })}
                  />
                </div>
                <div className="modal-form-group">
                  <label>Origin</label>
                  <input
                    type="text"
                    placeholder="e.g. Malaga Airport"
                    value={editForm.pickup_origin}
                    onChange={(e) => setEditForm({ ...editForm, pickup_origin: e.target.value })}
                  />
                </div>
              </div>
            </div>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowEditModal(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={confirmEditBooking}
                disabled={savingEdit}
              >
                {savingEdit ? 'Saving...' : 'Save Changes'}
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

      {/* Send Founder Email Confirmation Modal */}
      {showFounderEmailModal && bookingForFounderEmail && (
        <div className="modal-overlay" onClick={() => setShowFounderEmailModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Send Founder Email</h3>
            <p>This will send a personal follow-up email from Kristian to the customer about their incomplete booking.</p>
            <div className="modal-booking-info">
              <p><strong>Reference:</strong> {bookingForFounderEmail.reference}</p>
              <p><strong>Customer:</strong> {bookingForFounderEmail.customer?.first_name} {bookingForFounderEmail.customer?.last_name}</p>
              <p><strong>Email:</strong> {bookingForFounderEmail.customer?.email}</p>
            </div>
            <p className="modal-warning">
              The email will be CC'd to Kristian so he can see and respond to any replies.
            </p>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowFounderEmailModal(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={handleConfirmSendFounderEmail}
                disabled={sendingFounderEmailId}
              >
                {sendingFounderEmailId ? 'Sending...' : 'Yes, Send Email'}
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

      {/* Send Founder Thank You Email Confirmation Modal (for Marketing Subscribers) */}
      {showSubscriberFounderModal && founderEmailToSend && (
        <div className="modal-overlay" onClick={() => { setShowSubscriberFounderModal(false); setFounderEmailToSend(null); }}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Send Founder Thank You Email</h3>
            <p>Are you sure you want to send this personal thank you email from Kristian?</p>
            <div className="modal-booking-info">
              <p><strong>Subscriber:</strong> {founderEmailToSend.subscriber.first_name} {founderEmailToSend.subscriber.last_name}</p>
              <p><strong>Email:</strong> {founderEmailToSend.subscriber.email}</p>
            </div>
            <p className="modal-warning">
              This will generate a unique 10% promo code and send a personal thank you email from Kristian.
              The email will be CC'd to Kristian so he can see and respond to any replies.
            </p>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => { setShowSubscriberFounderModal(false); setFounderEmailToSend(null); }}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={confirmSendFounderEmail}
                disabled={sendingFounderEmailId}
              >
                {sendingFounderEmailId ? 'Sending...' : 'Yes, Send Founder Email'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Return Vehicle Inspection Modal */}
      {showReturnInspectionModal && bookingForInspection && (
        <div className="modal-overlay" onClick={closeReturnInspectionModal}>
          <div className="modal-content modal-content-wide" onClick={(e) => e.stopPropagation()}>
            <h3>Return Vehicle Inspection</h3>
            <div className="modal-booking-info">
              <p><strong>Booking:</strong> {bookingForInspection.reference}</p>
              <p><strong>Customer:</strong> {bookingForInspection.customer?.first_name} {bookingForInspection.customer?.last_name}</p>
              <p><strong>Vehicle:</strong> {bookingForInspection.vehicle?.registration} - {bookingForInspection.vehicle?.make} {bookingForInspection.vehicle?.model}</p>
            </div>

            {loadingReturnInspection ? (
              <div className="inspection-loading">
                <div className="spinner"></div>
                <p>Loading inspection data...</p>
              </div>
            ) : returnInspectionData ? (
              <div className="inspection-details">
                <div className="inspection-section">
                  <h4>Inspection Details</h4>
                  <div className="inspection-grid">
                    <div className="inspection-item">
                      <span className="inspection-label">Customer Name</span>
                      <span className="inspection-value">{returnInspectionData.customer_name || 'Not recorded'}</span>
                    </div>
                    <div className="inspection-item">
                      <span className="inspection-label">Signed Date</span>
                      <span className="inspection-value">{returnInspectionData.signed_date ? formatDateTimeUK(returnInspectionData.signed_date) : '-'}</span>
                    </div>
                    <div className="inspection-item">
                      <span className="inspection-label">Mileage</span>
                      <span className="inspection-value">{returnInspectionData.mileage ? `${returnInspectionData.mileage.toLocaleString()} miles` : 'Not recorded'}</span>
                    </div>
                    <div className="inspection-item">
                      <span className="inspection-label">Recorded</span>
                      <span className="inspection-value">{returnInspectionData.created_at ? formatDateTimeUK(returnInspectionData.created_at) : '-'}</span>
                    </div>
                  </div>
                </div>

                {returnInspectionData.declined ? (
                  <div className="inspection-section inspection-declined">
                    <h4>Inspection Declined</h4>
                    <p>The customer declined this return inspection.</p>
                    {returnInspectionData.declined_reason && (
                      <p><strong>Reason:</strong> {returnInspectionData.declined_reason}</p>
                    )}
                  </div>
                ) : (
                  <>
                    {returnInspectionData.notes && (
                      <div className="inspection-section">
                        <h4>Notes</h4>
                        <p className="inspection-notes">{returnInspectionData.notes}</p>
                      </div>
                    )}

                    {returnInspectionData.photos && Object.keys(returnInspectionData.photos).length > 0 && (
                      <div className="inspection-section">
                        <h4>Photos</h4>
                        <div className="inspection-photos">
                          {PHOTO_SLOTS.map(slot => (
                            returnInspectionData.photos[slot.key] && (
                              <div key={slot.key} className="inspection-photo">
                                <span className="photo-label">{slot.label}</span>
                                <img src={returnInspectionData.photos[slot.key]} alt={slot.label} />
                              </div>
                            )
                          ))}
                        </div>
                      </div>
                    )}

                    {returnInspectionData.signature && (
                      <div className="inspection-section">
                        <h4>Customer Signature</h4>
                        <div className="inspection-signature">
                          <img src={returnInspectionData.signature} alt="Customer Signature" />
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            ) : (
              <div className="inspection-empty">
                <p>No return vehicle inspection found for this booking.</p>
                <p className="inspection-empty-hint">The return inspection may not have been completed yet.</p>
              </div>
            )}

            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={closeReturnInspectionModal}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Drop-off Vehicle Inspection Modal */}
      {showDropoffInspectionModal && bookingForDropoffInspection && (
        <div className="modal-overlay" onClick={closeDropoffInspectionModal}>
          <div className="modal-content modal-content-wide" onClick={(e) => e.stopPropagation()}>
            <h3>Drop-off Vehicle Inspection</h3>
            <div className="modal-booking-info">
              <p><strong>Booking:</strong> {bookingForDropoffInspection.reference}</p>
              <p><strong>Customer:</strong> {bookingForDropoffInspection.customer?.first_name} {bookingForDropoffInspection.customer?.last_name}</p>
              <p><strong>Vehicle:</strong> {bookingForDropoffInspection.vehicle?.registration} - {bookingForDropoffInspection.vehicle?.make} {bookingForDropoffInspection.vehicle?.model}</p>
            </div>

            {loadingDropoffInspection ? (
              <div className="inspection-loading">
                <div className="spinner"></div>
                <p>Loading inspection data...</p>
              </div>
            ) : dropoffInspectionData ? (
              <div className="inspection-details">
                <div className="inspection-section">
                  <h4>Inspection Details</h4>
                  <div className="inspection-grid">
                    <div className="inspection-item">
                      <span className="inspection-label">Customer Name</span>
                      <span className="inspection-value">{dropoffInspectionData.customer_name || 'Not recorded'}</span>
                    </div>
                    <div className="inspection-item">
                      <span className="inspection-label">Signed Date</span>
                      <span className="inspection-value">{dropoffInspectionData.signed_date ? formatDateTimeUK(dropoffInspectionData.signed_date) : '-'}</span>
                    </div>
                    <div className="inspection-item">
                      <span className="inspection-label">Mileage</span>
                      <span className="inspection-value">{dropoffInspectionData.mileage ? `${dropoffInspectionData.mileage.toLocaleString()} miles` : 'Not recorded'}</span>
                    </div>
                    <div className="inspection-item">
                      <span className="inspection-label">Recorded</span>
                      <span className="inspection-value">{dropoffInspectionData.created_at ? formatDateTimeUK(dropoffInspectionData.created_at) : '-'}</span>
                    </div>
                  </div>
                </div>

                {dropoffInspectionData.vehicle_inspection_read && (
                  <div className="inspection-section">
                    <h4>Terms Acknowledgement</h4>
                    <p className="inspection-acknowledged">Customer confirmed they read the vehicle inspection terms.</p>
                  </div>
                )}

                {dropoffInspectionData.notes && (
                  <div className="inspection-section">
                    <h4>Notes</h4>
                    <p className="inspection-notes">{dropoffInspectionData.notes}</p>
                  </div>
                )}

                {dropoffInspectionData.photos && Object.keys(dropoffInspectionData.photos).length > 0 && (
                  <div className="inspection-section">
                    <h4>Photos</h4>
                    <div className="inspection-photos">
                      {PHOTO_SLOTS.map(slot => (
                        dropoffInspectionData.photos[slot.key] && (
                          <div key={slot.key} className="inspection-photo">
                            <span className="photo-label">{slot.label}</span>
                            <img src={dropoffInspectionData.photos[slot.key]} alt={slot.label} />
                          </div>
                        )
                      ))}
                    </div>
                  </div>
                )}

                {dropoffInspectionData.signature && (
                  <div className="inspection-section">
                    <h4>Customer Signature</h4>
                    <div className="inspection-signature">
                      <img src={dropoffInspectionData.signature} alt="Customer Signature" />
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="inspection-empty">
                <p>No drop-off vehicle inspection found for this booking.</p>
                <p className="inspection-empty-hint">The drop-off inspection may not have been completed yet.</p>
              </div>
            )}

            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={closeDropoffInspectionModal}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Admin
