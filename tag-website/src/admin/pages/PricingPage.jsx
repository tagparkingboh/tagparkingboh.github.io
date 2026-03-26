import { useState, useEffect } from 'react'
import { useAuth } from '../../AuthContext'
import { API_URL } from '../adminUtils'
import '../adminStyles.css'

function PricingPage() {
  const { token } = useAuth()
  const [pricing, setPricing] = useState({
    days_1_4_price: 65,
    week1_base_price: 85,
    week2_base_price: 150,
    daily_increment: 8,
    tier_increment: 5,
  })
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (token) fetchPricing()
  }, [token])

  const fetchPricing = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/admin/pricing`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        const data = await response.json()
        setPricing(data)
      }
    } catch (err) {
      console.error('Failed to fetch pricing:', err)
    } finally {
      setLoading(false)
    }
  }

  const savePricing = async () => {
    setSaving(true)
    setMessage('')
    try {
      const response = await fetch(`${API_URL}/api/admin/pricing`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(pricing)
      })
      if (response.ok) {
        setMessage('Pricing saved successfully!')
        setTimeout(() => setMessage(''), 3000)
      } else {
        setMessage('Failed to save pricing')
      }
    } catch (err) {
      setMessage('Network error saving pricing')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h2>Pricing Settings</h2>
        <button className="btn-primary" onClick={savePricing} disabled={saving || loading}>
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>

      {message && <div className={message.includes('success') ? 'admin-success' : 'admin-error'}>{message}</div>}

      {loading ? (
        <div className="admin-loading-inline">Loading pricing...</div>
      ) : (
        <div style={{ maxWidth: '500px' }}>
          <div style={{ marginBottom: '20px' }}>
            <h3 style={{ marginBottom: '15px', color: '#333' }}>Anchor Pricing</h3>

            <div style={{ marginBottom: '15px' }}>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>1-4 Days Price (£)</label>
              <input
                type="number"
                value={pricing.days_1_4_price}
                onChange={(e) => setPricing({ ...pricing, days_1_4_price: Number(e.target.value) })}
                style={{ width: '100%', padding: '10px', border: '1px solid #ddd', borderRadius: '6px' }}
              />
            </div>

            <div style={{ marginBottom: '15px' }}>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>Week 1 Base Price (7 days) (£)</label>
              <input
                type="number"
                value={pricing.week1_base_price}
                onChange={(e) => setPricing({ ...pricing, week1_base_price: Number(e.target.value) })}
                style={{ width: '100%', padding: '10px', border: '1px solid #ddd', borderRadius: '6px' }}
              />
            </div>

            <div style={{ marginBottom: '15px' }}>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>Week 2 Base Price (14 days) (£)</label>
              <input
                type="number"
                value={pricing.week2_base_price}
                onChange={(e) => setPricing({ ...pricing, week2_base_price: Number(e.target.value) })}
                style={{ width: '100%', padding: '10px', border: '1px solid #ddd', borderRadius: '6px' }}
              />
            </div>
          </div>

          <div>
            <h3 style={{ marginBottom: '15px', color: '#333' }}>Increments</h3>

            <div style={{ marginBottom: '15px' }}>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>Daily Increment (£)</label>
              <input
                type="number"
                value={pricing.daily_increment}
                onChange={(e) => setPricing({ ...pricing, daily_increment: Number(e.target.value) })}
                style={{ width: '100%', padding: '10px', border: '1px solid #ddd', borderRadius: '6px' }}
              />
              <small style={{ color: '#666' }}>Price increase per day between anchor points</small>
            </div>

            <div style={{ marginBottom: '15px' }}>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>Tier Increment (£)</label>
              <input
                type="number"
                value={pricing.tier_increment}
                onChange={(e) => setPricing({ ...pricing, tier_increment: Number(e.target.value) })}
                style={{ width: '100%', padding: '10px', border: '1px solid #ddd', borderRadius: '6px' }}
              />
              <small style={{ color: '#666' }}>Price difference between Early/Standard/Late booking tiers</small>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default PricingPage
