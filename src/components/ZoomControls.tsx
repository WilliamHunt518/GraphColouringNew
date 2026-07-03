import { useEffect, useState } from 'react'
import { getZoom, subscribeZoom, nudgeZoom, resetZoom, ZOOM_STEP, ZOOM_MIN, ZOOM_MAX } from '../utils/windowZoom'

// Floating per-window zoom control. Independent of the browser's per-origin zoom,
// so the map window and primary window scale separately on a dual-monitor setup.
export default function ZoomControls() {
  const [zoom, setZoom] = useState(getZoom())
  useEffect(() => subscribeZoom(setZoom), [])

  const btn =
    'w-7 h-7 flex items-center justify-center rounded text-gray-200 text-lg leading-none ' +
    'hover:bg-gray-700 disabled:opacity-30 disabled:hover:bg-transparent select-none'

  return (
    <div className="fixed bottom-3 right-3 z-[60] flex items-center gap-0.5 rounded-lg
                    bg-gray-900/85 border border-gray-700 px-1 py-1 shadow-lg backdrop-blur-sm">
      <button
        className={btn}
        title="Zoom out (Ctrl −)"
        disabled={zoom <= ZOOM_MIN + 1e-6}
        onClick={() => nudgeZoom(-ZOOM_STEP)}
      >−</button>
      <button
        className="min-w-[3rem] text-center text-xs text-gray-300 tabular-nums hover:text-white select-none"
        title="Reset zoom (Ctrl 0)"
        onClick={resetZoom}
      >{Math.round(zoom * 100)}%</button>
      <button
        className={btn}
        title="Zoom in (Ctrl +)"
        disabled={zoom >= ZOOM_MAX - 1e-6}
        onClick={() => nudgeZoom(ZOOM_STEP)}
      >+</button>
    </div>
  )
}
