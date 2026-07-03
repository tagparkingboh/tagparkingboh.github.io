/**
 * Per-slot availability filtering — the batched /api/capacity/check-slots
 * call and the owner decision to HIDE unavailable drop-off slots (not
 * disable them), with the page-1 "no space for this trip" full stop when
 * every candidate is full.
 *
 * Safety valves under test:
 *  - filtering only applies while the backend gate is live
 *    (time_aware_gate === true in the response) — otherwise per-day
 *    create-intent would 400 slots we still show;
 *  - filtering only applies when the answer matches the CURRENT inputs
 *    (slotCheckKey) — a stale verdict must never hide fresh slots;
 *  - a selected slot that becomes unavailable is deselected so the flow
 *    can't progress on it.
 *
 * Render-based; pattern from BookingsNewCapacityHonesty.test.jsx.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import BookingsNew from '../BookingsNew'

const DROPOFF = new Date(new Date().getFullYear(), new Date().getMonth(), new Date().getDate() + 30)
const PICKUP = new Date(new Date().getFullYear(), new Date().getMonth(), new Date().getDate() + 33)

const iso = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

// flightTime 14:00 → candidate slots 11:15 (165), 12:00 (120), 12:30 (90).
const SLOT_TIMES = ['11:15', '12:00', '12:30']

/**
 * Fetch mock. `slotResponses` is a queue: each /api/capacity/check-slots
 * POST consumes one {verdicts, gate} entry and answers with per-time
 * availability (default true). When the queue is empty the request HANGS
 * (never resolves) — that models an in-flight answer for changed inputs,
 * which must leave all slots visible.
 */
function installFetch({ slotResponses = [] } = {}) {
  const queue = [...slotResponses]
  const checkSlotsCalls = []
  global.fetch = vi.fn((url, opts = {}) => {
    const u = String(url)
    if (u.includes('/api/capacity/check-slots')) {
      const body = JSON.parse(opts.body)
      checkSlotsCalls.push(body)
      if (queue.length === 0) return new Promise(() => {})
      const { verdicts = {}, gate = true } = queue.shift()
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          slots: body.dropoff_times.map((t) => ({
            dropoff_time: t,
            available: verdicts[t] !== false,
            peak: verdicts[t] === false ? 73 : 0,
          })),
          online_capacity: 73,
          max_capacity: 73,
          time_aware_gate: gate,
        }),
      })
    }
    if (u.includes('/api/capacity/daily')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          daily_occupancy: {},
          daily_through_occupancy: {},
          daily_capacity: {},
          online_capacity: 73,
          max_capacity: 73,
          time_aware_gate: true,
        }),
      })
    }
    const arrayEndpoints = [
      '/api/booking/destinations', '/api/booking/airlines',
      '/api/flights/arrivals', '/api/flights/departures',
      '/api/blocked-dates/check',
    ]
    const body = arrayEndpoints.some((e) => u.includes(e)) ? [] : {}
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) })
  })
  return { checkSlotsCalls }
}

function seedManualFlow({ selectedSlot = '', arrivalTime = '' } = {}) {
  sessionStorage.clear()
  sessionStorage.setItem('booking_formData', JSON.stringify({
    dropoffDate: `${iso(DROPOFF)}T00:00:00`,
    pickupDate: `${iso(PICKUP)}T00:00:00`,
    dropoffSlot: '',
    dropoffAirline: '',
  }))
  sessionStorage.setItem('booking_manualDepartureData', JSON.stringify({
    flightTime: '14:00',
    dropoffSlot: selectedSlot,
    destinationName: 'Alicante',
    destinationCode: 'ALC',
    customDestination: '',
    airlineName: 'Jet2',
  }))
  if (arrivalTime) {
    sessionStorage.setItem('booking_manualArrivalData', JSON.stringify({
      flightTime: arrivalTime,
      airlineCode: 'LS',
      airlineName: 'Jet2',
      originName: 'Alicante',
      originCode: 'ALC',
      customOrigin: '',
    }))
  }
}

function mount() {
  return render(
    <MemoryRouter>
      <BookingsNew />
    </MemoryRouter>
  )
}

// jsdom reports 'ontouchstart' in window, so MobileTimePicker renders its
// read-only input + wheel overlay (not the desktop text input). Drive it
// the way a touch user would: open, pick the hour, confirm. Minutes stay
// at their parsed value ('00' here).
function setTimeViaWheel(inputId, hour) {
  fireEvent.click(document.getElementById(inputId))
  const overlay = document.querySelector('.time-picker-overlay')
  expect(overlay).not.toBeNull()
  const hourWheel = overlay.querySelectorAll('.wheel-column')[0]
  const item = Array.from(hourWheel.querySelectorAll('.wheel-item'))
    .find((el) => el.textContent === hour)
  fireEvent.click(item)
  fireEvent.click(overlay.querySelector('.time-picker-confirm'))
}

afterEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
})

describe('BookingsNew — slot filtering from /api/capacity/check-slots', () => {
  it('hides an unavailable slot and keeps the others (gate on)', async () => {
    installFetch({ slotResponses: [{ verdicts: { '12:00': false }, gate: true }] })
    seedManualFlow()
    mount()

    await waitFor(() => {
      expect(screen.getByText('11:15')).toBeInTheDocument()
      expect(screen.queryByText('12:00')).not.toBeInTheDocument()
    })
    // Hidden means GONE — no disabled radio, no greyed card.
    expect(screen.getByText('12:30')).toBeInTheDocument()
    expect(document.querySelectorAll('input[name="manualDropoffSlot"]')).toHaveLength(2)
  })

  it('shows every slot when the backend gate echo is false, whatever the verdicts', async () => {
    installFetch({ slotResponses: [{ verdicts: { '12:00': false, '11:15': false }, gate: false }] })
    seedManualFlow()
    mount()

    // Wait for the check-slots response to have been consumed…
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/capacity/check-slots'), expect.anything())
    })
    // …then confirm nothing was filtered: per-day create-intent is the
    // active gate, so hiding slots it would accept (or showing a UI that
    // disagrees with it) is wrong in both directions.
    for (const t of SLOT_TIMES) {
      expect(screen.getByText(t)).toBeInTheDocument()
    }
  })

  it('ignores a stale answer after inputs change (slotCheckKey mismatch)', async () => {
    // First (and only) queued answer belongs to the 14:00 flight. Changing
    // the departure time re-keys the request; the follow-up call hangs, so
    // the stale verdict must not filter the NEW slot set.
    installFetch({ slotResponses: [{ verdicts: { '12:00': false }, gate: true }] })
    seedManualFlow()
    mount()

    await waitFor(() => {
      expect(screen.queryByText('12:00')).not.toBeInTheDocument()
    })

    setTimeViaWheel('manualFlightTime', '15')
    expect(document.getElementById('manualFlightTime').value).toBe('15:00')

    // New slots: 12:15 / 13:00 / 13:30 — all visible while the re-check is
    // in flight, including 13:00 (the same "standard" slot position whose
    // OLD time was filtered).
    await waitFor(() => {
      expect(screen.getByText('12:15')).toBeInTheDocument()
      expect(screen.getByText('13:00')).toBeInTheDocument()
      expect(screen.getByText('13:30')).toBeInTheDocument()
    })
  })

  it('worst-cased full stop (no arrival yet) uses the tentative copy, not the definitive one', async () => {
    installFetch({
      slotResponses: [{
        verdicts: { '11:15': false, '12:00': false, '12:30': false },
        gate: true,
      }],
    })
    seedManualFlow()  // no arrival time → check runs on the 23:59 worst-case
    mount()

    // Entering the arrival time may reopen slots, so the copy must invite
    // that instead of declaring the trip impossible.
    await waitFor(() => {
      expect(screen.getByText(/can't see space for these dates yet/)).toBeInTheDocument()
    })
    expect(screen.queryByText(/no space for this trip/)).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '01202 798710' })).toBeInTheDocument()
    expect(document.querySelectorAll('input[name="manualDropoffSlot"]')).toHaveLength(0)
    expect(screen.queryByText('Select Drop-off Time')).not.toBeInTheDocument()
  })

  it('full stop with a real arrival time uses the definitive copy', async () => {
    installFetch({
      slotResponses: [{
        verdicts: { '11:15': false, '12:00': false, '12:30': false },
        gate: true,
      }],
    })
    seedManualFlow({ arrivalTime: '09:00' })
    mount()

    await waitFor(() => {
      expect(screen.getByText(/no space for this trip/)).toBeInTheDocument()
    })
    expect(screen.queryByText(/can't see space for these dates yet/)).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '01202 798710' })).toBeInTheDocument()
  })

  it('deselects a selected slot that becomes unavailable so the flow cannot progress', async () => {
    installFetch({ slotResponses: [{ verdicts: { '12:00': false }, gate: true }] })
    seedManualFlow({ selectedSlot: '120' })  // 12:00 selected, then reported full
    mount()

    // The Return Flight section is gated on a selected slot — once 12:00
    // is filtered the selection clears and the section goes away.
    await waitFor(() => {
      expect(screen.queryByText('12:00')).not.toBeInTheDocument()
      expect(screen.queryByText('Return Flight')).not.toBeInTheDocument()
    })
    const checked = Array.from(
      document.querySelectorAll('input[name="manualDropoffSlot"]:checked'))
    expect(checked).toHaveLength(0)
  })

  // Regression: slotCheckKey's return leg must come from the SAME arrival
  // chain as the pricing fetch (arrivalTimeOverride || manual entry ||
  // selected flight) — the slotCheckArrivalTime memo. Reading the old
  // flight-picker-only `pickupTime` memo left manual customers permanently
  // worst-cased at 23:59, and the re-check never fired because the key
  // never changed. The RAW landing time is sent; the backend owns the +30
  // and any midnight roll (_exit_window_from_arrival).
  it('re-checks and restores a hidden slot once the arrival time is entered (manual flow)', async () => {
    const { checkSlotsCalls } = installFetch({
      slotResponses: [
        { verdicts: { '12:00': false }, gate: true },  // no arrival: worst-case
        { verdicts: {}, gate: true },                  // with arrival: all fit
      ],
    })
    seedManualFlow({ selectedSlot: '90' })  // 12:30 stays available/selected
    mount()

    await waitFor(() => {
      expect(screen.queryByText('12:00')).not.toBeInTheDocument()
    })
    // Worst-cased first call: no arrival known yet → no arrival_time sent.
    expect(checkSlotsCalls[0].arrival_time).toBeUndefined()

    // Return Flight section is visible (slot 90 selected) — enter the
    // arrival time, which re-keys the slot check with the raw landing time.
    setTimeViaWheel('manualArrivalFlightTime', '09')

    await waitFor(() => {
      expect(screen.getByText('12:00')).toBeInTheDocument()
    })
    // The re-check carried the RAW landing time — not a client-derived meet
    // time (the +30/midnight-roll belongs to the backend).
    expect(checkSlotsCalls).toHaveLength(2)
    expect(checkSlotsCalls[1].arrival_time).toBe('09:00')
    expect(checkSlotsCalls[1].pickup_time).toBeUndefined()
  })
})

