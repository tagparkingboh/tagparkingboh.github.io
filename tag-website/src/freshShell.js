/* Self-healing for stale SPA shells.
 *
 * The site is served by Railway's static host, which sends no Cache-Control
 * on the shell (/, /employee, /admin/...). Mobile browsers heuristically
 * cache it for days, so phones keep loading old JS bundles and show stale
 * views until someone manually clears site data.
 *
 * Each build embeds __BUILD_ID__ (vite define) and ships dist/version.json
 * with the same value. On load and whenever the tab becomes visible again,
 * we fetch version.json (uncacheable) and force one reload when the server
 * has a newer build — the reload revalidates the shell via its ETag and
 * picks up the new bundles.
 */

const RELOAD_GUARD_KEY = 'tag-shell-reloaded-at'
const RELOAD_GUARD_MS = 60_000

const maybeReload = () => {
  let last = 0
  try {
    last = Number(sessionStorage.getItem(RELOAD_GUARD_KEY) || 0)
  } catch {
    // storage unavailable — still reload, the version gate limits repeats
  }
  if (Date.now() - last < RELOAD_GUARD_MS) return
  try {
    sessionStorage.setItem(RELOAD_GUARD_KEY, String(Date.now()))
  } catch {
    // ignore
  }
  window.location.reload()
}

const checkVersion = async () => {
  try {
    const res = await fetch('/version.json', { cache: 'no-store' })
    if (!res.ok) return // dev server / file missing — never reload on errors
    const data = await res.json()
    if (data?.buildId && typeof __BUILD_ID__ !== 'undefined' && data.buildId !== __BUILD_ID__) {
      maybeReload()
    }
  } catch {
    // offline or transient failure — leave the app alone
  }
}

export const installFreshShellGuard = () => {
  if (typeof window === 'undefined') return
  checkVersion()
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') checkVersion()
  })
  // If a deploy replaced hashed chunks a stale shell still references,
  // Vite surfaces it as a preload error — recover with one reload.
  window.addEventListener('vite:preloadError', (event) => {
    event.preventDefault()
    maybeReload()
  })
}
