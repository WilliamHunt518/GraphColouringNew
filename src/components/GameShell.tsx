import { useReducer, useEffect, useRef, useState, useMemo } from 'react'

const LOG = true
import type { StudyConfig, GameState, MapViewState, FreePlayAchievement } from '../types'
import { buildInitialState, gameReducer, reserveCount, complexityForSession } from '../store/gameReducer'
import PrimaryDisplay from './PrimaryDisplay'
import BetweenSession from './BetweenSession'
import SurveyModal from './SurveyModal'
import DemographicsForm from './DemographicsForm'
import TutorialSummary from './TutorialSummary'
import Tutorial from './Tutorial'
import FreePlayOverlay from './FreePlayOverlay'
import { TUTORIAL_STEPS } from '../utils/tutorialSteps'

const FREE_PLAY_MIN = 300  // seconds — free play always runs at least this long
const FREE_PLAY_MAX = 480  // seconds — hard cap so slow finishers can still complete the checklist

const CHANNEL_NAME = 'sar-study'

interface Props {
  config: StudyConfig
}

export default function GameShell({ config }: Props) {
  const [state, dispatch] = useReducer(gameReducer, config, buildInitialState)
  const [showTutorial, setShowTutorial] = useState((config.tutorialMode ?? false) && !config.skipToFreePlay)
  const [tutorialStep, setTutorialStep] = useState(0)
  const [openMissionId, setOpenMissionId] = useState<string | null>(null)
  const [showFreePlay, setShowFreePlay] = useState(false)
  const [freePlayStartAt, setFreePlayStartAt] = useState<number | null>(null)
  const [freePlayEventStart, setFreePlayEventStart] = useState(0)
  const rafRef = useRef<number | null>(null)
  const channelRef = useRef<BroadcastChannel | null>(null)
  const lastBroadcastElapsed = useRef<number>(-1)
  const lastStrategicModalRef = useRef<typeof state.strategicModal>(null)
  const lastOpenMissionIdRef = useRef<string | null>(null)
  const prevPendingRef = useRef<Set<string>>(new Set())
  const lastTutorialRef = useRef<{ active: boolean; step: number }>({ active: false, step: -1 })
  const lastMissionSigRef = useRef<string>('')

  // Skip directly to free play when flag is set (testing shortcut)
  useEffect(() => {
    if (!config.skipToFreePlay) return
    setFreePlayEventStart(0)
    setShowFreePlay(true)
    setFreePlayStartAt(state.elapsed)
    dispatch({ type: 'FORCE_MISSION_ARRIVAL' })
    dispatch({ type: 'FORCE_MISSION_ARRIVAL' })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Warn before closing/reloading while a study session is in progress (data is in-memory only)
  useEffect(() => {
    if (state.phase === 'done') return
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [state.phase])

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
      if (d._mapAction === 'TACTICAL_SUGGEST' && typeof d.missionId === 'string') {
        dispatch({ type: 'TACTICAL_SUGGEST', missionId: d.missionId })
      }
      if (d._mapAction === 'TACTICAL_ASSIGN_CHANGED' && typeof d.missionId === 'string') {
        dispatch({ type: 'TACTICAL_ASSIGN_CHANGED', missionId: d.missionId, op: d.op,
          droneId: d.droneId, taskId: d.taskId ?? null, recoveryMode: !!d.recoveryMode })
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
        dispatch({ type: 'CONFIRM_FAILURE_RECOVERY', missionId: d.missionId, taskAssignments: d.taskAssignments, droneSequences: d.droneSequences })
      }
      if (d._mapAction === 'ABANDON_MISSION' && typeof d.missionId === 'string') {
        dispatch({ type: 'ABANDON_MISSION', missionId: d.missionId })
      }
      if (d._mapAction === 'REPRIORITISE_TOP' && typeof d.missionId === 'string' && typeof d.taskId === 'string') {
        dispatch({ type: 'REPRIORITISE_TASK', missionId: d.missionId, taskId: d.taskId, direction: 'top' })
      }
      if (d._mapAction === 'APPLY_STRATEGIC' && typeof d.missionId === 'string') {
        dispatch({ type: 'APPLY_STRATEGIC', missionId: d.missionId, source: d.source,
          strategyIndex: d.strategyIndex ?? null, manualAllocation: d.manualAllocation ?? null,
          editedFromStrategy: d.editedFromStrategy ?? null, strategyCardCount: d.strategyCardCount,
          manualBeforeCardsLoaded: d.manualBeforeCardsLoaded ?? null,
          cardsLoadedAtManualSwitch: d.cardsLoadedAtManualSwitch ?? null })
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
      complexities: Array.from({ length: config.numSessions }, (_, i) => complexityForSession(config, i + 1)),
      seed: config.seed,
      epsilonStrategic: config.agentErrorRate,
      epsilonTactical: config.epsilonTactical,
      demographics: state.demographics,
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

  // Free play achievement computation — only checks events that occurred after free play began
  const freePlayAchievements = useMemo<FreePlayAchievement[]>(() => {
    if (!showFreePlay) return []
    const evts = state.events.flat().slice(freePlayEventStart)
    return [
      { id: 'manual_alloc',      label: 'Perform a manual strategic allocation',
        done: evts.some(e => e.type === 'strategic_choice' && (e as any).choiceType === 'manual') },
      { id: 'agent_alloc',       label: 'Accept a Strategic Assistant strategy',
        done: evts.some(e => e.type === 'strategic_choice' && (e as any).choiceType !== 'manual') },
      { id: 'override_tactical', label: 'Override a tactical plan',
        done: evts.some(e => e.type === 'tactical_confirmed' && (e as any).modifiedFromAgentPlan) },
      { id: 'chain_drone',       label: 'Chain a drone through two tasks',
        done: evts.some(e => e.type === 'tactical_confirmed' && (e as any).chainingUsed) },
    ]
  }, [showFreePlay, state.events, freePlayEventStart])

  const freePlaySecondsLeft = freePlayStartAt !== null
    ? Math.max(0, FREE_PLAY_MAX - (state.elapsed - freePlayStartAt))
    : FREE_PLAY_MAX

  // Free play runs for a minimum of FREE_PLAY_MIN before checklist completion can end it.
  const freePlayMinElapsed = freePlayStartAt !== null && state.elapsed >= freePlayStartAt + FREE_PLAY_MIN

  // Auto-end free play when the hard cap is hit, OR the checklist is complete past the minimum
  useEffect(() => {
    if (!showFreePlay || freePlayStartAt === null) return
    const allDone = freePlayAchievements.every(a => a.done)
    const timedOut = state.elapsed >= freePlayStartAt + FREE_PLAY_MAX
    if (timedOut || (allDone && freePlayMinElapsed)) {
      setShowFreePlay(false)
      dispatch({ type: 'FORCE_SESSION_END' })
    }
  }, [showFreePlay, freePlayStartAt, freePlayAchievements, freePlayMinElapsed, state.elapsed, dispatch])

  // Broadcast map state ~10fps, or immediately when strategic modal / openMissionId / tutorial /
  // mission status changes (so allocate/deploy/reassign/failure transitions reach the map instantly).
  useEffect(() => {
    if (!channelRef.current) return
    const modalChanged   = state.strategicModal !== lastStrategicModalRef.current
    const openChanged    = openMissionId !== lastOpenMissionIdRef.current
    const tutChanged     = showTutorial !== lastTutorialRef.current.active || tutorialStep !== lastTutorialRef.current.step
    // Signature of the per-mission flags that drive the map window's view (status + pending flags).
    // These change only on real transitions, not every tick, so bypassing the throttle here is cheap.
    const missionSig = state.missions.map(m => `${m.id}:${m.status}:${m.tacticalPending ? 1 : 0}:${m.failureRecoveryPending ? 1 : 0}`).join('|')
    const missionSigChanged = missionSig !== lastMissionSigRef.current
    if (!modalChanged && !openChanged && !tutChanged && !missionSigChanged && Math.abs(state.elapsed - lastBroadcastElapsed.current) < 0.1 && state.elapsed !== 0) return

    LOG && console.log('[SHELL] broadcasting — openMissionId:', openMissionId)
    lastBroadcastElapsed.current = state.elapsed
    lastStrategicModalRef.current = state.strategicModal
    lastOpenMissionIdRef.current = openMissionId
    lastTutorialRef.current = { active: showTutorial, step: tutorialStep }
    lastMissionSigRef.current = missionSig

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
      tacticalMode: state.config.tacticalMode,
      reserve: reserveCount(state.assets, state.missions),
      strategicModal: state.strategicModal,
      openMissionId,
      tutorialActive: showTutorial,
      tutorialStep,
      freePlayActive: showFreePlay,
      freePlayAchievements,
      freePlaySecondsLeft,
      freePlayCanFinish: freePlayMinElapsed,
    }
    channelRef.current.postMessage(payload)
  }, [state.elapsed, state.assets, state.missions, state.score, state.phase, state.sessionNumber, state.pendingBlueprints, state.strategicModal, state.config.mode, openMissionId, showTutorial, tutorialStep, showFreePlay, freePlayAchievements, freePlaySecondsLeft])

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

  if (state.phase === 'demographics') {
    return <DemographicsForm state={state} dispatch={dispatch} />
  }

  if (state.phase === 'playing') {
    const tutorialForceManual = showTutorial && (TUTORIAL_STEPS[tutorialStep]?.forceManual ?? false)
    const tutorialForceAgent = showTutorial && (TUTORIAL_STEPS[tutorialStep]?.forceAgent ?? false)
    return (
      <>
        <PrimaryDisplay state={state} dispatch={dispatch} setOpenMissionId={setOpenMissionId} tutorialForceManual={tutorialForceManual} tutorialForceAgent={tutorialForceAgent} />
        {showTutorial && (
          <Tutorial
            state={state}
            dispatch={dispatch}
            step={tutorialStep}
            onStep={setTutorialStep}
            onComplete={() => {
              setShowTutorial(false)
              if (config.tutorialMode) {
                setFreePlayEventStart(state.events.flat().length)
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
            canFinish={freePlayMinElapsed}
            onSkip={() => { setShowFreePlay(false); dispatch({ type: 'FORCE_SESSION_END' }) }}
          />
        )}
      </>
    )
  }

  if (state.phase === 'survey') {
    // Tutorial sessions skip the workload/trust surveys — show a recap summary instead.
    if (config.tutorialMode) {
      return <TutorialSummary onFinish={() => window.location.assign('/')} />
    }
    return <SurveyModal state={state} dispatch={dispatch} />
  }

  if (state.phase === 'between') {
    return <BetweenSession state={state} dispatch={dispatch} />
  }

  if (state.phase === 'done') {
    return <DoneScreen state={state} config={config} />
  }

  return null
}

function DoneScreen({ state, config }: { state: GameState; config: StudyConfig }) {
  const totalScore = state.completedSessionScores.reduce((a, b) => a + b, 0)

  function buildPayload() {
    return {
      participantId: config.participantId,
      condition: config.condition,
      mode: config.mode,
      complexities: sessionComplexities,
      seed: config.seed,
      epsilonStrategic: config.agentErrorRate,
      epsilonTactical: config.epsilonTactical,
      demographics: state.demographics,
      sessionScores: state.completedSessionScores,
      totalScore,
      sessions: state.events,
    }
  }

  function downloadData() {
    const blob = new Blob([JSON.stringify(buildPayload(), null, 2)], { type: 'application/json' })
    const url  = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `study_${config.participantId}_${config.condition}_${config.seed}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  useEffect(() => { downloadData() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const complexityLabel: Record<string, string> = {
    balanced: 'Balanced', strategic: 'Strategic Heavy', tactical: 'Tactical Heavy', full: 'Full Spectrum', quick: 'Quick Test',
  }
  const numSessions = state.completedSessionScores.length
  const sessionComplexities = Array.from({ length: config.numSessions }, (_, i) => complexityForSession(config, i + 1))
  const complexitySummary = sessionComplexities.every(c => c === sessionComplexities[0])
    ? (complexityLabel[sessionComplexities[0]] ?? sessionComplexities[0])
    : sessionComplexities.map(c => complexityLabel[c] ?? c).join(' → ')

  return (
    <div className="min-h-full bg-gray-950 flex items-center justify-center p-6">
      <div className="bg-gray-900 rounded-2xl border border-gray-700 p-8 max-w-lg w-full space-y-6 text-center">
        <div>
          <div className="text-5xl mb-3">✓</div>
          <p className="text-xs text-green-400 uppercase tracking-widest mb-2 font-semibold">Study Complete</p>
          <h2 className="text-2xl font-bold text-white">All sessions finished</h2>
          <p className="text-gray-400 text-sm mt-2">
            You have completed all {numSessions} sessions
            {config.collectDemographics
              ? '.'
              : <> of the <span className="text-white font-semibold">{config.condition}</span> condition ({complexitySummary} complexity).</>}
          </p>
        </div>

        {/* Scenario info */}
        <div className="bg-gray-800/60 rounded-xl border border-gray-700 p-4 text-left space-y-1.5">
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Participant</span>
            <span className="text-white font-mono">{config.participantId}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Condition</span>
            <span className="text-white font-mono">{config.condition}</span>
          </div>
          {!config.collectDemographics && (
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Complexity</span>
              <span className="text-white font-mono">{complexitySummary}</span>
            </div>
          )}
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Seed</span>
            <span className="text-white font-mono">{config.seed}</span>
          </div>
        </div>

        {/* Session scores — hidden from participants to avoid biasing */}
        {!config.collectDemographics && (
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
        )}

        <p className="text-gray-500 text-sm">Please ask the researcher to confirm your data has been saved.</p>

        <div className="space-y-2">
          <button onClick={downloadData} className="w-full py-3 bg-green-600 hover:bg-green-500 rounded-lg font-semibold text-white text-sm transition-colors">
            Download Study Data
          </button>
          <button onClick={downloadData} className="w-full py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-gray-300 text-xs transition-colors">
            Download Again
          </button>
        </div>
      </div>
    </div>
  )
}
