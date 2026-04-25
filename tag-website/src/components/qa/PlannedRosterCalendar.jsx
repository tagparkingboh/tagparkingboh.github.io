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
  const [feedbackShift, setFeedbackShift] = useState(null)
  const [feedbackShiftIndex, setFeedbackShiftIndex] = useState(null)

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

  // Group proposed_shifts by date. Stamp the original index onto each
  // shift so feedback can reference proposed_shift_index even after the
  // group-and-sort scrambles ordering.
  const shiftsByDate = useMemo(() => {
    const proposal = detail?.proposal
    if (!proposal?.proposed_shifts) return {}
    const grouped = {}
    proposal.proposed_shifts.forEach((s, idx) => {
      const key = s.date
      if (!grouped[key]) grouped[key] = []
      grouped[key].push({ ...s, __index: idx })
    })
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
                onShiftClick={(shift, idx) => {
                  setFeedbackShift(shift)
                  setFeedbackShiftIndex(idx)
                }}
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

      {feedbackShift && detail && (
        <FeedbackModal
          apiUrl={apiUrl}
          authHeader={authHeader}
          runId={detail.run_id}
          shift={feedbackShift}
          shiftIndex={feedbackShiftIndex}
          onClose={() => {
            setFeedbackShift(null)
            setFeedbackShiftIndex(null)
          }}
        />
      )}
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

function ProposalCalendar({ shiftsByDate, sortedDates, onShiftClick }) {
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
            {shiftsByDate[dateStr].map((s) => (
              <ShiftCard
                key={s.__index}
                shift={s}
                onClick={() => onShiftClick?.(s, s.__index)}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function ShiftCard({ shift, onClick }) {
  const unassigned = !shift.staff_id
  return (
    <button
      type="button"
      onClick={onClick}
      className={`prp-shift ${unassigned ? 'unassigned' : ''} prp-shift-${shift.kind || 'new'}`}
      title="Click to give feedback on this engine decision"
    >
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
    </button>
  )
}

function FeedbackModal({ apiUrl, authHeader, runId, shift, shiftIndex, onClose }) {
  const [adminShifts, setAdminShifts] = useState([])
  const [priorFeedback, setPriorFeedback] = useState([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)
  const [severity, setSeverity] = useState('issue')
  const [comment, setComment] = useState('')

  // Fetch admin calendar for this date + prior feedback for the same date.
  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      try {
        const [adminRes, fbRes] = await Promise.all([
          fetch(`${apiUrl}/api/roster?date=${shift.date}`, {
            headers: authHeader,
          }),
          fetch(
            `${apiUrl}/api/admin/qa/roster-planner/feedback?shift_date=${shift.date}`,
            { headers: authHeader }
          ),
        ])
        if (cancelled) return
        const adminBody = adminRes.ok ? await adminRes.json() : []
        const fbBody = fbRes.ok ? await fbRes.json() : []
        setAdminShifts(adminBody)
        setPriorFeedback(fbBody)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [apiUrl, authHeader, shift.date])

  async function submit() {
    if (!comment.trim()) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const res = await fetch(
        `${apiUrl}/api/admin/qa/roster-planner/runs/${runId}/feedback`,
        {
          method: 'POST',
          headers: { ...authHeader, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            shift_date: shift.date,
            shift_start_time: shift.start_time,
            shift_end_time: shift.end_time,
            shift_staff_id: shift.staff_id ?? null,
            proposed_shift_index: shiftIndex,
            severity,
            comment: comment.trim(),
          }),
        }
      )
      if (!res.ok) {
        const detail = await res.text()
        throw new Error(detail || `HTTP ${res.status}`)
      }
      // Refresh prior feedback to include the new row.
      const fbRes = await fetch(
        `${apiUrl}/api/admin/qa/roster-planner/feedback?shift_date=${shift.date}`,
        { headers: authHeader }
      )
      if (fbRes.ok) setPriorFeedback(await fbRes.json())
      setComment('')
      setSeverity('issue')
    } catch (err) {
      setSubmitError(err.message || 'Failed to submit feedback')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="prp-modal-backdrop" onClick={onClose}>
      <div className="prp-modal" onClick={(e) => e.stopPropagation()}>
        <div className="prp-modal-header">
          <h3>
            Engine decision · {shift.start_time}–{shift.end_time} ·{' '}
            {shift.staff_initials || (shift.staff_id ? `staff #${shift.staff_id}` : '? unassigned')}
          </h3>
          <button className="prp-modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className="prp-modal-grid">
          <div className="prp-modal-col">
            <h4>Engine proposal</h4>
            <ShiftDetail shift={shift} />
          </div>
          <div className="prp-modal-col">
            <h4>Admin calendar (live)</h4>
            {loading ? (
              <div className="prp-empty">Loading…</div>
            ) : adminShifts.length === 0 ? (
              <div className="prp-empty">No shifts scheduled on this date.</div>
            ) : (
              <ul className="prp-modal-shift-list">
                {adminShifts.map((s) => (
                  <li key={s.id}>
                    <strong>
                      {formatTime(s.start_time)}–{formatTime(s.end_time)}
                    </strong>{' '}
                    {s.staff_initials || (s.staff_id ? `#${s.staff_id}` : '?')}
                    {s.status && (
                      <span className="prp-modal-status">{s.status}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="prp-modal-feedback-form">
          <h4>Flag this decision</h4>
          <div className="prp-feedback-row">
            <label>
              Severity
              <select
                value={severity}
                onChange={(e) => setSeverity(e.target.value)}
              >
                <option value="blocker">blocker</option>
                <option value="issue">issue</option>
                <option value="note">note</option>
              </select>
            </label>
          </div>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="What's wrong with this assignment? (Who should it be, why, what's the right grouping?)"
            rows={3}
          />
          {submitError && <div className="prp-error">{submitError}</div>}
          <div className="prp-feedback-actions">
            <button
              className="prp-run-btn"
              onClick={submit}
              disabled={submitting || !comment.trim()}
            >
              {submitting ? 'Submitting…' : 'Submit feedback'}
            </button>
          </div>
        </div>

        <div className="prp-modal-prior">
          <h4>Prior feedback for this date ({priorFeedback.length})</h4>
          {priorFeedback.length === 0 ? (
            <div className="prp-empty">None yet.</div>
          ) : (
            <ul className="prp-modal-feedback-list">
              {priorFeedback.map((f) => (
                <li key={f.id} className={`prp-feedback-${f.severity}`}>
                  <div className="prp-feedback-meta">
                    <span className={`prp-severity-tag prp-severity-${f.severity}`}>
                      {f.severity}
                    </span>
                    <span>
                      {formatTime(f.shift_start_time)}–{formatTime(f.shift_end_time)}{' '}
                      {f.shift_staff_id ? `· staff #${f.shift_staff_id}` : ''}
                    </span>
                    <span className="prp-feedback-when">
                      {new Date(f.submitted_at).toLocaleString('en-GB', {
                        timeZone: 'Europe/London',
                        day: '2-digit',
                        month: 'short',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </div>
                  <div className="prp-feedback-comment">{f.comment}</div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}

function ShiftDetail({ shift }) {
  return (
    <ul className="prp-modal-shift-list">
      <li>
        <strong>Time:</strong> {shift.start_time}–{shift.end_time}
      </li>
      <li>
        <strong>Date:</strong> {shift.date}
      </li>
      <li>
        <strong>Staff:</strong>{' '}
        {shift.staff_id ? shift.staff_initials || `#${shift.staff_id}` : '? unassigned'}
      </li>
      <li>
        <strong>Type:</strong> {shift.shift_type || 'custom'}
      </li>
      <li>
        <strong>Kind:</strong> {shift.kind || 'new'}
      </li>
      {shift.linked_booking_refs?.length > 0 && (
        <li>
          <strong>Bookings:</strong> {shift.linked_booking_refs.join(', ')}
        </li>
      )}
    </ul>
  )
}

function formatTime(t) {
  if (!t) return '–'
  // Backend returns "HH:MM:SS" or "HH:MM"; trim seconds for display.
  return String(t).slice(0, 5)
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
