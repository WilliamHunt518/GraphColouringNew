// ─── Per-window UI zoom ──────────────────────────────────────────────────────
// The primary window and the map window (?view=map) are the SAME origin, so the
// browser's own page-zoom is remembered per-origin and applies to BOTH windows at
// once — useless for a dual-monitor setup where one screen is high-DPI and needs
// scaling up independently.
//
// This applies CSS `zoom` to the document root instead, which is fully independent
// per window/tab. Initial value comes from `?zoom=` (handy to bake into the pasted
// map-window URL), else a per-view localStorage value, else 1. Adjustable via the
// on-screen ZoomControls or Ctrl +/-/0 (overriding the browser's own zoom).

const MIN = 0.5
const MAX = 2.5
const STEP = 0.1

let zoom = 1
const listeners = new Set<(z: number) => void>()

function viewKey(): string {
  return new URLSearchParams(window.location.search).get('view') === 'map' ? 'map' : 'primary'
}

function storageKey(): string {
  return `sar-zoom-${viewKey()}`
}

function clamp(z: number): number {
  return Math.min(MAX, Math.max(MIN, Math.round(z * 100) / 100))
}

function apply(z: number): void {
  // Drives the #root logical-viewport scale in index.css. We scale a logical
  // viewport (sized 100%/z) back up rather than using CSS `zoom`, so the
  // fit-to-viewport map layout stays fully visible instead of being clipped.
  document.documentElement.style.setProperty('--ui-zoom', String(z))
}

export function getZoom(): number { return zoom }
export const ZOOM_MIN = MIN
export const ZOOM_MAX = MAX

export function setZoom(z: number): void {
  zoom = clamp(z)
  apply(zoom)
  try { localStorage.setItem(storageKey(), String(zoom)) } catch { /* private mode */ }
  listeners.forEach(l => l(zoom))
}

export function nudgeZoom(delta: number): void { setZoom(zoom + delta) }
export function resetZoom(): void { setZoom(1) }
export const ZOOM_STEP = STEP

export function subscribeZoom(cb: (z: number) => void): () => void {
  listeners.add(cb)
  return () => { listeners.delete(cb) }
}

export function initWindowZoom(): void {
  const param = new URLSearchParams(window.location.search).get('zoom')
  const stored = localStorage.getItem(storageKey())
  const initial = clamp(param != null ? Number(param) : stored != null ? Number(stored) : 1)
  zoom = Number.isFinite(initial) ? initial : 1
  apply(zoom)

  window.addEventListener('keydown', (e) => {
    if (!e.ctrlKey || e.altKey || e.metaKey) return
    // Include '=' and numpad '+' so it works regardless of shift/layout.
    if (e.key === '=' || e.key === '+' || e.code === 'NumpadAdd') {
      e.preventDefault(); nudgeZoom(STEP)
    } else if (e.key === '-' || e.code === 'NumpadSubtract') {
      e.preventDefault(); nudgeZoom(-STEP)
    } else if (e.key === '0' || e.code === 'Numpad0') {
      e.preventDefault(); resetZoom()
    }
  })
}
