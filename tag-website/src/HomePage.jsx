import { useState } from 'react'
import { Link } from 'react-router-dom'
import './App.css'

function HomePage() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [openFaq, setOpenFaq] = useState(null)
  const [openFooter, setOpenFooter] = useState(null)
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitStatus, setSubmitStatus] = useState(null) // 'success' | 'error' | null

  const isValidEmail = (email) => {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
  }

  const isFormValid = firstName.trim() && lastName.trim() && isValidEmail(email)

  const handleSubscribe = async () => {
    if (!isFormValid || isSubmitting) return

    setIsSubmitting(true)
    setSubmitStatus(null)

    const portalId = import.meta.env.VITE_HUBSPOT_PORTAL_ID
    const formId = import.meta.env.VITE_HUBSPOT_FORM_ID
    const hubspotUrl = `https://api.hsforms.com/submissions/v3/integration/submit/${portalId}/${formId}`

    const payload = {
      fields: [
        { name: 'firstname', value: firstName.trim() },
        { name: 'lastname', value: lastName.trim() },
        { name: 'email', value: email.trim() },
      ],
      context: {
        pageUri: window.location.href,
        pageName: 'Tag Parking - Subscribe',
      },
    }

    console.log('HubSpot Request:', JSON.stringify(payload, null, 2))

    try {
      const response = await fetch(hubspotUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })

      const responseData = await response.json().catch(() => null)
      console.log('HubSpot Response:', response.status, responseData)

      if (response.ok) {
        setSubmitStatus('success')
        setFirstName('')
        setLastName('')
        setEmail('')
      } else {
        console.error('HubSpot Error:', response.status, responseData)
        setSubmitStatus('error')
      }
    } catch (error) {
      console.error('Submit Error:', error)
      setSubmitStatus('error')
    } finally {
      setIsSubmitting(false)
    }
  }

  const toggleMenu = () => {
    setMenuOpen(!menuOpen)
  }

  const closeMenu = () => {
    setMenuOpen(false)
  }

  const toggleFaq = (index) => {
    setOpenFaq(openFaq === index ? null : index)
  }

  const toggleFooter = (index) => {
    setOpenFooter(openFooter === index ? null : index)
  }

  return (
    <div className="app">
      {/* Header/Nav */}
      <header className="header">
        <nav className="nav">
          <div className="logo">
            <img src="/assets/logo.svg" alt="TAG - Book it. Bag it. Tag it." className="logo-svg" />
          </div>
          <button className={`hamburger ${menuOpen ? 'open' : ''}`} onClick={toggleMenu} aria-label="Toggle menu">
            <span></span>
            <span></span>
            <span></span>
          </button>
          <ul className={`nav-links ${menuOpen ? 'open' : ''}`}>
            <li><a href="#how-it-works" onClick={closeMenu}>Meet & Greet</a></li>
            <li><a href="#pricing" onClick={closeMenu}>Pricing</a></li>
            <li><a href="#subscribe" onClick={closeMenu}>Subscribe</a></li>
            <li><a href="#contact" onClick={closeMenu}>Contact</a></li>
          </ul>
        </nav>
      </header>

      {/* Hero Section */}
      <section className="hero" id="hero">
        <div className="hero-content">
          <div className="hero-text">
            <p className="hero-subtitle">TAG: THE NEW WAY TO MEET AND GREET</p>
            <h1 className="hero-title">Enjoy peace of mind from<br />Palma to Paphos</h1>
          </div>

          <div className="hero-cta-group">
            <div className="intro-offer-banner">
              <span className="intro-offer-discount">10% off</span>
              <span className="intro-offer-text">for subscribers – register your interest below</span>
            </div>

            <a href="#subscribe" className="hero-cta">Subscribe</a>
          </div>

          <a href="#subscribe" className="scroll-indicator">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M7 10l5 5 5-5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </a>
        </div>
      </section>

      {/* Availability Tracker - hidden, will be moved to /tag-it page */}
      {/* <AvailabilityTracker /> */}

      {/* Features Banner Section */}
      <section className="features-banner">
        <div className="features-content">
          <div className="feature">
            <h2>50%</h2>
            <p>Save up to 50% off<br />official airport parking</p>
          </div>
          <div className="feature">
            <h2>£0</h2>
            <p>Zero parking fees:<br />everything's included</p>
          </div>
          <div className="feature">
            <h2>24/7</h2>
            <p>Security monitoring at<br />storage site</p>
          </div>
          <div className="feature">
            <h2>5 mins</h2>
            <p>5 minute average<br />handover time</p>
          </div>
          <div className="feature">
            <h2>Money back Guarantee</h2>
            <p>Your car will never leave<br />our secure car park</p>
          </div>
          <div className="feature">
            <h2>Park Mark certified</h2>
            <p>Approved for safer parking<br />by the Police</p>
          </div>
        </div>
        <div className="features-bottom-bar"></div>
      </section>

      {/* How TAG Works */}
      <section className="how-it-works" id="how-it-works">
        <h2>How Tag works for you.</h2>
        <div className="steps-cards">
          <div className="step-card">
            <div className="step-card-image">
              <img src="/assets/step-1.png" alt="Meet us at departures" />
            </div>
          </div>
          <div className="step-card">
            <div className="step-card-image">
              <img src="/assets/step-2.png" alt="Enjoy your trip" />
            </div>
          </div>
          <div className="step-card">
            <div className="step-card-image">
              <img src="/assets/step-3.png" alt="Pick up where you left off" />
            </div>
          </div>
        </div>
      </section>

      {/* Why Choose TAG Section */}
      <section className="why-choose">
        <div className="why-content">
          <h2>Why choose Tag?</h2>
        </div>
        <div className="why-images">
          <img src="/assets/why-choose-1.png" alt="TAG driver" className="why-img-1" />
          <img src="/assets/why-choose-2.png" alt="Security cameras" className="why-img-2" />
        </div>
      </section>

      {/* Feature Cards */}
      <section className="feature-cards">
        <div className="card">
          <div className="card-icon">
            <svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="1" y="1" width="38" height="38" rx="7" stroke="#CCFF00" strokeWidth="2"/>
              <path d="M12 20L17 25L28 14" stroke="#CCFF00" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <h3>Fully-vetted & insured drivers</h3>
          <p>All our drivers are fully background-checked, licensed, and insured for your peace of mind.</p>
        </div>
        <div className="card">
          <div className="card-icon">
            <svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M22 3L8 23H20L18 37L32 17H20L22 3Z" stroke="#CCFF00" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <h3>Instant convenience</h3>
          <p>No need to find a space or wait for a shuttle bus.</p>
        </div>
        <div className="card">
          <div className="card-icon">
            <svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="20" cy="20" r="18" stroke="#CCFF00" strokeWidth="2"/>
              <text x="20" y="26" textAnchor="middle" fill="#CCFF00" fontSize="16" fontWeight="600">£</text>
            </svg>
          </div>
          <h3>Transparent, competitive pricing</h3>
          <p>Clear pricing with no hidden fees. What you see is what you pay.</p>
        </div>
      </section>

      {/* Pricing Section */}
      <section className="pricing-section" id="pricing">
        <h2>Pricing & plans</h2>

        <div className="pricing-cards">
          <div className="pricing-card">
            <span className="pricing-label">1 WEEK TRIP</span>
            <div className="pricing-amount">
              <span className="currency">£</span>
              <span className="price">99</span>
            </div>
            <p className="pricing-note">one off payment</p>

            <ul className="pricing-features">
              <li><span className="check">✓</span> Meet & Greet at terminal</li>
              <li><span className="check">✓</span> Secure storage facility</li>
              <li><span className="check">✓</span> 24/7 monitoring</li>
              <li><span className="check">✓</span> No hidden fees</li>
              <li><span className="check">✓</span> Cancel up to 24 hours before booking</li>
            </ul>

            <a href="#subscribe" className="pricing-btn">Subscribe <span>→</span></a>
          </div>

          <div className="pricing-card">
            <span className="pricing-label">2 WEEK TRIP</span>
            <div className="pricing-amount">
              <span className="currency">£</span>
              <span className="price">135</span>
            </div>
            <p className="pricing-note">one off payment</p>

            <ul className="pricing-features">
              <li><span className="check">✓</span> Meet & Greet at terminal</li>
              <li><span className="check">✓</span> Secure storage facility</li>
              <li><span className="check">✓</span> 24/7 monitoring</li>
              <li><span className="check">✓</span> No hidden fees</li>
              <li><span className="check">✓</span> Cancel up to 24 hours before booking</li>
            </ul>

            <a href="#subscribe" className="pricing-btn">Subscribe <span>→</span></a>
          </div>
        </div>
      </section>

      {/* Support Section */}
      <section className="support-section">
        <div className="support-content">
          <h2>We are always here<br />for you and your car.</h2>

          <div className="support-features">
            <div className="support-item">
              <span className="check-icon">✓</span>
              <div>
                <h3>On-hand support</h3>
                <p>A dedicated customer care line when you need us.</p>
              </div>
            </div>
            <div className="support-item">
              <span className="check-icon">✓</span>
              <div>
                <h3>Safe & secure</h3>
                <p>Fully insured drivers and storage facility for complete piece of mind.</p>
              </div>
            </div>
          </div>
        </div>

        <div className="faq-box" id="faq-section">
          <h3>Common Questions</h3>

          <div className={`faq-item ${openFaq === 0 ? 'open' : ''}`}>
            <div className="faq-question" onClick={() => toggleFaq(0)}>
              <span>How does meet and greet parking work?</span>
              <span className="faq-arrow">›</span>
            </div>
            <div className="faq-answer">
              <p>When you arrive at the airport, call us and drive to the designated meeting point. Our driver will meet you, complete a quick vehicle condition check, and take your keys. When you return, call us and we will bring your car back to the same meeting point.</p>
            </div>
          </div>

          <div className={`faq-item ${openFaq === 1 ? 'open' : ''}`}>
            <div className="faq-question" onClick={() => toggleFaq(1)}>
              <span>Is my car insured while you have it?</span>
              <span className="faq-arrow">›</span>
            </div>
            <div className="faq-answer">
              <p>Yes, we maintain comprehensive insurance cover for all vehicles in our care. This covers damage caused by our negligence, theft from our facility, and fire damage.</p>
            </div>
          </div>

          <div className={`faq-item ${openFaq === 2 ? 'open' : ''}`}>
            <div className="faq-question" onClick={() => toggleFaq(2)}>
              <span>What is your cancellation policy?</span>
              <span className="faq-arrow">›</span>
            </div>
            <div className="faq-answer">
              <p>Cancel 24 hours or more before your departure time for a 100% refund. Cancel less than 24 hours before and no refund is available. Refunds are processed within 5-7 working days.</p>
            </div>
          </div>

          <div className={`faq-item ${openFaq === 3 ? 'open' : ''}`}>
            <div className="faq-question" onClick={() => toggleFaq(3)}>
              <span>What happens if my flight is delayed?</span>
              <span className="faq-arrow">›</span>
            </div>
            <div className="faq-answer">
              <p>We monitor all flights and will track your return flight. If your flight is delayed, we will adjust accordingly at no extra charge. Just call us when you land.</p>
            </div>
          </div>

          <div className={`faq-item ${openFaq === 4 ? 'open' : ''}`}>
            <div className="faq-question" onClick={() => toggleFaq(4)}>
              <span>Are there any hidden charges?</span>
              <span className="faq-arrow">›</span>
            </div>
            <div className="faq-answer">
              <p>No! The price you see when booking is the total price you pay. There are no hidden fees, no airport drop off fees, no amendment charges, and no extra costs for flight delays.</p>
            </div>
          </div>

          <Link to="/faq" state={{ from: 'accordion' }} className="faq-view-all">View all FAQs →</Link>
        </div>
      </section>

      {/* Subscribe Section */}
      <section className="subscribe" id="subscribe">
        <div className="subscribe-layout">
          <img src="/assets/departure-icon.png" alt="Departure" className="subscribe-icon" />
          <div className="subscribe-content">
            <h2>Get latest updates</h2>
            <p>Register your interest and be the first to know when we launch.</p>
            <div className="subscribe-form">
              <input
                type="text"
                placeholder="First name"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                required
              />
              <input
                type="text"
                placeholder="Last name"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                required
              />
              <input
                type="email"
                placeholder="Enter your email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
              <button
                onClick={handleSubscribe}
                disabled={!isFormValid || isSubmitting}
              >
                {isSubmitting ? 'Subscribing...' : 'Subscribe'}
              </button>
            </div>
            {submitStatus === 'success' && (
              <p className="subscribe-success">Thank you for subscribing! We'll be in touch soon.</p>
            )}
            {submitStatus === 'error' && (
              <p className="subscribe-error">Something went wrong. Please try again.</p>
            )}
            <p className="privacy-note">We'll never share your details with third parties.<br />View our Privacy Policy for more info.</p>
          </div>
        </div>
      </section>

      {/* Back to Top */}
      <a href="#hero" className="scroll-to-top">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M17 14l-5-5-5 5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </a>

      {/* Footer */}
      <footer className="footer" id="contact">
        <div className="footer-top">
          <h2>For everything else</h2>
        </div>
        <div className="footer-links">
          <div className={`footer-column ${openFooter === 0 ? 'open' : ''}`}>
            <h4 onClick={() => toggleFooter(0)}>Company <span className="footer-arrow">›</span></h4>
            <div className="footer-links-content">
              <a href="#about">About us</a>
              <a href="#contact">Contact us</a>
              <a href="#careers">Careers</a>
              <a href="#press">Press</a>
            </div>
          </div>
          <div className={`footer-column ${openFooter === 1 ? 'open' : ''}`}>
            <h4 onClick={() => toggleFooter(1)}>Product <span className="footer-arrow">›</span></h4>
            <div className="footer-links-content">
              <a href="#features">Features</a>
              <a href="#pricing">Pricing</a>
              <a href="#news">News</a>
              <a href="#help">Help desk</a>
            </div>
          </div>
          <div className={`footer-column ${openFooter === 2 ? 'open' : ''}`}>
            <h4 onClick={() => toggleFooter(2)}>Services <span className="footer-arrow">›</span></h4>
            <div className="footer-links-content">
              <a href="#locations">Locations</a>
              <a href="#how-to">How To</a>
              <Link to="/faq" state={{ from: 'footer' }}>FAQs</Link>
            </div>
          </div>
          <div className={`footer-column ${openFooter === 3 ? 'open' : ''}`}>
            <h4 onClick={() => toggleFooter(3)}>Legal <span className="footer-arrow">›</span></h4>
            <div className="footer-links-content">
              <Link to="/privacy-policy">Privacy Policy</Link>
              <Link to="/terms-conditions">Terms & Conditions</Link>
              <Link to="/refund-policy">Refund Policy</Link>
              <Link to="/cookie-policy">Cookie Policy</Link>
            </div>
          </div>
          <div className={`footer-column contact-column ${openFooter === 4 ? 'open' : ''}`}>
            <h4 onClick={() => toggleFooter(4)}>Contact us <span className="footer-arrow">›</span></h4>
            <div className="footer-links-content">
              <a href="mailto:support@tagparking.co.uk" className="contact-email">support@tagparking.co.uk</a>
              <a href="tel:+441305876543" className="contact-phone">+44 (0)1305 876 543</a>
            </div>
          </div>
        </div>
        <div className="social-links">
          <a href="https://www.facebook.com/people/Tag-Parking/61583879493475/" target="_blank" rel="noopener noreferrer" aria-label="Facebook">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M18 2h-3a5 5 0 00-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 011-1h3V2z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </a>
          <a href="https://www.instagram.com/tagparking/" target="_blank" rel="noopener noreferrer" aria-label="Instagram">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="2" y="2" width="20" height="20" rx="5" stroke="currentColor" strokeWidth="2"/>
              <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="2"/>
              <circle cx="18" cy="6" r="1" fill="currentColor"/>
            </svg>
          </a>
          <a href="https://www.linkedin.com/company/tag-parking/" target="_blank" rel="noopener noreferrer" aria-label="LinkedIn">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M16 8a6 6 0 016 6v7h-4v-7a2 2 0 00-2-2 2 2 0 00-2 2v7h-4v-7a6 6 0 016-6z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <rect x="2" y="9" width="4" height="12" stroke="currentColor" strokeWidth="2"/>
              <circle cx="4" cy="4" r="2" stroke="currentColor" strokeWidth="2"/>
            </svg>
          </a>
        </div>
        <div className="footer-bottom">
          <div className="footer-legal">
            <p>© 2025 Copyright, All rights reserved</p>
          </div>
          <div className="footer-logo">
            <img src="/assets/logo.svg" alt="TAG - Book it. Bag it. Tag it." className="footer-logo-img" />
          </div>
        </div>
      </footer>
    </div>
  )
}

export default HomePage
