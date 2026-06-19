import PricingSection from './PricingSection'
import TestimonialsSection from './TestimonialsSection'
import PromoModalsSection from './PromoModalsSection'

const SettingsSectionPage = ({
  activeTab,
  pricing,
  fetchPricing,
  pricingMessage,
  loadingPricing,
  setPricing,
  savingPricing,
  savePricing,
  testimonials,
  loadingTestimonials,
  fetchTestimonials,
  testimonialSuccessMessage,
  testimonialFilter,
  setTestimonialFilter,
  testimonialSort,
  setTestimonialSort,
  openAddTestimonialModal,
  renderStars,
  openEditTestimonialModal,
  handleToggleTestimonialStatus,
  setTestimonialToDelete,
  setShowDeleteTestimonialModal,
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
}) => {
  if (activeTab === 'pricing') {
    return (
      <PricingSection
        pricing={pricing}
        fetchPricing={fetchPricing}
        pricingMessage={pricingMessage}
        loadingPricing={loadingPricing}
        setPricing={setPricing}
        savingPricing={savingPricing}
        savePricing={savePricing}
      />
    )
  }

  if (activeTab === 'testimonials') {
    return (
      <TestimonialsSection
        testimonials={testimonials}
        loadingTestimonials={loadingTestimonials}
        fetchTestimonials={fetchTestimonials}
        testimonialSuccessMessage={testimonialSuccessMessage}
        testimonialFilter={testimonialFilter}
        setTestimonialFilter={setTestimonialFilter}
        testimonialSort={testimonialSort}
        setTestimonialSort={setTestimonialSort}
        openAddTestimonialModal={openAddTestimonialModal}
        renderStars={renderStars}
        openEditTestimonialModal={openEditTestimonialModal}
        handleToggleTestimonialStatus={handleToggleTestimonialStatus}
        setTestimonialToDelete={setTestimonialToDelete}
        setShowDeleteTestimonialModal={setShowDeleteTestimonialModal}
      />
    )
  }

  if (activeTab !== 'promo-modals') return null

  return (
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
}

export default SettingsSectionPage

