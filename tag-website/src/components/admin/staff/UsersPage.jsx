import { useEffect, useMemo, useState } from 'react'
import UsersSection from '../UsersSection'

const UsersPage = ({ API_URL, token }) => {
  const [users, setUsers] = useState([])
  const [loadingUsers, setLoadingUsers] = useState(false)
  const [userSearchTerm, setUserSearchTerm] = useState('')
  const [showUserModal, setShowUserModal] = useState(false)
  const [editingUser, setEditingUser] = useState(null)
  const [userForm, setUserForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    is_admin: false,
    is_active: true,
    driver_type: 'fleet',
  })
  const [savingUser, setSavingUser] = useState(false)
  const [showDeleteUserModal, setShowDeleteUserModal] = useState(false)
  const [userToDelete, setUserToDelete] = useState(null)
  const [deletingUser, setDeletingUser] = useState(false)
  const [userSuccessMessage, setUserSuccessMessage] = useState('')
  const [error, setError] = useState('')

  const fetchUsers = async () => {
    if (!token) return
    setLoadingUsers(true)
    setError('')
    try {
      const response = await fetch(`${API_URL}/api/admin/users`, {
        headers: { 'Authorization': `Bearer ${token}` },
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
      setLoadingUsers(false)
    }
  }

  const openAddUserModal = () => {
    setEditingUser(null)
    setUserForm({ first_name: '', last_name: '', email: '', phone: '', is_admin: false, is_active: true, driver_type: 'fleet' })
    setShowUserModal(true)
  }

  const openEditUserModal = (user) => {
    setEditingUser(user)
    setUserForm({
      first_name: user.first_name || '',
      last_name: user.last_name || '',
      email: user.email || '',
      phone: user.phone || '',
      is_admin: user.is_admin,
      is_active: user.is_active,
      driver_type: user.driver_type ?? '',
    })
    setShowUserModal(true)
  }

  const handleSaveUser = async () => {
    if (!token) return
    setSavingUser(true)
    setError('')
    try {
      const url = editingUser
        ? `${API_URL}/api/admin/users/${editingUser.id}`
        : `${API_URL}/api/admin/users`
      const method = editingUser ? 'PUT' : 'POST'
      const payload = {
        ...userForm,
        driver_type: userForm.driver_type === '' ? null : userForm.driver_type,
      }
      const response = await fetch(url, {
        method,
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })
      if (response.ok) {
        setShowUserModal(false)
        setUserSuccessMessage(editingUser ? 'User updated successfully' : 'User created successfully')
        setTimeout(() => setUserSuccessMessage(''), 3000)
        fetchUsers()
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to save user')
      }
    } catch (err) {
      setError('Network error saving user')
    } finally {
      setSavingUser(false)
    }
  }

  const handleToggleUserField = async (userRecord, field) => {
    if (!token) return
    try {
      const response = await fetch(`${API_URL}/api/admin/users/${userRecord.id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ [field]: !userRecord[field] }),
      })
      if (response.ok) {
        fetchUsers()
      } else {
        const data = await response.json()
        setError(data.detail || `Failed to update ${field}`)
      }
    } catch (err) {
      setError(`Network error updating ${field}`)
    }
  }

  const handleDeleteUser = async () => {
    if (!userToDelete || !token) return
    setDeletingUser(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/users/${userToDelete.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        setShowDeleteUserModal(false)
        setUserToDelete(null)
        setUserSuccessMessage('User deleted successfully')
        setTimeout(() => setUserSuccessMessage(''), 3000)
        fetchUsers()
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to delete user')
      }
    } catch (err) {
      setError('Network error deleting user')
    } finally {
      setDeletingUser(false)
    }
  }

  const filteredUsers = useMemo(() => {
    if (!userSearchTerm) return users
    const term = userSearchTerm.toLowerCase()
    return users.filter(user =>
      (user.first_name || '').toLowerCase().includes(term) ||
      (user.last_name || '').toLowerCase().includes(term) ||
      (user.email || '').toLowerCase().includes(term)
    )
  }, [users, userSearchTerm])

  useEffect(() => {
    fetchUsers()
  }, [token])

  return (
    <UsersSection
      userSuccessMessage={userSuccessMessage}
      error={error}
      userSearchTerm={userSearchTerm}
      setUserSearchTerm={setUserSearchTerm}
      filteredUsers={filteredUsers}
      loadingUsers={loadingUsers}
      openAddUserModal={openAddUserModal}
      openEditUserModal={openEditUserModal}
      handleToggleUserField={handleToggleUserField}
      setUserToDelete={setUserToDelete}
      setShowDeleteUserModal={setShowDeleteUserModal}
      showUserModal={showUserModal}
      setShowUserModal={setShowUserModal}
      editingUser={editingUser}
      userForm={userForm}
      setUserForm={setUserForm}
      handleSaveUser={handleSaveUser}
      savingUser={savingUser}
      showDeleteUserModal={showDeleteUserModal}
      userToDelete={userToDelete}
      handleDeleteUser={handleDeleteUser}
      deletingUser={deletingUser}
    />
  )
}

export default UsersPage
