import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import './BookingsNew.css'
import './BookingWelcome.css'

function BookingWelcome() {
  useEffect(() => {
    window.scrollTo(0, 0)
    if (window.gtag) {
      window.gtag('event', 'page_view', {
        page_path: '/tag-it',
        page_title: 'Booking — Choose service',
      })
    }
  }, [])

  return (
    <div className="bookings-new-page">
      <nav className="bookings-new-nav">
        <Link to="/" className="logo">
          <img src="/assets/logo.svg" alt="TAG - Book it. Bag it. Tag it." className="logo-svg" />
        </Link>
      </nav>

      <div className="booking-welcome-container">
        <h1>Welcome — how would you like to park?</h1>
        <p className="booking-welcome-subtitle">Bournemouth International Airport (BOH)</p>

        <div className="booking-welcome-cards">
          <Link to="/tag-it/meet-greet" className="booking-welcome-card">
            <h2>Meet &amp; Greet</h2>
            <p>Drive to the terminal, hand us your keys, head to check-in. We park your car for you.</p>
            <span className="booking-welcome-cta">Book Meet &amp; Greet <span aria-hidden="true">→</span></span>
          </Link>

          <Link to="/tag-it/park-ride" className="booking-welcome-card">
            <h2>Park &amp; Ride</h2>
            <p>Park your own car at our secure facility. Hop on the shuttle to the terminal.</p>
            <span className="booking-welcome-cta">Book Park &amp; Ride <span aria-hidden="true">→</span></span>
          </Link>
        </div>
      </div>
    </div>
  )
}

export default BookingWelcome
