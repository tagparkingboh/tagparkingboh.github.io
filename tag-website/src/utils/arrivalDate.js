// Resolve the canonical landing date for a booking, with a rollover-aware
// fallback for legacy rows where flight_arrival_date is NULL.
//
// New rows (created from 2026-05-20 onward) have flight_arrival_date set
// explicitly at create-payment time, so this just returns it. Legacy rows
// fall back to pickup_date — minus one day when arrival_time + 30 min
// crossed midnight, because the +30 rollover at create-payment pushed
// pickup_date past the actual landing day for late-night arrivals.
//
// Without the rollover-aware step, an admin opening Edit Booking on a
// 23:30+ legacy row and clicking Save without touching the date would
// silently persist pickup_date as flight_arrival_date — wrong by one day
// (see TAG-MNF73277 staging incident 2026-05-21).
export const resolveArrivalDate = (booking) => {
  if (booking?.flight_arrival_date) return booking.flight_arrival_date
  if (!booking?.pickup_date) return null

  const t = booking.flight_arrival_time
  if (typeof t === 'string' && /^\d{2}:\d{2}/.test(t)) {
    const [h, m] = t.split(':').map(Number)
    // arrival_time + 30 ≥ 24:00 means the +30-min rollover at create-payment
    // pushed pickup_date past the actual landing day → walk one day back.
    if (h * 60 + m + 30 >= 1440) {
      const [yy, mm, dd] = booking.pickup_date.split('-').map(Number)
      const d = new Date(yy, mm - 1, dd - 1)
      const pad = (n) => String(n).padStart(2, '0')
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
    }
  }
  // Daytime arrival or unknown arrival_time → pickup_date is the landing day.
  return booking.pickup_date
}
