import PromoModalsModals from './settings/PromoModalsModals'
import TestimonialsModals from './settings/TestimonialsModals'
import AdminModals from './AdminModals'

const AdminOverlayLayers = ({
  settingsModalsProps,
  bookingModalsProps,
}) => {
  return (
    <>
      <PromoModalsModals {...settingsModalsProps} />
      <TestimonialsModals {...settingsModalsProps} />
      <AdminModals {...bookingModalsProps} />
    </>
  )
}

export default AdminOverlayLayers
