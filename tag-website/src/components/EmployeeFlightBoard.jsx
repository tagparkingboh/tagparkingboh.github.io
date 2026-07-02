import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../AuthContext'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Refetch from OUR database every 5 minutes; the airport site is only hit by
// the backend's 30-minute scheduled scrape, never by this component.
const REFRESH_INTERVAL_MS = 5 * 60 * 1000

export const flightStatusClass = (status) => {
  const s = (status || '').toLowerCase()
  if (s.startsWith('landed') || s.startsWith('departed')) return 'fb-status-done'
  if (s.includes('delay') || s.includes('cancel') || s.includes('divert')) return 'fb-status-alert'
  if (s.startsWith('expected')) return 'fb-status-expected'
  if (s.includes('lounge') || s.includes('boarding') || s.includes('gate')) return 'fb-status-active'
  return 'fb-status-scheduled'
}

const formatUpdatedStamp = (scrapedAt, ageMinutes) => {
  if (!scrapedAt) return null
  const d = new Date(scrapedAt)
  if (Number.isNaN(d.getTime())) return null
  const hhmm = d.toLocaleTimeString('en-GB', {
    timeZone: 'Europe/London',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
  if (ageMinutes === null || ageMinutes === undefined) return `Updated ${hhmm}`
  return `Updated ${hhmm} (${ageMinutes} min ago)`
}

function EmployeeFlightBoard() {
  const { authFetch } = useAuth()
  const [board, setBoard] = useState(null)
  const [activeDirection, setActiveDirection] = useState('arrivals')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchBoard = useCallback(async () => {
    try {
      setError(null)
      const response = await authFetch(`${API_URL}/api/employee/flight-board`)
      if (!response.ok) throw new Error('Failed to load flight board')
      setBoard(await response.json())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    fetchBoard()
    const intervalId = setInterval(fetchBoard, REFRESH_INTERVAL_MS)
    return () => clearInterval(intervalId)
  }, [fetchBoard])

  const rows = board?.[activeDirection] || []
  const updatedStamp = formatUpdatedStamp(board?.scraped_at, board?.age_minutes)

  return (
    <section className="flight-board-section">
      <div className="flight-board-header">
        <h2>Bournemouth Airport — Live Flights</h2>
        <div className="flight-board-meta">
          {updatedStamp && (
            <span className={`flight-board-updated ${board?.stale ? 'flight-board-stale' : ''}`}>
              {updatedStamp}
              {board?.stale ? ' — may be out of date' : ''}
            </span>
          )}
          <button className="flight-board-refresh" onClick={fetchBoard} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      <div className="flight-board-tabs">
        <button
          className={`flight-board-tab ${activeDirection === 'arrivals' ? 'active' : ''}`}
          onClick={() => setActiveDirection('arrivals')}
        >
          Arrivals
        </button>
        <button
          className={`flight-board-tab ${activeDirection === 'departures' ? 'active' : ''}`}
          onClick={() => setActiveDirection('departures')}
        >
          Departures
        </button>
      </div>

      {error && <div className="flight-board-error">{error}</div>}

      {loading && !board ? (
        <p className="flight-board-empty">Loading flight board…</p>
      ) : !board?.available ? (
        <p className="flight-board-empty">
          No flight data yet — the board updates automatically every 30 minutes.
        </p>
      ) : rows.length === 0 ? (
        <p className="flight-board-empty">
          No {activeDirection} listed right now.
        </p>
      ) : (
        <div className="flight-board-table-wrap">
          <table className="flight-board-table">
            <thead>
              <tr>
                <th>{activeDirection === 'arrivals' ? 'From' : 'To'}</th>
                <th>Airline</th>
                <th>Flight</th>
                <th>Date</th>
                <th>Scheduled</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => (
                <tr key={`${row.flight || 'row'}-${idx}`}>
                  <td className="fb-place">{row.place || '-'}</td>
                  <td>{row.airline || '-'}</td>
                  <td className="fb-flight">{row.flight || '-'}</td>
                  <td>{row.date || '-'}</td>
                  <td className="fb-scheduled">{row.scheduled || '-'}</td>
                  <td className={flightStatusClass(row.status)}>{row.status || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default EmployeeFlightBoard
