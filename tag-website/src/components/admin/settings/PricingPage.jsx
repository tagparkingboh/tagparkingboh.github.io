import PricingSection from '../PricingSection'

const PricingPage = ({
  pricing,
  fetchPricing,
  pricingMessage,
  loadingPricing,
  setPricing,
  savingPricing,
  savePricing,
}) => (
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

export default PricingPage
