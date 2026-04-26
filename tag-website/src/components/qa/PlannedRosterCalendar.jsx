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
  // Action dialog state — one shift + one action open at a time.
  // dayShifts is the same-date sibling list, used by Merge to know
  // which adjacent shift goes left/right.
  const [actionShift, setActionShift] = useState(null)
  const [actionShiftIndex, setActionShiftIndex] = useState(null)
  const [actionType, setActionType] = useState(null)
  const [actionDayShifts, setActionDayShifts] = useState([])
  const [actionPos, setActionPos] = useState(0)

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
                onShiftAction={(shift, idx, action, posInDay, dayShifts) => {
                  setActionShift(shift)
                  setActionShiftIndex(idx)
                  setActionType(action)
                  setActionDayShifts(dayShifts)
                  setActionPos(posInDay)
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

      {actionShift && actionType && detail && (
        <ActionDialog
          apiUrl={apiUrl}
          authHeader={authHeader}
          runId={detail.run_id}
          shift={actionShift}
          shiftIndex={actionShiftIndex}
          actionType={actionType}
          dayShifts={actionDayShifts}
          posInDay={actionPos}
          onClose={() => {
            setActionShift(null)
            setActionShiftIndex(null)
            setActionType(null)
          }}
        />
      )}
    </div>
  )
}

// =============================================================================
// ActionDialog — single component that switches body by actionType.
// All four action variants share the modal frame (modal-overlay +
// customer-detail-modal) and post to the same /feedback endpoint with
// a structured override payload.
// =============================================================================

function ActionDialog({
  apiUrl, authHeader, runId, shift, shiftIndex,
  actionType, dayShifts, posInDay, onClose,
}) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  async function postOverride(override, comment, severity = 'note') {
    setSubmitting(true)
    setError(null)
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
            comment,
            override,
          }),
        }
      )
      if (!res.ok) throw new Error(await res.text() || `HTTP ${res.status}`)
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to submit')
    } finally {
      setSubmitting(false)
    }
  }

  if (actionType === 'delete') {
    return (
      <DeleteDialog
        shift={shift} submitting={submitting} error={error}
        onCancel={onClose}
        onConfirm={() => postOverride(
          { action: 'delete' },
          'Marked for deletion',
          'issue',
        )}
      />
    )
  }
  if (actionType === 'duplicate') {
    return (
      <DuplicateDialog
        apiUrl={apiUrl} authHeader={authHeader}
        shift={shift} submitting={submitting} error={error}
        onCancel={onClose}
        onSubmit={(staffIds) => postOverride(
          { action: 'duplicate', target_staff_ids: staffIds },
          `Duplicate to ${staffIds.length} additional driver(s)`,
        )}
      />
    )
  }
  if (actionType === 'merge') {
    return (
      <MergeDialog
        apiUrl={apiUrl} authHeader={authHeader}
        shift={shift} dayShifts={dayShifts} posInDay={posInDay}
        submitting={submitting} error={error}
        onCancel={onClose}
        onSubmit={(direction, mergedStaffId) => postOverride(
          { action: 'merge', merge_direction: direction, merged_staff_id: mergedStaffId },
          `Merge with ${direction} shift`,
        )}
      />
    )
  }
  if (actionType === 'split') {
    return (
      <SplitDialog
        apiUrl={apiUrl} authHeader={authHeader}
        shift={shift} submitting={submitting} error={error}
        onCancel={onClose}
        onSubmit={({ splitAt, firstStart, secondEnd, firstStaffId, secondStaffId }) => {
          const override = {
            action: 'split',
            split_at_time: splitAt + ':00',
            first_half_staff_id: firstStaffId,
            second_half_staff_id: secondStaffId,
          }
          if (firstStart) override.first_half_start_time = firstStart + ':00'
          if (secondEnd) override.second_half_end_time = secondEnd + ':00'
          postOverride(override, `Split at ${splitAt}`)
        }}
      />
    )
  }
  return null
}

function DialogShell({ title, error, footer, children }) {
  return (
    <div className="modal-overlay" onClick={(e) => e.stopPropagation()}>
      <div className="modal-content qa-action-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{title}</h3>
        </div>
        <div className="modal-body">
          {children}
          {error && <div className="prp-error">{error}</div>}
        </div>
        <div className="form-actions">{footer}</div>
      </div>
    </div>
  )
}

