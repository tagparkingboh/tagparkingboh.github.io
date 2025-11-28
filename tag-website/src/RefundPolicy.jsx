import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import './Legal.css'

function RefundPolicy() {
  const navigate = useNavigate()

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [])

  const handleBack = () => {
    navigate('/')
    setTimeout(() => {
      const element = document.getElementById('contact')
      if (element) {
        element.scrollIntoView({ behavior: 'smooth' })
      }
    }, 100)
  }

  return (
    <div className="legal-page">
      <nav className="legal-nav">
        <Link to="/" className="logo">
          <img src="/assets/logo.svg" alt="TAG - Book it. Bag it. Tag it." className="logo-svg" />
        </Link>
      </nav>

      <div className="legal-container">
        <button onClick={handleBack} className="legal-back-link">
          ← Back
        </button>

        <h1>Cancellation and Refund Policy</h1>
        <p className="legal-subtitle">Last Updated: January 2025</p>

        <div className="legal-content">
          <h2>1. Introduction</h2>
          <p>This Cancellation and Refund Policy explains the terms and conditions under which Tag Parking Ltd ("we", "us", "our") will provide refunds for cancelled bookings. This policy should be read in conjunction with our <Link to="/terms-conditions">Terms and Conditions</Link>.</p>
          <p><strong>Important:</strong> Please read this policy carefully before making a booking. By making a booking, you agree to the terms of this Cancellation and Refund Policy.</p>

          <h2>2. Cancellation Timeframes and Refunds</h2>
          <p>Our cancellation policy is simple and straightforward:</p>
          <table>
            <thead>
              <tr>
                <th>Cancellation Timeframe</th>
                <th>Refund Amount</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>More than 24 hours before departure</td>
                <td>100% refund</td>
              </tr>
              <tr>
                <td>Less than 24 hours before departure</td>
                <td>No refund</td>
              </tr>
              <tr>
                <td>No-show</td>
                <td>No refund</td>
              </tr>
            </tbody>
          </table>
          <p><strong>Note:</strong> The "departure date" refers to the date and time you are scheduled to drop off your vehicle with us, not your flight departure time.</p>

          <h2>3. How to Cancel Your Booking</h2>
          <p>To cancel your booking, you must contact us using one of the following methods:</p>
          <ul>
            <li><strong>Phone:</strong> 07739106145 (available 24/7)</li>
            <li><strong>Email:</strong> support@tagparking.co.uk</li>
            <li><strong>Through your online account</strong> (if applicable)</li>
          </ul>
          <p>When cancelling, please provide:</p>
          <ul>
            <li>Your booking reference number</li>
            <li>Your name and contact details</li>
            <li>Reason for cancellation (optional but helpful)</li>
          </ul>
          <p>We will send you a cancellation confirmation by email within 24 hours.</p>

          <h2>4. Refund Processing</h2>

          <h3>4.1 Processing Time</h3>
          <p>Refunds will be processed within 5-7 working days of receiving your cancellation request. The refund will be credited to the original payment method used for the booking.</p>

          <h3>4.2 Bank Processing Time</h3>
          <p>Please note that while we process refunds within 5-7 working days, your bank or card provider may take an additional 3-5 working days to credit the funds to your account.</p>

          <h3>4.3 Refund Method</h3>
          <p>Refunds will be issued to the original payment card or account used for the booking. We cannot issue refunds to a different payment method.</p>

          <h2>5. No-Show Policy</h2>
          <p>A "no-show" occurs when you fail to meet our driver at the designated meeting point and time, and you do not contact us within 30 minutes of your scheduled meeting time.</p>
          <p><strong>No refunds will be provided for no-shows.</strong> If you know you will be late or unable to make your booking, please contact us immediately to discuss options.</p>

          <h2>6. Amendments vs Cancellations</h2>
          <p>Before cancelling your booking, consider whether an amendment might be more suitable:</p>
          <ul>
            <li>You can amend your booking for different dates, times, vehicle, or airport (subject to availability)</li>
            <li>Amendments must be made at least 24 hours before your departure time</li>
            <li><strong>Good News:</strong> We do not charge any amendment fees. All amendments are completely free of charge!</li>
          </ul>

          <h2>7. Special Circumstances</h2>
          <p>We will consider refund requests outside our standard policy in the following situations:</p>

          <h3>7.1 Flight Cancellations</h3>
          <p>If your flight is cancelled by the airline (not due to your actions), we will provide a full refund regardless of the cancellation timeframe. You must provide proof of the flight cancellation.</p>

          <h3>7.2 Medical Emergencies</h3>
          <p>If you or an immediate family member experiences a medical emergency that prevents you from travelling, we will consider a full or partial refund. You must provide a medical certificate or doctor's note.</p>

          <h3>7.3 Bereavement</h3>
          <p>In the event of a death in your immediate family, we will provide a full refund. You must provide a death certificate or funeral notice.</p>

          <h3>7.4 Extreme Weather or Natural Disasters</h3>
          <p>If extreme weather or natural disasters make it impossible or unsafe to travel, we will provide a full refund or allow you to rebook for a later date at no additional cost.</p>

          <h3>7.5 Government Travel Restrictions</h3>
          <p>If government-imposed travel restrictions prevent you from travelling (e.g., lockdowns, travel bans), we will provide a full refund or credit for future use.</p>

          <h2>8. Cancellations by Tag Parking Ltd</h2>
          <p>We reserve the right to cancel your booking if:</p>
          <ul>
            <li>We are unable to provide the service due to circumstances beyond our control</li>
            <li>You have provided false or misleading information</li>
            <li>You have breached our Terms and Conditions</li>
            <li>Your vehicle does not meet our requirements</li>
          </ul>
          <p>If we cancel your booking, you will receive a full refund within 5-7 working days.</p>

          <h2>9. Partial Service Refunds</h2>
          <p>In some cases, you may be entitled to a partial refund if we fail to provide the full service:</p>

          <h3>9.1 Delayed Collection</h3>
          <p>If we are late collecting your vehicle upon your return:</p>
          <ul>
            <li>0-30 minutes late: No refund</li>
            <li>30-60 minutes late: 25% refund</li>
            <li>60-90 minutes late: 50% refund</li>
            <li>More than 90 minutes late: 75% refund</li>
          </ul>

          <h2>10. Credits and Vouchers</h2>
          <p>In some circumstances, we may offer a credit or voucher instead of a cash refund:</p>
          <ul>
            <li>Credits and vouchers are valid for 12 months from the date of issue</li>
            <li>Can be used for any of our services</li>
            <li>Are non-transferable</li>
            <li>Cannot be exchanged for cash</li>
          </ul>

          <h2>11. Refund Disputes</h2>
          <p>If you disagree with our refund decision, you can request an internal review by emailing info@tagparking.co.uk with "Refund Dispute" in the subject line. We will review your case and respond within 7 working days.</p>

          <h2>12. Consumer Rights</h2>
          <p>This Cancellation and Refund Policy does not affect your statutory rights under UK consumer protection law. If you believe we have not provided the service as described or have breached our contract with you, you may have additional rights under the Consumer Rights Act 2015.</p>

          <h2>13. Contact Information</h2>
          <p>For questions about cancellations or refunds, please contact us:</p>
          <p><strong>Tag Parking Ltd</strong></p>
          <p><strong>Address:</strong> 5 Ivegate, Yeadon, Leeds, England, LS19 7RE</p>
          <p><strong>Phone:</strong> 07739106145 (24/7)</p>
          <p><strong>Email:</strong> info@tagparking.co.uk</p>
          <p><strong>Office Hours:</strong> Monday to Friday, 9:00 AM - 5:00 PM</p>

          <div className="legal-footer">
            <p>© 2025 Tag Parking Ltd. All rights reserved.</p>
            <p>Registered in England and Wales</p>
            <p>Registered Address: 5 Ivegate, Yeadon, Leeds, England, LS19 7RE</p>
          </div>
        </div>
      </div>
    </div>
  )
}

export default RefundPolicy
