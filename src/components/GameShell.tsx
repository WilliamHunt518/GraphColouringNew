import { useReducer, useEffect, useRef } from 'react'
import type { StudyConfig, MapViewState } from '../types'
import { buildInitialState, gameReducer } from '../store/gameReducer'
import PrimaryDisplay from './PrimaryDisplay'
import BetweenSession from './BetweenSession'
import SurveyModal from './SurveyModal'

const CHANNEL_NAME = 'sar-study'

interface Props {
  config: StudyConfig
}

export default function GameShell({ config }: Props) {
  const [state, dispatch] = useReducer(gameReducer, config, buildInitialState)
  const rafRef = useRef<number | null>(null)
  const channelRef = useRef<BroadcastChannel | null>(null)
  const lastBroadcastElapsed = useRef<number>(-1)
  const lastCopilotModalRef = useRef<typeof state.copilotModal>(null)

  // BroadcastChannel — open once, close on unmount; listen for map→primary actions
  useEffect(() => {
    const channel = new BroadcastChannel(CHANNEL_NAME)
    channelRef.current = channel
    channel.onmessage = (e: MessageEvent) => {
      if (e.data?._mapAction === 'TOGGLE_TASK_PRIORITY' && typeof e.data.taskId === 'string') {
        dispatch({ type: 'TOGGLE_TASK_PRIORITY', taskId: e.data.taskId })
      }
      if (e.data?._mapAction === 'REPRIORITISE_TOP' && typeof e.data.missionId === 'string' && typeof e.data.taskId === 'string') {
        dispatch({ type: 'REPRIORITISE_TASK', missionId: e.data.missionId, taskId: e.data.taskId, direction: 'top' })
      }
    }
    return () => { channel.close(); channelRef.current = null }
  }, [])

  // Broadcast map state ~10fps, or immediately when copilot modal changes
  useEffect(() => {
    if (!channelRef.current) return
    const copilotChanged = state.copilotModal !== lastCopilotModalRef.current
    if (!copilotChanged && Math.abs(state.elapsed - lastBroadcastElapsed.current) < 0.1 && state.elapsed !== 0) return
    lastBroadcastElapsed.current = state.elapsed
    lastCopilotModalRef.current = state.copilotModal
    const payload: MapViewState = {
      assets: state.assets,
      missions: state.missions,
      elapsed: state.elapsed,
      sessionNumber: state.sessionNumber,
      score: state.score,
      phase: state.phase,
      pendingBlueprints: state.pendingBlueprints,
      copilotMissionId: state.copilotModal?.missionId ?? null,
      priorityTaskIds:  state.copilotModal?.priorityTaskIds ?? [],
    }
    channelRef.current.postMessage(payload)
  }, [state.elapsed, state.assets, state.missions, state.score, state.phase, state.sessionNumber, state.pendingBlueprints, state.copilotModal])

  // Tick loop — only runs when actively playing
  useEffect(() => {
    if (state.phase !== 'playing') {
      if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = null }
      return
    }
    const tick = () => {
      dispatch({ type: 'TICK', nowMs: Date.now() })
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => { if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = null } }
  }, [state.phase])

  if (state.phase === 'playing') {
    return <PrimaryDisplay state={state} dispatch={dispatch} />
  }

  if (state.phase === 'survey') {
    return <SurveyModal state={state} dispatch={dispatch} />
  }

  if (state.phase === 'between') {
    return <BetweenSession state={state} dispatch={dispatch} />
  }

  if (state.phase === 'done') {
    const totalScore = state.completedSessionScores.reduce((a, b) => a + b, 0)

    function downloadData() {
      const payload = {
        participantId: config.participantId,
        condition: config.condition,
        complexity: config.complexity,
        seed: config.seed,
        epsilonCopilot: config.epsilonCopilot,
        epsilonMeta: config.epsilonMeta,
        sessionScores: state.completedSessionScores,
        totalScore,
        sessions: state.events,
      }
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `study_${config.participantId}_${config.condition}_${config.seed}.json`
      a.click()
      URL.revokeObjectURL(url)
    }

    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center p-6">
        <div className="bg-gray-900 rounded-2xl border border-gray-700 p-8 max-w-md w-full space-y-6 text-center">
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-widest mb-2">Study complete</p>
            <h2 className="text-2xl font-bold text-white">Thank you</h2>
            <p className="text-gray-400 text-sm mt-1">Please ask the researcher to download your data.</p>
          </div>

          <div className="bg-gray-800 rounded-xl p-4 space-y-2 text-left">
            {state.completedSessionScores.map((s, i) => (
              <div key={i} className="flex justify-between text-sm text-gray-400">
                <span>Session {i + 1}</span>
                <span className="text-white font-mono tabular-nums">{s} pts</span>
              </div>
            ))}
            <div className="flex justify-between text-sm font-bold text-white border-t border-gray-700 pt-2 mt-1">
              <span>Total</span>
              <span className="font-mono tabular-nums">{totalScore} pts</span>
            </div>
          </div>

          <div className="space-y-2 text-xs text-gray-600">
            <p>Participant: {config.participantId} · Condition: {config.condition} · Seed: {config.seed}</p>
          </div>

          <button
            onClick={downloadData}
            className="w-full py-3 bg-green-600 hover:bg-green-500 rounded-lg font-semibold text-white text-sm transition-colors"
          >
            Download Study Data
          </button>
        </div>
      </div>
    )
  }

  return null
}
