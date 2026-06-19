import { test, expect } from '@playwright/test'

const ROUTES = [
  { path: '/admin', expectedBreadcrumb: 'Bookings', expectedUrl: '/admin/operations/bookings' },
  { path: '/admin/operations', expectedBreadcrumb: 'Bookings', expectedUrl: '/admin/operations/bookings' },
  { path: '/admin/operations/bookings', expectedBreadcrumb: 'Bookings', expectedUrl: '/admin/operations/bookings' },
  { path: '/admin/operations/calendar', expectedBreadcrumb: 'Calendar', expectedUrl: '/admin/operations/calendar' },
  { path: '/admin/operations/manual-booking', expectedBreadcrumb: 'Manual Booking', expectedUrl: '/admin/operations/manual-booking' },
  { path: '/admin/operations/flights', expectedBreadcrumb: 'Flights', expectedUrl: '/admin/operations/flights' },
  { path: '/admin/operations/messages', expectedBreadcrumb: 'Messages', expectedUrl: '/admin/operations/messages' },
  { path: '/admin/staff', expectedBreadcrumb: 'Payroll', expectedUrl: '/admin/staff/payroll' },
  { path: '/admin/staff/payroll', expectedBreadcrumb: 'Payroll', expectedUrl: '/admin/staff/payroll' },
  { path: '/admin/staff/users', expectedBreadcrumb: 'Users', expectedUrl: '/admin/staff/users' },
  { path: '/admin/customers', expectedBreadcrumb: 'Customers', expectedUrl: '/admin/customers/customers' },
  { path: '/admin/customers/customers', expectedBreadcrumb: 'Customers', expectedUrl: '/admin/customers/customers' },
  { path: '/admin/customers/abandoned-leads', expectedBreadcrumb: 'Abandoned Leads', expectedUrl: '/admin/customers/abandoned-leads' },
  { path: '/admin/settings', expectedBreadcrumb: 'Pricing', expectedUrl: '/admin/settings/pricing' },
  { path: '/admin/settings/pricing', expectedBreadcrumb: 'Pricing', expectedUrl: '/admin/settings/pricing' },
  { path: '/admin/settings/testimonials', expectedBreadcrumb: 'Testimonials', expectedUrl: '/admin/settings/testimonials' },
  { path: '/admin/settings/promo-modals', expectedBreadcrumb: 'Promo Modals', expectedUrl: '/admin/settings/promo-modals' },
  { path: '/admin/marketing', expectedBreadcrumb: 'Subscribers', expectedUrl: '/admin/marketing/subscribers' },
  { path: '/admin/marketing/subscribers', expectedBreadcrumb: 'Subscribers', expectedUrl: '/admin/marketing/subscribers' },
  { path: '/admin/marketing/promotions', expectedBreadcrumb: 'Promotions', expectedUrl: '/admin/marketing/promotions' },
  { path: '/admin/marketing/email-campaigns', expectedBreadcrumb: 'Email Campaigns', expectedUrl: '/admin/marketing/email-campaigns' },
  { path: '/admin/marketing/referrals', expectedBreadcrumb: 'Referrals', expectedUrl: '/admin/marketing/referrals' },
  { path: '/admin/marketing/sources', expectedBreadcrumb: 'Sources', expectedUrl: '/admin/marketing/sources' },
  { path: '/admin/reports', expectedBreadcrumb: 'Booking Growth', expectedUrl: '/admin/reports/booking-growth' },
  { path: '/admin/reports/booking-growth', expectedBreadcrumb: 'Booking Growth', expectedUrl: '/admin/reports/booking-growth' },
  { path: '/admin/reports/financial', expectedBreadcrumb: 'Financial', expectedUrl: '/admin/reports/financial' },
  { path: '/admin/reports/session-tracking', expectedBreadcrumb: 'Session Tracking', expectedUrl: '/admin/reports/session-tracking' },
  { path: '/admin/reports/abandoned-carts', expectedBreadcrumb: 'Abandoned Carts', expectedUrl: '/admin/reports/abandoned-carts' },
  { path: '/admin/reports/bookings-forecast', expectedBreadcrumb: 'Bookings Forecast', expectedUrl: '/admin/reports/bookings-forecast' },
  { path: '/admin/reports/occupancy', expectedBreadcrumb: 'Occupancy', expectedUrl: '/admin/reports/occupancy' },
  { path: '/admin/reports/popular-routes', expectedBreadcrumb: 'Popular Routes', expectedUrl: '/admin/reports/popular-routes' },
  { path: '/admin/reports/location-maps', expectedBreadcrumb: 'Location Maps', expectedUrl: '/admin/reports/location-maps' },
  { path: '/admin/qa', expectedBreadcrumb: 'Test Results', expectedUrl: '/admin/qa/test-results' },
  { path: '/admin/qa/test-results', expectedBreadcrumb: 'Test Results', expectedUrl: '/admin/qa/test-results' },
  { path: '/admin/qa/connection-pool', expectedBreadcrumb: 'Connection Pool', expectedUrl: '/admin/qa/connection-pool' },
  { path: '/admin/qa/audit-logs', expectedBreadcrumb: 'Audit Logs', expectedUrl: '/admin/qa/audit-logs' },
  { path: '/admin/qa/error-logs', expectedBreadcrumb: 'Error Logs', expectedUrl: '/admin/qa/error-logs' },
  { path: '/admin/qa/sql-interface', expectedBreadcrumb: 'SQL Interface', expectedUrl: '/admin/qa/sql-interface' },
  { path: '/admin/qa/roster-planner', expectedBreadcrumb: 'Roster Planner', expectedUrl: '/admin/qa/roster-planner' },
]

