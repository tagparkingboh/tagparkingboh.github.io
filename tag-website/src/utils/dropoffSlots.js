/* Drop-off slot builder with the 04:00 floor (owner-confirmed 2026-07-22).
 *
 * Slots are offsets before the departure time (2¾h / 2h / 1½h). A slot that
 * computes to a small-hours time (00:00–03:59 on the day of the flight) is
 * clamped UP to 04:00 and relabelled — customers are never offered a
 * drop-off earlier than 04:00. Example: 06:20 departure → 04:00 (clamped
 * from 03:35), 04:20, 04:50.
 *
 * Two deliberate exemptions:
 * - Previous-evening drop-offs for post-midnight flights (e.g. 00:35 flight
 *   → 22:05 the night before) are untouched; the floor only applies to
 *   same-day small-hours times.
 * - Clamping never moves a slot closer than 90 minutes to departure (the
 *   LATE offset). For a flight before 05:30 the clamp would breach that, so
 *   the original time is kept — no such flights exist at BOH today.
 *
 * Backend twin: DROP_OFF_FLOOR in backend/time_slots.py — keep in sync.
 */

export const DROP_OFF_FLOOR_MINUTES = 4 * 60
const LATE_OFFSET_MINUTES = 90

const SLOT_OFFSETS = [
  { id: '165', label: '2¾ hours before', minutes: 165 },
  { id: '120', label: '2 hours before', minutes: 120 },
  { id: '90', label: '1½ hours before', minutes: 90 },
]

const formatMinutes = (totalMinutes) => {
  if (totalMinutes < 0) totalMinutes += 24 * 60 // overnight: previous evening
  const hours = Math.floor(totalMinutes / 60) % 24
  const mins = totalMinutes % 60
  return `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}`
}

export function buildDropoffSlots(departureMinutes) {
  const slots = []
  const seenTimes = new Set()
  for (const { id, label, minutes } of SLOT_OFFSETS) {
    let slotMinutes = departureMinutes - minutes
    let slotLabel = label
    const sameDaySmallHours = slotMinutes >= 0 && slotMinutes < DROP_OFF_FLOOR_MINUTES
    const floorRespectsDeparture =
      DROP_OFF_FLOOR_MINUTES <= departureMinutes - LATE_OFFSET_MINUTES
    if (sameDaySmallHours && floorRespectsDeparture) {
      slotMinutes = DROP_OFF_FLOOR_MINUTES
      slotLabel = 'Earliest drop-off'
    }
    const time = formatMinutes(slotMinutes)
    if (seenTimes.has(time)) continue // two slots clamped to the same time
    seenTimes.add(time)
    slots.push({ id, label: slotLabel, time, available: 1, isLastSlot: false })
  }
  return slots
}
