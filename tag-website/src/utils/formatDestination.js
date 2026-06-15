/**
 * Display-only formatting for airport destination / origin names.
 *
 * This is a presentation transform for the operational roster/admin views —
 * NOT for the booking flow. The full canonical name is what gets stored on the
 * booking and shown in the airport selectors; this only shortens the long
 * names on the day-detail and shift cards so they stop wrapping.
 *
 * Rules (locked 2026-06-14):
 *   1. Strip a trailing parenthetical alias, e.g.
 *      "Madeira Airport (Cristiano Ronaldo International Airport)" → "Madeira Airport".
 *   2. Abbreviate "International Airport" → "Intl Airport".
 *
 * Pure, null-safe: returns the input unchanged when it's falsy so callers can
 * keep their own "Unknown" / "-" fallbacks.
 */
export function formatDestination(name) {
  if (!name) return name
  return name
    .replace(/\s*\([^)]*\)/g, '')              // drop parenthetical alias
    .replace(/\bInternational Airport\b/g, 'Intl Airport')
    .replace(/\s{2,}/g, ' ')                    // tidy any double space left behind
    .trim()
}
