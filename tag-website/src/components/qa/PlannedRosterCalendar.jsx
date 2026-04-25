import { useEffect, useMemo, useState } from 'react'
import './PlannedRosterCalendar.css'

/**
 * Shadow-mode QA Roster Planner.
 *
 * Renders the engine's latest run (or any historical run) as a calendar
 * of proposed shifts. Backed by the read endpoints
 *   GET /api/admin/qa/roster-planner/runs
 *   GET /api/admin/qa/roster-planner/runs/{run_id}
 * Backend never writes roster_shifts in this mode — what the user sees
 * here is "what the engine would have done." The UI has no commit
 * affordance by design.
 */
export default function PlannedRosterCalendar({ apiUrl, token }) {
  const [runs, setRuns] = useState([])
  const [selectedRunId, setSelectedRunId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState(null)

  const authHeader = useMemo(
    () => (token ? { Authorization: `Bearer ${token}` } : {}),
    [token]
  )

  // Initial load — fetch the run history; auto-select the newest.
  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch(
          `${apiUrl}/api/admin/qa/roster-planner/runs?limit=50`,
          { headers: authHeader }
        )
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const body = await res.json()
        if (cancelled) return
        setRuns(body)
        if (body.length > 0) setSelectedRunId(body[0].run_id)
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load runs')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [apiUrl, authHeader])

  // Detail load — when the selection changes.
  useEffect(() => {
    if (!selectedRunId) {
      setDetail(null)
      return
    }
    let cancelled = false
    async function loadDetail() {
      setDetailLoading(true)
      try {
        const res = await fetch(
          `${apiUrl}/api/admin/qa/roster-planner/runs/${selectedRunId}`,
          { headers: authHeader }
        )
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const body = await res.json()
        if (!cancelled) setDetail(body)
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load run detail')
      } finally {
        if (!cancelled) setDetailLoading(false)
      }
    }
    loadDetail()
    return () => {
      cancelled = true
    }
  }, [apiUrl, authHeader, selectedRunId])

  async function runNow() {
    setError(null)
    try {
      const res = await fetch(
        `${apiUrl}/api/admin/qa/roster-planner/propose`,
        { method: 'POST', headers: authHeader }
      )
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      // /propose records a 'manual' run server-side. Refresh the list.
      const listRes = await fetch(
        `${apiUrl}/api/admin/qa/roster-planner/runs?limit=50`,
        { headers: authHeader }
      )
      const list = await listRes.json()
      setRuns(list)
      if (list.length > 0) setSelectedRunId(list[0].run_id)
    } catch (err) {
      setError(err.message || 'Failed to run engine')
    }
  }

  // Group proposed_shifts by date for the calendar render.
  const shiftsByDate = useMemo(() => {
    const proposal = detail?.proposal
    if (!proposal?.proposed_shifts) return {}
    const grouped = {}
    for (const s of proposal.proposed_shifts) {
      const key = s.date
      if (!grouped[key]) grouped[key] = []
      grouped[key].push(s)
    }
    // Sort each day's shifts by start time.
    for (const day of Object.keys(grouped)) {
      grouped[day].sort((a, b) => (a.start_time > b.start_time ? 1 : -1))
    }
    return grouped
  }, [detail])

  const sortedDates = useMemo(
    () => Object.keys(shiftsByDate).sort(),
    [shiftsByDate]
  )

  return (
    <div className="prp-root">
      <div className="prp-header">
        <div>
          <h2>Roster Planner — Shadow Mode</h2>
          <p className="prp-subtitle">
            What the engine <em>would</em> do. Reads bookings, shifts,
            holidays, and the locked rules. Never writes.
          </p>
        </div>
        <button className="prp-run-btn" onClick={runNow}>
          Run engine now
        </button>
      </div>

      {error && <div className="prp-error">{error}</div>}

      <div className="prp-layout">
        <div className="prp-headline">
          {loading && <div className="prp-empty">Loading…</div>}
          {!loading && runs.length === 0 && (
            <div className="prp-empty">
              No runs yet. The engine fires automatically on booking,
              holiday, or settings events. Click <em>Run engine now</em>{' '}
              to generate one immediately.
            </div>
          )}
          {!loading && detail && (
            <>
              <RunSummary detail={detail} loading={detailLoading} />
              <ProposalCalendar
                shiftsByDate={shiftsByDate}
                sortedDates={sortedDates}
              />
              <WarningsList warnings={detail.warnings || []} />
            </>
          )}
        </div>

        <div className="prp-history">
          <h3>Recent runs</h3>
          {runs.length === 0 && <div className="prp-empty">No history yet.</div>}
          {runs.map((r) => (
            <button
              key={r.run_id}
              className={`prp-history-row ${
                r.run_id === selectedRunId ? 'selected' : ''
              } ${r.has_error ? 'errored' : ''}`}
              onClick={() => setSelectedRunId(r.run_id)}
              title={r.run_id}
            >
              <div className="prp-history-time">
                {new Date(r.triggered_at).toLocaleString('en-GB', {
                  timeZone: 'Europe/London',
                  day: '2-digit',
                  month: 'short',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </div>
              <div className="prp-history-trigger">{r.trigger_event}</div>
              {r.summary && (
                <div className="prp-history-summary">
                  {r.summary.new_shifts ?? 0} new
                  {r.summary.unmanned_events
                    ? ` · ${r.summary.unmanned_events} unmanned`
                    : ''}
                </div>
              )}
              {r.has_error && (
                <div className="prp-history-error">⚠ error</div>
              )}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function RunSummary({ detail, loading }) {
  const proposal = detail.proposal
  const summary = proposal?.summary || {}
  return (
    <div className="prp-run-summary">
      <div className="prp-run-meta">
        <span>
          <strong>Window:</strong> {detail.window_start} → {detail.window_end}
        </span>
        <span>
          <strong>Triggered:</strong>{' '}
          {new Date(detail.triggered_at).toLocaleString('en-GB', {
            timeZone: 'Europe/London',
          })}{' '}
          via <code>{detail.trigger_event}</code>
        </span>
        {detail.duration_ms != null && (
          <span>
            <strong>Engine time:</strong> {detail.duration_ms} ms
          </span>
        )}
      </div>
      <div className="prp-summary-counts">
        <Counter label="New" value={summary.new_shifts ?? 0} />
        <Counter label="Extended" value={summary.extended_shifts ?? 0} />
        <Counter label="Untouched" value={summary.untouched_shifts ?? 0} />
        <Counter
          label="Unmanned"
          value={summary.unmanned_events ?? 0}
          tone={summary.unmanned_events > 0 ? 'warn' : 'ok'}
        />
        <Counter
          label="At max hours"
          value={summary.staff_hit_max_hours ?? 0}
          tone={summary.staff_hit_max_hours > 0 ? 'warn' : 'ok'}
        />
      </div>
      {loading && <div className="prp-loading-tag">refreshing…</div>}
      {detail.error_text && (
        <div className="prp-error">
          Engine errored: <code>{detail.error_text}</code>
        </div>
      )}
    </div>
  )
}

function Counter({ label, value, tone = 'neutral' }) {
  return (
    <div className={`prp-counter prp-counter-${tone}`}>
      <div className="prp-counter-value">{value}</div>
      <div className="prp-counter-label">{label}</div>
    </div>
  )
}

function ProposalCalendar({ shiftsByDate, sortedDates }) {
  if (sortedDates.length === 0) {
    return (
      <div className="prp-empty">
        No proposed shifts in this window. (Empty bookings, or all dates
        already covered.)
      </div>
    )
  }
  return (
    <div className="prp-calendar">
      {sortedDates.map((dateStr) => (
        <div key={dateStr} className="prp-day">
          <div className="prp-day-header">
            {new Date(dateStr).toLocaleDateString('en-GB', {
              timeZone: 'Europe/London',
              weekday: 'short',
              day: '2-digit',
              month: 'short',
            })}
          </div>
          <div className="prp-day-shifts">
            {shiftsByDate[dateStr].map((s, i) => (
              <ShiftCard key={i} shift={s} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function ShiftCard({ shift }) {
  const unassigned = !shift.staff_id
  return (
    <div className={`prp-shift ${unassigned ? 'unassigned' : ''} prp-shift-${shift.kind || 'new'}`}>
      <div className="prp-shift-time">
        {shift.start_time}–{shift.end_time}
      </div>
      <div className="prp-shift-staff">
        {unassigned ? '? unassigned' : shift.staff_initials || `staff #${shift.staff_id}`}
      </div>
      {shift.shift_type && (
        <div className="prp-shift-type">{shift.shift_type}</div>
      )}
      {shift.linked_booking_refs?.length > 0 && (
        <div className="prp-shift-bookings">
          {shift.linked_booking_refs.map((ref) => (
            <span key={ref} className="prp-shift-booking">
              {ref}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function WarningsList({ warnings }) {
  if (warnings.length === 0) return null
  return (
    <div className="prp-warnings">
      <h4>Warnings ({warnings.length})</h4>
      <ul>
        {warnings.map((w, i) => (
          <li key={i} className={`prp-warning prp-warning-${w.severity || 'info'}`}>
            <code>{w.rule}</code>
            {w.message && <> — {w.message}</>}
          </li>
        ))}
      </ul>
    </div>
  )
}
