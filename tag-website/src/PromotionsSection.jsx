import { useState, useEffect } from 'react'
import './PromotionsSection.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function PromotionsSection() {
  const [promo, setPromo] = useState(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    // Fetch active promo section
    fetch(`${API_URL}/api/promo-section`)
      .then(res => res.json())
      .then(data => {
        if (data.promoSection && data.promoSection.promoCode) {
          setPromo(data.promoSection)
        }
      })
      .catch(err => console.error('Failed to fetch promotion:', err))
  }, [])

  const handleCopyCode = () => {
    if (promo?.promoCode) {
      navigator.clipboard.writeText(promo.promoCode)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  // Don't render if no active promo with a code
  if (!promo || !promo.promoCode) {
    return null
  }

  return (
    <>
      <section className="promotions-section" id="promotions">
        <h2>{promo.title || 'Special Offer'}</h2>
        {promo.message && (
          <p className="section-subtitle">{promo.message}</p>
        )}

        <div className="promo-card">
          <div className="promo-code-box">
            <div className="promo-code-label">Use code at checkout</div>
            <div className="promo-code-value" onClick={handleCopyCode} title="Click to copy">
              {promo.promoCode}
              <span className="promo-code-copy-icon">📋</span>
            </div>
            {copied && <div className="promo-code-copied">Copied to clipboard!</div>}
          </div>

          {promo.startDate && promo.endDate && (
            <div className="promo-dates">
              Valid: {promo.startDate} - {promo.endDate}
            </div>
          )}

          <div className="promo-cta-hint">
            Enter this code in the promo section when <a href="/tag-it">booking</a>
          </div>
        </div>
      </section>
      <div className="promotions-bottom-bar"></div>
    </>
  )
}

export default PromotionsSection
