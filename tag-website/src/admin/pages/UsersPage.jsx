import { useState, useEffect, useMemo } from 'react'
import { useAuth } from '../../AuthContext'
import { API_URL } from '../adminUtils'
import './UsersPage.css'

function UsersPage() {
  const { token } = useAuth()

  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [searchTerm, setSearchTerm] = useState('')

  // Modal states
  const [showModal, setShowModal] = useState(false)
  const [editingUser, setEditingUser] = useState(null)
  const [userForm, setUserForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    is_admin: false,
    is_active: true
  })
  const [saving, setSaving] = useState(false)

  // Delete modal
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [userToDelete, setUserToDelete] = useState(null)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    if (token) fetchUsers()
  }, [token])

  const fetchUsers = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${API_URL}/api/admin/users`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        const data = await response.json()
        setUsers(data.users || [])
      } else {
        setError('Failed to load users')
      }
    } catch (err) {
      setError('Network error loading users')
    } finally {
      setLoading(false)
    }
  }

  const filteredUsers = useMemo(() => {
    if (!searchTerm) return users
    const term = searchTerm.toLowerCase()
    return users.filter(u =>
      (u.first_name || '').toLowerCase().includes(term) ||
      (u.last_name || '').toLowerCase().includes(term) ||
      (u.email || '').toLowerCase().includes(term)
    )
  }, [users, searchTerm])

  const openAddModal = () => {
    setEditingUser(null)
    setUserForm({ first_name: '', last_name: '', email: '', phone: '', is_admin: false, is_active: true })
    setShowModal(true)
  }

  const openEditModal = (u) => {
    setEditingUser(u)
    setUserForm({
      first_name: u.first_name || '',
      last_name: u.last_name || '',
      email: u.email || '',
      phone: u.phone || '',
      is_admin: u.is_admin,
      is_active: u.is_active,
    })
    setShowModal(true)
  }

  const handleSave = async () => {
    setSaving(true)
    setError('')
    try {
      const url = editingUser
        ? `${API_URL}/api/admin/users/${editingUser.id}`
        : `${API_URL}/api/admin/users`
      const method = editingUser ? 'PUT' : 'POST'
      const response = await fetch(url, {
        method,
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(userForm),
      })
      if (response.ok) {
        setShowModal(false)
        setSuccessMessage(editingUser ? 'User updated successfully' : 'User created successfully')
        setTimeout(() => setSuccessMessage(''), 3000)
        fetchUsers()
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to save user')
      }
    } catch (err) {
      setError('Network error saving user')
    } finally {
      setSaving(false)
    }
  }

  const handleToggleField = async (u, field) => {
    try {
      const response = await fetch(`${API_URL}/api/admin/users/${u.id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ [field]: !u[field] }),
      })
      if (response.ok) {
        fetchUsers()
      } else {
        const data = await response.json()
        setError(data.detail || `Failed to update ${field}`)
        setTimeout(() => setError(''), 3000)
      }
    } catch (err) {
      setError(`Network error updating ${field}`)
    }
  }

  const handleDelete = async () => {
    if (!userToDelete) return
    setDeleting(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/users/${userToDelete.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        setShowDeleteModal(false)
        setUserToDelete(null)
        setSuccessMessage('User deleted successfully')
        setTimeout(() => setSuccessMessage(''), 3000)
        fetchUsers()
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to delete user')
      }
    } catch (err) {
      setError('Network error deleting user')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h2>User Management</h2>
        <button className="btn-primary" onClick={openAddModal}>+ Add User</button>
      </div>

      {successMessage && <div className="admin-success">{successMessage}</div>}
      {error && <div className="admin-error">{error}</div>}

      <div className="admin-filters">
        <div className="admin-search">
          <input
            type="text"
            className="admin-search-input"
            placeholder="Search by name or email..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          {searchTerm && (
            <button className="admin-search-clear" onClick={() => setSearchTerm('')}>&times;</button>
          )}
        </div>
        <span className="admin-filter-count">{filteredUsers.length} user{filteredUsers.length !== 1 ? 's' : ''}</span>
      </div>

      {loading ? (
        <div className="admin-loading-inline">Loading users...</div>
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
                      onClick={() => handleToggleField(u, 'is_admin')}
                      title={u.is_admin ? 'Remove admin' : 'Make admin'}
                    >
                      {u.is_admin ? 'Yes' : 'No'}
                    </button>
                  </td>
                  <td>
                    <button
                      className={`toggle-btn ${u.is_active ? 'toggle-on' : 'toggle-off'}`}
                      onClick={() => handleToggleField(u, 'is_active')}
                      title={u.is_active ? 'Deactivate' : 'Activate'}
                    >
                      {u.is_active ? 'Yes' : 'No'}
                    </button>
                  </td>
                  <td className="small-text">
                    {u.last_login ? new Date(u.last_login).toLocaleDateString('en-GB', { timeZone: 'Europe/London' }) : 'Never'}
                  </td>
                  <td className="actions-cell">
                    <button className="btn-secondary btn-sm" onClick={() => openEditModal(u)}>Edit</button>
                    <button className="btn-danger btn-sm" onClick={() => { setUserToDelete(u); setShowDeleteModal(true) }}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Add/Edit User Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
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
              <div className="user-form-toggles">
                <label className="checkbox-label">
                  <input type="checkbox" checked={userForm.is_admin} onChange={e => setUserForm({...userForm, is_admin: e.target.checked})} />
                  Admin
                </label>
                <label className="checkbox-label">
                  <input type="checkbox" checked={userForm.is_active} onChange={e => setUserForm({...userForm, is_active: e.target.checked})} />
                  Active
                </label>
              </div>
            </div>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setShowModal(false)}>Cancel</button>
              <button
                className="btn-primary"
                onClick={handleSave}
                disabled={saving || !userForm.first_name.trim() || !userForm.last_name.trim() || !userForm.email.trim()}
              >
                {saving ? 'Saving...' : (editingUser ? 'Update' : 'Create')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete User Confirmation Modal */}
      {showDeleteModal && userToDelete && (
        <div className="modal-overlay" onClick={() => setShowDeleteModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <h3>Delete User</h3>
            <p>Are you sure you want to delete <strong>{userToDelete.first_name} {userToDelete.last_name}</strong> ({userToDelete.email})?</p>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setShowDeleteModal(false)}>Cancel</button>
              <button className="btn-danger" onClick={handleDelete} disabled={deleting}>
                {deleting ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default UsersPage
