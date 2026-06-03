import { useState, useEffect } from 'react'
import './TestimonialsCarousel.css'

function TestimonialsCarousel() {
  const [testimonials, setTestimonials] = useState([])
  const [stats, setStats] = useState(null)
  const [cyclingIndex, setCyclingIndex] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [showPressModal, setShowPressModal] = useState(false)
  const [currentPage, setCurrentPage] = useState(0) // Pagination only used when showAll
  const [expandedReview, setExpandedReview] = useState(null) // Expanded review modal
  const [showAll, setShowAll] = useState(false) // false = top 10 only; true = full archive

  // Fetch testimonials from API
  useEffect(() => {
    const fetchTestimonials = async () => {
      const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      try {
        const response = await fetch(`${API_URL}/api/testimonials`)
        const data = await response.json()
        if (data.testimonials && data.testimonials.length > 0) {
          // API returns a weighted pool (5★ × 5, 4★ × 3, etc.). Dedupe first
          // so weighting doesn't multiply the same review across the grid,
          // then sort by date_added desc so the default 10 are the freshest.
          // Falls back to id desc when date_added is missing (legacy rows).
          const unique = deduplicateTestimonials([...data.testimonials])
          unique.sort((a, b) => {
            const da = a.date_added ? new Date(a.date_added).getTime() : 0
            const db = b.date_added ? new Date(b.date_added).getTime() : 0
            if (db !== da) return db - da
            return (b.id || 0) - (a.id || 0)
          })
          setTestimonials(unique)
        }
        // Store stats if available
        if (data.stats) {
          setStats(data.stats)
        }
      } catch (error) {
        console.error('Error fetching testimonials:', error)
      } finally {
        setIsLoading(false)
      }
    }
    fetchTestimonials()
  }, [])

  // Deduplicate testimonials by ID (keep first occurrence)
  const deduplicateTestimonials = (array) => {
    const seen = new Set()
    return array.filter((item) => {
      if (seen.has(item.id)) return false
      seen.add(item.id)
      return true
    })
  }

  // Build cycling items from buzz words with proper phrasing
  const formatBuzzWord = (word) => {
    const w = word.toLowerCase()
    if (w === 'recommend') return { phrase: "say they'd", buzzWord: 'Recommend' }
    if (w === 'friendly team') return { phrase: 'mention', buzzWord: 'Friendly Team' }
    if (w === 'stress free') return { phrase: "say it's", buzzWord: 'Stress Free' }
    if (w === 'on time') return { phrase: 'say we are', buzzWord: 'On Time' }
    if (w === 'good value') return { phrase: "say it's", buzzWord: 'Good Value' }
    if (w === 'safe & secure') return { phrase: 'felt', buzzWord: 'Safe & Secure' }
    if (w === 'use again') return { phrase: "say they'll", buzzWord: 'Use Again' }
    if (w === 'smooth service') return { phrase: 'mention', buzzWord: 'Smooth Service' }
    return { phrase: "say it's", buzzWord: word }
  }

  const cyclingItems = stats?.buzz_words?.map(bw => {
    const { phrase, buzzWord } = formatBuzzWord(bw.word)
    return { count: bw.count, phrase, buzzWord }
  }) || []
  const cyclingGroups = []
  for (let i = 0; i < cyclingItems.length; i += 3) {
    cyclingGroups.push(cyclingItems.slice(i, i + 3))
  }
  const currentBuzzGroup = cyclingGroups[cyclingIndex] || []

  // Cycle through groups every 3 seconds
  useEffect(() => {
    if (cyclingGroups.length <= 1) return
    const interval = setInterval(() => {
      setCyclingIndex((prev) => (prev + 1) % cyclingGroups.length)
    }, 3000)
    return () => clearInterval(interval)
  }, [cyclingGroups.length])

  // Render star rating (or nothing for unrated)
  const renderRating = (rating) => {
    if (rating === null || rating === undefined) {
      return null
    }
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

  // Format date as "Feb 2026"
  const formatDate = (dateString) => {
    if (!dateString) return ''
    const date = new Date(dateString)
    return date.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
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

  // Home-page default: surface only the most recent 10. "View all" toggle
  // reveals the full archive with the existing 12-per-page pagination.
  const DEFAULT_VISIBLE_COUNT = 10
  const pageSize = 12
  const totalPages = Math.ceil(testimonials.length / pageSize)

  const nextPage = () => {
    setCurrentPage(prev => Math.min(prev + 1, totalPages - 1))
  }

  const prevPage = () => {
    setCurrentPage(prev => Math.max(prev - 1, 0))
  }

  if (isLoading) {
    return null
  }

  if (testimonials.length === 0) {
    return null
  }

  let visibleTestimonials
  let hasNext = false
  let hasPrev = false
  if (showAll) {
    const startIndex = currentPage * pageSize
    visibleTestimonials = testimonials.slice(startIndex, startIndex + pageSize)
    hasNext = currentPage < totalPages - 1
    hasPrev = currentPage > 0
  } else {
    visibleTestimonials = testimonials.slice(0, DEFAULT_VISIBLE_COUNT)
  }

  const hiddenCount = testimonials.length - DEFAULT_VISIBLE_COUNT

  return (
    <section id="testimonials" className="testimonials-section">
      <h2>What our customers say:</h2>

      {/* Stats Bar */}
      {stats && (
        <div className="testimonials-stats">
          <div className="stats-bar">
            <div className="stats-primary-row">
              <div className="stat-box">
                <span className="stat-value">{stats.average_rating}<span className="stat-star">★</span></span>
                <span className="stat-label">Average</span>
              </div>
              <div className="stat-divider" />
              <div className="stat-box">
                <span className="stat-value">{stats.total_count}</span>
                <span className="stat-label">Reviews</span>
              </div>
            </div>
            {currentBuzzGroup.length > 0 && (
              <div className="stat-box stat-box-buzz">
                {currentBuzzGroup.map((item) => (
                  <div className="stat-buzz-item" key={item.buzzWord}>
                    <span className="stat-buzz-line1">
                      {item.count}× {item.phrase}
                    </span>
                    <span className="stat-buzz-line2">
                      "{item.buzzWord}"
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Masonry Grid */}
      <div className="testimonials-masonry">
        {visibleTestimonials.map((testimonial, index) => (
          <div
            key={testimonial.id}
            className="masonry-card"
            style={{ animationDelay: `${(index % 12) * 0.05}s` }}
            onClick={() => setExpandedReview(testimonial)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && setExpandedReview(testimonial)}
          >
            <div className="masonry-card-header">
              {renderRating(testimonial.star_rating)}
              {renderSourceBadge(testimonial.source)}
            </div>
            <blockquote className="masonry-card-text">
              "{testimonial.review_text}"
            </blockquote>
            <div className="masonry-card-footer">
              <span className="masonry-card-author">{testimonial.customer_name}</span>
              {testimonial.date_of_travel && (
                <span className="masonry-card-date">{formatDate(testimonial.date_of_travel)}</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Expanded Review Modal */}
      {expandedReview && (
        <div className="review-modal-overlay" onClick={() => setExpandedReview(null)}>
          <div className="review-modal" onClick={(e) => e.stopPropagation()}>
            <button
              className="review-modal-close"
              onClick={() => setExpandedReview(null)}
              aria-label="Close"
            >
              ✕
            </button>
            <div className="review-modal-header">
              {renderRating(expandedReview.star_rating)}
              {renderSourceBadge(expandedReview.source)}
            </div>
            <blockquote className="review-modal-text">
              "{expandedReview.review_text}"
            </blockquote>
            <div className="review-modal-footer">
              <span className="review-modal-author">{expandedReview.customer_name}</span>
              {expandedReview.date_of_travel && (
                <span className="review-modal-date">{formatDate(expandedReview.date_of_travel)}</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* "View all" toggle (collapsed default) */}
      {!showAll && hiddenCount > 0 && (
        <div className="testimonials-view-all">
          <button
            className="testimonials-view-all-btn"
            onClick={() => { setShowAll(true); setCurrentPage(0) }}
          >
            View all {testimonials.length} reviews
          </button>
        </div>
      )}

      {/* Pagination (only when expanded to full archive) */}
      {showAll && totalPages > 1 && (
        <div className="testimonials-pagination">
          <button
            className="testimonials-page-btn"
            onClick={prevPage}
            disabled={!hasPrev}
          >
            ← Previous
          </button>
          <span className="testimonials-page-info">
            Page {currentPage + 1} of {totalPages}
          </span>
          <button
            className="testimonials-page-btn"
            onClick={nextPage}
            disabled={!hasNext}
          >
            Next →
          </button>
        </div>
      )}

      {/* Show-fewer toggle (visible only when expanded) */}
      {showAll && (
        <div className="testimonials-view-all">
          <button
            className="testimonials-view-all-btn testimonials-view-all-btn--collapse"
            onClick={() => { setShowAll(false); setCurrentPage(0) }}
          >
            Show fewer
          </button>
        </div>
      )}

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
            <iframe
              src="/assets/Tag edit.pdf"
              title="Tag Parking featured in Southern Daily Echo, Dorset Echo & Salisbury Journal"
              className="press-modal-pdf"
            />
          </div>
        </div>
      )}
    </section>
  )
}

export default TestimonialsCarousel
