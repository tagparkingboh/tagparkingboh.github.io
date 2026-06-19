const UsersSection = ({
  userSuccessMessage,
  error,
  userSearchTerm,
  setUserSearchTerm,
  filteredUsers,
  loadingUsers,
  openAddUserModal,
  handleToggleUserField,
  setUserToDelete,
  setShowDeleteUserModal,
  openEditUserModal,
  showUserModal,
  setShowUserModal,
  editingUser,
  userForm,
  setUserForm,
  handleSaveUser,
  savingUser,
  showDeleteUserModal,
  userToDelete,
  handleDeleteUser,
  deletingUser,
}) => {
  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2>User Management</h2>
        <button className="action-btn paid-btn" onClick={openAddUserModal}>+ Add User</button>
      </div>

      {userSuccessMessage && (
        <div className="success-banner">{userSuccessMessage}</div>
      )}

      {error && <div className="admin-error">{error}</div>}

      <div className="admin-filters">
        <div className="admin-search">
          <input
            type="text"
            className="admin-search-input"
            placeholder="Search by name or email..."
            value={userSearchTerm}
            onChange={(e) => setUserSearchTerm(e.target.value)}
          />
          {userSearchTerm && (
            <button className="admin-search-clear" onClick={() => setUserSearchTerm('')}>&times;</button>
          )}
        </div>
        <span className="admin-filter-count">{filteredUsers.length} user{filteredUsers.length !== 1 ? 's' : ''}</span>
      </div>

      {loadingUsers ? (
        <div className="admin-loading-inline"><div className="spinner-small"></div> Loading users...</div>
      ) : filteredUsers.length === 0 ? (
        <p className="admin-empty">No users found</p>
      ) : (
        <div className="admin-table-container">
          <table className="admin-table users-table">
            <thead>
              <tr>
                <th>First Name</th>
                <th>Last Name</th>
                <th>Email</th>
                <th>Phone</th>
                <th>Admin</th>
                <th>Active</th>
                <th>Last Login</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map(u => (
                <tr key={u.id} className={!u.is_active ? 'user-inactive' : ''}>
                  <td>{u.first_name}</td>
                  <td>{u.last_name}</td>
                  <td>{u.email}</td>
                  <td>{u.phone || '-'}</td>
                  <td>
                    <button
                      className={`toggle-btn ${u.is_admin ? 'toggle-on' : 'toggle-off'}`}
                      onClick={() => handleToggleUserField(u, 'is_admin')}
                      title={u.is_admin ? 'Remove admin' : 'Make admin'}
                    >
                      {u.is_admin ? 'Yes' : 'No'}
                    </button>
                  </td>
                  <td>
                    <button
                      className={`toggle-btn ${u.is_active ? 'toggle-on' : 'toggle-off'}`}
                      onClick={() => handleToggleUserField(u, 'is_active')}
                      title={u.is_active ? 'Deactivate' : 'Activate'}
                    >
                      {u.is_active ? 'Yes' : 'No'}
                    </button>
                  </td>
                  <td className="small-text">{u.last_login ? new Date(u.last_login).toLocaleDateString('en-GB', { timeZone: 'Europe/London' }) : 'Never'}</td>
                  <td className="actions-cell">
                    <button className="action-btn email-btn" onClick={() => openEditUserModal(u)}>Edit</button>
                    <button className="action-btn cancel-btn" onClick={() => { setUserToDelete(u); setShowDeleteUserModal(true) }}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Add/Edit User Modal */}
      {showUserModal && (
        <div className="modal-overlay" onClick={() => setShowUserModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <h3>{editingUser ? 'Edit User' : 'Add User'}</h3>
            <div className="user-form">
              <div className="user-form-row">
                <div className="user-form-field">
                  <label>First Name</label>
                  <input type="text" value={userForm.first_name} onChange={e => setUserForm({...userForm, first_name: e.target.value})} />
                </div>
                <div className="user-form-field">
                  <label>Last Name</label>
                  <input type="text" value={userForm.last_name} onChange={e => setUserForm({...userForm, last_name: e.target.value})} />
                </div>
              </div>
              <div className="user-form-field">
                <label>Email</label>
                <input type="email" value={userForm.email} onChange={e => setUserForm({...userForm, email: e.target.value})} />
              </div>
              <div className="user-form-field">
                <label>Phone</label>
                <input type="text" value={userForm.phone} onChange={e => setUserForm({...userForm, phone: e.target.value})} />
              </div>
              <div className="user-form-field">
                <label>Driver Type</label>
                <select
                  value={userForm.driver_type ?? ''}
                  onChange={e => setUserForm({...userForm, driver_type: e.target.value})}
                >
                  <option value="">— (not a driver)</option>
                  <option value="jockey">Jockey</option>
                  <option value="fleet">Fleet</option>
                </select>
              </div>
              <div className="user-form-toggles">
                <label className="admin-checkbox-label">
                  <input
                    type="checkbox"
                    checked={userForm.is_admin}
                    onChange={e => {
                      const isAdmin = e.target.checked
                      // Add-User flow: flip the driver_type default along with the
                      // admin toggle (admin = no driver_type, non-admin = fleet).
                      // Don't overwrite a value the admin already chose, and never
                      // mutate driver_type when editing an existing user.
                      if (!editingUser) {
                        const defaulted = userForm.driver_type === (isAdmin ? 'fleet' : '')
                        if (defaulted) {
                          setUserForm({ ...userForm, is_admin: isAdmin, driver_type: isAdmin ? '' : 'fleet' })
                          return
                        }
                      }
                      setUserForm({ ...userForm, is_admin: isAdmin })
                    }}
                  />
                  Admin
                </label>
                <label className="admin-checkbox-label">
                  <input type="checkbox" checked={userForm.is_active} onChange={e => setUserForm({...userForm, is_active: e.target.checked})} />
                  Active
                </label>
              </div>
            </div>
            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={() => setShowUserModal(false)}>Cancel</button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={handleSaveUser}
                disabled={savingUser || !userForm.first_name.trim() || !userForm.last_name.trim() || !userForm.email.trim()}
              >
                {savingUser ? 'Saving...' : (editingUser ? 'Update' : 'Create')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete User Confirmation Modal */}
      {showDeleteUserModal && userToDelete && (
        <div className="modal-overlay" onClick={() => setShowDeleteUserModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <h3>Delete User</h3>
            <p>Are you sure you want to delete <strong>{userToDelete.first_name} {userToDelete.last_name}</strong> ({userToDelete.email})?</p>
            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={() => setShowDeleteUserModal(false)}>Cancel</button>
              <button className="modal-btn modal-btn-danger" onClick={handleDeleteUser} disabled={deletingUser}>
                {deletingUser ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default UsersSection
