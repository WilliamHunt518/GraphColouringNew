import { useState, useRef, useEffect } from 'react'

const LOG = true
import type { GameState, Mission, Task, Asset, AssetType, MissionCategory, AssetRequirement, Strategy, StrategicModal } from '../types'
import type { GameAction } from '../store/actions'
import { reserveCount } from '../store/gameReducer'
import { downloadStudySnapshot } from '../utils/debugLog'
import { previewAllocation } from '../utils/copilot'
import { HUB, droneLabel, ASSET_TYPE_LABEL, CATEGORY_PENALTY_RATE, TASK_WEIGHT, CHARGE_INTERVAL, TASK_PRIMARY, TASK_SUBSTITUTE } from '../utils/missionGen'
import { CAT_ICON, TASK_ICON, DRONE_ICON } from '../utils/icons'
import type { TaskType } from '../types'

interface Props {
  state: GameState
  dispatch: (a: GameAction) => void
  setOpenMissionId: (id: string | null) => void
  tutorialForceManual?: boolean
  tutorialForceAgent?: boolean
}

// ─── Colour / label helpers ────────────────────────────────────────────────

const CAT_BADGE: Record<MissionCategory, string> = {
  A: 'bg-gray-700 text-gray-200',
  B: 'bg-blue-900/80 text-blue-200',
  C: 'bg-amber-900/80 text-amber-200',
  D: 'bg-orange-900/80 text-orange-200',
  E: 'bg-red-900/80 text-red-200',
}

const CAT_NAME: Record<MissionCategory, string> = {
  A: 'Routine',
  B: 'Moderate',
  C: 'Significant',
  D: 'Critical',
  E: 'Mass Casualty',
}

const TASK_STATUS_STYLE: Record<Task['status'], string> = {
  pending:   'bg-gray-700 text-gray-400',
  traveling: 'bg-blue-800 text-blue-100 animate-pulse',
  executing: 'bg-amber-700 text-amber-100 animate-pulse',
  completed: 'bg-green-800 text-green-100',
  failed:    'bg-red-900 text-red-300',
}

const TASK_SHORT: Record<number, string> = { 1: 'Rcc', 2: 'Rcn', 3: 'Sup', 4: 'PSD', 5: 'S&S' }
const TASK_FULL:  Record<number, string> = { 1: 'Recce', 2: 'Recon', 3: 'Supply Drop', 4: 'Prec Supply Drop', 5: 'Search & Service' }

// Colored dots showing primary drone type composition
const TASK_DOTS: Record<number, AssetType[]> = {
  1: ['Blue'],
  2: ['Blue', 'Blue'],
  3: ['Red', 'Red', 'Green'],
  4: ['Red', 'Green', 'Green'],
  5: ['Blue', 'Red', 'Green'],
}

const ASSET_COLORS: Record<AssetType, string> = {
  Blue: 'text-blue-400', Red: 'text-red-400', Green: 'text-green-400',
}

const ASSET_DOT_COLOR: Record<AssetType, string> = {
  Blue: 'bg-blue-400', Red: 'bg-red-400', Green: 'bg-green-400',
}



function fmtTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}m ${s.toString().padStart(2, '0')}s`
}

// ─── Penalty helpers ──────────────────────────────────────────────────────

function missionPenaltyAccrued(mission: Mission, elapsed: number): number {
  const totalWeight = mission.tasks.reduce((s, t) => s + TASK_WEIGHT[t.type], 0)
  if (totalWeight === 0) return 0
  const rate = CATEGORY_PENALTY_RATE[mission.category]
  let penalty = 0
  for (const t of mission.tasks) {
    const taskRate = rate * TASK_WEIGHT[t.type] / totalWeight
    const endTime = t.completionTime ?? elapsed
    penalty += taskRate * Math.max(0, endTime - mission.arrivalTime)
  }
  return Math.round(penalty)
}

type UrgencyLevel = 'none' | 'low' | 'med' | 'high'

function penaltyUrgency(penaltyPts: number): UrgencyLevel {
  if (penaltyPts < 20)  return 'none'
  if (penaltyPts < 50)  return 'low'
  if (penaltyPts < 100) return 'med'
  return 'high'
}

// ─── Top-level ────────────────────────────────────────────────────────────

export default function PrimaryDisplay({ state, dispatch, setOpenMissionId, tutorialForceManual, tutorialForceAgent }: Props) {
  const [sortMode, setSortMode] = useState<'arrival' | 'score'>('arrival')
  const queued  = state.missions.filter(m => m.status === 'queued')
  const active  = state.missions.filter(m => m.status === 'active')
  const done    = state.missions.filter(m => m.status === 'completed' || m.status === 'failed' || m.status === 'abandoned')
  const reserve = reserveCount(state.assets)

  function sortByScore(missions: Mission[]) {
    const totalPts = (m: Mission) => m.tasks.reduce((sum, t) => sum + TASK_WEIGHT[t.type], 0)
    return [...missions].sort((a, b) => totalPts(b) - totalPts(a))
  }
  const sortedQueued = sortMode === 'score' ? sortByScore(queued) : queued
  const sortedActive = sortMode === 'score' ? sortByScore(active) : active

  const completionPoints = state.missions.flatMap(m => m.tasks)
    .filter(t => t.status === 'completed')
    .reduce((sum, t) => sum + TASK_WEIGHT[t.type], 0)

  return (
    <div className="h-screen flex flex-col bg-gray-950 text-white overflow-hidden">
      {/* Header */}
      <header data-tutorial="header" className="flex items-center justify-between px-5 py-2.5 bg-gray-900 border-b border-gray-800 flex-none">
        <div className="flex items-center gap-4">
          <span className="font-bold text-white">SAR Command</span>
          <span className="text-xs text-gray-400 uppercase tracking-wide">
            Session {state.sessionNumber} / {state.config.numSessions}
          </span>
          <span data-tutorial="mode-badge" className={`text-xs px-2 py-0.5 rounded border uppercase tracking-wide ${
            state.config.mode === 'agent'
              ? 'bg-purple-900/60 text-purple-300 border-purple-700/50'
              : 'bg-gray-800 text-gray-400 border-gray-700'
          }`}>
            {state.config.mode === 'agent' ? 'Assistant Mode' : 'Manual'}
          </span>
          {state.config.testingMode && (
            <span className="text-xs px-2 py-0.5 rounded border uppercase tracking-wide bg-orange-900/60 text-orange-300 border-orange-700/50 font-bold">
              TEST
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-sm">
          {state.config.testingMode && (
            <>
              <button
                onClick={() => dispatch({ type: 'FORCE_MISSION_ARRIVAL' })}
                disabled={state.pendingBlueprints.length === 0}
                className="text-xs px-2.5 py-1 rounded bg-orange-900/50 hover:bg-orange-800/60 text-orange-300 border border-orange-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                title="Spawn next mission immediately"
              >
                New Mission
              </button>
              <button
                onClick={() => dispatch({ type: 'FORCE_DRONE_FAILURE' })}
                disabled={!state.missions.some(m =>
                  m.status === 'active' && !m.failureRecoveryPending &&
                  state.assets.some(a => a.currentMissionId === m.id && a.status === 'deployed' && a.currentTaskId)
                )}
                className="text-xs px-2.5 py-1 rounded bg-red-900/50 hover:bg-red-800/60 text-red-300 border border-red-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                title="Force a drone failure on an active mission"
              >
                Force Failure
              </button>
              <button
                onClick={() => dispatch({ type: 'END_STUDY' })}
                className="text-xs px-2.5 py-1 rounded bg-gray-700/80 hover:bg-gray-600/80 text-gray-300 border border-gray-600 transition-colors"
                title="Skip straight to the end screen"
              >
                End Study
              </button>
            </>
          )}
          <span data-tutorial="timer" className="font-mono text-amber-400 font-bold">{formatCountdown(state.elapsed, state.sessionDuration)}</span>
          <span data-tutorial="score" className="text-gray-400 flex items-baseline gap-1.5">
            <span>Score: <span className="text-white font-bold">{state.score}</span></span>
            <span className="text-xs text-green-500" title="Completion points earned">+{completionPoints}</span>
            <span className="text-xs text-red-400" title="Accumulated wait penalty">−{state.penaltyAccrued} pen</span>
          </span>
          <button
            data-tutorial="tactical-btn"
            onClick={() => window.open('/?view=map', 'sar-tactical')}
            className="text-xs px-2.5 py-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700 transition-colors"
          >
            Tactical →
          </button>
          <button
            onClick={() => downloadStudySnapshot(state)}
            className="text-xs px-2.5 py-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-500 border border-gray-700 transition-colors"
            title="Download mid-session study snapshot (JSON)"
          >
            Snapshot
          </button>
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: compact reserve strip + mission list */}
        <div className="w-[440px] flex-none flex flex-col overflow-hidden border-r border-gray-800">
          {/* Compact reserve strip */}
          <div data-tutorial="reserve-strip" className="flex-none px-4 py-2.5 border-b border-gray-800 bg-gray-900/50 flex items-center gap-4 flex-wrap">
            <span className="text-xs text-gray-500 uppercase tracking-wider">Reserve</span>
            {(['Blue', 'Red', 'Green'] as AssetType[]).map(type => {
              const avail = reserve[type]
              const total = state.assets.filter(a => a.type === type).length
              const returning = state.assets.filter(a => a.type === type && a.status === 'returning').length
              const out = total - avail
              return (
                <span key={type} className={`flex items-center gap-1.5 text-base ${ASSET_COLORS[type]}`}>
                  <img src={DRONE_ICON[type]} className="w-6 h-6 flex-none" alt="" />
                  <span className="font-mono font-bold">{avail}</span>
                  <span className="text-gray-600 text-xs">/{total} ({out} out{returning > 0 ? `, ${returning} rtg` : ''})</span>
                </span>
              )
            })}
            {state.categoryForecast && (
              <span className="ml-auto text-[10px] text-gray-600">
                {(['A', 'B', 'C', 'D', 'E'] as const)
                  .filter(c => state.categoryForecast[c] > 0.1)
                  .map(c => `${c}${Math.round(state.categoryForecast[c] * 100)}%`)
                  .join(' ')}
              </span>
            )}
          </div>

          {/* Scrollable mission list */}
          <div data-tutorial="mission-list" className="flex-1 overflow-y-auto p-3 min-w-0 space-y-2">
            {(queued.length > 0 || active.length > 0) && (
              <div className="flex items-center justify-end mb-1">
                <button
                  onClick={() => setSortMode(s => s === 'arrival' ? 'score' : 'arrival')}
                  className={`text-xs px-2 py-0.5 rounded border transition-colors ${
                    sortMode === 'score'
                      ? 'bg-blue-900/30 text-blue-400 border-blue-700'
                      : 'bg-gray-800 text-gray-400 border-gray-700 hover:text-gray-200'
                  }`}
                >
                  Sort: {sortMode === 'arrival' ? 'Arrival ↓' : 'Score ↓'}
                </button>
              </div>
            )}
            {queued.length > 0 && (
              <section>
                <SectionLabel text="Incoming — awaiting allocation" dot="bg-amber-400" />
                {sortedQueued.map((m, i) => (
                  <MissionCard key={m.id} mission={m} state={state} dispatch={dispatch} isTutorialFirst={i === 0} tutorialForceManual={i === 0 ? tutorialForceManual : undefined} tutorialForceAgent={i === 0 ? tutorialForceAgent : undefined} />
                ))}
              </section>
            )}
            {active.length > 0 && (
              <section className={queued.length > 0 ? 'mt-4' : ''}>
                <SectionLabel text="Active missions" dot="bg-blue-400" />
                {sortedActive.map(m => (
                  <MissionCard key={m.id} mission={m} state={state} dispatch={dispatch} />
                ))}
              </section>
            )}
            {done.length > 0 && (
              <section className="mt-4 opacity-60">
                <SectionLabel text="Completed" dot="bg-gray-500" />
                {done.slice(-6).map(m => (
                  <MissionCard key={m.id} mission={m} state={state} dispatch={dispatch} />
                ))}
              </section>
            )}
            {queued.length === 0 && active.length === 0 && done.length === 0 && (
              <div className="flex flex-col items-center justify-center h-48 text-gray-600">
                <p className="text-sm">No missions yet</p>
                <p className="text-xs mt-1">Missions will appear here as they arrive</p>
              </div>
            )}
          </div>
        </div>

        {/* Right: embedded operational map */}
        <div data-tutorial="embedded-map" className="flex-1 relative overflow-hidden bg-gray-950">
          <EmbeddedOperationalMap state={state} dispatch={dispatch} setOpenMissionId={setOpenMissionId} />
        </div>
      </div>
    </div>
  )
}

// ─── Section label ────────────────────────────────────────────────────────

function SectionLabel({ text, dot }: { text: string; dot: string }) {
  return (
    <div className="flex items-center gap-2 mb-2 px-1">
      <span className={`w-1.5 h-1.5 rounded-full ${dot} flex-none`} />
      <span className="text-xs text-gray-500 uppercase tracking-wider">{text}</span>
    </div>
  )
}

// ─── Mission card ─────────────────────────────────────────────────────────

function MissionCard({ mission, state, dispatch, isTutorialFirst, tutorialForceManual, tutorialForceAgent }: { mission: Mission; state: GameState; dispatch: (a: GameAction) => void; isTutorialFirst?: boolean; tutorialForceManual?: boolean; tutorialForceAgent?: boolean }) {
  const isQueued    = mission.status === 'queued'
  const isActive    = mission.status === 'active'
  const isCompleted = mission.status === 'completed'
  const isFailed    = mission.status === 'failed'
  const isAllocating = state.strategicModal?.missionId === mission.id

  const completedTasks = mission.tasks.filter(t => t.status === 'completed').length
  const totalTasks = mission.tasks.length
  const deployedHere = state.assets.filter(a => a.currentMissionId === mission.id && a.status === 'deployed')

  const activeTaskIds = new Set(
    deployedHere.map(a => a.currentTaskId).filter((id): id is string => id !== null)
  )
  const doingCount = mission.tasks.filter(t => activeTaskIds.has(t.id)).length
  const chainQueuedCount = mission.tasks.filter(t =>
    t.status === 'traveling' && !activeTaskIds.has(t.id) && t.assignedAssetIds.length > 0
  ).length

  const penaltyPts = missionPenaltyAccrued(mission, state.elapsed)
  const urgency = (isQueued || isActive) ? penaltyUrgency(penaltyPts) : 'none'

  const borderColor = isAllocating ? 'border-blue-500'
    : mission.failureRecoveryPending ? 'border-red-600'
    : mission.tacticalPending ? 'border-yellow-500'
    : isQueued  ? 'border-amber-500'
    : isActive  ? 'border-blue-700'
    : 'border-gray-700'
  const bgColor = isAllocating ? 'bg-blue-950/20'
    : mission.failureRecoveryPending ? 'bg-red-950/20'
    : mission.tacticalPending ? 'bg-yellow-950/10'
    : isQueued  ? 'bg-amber-950/20'
    : isActive  ? 'bg-blue-950/10'
    : 'bg-gray-900/40'

  const eta = isActive
    ? Math.max(0, Math.max(...mission.tasks.map(t => t.completionTime ?? 0)) - state.elapsed)
    : null

  return (
    <div data-tutorial={isTutorialFirst ? 'first-mission-card' : undefined} className={`relative rounded-lg border-2 ${borderColor} ${bgColor} p-3 mb-2`}>
      {isQueued && !isAllocating && !mission.tacticalPending && (
        <div className="absolute inset-0 rounded-lg border-2 border-amber-400/70 animate-pulse pointer-events-none" />
      )}
      {/* Card header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-xs font-bold text-white">{mission.id}</span>
          <img src={CAT_ICON[mission.category]} className="w-5 h-5 flex-none" alt="" />
          <span className={`text-xs px-1.5 py-0.5 rounded font-bold ${CAT_BADGE[mission.category]}`}>
            {mission.category} · {CAT_NAME[mission.category]}
          </span>
          {isActive && (
            <span className="text-xs text-gray-400">
              {completedTasks}/{totalTasks}
              {doingCount > 0 && <> · <span className="text-blue-400">{doingCount} active</span></>}
              {chainQueuedCount > 0 && <> · <span className="text-gray-500">{chainQueuedCount} queued</span></>}
            </span>
          )}
          {isCompleted && <span className="text-xs text-green-400">complete</span>}
          {isFailed && <span className="text-xs text-red-400">failed</span>}
        </div>
        <div className="flex items-center gap-2 flex-none">
          {isActive && eta !== null && (
            <span className="text-xs text-gray-400 font-mono">ETA {formatSeconds(eta)}</span>
          )}
          {isQueued && !isAllocating && !mission.tacticalPending && (
            <button
              data-tutorial={isTutorialFirst ? 'first-allocate-btn' : undefined}
              onClick={() => dispatch({ type: 'OPEN_STRATEGIC', missionId: mission.id })}
              className="px-3 py-1 bg-amber-600 hover:bg-amber-500 rounded text-xs font-semibold text-white transition-colors"
            >
              Allocate
            </button>
          )}
          {isAllocating && (
            <span className="text-xs text-blue-400 font-medium">Allocating…</span>
          )}
        </div>
      </div>

      {/* Drone failure banner */}
      {mission.failureRecoveryPending && (
        <div className="mb-2 px-2 py-1.5 bg-red-900/40 border border-red-700/50 rounded text-xs text-red-300 flex items-center gap-2">
          <span className="font-bold">DRONE FAILURE</span>
          {mission.failedDroneId && <span className="text-red-400">{mission.failedDroneId} lost</span>}
          <span className="text-gray-500">— recovery required</span>
        </div>
      )}

      {/* Tactical pending notice */}
      {mission.tacticalPending && !mission.failureRecoveryPending && (
        <div data-tutorial={isTutorialFirst ? 'first-tactical-pending' : undefined} className="mb-2 px-2 py-1 bg-yellow-900/30 border border-yellow-700/50 rounded text-xs text-yellow-300">
          Tactical allocation pending confirmation — review on map
        </div>
      )}

      {/* Task progress + penalty histogram */}
      <MissionProgressSection mission={mission} elapsed={state.elapsed} urgency={urgency} activeTaskIds={activeTaskIds} isActive={isActive} greedy={state.config.tacticalMode === 'greedy'} tutorialFirst={isTutorialFirst} />

      {/* Task plan — shows drone→task assignments after allocation */}
      {isActive && <TaskPlanPanel mission={mission} />}


      {/* Strategic allocation panel */}
      {isAllocating && state.strategicModal && (
        <StrategicPanel modal={state.strategicModal} state={state} dispatch={dispatch} isTutorialFirst={isTutorialFirst} tutorialForceManual={tutorialForceManual} tutorialForceAgent={tutorialForceAgent} />
      )}
    </div>
  )
}

// ─── Strategic panel ──────────────────────────────────────────────────────

function StrategicPanel({ modal, state, dispatch, isTutorialFirst, tutorialForceManual, tutorialForceAgent }: { modal: StrategicModal; state: GameState; dispatch: (a: GameAction) => void; isTutorialFirst?: boolean; tutorialForceManual?: boolean; tutorialForceAgent?: boolean }) {
  const isAgent = state.config.mode === 'agent'
  // Auto-enter manual mode when there are no agent strategies (depleted reserve)
  const [showManual, setShowManual] = useState(!isAgent || modal.strategies.length === 0)
  const [confirmCancel, setConfirmCancel] = useState(false)
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null)
  const [manualAlloc, setManualAlloc] = useState<AssetRequirement>(modal.manualAllocation ?? { Blue: 0, Red: 0, Green: 0 })
  const [editedFromStrategy, setEditedFromStrategy] = useState<string | null>(null)
  const [loadedCards, setLoadedCards] = useState<Set<number>>(new Set())
  const reserve = reserveCount(state.assets)
  const mission = state.missions.find(m => m.id === modal.missionId)

  const showAgentCards = isAgent && !showManual
  const allCardsLoaded = !showAgentCards || modal.strategies.length === 0 || modal.strategies.every((_, i) => loadedCards.has(i))

  // Fire independent 3–5 s timers for each strategy card when in agent mode
  useEffect(() => {
    if (!showAgentCards || modal.strategies.length === 0) return
    const timers = modal.strategies.map((_, i) => {
      const delay = 3000 + Math.random() * 2000
      return window.setTimeout(() => setLoadedCards(prev => new Set([...prev, i])), delay)
    })
    return () => timers.forEach(clearTimeout)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  function handleApply() {
    if (showManual || !isAgent) {
      dispatch({ type: 'APPLY_STRATEGIC', missionId: modal.missionId, source: 'manual', strategyIndex: null, manualAllocation: manualAlloc, editedFromStrategy })
    } else if (selectedIdx !== null) {
      dispatch({ type: 'APPLY_STRATEGIC', missionId: modal.missionId, source: 'agent', strategyIndex: selectedIdx, manualAllocation: null })
    }
  }

  const canApply = showAgentCards
    ? selectedIdx !== null && allCardsLoaded
    : (manualAlloc.Blue + manualAlloc.Red + manualAlloc.Green > 0)

  return (
    <div data-tutorial={isTutorialFirst ? 'first-strategic-panel' : undefined} className="relative mt-2 border-2 border-blue-600/70 rounded-lg bg-gray-800/50 p-3 space-y-3">
      {showAgentCards && !allCardsLoaded && !tutorialForceManual && (
        <div className="absolute inset-0 rounded-lg border-2 border-blue-400/60 animate-pulse pointer-events-none" />
      )}
      {showAgentCards && tutorialForceManual && (
        <p className="text-xs text-gray-500 py-2 text-center">
          Assistant suggestions are disabled for this practice round.
        </p>
      )}
      {showAgentCards && !tutorialForceManual && (
        <div className="grid grid-cols-2 gap-2">
          {modal.strategies.map((strat, i) => (
            <StrategyCard key={strat.name} strat={strat} selected={selectedIdx === i} loaded={loadedCards.has(i)} reserve={reserve} onSelect={() => loadedCards.has(i) && setSelectedIdx(i)} tutorialId={isTutorialFirst && i === 0 ? 'first-strategy-card' : undefined} />
          ))}
          {modal.strategies.length === 0 && (
            <p className="col-span-2 text-xs text-gray-500 py-2 text-center">
              No feasible strategies with current reserve. Use manual allocation.
            </p>
          )}
        </div>
      )}

      {(!showAgentCards) && (
        <div data-tutorial={isTutorialFirst ? 'first-manual-picker' : undefined}>
          <ManualCountPicker
            allocation={manualAlloc}
            reserve={reserve}
            tasks={mission?.tasks ?? []}
            onChange={setManualAlloc}
          />
        </div>
      )}

      {/* Toggle: when showing agent cards → "Edit this allocation" (card selected) or "Set manually instead";
          when in manual → small "← Back" link (hidden if tutorialForceManual so user can't undo).
          Hidden entirely in either direction when tutorialForceAgent locks the operator into the agent-card flow. */}
      {isAgent && !tutorialForceAgent && (
        showManual ? (
          !tutorialForceManual && (
            <button
              data-tutorial={isTutorialFirst ? 'first-manual-toggle' : undefined}
              onClick={() => { setShowManual(false); setEditedFromStrategy(null) }}
              className="text-xs text-gray-500 hover:text-gray-300 w-full text-left"
            >
              ← Back to suggestions
            </button>
          )
        ) : (
          <button
            data-tutorial={isTutorialFirst ? 'first-manual-toggle' : undefined}
            onClick={() => {
              if (selectedIdx !== null) {
                const strat = modal.strategies[selectedIdx]
                setManualAlloc({ ...strat.assets })
                setEditedFromStrategy(strat.name)
              } else {
                setEditedFromStrategy(null)
              }
              setShowManual(true)
              if (tutorialForceManual) document.dispatchEvent(new CustomEvent('tutorial-manual-selected'))
            }}
            className="w-full py-2 px-3 rounded-lg border border-gray-600 bg-gray-800/50 hover:border-gray-400 hover:bg-gray-700/50 text-sm text-gray-400 hover:text-gray-200 transition-colors text-left"
          >
            {selectedIdx !== null ? 'Edit this allocation' : 'Set manually instead'}
          </button>
        )
      )}

      <div className="flex gap-2">
        <button
          data-tutorial={isTutorialFirst ? 'first-deploy-btn' : undefined}
          onClick={handleApply}
          disabled={!canApply}
          className="flex-1 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 rounded text-white text-sm font-semibold transition-colors">
          {showAgentCards ? 'Deploy Selected' : 'Deploy'}
        </button>
        {confirmCancel ? (
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-amber-400">Mission stays unallocated.</span>
            <button onClick={() => dispatch({ type: 'CLOSE_STRATEGIC' })}
              className="px-2 py-1 bg-red-700 hover:bg-red-600 rounded text-white text-xs font-semibold transition-colors">
              Confirm dismiss
            </button>
            <button onClick={() => setConfirmCancel(false)}
              className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 text-xs transition-colors">
              Go back
            </button>
          </div>
        ) : (
          <button onClick={() => setConfirmCancel(true)}
            className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 text-sm transition-colors">
            Cancel
          </button>
        )}
      </div>
    </div>
  )
}

function StrategyCard({ strat, selected, loaded, onSelect, tutorialId }: { strat: Strategy; selected: boolean; loaded: boolean; reserve?: AssetRequirement; onSelect: () => void; tutorialId?: string }) {
  const DRONE_COLOR: Record<AssetType, string> = { Blue: 'text-blue-300', Red: 'text-red-300', Green: 'text-green-300' }
  const DRONE_COLOR_DIM: Record<AssetType, string> = { Blue: 'text-blue-400/60', Red: 'text-red-400/60', Green: 'text-green-400/60' }

  if (!loaded) {
    return (
      <div data-tutorial={tutorialId}
        className="text-left p-3 rounded-lg border border-gray-700 bg-gray-800/50 flex flex-col items-center justify-center gap-2 min-h-[120px]">
        <div className="w-6 h-6 rounded-full border-2 border-gray-600 border-t-blue-400 animate-spin" />
        <span className="text-xs text-gray-500">Analysing...</span>
      </div>
    )
  }

  return (
    <button data-tutorial={tutorialId} onClick={onSelect}
      className={`text-left p-3 rounded-lg border transition-colors ${selected ? 'border-blue-500 bg-blue-900/30' : 'border-gray-600 bg-gray-800 hover:border-gray-400'}`}>
      <div className="flex items-center gap-1 mb-0.5">
        {selected && <span className="text-blue-400 text-xs">✓</span>}
        <div className="font-semibold text-sm text-white">{strat.name}</div>
      </div>
      <div className="text-xs text-gray-400 mt-0.5">{strat.description}</div>
      <div className="mt-2 text-xs space-y-1">
        <div className="flex items-center gap-1.5 flex-wrap">
          {(['Blue', 'Red', 'Green'] as AssetType[]).filter(t => strat.assets[t] > 0).map(t => (
            <span key={t} className={`flex items-center gap-0.5 ${DRONE_COLOR[t]}`}>
              <img src={DRONE_ICON[t]} className="w-3.5 h-3.5 flex-none" alt="" />
              <span className="font-bold">{strat.assets[t]}</span>
            </span>
          ))}
          {(['Blue', 'Red', 'Green'] as AssetType[] as AssetType[]).every(t => strat.assets[t] === 0) && (
            <span className="text-gray-600">—</span>
          )}
        </div>
        <div className="text-gray-400">ETA: {fmtTime(strat.expectedCompletionTime)}</div>
        <div className="flex items-center gap-1 flex-wrap">
          <span className="text-gray-600 text-xs">Res:</span>
          {(['Blue', 'Red', 'Green'] as AssetType[]).map(t => (
            <span key={t} className={`flex items-center gap-0.5 ${DRONE_COLOR_DIM[t]}`}>
              <img src={DRONE_ICON[t]} className="w-3 h-3 flex-none" alt="" />
              <span style={{ fontSize: '10px' }}>{strat.reserveAfter[t]}</span>
            </span>
          ))}
        </div>
      </div>
      <div className="mt-2 space-y-1">
        <ScoreBar label="Speed" value={strat.speedScore} color="bg-blue-500" />
        <ScoreBar label="Reserve" value={strat.reserveScore} color="bg-green-500" />
        <ScoreBar label="Resilience" value={strat.redundancyScore} color="bg-amber-500" />
      </div>
      <div className="mt-1 text-[10px] text-gray-500">
        Buffer:{' '}
        {(() => {
          const parts = (['Blue', 'Red', 'Green'] as AssetType[])
            .filter(t => strat.assets[t] > strat.minimumAssets[t])
            .map(t => `+${strat.assets[t] - strat.minimumAssets[t]} ${ASSET_TYPE_LABEL[t]}`)
          return parts.length > 0 ? parts.join(' · ') : 'at minimum'
        })()}
      </div>
    </button>
  )
}

// ─── Manual count picker ──────────────────────────────────────────────────

function ManualCountPicker({ allocation, reserve, tasks, onChange }: {
  allocation: AssetRequirement
  reserve: AssetRequirement
  tasks: Task[]
  onChange: (a: AssetRequirement) => void
}) {
  const eta = previewAllocation(tasks, allocation)
  // Per-type minimum (max single-task demand) — drones above this can absorb failures
  const floor = { Blue: 0, Red: 0, Green: 0 }
  for (const t of tasks) {
    const p = TASK_PRIMARY[t.type as TaskType]
    floor.Blue  = Math.max(floor.Blue,  p.Blue)
    floor.Red   = Math.max(floor.Red,   p.Red)
    floor.Green = Math.max(floor.Green, p.Green)
  }
  return (
    <div className="space-y-2">
      {(['Blue', 'Red', 'Green'] as const).map(type => {
        const spare = allocation[type] - floor[type]
        return (
          <div key={type} className="flex items-center gap-2">
            <span className={`text-xs w-28 ${ASSET_COLORS[type]}`}>
              {ASSET_TYPE_LABEL[type]} ({reserve[type]} avail)
            </span>
            <button onClick={() => onChange({ ...allocation, [type]: Math.max(0, allocation[type] - 1) })}
              className="w-6 h-6 rounded bg-gray-700 hover:bg-gray-600 text-white font-bold flex items-center justify-center">−</button>
            <span className="w-5 text-center font-mono text-white text-sm">{allocation[type]}</span>
            <button onClick={() => onChange({ ...allocation, [type]: Math.min(reserve[type], allocation[type] + 1) })}
              className="w-6 h-6 rounded bg-gray-700 hover:bg-gray-600 text-white font-bold flex items-center justify-center">+</button>
            <span className="text-xs text-gray-500">/ {reserve[type]}</span>
            {allocation[type] > 0 && (
              <span className={`text-[10px] ml-0.5 ${spare > 0 ? 'text-gray-600' : 'text-gray-700'}`}>
                {spare > 0 ? `${spare} can fail` : 'no spare'}
              </span>
            )}
          </div>
        )
      })}
      <div className="text-xs text-gray-400">
        {eta < Infinity
          ? <>ETA: <span className="text-white">{fmtTime(eta)}</span></>
          : <span className="text-red-400">Waiting for other missions to complete</span>
        }
      </div>
    </div>
  )
}

// ─── Mission progress section ─────────────────────────────────────────────

function MissionProgressSection({ mission, elapsed, urgency, activeTaskIds, isActive, greedy, tutorialFirst }: {
  mission: Mission
  elapsed: number
  urgency: UrgencyLevel
  activeTaskIds: Set<string>
  isActive: boolean
  greedy: boolean
  tutorialFirst?: boolean
}) {
  return (
    <div className="mt-2 pt-1.5 border-t border-gray-700/40 space-y-1.5">
      <div data-tutorial={tutorialFirst ? 'first-task-progress' : undefined}>
        <TaskProgressBar tasks={mission.tasks} urgency={urgency} activeTaskIds={activeTaskIds} isActive={isActive} greedy={greedy} />
      </div>
      <div data-tutorial={tutorialFirst ? 'first-penalty' : undefined}>
        <PenaltyHistogram mission={mission} elapsed={elapsed} />
      </div>
    </div>
  )
}

function TaskProgressBar({ tasks, urgency, activeTaskIds, isActive, greedy }: {
  tasks: Task[]
  urgency: UrgencyLevel
  activeTaskIds: Set<string>
  isActive: boolean
  greedy: boolean
}) {
  const totalValue = tasks.reduce((sum, t) => sum + TASK_WEIGHT[t.type], 0)
  if (totalValue === 0) return null
  const earnedValue = tasks.filter(t => t.status === 'completed').reduce((sum, t) => sum + TASK_WEIGHT[t.type], 0)

  // In greedy mode only the current step is committed; later tasks are still pending and shown
  // as "to plan" (yellow). Other modes treat unstarted-but-assigned tasks as chain-queued.
  const hasUpcoming = greedy && isActive && tasks.some(
    t => t.status === 'pending' && t.assignedAssetIds.length === 0
  )

  function segBg(t: Task): string {
    if (t.status === 'completed') return 'bg-green-600'
    if (t.status === 'failed')    return 'bg-red-800'
    if (t.status === 'executing') return 'bg-amber-500 animate-pulse'
    if (t.status === 'traveling') {
      if (isActive && !activeTaskIds.has(t.id) && t.assignedAssetIds.length > 0) {
        return greedy ? 'bg-yellow-700/60' : 'bg-blue-950/60'   // "to plan" (greedy) vs chain-queued
      }
      return 'bg-blue-700 animate-pulse'
    }
    if (isActive && t.assignedAssetIds.length === 0) {
      return greedy ? 'bg-yellow-700/60' : 'bg-gray-800 opacity-60'   // greedy: "to plan"
    }
    return 'bg-gray-700'
  }

  function urgencyTop(t: Task): string {
    if (t.status === 'completed' || t.status === 'failed') return ''
    return urgency === 'high' ? 'border-t-2 border-red-500'
      : urgency === 'med'    ? 'border-t border-orange-400'
      : urgency === 'low'    ? 'border-t border-yellow-600'
      : ''
  }

  return (
    <div className="space-y-1">
      <div className="flex h-8 rounded-sm overflow-hidden gap-px">
        {tasks.map(t => {
          const widthPct = (TASK_WEIGHT[t.type] / totalValue) * 100
          const showFull  = widthPct >= 15
          const showShort = widthPct >= 7
          return (
            <div
              key={t.id}
              className={`flex flex-col items-center justify-center overflow-hidden flex-none ${segBg(t)} ${urgencyTop(t)}`}
              style={{ width: `${widthPct}%` }}
              title={`${TASK_FULL[t.type]} · +${TASK_WEIGHT[t.type]} pts · ${t.status}`}
            >
              {showShort && (
                <img src={TASK_ICON[t.type]} className="w-4 h-4 flex-none" style={{ opacity: t.status === 'completed' ? 0.7 : 1 }} alt="" />
              )}
              {showFull && (
                <span className="text-white/55 leading-none" style={{ fontSize: '8px' }}>
                  +{TASK_WEIGHT[t.type]}
                </span>
              )}
              {showShort && (
                <div className="flex gap-1 mt-0.5">
                  {TASK_DOTS[t.type].map((dot, i) => (
                    <span key={i} className={`w-2.5 h-2.5 rounded-full ${ASSET_DOT_COLOR[dot]}`} />
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
      <div className="flex items-center justify-between" style={{ fontSize: '10px' }}>
        <span className="text-green-500">+{earnedValue} earned</span>
        <div className="flex items-center gap-2 text-gray-600">
          <LegendDot color="bg-green-600" label="Done" />
          <LegendDot color="bg-blue-700" label="Route" />
          <LegendDot color="bg-amber-500" label="Active" />
          {hasUpcoming
            ? <LegendDot color="bg-yellow-700/60" label="To plan" />
            : <LegendDot color="bg-gray-700" label="Pending" />}
        </div>
        <span className="text-gray-500">{totalValue} max</span>
      </div>
    </div>
  )
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-0.5">
      <span className={`w-2 h-2 rounded-sm inline-block flex-none ${color}`} />
      <span>{label}</span>
    </span>
  )
}

function PenaltyHistogram({ mission, elapsed }: { mission: Mission; elapsed: number }) {
  const rate = CATEGORY_PENALTY_RATE[mission.category]
  const isDone = mission.completionTime !== null
  const waitSecs = Math.max(0, (mission.completionTime ?? elapsed) - mission.arrivalTime)
  const numBars = Math.floor(waitSecs / CHARGE_INTERVAL)
  const partialFrac = isDone ? 0 : (waitSecs % CHARGE_INTERVAL) / CHARGE_INTERVAL

  const totalWeight = mission.tasks.reduce((s, t) => s + TASK_WEIGHT[t.type], 0)

  function pendingFrac(atElapsed: number): number {
    if (totalWeight === 0) return 0
    let pending = 0
    for (const t of mission.tasks) {
      if (t.completionTime === null || t.completionTime > atElapsed) pending += TASK_WEIGHT[t.type]
    }
    return pending / totalWeight
  }

  const totalPenalty = Math.round(
    totalWeight > 0
      ? mission.tasks.reduce((sum, t) => {
          const taskRate = rate * TASK_WEIGHT[t.type] / totalWeight
          const endTime = t.completionTime ?? elapsed
          return sum + taskRate * Math.max(0, endTime - mission.arrivalTime)
        }, 0)
      : 0
  )

  const GROWTH = 1.15
  const MAX_H = 36
  const hasPartial = !isDone && partialFrac > 0

  const barRelH = Array.from({ length: numBars }, (_, i) => {
    const midTime = mission.arrivalTime + (i + 0.5) * CHARGE_INTERVAL
    return (GROWTH ** i) * pendingFrac(midTime)
  })
  const partialRelH = hasPartial
    ? (GROWTH ** numBars) * pendingFrac(elapsed) * partialFrac
    : 0
  const maxRelH = Math.max(...barRelH, partialRelH, 0.001)
  const scale = MAX_H / maxRelH

  const currentRate = rate * pendingFrac(elapsed)

  return (
    <div className="space-y-0.5">
      <div
        className="flex items-end gap-px overflow-x-hidden"
        style={{ height: `${MAX_H}px` }}
        title="Penalty accrues per task until each task individually completes"
      >
        {numBars === 0 && !hasPartial && (
          <span className="text-gray-700 self-end leading-none" style={{ fontSize: '9px' }}>
            no penalty yet
          </span>
        )}
        {barRelH.map((h, i) => (
          <div
            key={i}
            className="flex-1 min-w-0 bg-red-600"
            style={{ height: `${Math.max(1, h * scale)}px` }}
          />
        ))}
        {hasPartial && (
          <div
            className="flex-1 min-w-0 bg-red-900 opacity-60"
            style={{ height: `${Math.max(1, partialRelH * scale)}px` }}
          />
        )}
      </div>
      <div className="flex justify-between" style={{ fontSize: '10px' }}>
        <span className="text-red-400">
          −{totalPenalty} pts{isDone ? ' (final)' : ''}
        </span>
        {!isDone && (
          <span className="text-gray-600">−{currentRate.toFixed(2)}/s · each task reduces rate</span>
        )}
      </div>
    </div>
  )
}

// ─── Co-Pilot task plan ───────────────────────────────────────────────────

function TaskPlanPanel({ mission }: { mission: Mission }) {
  const [open, setOpen] = useState(false)

  const assetChains = new Map<string, Task[]>()
  for (const task of mission.tasks) {
    for (const assetId of task.assignedAssetIds) {
      if (!assetChains.has(assetId)) assetChains.set(assetId, [])
      assetChains.get(assetId)!.push(task)
    }
  }
  for (const chain of assetChains.values()) {
    chain.sort((a, b) => mission.tasks.indexOf(a) - mission.tasks.indexOf(b))
  }

  const unassigned = mission.tasks.filter(t => t.status === 'pending' && t.assignedAssetIds.length === 0)

  // Build the total drone pool for this mission from all tasks' assigned IDs
  const poolIds = new Set(mission.tasks.flatMap(t => t.assignedAssetIds))
  const poolCounts = { Blue: 0, Red: 0, Green: 0 }
  for (const id of poolIds) {
    if (id.startsWith('B')) poolCounts.Blue++
    else if (id.startsWith('R')) poolCounts.Red++
    else poolCounts.Green++
  }

  // Split: tasks whose composition the pool CAN satisfy (queued) vs truly impossible
  const queuedTasks: Task[] = []
  const cannotFulfilTasks: Task[] = []
  for (const task of unassigned) {
    const prim = TASK_PRIMARY[task.type as TaskType]
    const sub = TASK_SUBSTITUTE[task.type as TaskType]
    const canPrim = poolCounts.Blue >= prim.Blue && poolCounts.Red >= prim.Red && poolCounts.Green >= prim.Green
    const canSub = !!sub && poolCounts.Blue >= sub.Blue && poolCounts.Red >= sub.Red && poolCounts.Green >= sub.Green
    if (canPrim || canSub) queuedTasks.push(task)
    else cannotFulfilTasks.push(task)
  }

  if (assetChains.size === 0 && unassigned.length === 0) return null

  return (
    <div className="mt-2 border-t border-gray-700/40 pt-2">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 transition-colors"
      >
        <span className="font-medium text-gray-400">Task Plan</span>
        <span>{open ? '▲' : '▼'}</span>
        {queuedTasks.length > 0 && (
          <span className="ml-1 text-blue-400">⏳ {queuedTasks.length} queued</span>
        )}
        {cannotFulfilTasks.length > 0 && (
          <span className="ml-1 text-amber-500">⚠ {cannotFulfilTasks.length} cannot fulfil</span>
        )}
      </button>

      {open && (
        <div className="mt-1.5 space-y-1">
          {[...assetChains.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([assetId, chain]) => (
            <div key={assetId} className="flex items-center gap-1 text-xs flex-wrap">
              <span className={`font-mono font-bold ${
                assetId.startsWith('B') ? 'text-blue-400' :
                assetId.startsWith('R') ? 'text-red-400' : 'text-green-400'
              }`}>{droneLabel(assetId)}</span>
              {chain.map((task, i) => (
                <span key={task.id} className="flex items-center gap-1">
                  {i > 0 && <span className="text-gray-600">→</span>}
                  <span className={`px-1 py-0.5 rounded text-xs ${TASK_STATUS_STYLE[task.status]}`}>
                    {TASK_SHORT[task.type]}
                  </span>
                </span>
              ))}
            </div>
          ))}
          {queuedTasks.length > 0 && (
            <div className="flex items-center gap-1 text-xs text-blue-500">
              <span>⏳ Queued:</span>
              {queuedTasks.map(t => (
                <span key={t.id} className="px-1 py-0.5 rounded bg-blue-900/30 border border-blue-700/40"
                  title={`${TASK_FULL[t.type]} (T${t.type}) waiting for drones to become available`}>
                  {TASK_SHORT[t.type]}
                </span>
              ))}
            </div>
          )}
          {cannotFulfilTasks.length > 0 && (
            <div className="flex items-center gap-1 text-xs text-amber-600">
              <span>⚠ Cannot fulfil:</span>
              {cannotFulfilTasks.map(t => (
                <span key={t.id} className="px-1 py-0.5 rounded bg-amber-900/30 border border-amber-700/40"
                  title={`${TASK_FULL[t.type]} (T${t.type}) — not enough drones of the required type were allocated`}>
                  {TASK_SHORT[t.type]}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Score bar ────────────────────────────────────────────────────────────

function ScoreBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="flex items-center gap-1.5 text-xs">
      <span className="text-gray-500 w-12">{label}</span>
      <div className="flex-1 bg-gray-700 rounded-full h-1">
        <div className={`${color} h-1 rounded-full`} style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="text-gray-400 w-6 text-right">{Math.round(value * 100)}%</span>
    </div>
  )
}

// ─── Embedded operational map ─────────────────────────────────────────────

const MAP_ZONE_STROKE: Record<string, string> = {
  queued: '#b45309', active: '#1d4ed8', completed: '#374151', failed: '#7f1d1d',
}
const MAP_ZONE_FILL: Record<string, string> = {
  queued: 'rgba(120,53,15,0.12)', active: 'rgba(29,78,216,0.10)', completed: 'rgba(55,65,81,0.04)', failed: 'rgba(127,29,29,0.04)',
}
const MAP_ASSET_COLOR: Record<AssetType, string> = { Blue: '#60a5fa', Red: '#f87171', Green: '#4ade80' }

// Full planned route for a deployed drone: current position → remaining task waypoints → hub.
// Uses the mission's stored per-drone sequence; falls back to assigned tasks (T5-first order).
function droneFullPathPoints(asset: Asset, mission: Mission): { x: number; y: number }[] {
  const seq = mission.droneSequences?.[asset.id]?.length
    ? mission.droneSequences[asset.id]
    : mission.tasks.filter(t => t.assignedAssetIds.includes(asset.id)).sort((a, b) => b.type - a.type).map(t => t.id)
  const pts: { x: number; y: number }[] = [{ x: asset.position.x, y: asset.position.y }]
  for (const tid of seq) {
    const t = mission.tasks.find(tt => tt.id === tid)
    if (!t || t.status === 'completed' || t.status === 'failed') continue
    pts.push({ x: t.waypoint.x, y: t.waypoint.y })
  }
  pts.push({ x: HUB.x, y: HUB.y })
  return pts
}

function EmbeddedOperationalMap({ state, dispatch, setOpenMissionId }: {
  state: GameState
  dispatch: (a: GameAction) => void
  setOpenMissionId: (id: string | null) => void
}) {
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 })
  const [grabbing, setGrabbing] = useState(false)
  const [detailLevel, setDetailLevel] = useState<0 | 1 | 2>(0)
  const [hoverDrone, setHoverDrone] = useState<string | null>(null)
  const [hoverZone, setHoverZone] = useState<string | null>(null)
  const [showFullPaths, setShowFullPaths] = useState(!!state.config.fullPathsOnHover)
  const svgRef = useRef<SVGSVGElement>(null)
  const isPanning = useRef(false)
  const hasMoved = useRef(false)
  const lastPos = useRef({ x: 0, y: 0 })
  const panPointerId = useRef<number | null>(null)
  const hasCaptured = useRef(false)

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const rect = svg.getBoundingClientRect()
      const pt = {
        x: (e.clientX - rect.left) / rect.width * 1000,
        y: (e.clientY - rect.top) / rect.height * 800,
      }
      const factor = e.deltaY < 0 ? 1.2 : 1 / 1.2
      setView(v => {
        const ns = Math.min(8, Math.max(0.25, v.scale * factor))
        const ratio = ns / v.scale
        return { x: pt.x - (pt.x - v.x) * ratio, y: pt.y - (pt.y - v.y) * ratio, scale: ns }
      })
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => svg.removeEventListener('wheel', onWheel)
  }, [])

  const gt = `translate(${view.x},${view.y}) scale(${view.scale})`

  return (
    <svg
      ref={svgRef}
      viewBox="0 0 1000 800"
      className="w-full h-full"
      style={{ cursor: grabbing ? 'grabbing' : 'grab', background: '#030712' }}
      onClick={() => {
        LOG && console.log('[PRIMARY] blank SVG click, hasMoved:', hasMoved.current)
        if (!hasMoved.current) setOpenMissionId(null)
      }}
      onPointerDown={e => {
        isPanning.current = true
        hasMoved.current = false
        hasCaptured.current = false
        panPointerId.current = e.pointerId
        lastPos.current = { x: e.clientX, y: e.clientY }
        setGrabbing(true)
      }}
      onPointerMove={e => {
        if (!isPanning.current) return
        const dx = e.clientX - lastPos.current.x
        const dy = e.clientY - lastPos.current.y
        lastPos.current = { x: e.clientX, y: e.clientY }
        if (Math.abs(dx) > 8 || Math.abs(dy) > 8) {
          hasMoved.current = true
          if (!hasCaptured.current) {
            e.currentTarget.setPointerCapture(panPointerId.current!)
            hasCaptured.current = true
          }
        }
        const rect = svgRef.current!.getBoundingClientRect()
        setView(v => ({ ...v, x: v.x + dx * 1000 / rect.width, y: v.y + dy * 800 / rect.height }))
      }}
      onPointerUp={() => { isPanning.current = false; setGrabbing(false); hasCaptured.current = false }}
    >
      <defs>
        <marker id="emap-arr-blue"  markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#60a5fa" />
        </marker>
        <marker id="emap-arr-red"   markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#f87171" />
        </marker>
        <marker id="emap-arr-green" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#4ade80" />
        </marker>
      </defs>
      <g transform={gt}>
        {/* Dark background */}
        <rect width="1000" height="800" fill="#030712" />

        {/* Grid dots */}
        {Array.from({ length: 20 }, (_, i) => i * 50).flatMap(gx =>
          Array.from({ length: 16 }, (_, j) => j * 50).map(gy => (
            <circle key={`${gx},${gy}`} cx={gx} cy={gy} r={0.8} fill="#1f2937" />
          ))
        )}

        {/* Mission zones */}
        {[...state.missions]
          .sort((a, b) => {
            const ord: Record<string, number> = { completed: 0, failed: 0, abandoned: 0, queued: 1, active: 2 }
            return (ord[a.status] ?? 0) - (ord[b.status] ?? 0)
          })
          .map(m => {
            const isAllocatable = m.status === 'queued' && !m.pendingAllocation && !m.tacticalPending
            const isTactical = m.tacticalPending || m.failureRecoveryPending
            const isClickable = isAllocatable || m.tacticalPending || m.failureRecoveryPending || m.status === 'active'
            return (
              <g key={m.id}
                onClick={e => {
                  e.stopPropagation()
                  LOG && console.log('[PRIMARY] mission click', m.id, { hasMoved: hasMoved.current, tacticalPending: m.tacticalPending, failureRecoveryPending: m.failureRecoveryPending, status: m.status, isAllocatable })
                  if (hasMoved.current) return
                  if (m.tacticalPending || m.failureRecoveryPending || m.status === 'active') {
                    LOG && console.log('[PRIMARY] → setOpenMissionId', m.id)
                    setOpenMissionId(m.id)
                  } else if (isAllocatable) {
                    dispatch({ type: 'OPEN_STRATEGIC', missionId: m.id })
                  }
                }}
                onMouseEnter={showFullPaths ? () => setHoverZone(m.id) : undefined}
                onMouseLeave={showFullPaths ? () => setHoverZone(z => (z === m.id ? null : z)) : undefined}
                style={{ cursor: isClickable ? 'pointer' : 'default' }}
              >
                <circle
                  cx={m.zoneCenter.x} cy={m.zoneCenter.y} r={m.zoneRadius}
                  fill={MAP_ZONE_FILL[m.status] ?? 'rgba(55,65,81,0.04)'}
                  stroke={isTactical ? '#d97706' : (MAP_ZONE_STROKE[m.status] ?? '#374151')}
                  strokeWidth={isTactical ? '2' : '1.5'}
                  strokeDasharray={isTactical ? '6 3' : undefined}
                />
                <text x={m.zoneCenter.x} y={m.zoneCenter.y - 4} textAnchor="middle" fill="white" fontSize="11" fontWeight="bold" fontFamily="monospace">{m.id}</text>
                <text x={m.zoneCenter.x} y={m.zoneCenter.y + 10} textAnchor="middle" fill="#9ca3af" fontSize="8" fontFamily="sans-serif">Cat {m.category}</text>
                {m.failureRecoveryPending && (
                  <text x={m.zoneCenter.x} y={m.zoneCenter.y + 22} textAnchor="middle" fill="#f87171" fontSize="7" fontFamily="sans-serif">FAILURE</text>
                )}
                {m.tacticalPending && !m.failureRecoveryPending && (
                  <text x={m.zoneCenter.x} y={m.zoneCenter.y + 22} textAnchor="middle" fill="#fbbf24" fontSize="7" fontFamily="sans-serif">TACTICAL</text>
                )}
                {isAllocatable && (
                  <text x={m.zoneCenter.x} y={m.zoneCenter.y + 22} textAnchor="middle" fill="#f59e0b" fontSize="7" fontFamily="sans-serif">allocate</text>
                )}
              </g>
            )
          })}

        {/* Asset route lines — all levels */}
        {state.assets
          .filter(a => a.status === 'deployed' || a.status === 'returning')
          .map(a => (
            <line key={`r-${a.id}`}
              x1={a.travelFrom.x} y1={a.travelFrom.y}
              x2={a.targetPosition.x} y2={a.targetPosition.y}
              stroke={MAP_ASSET_COLOR[a.type]}
              strokeWidth={detailLevel >= 1 ? '1.5' : '0.5'}
              opacity="0.2"
            />
          ))}

        {/* Full planned paths — revealed on hover when the setting is enabled.
            Hover a drone → that drone's path; hover a mission zone → every drone serving it. */}
        {showFullPaths && (() => {
          const ids = hoverDrone
            ? [hoverDrone]
            : hoverZone
              ? state.assets
                  .filter(a => a.currentMissionId === hoverZone && (a.status === 'deployed' || a.status === 'returning'))
                  .map(a => a.id)
              : []
          return ids.map(id => {
            const a = state.assets.find(x => x.id === id)
            if (!a || !a.currentMissionId) return null
            const m = state.missions.find(mm => mm.id === a.currentMissionId)
            if (!m) return null
            const pts = droneFullPathPoints(a, m)
            if (pts.length < 2) return null
            const color = MAP_ASSET_COLOR[a.type]
            return (
              <g key={`fp-${id}`} style={{ pointerEvents: 'none' }}>
                <polyline
                  points={pts.map(p => `${p.x},${p.y}`).join(' ')}
                  fill="none" stroke={color} strokeWidth={2} strokeDasharray="5 3" opacity={0.95}
                />
                {pts.slice(1, -1).map((p, i) => (
                  <circle key={i} cx={p.x} cy={p.y} r={2.5} fill={color} opacity={0.95} />
                ))}
              </g>
            )
          })
        })()}


        {/* Asset icons — all levels */}
        {state.assets
          .filter(a => a.status !== 'available' && a.status !== 'failed')
          .map(a => {
            const opacity = a.status === 'returning' ? 0.5 : 1
            return (
              <g key={a.id} opacity={opacity}
                onMouseEnter={showFullPaths ? () => setHoverDrone(a.id) : undefined}
                onMouseLeave={showFullPaths ? () => setHoverDrone(d => (d === a.id ? null : d)) : undefined}
                style={showFullPaths ? { cursor: 'pointer' } : undefined}>
                {showFullPaths && (
                  <circle cx={a.position.x} cy={a.position.y} r={10} fill="transparent" />
                )}
                <circle cx={a.position.x} cy={a.position.y} r={5}
                  fill={MAP_ASSET_COLOR[a.type]} fillOpacity={0.15} />
                <image href={DRONE_ICON[a.type]}
                  x={a.position.x - 4} y={a.position.y - 4} width={8} height={8}
                  style={{ pointerEvents: 'none' }} />
                {detailLevel >= 1 && (
                  <text
                    x={a.position.x + 7} y={a.position.y - 4}
                    fill={MAP_ASSET_COLOR[a.type]} fontSize="7" fontFamily="monospace"
                    style={{ pointerEvents: 'none' }}
                  >
                    {droneLabel(a.id)}
                  </text>
                )}
              </g>
            )
          })}

        {/* Mid/Full: task waypoints inside active mission zones */}
        {detailLevel >= 1 && state.missions
          .filter(m => m.status === 'active')
          .flatMap(m => m.tasks.map(t => ({ t, m })))
          .map(({ t }) => (
            <g key={`wp-${t.id}`}>
              {(() => {
                if (t.status !== 'executing' && t.status !== 'completed') return null
                const progress = t.status === 'completed'
                  ? 1
                  : t.startTime !== null && t.baseTime > 0
                    ? Math.min(1, Math.max(0, (state.elapsed - t.startTime) / t.baseTime))
                    : 0
                if (progress <= 0) return null
                const R = 8, circ = 2 * Math.PI * R
                return (
                  <circle
                    cx={t.waypoint.x} cy={t.waypoint.y} r={R}
                    fill="none"
                    stroke={t.status === 'completed' ? '#10b981' : '#3b82f6'}
                    strokeWidth={1.5}
                    strokeDasharray={`${circ} ${circ}`}
                    strokeDashoffset={circ * (1 - progress)}
                    transform={`rotate(-90 ${t.waypoint.x} ${t.waypoint.y})`}
                    style={{ pointerEvents: 'none' }}
                    opacity={0.8}
                  />
                )
              })()}
              <circle cx={t.waypoint.x} cy={t.waypoint.y} r={5}
                fill={t.status === 'completed' ? 'rgba(16,185,129,0.2)' : t.status === 'executing' ? 'rgba(245,158,11,0.2)' : 'rgba(30,41,59,0.8)'}
                stroke={t.status === 'completed' ? '#4ade80' : t.status === 'executing' ? '#f59e0b' : '#475569'}
                strokeWidth={0.8}
              />
              <image href={TASK_ICON[t.type as TaskType]}
                x={t.waypoint.x - 4} y={t.waypoint.y - 4} width={8} height={8}
                style={{ pointerEvents: 'none' }}
              />
              {detailLevel === 2 && (
                <text x={t.waypoint.x} y={t.waypoint.y + 10}
                  textAnchor="middle" fill="#94a3b8" fontSize="6" fontFamily="sans-serif"
                  style={{ pointerEvents: 'none' }}>
                  {TASK_FULL[t.type as TaskType]}
                </text>
              )}
            </g>
          ))}

        {/* Full: queued mission task waypoints (future planned tasks) */}
        {detailLevel === 2 && state.missions
          .filter(m => m.status === 'queued')
          .flatMap(m => m.tasks.map(t => ({ t, m })))
          .map(({ t }) => (
            <g key={`qwp-${t.id}`} opacity={0.45}>
              <circle cx={t.waypoint.x} cy={t.waypoint.y} r={4}
                fill="rgba(30,41,59,0.5)" stroke="#374151" strokeWidth={0.7} strokeDasharray="2 2"
              />
              <image href={TASK_ICON[t.type as TaskType]}
                x={t.waypoint.x - 3} y={t.waypoint.y - 3} width={6} height={6}
                style={{ pointerEvents: 'none' }}
              />
              <text x={t.waypoint.x} y={t.waypoint.y + 8}
                textAnchor="middle" fill="#6b7280" fontSize="5.5" fontFamily="sans-serif"
                style={{ pointerEvents: 'none' }}>
                {TASK_FULL[t.type as TaskType]}
              </text>
            </g>
          ))}

        {/* Hub */}
        <circle cx={HUB.x} cy={HUB.y} r={9} fill="#1e3a8a" stroke="#3b82f6" strokeWidth="1.5" />
        <text x={HUB.x} y={HUB.y + 22} textAnchor="middle" fill="#60a5fa" fontSize="9" fontFamily="monospace">HUB</text>
      </g>

      {/* Detail level toggle — stopPropagation prevents SVG pan handler from capturing pointer */}
      <g onClick={() => setDetailLevel(l => ((l + 1) % 3) as 0 | 1 | 2)} onPointerDown={e => e.stopPropagation()} style={{ cursor: 'pointer' }}>
        <rect x="6" y="770" width="60" height="16" rx="3" fill="#1f2937" stroke="#374151" />
        <text x="36" y="781" textAnchor="middle" fill="#9ca3af" fontSize="9" fontFamily="sans-serif">
          {(['Low', 'Mid', 'Full'] as const)[detailLevel]}
        </text>
      </g>

      {/* Full-path-on-hover toggle */}
      <g onClick={() => setShowFullPaths(v => !v)} onPointerDown={e => e.stopPropagation()} style={{ cursor: 'pointer' }}>
        <rect x="70" y="770" width="78" height="16" rx="3"
          fill={showFullPaths ? '#1e3a8a' : '#1f2937'} stroke={showFullPaths ? '#3b82f6' : '#374151'} />
        <text x="109" y="781" textAnchor="middle" fill={showFullPaths ? '#93c5fd' : '#9ca3af'} fontSize="9" fontFamily="sans-serif">
          Paths: {showFullPaths ? 'on' : 'off'}
        </text>
      </g>

      {/* Status overlay */}
      <text x="6" y="794" fill="#374151" fontSize="9" fontFamily="sans-serif">
        {showFullPaths
          ? 'Scroll/drag to navigate · hover a drone or mission to see its full path'
          : 'Scroll/drag to navigate · click queued zone to allocate'}
      </text>
    </svg>
  )
}

// ─── Utilities ────────────────────────────────────────────────────────────

function formatCountdown(elapsed: number, duration: number): string {
  const rem = Math.max(0, duration - elapsed)
  const m = Math.floor(rem / 60)
  const s = Math.floor(rem % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatSeconds(s: number): string {
  if (s < 60) return `${Math.round(s)}s`
  return `${Math.floor(s / 60)}m${Math.round(s % 60).toString().padStart(2, '0')}s`
}
