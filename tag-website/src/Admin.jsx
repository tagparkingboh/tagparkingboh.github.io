import { useState, useEffect, useMemo, Fragment, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'
import 'react-datepicker/dist/react-datepicker.css'
import AdminContentRouter from './components/admin/AdminContentRouter'
import AdminOverlayLayers from './components/admin/AdminOverlayLayers'
import AdminShellLayout from './components/admin/AdminShellLayout'
import useAdminRouteState from './components/admin/useAdminRouteState'
import {
  ADMIN_DEFAULT_ITEM_ID,
  ADMIN_DEFAULT_ROUTE,
  ADMIN_ITEM_BY_ROUTE,
  ADMIN_ITEM_META,
  ADMIN_ITEM_META_BY_ID,
  NAV_STRUCTURE,
  ADMIN_ROUTE_BY_ITEM_ID,
  getAdminItemIdForPath,
  getAdminItemIdForSelection,
  getAdminRouteForItem,
  getAdminSelectionForItem,
  isNavItemActiveForState,
  getDefaultRouteForCategory,
} from './components/admin/adminRouteConfig'
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
  const {
    activeTab,
    marketingSubTab,
    reportsSubTab,
    sidebarCollapsed,
    setSidebarCollapsed,
    expandedCategories,
    isNavItemActive,
    activeAdminItemMeta,
    toggleCategory,
    handleTabSelect,
  } = useAdminRouteState({
    user,
    isAuthenticated,
    isAdmin,
    loading,
    locationPathname: location.pathname,
    navigate,
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

  // Fetch pricing when pricing tab is active
  useEffect(() => {
    if (activeTab === 'pricing' && token) {
      fetchPricing()
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
          capacity_tier: Number(addFlightForm.capacity_tier),
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

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })

      if (response.ok) {
        setFlightsMessage(`Flight ${addFlightForm.flight_number} added successfully`)
        setShowAddFlightModal(false)
        resetAddFlightForm()
        fetchFlights()
        setTimeout(() => setFlightsMessage(''), 3000)
      } else {
        const data = await response.json()
        setFlightsMessage(`Error: ${data.detail || 'Failed to add flight'}`)
      }
    } catch (err) {
      setFlightsMessage('Network error adding flight')
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

  const openCustomerModalFromMarketing = (customer) => {
    if (!customer?.id) return
    handleTabSelect('customers')
    navigate(getAdminRouteForItem('customers'), {
      state: {
        openCustomerId: customer.id,
      },
    })
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

  // Group flights by month (YYYY-MM)
  const departuresByMonth = useMemo(() => {
    const groups = {}
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                        'July', 'August', 'September', 'October', 'November', 'December']

    departures.forEach(flight => {
      if (!flight.date) return
      const monthKey = flight.date.substring(0, 7)
      if (!groups[monthKey]) {
        const [year, month] = monthKey.split('-')
        groups[monthKey] = {
          label: `${monthNames[parseInt(month) - 1]} ${year}`,
          flights: []
        }
      }
      groups[monthKey].flights.push(flight)
    })

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
      const monthKey = flight.date.substring(0, 7)
      if (!groups[monthKey]) {
        const [year, month] = monthKey.split('-')
        groups[monthKey] = {
          label: `${monthNames[parseInt(month) - 1]} ${year}`,
          flights: []
        }
      }
      groups[monthKey].flights.push(flight)
    })

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
  const referralUsageTotal = referralsPagination.code_usage_filtered_total ?? (referralsPagination.code_usage_total ?? 0)
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

  const bookingSectionProps = {
    bookings,
    bookingsLoadAll,
    loadingData,
    fetchBookings,
    todaysBookings,
    filteredBookings,
    bookingsByStatus,
    searchTerm,
    setSearchTerm,
    statusFilter,
    setStatusFilter,
    hideTestEmails,
    setHideTestEmails,
    sortAsc,
    setSortAsc,
    collapsedStatusSections,
    setCollapsedStatusSections,
    expandedBookingMonths,
    setExpandedBookingMonths,
    expandedBookingId,
    setExpandedBookingId,
    formatDate,
    formatTime,
    bookingActionHandlers: {
      handleEditBookingClick,
      handleResendEmailClick,
      handleSwapVehicleClick,
      handleSendCancellationEmailClick,
      handleSendRefundEmailClick,
      handleRefundBookingClick,
      handleRefundClick,
      handleCancelClick,
      handleMarkPaid,
      handleSendFounderEmailClick,
      handleDeleteClick,
      handleViewDropoffInspectionClick,
      handleViewReturnInspectionClick,
      handleSendParkingUpdate,
      getParkingUpdateStatus,
      getParkingUpdateTitle,
      getParkingUpdateLabel,
    },
    bookingActionState: {
      cancellingId,
      deletingId,
      resendingEmailId,
      markingPaidId,
      sendingParkingUpdateId,
      sendingFounderEmailId,
      sendingCancellationEmailId,
      sendingRefundEmailId,
    },
  }

  const bookingsPageProps = {
    bookingSectionProps,
  }

  const calendarPageProps = {
    token,
  }

  const manualBookingPageProps = {
    token,
  }

  const flightsPageProps = {
    fetchFlights,
    exportFlights,
    loadingFlights,
    exportingFlights,
    flightsMessage,
    flightsSubTab,
    setFlightsSubTab,
    setEditingFlightId,
    flightAirlineFilter,
    setFlightAirlineFilter,
    flightFilters,
    flightNumberFilter,
    setFlightNumberFilter,
    departures,
    arrivals,
    flightDestFilter,
    setFlightDestFilter,
    flightOriginFilter,
    setFlightOriginFilter,
    flightMonthFilter,
    setFlightMonthFilter,
    flightsSortAsc,
    setFlightsSortAsc,
    departuresByMonth,
    arrivalsByMonth,
    collapsedFlightMonths,
    toggleFlightMonth,
    editingFlightId,
    setEditFlightForm,
    editFlightForm,
    savingFlight,
    saveFlightEdit,
    cancelEditFlight,
    startEditFlight,
    confirmDeleteFlight,
    showAddFlightModal,
    setShowAddFlightModal,
    addFlightForm,
    setAddFlightForm,
    resetAddFlightForm,
    handleAddFlight,
    addingFlight,
    showDeleteFlightModal,
    flightToDelete,
    setShowDeleteFlightModal,
    setFlightToDelete,
    handleDeleteFlight,
    deletingFlightId,
  }

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

  const marketingSectionProps = {
  REFERRALS_PAGE_SIZE_OPTIONS,
  activeTab,
  addManualRecipient,
  addRecipient,
  availablePromoCodes,
  campaignConfirm,
  campaignPreview,
  campaignToast,
  campaigns,
  closeCampaignModal,
  createCampaign,
  createPromotion,
  creatingCampaign,
  creatingPromotion,
  deleteCampaign,
  deletePromotion,
  deletingCampaignId,
  deletingPromotionId,
  editingCampaignId,
  editingPromotion,
  expandedPromotionId,
  expandedSubscriberId,
  expandedSubscriberMonths,
  expiryDate,
  expiryModalData,
  expiryTime,
  exportMarketingSourcesCSV,
  fetchCampaigns,
  fetchMarketingOtherDetails,
  fetchMarketingSources,
  fetchPromotionDetails,
  fetchReferralsDashboard,
  fetchSubscribers,
  filteredReferralCustomers,
  filteredReferralUsage,
  filteredSubscribers,
  formatDateTimeUK,
  formatDateUK,
  formatPence,
  generateCodesCount,
  generateCodesExpiryDate,
  generateCodesExpiryTime,
  generateCodesMaxUses,
  generateCodesPromotion,
  generateMoreCodes,
  generatingCodes,
  handleManualReferralInvite,
  handleReferralDashboardAction,
  hideTestEmails,
  loadingCampaigns,
  loadingMarketingOther,
  loadingMarketingSources,
  loadingPromotions,
  loadingReferrals,
  loadingSubscribers,
  manualRecipient,
  manualReferralInvite,
  manualReferralInviteMessage,
  marketingExportFromDate,
  marketingExportToDate,
  marketingOtherDetails,
  marketingOtherMonth,
  marketingSourcesData,
  marketingSubTab,
  newCampaign,
  newPromotion,
  openCampaignForEdit,
  openCustomerModal: openCustomerModalFromMarketing,
  openExpiryModal,
  openFounderEmailModal,
  openGenerateCodesModal,
  openSendPromoEmailModal,
  performDeleteCampaign,
  performSendCampaign,
  previewCampaign,
  promoEmailBody,
  promoEmailRecipients,
  promoEmailSubject,
  promoSuccessMessage,
  promotionDetails,
  promotionMessage,
  promotions,
  recipientSearchResults,
  recipientSearchTerm,
  referralCustomerEnd,
  referralCustomerStart,
  referralCustomerTotal,
  referralDashboardAction,
  referralUsageEnd,
  referralUsageStart,
  referralUsageTableRef,
  referralUsageTotal,
  referralsCustomerOffset,
  referralsCustomerPageSize,
  referralsCustomerSearch,
  referralsDashboard,
  referralsDashboardHasLoaded,
  referralsFilter,
  referralsUsageFilter,
  referralsUsageOffset,
  referralsUsagePageSize,
  referralsUsageSearch,
  refreshPromotions,
  removeRecipient,
  searchRecipients,
  searchingRecipients,
  selectedCodes,
  sendCampaign,
  sendPromo10Reminder,
  sendPromoEmailData,
  sendPromoEmails,
  sendPromoFreeReminder,
  sendingCampaign,
  sendingManualReferralInvite,
  sendingPromoEmails,
  onSelectAdminItem: handleTabSelect,
  setCampaignConfirm,
  setCampaignToast,
  setEditingPromotion,
  setExpandedPromotionId,
  setExpandedSubscriberId,
  setExpandedSubscriberMonths,
  setExpiryDate,
  setExpiryModalData,
  setExpiryTime,
  setGenerateCodesCount,
  setGenerateCodesExpiryDate,
  setGenerateCodesExpiryTime,
  setGenerateCodesMaxUses,
  setHideTestEmails,
  setManualRecipient,
  setManualReferralInvite,
  setMarketingExportFromDate,
  setMarketingExportToDate,
  setNewCampaign,
  setNewPromotion,
  setPromoEmailBody,
  setPromoEmailSubject,
  setPromotionMessage,
  setRecipientSearchTerm,
  setReferralsCustomerOffset,
  setReferralsCustomerPageSize,
  setReferralsCustomerSearch,
  setReferralsFilter,
  setReferralsUsageFilter,
  setReferralsUsageOffset,
  setReferralsUsagePageSize,
  setReferralsUsageSearch,
  setSearchTerm,
  setSelectedCodes,
  setShowCreateCampaign,
  setShowCreatePromotion,
  setShowExpiryModal,
  setShowGenerateCodesModal,
  setShowMarketingOtherModal,
  setShowSendPromoEmailModal,
  setSubscriberDateFrom,
  setSubscriberDateTo,
  setSubscriberSearchTerm,
  setSubscriberStatusFilter,
  showCreateCampaign,
  showCreatePromotion,
  showExpiryModal,
  showGenerateCodesModal,
  showMarketingOtherModal,
  showSendPromoEmailModal,
  subscriberDateFrom,
  subscriberDateTo,
  subscriberSearchTerm,
  subscriberStatusFilter,
  subscribers,
  toggleSharedOnSocials,
  toggleSharedPrivately,
  updatePromoCodeExpiry,
  updatePromotion,
  updatingExpiry,
  }


  const reportsSectionProps = {
    abandonedCartsData,
    abandonedCartsPeriod,
    activeTab,
    bookingLocations,
    bookingStats,
    capacityForm,
    capacityMessage,
    capacitySettings,
    dateToUkString,
    editingFinancialBooking,
    expandedDailyMonths,
    expandedFinancialMonths,
    expandedRevenueDailyMonths,
    exportFinancialCSV,
    exportingFinancial,
    fetchAbandonedCarts,
    fetchBookingLocations,
    fetchBookingStats,
    fetchBookingsForecast,
    fetchFinancialReport,
    fetchFunFacts,
    fetchOccupancyReport,
    fetchSessionTracking,
    financialData,
    financialFromDate,
    financialPromoFilter,
    financialStatusFilter,
    financialToDate,
    forecastData,
    formatDateInput,
    funFacts,
    loadingAbandonedCarts,
    loadingCapacitySettings,
    loadingFinancial,
    loadingForecast,
    loadingFunFacts,
    loadingLocations,
    loadingOccupancy,
    loadingPopular,
    loadingSecondaryReport,
    loadingSessionTracking,
    loadingStats,
    mapType,
    occupancyChartMaxPercent,
    occupancyChartOffset,
    occupancyData,
    occupancyView,
    originLocations,
    parseUkDate,
    peakHoursView,
    peakSearchView,
    popularData,
    popularTop,
    reportsSubTab,
    revenueChartType,
    revenueWeeklyPageIndex,
    saveCapacitySettings,
    saveFinancialOverride,
    savingCapacitySettings,
    savingFinancialOverride,
    secondaryGroup,
    secondaryReport,
    sessionTrackingData,
    sessionTrackingPeriod,
    setAbandonedCartsPeriod,
    setCapacityForm,
    setEditingFinancialBooking,
    setExpandedDailyMonths,
    setExpandedFinancialMonths,
    setExpandedRevenueDailyMonths,
    setFinancialFromDate,
    setFinancialPromoFilter,
    setFinancialStatusFilter,
    setFinancialToDate,
    setMapType,
    setOccupancyChartOffset,
    setOccupancyView,
    setPeakHoursView,
    setPeakSearchView,
    setPopularTop,
    setRevenueChartType,
    setRevenueWeeklyPageIndex,
    setSecondaryGroup,
    setSessionTrackingPeriod,
    setStatsChartType,
    setWeeklyPageIndex,
    skippedBookings,
    statsChartType,
    totalBookings,
    totalCustomers,
    weeklyPageIndex,
  }

  const staffPayrollPageProps = {
    token,
  }

  const staffUsersPageProps = {
    API_URL,
    token,
  }

  const customersPageProps = {
    API_URL,
    token,
    formatMarketingSource,
    onViewReferralDetails: () => {
      handleTabSelect('referrals')
    },
    onRefreshBookings: fetchBookings,
  }

  const leadsPageProps = {
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
  }

  const settingsModalsProps = {
    showPromoModalForm,
    editingPromoModal,
    promoModalForm,
    setPromoModalForm,
    setShowPromoModalForm,
    formatDateInput,
    parseUkDate,
    dateToUkString,
    loadingPromoCodesForModal,
    promoCodesForModal,
    setPromoCodeIsMultiUse,
    setSelectedPromoCodeInfo,
    selectedPromoCodeInfo,
    handleSavePromoModal,
    savingPromoModal,
    showDeletePromoModal,
    promoModalToDelete,
    setShowDeletePromoModal,
    handleDeletePromoModal,
    deletingPromoModal,
    showTestimonialModal,
    setShowTestimonialModal,
    testimonialForm,
    setTestimonialForm,
    detectedTestimonialThemes,
    editingTestimonial,
    handleSaveTestimonial,
    savingTestimonial,
    showDeleteTestimonialModal,
    setShowDeleteTestimonialModal,
    testimonialToDelete,
    handleDeleteTestimonial,
    deletingTestimonial,
  }

  const bookingModalsProps = {
    showCancelModal,
    setShowCancelModal,
    bookingToCancel,
    handleConfirmCancel,
    cancellingId,
    formatDate,
    showDeleteModal,
    setShowDeleteModal,
    bookingToDelete,
    confirmDeleteBooking,
    deletingId,
    showEditModal,
    setShowEditModal,
    bookingToEdit,
    editForm,
    setEditForm,
    formatDateInput,
    parseUkDate,
    dateToUkString,
    confirmEditBooking,
    savingEdit,
    showResendModal,
    setShowResendModal,
    bookingToResend,
    handleConfirmResendEmail,
    resendingEmailId,
    showRefundModal,
    setShowRefundModal,
    bookingToRefund,
    processingRefund,
    refundReason,
    setRefundReason,
    refundModalError,
    handleConfirmRefundBooking,
    showSwapVehicleModal,
    bookingForSwap,
    closeSwapVehicleModal,
    loadingCustomerVehicles,
    customerVehiclesForSwap,
    handleSelectVehicleForSwap,
    setSwapConfirmVehicle,
    swapConfirmVehicle,
    handleConfirmSwapVehicle,
    swappingVehicle,
    showCancellationEmailModal,
    setShowCancellationEmailModal,
    bookingForCancellationEmail,
    handleConfirmSendCancellationEmail,
    sendingCancellationEmailId,
    showRefundEmailModal,
    setShowRefundEmailModal,
    bookingForRefundEmail,
    handleConfirmSendRefundEmail,
    sendingRefundEmailId,
    showFounderEmailModal,
    setShowFounderEmailModal,
    bookingForFounderEmail,
    handleConfirmSendFounderEmail,
    sendingFounderEmailId,
    showPromoModal,
    setShowPromoModal,
    promoToSend,
    confirmSendPromo,
    sendingPromoId,
    setPromoToSend,
    showSubscriberFounderModal,
    setShowSubscriberFounderModal,
    founderEmailToSend,
    confirmSendFounderEmail,
    setFounderEmailToSend,
    showReturnInspectionModal,
    closeReturnInspectionModal,
    bookingForInspection,
    loadingReturnInspection,
    returnInspectionData,
    formatDateTimeUK,
    showDropoffInspectionModal,
    closeDropoffInspectionModal,
    bookingForDropoffInspection,
    loadingDropoffInspection,
    dropoffInspectionData,
  }

  const pricingSectionProps = {
    pricing,
    fetchPricing,
    pricingMessage,
    loadingPricing,
    setPricing,
    savingPricing,
    savePricing,
  }

  const testimonialsSectionProps = {
    testimonials,
    loadingTestimonials,
    fetchTestimonials,
    testimonialSuccessMessage,
    testimonialFilter,
    setTestimonialFilter,
    testimonialSort,
    setTestimonialSort,
    openAddTestimonialModal,
    renderStars,
    openEditTestimonialModal,
    handleToggleTestimonialStatus,
    setTestimonialToDelete,
    setShowDeleteTestimonialModal,
  }

  const promoModalsSectionProps = {
    promoModals,
    loadingPromoModals,
    fetchPromoModals,
    promoModalSuccessMessage,
    setEditingPromoModal,
    setPromoModalForm,
    setPromoCodeIsMultiUse,
    setSelectedPromoCodeInfo,
    setShowPromoModalForm,
    fetchPromoCodesForModal,
    openEditPromoModal,
    handleTogglePromoModalStatus,
    setPromoModalToDelete,
    setShowDeletePromoModal,
  }

  const settingsSectionProps = {
    activeTab,
    pricingSectionProps,
    testimonialsSectionProps,
    promoModalsSectionProps,
  }

  const staffSectionProps = {
    activeTab,
    staffPayrollPageProps,
    staffUsersPageProps,
  }

  const customersSectionProps = {
    activeTab,
    customersPageProps,
    leadsPageProps,
  }

  const qaSectionProps = {
    activeTab,
    API_URL,
    token,
    loadingTestResults,
    fetchTestResults,
    latestTestRun,
    testResults,
    loadingDbHealth,
    loadingPoolHistory,
    fetchDbHealth,
    fetchDbPoolHistory,
    dbHealth,
    dbPoolHistory,
    auditLogs,
    loadingAuditLogs,
    fetchAuditLogs,
    auditLogsTotalCount,
    auditLogsFilters,
    setAuditLogsFilters,
    auditEventTypes,
    auditLogsAutoRefresh,
    setAuditLogsAutoRefresh,
    expandedAuditLog,
    setExpandedAuditLog,
    auditLogsOffset,
    setAuditLogsOffset,
    errorLogs,
    loadingErrorLogs,
    errorLogsTotalCount,
    fetchErrorLogs,
    errorLogsFilters,
    setErrorLogsFilters,
    errorSeverities,
    errorTypes,
    expandedErrorLog,
    setExpandedErrorLog,
    sqlSessionToken,
    sqlSessionExpires,
    logoutSqlSession,
    sqlPinModalOpen,
    setSqlPinModalOpen,
    sqlPin,
    setSqlPin,
    verifySqlPin,
    sqlPinError,
    sqlQuery,
    setSqlQuery,
    executeSqlQuery,
    sqlLoading,
    sqlError,
    setSqlError,
    sqlResults,
    setSqlResults,
    exportSqlResultsCSV,
    exportSqlResultsPDF,
    sqlHistory,
    sqlTemplates,
    sqlTemplatesExpanded,
    setSqlTemplatesExpanded,
  }


  return (
    <>
    <AdminShellLayout
      user={user}
      sidebarCollapsed={sidebarCollapsed}
      onToggleSidebar={() => setSidebarCollapsed(!sidebarCollapsed)}
      onLogout={handleLogout}
      navStructure={NAV_STRUCTURE}
      expandedCategories={expandedCategories}
      onToggleCategory={toggleCategory}
      onSelectItem={handleTabSelect}
      isItemActive={isNavItemActive}
    >
      <AdminContentRouter
        adminDefaultRoute={ADMIN_DEFAULT_ROUTE}
        activeAdminItemMeta={activeAdminItemMeta}
        getDefaultRouteForCategory={getDefaultRouteForCategory}
        error={error}
        successMessage={successMessage}
        activeTab={activeTab}
        bookingsPageProps={bookingsPageProps}
        calendarPageProps={calendarPageProps}
        manualBookingPageProps={manualBookingPageProps}
        flightsPageProps={flightsPageProps}
        messagesPageProps={messagesPageProps}
        staffSectionProps={staffSectionProps}
        marketingSectionProps={marketingSectionProps}
        customersSectionProps={customersSectionProps}
        settingsSectionProps={settingsSectionProps}
        reportsSectionProps={reportsSectionProps}
        qaSectionProps={qaSectionProps}
        bookingsScrollTopVisible={bookingsScrollTopVisible}
        handleScrollToTop={() => window.scrollTo({ top: 0, behavior: 'auto' })}
      />
    </AdminShellLayout>

      <AdminOverlayLayers
        settingsModalsProps={settingsModalsProps}
        bookingModalsProps={bookingModalsProps}
      />
    </>
  )
}

export default Admin
export {
  ADMIN_ROUTE_BY_ITEM_ID,
  ADMIN_ITEM_BY_ROUTE,
  ADMIN_DEFAULT_ITEM_ID,
  ADMIN_DEFAULT_ROUTE,
  ADMIN_ITEM_META,
  ADMIN_ITEM_META_BY_ID,
  ADMIN_ITEM_META_BY_ID as adminItemMetaById,
  NAV_STRUCTURE,
  getAdminItemIdForPath,
  getAdminRouteForItem,
  getAdminSelectionForItem,
  getAdminItemIdForSelection,
  getDefaultRouteForCategory,
  isNavItemActiveForState,
}
export { getAdminItemIdForPath as getActiveRouteItemFromLocation }
