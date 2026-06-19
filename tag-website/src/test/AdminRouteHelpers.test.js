import { describe, it, expect } from 'vitest'
import {
  getAdminItemIdForPath,
  getAdminSelectionForItem,
  getAdminItemIdForSelection,
  getAdminRouteForItem,
  getDefaultRouteForCategory,
  ADMIN_ITEM_META,
  ADMIN_ITEM_META_BY_ID,
  NAV_STRUCTURE,
  ADMIN_ITEM_BY_ROUTE,
  ADMIN_DEFAULT_ROUTE,
  ADMIN_DEFAULT_ITEM_ID,
  ADMIN_ROUTE_BY_ITEM_ID,
  isNavItemActiveForState,
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
    expect(getAdminItemIdForPath('/admin/operations')).toBeNull()
    expect(getAdminItemIdForPath('/admin/reports')).toBeNull()
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

  it('keeps route mapping and metadata consistent', () => {
    const itemMetaIds = new Set(ADMIN_ITEM_META.map(item => item.itemId))
    for (const [itemId, route] of Object.entries(ADMIN_ROUTE_BY_ITEM_ID)) {
      expect(ADMIN_ITEM_BY_ROUTE[route]).toBe(itemId)
      expect(itemMetaIds.has(itemId)).toBe(true)
    }
    for (const [route, itemId] of Object.entries(ADMIN_ITEM_BY_ROUTE)) {
      expect(ADMIN_ROUTE_BY_ITEM_ID[itemId]).toBe(route)
      expect(itemMetaIds.has(itemId)).toBe(true)
    }
    expect(ADMIN_ITEM_META_BY_ID[ADMIN_DEFAULT_ITEM_ID].route).toBe(ADMIN_DEFAULT_ROUTE)
  })

  it('has one item per nav entry and no duplicate nav ids', () => {
    const navItemIds = NAV_STRUCTURE.flatMap(category => category.items.map(item => item.id))
    expect(new Set(navItemIds).size).toBe(navItemIds.length)
    for (const itemId of navItemIds) {
      expect(Object.prototype.hasOwnProperty.call(ADMIN_ROUTE_BY_ITEM_ID, itemId)).toBe(true)
    }
  })

  it('identifies active nav item for standard section tabs', () => {
    expect(isNavItemActiveForState('bookings', null, null, 'bookings')).toBe(true)
    expect(isNavItemActiveForState('calendar', null, null, 'calendar')).toBe(true)
    expect(isNavItemActiveForState('bookings', null, null, 'calendar')).toBe(false)
  })

  it('identifies active nav item for marketing nested tabs', () => {
    expect(isNavItemActiveForState('marketing', 'subscribers', null, 'marketing')).toBe(true)
    expect(isNavItemActiveForState('marketing', 'campaigns', null, 'campaigns')).toBe(true)
    expect(isNavItemActiveForState('marketing', 'campaigns', null, 'marketing')).toBe(false)
  })

  it('identifies active nav item for reports nested tabs', () => {
    expect(isNavItemActiveForState('reports', null, 'financial', 'reports-financial')).toBe(true)
    expect(isNavItemActiveForState('reports', null, 'popular', 'reports-routes')).toBe(true)
    expect(isNavItemActiveForState('reports', null, 'financial', 'reports-growth')).toBe(false)
  })
})
