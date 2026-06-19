import { useState, useEffect, useMemo, Fragment, useRef } from 'react'
import { useNavigate, Link, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import BookingCalendar from './components/BookingCalendar'
import { formatDestination } from './utils/formatDestination'
import BookingLocationMap from './components/BookingLocationMap'
import RosterCalendar from './components/RosterCalendar'
import CalendarSection from './components/admin/CalendarSection'
import ManualBookingSection from './components/admin/ManualBookingSection'
import PayrollSection from './components/admin/PayrollSection'
import TestResultsSection from './components/admin/qa/TestResultsSection'
import ConnectionPoolSection from './components/admin/qa/ConnectionPoolSection'
import AuditLogsSection from './components/admin/qa/AuditLogsSection'
import ErrorLogsSection from './components/admin/qa/ErrorLogsSection'
import SqlInterfaceSection from './components/admin/qa/SqlInterfaceSection'
import RosterPlannerSection from './components/admin/qa/RosterPlannerSection'
import LeadsSection from './components/admin/LeadsSection'
import CustomersSection from './components/admin/CustomersSection'
import TestimonialsSection from './components/admin/TestimonialsSection'
import PromoModalsSection from './components/admin/PromoModalsSection'
import PricingSection from './components/admin/PricingSection'
import UsersSection from './components/admin/UsersSection'
import FlightsSection from './components/admin/FlightsSection'
import MessagesSection from './components/admin/MessagesSection'
import { taxStatusClass, motStatusClass, shouldShowAlert, formatIsoDateUk } from './dvlaCompliance'
import { resolveArrivalDate } from './utils/arrivalDate'
import './Admin.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const REFERRALS_PAGE_SIZE_OPTIONS = [10, 25, 50, 100]
const REFERRALS_DEFAULT_PAGE_SIZE = 10

const formatUkTimestampInput = (date = new Date()) => {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/London',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(date)
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]))
  return `${values.day}/${values.month}/${values.year} ${values.hour}:${values.minute}`
}

const parseUkTimestampInput = (value) => {
  const match = String(value || '').trim().match(/^(\d{2})\/(\d{2})\/(\d{4})\s+(\d{2}):(\d{2})$/)
  if (!match) return null
  const [, dd, mm, yyyy, hh, min] = match
  const day = parseInt(dd, 10)
  const month = parseInt(mm, 10)
  const year = parseInt(yyyy, 10)
  const hour = parseInt(hh, 10)
  const minute = parseInt(min, 10)
  if (month < 1 || month > 12 || day < 1 || day > 31 || hour > 23 || minute > 59) return null
  const checkDate = new Date(year, month - 1, day)
  if (
    checkDate.getFullYear() !== year ||
    checkDate.getMonth() !== month - 1 ||
    checkDate.getDate() !== day
  ) {
    return null
  }
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}T${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:00`
}

const TESTIMONIAL_THEME_DEFINITIONS = [
  ['Recommend', [/\bhighly recommend(?:ed)?\b/i, /\brecommend(?:ed|ation)?\b/i]],
  ['Easy', [/\beasy\b/i, /\bsimple\b/i, /\bstraightforward\b/i, /\bdoddle\b/i]],
  ['Friendly Team', [/\bfriendly\b/i, /\bhelpful\b/i, /\blovely\b/i, /\bpolite\b/i, /\bcourteous\b/i, /\bteam\b/i, /\bstaff\b/i, /\bdriver(?:s)?\b/i]],
  ['Stress Free', [/\bstress[-\s]?free\b/i, /\bhassle[-\s]?free\b/i, /\bno hassle\b/i, /\bworry[-\s]?free\b/i, /\bno fuss\b/i, /\bpeace of mind\b/i]],
  ['On Time', [/\bon[-\s]?time\b/i, /\bpunctual\b/i, /\bprompt\b/i, /\btimely\b/i, /\bwaiting for us\b/i, /\bready when we arrived\b/i]],
  ['Professional', [/\bprofessional\b/i, /\befficient\b/i, /\breliable\b/i, /\bcommunicative\b/i, /\bresponsive\b/i, /\battentive\b/i, /\bwell[-\s]?organised\b/i, /\bwell[-\s]?organized\b/i]],
  ['Good Value', [/\bgood value\b/i, /\bgreat value\b/i, /\bexcellent value\b/i, /\bvalue for money\b/i, /\bgood price\b/i, /\bgreat price\b/i, /\baffordable\b/i, /\bcheaper\b/i, /\bworth it\b/i]],
  ['Safe & Secure', [/\bsafe\b/i, /\bsecure\b/i, /\bsecurity\b/i, /\bclean\b/i, /\bconfident\b/i, /\breassured\b/i]],
  ['Use Again', [/\buse again\b/i, /\bused again\b/i, /\bwill use\b/i, /\bwould use\b/i, /\bdefinitely use again\b/i, /\bwill be back\b/i, /\bcoming back\b/i]],
  ['Smooth Service', [/\bsmooth\b/i, /\bseamless\b/i, /\bconvenient\b/i, /\bflawless\b/i, /\bno issues\b/i, /\bno problems\b/i, /\bwithout issue\b/i]],
  ['Fantastic', [/\bfantastic\b/i, /\bamazing\b/i, /\bbrilliant\b/i, /\bexcellent\b/i, /\bgreat\b/i, /\bperfect\b/i, /\boutstanding\b/i, /\bincredible\b/i, /\bsuperb\b/i, /\btop[-\s]?notch\b/i, /\bfirst[-\s]?class\b/i, /\bimpressed\b/i, /\bbest\b/i, /\bspot on\b/i]],
]

const detectTestimonialThemes = (reviewText, maxThemes = 10) => {
  if (!reviewText?.trim()) return []
  const themes = []
  for (const [theme, patterns] of TESTIMONIAL_THEME_DEFINITIONS) {
    if (patterns.some(pattern => pattern.test(reviewText))) {
      themes.push(theme)
    }
    if (themes.length >= maxThemes) break
  }
  return themes
}

// Sidebar navigation structure
const NAV_STRUCTURE = [
  {
    category: 'Operations',
    icon: '📋',
    items: [
      { id: 'bookings', label: 'Bookings' },
      { id: 'calendar', label: 'Calendar' },
      { id: 'manual-booking', label: 'Manual Booking' },
      { id: 'flights', label: 'Flights' },
      { id: 'messages', label: 'Messages' },
    ]
  },
  {
    category: 'Staff',
    icon: '👥',
    items: [
      { id: 'payroll', label: 'Payroll' },
      { id: 'users', label: 'Users' },
    ]
  },
  {
    category: 'Customers',
    icon: '🧑‍💼',
    items: [
      { id: 'customers', label: 'Customers' },
      { id: 'leads', label: 'Abandoned Leads' },
    ]
  },
  {
    category: 'Marketing',
    icon: '📢',
    items: [
      { id: 'marketing', label: 'Subscribers' },
      { id: 'promotions', label: 'Promotions' },
      { id: 'campaigns', label: 'Email Campaigns' },
      { id: 'referrals', label: 'Referrals' },
      { id: 'sources', label: 'Sources' },
    ]
  },
  {
    category: 'Reports',
    icon: '📊',
    items: [
      { id: 'reports-growth', label: 'Booking Growth' },
      { id: 'reports-financial', label: 'Financial' },
      { id: 'reports-sessions', label: 'Session Tracking' },
      { id: 'reports-analytics', label: 'Abandoned Carts' },
      { id: 'reports-forecast', label: 'Bookings Forecast' },
      { id: 'reports-occupancy', label: 'Occupancy' },
      { id: 'reports-routes', label: 'Popular Routes' },
      { id: 'reports-map', label: 'Location Maps' },
    ]
  },
  {
    category: 'Settings',
    icon: '⚙️',
    items: [
      { id: 'pricing', label: 'Pricing' },
      { id: 'testimonials', label: 'Testimonials' },
      { id: 'promo-modals', label: 'Promo Modals' },
    ]
  },
  {
    category: 'QA',
    icon: '🔧',
    restrictToUserIds: [1, 2],  // Only visible to these user IDs
    items: [
      { id: 'qa-tests', label: 'Test Results' },
      { id: 'qa-connection-pool', label: 'Connection Pool' },
      { id: 'qa-audit', label: 'Audit Logs' },
      { id: 'qa-errors', label: 'Error Logs' },
      { id: 'qa-sql', label: 'SQL Interface' },
      { id: 'qa-roster-planner', label: 'Roster Planner' },
    ]
  },
]

const ADMIN_ROUTE_BY_ITEM_ID = {
  bookings: '/admin/operations/bookings',
  calendar: '/admin/operations/calendar',
  'manual-booking': '/admin/operations/manual-booking',
  flights: '/admin/operations/flights',
  messages: '/admin/operations/messages',
  payroll: '/admin/staff/payroll',
  users: '/admin/staff/users',
  customers: '/admin/customers/customers',
  leads: '/admin/customers/abandoned-leads',
  marketing: '/admin/marketing/subscribers',
  promotions: '/admin/marketing/promotions',
  campaigns: '/admin/marketing/email-campaigns',
  referrals: '/admin/marketing/referrals',
  sources: '/admin/marketing/sources',
  'reports-growth': '/admin/reports/booking-growth',
  'reports-financial': '/admin/reports/financial',
  'reports-sessions': '/admin/reports/session-tracking',
  'reports-analytics': '/admin/reports/abandoned-carts',
  'reports-forecast': '/admin/reports/bookings-forecast',
  'reports-occupancy': '/admin/reports/occupancy',
  'reports-routes': '/admin/reports/popular-routes',
  'reports-map': '/admin/reports/location-maps',
  pricing: '/admin/settings/pricing',
  testimonials: '/admin/settings/testimonials',
  'promo-modals': '/admin/settings/promo-modals',
  'qa-tests': '/admin/qa/test-results',
  'qa-connection-pool': '/admin/qa/connection-pool',
  'qa-audit': '/admin/qa/audit-logs',
  'qa-errors': '/admin/qa/error-logs',
  'qa-sql': '/admin/qa/sql-interface',
  'qa-roster-planner': '/admin/qa/roster-planner',
}

const ADMIN_ITEM_BY_ROUTE = Object.fromEntries(
  Object.entries(ADMIN_ROUTE_BY_ITEM_ID).map(([itemId, route]) => [route, itemId])
)

const ADMIN_DEFAULT_ITEM_ID = 'bookings'
const ADMIN_DEFAULT_ROUTE = ADMIN_ROUTE_BY_ITEM_ID[ADMIN_DEFAULT_ITEM_ID]

const ADMIN_ITEM_META = NAV_STRUCTURE.flatMap(category =>
  category.items.map(item => ({
    itemId: item.id,
    itemLabel: item.label,
    category: category.category,
    route: ADMIN_ROUTE_BY_ITEM_ID[item.id],
    restrictToUserIds: category.restrictToUserIds,
  }))
)

const ADMIN_ITEM_META_BY_ID = Object.fromEntries(
  ADMIN_ITEM_META.map(item => [item.itemId, item])
)

const getAdminItemIdForPath = (pathname) => {
  const normalisedPath = pathname.replace(/\/+$/, '') || '/admin'
  if (normalisedPath === '/admin') return ADMIN_DEFAULT_ITEM_ID
  return ADMIN_ITEM_BY_ROUTE[normalisedPath] || null
}

const getAdminRouteForItem = (itemId) => ADMIN_ROUTE_BY_ITEM_ID[itemId] || ADMIN_DEFAULT_ROUTE

const getAdminSelectionForItem = (itemId) => {
  const marketingSubTabs = {
    marketing: 'subscribers',
    promotions: 'promotions',
    campaigns: 'campaigns',
    referrals: 'referrals',
    sources: 'sources',
  }
  const reportsSubTabs = {
    'reports-growth': 'growth',
    'reports-occupancy': 'occupancy',
    'reports-routes': 'popular',
    'reports-map': 'map',
    'reports-financial': 'financial',
    'reports-sessions': 'sessions',
    'reports-analytics': 'analytics',
    'reports-forecast': 'forecast',
  }

  if (marketingSubTabs[itemId]) {
    return { activeTab: 'marketing', marketingSubTab: marketingSubTabs[itemId] }
  }
  if (reportsSubTabs[itemId]) {
    return { activeTab: 'reports', reportsSubTab: reportsSubTabs[itemId] }
  }
  return { activeTab: itemId }
}

const getAdminItemIdForSelection = (activeTab, marketingSubTab, reportsSubTab) => {
  if (activeTab === 'marketing') {
    const marketingItemBySubTab = {
      subscribers: 'marketing',
      promotions: 'promotions',
      campaigns: 'campaigns',
      referrals: 'referrals',
      sources: 'sources',
    }
    return marketingItemBySubTab[marketingSubTab] || 'marketing'
  }
  if (activeTab === 'reports') {
    const reportsItemBySubTab = {
      growth: 'reports-growth',
      occupancy: 'reports-occupancy',
      popular: 'reports-routes',
      map: 'reports-map',
      financial: 'reports-financial',
      sessions: 'reports-sessions',
      analytics: 'reports-analytics',
      forecast: 'reports-forecast',
    }
    return reportsItemBySubTab[reportsSubTab] || 'reports-growth'
  }
  return activeTab
}

const getDefaultRouteForCategory = (categoryName) => {
  const category = NAV_STRUCTURE.find(cat => cat.category === categoryName)
  const firstItem = category?.items?.[0]
  return firstItem ? getAdminRouteForItem(firstItem.id) : ADMIN_DEFAULT_ROUTE
}

// Photo slots - must match Employee.jsx
const PHOTO_SLOTS = [
  { key: 'front', label: 'Front' },
  { key: 'rear', label: 'Rear' },
  { key: 'driver_side', label: 'Driver Side' },
  { key: 'passenger_side', label: 'Passenger Side' },
  { key: 'additional_1', label: 'Additional 1' },
  { key: 'additional_2', label: 'Additional 2' },
]

// Get UK datetime format (DD/MM/YYYY HH:MM) for 2 hours ago (for QA logs default filter)
const getTwoHoursAgoUkDateTime = () => {
  const now = new Date()
  const twoHoursAgo = new Date(now.getTime() - 2 * 60 * 60 * 1000)
  // Use Intl.DateTimeFormat to properly format in UK timezone regardless of user's locale
  const formatter = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/London',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  })
  const parts = formatter.formatToParts(twoHoursAgo)
  const day = parts.find(p => p.type === 'day').value
  const month = parts.find(p => p.type === 'month').value
  const year = parts.find(p => p.type === 'year').value
  const hour = parts.find(p => p.type === 'hour').value
  const minute = parts.find(p => p.type === 'minute').value
  return `${day}/${month}/${year} ${hour}:${minute}`
}

// Convert UK datetime (DD/MM/YYYY HH:MM) to ISO format for API (converts to UTC)
const ukDateTimeToIso = (ukDateTime) => {
  if (!ukDateTime) return ''
  // Handle "DD/MM/YYYY HH:MM" format
  const parts = ukDateTime.trim().split(' ')
  if (parts.length < 1) return ''
  const datePart = parts[0]
  const timePart = parts[1] || '00:00'
  const [day, month, year] = datePart.split('/')
  // Validate format - must have day, month, year with reasonable values
  if (!day || !month || !year) return ''
  // Validate year is 4 digits and reasonable (2020-2099)
  if (!/^\d{4}$/.test(year) || parseInt(year) < 2020 || parseInt(year) > 2099) return ''
  // Validate month is 1-12
  if (!/^\d{1,2}$/.test(month) || parseInt(month) < 1 || parseInt(month) > 12) return ''
  // Validate day is 1-31
  if (!/^\d{1,2}$/.test(day) || parseInt(day) < 1 || parseInt(day) > 31) return ''

  // Create a date object interpreting the input as UK time
  // Format: YYYY-MM-DDTHH:MM with explicit UK timezone
  const ukDateStr = `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}T${timePart}:00`

  // Use Intl to determine UK offset for this specific date (handles BST/GMT)
  const tempDate = new Date(ukDateStr + 'Z') // Parse as UTC temporarily
  const ukFormatter = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/London',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false
  })

  // Get the UK offset by comparing UTC and UK representations
  // Create the date as if it were UK time, then convert to UTC
  const [hours, minutes] = timePart.split(':').map(Number)

  // Create date in UK timezone and get UTC equivalent
  // Trick: Create a date, format it in UK tz, compare to get offset
  const testDate = new Date(Date.UTC(parseInt(year), parseInt(month) - 1, parseInt(day), hours, minutes || 0))
  const ukParts = ukFormatter.formatToParts(testDate)
  const ukHour = parseInt(ukParts.find(p => p.type === 'hour').value)
  const utcHour = testDate.getUTCHours()
  const ukOffset = ukHour - utcHour // Positive means UK is ahead of UTC

  // Adjust: if user entered UK time, we need to subtract the offset to get UTC
  const utcDate = new Date(Date.UTC(parseInt(year), parseInt(month) - 1, parseInt(day), hours - ukOffset, minutes || 0))

  return utcDate.toISOString()
}

// UK date format helpers (DD/MM/YYYY)
const isoToUkDate = (isoDate) => {
  if (!isoDate) return ''
  // Handle both "YYYY-MM-DD" and "YYYY-MM-DDTHH:MM:SS" formats
  const datePart = isoDate.split('T')[0]
  const [year, month, day] = datePart.split('-')
  if (!year || !month || !day) return ''
  return `${day}/${month}/${year}`
}

const ukToIsoDate = (ukDate) => {
  if (!ukDate) return ''
  const parts = ukDate.split('/')
  if (parts.length !== 3) return ''
  const [day, month, year] = parts
  return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`
}

// Auto-format date input as DD/MM/YYYY
const formatDateInput = (value) => {
  // Remove non-digits
  const digits = value.replace(/\D/g, '')

  // Build formatted string
  let formatted = ''
  if (digits.length > 0) {
    formatted = digits.slice(0, 2)
  }
  if (digits.length > 2) {
    formatted += '/' + digits.slice(2, 4)
  }
  if (digits.length > 4) {
    formatted += '/' + digits.slice(4, 8)
  }

  return formatted
}

// Parse UK date string (DD/MM/YYYY) to Date object
const parseUkDate = (ukDateStr) => {
  if (!ukDateStr || ukDateStr.length !== 10) return null
  const [day, month, year] = ukDateStr.split('/')
  if (!day || !month || !year) return null
  const date = new Date(parseInt(year), parseInt(month) - 1, parseInt(day))
  return isNaN(date.getTime()) ? null : date
}

// Format Date object to UK date string (DD/MM/YYYY)
const dateToUkString = (date) => {
  if (!date) return ''
  const day = String(date.getDate()).padStart(2, '0')
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const year = date.getFullYear()
  return `${day}/${month}/${year}`
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
    'word_of_mouth': 'Word of Mouth',
    'leaflet': 'Leaflet',
    'tv': 'TV',
    'radio': 'Radio',
    'expectations_travel': 'Expectations Travel',
    'other': 'Other',
  }
  return sourceMap[source] || source
}

function Admin() {
  const { user, token, loading, isAuthenticated, isAdmin, logout, authFetch } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const requestedInitialAdminItemId = getAdminItemIdForPath(location.pathname) || ADMIN_DEFAULT_ITEM_ID
  const requestedInitialAdminItemMeta = ADMIN_ITEM_META_BY_ID[requestedInitialAdminItemId]
  const initialRouteAllowed = requestedInitialAdminItemMeta && (
    !requestedInitialAdminItemMeta.restrictToUserIds ||
    requestedInitialAdminItemMeta.restrictToUserIds.includes(user?.id)
  )
  const initialAdminItemId = initialRouteAllowed ? requestedInitialAdminItemId : ADMIN_DEFAULT_ITEM_ID
  const initialAdminSelection = getAdminSelectionForItem(initialAdminItemId)

  const [activeTab, setActiveTab] = useState(initialAdminSelection.activeTab)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => (
    typeof window !== 'undefined' &&
    window.matchMedia?.('(max-width: 768px)').matches
  ))
  const [expandedCategories, setExpandedCategories] = useState(() => {
    // Expand the category containing the current tab
    const expanded = {}
    NAV_STRUCTURE.forEach(cat => {
      if (cat.items.some(item => item.id === initialAdminItemId)) {
        expanded[cat.category] = true
      }
    })
    return expanded
  })
  const [bookings, setBookings] = useState([])
  const [bookingsLoadAll, setBookingsLoadAll] = useState(false)
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
    dropoff_date: '',
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
  const [sendingParkingUpdateId, setSendingParkingUpdateId] = useState(null)
  const [showResendModal, setShowResendModal] = useState(false)
  const [bookingToResend, setBookingToResend] = useState(null)
  const [showRefundModal, setShowRefundModal] = useState(false)
  const [bookingToRefund, setBookingToRefund] = useState(null)
  const [refundReason, setRefundReason] = useState('requested_by_customer')
  const [processingRefund, setProcessingRefund] = useState(false)
  const [refundModalError, setRefundModalError] = useState('')
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
  const [marketingSubTab, setMarketingSubTab] = useState(initialAdminSelection.marketingSubTab || 'subscribers') // 'subscribers', 'promotions', 'campaigns', 'referrals', or 'sources'
  const [referralsDashboard, setReferralsDashboard] = useState({ stats: {}, customers: [], code_usage: [] })
  const [loadingReferrals, setLoadingReferrals] = useState(false)
  const [referralsFilter, setReferralsFilter] = useState('all')
  const [referralsCustomerSearch, setReferralsCustomerSearch] = useState('')
  const [referralsCustomerSearchQuery, setReferralsCustomerSearchQuery] = useState('')
  const [referralsCustomerOffset, setReferralsCustomerOffset] = useState(0)
  const [referralsCustomerPageSize, setReferralsCustomerPageSize] = useState(REFERRALS_DEFAULT_PAGE_SIZE)
  const [referralsUsageFilter, setReferralsUsageFilter] = useState('all')
  const [referralsUsageSearch, setReferralsUsageSearch] = useState('')
  const [referralsUsageSearchQuery, setReferralsUsageSearchQuery] = useState('')
  const [referralsUsageOffset, setReferralsUsageOffset] = useState(0)
  const [referralsUsagePageSize, setReferralsUsagePageSize] = useState(REFERRALS_DEFAULT_PAGE_SIZE)
  const [referralDashboardAction, setReferralDashboardAction] = useState(null)
  const [manualReferralInvite, setManualReferralInvite] = useState({ first_name: '', last_name: '', email: '' })
  const [sendingManualReferralInvite, setSendingManualReferralInvite] = useState(false)
  const [manualReferralInviteMessage, setManualReferralInviteMessage] = useState('')
  const referralDashboardActionInFlightRef = useRef(false)
  const referralUsageTableRef = useRef(null)

  // Email Campaigns state
  const [campaigns, setCampaigns] = useState([])
  const [loadingCampaigns, setLoadingCampaigns] = useState(false)
  const [showCreateCampaign, setShowCreateCampaign] = useState(false)
  const [newCampaign, setNewCampaign] = useState({ subject: '', message: '', promo_code_id: null, subscriber_ids: [] })
  const [creatingCampaign, setCreatingCampaign] = useState(false)
  const [availablePromoCodes, setAvailablePromoCodes] = useState([])
  const [campaignPreview, setCampaignPreview] = useState(null)
  const [sendingCampaign, setSendingCampaign] = useState(false)
  const [editingCampaignId, setEditingCampaignId] = useState(null)
  const [deletingCampaignId, setDeletingCampaignId] = useState(null)
  const [campaignConfirm, setCampaignConfirm] = useState(null) // { action: 'delete' | 'send', id }
  const [campaignToast, setCampaignToast] = useState(null) // { type: 'success' | 'error', message }

  // Promotions state
  const [promotions, setPromotions] = useState([])
  const [loadingPromotions, setLoadingPromotions] = useState(false)
  const [showCreatePromotion, setShowCreatePromotion] = useState(false)
  const [newPromotion, setNewPromotion] = useState({ name: '', description: '', discount_percent: 10, discount_type: null, total_codes: 10, code_prefix: '', custom_code: '', expiry_date: '', expiry_time: '', max_uses: '' })
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
  const [generateCodesExpiryDate, setGenerateCodesExpiryDate] = useState('')
  const [generateCodesExpiryTime, setGenerateCodesExpiryTime] = useState('')
  const [generateCodesMaxUses, setGenerateCodesMaxUses] = useState('')
  // Promo code expiry state
  const [showExpiryModal, setShowExpiryModal] = useState(false)
  const [expiryModalData, setExpiryModalData] = useState(null) // { promotionId, code } or { promotionId, codes: [] } for bulk
  const [expiryDate, setExpiryDate] = useState('') // DD/MM/YYYY
  const [expiryTime, setExpiryTime] = useState('') // HH:MM
  const [updatingExpiry, setUpdatingExpiry] = useState(false)
  const [selectedCodes, setSelectedCodes] = useState({}) // { [promotionId]: Set of code ids }

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
  const [selectedCustomer, setSelectedCustomer] = useState(null)
  const [showCustomerModal, setShowCustomerModal] = useState(false)
  const [loadingCustomerDetail, setLoadingCustomerDetail] = useState(false)
  const [addingVehicle, setAddingVehicle] = useState(false)
  const [showAddVehicleForm, setShowAddVehicleForm] = useState(false)
  const [newVehicleForm, setNewVehicleForm] = useState({ registration: '', make: '', model: '', colour: '' })
  const [vehicleLookupLoading, setVehicleLookupLoading] = useState(false)

  // Swap vehicle state
  const [showSwapVehicleModal, setShowSwapVehicleModal] = useState(false)
  const [swappingVehicle, setSwappingVehicle] = useState(false)
  const [customerVehiclesForSwap, setCustomerVehiclesForSwap] = useState([])
  const [loadingCustomerVehicles, setLoadingCustomerVehicles] = useState(false)
  const [swapConfirmVehicle, setSwapConfirmVehicle] = useState(null)
  const [bookingForSwap, setBookingForSwap] = useState(null)

  // Pricing settings state - anchor pricing with daily increment
  const [pricing, setPricing] = useState({
    days_1_4_price: 65,       // 1-4 days anchor
    week1_base_price: 85,     // 7 days anchor
    week2_base_price: 150,    // 14 days anchor
    daily_increment: 8,       // Daily increment between anchors
    tier_increment: 5,        // Early -> Standard -> Late increment
    peak_day_increment: 0,    // Peak day increment (Fri/Sat drop-off, Sun/Mon/Tue pickup)
    show_price_range: false,  // False = "From £X", True = "£X-£Y" range
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
  const [userForm, setUserForm] = useState({ first_name: '', last_name: '', email: '', phone: '', is_admin: false, is_active: true, driver_type: 'fleet' })
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

  // SMS Messages state
  const [messagesSubTab, setMessagesSubTab] = useState('inbox') // 'inbox', 'sent', 'templates', 'bulk'
  const [smsMessages, setSmsMessages] = useState([])
  const [smsTemplates, setSmsTemplates] = useState([])
  const [smsStats, setSmsStats] = useState(null)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [loadingTemplates, setLoadingTemplates] = useState(false)
  const [messagesMessage, setMessagesMessage] = useState('')
  const [selectedTemplate, setSelectedTemplate] = useState(null)
  const [showSendSmsModal, setShowSendSmsModal] = useState(false)
  const [sendSmsForm, setSendSmsForm] = useState({ phone: '', content: '', booking_id: '', customer_id: '' })
  const [sendingSms, setSendingSms] = useState(false)
  const [smsBookingSearch, setSmsBookingSearch] = useState('')
  const [smsBookingResults, setSmsBookingResults] = useState([])
  const [searchingSmsBookings, setSearchingSmsBookings] = useState(false)
  const [selectedSmsBooking, setSelectedSmsBooking] = useState(null)
  const [showBulkSmsModal, setShowBulkSmsModal] = useState(false)
  const [bulkSmsForm, setBulkSmsForm] = useState({ template_id: '', filter_status: 'confirmed', custom_content: '' })
  const [sendingBulkSms, setSendingBulkSms] = useState(false)
  const [bulkSmsPreview, setBulkSmsPreview] = useState(null)
  const [showEditTemplateModal, setShowEditTemplateModal] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState(null)
  const [savingTemplate, setSavingTemplate] = useState(false)
  const [showCreateTemplateModal, setShowCreateTemplateModal] = useState(false)
  const [newTemplate, setNewTemplate] = useState({ name: '', content: '', description: '', is_active: true, trigger_event: null })
  const [creatingTemplate, setCreatingTemplate] = useState(false)
  const [deletingTemplateId, setDeletingTemplateId] = useState(null)
  const [templateToDelete, setTemplateToDelete] = useState(null)
  const [expandedMessageId, setExpandedMessageId] = useState(null)
  const [resendingMessageId, setResendingMessageId] = useState(null)
  const [deletingMessageId, setDeletingMessageId] = useState(null)
  const [messageToDelete, setMessageToDelete] = useState(null)
  const [smsDirectionFilter, setSmsDirectionFilter] = useState('inbound') // 'inbound', 'outbound'
  const [smsStatusFilter, setSmsStatusFilter] = useState('all') // 'all', 'pending', 'sent', 'delivered', 'failed'
  // SMS Drafts state
  const [smsDrafts, setSmsDrafts] = useState([])
  const [loadingDrafts, setLoadingDrafts] = useState(false)
  const [savingDraft, setSavingDraft] = useState(false)
  const [editingDraft, setEditingDraft] = useState(null)
  const [sendingDraftId, setSendingDraftId] = useState(null)
  const [deletingDraftId, setDeletingDraftId] = useState(null)
  // SMS Threads state (conversation view)
  const [smsThreads, setSmsThreads] = useState([])
  const [loadingThreads, setLoadingThreads] = useState(false)
  const [selectedThread, setSelectedThread] = useState(null)
  const [threadMessages, setThreadMessages] = useState([])
  const [loadingConversation, setLoadingConversation] = useState(false)
  const [replyContent, setReplyContent] = useState('')
  const [sendingReply, setSendingReply] = useState(false)
  const [selectedThreads, setSelectedThreads] = useState(new Set())
  const [deletingThreads, setDeletingThreads] = useState(false)
  const conversationEndRef = useRef(null)

  // Bookings-tab scroll-to-top button: page can grow very long, so a
  // floating chevron lets the admin jump back to the top.
  const [bookingsScrollTopVisible, setBookingsScrollTopVisible] = useState(false)

  // SMS textarea refs for variable insertion
  const sendSmsTextareaRef = useRef(null)
  const newTemplateTextareaRef = useRef(null)
  const editTemplateTextareaRef = useRef(null)

  // Available SMS variables
  const smsVariables = [
    { label: 'First Name', value: '{{first_name}}' },
    { label: 'Last Name', value: '{{last_name}}' },
    { label: 'Booking Ref', value: '{{booking_reference}}' },
    { label: 'Drop-off Date', value: '{{dropoff_date}}' },
    { label: 'Drop-off Time', value: '{{dropoff_time}}' },
    { label: 'Pickup Date', value: '{{pickup_date}}' },
    { label: 'Pickup Time', value: '{{pickup_time}}' },
    { label: 'Destination', value: '{{destination}}' },
    { label: 'Vehicle Reg', value: '{{vehicle_reg}}' },
    { label: 'Total Price', value: '{{total_price}}' },
    { label: 'Days', value: '{{days}}' },
    { label: 'Google Review', value: '{{google_review_link}}' },
  ]

  // Reports / Booking Locations state
  const [mapType, setMapType] = useState('bookings') // 'bookings' or 'origins'
  const [bookingLocations, setBookingLocations] = useState([])
  const [originLocations, setOriginLocations] = useState([])
  const [skippedBookings, setSkippedBookings] = useState([])
  const [totalBookings, setTotalBookings] = useState(0)
  const [totalCustomers, setTotalCustomers] = useState(0)
  const [loadingLocations, setLoadingLocations] = useState(false)

  // Booking stats state (for growth charts)
  const [reportsSubTab, setReportsSubTab] = useState(initialAdminSelection.reportsSubTab || 'growth') // 'growth', 'map', or 'occupancy'
  const [bookingStats, setBookingStats] = useState(null)
  const [loadingStats, setLoadingStats] = useState(false)
  const [statsChartType, setStatsChartType] = useState('monthly') // 'daily', 'weekly', 'monthly', 'cumulative'
  const [weeklyPageIndex, setWeeklyPageIndex] = useState(0) // For weekly navigation (0 = most recent)
  const [expandedDailyMonths, setExpandedDailyMonths] = useState({}) // For daily collapsible months

  // Occupancy report state
  const [occupancyData, setOccupancyData] = useState(null)
  const [loadingOccupancy, setLoadingOccupancy] = useState(false)
  const [occupancyView, setOccupancyView] = useState('daily') // 'daily', 'weekly', 'monthly'
  const [secondaryReport, setSecondaryReport] = useState(null)
  const [loadingSecondaryReport, setLoadingSecondaryReport] = useState(false)
  const [secondaryGroup, setSecondaryGroup] = useState('daily') // grouping for the P2 panel
  const [occupancyChartOffset, setOccupancyChartOffset] = useState(0) // 0 = centered on today, negative = past, positive = future
  const todayInputValue = formatUkTimestampInput()
  const [capacitySettings, setCapacitySettings] = useState(null)
  const [loadingCapacitySettings, setLoadingCapacitySettings] = useState(false)
  const [savingCapacitySettings, setSavingCapacitySettings] = useState(false)
  const [capacityMessage, setCapacityMessage] = useState('')
  const [capacityForm, setCapacityForm] = useState({
    effective_from: todayInputValue,
    total_spaces: '75',
    online_spaces: '73',
  })
  const occupancyChartMaxPercent = useMemo(() => {
    if (!occupancyData?.data?.length) return 110
    const maxPercent = occupancyData.data.reduce((max, item) => {
      const percent = item.occupancy_percent || item.avg_occupancy_percent || 0
      const online = item.online_capacity || item.avg_online_capacity || occupancyData.online_capacity || occupancyData.max_capacity || 73
      const total = item.total_capacity || item.avg_total_capacity || occupancyData.total_capacity || online
      const totalRatio = online ? (total / online) * 100 : 100
      return Math.max(max, percent, totalRatio)
    }, 100)
    return Math.max(110, Math.ceil(maxPercent / 10) * 10)
  }, [occupancyData])

  // Popular airlines/destinations report state
  const [popularData, setPopularData] = useState(null)
  const [loadingPopular, setLoadingPopular] = useState(false)
  const [popularTop, setPopularTop] = useState(10) // 5, 10, 20

  // Fun facts state
  const [funFacts, setFunFacts] = useState(null)

  // Peak booking hours view state
  const [peakHoursView, setPeakHoursView] = useState('overall') // 'overall', 'Monday', 'Tuesday', etc.
  const [peakSearchView, setPeakSearchView] = useState('overall') // 'overall', 'Monday', 'Tuesday', etc.
  const [loadingFunFacts, setLoadingFunFacts] = useState(false)

  // Financial report state
  const [financialData, setFinancialData] = useState(null)
  const [loadingFinancial, setLoadingFinancial] = useState(false)
  const [financialFromDate, setFinancialFromDate] = useState('')
  const [financialToDate, setFinancialToDate] = useState('')
  const [financialStatusFilter, setFinancialStatusFilter] = useState('all')
  const [financialPromoFilter, setFinancialPromoFilter] = useState('all')
  const [expandedFinancialMonths, setExpandedFinancialMonths] = useState({})
  const [revenueChartType, setRevenueChartType] = useState('monthly') // 'daily', 'weekly', 'monthly', 'cumulative'
  const [revenueWeeklyPageIndex, setRevenueWeeklyPageIndex] = useState(0) // For weekly navigation
  const [expandedRevenueDailyMonths, setExpandedRevenueDailyMonths] = useState({}) // For daily collapsible months
  const [exportingFinancial, setExportingFinancial] = useState(false)
  const [editingFinancialBooking, setEditingFinancialBooking] = useState(null) // { id, grossPence, discountPence }
  const [savingFinancialOverride, setSavingFinancialOverride] = useState(false)

  // Session tracking report state
  const [sessionTrackingData, setSessionTrackingData] = useState(null)
  const [loadingSessionTracking, setLoadingSessionTracking] = useState(false)
  const [sessionTrackingPeriod, setSessionTrackingPeriod] = useState('daily') // 'daily', 'weekly', 'monthly'

  // Abandoned carts report state
  const [abandonedCartsData, setAbandonedCartsData] = useState(null)
  const [loadingAbandonedCarts, setLoadingAbandonedCarts] = useState(false)
  const [abandonedCartsPeriod, setAbandonedCartsPeriod] = useState('daily') // 'daily', 'weekly', 'monthly'

  // Bookings forecast report state
  const [forecastData, setForecastData] = useState(null)
  const [loadingForecast, setLoadingForecast] = useState(false)

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
  const [dbHealth, setDbHealth] = useState(null)
  const [loadingDbHealth, setLoadingDbHealth] = useState(false)
  const [dbPoolHistory, setDbPoolHistory] = useState(null)
  const [loadingPoolHistory, setLoadingPoolHistory] = useState(false)

  // QA Dashboard - Audit Logs state
  const [auditLogs, setAuditLogs] = useState([])
  const [auditLogsTotalCount, setAuditLogsTotalCount] = useState(0)
  const [loadingAuditLogs, setLoadingAuditLogs] = useState(false)
  const [auditLogsFilters, setAuditLogsFilters] = useState({
    search: '',
    booking_reference: '',
    event: '',
    date_from: getTwoHoursAgoUkDateTime(),
    date_to: '',
  })
  const [auditLogsOffset, setAuditLogsOffset] = useState(0)
  const [auditEventTypes, setAuditEventTypes] = useState([])
  const [auditLogsAutoRefresh, setAuditLogsAutoRefresh] = useState(false)

  // QA Dashboard - Error Logs state
  const [errorLogs, setErrorLogs] = useState([])
  const [errorLogsTotalCount, setErrorLogsTotalCount] = useState(0)
  const [loadingErrorLogs, setLoadingErrorLogs] = useState(false)
  const [errorLogsFilters, setErrorLogsFilters] = useState({
    search: '',
    booking_reference: '',
    severity: '',
    error_type: '',
    date_from: getTwoHoursAgoUkDateTime(),
    date_to: '',
  })
  const [errorLogsOffset, setErrorLogsOffset] = useState(0)
  const [errorSeverities, setErrorSeverities] = useState([])
  const [errorTypes, setErrorTypes] = useState([])

  // QA Dashboard - Expanded rows for details
  const [expandedAuditLog, setExpandedAuditLog] = useState(null)
  const [expandedErrorLog, setExpandedErrorLog] = useState(null)

  // QA Dashboard - SQL Interface state
  const [sqlSessionToken, setSqlSessionToken] = useState(null)
  const [sqlSessionExpires, setSqlSessionExpires] = useState(null)
  const [sqlPinModalOpen, setSqlPinModalOpen] = useState(false)
  const [sqlPin, setSqlPin] = useState('')
  const [sqlPinError, setSqlPinError] = useState('')
  const [sqlQuery, setSqlQuery] = useState('')
  const [sqlResults, setSqlResults] = useState(null)
  const [sqlError, setSqlError] = useState('')
  const [sqlLoading, setSqlLoading] = useState(false)
  // sqlConfirmModal removed 2026-05-30 PR 8: SQL console is read-only.
  // No more write confirmation flow.
  const [sqlHistory, setSqlHistory] = useState([])
  const [sqlTemplatesExpanded, setSqlTemplatesExpanded] = useState({})

  // SQL Templates organized by category
  const sqlTemplates = {
    'Customers': [
      { name: 'Find by ID (quick)', query: 'SELECT id, first_name, last_name, email, phone FROM customers WHERE id = {id}', note: 'Essential columns only' },
      { name: 'Find by ID (full)', query: 'SELECT * FROM customers WHERE id = {id}', note: 'All columns' },
      { name: 'Find by email (quick)', query: "SELECT id, first_name, last_name, email, phone FROM customers WHERE email = '{email}'", note: 'Essential columns only' },
      { name: 'Find by email (full)', query: "SELECT * FROM customers WHERE email = '{email}'", note: 'All columns' },
      { name: 'Recent customers', query: 'SELECT id, first_name, last_name, email, phone, created_at FROM customers ORDER BY created_at DESC LIMIT 20', note: 'Last 20' },
      { name: 'Search by name', query: "SELECT id, first_name, last_name, email, phone FROM customers WHERE first_name ILIKE '%{name}%' OR last_name ILIKE '%{name}%'", note: 'Partial match' },
      // Write templates (update contact, email, billing) removed 2026-05-30 PR 8.
    ],
    'Vehicles': [
      { name: 'Find by ID (quick)', query: 'SELECT id, customer_id, registration, make, model, colour FROM vehicles WHERE id = {id}', note: 'Essential columns' },
      { name: 'Find by ID (full)', query: 'SELECT * FROM vehicles WHERE id = {id}', note: 'All columns' },
      { name: 'Find by reg (quick)', query: "SELECT id, customer_id, registration, make, model, colour FROM vehicles WHERE registration = '{reg}'", note: 'Essential columns' },
      { name: 'Find by reg (full)', query: "SELECT * FROM vehicles WHERE registration = '{reg}'", note: 'All columns' },
      { name: 'Customer vehicles', query: 'SELECT id, registration, make, model, colour FROM vehicles WHERE customer_id = {id}', note: 'All vehicles for customer' },
      { name: 'Customer + Vehicle', query: 'SELECT c.id AS customer_id, c.first_name, c.last_name, c.email, v.id AS vehicle_id, v.registration, v.make, v.model, v.colour FROM customers c JOIN vehicles v ON v.customer_id = c.id WHERE c.id = {id}', note: 'Join by customer ID' },
      // Write templates (add vehicle, update vehicle) removed 2026-05-30 PR 8.
    ],
    'Bookings': [
      { name: 'Find by ID (quick)', query: 'SELECT id, reference, customer_id, vehicle_id, status, dropoff_date, pickup_date FROM bookings WHERE id = {id}', note: 'Essential columns' },
      { name: 'Find by ID (full)', query: 'SELECT * FROM bookings WHERE id = {id}', note: 'All columns' },
      { name: 'Find by ref (quick)', query: "SELECT id, reference, customer_id, vehicle_id, status, dropoff_date, pickup_date FROM bookings WHERE reference = '{ref}'", note: 'Essential columns' },
      { name: 'Find by ref (full)', query: "SELECT * FROM bookings WHERE reference = '{ref}'", note: 'All columns' },
      { name: 'Customer bookings', query: 'SELECT id, reference, vehicle_id, status, dropoff_date, pickup_date FROM bookings WHERE customer_id = {id} ORDER BY created_at DESC', note: 'All bookings for customer' },
      { name: 'Recent bookings', query: 'SELECT id, reference, status, dropoff_date, pickup_date, created_at FROM bookings ORDER BY created_at DESC LIMIT 20', note: 'Last 20' },
      { name: 'By date range', query: "SELECT id, reference, status, dropoff_date, pickup_date FROM bookings WHERE dropoff_date BETWEEN '{start}' AND '{end}' ORDER BY dropoff_date", note: 'YYYY-MM-DD format' },
      { name: "Today's drop-offs", query: "SELECT b.id, b.reference, c.first_name, c.last_name, v.registration, b.dropoff_time FROM bookings b JOIN customers c ON c.id = b.customer_id JOIN vehicles v ON v.id = b.vehicle_id WHERE b.status = 'confirmed' AND b.dropoff_date = CURRENT_DATE ORDER BY b.dropoff_time", note: 'Confirmed today' },
      { name: 'Customer + Vehicle + Booking', query: 'SELECT c.id AS cust_id, c.first_name, c.last_name, c.email, v.id AS veh_id, v.registration, b.id AS book_id, b.reference, b.status, b.dropoff_date, b.pickup_date FROM customers c JOIN vehicles v ON v.customer_id = c.id JOIN bookings b ON b.customer_id = c.id AND b.vehicle_id = v.id WHERE c.id = {id} ORDER BY b.created_at DESC', note: 'Full journey' },
      // Write templates (switch vehicle, update status/dates/times, add notes)
      // removed 2026-05-30 PR 8: SQL console is read-only. Writes route
      // through inline python3 -c scripts.
    ],
    'Payments': [
      { name: 'Find by booking (quick)', query: 'SELECT id, booking_id, amount_pence, status, stripe_payment_intent_id FROM payments WHERE booking_id = {id}', note: 'Essential columns' },
      { name: 'Find by booking (full)', query: 'SELECT * FROM payments WHERE booking_id = {id}', note: 'All columns' },
      { name: 'Find by Stripe ID', query: "SELECT id, booking_id, amount_pence, status FROM payments WHERE stripe_payment_intent_id = '{pi}'", note: 'By payment intent' },
      { name: 'Recent payments', query: 'SELECT p.id, b.reference, p.amount_pence, p.status, p.paid_at FROM payments p JOIN bookings b ON b.id = p.booking_id ORDER BY p.created_at DESC LIMIT 20', note: 'Last 20' },
      { name: 'Customer payments', query: 'SELECT b.reference, p.amount_pence, p.status, p.paid_at FROM payments p JOIN bookings b ON b.id = p.booking_id WHERE b.customer_id = {id} ORDER BY p.created_at DESC', note: 'All for customer' },
      // Write templates (update status, record refund) removed 2026-05-30 PR 8.
    ],
    'Promo Codes': [
      { name: 'Find code (quick)', query: "SELECT pc.id, pc.code, pc.is_used, pc.use_count, pr.discount_percent FROM promo_codes pc JOIN promotions pr ON pr.id = pc.promotion_id WHERE pc.code = '{code}'", note: 'Essential info' },
      { name: 'Find code (full)', query: "SELECT pc.*, pr.name AS promotion_name, pr.discount_percent FROM promo_codes pc JOIN promotions pr ON pr.id = pc.promotion_id WHERE pc.code = '{code}'", note: 'All columns' },
      { name: 'Customer promos', query: 'SELECT pc.code, pr.discount_percent, pc.is_used, pc.use_count FROM promo_codes pc JOIN promotions pr ON pr.id = pc.promotion_id WHERE pc.customer_id = {id}', note: 'By customer ID' },
      { name: 'Booking promo', query: 'SELECT pc.code, pr.discount_percent, pc.used_at FROM promo_codes pc JOIN promotions pr ON pr.id = pc.promotion_id WHERE pc.booking_id = {id}', note: 'By booking ID' },
      { name: 'Recent usage', query: 'SELECT pc.code, pr.discount_percent, pc.used_at, b.reference FROM promo_codes pc JOIN promotions pr ON pr.id = pc.promotion_id JOIN bookings b ON b.id = pc.booking_id WHERE pc.is_used = true ORDER BY pc.used_at DESC LIMIT 20', note: 'Last 20 uses' },
      { name: 'All promotions', query: 'SELECT id, name, discount_percent, code_prefix, total_codes, codes_used FROM promotions ORDER BY created_at DESC', note: 'Campaign list' },
      // Write templates (mark used, reset code) removed 2026-05-30 PR 8.
    ],
    'Flights': [
      { name: 'Departures (quick)', query: "SELECT id, flight_number, departure_time, destination_name, capacity_tier FROM flight_departures WHERE date = '{date}' ORDER BY departure_time", note: 'Essential columns' },
      { name: 'Departures (full)', query: "SELECT * FROM flight_departures WHERE date = '{date}' ORDER BY departure_time", note: 'All columns' },
      { name: 'Arrivals (quick)', query: "SELECT id, flight_number, arrival_time, origin_name FROM flight_arrivals WHERE date = '{date}' ORDER BY arrival_time", note: 'Essential columns' },
      { name: 'Arrivals (full)', query: "SELECT * FROM flight_arrivals WHERE date = '{date}' ORDER BY arrival_time", note: 'All columns' },
      { name: 'Available slots', query: "SELECT id, flight_number, departure_time, destination_name, capacity_tier, slots_booked_early, slots_booked_late FROM flight_departures WHERE date = '{date}' AND capacity_tier > 0 ORDER BY departure_time", note: 'With availability' },
      // Write templates (update capacity, adjust slots) removed 2026-05-30 PR 8.
    ],
    'Marketing': [
      { name: 'Find subscriber (quick)', query: "SELECT id, first_name, last_name, email, source FROM marketing_subscribers WHERE email = '{email}'", note: 'Essential columns' },
      { name: 'Find subscriber (full)', query: "SELECT * FROM marketing_subscribers WHERE email = '{email}'", note: 'All columns' },
      { name: 'Recent subscribers', query: 'SELECT id, first_name, last_name, email, source, subscribed_at FROM marketing_subscribers ORDER BY subscribed_at DESC LIMIT 20', note: 'Last 20' },
      { name: 'Source breakdown', query: 'SELECT source, COUNT(*) as count FROM marketing_sources GROUP BY source ORDER BY count DESC', note: 'Grouped counts' },
    ],
    'Staff & Roster': [
      { name: 'All users', query: 'SELECT id, first_name, last_name, email, is_admin, is_active FROM users ORDER BY id', note: 'Staff list' },
      { name: 'Shifts (quick)', query: "SELECT rs.id, rs.staff_id, rs.date, rs.start_time, rs.end_time, rs.status FROM roster_shifts rs WHERE rs.date = '{date}' ORDER BY rs.start_time", note: 'Essential columns' },
      { name: 'Shifts (full)', query: "SELECT rs.*, u.first_name, u.last_name FROM roster_shifts rs LEFT JOIN users u ON u.id = rs.staff_id WHERE rs.date = '{date}' ORDER BY rs.start_time", note: 'With staff names' },
      // Write templates (assign staff, update status) removed 2026-05-30 PR 8.
    ],
    'Inspections': [
      { name: 'By booking (quick)', query: 'SELECT id, inspection_type, customer_name, mileage, declined FROM vehicle_inspections WHERE booking_id = {id}', note: 'Essential columns' },
      { name: 'By booking (full)', query: 'SELECT * FROM vehicle_inspections WHERE booking_id = {id}', note: 'All columns' },
      { name: 'Recent inspections', query: 'SELECT vi.id, b.reference, vi.inspection_type, vi.customer_name, vi.mileage FROM vehicle_inspections vi JOIN bookings b ON b.id = vi.booking_id ORDER BY vi.created_at DESC LIMIT 20', note: 'Last 20' },
    ],
    '📊 Analytics': [
      { name: 'Top 5 drop-off hours', query: "SELECT EXTRACT(HOUR FROM dropoff_time)::int AS hour_start, (EXTRACT(HOUR FROM dropoff_time)::int + 1) AS hour_end, COUNT(*) AS count FROM bookings WHERE dropoff_time IS NOT NULL GROUP BY EXTRACT(HOUR FROM dropoff_time) ORDER BY count DESC LIMIT 5", note: 'Most popular drop-off times' },
      { name: 'Top 5 pickup hours', query: "SELECT EXTRACT(HOUR FROM pickup_time)::int AS hour_start, (EXTRACT(HOUR FROM pickup_time)::int + 1) AS hour_end, COUNT(*) AS count FROM bookings WHERE pickup_time IS NOT NULL GROUP BY EXTRACT(HOUR FROM pickup_time) ORDER BY count DESC LIMIT 5", note: 'Most popular pickup times' },
      { name: 'Drop-off hours (all)', query: "SELECT EXTRACT(HOUR FROM dropoff_time)::int AS hour_start, (EXTRACT(HOUR FROM dropoff_time)::int + 1) AS hour_end, COUNT(*) AS count FROM bookings WHERE dropoff_time IS NOT NULL GROUP BY EXTRACT(HOUR FROM dropoff_time) ORDER BY EXTRACT(HOUR FROM dropoff_time)", note: 'All drop-off hours' },
      { name: 'Pickup hours (all)', query: "SELECT EXTRACT(HOUR FROM pickup_time)::int AS hour_start, (EXTRACT(HOUR FROM pickup_time)::int + 1) AS hour_end, COUNT(*) AS count FROM bookings WHERE pickup_time IS NOT NULL GROUP BY EXTRACT(HOUR FROM pickup_time) ORDER BY EXTRACT(HOUR FROM pickup_time)", note: 'All pickup hours' },
      { name: 'Drop-offs by day of week', query: "SELECT TRIM(TO_CHAR(dropoff_date, 'Day')) AS day_name, EXTRACT(DOW FROM dropoff_date)::int AS day_num, COUNT(*) AS count FROM bookings WHERE dropoff_date IS NOT NULL GROUP BY day_name, day_num ORDER BY count DESC", note: 'Busiest drop-off days' },
      { name: 'Pick-ups by day of week', query: "SELECT TRIM(TO_CHAR(pickup_date, 'Day')) AS day_name, EXTRACT(DOW FROM pickup_date)::int AS day_num, COUNT(*) AS count FROM bookings WHERE pickup_date IS NOT NULL GROUP BY day_name, day_num ORDER BY count DESC", note: 'Busiest pick-up days' },
      { name: 'Bookings created by day', query: "SELECT TRIM(TO_CHAR(created_at, 'Day')) AS day_name, EXTRACT(DOW FROM created_at)::int AS day_num, COUNT(*) AS count FROM bookings WHERE created_at IS NOT NULL GROUP BY day_name, day_num ORDER BY count DESC", note: 'When bookings are made' },
      { name: 'Bookings by month', query: "SELECT TO_CHAR(dropoff_date, 'YYYY-MM') AS month, COUNT(*) AS count FROM bookings GROUP BY month ORDER BY month DESC LIMIT 12", note: 'Last 12 months' },
      { name: 'Top 20 abandoned dates', query: "SELECT DATE(a.created_at) AS date, COUNT(DISTINCT a.session_id) AS abandoned_sessions FROM audit_logs a WHERE a.event = 'dates_selected' AND a.session_id NOT IN (SELECT DISTINCT session_id FROM audit_logs WHERE event IN ('payment_succeeded', 'booking_confirmed') AND session_id IS NOT NULL) AND a.session_id IS NOT NULL GROUP BY DATE(a.created_at) ORDER BY abandoned_sessions DESC LIMIT 20", note: 'Dates with most abandoned sessions' },
      { name: 'Top 20 abandoned hours', query: "SELECT EXTRACT(HOUR FROM a.created_at)::int AS hour_start, (EXTRACT(HOUR FROM a.created_at)::int + 1) AS hour_end, COUNT(DISTINCT a.session_id) AS abandoned_sessions FROM audit_logs a WHERE a.event = 'dates_selected' AND a.session_id NOT IN (SELECT DISTINCT session_id FROM audit_logs WHERE event IN ('payment_succeeded', 'booking_confirmed') AND session_id IS NOT NULL) AND a.session_id IS NOT NULL GROUP BY EXTRACT(HOUR FROM a.created_at) ORDER BY abandoned_sessions DESC LIMIT 20", note: 'Hours with most abandoned sessions' },
      { name: 'Abandoned by date+hour', query: "SELECT DATE(a.created_at) AS date, EXTRACT(HOUR FROM a.created_at)::int AS hour, COUNT(DISTINCT a.session_id) AS abandoned FROM audit_logs a WHERE a.event = 'dates_selected' AND a.session_id NOT IN (SELECT DISTINCT session_id FROM audit_logs WHERE event IN ('payment_succeeded', 'booking_confirmed') AND session_id IS NOT NULL) AND a.session_id IS NOT NULL GROUP BY DATE(a.created_at), EXTRACT(HOUR FROM a.created_at) ORDER BY abandoned DESC LIMIT 20", note: 'Top 20 date+hour combinations' },
      { name: 'Abandoned by day of week', query: "SELECT TO_CHAR(a.created_at, 'Day') AS day_name, EXTRACT(DOW FROM a.created_at) AS day_num, COUNT(DISTINCT a.session_id) AS abandoned FROM audit_logs a WHERE a.event = 'dates_selected' AND a.session_id NOT IN (SELECT DISTINCT session_id FROM audit_logs WHERE event IN ('payment_succeeded', 'booking_confirmed') AND session_id IS NOT NULL) AND a.session_id IS NOT NULL GROUP BY day_name, day_num ORDER BY day_num", note: 'Which days see most abandonment' },
      { name: 'Abandoned carts (all time)', query: "SELECT a.created_at, a.session_id, a.event_data::json->>'dropoff_date' AS dropoff_date, a.event_data::json->>'departure_time' AS departure_time, a.event_data::json->>'pickup_date' AS pickup_date, a.event_data::json->>'arrival_time' AS arrival_time, a.event_data::json->>'departure_destination' AS destination, (a.event_data::json->>'pickup_date')::date - (a.event_data::json->>'dropoff_date')::date AS days, a.event_data::json->>'departure_airline' AS airline FROM audit_logs a WHERE a.event = 'flight_selected' AND a.session_id NOT IN (SELECT DISTINCT session_id FROM audit_logs WHERE event IN ('payment_succeeded', 'booking_confirmed') AND session_id IS NOT NULL) AND a.session_id IS NOT NULL AND a.event_data::json->>'dropoff_date' IS NOT NULL AND a.event_data::json->>'pickup_date' IS NOT NULL ORDER BY a.created_at DESC LIMIT 500", note: 'All abandoned with flight details (max 500)' },
      { name: 'Abandoned carts (recent 50)', query: "SELECT a.created_at, a.session_id, a.event_data::json->>'dropoff_date' AS dropoff_date, a.event_data::json->>'departure_time' AS departure_time, a.event_data::json->>'pickup_date' AS pickup_date, a.event_data::json->>'arrival_time' AS arrival_time, a.event_data::json->>'departure_destination' AS destination, (a.event_data::json->>'pickup_date')::date - (a.event_data::json->>'dropoff_date')::date AS days, a.event_data::json->>'departure_airline' AS airline FROM audit_logs a WHERE a.event = 'flight_selected' AND a.session_id NOT IN (SELECT DISTINCT session_id FROM audit_logs WHERE event IN ('payment_succeeded', 'booking_confirmed') AND session_id IS NOT NULL) AND a.session_id IS NOT NULL AND a.event_data::json->>'dropoff_date' IS NOT NULL AND a.event_data::json->>'pickup_date' IS NOT NULL ORDER BY a.created_at DESC LIMIT 50", note: 'Last 50 abandoned' },
      { name: 'Abandoned carts (today)', query: "SELECT a.created_at, a.session_id, a.event_data::json->>'dropoff_date' AS dropoff_date, a.event_data::json->>'departure_time' AS departure_time, a.event_data::json->>'pickup_date' AS pickup_date, a.event_data::json->>'arrival_time' AS arrival_time, a.event_data::json->>'departure_destination' AS destination, (a.event_data::json->>'pickup_date')::date - (a.event_data::json->>'dropoff_date')::date AS days, a.event_data::json->>'departure_airline' AS airline FROM audit_logs a WHERE a.event = 'flight_selected' AND DATE(a.created_at) = CURRENT_DATE AND a.session_id NOT IN (SELECT DISTINCT session_id FROM audit_logs WHERE event IN ('payment_succeeded', 'booking_confirmed') AND session_id IS NOT NULL) AND a.session_id IS NOT NULL AND a.event_data::json->>'dropoff_date' IS NOT NULL AND a.event_data::json->>'pickup_date' IS NOT NULL ORDER BY a.created_at DESC", note: 'Today only' },
      { name: 'Abandoned by destination', query: "SELECT a.event_data::json->>'departure_destination' AS destination, COUNT(DISTINCT a.session_id) AS abandoned FROM audit_logs a WHERE a.event = 'flight_selected' AND a.session_id NOT IN (SELECT DISTINCT session_id FROM audit_logs WHERE event IN ('payment_succeeded', 'booking_confirmed') AND session_id IS NOT NULL) AND a.session_id IS NOT NULL AND a.event_data::json->>'departure_destination' IS NOT NULL GROUP BY destination ORDER BY abandoned DESC LIMIT 20", note: 'Most abandoned destinations' },
      { name: 'Abandoned by parking days', query: "SELECT (a.event_data::json->>'days_parking')::int AS days, COUNT(DISTINCT a.session_id) AS abandoned FROM audit_logs a WHERE a.event = 'dates_selected' AND a.session_id NOT IN (SELECT DISTINCT session_id FROM audit_logs WHERE event IN ('payment_succeeded', 'booking_confirmed') AND session_id IS NOT NULL) AND a.session_id IS NOT NULL AND a.event_data::json->>'days_parking' IS NOT NULL GROUP BY days ORDER BY abandoned DESC LIMIT 20", note: 'Most abandoned by trip length' },
    ],
    '🔍 Debug': [
      { name: '🔴 Payment not found by PI', query: "SELECT * FROM payments WHERE stripe_payment_intent_id = '{pi}'", note: 'Check if payment exists for intent' },
      { name: '🔴 Search PI partial match', query: "SELECT id, booking_id, stripe_payment_intent_id, status, created_at FROM payments WHERE stripe_payment_intent_id LIKE '%{partial}%'", note: 'Partial PI search' },
      { name: '🔴 Recent failed payments', query: "SELECT p.id, b.reference, p.stripe_payment_intent_id, p.status, p.created_at FROM payments p JOIN bookings b ON b.id = p.booking_id WHERE p.status = 'failed' ORDER BY p.created_at DESC LIMIT 20", note: 'Failed payments' },
      { name: '🔴 Pending payments', query: "SELECT p.id, b.reference, p.stripe_payment_intent_id, p.amount_pence, p.created_at FROM payments p JOIN bookings b ON b.id = p.booking_id WHERE p.status = 'pending' ORDER BY p.created_at DESC LIMIT 20", note: 'Awaiting completion' },
      { name: '🔴 Orphaned payments', query: "SELECT p.* FROM payments p LEFT JOIN bookings b ON b.id = p.booking_id WHERE b.id IS NULL", note: 'Payments without booking' },
      { name: '🔴 Booking without payment', query: "SELECT b.id, b.reference, b.status, b.created_at FROM bookings b LEFT JOIN payments p ON p.booking_id = b.id WHERE p.id IS NULL AND b.status != 'pending' ORDER BY b.created_at DESC LIMIT 20", note: 'Missing payment records' },
      { name: '🔴 Payment audit by PI', query: "SELECT al.* FROM audit_logs al WHERE al.event_data LIKE '%{pi}%' ORDER BY al.created_at DESC", note: 'Audit trail for payment intent' },
      { name: '🔴 Error logs by PI', query: "SELECT * FROM error_logs WHERE message LIKE '%{pi}%' OR request_data LIKE '%{pi}%' ORDER BY created_at DESC", note: 'Errors mentioning payment intent' },
      { name: '🔴 Recent payment errors', query: "SELECT id, error_type, message, endpoint, created_at FROM error_logs WHERE error_type LIKE '%payment%' OR error_type LIKE '%stripe%' ORDER BY created_at DESC LIMIT 20", note: 'Payment-related errors' },
      { name: '🔴 Booking status mismatch', query: "SELECT b.id, b.reference, b.status AS booking_status, p.status AS payment_status FROM bookings b JOIN payments p ON p.booking_id = b.id WHERE (b.status = 'confirmed' AND p.status != 'succeeded') OR (b.status = 'pending' AND p.status = 'succeeded')", note: 'Status inconsistencies' },
      { name: '🔴 Duplicate payment intents', query: "SELECT stripe_payment_intent_id, COUNT(*) as count FROM payments GROUP BY stripe_payment_intent_id HAVING COUNT(*) > 1", note: 'Duplicate PI records' },
      { name: '🔴 Session audit trail', query: "SELECT * FROM audit_logs WHERE session_id = '{session}' ORDER BY created_at", note: 'Full session history' },
    ],
  }

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
  const detectedTestimonialThemes = useMemo(
    () => detectTestimonialThemes(testimonialForm.review_text),
    [testimonialForm.review_text]
  )

  // Promo Modals state
  const [promoModals, setPromoModals] = useState([])
  const [loadingPromoModals, setLoadingPromoModals] = useState(false)
  const [showPromoModalForm, setShowPromoModalForm] = useState(false)
  const [editingPromoModal, setEditingPromoModal] = useState(null)
  const [promoModalForm, setPromoModalForm] = useState({
    type: 'info_modal',  // info_modal or promo_section
    title: '',
    message: '',
    button_text: 'Subscribe',
    button_action: 'subscribe',
    button_link: '',
    start_date: '',
    end_date: '',
    background_color: '#343434',
    text_color: '#d9ff00',
    button_color: '#d9ff00',
    button_text_color: '#343434',
    status: 'inactive',
    max_subscribers: '',
    promo_code: ''
  })
  const [savingPromoModal, setSavingPromoModal] = useState(false)
  const [showDeletePromoModal, setShowDeletePromoModal] = useState(false)
  const [promoModalToDelete, setPromoModalToDelete] = useState(null)
  const [deletingPromoModal, setDeletingPromoModal] = useState(false)
  const [promoModalSuccessMessage, setPromoModalSuccessMessage] = useState('')
  const [promoCodeIsMultiUse, setPromoCodeIsMultiUse] = useState(false)
  const [promoCodesForModal, setPromoCodesForModal] = useState([]) // Available promo codes for selection
  const [loadingPromoCodesForModal, setLoadingPromoCodesForModal] = useState(false)
  const [selectedPromoCodeInfo, setSelectedPromoCodeInfo] = useState(null) // Info about selected code

  // Test email domains to filter out
  const testEmailDomains = ['yopmail.com', 'mailinator.com', 'guerrillamail.com', 'tempmail.com', 'fakeinbox.com', 'test.com', 'example.com', 'staging.tag.com']

  const isTestEmail = (email) => {
    if (!email) return false
    const domain = email.toLowerCase().split('@')[1]
    return testEmailDomains.includes(domain) || domain?.includes('test') || domain?.includes('staging')
  }

  const applyAdminItemSelection = (itemId) => {
    const selection = getAdminSelectionForItem(itemId)
    setActiveTab(selection.activeTab)
    if (selection.marketingSubTab) {
      setMarketingSubTab(selection.marketingSubTab)
    }
    if (selection.reportsSubTab) {
      setReportsSubTab(selection.reportsSubTab)
    }
    NAV_STRUCTURE.forEach(cat => {
      if (cat.items.some(item => item.id === itemId)) {
        setExpandedCategories(prev => ({ ...prev, [cat.category]: true }))
      }
    })
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

  useEffect(() => {
    if (loading || !isAuthenticated || !isAdmin) return

    const normalisedPath = location.pathname.replace(/\/+$/, '') || '/admin'
    const routeItemId = getAdminItemIdForPath(normalisedPath)
    const routeItemMeta = routeItemId ? ADMIN_ITEM_META_BY_ID[routeItemId] : null
    const routeAllowed = routeItemMeta && (
      !routeItemMeta.restrictToUserIds ||
      routeItemMeta.restrictToUserIds.includes(user?.id)
    )

    if (normalisedPath === '/admin') {
      navigate(ADMIN_DEFAULT_ROUTE, { replace: true })
      return
    }
    if (!routeItemId || !routeAllowed) {
      navigate(ADMIN_DEFAULT_ROUTE, { replace: true })
      return
    }

    applyAdminItemSelection(routeItemId)
  }, [loading, isAuthenticated, isAdmin, location.pathname, navigate, user?.id])

  // Fetch bookings when tab is active
  useEffect(() => {
    if (activeTab === 'bookings' && token) {
      fetchBookings()
    }
  }, [activeTab, token])

  // Show / hide the Bookings tab's scroll-to-top button based on how far
  // the page has been scrolled. The whole admin layout grows with content
  // (min-height: 100vh on body/#root/.admin-layout), so the window is the
  // real scroll container, not .admin-main.
  useEffect(() => {
    if (activeTab !== 'bookings') {
      setBookingsScrollTopVisible(false)
      return
    }
    const onScroll = () => setBookingsScrollTopVisible(window.scrollY > 400)
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [activeTab])


  // Fetch subscribers when marketing tab is active with subscribers or campaigns sub-tab
  useEffect(() => {
    if (activeTab === 'marketing' && token && (marketingSubTab === 'subscribers' || marketingSubTab === 'campaigns')) {
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

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setReferralsCustomerSearchQuery(referralsCustomerSearch.trim())
      setReferralsCustomerOffset(0)
    }, 350)
    return () => window.clearTimeout(timeout)
  }, [referralsCustomerSearch])

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setReferralsUsageSearchQuery(referralsUsageSearch.trim())
      setReferralsUsageOffset(0)
    }, 350)
    return () => window.clearTimeout(timeout)
  }, [referralsUsageSearch])

  useEffect(() => {
    if (activeTab === 'marketing' && token && marketingSubTab === 'referrals') {
      fetchReferralsDashboard()
    }
  }, [
    activeTab,
    token,
    marketingSubTab,
    referralsFilter,
    referralsCustomerSearchQuery,
    referralsCustomerOffset,
    referralsCustomerPageSize,
    referralsUsageFilter,
    referralsUsageSearchQuery,
    referralsUsageOffset,
    referralsUsagePageSize,
  ])

  // Fetch email campaigns when marketing tab is active with campaigns sub-tab
  useEffect(() => {
    if (activeTab === 'marketing' && token && marketingSubTab === 'campaigns') {
      fetchCampaigns()
      fetchAvailablePromoCodes()
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

  // Fetch SMS messages when messages tab is active
  useEffect(() => {
    if (activeTab === 'messages' && token) {
      fetchSmsMessages()
      fetchSmsTemplates()
      fetchSmsStats()
      fetchSmsThreads()
    }
  }, [activeTab, token])

  // Re-fetch messages when filters change
  useEffect(() => {
    if (activeTab === 'messages' && token) {
      if (messagesSubTab === 'conversations') {
        fetchSmsThreads()
      } else {
        fetchSmsMessages()
      }
    }
  }, [messagesSubTab, smsDirectionFilter, smsStatusFilter])

  // Keep the open SMS thread fresh so delivery reports show ticks without
  // forcing the admin to close and reopen the conversation.
  useEffect(() => {
    if (activeTab !== 'messages' || messagesSubTab !== 'conversations' || !selectedThread || !token) return

    const interval = setInterval(() => {
      fetchConversation(selectedThread.phone_number, { silent: true })
      fetchSmsStats()
    }, 300000)

    return () => clearInterval(interval)
  }, [activeTab, messagesSubTab, selectedThread?.phone_number, token])

  // Fetch booking locations when reports tab is active or map type changes
  useEffect(() => {
    if (activeTab === 'reports' && token) {
      if (reportsSubTab === 'map') {
        fetchBookingLocations(mapType)
      } else if (reportsSubTab === 'growth') {
        fetchBookingStats()
        fetchFunFacts()
      } else if (reportsSubTab === 'occupancy') {
        fetchCapacitySettings()
        fetchSecondaryCarparkReport()
        fetchOccupancyReport(occupancyView)
      } else if (reportsSubTab === 'popular') {
        fetchPopularReport()
      } else if (reportsSubTab === 'financial') {
        fetchFinancialReport()
      } else if (reportsSubTab === 'sessions') {
        fetchSessionTracking()
      } else if (reportsSubTab === 'analytics') {
        fetchAbandonedCarts()
      } else if (reportsSubTab === 'forecast') {
        fetchBookingsForecast()
      }
    }
  }, [activeTab, token, mapType, reportsSubTab, occupancyView, popularTop, sessionTrackingPeriod, abandonedCartsPeriod])

  // Fetch test results when QA Tests tab is active
  useEffect(() => {
    if (activeTab === 'qa-tests' && token) {
      fetchTestResults()
    }
  }, [activeTab, token])

  // Fetch database connection pool data when its QA tab is active
  useEffect(() => {
    if (activeTab === 'qa-connection-pool' && token) {
      fetchDbHealth()
      fetchDbPoolHistory()
    }
  }, [activeTab, token])

  // Fetch audit event types and error log meta when any QA tab is active
  useEffect(() => {
    if (activeTab.startsWith('qa-') && token) {
      fetchAuditEventTypes()
      fetchErrorLogMeta()
    }
  }, [activeTab, token])

  // Fetch audit logs when QA Audit tab is active
  useEffect(() => {
    if (activeTab === 'qa-audit' && token) {
      fetchAuditLogs(true)
    }
  }, [activeTab, token, auditLogsFilters])

  // Auto-refresh audit logs every 30 seconds when enabled
  useEffect(() => {
    if (!auditLogsAutoRefresh || activeTab !== 'qa-audit' || !token) return
    const interval = setInterval(() => {
      fetchAuditLogs(true)
    }, 30000)
    return () => clearInterval(interval)
  }, [auditLogsAutoRefresh, activeTab, token, auditLogsFilters])

  // Fetch error logs when QA Errors tab is active
  useEffect(() => {
    if (activeTab === 'qa-errors' && token) {
      fetchErrorLogs(true)
    }
  }, [activeTab, token, errorLogsFilters])

  // Check SQL session when SQL tab is opened
  useEffect(() => {
    if (activeTab === 'qa-sql' && token) {
      checkSqlSession()
    }
  }, [activeTab, token])

  // Check if SQL session has expired (every minute)
  useEffect(() => {
    if (sqlSessionExpires) {
      const checkExpiry = setInterval(() => {
        if (new Date() > sqlSessionExpires) {
          localStorage.removeItem('sqlSessionToken')
          setSqlSessionToken(null)
          setSqlSessionExpires(null)
        }
      }, 60000)
      return () => clearInterval(checkExpiry)
    }
  }, [sqlSessionExpires])

  // Fetch testimonials when testimonials tab is active
  useEffect(() => {
    if (activeTab === 'testimonials' && token) {
      fetchTestimonials()
    }
  }, [activeTab, token, testimonialFilter, testimonialSort])

  // Fetch promo modals when promo-modals tab is active
  useEffect(() => {
    if (activeTab === 'promo-modals' && token) {
      fetchPromoModals()
    }
  }, [activeTab, token])

  const fetchPromoModals = async () => {
    setLoadingPromoModals(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/promo-modals`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setPromoModals(data.promoModals || [])
      }
    } catch (err) {
      console.error('Failed to fetch promo modals:', err)
    } finally {
      setLoadingPromoModals(false)
    }
  }

  const handleSavePromoModal = async () => {
    setSavingPromoModal(true)
    setPromoModalSuccessMessage('')
    try {
      const url = editingPromoModal
        ? `${API_URL}/api/admin/promo-modals/${editingPromoModal.id}`
        : `${API_URL}/api/admin/promo-modals`
      const method = editingPromoModal ? 'PUT' : 'POST'

      // Convert empty strings to null for optional integer fields
      const payload = {
        ...promoModalForm,
        max_subscribers: promoModalForm.max_subscribers === '' ? null : parseInt(promoModalForm.max_subscribers, 10) || null,
      }

      const response = await fetch(url, {
        method,
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })

      if (response.ok) {
        const typeLabel = promoModalForm.type === 'promo_section' ? 'Promo section' : 'Info modal'
        setPromoModalSuccessMessage(editingPromoModal ? `${typeLabel} updated!` : `${typeLabel} created!`)
        setTimeout(() => setPromoModalSuccessMessage(''), 3000)
        setShowPromoModalForm(false)
        setEditingPromoModal(null)
        setPromoModalForm({
          type: 'info_modal',
          title: '',
          message: '',
          button_text: 'Subscribe',
          button_action: 'subscribe',
          button_link: '',
          start_date: '',
          end_date: '',
          background_color: '#343434',
          text_color: '#d9ff00',
          button_color: '#d9ff00',
          button_text_color: '#343434',
          status: 'inactive',
          max_subscribers: '',
          promo_code: ''
        })
        fetchPromoModals()
      } else {
        const error = await response.json()
        alert(error.detail || 'Failed to save promo modal')
      }
    } catch (err) {
      console.error('Failed to save promo modal:', err)
      alert('Failed to save promo modal')
    } finally {
      setSavingPromoModal(false)
    }
  }

  const handleDeletePromoModal = async () => {
    if (!promoModalToDelete) return
    setDeletingPromoModal(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/promo-modals/${promoModalToDelete.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        setPromoModalSuccessMessage('Promo modal deleted!')
        setTimeout(() => setPromoModalSuccessMessage(''), 3000)
        setShowDeletePromoModal(false)
        setPromoModalToDelete(null)
        fetchPromoModals()
      }
    } catch (err) {
      console.error('Failed to delete promo modal:', err)
    } finally {
      setDeletingPromoModal(false)
    }
  }

  const handleTogglePromoModalStatus = async (modal) => {
    try {
      const response = await fetch(`${API_URL}/api/admin/promo-modals/${modal.id}/status`, {
        method: 'PATCH',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        fetchPromoModals()
      }
    } catch (err) {
      console.error('Error toggling promo modal status:', err)
    }
  }

  const openEditPromoModal = (modal) => {
    setEditingPromoModal(modal)
    setPromoModalForm({
      type: modal.type || 'info_modal',
      title: modal.title,
      message: modal.message,
      button_text: modal.buttonText,
      button_action: modal.buttonAction,
      button_link: modal.buttonLink || '',
      start_date: modal.startDate || '',
      end_date: modal.endDate || '',
      background_color: modal.backgroundColor,
      text_color: modal.textColor,
      button_color: modal.buttonColor,
      button_text_color: modal.buttonTextColor || '#ffffff',
      status: modal.status,
      max_subscribers: modal.maxSubscribers || '',
      promo_code: modal.promoCode || ''
    })
    // Fetch promo codes for dropdown and set selected info
    fetchPromoCodesForModal().then(() => {
      if (modal.promoCode) {
        // Find the code info from the loaded codes
        const codeInfo = promoCodesForModal.find(c => c.code === modal.promoCode)
        setSelectedPromoCodeInfo(codeInfo || null)
        setPromoCodeIsMultiUse(codeInfo?.is_multi_use || false)
      } else {
        setSelectedPromoCodeInfo(null)
        setPromoCodeIsMultiUse(false)
      }
    })
    setShowPromoModalForm(true)
  }

  // Check if a promo code is multi-use by looking it up in the promo_codes table
  const checkPromoCodeIsMultiUse = async (code) => {
    if (!code || !code.trim()) {
      setPromoCodeIsMultiUse(false)
      return
    }
    try {
      const response = await fetch(`${API_URL}/api/promo/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code.trim().toUpperCase() })
      })
      if (response.ok) {
        const data = await response.json()
        // If valid and is_multi_use is true, it's a multi-use code
        setPromoCodeIsMultiUse(data.valid && data.is_multi_use === true)
      } else {
        setPromoCodeIsMultiUse(false)
      }
    } catch (err) {
      console.error('Error checking promo code:', err)
      setPromoCodeIsMultiUse(false)
    }
  }

  // Fetch all promo codes from all promotions for the dropdown
  const fetchPromoCodesForModal = async () => {
    setLoadingPromoCodesForModal(true)
    try {
      // Get all promotions first
      const promoResponse = await fetch(`${API_URL}/api/admin/promotions`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (!promoResponse.ok) {
        setPromoCodesForModal([])
        return
      }
      const promoData = await promoResponse.json()
      const allPromotions = promoData.promotions || []

      // For each promotion, get its codes
      const allCodes = []
      for (const promo of allPromotions) {
        const detailResponse = await fetch(`${API_URL}/api/admin/promotions/${promo.id}`, {
          headers: { 'Authorization': `Bearer ${token}` },
        })
        if (detailResponse.ok) {
          const detailData = await detailResponse.json()
          const codes = detailData.codes || []
          // Add promotion info to each code
          codes.forEach(code => {
            allCodes.push({
              ...code,
              promotion_name: promo.name,
              promotion_discount: promo.discount_percent,
            })
          })
        }
      }
      setPromoCodesForModal(allCodes)
    } catch (err) {
      console.error('Failed to fetch promo codes:', err)
      setPromoCodesForModal([])
    } finally {
      setLoadingPromoCodesForModal(false)
    }
  }

  const fetchTestimonials = async () => {
    setLoadingTestimonials(true)
    try {
      const params = new URLSearchParams()
      if (testimonialFilter.star_rating) params.append('star_rating', testimonialFilter.star_rating)
      if (testimonialFilter.status) params.append('status', testimonialFilter.status)
      params.append('sort', testimonialSort.field)
      params.append('order', testimonialSort.order)

      const response = await authFetch(`${API_URL}/api/admin/testimonials?${params}`)
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

      const response = await authFetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
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
      const response = await authFetch(`${API_URL}/api/admin/testimonials/${testimonialToDelete.id}`, {
        method: 'DELETE',
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
      const response = await authFetch(`${API_URL}/api/admin/testimonials/${testimonial.id}/status`, {
        method: 'PATCH',
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

  const fetchDbHealth = async () => {
    setLoadingDbHealth(true)
    try {
      const res = await fetch(`${API_URL}/api/admin/db-health`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setDbHealth(data)
      }
    } catch (err) {
      console.error('Failed to fetch DB health:', err)
    } finally {
      setLoadingDbHealth(false)
    }
  }

  const fetchDbPoolHistory = async (hours = 24) => {
    setLoadingPoolHistory(true)
    try {
      const res = await fetch(`${API_URL}/api/admin/db-health/history?hours=${hours}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setDbPoolHistory(data)
      }
    } catch (err) {
      console.error('Failed to fetch DB pool history:', err)
    } finally {
      setLoadingPoolHistory(false)
    }
  }

  const fetchAuditLogs = async (resetOffset = false, explicitOffset = null) => {
    setLoadingAuditLogs(true)
    if (resetOffset) {
      setAuditLogsOffset(0)
    }
    const currentOffset = explicitOffset !== null ? explicitOffset : (resetOffset ? 0 : auditLogsOffset)
    try {
      const params = new URLSearchParams({
        limit: '50',
        offset: currentOffset.toString(),
      })
      if (auditLogsFilters.search) params.append('search', auditLogsFilters.search)
      if (auditLogsFilters.booking_reference) params.append('booking_reference', auditLogsFilters.booking_reference)
      if (auditLogsFilters.event) params.append('event', auditLogsFilters.event)
      if (auditLogsFilters.date_from) params.append('date_from', ukDateTimeToIso(auditLogsFilters.date_from))
      if (auditLogsFilters.date_to) params.append('date_to', ukDateTimeToIso(auditLogsFilters.date_to))

      const response = await fetch(`${API_URL}/api/admin/audit-logs?${params}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setAuditLogs(data.audit_logs || [])
        setAuditLogsTotalCount(data.total_count || 0)
      }
    } catch (err) {
      console.error('Failed to fetch audit logs:', err)
    } finally {
      setLoadingAuditLogs(false)
    }
  }

  const fetchAuditEventTypes = async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/audit-logs/events`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setAuditEventTypes(data.events || [])
      }
    } catch (err) {
      console.error('Failed to fetch audit event types:', err)
    }
  }

  const fetchErrorLogs = async (resetOffset = false, explicitOffset = null) => {
    setLoadingErrorLogs(true)
    if (resetOffset) {
      setErrorLogsOffset(0)
    }
    const currentOffset = explicitOffset !== null ? explicitOffset : (resetOffset ? 0 : errorLogsOffset)
    try {
      const params = new URLSearchParams({
        limit: '50',
        offset: currentOffset.toString(),
      })
      if (errorLogsFilters.search) params.append('search', errorLogsFilters.search)
      if (errorLogsFilters.booking_reference) params.append('booking_reference', errorLogsFilters.booking_reference)
      if (errorLogsFilters.severity) params.append('severity', errorLogsFilters.severity)
      if (errorLogsFilters.error_type) params.append('error_type', errorLogsFilters.error_type)
      if (errorLogsFilters.date_from) params.append('date_from', ukDateTimeToIso(errorLogsFilters.date_from))
      if (errorLogsFilters.date_to) params.append('date_to', ukDateTimeToIso(errorLogsFilters.date_to))

      const response = await fetch(`${API_URL}/api/admin/error-logs?${params}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setErrorLogs(data.error_logs || [])
        setErrorLogsTotalCount(data.total_count || 0)
      }
    } catch (err) {
      console.error('Failed to fetch error logs:', err)
    } finally {
      setLoadingErrorLogs(false)
    }
  }

  const fetchErrorLogMeta = async () => {
    try {
      const [sevRes, typesRes] = await Promise.all([
        fetch(`${API_URL}/api/admin/error-logs/severities`, {
          headers: { 'Authorization': `Bearer ${token}` },
        }),
        fetch(`${API_URL}/api/admin/error-logs/types`, {
          headers: { 'Authorization': `Bearer ${token}` },
        }),
      ])
      if (sevRes.ok) {
        const data = await sevRes.json()
        setErrorSeverities(data.severities || [])
      }
      if (typesRes.ok) {
        const data = await typesRes.json()
        setErrorTypes(data.error_types || [])
      }
    } catch (err) {
      console.error('Failed to fetch error log metadata:', err)
    }
  }

  // SQL Interface functions
  const checkSqlSession = async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/sql/session-status`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        if (data.valid) {
          // Restore session from localStorage if token matches
          const storedToken = localStorage.getItem('sqlSessionToken')
          if (storedToken) {
            setSqlSessionToken(storedToken)
            setSqlSessionExpires(new Date(data.expires_at))
          }
        } else {
          // Clear expired session
          localStorage.removeItem('sqlSessionToken')
          setSqlSessionToken(null)
          setSqlSessionExpires(null)
        }
      }
    } catch (err) {
      console.error('Failed to check SQL session:', err)
    }
  }

  const verifySqlPin = async () => {
    setSqlPinError('')
    try {
      const response = await fetch(`${API_URL}/api/admin/sql/verify-pin`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ pin: sqlPin }),
      })
      const data = await response.json()
      if (response.ok && data.success) {
        setSqlSessionToken(data.session_token)
        setSqlSessionExpires(new Date(data.expires_at))
        localStorage.setItem('sqlSessionToken', data.session_token)
        setSqlPinModalOpen(false)
        setSqlPin('')
      } else {
        setSqlPinError(data.detail || 'Invalid PIN')
      }
    } catch (err) {
      setSqlPinError('Failed to verify PIN')
    }
  }

  const logoutSqlSession = async () => {
    try {
      await fetch(`${API_URL}/api/admin/sql/logout`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      })
    } catch (err) {
      console.error('Failed to logout SQL session:', err)
    }
    localStorage.removeItem('sqlSessionToken')
    setSqlSessionToken(null)
    setSqlSessionExpires(null)
    setSqlResults(null)
    setSqlQuery('')
  }

  // 2026-05-30 PR 8: SQL console is read-only. `confirmed` flag +
  // requires_confirmation response shape are dead — backend rejects
  // any non-SELECT/WITH with 403 and an audit row. Writes route
  // through inline python3 -c scripts.
  const executeSqlQuery = async () => {
    if (!sqlQuery.trim()) return

    setSqlLoading(true)
    setSqlError('')
    setSqlResults(null)

    try {
      const response = await fetch(`${API_URL}/api/admin/sql/execute`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: sqlQuery,
          session_token: sqlSessionToken,
        }),
      })
      const data = await response.json()

      if (!response.ok) {
        if (response.status === 401) {
          // Session expired
          localStorage.removeItem('sqlSessionToken')
          setSqlSessionToken(null)
          setSqlSessionExpires(null)
          setSqlPinModalOpen(true)
          setSqlError('Session expired. Please verify PIN again.')
        } else {
          setSqlError(data.detail || 'Query failed')
        }
        return
      }

      setSqlResults(data)
      // Add to history
      setSqlHistory(prev => [{
        query: sqlQuery,
        timestamp: new Date(),
        success: true,
        rowCount: data.row_count || 0,
      }, ...prev.slice(0, 19)])

    } catch (err) {
      setSqlError('Failed to execute query')
    } finally {
      setSqlLoading(false)
    }
  }

  // confirmSqlWrite removed 2026-05-30 PR 8: no write path to confirm.

  const exportSqlResultsCSV = () => {
    if (!sqlResults || !sqlResults.data || sqlResults.data.length === 0) return

    const columns = sqlResults.columns
    const rows = sqlResults.data

    // Build CSV content
    const csvContent = [
      columns.join(','),
      ...rows.map(row =>
        columns.map(col => {
          const value = row[col]
          if (value === null) return ''
          if (typeof value === 'object') return `"${JSON.stringify(value).replace(/"/g, '""')}"`
          const strValue = String(value)
          // Escape quotes and wrap in quotes if contains comma, quote, or newline
          if (strValue.includes(',') || strValue.includes('"') || strValue.includes('\n')) {
            return `"${strValue.replace(/"/g, '""')}"`
          }
          return strValue
        }).join(',')
      )
    ].join('\n')

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `sql-results-${new Date().toISOString().split('T')[0]}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const exportSqlResultsPDF = () => {
    if (!sqlResults || !sqlResults.data || sqlResults.data.length === 0) return

    const columns = sqlResults.columns
    const rows = sqlResults.data

    // Create printable HTML
    const printContent = `
      <!DOCTYPE html>
      <html>
      <head>
        <title>SQL Results - ${new Date().toLocaleDateString()}</title>
        <style>
          body { font-family: Arial, sans-serif; margin: 20px; }
          h1 { font-size: 18px; margin-bottom: 10px; }
          .meta { color: #666; font-size: 12px; margin-bottom: 20px; }
          table { border-collapse: collapse; width: 100%; font-size: 11px; }
          th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }
          th { background-color: #f5f5f5; font-weight: bold; }
          tr:nth-child(even) { background-color: #fafafa; }
          .null { color: #999; font-style: italic; }
          @media print {
            body { margin: 10px; }
            table { page-break-inside: auto; }
            tr { page-break-inside: avoid; }
          }
        </style>
      </head>
      <body>
        <h1>SQL Query Results</h1>
        <div class="meta">
          Generated: ${new Date().toLocaleString()} |
          Rows: ${rows.length}${sqlResults.has_more ? ' (limited to 500)' : ''}
        </div>
        <table>
          <thead>
            <tr>
              ${columns.map(col => `<th>${col}</th>`).join('')}
            </tr>
          </thead>
          <tbody>
            ${rows.map(row => `
              <tr>
                ${columns.map(col => {
                  const value = row[col]
                  if (value === null) return '<td class="null">NULL</td>'
                  if (typeof value === 'object') return `<td>${JSON.stringify(value)}</td>`
                  return `<td>${String(value).replace(/</g, '&lt;').replace(/>/g, '&gt;')}</td>`
                }).join('')}
              </tr>
            `).join('')}
          </tbody>
        </table>
      </body>
      </html>
    `

    const printWindow = window.open('', '_blank')
    printWindow.document.write(printContent)
    printWindow.document.close()
    printWindow.onload = () => {
      printWindow.print()
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

  const fetchFunFacts = async (forceRefresh = false) => {
    setLoadingFunFacts(true)
    try {
      const params = new URLSearchParams()
      if (forceRefresh) params.append('refresh', 'true')
      const response = await fetch(`${API_URL}/api/admin/reports/fun-facts?${params}`, {
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

  const fetchCapacitySettings = async () => {
    setLoadingCapacitySettings(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/capacity-settings`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setCapacitySettings(data)
        if (data.current) {
          setCapacityForm({
            effective_from: data.current.effective_from_display || todayInputValue,
            total_spaces: String(data.current.total_spaces || 75),
            online_spaces: String(data.current.online_spaces || 73),
          })
        }
      }
    } catch (err) {
      console.error('Failed to fetch capacity settings:', err)
    } finally {
      setLoadingCapacitySettings(false)
    }
  }

  const fetchSecondaryCarparkReport = async () => {
    setLoadingSecondaryReport(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/reports/secondary-carpark`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        setSecondaryReport(await response.json())
      }
    } catch (err) {
      console.error('Failed to fetch secondary car park report:', err)
    } finally {
      setLoadingSecondaryReport(false)
    }
  }

  const saveCapacitySettings = async (event) => {
    event.preventDefault()
    setCapacityMessage('')

    const totalSpaces = parseInt(capacityForm.total_spaces, 10)
    const onlineSpaces = parseInt(capacityForm.online_spaces, 10)

    const effectiveFrom = parseUkTimestampInput(capacityForm.effective_from)

    if (!effectiveFrom || Number.isNaN(totalSpaces) || Number.isNaN(onlineSpaces)) {
      setCapacityMessage('Enter an effective timestamp as dd/mm/yyyy HH:mm, plus total and online spaces.')
      return
    }
    if (totalSpaces < 1 || onlineSpaces < 1) {
      setCapacityMessage('Capacity values must be at least 1.')
      return
    }
    if (onlineSpaces > totalSpaces) {
      setCapacityMessage('Online spaces cannot exceed total spaces.')
      return
    }

    setSavingCapacitySettings(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/capacity-settings`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          effective_from: effectiveFrom,
          total_spaces: totalSpaces,
          online_spaces: onlineSpaces,
        }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        setCapacityMessage(data.detail || 'Failed to save capacity settings.')
        return
      }
      setCapacityMessage('Capacity settings saved.')
      await fetchCapacitySettings()
      await fetchOccupancyReport(occupancyView, true)
    } catch (err) {
      console.error('Failed to save capacity settings:', err)
      setCapacityMessage('Network error saving capacity settings.')
    } finally {
      setSavingCapacitySettings(false)
    }
  }

  const fetchOccupancyReport = async (view = 'daily', forceRefresh = false) => {
    setLoadingOccupancy(true)
    try {
      const params = new URLSearchParams({ view })
      if (forceRefresh) params.append('refresh', 'true')
      const response = await fetch(`${API_URL}/api/admin/reports/occupancy?${params}`, {
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

  const fetchPopularReport = async (forceRefresh = false) => {
    setLoadingPopular(true)
    try {
      const params = new URLSearchParams({
        top: popularTop.toString(),
      })
      if (forceRefresh) params.append('refresh', 'true')
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

  const fetchFinancialReport = async (forceRefresh = false) => {
    setLoadingFinancial(true)
    try {
      const params = new URLSearchParams()
      if (financialFromDate) params.append('from_date', financialFromDate)
      if (financialToDate) params.append('to_date', financialToDate)
      if (financialStatusFilter !== 'all') params.append('status_filter', financialStatusFilter)
      if (financialPromoFilter !== 'all') params.append('promo_filter', financialPromoFilter)
      if (forceRefresh) params.append('refresh', 'true')

      const response = await fetch(`${API_URL}/api/admin/reports/financial?${params}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setFinancialData(data)
      }
    } catch (err) {
      console.error('Failed to fetch financial report:', err)
    } finally {
      setLoadingFinancial(false)
    }
  }

  const fetchSessionTracking = async (period = sessionTrackingPeriod, forceRefresh = false) => {
    setLoadingSessionTracking(true)
    try {
      const params = new URLSearchParams({ period })
      if (forceRefresh) params.append('refresh', 'true')
      const response = await fetch(`${API_URL}/api/admin/reports/session-tracking?${params}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setSessionTrackingData(data)
      }
    } catch (err) {
      console.error('Failed to fetch session tracking:', err)
    } finally {
      setLoadingSessionTracking(false)
    }
  }

  const fetchAbandonedCarts = async (period = abandonedCartsPeriod, refresh = false) => {
    setLoadingAbandonedCarts(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/reports/abandoned-carts?period=${period}&refresh=${refresh}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setAbandonedCartsData(data)
      }
    } catch (err) {
      console.error('Failed to fetch abandoned carts:', err)
    } finally {
      setLoadingAbandonedCarts(false)
    }
  }

  const fetchBookingsForecast = async (forceRefresh = false) => {
    setLoadingForecast(true)
    try {
      const params = new URLSearchParams()
      if (forceRefresh) params.append('refresh', 'true')
      const response = await fetch(`${API_URL}/api/admin/reports/bookings-forecast?${params}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setForecastData(data)
      }
    } catch (err) {
      console.error('Failed to fetch bookings forecast:', err)
    } finally {
      setLoadingForecast(false)
    }
  }

  const saveFinancialOverride = async (bookingId, editing) => {
    setSavingFinancialOverride(true)
    const fail = (message) => setEditingFinancialBooking(prev => prev ? { ...prev, error: message } : prev)
    try {
      const grossPence = Math.round(parseFloat(editing.gross) * 100)
      const discountPence = Math.round(parseFloat(editing.discount || '0') * 100)
      // Only send promo_code when the admin changed it — omitting it leaves
      // attribution untouched; an empty value clears it.
      const trimmedPromo = (editing.promo ?? '').trim()
      const promoChanged = trimmedPromo !== (editing.initialPromo ?? '').trim()
      const figuresChanged = grossPence !== editing.initialGrossPence
        || discountPence !== editing.initialDiscountPence

      if (figuresChanged || promoChanged) {
        let url = `${API_URL}/api/admin/bookings/${bookingId}/financial-override?gross_pence=${grossPence}&discount_pence=${discountPence}`
        if (promoChanged) {
          url += `&promo_code=${encodeURIComponent(trimmedPromo)}`
        }
        const response = await fetch(url, {
          method: 'PUT',
          headers: { 'Authorization': `Bearer ${token}` },
        })
        if (!response.ok) {
          const data = await response.json().catch(() => ({}))
          console.error('Failed to save financial override', data)
          fail(data.detail || 'Failed to save financial override.')
          return
        }
      }

      // Refund sync: a Stripe id (re_/pi_) fetches verified figures from
      // Stripe; a plain number records a manual refund amount in pounds.
      const refundField = (editing.refund ?? '').trim()
      let refundWarning = null
      if (refundField) {
        let url = `${API_URL}/api/admin/bookings/${bookingId}/refund-sync?`
        if (/^(re_|pi_)/.test(refundField)) {
          url += `stripe_id=${encodeURIComponent(refundField)}`
        } else {
          const pounds = parseFloat(refundField)
          if (Number.isNaN(pounds)) {
            fail('Refund must be a Stripe id (re_… / pi_…) or an amount in pounds.')
            return
          }
          url += `refund_pence=${Math.round(pounds * 100)}`
        }
        const response = await fetch(url, {
          method: 'PUT',
          headers: { 'Authorization': `Bearer ${token}` },
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok) {
          console.error('Failed to sync refund', data)
          fail(data.detail || 'Failed to record the refund.')
          return
        }
        refundWarning = data.warning || null
      }

      // Refresh the financial report to show updated values (force refresh to bypass cache)
      await fetchFinancialReport(true)
      if (refundWarning) {
        // Saved, but Stripe's charge total didn't match the recorded payment
        // — keep the row open so the admin sees it.
        fail(`Saved — ${refundWarning}`)
      } else {
        setEditingFinancialBooking(null)
      }
    } catch (err) {
      console.error('Error saving financial override:', err)
      fail('Network error saving financial changes.')
    } finally {
      setSavingFinancialOverride(false)
    }
  }

  const exportFinancialCSV = async () => {
    setExportingFinancial(true)
    try {
      const params = new URLSearchParams()
      if (financialFromDate) params.append('from_date', financialFromDate)
      if (financialToDate) params.append('to_date', financialToDate)
      if (financialStatusFilter !== 'all') params.append('status_filter', financialStatusFilter)
      if (financialPromoFilter !== 'all') params.append('promo_filter', financialPromoFilter)

      const response = await fetch(`${API_URL}/api/admin/reports/financial/export?${params}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const blob = await response.blob()
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `financial-report-${new Date().toISOString().split('T')[0]}.csv`
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        a.remove()
      }
    } catch (err) {
      console.error('Failed to export financial report:', err)
    } finally {
      setExportingFinancial(false)
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

  // Fetch email campaigns
  const fetchCampaigns = async () => {
    setLoadingCampaigns(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/marketing/campaigns`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setCampaigns(data.campaigns || [])
      }
    } catch (err) {
      console.error('Failed to fetch campaigns:', err)
    } finally {
      setLoadingCampaigns(false)
    }
  }

  // Fetch available promo codes for campaigns
  const fetchAvailablePromoCodes = async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/marketing/promo-codes`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setAvailablePromoCodes(data.promo_codes || [])
      }
    } catch (err) {
      console.error('Failed to fetch promo codes:', err)
    }
  }

  const showCampaignToast = (type, message) => {
    setCampaignToast({ type, message })
    window.clearTimeout(showCampaignToast._timer)
    showCampaignToast._timer = window.setTimeout(() => setCampaignToast(null), 4000)
  }

  // Create or update email campaign
  const createCampaign = async () => {
    if (!newCampaign.subject || !newCampaign.message || newCampaign.subscriber_ids.length === 0) {
      showCampaignToast('error', 'Please fill in subject, message, and select at least one recipient')
      return
    }
    setCreatingCampaign(true)
    try {
      const isEdit = !!editingCampaignId
      const url = isEdit
        ? `${API_URL}/api/admin/marketing/campaigns/${editingCampaignId}`
        : `${API_URL}/api/admin/marketing/campaigns`
      const response = await fetch(url, {
        method: isEdit ? 'PUT' : 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          subject: newCampaign.subject,
          message: newCampaign.message,
          promo_code_id: newCampaign.promo_code_id,
          subscriber_ids: newCampaign.subscriber_ids,
        }),
      })
      if (response.ok) {
        const wasEdit = isEdit
        closeCampaignModal()
        fetchCampaigns()
        showCampaignToast('success', wasEdit ? 'Campaign updated' : 'Campaign created as draft')
      } else {
        const data = await response.json()
        showCampaignToast('error', data.detail || (isEdit ? 'Failed to update campaign' : 'Failed to create campaign'))
      }
    } catch (err) {
      console.error('Failed to save campaign:', err)
      showCampaignToast('error', 'Failed to save campaign')
    } finally {
      setCreatingCampaign(false)
    }
  }

  const closeCampaignModal = () => {
    setShowCreateCampaign(false)
    setNewCampaign({ subject: '', message: '', promo_code_id: null, subscriber_ids: [] })
    setEditingCampaignId(null)
    setCampaignPreview(null)
  }

  const openCampaignForEdit = async (campaignId) => {
    try {
      const response = await fetch(`${API_URL}/api/admin/marketing/campaigns/${campaignId}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (!response.ok) {
        showCampaignToast('error', 'Failed to load campaign')
        return
      }
      const data = await response.json()
      setEditingCampaignId(campaignId)
      setNewCampaign({
        subject: data.subject || '',
        message: data.message || '',
        promo_code_id: data.promo_code_id || null,
        subscriber_ids: (data.recipients || []).map(r => r.subscriber_id),
      })
      setCampaignPreview(null)
      setShowCreateCampaign(true)
    } catch (err) {
      console.error('Failed to load campaign for edit:', err)
      showCampaignToast('error', 'Failed to load campaign')
    }
  }

  const deleteCampaign = (campaignId) => {
    setCampaignConfirm({ action: 'delete', id: campaignId })
  }

  const performDeleteCampaign = async (campaignId) => {
    setDeletingCampaignId(campaignId)
    try {
      const response = await fetch(`${API_URL}/api/admin/marketing/campaigns/${campaignId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        fetchCampaigns()
        showCampaignToast('success', 'Campaign deleted')
      } else {
        const data = await response.json()
        showCampaignToast('error', data.detail || 'Failed to delete campaign')
      }
    } catch (err) {
      console.error('Failed to delete campaign:', err)
      showCampaignToast('error', 'Failed to delete campaign')
    } finally {
      setDeletingCampaignId(null)
    }
  }

  // Send email campaign — opens confirm modal
  const sendCampaign = (campaignId) => {
    setCampaignConfirm({ action: 'send', id: campaignId })
  }

  const performSendCampaign = async (campaignId) => {
    setSendingCampaign(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/marketing/campaigns/${campaignId}/send`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        fetchCampaigns()
        showCampaignToast('success', 'Campaign sending started')
      } else {
        const data = await response.json()
        showCampaignToast('error', data.detail || 'Failed to send campaign')
      }
    } catch (err) {
      console.error('Failed to send campaign:', err)
      showCampaignToast('error', 'Failed to send campaign')
    } finally {
      setSendingCampaign(false)
    }
  }

  // Preview campaign
  const previewCampaign = async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/marketing/campaigns/preview`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          subject: newCampaign.subject,
          message: newCampaign.message,
          promo_code_id: newCampaign.promo_code_id,
        }),
      })
      if (response.ok) {
        const data = await response.json()
        setCampaignPreview(data)
      }
    } catch (err) {
      console.error('Failed to preview campaign:', err)
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

  const fetchBookingLocations = async (type = 'bookings', forceRefresh = false) => {
    setLoadingLocations(true)
    setError('')
    try {
      const params = new URLSearchParams({ map_type: type })
      if (forceRefresh) params.append('refresh', 'true')
      const response = await fetch(`${API_URL}/api/admin/reports/booking-locations?${params}`, {
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

  const fetchReferralsDashboard = async () => {
    setLoadingReferrals(true)
    setError('')
    try {
      const params = new URLSearchParams({
        customer_limit: String(referralsCustomerPageSize),
        customer_offset: String(referralsCustomerOffset),
        customer_filter: referralsFilter,
        customer_search: referralsCustomerSearchQuery,
        usage_limit: String(referralsUsagePageSize),
        usage_offset: String(referralsUsageOffset),
        usage_filter: referralsUsageFilter,
        usage_search: referralsUsageSearchQuery,
      })
      const response = await fetch(`${API_URL}/api/admin/marketing/referrals?${params.toString()}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      const data = await response.json()
      if (response.ok) {
        setReferralsDashboard({
          stats: data.stats || {},
          customers: data.customers || [],
          code_usage: data.code_usage || [],
          pagination: data.pagination || {},
        })
      } else {
        setError(data.detail || 'Failed to load referrals dashboard')
      }
    } catch (err) {
      setError('Network error loading referrals dashboard')
    } finally {
      setLoadingReferrals(false)
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
        setNewPromotion({ name: '', description: '', discount_percent: 10, discount_type: null, total_codes: 10, code_prefix: '', custom_code: '', expiry_date: '', expiry_time: '', max_uses: '' })
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

  const openExpiryModal = (promotionId, code) => {
    setExpiryModalData({ promotionId, code })
    // Pre-fill with existing expiry if set
    if (code.expires_at) {
      const expiryDate = new Date(code.expires_at)
      const day = String(expiryDate.getDate()).padStart(2, '0')
      const month = String(expiryDate.getMonth() + 1).padStart(2, '0')
      const year = expiryDate.getFullYear()
      const hours = String(expiryDate.getHours()).padStart(2, '0')
      const minutes = String(expiryDate.getMinutes()).padStart(2, '0')
      setExpiryDate(`${day}/${month}/${year}`)
      setExpiryTime(`${hours}:${minutes}`)
    } else {
      setExpiryDate('')
      setExpiryTime('')
    }
    setShowExpiryModal(true)
  }

  const updatePromoCodeExpiry = async () => {
    if (!expiryModalData) return

    // Validate: both must be set or both must be empty
    if ((expiryDate && !expiryTime) || (!expiryDate && expiryTime)) {
      setPromotionMessage('Error: Both date and time must be set, or both must be empty to remove expiry')
      return
    }

    setUpdatingExpiry(true)
    try {
      let response
      const isBulk = expiryModalData.isBulk && expiryModalData.codeIds?.length > 0

      if (isBulk) {
        // Bulk update
        response = await fetch(`${API_URL}/api/admin/promo-codes/bulk-expiry`, {
          method: 'PATCH',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            code_ids: expiryModalData.codeIds,
            expiry_date: expiryDate || null,
            expiry_time: expiryTime || null
          })
        })
      } else {
        // Single code update
        response = await fetch(`${API_URL}/api/admin/promo-codes/${expiryModalData.code.id}/expiry`, {
          method: 'PATCH',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            expiry_date: expiryDate || null,
            expiry_time: expiryTime || null
          })
        })
      }

      if (response.ok) {
        const data = await response.json()

        if (isBulk) {
          // Bulk update - update all affected codes in local state
          const updatedCodesMap = {}
          data.codes.forEach(c => {
            updatedCodesMap[c.code_id] = { expires_at: c.expires_at, is_expired: c.is_expired }
          })

          setPromotionDetails(prev => ({
            ...prev,
            [expiryModalData.promotionId]: {
              ...prev[expiryModalData.promotionId],
              codes: prev[expiryModalData.promotionId].codes.map(code =>
                updatedCodesMap[code.id]
                  ? { ...code, ...updatedCodesMap[code.id] }
                  : code
              )
            }
          }))

          // Clear selection after bulk update
          setSelectedCodes(prev => ({ ...prev, [expiryModalData.promotionId]: new Set() }))
        } else {
          // Single code update
          setPromotionDetails(prev => ({
            ...prev,
            [expiryModalData.promotionId]: {
              ...prev[expiryModalData.promotionId],
              codes: prev[expiryModalData.promotionId].codes.map(code =>
                code.id === expiryModalData.code.id
                  ? { ...code, expires_at: data.expires_at, is_expired: data.is_expired }
                  : code
              )
            }
          }))
        }

        setShowExpiryModal(false)
        setExpiryModalData(null)
        setPromotionMessage(data.message)
      } else {
        const error = await response.json()
        setPromotionMessage(`Error: ${error.detail || 'Failed to update expiry'}`)
      }
    } catch (err) {
      console.error('Failed to update expiry:', err)
      setPromotionMessage('Network error updating expiry')
    } finally {
      setUpdatingExpiry(false)
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
    setGenerateCodesExpiryDate('')
    setGenerateCodesExpiryTime('')
    setShowGenerateCodesModal(true)
  }

  const generateMoreCodes = async () => {
    if (!generateCodesPromotion) return
    setGeneratingCodes(true)
    try {
      const requestBody = { count: generateCodesCount }
      if (generateCodesExpiryDate && generateCodesExpiryTime) {
        requestBody.expiry_date = generateCodesExpiryDate
        requestBody.expiry_time = generateCodesExpiryTime
      }
      if (generateCodesMaxUses !== '') {
        requestBody.max_uses = generateCodesMaxUses
      }
      const response = await fetch(`${API_URL}/api/admin/promotions/${generateCodesPromotion.id}/generate-codes`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      })
      if (response.ok) {
        const data = await response.json()
        const expiryMsg = generateCodesExpiryDate ? ` (expiring ${generateCodesExpiryDate} ${generateCodesExpiryTime})` : ''
        const multiUseMsg = generateCodesMaxUses === '0' ? ' (unlimited uses)' : generateCodesMaxUses ? ` (max ${generateCodesMaxUses} uses each)` : ''
        setPromotionMessage(`Successfully generated ${data.codes_created} new codes${expiryMsg}${multiUseMsg}`)
        setShowGenerateCodesModal(false)
        setGenerateCodesPromotion(null)
        setGenerateCodesExpiryDate('')
        setGenerateCodesExpiryTime('')
        setGenerateCodesMaxUses('')
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
    // New users default to fleet driver_type; admin checkbox flips the default
    // to NULL — see effect in the form's Admin onChange below.
    setUserForm({ first_name: '', last_name: '', email: '', phone: '', is_admin: false, is_active: true, driver_type: 'fleet' })
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
      driver_type: u.driver_type ?? '',
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
      // Empty string in the select means "no driver type" — send NULL so the
      // backend's model_fields_set check fires and the column is cleared.
      const payload = {
        ...userForm,
        driver_type: userForm.driver_type === '' ? null : userForm.driver_type,
      }
      const response = await fetch(url, {
        method,
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
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
        // Refresh bookings to reflect customer changes
        fetchBookings()
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

  const getReferralActionCopy = (action) => (
    {
      'cancel-code': {
        confirm: 'Cancel this referral promo code? The customer will need a new code before sharing again.',
        loading: 'Cancelling...',
        success: 'Referral code cancelled',
      },
      'generate-new-code': {
        confirm: 'Generate a new referral code? This will cancel the current code and email the replacement.',
        loading: 'Generating...',
        success: 'New referral code generated and sent',
      },
      'resend-code': {
        confirm: null,
        loading: 'Resending...',
        success: 'Referral code resent',
      },
    }[action]
  )

  const handleReferralDashboardAction = async (customer, action) => {
    if (!customer?.customer_id) return
    if (referralDashboardActionInFlightRef.current) return

    const actionCopy = getReferralActionCopy(action)
    if (!actionCopy) return
    if (actionCopy.confirm && !window.confirm(actionCopy.confirm)) return

    referralDashboardActionInFlightRef.current = true
    setReferralDashboardAction(`${customer.customer_id}:${action}`)
    setError('')
    try {
      const response = await fetch(`${API_URL}/api/admin/customers/${customer.customer_id}/referral/${action}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      const data = await response.json()
      if (response.ok) {
        await fetchReferralsDashboard()
        if (selectedCustomer?.id === customer.customer_id && data.referral_program) {
          setSelectedCustomer(prev => ({
            ...prev,
            referral_program: data.referral_program,
          }))
        }
      } else {
        setError(data.detail || 'Referral action failed')
      }
    } catch (err) {
      setError('Network error updating referral program')
    } finally {
      referralDashboardActionInFlightRef.current = false
      setReferralDashboardAction(null)
    }
  }

  const handleManualReferralInvite = async (e) => {
    e.preventDefault()
    if (sendingManualReferralInvite) return

    setSendingManualReferralInvite(true)
    setManualReferralInviteMessage('')
    setError('')
    try {
      const response = await fetch(`${API_URL}/api/admin/marketing/referrals/manual-invite`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          first_name: manualReferralInvite.first_name.trim(),
          last_name: manualReferralInvite.last_name.trim(),
          email: manualReferralInvite.email.trim(),
        }),
      })
      const data = await response.json()
      if (response.ok) {
        setManualReferralInviteMessage(data.message || 'Referral invite sent')
        setManualReferralInvite({ first_name: '', last_name: '', email: '' })
        setReferralsFilter('all')
        setReferralsCustomerSearch(data.customer?.email || '')
        setReferralsCustomerOffset(0)
        await fetchReferralsDashboard()
      } else {
        setError(data.detail || 'Failed to send referral invite')
      }
    } catch (err) {
      setError('Network error sending referral invite')
    } finally {
      setSendingManualReferralInvite(false)
    }
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
        // Add vehicle to selected customer
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
    if (!window.confirm('Are you sure you want to delete this customer?')) return

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
        // Update customer in list
        setCustomers(prev => prev.map(c =>
          c.id === selectedCustomer.id ? data.customer : c
        ))
        // Update selected customer
        setSelectedCustomer(prev => ({
          ...prev,
          email: data.customer.email,
          phone: data.customer.phone,
        }))
        setEditingCustomerId(null)
        setEditCustomerForm({ email: '', phone: '' })
        setCustomerMessage('Customer updated successfully')
        setTimeout(() => setCustomerMessage(''), 3000)
        fetchBookings()
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
          peak_day_increment: data.peak_day_increment ?? 0,
          show_price_range: data.show_price_range ?? false,
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

  const fetchBookings = async (loadAll = false) => {
    setLoadingData(true)
    setError('')
    try {
      const params = new URLSearchParams()
      if (loadAll) {
        params.append('days', '0')
      }
      const response = await fetch(`${API_URL}/api/admin/bookings?${params}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setBookings(data.bookings || data || [])
        setBookingsLoadAll(loadAll)
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

  // Today's bookings — bucketed on the effective (paid) date in UK time, to
  // match the backend reports. A booking that initiates at 23:59 and confirms
  // at 00:12 lands on the confirmed day, not the day it was started.
  const todaysBookings = useMemo(() => {
    // Get today's date in UK timezone (YYYY-MM-DD format)
    const todayUK = new Date().toLocaleDateString('en-CA', { timeZone: 'Europe/London' })

    // Payment-success time, falling back to created_at (manual/unpaid).
    const effectiveTs = (b) => b.payment?.paid_at || b.created_at

    let todays = bookings.filter(b => {
      const ts = effectiveTs(b)
      if (!ts) return false
      const effDate = new Date(ts).toLocaleDateString('en-CA', { timeZone: 'Europe/London' })
      return effDate === todayUK
    })

    // Hide test emails
    if (hideTestEmails) {
      todays = todays.filter(b => !isTestEmail(b.customer?.email))
    }

    // Sort by effective timestamp descending (newest first)
    todays.sort((a, b) => new Date(effectiveTs(b)) - new Date(effectiveTs(a)))

    return todays
  }, [bookings, hideTestEmails])

  // Group bookings by status. Refunded is its own bucket (TAG-initiated:
  // we made the customer's experience go wrong); Cancelled is customer-
  // initiated ("can't travel"). Don't conflate the two.
  const bookingsByStatus = useMemo(() => {
    const groups = {
      confirmed: [],
      completed: [],
      pending: [],
      cancelled: [],
      refunded: [],
    }

    filteredBookings.forEach(booking => {
      const status = (booking.status || 'pending').toLowerCase()
      if (groups[status]) {
        groups[status].push(booking)
      } else {
        // Truly unknown status — fall back to cancelled so it's visible.
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
                {booking.secondary_carpark && (
                  <div className="booking-detail">
                    <span className="detail-label">Car Park</span>
                    <span className="detail-value" title={booking.secondary_carpark.reason}>
                      {booking.secondary_carpark.assigned_carpark === 'secondary'
                        ? `Secondary (qualified — ${booking.secondary_carpark.reason})`
                        : `Main (${booking.secondary_carpark.reason})`}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Vehicle Information Section */}
          <div className="booking-section">
            <h4>Vehicle Information</h4>
            <div className="booking-section-content">
              <div className="booking-detail-row">
                <div className="booking-detail">
                  <span className="detail-label">Vehicle</span>
                  <span className="detail-value">
                    <span className="vehicle-reg">{booking.vehicle?.registration}</span>
                    {' '}
                    {booking.vehicle?.colour} {booking.vehicle?.make}
                    {shouldShowAlert(booking.vehicle?.tax_status, booking.vehicle?.mot_status) && (
                      <span
                        className="dvla-alert-badge"
                        title="Vehicle tax/MOT compliance alert"
                        aria-label="Vehicle compliance alert"
                      >
                        ⚠
                      </span>
                    )}
                  </span>
                </div>
                {(() => {
                  // Expiry dates only render for confirmed/refunded bookings
                  // (locked rule — these are the only statuses where we
                  // care about live compliance).
                  const status = booking.status?.toLowerCase()
                  const showDates = status === 'confirmed' || status === 'refunded'
                  return (
                    <>
                      <div className="booking-detail">
                        <span className="detail-label">Tax</span>
                        <span
                          className={`detail-value dvla-status dvla-status-${taxStatusClass(booking.vehicle?.tax_status)}`}
                          data-testid="dvla-tax-status"
                        >
                          {booking.vehicle?.tax_status || '—'}
                        </span>
                        {showDates && booking.vehicle?.tax_due_date && (
                          <span className="dvla-expiry-date">
                            Due {formatIsoDateUk(booking.vehicle.tax_due_date)}
                          </span>
                        )}
                      </div>
                      <div className="booking-detail">
                        <span className="detail-label">MOT</span>
                        <span
                          className={`detail-value dvla-status dvla-status-${motStatusClass(booking.vehicle?.mot_status)}`}
                          data-testid="dvla-mot-status"
                        >
                          {booking.vehicle?.mot_status || '—'}
                        </span>
                        {showDates && booking.vehicle?.mot_expiry_date && (
                          <span className="dvla-expiry-date">
                            Expires {formatIsoDateUk(booking.vehicle.mot_expiry_date)}
                          </span>
                        )}
                      </div>
                    </>
                  )
                })()}
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
                  <span className="detail-value">{formatDestination(booking.dropoff_destination) || '-'}</span>
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
                  <span className="detail-label">Arrival Date</span>
                  <span className="detail-value">{formatDate(resolveArrivalDate(booking))}</span>
                </div>
                <div className="booking-detail">
                  <span className="detail-label">Arrival Time</span>
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
                  <span className="detail-value">{formatDestination(booking.pickup_origin) || '-'}</span>
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

          {/* Refunded Section — shown whenever the payment row carries refund
              metadata, regardless of booking.status. This way the refund
              history stays visible after a `refunded → completed` transition
              (TAG-initiated goodwill refund + customer still parks). */}
          {booking.payment?.refund_amount_pence > 0 && (
            <div className="booking-section booking-refund-section">
              <h4>Refunded</h4>
              <div className="booking-section-content">
                <div className="booking-detail-row">
                  <div className="booking-detail">
                    <span className="detail-label">Refund Amount</span>
                    <span className="detail-value" style={{ color: '#ef4444', fontWeight: 600 }}>
                      −£{(booking.payment.refund_amount_pence / 100).toFixed(2)}
                    </span>
                  </div>
                  {booking.payment.refunded_at && (
                    <div className="booking-detail">
                      <span className="detail-label">Refunded At</span>
                      <span className="detail-value">
                        {new Date(booking.payment.refunded_at).toLocaleString('en-GB', {
                          day: '2-digit', month: '2-digit', year: 'numeric',
                          hour: '2-digit', minute: '2-digit',
                          timeZone: 'Europe/London',
                        })}
                      </span>
                    </div>
                  )}
                  {booking.payment.refund_reason && (
                    <div className="booking-detail">
                      <span className="detail-label">Reason</span>
                      <span className="detail-value">{booking.payment.refund_reason}</span>
                    </div>
                  )}
                  {booking.payment.refund_id && (
                    <div className="booking-detail">
                      <span className="detail-label">Stripe Refund ID</span>
                      <span className="detail-value" style={{ fontFamily: 'monospace', fontSize: '0.85em' }}>
                        {booking.payment.refund_id}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

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
              {/* Swap Vehicle button - only show if not completed and customer has multiple vehicles */}
              {booking.status?.toLowerCase() !== 'completed' && (booking.customer?.vehicle_count || 0) > 1 && (
                <button
                  className="action-btn swap-btn"
                  onClick={(e) => handleSwapVehicleClick(booking, e)}
                >
                  Swap Vehicle
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
                <>
                  <button
                    className="action-btn refund-btn"
                    onClick={(e) => handleRefundBookingClick(booking, e)}
                  >
                    Refund Booking
                  </button>
                  <button
                    className="action-btn"
                    onClick={(e) => handleRefundClick(booking, e)}
                    title="Open this payment in the Stripe dashboard (inspection or partial refunds)"
                  >
                    Open in Stripe ↗
                  </button>
                </>
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

              {/* Confirmation Email Status Indicator */}
              <div className="reminder-status-indicator">
                <span className="reminder-label">Confirmation</span>
                <span className={`reminder-badge ${booking.confirmation_email_sent ? 'sent' : 'pending'}`}>
                  {booking.confirmation_email_sent ? 'Sent ✓' : 'Pending'}
                </span>
              </div>

              {/* Parking Update Status Indicator */}
              <button
                type="button"
                className="reminder-status-indicator reminder-status-button"
                onClick={(e) => handleSendParkingUpdate(booking, e)}
                disabled={sendingParkingUpdateId === booking.id}
                title={getParkingUpdateTitle(booking)}
              >
                <span className="reminder-label">Parking Update</span>
                <span className={`reminder-badge ${getParkingUpdateStatus(booking)}`}>
                  {sendingParkingUpdateId === booking.id
                    ? 'Sending...'
                    : getParkingUpdateLabel(booking)}
                </span>
              </button>

              {/* 2-Day Reminder Status Indicator */}
              <div className="reminder-status-indicator">
                <span className="reminder-label">2-Day Reminder</span>
                <span className={`reminder-badge ${booking.reminder_2day_sent ? 'sent' : 'pending'}`}>
                  {booking.reminder_2day_sent ? 'Sent ✓' : 'Pending'}
                </span>
              </div>

              {/* Thank You Email Status Indicator - only for completed bookings */}
              {booking.status?.toLowerCase() === 'completed' && (
                <div className="reminder-status-indicator">
                  <span className="reminder-label">Thank You</span>
                  <span className={`reminder-badge ${booking.thank_you_email_sent ? 'sent' : 'pending'}`}>
                    {booking.thank_you_email_sent ? 'Sent ✓' : 'Pending'}
                  </span>
                </div>
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

  // Insert SMS variable at cursor position
  const insertSmsVariable = (variable, textareaRef, currentValue, setValue) => {
    const textarea = textareaRef.current
    if (!textarea) {
      // Fallback: append to end
      setValue(prev => ({ ...prev, content: prev.content + variable }))
      return
    }

    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const newContent = currentValue.substring(0, start) + variable + currentValue.substring(end)
    setValue(prev => ({ ...prev, content: newContent }))

    // Restore cursor position after the inserted variable
    setTimeout(() => {
      textarea.focus()
      textarea.setSelectionRange(start + variable.length, start + variable.length)
    }, 0)
  }

  // SMS Message functions
  const fetchSmsMessages = async () => {
    setLoadingMessages(true)
    try {
      const params = new URLSearchParams()
      if (smsDirectionFilter !== 'all') params.append('direction', smsDirectionFilter)
      if (smsStatusFilter !== 'all') params.append('status', smsStatusFilter)
      params.append('limit', '100')

      const response = await fetch(`${API_URL}/api/admin/sms/messages?${params}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setSmsMessages(data.messages || [])
      }
    } catch (err) {
      console.error('Failed to fetch SMS messages:', err)
    } finally {
      setLoadingMessages(false)
    }
  }

  const fetchSmsTemplates = async () => {
    setLoadingTemplates(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/sms/templates`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setSmsTemplates(Array.isArray(data) ? data : [])
      }
    } catch (err) {
      console.error('Failed to fetch SMS templates:', err)
    } finally {
      setLoadingTemplates(false)
    }
  }

  const fetchSmsStats = async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/sms/stats`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setSmsStats(data)
      }
    } catch (err) {
      console.error('Failed to fetch SMS stats:', err)
    }
  }

  // Fetch SMS threads (conversations grouped by phone)
  const fetchSmsThreads = async () => {
    setLoadingThreads(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/sms/threads`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setSmsThreads(data.threads || [])
      }
    } catch (err) {
      console.error('Failed to fetch SMS threads:', err)
    } finally {
      setLoadingThreads(false)
    }
  }

  // Fetch conversation messages for a specific thread
  const fetchConversation = async (phoneNumber, options = {}) => {
    const { silent = false } = options
    if (!silent) setLoadingConversation(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/sms/messages/conversation/${encodeURIComponent(phoneNumber)}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setThreadMessages(data.messages || [])
        // Refresh thread list to update unread counts
        fetchSmsThreads()
        fetchSmsStats()
        // Scroll to bottom of conversation
        setTimeout(() => {
          conversationEndRef.current?.scrollIntoView({ behavior: 'smooth' })
        }, 100)
      }
    } catch (err) {
      console.error('Failed to fetch conversation:', err)
    } finally {
      if (!silent) setLoadingConversation(false)
    }
  }

  // Select a thread and load its messages
  const selectThread = (thread) => {
    setSelectedThread(thread)
    setReplyContent('')
    fetchConversation(thread.phone_number)
  }

  // Send a reply in the current conversation
  const sendReply = async () => {
    if (!selectedThread || !replyContent.trim()) return
    setSendingReply(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/sms/send`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          phone: selectedThread.phone_number,
          content: replyContent.trim(),
          customer_id: selectedThread.customer?.id || null,
        }),
      })
      if (response.ok) {
        setReplyContent('')
        fetchConversation(selectedThread.phone_number)
      } else {
        const data = await response.json()
        setMessagesMessage(`Error: ${data.detail || 'Failed to send message'}`)
        setTimeout(() => setMessagesMessage(''), 5000)
      }
    } catch (err) {
      console.error('Failed to send reply:', err)
      setMessagesMessage('Error: Failed to send message')
      setTimeout(() => setMessagesMessage(''), 5000)
    } finally {
      setSendingReply(false)
    }
  }

  // Toggle thread selection for bulk operations
  const toggleThreadSelection = (phoneNumber, e) => {
    e.stopPropagation()
    setSelectedThreads(prev => {
      const newSet = new Set(prev)
      if (newSet.has(phoneNumber)) {
        newSet.delete(phoneNumber)
      } else {
        newSet.add(phoneNumber)
      }
      return newSet
    })
  }

  // Select/deselect all threads
  const toggleSelectAll = () => {
    if (selectedThreads.size === smsThreads.length) {
      setSelectedThreads(new Set())
    } else {
      setSelectedThreads(new Set(smsThreads.map(t => t.phone_number)))
    }
  }

  // Delete a single thread
  const deleteThread = async (phoneNumber) => {
    if (!confirm(`Delete all messages with ${phoneNumber}?`)) return

    try {
      const response = await fetch(`${API_URL}/api/admin/sms/threads/${encodeURIComponent(phoneNumber)}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        if (selectedThread?.phone_number === phoneNumber) {
          setSelectedThread(null)
          setThreadMessages([])
        }
        fetchSmsThreads()
        fetchSmsStats()
      }
    } catch (err) {
      console.error('Failed to delete thread:', err)
    }
  }

  // Bulk delete selected threads
  const bulkDeleteThreads = async () => {
    if (selectedThreads.size === 0) return
    if (!confirm(`Delete ${selectedThreads.size} conversation(s)?`)) return

    setDeletingThreads(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/sms/threads/bulk-delete`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ phone_numbers: Array.from(selectedThreads) }),
      })
      if (response.ok) {
        if (selectedThread && selectedThreads.has(selectedThread.phone_number)) {
          setSelectedThread(null)
          setThreadMessages([])
        }
        setSelectedThreads(new Set())
        fetchSmsThreads()
        fetchSmsStats()
      }
    } catch (err) {
      console.error('Failed to bulk delete threads:', err)
    } finally {
      setDeletingThreads(false)
    }
  }

  const fetchSmsDrafts = async () => {
    setLoadingDrafts(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/sms/drafts`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setSmsDrafts(data.drafts || [])
      }
    } catch (err) {
      console.error('Failed to fetch SMS drafts:', err)
    } finally {
      setLoadingDrafts(false)
    }
  }

  const handleSaveDraft = async () => {
    setSavingDraft(true)
    setMessagesMessage('')
    try {
      const url = editingDraft
        ? `${API_URL}/api/admin/sms/drafts/${editingDraft.id}`
        : `${API_URL}/api/admin/sms/drafts`
      const method = editingDraft ? 'PUT' : 'POST'

      const response = await fetch(url, {
        method,
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          phone: sendSmsForm.phone,
          content: sendSmsForm.content,
          booking_id: sendSmsForm.booking_id ? parseInt(sendSmsForm.booking_id) : null,
          customer_id: sendSmsForm.customer_id ? parseInt(sendSmsForm.customer_id) : null,
        }),
      })
      if (response.ok) {
        setMessagesMessage(editingDraft ? 'Draft updated!' : 'Draft saved!')
        setTimeout(() => setMessagesMessage(''), 3000)
        setShowSendSmsModal(false)
        setSendSmsForm({ phone: '', content: '', booking_id: '', customer_id: '' })
        setSelectedSmsBooking(null)
        setSmsBookingSearch('')
        setSmsBookingResults([])
        setEditingDraft(null)
        fetchSmsDrafts()
      } else {
        const err = await response.json()
        setMessagesMessage(`Error: ${err.detail || 'Failed to save draft'}`)
      }
    } catch (err) {
      console.error('Failed to save draft:', err)
      setMessagesMessage('Error: Failed to save draft')
    } finally {
      setSavingDraft(false)
    }
  }

  const handleSendDraft = async (draftId) => {
    setSendingDraftId(draftId)
    setMessagesMessage('')
    try {
      const response = await fetch(`${API_URL}/api/admin/sms/drafts/${draftId}/send`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        setMessagesMessage('Draft sent successfully!')
        setTimeout(() => setMessagesMessage(''), 3000)
        fetchSmsDrafts()
        fetchSmsMessages()
        fetchSmsStats()
      } else {
        const err = await response.json()
        setMessagesMessage(`Error: ${err.detail || 'Failed to send draft'}`)
      }
    } catch (err) {
      console.error('Failed to send draft:', err)
      setMessagesMessage('Error: Failed to send draft')
    } finally {
      setSendingDraftId(null)
    }
  }

  const handleDeleteDraft = async (draftId) => {
    setDeletingDraftId(draftId)
    try {
      const response = await fetch(`${API_URL}/api/admin/sms/drafts/${draftId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        setMessagesMessage('Draft deleted!')
        setTimeout(() => setMessagesMessage(''), 3000)
        fetchSmsDrafts()
      } else {
        const err = await response.json()
        setMessagesMessage(`Error: ${err.detail || 'Failed to delete draft'}`)
      }
    } catch (err) {
      console.error('Failed to delete draft:', err)
    } finally {
      setDeletingDraftId(null)
    }
  }

  const handleEditDraft = (draft) => {
    setEditingDraft(draft)
    setSendSmsForm({
      phone: draft.phone_number || '',
      content: draft.content || '',
      booking_id: draft.booking_id || '',
      customer_id: draft.customer_id || '',
    })
    if (draft.booking_reference) {
      setSelectedSmsBooking({
        id: draft.booking_id,
        reference: draft.booking_reference,
        customer_first_name: draft.customer_name?.split(' ')[0] || '',
        customer_last_name: draft.customer_name?.split(' ').slice(1).join(' ') || '',
      })
    }
    setShowSendSmsModal(true)
  }

  const refreshSmsStatuses = async () => {
    setLoadingMessages(true)
    setMessagesMessage('')
    try {
      const response = await fetch(`${API_URL}/api/admin/sms/refresh-statuses`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        if (data.updated > 0) {
          setMessagesMessage(`Updated ${data.updated} message status${data.updated > 1 ? 'es' : ''}`)
        } else {
          setMessagesMessage('All statuses are up to date')
        }
        setTimeout(() => setMessagesMessage(''), 3000)
        if (selectedThread) {
          fetchConversation(selectedThread.phone_number, { silent: true })
        } else {
          fetchSmsMessages()
        }
        fetchSmsStats()
      } else {
        const err = await response.json()
        setMessagesMessage(`Error: ${err.detail || 'Failed to refresh statuses'}`)
      }
    } catch (err) {
      console.error('Failed to refresh SMS statuses:', err)
      setMessagesMessage('Error: Failed to refresh statuses')
    } finally {
      setLoadingMessages(false)
    }
  }

  const handleSendSms = async () => {
    setSendingSms(true)
    setMessagesMessage('')
    try {
      const response = await fetch(`${API_URL}/api/admin/sms/send`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          phone: sendSmsForm.phone,
          content: sendSmsForm.content,
          booking_id: sendSmsForm.booking_id ? parseInt(sendSmsForm.booking_id) : null,
          customer_id: sendSmsForm.customer_id ? parseInt(sendSmsForm.customer_id) : null,
        }),
      })

      if (response.ok) {
        setMessagesMessage('SMS sent successfully!')
        setTimeout(() => setMessagesMessage(''), 3000)
        setShowSendSmsModal(false)
        setSendSmsForm({ phone: '', content: '', booking_id: '', customer_id: '' })
        fetchSmsMessages()
        fetchSmsStats()
      } else {
        const data = await response.json()
        setMessagesMessage(`Error: ${data.detail || 'Failed to send SMS'}`)
      }
    } catch (err) {
      setMessagesMessage(`Error: ${err.message}`)
    } finally {
      setSendingSms(false)
    }
  }

  const handleSaveTemplate = async () => {
    setSavingTemplate(true)
    setMessagesMessage('')
    try {
      const response = await fetch(`${API_URL}/api/admin/sms/templates/${editingTemplate.id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: editingTemplate.name,
          content: editingTemplate.content,
          description: editingTemplate.description,
          is_active: editingTemplate.is_active,
          trigger_event: editingTemplate.trigger_event || null,
          is_automated: !!editingTemplate.trigger_event,
        }),
      })

      if (response.ok) {
        setMessagesMessage('Template saved successfully!')
        setTimeout(() => setMessagesMessage(''), 3000)
        setShowEditTemplateModal(false)
        setEditingTemplate(null)
        fetchSmsTemplates()
      } else {
        const data = await response.json()
        setMessagesMessage(`Error: ${data.detail || 'Failed to save template'}`)
      }
    } catch (err) {
      setMessagesMessage(`Error: ${err.message}`)
    } finally {
      setSavingTemplate(false)
    }
  }

  const handleCreateTemplate = async () => {
    setCreatingTemplate(true)
    setMessagesMessage('')
    try {
      const response = await fetch(`${API_URL}/api/admin/sms/templates`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: newTemplate.name,
          content: newTemplate.content,
          description: newTemplate.description,
          is_active: newTemplate.is_active,
          trigger_event: newTemplate.trigger_event || null,
          is_automated: !!newTemplate.trigger_event,
        }),
      })

      if (response.ok) {
        setMessagesMessage('Template created successfully!')
        setTimeout(() => setMessagesMessage(''), 3000)
        setShowCreateTemplateModal(false)
        setNewTemplate({ name: '', content: '', description: '', is_active: true, trigger_event: null })
        fetchSmsTemplates()
      } else {
        const data = await response.json()
        setMessagesMessage(`Error: ${data.detail || 'Failed to create template'}`)
      }
    } catch (err) {
      setMessagesMessage(`Error: ${err.message}`)
    } finally {
      setCreatingTemplate(false)
    }
  }

  const handleDeleteTemplate = async () => {
    if (!templateToDelete) return
    setDeletingTemplateId(templateToDelete.id)
    try {
      const response = await fetch(`${API_URL}/api/admin/sms/templates/${templateToDelete.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        setMessagesMessage('Template deleted successfully!')
        setTimeout(() => setMessagesMessage(''), 3000)
        setTemplateToDelete(null)
        fetchSmsTemplates()
      } else {
        const data = await response.json()
        setMessagesMessage(`Error: ${data.detail || 'Failed to delete template'}`)
      }
    } catch (err) {
      setMessagesMessage(`Error: ${err.message}`)
    } finally {
      setDeletingTemplateId(null)
    }
  }

  const handleResendMessage = async (messageId) => {
    setResendingMessageId(messageId)
    try {
      const response = await fetch(`${API_URL}/api/admin/sms/messages/${messageId}/resend`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        setMessagesMessage('Message resent successfully!')
        setTimeout(() => setMessagesMessage(''), 3000)
        fetchSmsMessages()
      } else {
        const data = await response.json()
        setMessagesMessage(`Error: ${data.detail || 'Failed to resend message'}`)
      }
    } catch (err) {
      setMessagesMessage(`Error: ${err.message}`)
    } finally {
      setResendingMessageId(null)
    }
  }

  const handleDeleteMessage = async () => {
    if (!messageToDelete) return
    setDeletingMessageId(messageToDelete.id)
    try {
      const response = await fetch(`${API_URL}/api/admin/sms/messages/${messageToDelete.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        setMessagesMessage('Message deleted successfully!')
        setTimeout(() => setMessagesMessage(''), 3000)
        setMessageToDelete(null)
        fetchSmsMessages()
      } else {
        const data = await response.json()
        setMessagesMessage(`Error: ${data.detail || 'Failed to delete message'}`)
      }
    } catch (err) {
      setMessagesMessage(`Error: ${err.message}`)
    } finally {
      setDeletingMessageId(null)
    }
  }

  const searchBookingsForSms = async (searchTerm) => {
    if (!searchTerm || searchTerm.length < 2) {
      setSmsBookingResults([])
      return
    }

    setSearchingSmsBookings(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/bookings?search=${encodeURIComponent(searchTerm)}&limit=10`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        // Filter to only show bookings with phone numbers
        const withPhone = (data.bookings || []).filter(b => b.customer?.phone)
        setSmsBookingResults(withPhone.slice(0, 5))
      }
    } catch (err) {
      console.error('Failed to search bookings:', err)
    } finally {
      setSearchingSmsBookings(false)
    }
  }

  const selectBookingForSms = (booking) => {
    setSelectedSmsBooking(booking)
    setSendSmsForm(prev => ({
      ...prev,
      phone: booking.customer?.phone || '',
      booking_id: booking.id?.toString() || '',
      customer_id: booking.customer?.id?.toString() || '',
    }))
    setSmsBookingSearch('')
    setSmsBookingResults([])
  }

  const clearSelectedBooking = () => {
    setSelectedSmsBooking(null)
    setSendSmsForm(prev => ({
      ...prev,
      phone: '',
      booking_id: '',
      customer_id: '',
    }))
  }

  const formatPhoneForDisplay = (phone) => {
    if (!phone) return '-'
    // Format 447XXXXXXXXX as +44 7XXX XXX XXX
    if (phone.startsWith('44') && phone.length === 12) {
      return `+44 ${phone.slice(2, 6)} ${phone.slice(6, 9)} ${phone.slice(9)}`
    }
    return phone
  }

  const getSmsStatusBadge = (status) => {
    const statusColors = {
      pending: 'status-pending',
      sent: 'status-confirmed',
      delivered: 'status-completed',
      failed: 'status-cancelled',
    }
    return statusColors[status] || 'status-pending'
  }

  const formatPence = (amountPence) => (
    amountPence === null || amountPence === undefined ? '-' : `£${(amountPence / 100).toFixed(2)}`
  )

  const filteredReferralCustomers = useMemo(() => {
    return referralsDashboard.customers || []
  }, [referralsDashboard.customers])

  const filteredReferralUsage = useMemo(() => {
    return referralsDashboard.code_usage || []
  }, [referralsDashboard.code_usage])

  const referralsPagination = referralsDashboard.pagination || {}
  const referralsDashboardHasLoaded = Boolean(
    referralsDashboard.pagination ||
    (referralsDashboard.customers || []).length ||
    (referralsDashboard.code_usage || []).length ||
    Object.keys(referralsDashboard.stats || {}).length
  )
  const referralCustomerTotal = referralsPagination.customer_total || 0
  const referralUsageTotal = referralsPagination.code_usage_filtered_total ?? referralsPagination.code_usage_total ?? 0
  const referralCustomerStart = referralCustomerTotal ? referralsCustomerOffset + 1 : 0
  const referralCustomerEnd = Math.min(referralsCustomerOffset + referralsCustomerPageSize, referralCustomerTotal)
  const referralUsageStart = referralUsageTotal ? referralsUsageOffset + 1 : 0
  const referralUsageEnd = Math.min(referralsUsageOffset + referralsUsagePageSize, referralUsageTotal)

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
    const isClosing = expandedBookingId === bookingId
    setExpandedBookingId(isClosing ? null : bookingId)

    if (!isClosing) {
      window.requestAnimationFrame(() => {
        const element = document.querySelector(`.booking-card[data-booking-id="${bookingId}"]`)
        element?.scrollIntoView({ behavior: 'auto', block: 'start' })
      })
    }
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
      // Dropoff/Departure details - convert ISO date to UK format for display
      dropoff_date: isoToUkDate(booking.dropoff_date) || '',
      dropoff_time: booking.dropoff_time || '',
      flight_departure_time: booking.flight_departure_time || '',
      dropoff_airline_name: booking.dropoff_airline_name || '',
      dropoff_flight_number: booking.dropoff_flight_number || '',
      dropoff_destination: booking.dropoff_destination || '',
      // Pickup/Return details - convert ISO date to UK format for display
      pickup_date: isoToUkDate(booking.pickup_date) || '',
      // Arrival date is editable independently of pickup_date. For legacy rows
      // where flight_arrival_date is NULL we derive a sensible default via
      // resolveArrivalDate (which reverses the +30-min rollover for late-night
      // arrivals — naive pickup_date as the default would silently set the
      // wrong day for any 23:30+ flight, see TAG-MNF73277 incident 2026-05-21).
      flight_arrival_date: isoToUkDate(resolveArrivalDate(booking)) || '',
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
          // Dropoff/Departure details - convert UK date back to ISO format for API
          dropoff_date: ukToIsoDate(editForm.dropoff_date) || null,
          dropoff_time: editForm.dropoff_time || null,
          flight_departure_time: editForm.flight_departure_time || null,
          dropoff_airline_name: editForm.dropoff_airline_name || null,
          dropoff_flight_number: editForm.dropoff_flight_number || null,
          dropoff_destination: editForm.dropoff_destination || null,
          // Pickup/Return details - convert UK date back to ISO format for API
          pickup_date: ukToIsoDate(editForm.pickup_date) || null,
          flight_arrival_date: ukToIsoDate(editForm.flight_arrival_date) || null,
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
    // Open Stripe dashboard to the payment intent (inspection / partial refunds)
    const paymentIntentId = booking.payment?.stripe_payment_intent_id
    if (paymentIntentId) {
      // Stripe dashboard URL for payment intent
      const stripeUrl = `https://dashboard.stripe.com/payments/${paymentIntentId}`
      window.open(stripeUrl, '_blank')
    } else {
      setError('No payment found for this booking')
    }
  }

  const handleRefundBookingClick = (booking, e) => {
    e.stopPropagation()
    setBookingToRefund(booking)
    setRefundReason('requested_by_customer')
    setRefundModalError('')
    setShowRefundModal(true)
  }

  const handleConfirmRefundBooking = async () => {
    if (!bookingToRefund) return
    const paymentIntentId = bookingToRefund.payment?.stripe_payment_intent_id
    if (!paymentIntentId) {
      setRefundModalError('No payment intent on this booking.')
      return
    }

    setProcessingRefund(true)
    setRefundModalError('')
    try {
      const response = await fetch(
        `${API_URL}/api/admin/refund/${paymentIntentId}?booking_id=${bookingToRefund.id}&reason=${refundReason}`,
        {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
        }
      )
      const data = await response.json().catch(() => ({}))
      if (response.ok) {
        setShowRefundModal(false)
        setBookingToRefund(null)
        fetchBookings()
      } else {
        setRefundModalError(data.detail || 'Refund failed.')
      }
    } catch (err) {
      console.error('Error processing refund:', err)
      setRefundModalError('Network error processing refund.')
    } finally {
      setProcessingRefund(false)
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

  const getParkingUpdateStatus = (booking) => {
    const emailStatus = booking.parking_update_email_status || 'pending'
    const smsStatus = booking.parking_update_sms_status || 'pending'
    if (emailStatus === 'failed') {
      return 'failed'
    }
    if (emailStatus === 'sent' && smsStatus === 'sent') {
      return 'sent'
    }
    if (emailStatus === 'sent') {
      return 'partial'
    }
    return 'pending'
  }

  const getParkingUpdateLabel = (booking) => {
    const emailStatus = booking.parking_update_email_status || 'pending'
    const smsStatus = booking.parking_update_sms_status || 'pending'
    if (emailStatus === 'failed') {
      return 'Failed'
    }
    if (emailStatus === 'sent' && smsStatus === 'sent') {
      return 'Sent ✓'
    }
    if (emailStatus === 'sent' && smsStatus === 'failed') {
      return 'Email Sent / SMS Failed'
    }
    if (emailStatus === 'sent' && smsStatus === 'disabled') {
      return 'Email Sent / SMS Off'
    }
    if (emailStatus === 'sent') {
      return `Email Sent / SMS ${smsStatus}`
    }
    return 'Pending'
  }

  const getParkingUpdateTitle = (booking) => {
    const details = []
    details.push(`Email status: ${booking.parking_update_email_status || 'pending'}`)
    details.push(`SMS status: ${booking.parking_update_sms_status || 'pending'}`)
    if (booking.parking_update_email_sent_at) {
      details.push(`Email: ${formatDateTimeUK(booking.parking_update_email_sent_at)}`)
    }
    if (booking.parking_update_email_attempt_count) {
      details.push(`Email attempts: ${booking.parking_update_email_attempt_count}`)
    }
    if (booking.parking_update_email_last_attempt_at) {
      details.push(`Last email attempt: ${formatDateTimeUK(booking.parking_update_email_last_attempt_at)}`)
    }
    if (booking.parking_update_sms_sent_at) {
      details.push(`SMS: ${formatDateTimeUK(booking.parking_update_sms_sent_at)}`)
    }
    if (booking.parking_update_last_error) {
      details.push(`Error: ${booking.parking_update_last_error}`)
    }
    return details.length ? details.join(' | ') : 'Click to send parking update'
  }

  const handleSendParkingUpdate = async (booking, e) => {
    e.stopPropagation()
    if (sendingParkingUpdateId === booking.id) return

    setSendingParkingUpdateId(booking.id)
    setError('')
    setSuccessMessage('')

    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/${booking.id}/send-parking-update`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      })
      const data = await response.json()

      if (response.ok) {
        setBookings(prev => prev.map(item => (
          item.id === booking.id
            ? {
                ...item,
                parking_update_email_status: data.parking_update_email_status,
                parking_update_email_sent_at: data.parking_update_email_sent_at,
                parking_update_email_attempt_count: data.parking_update_email_attempt_count,
                parking_update_email_last_attempt_at: data.parking_update_email_last_attempt_at,
                parking_update_sms_status: data.parking_update_sms_status,
                parking_update_sms_sent_at: data.parking_update_sms_sent_at,
                parking_update_last_error: data.parking_update_last_error,
              }
            : item
        )))
        setSuccessMessage(data.message || 'Parking update sent')
        setTimeout(() => setSuccessMessage(''), 3000)
      } else {
        setError(data.detail || 'Failed to send parking update')
      }
    } catch (err) {
      setError('Network error while sending parking update')
    } finally {
      setSendingParkingUpdateId(null)
    }
  }

  // Swap Vehicle handlers
  const handleSwapVehicleClick = async (booking, e) => {
    e.stopPropagation()
    setBookingForSwap(booking)
    setLoadingCustomerVehicles(true)
    setShowSwapVehicleModal(true)

    try {
      // Fetch customer details including vehicles
      const response = await fetch(`${API_URL}/api/admin/customers/${booking.customer?.id}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })

      if (response.ok) {
        const data = await response.json()
        // Filter out the current vehicle
        const otherVehicles = data.vehicles.filter(v => v.id !== booking.vehicle?.id)
        setCustomerVehiclesForSwap(otherVehicles)
      } else {
        setError('Failed to fetch customer vehicles')
        setShowSwapVehicleModal(false)
      }
    } catch (err) {
      setError('Network error fetching vehicles')
      setShowSwapVehicleModal(false)
    } finally {
      setLoadingCustomerVehicles(false)
    }
  }

  const handleSelectVehicleForSwap = (vehicle) => {
    setSwapConfirmVehicle(vehicle)
  }

  const handleConfirmSwapVehicle = async () => {
    if (!bookingForSwap || !swapConfirmVehicle) return

    setSwappingVehicle(true)
    setError('')

    // Store values before modal close clears state
    const bookingId = bookingForSwap.id
    const vehicleId = swapConfirmVehicle.id

    try {
      const response = await fetch(`${API_URL}/api/admin/bookings/${bookingId}/swap-vehicle`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ vehicle_id: vehicleId }),
      })

      if (response.ok) {
        // Close modals and refresh bookings list
        closeSwapVehicleModal()
        fetchBookings()
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to swap vehicle')
      }
    } catch (err) {
      setError('Network error while swapping vehicle')
    } finally {
      setSwappingVehicle(false)
    }
  }

  const closeSwapVehicleModal = () => {
    setShowSwapVehicleModal(false)
    setSwapConfirmVehicle(null)
    setBookingForSwap(null)
    setCustomerVehiclesForSwap([])
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

  // resolveArrivalDate now lives in src/utils/arrivalDate.js so it can be
  // H/U/E/B tested in isolation. Used at line ~4104 (booking-detail card)
  // and line ~5390 (Edit Booking form initialiser).

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

  // Toggle category expansion
  const toggleCategory = (categoryName) => {
    setExpandedCategories(prev => ({
      ...prev,
      [categoryName]: !prev[categoryName]
    }))
  }

  // Handle tab selection - also expand the parent category
  const handleTabSelect = (tabId) => {
    applyAdminItemSelection(tabId)
    navigate(getAdminRouteForItem(tabId))
    if (typeof window !== 'undefined' && window.matchMedia?.('(max-width: 768px)').matches) {
      setSidebarCollapsed(true)
    }
  }

  // Check if a nav item is active
  const isNavItemActive = (itemId) => {
    // Marketing sub-tabs
    if (itemId === 'marketing' && activeTab === 'marketing' && marketingSubTab === 'subscribers') return true
    if (itemId === 'promotions' && activeTab === 'marketing' && marketingSubTab === 'promotions') return true
    if (itemId === 'campaigns' && activeTab === 'marketing' && marketingSubTab === 'campaigns') return true
    if (itemId === 'referrals' && activeTab === 'marketing' && marketingSubTab === 'referrals') return true
    if (itemId === 'sources' && activeTab === 'marketing' && marketingSubTab === 'sources') return true
    // Reports sub-tabs
    if (itemId === 'reports-growth' && activeTab === 'reports' && reportsSubTab === 'growth') return true
    if (itemId === 'reports-occupancy' && activeTab === 'reports' && reportsSubTab === 'occupancy') return true
    if (itemId === 'reports-routes' && activeTab === 'reports' && reportsSubTab === 'popular') return true
    if (itemId === 'reports-map' && activeTab === 'reports' && reportsSubTab === 'map') return true
    if (itemId === 'reports-financial' && activeTab === 'reports' && reportsSubTab === 'financial') return true
    if (itemId === 'reports-sessions' && activeTab === 'reports' && reportsSubTab === 'sessions') return true
    if (itemId === 'reports-analytics' && activeTab === 'reports' && reportsSubTab === 'analytics') return true
    if (itemId === 'reports-forecast' && activeTab === 'reports' && reportsSubTab === 'forecast') return true
    // Standard tabs (exclude marketing and reports sub-tab ids)
    const subTabIds = ['marketing', 'promotions', 'campaigns', 'referrals', 'sources', 'reports-growth', 'reports-occupancy', 'reports-routes', 'reports-map', 'reports-financial', 'reports-sessions', 'reports-analytics', 'reports-forecast']
    if (!subTabIds.includes(itemId)) {
      return activeTab === itemId
    }
    return false
  }

  const activeAdminItemId = getAdminItemIdForSelection(activeTab, marketingSubTab, reportsSubTab)
  const activeAdminItemMeta = ADMIN_ITEM_META_BY_ID[activeAdminItemId] || ADMIN_ITEM_META_BY_ID[ADMIN_DEFAULT_ITEM_ID]

  const messagesSectionProps = {
    fetchSmsMessages,
    fetchSmsStats,
    loadingMessages,
    refreshSmsStatuses,
    setShowSendSmsModal,
    messagesMessage,
    smsStats,
    messagesSubTab,
    setMessagesSubTab,
    setSelectedThread,
    fetchSmsThreads,
    fetchSmsDrafts,
    smsThreads,
    selectedThreads,
    toggleSelectAll,
    loadingThreads,
    selectedThread,
    selectThread,
    toggleThreadSelection,
    formatPhoneForDisplay,
    fetchConversation,
    loadingConversation,
    deleteThread,
    threadMessages,
    conversationEndRef,
    replyContent,
    setReplyContent,
    sendReply,
    sendingReply,
    setSmsDirectionFilter,
    setSmsStatusFilter,
    getSmsStatusBadge,
    smsMessages,
    setExpandedMessageId,
    expandedMessageId,
    resendingMessageId,
    handleResendMessage,
    setMessageToDelete,
    deletingMessageId,
    handleDeleteMessage,
    loadingTemplates,
    smsTemplates,
    setShowCreateTemplateModal,
    setSendSmsForm,
    setEditingTemplate,
    setShowEditTemplateModal,
    setTemplateToDelete,
    editingTemplate,
    savingTemplate,
    deletingTemplateId,
    templateToDelete,
    showEditTemplateModal,
    editTemplateTextareaRef,
    handleSaveTemplate,
    newTemplate,
    creatingTemplate,
    showCreateTemplateModal,
    newTemplateTextareaRef,
    setNewTemplate,
    showSendSmsModal,
    sendSmsForm,
    smsBookingSearch,
    setSmsBookingSearch,
    searchingSmsBookings,
    smsBookingResults,
    setSmsBookingResults,
    searchBookingsForSms,
    selectBookingForSms,
    selectedSmsBooking,
    setSelectedSmsBooking,
    handleSaveDraft,
    savingDraft,
    editingDraft,
    handleSendSms,
    sendingSms,
    handleEditDraft,
    loadingDrafts,
    smsDrafts,
    sendingDraftId,
    handleSendDraft,
    handleDeleteDraft,
    deletingDraftId,
    clearSelectedBooking,
    smsVariables,
    insertSmsVariable,
    sendSmsTextareaRef,
    handleCreateTemplate,
    handleDeleteTemplate,
    setEditingDraft,
    messageToDelete,
    bulkDeleteThreads,
    deletingThreads,
    smsStatusFilter,
  }

  return (
    <div className={`admin-layout ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      {/* Header */}
      <header className="admin-header">
        <div className="admin-header-left">
          <button
            className="sidebar-toggle"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {sidebarCollapsed ? '☰' : '✕'}
          </button>
          <Link to="/">
            <img src="/assets/logo.svg" alt="TAG Parking" className="admin-logo" />
          </Link>
          <h1>Admin</h1>
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

      <div className="admin-body">
        {/* Sidebar */}
        <aside className="admin-sidebar">
          <nav className="admin-sidebar-nav">
            {NAV_STRUCTURE
              .filter(cat => !cat.restrictToUserIds || cat.restrictToUserIds.includes(user?.id))
              .map(cat => (
              <div key={cat.category} className="nav-category">
                <button
                  className={`nav-category-header ${expandedCategories[cat.category] ? 'expanded' : ''}`}
                  onClick={() => toggleCategory(cat.category)}
                >
                  <span className="nav-category-icon">{cat.icon}</span>
                  {!sidebarCollapsed && (
                    <>
                      <span className="nav-category-label">{cat.category}</span>
                      <span className="nav-category-arrow">
                        {expandedCategories[cat.category] ? '▼' : '▶'}
                      </span>
                    </>
                  )}
                </button>
                {expandedCategories[cat.category] && !sidebarCollapsed && (
                  <div className="nav-category-items">
                    {cat.items.map(item => (
                      <button
                        key={item.id}
                        className={`nav-item ${isNavItemActive(item.id) ? 'active' : ''}`}
                        onClick={() => handleTabSelect(item.id)}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </nav>
        </aside>

        {/* Main Content */}
        <main className="admin-main">
        <nav className="admin-breadcrumbs" aria-label="Admin breadcrumb">
          <ol className="admin-breadcrumb-list">
            <li className="admin-breadcrumb-item">
              <Link to={ADMIN_DEFAULT_ROUTE} className="admin-breadcrumb-link">
                <span className="admin-breadcrumb-icon" aria-hidden="true">⌂</span>
                <span>Admin</span>
              </Link>
            </li>
            <li className="admin-breadcrumb-separator" aria-hidden="true">›</li>
            <li className="admin-breadcrumb-item">
              <Link to={getDefaultRouteForCategory(activeAdminItemMeta.category)} className="admin-breadcrumb-link">
                {activeAdminItemMeta.category}
              </Link>
            </li>
            <li className="admin-breadcrumb-separator" aria-hidden="true">›</li>
            <li className="admin-breadcrumb-item admin-breadcrumb-current" aria-current="page">
              {activeAdminItemMeta.itemLabel}
            </li>
          </ol>
        </nav>
        {error && <div className="admin-error">{error}</div>}
        {successMessage && <div className="admin-success">{successMessage}</div>}

        {activeTab === 'bookings' && (
          <div className="admin-section">
            <div className="admin-section-header">
              <h2>Bookings {!bookingsLoadAll && <span className="filter-badge">Last 30 days</span>}</h2>
              <div style={{ display: 'flex', gap: '8px' }}>
                {!bookingsLoadAll && (
                  <button onClick={() => fetchBookings(true)} className="admin-refresh" disabled={loadingData}>
                    {loadingData ? 'Loading...' : 'Load All'}
                  </button>
                )}
                {bookingsLoadAll && (
                  <button onClick={() => fetchBookings(false)} className="admin-refresh" disabled={loadingData}>
                    {loadingData ? 'Loading...' : 'Last 30 Days'}
                  </button>
                )}
                <button onClick={() => fetchBookings(bookingsLoadAll)} className="admin-refresh" disabled={loadingData}>
                  {loadingData ? 'Loading...' : 'Refresh'}
                </button>
              </div>
            </div>

            {/* Today's Bookings */}
            {todaysBookings.length > 0 && (
              <div className="recent-bookings-container">
                <h3 className="recent-bookings-title">Today's Bookings - {new Date().toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'long', timeZone: 'Europe/London' })}</h3>
                <div className="recent-bookings-grid">
                  {todaysBookings.map((booking) => (
                    <div
                      key={booking.id || booking.reference}
                      className={`recent-booking-card booking-status-${booking.status?.toLowerCase() || 'pending'}`}
                      onClick={() => {
                        // Navigate to Bookings tab and open this booking
                        const statusKey = (booking.status || 'pending').toLowerCase()

                        // Switch to bookings tab
                        setActiveTab('bookings')

                        // Expand the status section
                        setCollapsedStatusSections(prev => ({
                          ...prev,
                          [statusKey]: false
                        }))

                        // For confirmed/completed, expand the month container
                        if (statusKey === 'confirmed' || statusKey === 'completed') {
                          const dropoffDate = new Date(booking.dropoff_date + 'T12:00:00')
                          const monthKey = `${dropoffDate.getFullYear()}-${String(dropoffDate.getMonth() + 1).padStart(2, '0')}`
                          const expandKey = `${statusKey}-${monthKey}`
                          setExpandedBookingMonths(prev => ({
                            ...prev,
                            [expandKey]: true
                          }))
                        }

                        // Expand this specific booking
                        setExpandedBookingId(booking.id)

                        // Scroll to the booking after DOM updates
                        setTimeout(() => {
                          const element = document.querySelector(`.booking-card[data-booking-id="${booking.id}"]`)
                          if (element) {
                            element.scrollIntoView({ behavior: 'auto', block: 'start' })
                          }
                        }, 300)
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
                {/* Render each status section in order: Confirmed, Completed, Pending, Cancelled, Refunded.
                    Cancelled and Refunded are deliberately separate — Cancelled is customer-initiated
                    ("can't travel"); Refunded is TAG-initiated when we've messed up the experience. */}
                {[
                  { key: 'confirmed', label: 'Confirmed', color: '#28a745' },
                  { key: 'completed', label: 'Completed', color: '#6c757d' },
                  { key: 'pending', label: 'Pending', color: '#ffc107' },
                  { key: 'cancelled', label: 'Cancelled', color: '#dc3545' },
                  { key: 'refunded', label: 'Refunded', color: '#f97316' },
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
                            /* For pending, cancelled, and refunded, show flat list */
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
          <CalendarSection token={token} />
        )}

        {activeTab === 'payroll' && (
          <PayrollSection token={token} />
        )}

        {activeTab === 'manual-booking' && (
          <ManualBookingSection token={token} />
        )}

        {activeTab === 'users' && (
          <UsersSection
            userSuccessMessage={userSuccessMessage}
            error={error}
            userSearchTerm={userSearchTerm}
            setUserSearchTerm={setUserSearchTerm}
            filteredUsers={filteredUsers}
            loadingUsers={loadingUsers}
            openAddUserModal={openAddUserModal}
            openEditUserModal={openEditUserModal}
            handleToggleUserField={handleToggleUserField}
            setUserToDelete={setUserToDelete}
            setShowDeleteUserModal={setShowDeleteUserModal}
            showUserModal={showUserModal}
            setShowUserModal={setShowUserModal}
            editingUser={editingUser}
            userForm={userForm}
            setUserForm={setUserForm}
            handleSaveUser={handleSaveUser}
            savingUser={savingUser}
            showDeleteUserModal={showDeleteUserModal}
            userToDelete={userToDelete}
            handleDeleteUser={handleDeleteUser}
            deletingUser={deletingUser}
          />
        )}

        {activeTab === 'flights' && (
          <FlightsSection
            fetchFlights={fetchFlights}
            exportFlights={exportFlights}
            loadingFlights={loadingFlights}
            exportingFlights={exportingFlights}
            flightsMessage={flightsMessage}
            flightsSubTab={flightsSubTab}
            setFlightsSubTab={setFlightsSubTab}
            setEditingFlightId={setEditingFlightId}
            flightAirlineFilter={flightAirlineFilter}
            setFlightAirlineFilter={setFlightAirlineFilter}
            flightFilters={flightFilters}
            flightNumberFilter={flightNumberFilter}
            setFlightNumberFilter={setFlightNumberFilter}
            departures={departures}
            arrivals={arrivals}
            flightDestFilter={flightDestFilter}
            setFlightDestFilter={setFlightDestFilter}
            flightOriginFilter={flightOriginFilter}
            setFlightOriginFilter={setFlightOriginFilter}
            flightMonthFilter={flightMonthFilter}
            setFlightMonthFilter={setFlightMonthFilter}
            flightsSortAsc={flightsSortAsc}
            setFlightsSortAsc={setFlightsSortAsc}
            departuresByMonth={departuresByMonth}
            arrivalsByMonth={arrivalsByMonth}
            collapsedFlightMonths={collapsedFlightMonths}
            toggleFlightMonth={toggleFlightMonth}
            editingFlightId={editingFlightId}
            setEditFlightForm={setEditFlightForm}
            editFlightForm={editFlightForm}
            savingFlight={savingFlight}
            saveFlightEdit={saveFlightEdit}
            cancelEditFlight={cancelEditFlight}
            startEditFlight={startEditFlight}
            confirmDeleteFlight={confirmDeleteFlight}
            showAddFlightModal={showAddFlightModal}
            setShowAddFlightModal={setShowAddFlightModal}
            addFlightForm={addFlightForm}
            setAddFlightForm={setAddFlightForm}
            resetAddFlightForm={resetAddFlightForm}
            handleAddFlight={handleAddFlight}
            addingFlight={addingFlight}
            showDeleteFlightModal={showDeleteFlightModal}
            flightToDelete={flightToDelete}
            setShowDeleteFlightModal={setShowDeleteFlightModal}
            setFlightToDelete={setFlightToDelete}
            handleDeleteFlight={handleDeleteFlight}
            deletingFlightId={deletingFlightId}
          />
        )}

        <MessagesSection {...messagesSectionProps} />

        {activeTab === 'marketing' && (
          <div className="admin-section">
            <h2>
              {marketingSubTab === 'subscribers' && 'Subscribers'}
              {marketingSubTab === 'promotions' && 'Promotions'}
              {marketingSubTab === 'campaigns' && 'Email Campaigns'}
              {marketingSubTab === 'referrals' && 'Referrals'}
              {marketingSubTab === 'sources' && 'Sources'}
            </h2>

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
              <div className="admin-promotions-section">
                <div className="admin-section-header" style={{ justifyContent: 'flex-end' }}>
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
                          value={newPromotion.discount_percent === 100 ? (newPromotion.discount_type === 'free_week' ? '100_week' : '100_full') : String(newPromotion.discount_percent)}
                          onChange={(e) => {
                            const v = e.target.value
                            if (v === '100_full') {
                              setNewPromotion(prev => ({ ...prev, discount_percent: 100, discount_type: 'free_100' }))
                            } else if (v === '100_week') {
                              setNewPromotion(prev => ({ ...prev, discount_percent: 100, discount_type: 'free_week' }))
                            } else {
                              setNewPromotion(prev => ({ ...prev, discount_percent: parseInt(v), discount_type: null }))
                            }
                          }}
                          className="admin-select"
                        >
                          <option value="10">10%</option>
                          <option value="15">15%</option>
                          <option value="20">20%</option>
                          <option value="25">25%</option>
                          <option value="50">50%</option>
                          <option value="100_full">100% (Free)</option>
                          <option value="100_week">1 Week Free</option>
                        </select>
                      </div>
                      {!newPromotion.custom_code && (
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
                      )}
                    </div>
                    <div className="form-row" style={{ display: 'flex', gap: '15px', flexWrap: 'wrap', marginBottom: '15px' }}>
                      <div className="form-group" style={{ flex: '1', minWidth: '200px' }}>
                        <label>Custom Code (e.g., SUMMER10)</label>
                        <input
                          type="text"
                          value={newPromotion.custom_code}
                          onChange={(e) => setNewPromotion(prev => ({ ...prev, custom_code: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 20), total_codes: e.target.value ? 1 : prev.total_codes }))}
                          placeholder="Leave empty for auto-generated codes"
                          className="admin-input"
                          maxLength="20"
                          disabled={newPromotion.total_codes > 1 && !newPromotion.custom_code}
                        />
                        <small style={{ color: '#666', fontSize: '12px' }}>
                          {newPromotion.custom_code ? `Code will be: ${newPromotion.custom_code}` : 'Or use Code Prefix below for auto-generated codes'}
                        </small>
                      </div>
                    </div>
                    {!newPromotion.custom_code && (
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
                    )}
                    <div className="form-row" style={{ display: 'flex', gap: '15px', flexWrap: 'wrap', marginBottom: '15px', padding: '15px', background: '#f8f9fa', borderRadius: '8px', border: '1px solid #e9ecef' }}>
                      <div style={{ width: '100%', marginBottom: '5px' }}>
                        <label style={{ fontWeight: '600', color: '#495057' }}>⏰ Code Expiry (optional)</label>
                        <small style={{ display: 'block', color: '#666', fontSize: '12px' }}>Set an expiry for all generated codes - great for flash sales!</small>
                      </div>
                      <div className="form-group" style={{ flex: '1', minWidth: '140px' }}>
                        <label>Expiry Date</label>
                        <input
                          type="text"
                          value={newPromotion.expiry_date}
                          onChange={(e) => setNewPromotion(prev => ({ ...prev, expiry_date: e.target.value }))}
                          placeholder="DD/MM/YYYY"
                          className="admin-input"
                        />
                      </div>
                      <div className="form-group" style={{ flex: '1', minWidth: '140px' }}>
                        <label>Expiry Time (UK)</label>
                        <input
                          type="text"
                          value={newPromotion.expiry_time}
                          onChange={(e) => setNewPromotion(prev => ({ ...prev, expiry_time: e.target.value }))}
                          placeholder="HH:MM (24hr)"
                          className="admin-input"
                        />
                      </div>
                    </div>
                    <div className="form-row" style={{ display: 'flex', gap: '15px', flexWrap: 'wrap', marginBottom: '15px', padding: '15px', background: newPromotion.max_uses === '0' ? '#e8f5e9' : '#f8f9fa', borderRadius: '8px', border: newPromotion.max_uses === '0' ? '1px solid #c8e6c9' : '1px solid #e9ecef' }}>
                      <div style={{ width: '100%' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', fontWeight: '600', color: newPromotion.max_uses === '0' ? '#2e7d32' : '#495057' }}>
                          <input
                            type="checkbox"
                            checked={newPromotion.max_uses === '0'}
                            onChange={(e) => setNewPromotion(prev => ({ ...prev, max_uses: e.target.checked ? '0' : '' }))}
                            style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                          />
                          🔄 Unlimited Uses (multi-use code)
                        </label>
                        <small style={{ display: 'block', color: '#666', fontSize: '12px', marginTop: '5px', marginLeft: '28px' }}>
                          {newPromotion.max_uses === '0'
                            ? 'This code can be used unlimited times by multiple customers'
                            : 'Default: single-use code (one customer only)'}
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
                        onClick={() => { setShowCreatePromotion(false); setNewPromotion({ name: '', description: '', discount_percent: 10, discount_type: null, total_codes: 10, code_prefix: '', custom_code: '', expiry_date: '', expiry_time: '', max_uses: '' }); }}
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
                                {/* Bulk Actions Bar */}
                                {selectedCodes[promo.id]?.size > 0 && (
                                  <div style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '15px',
                                    padding: '10px 15px',
                                    marginBottom: '10px',
                                    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                                    borderRadius: '8px',
                                    color: 'white'
                                  }}>
                                    <span style={{ fontWeight: '600' }}>
                                      {selectedCodes[promo.id].size} code{selectedCodes[promo.id].size > 1 ? 's' : ''} selected
                                    </span>
                                    <button
                                      onClick={() => {
                                        setExpiryModalData({
                                          promotionId: promo.id,
                                          codeIds: Array.from(selectedCodes[promo.id]),
                                          isBulk: true
                                        })
                                        setExpiryDate('')
                                        setExpiryTime('')
                                        setShowExpiryModal(true)
                                      }}
                                      style={{
                                        background: 'white',
                                        color: '#667eea',
                                        border: 'none',
                                        padding: '6px 12px',
                                        borderRadius: '6px',
                                        fontWeight: '600',
                                        fontSize: '12px',
                                        cursor: 'pointer'
                                      }}
                                    >
                                      ⏰ Set Expiry
                                    </button>
                                    <button
                                      onClick={() => setSelectedCodes(prev => ({ ...prev, [promo.id]: new Set() }))}
                                      style={{
                                        background: 'rgba(255,255,255,0.2)',
                                        color: 'white',
                                        border: 'none',
                                        padding: '6px 12px',
                                        borderRadius: '6px',
                                        fontWeight: '600',
                                        fontSize: '12px',
                                        cursor: 'pointer'
                                      }}
                                    >
                                      Clear Selection
                                    </button>
                                  </div>
                                )}
                                {/* Copy Available Codes Button */}
                                <div style={{ marginBottom: '10px', display: 'flex', gap: '10px' }}>
                                  <button
                                    onClick={() => {
                                      const codes = promotionDetails[promo.id]?.codes || []
                                      const availableCodes = codes.filter(c => !c.is_used && !c.email_sent && !c.shared_on_socials && !c.shared_privately)
                                      const codeStrings = availableCodes.map(c => c.code).join('\n')
                                      navigator.clipboard.writeText(codeStrings).then(() => {
                                        setPromotionMessage(`Copied ${availableCodes.length} available codes to clipboard`)
                                      }).catch(() => {
                                        setPromotionMessage('Failed to copy to clipboard')
                                      })
                                    }}
                                    disabled={!(promotionDetails[promo.id]?.codes || []).some(c => !c.is_used && !c.email_sent && !c.shared_on_socials && !c.shared_privately)}
                                    style={{
                                      background: '#e9ecef',
                                      color: '#495057',
                                      border: 'none',
                                      padding: '6px 12px',
                                      borderRadius: '6px',
                                      fontWeight: '500',
                                      fontSize: '12px',
                                      cursor: 'pointer',
                                      display: 'flex',
                                      alignItems: 'center',
                                      gap: '6px',
                                      opacity: (promotionDetails[promo.id]?.codes || []).some(c => !c.is_used && !c.email_sent && !c.shared_on_socials && !c.shared_privately) ? 1 : 0.5
                                    }}
                                  >
                                    📋 Copy Available Codes ({(promotionDetails[promo.id]?.codes || []).filter(c => !c.is_used && !c.email_sent && !c.shared_on_socials && !c.shared_privately).length})
                                  </button>
                                </div>
                                <table className="admin-table" style={{ width: '100%', fontSize: '13px' }}>
                                  <thead>
                                    <tr>
                                      <th style={{ width: '40px', textAlign: 'center' }}>
                                        <input
                                          type="checkbox"
                                          checked={promotionDetails[promo.id]?.codes?.length > 0 &&
                                            promotionDetails[promo.id].codes.every(c => selectedCodes[promo.id]?.has(c.id))}
                                          onChange={(e) => {
                                            const codes = promotionDetails[promo.id]?.codes || []
                                            if (e.target.checked) {
                                              setSelectedCodes(prev => ({
                                                ...prev,
                                                [promo.id]: new Set(codes.map(c => c.id))
                                              }))
                                            } else {
                                              setSelectedCodes(prev => ({
                                                ...prev,
                                                [promo.id]: new Set()
                                              }))
                                            }
                                          }}
                                          title="Select all codes"
                                          style={{ cursor: 'pointer' }}
                                        />
                                      </th>
                                      <th>Code</th>
                                      <th>Recipient</th>
                                      <th>Shared on Socials</th>
                                      <th>Shared Privately</th>
                                      <th>Expiry</th>
                                      <th>Status</th>
                                      <th>Booking</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {promotionDetails[promo.id].codes.map(code => (
                                      <tr key={code.id} style={{ background: selectedCodes[promo.id]?.has(code.id) ? '#f0f7ff' : 'transparent' }}>
                                        <td style={{ textAlign: 'center' }}>
                                          <input
                                            type="checkbox"
                                            checked={selectedCodes[promo.id]?.has(code.id) || false}
                                            onChange={(e) => {
                                              setSelectedCodes(prev => {
                                                const currentSet = prev[promo.id] ? new Set(prev[promo.id]) : new Set()
                                                if (e.target.checked) {
                                                  currentSet.add(code.id)
                                                } else {
                                                  currentSet.delete(code.id)
                                                }
                                                return { ...prev, [promo.id]: currentSet }
                                              })
                                            }}
                                            style={{ cursor: 'pointer' }}
                                          />
                                        </td>
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
                                          {/* Expiry: clickable to set/edit, shows status */}
                                          <button
                                            onClick={() => openExpiryModal(promo.id, code)}
                                            style={{
                                              display: 'inline-flex',
                                              alignItems: 'center',
                                              gap: '6px',
                                              padding: '4px 10px',
                                              borderRadius: '12px',
                                              fontSize: '11px',
                                              fontWeight: '600',
                                              border: 'none',
                                              cursor: 'pointer',
                                              background: code.is_expired
                                                ? 'linear-gradient(135deg, #dc3545 0%, #c82333 100%)'
                                                : code.expires_at
                                                  ? 'linear-gradient(135deg, #ffc107 0%, #e0a800 100%)'
                                                  : '#e9ecef',
                                              color: code.is_expired || code.expires_at ? 'white' : '#666',
                                              transition: 'all 0.2s ease'
                                            }}
                                            title={code.expires_at
                                              ? `Expires: ${new Date(code.expires_at).toLocaleString('en-GB', { timeZone: 'Europe/London', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}`
                                              : 'Click to set expiry'
                                            }
                                          >
                                            {code.is_expired ? (
                                              <>⏰ Expired</>
                                            ) : code.expires_at ? (
                                              <>⏰ {new Date(code.expires_at).toLocaleDateString('en-GB', { timeZone: 'Europe/London', day: '2-digit', month: '2-digit' })} {new Date(code.expires_at).toLocaleTimeString('en-GB', { timeZone: 'Europe/London', hour: '2-digit', minute: '2-digit' })}</>
                                            ) : (
                                              <>Set Expiry</>
                                            )}
                                          </button>
                                        </td>
                                        <td>
                                          <span className={`status-badge ${code.is_used ? 'used' : code.is_expired ? 'expired' : (code.email_sent || code.shared_on_socials || code.shared_privately) ? 'sent' : 'pending'}`}>
                                            {code.is_multi_use ? (
                                              // Multi-use code - show usage count
                                              code.max_uses === 0 ? (
                                                // Unlimited uses
                                                <span>∞ {code.use_count} {code.use_count === 1 ? 'use' : 'uses'}</span>
                                              ) : (
                                                // Limited uses
                                                <span>{code.use_count}/{code.max_uses} uses</span>
                                              )
                                            ) : (
                                              // Single-use code
                                              code.is_used ? 'Used' : code.is_expired ? 'Expired' : (code.email_sent || code.shared_on_socials || code.shared_privately) ? 'Shared' : 'Available'
                                            )}
                                          </span>
                                        </td>
                                        <td>
                                          {code.booking_references && code.booking_references.length > 0 ? (
                                            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                                              {code.booking_references.map((ref, idx) => (
                                                <code key={idx} style={{ background: '#f0f0f0', padding: '2px 6px', borderRadius: '3px', fontSize: '0.85em' }}>{ref}</code>
                                              ))}
                                            </div>
                                          ) : code.booking_reference ? (
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

            {/* Email Campaigns Sub-tab */}
            {marketingSubTab === 'campaigns' && (
              <div className="email-campaigns-section">
                <div className="admin-section-header" style={{ justifyContent: 'flex-end' }}>
                  <div className="flights-header-actions">
                    <button
                      className="btn-secondary"
                      onClick={fetchCampaigns}
                      disabled={loadingCampaigns}
                    >
                      {loadingCampaigns ? 'Loading...' : '↻ Refresh'}
                    </button>
                    <button
                      className="btn-primary"
                      onClick={() => setShowCreateCampaign(true)}
                    >
                      + New Campaign
                    </button>
                  </div>
                </div>

                {/* Campaign List */}
                {loadingCampaigns ? (
                  <div className="loading-spinner">Loading campaigns...</div>
                ) : campaigns.length === 0 ? (
                  <div className="no-data-message">
                    <p>No email campaigns yet. Create your first campaign to send marketing emails to subscribers.</p>
                  </div>
                ) : (
                  <table className="admin-table">
                    <thead>
                      <tr>
                        <th>Subject</th>
                        <th>Status</th>
                        <th>Recipients</th>
                        <th>Sent</th>
                        <th>Failed</th>
                        <th>Created</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {campaigns.map(campaign => (
                        <tr key={campaign.id}>
                          <td>
                            <strong>{campaign.subject}</strong>
                            {campaign.promo_code && (
                              <span className="promo-badge" style={{ marginLeft: '8px', background: '#CCFF00', color: '#1A1A1A', padding: '2px 6px', borderRadius: '4px', fontSize: '12px' }}>
                                {campaign.promo_code}
                              </span>
                            )}
                          </td>
                          <td>
                            <span className={`status-badge status-${campaign.status}`}>
                              {campaign.status}
                            </span>
                          </td>
                          <td>{campaign.total_recipients}</td>
                          <td>{campaign.sent_count}</td>
                          <td>{campaign.failed_count}</td>
                          <td>{campaign.created_at ? new Date(campaign.created_at).toLocaleDateString('en-GB') : '-'}</td>
                          <td>
                            {campaign.status === 'draft' && (
                              <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                                <button
                                  onClick={() => openCampaignForEdit(campaign.id)}
                                  style={{ padding: '6px 14px', fontSize: '0.8rem', fontWeight: '600', borderRadius: '20px', background: '#f0f0f0', color: '#333', border: 'none', cursor: 'pointer' }}
                                >
                                  Edit
                                </button>
                                <button
                                  onClick={() => deleteCampaign(campaign.id)}
                                  disabled={deletingCampaignId === campaign.id}
                                  style={{ padding: '6px 14px', fontSize: '0.8rem', fontWeight: '600', borderRadius: '20px', background: '#f0f0f0', color: '#c53030', border: 'none', cursor: 'pointer', opacity: deletingCampaignId === campaign.id ? 0.6 : 1 }}
                                >
                                  {deletingCampaignId === campaign.id ? 'Deleting...' : 'Delete'}
                                </button>
                                <button
                                  onClick={() => sendCampaign(campaign.id)}
                                  disabled={sendingCampaign}
                                  style={{ padding: '6px 14px', fontSize: '0.8rem', fontWeight: '600', borderRadius: '20px', background: '#f7b32b', color: '#1a1a2e', border: 'none', cursor: 'pointer', opacity: sendingCampaign ? 0.6 : 1 }}
                                >
                                  {sendingCampaign ? 'Sending...' : 'Send'}
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}

                {/* Create Campaign Modal */}
                {showCreateCampaign && (
                  <div className="modal-overlay" onClick={closeCampaignModal}>
                    <div className="modal-content" style={{ maxWidth: '1200px', width: '95%' }} onClick={(e) => e.stopPropagation()}>
                      <div className="modal-header">
                        <h3>{editingCampaignId ? 'Edit Email Campaign' : 'Create Email Campaign'}</h3>
                        <button className="modal-close" onClick={closeCampaignModal}>×</button>
                      </div>
                      <div className="modal-body">
                        {/* Campaign Details Section */}
                        <div style={{ background: '#f9f9f9', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
                          <h4 style={{ margin: '0 0 4px 0', fontSize: '16px', fontWeight: '600' }}>Campaign Details</h4>
                          <div style={{ height: '3px', background: '#D4AF37', width: '120px', marginBottom: '20px' }}></div>

                          <div className="form-group">
                            <label>Subject Line *</label>
                            <input
                              type="text"
                              value={newCampaign.subject}
                              onChange={(e) => setNewCampaign({ ...newCampaign, subject: e.target.value })}
                              placeholder="e.g., Your exclusive 15% off code inside"
                              style={{ width: '100%' }}
                            />
                            <small style={{ color: '#666' }}>
                              Short and specific works best — this is what subscribers see in their inbox.
                            </small>
                          </div>

                          <div className="form-group">
                            <label>Message *</label>
                            <textarea
                              rows={8}
                              value={newCampaign.message}
                              onChange={(e) => setNewCampaign({ ...newCampaign, message: e.target.value })}
                              placeholder={`Write the body of the email — no need for a greeting or sign-off.\n\nThe template automatically adds:\n  • "Hi [first name]," at the top\n  • "Best, [founder name]" at the bottom\n\nExample:\nWe're running a spring offer this month — 15% off any booking over 5 days. Use the code below at checkout. It's our way of saying thanks for booking with us.`}
                              style={{ width: '100%' }}
                            />
                            <small style={{ color: '#666' }}>
                              Tip: keep it short, warm, and conversational. Preview before sending.
                            </small>
                          </div>

                          <div className="form-group">
                            <label>Promo Code (optional)</label>
                            <select
                              value={newCampaign.promo_code_id || ''}
                              onChange={(e) => setNewCampaign({ ...newCampaign, promo_code_id: e.target.value ? parseInt(e.target.value) : null })}
                              style={{ width: '100%' }}
                            >
                              <option value="">No promo code</option>
                              {availablePromoCodes.map(code => (
                                <option key={code.id} value={code.id}>
                                  {code.code} ({code.discount_percent}% off, {code.use_count}/{code.max_uses === 0 ? '∞' : code.max_uses} used)
                                </option>
                              ))}
                            </select>
                          </div>
                        </div>

                        {/* Recipients Section */}
                        <div style={{ background: '#f9f9f9', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
                          <h4 style={{ margin: '0 0 4px 0', fontSize: '16px', fontWeight: '600' }}>Recipients</h4>
                          <div style={{ height: '3px', background: '#D4AF37', width: '80px', marginBottom: '20px' }}></div>

                          <div style={{ display: 'flex', gap: '10px', marginBottom: '15px', flexWrap: 'wrap', alignItems: 'center' }}>
                            <input
                              type="text"
                              placeholder="Search subscribers..."
                              value={newCampaign.searchFilter || ''}
                              onChange={(e) => setNewCampaign({ ...newCampaign, searchFilter: e.target.value })}
                              style={{ flex: '1', minWidth: '200px', padding: '8px 14px', borderRadius: '20px', border: '1px solid #ddd' }}
                            />
                            <button
                              type="button"
                              onClick={() => {
                                const allIds = subscribers.filter(s => !s.unsubscribed).map(s => s.id)
                                setNewCampaign({ ...newCampaign, subscriber_ids: allIds })
                              }}
                              style={{ padding: '8px 16px', fontSize: '0.8rem', fontWeight: '600', borderRadius: '20px', background: '#f0f0f0', color: '#333', border: 'none', cursor: 'pointer', flexShrink: 0 }}
                            >
                              Select All ({subscribers.filter(s => !s.unsubscribed).length})
                            </button>
                            <button
                              type="button"
                              onClick={() => setNewCampaign({ ...newCampaign, subscriber_ids: [] })}
                              style={{ padding: '8px 16px', fontSize: '0.8rem', fontWeight: '600', borderRadius: '20px', background: '#f0f0f0', color: '#333', border: 'none', cursor: 'pointer', flexShrink: 0 }}
                            >
                              Clear
                            </button>
                          </div>

                          <div style={{ maxHeight: '250px', overflow: 'auto', border: '1px solid #ddd', borderRadius: '8px', background: 'white' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                              <thead>
                                <tr style={{ background: '#f5f5f5', position: 'sticky', top: 0 }}>
                                  <th style={{ padding: '10px 15px', textAlign: 'left', width: '40px' }}></th>
                                  <th style={{ padding: '10px 15px', textAlign: 'left' }}>Name</th>
                                  <th style={{ padding: '10px 15px', textAlign: 'left' }}>Email</th>
                                </tr>
                              </thead>
                              <tbody>
                                {subscribers
                                  .filter(s => !s.unsubscribed)
                                  .filter(s => {
                                    const search = (newCampaign.searchFilter || '').toLowerCase()
                                    if (!search) return true
                                    return (
                                      (s.first_name || '').toLowerCase().includes(search) ||
                                      (s.last_name || '').toLowerCase().includes(search) ||
                                      (s.email || '').toLowerCase().includes(search)
                                    )
                                  })
                                  .map(subscriber => (
                                    <tr
                                      key={subscriber.id}
                                      style={{
                                        borderBottom: '1px solid #eee',
                                        cursor: 'pointer',
                                        background: newCampaign.subscriber_ids.includes(subscriber.id) ? '#fff9e6' : 'transparent'
                                      }}
                                      onClick={() => {
                                        if (newCampaign.subscriber_ids.includes(subscriber.id)) {
                                          setNewCampaign({ ...newCampaign, subscriber_ids: newCampaign.subscriber_ids.filter(id => id !== subscriber.id) })
                                        } else {
                                          setNewCampaign({ ...newCampaign, subscriber_ids: [...newCampaign.subscriber_ids, subscriber.id] })
                                        }
                                      }}
                                    >
                                      <td style={{ padding: '10px 15px' }}>
                                        <input
                                          type="checkbox"
                                          checked={newCampaign.subscriber_ids.includes(subscriber.id)}
                                          onChange={() => {}}
                                          style={{ cursor: 'pointer' }}
                                        />
                                      </td>
                                      <td style={{ padding: '10px 15px', fontWeight: '500' }}>
                                        {subscriber.first_name} {subscriber.last_name}
                                      </td>
                                      <td style={{ padding: '10px 15px', color: '#666' }}>
                                        {subscriber.email}
                                      </td>
                                    </tr>
                                  ))}
                              </tbody>
                            </table>
                          </div>
                          <div style={{ marginTop: '10px', color: '#666', fontSize: '14px' }}>
                            <strong>{newCampaign.subscriber_ids.length}</strong> recipient(s) selected
                          </div>
                        </div>

                        {/* Preview Section */}
                        {campaignPreview && (
                          <div style={{ background: '#f0f7ff', padding: '20px', borderRadius: '8px', marginBottom: '10px' }}>
                            <h4 style={{ margin: '0 0 4px 0', fontSize: '16px', fontWeight: '600' }}>Preview</h4>
                            <div style={{ height: '3px', background: '#4a90d9', width: '60px', marginBottom: '15px' }}></div>
                            <p><strong>Subject:</strong> {campaignPreview.subject}</p>
                            <div style={{ whiteSpace: 'pre-wrap', background: 'white', padding: '15px', borderRadius: '6px', border: '1px solid #ddd' }}>
                              {campaignPreview.message}
                            </div>
                            {campaignPreview.promo_code && (
                              <p style={{ marginTop: '10px' }}><strong>Promo Code:</strong> <span style={{ background: '#D4AF37', color: 'white', padding: '2px 8px', borderRadius: '4px' }}>{campaignPreview.promo_code}</span></p>
                            )}
                          </div>
                        )}
                      </div>

                      <div className="modal-actions" style={{ borderTop: '1px solid #eee', paddingTop: '20px', marginTop: '10px', flexWrap: 'wrap' }}>
                        <button
                          className="modal-btn modal-btn-secondary"
                          onClick={closeCampaignModal}
                          style={{ borderRadius: '20px' }}
                        >
                          Cancel
                        </button>
                        <button
                          className="modal-btn modal-btn-secondary"
                          onClick={previewCampaign}
                          disabled={!newCampaign.subject || !newCampaign.message}
                          style={{ borderRadius: '20px' }}
                        >
                          Preview
                        </button>
                        <button
                          className="modal-btn modal-btn-primary"
                          onClick={createCampaign}
                          disabled={creatingCampaign || !newCampaign.subject || !newCampaign.message || newCampaign.subscriber_ids.length === 0}
                          style={{ borderRadius: '20px' }}
                        >
                          {creatingCampaign
                            ? (editingCampaignId ? 'Saving...' : 'Creating...')
                            : (editingCampaignId ? 'Save Changes' : 'Create Campaign')}
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* Campaign Toast */}
                {campaignToast && (
                  <div
                    style={{
                      position: 'fixed',
                      bottom: '24px',
                      right: '24px',
                      zIndex: 10000,
                      background: campaignToast.type === 'success' ? '#276749' : '#c53030',
                      color: 'white',
                      padding: '14px 20px',
                      borderRadius: '12px',
                      boxShadow: '0 8px 24px rgba(0,0,0,0.2)',
                      fontSize: '14px',
                      fontWeight: '500',
                      maxWidth: '360px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '12px',
                    }}
                  >
                    <span>{campaignToast.type === 'success' ? '✓' : '!'}</span>
                    <span>{campaignToast.message}</span>
                    <button
                      onClick={() => setCampaignToast(null)}
                      style={{ background: 'transparent', border: 'none', color: 'white', cursor: 'pointer', fontSize: '18px', lineHeight: 1, padding: 0, marginLeft: 'auto' }}
                      aria-label="Dismiss"
                    >
                      ×
                    </button>
                  </div>
                )}

                {/* Campaign Confirm Modal (Delete / Send) */}
                {campaignConfirm && (
                  <div className="modal-overlay" onClick={() => setCampaignConfirm(null)}>
                    <div className="modal-content" style={{ maxWidth: '440px', width: '90%' }} onClick={(e) => e.stopPropagation()}>
                      <div className="modal-header">
                        <h3>
                          {campaignConfirm.action === 'delete' ? 'Delete draft campaign?' : 'Send campaign?'}
                        </h3>
                        <button className="modal-close" onClick={() => setCampaignConfirm(null)}>×</button>
                      </div>
                      <div className="modal-body">
                        <p style={{ margin: 0, color: '#444' }}>
                          {campaignConfirm.action === 'delete'
                            ? 'This will permanently remove the draft and its selected recipients. This cannot be undone.'
                            : 'This will email every selected recipient immediately. This cannot be undone.'}
                        </p>
                      </div>
                      <div className="modal-actions" style={{ borderTop: '1px solid #eee', paddingTop: '16px', marginTop: '10px' }}>
                        <button
                          className="modal-btn modal-btn-secondary"
                          onClick={() => setCampaignConfirm(null)}
                          style={{ borderRadius: '20px' }}
                        >
                          Cancel
                        </button>
                        <button
                          className={campaignConfirm.action === 'delete' ? 'modal-btn modal-btn-danger' : 'modal-btn modal-btn-primary'}
                          onClick={() => {
                            const { action, id } = campaignConfirm
                            setCampaignConfirm(null)
                            if (action === 'delete') {
                              performDeleteCampaign(id)
                            } else {
                              performSendCampaign(id)
                            }
                          }}
                          style={{ borderRadius: '20px', color: campaignConfirm.action === 'delete' ? 'white' : undefined }}
                        >
                          {campaignConfirm.action === 'delete' ? 'Delete' : 'Send Campaign'}
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {marketingSubTab === 'referrals' && (
              <div className="referrals-dashboard">
                <div className="admin-section-header">
                  <h2>Referral Program</h2>
                  <button
                    className="referrals-refresh-button"
                    onClick={fetchReferralsDashboard}
                    disabled={loadingReferrals}
                    type="button"
                    aria-label="Refresh referrals dashboard"
                  >
                    <span className={loadingReferrals ? 'referrals-refresh-icon spinning' : 'referrals-refresh-icon'} aria-hidden="true">↻</span>
                    <span>{loadingReferrals ? 'Refreshing' : 'Refresh'}</span>
                  </button>
                </div>

                <form className="manual-referral-invite-panel" onSubmit={handleManualReferralInvite}>
                  <div className="manual-referral-invite-heading">
                    <h3>Social referral invite</h3>
                  </div>
                  <div className="manual-referral-invite-fields">
                    <label className="referrals-control">
                      <span>First name</span>
                      <input
                        type="text"
                        value={manualReferralInvite.first_name}
                        onChange={(e) => setManualReferralInvite(prev => ({ ...prev, first_name: e.target.value }))}
                        required
                      />
                    </label>
                    <label className="referrals-control">
                      <span>Last name</span>
                      <input
                        type="text"
                        value={manualReferralInvite.last_name}
                        onChange={(e) => setManualReferralInvite(prev => ({ ...prev, last_name: e.target.value }))}
                        required
                      />
                    </label>
                    <label className="referrals-control referrals-control-wide">
                      <span>Email</span>
                      <input
                        type="email"
                        value={manualReferralInvite.email}
                        onChange={(e) => setManualReferralInvite(prev => ({ ...prev, email: e.target.value }))}
                        required
                      />
                    </label>
                    <button
                      type="submit"
                      className="referrals-send-button"
                      disabled={
                        sendingManualReferralInvite ||
                        !manualReferralInvite.first_name.trim() ||
                        !manualReferralInvite.last_name.trim() ||
                        !manualReferralInvite.email.trim()
                      }
                    >
                      {sendingManualReferralInvite ? 'Sending...' : 'Send Invite'}
                    </button>
                  </div>
                  {manualReferralInviteMessage && (
                    <div className="manual-referral-invite-message">{manualReferralInviteMessage}</div>
                  )}
                </form>

                {loadingReferrals && !referralsDashboardHasLoaded ? (
                  <div className="loading-state">Loading referrals...</div>
                ) : (
                  <div className="referrals-dashboard-content" aria-busy={loadingReferrals ? 'true' : 'false'}>
                    <div className="referral-stats-grid">
                      {[
                        ['Invites sent', referralsDashboard.stats.invites_sent, 'blue'],
                        ['Awaiting response', referralsDashboard.stats.awaiting_response, 'amber'],
                        ['Opted in', referralsDashboard.stats.opted_in, 'green'],
                        ['Opted out', referralsDashboard.stats.opted_out, 'rose'],
                        ['Response opt-in rate', `${referralsDashboard.stats.opt_in_rate || 0}%`, 'teal'],
                        ['Codes generated', referralsDashboard.stats.referral_codes_generated, 'indigo'],
                        ['Code bookings', referralsDashboard.stats.referral_code_bookings_created, 'violet'],
                        ['Qualified referrals', referralsDashboard.stats.completed_qualified_referrals, 'emerald'],
                        ['Self-use / disqualified', referralsDashboard.stats.self_use_disqualified_referrals, 'orange'],
                        ['Rewards earned', referralsDashboard.stats.rewards_earned, 'cyan'],
                        ['Rewards sent', referralsDashboard.stats.rewards_sent, 'slate'],
                      ].map(([label, value, tone]) => (
                        <div className={`stats-card referral-stat-card referral-stat-card-${tone}`} key={label}>
                          <div className="stats-card-value">{value ?? 0}</div>
                          <div className="stats-card-label">{label}</div>
                        </div>
                      ))}
                    </div>

                    <div className="referrals-panel">
                      <div className="referrals-panel-header">
                        <h3>Referral Customers</h3>
                        <div className="referrals-control-group">
                          <label className="referrals-control">
                            <span>Filter</span>
                            <select
                              value={referralsFilter}
                              onChange={(e) => {
                                setReferralsFilter(e.target.value)
                                setReferralsCustomerOffset(0)
                              }}
                            >
                              <option value="all">All</option>
                              <option value="awaiting_response">Awaiting response</option>
                              <option value="opted_in">Opted in</option>
                              <option value="opted_out">Opted out</option>
                              <option value="has_code_usage">Has code usage</option>
                              <option value="has_qualified">Has qualified referrals</option>
                              <option value="reward_earned">Reward earned</option>
                              <option value="self_use_only">Self-use only</option>
                              <option value="disqualified_usage">Disqualified usage</option>
                            </select>
                          </label>
                          <label className="referrals-control referrals-control-wide">
                            <span>Search</span>
                            <input
                              type="text"
                              className="referrals-search"
                              placeholder="Customer, email, code"
                              value={referralsCustomerSearch}
                              onChange={(e) => setReferralsCustomerSearch(e.target.value)}
                            />
                          </label>
                        </div>
                      </div>
                      <div className="admin-table-container">
                        <table className="admin-table referrals-table">
                          <thead>
                            <tr>
                              <th>Customer</th>
                              <th>Email</th>
                              <th>Status</th>
                              <th>Source</th>
                              <th>Code</th>
                              <th>Uses</th>
                              <th>Qualified</th>
                              <th>Reward</th>
                              <th>Invite Sent</th>
                              <th>Code Email Sent</th>
                              <th>Reminder Sent</th>
                              <th>Responded</th>
                              <th>Reward Earned</th>
                              <th>Reward Email Sent</th>
                              <th>Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {filteredReferralCustomers.map(row => (
                              <tr key={row.program_id}>
                                <td>{row.customer_name || '-'}</td>
                                <td>{row.email || '-'}</td>
                                <td><span className={`status-badge ${row.status}`}>{row.status_label}</span></td>
                                <td><span className={`referral-source-pill ${row.invite_source || 'booking'}`}>{row.invite_source_label || 'Booking'}</span></td>
                                <td><span className="promo-code-display">{row.code || '-'}</span></td>
                                <td>{row.uses || 0}</td>
                                <td>{row.qualified || 0}</td>
                                <td>{row.reward_code || (row.reward_earned ? 'Earned' : '-')}</td>
                                <td>{formatDateTimeUK(row.invite_sent_at)}</td>
                                <td>{formatDateTimeUK(row.code_email_sent_at)}</td>
                                <td>{formatDateTimeUK(row.reminder_sent_at)}</td>
                                <td>{formatDateTimeUK(row.responded_at)}</td>
                                <td>{formatDateTimeUK(row.reward_earned_at)}</td>
                                <td>{formatDateTimeUK(row.reward_email_sent_at)}</td>
                                <td>
                                  <div className="referral-action-row">
                                    <button
                                      className="referral-action-button referral-action-button-neutral"
                                      onClick={() => openCustomerModal({ id: row.customer_id })}
                                    >
                                      View Customer
                                    </button>
                                    {row.code && (
                                      <button
                                        className="referral-action-button referral-action-button-neutral"
                                        onClick={() => {
                                          setReferralsUsageFilter('all')
                                          setReferralsUsageSearch(row.code)
                                          setReferralsUsageOffset(0)
                                          setTimeout(() => {
                                            referralUsageTableRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                                          }, 0)
                                        }}
                                      >
                                        View Bookings
                                      </button>
                                    )}
                                    <button
                                      className="referral-action-button referral-action-button-success"
                                      onClick={() => handleReferralDashboardAction(row, 'resend-code')}
                                      disabled={!!referralDashboardAction || !row.code || !row.code_active}
                                    >
                                      {referralDashboardAction === `${row.customer_id}:resend-code` ? 'Resending...' : 'Resend Code'}
                                    </button>
                                    <button
                                      className="referral-action-button referral-action-button-success"
                                      onClick={() => handleReferralDashboardAction(row, 'generate-new-code')}
                                      disabled={!!referralDashboardAction}
                                    >
                                      {referralDashboardAction === `${row.customer_id}:generate-new-code` ? 'Generating...' : 'Generate Code'}
                                    </button>
                                    <button
                                      className="referral-action-button referral-action-button-danger"
                                      onClick={() => handleReferralDashboardAction(row, 'cancel-code')}
                                      disabled={!!referralDashboardAction || !row.code || !row.code_active}
                                    >
                                      {referralDashboardAction === `${row.customer_id}:cancel-code` ? 'Cancelling...' : 'Cancel Code'}
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                            {filteredReferralCustomers.length === 0 && (
                              <tr><td colSpan="15" className="no-data">No referral customers match this filter.</td></tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                      <div className="referrals-pagination">
                        <span>
                          Showing {referralCustomerStart}-{referralCustomerEnd} of {referralCustomerTotal} customers
                        </span>
                        <div className="referrals-pagination-controls">
                          <label className="referrals-page-size">
                            <span>Rows</span>
                            <select
                              value={referralsCustomerPageSize}
                              onChange={(e) => {
                                setReferralsCustomerPageSize(Number(e.target.value))
                                setReferralsCustomerOffset(0)
                              }}
                            >
                              {REFERRALS_PAGE_SIZE_OPTIONS.map(size => (
                                <option key={size} value={size}>{size}</option>
                              ))}
                            </select>
                          </label>
                          <button
                            className="referrals-page-button"
                            disabled={loadingReferrals || referralsCustomerOffset === 0}
                            onClick={() => setReferralsCustomerOffset(Math.max(0, referralsCustomerOffset - referralsCustomerPageSize))}
                          >
                            Previous
                          </button>
                          <button
                            className="referrals-page-button"
                            disabled={loadingReferrals || referralCustomerEnd >= referralCustomerTotal}
                            onClick={() => setReferralsCustomerOffset(referralsCustomerOffset + referralsCustomerPageSize)}
                          >
                            Next
                          </button>
                        </div>
                      </div>
                    </div>

                    <div className="referrals-panel" ref={referralUsageTableRef}>
                      <div className="referrals-panel-header">
                        <h3>Code Usage / Bookings</h3>
                        <div className="referrals-control-group">
                          <label className="referrals-control referrals-control-wide">
                            <span>Search</span>
                            <input
                              type="text"
                              className="referrals-usage-search"
                              placeholder="Code, booking, referrer"
                              value={referralsUsageSearch}
                              onChange={(e) => setReferralsUsageSearch(e.target.value)}
                            />
                          </label>
                          <label className="referrals-control">
                            <span>Filter</span>
                            <select
                              value={referralsUsageFilter}
                              onChange={(e) => {
                                setReferralsUsageFilter(e.target.value)
                                setReferralsUsageOffset(0)
                              }}
                            >
                              <option value="all">All</option>
                              <option value="open_bookings">Pending / confirmed bookings</option>
                              <option value="completed">Completed bookings</option>
                              <option value="pending">Pending attribution</option>
                              <option value="qualified">Qualified</option>
                              <option value="disqualified">Disqualified</option>
                              <option value="self_use">Self-use</option>
                            </select>
                          </label>
                        </div>
                      </div>
                      <div className="admin-table-container">
                        <table className="admin-table referrals-table">
                          <thead>
                            <tr>
                              <th>Referrer</th>
                              <th>Code</th>
                              <th>Used By</th>
                              <th>Booking</th>
                              <th>Booking Status</th>
                              <th>Discount</th>
                              <th>Self-use</th>
                              <th>Attribution</th>
                              <th>Completed At</th>
                            </tr>
                          </thead>
                          <tbody>
                            {filteredReferralUsage.map(row => (
                              <tr key={row.usage_id}>
                                <td>{row.referrer || '-'}</td>
                                <td><span className="promo-code-display">{row.code || '-'}</span></td>
                                <td>{row.used_by || '-'}</td>
                                <td>
                                  {row.booking_reference ? (
                                    <button
                                      type="button"
                                      className="link-button"
                                      onClick={() => {
                                        setActiveTab('bookings')
                                        setSearchTerm(row.booking_reference)
                                      }}
                                    >
                                      {row.booking_reference}
                                    </button>
                                  ) : '-'}
                                </td>
                                <td><span className={`status-badge ${row.booking_status || 'pending'}`}>{row.booking_status || '-'}</span></td>
                                <td>{row.discount_percent}% {row.discount_amount_pence ? `(${formatPence(row.discount_amount_pence)})` : ''}</td>
                                <td>{row.self_use ? 'Yes' : 'No'}</td>
                                <td><span className={`status-badge ${row.attribution_status}`}>{row.attribution_status}</span></td>
                                <td>{formatDateTimeUK(row.completed_at)}</td>
                              </tr>
                            ))}
                            {filteredReferralUsage.length === 0 && (
                              <tr><td colSpan="9" className="no-data">No referral code usage matches this filter.</td></tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                      <div className="referrals-pagination">
                        <span>
                          Showing {referralUsageStart}-{referralUsageEnd} of {referralUsageTotal} code usages
                        </span>
                        <div className="referrals-pagination-controls">
                          <label className="referrals-page-size">
                            <span>Rows</span>
                            <select
                              value={referralsUsagePageSize}
                              onChange={(e) => {
                                setReferralsUsagePageSize(Number(e.target.value))
                                setReferralsUsageOffset(0)
                              }}
                            >
                              {REFERRALS_PAGE_SIZE_OPTIONS.map(size => (
                                <option key={size} value={size}>{size}</option>
                              ))}
                            </select>
                          </label>
                          <button
                            className="referrals-page-button"
                            disabled={loadingReferrals || referralsUsageOffset === 0}
                            onClick={() => setReferralsUsageOffset(Math.max(0, referralsUsageOffset - referralsUsagePageSize))}
                          >
                            Previous
                          </button>
                          <button
                            className="referrals-page-button"
                            disabled={loadingReferrals || referralUsageEnd >= referralUsageTotal}
                            onClick={() => setReferralsUsageOffset(referralsUsageOffset + referralsUsagePageSize)}
                          >
                            Next
                          </button>
                        </div>
                      </div>
                    </div>
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
                                { key: 'google', label: 'Google', icon: 'bi bi-google' },
                                { key: 'facebook', label: 'Facebook', icon: 'bi bi-facebook' },
                                { key: 'instagram', label: 'Instagram', icon: 'bi bi-instagram' },
                                { key: 'word_of_mouth', label: 'Word of Mouth', icon: null },
                                { key: 'leaflet', label: 'Leaflet', icon: 'bi bi-file-text' },
                                { key: 'tv', label: 'TV', icon: 'bi bi-tv' },
                                { key: 'radio', label: 'Radio', icon: 'bi bi-broadcast' },
                                { key: 'newspaper', label: 'Newspaper', icon: 'bi bi-newspaper' },
                                { key: 'linkedin', label: 'LinkedIn', icon: 'bi bi-linkedin' },
                                { key: 'afc_bournemouth', label: 'AFCB', icon: null },
                                { key: 'expectations_travel', label: 'Expect.', icon: null },
                                { key: 'other', label: 'Other', icon: null }
                              ].map(source => (
                                <th key={source.key} title={source.label}>
                                  {source.icon ? <i className={source.icon}></i> : source.label}
                                </th>
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
                                  {['google', 'facebook', 'instagram', 'word_of_mouth', 'leaflet', 'tv', 'radio', 'newspaper', 'linkedin', 'afc_bournemouth', 'expectations_travel', 'other'].map(source => (
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
                            expectations_travel: 'Expectations Travel',
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
                            expectations_travel: 'Expectations Travel',
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
                    <div className="form-group" style={{ marginBottom: '15px' }}>
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
                    <div style={{ padding: '15px', background: '#f8f9fa', borderRadius: '8px', border: '1px solid #e9ecef', marginBottom: '15px' }}>
                      <label style={{ fontWeight: '600', color: '#495057', marginBottom: '10px', display: 'block' }}>⏰ Code Expiry (optional)</label>
                      <div style={{ display: 'flex', gap: '10px' }}>
                        <div className="form-group" style={{ flex: 1 }}>
                          <label style={{ fontSize: '12px' }}>Date (DD/MM/YYYY)</label>
                          <input
                            type="text"
                            value={generateCodesExpiryDate}
                            onChange={(e) => setGenerateCodesExpiryDate(e.target.value)}
                            placeholder="28/03/2026"
                            className="admin-input"
                            style={{ width: '100%' }}
                          />
                        </div>
                        <div className="form-group" style={{ flex: 1 }}>
                          <label style={{ fontSize: '12px' }}>Time (HH:MM UK)</label>
                          <input
                            type="text"
                            value={generateCodesExpiryTime}
                            onChange={(e) => setGenerateCodesExpiryTime(e.target.value)}
                            placeholder="14:30"
                            className="admin-input"
                            style={{ width: '100%' }}
                          />
                        </div>
                      </div>
                    </div>
                    <div style={{ padding: '15px', background: generateCodesMaxUses === '0' ? '#e8f5e9' : '#f8f9fa', borderRadius: '8px', border: generateCodesMaxUses === '0' ? '1px solid #c8e6c9' : '1px solid #e9ecef' }}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', fontWeight: '600', color: generateCodesMaxUses === '0' ? '#2e7d32' : '#495057' }}>
                        <input
                          type="checkbox"
                          checked={generateCodesMaxUses === '0'}
                          onChange={(e) => setGenerateCodesMaxUses(e.target.checked ? '0' : '')}
                          style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                        />
                        🔄 Unlimited Uses (multi-use code)
                      </label>
                      <small style={{ color: '#666', fontSize: '11px', marginTop: '5px', display: 'block', marginLeft: '28px' }}>
                        {generateCodesMaxUses === '0'
                          ? 'This code can be used unlimited times'
                          : 'Default: single-use code'}
                      </small>
                    </div>
                  </div>
                  <div className="modal-actions">
                    <button
                      className="modal-btn modal-btn-secondary"
                      onClick={() => { setShowGenerateCodesModal(false); setGenerateCodesExpiryDate(''); setGenerateCodesExpiryTime(''); }}
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

            {/* Set Expiry Modal */}
            {showExpiryModal && expiryModalData && (
              <div className="modal-overlay" onClick={() => setShowExpiryModal(false)}>
                <div className="modal-content" style={{ maxWidth: '400px' }} onClick={(e) => e.stopPropagation()}>
                  <div className="modal-header">
                    <h3>{expiryModalData.isBulk ? 'Set Expiry for Selected Codes' : 'Set Code Expiry'}</h3>
                    <button className="modal-close" onClick={() => setShowExpiryModal(false)}>&times;</button>
                  </div>
                  <div className="modal-body">
                    {expiryModalData.isBulk ? (
                      <p style={{ marginBottom: '15px', color: '#666' }}>
                        Setting expiry for <strong>{expiryModalData.codeIds?.length}</strong> selected code{expiryModalData.codeIds?.length > 1 ? 's' : ''}
                      </p>
                    ) : (
                      <>
                        <p style={{ marginBottom: '15px', color: '#666' }}>
                          Code: <code style={{ background: '#f0f0f0', padding: '2px 6px', borderRadius: '3px' }}>{expiryModalData.code?.code}</code>
                        </p>
                        {expiryModalData.code?.is_expired && (
                          <p style={{ marginBottom: '15px', color: '#dc3545', fontWeight: '600' }}>
                            This code has expired
                          </p>
                        )}
                      </>
                    )}
                    <div className="form-group" style={{ marginBottom: '15px' }}>
                      <label>Expiry Date (DD/MM/YYYY)</label>
                      <input
                        type="text"
                        value={expiryDate}
                        onChange={(e) => setExpiryDate(e.target.value)}
                        placeholder="28/03/2026"
                        className="admin-input"
                        style={{ width: '100%' }}
                      />
                    </div>
                    <div className="form-group" style={{ marginBottom: '15px' }}>
                      <label>Expiry Time (HH:MM - 24hr UK time)</label>
                      <input
                        type="text"
                        value={expiryTime}
                        onChange={(e) => setExpiryTime(e.target.value)}
                        placeholder="14:30"
                        className="admin-input"
                        style={{ width: '100%' }}
                      />
                    </div>
                    <p style={{ fontSize: '12px', color: '#999' }}>
                      Leave both fields empty to remove expiry (code{expiryModalData.isBulk ? 's' : ''} never expire{expiryModalData.isBulk ? '' : 's'})
                    </p>
                  </div>
                  <div className="modal-actions">
                    <button
                      className="modal-btn modal-btn-secondary"
                      onClick={() => setShowExpiryModal(false)}
                    >
                      Cancel
                    </button>
                    <button
                      className="modal-btn modal-btn-primary"
                      onClick={updatePromoCodeExpiry}
                      disabled={updatingExpiry}
                    >
                      {updatingExpiry ? 'Saving...' : (expiryModalData.isBulk ? `Update ${expiryModalData.codeIds?.length} Codes` : 'Save Expiry')}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'leads' && (
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
        )}

        {activeTab === 'customers' && (
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
            onViewReferralDetails={() => {
              closeCustomerModal()
              setActiveTab('marketing')
              setMarketingSubTab('referrals')
            }}
          />
        )}

        {activeTab === 'pricing' && (
          <PricingSection
            pricing={pricing}
            fetchPricing={fetchPricing}
            pricingMessage={pricingMessage}
            loadingPricing={loadingPricing}
            setPricing={setPricing}
            savingPricing={savingPricing}
            savePricing={savePricing}
          />
        )}

        {activeTab === 'reports' && (
          <div className="admin-section">
            <h2>
              {reportsSubTab === 'growth' && 'Booking Growth'}
              {reportsSubTab === 'financial' && 'Financial'}
              {reportsSubTab === 'sessions' && 'Session Tracking'}
              {reportsSubTab === 'analytics' && 'Abandoned Carts'}
              {reportsSubTab === 'forecast' && 'Bookings Forecast'}
              {reportsSubTab === 'occupancy' && 'Occupancy'}
              {reportsSubTab === 'popular' && 'Popular Routes'}
              {reportsSubTab === 'map' && 'Location Maps'}
            </h2>

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
                        onClick={() => { fetchBookingStats(); fetchFunFacts(true); }}
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
                            {' '}({bookingStats.this_month >= bookingStats.last_month ? '+' : ''}{Math.round(((bookingStats.this_month - bookingStats.last_month) / bookingStats.last_month) * 100)}%)
                          </div>
                        )}
                      </div>
                      <div className="stats-card">
                        <div className="stats-card-value">{bookingStats.this_week}</div>
                        <div className="stats-card-label">This Week</div>
                        {bookingStats.last_week > 0 && (
                          <div className={`stats-card-change ${bookingStats.this_week >= bookingStats.last_week ? 'positive' : 'negative'}`}>
                            {bookingStats.this_week >= bookingStats.last_week ? '+' : ''}{bookingStats.this_week - bookingStats.last_week} vs last week
                            {' '}({bookingStats.this_week >= bookingStats.last_week ? '+' : ''}{Math.round(((bookingStats.this_week - bookingStats.last_week) / bookingStats.last_week) * 100)}%)
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
                            {bookingStats.top_durations?.length > 0 && (
                              <div className="trip-insight-busiest-section">
                                <span className="trip-insight-busiest-label">Top 10:</span>
                                {bookingStats.top_durations.map((d, i) => (
                                  <span key={i} className="trip-insight-busiest">
                                    {d.days} day{d.days !== 1 ? 's' : ''} ({d.count} · {d.percent}%)
                                  </span>
                                ))}
                              </div>
                            )}
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

                    {/* Busiest Booking Days (when customers make bookings) */}
                    {bookingStats.booking_days_of_week && bookingStats.booking_days_of_week.length > 0 && (
                      <div className="booking-days-section">
                        <h3>Busiest Booking Days</h3>
                        <p className="section-subtitle">When customers make their bookings (UK time)</p>
                        <div className="day-of-week-chart">
                          {(() => {
                            const maxCount = Math.max(...bookingStats.booking_days_of_week.map(d => d.count));
                            return bookingStats.booking_days_of_week.map((day, index) => (
                              <div key={index} className="day-bar-container">
                                <div className="day-label">{day.day.substring(0, 3)}</div>
                                <div className="day-bar-wrapper">
                                  <div
                                    className="day-bar"
                                    style={{
                                      height: `${maxCount > 0 ? (day.count / maxCount) * 100 : 0}%`,
                                      backgroundColor: day.count === maxCount ? '#22c55e' : '#3b82f6'
                                    }}
                                  />
                                </div>
                                <div className="day-count">{day.count}</div>
                                <div className="day-percent">{day.percent}%</div>
                              </div>
                            ));
                          })()}
                        </div>
                      </div>
                    )}

                    {/* Peak Booking Hours (UK timezone) */}
                    {bookingStats.booking_hours_of_day && bookingStats.booking_hours_of_day.length > 0 && (
                      <div className="booking-hours-section">
                        <h3>Peak Booking Hours</h3>
                        <p className="section-subtitle">When customers make their bookings (UK time)</p>

                        {/* View Switcher */}
                        <div className="peak-hours-view-switcher">
                          <button
                            className={`view-switch-btn ${peakHoursView === 'overall' ? 'active' : ''}`}
                            onClick={() => setPeakHoursView('overall')}
                          >
                            Overall
                          </button>
                          {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map(day => (
                            <button
                              key={day}
                              className={`view-switch-btn ${peakHoursView === day ? 'active' : ''}`}
                              onClick={() => setPeakHoursView(day)}
                            >
                              {day.substring(0, 3)}
                            </button>
                          ))}
                        </div>

                        {/* Time Ranges Summary - only show for overall view */}
                        {peakHoursView === 'overall' && bookingStats.booking_time_ranges && (
                          <div className="time-ranges-grid">
                            {bookingStats.booking_time_ranges.map((range, index) => (
                              <div key={index} className="time-range-card">
                                <div className="time-range-label">{range.label.split(' ')[0]}</div>
                                <div className="time-range-hours">{range.label.match(/\(([^)]+)\)/)?.[1]}</div>
                                <div className="time-range-count">{range.count}</div>
                                <div className="time-range-percent">{range.percent}%</div>
                              </div>
                            ))}
                          </div>
                        )}

                        {/* Day-specific total */}
                        {peakHoursView !== 'overall' && bookingStats.booking_hours_by_day?.[peakHoursView] && (
                          <div className="day-specific-summary">
                            <span className="day-total-label">{peakHoursView}s:</span>
                            <span className="day-total-count">{bookingStats.booking_hours_by_day[peakHoursView].total} bookings</span>
                          </div>
                        )}

                        {/* Hourly Breakdown Chart */}
                        <div className="hourly-chart">
                          {(() => {
                            const hoursData = peakHoursView === 'overall'
                              ? bookingStats.booking_hours_of_day
                              : bookingStats.booking_hours_by_day?.[peakHoursView]?.hours || [];
                            const maxCount = Math.max(...hoursData.map(h => h.count), 1);

                            return hoursData.map((hour, index) => (
                              <div key={index} className="hour-bar-container">
                                <div className="hour-bar-wrapper">
                                  <div
                                    className="hour-bar"
                                    style={{
                                      height: `${maxCount > 0 ? (hour.count / maxCount) * 100 : 0}%`,
                                      backgroundColor: hour.count === maxCount ? '#22c55e' : '#3b82f6'
                                    }}
                                    title={`${hour.label}: ${hour.count} bookings (${hour.percent}%)`}
                                  />
                                </div>
                                <div className="hour-label">{hour.hour}</div>
                              </div>
                            ));
                          })()}
                        </div>
                        <p className="chart-helper-text">Hours shown in 24-hour format (UK timezone)</p>
                      </div>
                    )}

                    {/* Peak Search Hours (UK timezone) */}
                    {bookingStats.search_hours_of_day && bookingStats.search_hours_of_day.length > 0 && bookingStats.total_searches > 0 && (
                      <div className="booking-hours-section search-hours-section">
                        <h3>Peak Search Hours</h3>
                        <p className="section-subtitle">When customers search for quotes (UK time)</p>

                        {/* View Switcher */}
                        <div className="peak-hours-view-switcher">
                          <button
                            className={`view-switch-btn ${peakSearchView === 'overall' ? 'active' : ''}`}
                            onClick={() => setPeakSearchView('overall')}
                          >
                            Overall
                          </button>
                          {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map(day => (
                            <button
                              key={day}
                              className={`view-switch-btn ${peakSearchView === day ? 'active' : ''}`}
                              onClick={() => setPeakSearchView(day)}
                            >
                              {day.substring(0, 3)}
                            </button>
                          ))}
                        </div>

                        {/* Time Ranges Summary - only show for overall view */}
                        {peakSearchView === 'overall' && bookingStats.search_time_ranges && (
                          <div className="time-ranges-grid">
                            {bookingStats.search_time_ranges.map((range, index) => (
                              <div key={index} className="time-range-card search">
                                <div className="time-range-label">{range.label.split(' ')[0]}</div>
                                <div className="time-range-hours">{range.label.match(/\(([^)]+)\)/)?.[1]}</div>
                                <div className="time-range-count">{range.count}</div>
                                <div className="time-range-percent">{range.percent}%</div>
                              </div>
                            ))}
                          </div>
                        )}

                        {/* Day-specific total */}
                        {peakSearchView !== 'overall' && bookingStats.search_hours_by_day?.[peakSearchView] && (
                          <div className="day-specific-summary">
                            <span className="day-total-label">{peakSearchView}s:</span>
                            <span className="day-total-count">{bookingStats.search_hours_by_day[peakSearchView].total} searches</span>
                          </div>
                        )}

                        {/* Hourly Breakdown Chart */}
                        <div className="hourly-chart">
                          {(() => {
                            const hoursData = peakSearchView === 'overall'
                              ? bookingStats.search_hours_of_day
                              : bookingStats.search_hours_by_day?.[peakSearchView]?.hours || [];
                            const maxCount = Math.max(...hoursData.map(h => h.count), 1);

                            return hoursData.map((hour, index) => (
                              <div key={index} className="hour-bar-container">
                                <div className="hour-bar-wrapper">
                                  <div
                                    className="hour-bar search"
                                    style={{
                                      height: `${maxCount > 0 ? (hour.count / maxCount) * 100 : 0}%`,
                                      backgroundColor: hour.count === maxCount ? '#f97316' : '#fb923c'
                                    }}
                                    title={`${hour.label}: ${hour.count} searches (${hour.percent}%)`}
                                  />
                                </div>
                                <div className="hour-label">{hour.hour}</div>
                              </div>
                            ));
                          })()}
                        </div>
                        <p className="chart-helper-text">Hours shown in 24-hour format (UK timezone)</p>
                        {bookingStats.search_data_start_date && (
                          <p className="chart-footnote">* Session tracking went live {bookingStats.search_data_start_date}</p>
                        )}
                      </div>
                    )}

                    {/* Google Ads Bid Recommendations */}
                    {bookingStats?.bid_recommendations && bookingStats.bid_recommendations.length > 0 && (
                      <div className="bid-recommendations-section">
                        <h3>Google Ads Bid Recommendations</h3>
                        <p className="section-subtitle">
                          Daily recommendations based on search volume and conversion rates since {bookingStats.search_data_start_date}.
                          <br />
                          <strong>{bookingStats.total_searches}</strong> searches → <strong>{bookingStats.bid_total_bookings}</strong> bookings = <strong>{bookingStats.overall_conversion_rate}%</strong> conversion
                        </p>
                        <div className="bid-recommendations-grid">
                          {bookingStats.bid_recommendations.map((rec) => (
                            <div
                              key={rec.day}
                              className={`bid-recommendation-card ${rec.recommendation} priority-${rec.priority}`}
                            >
                              <div className="bid-rec-header">
                                <span className="bid-rec-day">{rec.day}</span>
                                <span className={`bid-rec-badge ${rec.recommendation}`}>
                                  {rec.recommendation === 'increase' && '↑ Increase'}
                                  {rec.recommendation === 'maintain' && '→ Maintain'}
                                  {rec.recommendation === 'reduce' && '↓ Reduce'}
                                </span>
                              </div>
                              <div className="bid-rec-stats">
                                <div className="bid-rec-stat">
                                  <span className="stat-value">{rec.searches}</span>
                                  <span className="stat-label">Searches</span>
                                </div>
                                <div className="bid-rec-stat">
                                  <span className="stat-value">{rec.bookings}</span>
                                  <span className="stat-label">Bookings</span>
                                </div>
                                <div className="bid-rec-stat">
                                  <span className="stat-value">{rec.conversion_rate}%</span>
                                  <span className="stat-label">Conversion</span>
                                </div>
                              </div>
                              <p className="bid-rec-reason">{rec.reason}</p>
                              {rec.peak_search_hours.length > 0 && (
                                <div className="bid-rec-peak-hours">
                                  <span className="peak-hours-label">Peak search hours:</span>
                                  <span className="peak-hours-value">{rec.peak_search_hours.join(', ')}</span>
                                </div>
                              )}
                              {rec.high_converting_hours.length > 0 && (
                                <div className="bid-rec-converting-hours">
                                  <span className="converting-hours-label">Best converting:</span>
                                  <span className="converting-hours-value">
                                    {rec.high_converting_hours.map(h => `${h.label} (${h.conversion_rate}%)`).join(', ')}
                                  </span>
                                </div>
                              )}
                            </div>
                          ))}
                          {/* Overall Summary Card */}
                          <div className="bid-recommendation-card overall">
                            <div className="bid-rec-header">
                              <span className="bid-rec-day">Overall</span>
                              <span className="bid-rec-badge overall">Summary</span>
                            </div>
                            <div className="bid-rec-stats">
                              <div className="bid-rec-stat">
                                <span className="stat-value">{bookingStats.total_searches}</span>
                                <span className="stat-label">Searches</span>
                              </div>
                              <div className="bid-rec-stat">
                                <span className="stat-value">{bookingStats.bid_total_bookings}</span>
                                <span className="stat-label">Bookings</span>
                              </div>
                              <div className="bid-rec-stat">
                                <span className="stat-value">{bookingStats.overall_conversion_rate}%</span>
                                <span className="stat-label">Conversion</span>
                              </div>
                            </div>
                            <p className="bid-rec-reason">
                              {bookingStats.overall_conversion_rate >= 50
                                ? 'Strong conversion rate - campaigns performing well'
                                : bookingStats.overall_conversion_rate >= 30
                                ? 'Good conversion rate - room for optimization'
                                : 'Focus on high-converting days for better ROI'}
                            </p>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Monthly Booking Pattern (payday hypothesis) */}
                    {bookingStats?.monthly_booking_pattern && bookingStats.monthly_booking_pattern.months.length > 0 && (
                      <div className="monthly-pattern-section">
                        <h3>Monthly Booking Pattern</h3>
                        <p className="section-subtitle">
                          Bookings (confirmed + completed, all sources) grouped by week-of-month.
                          Testing whether bookings cluster around UK monthly payday.
                          <br />
                          <strong>Year:</strong> {bookingStats.monthly_booking_pattern.year}
                        </p>
                        <div className="monthly-pattern-grid">
                          {bookingStats.monthly_booking_pattern.months.map((month) => {
                            const max = Math.max(...month.buckets.map(b => b.count), 1)
                            return (
                              <div key={month.month} className="monthly-pattern-card">
                                <div className="monthly-pattern-header">
                                  <span className="monthly-pattern-label">{month.label}</span>
                                  <span className="monthly-pattern-total">{month.total} bookings</span>
                                </div>
                                <div className="monthly-pattern-bars">
                                  {month.buckets.map((b) => (
                                    <div
                                      key={b.key}
                                      className={`monthly-pattern-bar-row ${b.key === month.busiest_bucket ? 'busiest' : ''}`}
                                    >
                                      <span className="bucket-label">{b.label}</span>
                                      <div className="bucket-bar-track">
                                        <div
                                          className="bucket-bar-fill"
                                          style={{ width: `${(b.count / max) * 100}%` }}
                                        />
                                      </div>
                                      <span className="bucket-count">{b.count}</span>
                                    </div>
                                  ))}
                                </div>
                                {month.busiest_bucket && (
                                  <p className="monthly-pattern-insight">
                                    Busiest: <strong>{month.buckets.find(b => b.key === month.busiest_bucket)?.label}</strong>
                                  </p>
                                )}
                              </div>
                            )
                          })}
                          {/* Overall card */}
                          {(() => {
                            const overall = bookingStats.monthly_booking_pattern.overall
                            const max = Math.max(...overall.buckets.map(b => b.count), 1)
                            return (
                              <div className="monthly-pattern-card overall">
                                <div className="monthly-pattern-header">
                                  <span className="monthly-pattern-label">Overall</span>
                                  <span className="monthly-pattern-total">{overall.total} bookings</span>
                                </div>
                                <div className="monthly-pattern-bars">
                                  {overall.buckets.map((b) => (
                                    <div
                                      key={b.key}
                                      className={`monthly-pattern-bar-row ${b.key === overall.busiest_bucket ? 'busiest' : ''}`}
                                    >
                                      <span className="bucket-label">{b.label}</span>
                                      <div className="bucket-bar-track">
                                        <div
                                          className="bucket-bar-fill"
                                          style={{ width: `${(b.count / max) * 100}%` }}
                                        />
                                      </div>
                                      <span className="bucket-count">{b.count}</span>
                                    </div>
                                  ))}
                                </div>
                                {overall.busiest_bucket && (
                                  <p className="monthly-pattern-insight">
                                    Busiest overall: <strong>{overall.buckets.find(b => b.key === overall.busiest_bucket)?.label}</strong>
                                  </p>
                                )}
                              </div>
                            )
                          })()}
                        </div>
                      </div>
                    )}

                    {/* Fun Facts */}
                    {funFacts && (
                      <div className="fun-facts-section">
                        <h3>Fun Facts</h3>
                        <div className="fun-facts-grid">
                          {funFacts.busiestDay && (
                            <div className="fun-fact-card">
                              <span className="fun-fact-icon">📅</span>
                              <div className="fun-fact-content">
                                <span className="fun-fact-label">Busiest {funFacts.busiestDay.dates?.length > 1 ? 'Days' : 'Day'}</span>
                                <span className="fun-fact-value">{funFacts.busiestDay.count} bookings</span>
                                {funFacts.busiestDay.dates?.map((date, index) => (
                                  <span key={index} className="fun-fact-detail">{date}</span>
                                ))}
                              </div>
                            </div>
                          )}
                          {funFacts.busiestWeek && (
                            <div className="fun-fact-card">
                              <span className="fun-fact-icon">📈</span>
                              <div className="fun-fact-content">
                                <span className="fun-fact-label">Busiest Week</span>
                                <span className="fun-fact-value">{funFacts.busiestWeek.bookings} bookings</span>
                                <span className="fun-fact-detail">{funFacts.busiestWeek.startDate} - {funFacts.busiestWeek.endDate}</span>
                              </div>
                            </div>
                          )}
                          {funFacts.busiestMonth && (
                            <div className="fun-fact-card">
                              <span className="fun-fact-icon">🗓️</span>
                              <div className="fun-fact-content">
                                <span className="fun-fact-label">Busiest Month</span>
                                <span className="fun-fact-value">{funFacts.busiestMonth.bookings} bookings</span>
                                <span className="fun-fact-detail">{funFacts.busiestMonth.month}</span>
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
                                <span className="fun-fact-detail">{funFacts.longestTrip.customerName || funFacts.longestTrip.dates}</span>
                              </div>
                            </div>
                          )}
                          {funFacts.highestTransaction && (
                            <div className="fun-fact-card">
                              <span className="fun-fact-icon">💰</span>
                              <div className="fun-fact-content">
                                <span className="fun-fact-label">Highest Transaction</span>
                                <span className="fun-fact-value">{funFacts.highestTransaction.amount}</span>
                                <span className="fun-fact-detail">{funFacts.highestTransaction.customerName || `${funFacts.highestTransaction.days} day trip`}</span>
                              </div>
                            </div>
                          )}
                          {funFacts.latestTimeOfNight && (
                            <div className="fun-fact-card">
                              <span className="fun-fact-icon">🌙</span>
                              <div className="fun-fact-content">
                                <span className="fun-fact-label">Latest Night Owl</span>
                                <span className="fun-fact-value">{funFacts.latestTimeOfNight.time}</span>
                                <span className="fun-fact-detail">{funFacts.latestTimeOfNight.customerName || funFacts.latestTimeOfNight.date}</span>
                              </div>
                            </div>
                          )}
                          {funFacts.earliestTimeOfDay && (
                            <div className="fun-fact-card">
                              <span className="fun-fact-icon">🌅</span>
                              <div className="fun-fact-content">
                                <span className="fun-fact-label">Earliest Riser</span>
                                <span className="fun-fact-value">{funFacts.earliestTimeOfDay.time}</span>
                                <span className="fun-fact-detail">{funFacts.earliestTimeOfDay.customerName || funFacts.earliestTimeOfDay.date}</span>
                              </div>
                            </div>
                          )}
                          {funFacts.lastMinuteBooking && (
                            <div className="fun-fact-card">
                              <span className="fun-fact-icon">⚡</span>
                              <div className="fun-fact-content">
                                <span className="fun-fact-label">Last Minute Booking</span>
                                <span className="fun-fact-value">
                                  {funFacts.lastMinuteBooking.gapDays === 0
                                    ? (funFacts.lastMinuteBooking.gapTime || 'Same day')
                                    : `${funFacts.lastMinuteBooking.gapDays} day${funFacts.lastMinuteBooking.gapDays !== 1 ? 's' : ''} before`}
                                </span>
                                <span className="fun-fact-detail">{funFacts.lastMinuteBooking.customerName || (funFacts.lastMinuteBooking.gapDays === 0 ? 'before drop-off' : `Drop-off: ${funFacts.lastMinuteBooking.dropoffDate}`)}</span>
                              </div>
                            </div>
                          )}
                          {funFacts.advanceBooking && (
                            <div className="fun-fact-card">
                              <span className="fun-fact-icon">📆</span>
                              <div className="fun-fact-content">
                                <span className="fun-fact-label">Most Advance Booking</span>
                                <span className="fun-fact-value">
                                  {funFacts.advanceBooking.gapDetailed
                                    ? `${funFacts.advanceBooking.gapDetailed.months}m ${funFacts.advanceBooking.gapDetailed.days}d ${String(funFacts.advanceBooking.gapDetailed.hours).padStart(2, '0')}:${String(funFacts.advanceBooking.gapDetailed.minutes).padStart(2, '0')}:${String(funFacts.advanceBooking.gapDetailed.seconds).padStart(2, '0')}`
                                    : `${funFacts.advanceBooking.gapDays} days ahead`}
                                </span>
                                <span className="fun-fact-detail">{funFacts.advanceBooking.customerName || 'before drop-off'}</span>
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Milestones */}
                    {funFacts?.milestones?.length > 0 && (
                      <div className="milestones-section">
                        <h3>Booking Milestones</h3>
                        <div className="milestones-grid">
                          {funFacts.milestones.map((milestone) => (
                            <div key={milestone.number} className={`milestone-card milestone-${milestone.number === 1 ? 'first' : milestone.number >= 100 ? 'century' : 'standard'}`}>
                              <div className="milestone-badge">
                                <span className="milestone-number">{milestone.label}</span>
                                <span className="milestone-label">booking</span>
                              </div>
                              <div className="milestone-details">
                                {milestone.customerName && (
                                  <span className="milestone-customer">{milestone.customerName}</span>
                                )}
                                <span className="milestone-datetime">{milestone.date} at {milestone.time}</span>
                              </div>
                            </div>
                          ))}
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
                                {[1, 2, 3, 4, 5, 10, 15, 20, 25, 30].map(target => (
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
                                {[1, 5, 10, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100].map(target => (
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
                                {[1, 10, 25, 50, 75, 100, 125, 150, 175, 200, 250, 300, 350].map(target => (
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
                                {[1, 10, 25, 50, 75, 100, 150, 250, 500, 750, 1000].map(target => (
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
                  View online-cap utilization from confirmed and completed bookings. Total capacity and manual reserve are managed below.
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
                    onClick={() => fetchOccupancyReport(occupancyView, true)}
                    disabled={loadingOccupancy}
                  >
                    {loadingOccupancy ? 'Refreshing...' : 'Refresh Data'}
                  </button>
                </div>

                <div className="capacity-settings-panel">
                  <div className="capacity-settings-header">
                    <div>
                      <h4>Capacity Schedule</h4>
                      <p>Total spaces minus online spaces becomes the manual reserve. Each row applies to that UK operational day.</p>
                    </div>
                    {loadingCapacitySettings && <span className="capacity-settings-status">Loading...</span>}
                  </div>

                  <form className="capacity-settings-form" onSubmit={saveCapacitySettings}>
                    <label>
                      <span>Effective From (UK)</span>
                      <input
                        type="text"
                        inputMode="numeric"
                        placeholder="11/06/2026 14:30"
                        value={capacityForm.effective_from}
                        onChange={e => setCapacityForm({ ...capacityForm, effective_from: e.target.value })}
                      />
                    </label>
                    <label>
                      <span>Total Spaces</span>
                      <input
                        type="number"
                        min="1"
                        value={capacityForm.total_spaces}
                        onChange={e => setCapacityForm({ ...capacityForm, total_spaces: e.target.value })}
                      />
                    </label>
                    <label>
                      <span>Online Spaces</span>
                      <input
                        type="number"
                        min="1"
                        value={capacityForm.online_spaces}
                        onChange={e => setCapacityForm({ ...capacityForm, online_spaces: e.target.value })}
                      />
                    </label>
                    <div className="capacity-reserve-preview">
                      <span>Manual Reserve</span>
                      <strong>
                        {Math.max(
                          0,
                          (parseInt(capacityForm.total_spaces, 10) || 0) -
                          (parseInt(capacityForm.online_spaces, 10) || 0)
                        )}
                      </strong>
                    </div>
                    <button
                      type="submit"
                      className="save-capacity-btn"
                      disabled={savingCapacitySettings}
                    >
                      {savingCapacitySettings ? 'Saving...' : 'Save Capacity'}
                    </button>
                  </form>

                  {capacityMessage && (
                    <div className={`capacity-settings-message ${capacityMessage.includes('saved') ? 'success' : 'error'}`}>
                      {capacityMessage}
                    </div>
                  )}

                  {capacitySettings?.settings?.length > 0 && (
                    <div className="capacity-schedule-list">
                      {capacitySettings.settings.map(setting => (
                        <div key={setting.effective_from} className="capacity-schedule-row">
                          <span>{setting.effective_from_display || setting.effective_from}</span>
                          <strong>{setting.total_spaces} total</strong>
                          <strong>{setting.online_spaces} online</strong>
                          <strong>{setting.manual_spaces} manual</strong>
                        </div>
                      ))}
                    </div>
                  )}
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
                        <span className="occupancy-stat-label">Online Spaces</span>
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
                              Online cap: {occupancyData.max_capacity} spaces
                            </span>
                        </div>
                      </div>
                        <div className="occupancy-chart-wrapper">
                          <div className="occupancy-y-axis">
                            <span className="y-axis-label" style={{ bottom: '100%' }}>{occupancyChartMaxPercent}%</span>
                            <span className="y-axis-label" style={{ bottom: `${(100 / occupancyChartMaxPercent) * 87.5 + 12.5}%` }}>100%</span>
                            <span className="y-axis-label" style={{ bottom: `${(75 / occupancyChartMaxPercent) * 87.5 + 12.5}%` }}>75%</span>
                            <span className="y-axis-label" style={{ bottom: `${(50 / occupancyChartMaxPercent) * 87.5 + 12.5}%` }}>50%</span>
                            <span className="y-axis-label" style={{ bottom: `${(25 / occupancyChartMaxPercent) * 87.5 + 12.5}%` }}>25%</span>
                            <span className="y-axis-label" style={{ bottom: '12.5%' }}>0%</span>
                          </div>
                          <div className="occupancy-chart-area">
                            <div className="occupancy-gridlines">
                              <div className="gridline" style={{ bottom: '100%' }}></div>
                              <div className="gridline gridline-cap" style={{ bottom: `${(100 / occupancyChartMaxPercent) * 100}%` }}></div>
                              <div className="gridline" style={{ bottom: `${(75 / occupancyChartMaxPercent) * 100}%` }}></div>
                              <div className="gridline" style={{ bottom: `${(50 / occupancyChartMaxPercent) * 100}%` }}></div>
                              <div className="gridline" style={{ bottom: `${(25 / occupancyChartMaxPercent) * 100}%` }}></div>
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
                                const online = item.online_capacity || item.avg_online_capacity || occupancyData.online_capacity || occupancyData.max_capacity;
                                const available = (item.available ?? item.avg_available ?? (online - occupied));
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
                                    <div className={barClass} style={{ height: `${Math.max((percent / occupancyChartMaxPercent) * 100, 3)}%` }}>
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

                      {/* Secondary Car Park (P2) — future eligible events */}
                      <div className="capacity-settings-panel secondary-carpark-panel">
                        <div className="capacity-settings-header">
                          <div>
                            <h4>Secondary Car Park (P2)</h4>
                            <p>
                              Future drop-offs and pickups (from today) for bookings within{' '}
                              {secondaryReport ? `${secondaryReport.window_start}–${secondaryReport.window_end}` : 'the operating window'}
                              {secondaryReport ? ` — ${secondaryReport.count} eligible bookings, capacity ${secondaryReport.capacity}` : ''}
                            </p>
                          </div>
                          <div className="chart-controls" style={{ margin: 0 }}>
                            <select value={secondaryGroup} onChange={e => setSecondaryGroup(e.target.value)}>
                              <option value="daily">Daily</option>
                              <option value="weekly">Weekly</option>
                              <option value="monthly">Monthly</option>
                            </select>
                          </div>
                        </div>
                        {loadingSecondaryReport ? (
                          <div className="admin-loading-inline"><div className="spinner-small"></div><span>Loading...</span></div>
                        ) : !secondaryReport || (secondaryReport.events || []).length === 0 ? (
                          <p style={{ opacity: 0.7 }}>No eligible future bookings.</p>
                        ) : (() => {
                          const groupKey = (ev) => {
                            const d = new Date(ev.date + 'T00:00:00')
                            if (secondaryGroup === 'monthly') {
                              return d.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
                            }
                            if (secondaryGroup === 'weekly') {
                              const monday = new Date(d)
                              monday.setDate(d.getDate() - ((d.getDay() + 6) % 7))
                              const sunday = new Date(monday)
                              sunday.setDate(monday.getDate() + 6)
                              const fmt = (x) => x.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: 'numeric' })
                              return `Week ${fmt(monday)} – ${fmt(sunday)}`
                            }
                            return d.toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric' })
                          }
                          const groups = {}
                          secondaryReport.events.forEach(ev => {
                            const key = groupKey(ev)
                            if (!groups[key]) groups[key] = []
                            groups[key].push(ev)
                          })
                          return Object.entries(groups).map(([label, rows]) => (
                            <details key={label} className="occupancy-month-group">
                              <summary className="occupancy-month-header">
                                <span className="month-title">{label}</span>
                                <span className="month-stats">
                                  <span className="month-days">{rows.length} event{rows.length !== 1 ? 's' : ''}</span>
                                </span>
                              </summary>
                              <div className="occupancy-table-wrapper">
                                <table className="occupancy-table p2-events-table">
                                  <colgroup>
                                    <col style={{ width: '17%' }} />
                                    <col style={{ width: '24%' }} />
                                    <col style={{ width: '21%' }} />
                                    <col style={{ width: '15%' }} />
                                    <col style={{ width: '23%' }} />
                                  </colgroup>
                                  <thead>
                                    <tr>
                                      <th>Ref</th>
                                      <th>Name</th>
                                      <th>Car</th>
                                      <th>Reg</th>
                                      <th>Event</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {rows.map((ev, i) => (
                                      <tr key={`${ev.reference}-${ev.event}-${i}`}>
                                        <td className="date-cell" data-label="Ref">{ev.reference}</td>
                                        <td data-label="Name">{ev.customer_name || '-'}</td>
                                        <td data-label="Car">{ev.car || '-'}</td>
                                        <td className="p2-reg-cell" data-label="Reg">{ev.registration || '-'}</td>
                                        <td data-label="Event">
                                          {ev.event === 'dropoff' ? 'Drop-off' : 'Pickup'}
                                          {secondaryGroup === 'daily' ? '' : ` ${ev.display_date}`}
                                          {ev.time ? ` @ ${ev.time}` : ''}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </details>
                          ))
                        })()}
                      </div>
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
                    onClick={() => fetchBookingLocations(mapType, true)}
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

            {/* Financial Report */}
            {reportsSubTab === 'financial' && (
              <>
                <div className="reports-section-header">
                  <button
                    className="refresh-page-btn"
                    onClick={() => fetchFinancialReport(true)}
                    disabled={loadingFinancial}
                  >
                    {loadingFinancial ? 'Refreshing...' : 'Refresh Page'}
                  </button>
                </div>

                {/* Filters */}
                <div className="financial-filters">
                  <div className="filter-group">
                    <label>From Date</label>
                    <div style={{ display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
                      <input
                        type="text"
                        placeholder="DD/MM/YYYY"
                        value={financialFromDate}
                        onChange={(e) => setFinancialFromDate(formatDateInput(e.target.value))}
                        maxLength={10}
                      />
                      <DatePicker
                        selected={parseUkDate(financialFromDate)}
                        onChange={(date) => setFinancialFromDate(dateToUkString(date))}
                        dateFormat="dd/MM/yyyy"
                        customInput={<button type="button" className="date-picker-btn">📅</button>}
                      />
                    </div>
                  </div>
                  <div className="filter-group">
                    <label>To Date</label>
                    <div style={{ display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
                      <input
                        type="text"
                        placeholder="DD/MM/YYYY"
                        value={financialToDate}
                        onChange={(e) => setFinancialToDate(formatDateInput(e.target.value))}
                        maxLength={10}
                      />
                      <DatePicker
                        selected={parseUkDate(financialToDate)}
                        onChange={(date) => setFinancialToDate(dateToUkString(date))}
                        dateFormat="dd/MM/yyyy"
                        customInput={<button type="button" className="date-picker-btn">📅</button>}
                      />
                    </div>
                  </div>
                  <div className="filter-group">
                    <label>Status</label>
                    <select
                      value={financialStatusFilter}
                      onChange={(e) => setFinancialStatusFilter(e.target.value)}
                    >
                      <option value="all">All</option>
                      <option value="confirmed">Confirmed</option>
                      <option value="completed">Completed</option>
                      <option value="refunded">Refunded</option>
                    </select>
                  </div>
                  <div className="filter-group">
                    <label>Promo Code</label>
                    <select
                      value={financialPromoFilter}
                      onChange={(e) => setFinancialPromoFilter(e.target.value)}
                    >
                      <option value="all">All</option>
                      <option value="yes">With Promo</option>
                      <option value="no">Without Promo</option>
                    </select>
                  </div>
                  <button
                    className="filter-apply-btn"
                    onClick={fetchFinancialReport}
                    disabled={loadingFinancial}
                  >
                    Apply Filters
                  </button>
                  <button
                    className="export-csv-btn"
                    onClick={exportFinancialCSV}
                    disabled={exportingFinancial}
                  >
                    {exportingFinancial ? 'Exporting...' : 'Export CSV'}
                  </button>
                </div>

                {loadingFinancial ? (
                  <div className="admin-loading-inline">
                    <div className="spinner-small"></div>
                    <span>Loading financial report...</span>
                  </div>
                ) : financialData ? (
                  <>
                    {/* Revenue Fun Facts */}
                    <div className="financial-fun-facts">
                      <h3>Revenue Highlights</h3>
                      <div className="stats-summary-cards">
                        {financialData.funFacts?.revenueToday && (
                          <div className="stats-card fun-fact-card fun-fact-vertical">
                            <div className="stats-card-label">Revenue Today</div>
                            <div className="stats-card-value">{financialData.funFacts.revenueToday.amount}</div>
                            {financialData.funFacts.revenueToday.vsYesterday && (
                              <div className="fun-fact-change" style={{ color: financialData.funFacts.revenueToday.vsYesterday.startsWith('+') ? '#22c55e' : '#ef4444' }}>
                                {financialData.funFacts.revenueToday.vsYesterday} vs yesterday
                              </div>
                            )}
                          </div>
                        )}
                        {financialData.funFacts?.revenueThisWeek && (
                          <div className="stats-card fun-fact-card fun-fact-vertical">
                            <div className="stats-card-label">Revenue This Week</div>
                            <div className="stats-card-value">{financialData.funFacts.revenueThisWeek.amount}</div>
                            {financialData.funFacts.revenueThisWeek.vsLastWeek && (
                              <div className="fun-fact-change" style={{ color: financialData.funFacts.revenueThisWeek.vsLastWeek.startsWith('+') ? '#22c55e' : '#ef4444' }}>
                                {financialData.funFacts.revenueThisWeek.vsLastWeek} vs last week
                              </div>
                            )}
                          </div>
                        )}
                        {financialData.funFacts?.revenueThisMonth && (
                          <div className="stats-card fun-fact-card fun-fact-vertical">
                            <div className="stats-card-label">Revenue This Month</div>
                            <div className="stats-card-value">{financialData.funFacts.revenueThisMonth.amount}</div>
                            {financialData.funFacts.revenueThisMonth.vsLastMonth && (
                              <div className="fun-fact-change" style={{ color: financialData.funFacts.revenueThisMonth.vsLastMonth.startsWith('+') ? '#22c55e' : '#ef4444' }}>
                                {financialData.funFacts.revenueThisMonth.vsLastMonth} vs last month
                              </div>
                            )}
                          </div>
                        )}
                        {financialData.funFacts?.topRevenueDay && (
                          <div className="stats-card fun-fact-card fun-fact-vertical">
                            <div className="stats-card-label">Top Revenue Day</div>
                            <div className="stats-card-value">{financialData.funFacts.topRevenueDay.amount}</div>
                            <div className="fun-fact-detail">{financialData.funFacts.topRevenueDay.date}</div>
                          </div>
                        )}
                        {financialData.funFacts?.topRevenueWeek && (
                          <div className="stats-card fun-fact-card fun-fact-vertical">
                            <div className="stats-card-label">Top Revenue Week</div>
                            <div className="stats-card-value">{financialData.funFacts.topRevenueWeek.amount}</div>
                            <div className="fun-fact-detail">{financialData.funFacts.topRevenueWeek.week}</div>
                          </div>
                        )}
                        {financialData.funFacts?.topRevenueMonth && (
                          <div className="stats-card fun-fact-card fun-fact-vertical">
                            <div className="stats-card-label">Top Revenue Month</div>
                            <div className="stats-card-value">{financialData.funFacts.topRevenueMonth.amount}</div>
                            <div className="fun-fact-detail">{financialData.funFacts.topRevenueMonth.month}</div>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Revenue Milestones */}
                    {financialData.funFacts?.revenueMilestones?.length > 0 && (
                      <div className="revenue-milestones-section">
                        <h3>Revenue Milestones</h3>
                        <div className="revenue-milestones-grid">
                          {financialData.funFacts.revenueMilestones.map((milestone) => (
                            <div
                              key={milestone.amount}
                              className={`revenue-milestone-card ${milestone.achieved ? 'achieved' : 'pending'} ${milestone.amount >= 50000 ? 'major' : milestone.amount >= 10000 ? 'significant' : ''}`}
                            >
                              <div className="milestone-amount">{milestone.label}</div>
                              {milestone.achieved ? (
                                <div className="milestone-date">{milestone.date}</div>
                              ) : (
                                <div className="milestone-pending">Coming soon...</div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Summary Totals */}
                    <div className="financial-summary">
                      <h3>Summary</h3>
                      <div className="stats-summary-cards">
                        <div className="stats-card">
                          <div className="stats-card-value">{financialData.summary?.totalBookings || 0}</div>
                          <div className="stats-card-label">Total Bookings</div>
                        </div>
                        <div className="stats-card">
                          <div className="stats-card-value">{financialData.summary?.totalGross || '£0.00'}</div>
                          <div className="stats-card-label">Original Price (Gross)</div>
                        </div>
                        <div className="stats-card">
                          <div className="stats-card-value" style={{ color: '#f59e0b' }}>{financialData.summary?.totalDiscount || '£0.00'}</div>
                          <div className="stats-card-label">Total Discounts</div>
                        </div>
                        <div className="stats-card">
                          <div className="stats-card-value">{financialData.summary?.totalNet || '£0.00'}</div>
                          <div className="stats-card-label">Amount Paid (Net)</div>
                        </div>
                        <div className="stats-card">
                          <div className="stats-card-value" style={{ color: '#ef4444' }}>{financialData.summary?.totalRefunds || '£0.00'}</div>
                          <div className="stats-card-label">Total Refunds</div>
                        </div>
                        <div className="stats-card">
                          <div className="stats-card-value" style={{ color: '#22c55e' }}>{financialData.summary?.totalRevenue || '£0.00'}</div>
                          <div className="stats-card-label">Final Revenue</div>
                        </div>
                      </div>
                    </div>

                    {/* Revenue Chart */}
                    {financialData.chartData && (
                      <div className="booking-chart revenue-chart-section">
                        <div className="chart-controls">
                          <label>View:</label>
                          <select value={revenueChartType} onChange={e => setRevenueChartType(e.target.value)}>
                            <option value="monthly">Monthly</option>
                            <option value="weekly">Weekly</option>
                            <option value="daily">Daily</option>
                            <option value="cumulative">Cumulative Growth</option>
                          </select>
                        </div>

                        <h3>
                          {revenueChartType === 'monthly' && 'Revenue by Month'}
                          {revenueChartType === 'weekly' && 'Revenue by Week'}
                          {revenueChartType === 'daily' && 'Revenue by Day'}
                          {revenueChartType === 'cumulative' && 'Cumulative Revenue Growth'}
                        </h3>

                        <div className="chart-container">
                          {revenueChartType === 'cumulative' ? (
                            <div className="line-chart">
                              {financialData.chartData.cumulative?.length > 0 && (
                                <>
                                  <div className="chart-y-axis">
                                    <span>£{Math.round(Math.max(...financialData.chartData.cumulative.map(d => d.totalPounds)))}</span>
                                    <span>£{Math.round(Math.max(...financialData.chartData.cumulative.map(d => d.totalPounds)) / 2)}</span>
                                    <span>£0</span>
                                  </div>
                                  <div className="chart-area">
                                    <svg viewBox={`0 0 ${Math.min(financialData.chartData.cumulative.length * 30, 1200)} 200`} preserveAspectRatio="none">
                                      <defs>
                                        <linearGradient id="revenueLineGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                                          <stop offset="0%" stopColor="#22c55e" stopOpacity="0.3" />
                                          <stop offset="100%" stopColor="#22c55e" stopOpacity="0.05" />
                                        </linearGradient>
                                      </defs>
                                      {(() => {
                                        const data = financialData.chartData.cumulative
                                        const maxVal = Math.max(...data.map(d => d.totalPounds))
                                        const width = Math.min(data.length * 30, 1200)
                                        const points = data.map((d, i) => {
                                          const x = (i / (data.length - 1)) * width
                                          const y = 200 - ((d.totalPounds / maxVal) * 180)
                                          return `${x},${y}`
                                        }).join(' ')
                                        const areaPoints = `0,200 ${points} ${width},200`
                                        return (
                                          <>
                                            <polygon points={areaPoints} fill="url(#revenueLineGradient)" />
                                            <polyline points={points} fill="none" stroke="#22c55e" strokeWidth="2" />
                                          </>
                                        )
                                      })()}
                                    </svg>
                                  </div>
                                </>
                              )}
                            </div>
                          ) : revenueChartType === 'weekly' ? (
                            <div className="weekly-chart-container">
                              {(() => {
                                const data = financialData.chartData.weekly || []
                                const weeksPerPage = 8
                                const totalPages = Math.ceil(data.length / weeksPerPage)
                                const startIdx = Math.max(0, data.length - weeksPerPage - (revenueWeeklyPageIndex * weeksPerPage))
                                const endIdx = Math.min(data.length, startIdx + weeksPerPage)
                                const displayData = data.slice(startIdx, endIdx)
                                const maxRevenue = Math.max(...displayData.map(d => d.revenuePounds), 1)
                                const BAR_STACK_PX = 150 // matches inline height below; px-based to avoid the single-child flex-column % quirk that was clipping bars to ~full height

                                return (
                                  <>
                                    {totalPages > 1 && (
                                      <div className="chart-navigation">
                                        <button
                                          className="nav-btn"
                                          onClick={() => setRevenueWeeklyPageIndex(i => Math.min(i + 1, totalPages - 1))}
                                          disabled={revenueWeeklyPageIndex >= totalPages - 1}
                                        >
                                          &larr; Older
                                        </button>
                                        <span className="nav-info">
                                          Showing weeks {startIdx + 1}-{endIdx} of {data.length}
                                        </span>
                                        <button
                                          className="nav-btn"
                                          onClick={() => setRevenueWeeklyPageIndex(i => Math.max(i - 1, 0))}
                                          disabled={revenueWeeklyPageIndex <= 0}
                                        >
                                          Newer &rarr;
                                        </button>
                                      </div>
                                    )}
                                    <div className="stacked-bar-chart">
                                      {displayData.map((item, idx) => (
                                        <div key={idx} className="bar-column">
                                          <div className="bar-stack" style={{ height: `${BAR_STACK_PX}px` }}>
                                            <div
                                              className="bar-segment bar-confirmed"
                                              style={{ height: `${(item.revenuePounds / maxRevenue) * BAR_STACK_PX}px` }}
                                              title={`£${item.revenuePounds.toFixed(2)}`}
                                            />
                                          </div>
                                          <div className="bar-label">{item.weekLabel?.split(' - ')[0] || item.week}</div>
                                          <div className="bar-total">£{item.revenuePounds.toFixed(0)}</div>
                                        </div>
                                      ))}
                                    </div>
                                  </>
                                )
                              })()}
                            </div>
                          ) : revenueChartType === 'daily' ? (
                            <div className="daily-chart-container">
                              {(() => {
                                const data = financialData.chartData.daily || []
                                const monthlyGroups = {}
                                data.forEach(item => {
                                  const monthKey = item.date?.slice(0, 7)
                                  if (monthKey) {
                                    if (!monthlyGroups[monthKey]) monthlyGroups[monthKey] = []
                                    monthlyGroups[monthKey].push(item)
                                  }
                                })
                                const months = Object.keys(monthlyGroups).sort().reverse()

                                return months.map(monthKey => {
                                  const monthItems = monthlyGroups[monthKey]
                                  const [year, month] = monthKey.split('-')
                                  const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
                                  const monthLabel = `${monthNames[parseInt(month, 10) - 1]} ${year}`
                                  const isExpanded = expandedRevenueDailyMonths[monthKey] !== false
                                  const monthTotal = monthItems.reduce((sum, d) => sum + d.revenuePounds, 0)
                                  const maxRevenue = Math.max(...monthItems.map(d => d.revenuePounds), 1)
                                  const BAR_STACK_PX = 150

                                  return (
                                    <div key={monthKey} className="daily-month-group">
                                      <div
                                        className="daily-month-header"
                                        onClick={() => setExpandedRevenueDailyMonths(prev => ({
                                          ...prev,
                                          [monthKey]: !isExpanded
                                        }))}
                                      >
                                        <span className="expand-icon">{isExpanded ? '▼' : '▶'}</span>
                                        <span className="month-label">{monthLabel}</span>
                                        <span className="month-total">£{monthTotal.toFixed(2)}</span>
                                      </div>
                                      {isExpanded && (
                                        <div className="stacked-bar-chart daily-bar-chart">
                                          {monthItems.map((item, idx) => {
                                            const dayLabel = item.date?.slice(8, 10).replace(/^0/, '') || ''
                                            return (
                                              <div key={idx} className="bar-column">
                                                <div className="bar-stack" style={{ height: `${BAR_STACK_PX}px` }}>
                                                  <div
                                                    className="bar-segment bar-confirmed"
                                                    style={{ height: `${(item.revenuePounds / maxRevenue) * BAR_STACK_PX}px` }}
                                                    title={`£${item.revenuePounds.toFixed(2)}`}
                                                  />
                                                </div>
                                                <div className="bar-label">{dayLabel}</div>
                                                <div className="bar-total">£{item.revenuePounds.toFixed(0)}</div>
                                              </div>
                                            )
                                          })}
                                        </div>
                                      )}
                                    </div>
                                  )
                                })
                              })()}
                            </div>
                          ) : (
                            <div className="stacked-bar-chart">
                              {(() => {
                                const data = financialData.chartData.monthly || []
                                const maxRevenue = Math.max(...data.map(d => d.revenuePounds), 1)
                                const BAR_STACK_PX = 150
                                return data.map((item, idx) => (
                                  <div key={idx} className="bar-column">
                                    <div className="bar-stack" style={{ height: `${BAR_STACK_PX}px` }}>
                                      <div
                                        className="bar-segment bar-confirmed"
                                        style={{ height: `${(item.revenuePounds / maxRevenue) * BAR_STACK_PX}px` }}
                                        title={`£${item.revenuePounds.toFixed(2)}`}
                                      />
                                    </div>
                                    <div className="bar-label">{item.monthLabel}</div>
                                    <div className="bar-total">£{item.revenuePounds.toFixed(0)}</div>
                                  </div>
                                ))
                              })()}
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Monthly Breakdown */}
                    <div className="financial-monthly-breakdown">
                      <h3>Monthly Breakdown</h3>
                      {financialData.monthlyData?.length === 0 ? (
                        <p className="admin-empty">No financial data found for the selected filters.</p>
                      ) : (
                        financialData.monthlyData?.map((month) => (
                          <div key={month.monthKey} className="financial-month-container">
                            <div
                              className="financial-month-header"
                              onClick={() => setExpandedFinancialMonths(prev => ({
                                ...prev,
                                [month.monthKey]: !prev[month.monthKey]
                              }))}
                            >
                              <span className="expand-icon">{expandedFinancialMonths[month.monthKey] ? '▼' : '▶'}</span>
                              <span className="month-label">{month.monthLabel}</span>
                              <span className="month-count">{month.bookingCount} bookings</span>
                              <span className="month-gross">Gross: {month.totalGross}</span>
                              <span className="month-discount">Discounts: {month.totalDiscount}</span>
                              <span className="month-net">Paid: {month.totalNet}</span>
                              <span className="month-refunds">Refunds: {month.totalRefunds}</span>
                              <span className="month-revenue">Revenue: {month.totalRevenue}</span>
                            </div>
                            {expandedFinancialMonths[month.monthKey] && (
                              <div className="financial-month-bookings">
                                <table className="admin-table financial-table financial-table-compact">
                                  <thead>
                                    <tr>
                                      <th style={{ width: '70px' }}>Date</th>
                                      <th style={{ width: '100px' }}>Ref</th>
                                      <th style={{ width: '120px' }}>Customer</th>
                                      <th style={{ width: '40px' }}>Days</th>
                                      <th style={{ width: '60px' }}>Gross</th>
                                      <th style={{ width: '100px' }}>Promo</th>
                                      <th style={{ width: '70px' }}>Discount</th>
                                      <th style={{ width: '60px' }}>Paid</th>
                                      <th style={{ width: '60px' }}>Refund</th>
                                      <th style={{ width: '60px' }}>Revenue</th>
                                      <th style={{ width: '70px' }}>Status</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {month.bookings.map((booking) => (
                                      <tr key={booking.id} className={booking.needsOverride ? 'needs-override' : ''}>
                                        <td>{booking.paidDate}</td>
                                        <td>{booking.reference}</td>
                                        <td>{booking.customerName}</td>
                                        <td>{booking.tripDays || '-'}</td>
                                        {/* Gross column - editable if needs override */}
                                        <td>
                                          {editingFinancialBooking?.id === booking.id ? (
                                            <input
                                              type="number"
                                              step="0.01"
                                              min="0"
                                              className="financial-edit-input"
                                              value={editingFinancialBooking.gross}
                                              onChange={(e) => setEditingFinancialBooking({
                                                ...editingFinancialBooking,
                                                gross: e.target.value
                                              })}
                                              placeholder="0.00"
                                            />
                                          ) : (
                                            <>
                                              {booking.grossPrice}
                                              {booking.hasOverride && <span className="override-indicator" title="Manual override">*</span>}
                                            </>
                                          )}
                                        </td>
                                        <td>
                                          <span className="financial-promo-cell">
                                            {editingFinancialBooking?.id === booking.id ? (
                                              <input
                                                type="text"
                                                className="financial-edit-input"
                                                value={editingFinancialBooking.promo}
                                                onChange={(e) => setEditingFinancialBooking({
                                                  ...editingFinancialBooking,
                                                  promo: e.target.value
                                                })}
                                                placeholder="Promo code"
                                                title="Promotions-system code — clear to remove attribution"
                                              />
                                            ) : (
                                              <span className="financial-promo-text">
                                                {booking.promoCode || '-'}
                                              </span>
                                            )}
                                            {(booking.canEditFinancials ?? booking.needsOverride) && editingFinancialBooking?.id !== booking.id && (
                                              <button
                                                className="edit-btn-inline"
                                                onClick={() => setEditingFinancialBooking({
                                                  id: booking.id,
                                                  gross: booking.grossPence ? (booking.grossPence / 100).toFixed(2) : '',
                                                  discount: booking.discountPence ? (booking.discountPence / 100).toFixed(2) : '',
                                                  initialGrossPence: booking.grossPence || 0,
                                                  initialDiscountPence: booking.discountPence || 0,
                                                  promo: booking.promoCode || '',
                                                  initialPromo: booking.promoCode || '',
                                                  refund: '',
                                                })}
                                                title="Edit financial values"
                                              >
                                                ✎ Edit
                                              </button>
                                            )}
                                          </span>
                                        </td>
                                        {/* Discount column - editable if in edit mode */}
                                        <td style={{ color: booking.discountAmount ? '#f59e0b' : 'inherit' }}>
                                          {editingFinancialBooking?.id === booking.id ? (
                                            <input
                                              type="number"
                                              step="0.01"
                                              min="0"
                                              className="financial-edit-input"
                                              value={editingFinancialBooking.discount}
                                              onChange={(e) => setEditingFinancialBooking({
                                                ...editingFinancialBooking,
                                                discount: e.target.value
                                              })}
                                              placeholder="0.00"
                                            />
                                          ) : (
                                            booking.discountAmount || '-'
                                          )}
                                        </td>
                                        <td>{booking.netPrice}</td>
                                        <td style={{ color: booking.refundAmount ? '#ef4444' : 'inherit' }}>
                                          {editingFinancialBooking?.id === booking.id ? (
                                            <input
                                              type="text"
                                              className="financial-edit-input"
                                              value={editingFinancialBooking.refund}
                                              onChange={(e) => setEditingFinancialBooking({
                                                ...editingFinancialBooking,
                                                refund: e.target.value
                                              })}
                                              placeholder="re_… / £"
                                              title="Paste a Stripe refund id (re_…) or payment intent (pi_…) to sync from Stripe, or type a refund amount in pounds"
                                            />
                                          ) : (
                                            <>
                                              {booking.refundAmount || '-'}
                                              {/* Payment-state tag: booking status alone hides refund
                                                  state (a completed trip can carry a partial refund) */}
                                              {booking.paymentStatus === 'partially_refunded' && (
                                                <span style={{ display: 'block', fontSize: '10px', color: '#f59e0b' }}>
                                                  Partial refund
                                                </span>
                                              )}
                                              {booking.paymentStatus === 'refunded' && (
                                                <span style={{ display: 'block', fontSize: '10px', color: '#ef4444' }}>
                                                  Refunded
                                                </span>
                                              )}
                                            </>
                                          )}
                                        </td>
                                        <td style={{ color: '#22c55e' }}>{booking.netRevenue}</td>
                                        <td>
                                          {editingFinancialBooking?.id === booking.id ? (
                                            <div className="edit-actions">
                                              <button
                                                className="save-btn-inline"
                                                onClick={() => saveFinancialOverride(booking.id, editingFinancialBooking)}
                                                disabled={savingFinancialOverride || !editingFinancialBooking.gross}
                                                title="Save"
                                              >
                                                {savingFinancialOverride ? '...' : '✓'}
                                              </button>
                                              <button
                                                className="cancel-btn-inline"
                                                onClick={() => setEditingFinancialBooking(null)}
                                                title="Cancel"
                                              >
                                                ✕
                                              </button>
                                              {editingFinancialBooking.error && (
                                                <span
                                                  className="financial-edit-error"
                                                  style={{ color: '#ef4444', fontSize: '11px', display: 'block' }}
                                                  title={editingFinancialBooking.error}
                                                >
                                                  {editingFinancialBooking.error}
                                                </span>
                                              )}
                                            </div>
                                          ) : (
                                            <span className={`status-badge status-${booking.status}`}>
                                              {booking.status}
                                            </span>
                                          )}
                                        </td>
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
                  </>
                ) : (
                  <p className="admin-empty">Click "Refresh Page" to load financial data.</p>
                )}
              </>
            )}

            {/* Session Tracking Report */}
            {reportsSubTab === 'sessions' && (
              <>
                <div className="reports-section-header">
                  <div className="period-selector">
                    <button
                      className={`period-btn ${sessionTrackingPeriod === 'daily' ? 'active' : ''}`}
                      onClick={() => setSessionTrackingPeriod('daily')}
                    >
                      Daily
                    </button>
                    <button
                      className={`period-btn ${sessionTrackingPeriod === 'weekly' ? 'active' : ''}`}
                      onClick={() => setSessionTrackingPeriod('weekly')}
                    >
                      Weekly
                    </button>
                    <button
                      className={`period-btn ${sessionTrackingPeriod === 'monthly' ? 'active' : ''}`}
                      onClick={() => setSessionTrackingPeriod('monthly')}
                    >
                      Monthly
                    </button>
                  </div>
                  <button
                    className="refresh-page-btn"
                    onClick={() => fetchSessionTracking(sessionTrackingPeriod, true)}
                    disabled={loadingSessionTracking}
                  >
                    {loadingSessionTracking ? 'Refreshing...' : 'Refresh Page'}
                  </button>
                </div>

                {loadingSessionTracking ? (
                  <div className="admin-loading-inline">
                    <div className="spinner-small"></div>
                    <span>Loading session tracking data...</span>
                  </div>
                ) : sessionTrackingData ? (
                  <>
                    {/* Cumulative Funnel Summary */}
                    <div className="session-funnel-summary">
                      <h3>Booking Funnel (Cumulative)</h3>
                      <div className="funnel-cards">
                        {sessionTrackingData.stages?.map((stage, index) => {
                          const count = sessionTrackingData.cumulative?.counts?.[stage.key] || 0
                          const conversionRate = sessionTrackingData.cumulative?.conversion_rates?.[stage.key] || 0
                          const prevCount = index > 0
                            ? sessionTrackingData.cumulative?.counts?.[sessionTrackingData.stages[index - 1].key] || 0
                            : count
                          const dropOff = index > 0 && prevCount > 0
                            ? prevCount - count
                            : 0

                          return (
                            <div key={stage.key} className="funnel-card">
                              <div className="funnel-card-header">
                                <span className="funnel-step">{index + 1}</span>
                                <span className="funnel-label">{stage.label}</span>
                              </div>
                              <div className="funnel-card-value">{count.toLocaleString()}</div>
                              {index > 0 && (
                                <div className="funnel-card-meta">
                                  <span className={`conversion-rate ${conversionRate >= 50 ? 'good' : conversionRate >= 25 ? 'medium' : 'poor'}`}>
                                    {conversionRate}% conversion
                                  </span>
                                  {dropOff > 0 && (
                                    <span className="drop-off">-{dropOff} dropped</span>
                                  )}
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                      <div className="overall-conversion">
                        <strong>Overall Conversion Rate:</strong>{' '}
                        <span className={`conversion-rate ${(sessionTrackingData.cumulative?.overall_conversion || 0) >= 10 ? 'good' : 'medium'}`}>
                          {sessionTrackingData.cumulative?.overall_conversion || 0}%
                        </span>
                        <span className="conversion-label">(Dates Selected → Booking Confirmed)</span>
                      </div>
                    </div>

                    {/* Period-by-Period Breakdown */}
                    <div className="session-period-table">
                      <h3>
                        {sessionTrackingPeriod === 'daily' && 'Daily Breakdown (Last 30 Days)'}
                        {sessionTrackingPeriod === 'weekly' && 'Weekly Breakdown (Last 12 Weeks)'}
                        {sessionTrackingPeriod === 'monthly' && 'Monthly Breakdown (Last 12 Months)'}
                      </h3>
                      {sessionTrackingData.periods?.length > 0 ? (
                        <table className="admin-table">
                          <thead>
                            <tr>
                              <th>Period</th>
                              {sessionTrackingData.stages?.map(stage => (
                                <th key={stage.key}>{stage.label}</th>
                              ))}
                              <th>Manual</th>
                              <th>Free</th>
                            </tr>
                          </thead>
                          <tbody>
                            {sessionTrackingData.periods?.slice().reverse().map(period => (
                              <tr key={period.period}>
                                <td><strong>{period.label}</strong></td>
                                {sessionTrackingData.stages?.map(stage => (
                                  <td key={stage.key}>
                                    {period.counts?.[stage.key] || 0}
                                  </td>
                                ))}
                                <td className="manual-booking-cell">
                                  {period.manual_bookings > 0 ? `+${period.manual_bookings}` : '-'}
                                </td>
                                <td className="free-booking-cell">
                                  {period.free_bookings > 0 ? `+${period.free_bookings}` : '-'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      ) : (
                        <p className="admin-empty">No session data available for this period.</p>
                      )}
                      {(sessionTrackingData.cumulative?.manual_bookings > 0 || sessionTrackingData.cumulative?.free_bookings > 0) && (
                        <p className="manual-bookings-note">
                          {sessionTrackingData.cumulative?.manual_bookings > 0 && (
                            <>* Manual: {sessionTrackingData.cumulative.manual_bookings} booking{sessionTrackingData.cumulative.manual_bookings !== 1 ? 's' : ''} via Admin (phone/walk-in). </>
                          )}
                          {sessionTrackingData.cumulative?.free_bookings > 0 && (
                            <>* Free: {sessionTrackingData.cumulative.free_bookings} booking{sessionTrackingData.cumulative.free_bookings !== 1 ? 's' : ''} with 100% promo code. </>
                          )}
                          These bypass the payment step.
                        </p>
                      )}
                    </div>
                  </>
                ) : (
                  <p className="admin-empty">Click "Refresh Page" to load session tracking data.</p>
                )}
              </>
            )}

            {/* Abandoned Carts Analytics */}
            {reportsSubTab === 'analytics' && (
              <>
                <div className="reports-section-header">
                  <div className="period-selector">
                    <button
                      className={`period-btn ${abandonedCartsPeriod === 'daily' ? 'active' : ''}`}
                      onClick={() => { setAbandonedCartsPeriod('daily'); fetchAbandonedCarts('daily'); }}
                    >
                      Daily
                    </button>
                    <button
                      className={`period-btn ${abandonedCartsPeriod === 'weekly' ? 'active' : ''}`}
                      onClick={() => { setAbandonedCartsPeriod('weekly'); fetchAbandonedCarts('weekly'); }}
                    >
                      Weekly
                    </button>
                    <button
                      className={`period-btn ${abandonedCartsPeriod === 'monthly' ? 'active' : ''}`}
                      onClick={() => { setAbandonedCartsPeriod('monthly'); fetchAbandonedCarts('monthly'); }}
                    >
                      Monthly
                    </button>
                  </div>
                  <button
                    className="refresh-page-btn"
                    onClick={() => fetchAbandonedCarts(abandonedCartsPeriod, true)}
                    disabled={loadingAbandonedCarts}
                  >
                    {loadingAbandonedCarts ? 'Refreshing...' : 'Refresh Data'}
                  </button>
                </div>

                {loadingAbandonedCarts ? (
                  <div className="admin-loading-inline">
                    <div className="spinner-small"></div>
                    <span>Loading abandoned carts data...</span>
                  </div>
                ) : abandonedCartsData ? (
                  <>
                    {/* Cumulative Summary */}
                    <div className="abandoned-carts-summary">
                      <div className="stats-summary-cards">
                        <div className="stats-card">
                          <div className="stats-card-value">{abandonedCartsData.cumulative?.total_abandoned || 0}</div>
                          <div className="stats-card-label">Total Abandoned</div>
                        </div>
                      </div>

                      {/* Top Destinations */}
                      <div className="abandoned-analytics-grid">
                        <div className="abandoned-analytics-card">
                          <h4>Top Destinations (Abandoned)</h4>
                          {abandonedCartsData.cumulative?.top_destinations?.length > 0 ? (
                            <table className="admin-table compact">
                              <thead>
                                <tr>
                                  <th>Destination</th>
                                  <th>Count</th>
                                </tr>
                              </thead>
                              <tbody>
                                {abandonedCartsData.cumulative.top_destinations.map((item, idx) => (
                                  <tr key={idx}>
                                    <td>{item.destination}</td>
                                    <td>{item.count}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          ) : (
                            <p className="admin-empty">No destination data</p>
                          )}
                        </div>

                        <div className="abandoned-analytics-card">
                          <h4>Top Trip Lengths (Abandoned)</h4>
                          {abandonedCartsData.cumulative?.top_days?.length > 0 ? (
                            <table className="admin-table compact">
                              <thead>
                                <tr>
                                  <th>Days</th>
                                  <th>Count</th>
                                </tr>
                              </thead>
                              <tbody>
                                {abandonedCartsData.cumulative.top_days.map((item, idx) => (
                                  <tr key={idx}>
                                    <td>{item.days} days</td>
                                    <td>{item.count}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          ) : (
                            <p className="admin-empty">No trip length data</p>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Period-by-Period Breakdown */}
                    <div className="abandoned-period-table">
                      <h3>
                        {abandonedCartsPeriod === 'daily' && 'Daily Breakdown'}
                        {abandonedCartsPeriod === 'weekly' && 'Weekly Breakdown'}
                        {abandonedCartsPeriod === 'monthly' && 'Monthly Breakdown'}
                      </h3>
                      {abandonedCartsData.periods?.length > 0 ? (
                        <table className="admin-table">
                          <thead>
                            <tr>
                              <th>Period</th>
                              <th>Abandoned Sessions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {abandonedCartsData.periods?.slice().reverse().map(period => (
                              <tr key={period.period}>
                                <td><strong>{period.label}</strong></td>
                                <td>{period.abandoned_count}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      ) : (
                        <p className="admin-empty">No abandoned cart data available for this period.</p>
                      )}
                    </div>

                    {/* Recent Abandoned Carts */}
                    <div className="abandoned-recent-table">
                      <h3>Recent Abandoned Carts (with flight details)</h3>
                      {abandonedCartsData.recent_abandoned?.length > 0 ? (
                        <div className="sql-results-table-wrapper">
                          <table className="admin-table">
                            <thead>
                              <tr>
                                <th>Date/Time</th>
                                <th>Drop-off</th>
                                <th>Departure</th>
                                <th>Pick-up</th>
                                <th>Arrival</th>
                                <th>Destination</th>
                                <th>Days</th>
                                <th>Airline</th>
                              </tr>
                            </thead>
                            <tbody>
                              {abandonedCartsData.recent_abandoned.map((item, idx) => (
                                <tr key={idx}>
                                  <td>{new Date(item.created_at).toLocaleString('en-GB', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/London' })}</td>
                                  <td>{item.dropoff_date}</td>
                                  <td>{item.departure_time}</td>
                                  <td>{item.pickup_date}</td>
                                  <td>{item.arrival_time}</td>
                                  <td>{item.destination}</td>
                                  <td>{item.days}</td>
                                  <td>{item.airline}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className="admin-empty">No recent abandoned carts with flight details.</p>
                      )}
                    </div>
                  </>
                ) : (
                  <p className="admin-empty">Click "Refresh Page" to load abandoned carts data.</p>
                )}
              </>
            )}

            {/* Bookings Forecast */}
            {reportsSubTab === 'forecast' && (
              <>
                <div className="forecast-header">
                  <button
                    className="admin-refresh"
                    onClick={() => fetchBookingsForecast(true)}
                    disabled={loadingForecast}
                  >
                    {loadingForecast ? 'Loading...' : 'Refresh'}
                  </button>
                </div>

                {loadingForecast ? (
                  <div className="admin-loading-inline">
                    <div className="spinner-small"></div>
                    <span>Loading forecast data...</span>
                  </div>
                ) : forecastData ? (
                  <>
                    {/* Data Range Info */}
                    <div className="forecast-info">
                      <p>Based on <strong>{forecastData.data_range?.total_bookings_analyzed || 0}</strong> bookings (last 6 months) and <strong>{forecastData.data_range?.total_abandoned_sessions || 0}</strong> abandoned searches (last 30 days)</p>
                    </div>

                    {/* Multi-Model Destination Predictions */}
                    <div className="forecast-section full-width">
                      <h4>Destination Predictions (3 Models)</h4>
                      <p className="forecast-subtitle">
                        <strong>Balanced:</strong> 60% bookings + 40% searches |
                        <strong> Momentum:</strong> 30% bookings + 70% searches (emerging trends) |
                        <strong> Established:</strong> 80% bookings + 20% searches (proven demand)
                      </p>
                      {forecastData.destinations?.length > 0 ? (
                        <table className="forecast-table multi-model">
                          <thead>
                            <tr>
                              <th>Destination</th>
                              <th>Bookings</th>
                              <th>Searches</th>
                              <th>Balanced</th>
                              <th>Momentum</th>
                              <th>Established</th>
                              <th>Confidence</th>
                              <th>Trend</th>
                              <th>Best Day</th>
                            </tr>
                          </thead>
                          <tbody>
                            {forecastData.destinations.slice(0, 15).map((item, idx) => (
                              <tr key={idx} className={item.status === 'high_demand' ? 'row-highlight' : ''}>
                                <td><strong>{item.destination}</strong></td>
                                <td>{item.bookings_6m}</td>
                                <td>{item.searches_30d}</td>
                                <td>
                                  <span className={`model-score balanced ${item.status}`}>
                                    {item.score_balanced}
                                  </span>
                                </td>
                                <td>
                                  <span className={`model-score momentum ${item.score_momentum > item.score_balanced ? 'higher' : ''}`}>
                                    {item.score_momentum}
                                  </span>
                                </td>
                                <td>
                                  <span className={`model-score established ${item.score_established > item.score_balanced ? 'higher' : ''}`}>
                                    {item.score_established}
                                  </span>
                                </td>
                                <td>
                                  <span className={`confidence-badge ${item.confidence}`}>
                                    {item.confidence_icon}
                                  </span>
                                </td>
                                <td>
                                  <span className={`trend-badge ${item.trend}`}>
                                    {item.trend === 'rising' ? '📈' : item.trend === 'stable' ? '📊' : '➖'}
                                  </span>
                                </td>
                                <td>{item.best_day || '-'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      ) : (
                        <p className="admin-empty">No destination data available</p>
                      )}
                      <div className="model-legend">
                        <span><strong>Confidence:</strong> ✓✓✓ High (models agree) | ✓✓ Medium | ⚠️ Low (investigate)</span>
                        <span><strong>Trend:</strong> 📈 Rising (momentum {'>'} established) | 📊 Stable | ➖ Neutral</span>
                      </div>
                    </div>

                    {/* Summary Cards */}
                    <div className="forecast-grid">

                      {/* Day of Week Analysis - Drop-offs */}
                      <div className="forecast-card">
                        <h4>Busiest Days of Week</h4>
                        <p className="forecast-subtitle">When do customers drop off?</p>
                        {forecastData.day_of_week?.length > 0 ? (
                          <div className="dow-chart">
                            {forecastData.day_of_week.map((day, idx) => (
                              <div key={idx} className="dow-bar-container">
                                <span className="dow-label">{day.day_short}</span>
                                <div className="dow-bar-wrapper">
                                  <div
                                    className="dow-bar"
                                    style={{ width: `${Math.min(day.percentage * 5, 100)}%` }}
                                  ></div>
                                </div>
                                <span className="dow-value">{day.bookings} ({day.percentage}%)</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="admin-empty">No day-of-week data available</p>
                        )}
                      </div>

                      {/* Day of Week Analysis - Pick-ups */}
                      <div className="forecast-card">
                        <h4>Busiest Pickup Days</h4>
                        <p className="forecast-subtitle">When do customers pick up?</p>
                        {forecastData.pickup_day_of_week?.length > 0 ? (
                          <div className="dow-chart">
                            {forecastData.pickup_day_of_week.map((day, idx) => (
                              <div key={idx} className="dow-bar-container">
                                <span className="dow-label">{day.day_short}</span>
                                <div className="dow-bar-wrapper">
                                  <div
                                    className="dow-bar pickup"
                                    style={{ width: `${Math.min(day.percentage * 5, 100)}%` }}
                                  ></div>
                                </div>
                                <span className="dow-value">{day.bookings} ({day.percentage}%)</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="admin-empty">No pickup day data available</p>
                        )}
                      </div>

                      {/* Combined Seasonality - Booking, Travel & Abandoned Month */}
                      <div className="forecast-card wide">
                        <h4>Monthly Patterns</h4>
                        <p className="forecast-subtitle">Booked (green) · Traveled (blue) · Abandoned (red)</p>
                        {forecastData.seasonality_travel?.length > 0 ? (
                          <div className="monthly-patterns-chart">
                            {(() => {
                              const maxTravel = Math.max(...forecastData.seasonality_travel.map(m => m.bookings)) || 1;
                              const maxBooking = Math.max(...(forecastData.seasonality_booking || []).map(m => m.bookings)) || 1;
                              const maxAbandoned = Math.max(...(forecastData.seasonality_abandoned || []).map(m => m.count)) || 1;
                              const maxAll = Math.max(maxTravel, maxBooking, maxAbandoned);
                              return forecastData.seasonality_travel.map((travelMonth, idx) => {
                                const bookingMonth = forecastData.seasonality_booking?.[idx] || { bookings: 0 };
                                const abandonedMonth = forecastData.seasonality_abandoned?.[idx] || { count: 0 };
                                return (
                                  <div key={idx} className="monthly-column">
                                    <div className="monthly-bars">
                                      <div className="monthly-bar-group">
                                        <div
                                          className="monthly-bar booking"
                                          style={{ height: `${(bookingMonth.bookings / maxAll) * 100}%` }}
                                          title={`Booked: ${bookingMonth.bookings}`}
                                        ></div>
                                        <div
                                          className="monthly-bar travel"
                                          style={{ height: `${(travelMonth.bookings / maxAll) * 100}%` }}
                                          title={`Traveled: ${travelMonth.bookings}`}
                                        ></div>
                                        <div
                                          className="monthly-bar abandoned"
                                          style={{ height: `${(abandonedMonth.count / maxAll) * 100}%` }}
                                          title={`Abandoned: ${abandonedMonth.count}`}
                                        ></div>
                                      </div>
                                    </div>
                                    <span className="monthly-label">{travelMonth.month}</span>
                                  </div>
                                );
                              });
                            })()}
                            <div className="combined-legend">
                              <span className="legend-item"><span className="legend-color booking"></span> Booked</span>
                              <span className="legend-item"><span className="legend-color travel"></span> Traveled</span>
                              <span className="legend-item"><span className="legend-color abandoned"></span> Abandoned</span>
                            </div>
                          </div>
                        ) : (
                          <p className="admin-empty">No data available</p>
                        )}
                      </div>

                      {/* Departure Times */}
                      <div className="forecast-card">
                        <h4>Departure Times</h4>
                        <p className="forecast-subtitle">Most popular flight departure times</p>
                        {forecastData.departure_times?.length > 0 ? (
                          <div className="departure-time-chart">
                            {(() => {
                              const maxBookings = Math.max(...forecastData.departure_times.map(t => t.bookings)) || 1;
                              return forecastData.departure_times.map((slot, idx) => (
                                <div key={idx} className="time-bar-container">
                                  <span className="time-label">{slot.time}</span>
                                  <div className="time-bar-wrapper">
                                    <div
                                      className="time-bar"
                                      style={{ width: `${(slot.bookings / maxBookings) * 100}%` }}
                                    ></div>
                                  </div>
                                  <span className="time-value">{slot.bookings}</span>
                                </div>
                              ));
                            })()}
                          </div>
                        ) : (
                          <p className="admin-empty">No departure time data available</p>
                        )}
                      </div>

                      {/* Arrival Times */}
                      <div className="forecast-card">
                        <h4>Arrival Times</h4>
                        <p className="forecast-subtitle">Most popular flight arrival times</p>
                        {forecastData.arrival_times?.length > 0 ? (
                          <div className="departure-time-chart">
                            {(() => {
                              const maxBookings = Math.max(...forecastData.arrival_times.map(t => t.bookings)) || 1;
                              return forecastData.arrival_times.map((slot, idx) => (
                                <div key={idx} className="time-bar-container">
                                  <span className="time-label">{slot.time}</span>
                                  <div className="time-bar-wrapper">
                                    <div
                                      className="time-bar arrival"
                                      style={{ width: `${(slot.bookings / maxBookings) * 100}%` }}
                                    ></div>
                                  </div>
                                  <span className="time-value">{slot.bookings}</span>
                                </div>
                              ));
                            })()}
                          </div>
                        ) : (
                          <p className="admin-empty">No arrival time data available</p>
                        )}
                      </div>

                      {/* Top Airlines */}
                      <div className="forecast-card">
                        <h4>Top Airlines</h4>
                        <p className="forecast-subtitle">Most popular carriers</p>
                        {forecastData.airlines?.length > 0 ? (
                          <table className="forecast-table compact">
                            <thead>
                              <tr>
                                <th>Airline</th>
                                <th>Bookings</th>
                                <th>Searches</th>
                                <th>%</th>
                              </tr>
                            </thead>
                            <tbody>
                              {forecastData.airlines.map((item, idx) => (
                                <tr key={idx}>
                                  <td>{item.airline}</td>
                                  <td>{item.bookings_6m}</td>
                                  <td>{item.searches_30d}</td>
                                  <td>{item.percentage}%</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        ) : (
                          <p className="admin-empty">No airline data available</p>
                        )}
                      </div>
                    </div>

                    {/* Predicted Dates */}
                    {forecastData.predicted_dates?.length > 0 && (
                      <div className="forecast-section">
                        <h4>Predicted Busy Dates</h4>
                        <p className="forecast-subtitle">Next 30 days ranked by likelihood of bookings</p>
                        <div className="predicted-dates-grid">
                          {forecastData.predicted_dates.slice(0, 10).map((item, idx) => (
                            <div key={idx} className={`predicted-date-card ${item.likelihood}`}>
                              <div className="predicted-date">{item.display_date}</div>
                              <div className="predicted-day">{item.day_of_week}</div>
                              <div className="predicted-score">Score: {item.prediction_score}</div>
                              {item.searches > 0 && (
                                <div className="predicted-searches">{item.searches} active searches</div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Opportunity Gaps */}
                    {forecastData.opportunity_gaps?.length > 0 && (
                      <div className="forecast-section">
                        <h4>Opportunity Gaps</h4>
                        <p className="forecast-subtitle">High search interest but low conversion - potential untapped demand</p>
                        <table className="forecast-table">
                          <thead>
                            <tr>
                              <th>Destination</th>
                              <th>Searches (30d)</th>
                              <th>Bookings (6m)</th>
                              <th>Gap Score</th>
                            </tr>
                          </thead>
                          <tbody>
                            {forecastData.opportunity_gaps.map((item, idx) => (
                              <tr key={idx}>
                                <td><strong>{item.destination}</strong></td>
                                <td>{item.searches}</td>
                                <td>{item.bookings}</td>
                                <td>
                                  <span className="opportunity-score">{item.gap_score.toFixed(1)}</span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {/* Upcoming Demand */}
                    {forecastData.upcoming_demand?.length > 0 && (
                      <div className="forecast-section">
                        <h4>Upcoming Dates with Search Interest</h4>
                        <p className="forecast-subtitle">Dates people are searching for in the next 30 days</p>
                        <div className="upcoming-demand-grid">
                          {forecastData.upcoming_demand.map((item, idx) => (
                            <div key={idx} className="upcoming-demand-card">
                              <div className="upcoming-date">{item.display_date}</div>
                              <div className="upcoming-day">{item.day_of_week}</div>
                              <div className="upcoming-searches">{item.searches} searches</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <p className="admin-empty">No forecast data available. Click Refresh to load.</p>
                )}
              </>
            )}
          </div>
        )}

        {/* QA - Test Results */}
        {activeTab === 'qa-tests' && (
          <TestResultsSection
            loadingTestResults={loadingTestResults}
            fetchTestResults={fetchTestResults}
            latestTestRun={latestTestRun}
            testResults={testResults}
          />
        )}

        {/* QA - Connection Pool */}
        {activeTab === 'qa-connection-pool' && (
          <ConnectionPoolSection
            loadingDbHealth={loadingDbHealth}
            loadingPoolHistory={loadingPoolHistory}
            fetchDbHealth={fetchDbHealth}
            fetchDbPoolHistory={fetchDbPoolHistory}
            dbHealth={dbHealth}
            dbPoolHistory={dbPoolHistory}
          />
        )}

        {/* QA - Audit Logs */}
        {activeTab === 'qa-audit' && (
          <AuditLogsSection
            auditLogs={auditLogs}
            loadingAuditLogs={loadingAuditLogs}
            fetchAuditLogs={fetchAuditLogs}
            auditLogsTotalCount={auditLogsTotalCount}
            auditLogsFilters={auditLogsFilters}
            setAuditLogsFilters={setAuditLogsFilters}
            auditEventTypes={auditEventTypes}
            auditLogsAutoRefresh={auditLogsAutoRefresh}
            setAuditLogsAutoRefresh={setAuditLogsAutoRefresh}
            expandedAuditLog={expandedAuditLog}
            setExpandedAuditLog={setExpandedAuditLog}
            auditLogsOffset={auditLogsOffset}
            setAuditLogsOffset={setAuditLogsOffset}
          />
        )}


        {/* QA - Error Logs */}
        {activeTab === 'qa-errors' && (
          <ErrorLogsSection
            errorLogs={errorLogs}
            loadingErrorLogs={loadingErrorLogs}
            errorLogsTotalCount={errorLogsTotalCount}
            fetchErrorLogs={fetchErrorLogs}
            errorLogsFilters={errorLogsFilters}
            setErrorLogsFilters={setErrorLogsFilters}
            errorSeverities={errorSeverities}
            errorTypes={errorTypes}
            expandedErrorLog={expandedErrorLog}
            setExpandedErrorLog={setExpandedErrorLog}
            errorLogsOffset={errorLogsOffset}
            setErrorLogsOffset={setErrorLogsOffset}
          />
        )}

        {/* QA - SQL Interface */}
        {activeTab === 'qa-sql' && (
          <SqlInterfaceSection
            sqlSessionToken={sqlSessionToken}
            sqlSessionExpires={sqlSessionExpires}
            logoutSqlSession={logoutSqlSession}
            sqlPinModalOpen={sqlPinModalOpen}
            setSqlPinModalOpen={setSqlPinModalOpen}
            sqlPin={sqlPin}
            setSqlPin={setSqlPin}
            verifySqlPin={verifySqlPin}
            sqlPinError={sqlPinError}
            sqlQuery={sqlQuery}
            setSqlQuery={setSqlQuery}
            executeSqlQuery={executeSqlQuery}
            sqlLoading={sqlLoading}
            sqlError={sqlError}
            setSqlError={setSqlError}
            sqlResults={sqlResults}
            setSqlResults={setSqlResults}
            exportSqlResultsCSV={exportSqlResultsCSV}
            exportSqlResultsPDF={exportSqlResultsPDF}
            sqlHistory={sqlHistory}
            sqlTemplates={sqlTemplates}
            sqlTemplatesExpanded={sqlTemplatesExpanded}
            setSqlTemplatesExpanded={setSqlTemplatesExpanded}
          />
        )}

        {/* QA - Roster Planner (shadow mode, read-only) */}
        {activeTab === 'qa-roster-planner' && (
          <RosterPlannerSection apiUrl={API_URL} token={token} />
        )}

        {/* Testimonials Section */}
        {activeTab === 'testimonials' && (
          <TestimonialsSection
            testimonials={testimonials}
            loadingTestimonials={loadingTestimonials}
            fetchTestimonials={fetchTestimonials}
            testimonialSuccessMessage={testimonialSuccessMessage}
            testimonialFilter={testimonialFilter}
            setTestimonialFilter={setTestimonialFilter}
            testimonialSort={testimonialSort}
            setTestimonialSort={setTestimonialSort}
            openAddTestimonialModal={openAddTestimonialModal}
            renderStars={renderStars}
            openEditTestimonialModal={openEditTestimonialModal}
            handleToggleTestimonialStatus={handleToggleTestimonialStatus}
            setTestimonialToDelete={setTestimonialToDelete}
            setShowDeleteTestimonialModal={setShowDeleteTestimonialModal}
          />
        )}

        {/* Promo Modals Section */}
        {activeTab === 'promo-modals' && (
          <PromoModalsSection
            promoModals={promoModals}
            loadingPromoModals={loadingPromoModals}
            fetchPromoModals={fetchPromoModals}
            promoModalSuccessMessage={promoModalSuccessMessage}
            setEditingPromoModal={setEditingPromoModal}
            setPromoModalForm={setPromoModalForm}
            setPromoCodeIsMultiUse={setPromoCodeIsMultiUse}
            setSelectedPromoCodeInfo={setSelectedPromoCodeInfo}
            setShowPromoModalForm={setShowPromoModalForm}
            fetchPromoCodesForModal={fetchPromoCodesForModal}
            openEditPromoModal={openEditPromoModal}
            handleTogglePromoModalStatus={handleTogglePromoModalStatus}
            setPromoModalToDelete={setPromoModalToDelete}
            setShowDeletePromoModal={setShowDeletePromoModal}
          />
        )}

        {activeTab === 'bookings' && bookingsScrollTopVisible && (
          <button
            type="button"
            className="bookings-scroll-top"
            onClick={() => window.scrollTo({ top: 0, behavior: 'auto' })}
            aria-label="Scroll to top"
            title="Back to top"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
              <path d="M17 14l-5-5-5 5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"></path>
            </svg>
          </button>
        )}

        </main>
      </div>

      {/* Promo Modal Add/Edit Modal */}
      {showPromoModalForm && (
        <div className="modal-overlay" onClick={() => setShowPromoModalForm(false)}>
          <div className="modal-content modal-content-wide" onClick={(e) => e.stopPropagation()}>
            <h3>{editingPromoModal ? `Edit ${promoModalForm.type === 'promo_section' ? 'Promo Section' : 'Info Modal'}` : `Add ${promoModalForm.type === 'promo_section' ? 'Promo Section' : 'Info Modal'}`}</h3>

            <div className="modal-form">
              {/* Common Settings */}
              <div style={{ background: '#f8f9fa', padding: '1rem', borderRadius: '8px', marginBottom: '1.5rem' }}>
                <h4 style={{ margin: '0 0 1rem 0', color: '#343434', fontSize: '1rem', borderBottom: '2px solid #d9ff00', paddingBottom: '0.5rem' }}>
                  {promoModalForm.type === 'promo_section' ? 'Promo Section Settings' : 'Info Modal Settings'}
                </h4>
                <p style={{ fontSize: '0.85rem', color: '#666', margin: '0 0 1rem 0' }}>
                  {promoModalForm.type === 'promo_section'
                    ? 'This appears as a section on the homepage with a copyable promo code'
                    : 'This appears as a popup when users first visit the site'}
                </p>

              <div className="form-group">
                <label>Title *</label>
                <input
                  type="text"
                  value={promoModalForm.title}
                  onChange={(e) => setPromoModalForm({ ...promoModalForm, title: e.target.value })}
                  placeholder="e.g. Spring Sale!"
                  maxLength={100}
                />
              </div>

              <div className="form-group">
                <label>Message *</label>
                <textarea
                  value={promoModalForm.message}
                  onChange={(e) => setPromoModalForm({ ...promoModalForm, message: e.target.value })}
                  placeholder="Enter the promotional message..."
                  rows={4}
                />
              </div>

              {/* Button fields - Info Modal only */}
              {promoModalForm.type === 'info_modal' && (
                <>
                  <div className="form-row">
                    <div className="form-group">
                      <label>Button Text</label>
                      <input
                        type="text"
                        value={promoModalForm.button_text}
                        onChange={(e) => setPromoModalForm({ ...promoModalForm, button_text: e.target.value })}
                        placeholder="Subscribe"
                      />
                    </div>

                    <div className="form-group">
                      <label>Button Action</label>
                      <select
                        value={promoModalForm.button_action}
                        onChange={(e) => setPromoModalForm({ ...promoModalForm, button_action: e.target.value })}
                      >
                        <option value="promotions">Scroll to Promotions</option>
                        <option value="subscribe">Scroll to Subscribe</option>
                        <option value="link">Open Link</option>
                        <option value="close">Just Close</option>
                      </select>
                    </div>
                  </div>

                  {promoModalForm.button_action === 'link' && (
                    <div className="form-group">
                      <label>Button Link</label>
                      <input
                        type="url"
                        value={promoModalForm.button_link}
                        onChange={(e) => setPromoModalForm({ ...promoModalForm, button_link: e.target.value })}
                        placeholder="https://..."
                      />
                    </div>
                  )}
                </>
              )}

              {/* Promo Code - Promo Section only */}
              {promoModalForm.type === 'promo_section' && (
                <div className="form-group">
                  <label>Promo Code *</label>
                  <select
                    value={promoModalForm.promo_code}
                    onChange={(e) => {
                      const selectedCode = e.target.value
                      setPromoModalForm({ ...promoModalForm, promo_code: selectedCode })
                      const codeInfo = promoCodesForModal.find(c => c.code === selectedCode)
                      setSelectedPromoCodeInfo(codeInfo || null)
                      setPromoCodeIsMultiUse(codeInfo?.is_multi_use || false)
                    }}
                    style={{ width: '100%', padding: '0.5rem' }}
                  >
                    <option value="">-- Select a promo code --</option>
                    {loadingPromoCodesForModal ? (
                      <option disabled>Loading...</option>
                    ) : (
                      [...new Set(promoCodesForModal.map(c => c.promotion_name))].map(promoName => (
                        <optgroup key={promoName} label={promoName}>
                          {promoCodesForModal
                            .filter(c => c.promotion_name === promoName)
                            .map(c => (
                              <option key={c.id} value={c.code}>
                                {c.code} ({c.promotion_discount}% off{c.is_multi_use ? ', multi-use' : ''}{c.is_used && !c.is_multi_use ? ', USED' : ''})
                              </option>
                            ))
                          }
                        </optgroup>
                      ))
                    )}
                  </select>
                  {selectedPromoCodeInfo && (
                    <small style={{ color: selectedPromoCodeInfo.is_multi_use ? '#16a34a' : '#666', fontSize: '0.8rem', display: 'block', marginTop: '0.25rem' }}>
                      {selectedPromoCodeInfo.is_multi_use
                        ? `Multi-use code (${selectedPromoCodeInfo.use_count || 0} uses) - section expires by end date`
                        : selectedPromoCodeInfo.is_used
                          ? 'This code has already been used'
                          : 'Single-use code - section hides when used'
                      }
                    </small>
                  )}
                </div>
              )}
              </div>

              {/* Date & Status Settings */}
              <div style={{ background: '#f8f9fa', padding: '1rem', borderRadius: '8px', marginBottom: '1.5rem' }}>
                <h4 style={{ margin: '0 0 1rem 0', color: '#343434', fontSize: '1rem', borderBottom: '2px solid #d9ff00', paddingBottom: '0.5rem' }}>
                  Schedule & Status
                </h4>

              <div className="form-row">
                <div className="form-group">
                  <label>Start Date</label>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <input
                      type="text"
                      value={promoModalForm.start_date}
                      onChange={(e) => setPromoModalForm({ ...promoModalForm, start_date: formatDateInput(e.target.value) })}
                      placeholder="DD/MM/YYYY"
                      maxLength={10}
                      style={{ width: '125px' }}
                    />
                    <DatePicker
                      selected={parseUkDate(promoModalForm.start_date)}
                      onChange={(date) => setPromoModalForm({ ...promoModalForm, start_date: dateToUkString(date) })}
                      dateFormat="dd/MM/yyyy"
                      customInput={<button type="button" className="date-picker-btn">📅</button>}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label>End Date</label>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <input
                      type="text"
                      value={promoModalForm.end_date}
                      onChange={(e) => setPromoModalForm({ ...promoModalForm, end_date: formatDateInput(e.target.value) })}
                      placeholder="DD/MM/YYYY"
                      maxLength={10}
                      style={{ width: '125px' }}
                    />
                    <DatePicker
                      selected={parseUkDate(promoModalForm.end_date)}
                      onChange={(date) => setPromoModalForm({ ...promoModalForm, end_date: dateToUkString(date) })}
                      dateFormat="dd/MM/yyyy"
                      customInput={<button type="button" className="date-picker-btn">📅</button>}
                    />
                  </div>
                </div>
              </div>

              {/* Color fields - only for Info Modal type */}
              {promoModalForm.type === 'info_modal' && (
                <div className="form-row">
                  <div className="form-group">
                    <label>Background Color</label>
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <input
                        type="color"
                        value={promoModalForm.background_color}
                        onChange={(e) => setPromoModalForm({ ...promoModalForm, background_color: e.target.value })}
                        style={{ width: '50px', height: '35px', cursor: 'pointer' }}
                      />
                      <input
                        type="text"
                        value={promoModalForm.background_color}
                        onChange={(e) => setPromoModalForm({ ...promoModalForm, background_color: e.target.value })}
                        style={{ flex: 1 }}
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label>Text Color</label>
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <input
                        type="color"
                        value={promoModalForm.text_color}
                        onChange={(e) => setPromoModalForm({ ...promoModalForm, text_color: e.target.value })}
                        style={{ width: '50px', height: '35px', cursor: 'pointer' }}
                      />
                      <input
                        type="text"
                        value={promoModalForm.text_color}
                        onChange={(e) => setPromoModalForm({ ...promoModalForm, text_color: e.target.value })}
                        style={{ flex: 1 }}
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label>Button Color</label>
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <input
                        type="color"
                        value={promoModalForm.button_color}
                        onChange={(e) => setPromoModalForm({ ...promoModalForm, button_color: e.target.value })}
                        style={{ width: '50px', height: '35px', cursor: 'pointer' }}
                      />
                      <input
                        type="text"
                        value={promoModalForm.button_color}
                        onChange={(e) => setPromoModalForm({ ...promoModalForm, button_color: e.target.value })}
                        style={{ flex: 1 }}
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label>Button Text Color</label>
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <input
                        type="color"
                        value={promoModalForm.button_text_color}
                        onChange={(e) => setPromoModalForm({ ...promoModalForm, button_text_color: e.target.value })}
                        style={{ width: '50px', height: '35px', cursor: 'pointer' }}
                      />
                      <input
                        type="text"
                        value={promoModalForm.button_text_color}
                        onChange={(e) => setPromoModalForm({ ...promoModalForm, button_text_color: e.target.value })}
                        style={{ flex: 1 }}
                      />
                    </div>
                  </div>
                </div>
              )}

              <div className="form-row">
                <div className="form-group">
                  <label>Status</label>
                  <select
                    value={promoModalForm.status}
                    onChange={(e) => setPromoModalForm({ ...promoModalForm, status: e.target.value })}
                  >
                    <option value="inactive">Inactive (Draft)</option>
                    <option value="active">Active (Live)</option>
                    <option value="scheduled">Scheduled</option>
                  </select>
                </div>

                {/* Max Subscribers - Info Modal only */}
                {promoModalForm.type === 'info_modal' && (
                  <div className="form-group">
                    <label>Max Views</label>
                    <input
                      type="number"
                      min="1"
                      value={promoModalForm.max_subscribers}
                      onChange={(e) => setPromoModalForm({ ...promoModalForm, max_subscribers: e.target.value })}
                      placeholder="Leave empty for unlimited"
                    />
                    <small style={{ color: '#666', fontSize: '0.8rem' }}>
                      Auto-deactivates after this many views
                    </small>
                  </div>
                )}
              </div>
              </div>

              {/* Previews - show only the relevant preview based on type */}
              <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                {/* Info Modal Preview - only for info_modal type */}
                {promoModalForm.type === 'info_modal' && (
                  <div className="form-group" style={{ flex: '1', minWidth: '250px' }}>
                    <label>Info Modal Preview</label>
                    <div
                      style={{
                        backgroundColor: promoModalForm.background_color,
                        color: promoModalForm.text_color,
                        padding: '1.5rem',
                        borderRadius: '8px',
                        textAlign: 'center',
                      }}
                    >
                      <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '1.25rem' }}>{promoModalForm.title || 'Title'}</h4>
                      <p style={{ margin: '0 0 1rem 0', opacity: 0.9, whiteSpace: 'pre-line', fontSize: '0.9rem' }}>{promoModalForm.message || 'Your message here...'}</p>
                      <button
                        style={{
                          backgroundColor: promoModalForm.button_color,
                          color: promoModalForm.button_text_color,
                          border: 'none',
                          padding: '0.5rem 1.5rem',
                          borderRadius: '4px',
                          cursor: 'pointer',
                        }}
                      >
                        {promoModalForm.button_text || 'Subscribe'}
                      </button>
                    </div>
                  </div>
                )}

                {/* Promotions Section Preview - only for promo_section type */}
                {promoModalForm.type === 'promo_section' && (
                  <div className="form-group" style={{ flex: '1', minWidth: '300px' }}>
                    <label>Promotions Section Preview</label>
                    <div
                      style={{
                        backgroundColor: '#343434',
                        color: '#d9ff00',
                        padding: '1.5rem',
                        borderRadius: '8px',
                        textAlign: 'center',
                      }}
                    >
                      <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '1.1rem' }}>{promoModalForm.title || 'Title'}</h4>
                      {promoModalForm.message && (
                        <p style={{ margin: '0 0 1rem 0', opacity: 0.9, whiteSpace: 'pre-line', fontSize: '0.85rem' }}>{promoModalForm.message}</p>
                      )}
                      {promoModalForm.promo_code && (
                        <div style={{
                          backgroundColor: '#fff',
                          color: '#343434',
                          padding: '0.75rem 1rem',
                          borderRadius: '6px',
                          marginTop: '0.5rem',
                          border: '2px dashed #d9ff00'
                        }}>
                          <div style={{ fontSize: '0.7rem', color: '#888' }}>USE CODE</div>
                          <div style={{ fontSize: '1.1rem', fontWeight: 'bold', letterSpacing: '1px' }}>{promoModalForm.promo_code}</div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowPromoModalForm(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={handleSavePromoModal}
                disabled={savingPromoModal || !promoModalForm.title || !promoModalForm.message}
              >
                {savingPromoModal ? 'Saving...' : (editingPromoModal ? 'Update' : 'Save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Promo Modal Confirmation */}
      {showDeletePromoModal && promoModalToDelete && (
        <div className="modal-overlay" onClick={() => setShowDeletePromoModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Delete Promo Modal</h3>
            <p>Are you sure you want to delete this promo modal?</p>
            <div className="modal-booking-info">
              <p><strong>Title:</strong> {promoModalToDelete.title}</p>
              <p><strong>Views:</strong> {promoModalToDelete.viewCount} | <strong>Clicks:</strong> {promoModalToDelete.clickCount}</p>
            </div>
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowDeletePromoModal(false)}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-danger"
                onClick={handleDeletePromoModal}
                disabled={deletingPromoModal}
              >
                {deletingPromoModal ? 'Deleting...' : 'Yes, Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

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
                {detectedTestimonialThemes.length > 0 && (
                  <div className="testimonial-theme-preview" aria-label="Detected testimonial themes">
                    <span className="testimonial-theme-preview-label">Themes</span>
                    <div className="testimonial-theme-pills">
                      {detectedTestimonialThemes.map(theme => (
                        <span key={theme} className="testimonial-theme-pill">{theme}</span>
                      ))}
                    </div>
                  </div>
                )}
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
                  <label>Drop-off Date</label>
                  <div style={{ display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
                    <input
                      type="text"
                      placeholder="DD/MM/YYYY"
                      value={editForm.dropoff_date}
                      onChange={(e) => setEditForm({ ...editForm, dropoff_date: formatDateInput(e.target.value) })}
                      maxLength={10}
                      style={{ width: '125px' }}
                    />
                    <DatePicker
                      selected={parseUkDate(editForm.dropoff_date)}
                      onChange={(date) => setEditForm({ ...editForm, dropoff_date: dateToUkString(date) })}
                      dateFormat="dd/MM/yyyy"
                      customInput={<button type="button" className="date-picker-btn">📅</button>}
                    />
                  </div>
                </div>
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
                  <label>Arrival Date</label>
                  <div style={{ display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
                    <input
                      type="text"
                      placeholder="DD/MM/YYYY"
                      pattern="\d{2}/\d{2}/\d{4}"
                      value={editForm.flight_arrival_date}
                      onChange={(e) => setEditForm({ ...editForm, flight_arrival_date: formatDateInput(e.target.value) })}
                      maxLength={10}
                      style={{ width: '125px' }}
                    />
                    <DatePicker
                      selected={parseUkDate(editForm.flight_arrival_date)}
                      onChange={(date) => setEditForm({ ...editForm, flight_arrival_date: dateToUkString(date) })}
                      dateFormat="dd/MM/yyyy"
                      customInput={<button type="button" className="date-picker-btn">📅</button>}
                    />
                  </div>
                </div>
                <div className="modal-form-group">
                  <label>Pickup Date</label>
                  <div style={{ display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
                    <input
                      type="text"
                      placeholder="DD/MM/YYYY"
                      pattern="\d{2}/\d{2}/\d{4}"
                      value={editForm.pickup_date}
                      onChange={(e) => setEditForm({ ...editForm, pickup_date: formatDateInput(e.target.value) })}
                      maxLength={10}
                      style={{ width: '125px' }}
                    />
                    <DatePicker
                      selected={parseUkDate(editForm.pickup_date)}
                      onChange={(date) => setEditForm({ ...editForm, pickup_date: dateToUkString(date) })}
                      dateFormat="dd/MM/yyyy"
                      customInput={<button type="button" className="date-picker-btn">📅</button>}
                    />
                  </div>
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

      {/* Refund Booking Modal */}
      {showRefundModal && bookingToRefund && (
        <div className="modal-overlay" onClick={() => !processingRefund && setShowRefundModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Refund Booking</h3>
            <p>
              This issues a <strong>full refund of £{((bookingToRefund.payment?.amount_pence || 0) / 100).toFixed(2)}</strong> via
              Stripe. It cannot be undone. Financials updates automatically;
              the refund email stays a separate manual step.
            </p>
            <div className="modal-booking-info">
              <p><strong>Reference:</strong> {bookingToRefund.reference}</p>
              <p><strong>Customer:</strong> {bookingToRefund.customer?.first_name} {bookingToRefund.customer?.last_name}</p>
            </div>
            <div className="modal-form-group" style={{ margin: '12px 0' }}>
              <label>Reason</label>
              <select
                value={refundReason}
                onChange={(e) => setRefundReason(e.target.value)}
                disabled={processingRefund}
              >
                <option value="requested_by_customer">Customer request</option>
                <option value="duplicate">Duplicate payment</option>
                <option value="fraudulent">Fraudulent</option>
              </select>
            </div>
            {refundModalError && (
              <p style={{ color: '#ef4444', fontSize: '13px' }}>{refundModalError}</p>
            )}
            <div className="modal-actions">
              <button
                className="modal-btn modal-btn-secondary"
                onClick={() => setShowRefundModal(false)}
                disabled={processingRefund}
              >
                Cancel
              </button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={handleConfirmRefundBooking}
                disabled={processingRefund}
              >
                {processingRefund
                  ? 'Refunding...'
                  : `Refund £${((bookingToRefund.payment?.amount_pence || 0) / 100).toFixed(2)}`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Swap Vehicle Modal */}
      {showSwapVehicleModal && bookingForSwap && (
        <div className="modal-overlay" onClick={closeSwapVehicleModal}>
          <div className="modal-content swap-vehicle-modal" onClick={(e) => e.stopPropagation()}>
            {!swapConfirmVehicle ? (
              <>
                <h3>Swap Vehicle</h3>
                <div className="modal-booking-info">
                  <p><strong>Booking:</strong> {bookingForSwap.reference}</p>
                  <p><strong>Current Vehicle:</strong> {bookingForSwap.vehicle?.registration} ({bookingForSwap.vehicle?.make} {bookingForSwap.vehicle?.colour})</p>
                </div>

                {loadingCustomerVehicles ? (
                  <div className="loading-spinner">Loading vehicles...</div>
                ) : customerVehiclesForSwap.length === 0 ? (
                  <div className="no-vehicles-message">
                    <p>No other vehicles found for this customer.</p>
                    <p className="hint">Add vehicles in the customer's profile first.</p>
                  </div>
                ) : (
                  <>
                    <p className="swap-instruction">Select a vehicle to swap to:</p>
                    <div className="swap-vehicles-list">
                      {customerVehiclesForSwap.map(vehicle => (
                        <div
                          key={vehicle.id}
                          className="swap-vehicle-card"
                          onClick={() => handleSelectVehicleForSwap(vehicle)}
                        >
                          <div className="swap-vehicle-reg">{vehicle.registration}</div>
                          <div className="swap-vehicle-details">
                            {vehicle.make} {vehicle.model && `${vehicle.model} `}- {vehicle.colour}
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}

                <div className="modal-actions">
                  <button
                    className="modal-btn modal-btn-secondary"
                    onClick={closeSwapVehicleModal}
                  >
                    Cancel
                  </button>
                </div>
              </>
            ) : (
              <>
                <h3>Confirm Vehicle Swap</h3>
                <div className="swap-confirm-info">
                  <div className="swap-from">
                    <span className="swap-label">From:</span>
                    <span className="swap-reg">{bookingForSwap.vehicle?.registration}</span>
                    <span className="swap-details">{bookingForSwap.vehicle?.make} {bookingForSwap.vehicle?.colour}</span>
                  </div>
                  <div className="swap-arrow">→</div>
                  <div className="swap-to">
                    <span className="swap-label">To:</span>
                    <span className="swap-reg">{swapConfirmVehicle.registration}</span>
                    <span className="swap-details">{swapConfirmVehicle.make} {swapConfirmVehicle.model && `${swapConfirmVehicle.model} `}{swapConfirmVehicle.colour}</span>
                  </div>
                </div>
                <p className="swap-warning">This will update the vehicle for booking {bookingForSwap.reference}.</p>
                <div className="modal-actions">
                  <button
                    className="modal-btn modal-btn-secondary"
                    onClick={() => setSwapConfirmVehicle(null)}
                  >
                    Back
                  </button>
                  <button
                    className="modal-btn modal-btn-primary"
                    onClick={handleConfirmSwapVehicle}
                    disabled={swappingVehicle}
                  >
                    {swappingVehicle ? 'Swapping...' : 'Confirm Swap'}
                  </button>
                </div>
              </>
            )}
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
              <p><strong>Vehicle:</strong> {bookingForInspection.vehicle?.registration} - {bookingForInspection.vehicle?.colour} {bookingForInspection.vehicle?.make}</p>
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
              <p><strong>Vehicle:</strong> {bookingForDropoffInspection.vehicle?.registration} - {bookingForDropoffInspection.vehicle?.colour} {bookingForDropoffInspection.vehicle?.make}</p>
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
