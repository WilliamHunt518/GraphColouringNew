import { useState, useEffect } from 'react'
import type { MapViewState } from '../types'
import MapDisplay from './MapDisplay'

const CHANNEL_NAME = 'sar-study'

export default function MapWindowClient() {
  const [viewState, setViewState] = useState<MapViewState | null>(null)

  useEffect(() => {
    const channel = new BroadcastChannel(CHANNEL_NAME)
    channel.onmessage = (e: MessageEvent<MapViewState>) => {
      setViewState(e.data)
    }
    return () => channel.close()
  }, [])

  if (!viewState) {
    return (
      <div className="h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-center space-y-3">
          <div className="text-gray-500 text-lg">Waiting for primary window…</div>
          <div className="text-gray-700 text-sm">Open the study in the main window, then start a session.</div>
        </div>
      </div>
    )
  }

  return <MapDisplay state={viewState} />
}
