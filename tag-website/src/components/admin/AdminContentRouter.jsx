import OperationsSectionPage from './operations/OperationsSectionPage'
import StaffSectionPage from './staff/StaffSectionPage'
import CustomersSectionPage from './customers/CustomersSectionPage'
import SubscribersPage from './marketing/SubscribersPage'
import PromotionsPage from './marketing/PromotionsPage'
import CampaignsPage from './marketing/CampaignsPage'
import ReferralsPage from './marketing/ReferralsPage'
import SourcesPage from './marketing/SourcesPage'
import SettingsSectionPage from './settings/SettingsSectionPage'
import BookingGrowthPage from './reports/BookingGrowthPage'
import OccupancyPage from './reports/OccupancyPage'
import PopularRoutesPage from './reports/PopularRoutesPage'
import LocationMapsPage from './reports/LocationMapsPage'
import FinancialsPage from './reports/FinancialsPage'
import SessionsPage from './reports/SessionsPage'
import AbandonedCartsPage from './reports/AbandonedCartsPage'
import ForecastPage from './reports/ForecastPage'
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

      {(() => {
        if (activeTab !== 'marketing') return null

        const marketingPages = {
          subscribers: SubscribersPage,
          promotions: PromotionsPage,
          campaigns: CampaignsPage,
          referrals: ReferralsPage,
          sources: SourcesPage,
        }
        const MarketingPage = marketingPages[marketingSectionProps.marketingSubTab] || SubscribersPage

        return <MarketingPage {...marketingSectionProps} />
      })()}

      {(activeTab === 'customers' || activeTab === 'leads') ? (
        <CustomersSectionPage {...customersSectionProps} />
      ) : null}

      {(activeTab === 'pricing' || activeTab === 'testimonials' || activeTab === 'promo-modals') ? (
        <SettingsSectionPage {...settingsSectionProps} />
      ) : null}

      {(() => {
        if (activeTab !== 'reports') return null

        const reportsPages = {
          growth: BookingGrowthPage,
          occupancy: OccupancyPage,
          popular: PopularRoutesPage,
          map: LocationMapsPage,
          financial: FinancialsPage,
          sessions: SessionsPage,
          analytics: AbandonedCartsPage,
          forecast: ForecastPage,
        }
        const ReportsPage = reportsPages[reportsSectionProps.reportsSubTab] || BookingGrowthPage

        return <ReportsPage {...reportsSectionProps} />
      })()}
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
