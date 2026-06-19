import PromoModalsSection from '../PromoModalsSection'

const PromoModalsPage = ({
  promoModals,
  loadingPromoModals,
  fetchPromoModals,
  promoModalSuccessMessage,
  setEditingPromoModal,
  setPromoModalForm,
  setPromoCodeIsMultiUse,
  setSelectedPromoCodeInfo,
  setShowPromoModalForm,
  fetchPromoCodesForModal,
  openEditPromoModal,
  handleTogglePromoModalStatus,
  setPromoModalToDelete,
  setShowDeletePromoModal,
}) => (
  <PromoModalsSection
    promoModals={promoModals}
    loadingPromoModals={loadingPromoModals}
    fetchPromoModals={fetchPromoModals}
    promoModalSuccessMessage={promoModalSuccessMessage}
    setEditingPromoModal={setEditingPromoModal}
    setPromoModalForm={setPromoModalForm}
    setPromoCodeIsMultiUse={setPromoCodeIsMultiUse}
    setSelectedPromoCodeInfo={setSelectedPromoCodeInfo}
    setShowPromoModalForm={setShowPromoModalForm}
    fetchPromoCodesForModal={fetchPromoCodesForModal}
    openEditPromoModal={openEditPromoModal}
    handleTogglePromoModalStatus={handleTogglePromoModalStatus}
    setPromoModalToDelete={setPromoModalToDelete}
    setShowDeletePromoModal={setShowDeletePromoModal}
  />
)

export default PromoModalsPage
