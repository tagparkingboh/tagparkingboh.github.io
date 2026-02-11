import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
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
import Admin from './Admin.jsx'
import Employee from './Employee.jsx'
import { AuthProvider } from './AuthContext.jsx'

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
          <Route path="/admin" element={<Admin />} />
          <Route path="/employee" element={<Employee />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
