import { useState, useEffect, useRef } from 'react'

const LOG = true
import type { MapViewState } from '../types'
import MapDisplay from './MapDisplay'
import TacticalTutorial from './TacticalTutorial'
import FreePlayOverlay from './FreePlayOverlay'
import ZoomControls from './ZoomControls'
import { TUTORIAL_STEPS } from '../utils/tutorialSteps'

const CHANNEL_NAME = 'sar-study'

export default function MapWindowClient() {
  const [viewState, setViewState] = useState<MapViewState | null>(null)
  const channelRef = useRef<BroadcastChannel | null>(null)

  useEffect(() => {
    const channel = new BroadcastChannel(CHANNEL_NAME)
    channelRef.current = channel
    let lastLoggedOpenId: string | null | undefined = undefined
    channel.onmessage = (e: MessageEvent) => {
      if (LOG) {
        const oid = e.data?.openMissionId
        if (e.data?._mapAction || oid !== lastLoggedOpenId) {
          console.log('[MAP CLIENT] message — openMissionId:', oid, 'isAction:', !!e.data?._mapAction)
          lastLoggedOpenId = oid
        }
      }
      if (e.data?._mapAction) return  // outgoing action echoes — ignore
      if (e.data?._tutorialAction) return  // tutorial back-channel — ignore
      setViewState(e.data as MapViewState)
    }
    return () => { channel.close(); channelRef.current = null }
  }, [])

  function handleReprioritiseTop(missionId: string, taskId: string) {
    channelRef.current?.postMessage({ _mapAction: 'REPRIORITISE_TOP', missionId, taskId })
  }

  function sendTutorialAction(action: 'NEXT' | 'BACK' | 'COMPLETE') {
    channelRef.current?.postMessage({ _tutorialAction: action })
  }

  if (!viewState) {
    return (
      <div className="h-full bg-gray-950 flex items-center justify-center">
        <div className="text-center space-y-3">
          <div className="text-gray-500 text-lg">Waiting for primary window…</div>
          <div className="text-gray-700 text-sm">Open the study in the main window, then start a session.</div>
        </div>
        <ZoomControls />
      </div>
    )
  }

  const showTacticalTutorial =
    viewState.tutorialActive &&
    (TUTORIAL_STEPS[viewState.tutorialStep]?.inMapWindow ?? false)

  return (
    <>
      <MapDisplay state={viewState} onReprioritiseTop={handleReprioritiseTop} />
      {showTacticalTutorial && (
        <TacticalTutorial
          state={viewState}
          step={viewState.tutorialStep}
          onNext={()     => sendTutorialAction('NEXT')}
          onBack={()     => sendTutorialAction('BACK')}
          onComplete={() => sendTutorialAction('COMPLETE')}
        />
      )}
      <ZoomControls />
      {viewState.freePlayActive && (
        <FreePlayOverlay
          achievements={viewState.freePlayAchievements}
          secondsLeft={viewState.freePlaySecondsLeft}
          canFinish={viewState.freePlayCanFinish}
          onSkip={() => {}}
          readOnly
        />
      )}
    </>
  )
}
