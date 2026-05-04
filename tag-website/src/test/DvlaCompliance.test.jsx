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
    ['No details held by DVLA'],
    ['No results returned'],
  ])('returns alert for "%s"', (value) => {
    expect(motStatusClass(value)).toBe('alert')
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
    expect(shouldShowAlert('SORN', 'No details held by DVLA')).toBe(true)
  })

  // Boundary: every alert-listed value individually triggers via shouldShowAlert
  it.each([
    ['Untaxed', 'Valid'],
    ['SORN', 'Valid'],
    ['Not Taxed for on Road Use', 'Valid'],
    ['Taxed', 'Not valid'],
    ['Taxed', 'No details held by DVLA'],
    ['Taxed', 'No results returned'],
  ])('triggers alert for tax="%s" mot="%s"', (tax, mot) => {
    expect(shouldShowAlert(tax, mot)).toBe(true)
  })
})
