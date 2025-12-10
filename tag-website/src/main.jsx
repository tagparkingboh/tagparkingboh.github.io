import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import LandingPage from './LandingPage.jsx'
import HomePage from './HomePage.jsx'
import Bookings from './Bookings.jsx'
import PrivacyPolicy from './PrivacyPolicy.jsx'
import TermsConditions from './TermsConditions.jsx'
import RefundPolicy from './RefundPolicy.jsx'
import CookiePolicy from './CookiePolicy.jsx'
import FAQ from './FAQ.jsx'

// Toggle this to switch between Landing Page (pre-launch) and Home Page (post-launch)
const IS_LAUNCHED = true

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={IS_LAUNCHED ? <HomePage /> : <LandingPage />} />
        <Route path="/tag-it" element={<Bookings />} />
        <Route path="/privacy-policy" element={<PrivacyPolicy />} />
        <Route path="/terms-conditions" element={<TermsConditions />} />
        <Route path="/refund-policy" element={<RefundPolicy />} />
        <Route path="/cookie-policy" element={<CookiePolicy />} />
        <Route path="/faq" element={<FAQ />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
