import { useEffect, useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import './Legal.css'
import './FAQ.css'

function FAQ() {
  const navigate = useNavigate()
  const location = useLocation()
  const [openSection, setOpenSection] = useState(null)
  const [openQuestion, setOpenQuestion] = useState(null)

  // Check where the user came from (footer or faq accordion)
  const cameFromFooter = location.state?.from === 'footer'

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [])

  const handleBack = () => {
    navigate('/')
    setTimeout(() => {
      const targetId = cameFromFooter ? 'contact' : 'faq-section'
      const element = document.getElementById(targetId)
      if (element) {
        element.scrollIntoView({ behavior: 'smooth' })
      }
    }, 100)
  }

  const toggleSection = (index) => {
    setOpenSection(openSection === index ? null : index)
    setOpenQuestion(null)
  }

  const toggleQuestion = (sectionIndex, questionIndex) => {
    const key = `${sectionIndex}-${questionIndex}`
    setOpenQuestion(openQuestion === key ? null : key)
  }

  const faqData = [
    {
      title: "1. Booking and Payment",
      questions: [
        { q: "How do I make a booking?", a: "You can make a booking through our website at www.tagparking.co.uk, by phone on 07739106145, or by email at info@tagparking.co.uk. You will need to provide your name, contact details, vehicle registration, flight information, and payment details." },
        { q: "When do I need to pay?", a: "Payment is required in full at the time of booking. We accept all major credit and debit cards." },
        { q: "Will I receive a booking confirmation?", a: "Yes! Once your payment is processed, you will receive a booking confirmation email within minutes. This will include your booking reference number, meeting point details, and contact numbers for the day of travel." },
        { q: "How far in advance should I book?", a: "We recommend booking as early as possible to guarantee availability, especially during peak travel periods. The sooner you book the cheaper your parking will be!" },
        { q: "Can I book for someone else?", a: "Yes, you can book on behalf of another person. Just make sure to provide their contact details and vehicle information when booking." }
      ]
    },
    {
      title: "2. The Service",
      questions: [
        { q: "How does meet and greet parking work?", a: "When you arrive at the airport, call us and drive to the designated meeting point. Our driver will meet you, complete a quick vehicle condition check, and take your keys. You then head straight to check-in. When you return, call us after collecting your luggage, and we will bring your car back to the same meeting point." },
        { q: "Where do you park my car?", a: "Your vehicle is parked in our secure, insured off-airport facility. The location is monitored 24/7 with CCTV. We do not disclose the exact location for security reasons." },
        { q: "Is my car insured while you have it?", a: "Yes, we maintain comprehensive insurance cover for all vehicles in our care. This covers damage caused by our negligence, theft from our facility, and fire damage." },
        { q: "What happens if my flight is delayed?", a: "We monitor all flights and will track your return flight. If your flight is delayed, we will adjust accordingly at no extra charge. Just call us when you land." },
        { q: "How long does the handover take?", a: "The drop-off process typically takes 5-10 minutes. Collection is usually even quicker - just 2-3 minutes once we arrive with your car." }
      ]
    },
    {
      title: "3. Vehicle Requirements",
      questions: [
        { q: "What type of vehicles do you accept?", a: "We accept most standard cars, SUVs, and small vans. Your vehicle must not exceed: Length 5m, Width 2m, Height 2m. If you have a larger vehicle, please contact us." },
        { q: "Does my car need to be roadworthy?", a: "Yes, your vehicle must be roadworthy with valid MOT (if applicable), road tax, and insurance. We reserve the right to refuse service if your vehicle is not legal to drive." },
        { q: "Can I leave items in my car?", a: "You can leave everyday items like child seats, but you MUST remove all valuables including cash, electronics, jewellery, and important documents. We are not liable for any items left in the vehicle." },
        { q: "Do you accept electric or hybrid vehicles?", a: "Yes, we accept electric and hybrid vehicles. Please ensure your vehicle has sufficient charge for us to drive it to and from our facility (approximately 10-15 miles)." }
      ]
    },
    {
      title: "4. Cancellations and Amendments",
      questions: [
        { q: "What is your cancellation policy?", a: "Cancel 24 hours or more before your departure time = 100% refund. Cancel less than 24 hours before = No refund. Refunds are processed within 5-7 working days." },
        { q: "Can I change my booking?", a: "Yes! You can amend your booking free of charge as long as you do so at least 24 hours before your departure time. Changes are subject to availability." },
        { q: "Are there any amendment fees?", a: "No! We do not charge any fees for amendments. All changes are completely free as long as they are made at least 24 hours before your departure time." },
        { q: "What if my flight is cancelled?", a: "If your flight is cancelled by the airline, we will provide a full refund regardless of when you notify us. Just provide proof of the cancellation." },
        { q: "What if I do not show up?", a: "If you do not meet our driver and do not contact us within 30 minutes of your scheduled meeting time, this is considered a no-show and no refund will be provided." }
      ]
    },
    {
      title: "5. On the Day",
      questions: [
        { q: "What time should I arrive at the meeting point?", a: "Arrive at the meeting point at your booked time. We recommend allowing 10-15 minutes for the handover process before you need to check in for your flight." },
        { q: "What if I am running late?", a: "Call us immediately on the phone number provided in your booking confirmation. We will do our best to accommodate you, but additional charges may apply for extended waiting times." },
        { q: "What do I need to bring?", a: "Bring your booking reference number, your vehicle keys (including any spare keys), your driving licence, and any access codes for your vehicle." },
        { q: "Will you check my car condition?", a: "Yes, we conduct a thorough condition check at drop-off and take photographs. We do the same when returning your vehicle. This protects both you and us." },
        { q: "When should I call for collection?", a: "Call us after you have collected your luggage and are ready to leave the terminal. We typically need 10-15 minutes to bring your car to the meeting point." }
      ]
    },
    {
      title: "6. Security and Safety",
      questions: [
        { q: "How secure is your parking facility?", a: "Very secure! Our facility features 24/7 CCTV monitoring, secure perimeter fencing, and comprehensive insurance coverage." },
        { q: "Who will drive my car?", a: "Only our trained, insured, and licensed drivers will handle your vehicle. All our drivers undergo background checks and are experienced in handling a wide range of vehicles." },
        { q: "What if my car is damaged?", a: "If you notice any damage when collecting your vehicle, report it immediately before leaving the airport. We have comprehensive insurance to cover any damage caused while your car is in our care. Claims must be reported within 24 hours." },
        { q: "Do you drive my car?", a: "Yes, we drive your car from the airport to our secure facility and back (approximately 5 miles each way). We guarantee that your car will not be moved from our facility during your holiday." }
      ]
    },
    {
      title: "7. Pricing and Charges",
      questions: [
        { q: "Are there any hidden charges?", a: "No! The price you see when booking is the total price you pay. There are no hidden fees, no airport drop off fees, no amendment charges, and no extra costs for flight delays." },
        { q: "Do you charge extra for flight delays?", a: "No, we do not charge extra for flight delays. We monitor your flight and adjust accordingly at no additional cost." },
        { q: "Is VAT included in your prices?", a: "Yes, all prices shown include VAT where applicable." },
        { q: "Do you offer discounts or promotions?", a: "We occasionally offer special promotions and discounts. Sign up for our newsletter to stay informed about current offers." }
      ]
    },
    {
      title: "8. General Questions",
      questions: [
        { q: "Which airports do you serve?", a: "We currently serve Bournemouth Airport." },
        { q: "Can I get a receipt or invoice?", a: "Yes, a receipt is automatically sent with your booking confirmation email. If you need a VAT invoice for business expenses, just let us know." },
        { q: "Do you offer long-term parking?", a: "Yes, we can accommodate long-term parking. Contact us for special rates for stays longer than 2 weeks." },
        { q: "How can I contact you?", a: "Phone: 07739106145 (24/7 for emergencies on day of travel), Email: info@tagparking.co.uk, Website: www.tagparking.co.uk. Office hours: Monday-Friday, 9:00 AM - 5:00 PM." }
      ]
    }
  ]

  return (
    <div className="legal-page">
      <nav className="legal-nav">
        <Link to="/" className="logo">
          <img src="/assets/logo.svg" alt="TAG - Book it. Bag it. Tag it." className="logo-svg" />
        </Link>
      </nav>

      <div className="legal-container faq-container">
        <button onClick={handleBack} className="legal-back-link">
          ← Back
        </button>

        <h1>Frequently Asked Questions</h1>
        <p className="legal-subtitle">Last Updated: November 2025</p>

        <div className="legal-content faq-content">
          <p className="faq-intro">Welcome to Tag Parking Ltd! Below you will find answers to the most common questions about our meet and greet parking service. If you cannot find the answer you are looking for, please do not hesitate to contact us.</p>

          <p className="faq-contact"><strong>Quick Contact:</strong> Phone: 07739106145 | Email: info@tagparking.co.uk</p>

          <div className="faq-sections">
            {faqData.map((section, sectionIndex) => (
              <div key={sectionIndex} className={`faq-section ${openSection === sectionIndex ? 'open' : ''}`}>
                <div className="faq-section-header" onClick={() => toggleSection(sectionIndex)}>
                  <h2>{section.title}</h2>
                  <span className="faq-section-arrow">›</span>
                </div>
                <div className="faq-section-content">
                  {section.questions.map((item, questionIndex) => (
                    <div
                      key={questionIndex}
                      className={`faq-item ${openQuestion === `${sectionIndex}-${questionIndex}` ? 'open' : ''}`}
                    >
                      <div
                        className="faq-question"
                        onClick={() => toggleQuestion(sectionIndex, questionIndex)}
                      >
                        <span>{item.q}</span>
                        <span className="faq-arrow">›</span>
                      </div>
                      <div className="faq-answer">
                        <p>{item.a}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div className="faq-still-questions">
            <h2>Still Have Questions?</h2>
            <p>If you could not find the answer to your question, we are here to help!</p>
            <div className="faq-contact-details">
              <p><strong>Phone:</strong> 07739106145 (Available 24/7 for emergencies on day of travel)</p>
              <p><strong>Email:</strong> info@tagparking.co.uk</p>
              <p><strong>Website:</strong> www.tagparking.co.uk</p>
              <p><strong>Address:</strong> 5 Ivegate, Yeadon, Leeds, England, LS19 7RE</p>
            </div>
          </div>

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

export default FAQ