describe('BookingsNew — full-stop recovery path (reviewer-required end-to-end)', () => {
  it('tentative full stop keeps the arrival-entry form on screen', async () => {
    installFetch({
      slotResponses: [{
        verdicts: { '11:15': false, '12:00': false, '12:30': false },
        gate: true,
      }],
    })
    seedManualFlow()  // no arrival → worst-cased verdict
    mount()

    await waitFor(() => {
      expect(screen.getByText(/can't see space for these dates yet/)).toBeInTheDocument()
    })
    // The copy says "add your return flight time below" — the input it
    // points at must actually be there (it is gated on the pickup date,
    // not on a selected slot).
    expect(document.getElementById('manualArrivalFlightTime')).not.toBeNull()
  })

  it('entering an arrival that still leaves everything full flips tentative → definitive', async () => {
    installFetch({
      slotResponses: [
        { verdicts: { '11:15': false, '12:00': false, '12:30': false }, gate: true },
        { verdicts: { '11:15': false, '12:00': false, '12:30': false }, gate: true },
      ],
    })
    seedManualFlow()
    mount()

    await waitFor(() => {
      expect(screen.getByText(/can't see space for these dates yet/)).toBeInTheDocument()
    })

    setTimeViaWheel('manualArrivalFlightTime', '09')

    await waitFor(() => {
      expect(screen.getByText(/no space for this trip/)).toBeInTheDocument()
    })
    expect(screen.queryByText(/can't see space for these dates yet/)).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '01202 798710' })).toBeInTheDocument()
  })

  it('entering an arrival that frees a slot clears the full stop and renders the slot', async () => {
    installFetch({
      slotResponses: [
        { verdicts: { '11:15': false, '12:00': false, '12:30': false }, gate: true },
        { verdicts: { '11:15': false, '12:00': false }, gate: true },  // 12:30 now fits
      ],
    })
    seedManualFlow()
    mount()

    await waitFor(() => {
      expect(screen.getByText(/can't see space for these dates yet/)).toBeInTheDocument()
    })

    setTimeViaWheel('manualArrivalFlightTime', '09')

    // Recovery: the worst-case stop disappears, the freed slot is offered.
    await waitFor(() => {
      expect(screen.getByText('12:30')).toBeInTheDocument()
    })
    expect(screen.queryByText(/can't see space for these dates yet/)).not.toBeInTheDocument()
    expect(screen.queryByText(/no space for this trip/)).not.toBeInTheDocument()
    expect(screen.getByText('Select Drop-off Time')).toBeInTheDocument()
    expect(screen.queryByText('11:15')).not.toBeInTheDocument()
    expect(screen.queryByText('12:00')).not.toBeInTheDocument()
  })
})
