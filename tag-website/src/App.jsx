import { Link } from 'react-router-dom'
import './App.css'

function App() {
  return (
    <div className="app">
      {/* Hero Section */}
      <section className="hero">
        <nav className="nav">
          <div className="logo">
            <img src="/logo.svg" alt="TAG - Book it. Bag it. Tag it." className="logo-svg" />
          </div>
          <ul className="nav-links">
            <li><a href="#book">Book</a></li>
            <li><a href="#pricing">Pricing</a></li>
            <li><a href="#support">Support</a></li>
            <li><a href="#contact">Contact</a></li>
          </ul>
        </nav>

        <div className="intro-badge">
          <img src="/intro-offer.svg" alt="Intro Offer £75 p.w." className="intro-offer-svg" />
        </div>

        <div className="hero-content">
          <div className="hero-text">
            <p className="hero-subtitle">TAG: THE NEW WAY TO MEET AND GREET</p>
            <h1 className="hero-title">Curb to Costa del Sol,<br />we'll be ready.</h1>
          </div>

          <Link to="/book" className="hero-cta">Book your Tag</Link>

          <div className="hero-video-link">
            <svg className="play-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="12" cy="12" r="11" stroke="white" strokeWidth="2"/>
              <path d="M10 8l6 4-6 4V8z" fill="white"/>
            </svg>
            <span>Take a look at how Tag works</span>
          </div>
        </div>

        <div className="scroll-indicator">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M7 10l5 5 5-5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
      </section>

      {/* Features Banner Section */}
      <section className="features-banner">
        <div className="features-content">
          <div className="feature">
            <h2>60%</h2>
            <p>Save up to 60% off<br />official airport parking</p>
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
        </div>
        <div className="features-bottom-bar"></div>
      </section>

      {/* How TAG Works */}
      <section className="how-it-works">
        <h2>How TAG works for you.</h2>
        <p className="how-it-works-subtitle">This is dummy copy. It is not meant to be read. It has<br />been placed here solely to demonstrate.</p>
        <div className="steps-cards">
          <div className="step-card">
            <div className="step-card-image">
              <img src="/step-1.png" alt="Meet us at departures" />
            </div>
          </div>
          <div className="step-card">
            <div className="step-card-image">
              <img src="/step-2.png" alt="Enjoy your trip" />
            </div>
          </div>
          <div className="step-card">
            <div className="step-card-image">
              <img src="/step-3.png" alt="Pick up where you left off" />
            </div>
          </div>
        </div>
      </section>

      {/* Why Choose TAG Section */}
      <section className="why-choose">
        <div className="why-content">
          <h2>Why choose TAG?</h2>
          <p>This is dummy copy. It is not meant to be read.<br />It has been placed here solely to demonstrate.</p>
        </div>
        <div className="why-images">
          <img src="/why-choose-1.png" alt="TAG driver" className="why-img-1" />
          <img src="/why-choose-2.png" alt="Security cameras" className="why-img-2" />
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
          <p>This is dummy copy. It is not meant to be read. It has been placed here solely to demonstrate the look.</p>
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
          <p>This is dummy copy. It has been placed here solely to feel of finished dummy text on a page.</p>
        </div>
      </section>

      {/* Pricing Section */}
      <section className="pricing-section">
        <h2>Pricing & plans</h2>
        <p className="pricing-subtitle">With lots of unique blocks, you can easily build a page without<br />coding. Build your next landing page.</p>

        <div className="pricing-cards">
          <div className="pricing-card">
            <span className="pricing-label">QUICK TRIPS</span>
            <div className="pricing-amount">
              <span className="currency">£</span>
              <span className="price">99</span>
              <span className="period">/ 1 week</span>
            </div>
            <p className="pricing-note">one off payment</p>

            <ul className="pricing-features">
              <li><span className="check">✓</span> Meet & Greet at terminal</li>
              <li><span className="check">✓</span> Secure storage facility</li>
              <li><span className="check">✓</span> 24/7 monitoring</li>
              <li><span className="check">✓</span> No hidden fees</li>
              <li><span className="check">✓</span> Cancel up to 24 hours before booking</li>
            </ul>

            <Link to="/book" className="pricing-btn">Book your Tag <span>→</span></Link>
          </div>

          <div className="pricing-card">
            <span className="pricing-label">LONGER STAYS</span>
            <div className="pricing-amount">
              <span className="currency">£</span>
              <span className="price">135</span>
              <span className="period">/ 2 weeks</span>
            </div>
            <p className="pricing-note">one off payment</p>

            <ul className="pricing-features">
              <li><span className="check">✓</span> Meet & Greet at terminal</li>
              <li><span className="check">✓</span> Secure storage facility</li>
              <li><span className="check">✓</span> 24/7 monitoring</li>
              <li><span className="check">✓</span> No hidden fees</li>
              <li><span className="check">✓</span> Cancel up to 24 hours before booking</li>
            </ul>

            <Link to="/book" className="pricing-btn">Book your Tag <span>→</span></Link>
          </div>
        </div>
      </section>

      {/* Support Section */}
      <section className="support-section">
        <div className="support-content">
          <h2>We are always here<br />for you and your car.</h2>
          <p className="support-note">This is dummy copy. It is not meant to be read.<br />It has been placed here solely to demonstrate.</p>

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

        <div className="faq-box">
          <h3>How to get started</h3>
          <p>With lots of unique blocks, you can easily build a page with coding. Build your next landing page. Integer ut obe ryn. Sed feugiat vitae turpis a porta.</p>
          <div className="faq-item">Can I use Tag for my clients?</div>
          <div className="faq-item">How often can I use it?</div>
          <div className="faq-item">How can I access to old version?</div>
        </div>
      </section>

      {/* Subscribe Section */}
      <section className="subscribe">
        <div className="subscribe-layout">
          <img src="/departure-icon.png" alt="Departure" className="subscribe-icon" />
          <div className="subscribe-content">
            <h2>Get latest updates</h2>
            <p>With lots of unique blocks, you can easily build a page<br />without coding. Build your next landing page.</p>
            <div className="subscribe-form">
              <input type="email" placeholder="Enter your email" />
              <button>Subscribe</button>
            </div>
            <p className="privacy-note">We'll never share your details with third parties.<br />View our Privacy Policy for more info.</p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="footer">
        <div className="footer-top">
          <h2>For everything else</h2>
        </div>
        <div className="footer-links">
          <div className="footer-column">
            <h4>Company</h4>
            <a href="#about">About us</a>
            <a href="#contact">Contact us</a>
            <a href="#careers">Careers</a>
            <a href="#press">Press</a>
          </div>
          <div className="footer-column">
            <h4>Product</h4>
            <a href="#features">Features</a>
            <a href="#pricing">Pricing</a>
            <a href="#news">News</a>
            <a href="#help">Help desk</a>
          </div>
          <div className="footer-column">
            <h4>Services</h4>
            <a href="#locations">Locations</a>
            <a href="#how-to">How To</a>
            <a href="#faqs">FAQs</a>
          </div>
          <div className="footer-column">
            <h4>Legal</h4>
            <a href="#privacy">Privacy Policy</a>
            <a href="#terms">Terms & Conditions</a>
            <a href="#refund">Refund Policy</a>
          </div>
          <div className="footer-column">
            <h4>Contact us</h4>
            <a href="mailto:support@tagparking.co.uk" className="contact-email">support@tagparking.co.uk</a>
            <a href="tel:+441305876543" className="contact-phone">+44 (0)1305 876 543</a>
          </div>
        </div>
        <div className="social-links">
          <a href="#facebook" aria-label="Facebook">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M18 2h-3a5 5 0 00-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 011-1h3V2z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </a>
          <a href="#instagram" aria-label="Instagram">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="2" y="2" width="20" height="20" rx="5" stroke="currentColor" strokeWidth="2"/>
              <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="2"/>
              <circle cx="18" cy="6" r="1" fill="currentColor"/>
            </svg>
          </a>
          <a href="#linkedin" aria-label="LinkedIn">
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
            <img src="/logo.svg" alt="TAG - Book it. Bag it. Tag it." className="footer-logo-img" />
          </div>
        </div>
      </footer>
    </div>
  )
}

export default App
