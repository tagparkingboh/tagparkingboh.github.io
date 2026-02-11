import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import './Legal.css'

function VehicleInspectionTerms() {
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

        <h1>Vehicle Inspection Terms & Conditions</h1>
        <p className="legal-subtitle">Last Updated: February 2025</p>

        <div className="legal-content">
          <h2>1. Introduction</h2>
          <p>These Vehicle Inspection Terms & Conditions ("Inspection Terms") govern the vehicle inspection process conducted by Tag Parking Ltd ("we", "us", "our") as part of our meet and greet parking services at Bournemouth Airport. By using our services, you agree to these Inspection Terms.</p>

          <h2>2. Purpose of Vehicle Inspection</h2>
          <p>We conduct vehicle inspections to:</p>
          <ul>
            <li>Document the condition of your vehicle at the time of handover</li>
            <li>Protect both parties by creating a verifiable record of pre-existing damage</li>
            <li>Ensure transparency and accountability throughout the parking period</li>
            <li>Facilitate fair resolution of any disputes regarding vehicle condition</li>
          </ul>

          <h2>3. Inspection Process</h2>

          <h3>3.1 Drop-off Inspection</h3>
          <p>When you hand over your vehicle to our driver:</p>
          <ul>
            <li>Our driver will conduct a thorough visual inspection of your vehicle's exterior</li>
            <li>All visible damage, scratches, dents, and marks will be recorded</li>
            <li>Photographs will be taken to document the vehicle's condition</li>
            <li>You will be asked to review and acknowledge the inspection record</li>
            <li>Any items of concern should be raised immediately with the driver</li>
          </ul>

          <h3>3.2 Collection Inspection</h3>
          <p>When your vehicle is returned to you:</p>
          <ul>
            <li>You are encouraged to inspect your vehicle before departure</li>
            <li>Any concerns about vehicle condition must be reported immediately to our driver</li>
            <li>Claims for damage not reported at the time of collection may be difficult to verify</li>
          </ul>

          <h2>4. Recording and Documentation</h2>
          <p>The inspection record includes:</p>
          <ul>
            <li>Date and time of inspection</li>
            <li>Vehicle registration number</li>
            <li>Photographic evidence of vehicle condition</li>
            <li>Written notes of any damage or marks observed</li>
            <li>Driver's name and signature</li>
            <li>Customer acknowledgement (where applicable)</li>
          </ul>
          <p>This documentation is stored securely in accordance with our Privacy Policy and data protection regulations.</p>

          <h2>5. Your Responsibilities</h2>
          <p>As the vehicle owner, you are responsible for:</p>
          <ul>
            <li>Ensuring your vehicle is in a roadworthy condition</li>
            <li>Declaring any existing damage or mechanical issues at drop-off</li>
            <li>Removing all valuables and personal items from the vehicle</li>
            <li>Ensuring the vehicle has adequate fuel for the transfer to and from our secure facility</li>
            <li>Reviewing the inspection record and raising any discrepancies immediately</li>
            <li>Providing accurate contact details for communication during your trip</li>
          </ul>

          <h2>6. Liability and Claims</h2>

          <h3>6.1 Our Liability</h3>
          <p>Tag Parking Ltd accepts liability for damage caused to your vehicle whilst in our care, subject to the following conditions:</p>
          <ul>
            <li>The damage was not recorded during the drop-off inspection</li>
            <li>The damage was reported to our driver at the time of collection</li>
            <li>The damage is consistent with having occurred during the parking period</li>
          </ul>

          <h3>6.2 Exclusions</h3>
          <p>We are not liable for:</p>
          <ul>
            <li>Pre-existing damage documented during the drop-off inspection</li>
            <li>Damage not reported at the time of vehicle collection</li>
            <li>Wear and tear, mechanical failures, or faults unrelated to our handling</li>
            <li>Loss or damage to personal belongings left in the vehicle</li>
            <li>Damage caused by acts of God, severe weather, or events beyond our control</li>
          </ul>

          <h3>6.3 Claims Process</h3>
          <p>To make a claim for vehicle damage:</p>
          <ul>
            <li>Report the damage immediately to our driver at collection</li>
            <li>Contact us within 24 hours at support@tagparking.co.uk</li>
            <li>Provide photographs of the damage</li>
            <li>Retain all documentation until the claim is resolved</li>
          </ul>

          <h2>7. Valuables and Personal Items</h2>
          <p>We strongly advise that you remove all valuables and personal items from your vehicle before handover. Tag Parking Ltd accepts no responsibility for:</p>
          <ul>
            <li>Cash, jewellery, or other valuables</li>
            <li>Electronic devices including sat navs, dash cams, and mobile phones</li>
            <li>Personal documents or identification</li>
            <li>Any other items left in the vehicle</li>
          </ul>

          <h2>8. Vehicle Security</h2>
          <p>Your vehicle will be:</p>
          <ul>
            <li>Stored in our secure, monitored parking facility</li>
            <li>Protected by CCTV surveillance 24/7</li>
            <li>Accessed only by authorised Tag Parking Ltd personnel</li>
            <li>Kept locked at all times when not being moved</li>
          </ul>

          <h2>9. Data Protection</h2>
          <p>Vehicle inspection records, including photographs, are processed in accordance with our Privacy Policy and UK GDPR requirements. Records are retained for 12 months from the date of service unless required longer for ongoing claims or legal purposes.</p>

          <h2>10. Amendments</h2>
          <p>We reserve the right to update these Inspection Terms at any time. Changes will be posted on our website with an updated revision date. Continued use of our services constitutes acceptance of any amended terms.</p>

          <h2>11. Contact Us</h2>
          <p>If you have any questions about these Vehicle Inspection Terms & Conditions, please contact us:</p>
          <p><strong>Company:</strong> Tag Parking Ltd</p>
          <p><strong>Address:</strong> 5 Ivegate, Yeadon, Leeds, England, LS19 7RE</p>
          <p><strong>Phone:</strong> 07739106145</p>
          <p><strong>Email:</strong> support@tagparking.co.uk</p>

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

export default VehicleInspectionTerms
