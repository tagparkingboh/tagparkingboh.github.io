import TestimonialsSection from '../TestimonialsSection'

const TestimonialsPage = ({
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
}) => (
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

export default TestimonialsPage
