import { useState, useEffect } from 'react'
import './AvailabilityTracker.css'

function AvailabilityTracker() {
  const [availability, setAvailability] = useState([])

  // Get the next Sunday from a given date
  const getNextSunday = (date) => {
    const result = new Date(date)
    const dayOfWeek = result.getDay()
    const daysUntilSunday = dayOfWeek === 0 ? 7 : 7 - dayOfWeek
    result.setDate(result.getDate() + daysUntilSunday)
    return result
  }

  // Format date as "DD MMM"
  const formatDate = (date) => {
    const options = { day: 'numeric', month: 'short' }
    return date.toLocaleDateString('en-GB', options)
  }

  // Generate random availability data for demo purposes
  // In production, this will come from actual booking data
  const generateAvailability = () => {
    const weeks = []
    const today = new Date()
    let currentSunday = getNextSunday(today)

    for (let i = 0; i < 4; i++) {
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
        date: formatDate(currentSunday),
        label: `Week ending ${formatDate(currentSunday)}`,
        percentage,
        status: percentage <= 65 ? 'green' : percentage <= 84 ? 'yellow' : 'red'
      })

      // Move to next Sunday
      currentSunday = new Date(currentSunday)
      currentSunday.setDate(currentSunday.getDate() + 7)
    }

    return weeks
  }

  useEffect(() => {
    // Initial load
    setAvailability(generateAvailability())

    // Update every 2 minutes (120000ms) with gradual changes
    const interval = setInterval(() => {
      setAvailability(prevAvailability => {
        return prevAvailability.map(week => {
          // Gradually increase percentage by 1-3%
          const increase = Math.floor(Math.random() * 3) + 1
          let newPercentage = week.percentage + increase

          // Cap at 100%
          if (newPercentage > 100) newPercentage = 100

          // Determine new status based on percentage
          const newStatus = newPercentage <= 65 ? 'green' : newPercentage <= 84 ? 'yellow' : 'red'

          return {
            ...week,
            percentage: newPercentage,
            status: newStatus
          }
        })
      })
    }, 120000) // 2 minutes

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

        <div className="availability-bars">
          {availability.map((week) => (
            <div key={week.week} className="availability-row">
              <div className="availability-info">
                <div className="week-date">
                  <span className="week-ending-label">Week ending</span>
                  <span className="week-date-value">{week.date}</span>
                </div>
                <div className="availability-status">{getStatusLabel(week.status)}</div>
              </div>
              <div className="bar-container">
                <div
                  className={`availability-bar ${week.status}`}
                  style={{ width: `${week.percentage}%` }}
                >
                  <span className="bar-percentage">{week.percentage}%</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

export default AvailabilityTracker
