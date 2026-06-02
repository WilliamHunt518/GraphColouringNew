import { useReducer, useEffect, useRef, useState, useMemo } from 'react'

const LOG = true
import type { StudyConfig, MapViewState, FreePlayAchievement } from '../types'
import { buildInitialState, gameReducer, reserveCount } from '../store/gameReducer'
import PrimaryDisplay from './PrimaryDisplay'
import BetweenSession from './BetweenSession'
import SurveyModal from './SurveyModal'
import Tutorial from './Tutorial'
import FreePlayOverlay from './FreePlayOverlay'
import { TUTORIAL_STEPS } from '../utils/tutorialSteps'

const FREE_PLAY_MAX = 300  // seconds

const CHANNEL_NAME = 'sar-study'

type CallsignMode = 'id' | 'arthurian' | 'nato'

interface Props {
  config: StudyConfig
}

export default function GameShell({ config }: Props) {
  const [state, dispatch] = useReducer(gameReducer, config, buildInitialState)
  const [callsignMode, setCallsignMode] = useState<CallsignMode>('id')
  const [showTutorial, setShowTutorial] = useState(config.tutorialMode ?? false)
  const [tutorialStep, setTutorialStep] = useState(0)
  const [openMissionId, setOpenMissionId] = useState<string | null>(null)
  const [showFreePlay, setShowFreePlay] = useState(false)
  const [freePlayStartAt, setFreePlayStartAt] = useState<number | null>(null)
  const rafRef = useRef<number | null>(null)
  const channelRef = useRef<BroadcastChannel | null>(null)
  const lastBroadcastElapsed = useRef<number>(-1)
  const lastStrategicModalRef = useRef<typeof state.strategicModal>(null)
  const lastOpenMissionIdRef = useRef<string | null>(null)
  const prevPendingRef = useRef<Set<string>>(new Set())
  const lastTutorialRef = useRef<{ active: boolean; step: number }>({ active: false, step: -1 })

  // BroadcastChannel — open once, close on unmount; listen for map→primary actions
  useEffect(() => {
    const channel = new BroadcastChannel(CHANNEL_NAME)
    channelRef.current = channel
    channel.onmessage = (e: MessageEvent) => {
      const d = e.data
      // Tutorial navigation from map window
      if (d?._tutorialAction) {
        if (d._tutorialAction === 'NEXT')     setTutorialStep(s => Math.min(s + 1, TUTORIAL_STEPS.length - 1))
        if (d._tutorialAction === 'BACK')     setTutorialStep(s => Math.max(0, s - 1))
        if (d._tutorialAction === 'COMPLETE') setShowTutorial(false)
        return
      }
      if (!d?._mapAction) return
      if (d._mapAction === 'CONFIRM_TACTICAL' && typeof d.missionId === 'string') {
        dispatch({ type: 'CONFIRM_TACTICAL', missionId: d.missionId, taskAssignments: d.taskAssignments, droneSequences: d.droneSequences })
      }
      if (d._mapAction === 'OVERRIDE_TACTICAL' && typeof d.missionId === 'string') {
        dispatch({ type: 'OVERRIDE_TACTICAL', missionId: d.missionId })
      }
      if (d._mapAction === 'ACCEPT_RECOVERY' && typeof d.missionId === 'string' && typeof d.recoveryType === 'string') {
        dispatch({ type: 'ACCEPT_RECOVERY', missionId: d.missionId, recoveryType: d.recoveryType })
      }
      if (d._mapAction === 'APPLY_MANUAL_RECOVERY' && typeof d.missionId === 'string') {
        dispatch({ type: 'APPLY_MANUAL_RECOVERY', missionId: d.missionId, taskId: d.taskId, newAssetId: d.newAssetId })
      }
      if (d._mapAction === 'CONFIRM_FAILURE_RECOVERY' && typeof d.missionId === 'string') {
        dispatch({ type: 'CONFIRM_FAILURE_RECOVERY', missionId: d.missionId, taskAssignments: d.taskAssignments })
      }
      if (d._mapAction === 'ABANDON_MISSION' && typeof d.missionId === 'string') {
        dispatch({ type: 'ABANDON_MISSION', missionId: d.missionId })
      }
      if (d._mapAction === 'REPRIORITISE_TOP' && typeof d.missionId === 'string' && typeof d.taskId === 'string') {
        dispatch({ type: 'REPRIORITISE_TASK', missionId: d.missionId, taskId: d.taskId, direction: 'top' })
      }
      if (d._mapAction === 'APPLY_STRATEGIC' && typeof d.missionId === 'string') {
        dispatch({ type: 'APPLY_STRATEGIC', missionId: d.missionId, source: d.source,
          strategyIndex: d.strategyIndex ?? null, manualAllocation: d.manualAllocation ?? null })
      }
      if (d._mapAction === 'CLOSE_STRATEGIC') {
        dispatch({ type: 'CLOSE_STRATEGIC' })
      }
    }
    return () => { channel.close(); channelRef.current = null }
  }, [])

  // Autosave to localStorage at each session boundary
  useEffect(() => {
    if (state.phase !== 'survey' && state.phase !== 'done') return
    const payload = {
      participantId: config.participantId,
      condition: config.condition,
      mode: config.mode,
      complexity: config.complexity,
      seed: config.seed,
      epsilonStrategic: config.agentErrorRate,
      epsilonTactical: config.epsilonTactical,
      sessionScores: state.completedSessionScores,
      sessions: state.events,
    }
    try {
      localStorage.setItem(`sar_backup_${config.participantId}_${config.seed}`, JSON.stringify(payload))
    } catch { /* storage quota exceeded — ignore */ }
  }, [state.phase, state.sessionNumber])

  // Auto-clear openMissionId when the mission leaves the pending pool
  useEffect(() => {
    const allPending = new Set(state.missions.filter(m => m.failureRecoveryPending || (m.tacticalPending && !!m.pendingAllocation)).map(m => m.id))
    setOpenMissionId(prev => {
      if (prev && prevPendingRef.current.has(prev) && !allPending.has(prev)) {
        LOG && console.log('[SHELL] auto-clear: openMissionId → null (was:', prev, ')')
        return null
      }
      return prev
    })
    prevPendingRef.current = allPending
  }, [state.missions])

  // Free play achievement computation
  const freePlayAchievements = useMemo<FreePlayAchievement[]>(() => {
    if (!showFreePlay) return []
    const evts = state.events.flat()
    return [
      { id: 'manual_alloc',      label: 'Perform a manual strategic allocation',
        done: evts.some(e => e.type === 'strategic_choice' && (e as any).choiceType === 'manual') },
      { id: 'agent_alloc',       label: 'Accept a Strategic Agent strategy',
        done: evts.some(e => e.type === 'strategic_choice' && (e as any).choiceType !== 'manual') },
      { id: 'override_tactical', label: 'Override a tactical plan',
        done: evts.some(e => e.type === 'tactical_confirmed' && (e as any).modifiedFromAgentPlan) },
      { id: 'chain_drone',       label: 'Chain a drone through two tasks',
        done: evts.some(e => e.type === 'tactical_confirmed' && (e as any).chainingUsed) },
    ]
  }, [showFreePlay, state.events])

  const freePlaySecondsLeft = freePlayStartAt !== null
    ? Math.max(0, FREE_PLAY_MAX - (state.elapsed - freePlayStartAt))
    : FREE_PLAY_MAX

  // Auto-end free play when all achieved OR timed out
  useEffect(() => {
    if (!showFreePlay || freePlayStartAt === null) return
    const allDone = freePlayAchievements.every(a => a.done)
    const timedOut = state.elapsed >= freePlayStartAt + FREE_PLAY_MAX
    if (allDone || timedOut) {
      setShowFreePlay(false)
      dispatch({ type: 'FORCE_SESSION_END' })
    }
  }, [showFreePlay, freePlayStartAt, freePlayAchievements, state.elapsed, dispatch])

  // Broadcast map state ~10fps, or immediately when strategic modal / openMissionId / tutorial changes
  useEffect(() => {
    if (!channelRef.current) return
    const modalChanged   = state.strategicModal !== lastStrategicModalRef.current
    const openChanged    = openMissionId !== lastOpenMissionIdRef.current
    const tutChanged     = showTutorial !== lastTutorialRef.current.active || tutorialStep !== lastTutorialRef.current.step
    if (!modalChanged && !openChanged && !tutChanged && Math.abs(state.elapsed - lastBroadcastElapsed.current) < 0.1 && state.elapsed !== 0) return

    LOG && console.log('[SHELL] broadcasting — openMissionId:', openMissionId)
    lastBroadcastElapsed.current = state.elapsed
    lastStrategicModalRef.current = state.strategicModal
    lastOpenMissionIdRef.current = openMissionId
    lastTutorialRef.current = { active: showTutorial, step: tutorialStep }

    const payload: MapViewState = {
      assets: state.assets,
      missions: state.missions,
      elapsed: state.elapsed,
      sessionNumber: state.sessionNumber,
      numSessions: state.config.numSessions,
      score: state.score,
      penaltyAccrued: state.penaltyAccrued,
      phase: state.phase,
      pendingBlueprints: state.pendingBlueprints,
      mode: state.config.mode,
      reserve: reserveCount(state.assets),
      callsignMode,
      strategicModal: state.strategicModal,
      openMissionId,
      tutorialActive: showTutorial,
      tutorialStep,
      freePlayActive: showFreePlay,
      freePlayAchievements,
      freePlaySecondsLeft,
    }
    channelRef.current.postMessage(payload)
  }, [state.elapsed, state.assets, state.missions, state.score, state.phase, state.sessionNumber, state.pendingBlueprints, state.strategicModal, state.config.mode, callsignMode, openMissionId, showTutorial, tutorialStep, showFreePlay, freePlayAchievements, freePlaySecondsLeft])

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
    const tutorialForceManual = showTutorial && (TUTORIAL_STEPS[tutorialStep]?.forceManual ?? false)
    return (
      <>
        <PrimaryDisplay state={state} dispatch={dispatch} callsignMode={callsignMode} setCallsignMode={setCallsignMode} setOpenMissionId={setOpenMissionId} tutorialForceManual={tutorialForceManual} />
        {showTutorial && (
          <Tutorial
            state={state}
            dispatch={dispatch}
            step={tutorialStep}
            onStep={setTutorialStep}
            onComplete={() => {
              setShowTutorial(false)
              if (config.tutorialMode) {
                setShowFreePlay(true)
                setFreePlayStartAt(state.elapsed)
                dispatch({ type: 'FORCE_MISSION_ARRIVAL' })
                dispatch({ type: 'FORCE_MISSION_ARRIVAL' })
              }
            }}
          />
        )}
        {showFreePlay && config.tutorialMode && (
          <FreePlayOverlay
            achievements={freePlayAchievements}
            secondsLeft={freePlaySecondsLeft}
            onSkip={() => { setShowFreePlay(false); dispatch({ type: 'FORCE_SESSION_END' }) }}
          />
        )}
      </>
    )
  }

  if (state.phase === 'survey') {
    return <SurveyModal state={state} dispatch={dispatch} />
  }

  if (state.phase === 'between') {
    return <BetweenSession state={state} dispatch={dispatch} />
  }

  if (state.phase === 'done') {
    const totalScore = state.completedSessionScores.reduce((a, b) => a + b, 0)

    function buildPayload() {
      return {
        participantId: config.participantId,
        condition: config.condition,
        mode: config.mode,
        complexity: config.complexity,
        seed: config.seed,
        epsilonStrategic: config.agentErrorRate,
        epsilonTactical: config.epsilonTactical,
        sessionScores: state.completedSessionScores,
        totalScore,
        sessions: state.events,
      }
    }

    function downloadData() {
      const blob = new Blob([JSON.stringify(buildPayload(), null, 2)], { type: 'application/json' })
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
          <button onClick={downloadData} className="w-full py-3 bg-green-600 hover:bg-green-500 rounded-lg font-semibold text-white text-sm transition-colors">
            Download Study Data
          </button>
        </div>
      </div>
    )
  }

  return null
}
