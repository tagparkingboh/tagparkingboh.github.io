import './App.css'

function App() {
  return (
    <div className="app">
      {/* Hero Section */}
      <section className="hero">
        <nav className="nav">
          <div className="logo">
            <span className="logo-text">TAG</span>
            <span className="logo-tagline">Book it. Bag it. Tag it.</span>
          </div>
          <ul className="nav-links">
            <li><a href="#home">Home</a></li>
            <li><a href="#about">About</a></li>
            <li><a href="#services">Services</a></li>
            <li><a href="#contact">Contact</a></li>
          </ul>
        </nav>

        <div className="hero-content">
          <div className="intro-badge">
            <span className="intro-label">INTRO OFFER</span>
            <span className="intro-price">£75</span>
            <span className="intro-period">p.w.</span>
          </div>

          <div className="hero-text">
            <p className="hero-subtitle">TAG: THE NEW WAY TO MEET AND GREET</p>
            <h1 className="hero-title">Curb to Costa del Sol,<br />we'll be ready.</h1>
          </div>

          <div className="booking-form">
            <div className="form-group">
              <span className="form-icon">📍</span>
              <select className="form-select">
                <option>Select destination</option>
                <option>Heathrow</option>
                <option>Gatwick</option>
                <option>Stansted</option>
                <option>Luton</option>
              </select>
            </div>

            <div className="form-group">
              <span className="form-icon">📅</span>
              <input type="date" className="form-select" placeholder="Select date" />
            </div>

            <button className="btn-book">Book</button>
          </div>

          <p className="hero-footnote">Next to the official long-stay</p>
        </div>
      </section>

      {/* Features Section */}
      <section className="features-banner">
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
      </section>

      {/* Why Choose TAG Section */}
      <section className="why-choose">
        <div className="why-content">
          <h2>Why choose TAG?</h2>
          <p>This is dummy copy. It is not meant to be read.<br />It has been placed here solely to demonstrate.</p>
        </div>
        <div className="why-images">
          <div className="why-image-placeholder">Person in TAG jacket</div>
          <div className="why-image-placeholder">Security camera</div>
        </div>
      </section>

      {/* Feature Cards */}
      <section className="feature-cards">
        <div className="card">
          <div className="card-icon">✓</div>
          <h3>Fully-vetted & insured drivers</h3>
          <p>This is dummy copy. It is not meant to be read. It has been placed here solely to demonstrate the look.</p>
        </div>
        <div className="card">
          <div className="card-icon">⚡</div>
          <h3>Instant convenience</h3>
          <p>No need to find a space or wait for a shuttle bus.</p>
        </div>
        <div className="card">
          <div className="card-icon">£</div>
          <h3>Transparent, competitive pricing</h3>
          <p>This is dummy copy. It has been placed here solely to feel of finished dummy text on a page.</p>
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

      {/* How TAG Works */}
      <section className="how-it-works">
        <h2>How TAG works for you.</h2>
        <p>This is dummy copy. It is not meant to be read. It has<br />been placed here solely to demonstrate.</p>
        <div className="steps">
          <div className="step">
            <span className="step-number">1</span>
            <h3>Meet us at departures</h3>
            <p>No need to find parking. Simply meet us at<br />one of our set drivers will be waiting.</p>
          </div>
          <div className="step">
            <span className="step-number">2</span>
            <h3>Enjoy your trip</h3>
            <p>We'll store your car at our fully insured,<br />advanced security storage from the airport</p>
          </div>
          <div className="step">
            <span className="step-number">3</span>
            <h3>Pick up where you left off</h3>
            <p>When you land, simply call us to come<br />to hand back your keys</p>
          </div>
        </div>
      </section>

      {/* Subscribe Section */}
      <section className="subscribe">
        <h2>Get latest updates</h2>
        <p>With lots of unique blocks, you can easily build a page<br />without coding. Build your next landing page.</p>
        <div className="subscribe-form">
          <input type="email" placeholder="Enter your email" />
          <button>Subscribe</button>
        </div>
        <p className="privacy-note">We'll never share your details with third parties.<br />View our Privacy Policy for more info.</p>
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
        <div className="footer-bottom">
          <div className="social-links">
            <span>f</span>
            <span>📷</span>
          </div>
          <div className="footer-legal">
            <p>© 2025 Copyright, All rights reserved</p>
          </div>
          <div className="footer-logo">
            <span className="logo-tagline">Book it. Bag it. Tag it.</span>
            <span className="logo-text">TAG</span>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default App
