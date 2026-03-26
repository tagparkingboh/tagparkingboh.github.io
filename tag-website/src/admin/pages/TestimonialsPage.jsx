import { useState, useEffect } from 'react'
import { useAuth } from '../../AuthContext'
import { API_URL } from '../adminUtils'
import '../adminStyles.css'

function TestimonialsPage() {
  const { token } = useAuth()
  const [testimonials, setTestimonials] = useState([])
  const [loading, setLoading] = useState(false)
  const [filter, setFilter] = useState({ star_rating: '', status: '' })

  useEffect(() => {
    if (token) fetchTestimonials()
  }, [token, filter])

  const fetchTestimonials = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (filter.star_rating) params.append('star_rating', filter.star_rating)
      if (filter.status) params.append('status', filter.status)

      const response = await fetch(`${API_URL}/api/admin/testimonials?${params}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        const data = await response.json()
        setTestimonials(data.testimonials || [])
      }
    } catch (err) {
      console.error('Failed to fetch testimonials:', err)
    } finally {
      setLoading(false)
    }
  }

  const toggleStatus = async (testimonial) => {
    try {
      const response = await fetch(`${API_URL}/api/admin/testimonials/${testimonial.id}/status`, {
        method: 'PATCH',
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        fetchTestimonials()
      }
    } catch (err) {
      console.error('Failed to toggle status:', err)
    }
  }

  const renderStars = (rating) => {
    if (rating === null || rating === undefined) return <span style={{ color: '#999' }}>No rating</span>
    return (
      <span style={{ color: '#f7b32b' }}>
        {'★'.repeat(rating)}{'☆'.repeat(5 - rating)}
      </span>
    )
  }

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h2>Testimonials</h2>
        <button className="btn-primary">+ Add Testimonial</button>
      </div>

      <div className="admin-filters">
        <select
          value={filter.star_rating}
          onChange={(e) => setFilter({ ...filter, star_rating: e.target.value })}
          className="admin-select"
        >
          <option value="">All Ratings</option>
          <option value="5">5 Stars</option>
          <option value="4">4 Stars</option>
          <option value="3">3 Stars</option>
          <option value="2">2 Stars</option>
          <option value="1">1 Star</option>
        </select>
        <select
          value={filter.status}
          onChange={(e) => setFilter({ ...filter, status: e.target.value })}
          className="admin-select"
        >
          <option value="">All Status</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
        <span className="admin-filter-count">{testimonials.length} testimonials</span>
      </div>

      {loading ? (
        <div className="admin-loading-inline">Loading testimonials...</div>
      ) : testimonials.length === 0 ? (
        <p className="admin-empty">No testimonials found</p>
      ) : (
        <div style={{ display: 'grid', gap: '15px' }}>
          {testimonials.map(t => (
            <div key={t.id} style={{
              background: '#f9f9f9',
              padding: '20px',
              borderRadius: '8px',
              borderLeft: `4px solid ${t.status === 'active' ? '#28a745' : '#999'}`
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
                <div>
                  <strong>{t.customer_name}</strong>
                  <div>{renderStars(t.star_rating)}</div>
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                  <button
                    className="btn-secondary btn-sm"
                    onClick={() => toggleStatus(t)}
                  >
                    {t.status === 'active' ? 'Deactivate' : 'Activate'}
                  </button>
                  <button className="btn-secondary btn-sm">Edit</button>
                </div>
              </div>
              <p style={{ margin: '10px 0', color: '#444', fontStyle: 'italic' }}>
                "{t.review_text}"
              </p>
              <div style={{ fontSize: '12px', color: '#888' }}>
                {t.date_of_travel && `Travel: ${t.date_of_travel}`}
                {t.source && ` | Source: ${t.source}`}
                {t.is_featured && <span style={{ marginLeft: '10px', color: '#f7b32b' }}>Featured</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default TestimonialsPage
