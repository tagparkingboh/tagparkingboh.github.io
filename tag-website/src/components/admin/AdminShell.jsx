import { Link } from 'react-router-dom'

const AdminSidebar = ({
  navStructure,
  user,
  expandedCategories,
  sidebarCollapsed,
  onToggleCategory,
  onSelectItem,
  isItemActive,
}) => {
  return (
    <aside className="admin-sidebar">
      <nav className="admin-sidebar-nav">
        {navStructure
          .filter((cat) => {
            if (!cat.restrictToUserIds) return true
            const userId = user?.id
            return cat.restrictToUserIds.includes(userId)
          })
          .map((cat) => (
            <div key={cat.category} className="nav-category">
              <button
                className={`nav-category-header ${expandedCategories[cat.category] ? 'expanded' : ''}`}
                onClick={() => onToggleCategory(cat.category)}
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
                  {cat.items.map((item) => (
                    <button
                      key={item.id}
                      className={`nav-item ${isItemActive(item.id) ? 'active' : ''}`}
                      onClick={() => onSelectItem(item.id)}
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
  )
}

const AdminBreadcrumbs = ({
  adminDefaultRoute,
  activeAdminItemMeta,
  getDefaultRouteForCategory,
}) => {
  return (
    <nav className="admin-breadcrumbs" aria-label="Admin breadcrumb">
      <ol className="admin-breadcrumb-list">
        <li className="admin-breadcrumb-item">
          <Link to={adminDefaultRoute} className="admin-breadcrumb-link">
            <span className="admin-breadcrumb-icon" aria-hidden="true">⌂</span>
            <span>Admin</span>
          </Link>
        </li>
        <li className="admin-breadcrumb-separator" aria-hidden="true">›</li>
        <li className="admin-breadcrumb-item">
          <Link
            to={getDefaultRouteForCategory(activeAdminItemMeta.category)}
            className="admin-breadcrumb-link"
          >
            {activeAdminItemMeta.category}
          </Link>
        </li>
        <li className="admin-breadcrumb-separator" aria-hidden="true">›</li>
        <li className="admin-breadcrumb-item admin-breadcrumb-current" aria-current="page">
          {activeAdminItemMeta.itemLabel}
        </li>
      </ol>
    </nav>
  )
}

export { AdminSidebar, AdminBreadcrumbs }
