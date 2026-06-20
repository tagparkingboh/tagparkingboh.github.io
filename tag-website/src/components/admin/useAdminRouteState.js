import { useEffect, useState } from 'react'
import {
  ADMIN_DEFAULT_ITEM_ID,
  ADMIN_DEFAULT_ROUTE,
  ADMIN_ITEM_META_BY_ID,
  NAV_STRUCTURE,
  getAdminItemIdForPath,
  getAdminItemIdForSelection,
  getAdminRouteForItem,
  getAdminSelectionForItem,
  isNavItemActiveForState,
} from './adminRouteConfig'

const useAdminRouteState = ({
  user,
  isAuthenticated,
  isAdmin,
  loading,
  locationPathname,
  navigate,
}) => {
  const requestedInitialAdminItemId = getAdminItemIdForPath(locationPathname) || ADMIN_DEFAULT_ITEM_ID
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
    window.matchMedia?.('(max-width: 1024px)').matches
  ))
  const [expandedCategories, setExpandedCategories] = useState(() => {
    const expanded = {}
    NAV_STRUCTURE.forEach(cat => {
      if (cat.items.some(item => item.id === initialAdminItemId)) {
        expanded[cat.category] = true
      }
    })
    return expanded
  })
  const [marketingSubTab, setMarketingSubTab] = useState(initialAdminSelection.marketingSubTab || 'subscribers')
  const [reportsSubTab, setReportsSubTab] = useState(initialAdminSelection.reportsSubTab || 'growth')

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

  useEffect(() => {
    if (loading || !isAuthenticated || !isAdmin) return

    const normalisedPath = (locationPathname || '').replace(/\/+$/, '') || '/admin'
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
    const canonicalRoute = getAdminRouteForItem(routeItemId)
    if (normalisedPath !== canonicalRoute) {
      navigate(canonicalRoute, { replace: true })
      return
    }

    applyAdminItemSelection(routeItemId)
  }, [loading, isAuthenticated, isAdmin, locationPathname, navigate, user?.id])

  const activeAdminItemId = getAdminItemIdForSelection(activeTab, marketingSubTab, reportsSubTab)
  const activeAdminItemMeta = ADMIN_ITEM_META_BY_ID[activeAdminItemId] || ADMIN_ITEM_META_BY_ID[ADMIN_DEFAULT_ITEM_ID]

  const toggleCategory = (categoryName) => {
    setExpandedCategories(prev => ({
      ...prev,
      [categoryName]: !prev[categoryName]
    }))
  }

  const handleTabSelect = (tabId) => {
    applyAdminItemSelection(tabId)
    navigate(getAdminRouteForItem(tabId))
    if (typeof window !== 'undefined' && window.matchMedia?.('(max-width: 1024px)').matches) {
      setSidebarCollapsed(true)
    }
  }

  const isNavItemActive = (itemId) => isNavItemActiveForState(activeTab, marketingSubTab, reportsSubTab, itemId)

  return {
    activeTab,
    setActiveTab,
    marketingSubTab,
    setMarketingSubTab,
    reportsSubTab,
    setReportsSubTab,
    sidebarCollapsed,
    setSidebarCollapsed,
    expandedCategories,
    setExpandedCategories,
    isNavItemActive,
    activeAdminItemMeta,
    activeAdminItemId,
    toggleCategory,
    handleTabSelect,
    applyAdminItemSelection,
  }
}

export default useAdminRouteState
