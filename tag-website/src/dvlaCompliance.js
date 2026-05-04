// DVLA compliance status semantics — FE mirror of backend/dvla_compliance.py.
// Locked 2026-05-03: which raw DVLA strings render green vs red, and which
// trigger the visual alert badge.

const TAX_OK = 'Taxed'
const MOT_OK = 'Valid'

const TAX_ALERT_VALUES = new Set([
  'Untaxed',
  'SORN',
  'Not Taxed for on Road Use',
])

const MOT_ALERT_VALUES = new Set([
  'Not valid',
  'No details held by DVLA',
  'No results returned',
])

// Returns 'ok' | 'alert' | 'unknown' for a taxStatus value.
// 'unknown' covers null, undefined, "Could not verify", and any DVLA value
// not in the locked enum (rather than alert on it — we'd rather miss an
// alert than spam on a DVLA spec change).
export function taxStatusClass(value) {
  if (value === TAX_OK) return 'ok'
  if (TAX_ALERT_VALUES.has(value)) return 'alert'
  return 'unknown'
}

export function motStatusClass(value) {
  if (value === MOT_OK) return 'ok'
  if (MOT_ALERT_VALUES.has(value)) return 'alert'
  return 'unknown'
}

// True if either status warrants showing the visual alert badge.
// Mirrors backend.dvla_compliance.should_alert().
export function shouldShowAlert(taxStatus, motStatus) {
  return (
    taxStatusClass(taxStatus) === 'alert' ||
    motStatusClass(motStatus) === 'alert'
  )
}
