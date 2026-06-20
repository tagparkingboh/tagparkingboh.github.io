import OperationsSectionPage from './operations/OperationsSectionPage'
import StaffSectionPage from './staff/StaffSectionPage'
import MarketingSectionPage from './marketing/MarketingSectionPage'
import CustomersSectionPage from './customers/CustomersSectionPage'
import SettingsSectionPage from './settings/SettingsSectionPage'
import ReportsSectionPage from './reports/ReportsSectionPage'
import QASectionPage from './QASectionPage'
import { AdminBreadcrumbs } from './AdminShell'

const AdminContentRouter = ({
  adminDefaultRoute,
  activeAdminItemMeta,
  getDefaultRouteForCategory,
  error,
  successMessage,
  activeTab,
  bookingsPageProps,
  calendarPageProps,
  manualBookingPageProps,
  flightsPageProps,
  messagesPageProps,
  staffSectionProps,
  marketingSectionProps,
  customersSectionProps,
  settingsSectionProps,
  reportsSectionProps,
  qaSectionProps,
  bookingsScrollTopVisible,
  handleScrollToTop,
}) => {
  return (
    <>
      <AdminBreadcrumbs
        adminDefaultRoute={adminDefaultRoute}
        activeAdminItemMeta={activeAdminItemMeta}
        getDefaultRouteForCategory={getDefaultRouteForCategory}
      />
      {error && <div className="admin-error">{error}</div>}
      {successMessage && <div className="admin-success">{successMessage}</div>}

      <OperationsSectionPage
        activeTab={activeTab}
        bookingsPageProps={bookingsPageProps}
        calendarPageProps={calendarPageProps}
        manualBookingPageProps={manualBookingPageProps}
        flightsPageProps={flightsPageProps}
        messagesPageProps={messagesPageProps}
      />

      {activeTab === 'payroll' || activeTab === 'users' ? (
        <StaffSectionPage {...staffSectionProps} />
      ) : null}

      <MarketingSectionPage {...marketingSectionProps} />

      {(activeTab === 'customers' || activeTab === 'leads') ? (
        <CustomersSectionPage {...customersSectionProps} />
      ) : null}

      {(activeTab === 'pricing' || activeTab === 'testimonials' || activeTab === 'promo-modals') ? (
        <SettingsSectionPage {...settingsSectionProps} />
      ) : null}

      <ReportsSectionPage {...reportsSectionProps} />

      <QASectionPage {...qaSectionProps} />

      {activeTab === 'bookings' && bookingsScrollTopVisible && (
        <button
          type="button"
          className="bookings-scroll-top"
          onClick={handleScrollToTop}
          aria-label="Scroll to top"
          title="Back to top"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <path d="M17 14l-5-5-5 5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"></path>
          </svg>
        </button>
      )}
    </>
  )
}

export default AdminContentRouter
