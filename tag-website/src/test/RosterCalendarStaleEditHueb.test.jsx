import { describe, expect, it } from 'vitest'
import {
  buildShiftUpdateDiff,
  shiftToEditForm,
  shouldRefetchOnWake,
  WAKE_REFETCH_MIN_INTERVAL_MS,
} from '../components/RosterCalendar'

// Fixtures mirror the 2026-07-23 incident (all times UK wall-clock): the
// Mon 27 Jul early shift, cut by the engine to 03:50-07:30 (earliest job
// TAG-DKG92004 04:20 minus the 30-min start buffer), staffed and admin
// shaped. The admin edited from a phone whose suspended tab still held an
// older snapshot — saving a driver change wrote the stale window back.
const apiShift = (overrides = {}) => ({
  id: 5600,
  staff_id: 15,
  created_source: 'auto',
  date: '2026-07-27',
  end_date: '2026-07-27',
  start_time: '03:50:00',
  end_time: '07:30:00',
  shift_type: 'early_morning',
  notes: null,
  intended_driver_type: 'jockey',
  bookings: [
    { id: 1021, reference: 'TAG-DKG92004' },
    { id: 912, reference: 'TAG-PSQ44974' },
  ],
  ...overrides,
})

const openedForm = (overrides = {}) => ({
  staff_id: 15,
  booking_ids: [1021, 912],
  date: '27/07/2026',
  end_date: '',
  start_time: '03:50',
  end_time: '07:30',
  shift_type: 'early_morning',
  notes: '',
  intended_driver_type: 'jockey',
  ...overrides,
})

describe('HUEB: shiftToEditForm (dialog populates from a fresh fetch)', () => {
  it('H: maps an API shift row to the edit form shape', () => {
    expect(shiftToEditForm(apiShift())).toEqual(openedForm())
  })

  it('H: trims HH:MM:SS times to the HH:MM the time inputs use', () => {
    const form = shiftToEditForm(apiShift({ start_time: '04:30:00', end_time: '08:00:00' }))
    expect(form.start_time).toBe('04:30')
    expect(form.end_time).toBe('08:00')
  })

  it('E: overnight shift keeps its distinct end_date as a UK string', () => {
    const form = shiftToEditForm(apiShift({ date: '2026-07-27', end_date: '2026-07-28' }))
    expect(form.date).toBe('27/07/2026')
    expect(form.end_date).toBe('28/07/2026')
  })

  it('E: unassigned shift with null fields normalises to form defaults', () => {
    const form = shiftToEditForm(apiShift({
      staff_id: null,
      notes: null,
      intended_driver_type: null,
      bookings: null,
    }))
    expect(form.staff_id).toBe('')
    expect(form.notes).toBe('')
    expect(form.intended_driver_type).toBe('jockey')
    expect(form.booking_ids).toEqual([])
  })
})

describe('HUEB: buildShiftUpdateDiff (diff-only saves)', () => {
  it('H: driver-only change sends staff_id and NOTHING else — the stale-tab regression', () => {
    // The exact incident shape: admin reassigns the driver from a dialog
    // whose window fields are untouched. The old code sent start_time
    // 03:50 back even when the DB had since moved on — the diff must not.
    const diff = buildShiftUpdateDiff(openedForm(), openedForm({ staff_id: '14' }))
    expect(diff).toEqual({ staff_id: 14 })
  })

  it('H: time-only change sends just the changed time field', () => {
    const diff = buildShiftUpdateDiff(openedForm(), openedForm({ start_time: '04:30' }))
    expect(diff).toEqual({ start_time: '04:30' })
  })

  it('H: untouched form produces an empty diff (save becomes a no-op)', () => {
    expect(buildShiftUpdateDiff(openedForm(), openedForm())).toEqual({})
  })

  it('U: unassigning sends an explicit staff_id null, not an omission', () => {
    // Backend distinguishes absent (leave alone) from null (unassign) via
    // the staff_id_provided marker — clearing the driver must be a null.
    const diff = buildShiftUpdateDiff(openedForm(), openedForm({ staff_id: '' }))
    expect(diff).toEqual({ staff_id: null })
  })

  it('U: clearing an overnight end_date sends an explicit null', () => {
    const initial = openedForm({ end_date: '28/07/2026' })
    const diff = buildShiftUpdateDiff(initial, { ...initial, end_date: '' })
    expect(diff).toEqual({ end_date: null })
  })

  it('E: booking_ids reordered or string-typed is NOT a change', () => {
    // Checkbox toggles can leave ids as strings and in click order — the
    // same set must not go on the wire (a booking_ids write rebuilds links
    // and pool-syncs twins server-side).
    const diff = buildShiftUpdateDiff(
      openedForm({ booking_ids: [1021, 912] }),
      openedForm({ booking_ids: ['912', '1021'] }),
    )
    expect(diff).toEqual({})
  })

  it('E: a real booking set change is sent as parsed ints', () => {
    const diff = buildShiftUpdateDiff(
      openedForm(),
      openedForm({ booking_ids: ['1021', '912', '1450'] }),
    )
    expect(diff).toEqual({ booking_ids: [1021, 912, 1450] })
  })

  it('E: bookingLinksReadOnly suppresses booking_ids even when changed', () => {
    // Synced pool children mirror their parent's bookings; the dialog
    // renders them read-only and the save must never write them.
    const diff = buildShiftUpdateDiff(
      openedForm(),
      openedForm({ booking_ids: [1021] }),
      { bookingLinksReadOnly: true },
    )
    expect(diff).toEqual({})
  })

  it('E: clearing notes sends empty string so the backend actually clears', () => {
    const initial = openedForm({ notes: 'cover for holiday' })
    const diff = buildShiftUpdateDiff(initial, { ...initial, notes: '' })
    expect(diff).toEqual({ notes: '' })
  })

  it('B: date change converts UK input to the ISO the API expects', () => {
    const diff = buildShiftUpdateDiff(openedForm(), openedForm({ date: '28/07/2026' }))
    expect(diff).toEqual({ date: '2026-07-28' })
  })

  it('B: missing snapshot (defensive) treats every set field as changed', () => {
    // If the ref were ever lost the diff degrades to the old full-payload
    // behaviour rather than sending nothing.
    const diff = buildShiftUpdateDiff({}, openedForm())
    expect(diff.start_time).toBe('03:50')
    expect(diff.staff_id).toBe(15)
    expect(diff.date).toBe('2026-07-27')
  })
})

describe('HUEB: shouldRefetchOnWake (stale-tab refetch throttle)', () => {
  const T0 = 1_753_263_000_000 // arbitrary epoch ms; elapsed math is tz-free

  it('H: visible tab past the throttle interval refetches', () => {
    expect(shouldRefetchOnWake('visible', T0, T0 + WAKE_REFETCH_MIN_INTERVAL_MS + 1)).toBe(true)
  })

  it('U: hidden tab never refetches, however stale', () => {
    expect(shouldRefetchOnWake('hidden', T0, T0 + 10 * WAKE_REFETCH_MIN_INTERVAL_MS)).toBe(false)
  })

  it('B: exactly at the interval refetches (t)', () => {
    expect(shouldRefetchOnWake('visible', T0, T0 + WAKE_REFETCH_MIN_INTERVAL_MS)).toBe(true)
  })

  it('B: one ms under the interval does not (t-ε)', () => {
    expect(shouldRefetchOnWake('visible', T0, T0 + WAKE_REFETCH_MIN_INTERVAL_MS - 1)).toBe(false)
  })
})