const VIEWPORTS = [
  { name: 'desktop', width: 1366, height: 900 },
  { name: 'tablet', width: 768, height: 900 },
  { name: 'mobile', width: 390, height: 900 },
]

const defaultAdminUser = {
  id: 1,
  first_name: 'QA',
  last_name: 'Admin',
  is_admin: true,
}

const apiFixtureForPath = (pathname: string) => {
  const lower = pathname.toLowerCase()

  if (lower === '/api/admin/bookings' || lower.startsWith('/api/admin/bookings')) {
    return { bookings: [] }
  }
  if (lower === '/api/admin/pricing') {
    return {
      days_1_4_price: 100,
      week1_base_price: 250,
      week2_base_price: 700,
      daily_increment: 12,
      tier_increment: 35,
      peak_day_increment: 25,
      show_price_range: true,
    }
  }
  if (lower === '/api/admin/testimonials') {
    return { testimonials: [] }
  }
  if (lower === '/api/admin/promo-modals') {
    return { promoModals: [] }
  }
  if (lower === '/api/admin/promotions') {
    return { promotions: [] }
  }
  if (lower === '/api/admin/customers') {
    return { customers: [] }
  }
  if (lower === '/api/admin/abandoned-leads') {
    return { leads: [] }
  }
  if (lower === '/api/admin/marketing-subscribers') {
    return { subscribers: [] }
  }
  if (lower === '/api/admin/reports/financial') {
    return {
      funFacts: {},
      summary: {
        totalBookings: 0,
        totalGross: '£0.00',
        totalDiscount: '£0.00',
        totalNet: '£0.00',
        totalRefunds: '£0.00',
        totalRevenue: '£0.00',
      },
      chartData: {
        cumulative: [],
        weekly: [],
        daily: [],
        monthly: [],
      },
      monthlyData: [],
      details: [],
      totalGross: 0,
      totalDiscount: 0,
      totalNet: 0,
      totalRefunds: 0,
      totalRevenue: 0,
    }
  }
  if (lower === '/api/admin/db-health') {
    return {
      health: 'healthy',
      usage_percent: 10,
      checked_out: 1,
      overflow: 0,
      checked_in: 9,
      max_connections: 20,
      circuit_breaker: {
        state: 'CLOSED',
      },
    }
  }
  if (lower === '/api/admin/db-health/history') {
    return {
      snapshot_count: 1,
      circuit_breaker: {
        state: 'CLOSED',
      },
      snapshots: [
        {
          id: 1,
          timestamp: '2026-06-18T10:00:00+01:00',
          health_status: 'healthy',
          usage_percent: 10,
          checked_out: 1,
          overflow: 0,
          checked_in: 9,
          trigger: 'smoke',
        },
      ],
    }
  }
  if (lower === '/api/admin/test-results') {
    return { test_results: [] }
  }
  if (lower === '/api/admin/test-results/latest') {
    return { test_run: null }
  }
  if (lower === '/api/admin/capacity-settings') {
    return { current: null, history: [] }
  }
  if (lower === '/api/admin/bookings/stats') {
    return {
      total_successful: 0,
      this_month: 0,
      last_month: 0,
      this_week: 0,
      last_week: 0,
      avg_revenue_per_customer: 0,
      total_revenue: 0,
      paid_customer_count: 0,
      avg_trip_duration: 0,
      top_durations: [],
      dropoff_range: { am: 0, pm: 0, am_busiest: [], pm_busiest: [] },
      pickup_range: { am: 0, pm: 0, am_busiest: [], pm_busiest: [] },
      booking_days_of_week: [],
      booking_hours_of_day: [],
      booking_hours_by_day: {},
      booking_time_ranges: [],
    }
  }
  if (lower === '/api/admin/reports/fun-facts') {
    return {
      average_booking_value: 0,
      busiest_dropoff_time: '-',
      busiest_pickup_time: '-',
      conversion_rate: 0,
      no_show_rate: 0,
    }
  }
  if (lower === '/api/admin/reports/secondary-carpark') {
    return {
      active: [],
      inactive: [],
      usage: [],
    }
  }
  if (lower === '/api/admin/reports/occupancy') {
    return {
      data: [],
      online_capacity: 0,
      max_capacity: 0,
      total_capacity: 0,
      avg_occupancy_percent: 0,
      data_labels: [],
    }
  }
  if (lower === '/api/admin/reports/popular') {
    return {
      routes: [],
      destinations: [],
    }
  }
  if (lower === '/api/admin/reports/session-tracking') {
    return { sessions: [] }
  }
  if (lower === '/api/admin/reports/abandoned-carts') {
    return { period: 'daily', cart_abandonment_rate: 0, abandoned: [] }
  }
  if (lower === '/api/admin/reports/bookings-forecast') {
    return { forecast: [], weekly: [] }
  }
  if (lower === '/api/admin/users') {
    return { users: [] }
  }
  if (lower.startsWith('/api/payroll')) {
    return { staff: [] }
  }
  if (lower === '/api/admin/audit-logs') {
    return { events: [], total: 0 }
  }
  if (lower === '/api/admin/error-logs') {
    return { errors: [], total: 0 }
  }
  if (lower === '/api/admin/sql/templates') {
    return { templates: [] }
  }
  if (lower === '/api/admin/reports/booking-locations') {
    return { locations: [] }
  }
  if (lower === '/api/admin/reports/location-maps') {
    return { map_data: [] }
  }
  if (lower === '/api/admin/reports/booking-growth') {
    return { data: [] }
  }
  if (lower === '/api/admin/marketing-sources') {
    return { sources: [] }
  }
  if (lower === '/api/admin/campaigns' || lower.includes('/api/admin/campaigns')) {
    return { campaigns: [] }
  }
  if (lower === '/api/admin/promos') {
    return { promotions: [] }
  }
  if (lower === '/api/admin/messages') {
    return { threads: [] }
  }
  if (lower === '/api/admin/messages/threads') {
    return { threads: [] }
  }
  if (lower === '/api/admin/messages/stats') {
    return {
      total_sent: 0,
      delivered: 0,
      pending: 0,
      failed: 0,
      unread: 0,
      conversations: 0,
    }
  }
  if (lower === '/api/admin/referrals-dashboard') {
    return { stats: {}, customers: [], code_usage: [] }
  }
  if (lower === '/api/admin/messages/templates') {
    return { templates: [] }
  }
  if (lower === '/api/admin/roster-planner') {
    return { settings: null, schedule: [] }
  }
  if (lower === '/api/auth/me') {
    return defaultAdminUser
  }

  return {}
}

