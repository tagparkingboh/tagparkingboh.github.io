import { useState, useEffect } from 'react'
import './AvailabilityTracker.css'

function AvailabilityTracker() {
  const [availability, setAvailability] = useState([])

  // Generate random availability data for demo purposes
  // In production, this will come from actual booking data
  const generateAvailability = () => {
    const weeks = []
    const today = new Date()

    for (let i = 0; i < 4; i++) {
      const weekStart = new Date(today)
      weekStart.setDate(today.getDate() + (i * 7))

      // Generate random percentage (weighted towards lower values for realism)
      const random = Math.random()
      let percentage
      if (random < 0.5) {
        percentage = Math.floor(Math.random() * 50) + 10 // 10-60%
      } else if (random < 0.8) {
        percentage = Math.floor(Math.random() * 20) + 60 // 60-80%
      } else {
        percentage = Math.floor(Math.random() * 15) + 85 // 85-100%
      }

      weeks.push({
        week: i + 1,
        label: i === 0 ? 'This Week' : `Week ${i + 1}`,
        percentage,
        status: percentage <= 65 ? 'green' : percentage <= 84 ? 'yellow' : 'red'
      })
    }

    return weeks
  }

  useEffect(() => {
    // Initial load
    setAvailability(generateAvailability())

    // Update every 30 minutes (1800000ms)
    const interval = setInterval(() => {
      setAvailability(generateAvailability())
    }, 1800000)

    return () => clearInterval(interval)
  }, [])

  const getStatusLabel = (status) => {
    switch (status) {
      case 'green':
        return 'Available'
      case 'yellow':
        return 'Filling Up'
      case 'red':
        return 'Almost Full'
      default:
        return ''
    }
  }

  return (
    <section className="availability-tracker">
      <div className="availability-container">
        <h2 className="availability-title">Parking Availability</h2>
        <p className="availability-subtitle">Real-time availability for the next 4 weeks</p>

        <div className="availability-grid">
          {availability.map((week) => (
            <div key={week.week} className="availability-card">
              <div className="week-label">{week.label}</div>
              <div className={`traffic-light ${week.status}`}>
                <div className="light red-light"></div>
                <div className="light yellow-light"></div>
                <div className="light green-light"></div>
              </div>
              <div className="availability-status">{getStatusLabel(week.status)}</div>
              <div className="availability-percentage">{week.percentage}% booked</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

export default AvailabilityTracker
