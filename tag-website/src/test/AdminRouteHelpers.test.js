import { describe, it, expect } from 'vitest'
import {
  getAdminItemIdForPath,
  getAdminSelectionForItem,
  getAdminItemIdForSelection,
  getAdminRouteForItem,
  getDefaultRouteForCategory,
  ADMIN_DEFAULT_ROUTE,
} from '../Admin'

describe('admin route helpers', () => {
  it('maps canonical admin route paths to item ids', () => {
    expect(getAdminItemIdForPath('/admin')).toBe('bookings')
    expect(getAdminItemIdForPath('/admin/operations/bookings')).toBe('bookings')
    expect(getAdminItemIdForPath('/admin/operations/calendar')).toBe('calendar')
    expect(getAdminItemIdForPath('/admin/staff/users')).toBe('users')
    expect(getAdminItemIdForPath('/admin/customers/abandoned-leads')).toBe('leads')
    expect(getAdminItemIdForPath('/admin/marketing/email-campaigns')).toBe('campaigns')
    expect(getAdminItemIdForPath('/admin/reports/booking-growth')).toBe('reports-growth')
    expect(getAdminItemIdForPath('/admin/qa/roster-planner')).toBe('qa-roster-planner')
  })

  it('normalizes trailing slashes', () => {
    expect(getAdminItemIdForPath('/admin/operations/bookings/')).toBe('bookings')
    expect(getAdminItemIdForPath('/admin/reports/location-maps/')).toBe('reports-map')
    expect(getAdminItemIdForPath('/admin/qa/connection-pool/')).toBe('qa-connection-pool')
  })

  it('returns null for unknown admin paths', () => {
    expect(getAdminItemIdForPath('/admin/not-a-section')).toBeNull()
    expect(getAdminItemIdForPath('/random/path')).toBeNull()
  })

  it('derives route item selections from item ids', () => {
    expect(getAdminSelectionForItem('bookings')).toEqual({ activeTab: 'bookings' })
    expect(getAdminSelectionForItem('campaigns')).toEqual({
      activeTab: 'marketing',
      marketingSubTab: 'campaigns',
    })
    expect(getAdminSelectionForItem('reports-forecast')).toEqual({
      activeTab: 'reports',
      reportsSubTab: 'forecast',
    })
    expect(getAdminSelectionForItem('leads')).toEqual({
      activeTab: 'leads',
    })
  })

  it('inverts selection back to item ids', () => {
    expect(getAdminItemIdForSelection('bookings')).toBe('bookings')
    expect(getAdminItemIdForSelection('marketing', 'subscribers')).toBe('marketing')
    expect(getAdminItemIdForSelection('marketing', 'campaigns')).toBe('campaigns')
    expect(getAdminItemIdForSelection('reports', null, 'financial')).toBe('reports-financial')
    expect(getAdminItemIdForSelection('reports', null, 'popular')).toBe('reports-routes')
  })

  it('reconstructs default routes from item and category metadata', () => {
    expect(getAdminRouteForItem('bookings')).toBe('/admin/operations/bookings')
    expect(getAdminRouteForItem('qa-tests')).toBe('/admin/qa/test-results')
    expect(getDefaultRouteForCategory('Operations')).toBe('/admin/operations/bookings')
    expect(getDefaultRouteForCategory('QA')).toBe('/admin/qa/test-results')
    expect(getDefaultRouteForCategory('Unknown')).toBe(ADMIN_DEFAULT_ROUTE)
  })
})
