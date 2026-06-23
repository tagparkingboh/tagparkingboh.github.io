import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import TestimonialsCarousel from './TestimonialsCarousel'
import PromotionsSection from './PromotionsSection'
import CompetitionSection, { COMPETITION_CLOSES_AT } from './CompetitionSection'
import PromoModal from './PromoModal'
import './App.css'

function HomePage() {
  // DISABLED: HubSpot tracking script
  // useEffect(() => {
  //   const script = document.createElement('script')
  //   script.src = '//js-ap1.hs-scripts.com/442431654.js'
  //   script.id = 'hs-script-loader'
  //   script.async = true
  //   script.defer = true
  //   document.body.appendChild(script)

  //   return () => {
  //     // Cleanup on unmount
  //     const existingScript = document.getElementById('hs-script-loader')
  //     if (existingScript) {
  //       existingScript.remove()
  //     }
  //   }
  // }, [])

  const [menuOpen, setMenuOpen] = useState(false)
  const [openFaq, setOpenFaq] = useState(null)
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitStatus, setSubmitStatus] = useState(null) // 'success' | 'error' | null
  const [heroBannerIndex, setHeroBannerIndex] = useState(0)
  const [bannerFading, setBannerFading] = useState(false)
  const [prices, setPrices] = useState({ days4: 65, days4Max: 75, week1: 89, week1Max: 99, week2: 140, week2Max: 150, showRange: false })
  const [airportComparison, setAirportComparison] = useState(null)
  const [hasActivePromo, setHasActivePromo] = useState(false)
  // Drives the desktop floating-nav effect — true once the user has scrolled
  // past the top of the hero. The header CSS uses this to flip from absolute
  // overlay to fixed pill with a dark blur. Mobile ignores the class.
  const [isHeaderScrolled, setIsHeaderScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setIsHeaderScrolled(window.scrollY > 80)
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // Alternate hero banner every 10 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      setBannerFading(true)
      setTimeout(() => {
        setHeroBannerIndex(prev => (prev + 1) % 8)
        setBannerFading(false)
      }, 300) // Fade out duration
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  // Scroll to hash anchor on page load (for external links like emails)
  useEffect(() => {
    if (window.location.hash) {
      const id = window.location.hash.substring(1)
      const scrollToElement = () => {
        const element = document.getElementById(id)
        if (element) {
          const width = window.innerWidth
          const isMobile = width < 768
          const isTablet = width >= 768 && width < 1024
          const offset = isMobile ? 1700 : isTablet ? -425 : 450
          window.scrollTo({
            top: element.offsetTop + offset,
            behavior: 'smooth'
          })
        }
      }
      // Try multiple times to ensure element exists
      setTimeout(scrollToElement, 500)
      setTimeout(scrollToElement, 1500)
    }
  }, [])

  // Fetch pricing from API
  const fetchPricing = () => {
    const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    fetch(`${API_URL}/api/pricing`, {
      cache: 'no-store',
    })
      .then(res => res.json())
      .then(data => {
        const tierIncrement = data.tier_increment || 5
        const peakDayIncrement = data.peak_day_increment || 0
        const maxAddon = (tierIncrement * 2) + peakDayIncrement
        setPrices({
          days4: data.days_1_4_price || 65,
          days4Max: (data.days_1_4_price || 65) + maxAddon,
          week1: data.week1_base_price || 89,
          week1Max: (data.week1_base_price || 89) + maxAddon,
          week2: data.week2_base_price || 140,
          week2Max: (data.week2_base_price || 140) + maxAddon,
          showRange: data.show_price_range || false,
        })
      })
      .catch(() => {
        // Keep defaults on error
      })
  }

  const fetchAirportComparison = () => {
    const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    fetch(`${API_URL}/api/airport-parking/homepage-comparison`, {
      cache: 'no-store',
    })
      .then(res => res.json())
      .then(data => {
        setAirportComparison(data)
      })
      .catch(() => {
        setAirportComparison(null)
      })
  }

  useEffect(() => {
    fetchPricing()
    fetchAirportComparison()

    // Listen for pricing updates from Admin page via BroadcastChannel
    const channel = new BroadcastChannel('pricing-updates')
    channel.onmessage = (event) => {
      if (event.data === 'pricing-updated') {
        fetchPricing()
      }
    }
    return () => channel.close()
  }, [])

  const formatPounds = (pence) => `£${((pence || 0) / 100).toFixed(2)}`
  const formatCheckedDate = (value) => {
    if (!value) return 'awaiting live check'
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return 'recently'
    return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'Europe/London' })
  }

  const comparisonByDay = new Map((airportComparison?.items || []).map(item => [item.billingDays, item]))
  const comparisonRows = [
    {
      billingDays: 4,
      label: '4 DAYS',
      airportPence: comparisonByDay.get(4)?.cheapestPence || Math.round(prices.days4Max * 100),
      tagPence: comparisonByDay.get(4)?.tagPricePence || Math.round(prices.days4 * 100),
      savingPct: comparisonByDay.get(4)?.savingPct || 0,
      live: Boolean(comparisonByDay.get(4)),
    },
    {
      billingDays: 7,
      label: '7 DAYS',
      badge: 'Most popular',
      airportPence: comparisonByDay.get(7)?.cheapestPence || Math.round(prices.week1Max * 100),
      tagPence: comparisonByDay.get(7)?.tagPricePence || Math.round(prices.week1 * 100),
      savingPct: comparisonByDay.get(7)?.savingPct || 0,
      live: Boolean(comparisonByDay.get(7)),
    },
  ]
  const hasLiveComparison = Boolean(airportComparison?.items?.length)

  // Check if there's an active promo section
  useEffect(() => {
    const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    fetch(`${API_URL}/api/promo-section`)
      .then(res => res.json())
      .then(data => {
        setHasActivePromo(!!(data.promoSection && data.promoSection.promoCode))
      })
      .catch(() => setHasActivePromo(false))
  }, [])

  const isValidEmail = (email) => {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
  }

  const isFormValid = firstName.trim() && lastName.trim() && isValidEmail(email)

  const handleSubscribe = async () => {
    if (!isFormValid || isSubmitting) return

    setIsSubmitting(true)
    setSubmitStatus(null)

    const trimmedFirstName = firstName.trim()
    const trimmedLastName = lastName.trim()
    const trimmedEmail = email.trim()

    // Send to our backend API
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    try {
      const apiResponse = await fetch(`${apiUrl}/api/marketing/subscribe`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          first_name: trimmedFirstName,
          last_name: trimmedLastName,
          email: trimmedEmail,
          source: 'homepage',
        }),
      })
      const apiData = await apiResponse.json().catch(() => null)
      console.log('Marketing API Response:', apiResponse.status, apiData)
      // Backend API success - show success message
      if (apiResponse.ok && apiData?.success) {
        // Check if already subscribed or re-subscribed
        if (apiData.is_new_subscriber === false) {
          setSubmitStatus('already_subscribed')
        } else if (apiData.message === "Welcome back! You've been re-subscribed.") {
          setSubmitStatus('resubscribed')
        } else {
          setSubmitStatus('success')
        }
        setFirstName('')
        setLastName('')
        setEmail('')
      } else {
        setSubmitStatus('error')
      }
    } catch (apiError) {
      console.error('Marketing API Error:', apiError)
      setSubmitStatus('error')
    } finally {
      setIsSubmitting(false)
    }

    // DISABLED: HubSpot form submission
    // const portalId = import.meta.env.VITE_HUBSPOT_PORTAL_ID
    // const formId = import.meta.env.VITE_HUBSPOT_FORM_ID
    // const hubspotUrl = `https://api.hsforms.com/submissions/v3/integration/submit/${portalId}/${formId}`

    // const payload = {
    //   fields: [
    //     { name: 'firstname', value: trimmedFirstName },
    //     { name: 'lastname', value: trimmedLastName },
    //     { name: 'email', value: trimmedEmail },
    //   ],
    //   context: {
    //     pageUri: window.location.href,
    //     pageName: 'Tag Parking - Subscribe',
    //   },
    // }

    // console.log('HubSpot Request:', JSON.stringify(payload, null, 2))

    // try {
    //   const response = await fetch(hubspotUrl, {
    //     method: 'POST',
    //     headers: {
    //       'Content-Type': 'application/json',
    //     },
    //     body: JSON.stringify(payload),
    //   })

    //   const responseData = await response.json().catch(() => null)
    //   console.log('HubSpot Response:', response.status, responseData)

    //   if (response.ok) {
    //     setSubmitStatus('success')
    //     setFirstName('')
    //     setLastName('')
    //     setEmail('')
    //   } else {
    //     console.error('HubSpot Error:', response.status, responseData)
    //     setSubmitStatus('error')
    //   }
    // } catch (error) {
    //   console.error('Submit Error:', error)
    //   setSubmitStatus('error')
    // } finally {
    //   setIsSubmitting(false)
    // }
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

  return (
    <div className="app">
      {/* Promo Modal */}
      <PromoModal />

      {/* Header/Nav */}
      <header className={`header ${isHeaderScrolled ? 'header-scrolled' : ''}`}>
        <nav className="nav">
          <div className="logo">
            <img src="/assets/logo.svg" alt="TAG - Book it. Bag it. Tag it." className="logo-svg" fetchpriority="high" />
          </div>
          <button className={`hamburger ${menuOpen ? 'open' : ''}`} onClick={toggleMenu} aria-label="Toggle menu">
            <span></span>
            <span></span>
            <span></span>
          </button>
          <div className={`menu-overlay ${menuOpen ? 'open' : ''}`} onClick={closeMenu}></div>
          <ul className={`nav-links ${menuOpen ? 'open' : ''}`}>
            <li><a href="#pricing" onClick={closeMenu}>Pricing</a></li>
            {hasActivePromo && <li><a href="#promotions" onClick={closeMenu}>Promotions</a></li>}
            {new Date() < COMPETITION_CLOSES_AT && <li><a href="#competition" onClick={closeMenu}>Competition</a></li>}
            <li><a href="#how-it-works" onClick={closeMenu}>Meet & Greet</a></li>
            <li><a href="#secure-carpark" onClick={closeMenu}>Car Park</a></li>
            <li><a href="#testimonials" onClick={closeMenu}>Testimonials</a></li>
            <li><a href="#subscribe" onClick={closeMenu}>Subscribe</a></li>
            <li><a href="#contact" onClick={closeMenu}>Contact</a></li>
          </ul>
        </nav>
      </header>

      <main>
      {/* Hero Section */}
      <section className="hero" id="hero">
        <div className="hero-content">
          <div className="hero-text">
            <p className="hero-subtitle">TAG: HIGHLY-RATED, FRIENDLY, AND EFFICIENT MEET-AND-GREET<br />SERVICE AT BOURNEMOUTH AIRPORT</p>
            <h1 className={`hero-title ${bannerFading ? 'fading' : ''}`}>
              {heroBannerIndex === 0 && (
                hasLiveComparison
                  ? <>Save up to 70% off<br />official airport parking</>
                  : <>Live Bournemouth Airport<br />price comparison</>
              )}
              {heroBannerIndex === 1 && (
                <>Friendly and cost-effective alternative<br />to official airport parking</>
              )}
              {heroBannerIndex === 2 && (
                <>Read our story in the<br /><a href="https://www.bournemouthecho.co.uk/news/25707007.new-parking-business-launches-near-bournemouth-airport/" target="_blank" rel="noopener noreferrer" className="hero-link">Daily Echo</a></>
              )}
              {heroBannerIndex === 3 && (
                <>It's time to Tag it.<br />Book your parking now</>
              )}
              {heroBannerIndex === 4 && (
                <>Enjoy peace of mind from<br />Palma to Paphos</>
              )}
              {heroBannerIndex === 5 && (
                <>Secure parking<br />guaranteed, 24/7</>
              )}
              {heroBannerIndex === 6 && (
                <>Free cancellation up to<br />24 hours before</>
              )}
              {heroBannerIndex === 7 && (
                <>Secure payments<br />powered by Stripe</>
              )}
            </h1>
          </div>

          <div className="hero-cta-group">
            <Link to="/tag-it" className="hero-cta" onClick={() => window.gtag && window.gtag('event', 'book_it_click', { event_category: 'cta', event_label: 'hero_section' })}>Book it <span>→</span></Link>
          </div>

          <a href="#how-it-works" className="scroll-indicator" aria-label="Scroll down to how it works section">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
              <path d="M7 10l5 5 5-5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </a>
        </div>
      </section>

      {/* Availability Tracker - hidden, will be moved to /tag-it page */}
      {/* <AvailabilityTracker /> */}

      {/* Hero Bottom Bar */}
      <div className="hero-bottom-bar"></div>

      {/* Pricing Section */}
      <section className="pricing-section" id="pricing">
        <p className="pricing-live-kicker">
          {airportComparison?.checkedAt
            ? `🟢 LIVE BOH prices · checked ${formatCheckedDate(airportComparison.checkedAt)}`
            : 'Bournemouth Airport comparison · awaiting live check'}
        </p>
        <h2>Live airport comparison</h2>
        <p className="pricing-subtitle">See how Tag compares with Bournemouth Airport's latest checked prices for the two most popular stay lengths.</p>

        <div className="live-pricing-card">
          <div className="live-comparison-rows">
            {comparisonRows.map(row => (
              <div
                className={`live-comparison-row ${row.badge ? 'popular' : ''}`}
                key={row.billingDays}
              >
                <div className="live-row-heading">
                  <span className="live-row-duration">{row.label}</span>
                  {row.badge && <span className="live-row-badge">{row.badge}</span>}
                </div>
                <div className="live-price-grid">
                  <div className="live-price-side airport-side">
                    <span className="live-price-label">Airport</span>
                    <strong>{formatPounds(row.airportPence)}</strong>
                  </div>
                  <div className="live-price-side tag-side">
                    <span className="live-price-label">TAG</span>
                    <strong>{formatPounds(row.tagPence)}</strong>
                  </div>
                </div>
                {!row.live && <p className="live-row-note">Using TAG base rate while the latest live airport check refreshes.</p>}
              </div>
            ))}
          </div>
          <ul className="live-trust-list">
            <li>✓ Meet & Greet</li>
            <li>✓ 24/7 secure car park</li>
            <li>✓ No hidden fees</li>
            <li>✓ Free cancellation up to 24hrs before</li>
          </ul>
          <p className="live-savings-line stats-bar">
            {airportComparison?.items?.length
              ? 'Up to 35% cheaper than BOH\'s lowest-priced option · up to 70% cheaper than Premium Parking'
              : 'Live airport savings update automatically from recent checked prices.'}
          </p>
        </div>

        <Link to="/tag-it" className="pricing-btn pricing-btn-center" onClick={() => window.gtag && window.gtag('event', 'book_it_click', { event_category: 'cta', event_label: 'pricing_section' })}>Book it <span>→</span></Link>
        <p className="pricing-early-note">*Book early for the best price — leaving it late costs more</p>
      </section>

      {/* Features Banner Section */}
      <section className="features-banner">
        <div className="features-content">
          <div className="feature">
            <h2>{hasLiveComparison ? '70%' : 'Live'}</h2>
            <p>{hasLiveComparison ? <>Save up to 70% off<br />Premium Parking</> : <>Airport price checks<br />refreshed daily</>}</p>
          </div>
          <div className="feature">
            <h2>£0</h2>
            <p><span className="semi-bold">Zero</span> drop off fees:<br />everything is included</p>
          </div>
          <div className="feature">
            <h2>24/7</h2>
            <p>Your car never leaves our<br />secure car park</p>
          </div>
          <div className="feature">
            <h2>60s</h2>
            <p>1 minute walk<br />to the terminal</p>
          </div>
        </div>
        <div className="features-bottom-bar"></div>
      </section>

      {/* Promotions Section - only shows if there's an active promo */}
      <PromotionsSection />

      {/* Ticket Giveaway — auto-hides after the close date in CompetitionSection.jsx */}
      <CompetitionSection />

      {/* How TAG Works */}
      <section className="how-it-works" id="how-it-works">
        <h2>How Tag works for you.</h2>
        <p className="how-it-works-subtitle">No buses, no sky high fees, just a quick, easy and<br />stress-free alternative to parking at Bournemouth airport.</p>
        <div className="steps-cards">
          <div className="step-card">
            <div className="step-card-image">
              <img src="/assets/step-1.webp" alt="Meet us at departures" loading="lazy" />
            </div>
            <h3>Meet us at departures</h3>
            <p>Simply drive to the terminal car park drop off <span className="semi-bold">area</span>, and one of our drivers will be waiting</p>
          </div>
          <div className="step-card">
            <div className="step-card-image">
              <img src="/assets/step-2.webp" alt="Enjoy your trip" loading="lazy" />
            </div>
            <h3>Enjoy your trip</h3>
            <p>Relax while we park your car in our highly secured location, minutes from the airport</p>
          </div>
          <div className="step-card">
            <div className="step-card-image">
              <img src="/assets/step-3.webp" alt="Pick up where you left off" loading="lazy" />
            </div>
            <h3>Pick up where you left off</h3>
            <p>We then meet you at the same spot to hand back your keys</p>
          </div>
        </div>
      </section>

      {/* Why Choose TAG Section */}
      <section className="why-choose">
        <div className="why-content">
          <h2>Why choose Tag?</h2>
          <p className="why-subtitle">Our mission is simple: to provide an easier, faster and more cost-efficient meet & greet service for everyone. However you're travelling, we're here to give you a seamless experience from the moment you arrive.</p>
        </div>
        <div className="why-images">
          <img src="/assets/why-choose-1.webp" alt="TAG driver" className="why-img-1" loading="lazy" />
          <img src="/assets/why-choose-2.webp" alt="Security cameras" className="why-img-2" loading="lazy" />
        </div>
      </section>

      {/* Feature Cards */}
      <section className="feature-cards">
        <div className="card">
          <div className="card-icon">
            <img src="/assets/why-01.webp" alt="Fully-vetted drivers" loading="lazy" />
          </div>
          <div className="card-content">
            <h3>Fully-vetted & insured drivers</h3>
            <p>Our drivers are fully background-checked, licensed and insured.</p>
          </div>
        </div>
        <div className="card">
          <div className="card-icon">
            <img src="/assets/why-02.webp" alt="Instant convenience" loading="lazy" />
          </div>
          <div className="card-content">
            <h3>Instant convenience</h3>
            <p>No need to find a space or wait for a shuttle bus.</p>
          </div>
        </div>
        <div className="card">
          <div className="card-icon">
            <img src="/assets/why-03.webp" alt="Transparent pricing" loading="lazy" />
          </div>
          <div className="card-content">
            <h3>Transparent, competitive pricing</h3>
            <p>Clear pricing with no hidden fees. What you see is what you pay.</p>
          </div>
        </div>
      </section>

      {/* Secure Car Park Section */}
      <section className="secure-carpark" id="secure-carpark">
        <div className="secure-carpark-container">
          {/* Header shown above image on tablet/mobile */}
          <div className="secure-carpark-header">
            <h2>Our Secure Car Park</h2>
            <p className="secure-carpark-subtitle">Your car never leaves our premises</p>
          </div>
          <div className="secure-carpark-image">
            <img
              src="/assets/secure-carpark.webp"
              alt="TAG Parking secure car park with CCTV and barrier control"
              loading="lazy"
            />
          </div>
          <div className="secure-carpark-content">
            <h2>Our Secure Car Park</h2>
            <p className="secure-carpark-subtitle">Your car never leaves our premises</p>
            <ul className="secure-carpark-features">
              <li>24/7 CCTV monitoring</li>
              <li>Secure perimeter fencing</li>
              <li>Security barrier</li>
              <li>Security lighting</li>
            </ul>
            <p className="secure-carpark-tagline">Peace of mind while you're away</p>
          </div>
        </div>
      </section>

      {/* Testimonials Section */}
      <TestimonialsCarousel />

      {/* Support Section */}
      <section className="support-section">
        <div className="support-content">
          <h2>We're always here for you and your car.</h2>
          <p className="support-subtitle">Our 24/7 CCTV monitoring, secure perimeter fencing, and comprehensive insurance coverage give you peace of mind while you're away.</p>

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
              <p><span className="semi-bold">Meet us at the agreed booking time at the airport parking drop off area.</span> Our driver will meet you, complete a quick vehicle condition check, and take your keys. When you return, call us and we will bring your car back to the same meeting point.</p>
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
          <img src="/assets/departure-icon.webp" alt="Departure" className="subscribe-icon" loading="lazy" />
          <div className="subscribe-content">
            <h2>Sign up today</h2>
            <p className="subscribe-subtitle">Sign up for news and offers:</p>
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
                {isSubmitting ? 'Signing up...' : 'Sign up'}
              </button>
            </div>
            {submitStatus === 'success' && (
              <p className="subscribe-success">Thank you for subscribing! We'll be in touch soon.</p>
            )}
            {submitStatus === 'resubscribed' && (
              <p className="subscribe-success">Welcome back! You've been re-subscribed.</p>
            )}
            {submitStatus === 'already_subscribed' && (
              <p className="subscribe-success">You're already on the list! We'll be in touch soon.</p>
            )}
            {submitStatus === 'error' && (
              <p className="subscribe-error">Something went wrong. Please try again.</p>
            )}
            <p className="privacy-note">We'll never share your details with third parties.<br />View our Privacy Policy for more info.</p>
          </div>
        </div>
      </section>

      {/* Back to Top */}
      <a href="#hero" className="scroll-to-top" aria-label="Scroll back to top">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <path d="M17 14l-5-5-5 5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </a>
      </main>

      {/* Footer */}
      <footer className="footer" id="contact">
        <div className="footer-top">
          <h2>For everything else</h2>
        </div>
        <div className="footer-links footer-links-simple">
          <Link to="/faq" state={{ from: 'footer' }}>FAQs</Link>
          <Link to="/privacy-policy">Privacy Policy</Link>
          <Link to="/terms-conditions">Terms & Conditions</Link>
          <Link to="/refund-policy">Refund Policy</Link>
          <Link to="/cookie-policy">Cookie Policy</Link>
          <Link to="/vehicle-inspection-terms">Vehicle Inspection T&Cs</Link>
        </div>
        <div className="footer-contact">
          <a href="mailto:support@tagparking.co.uk">support@tagparking.co.uk</a>
          <a href="tel:01202 798710">01202 798710</a>
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
