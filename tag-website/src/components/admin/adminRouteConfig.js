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
    ],
  },
  {
    category: 'Staff',
    icon: '👥',
    items: [
      { id: 'payroll', label: 'Payroll' },
      { id: 'users', label: 'Users' },
    ],
  },
  {
    category: 'Customers',
    icon: '🧑‍💼',
    items: [
      { id: 'customers', label: 'Customers' },
      { id: 'leads', label: 'Abandoned Leads' },
    ],
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
    ],
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
    ],
  },
  {
    category: 'Settings',
    icon: '⚙️',
    items: [
      { id: 'pricing', label: 'Pricing' },
      { id: 'testimonials', label: 'Testimonials' },
      { id: 'promo-modals', label: 'Promo Modals' },
    ],
  },
  {
    category: 'QA',
    icon: '🔧',
    restrictToUserIds: [1, 2],
    items: [
      { id: 'qa-tests', label: 'Test Results' },
      { id: 'qa-connection-pool', label: 'Connection Pool' },
      { id: 'qa-audit', label: 'Audit Logs' },
      { id: 'qa-errors', label: 'Error Logs' },
      { id: 'qa-sql', label: 'SQL Interface' },
      { id: 'qa-roster-planner', label: 'Roster Planner' },
    ],
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
  Object.entries(ADMIN_ROUTE_BY_ITEM_ID).map(([itemId, route]) => [route, itemId]),
)

const ADMIN_DEFAULT_ITEM_ID = 'bookings'
const ADMIN_DEFAULT_ROUTE = ADMIN_ROUTE_BY_ITEM_ID[ADMIN_DEFAULT_ITEM_ID]

const ADMIN_ITEM_META = NAV_STRUCTURE.flatMap((category) =>
  category.items.map((item) => ({
    itemId: item.id,
    itemLabel: item.label,
    category: category.category,
    route: ADMIN_ROUTE_BY_ITEM_ID[item.id],
    restrictToUserIds: category.restrictToUserIds,
  })),
)

const normalizeAdminCategorySlug = (categoryName) =>
  String(categoryName || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)+/g, '')

const ADMIN_ITEM_ID_BY_CATEGORY_SLUG = Object.fromEntries(
  NAV_STRUCTURE
    .filter(category => category.items?.length)
    .map(category => [normalizeAdminCategorySlug(category.category), category.items[0].id]),
)

const ADMIN_ITEM_META_BY_ID = Object.fromEntries(
  ADMIN_ITEM_META.map((item) => [item.itemId, item]),
)

const getAdminItemIdForPath = (pathname) => {
  const normalisedPath = (pathname || '').replace(/\/+$/, '') || '/admin'
  const lowerPath = normalisedPath.toLowerCase()
  if (lowerPath === '/admin') return ADMIN_DEFAULT_ITEM_ID
  if (ADMIN_ITEM_BY_ROUTE[lowerPath]) {
    return ADMIN_ITEM_BY_ROUTE[lowerPath]
  }
  const categoryMatch = lowerPath.match(/^\/admin\/([^/]+)$/)
  if (!categoryMatch) return null
  const categorySlug = categoryMatch[1].toLowerCase()
  return ADMIN_ITEM_ID_BY_CATEGORY_SLUG[categorySlug] || null
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

const isNavItemActiveForState = (activeTab, marketingSubTab, reportsSubTab, itemId) => {
  if (itemId === 'marketing' && activeTab === 'marketing' && marketingSubTab === 'subscribers') return true
  if (itemId === 'promotions' && activeTab === 'marketing' && marketingSubTab === 'promotions') return true
  if (itemId === 'campaigns' && activeTab === 'marketing' && marketingSubTab === 'campaigns') return true
  if (itemId === 'referrals' && activeTab === 'marketing' && marketingSubTab === 'referrals') return true
  if (itemId === 'sources' && activeTab === 'marketing' && marketingSubTab === 'sources') return true
  if (itemId === 'reports-growth' && activeTab === 'reports' && reportsSubTab === 'growth') return true
  if (itemId === 'reports-occupancy' && activeTab === 'reports' && reportsSubTab === 'occupancy') return true
  if (itemId === 'reports-routes' && activeTab === 'reports' && reportsSubTab === 'popular') return true
  if (itemId === 'reports-map' && activeTab === 'reports' && reportsSubTab === 'map') return true
  if (itemId === 'reports-financial' && activeTab === 'reports' && reportsSubTab === 'financial') return true
  if (itemId === 'reports-sessions' && activeTab === 'reports' && reportsSubTab === 'sessions') return true
  if (itemId === 'reports-analytics' && activeTab === 'reports' && reportsSubTab === 'analytics') return true
  if (itemId === 'reports-forecast' && activeTab === 'reports' && reportsSubTab === 'forecast') return true
  const subTabIds = ['marketing', 'promotions', 'campaigns', 'referrals', 'sources', 'reports-growth', 'reports-occupancy', 'reports-routes', 'reports-map', 'reports-financial', 'reports-sessions', 'reports-analytics', 'reports-forecast']
  if (!subTabIds.includes(itemId)) {
    return activeTab === itemId
  }
  return false
}

export {
  ADMIN_ROUTE_BY_ITEM_ID,
  ADMIN_ITEM_BY_ROUTE,
  ADMIN_DEFAULT_ITEM_ID,
  ADMIN_DEFAULT_ROUTE,
  ADMIN_ITEM_META,
  ADMIN_ITEM_META_BY_ID,
  NAV_STRUCTURE,
  getAdminItemIdForPath,
  getAdminRouteForItem,
  getAdminSelectionForItem,
  getAdminItemIdForSelection,
  getDefaultRouteForCategory,
  isNavItemActiveForState,
}
