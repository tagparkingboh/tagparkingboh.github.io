import { Link } from 'react-router-dom'
import './Bookings.css'

function Bookings() {
  return (
    <div className="bookings-page">
      <nav className="bookings-nav">
        <Link to="/" className="logo">
          <img src="/logo.svg" alt="TAG - Book it. Bag it. Tag it." className="logo-svg" />
        </Link>
      </nav>

      <div className="bookings-container">
        <h1>Book your Tag</h1>
        <p className="bookings-subtitle">Fill in your details below and we'll take care of the rest.</p>

        <form className="bookings-form">
          <div className="form-section">
            <h2>Trip Details</h2>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="airport">Airport</label>
                <select id="airport" name="airport" required>
                  <option value="">Select airport</option>
                  <option value="heathrow">London Heathrow</option>
                  <option value="gatwick">London Gatwick</option>
                  <option value="stansted">London Stansted</option>
                  <option value="luton">London Luton</option>
                  <option value="manchester">Manchester</option>
                  <option value="birmingham">Birmingham</option>
                </select>
              </div>
              <div className="form-group">
                <label htmlFor="terminal">Terminal</label>
                <select id="terminal" name="terminal" required>
                  <option value="">Select terminal</option>
                  <option value="1">Terminal 1</option>
                  <option value="2">Terminal 2</option>
                  <option value="3">Terminal 3</option>
                  <option value="4">Terminal 4</option>
                  <option value="5">Terminal 5</option>
                </select>
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="dropoff-date">Drop-off Date</label>
                <input type="date" id="dropoff-date" name="dropoff-date" required />
              </div>
              <div className="form-group">
                <label htmlFor="dropoff-time">Drop-off Time</label>
                <input type="time" id="dropoff-time" name="dropoff-time" required />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="pickup-date">Pick-up Date</label>
                <input type="date" id="pickup-date" name="pickup-date" required />
              </div>
              <div className="form-group">
                <label htmlFor="pickup-time">Pick-up Time</label>
                <input type="time" id="pickup-time" name="pickup-time" required />
              </div>
            </div>
          </div>

          <div className="form-section">
            <h2>Vehicle Details</h2>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="registration">Registration Number</label>
                <input type="text" id="registration" name="registration" placeholder="e.g. AB12 CDE" required />
              </div>
              <div className="form-group">
                <label htmlFor="make">Vehicle Make</label>
                <input type="text" id="make" name="make" placeholder="e.g. BMW" required />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="model">Vehicle Model</label>
                <input type="text" id="model" name="model" placeholder="e.g. 3 Series" required />
              </div>
              <div className="form-group">
                <label htmlFor="colour">Vehicle Colour</label>
                <input type="text" id="colour" name="colour" placeholder="e.g. Black" required />
              </div>
            </div>
          </div>

          <div className="form-section">
            <h2>Your Details</h2>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="first-name">First Name</label>
                <input type="text" id="first-name" name="first-name" placeholder="John" required />
              </div>
              <div className="form-group">
                <label htmlFor="last-name">Last Name</label>
                <input type="text" id="last-name" name="last-name" placeholder="Smith" required />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="email">Email Address</label>
                <input type="email" id="email" name="email" placeholder="john@example.com" required />
              </div>
              <div className="form-group">
                <label htmlFor="phone">Phone Number</label>
                <input type="tel" id="phone" name="phone" placeholder="+44 7123 456789" required />
              </div>
            </div>

            <div className="form-group full-width">
              <label htmlFor="flight">Flight Number (optional)</label>
              <input type="text" id="flight" name="flight" placeholder="e.g. BA123" />
            </div>
          </div>

          <div className="form-section">
            <h2>Select Package</h2>

            <div className="package-options">
              <label className="package-option">
                <input type="radio" name="package" value="quick" defaultChecked />
                <div className="package-card">
                  <span className="package-name">Quick Trips</span>
                  <span className="package-price">£99 / 1 week</span>
                </div>
              </label>
              <label className="package-option">
                <input type="radio" name="package" value="longer" />
                <div className="package-card">
                  <span className="package-name">Longer Stays</span>
                  <span className="package-price">£135 / 2 weeks</span>
                </div>
              </label>
            </div>
          </div>

          <div className="form-section">
            <div className="form-group checkbox-group">
              <label className="checkbox-label">
                <input type="checkbox" name="terms" required />
                <span>I agree to the <a href="#terms">Terms & Conditions</a> and <a href="#privacy">Privacy Policy</a></span>
              </label>
            </div>
          </div>

          <button type="submit" className="submit-btn">Confirm Booking</button>
        </form>
      </div>

      <footer className="bookings-footer">
        <p>© 2025 TAG Parking. All rights reserved.</p>
      </footer>
    </div>
  )
}

export default Bookings
