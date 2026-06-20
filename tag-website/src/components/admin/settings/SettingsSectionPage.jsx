import PricingPage from './PricingPage'
import TestimonialsPage from './TestimonialsPage'
import PromoModalsPage from './PromoModalsPage'

const SettingsSectionPage = ({
  activeTab,
  pricingSectionProps,
  testimonialsSectionProps,
  promoModalsSectionProps,
}) => {
  if (activeTab === 'pricing') {
    return <PricingPage {...pricingSectionProps} />
  }

  if (activeTab === 'testimonials') {
    return <TestimonialsPage {...testimonialsSectionProps} />
  }

  if (activeTab === 'promo-modals') {
    return <PromoModalsPage {...promoModalsSectionProps} />
  }

  return null
}

export default SettingsSectionPage
