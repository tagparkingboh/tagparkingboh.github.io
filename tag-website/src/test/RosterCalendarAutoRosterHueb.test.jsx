import { describe, expect, it } from 'vitest'
import { getRosterCoverageReviewItems } from '../components/RosterCalendar'

const pickupBookings = {
  dropoffs: [],
  pickups: [
    {
      id: 501,
      status: 'confirmed',
      reference: 'TAG-HUEB501',
      customer_first_name: 'Late',
      customer_last_name: 'Arrival',
      flight_arrival_time: '23:50',
      pickup_flight_number: 'KL501',
      pickup_origin: 'AMS',
    },
  ],
}

const linkedAutoShift = (overrides = {}) => ({
  id: 20,
  staff_id: null,
  created_source: 'auto',
  date: '2026-06-14',
  end_date: '2026-06-15',
  start_time: '21:45',
  end_time: '00:10',
  bookings: [{ id: 501, reference: 'TAG-HUEB501', type: 'pickup' }],
  ...overrides,
})

const fixedAssignedShift = (overrides = {}) => ({
  id: 10,
  staff_id: 7,
  created_source: 'manual',
  date: '2026-06-14',
  end_date: '2026-06-14',
  start_time: '21:50',
  end_time: '23:50',
  bookings: [],
  ...overrides,
})

describe('HUEB: auto-roster unstaffed overlap alert', () => {
  it('H: alerts when a late booking is linked to an auto-created unassigned shift overlapping a fixed assigned shift', () => {
    const items = getRosterCoverageReviewItems(pickupBookings, [
      fixedAssignedShift(),
      linkedAutoShift(),
    ])

    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({
      kind: 'unassigned-linked-shift',
      booking_reference: 'TAG-HUEB501',
      event_type: 'pickup',
      shift_ids: [20],
      shift_times: ['21:45-00:10'],
    })
  })

  it('U: does not alert for a manually-created unassigned shift, even when it overlaps assigned work', () => {
    const items = getRosterCoverageReviewItems(pickupBookings, [
      fixedAssignedShift(),
      linkedAutoShift({ created_source: 'manual' }),
    ])

    expect(items).toEqual([])
  })

  it('E: does not alert for an auto-created unassigned shift when no assigned shift blocks the same window', () => {
    const items = getRosterCoverageReviewItems(pickupBookings, [
      fixedAssignedShift({ start_time: '16:00', end_time: '17:30' }),
      linkedAutoShift({ start_time: '21:45', end_time: '00:10' }),
    ])

    expect(items).toEqual([])
  })

  it('B: treats overnight overlap as blocking when the auto shift crosses midnight', () => {
    const items = getRosterCoverageReviewItems(pickupBookings, [
      fixedAssignedShift({
        id: 11,
        start_time: '23:40',
        end_time: '00:40',
        end_date: '2026-06-15',
      }),
      linkedAutoShift({
        id: 21,
        start_time: '23:40',
        end_time: '01:35',
      }),
    ])

    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({
      kind: 'unassigned-linked-shift',
      shift_ids: [21],
      shift_times: ['23:40-01:35'],
    })
  })
})
