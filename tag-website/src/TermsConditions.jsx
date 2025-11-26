import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import './Legal.css'

function TermsConditions() {
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [])

  return (
    <div className="legal-page">
      <nav className="legal-nav">
        <Link to="/" className="logo">
          <img src="/logo.svg" alt="TAG - Book it. Bag it. Tag it." className="logo-svg" />
        </Link>
      </nav>

      <div className="legal-container">
        <Link to="/#contact" className="legal-back-link">
          ← Back
        </Link>

        <h1>Terms and Conditions</h1>
        <p className="legal-subtitle">Last Updated: January 2025</p>

        <div className="legal-content">
          <h2>1. Introduction and Acceptance of Terms</h2>
          <p>These Terms and Conditions ("Terms") govern your use of the meet and greet parking services provided by Tag Parking Ltd ("we", "us", "our", "the Company"). By making a booking with us, you ("you", "your", "the Customer") agree to be bound by these Terms.</p>
          <p><strong>Important:</strong> Please read these Terms carefully before making a booking. If you do not agree with any part of these Terms, you should not use our services.</p>

          <h2>2. Company Information</h2>
          <p><strong>Company Name:</strong> Tag Parking Ltd</p>
          <p><strong>Registered Address:</strong> 5 Ivegate, Yeadon, Leeds, England, LS19 7RE</p>
          <p><strong>Phone:</strong> 07739106145</p>
          <p><strong>Email:</strong> info@tagparking.co.uk</p>
          <p><strong>Website:</strong> www.tagparking.co.uk</p>

          <h2>3. Service Description</h2>
          <p>Tag Parking Ltd provides meet and greet parking services at various UK airports. Our service includes:</p>
          <ul>
            <li>Meeting you at the airport terminal at your specified departure time</li>
            <li>Taking custody of your vehicle and parking it in a secure facility</li>
            <li>Returning your vehicle to you at the airport terminal upon your return</li>
            <li>Vehicle condition checks at drop-off and collection</li>
          </ul>
          <p>The specific details of the service, including meeting points and procedures, will be confirmed in your booking confirmation.</p>

          <h2>4. Booking and Payment</h2>

          <h3>4.1 Making a Booking</h3>
          <p>To make a booking, you must:</p>
          <ul>
            <li>Provide accurate and complete information including your name, contact details, vehicle details, and flight information</li>
            <li>Be at least 18 years of age</li>
            <li>Hold a valid driving licence</li>
            <li>Be the registered keeper of the vehicle or have the registered keeper's permission to use our services</li>
          </ul>

          <h3>4.2 Payment Terms</h3>
          <ul>
            <li>Payment must be made in full at the time of booking</li>
            <li>We accept payment by credit card, debit card, or other methods as displayed on our website</li>
            <li>All prices are in British Pounds (GBP) and include VAT where applicable</li>
            <li>Prices are subject to change, but you will be charged the price displayed at the time of booking</li>
          </ul>

          <h3>4.3 Booking Confirmation</h3>
          <p>Once payment is received, we will send you a booking confirmation by email containing your booking reference number, service details, and important instructions.</p>

          <h2>5. Amendments and Cancellations</h2>

          <h3>5.1 Amendments by Customer</h3>
          <p>You may amend your booking subject to the following conditions:</p>
          <ul>
            <li>Amendments must be made at least 24 hours before your departure time</li>
            <li>Amendments are subject to availability</li>
            <li>If the amendment results in a higher price, you must pay the difference</li>
            <li>If the amendment results in a lower price, we will refund the difference</li>
            <li>There are no amendment fees - all amendments are free of charge</li>
          </ul>

          <h3>5.2 Cancellations by Customer</h3>
          <p>Please refer to our separate <Link to="/refund-policy">Refund Policy</Link> for full details on cancellations and refunds.</p>
          <p><strong>Summary:</strong> You will receive a 100% refund if you cancel at least 24 hours before your departure time. No refund is available for cancellations made less than 24 hours before departure.</p>

          <h2>6. Your Responsibilities</h2>

          <h3>6.1 Vehicle Requirements</h3>
          <p>You must ensure that:</p>
          <ul>
            <li>Your vehicle is roadworthy and legal to drive</li>
            <li>Your vehicle has valid MOT (if applicable), road tax, and insurance</li>
            <li>Your vehicle is not carrying any illegal, dangerous, or prohibited items</li>
            <li>Your vehicle does not exceed standard size limits (length: 5m, width: 2m, height: 2m)</li>
            <li>You have removed all valuables from the vehicle</li>
          </ul>

          <h3>6.2 Meeting Our Driver</h3>
          <p>You must:</p>
          <ul>
            <li>Arrive at the designated meeting point at the agreed time</li>
            <li>Call us if you are running late or cannot find our driver</li>
            <li>Provide your vehicle keys and any necessary access codes or devices</li>
            <li>Complete the vehicle condition check with our driver</li>
          </ul>

          <h2>7. Our Responsibilities</h2>
          <p>We will:</p>
          <ul>
            <li>Meet you at the designated meeting point at the agreed time</li>
            <li>Park your vehicle in a secure, insured facility</li>
            <li>Return your vehicle to you at the agreed collection point</li>
            <li>Conduct vehicle condition checks at drop-off and collection</li>
            <li>Monitor your return flight for delays</li>
            <li>Maintain appropriate insurance cover for your vehicle while in our care</li>
          </ul>

          <h2>8. Vehicle Condition and Inspection</h2>

          <h3>8.1 Drop-off Inspection</h3>
          <p>When you hand over your vehicle, our driver will conduct a condition check and take photographs. You will be asked to sign or electronically confirm the condition report.</p>

          <h3>8.2 Collection Inspection</h3>
          <p>When we return your vehicle, you should inspect it immediately and report any damage or concerns before leaving the airport. Once you drive away, we will assume you are satisfied with the vehicle's condition.</p>

          <h3>8.3 Damage Claims</h3>
          <p>Any damage claims must be reported to us within 24 hours of collection. Claims reported after this time may not be accepted. You must provide photographic evidence of any damage.</p>

          <h2>9. Liability and Insurance</h2>

          <h3>9.1 Our Insurance</h3>
          <p>We maintain comprehensive insurance cover for your vehicle while it is in our care. Our insurance covers:</p>
          <ul>
            <li>Damage to your vehicle caused by our negligence</li>
            <li>Theft of your vehicle from our secure facility</li>
            <li>Fire damage while in our custody</li>
          </ul>

          <h3>9.2 Limitations of Liability</h3>
          <p>We are not liable for:</p>
          <ul>
            <li>Pre-existing damage to your vehicle</li>
            <li>Items left in your vehicle (you must remove all valuables)</li>
            <li>Mechanical breakdowns or failures</li>
            <li>Damage caused by factors beyond our control</li>
            <li>Consequential losses (e.g., missed flights, accommodation costs)</li>
            <li>Damage not reported within 24 hours of collection</li>
          </ul>

          <h2>10. Prohibited Items</h2>
          <p>You must not leave the following items in your vehicle:</p>
          <ul>
            <li>Cash, credit cards, or other financial instruments</li>
            <li>Jewellery, watches, or other valuable items</li>
            <li>Electronic devices (laptops, tablets, phones, cameras)</li>
            <li>Important documents (passports, driving licences, etc.)</li>
            <li>Illegal substances or items</li>
            <li>Dangerous goods or hazardous materials</li>
          </ul>
          <p>We are not liable for any items left in your vehicle.</p>

          <h2>11. Delays and No-Shows</h2>

          <h3>11.1 Customer Delays</h3>
          <p>If you are delayed and cannot meet our driver at the agreed time, you must contact us immediately. We will make reasonable efforts to accommodate delays, but additional charges may apply for extended waiting times.</p>

          <h3>11.2 Customer No-Shows</h3>
          <p>If you fail to meet our driver and do not contact us within 30 minutes of your scheduled meeting time, this will be considered a no-show. No refund will be provided for no-shows.</p>

          <h2>12. Data Protection and Privacy</h2>
          <p>We collect and process your personal data in accordance with UK GDPR and the Data Protection Act 2018. For full details on how we handle your data, please see our <Link to="/privacy-policy">Privacy Policy</Link>.</p>

          <h2>13. Complaints and Disputes</h2>
          <p>If you have a complaint about our service:</p>
          <ul>
            <li>Contact us within 7 days of your return</li>
            <li>Provide your booking reference and details of the complaint</li>
            <li>Include any supporting evidence (photos, receipts, etc.)</li>
          </ul>
          <p>We will acknowledge your complaint within 2 working days and provide a response within 14 days.</p>

          <h2>14. Force Majeure</h2>
          <p>We are not liable for any failure to perform our obligations due to circumstances beyond our reasonable control, including extreme weather, natural disasters, strikes, terrorism, government restrictions, airport closures, or pandemics.</p>

          <h2>15. Changes to Terms</h2>
          <p>We reserve the right to update these Terms at any time. Changes will be posted on our website with an updated "Last Updated" date. Bookings made before changes take effect will be governed by the Terms in place at the time of booking.</p>

          <h2>16. Governing Law and Jurisdiction</h2>
          <p>These Terms are governed by the laws of England and Wales. Any disputes arising from these Terms or our services will be subject to the exclusive jurisdiction of the courts of England and Wales.</p>

          <h2>17. Contact Information</h2>
          <p>For questions about these Terms or our services, please contact us:</p>
          <p><strong>Tag Parking Ltd</strong></p>
          <p><strong>Address:</strong> 5 Ivegate, Yeadon, Leeds, England, LS19 7RE</p>
          <p><strong>Phone:</strong> 07739106145</p>
          <p><strong>Email:</strong> info@tagparking.co.uk</p>

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

export default TermsConditions