const buildApiRouteMock = async (route) => {
  const url = new URL(route.request().url())
  const body = apiFixtureForPath(url.pathname.toLowerCase())
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

test.describe('admin route deep links', () => {
  for (const viewport of VIEWPORTS) {
    for (const route of ROUTES) {
      test(`route ${route.path} renders ${route.expectedBreadcrumb} breadcrumb on ${viewport.name}`, async ({ page }) => {
        await page.setViewportSize({ width: viewport.width, height: viewport.height })
        await page.route('**/api/**', buildApiRouteMock)
        await page.addInitScript(
          ({ adminUser }) => {
            window.localStorage.setItem('auth_token', 'smoke-token')
            window.localStorage.setItem('auth_user', JSON.stringify(adminUser))
          },
          { adminUser: defaultAdminUser }
        )

        await page.goto(route.path)

        const breadcrumb = page.locator('.admin-breadcrumb-item.admin-breadcrumb-current')
        await expect(breadcrumb).toHaveText(route.expectedBreadcrumb)

        await expect(page.locator('.admin-layout')).toBeVisible()
        const currentPath = new URL(page.url()).pathname
        expect(currentPath.replace(/\/$/, '')).toBe(route.expectedUrl)

        const overflow = await page.evaluate(() => ({
          doc: Math.ceil(document.documentElement.scrollWidth),
          win: Math.ceil(window.innerWidth),
        }))
        expect(overflow.doc).toBeLessThanOrEqual(overflow.win + 2)
      })
    }
  }

  test('mobile sidebar collapses after route selection', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 900 })
    await page.route('**/api/**', buildApiRouteMock)
    await page.addInitScript(
      ({ adminUser }) => {
        window.localStorage.setItem('auth_token', 'smoke-token')
        window.localStorage.setItem('auth_user', JSON.stringify(adminUser))
      },
      { adminUser: defaultAdminUser }
    )

    await page.goto('/admin/operations/bookings')
    await expect(page.locator('.admin-layout')).toHaveClass(/sidebar-collapsed/)

    const sidebarToggle = page.locator('button', { hasText: '☰' })
    await expect(sidebarToggle).toBeVisible()
    await sidebarToggle.click()
    await expect(page.locator('.admin-layout')).not.toHaveClass(/sidebar-collapsed/)

    await page.getByRole('button', { name: 'Reports' }).click()
    await page.getByRole('button', { name: 'Booking Growth' }).click()

    await expect(page.locator('.admin-layout')).toHaveClass(/sidebar-collapsed/)
    expect(new URL(page.url()).pathname).toBe('/admin/reports/booking-growth')
  })

  test('tablet sidebar collapses after route selection', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 900 })
    await page.route('**/api/**', buildApiRouteMock)
    await page.addInitScript(
      ({ adminUser }) => {
        window.localStorage.setItem('auth_token', 'smoke-token')
        window.localStorage.setItem('auth_user', JSON.stringify(adminUser))
      },
      { adminUser: defaultAdminUser }
    )

    await page.goto('/admin/operations/bookings')
    await expect(page.locator('.admin-layout')).toHaveClass(/sidebar-collapsed/)

    const sidebarToggle = page.locator('button', { hasText: '☰' })
    await expect(sidebarToggle).toBeVisible()
    await sidebarToggle.click()
    await expect(page.locator('.admin-layout')).not.toHaveClass(/sidebar-collapsed/)

    await page.getByRole('button', { name: 'Reports' }).click()
    await page.getByRole('button', { name: 'Financial' }).click()

    await expect(page.locator('.admin-layout')).toHaveClass(/sidebar-collapsed/)
    expect(new URL(page.url()).pathname).toBe('/admin/reports/financial')
  })
})
