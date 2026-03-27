import { useState, useEffect } from 'react'
import './PromoModal.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function PromoModal() {
  const [promo, setPromo] = useState(null)
  const [isVisible, setIsVisible] = useState(false)
  const [isClosing, setIsClosing] = useState(false)

  useEffect(() => {
    // Check if user has already dismissed a promo this session
    const dismissedPromoId = sessionStorage.getItem('dismissedPromoId')

    // Fetch active promo
    fetch(`${API_URL}/api/promo-modal`)
      .then(res => res.json())
      .then(data => {
        if (data.promoModal) {
          // Don't show if user already dismissed this specific promo
          if (dismissedPromoId === String(data.promoModal.id)) {
            return
          }
          setPromo(data.promoModal)
          setIsVisible(true)
          // Track view
          fetch(`${API_URL}/api/promo-modal/${data.promoModal.id}/view`, { method: 'POST' })
        }
      })
      .catch(err => console.error('Failed to fetch promo modal:', err))
  }, [])

  const handleClose = () => {
    setIsClosing(true)
    setTimeout(() => {
      setIsVisible(false)
      if (promo) {
        sessionStorage.setItem('dismissedPromoId', String(promo.id))
      }
    }, 300) // Match CSS animation duration
  }

  const handleButtonClick = () => {
    if (!promo) return

    // Track click
    fetch(`${API_URL}/api/promo-modal/${promo.id}/click`, { method: 'POST' })

    if (promo.buttonAction === 'subscribe') {
      // Scroll to subscribe section
      const subscribeSection = document.getElementById('subscribe')
      if (subscribeSection) {
        subscribeSection.scrollIntoView({ behavior: 'smooth' })
      }
      handleClose()
    } else if (promo.buttonAction === 'link' && promo.buttonLink) {
      window.open(promo.buttonLink, '_blank')
      handleClose()
    } else {
      handleClose()
    }
  }

  if (!isVisible || !promo) return null

  return (
    <div className={`promo-modal-overlay ${isClosing ? 'closing' : ''}`} onClick={handleClose}>
      <div
        className={`promo-modal ${isClosing ? 'closing' : ''}`}
        style={{
          backgroundColor: promo.backgroundColor,
          color: promo.textColor,
        }}
        onClick={e => e.stopPropagation()}
      >
        <button
          className="promo-modal-close"
          onClick={handleClose}
          aria-label="Close"
          style={{ color: promo.textColor }}
        >
          ✕
        </button>

        <div className="promo-modal-content">
          <h2 className="promo-modal-title">{promo.title}</h2>
          <p className="promo-modal-message" style={{ whiteSpace: 'pre-line' }}>{promo.message}</p>

          {promo.startDate && promo.endDate && (
            <p className="promo-modal-dates">
              Valid: {promo.startDate} - {promo.endDate}
            </p>
          )}

          <button
            className="promo-modal-button"
            onClick={handleButtonClick}
            style={{
              backgroundColor: promo.buttonColor,
              color: promo.buttonTextColor || '#ffffff',
            }}
          >
            {promo.buttonText}
          </button>
        </div>
      </div>
    </div>
  )
}

export default PromoModal
