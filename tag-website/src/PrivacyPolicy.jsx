import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import './Legal.css'

function PrivacyPolicy() {
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

        <h1>Privacy Policy</h1>
        <p className="legal-subtitle">Last Updated: November 2025</p>

        <div className="legal-content">
          <h2>1. Introduction</h2>
          <p>Tag Parking Ltd ("we", "us", "our") is committed to protecting your privacy and personal data. This Privacy Policy explains how we collect, use, store, and protect your personal information in accordance with the UK General Data Protection Regulation (UK GDPR) and the Data Protection Act 2018.</p>
          <p><strong>Your Rights:</strong> You have the right to know what personal data we hold about you, how we use it, and to request its deletion. Please read this policy carefully to understand our practices.</p>

          <h2>2. Data Controller</h2>
          <p><strong>Data Controller:</strong> Tag Parking Ltd</p>
          <p><strong>Registered Address:</strong> 5 Ivegate, Yeadon, Leeds, England, LS19 7RE</p>
          <p><strong>Phone:</strong> 07739106145</p>
          <p><strong>Email:</strong> privacy@tagparking.co.uk</p>

          <h2>3. What Personal Data We Collect</h2>

          <h3>3.1 Information You Provide to Us</h3>
          <p>When you make a booking with Tag Parking Ltd, we collect the following information:</p>
          <ul>
            <li><strong>Personal identification details:</strong> Full name, email address, telephone number</li>
            <li><strong>Vehicle information:</strong> Vehicle registration number, make, model, colour</li>
            <li><strong>Travel details:</strong> Flight number, departure date and time, arrival date and time, airport terminal</li>
            <li><strong>Payment information:</strong> Billing address, payment card details (processed securely through our payment provider)</li>
            <li><strong>Special requirements:</strong> Any additional services or accessibility needs you request</li>
          </ul>

          <h3>3.2 Information We Collect Automatically</h3>
          <p>When you visit our website or use our services, we automatically collect:</p>
          <ul>
            <li><strong>Technical information:</strong> IP address, browser type and version, device type, operating system</li>
            <li><strong>Usage information:</strong> Pages visited, time spent on pages, links clicked, navigation patterns</li>
            <li><strong>Location data:</strong> General location based on IP address</li>
            <li><strong>Cookie data:</strong> Information collected through cookies (see our Cookie Policy for full details)</li>
          </ul>

          <h3>3.3 Information We Create During Service Delivery</h3>
          <p>As part of providing our meet and greet parking service, we create and maintain:</p>
          <ul>
            <li><strong>Vehicle condition reports:</strong> Photographs and written descriptions of your vehicle's condition at drop-off and collection</li>
            <li><strong>Service records:</strong> Drop-off times, collection times, parking location, staff member details</li>
            <li><strong>Communication records:</strong> Copies of emails, text messages, and notes from telephone conversations</li>
            <li><strong>CCTV footage:</strong> Security camera recordings from our parking facilities</li>
          </ul>

          <h2>4. How We Use Your Personal Data</h2>
          <p>We use your personal information for the following purposes:</p>
          <ul>
            <li>To process and manage your parking booking</li>
            <li>To communicate with you about your booking (confirmations, reminders, updates)</li>
            <li>To coordinate vehicle collection and return at the airport</li>
            <li>To process payments and issue refunds when applicable</li>
            <li>To maintain vehicle condition records for insurance and liability purposes</li>
            <li>To handle customer service enquiries, complaints, and claims</li>
            <li>To improve our services based on customer feedback and usage patterns</li>
            <li>To send marketing communications (only with your consent)</li>
            <li>To comply with legal obligations including tax and accounting requirements</li>
            <li>To prevent fraud and ensure security of our facilities</li>
          </ul>

          <h2>5. How We Share Your Personal Data</h2>

          <h3>5.1 Third-Party Service Providers</h3>
          <p>We share your personal data with carefully selected third-party service providers who help us deliver our services:</p>
          <ul>
            <li><strong>Payment processors:</strong> To securely process your payment transactions</li>
            <li><strong>Email service providers:</strong> To send booking confirmations, reminders, and service updates</li>
            <li><strong>SMS providers:</strong> To send text message notifications about your booking</li>
            <li><strong>Cloud storage providers:</strong> To securely store booking and vehicle condition data</li>
            <li><strong>Insurance providers:</strong> In the event of a claim or incident involving your vehicle</li>
            <li><strong>Website hosting and IT support:</strong> To maintain and secure our website and systems</li>
          </ul>

          <h3>5.2 Legal and Regulatory Disclosures</h3>
          <p>We may disclose your personal data when required by law or to:</p>
          <ul>
            <li>Comply with legal obligations, court orders, or regulatory requirements</li>
            <li>Protect and defend our legal rights and property</li>
            <li>Prevent or investigate fraud, security breaches, or illegal activities</li>
            <li>Protect the safety and security of our customers, staff, and facilities</li>
            <li>Respond to requests from law enforcement or government authorities</li>
          </ul>

          <h3>5.3 No Sale of Personal Data</h3>
          <p>We do not sell, rent, or trade your personal data to third parties for their marketing purposes.</p>

          <h2>6. How Long We Keep Your Data</h2>
          <p>We retain your personal data for the following periods:</p>
          <ul>
            <li><strong>Booking and service records:</strong> 6 years from the date of service</li>
            <li><strong>Vehicle condition photographs:</strong> 12 months from collection</li>
            <li><strong>CCTV footage:</strong> 30 days (unless required for investigation)</li>
            <li><strong>Marketing consent records:</strong> Duration of consent plus 2 years</li>
            <li><strong>Financial records:</strong> 7 years as required by law</li>
          </ul>

          <h2>7. Your Rights Under UK GDPR</h2>
          <p>Under UK GDPR, you have the following rights regarding your personal data:</p>
          <ul>
            <li><strong>Right of Access:</strong> Request a copy of the personal data we hold about you</li>
            <li><strong>Right to Rectification:</strong> Request correction of inaccurate or incomplete personal data</li>
            <li><strong>Right to Erasure:</strong> Request deletion of your personal data (subject to legal retention requirements)</li>
            <li><strong>Right to Restriction of Processing:</strong> Request that we limit how we use your data in certain circumstances</li>
            <li><strong>Right to Data Portability:</strong> Receive your personal data in a structured, commonly used, machine-readable format</li>
            <li><strong>Right to Object:</strong> Object to processing based on legitimate interests or for direct marketing purposes</li>
            <li><strong>Right to Withdraw Consent:</strong> Withdraw your consent for marketing communications at any time</li>
          </ul>
          <p>To exercise any of these rights, please contact us at privacy@tagparking.co.uk</p>

          <h2>8. Security Measures</h2>
          <p>We implement robust technical and organizational security measures to protect your personal data:</p>
          <ul>
            <li><strong>Encryption:</strong> SSL/TLS encryption for all data transmitted via our website</li>
            <li><strong>Secure Payment Processing:</strong> PCI-DSS compliant payment providers (we do not store card details)</li>
            <li><strong>Access Controls:</strong> Strict authentication and authorization for staff accessing customer data</li>
            <li><strong>Regular Security Audits:</strong> Ongoing monitoring and testing of our systems</li>
            <li><strong>Staff Training:</strong> Regular data protection and security training for all employees</li>
          </ul>

          <h2>9. Contact Us</h2>
          <p>If you have any questions, concerns, or requests regarding this Privacy Policy or how we handle your personal data, please contact us:</p>
          <p><strong>Company:</strong> Tag Parking Ltd</p>
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

export default PrivacyPolicy
