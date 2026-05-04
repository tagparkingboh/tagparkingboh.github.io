/**
 * Tests for src/dvlaCompliance.js — FE mirror of backend/dvla_compliance.py.
 *
 * Locks the FE rendering rules: which DVLA strings paint green, which paint
 * red, and which trigger the inline alert badge on the Admin booking detail
 * vehicle row. HUEB matrix per backend SPEC.md.
 */
import { describe, it, expect } from 'vitest'
import {
  taxStatusClass,
  motStatusClass,
  shouldShowAlert,
  formatIsoDateUk,
} from '../dvlaCompliance'

describe('taxStatusClass', () => {
  // Happy: only "Taxed" is green
  it('returns ok for "Taxed"', () => {
    expect(taxStatusClass('Taxed')).toBe('ok')
  })

  // Unhappy: every locked alert value paints red
  it.each([
    ['Untaxed'],
    ['SORN'],
    ['Not Taxed for on Road Use'],
  ])('returns alert for "%s"', (value) => {
    expect(taxStatusClass(value)).toBe('alert')
  })

  // Edge: missing/null/undefined → unknown (grey)
  it('returns unknown for null', () => {
    expect(taxStatusClass(null)).toBe('unknown')
  })

  it('returns unknown for undefined', () => {
    expect(taxStatusClass(undefined)).toBe('unknown')
  })

  it('returns unknown for "Could not verify" sentinel', () => {
    expect(taxStatusClass('Could not verify')).toBe('unknown')
  })

  // Boundary: case-sensitive — DVLA strings are verbatim
  it('is case-sensitive — "TAXED" is not ok', () => {
    expect(taxStatusClass('TAXED')).toBe('unknown')
  })

  it('is case-sensitive — "untaxed" is not alert', () => {
    expect(taxStatusClass('untaxed')).toBe('unknown')
  })

  // Boundary: unknown DVLA values default to unknown, not alert
  it('returns unknown for any unrecognised string', () => {
    expect(taxStatusClass('Some Future DVLA Value')).toBe('unknown')
  })
})

describe('motStatusClass', () => {
  // Happy
  it('returns ok for "Valid"', () => {
    expect(motStatusClass('Valid')).toBe('ok')
  })

  // Unhappy: every locked alert value paints red
  it.each([
    ['Not valid'],
    ['No results returned'],
  ])('returns alert for "%s"', (value) => {
    expect(motStatusClass(value)).toBe('alert')
  })

  // Edge: "No details held by DVLA" is NOT alertable — it's how DVLA
  // reports MOT-exempt cars under 3 years old. Renders grey, not red.
  it('returns unknown for "No details held by DVLA"', () => {
    expect(motStatusClass('No details held by DVLA')).toBe('unknown')
  })

  // Edge
  it('returns unknown for null', () => {
    expect(motStatusClass(null)).toBe('unknown')
  })

  it('returns unknown for "Could not verify" sentinel', () => {
    expect(motStatusClass('Could not verify')).toBe('unknown')
  })

  // Boundary
  it('is case-sensitive — "VALID" is not ok', () => {
    expect(motStatusClass('VALID')).toBe('unknown')
  })

  it('returns unknown for unrecognised strings', () => {
    expect(motStatusClass('Brand new value')).toBe('unknown')
  })
})

describe('shouldShowAlert', () => {
  // Happy: no alert when both safe
  it('returns false when both safe', () => {
    expect(shouldShowAlert('Taxed', 'Valid')).toBe(false)
  })

  it('returns false when both null', () => {
    expect(shouldShowAlert(null, null)).toBe(false)
  })

  it('returns false when both "Could not verify"', () => {
    // Retry policy handles this — no admin badge.
    expect(shouldShowAlert('Could not verify', 'Could not verify')).toBe(false)
  })

  // Unhappy: tax-only alert triggers
  it('returns true when only tax alerts', () => {
    expect(shouldShowAlert('Untaxed', 'Valid')).toBe(true)
  })

  // Unhappy: mot-only alert triggers
  it('returns true when only mot alerts', () => {
    expect(shouldShowAlert('Taxed', 'Not valid')).toBe(true)
  })

  // Edge: both alert
  it('returns true when both alert', () => {
    expect(shouldShowAlert('SORN', 'Not valid')).toBe(true)
  })

  // Edge: "No details held by DVLA" alone does NOT trigger
  it('does not trigger for "No details held by DVLA" alone', () => {
    expect(shouldShowAlert('Taxed', 'No details held by DVLA')).toBe(false)
  })

  // Boundary: every alert-listed value individually triggers via shouldShowAlert
  it.each([
    ['Untaxed', 'Valid'],
    ['SORN', 'Valid'],
    ['Not Taxed for on Road Use', 'Valid'],
    ['Taxed', 'Not valid'],
    ['Taxed', 'No results returned'],
  ])('triggers alert for tax="%s" mot="%s"', (tax, mot) => {
    expect(shouldShowAlert(tax, mot)).toBe(true)
  })
})

describe('formatIsoDateUk', () => {
  // Happy
  it('formats DVLA "YYYY-MM-DD" as DD/MM/YYYY', () => {
    expect(formatIsoDateUk('2026-09-01')).toBe('01/09/2026')
  })

  it('handles date-time strings by ignoring the time portion', () => {
    expect(formatIsoDateUk('2026-09-01T12:34:56Z')).toBe('01/09/2026')
  })

  // Edge: null/undefined/empty
  it('returns empty string for null', () => {
    expect(formatIsoDateUk(null)).toBe('')
  })

  it('returns empty string for undefined', () => {
    expect(formatIsoDateUk(undefined)).toBe('')
  })

  it('returns empty string for empty string', () => {
    expect(formatIsoDateUk('')).toBe('')
  })

  // Edge: malformed input
  it('returns empty string for non-ISO strings', () => {
    expect(formatIsoDateUk('not a date')).toBe('')
  })

  it('returns empty string for partial dates', () => {
    expect(formatIsoDateUk('2026-09')).toBe('')
  })

  // Boundary: timezone safety — manual parse, no Date constructor.
  // A timezone-naive Date(string) on a UTC-behind machine could shift
  // 2026-01-01 → 2025-12-31. Confirm the formatter doesn't do that.
  it('does not shift the day across timezones', () => {
    expect(formatIsoDateUk('2026-01-01')).toBe('01/01/2026')
    expect(formatIsoDateUk('2026-12-31')).toBe('31/12/2026')
  })

  // Boundary: leading zero on single-digit day/month
  it('zero-pads single-digit day/month', () => {
    expect(formatIsoDateUk('2026-03-05')).toBe('05/03/2026')
  })
})
