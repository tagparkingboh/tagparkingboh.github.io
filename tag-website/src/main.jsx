import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import './index.css'
import LandingPage from './LandingPage.jsx'
import HomePage from './HomePage.jsx'
import Bookings from './Bookings.jsx'
import BookingsNew from './BookingsNew.jsx'
import PrivacyPolicy from './PrivacyPolicy.jsx'
import TermsConditions from './TermsConditions.jsx'
import RefundPolicy from './RefundPolicy.jsx'
import CookiePolicy from './CookiePolicy.jsx'
import VehicleInspectionTerms from './VehicleInspectionTerms.jsx'
import FAQ from './FAQ.jsx'
import Login from './Login.jsx'
import Employee from './Employee.jsx'
import { AuthProvider } from './AuthContext.jsx'

// Admin Layout and Pages
import AdminLayout from './admin/AdminLayout.jsx'
import BookingsPage from './admin/pages/BookingsPage.jsx'
import ManualBookingPage from './admin/pages/ManualBookingPage.jsx'
import FlightsPage from './admin/pages/FlightsPage.jsx'
import RosterPage from './admin/pages/RosterPage.jsx'
import PayrollPage from './admin/pages/PayrollPage.jsx'
import UsersPage from './admin/pages/UsersPage.jsx'
import CustomersPage from './admin/pages/CustomersPage.jsx'
import LeadsPage from './admin/pages/LeadsPage.jsx'
import SubscribersPage from './admin/pages/SubscribersPage.jsx'
import PromotionsPage from './admin/pages/PromotionsPage.jsx'
import SourcesPage from './admin/pages/SourcesPage.jsx'
import GrowthPage from './admin/pages/GrowthPage.jsx'
import OccupancyPage from './admin/pages/OccupancyPage.jsx'
import PopularRoutesPage from './admin/pages/PopularRoutesPage.jsx'
import MapPage from './admin/pages/MapPage.jsx'
import PricingPage from './admin/pages/PricingPage.jsx'
import QAPage from './admin/pages/QAPage.jsx'
import TestimonialsPage from './admin/pages/TestimonialsPage.jsx'

// Toggle this to switch between Landing Page (pre-launch) and Home Page (post-launch)
const IS_LAUNCHED = true

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={IS_LAUNCHED ? <HomePage /> : <LandingPage />} />
          <Route path="/tag-it" element={<BookingsNew />} />
          <Route path="/book-original" element={<Bookings />} />  {/* Original 6-part flow for A/B testing */}
          <Route path="/privacy-policy" element={<PrivacyPolicy />} />
          <Route path="/terms-conditions" element={<TermsConditions />} />
          <Route path="/refund-policy" element={<RefundPolicy />} />
          <Route path="/cookie-policy" element={<CookiePolicy />} />
          <Route path="/vehicle-inspection-terms" element={<VehicleInspectionTerms />} />
          <Route path="/faq" element={<FAQ />} />
          <Route path="/login" element={<Login />} />
          <Route path="/employee" element={<Employee />} />

          {/* Admin Routes */}
          <Route path="/admin" element={<AdminLayout />}>
            {/* Default redirect to bookings */}
            <Route index element={<Navigate to="/admin/operations/bookings" replace />} />

            {/* Operations */}
            <Route path="operations/bookings" element={<BookingsPage />} />
            <Route path="operations/manual-booking" element={<ManualBookingPage />} />
            <Route path="operations/flights" element={<FlightsPage />} />

            {/* Staff */}
            <Route path="staff/roster" element={<RosterPage />} />
            <Route path="staff/payroll" element={<PayrollPage />} />
            <Route path="staff/users" element={<UsersPage />} />

            {/* Customers */}
            <Route path="customers/list" element={<CustomersPage />} />
            <Route path="customers/leads" element={<LeadsPage />} />

            {/* Marketing */}
            <Route path="marketing/subscribers" element={<SubscribersPage />} />
            <Route path="marketing/promotions" element={<PromotionsPage />} />
            <Route path="marketing/sources" element={<SourcesPage />} />

            {/* Reports */}
            <Route path="reports/growth" element={<GrowthPage />} />
            <Route path="reports/occupancy" element={<OccupancyPage />} />
            <Route path="reports/popular-routes" element={<PopularRoutesPage />} />
            <Route path="reports/map" element={<MapPage />} />

            {/* Settings */}
            <Route path="settings/pricing" element={<PricingPage />} />
            <Route path="settings/qa" element={<QAPage />} />
            <Route path="settings/testimonials" element={<TestimonialsPage />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