function DeleteDialog({ shift, submitting, error, onCancel, onConfirm }) {
  return (
    <DialogShell
      title={`Delete shift · ${formatTime(shift.start_time)}–${formatTime(shift.end_time)}`}
      error={error}
      footer={
        <>
          <button className="btn-danger" onClick={onConfirm} disabled={submitting}>
            {submitting ? 'Saving…' : 'Mark for deletion'}
          </button>
          <button className="btn-secondary" onClick={onCancel}>Cancel</button>
        </>
      }
    >
      <p>
        Records this engine decision as one to delete on review.
        No <code>roster_shifts</code> rows are touched (shadow mode).
      </p>
    </DialogShell>
  )
}

function useAssignableStaff(apiUrl, authHeader) {
  const [staff, setStaff] = useState([])
  useEffect(() => {
    let cancelled = false
    fetch(`${apiUrl}/api/staff?is_active=true&auto_assign_excluded=false`, { headers: authHeader })
      .then((r) => (r.ok ? r.json() : []))
      .then((body) => { if (!cancelled) setStaff(body) })
    return () => { cancelled = true }
  }, [apiUrl, authHeader])
  return staff
}

function DuplicateDialog({ apiUrl, authHeader, shift, submitting, error, onCancel, onSubmit }) {
  const staff = useAssignableStaff(apiUrl, authHeader)
  const [picked, setPicked] = useState(new Set())

  function toggle(id) {
    const next = new Set(picked)
    if (next.has(id)) next.delete(id); else next.add(id)
    setPicked(next)
  }

  return (
    <DialogShell
      title={`Duplicate · ${formatTime(shift.start_time)}–${formatTime(shift.end_time)} · ${formatUkDate(shift.date)}`}
      error={error}
      footer={
        <>
          <button
            className="btn-primary"
            onClick={() => onSubmit(Array.from(picked))}
            disabled={submitting || picked.size === 0}
          >
            {submitting ? 'Saving…' : `Save (${picked.size} driver${picked.size === 1 ? '' : 's'})`}
          </button>
          <button className="btn-secondary" onClick={onCancel}>Cancel</button>
        </>
      }
    >
      <p style={{ marginTop: 0 }}>
        Add drivers to this same shift window. Each selection becomes a
        carbon-copy assignment.
      </p>
      <ul className="prp-staff-picker">
        {staff.length === 0 && <li className="prp-empty">No assignable staff loaded.</li>}
        {staff.map((s) => (
          <li key={s.id}>
            <label>
              <input
                type="checkbox"
                checked={picked.has(s.id)}
                onChange={() => toggle(s.id)}
                disabled={s.id === shift.staff_id}
              />
              <span>{s.first_name} {s.last_name}</span>
              {s.id === shift.staff_id && (
                <span className="prp-staff-tag">on this shift</span>
              )}
            </label>
          </li>
        ))}
      </ul>
    </DialogShell>
  )
}

