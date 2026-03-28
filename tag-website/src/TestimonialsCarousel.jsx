import { useState, useEffect, useCallback } from 'react'
import './TestimonialsCarousel.css'

function TestimonialsCarousel() {
  const [testimonials, setTestimonials] = useState([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isTransitioning, setIsTransitioning] = useState(false)
  const [isPaused, setIsPaused] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [showPressModal, setShowPressModal] = useState(false)

  // Fetch testimonials from API
  useEffect(() => {
    const fetchTestimonials = async () => {
      const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      try {
        const response = await fetch(`${API_URL}/api/testimonials`)
        const data = await response.json()
        if (data.testimonials && data.testimonials.length > 0) {
          // Shuffle and deduplicate the weighted pool
          const shuffled = shuffleArray([...data.testimonials])
          const unique = deduplicateTestimonials(shuffled)
          setTestimonials(unique)
        }
      } catch (error) {
        console.error('Error fetching testimonials:', error)
      } finally {
        setIsLoading(false)
      }
    }
    fetchTestimonials()
  }, [])

  // Shuffle array (Fisher-Yates)
  const shuffleArray = (array) => {
    for (let i = array.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[array[i], array[j]] = [array[j], array[i]]
    }
    return array
  }

  // Deduplicate testimonials by ID (keep first occurrence)
  const deduplicateTestimonials = (array) => {
    const seen = new Set()
    return array.filter((item) => {
      if (seen.has(item.id)) return false
      seen.add(item.id)
      return true
    })
  }

  // Auto-rotate carousel
  const goToNext = useCallback(() => {
    if (testimonials.length <= 1) return
    setIsTransitioning(true)
    setTimeout(() => {
      setCurrentIndex((prev) => (prev + 1) % testimonials.length)
      setIsTransitioning(false)
    }, 300)
  }, [testimonials.length])

  useEffect(() => {
    if (testimonials.length <= 1 || isPaused) return
    const interval = setInterval(goToNext, 7000) // 7 seconds per slide
    return () => clearInterval(interval)
  }, [testimonials.length, isPaused, goToNext])

  // Navigation handlers
  const goToPrevious = () => {
    if (testimonials.length <= 1) return
    setIsTransitioning(true)
    setTimeout(() => {
      setCurrentIndex((prev) => (prev - 1 + testimonials.length) % testimonials.length)
      setIsTransitioning(false)
    }, 300)
  }

  // Render star rating (or nothing for unrated)
  const renderRating = (rating) => {
    if (rating === null || rating === undefined) {
      // Unrated - show nothing
      return null
    }
    // Show stars for rated testimonials
    return (
      <div className="testimonial-stars">
        {[1, 2, 3, 4, 5].map((star) => (
          <span key={star} className={star <= rating ? 'star filled' : 'star'}>
            ★
          </span>
        ))}
      </div>
    )
  }

  // Format date as "February 2026"
  const formatDate = (dateString) => {
    if (!dateString) return ''
    const date = new Date(dateString)
    return date.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
  }

  // Source badge
  const renderSourceBadge = (source) => {
    if (!source) return null
    const sourceIcons = {
      google: { icon: 'G', color: '#4285F4' },
      trustpilot: { icon: 'T', color: '#00B67A' },
      facebook: { icon: 'f', color: '#1877F2' },
      linkedin: { icon: 'in', color: '#0A66C2' },
      email: { icon: '@', color: '#EA4335' },
      other: { icon: '★', color: '#CCFF00' },
    }
    const sourceConfig = sourceIcons[source.toLowerCase()] || sourceIcons.other
    return (
      <span className="testimonial-source-badge" style={{ backgroundColor: sourceConfig.color }}>
        {sourceConfig.icon}
      </span>
    )
  }

  if (isLoading) {
    return null // Don't render anything while loading
  }

  if (testimonials.length === 0) {
    return null // Don't render if no testimonials
  }

  const currentTestimonial = testimonials[currentIndex]

  return (
    <section id="testimonials" className="testimonials-section">
      <h2>What our customers say:</h2>
      <div
        className="testimonials-carousel"
        onMouseEnter={() => setIsPaused(true)}
        onMouseLeave={() => setIsPaused(false)}
      >
        <button
          className="carousel-nav carousel-nav-prev"
          onClick={goToPrevious}
          aria-label="Previous testimonial"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M15 18l-6-6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>

        <div className={`testimonial-card ${isTransitioning ? 'transitioning' : ''}`}>
          <div className="testimonial-header">
            {renderRating(currentTestimonial.star_rating)}
            {renderSourceBadge(currentTestimonial.source)}
          </div>
          <blockquote className="testimonial-text">
            {`"${currentTestimonial.review_text}"`}
          </blockquote>
          <div className="testimonial-footer">
            <span className="testimonial-author">{currentTestimonial.customer_name}</span>
            {currentTestimonial.date_of_travel && (
              <span className="testimonial-date">{formatDate(currentTestimonial.date_of_travel)}</span>
            )}
          </div>
        </div>

        <button
          className="carousel-nav carousel-nav-next"
          onClick={goToNext}
          aria-label="Next testimonial"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M9 18l6-6-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      </div>

      <div className="testimonial-dots">
        {testimonials.map((_, index) => (
          <button
            key={index}
            className={`dot ${index === currentIndex ? 'active' : ''}`}
            onClick={() => {
              setIsTransitioning(true)
              setTimeout(() => {
                setCurrentIndex(index)
                setIsTransitioning(false)
              }, 300)
            }}
            aria-label={`Go to testimonial ${index + 1}`}
          />
        ))}
      </div>

      <div className="testimonials-press">
        <svg className="press-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M19 3H5C3.89543 3 3 3.89543 3 5V19C3 20.1046 3.89543 21 5 21H19C20.1046 21 21 20.1046 21 19V5C21 3.89543 20.1046 3 19 3Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M7 7H12" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
          <path d="M7 11H17" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
          <path d="M7 15H17" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
        </svg>
        <span>Read our story in the </span>
        <a
          href="https://www.bournemouthecho.co.uk/news/25707007.new-parking-business-launches-near-bournemouth-airport/"
          target="_blank"
          rel="noopener noreferrer"
          className="press-link"
        >
          Daily Echo
        </a>
      </div>

      <div className="testimonials-press testimonials-press-featured">
        <span>As featured in the </span>
        <button
          onClick={() => setShowPressModal(true)}
          className="press-link press-link-papers"
        >
          <span className="papers-desktop">Southern Daily Echo, Dorset Echo & Salisbury Journal</span>
          <span className="papers-mobile">Dorset Echo,<br />Southern Daily Echo & Salisbury Journal</span>
        </button>
      </div>

      {/* Press Article Modal */}
      {showPressModal && (
        <div className="press-modal-overlay" onClick={() => setShowPressModal(false)}>
          <div className="press-modal" onClick={(e) => e.stopPropagation()}>
            <button
              className="press-modal-close"
              onClick={() => setShowPressModal(false)}
              aria-label="Close"
            >
              ✕
            </button>
            <img
              src="/assets/tag-press-article.png"
              alt="Tag Parking featured in Southern Daily Echo, Dorset Echo & Salisbury Journal"
              className="press-modal-image"
            />
          </div>
        </div>
      )}
    </section>
  )
}

export default TestimonialsCarousel
