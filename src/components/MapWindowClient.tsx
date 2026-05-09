import { useState, useEffect, useRef } from 'react'
import type { MapViewState } from '../types'
import MapDisplay from './MapDisplay'

const CHANNEL_NAME = 'sar-study'

export default function MapWindowClient() {
  const [viewState, setViewState] = useState<MapViewState | null>(null)
  const channelRef = useRef<BroadcastChannel | null>(null)

  useEffect(() => {
    const channel = new BroadcastChannel(CHANNEL_NAME)
    channelRef.current = channel
    channel.onmessage = (e: MessageEvent) => {
      // Ignore action messages (from other map windows); only accept MapViewState payloads
      if (!e.data?._mapAction) setViewState(e.data as MapViewState)
    }
    return () => { channel.close(); channelRef.current = null }
  }, [])

  function handleToggleTaskPriority(taskId: string) {
    channelRef.current?.postMessage({ _mapAction: 'TOGGLE_TASK_PRIORITY', taskId })
  }

  function handleReprioritiseTop(missionId: string, taskId: string) {
    channelRef.current?.postMessage({ _mapAction: 'REPRIORITISE_TOP', missionId, taskId })
  }

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

  return <MapDisplay state={viewState} onToggleTaskPriority={handleToggleTaskPriority} onReprioritiseTop={handleReprioritiseTop} />
}