function MergeDialog({ apiUrl, authHeader, shift, dayShifts, posInDay, submitting, error, onCancel, onSubmit }) {
  const staff = useAssignableStaff(apiUrl, authHeader)
  const prev = posInDay > 0 ? dayShifts[posInDay - 1] : null
  const next = posInDay < dayShifts.length - 1 ? dayShifts[posInDay + 1] : null
  const [direction, setDirection] = useState(prev ? 'left' : 'right')
  const [mergedStaffId, setMergedStaffId] = useState(shift.staff_id || '')

  return (
    <DialogShell
      title={`Merge · ${formatTime(shift.start_time)}–${formatTime(shift.end_time)}`}
      error={error}
      footer={
        <>
          <button
            className="btn-primary"
            onClick={() => onSubmit(direction, mergedStaffId === '' ? null : Number(mergedStaffId))}
            disabled={submitting || (!prev && !next)}
          >
            {submitting ? 'Saving…' : 'Save'}
          </button>
          <button className="btn-secondary" onClick={onCancel}>Cancel</button>
        </>
      }
    >
      <p style={{ marginTop: 0 }}>
        Merge two shifts into one (e.g. cleaning duties between event clusters).
        Pick which adjacent shift to merge with and who staffs the result.
      </p>
      <div className="prp-merge-options">
        <label className={`prp-merge-option ${!prev ? 'disabled' : ''}`}>
          <input
            type="radio" name="merge-direction" value="left"
            checked={direction === 'left'}
            disabled={!prev}
            onChange={() => setDirection('left')}
          />
          <strong>← Previous</strong>
          <span>{prev ? `${formatTime(prev.start_time)}–${formatTime(prev.end_time)} · ${prev.staff_initials || (prev.staff_id ? `#${prev.staff_id}` : '?')}` : 'no previous shift'}</span>
        </label>
        <label className={`prp-merge-option ${!next ? 'disabled' : ''}`}>
          <input
            type="radio" name="merge-direction" value="right"
            checked={direction === 'right'}
            disabled={!next}
            onChange={() => setDirection('right')}
          />
          <strong>Next →</strong>
          <span>{next ? `${formatTime(next.start_time)}–${formatTime(next.end_time)} · ${next.staff_initials || (next.staff_id ? `#${next.staff_id}` : '?')}` : 'no next shift'}</span>
        </label>
      </div>
      <div className="form-row">
        <label>Staff for the merged shift:</label>
        <select className="form-input" value={mergedStaffId} onChange={(e) => setMergedStaffId(e.target.value)}>
          <option value="">? unassigned</option>
          {staff.map((s) => (
            <option key={s.id} value={s.id}>{s.first_name} {s.last_name}</option>
          ))}
        </select>
      </div>
    </DialogShell>
  )
}

function SplitDialog({ apiUrl, authHeader, shift, submitting, error, onCancel, onSubmit }) {
  const staff = useAssignableStaff(apiUrl, authHeader)
  const sourceStart = formatTime(shift.start_time)
  const sourceEnd = formatTime(shift.end_time)

  // Three time points (each is editable):
  //   firstStart ≤ splitAt ≤ secondEnd
  // firstStart can be earlier than the source's start (extending the
  // first half backward — e.g. for vehicle prep before the first event).
  // secondEnd can be later than the source's end (extending the second
  // half forward — e.g. for cleaning duties after the last event).
  const [firstStart, setFirstStart] = useState(sourceStart)
  const [splitAt, setSplitAt] = useState(midpointTime(shift.start_time, shift.end_time))
  const [secondEnd, setSecondEnd] = useState(sourceEnd)
  const [firstStaffId, setFirstStaffId] = useState(shift.staff_id || '')
  const [secondStaffId, setSecondStaffId] = useState('')

  const validOrder = firstStart < splitAt && splitAt < secondEnd
  const canSave = !submitting && validOrder && secondStaffId !== ''

  // Only send the outer-bound overrides when they actually differ from
  // the source — keeps the audit row minimal when no extension was made.
  function handleSave() {
    onSubmit({
      splitAt,
      firstStart: firstStart !== sourceStart ? firstStart : null,
      secondEnd: secondEnd !== sourceEnd ? secondEnd : null,
      firstStaffId: firstStaffId === '' ? null : Number(firstStaffId),
      secondStaffId: secondStaffId === '' ? null : Number(secondStaffId),
    })
  }

  return (
    <DialogShell
      title={`Split · ${sourceStart}–${sourceEnd}`}
      error={error}
      footer={
        <>
          <button className="btn-primary" onClick={handleSave} disabled={!canSave}>
            {submitting ? 'Saving…' : 'Save'}
          </button>
          <button className="btn-secondary" onClick={onCancel}>Cancel</button>
        </>
      }
    >
      <p style={{ marginTop: 0 }}>
        Splits this shift into two halves. Outer ends are editable —
        you can extend the first half backward (vehicle prep) or the
        second half forward (cleaning duties).
      </p>

      <div className="customer-edit-form" style={{ marginBottom: '0.75rem' }}>
        <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem' }}>First half</h4>
        <div className="form-row">
          <label>Start:</label>
          <input
            type="time" className="form-input"
            value={firstStart}
            onChange={(e) => setFirstStart(e.target.value)}
          />
          {firstStart !== sourceStart && (
            <small style={{ color: '#6b7280' }}>extends source ({sourceStart})</small>
          )}
        </div>
        <div className="form-row">
          <label>End (split at):</label>
          <input
            type="time" className="form-input"
            value={splitAt}
            onChange={(e) => setSplitAt(e.target.value)}
          />
        </div>
        <div className="form-row">
          <label>Staff:</label>
          <select className="form-input" value={firstStaffId} onChange={(e) => setFirstStaffId(e.target.value)}>
            <option value="">? unassigned</option>
            {staff.map((s) => (
              <option key={s.id} value={s.id}>{s.first_name} {s.last_name}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="customer-edit-form">
        <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem' }}>Second half</h4>
        <div className="form-row">
          <label>Start (split at):</label>
          <input type="time" className="form-input" value={splitAt} disabled />
        </div>
        <div className="form-row">
          <label>End:</label>
          <input
            type="time" className="form-input"
            value={secondEnd}
            onChange={(e) => setSecondEnd(e.target.value)}
          />
          {secondEnd !== sourceEnd && (
            <small style={{ color: '#6b7280' }}>extends source ({sourceEnd})</small>
          )}
        </div>
        <div className="form-row">
          <label>Staff:</label>
          <select className="form-input" value={secondStaffId} onChange={(e) => setSecondStaffId(e.target.value)}>
            <option value="">? select staff</option>
            {staff.map((s) => (
              <option key={s.id} value={s.id}>{s.first_name} {s.last_name}</option>
            ))}
          </select>
        </div>
      </div>

      {!validOrder && (
        <small style={{ color: '#b91c1c' }}>
          Times must satisfy: first-half start &lt; split &lt; second-half end.
        </small>
      )}
    </DialogShell>
  )
}

function midpointTime(start, end) {
  // Best-effort midpoint pre-fill. Both inputs may be HH:MM:SS or HH:MM.
  const [sh, sm] = String(start).split(':').slice(0, 2).map(Number)
  const [eh, em] = String(end).split(':').slice(0, 2).map(Number)
  if ([sh, sm, eh, em].some(Number.isNaN)) return ''
  let s = sh * 60 + sm
  let e = eh * 60 + em
  if (e <= s) e += 24 * 60 // overnight
  const mid = Math.floor((s + e) / 2) % (24 * 60)
  const h = Math.floor(mid / 60)
  const m = mid % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
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

function ProposalCalendar({ shiftsByDate, sortedDates, onShiftClick, onShiftAction }) {
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
      {sortedDates.map((dateStr) => {
        const dayShifts = shiftsByDate[dateStr]
        return (
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
              {dayShifts.map((s, posInDay) => (
                <ShiftCard
                  key={s.__index}
                  shift={s}
                  onCardClick={() => onShiftClick?.(s, s.__index)}
                  onAction={(action) => onShiftAction?.(s, s.__index, action, posInDay, dayShifts)}
                  hasPrev={posInDay > 0}
                  hasNext={posInDay < dayShifts.length - 1}
                />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ShiftCard({ shift, onCardClick, onAction, hasPrev, hasNext }) {
  const unassigned = !shift.staff_id
  return (
    <div
      className={`prp-shift ${unassigned ? 'unassigned' : ''} prp-shift-${shift.kind || 'new'}`}
    >
      <div
        className="prp-shift-body"
        role="button"
        tabIndex={0}
        onClick={onCardClick}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onCardClick?.()
          }
        }}
        title="Click to give feedback / edit this shift"
      >
        <div className="prp-shift-time">
          {formatTime(shift.start_time)}–{formatTime(shift.end_time)}
        </div>
        <div className="prp-shift-staff">
          {unassigned ? '? unassigned' : shift.staff_initials || `staff #${shift.staff_id}`}
        </div>
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
      <div className="prp-shift-actions booking-actions">
        <button
          type="button"
          className="action-btn edit-btn"
          onClick={(e) => { e.stopPropagation(); onAction?.('duplicate') }}
        >
          Duplicate
        </button>
        <button
          type="button"
          className="action-btn paid-btn"
          onClick={(e) => { e.stopPropagation(); onAction?.('merge') }}
          disabled={!hasPrev && !hasNext}
          title={!hasPrev && !hasNext ? 'No adjacent shift on this date' : ''}
        >
          Merge
        </button>
        <button
          type="button"
          className="action-btn refund-btn"
          onClick={(e) => { e.stopPropagation(); onAction?.('split') }}
        >
          Split
        </button>
        <button
          type="button"
          className="action-btn cancel-btn"
          onClick={(e) => { e.stopPropagation(); onAction?.('delete') }}
        >
          Delete
        </button>
      </div>
    </div>
  )
}

function FeedbackModal({ apiUrl, authHeader, runId, shift, shiftIndex, onClose }) {
  const [adminShifts, setAdminShifts] = useState([])
  const [priorFeedback, setPriorFeedback] = useState([])
  const [assignableStaff, setAssignableStaff] = useState([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)
  const [severity, setSeverity] = useState('issue')
  const [comment, setComment] = useState('')
  // Override fields — prefill from engine values; admin tweaks if needed.
  const [overrideStaffId, setOverrideStaffId] = useState(shift.staff_id ?? '')
  const [overrideStart, setOverrideStart] = useState(shortTime(shift.start_time))
  const [overrideEnd, setOverrideEnd] = useState(shortTime(shift.end_time))

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      try {
        const [adminRes, fbRes, staffRes] = await Promise.all([
          fetch(`${apiUrl}/api/roster?date=${shift.date}`, { headers: authHeader }),
          fetch(
            `${apiUrl}/api/admin/qa/roster-planner/feedback?shift_date=${shift.date}`,
            { headers: authHeader }
          ),
          // Assignable pool — active staff who are NOT auto_assign_excluded
          // (Mark Custard, John Penney, Uber Driver, Jez Taylor stay out).
          fetch(
            `${apiUrl}/api/staff?is_active=true&auto_assign_excluded=false`,
            { headers: authHeader }
          ),
        ])
        if (cancelled) return
        setAdminShifts(adminRes.ok ? await adminRes.json() : [])
        setPriorFeedback(fbRes.ok ? await fbRes.json() : [])
        setAssignableStaff(staffRes.ok ? await staffRes.json() : [])
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [apiUrl, authHeader, shift.date])

  function buildOverridePayload() {
    // Only include the override block if at least one field differs from
    // the engine's original decision.
    const original = {
      staff_id: shift.staff_id ?? null,
      start_time: shortTime(shift.start_time),
      end_time: shortTime(shift.end_time),
    }
    const proposed = {
      staff_id: overrideStaffId === '' ? null : Number(overrideStaffId),
      start_time: overrideStart,
      end_time: overrideEnd,
    }
    const diff = {}
    if (proposed.staff_id !== original.staff_id) diff.staff_id = proposed.staff_id
    if (proposed.start_time && proposed.start_time !== original.start_time) diff.start_time = `${proposed.start_time}:00`
    if (proposed.end_time && proposed.end_time !== original.end_time) diff.end_time = `${proposed.end_time}:00`
    return Object.keys(diff).length > 0 ? diff : null
  }

  async function submit() {
    if (!comment.trim()) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const override = buildOverridePayload()
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
            ...(override ? { override } : {}),
          }),
        }
      )
      if (!res.ok) {
        const detail = await res.text()
        throw new Error(detail || `HTTP ${res.status}`)
      }
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

  const engineStaffLabel = shift.staff_id
    ? shift.staff_initials || `staff #${shift.staff_id}`
    : '? unassigned'

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content qa-shift-edit-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h3>
            Edit shift · {formatTime(shift.start_time)}–{formatTime(shift.end_time)} · {engineStaffLabel}
          </h3>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        <div className="modal-body">
          {/* Engine proposal — read-only */}
          <div className="customer-detail-section">
            <h4>Engine proposal</h4>
            <div className="customer-info-grid">
              <div className="info-row">
                <span className="info-label">Date:</span>
                <span className="info-value">{formatUkDate(shift.date)}</span>
              </div>
              <div className="info-row">
                <span className="info-label">Time:</span>
                <span className="info-value">
                  {formatTime(shift.start_time)}–{formatTime(shift.end_time)}
                </span>
              </div>
              <div className="info-row">
                <span className="info-label">Staff:</span>
                <span className="info-value">{engineStaffLabel}</span>
              </div>
              <div className="info-row">
                <span className="info-label">Type:</span>
                <span className="info-value">{shift.shift_type || 'custom'}</span>
              </div>
              <div className="info-row">
                <span className="info-label">Kind:</span>
                <span className="info-value">{shift.kind || 'new'}</span>
              </div>
            </div>
            {shift.events?.length > 0 && (
              <ul className="prp-event-list" style={{ marginTop: '0.75rem' }}>
                {shift.events.map((e, i) => (
                  <EventRow key={`${e.booking_id}-${e.event_type}-${i}`} event={e} />
                ))}
              </ul>
            )}
          </div>

          {/* Admin calendar (live) */}
          <div className="customer-detail-section">
            <h4>Admin calendar (live) · {formatUkDate(shift.date)}</h4>
            {loading ? (
              <div className="prp-empty">Loading…</div>
            ) : adminShifts.length === 0 ? (
              <div className="prp-empty">No shifts scheduled on this date.</div>
            ) : (
              <div className="prp-admin-shift-stack">
                {adminShifts.map((s) => (
                  <AdminShiftBlock key={s.id} shift={s} />
                ))}
              </div>
            )}
          </div>

          {/* Override (structured "what I would have done") */}
          <div className="customer-detail-section">
            <h4>Override</h4>
            <div className="customer-edit-form">
              <div className="form-row">
                <label>Staff:</label>
                <select
                  className="form-input"
                  value={overrideStaffId}
                  onChange={(e) => setOverrideStaffId(e.target.value)}
                >
                  <option value="">? unassigned</option>
                  {assignableStaff.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.first_name} {u.last_name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-row">
                <label>Start time:</label>
                <input
                  type="time"
                  className="form-input"
                  value={overrideStart}
                  onChange={(e) => setOverrideStart(e.target.value)}
                />
              </div>
              <div className="form-row">
                <label>End time:</label>
                <input
                  type="time"
                  className="form-input"
                  value={overrideEnd}
                  onChange={(e) => setOverrideEnd(e.target.value)}
                />
              </div>
            </div>
          </div>

          {/* Feedback */}
          <div className="customer-detail-section">
            <h4>Feedback</h4>
            <div className="customer-edit-form">
              <div className="form-row">
                <label>Severity:</label>
                <select
                  className="form-input"
                  value={severity}
                  onChange={(e) => setSeverity(e.target.value)}
                >
                  <option value="blocker">Blocker</option>
                  <option value="issue">Issue</option>
                  <option value="note">Note</option>
                </select>
              </div>
              <div className="form-row">
                <label>Comment:</label>
                <textarea
                  className="form-input"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="What's wrong with this assignment? (Who should it be, why, what's the right grouping?)"
                  rows={3}
                />
              </div>
              {submitError && <div className="prp-error">{submitError}</div>}
              <div className="form-actions">
                <button
                  className="btn-primary"
                  onClick={submit}
                  disabled={submitting || !comment.trim()}
                >
                  {submitting ? 'Saving…' : 'Save'}
                </button>
                <button className="btn-secondary" onClick={onClose}>
                  Cancel
                </button>
              </div>
            </div>
          </div>

          {/* Prior feedback */}
          <div className="customer-detail-section">
            <h4>Prior feedback for {formatUkDate(shift.date)} ({priorFeedback.length})</h4>
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
                    {f.override && (
                      <div className="prp-feedback-override">
                        Override:{' '}
                        {f.override.staff_id != null && (
                          <span>staff #{f.override.staff_id} </span>
                        )}
                        {f.override.start_time && (
                          <span>· start {shortTime(f.override.start_time)} </span>
                        )}
                        {f.override.end_time && (
                          <span>· end {shortTime(f.override.end_time)}</span>
                        )}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function shortTime(t) {
  // Trim "HH:MM:SS" to "HH:MM" for <input type="time"> compatibility.
  if (!t) return ''
  return String(t).slice(0, 5)
}

function formatUkDate(yyyymmdd) {
  // SPEC: DD/MM/YYYY display.
  if (!yyyymmdd) return ''
  const [y, m, d] = String(yyyymmdd).split('-')
  if (!y || !m || !d) return yyyymmdd
  return `${d}/${m}/${y}`
}

function ShiftDetail({ shift }) {
  return (
    <div className="prp-shift-detail">
      <div className="prp-shift-detail-meta">
        <span><strong>Time:</strong> {formatTime(shift.start_time)}–{formatTime(shift.end_time)}</span>
        <span><strong>Date:</strong> {shift.date}</span>
        <span>
          <strong>Staff:</strong>{' '}
          {shift.staff_id ? shift.staff_initials || `#${shift.staff_id}` : '? unassigned'}
        </span>
        <span><strong>Type:</strong> {shift.shift_type || 'custom'}</span>
        <span><strong>Kind:</strong> {shift.kind || 'new'}</span>
      </div>
      {shift.events?.length > 0 ? (
        <ul className="prp-event-list">
          {shift.events.map((e, i) => (
            <EventRow key={`${e.booking_id}-${e.event_type}-${i}`} event={e} />
          ))}
        </ul>
      ) : (
        <div className="prp-empty">No bookings linked to this shift.</div>
      )}
    </div>
  )
}

function AdminShiftBlock({ shift }) {
  // /api/roster returns RosterShiftResponse with .bookings (List[LinkedBookingInfo]).
  // The DEPRECATED single booking_* fields are also kept on the response for
  // backwards-compat — fall back to those if bookings is empty.
  let bookings = shift.bookings || []
  if (bookings.length === 0 && shift.booking_reference) {
    bookings = [
      {
        id: shift.booking_id,
        reference: shift.booking_reference,
        type: shift.booking_type,
        customer_name: shift.booking_customer_name,
        time: shift.booking_time,
        flight_number: shift.booking_flight_number,
        destination: shift.booking_destination,
      },
    ]
  }
  return (
    <div className="prp-admin-shift">
      <div className="prp-admin-shift-head">
        <strong>
          {formatTime(shift.start_time)}–{formatTime(shift.end_time)}
        </strong>
        <span>
          {shift.staff_initials || (shift.staff_id ? `#${shift.staff_id}` : '? unassigned')}
        </span>
        {shift.status && <span className="prp-modal-status">{shift.status}</span>}
      </div>
      {bookings.length > 0 && (
        <ul className="prp-event-list">
          {bookings.map((b) => (
            <li
              key={`${b.id}-${b.type}`}
              className={`prp-event prp-event-${b.type === 'dropoff' ? 'dropoff' : 'pickup'}`}
            >
              <div className="prp-event-head">
                <span className="prp-event-icon">{b.type === 'dropoff' ? '🚗' : '🛬'}</span>
                <span className="prp-event-ref">{b.reference}</span>
                {b.customer_name && (
                  <span className="prp-event-customer">{b.customer_name}</span>
                )}
              </div>
              <div className="prp-event-line">
                {b.time && <span>@ {b.time}</span>}
                {b.flight_number && <span> · {b.flight_number}</span>}
                {b.destination && <span> · → {b.destination}</span>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function EventRow({ event }) {
  const isDropoff = event.event_type === 'drop_off'
  const eventTime = formatEventTime(event.event_time)
  return (
    <li className={`prp-event prp-event-${isDropoff ? 'dropoff' : 'pickup'}`}>
      <div className="prp-event-head">
        <span className="prp-event-icon">{isDropoff ? '🚗' : '🛬'}</span>
        <span className="prp-event-ref">{event.booking_reference}</span>
        {event.customer_name && (
          <span className="prp-event-customer">{event.customer_name}</span>
        )}
      </div>
      <div className="prp-event-line">
        {eventTime && <span>@ {eventTime}</span>}
        {event.flight_number && <span> · {event.flight_number}</span>}
        {event.destination && <span> · → {event.destination}</span>}
      </div>
    </li>
  )
}

function formatEventTime(t) {
  if (!t) return null
  // Engine emits ISO datetime like "2026-04-25T04:55:00+01:00"; show HH:MM only.
  try {
    const d = new Date(t)
    if (isNaN(d.getTime())) return String(t).slice(11, 16) || null
    return d.toLocaleTimeString('en-GB', {
      timeZone: 'Europe/London',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return null
  }
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
