import { useState, useEffect } from 'react'
import { Link, NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import './AdminLayout.css'

const NAV_STRUCTURE = [
  {
    category: 'Operations',
    icon: '📋',
    items: [
      { path: '/admin/operations/bookings', label: 'Bookings' },
      { path: '/admin/operations/manual-booking', label: 'Manual Booking' },
      { path: '/admin/operations/flights', label: 'Flights' },
    ]
  },
  {
    category: 'Staff',
    icon: '👥',
    items: [
      { path: '/admin/staff/roster', label: 'Roster' },
      { path: '/admin/staff/payroll', label: 'Payroll' },
      { path: '/admin/staff/users', label: 'Users' },
    ]
  },
  {
    category: 'Customers',
    icon: '🧑‍💼',
    items: [
      { path: '/admin/customers/list', label: 'Customers' },
      { path: '/admin/customers/leads', label: 'Abandoned Leads' },
    ]
  },
  {
    category: 'Marketing',
    icon: '📢',
    items: [
      { path: '/admin/marketing/subscribers', label: 'Subscribers' },
      { path: '/admin/marketing/promotions', label: 'Promotions' },
      { path: '/admin/marketing/sources', label: 'Sources' },
    ]
  },
  {
    category: 'Reports',
    icon: '📊',
    items: [
      { path: '/admin/reports/growth', label: 'Growth' },
      { path: '/admin/reports/occupancy', label: 'Occupancy' },
      { path: '/admin/reports/popular-routes', label: 'Popular Routes' },
      { path: '/admin/reports/map', label: 'Map' },
    ]
  },
  {
    category: 'Settings',
    icon: '⚙️',
    items: [
      { path: '/admin/settings/pricing', label: 'Pricing' },
      { path: '/admin/settings/qa', label: 'QA Dashboard' },
      { path: '/admin/settings/testimonials', label: 'Testimonials' },
    ]
  },
]

function AdminLayout() {
  const { user, loading, isAuthenticated, isAdmin, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [expandedCategories, setExpandedCategories] = useState(() => {
    // Expand the category containing the current path
    const currentPath = location.pathname
    const expanded = {}
    NAV_STRUCTURE.forEach(cat => {
      if (cat.items.some(item => currentPath.startsWith(item.path))) {
        expanded[cat.category] = true
      }
    })
    return expanded
  })

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

  // Update expanded category when route changes
  useEffect(() => {
    const currentPath = location.pathname
    NAV_STRUCTURE.forEach(cat => {
      if (cat.items.some(item => currentPath.startsWith(item.path))) {
        setExpandedCategories(prev => ({ ...prev, [cat.category]: true }))
      }
    })
  }, [location.pathname])

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const toggleCategory = (category) => {
    setExpandedCategories(prev => ({
      ...prev,
      [category]: !prev[category]
    }))
  }

  if (loading) {
    return <div className="admin-loading">Loading...</div>
  }

  if (!isAuthenticated || !isAdmin) {
    return null
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
            {NAV_STRUCTURE.map(cat => (
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
                      <NavLink
                        key={item.path}
                        to={item.path}
                        className={({ isActive }) =>
                          `nav-item ${isActive ? 'active' : ''}`
                        }
                      >
                        {item.label}
                      </NavLink>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </nav>
        </aside>

        {/* Main Content */}
        <main className="admin-main">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export default AdminLayout
