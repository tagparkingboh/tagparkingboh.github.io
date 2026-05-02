import { Fragment, useEffect, useMemo, useState } from 'react'
import RosterCalendar from '../RosterCalendar'
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

// 2026-05-02 — the planner→calendar commit pipeline is severed temporarily
// while auto-create-on-booking takes over (see SPEC.md "Roster Planner v2"
// note). Flip this back to false to re-enable the Phase 3 commit UI.
const COMMIT_PIPELINE_DISABLED = true

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

  // Phase 3 commit / undo state.
  // selectedToCommit: Set of proposed_shifts indexes the admin has ticked.
  //   Reset whenever the run selection changes (a different run = different
  //   index space).
  // commitConfirmOpen: shows the confirm dialog before POSTing /commit.
  // committing: true while the POST is in flight, disables UI.
  // commitMessage: success / error banner shown briefly after a commit.
  // undoConfirmRunId: the run_id whose undo confirm dialog is open (or null).
  const [selectedToCommit, setSelectedToCommit] = useState(() => new Set())
  const [commitConfirmOpen, setCommitConfirmOpen] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [commitMessage, setCommitMessage] = useState(null)
  const [undoConfirmRunId, setUndoConfirmRunId] = useState(null)
  const [undoing, setUndoing] = useState(false)

  // Regenerate-auto-roster modal state.
  const [regenerateOpen, setRegenerateOpen] = useState(false)
  const [regenerateRunning, setRegenerateRunning] = useState(false)
  const [regenerateMessage, setRegenerateMessage] = useState(null)
  const [calendarRefreshTick, setCalendarRefreshTick] = useState(0)

  // Per-proposal-index override state. Populated when an admin clicks an
  // action button (Unassign / Delete / Duplicate) and confirms the dialog.
  // Sent in the /commit body as `overrides`. Resets when the active run
  // changes (index space is per-run).
  // Shape: { [proposalIndex: number]: { action, target_staff_ids?, ... } }
  const [overridesByIndex, setOverridesByIndex] = useState({})

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

  // Reset commit selection + overrides whenever the active run changes —
  // index space is per-run, so leaving stale state across runs would
  // commit the wrong proposals or apply the wrong overrides.
  useEffect(() => {
    setSelectedToCommit(new Set())
    setOverridesByIndex({})
    setCommitMessage(null)
  }, [selectedRunId])

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

  async function performRegenerate(payload) {
    setRegenerateRunning(true)
    setError(null)
    setRegenerateMessage(null)
    try {
      const res = await fetch(
        `${apiUrl}/api/admin/qa/roster-planner/regenerate-auto`,
        {
          method: 'POST',
          headers: { ...authHeader, 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      )
      const body = await res.json().catch(() => null)
      if (!res.ok) {
        throw new Error(body?.detail || `Regenerate failed (HTTP ${res.status})`)
      }
      setRegenerateMessage(
        `${body.bookings_processed} booking${body.bookings_processed === 1 ? '' : 's'} processed across ${body.dates_covered} day${body.dates_covered === 1 ? '' : 's'}: ` +
        `${body.created} created, ${body.extended} extended, ${body.deleted} cleared.`
      )
      setRegenerateOpen(false)
      // Force the embedded auto-Calendar to refresh so the new shifts show up.
      setCalendarRefreshTick((t) => t + 1)
    } catch (err) {
      setError(err.message || 'Regenerate failed')
    } finally {
      setRegenerateRunning(false)
    }
  }

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

  async function refreshRunsList() {
    try {
      const res = await fetch(
        `${apiUrl}/api/admin/qa/roster-planner/runs?limit=50`,
        { headers: authHeader }
      )
      if (res.ok) setRuns(await res.json())
    } catch {/* non-fatal — list is informational */}
  }

  async function refreshSelectedDetail() {
    if (!selectedRunId) return
    try {
      const res = await fetch(
        `${apiUrl}/api/admin/qa/roster-planner/runs/${selectedRunId}`,
        { headers: authHeader }
      )
      if (res.ok) setDetail(await res.json())
    } catch {/* non-fatal — banner already informs the user */}
  }

  function toggleCommitTick(idx) {
    setSelectedToCommit((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  // Set / clear a per-proposal override (called by ActionDialog after the
  // admin confirms an action). Auto-ticks the proposal so the override
  // doesn't get filtered out at commit time for being unticked.
  function setOverride(idx, override) {
    setOverridesByIndex((prev) => ({ ...prev, [idx]: override }))
    setSelectedToCommit((prev) => new Set([...prev, idx]))
  }

  function clearOverride(idx) {
    setOverridesByIndex((prev) => {
      const next = { ...prev }
      delete next[idx]
      return next
    })
  }

  function selectAllNew() {
    if (!detail?.proposal?.proposed_shifts) return
    const committed = new Set(detail.committed_indexes || [])
    const all = new Set()
    detail.proposal.proposed_shifts.forEach((s, idx) => {
      // Skip committed proposals — re-ticking them would just hit a 409 overlap.
      if (s.kind === 'new' && !committed.has(idx)) all.add(idx)
    })
    setSelectedToCommit(all)
  }

  function clearSelection() {
    setSelectedToCommit(new Set())
  }

  async function performCommit() {
    if (!selectedRunId || selectedToCommit.size === 0) return
    setCommitting(true)
    setError(null)
    setCommitMessage(null)
    try {
      const indexes = Array.from(selectedToCommit).sort((a, b) => a - b)
      // Strip overrides whose index isn't ticked — the backend ignores them
      // anyway but cleaner not to send dead data.
      const tickedSet = new Set(indexes)
      const filteredOverrides = Object.fromEntries(
        Object.entries(overridesByIndex)
          .filter(([k]) => tickedSet.has(Number(k)))
      )
      const res = await fetch(
        `${apiUrl}/api/admin/qa/roster-planner/commit`,
        {
          method: 'POST',
          headers: { ...authHeader, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            run_id: selectedRunId,
            proposal_indexes: indexes,
            overrides: filteredOverrides,
          }),
        }
      )
      const body = await res.json().catch(() => null)
      if (!res.ok) {
        throw new Error(body?.detail || `Commit failed (HTTP ${res.status})`)
      }
      setCommitMessage(
        `Committed ${body.shifts_created} shift${
          body.shifts_created === 1 ? '' : 's'
        }. They are now live in the roster.`
      )
      // Clear local state for indexes we just committed — committed_indexes
      // from refreshSelectedDetail() will own the visual state from now on.
      setSelectedToCommit(new Set())
      setOverridesByIndex((prev) => {
        const next = { ...prev }
        for (const idx of indexes) delete next[idx]
        return next
      })
      setCommitConfirmOpen(false)
      await Promise.all([refreshRunsList(), refreshSelectedDetail()])
    } catch (err) {
      setError(err.message || 'Commit failed')
      setCommitConfirmOpen(false)
    } finally {
      setCommitting(false)
    }
  }

  async function performUndo(runId) {
    setUndoing(true)
    setError(null)
    setCommitMessage(null)
    try {
      const res = await fetch(
        `${apiUrl}/api/admin/qa/roster-planner/runs/${runId}`,
        { method: 'DELETE', headers: authHeader }
      )
      const body = await res.json().catch(() => null)
      if (!res.ok) {
        throw new Error(body?.detail || `Undo failed (HTTP ${res.status})`)
      }
      setCommitMessage(
        body.shifts_deleted > 0
          ? `Undone — ${body.shifts_deleted} shift${
              body.shifts_deleted === 1 ? '' : 's'
            } removed.`
          : 'Undo had nothing to remove (run was not committed or already undone).'
      )
      setUndoConfirmRunId(null)
      await Promise.all([refreshRunsList(), refreshSelectedDetail()])
    } catch (err) {
      setError(err.message || 'Undo failed')
      setUndoConfirmRunId(null)
    } finally {
      setUndoing(false)
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
        <div className="prp-header-actions">
          <button
            className="prp-run-btn"
            onClick={() => setRegenerateOpen(true)}
            title="Open the regenerate-auto-roster modal"
          >
            Regenerate auto-roster
          </button>
          <button
            type="button"
            className="prp-shadow-run-btn"
            onClick={runNow}
            title="Re-run the shadow-mode engine for QA review (no writes)"
          >
            Run shadow engine
          </button>
          <button
            type="button"
            className="prp-refresh-btn"
            onClick={() => Promise.all([refreshRunsList(), refreshSelectedDetail()])}
            title="Re-fetch runs + selected run detail (no page reload)"
          >
            ⟳ Refresh
          </button>
        </div>
      </div>

      {error && <div className="prp-error">{error}</div>}

      {/* 2026-05-02 self-contained auto-roster Calendar — wired to the
          live `created_source='auto'` shifts created by auto_roster.py
          on booking confirmation. Edit / duplicate UX is the same as
          the regular admin Roster Calendar. The shadow-mode planner
          output below is left in place for QA reference. */}
      <div className="prp-section prp-auto-calendar">
        <h3 className="prp-section-title">Auto Roster (live)</h3>
        <p className="prp-section-blurb">
          Shifts auto-created from confirmed bookings. Edits / duplicates
          here flow into the regular roster once promoted (admin promotion
          is a separate workflow — coming soon).
        </p>
        {regenerateMessage && (
          <div className="prp-regenerate-message">{regenerateMessage}</div>
        )}
        <RosterCalendar
          token={token}
          isAdmin={true}
          sourceFilter="auto"
          refreshTrigger={calendarRefreshTick}
        />
      </div>

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
              <JockeyPreferences jockeys={detail.proposal?.jockeys || []} />
              <PredictedHoursBreakdown
                jockeys={detail.proposal?.jockeys || []}
                maxHoursPerWeek={detail.proposal?.max_hours_per_week ?? 40}
                windowStart={detail.window_start}
                windowEnd={detail.window_end}
              />
              {!COMMIT_PIPELINE_DISABLED && (
                <CommitBar
                  selectedCount={selectedToCommit.size}
                  newProposalCount={
                    detail.proposal?.proposed_shifts?.filter((s) => s.kind === 'new').length ?? 0
                  }
                  onSelectAll={selectAllNew}
                  onClear={clearSelection}
                  onCommit={() => setCommitConfirmOpen(true)}
                  committing={committing}
                  message={commitMessage}
                />
              )}
              <ProposalCalendar
                shiftsByDate={shiftsByDate}
                sortedDates={sortedDates}
                selectedToCommit={selectedToCommit}
                committedIndexes={new Set(detail.committed_indexes || [])}
                committedShiftsByIndex={detail.committed_shifts_by_index || {}}
                overridesByIndex={overridesByIndex}
                onToggleCommitTick={toggleCommitTick}
                onClearOverride={clearOverride}
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
            <div
              key={r.run_id}
              className={`prp-history-row-wrap ${r.run_id === selectedRunId ? 'selected' : ''}`}
            >
              <button
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
              <button
                className="prp-history-undo-btn"
                onClick={() => setUndoConfirmRunId(r.run_id)}
                title="Undo this run — deletes engine-created shifts that haven't been confirmed"
              >
                Undo
              </button>
            </div>
          ))}
        </div>
      </div>

      {!COMMIT_PIPELINE_DISABLED && commitConfirmOpen && (
        <CommitConfirmModal
          count={selectedToCommit.size}
          onCancel={() => setCommitConfirmOpen(false)}
          onConfirm={performCommit}
          submitting={committing}
        />
      )}

      {regenerateOpen && (
        <RegenerateAutoModal
          onCancel={() => setRegenerateOpen(false)}
          onConfirm={performRegenerate}
          submitting={regenerateRunning}
        />
      )}

      {undoConfirmRunId && (
        <UndoConfirmModal
          runId={undoConfirmRunId}
          onCancel={() => setUndoConfirmRunId(null)}
          onConfirm={() => performUndo(undoConfirmRunId)}
          submitting={undoing}
        />
      )}

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
          onActionApplied={setOverride}
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
  actionType, dayShifts, posInDay, onClose, onActionApplied,
}) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  async function postOverride(override, comment, severity = 'note', applyToCommit = true) {
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
      // Phase 3.5: actions the backend honours at commit time → apply to
      // local override state. merge / split are still feedback-only (Phase
      // 3.6) — pass applyToCommit=false for those.
      if (applyToCommit && onActionApplied) {
        onActionApplied(shiftIndex, override)
      }
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
  if (actionType === 'unassign') {
    return (
      <UnassignDialog
        shift={shift} submitting={submitting} error={error}
        onCancel={onClose}
        onConfirm={() => postOverride(
          { action: 'unassign' },
          'Marked for unassign — shift will be committed without a jockey',
          'note',
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
        onSubmit={({ staffIds, addUnassignedJockey, addUnassignedFleet }) => {
          const extras = (addUnassignedJockey ? 1 : 0) + (addUnassignedFleet ? 1 : 0)
          const total = staffIds.length + extras
          const parts = []
          if (staffIds.length) parts.push(`${staffIds.length} driver${staffIds.length === 1 ? '' : 's'}`)
          if (addUnassignedJockey) parts.push('1 unassigned jockey')
          if (addUnassignedFleet) parts.push('1 unassigned fleet')
          return postOverride(
            {
              action: 'duplicate',
              target_staff_ids: staffIds,
              add_unassigned_jockey: addUnassignedJockey,
              add_unassigned_fleet: addUnassignedFleet,
            },
            `Duplicate to ${total} additional row(s): ${parts.join(' + ')}`,
          )
        }}
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
          'note',
          false,  // Phase 3.6 — feedback only, backend rejects on commit
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
          postOverride(override, `Split at ${splitAt}`, 'note', false)  // Phase 3.6
        }}
      />
    )
  }
  return null
}

// =============================================================================
// UnassignDialog — confirm dialog for the new Unassign action.
// =============================================================================
function UnassignDialog({ shift, submitting, error, onCancel, onConfirm }) {
  const currentStaff = shift.staff_initials || (shift.staff_id ? `staff #${shift.staff_id}` : 'unassigned')
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
        <h3 style={{ marginTop: 0 }}>Unassign this shift?</h3>
        <p style={{ color: '#444' }}>
          This shift is currently proposed for <strong>{currentStaff}</strong>. Unassigning
          drops the assignment so the shift commits as <strong>?</strong> — any eligible
          jockey can then claim it from the Employee app.
        </p>
        {error && <div className="prp-error" style={{ marginTop: '0.5rem' }}>{error}</div>}
        <div className="modal-actions">
          <button className="modal-btn modal-btn-secondary" onClick={onCancel} disabled={submitting}>
            Cancel
          </button>
          <button className="modal-btn modal-btn-primary" onClick={onConfirm} disabled={submitting}>
            {submitting ? 'Marking…' : 'Yes, unassign'}
          </button>
        </div>
      </div>
    </div>
  )
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
  const [addUnassignedJockey, setAddUnassignedJockey] = useState(false)
  const [addUnassignedFleet, setAddUnassignedFleet] = useState(false)

  function toggle(id) {
    const next = new Set(picked)
    if (next.has(id)) next.delete(id); else next.add(id)
    setPicked(next)
  }

  const totalExtras = picked.size + (addUnassignedJockey ? 1 : 0) + (addUnassignedFleet ? 1 : 0)

  return (
    <DialogShell
      title={`Duplicate · ${formatTime(shift.start_time)}–${formatTime(shift.end_time)} · ${formatUkDate(shift.date)}`}
      error={error}
      footer={
        <>
          <button
            className="btn-primary"
            onClick={() => onSubmit({
              staffIds: Array.from(picked),
              addUnassignedJockey,
              addUnassignedFleet,
            })}
            disabled={submitting || totalExtras === 0}
          >
            {submitting ? 'Saving…' : `Save (${totalExtras} row${totalExtras === 1 ? '' : 's'})`}
          </button>
          <button className="btn-secondary" onClick={onCancel}>Cancel</button>
        </>
      }
    >
      <p style={{ marginTop: 0 }}>
        Add drivers to this same shift window. Each selection becomes a
        carbon-copy assignment. Tick "Unassigned Jockey" or "Unassigned
        Fleet" to fan out an extra slot anyone of that type can claim.
      </p>
      <ul className="prp-staff-picker">
        <li>
          <label>
            <input
              type="checkbox"
              checked={addUnassignedJockey}
              onChange={() => setAddUnassignedJockey((v) => !v)}
            />
            <span>🏇 Unassigned Jockey</span>
            <span className="prp-staff-tag">+1 open slot</span>
          </label>
        </li>
        <li>
          <label>
            <input
              type="checkbox"
              checked={addUnassignedFleet}
              onChange={() => setAddUnassignedFleet((v) => !v)}
            />
            <span>🚐 Unassigned Fleet</span>
            <span className="prp-staff-tag">+1 open slot</span>
          </label>
        </li>
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

function ProposalCalendar({
  shiftsByDate,
  sortedDates,
  selectedToCommit,
  committedIndexes,
  committedShiftsByIndex,
  overridesByIndex,
  onToggleCommitTick,
  onClearOverride,
  onShiftClick,
  onShiftAction,
}) {
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
              {dayShifts.map((s, posInDay) => {
                // Once committed, the proposal can map to N live shifts
                // (original + duplicates). The first committed shift is the
                // proposal's "primary" — render it on the main card. Each
                // extra shift gets its own slim DuplicateShiftCard so the
                // admin sees one card per actual roster row.
                const committed = committedShiftsByIndex?.[s.__index] ?? []
                const primary = committed.length > 0 ? [committed[0]] : null
                const dups = committed.slice(1)
                return (
                  <Fragment key={s.__index}>
                    <ShiftCard
                      shift={s}
                      isCommitTicked={selectedToCommit?.has(s.__index) ?? false}
                      isCommitted={committedIndexes?.has(s.__index) ?? false}
                      committedShifts={primary}
                      override={overridesByIndex?.[s.__index] ?? null}
                      onClearOverride={() => onClearOverride?.(s.__index)}
                      onToggleCommitTick={() => onToggleCommitTick?.(s.__index)}
                      onCardClick={() => onShiftClick?.(s, s.__index)}
                      onAction={(action) => onShiftAction?.(s, s.__index, action, posInDay, dayShifts)}
                      hasPrev={posInDay > 0}
                      hasNext={posInDay < dayShifts.length - 1}
                    />
                    {dups.map((dup, dupIdx) => (
                      <DuplicateShiftCard
                        key={`${s.__index}-dup-${dup.shift_id ?? dupIdx}`}
                        shift={s}
                        liveShift={dup}
                      />
                    ))}
                  </Fragment>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ShiftCard({
  shift,
  isCommitTicked,
  isCommitted,
  committedShifts,
  override,
  onClearOverride,
  onToggleCommitTick,
  onCardClick,
  onAction,
  hasPrev,
  hasNext,
}) {
  const unassigned = !shift.staff_id
  // Phase 3: only `kind === 'new'` proposals can be committed. Other kinds
  // ('extend', 'untouched_for_reason') are display-only.
  const isCommittable = shift.kind === 'new' || !shift.kind
  // Override-derived display state.
  const overrideAction = override?.action ?? null
  const isDeleted = overrideAction === 'delete'
  const isUnassignOverride = overrideAction === 'unassign'
  const duplicateCount = overrideAction === 'duplicate'
    ? (override.target_staff_ids?.length || 0)
      + (override.add_unassigned_jockey ? 1 : 0)
      + (override.add_unassigned_fleet ? 1 : 0)
    : 0
  // Live committed state takes precedence: once the shift is on the live roster,
  // show the actual claim status (could differ from the proposal if a jockey grabbed it).
  const liveCommitted = isCommitted && Array.isArray(committedShifts) && committedShifts.length > 0
  const displayInitials = liveCommitted
    ? committedShifts.map((c) => c.staff_initials || '?').join(' · ')
    : (isUnassignOverride
      ? '?'
      : (shift.staff_initials || (shift.staff_id ? `staff #${shift.staff_id}` : '?')))
  const liveUnassigned = liveCommitted && committedShifts.every((c) => !c.staff_id)
  const showUnassigned = liveCommitted ? liveUnassigned : unassigned
  // Source badge for already-saved shifts so admins can tell at a glance
  // whether an `untouched_for_reason` row came from a manual Calendar
  // entry or a previous engine run.
  const sourceBadge = shift.kind === 'untouched_for_reason'
    ? (shift.created_source === 'planner'
        ? { label: 'Engine', cls: 'prp-source-engine', title: shift.planner_run_id ? `Engine commit (run ${shift.planner_run_id.slice(0, 8)})` : 'Created by a previous engine commit' }
        : { label: 'Calendar', cls: 'prp-source-manual', title: 'Created manually via the admin Calendar' })
    : null
  // Cards backed by an admin-created Calendar shift are read-only in the
  // planner — Duplicate / Merge / Split / Unassign / Delete belong on the
  // Calendar UI, not here. Hide the action row to avoid implying the planner
  // can mutate them.
  const isAdminCreated = shift.kind === 'untouched_for_reason' && shift.created_source === 'manual'
  return (
    <div
      className={`prp-shift ${showUnassigned ? 'unassigned' : ''} prp-shift-${shift.kind || 'new'} ${
        isAdminCreated ? 'prp-shift-calendar-source' : ''
      } ${isCommitTicked ? 'commit-ticked' : ''
      } ${isCommitted ? 'committed' : ''} ${isDeleted ? 'override-delete' : ''} ${
        overrideAction ? 'has-override' : ''
      }`}
    >
      {isCommittable && isCommitted && (
        <div
          className="prp-committed-banner"
          title="This proposal has already been committed to the live roster — undo the run if you want to remove it"
        >
          ✓ Committed — live in roster
        </div>
      )}
      {!COMMIT_PIPELINE_DISABLED && isCommittable && !isCommitted && (
        <label
          className="prp-commit-tick"
          onClick={(e) => e.stopPropagation()}
          title="Tick to include this shift when committing"
        >
          <input
            type="checkbox"
            checked={!!isCommitTicked}
            onChange={onToggleCommitTick}
          />
          <span className="prp-commit-tick-label">Include in commit</span>
        </label>
      )}
      {overrideAction && !isCommitted && (
        <button
          type="button"
          className={`prp-override-badge prp-override-${overrideAction}`}
          onClick={(e) => { e.stopPropagation(); onClearOverride?.() }}
          title="Click to clear this override"
        >
          {overrideAction === 'delete' && '✕ Delete'}
          {overrideAction === 'unassign' && '? Unassign'}
          {overrideAction === 'duplicate' && `+${duplicateCount} Duplicate`}
          {overrideAction === 'merge' && '⇔ Merge'}
          {overrideAction === 'split' && '⇆ Split'}
        </button>
      )}
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
        {sourceBadge && (
          <div className={`prp-source-badge ${sourceBadge.cls}`} title={sourceBadge.title}>
            {sourceBadge.label}
          </div>
        )}
        <div className="prp-shift-time">
          {formatTime(shift.start_time)}–{formatTime(shift.end_time)}
        </div>
        <div className="prp-shift-staff">
          {showUnassigned ? '? unassigned' : displayInitials}
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
      {!isCommitted && !isAdminCreated && (
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
            className="action-btn unassign-btn"
            onClick={(e) => { e.stopPropagation(); onAction?.('unassign') }}
            disabled={!shift.staff_id}
            title={!shift.staff_id ? 'Already unassigned' : 'Drop staff_id so any jockey can claim it'}
          >
            Unassign
          </button>
          <button
            type="button"
            className="action-btn cancel-btn"
            onClick={(e) => { e.stopPropagation(); onAction?.('delete') }}
          >
            Delete
          </button>
        </div>
      )}
    </div>
  )
}

// Slim card rendered for each duplicate of a committed proposal — one card
// per live shift on the roster. No commit/override controls (the shift is
// already live; admins manage it via the regular roster admin UI).
function DuplicateShiftCard({ shift, liveShift }) {
  const isUnassigned = !liveShift?.staff_id
  const initials = liveShift?.staff_initials || '?'
  const isFleet = liveShift?.intended_driver_type === 'fleet'
  return (
    <div
      className={`prp-shift prp-shift-duplicate ${isUnassigned ? 'unassigned' : ''} committed`}
    >
      <div
        className="prp-committed-banner prp-duplicate-banner"
        title="Live duplicate shift created at commit time"
      >
        ⎘ Duplicate — live in roster
      </div>
      <div className="prp-shift-body" title="Live duplicate shift">
        <div className="prp-shift-time">
          {formatTime(shift.start_time)}–{formatTime(shift.end_time)}
        </div>
        <div className="prp-shift-staff">
          {isUnassigned ? `? unassigned (${isFleet ? 'fleet' : 'jockey'})` : initials}
        </div>
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
        // The /api/roster?date= endpoint returns any shift whose start
        // OR end falls on the date — fine for the main calendar (which
        // renders overnight shifts on both days), but here we want only
        // shifts that actually START on this date. A 23:30–01:00 shift
        // belongs to its start day, not its end day.
        const allAdmin = adminRes.ok ? await adminRes.json() : []
        setAdminShifts(allAdmin.filter((s) => s.date === shift.date))
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
  const isRefunded = event.status === 'refunded'
  const eventTime = formatEventTime(event.event_time)
  return (
    <li className={`prp-event prp-event-${isDropoff ? 'dropoff' : 'pickup'} ${isRefunded ? 'prp-event-refunded' : ''}`}>
      <div className="prp-event-head">
        <span className="prp-event-icon">{isDropoff ? '🚗' : '🛬'}</span>
        <span className="prp-event-ref">{event.booking_reference}</span>
        {isRefunded && (
          <span className="prp-event-refunded-pill" title="This booking was refunded">REFUNDED</span>
        )}
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
            {Array.isArray(w.exclusions) && w.exclusions.length > 0 && (
              <ul className="prp-warning-exclusions">
                {w.exclusions.map((ex, j) => (
                  <li key={j}>
                    <strong>{ex.initials}</strong> — {ex.reason}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

function JockeyPreferences({ jockeys }) {
  if (!jockeys || jockeys.length === 0) return null
  return (
    <div className="prp-jockeys">
      <h4>Jockey drivers ({jockeys.length})</h4>
      <table className="prp-jockeys-table">
        <thead>
          <tr>
            <th>Driver</th>
            <th>Window</th>
            <th>Days off</th>
            <th>Holidays in window</th>
            <th>Role</th>
          </tr>
        </thead>
        <tbody>
          {jockeys.map((j) => (
            <tr key={j.id}>
              <td>
                <strong>{j.initials}</strong>{' '}
                <span className="prp-jockeys-name">
                  {j.first_name} {j.last_name}
                </span>
              </td>
              <td>
                {j.preferred_start_time && j.preferred_end_time
                  ? `${formatTime(j.preferred_start_time)}–${formatTime(j.preferred_end_time)}`
                  : <span className="prp-jockeys-muted">no window</span>}
              </td>
              <td>
                {j.preferred_days_off && j.preferred_days_off.length > 0
                  ? j.preferred_days_off.join(', ')
                  : <span className="prp-jockeys-muted">none</span>}
              </td>
              <td>
                {j.holidays_in_window && j.holidays_in_window.length > 0
                  ? j.holidays_in_window.map((h, i) => (
                      <div key={i}>
                        {h.start_date} → {h.end_date}
                      </div>
                    ))
                  : <span className="prp-jockeys-muted">none</span>}
              </td>
              <td>
                {j.is_fallback_driver
                  ? <span className="prp-jockeys-fallback">fallback</span>
                  : <span className="prp-jockeys-primary">primary</span>}
                {j.auto_assign_excluded && (
                  <span className="prp-jockeys-disabled"> (auto-assign off)</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PredictedHoursBreakdown({ jockeys, maxHoursPerWeek = 40, windowStart, windowEnd }) {
  const [expanded, setExpanded] = useState(true)
  const [expandedWeeks, setExpandedWeeks] = useState({})
  const [totalsExpanded, setTotalsExpanded] = useState(false)

  if (!jockeys || jockeys.length === 0) return null

  // Union of every week any jockey appears in, ascending.
  const weekKeys = Array.from(
    new Set(
      jockeys.flatMap((j) =>
        (j.predicted_hours_by_week || []).map((w) => w.week_start)
      )
    )
  ).sort()

  if (weekKeys.length === 0) return null

  const fmtHours = (h) => `${Number(h || 0).toFixed(1)}h`
  const windowLabel = windowStart && windowEnd
    ? `${formatUkDate(windowStart)} → ${formatUkDate(windowEnd)}`
    : ''

  return (
    <div className="hours-breakdown-section prp-predicted-hours">
      <h3
        className="hours-breakdown-title hours-breakdown-clickable"
        onClick={() => setExpanded((e) => !e)}
      >
        <span className={`hours-section-caret ${expanded ? 'expanded' : ''}`}>▶</span>
        Predicted hours <span className="week-range">({windowLabel})</span>
      </h3>
      {expanded && (
        <div className="hours-breakdown-container">
          {weekKeys.map((wk, idx) => {
            const weekEnd = isoAddDays(wk, 6)
            return (
              <div key={wk} className="hours-week-container">
                <div
                  className="hours-week-header"
                  onClick={() =>
                    setExpandedWeeks((p) => ({ ...p, [idx]: !p[idx] }))
                  }
                >
                  <span className={`hours-caret ${expandedWeeks[idx] ? 'expanded' : ''}`}>▶</span>
                  <span className="hours-week-label">Week of {formatUkDate(wk)}</span>
                  <span className="hours-week-range">
                    ({formatUkDate(wk)} – {formatUkDate(weekEnd)})
                  </span>
                </div>
                {expandedWeeks[idx] && (
                  <div className="hours-week-content">
                    <div className="weekly-hours-grid">
                      {jockeys.map((j) => {
                        const wkHours =
                          (j.predicted_hours_by_week || []).find(
                            (w) => w.week_start === wk
                          )?.hours ?? 0
                        const atCap = wkHours >= maxHoursPerWeek
                        return (
                          <div
                            key={j.id}
                            className={`weekly-hours-card${atCap ? ' weekly-hours-card-over' : ''}`}
                          >
                            <div className="employee-name">
                              {j.initials} · {j.first_name} {j.last_name}
                            </div>
                            <div className="hours-summary">
                              <span className="total-hours">{fmtHours(wkHours)}</span>
                              {atCap && (
                                <span className="shift-count">at/over cap</span>
                              )}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            )
          })}

          {/* Monthly Totals — total predicted across the window */}
          <div className="hours-week-container monthly-totals">
            <div
              className="hours-week-header monthly-header"
              onClick={() => setTotalsExpanded((e) => !e)}
            >
              <span className={`hours-caret ${totalsExpanded ? 'expanded' : ''}`}>▶</span>
              <span className="hours-week-label">Monthly Totals</span>
            </div>
            {totalsExpanded && (
              <div className="hours-week-content">
                <div className="weekly-hours-grid">
                  {jockeys.map((j) => (
                    <div key={j.id} className="weekly-hours-card">
                      <div className="employee-name">
                        {j.initials} · {j.first_name} {j.last_name}
                      </div>
                      <div className="hours-summary">
                        <span className="total-hours">
                          {fmtHours(j.predicted_hours_total)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function isoAddDays(iso, days) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d))
  dt.setUTCDate(dt.getUTCDate() + days)
  const yy = dt.getUTCFullYear()
  const mm = String(dt.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(dt.getUTCDate()).padStart(2, '0')
  return `${yy}-${mm}-${dd}`
}

// =============================================================================
// CommitBar — toolbar above the proposal calendar.
// Shows tick count, select-all / clear / commit buttons, last-action banner.
// =============================================================================
function CommitBar({ selectedCount, newProposalCount, onSelectAll, onClear, onCommit, committing, message }) {
  return (
    <div className="prp-commit-bar">
      <div className="prp-commit-counter">
        <strong>{selectedCount}</strong> of <strong>{newProposalCount}</strong> new proposal{newProposalCount === 1 ? '' : 's'} selected
      </div>
      <div className="prp-commit-actions">
        <button
          type="button"
          className="prp-commit-secondary"
          onClick={onSelectAll}
          disabled={committing || newProposalCount === 0 || selectedCount === newProposalCount}
        >
          Select all
        </button>
        <button
          type="button"
          className="prp-commit-secondary"
          onClick={onClear}
          disabled={committing || selectedCount === 0}
        >
          Clear
        </button>
        <button
          type="button"
          className="prp-commit-primary"
          onClick={onCommit}
          disabled={committing || selectedCount === 0}
        >
          {committing ? 'Committing…' : `Commit ${selectedCount} shift${selectedCount === 1 ? '' : 's'}`}
        </button>
      </div>
      {message && <div className="prp-commit-message">{message}</div>}
    </div>
  )
}

// =============================================================================
// CommitConfirmModal — second-step confirmation before /commit POST.
// Phase 3 commits are additive only, so this is a single-click confirm
// (Phase 4 will add a stricter confirm for within-24h discards).
// =============================================================================
function CommitConfirmModal({ count, onCancel, onConfirm, submitting }) {
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
        <h3 style={{ marginTop: 0 }}>Commit {count} shift{count === 1 ? '' : 's'}?</h3>
        <p style={{ color: '#444' }}>
          These shifts will be written to the live roster, tagged with the run ID
          so an undo can remove them later. Phase 3 is additive only — any
          proposal that overlaps an existing shift will be rejected and nothing
          will be committed.
        </p>
        <div className="modal-actions">
          <button className="modal-btn modal-btn-secondary" onClick={onCancel} disabled={submitting}>
            Cancel
          </button>
          <button className="modal-btn modal-btn-primary" onClick={onConfirm} disabled={submitting}>
            {submitting ? 'Committing…' : 'Yes, commit'}
          </button>
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// UndoConfirmModal — for DELETE /runs/{run_id}.
// =============================================================================
function UndoConfirmModal({ runId, onCancel, onConfirm, submitting }) {
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
        <h3 style={{ marginTop: 0 }}>Undo this run?</h3>
        <p style={{ color: '#444' }}>
          Deletes every shift this run created (status = scheduled). Already-confirmed
          shifts are <strong>kept</strong>. Customer bookings linked to deleted shifts
          are unlinked, not removed.
        </p>
        <p style={{ color: '#777', fontSize: '0.85rem' }}>
          Run: <code>{runId}</code>
        </p>
        <div className="modal-actions">
          <button className="modal-btn modal-btn-secondary" onClick={onCancel} disabled={submitting}>
            Cancel
          </button>
          <button className="modal-btn modal-btn-primary" onClick={onConfirm} disabled={submitting}>
            {submitting ? 'Undoing…' : 'Yes, undo'}
          </button>
        </div>
      </div>
    </div>
  )
}


// ===========================================================================
// RegenerateAutoModal — date-scope picker for the (Re)generate auto-roster
// flow. Three modes:
//   * next_4_weeks (default) — rolling window from today.
//   * date_range — admin picks from / to.
//   * individual_dates — admin enters a comma-separated list of YYYY-MM-DD.
// Force-rebuild is opt-in and double-confirmed because it deletes existing
// untouched auto-shifts in scope before recreating.
// ===========================================================================

function RegenerateAutoModal({ onCancel, onConfirm, submitting }) {
  const [mode, setMode] = useState('next_4_weeks')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [datesText, setDatesText] = useState('')
  const [forceRebuild, setForceRebuild] = useState(false)
  const [showRebuildConfirm, setShowRebuildConfirm] = useState(false)
  const [validationError, setValidationError] = useState(null)

  function buildPayload() {
    const payload = { mode, force_rebuild: forceRebuild }
    if (mode === 'date_range') {
      if (!dateFrom || !dateTo) {
        return { error: 'Pick both a from and a to date.' }
      }
      if (dateTo < dateFrom) {
        return { error: 'To date must be on or after from date.' }
      }
      payload.date_from = dateFrom
      payload.date_to = dateTo
    } else if (mode === 'individual_dates') {
      const tokens = datesText
        .split(/[\s,]+/)
        .map((t) => t.trim())
        .filter(Boolean)
      if (tokens.length === 0) {
        return { error: 'Enter at least one date (YYYY-MM-DD, comma-separated).' }
      }
      const bad = tokens.filter((t) => !/^\d{4}-\d{2}-\d{2}$/.test(t))
      if (bad.length) {
        return { error: `Invalid date format: ${bad.join(', ')}. Use YYYY-MM-DD.` }
      }
      payload.dates = tokens
    }
    return { payload }
  }

  function handleSubmit() {
    setValidationError(null)
    const { payload, error } = buildPayload()
    if (error) {
      setValidationError(error)
      return
    }
    if (forceRebuild && !showRebuildConfirm) {
      setShowRebuildConfirm(true)
      return
    }
    onConfirm(payload)
  }

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginTop: 0 }}>Regenerate auto-roster</h3>
        <p style={{ color: '#444', marginTop: 0 }}>
          Pulls every CONFIRMED booking in scope and re-runs auto-create / extend.
          Refunded bookings keep their links; cancelled bookings unlink.
        </p>

        <div className="prp-regen-section">
          <label className="prp-regen-radio">
            <input
              type="radio"
              name="regen-mode"
              checked={mode === 'next_4_weeks'}
              onChange={() => setMode('next_4_weeks')}
            />
            <span><strong>Next 4 weeks</strong> — rolling window from today.</span>
          </label>
          <label className="prp-regen-radio">
            <input
              type="radio"
              name="regen-mode"
              checked={mode === 'date_range'}
              onChange={() => setMode('date_range')}
            />
            <span><strong>Date range</strong></span>
          </label>
          {mode === 'date_range' && (
            <div className="prp-regen-inputs">
              <label>
                From <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
              </label>
              <label>
                To <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
              </label>
            </div>
          )}
          <label className="prp-regen-radio">
            <input
              type="radio"
              name="regen-mode"
              checked={mode === 'individual_dates'}
              onChange={() => setMode('individual_dates')}
            />
            <span><strong>Individual dates</strong> — comma-separated YYYY-MM-DD</span>
          </label>
          {mode === 'individual_dates' && (
            <div className="prp-regen-inputs">
              <input
                type="text"
                value={datesText}
                onChange={(e) => setDatesText(e.target.value)}
                placeholder="2026-06-04, 2026-06-05, 2026-06-11"
                style={{ width: '100%' }}
              />
            </div>
          )}
        </div>

        <label className="prp-regen-rebuild">
          <input
            type="checkbox"
            checked={forceRebuild}
            onChange={(e) => {
              setForceRebuild(e.target.checked)
              setShowRebuildConfirm(false)
            }}
          />
          <span>
            <strong>Force rebuild.</strong> Delete every still-unassigned, still-scheduled
            auto-shift in the chosen scope before recreating. <em>Wipes admin edits to those
            shifts.</em> Off by default.
          </span>
        </label>
        {forceRebuild && showRebuildConfirm && (
          <div className="prp-regen-rebuild-confirm">
            You're about to delete every untouched auto-shift in scope. Click Run again to confirm.
          </div>
        )}

        {validationError && <div className="prp-error">{validationError}</div>}

        <div className="modal-actions">
          <button className="modal-btn modal-btn-secondary" onClick={onCancel} disabled={submitting}>
            Cancel
          </button>
          <button className="modal-btn modal-btn-primary" onClick={handleSubmit} disabled={submitting}>
            {submitting ? 'Running…' : forceRebuild && showRebuildConfirm ? 'Yes, rebuild' : 'Run'}
          </button>
        </div>
      </div>
    </div>
  )
}
