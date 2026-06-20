import { Link } from 'react-router-dom'
import { AdminSidebar } from './AdminShell'

const AdminShellLayout = ({
  user,
  sidebarCollapsed,
  onToggleSidebar,
  onLogout,
  navStructure,
  expandedCategories,
  onToggleCategory,
  onSelectItem,
  isItemActive,
  children,
}) => {
  return (
    <div className={`admin-layout ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <header className="admin-header">
        <div className="admin-header-left">
          <button
            className="sidebar-toggle"
            onClick={onToggleSidebar}
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
          <button onClick={onLogout} className="admin-logout">
            Logout
          </button>
        </div>
      </header>

      <div className="admin-body">
        <AdminSidebar
          navStructure={navStructure}
          user={user}
          expandedCategories={expandedCategories}
          sidebarCollapsed={sidebarCollapsed}
          onToggleCategory={onToggleCategory}
          onSelectItem={onSelectItem}
          isItemActive={isItemActive}
        />

        <main className="admin-main">
          {children}
        </main>
      </div>
    </div>
  )
}

export default AdminShellLayout
