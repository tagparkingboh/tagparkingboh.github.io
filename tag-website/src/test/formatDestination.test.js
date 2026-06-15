/**
 * Tests for the airport-name display formatter (utils/formatDestination.js).
 *
 * Rules (locked 2026-06-14):
 *   1. Strip a trailing parenthetical alias.
 *   2. Abbreviate "International Airport" → "Intl Airport".
 * Display-only — never applied to the booking-flow selectors or stored values.
 */
import { describe, it, expect } from 'vitest'
import { formatDestination } from '../utils/formatDestination'

describe('formatDestination', () => {
  it('strips a parenthetical alias', () => {
    expect(formatDestination('Madeira Airport (Cristiano Ronaldo International Airport)')).toBe('Madeira Airport')
    expect(formatDestination('Lanzarote Airport (César Manrique-Lanzarote Airport)')).toBe('Lanzarote Airport')
  })

  it('abbreviates International Airport to Intl Airport', () => {
    expect(formatDestination('Heraklion International Airport')).toBe('Heraklion Intl Airport')
    expect(formatDestination('Rhodes International Airport')).toBe('Rhodes Intl Airport')
    expect(formatDestination('Kraków John Paul II International Airport')).toBe('Kraków John Paul II Intl Airport')
  })

  it('leaves names without a parenthetical or "International Airport" unchanged', () => {
    expect(formatDestination('Faro Airport')).toBe('Faro Airport')
    expect(formatDestination('Málaga-Costa del Sol Airport')).toBe('Málaga-Costa del Sol Airport')
    expect(formatDestination('Sicily - Trapani-Birgi Airport')).toBe('Sicily - Trapani-Birgi Airport')
  })

  it('is null-safe and preserves falsy input for caller fallbacks', () => {
    expect(formatDestination(null)).toBe(null)
    expect(formatDestination(undefined)).toBe(undefined)
    expect(formatDestination('')).toBe('')
  })

  it('does not leave a double space behind after stripping', () => {
    expect(formatDestination('Madeira Airport (X)')).toBe('Madeira Airport')
    expect(formatDestination('Madeira Airport (X) Terminal')).toBe('Madeira Airport Terminal')
  })
})
