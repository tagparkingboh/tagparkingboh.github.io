import PayrollSection from './PayrollSection'
import UsersSection from './UsersSection'

const StaffSectionPage = ({
  activeTab,
  token,
  userSuccessMessage,
  error,
  userSearchTerm,
  setUserSearchTerm,
  filteredUsers,
  loadingUsers,
  openAddUserModal,
  openEditUserModal,
  handleToggleUserField,
  setUserToDelete,
  setShowDeleteUserModal,
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
  if (activeTab === 'payroll') {
    return <PayrollSection token={token} />
  }

  if (activeTab !== 'users') return null

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

export default StaffSectionPage

