import { useState } from 'react'
import type { GameState, Mission, Task, Asset, AssetType, MissionCategory, AssetRequirement, Strategy } from '../types'
import type { GameAction } from '../store/actions'
import { reserveCount } from '../store/gameReducer'
import { downloadDebugLog } from '../utils/debugLog'
import { previewAllocation } from '../utils/copilot'
import { ASSET_CALLSIGNS } from '../utils/missionGen'

interface Props {
  state: GameState
  dispatch: (a: GameAction) => void
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

const TASK_SHORT: Record<number, string> = { 1: 'Rcn', 2: 'Sup', 3: 'Ext', 4: 'Med', 5: 'Rsc' }
const TASK_FULL:  Record<number, string> = { 1: 'Recce', 2: 'Resupply', 3: 'Extraction', 4: 'Medevac', 5: 'Rescue' }

// Colored dots showing which drone types a task requires (primary composition)
const TASK_DOTS: Record<number, AssetType[]> = {
  1: ['Blue'],
  2: ['Blue', 'Red'],
  3: ['Blue', 'Red', 'Red'],
  4: ['Blue', 'Blue', 'Blue', 'Green'],
  5: ['Red', 'Green'],
}

const DRONE_NAME: Record<AssetType, string> = {
  Blue:  'Recon',
  Red:   'Logistics',
  Green: 'Specialist',
}

const ASSET_COLORS: Record<AssetType, string> = {
  Blue: 'text-blue-400', Red: 'text-red-400', Green: 'text-green-400',
}

const ASSET_DOT_COLOR: Record<AssetType, string> = {
  Blue: 'bg-blue-400', Red: 'bg-red-400', Green: 'bg-green-400',
}

const ASSET_BAR_COLOR: Record<AssetType, string> = {
  Blue: 'bg-blue-500', Red: 'bg-red-500', Green: 'bg-green-500',
}

const ASSET_CHIP_IDLE: Record<AssetType, string> = {
  Blue:  'bg-blue-900/40 text-blue-400',
  Red:   'bg-red-900/40 text-red-400',
  Green: 'bg-green-900/40 text-green-400',
}

const ASSET_TOTAL: Record<AssetType, number> = { Blue: 18, Red: 9, Green: 3 }


function fmtTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}m ${s.toString().padStart(2, '0')}s`
}

// ─── Top-level ────────────────────────────────────────────────────────────

export default function PrimaryDisplay({ state, dispatch }: Props) {
  const [useCallsigns, setUseCallsigns] = useState(false)
  const queued  = state.missions.filter(m => m.status === 'queued')
  const active  = state.missions.filter(m => m.status === 'active')
  const done    = state.missions.filter(m => m.status === 'completed' || m.status === 'failed')
  const reserve = reserveCount(state.assets)

  return (
    <div className="h-screen flex flex-col bg-gray-950 text-white overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-5 py-2.5 bg-gray-900 border-b border-gray-800 flex-none">
        <div className="flex items-center gap-4">
          <span className="font-bold text-white">SAR Command</span>
          <span className="text-xs text-gray-400 uppercase tracking-wide">
            Session {state.sessionNumber} / 3
          </span>
        </div>
        <div className="flex items-center gap-6 text-sm">
          <span className="font-mono text-amber-400 font-bold">{formatCountdown(state.elapsed)}</span>
          <span className="text-gray-400">Score: <span className="text-white font-bold">{state.score}</span></span>
          <button
            onClick={() => window.open('/?view=map', '_blank', 'noopener')}
            className="text-xs px-2.5 py-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700 transition-colors"
          >
            Open Map
          </button>
          <button
            onClick={() => setUseCallsigns(c => !c)}
            className={`text-xs px-2.5 py-1 rounded border transition-colors ${
              useCallsigns
                ? 'bg-blue-700 text-white border-blue-500'
                : 'bg-gray-800 text-gray-300 border-gray-700 hover:bg-gray-700'
            }`}
          >
            Callsigns
          </button>
          <button
            onClick={downloadDebugLog}
            className="text-xs px-2.5 py-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-500 border border-gray-700 transition-colors"
            title="Download debug log"
          >
            Debug Log
          </button>
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: mission queue */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2 min-w-0">
          {queued.length > 0 && (
            <section>
              <SectionLabel text="Incoming — awaiting allocation" dot="bg-amber-400" />
              {queued.map(m => (
                <MissionCard key={m.id} mission={m} state={state} dispatch={dispatch} useCallsigns={useCallsigns} />
              ))}
            </section>
          )}
          {active.length > 0 && (
            <section className={queued.length > 0 ? 'mt-4' : ''}>
              <SectionLabel text="Active missions" dot="bg-blue-400" />
              {active.map(m => (
                <MissionCard key={m.id} mission={m} state={state} dispatch={dispatch} useCallsigns={useCallsigns} />
              ))}
            </section>
          )}
          {done.length > 0 && (
            <section className="mt-4 opacity-60">
              <SectionLabel text="Completed" dot="bg-gray-500" />
              {done.slice(-6).map(m => (
                <MissionCard key={m.id} mission={m} state={state} dispatch={dispatch} useCallsigns={useCallsigns} />
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

        {/* Right: reserve + Meta-Co-Pilot */}
        <aside className="w-72 flex-none border-l border-gray-800 flex flex-col overflow-hidden">
          <div className="overflow-y-auto flex-1 p-4 space-y-4">
            <ReservePanel state={state} reserve={reserve} />
            <ForecastPanel state={state} />
          </div>
        </aside>
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

function MissionCard({ mission, state, dispatch, useCallsigns }: { mission: Mission; state: GameState; dispatch: (a: GameAction) => void; useCallsigns: boolean }) {
  const isQueued    = mission.status === 'queued'
  const isActive    = mission.status === 'active'
  const isCompleted = mission.status === 'completed'
  const isFailed    = mission.status === 'failed'
  const isAllocating = state.copilotModal?.missionId === mission.id


  const completedTasks = mission.tasks.filter(t => t.status === 'completed').length
  const totalTasks = mission.tasks.length
  const deployedHere = state.assets.filter(a => a.currentMissionId === mission.id && a.status === 'deployed')

  const borderColor = isAllocating
    ? 'border-blue-500'
    : isQueued ? 'border-amber-700' : isActive ? 'border-blue-800' : 'border-gray-800'
  const bgColor = isAllocating
    ? 'bg-blue-950/20'
    : isQueued ? 'bg-amber-950/20' : isActive ? 'bg-blue-950/10' : 'bg-gray-900/40'

  const eta = isActive
    ? Math.max(0, Math.max(...mission.tasks.map(t => t.completionTime ?? 0)) - state.elapsed)
    : null

  return (
    <div className={`rounded-lg border ${borderColor} ${bgColor} p-3 mb-2`}>
      {/* Card header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-xs font-bold text-white">{mission.id}</span>
          <span className={`text-xs px-1.5 py-0.5 rounded font-bold ${CAT_BADGE[mission.category]}`}>
            {mission.category} · {CAT_NAME[mission.category]}
          </span>
          {isActive && <span className="text-xs text-gray-400">{completedTasks}/{totalTasks}</span>}
          {isCompleted && <span className="text-xs text-green-400">✓ complete</span>}
          {isFailed && <span className="text-xs text-red-400">✗ failed</span>}
        </div>
        <div className="flex items-center gap-2 flex-none">
          {isActive && eta !== null && (
            <span className="text-xs text-gray-400 font-mono">ETA {formatSeconds(eta)}</span>
          )}
          {isQueued && !isAllocating && (
            <button
              onClick={() => dispatch({ type: 'OPEN_ALLOCATE', missionId: mission.id })}
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

      {/* Task badges — status strip */}
      <div className="flex flex-wrap gap-1 mt-1">
        {mission.tasks.map(t => (
          <TaskBadge key={t.id} task={t} missionActive={isActive} />
        ))}
      </div>

      {/* Co-Pilot task plan — shown after allocation */}
      {isActive && <CopilotPlanPanel mission={mission} useCallsigns={useCallsigns} />}

      {/* Assigned assets strip */}
      {isActive && deployedHere.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5 pt-1.5 border-t border-gray-700/40">
          {deployedHere.map(a => {
            const task = mission.tasks.find(t => t.id === a.currentTaskId)
            const recallable = task?.status === 'traveling' || task?.status === 'executing'
            const recallCostSec = task?.completionTime != null
              ? Math.max(0, Math.round(task.completionTime - state.elapsed))
              : null
            return (
              <DroneChip
                key={a.id}
                asset={a}
                recallable={recallable ?? false}
                isZeroCost={recallCostSec === 0}
                recallCostSec={recallCostSec}
                callsign={useCallsigns ? ASSET_CALLSIGNS[a.id] : undefined}
                onRecall={() => dispatch({ type: 'RECALL_ASSET', assetId: a.id })}
              />
            )
          })}
        </div>
      )}

      {/* Inline allocation panel */}
      {isAllocating && <InlineAllocator state={state} dispatch={dispatch} />}
    </div>
  )
}

// ─── Task badge ───────────────────────────────────────────────────────────

function TaskBadge({ task, missionActive, isPriority, onTogglePriority }: {
  task: Task
  missionActive?: boolean
  isPriority?: boolean
  onTogglePriority?: () => void
}) {
  const isUnassigned = missionActive === true && task.status === 'pending' && task.assignedAssetIds.length === 0
  const baseStyle = isUnassigned
    ? 'bg-gray-900 border border-amber-700/60 text-amber-600 opacity-70'
    : TASK_STATUS_STYLE[task.status]

  return (
    <div
      className={`relative inline-flex flex-col items-center justify-center px-1.5 py-0.5 rounded
        ${baseStyle}
        ${onTogglePriority ? 'cursor-pointer hover:brightness-125' : 'cursor-default'}
        ${isPriority ? 'ring-1 ring-yellow-400' : ''}`}
      title={isUnassigned
        ? `${TASK_FULL[task.type]} (T${task.type}) — no drones assigned (insufficient reserve)`
        : `${TASK_FULL[task.type]} (T${task.type}) — ${task.status}${onTogglePriority ? ' · click to prioritise' : ''}`}
      onClick={onTogglePriority}
    >
      {isPriority && (
        <span className="absolute -top-1 -right-1 text-yellow-400 text-xs leading-none">★</span>
      )}
      <span className="text-xs font-bold leading-tight">
        {TASK_SHORT[task.type]}{isUnassigned ? '?' : ''}
      </span>
      <div className="flex gap-0.5 mt-0.5">
        {TASK_DOTS[task.type].map((t, i) => (
          <span key={i} className={`w-1.5 h-1.5 rounded-full ${ASSET_DOT_COLOR[t]} opacity-75`} />
        ))}
      </div>
    </div>
  )
}

// ─── Drone chip with confirmation popout ──────────────────────────────────

function DroneChip({ asset, recallable, isZeroCost, recallCostSec, callsign, onRecall }: {
  asset: Asset
  recallable: boolean
  isZeroCost: boolean
  recallCostSec: number | null
  callsign?: string
  onRecall: () => void
}) {
  const [confirming, setConfirming] = useState(false)
  const label = callsign ?? asset.id

  return (
    <div className="relative">
      <button
        disabled={!recallable}
        onClick={() => recallable && setConfirming(c => !c)}
        title={recallable ? `Click to recall ${label}` : label}
        className={`font-mono text-xs px-1 py-0.5 rounded leading-none transition-colors ${
          recallable
            ? isZeroCost
              ? 'bg-green-800/60 text-green-200 hover:bg-green-700 cursor-pointer'
              : 'bg-orange-900/60 text-orange-300 hover:bg-orange-800 cursor-pointer'
            : `${ASSET_CHIP_IDLE[asset.type]} cursor-default opacity-70`
        }`}
      >
        {label}
      </button>

      {confirming && (
        <div
          className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 z-30 bg-gray-900 border border-gray-600 rounded-lg p-2 shadow-2xl min-w-max"
          onClick={e => e.stopPropagation()}
        >
          <p className="text-xs font-semibold text-white mb-0.5">Recall {label}?</p>
          <p className={`text-xs mb-2 ${isZeroCost ? 'text-green-400' : 'text-orange-400'}`}>
            {isZeroCost ? 'Free — task complete' : `+${recallCostSec}s penalty`}
          </p>
          <div className="flex gap-1">
            <button
              onClick={() => { onRecall(); setConfirming(false) }}
              className={`px-2 py-0.5 text-xs rounded font-semibold text-white ${
                isZeroCost ? 'bg-green-700 hover:bg-green-600' : 'bg-red-700 hover:bg-red-600'
              }`}
            >
              Recall
            </button>
            <button
              onClick={() => setConfirming(false)}
              className="px-2 py-0.5 text-xs rounded bg-gray-700 hover:bg-gray-600 text-gray-300"
            >
              ✕
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Co-Pilot task plan ───────────────────────────────────────────────────

function CopilotPlanPanel({ mission, useCallsigns }: { mission: Mission; useCallsigns: boolean }) {
  const [open, setOpen] = useState(false)

  // Build per-asset task chains by grouping tasks by asset ID.
  // Sort each chain by position in mission.tasks so reprioritisation is reflected.
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

  if (assetChains.size === 0 && unassigned.length === 0) return null

  return (
    <div className="mt-2 border-t border-gray-700/40 pt-2">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 transition-colors"
      >
        <span className="font-medium text-gray-400">Co-Pilot Plan</span>
        <span>{open ? '▲' : '▼'}</span>
        {unassigned.length > 0 && (
          <span className="ml-1 text-amber-500">⚠ {unassigned.length} unassigned</span>
        )}
      </button>

      {open && (
        <div className="mt-1.5 space-y-1">
          {[...assetChains.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([assetId, chain]) => (
            <div key={assetId} className="flex items-center gap-1 text-xs flex-wrap">
              <span className={`font-mono font-bold ${
                assetId.startsWith('B') ? 'text-blue-400' :
                assetId.startsWith('R') ? 'text-red-400' : 'text-green-400'
              }`}>{useCallsigns ? (ASSET_CALLSIGNS[assetId] ?? assetId) : assetId}</span>
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
          {unassigned.length > 0 && (
            <div className="flex items-center gap-1 text-xs text-amber-600">
              <span>⚠ Unassigned:</span>
              {unassigned.map(t => (
                <span key={t.id} className="px-1 py-0.5 rounded bg-amber-900/30 border border-amber-700/40">
                  {TASK_SHORT[t.type]}
                </span>
              ))}
              <span className="text-gray-600">(no reserve)</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Task priority panel ──────────────────────────────────────────────────

function TaskPriorityPanel({ tasks, priorityIds, onToggle }: {
  tasks: Task[]
  priorityIds: string[]
  onToggle: (taskId: string) => void
}) {
  const prioritised = priorityIds
    .map(id => tasks.find(t => t.id === id))
    .filter((t): t is Task => t !== undefined)
  const rest = tasks.filter(t => !priorityIds.includes(t.id))

  return (
    <div className="space-y-1.5 pb-1 border-b border-gray-700/50">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500 uppercase tracking-wider">Execution Priority</p>
        {priorityIds.length > 0 && (
          <span className="text-xs text-gray-600">click to remove</span>
        )}
      </div>

      {prioritised.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          {prioritised.map((task, i) => (
            <button
              key={task.id}
              onClick={() => onToggle(task.id)}
              className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-yellow-900/40 border border-yellow-600/70 text-yellow-200 text-xs font-medium hover:bg-yellow-800/50 transition-colors"
            >
              <span className="text-yellow-500 font-bold">{i + 1}</span>
              {TASK_SHORT[task.type]}
            </button>
          ))}
          <span className="text-xs text-gray-600">→ then plan</span>
        </div>
      )}

      <div className="flex flex-wrap gap-1">
        {prioritised.length === 0 && (
          <span className="text-xs text-gray-600 w-full">Click to run first:</span>
        )}
        {rest.map(task => (
          <button
            key={task.id}
            onClick={() => onToggle(task.id)}
            className="flex flex-col items-center px-1.5 py-0.5 rounded bg-gray-800 hover:bg-gray-700 border border-gray-600 hover:border-gray-400 text-gray-300 text-xs transition-colors"
          >
            <span className="font-bold leading-tight">{TASK_SHORT[task.type]}</span>
            <div className="flex gap-0.5 mt-0.5">
              {TASK_DOTS[task.type].map((t, i) => (
                <span key={i} className={`w-1.5 h-1.5 rounded-full ${ASSET_DOT_COLOR[t]}`} />
              ))}
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

// ─── Inline allocator ─────────────────────────────────────────────────────

function InlineAllocator({ state, dispatch }: { state: GameState; dispatch: (a: GameAction) => void }) {
  const modal = state.copilotModal!
  const reserve = reserveCount(state.assets)
  const [manualMode, setManualMode] = useState(false)
  const [manualAlloc, setManualAlloc] = useState<AssetRequirement>({ Blue: 0, Red: 0, Green: 0 })
  const [editingIndex, setEditingIndex] = useState<number | null>(null)

  const selectedStrat = modal.selectedIndex !== null ? modal.strategies[modal.selectedIndex] : null
  const editedAlloc = modal.editedAllocation
  const toApply: AssetRequirement = manualMode
    ? manualAlloc
    : editedAlloc ?? selectedStrat?.assets ?? { Blue: 0, Red: 0, Green: 0 }

  const isFeasible = (a: AssetRequirement) =>
    a.Blue <= reserve.Blue && a.Red <= reserve.Red && a.Green <= reserve.Green
  const canApply = manualMode
    ? (toApply.Blue + toApply.Red + toApply.Green > 0) && isFeasible(toApply)
    : selectedStrat != null && isFeasible(toApply)

  function applySource(): 'copilot_as_proposed' | 'copilot_modified' | 'manual' {
    if (manualMode) return 'manual'
    if (editedAlloc) return 'copilot_modified'
    return 'copilot_as_proposed'
  }

  function handleApply() {
    if (!canApply) return
    dispatch({
      type: 'APPLY_ALLOCATION',
      missionId: modal.missionId,
      allocation: toApply,
      source: applySource(),
      strategies: modal.strategies,
      selectedIndex: modal.selectedIndex,
    })
  }

  function handleDismiss() {
    dispatch({ type: 'DISMISS_COPILOT', missionId: modal.missionId })
  }

  return (
    <div className="mt-3 border-t border-gray-700 pt-3 space-y-3">

      {/* Fleet status */}
      <div className="space-y-1.5">
        <p className="text-xs text-gray-500 uppercase tracking-wider">Fleet Status</p>
        <div className="grid grid-cols-3 gap-3">
          {(['Blue', 'Red', 'Green'] as AssetType[]).map(type => {
            const avail    = reserve[type]
            const deployed = state.assets.filter(a => a.type === type && a.status === 'deployed').length
            const returning = state.assets.filter(a => a.type === type && a.status === 'returning').length
            const total    = ASSET_TOTAL[type]
            return (
              <div key={type} className="space-y-1">
                <div className="flex justify-between items-baseline">
                  <span className={`text-xs font-medium ${ASSET_COLORS[type]}`}>{DRONE_NAME[type]}</span>
                  <span className="text-xs text-white font-mono">{avail}/{total} avail</span>
                </div>
                <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden flex">
                  <div
                    className={`h-full ${ASSET_BAR_COLOR[type]} transition-all`}
                    style={{ width: `${(avail / total) * 100}%` }}
                  />
                  <div
                    className="h-full bg-gray-500 transition-all"
                    style={{ width: `${(returning / total) * 100}%` }}
                  />
                </div>
                <p className="text-xs text-gray-600">{deployed} out · {returning} returning</p>
              </div>
            )
          })}
        </div>
      </div>

      {/* Task priority */}
      <TaskPriorityPanel
        tasks={state.missions.find(m => m.id === modal.missionId)?.tasks ?? []}
        priorityIds={modal.priorityTaskIds}
        onToggle={id => dispatch({ type: 'TOGGLE_TASK_PRIORITY', taskId: id })}
      />

      {/* Mode tabs */}
      <div className="flex gap-1">
        <button
          onClick={() => setManualMode(false)}
          className={`px-3 py-1 text-xs rounded font-medium transition-colors ${
            !manualMode ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-gray-200'
          }`}
        >
          Meta-Co-Pilot
        </button>
        <button
          onClick={() => setManualMode(true)}
          className={`px-3 py-1 text-xs rounded font-medium transition-colors ${
            manualMode ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-gray-200'
          }`}
        >
          Manual
        </button>
      </div>

      {/* Strategies or manual */}
      {!manualMode ? (
        <InlineStrategyCards
          strategies={modal.strategies}
          selectedIndex={modal.selectedIndex}
          editedAlloc={editedAlloc}
          editingIndex={editingIndex}
          reserve={reserve}
          onSelect={i => { dispatch({ type: 'SELECT_STRATEGY', strategyIndex: i }); setEditingIndex(null) }}
          onEdit={a => dispatch({ type: 'EDIT_ALLOCATION', allocation: a })}
          onToggleEdit={i => setEditingIndex(editingIndex === i ? null : i)}
        />
      ) : (
        <ManualAllocator
          reserve={reserve}
          allocation={manualAlloc}
          tasks={state.missions.find(m => m.id === modal.missionId)?.tasks ?? []}
          onChange={setManualAlloc}
        />
      )}

      {/* Footer */}
      <div className="flex items-center justify-between pt-2 border-t border-gray-700">
        <div className="text-xs text-gray-500">
          {canApply && !manualMode && selectedStrat && (
            <span>Applying <span className="text-gray-300">{selectedStrat.name}</span></span>
          )}
          {!canApply && !manualMode && <span>Select a strategy above</span>}
          {canApply && manualMode && <span className="text-gray-300">Manual allocation ready</span>}
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleDismiss}
            className="px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors"
          >
            Dismiss
          </button>
          <button
            onClick={handleApply}
            disabled={!canApply}
            className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed rounded text-xs font-semibold text-white transition-colors"
          >
            Apply
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Inline strategy cards ────────────────────────────────────────────────

function InlineStrategyCards({
  strategies, selectedIndex, editedAlloc, editingIndex, reserve, onSelect, onEdit, onToggleEdit,
}: {
  strategies: Strategy[]
  selectedIndex: number | null
  editedAlloc: AssetRequirement | null
  editingIndex: number | null
  reserve: AssetRequirement
  onSelect: (i: number) => void
  onEdit: (a: AssetRequirement) => void
  onToggleEdit: (i: number) => void
}) {
  if (strategies.length === 0) {
    return (
      <p className="text-xs text-gray-500 py-2 text-center">
        No feasible strategies with current reserve. Use Manual allocation.
      </p>
    )
  }

  return (
    <div className="grid grid-cols-2 gap-2">
      {strategies.map((s, i) => {
        const selected = selectedIndex === i
        const editing  = editingIndex === i && selected
        return (
          <div
            key={s.name}
            onClick={() => onSelect(i)}
            className={`rounded-lg border-2 p-2.5 cursor-pointer transition-all space-y-2 ${
              selected
                ? 'border-blue-500 bg-blue-950/40'
                : 'border-gray-700 bg-gray-800 hover:border-gray-500'
            }`}
          >
            <div>
              <div className="flex items-center gap-1 mb-0.5">
                {selected && <span className="text-blue-400 text-xs">✓</span>}
                <span className="font-bold text-white text-xs leading-tight">{s.name}</span>
              </div>
              <p className="text-xs text-gray-500 leading-snug">{s.description}</p>
            </div>

            <div>
              <span className="text-sm font-mono font-bold text-white">{fmtTime(s.expectedCompletionTime)}</span>
              <p className="text-xs text-gray-500">est. completion</p>
            </div>

            <div className="space-y-0.5">
              <p className="text-xs text-gray-500 uppercase tracking-wider">Need</p>
              {(['Blue', 'Red', 'Green'] as AssetType[]).filter(t => s.assets[t] > 0).map(t => (
                <div key={t} className="flex justify-between text-xs">
                  <span className={ASSET_COLORS[t]}>{DRONE_NAME[t]}</span>
                  <span className="text-white font-mono">{s.assets[t]}</span>
                </div>
              ))}
            </div>

            <div className="space-y-0.5">
              <p className="text-xs text-gray-500 uppercase tracking-wider">Reserve after</p>
              {(['Blue', 'Red', 'Green'] as AssetType[]).map(t => (
                <div key={t} className="flex justify-between text-xs">
                  <span className={ASSET_COLORS[t]}>{DRONE_NAME[t]}</span>
                  <span className={`font-mono ${s.reserveAfter[t] === 0 ? 'text-red-400' : 'text-gray-300'}`}>
                    {s.reserveAfter[t]}
                  </span>
                </div>
              ))}
            </div>

            <div className="space-y-1">
              <ScoreBar label="Speed" value={s.speedScore} color="bg-blue-500" />
              <ScoreBar label="Reserve" value={s.reserveScore} color="bg-green-500" />
            </div>

            {selected && (
              <button
                onClick={e => { e.stopPropagation(); onToggleEdit(i) }}
                className="w-full text-xs text-blue-400 hover:text-blue-200 py-0.5 border border-blue-700 rounded transition-colors"
              >
                {editing ? 'Cancel edit' : 'Modify assets'}
              </button>
            )}

            {editing && (
              <div onClick={e => e.stopPropagation()} className="space-y-1.5 border-t border-gray-700 pt-2">
                {(['Blue', 'Red', 'Green'] as AssetType[]).map(t => (
                  <AssetStepper
                    key={t}
                    type={t}
                    value={(editedAlloc ?? s.assets)[t]}
                    max={reserve[t]}
                    onChange={v => onEdit({ ...(editedAlloc ?? s.assets), [t]: v })}
                  />
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ─── Manual allocator ─────────────────────────────────────────────────────

function ManualAllocator({
  reserve, allocation, tasks, onChange,
}: {
  reserve: AssetRequirement
  allocation: AssetRequirement
  tasks: Task[]
  onChange: (a: AssetRequirement) => void
}) {
  const hasAny = allocation.Blue + allocation.Red + allocation.Green > 0
  const eta = hasAny ? previewAllocation(tasks, allocation) : null

  return (
    <div className="max-w-xs space-y-3">
      <p className="text-xs text-gray-500">Specify how many of each type to commit.</p>
      {(['Blue', 'Red', 'Green'] as AssetType[]).map(t => (
        <AssetStepper
          key={t}
          type={t}
          value={allocation[t]}
          max={reserve[t]}
          onChange={v => onChange({ ...allocation, [t]: v })}
        />
      ))}
      <div className="flex items-center gap-2 pt-1 border-t border-gray-700/50">
        <span className="text-xs text-gray-500">Est. completion:</span>
        <span className="text-sm font-mono font-bold text-white">
          {eta !== null ? fmtTime(eta) : '—'}
        </span>
      </div>
    </div>
  )
}

// ─── Asset stepper ────────────────────────────────────────────────────────

function AssetStepper({
  type, value, max, onChange,
}: {
  type: AssetType
  value: number
  max: number
  onChange: (v: number) => void
}) {
  return (
    <div className="flex items-center gap-2">
      <span className={`w-20 text-xs font-medium ${ASSET_COLORS[type]}`}>{DRONE_NAME[type]}</span>
      <button
        onClick={() => onChange(Math.max(0, value - 1))}
        className="w-6 h-6 rounded bg-gray-700 hover:bg-gray-600 text-white font-bold text-sm flex items-center justify-center"
      >−</button>
      <span className="w-5 text-center font-mono text-white font-bold text-xs">{value}</span>
      <button
        onClick={() => onChange(Math.min(max, value + 1))}
        className="w-6 h-6 rounded bg-gray-700 hover:bg-gray-600 text-white font-bold text-sm flex items-center justify-center"
      >+</button>
      <span className="text-xs text-gray-500">/ {max} avail</span>
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

// ─── Reserve panel ────────────────────────────────────────────────────────

function ReservePanel({ state, reserve }: { state: GameState; reserve: AssetRequirement }) {
  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-3 space-y-3">
      <p className="text-xs text-gray-500 uppercase tracking-wider">Reserve</p>
      {(['Blue', 'Red', 'Green'] as AssetType[]).map(type => {
        const total    = ASSET_TOTAL[type]
        const avail    = reserve[type]
        const deployed = state.assets.filter(a => a.type === type && a.status === 'deployed').length
        const returning = state.assets.filter(a => a.type === type && a.status === 'returning').length
        return (
          <div key={type} className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className={ASSET_COLORS[type]}>{DRONE_NAME[type]}</span>
              <span className="text-gray-400 font-mono">
                {avail} avail · {deployed} out · {returning} rtng
              </span>
            </div>
            <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden flex">
              <div
                className={`h-full ${ASSET_BAR_COLOR[type]} transition-all`}
                style={{ width: `${(avail / total) * 100}%` }}
              />
              <div
                className="h-full bg-gray-500 transition-all"
                style={{ width: `${(returning / total) * 100}%` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─── Forecast panel ───────────────────────────────────────────────────────

function ForecastPanel({ state }: { state: GameState }) {
  const f = state.categoryForecast
  const cats = ['A', 'B', 'C', 'D', 'E'] as MissionCategory[]
  const next = state.pendingBlueprints[0]
  const maxF = Math.max(...cats.map(c => f[c]), 0.01)

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-3 space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500 uppercase tracking-wider">Next mission forecast</p>
        {next && (
          <span className="text-xs text-gray-600 font-mono">
            in {formatSeconds(Math.max(0, next.arrivalTime - state.elapsed))}
          </span>
        )}
      </div>
      <div className="flex gap-1 items-end" style={{ height: '68px' }}>
        {cats.map(c => (
          <div key={c} className="flex-1 flex flex-col items-center gap-0.5">
            <div
              className={`w-full rounded-t transition-all ${CAT_BADGE[c].split(' ')[0]}`}
              style={{ height: `${Math.max(f[c] > 0 ? 2 : 0, Math.round((f[c] / maxF) * 52))}px` }}
            />
            <span className="text-xs text-gray-500" title={CAT_NAME[c]}>{c}</span>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-1 items-center justify-end">
        {cats.filter(c => f[c] > 0.05).map(c => (
          <span key={c} className={`text-xs px-1 rounded ${CAT_BADGE[c]}`}>
            {c} {Math.round(f[c] * 100)}%
          </span>
        ))}
      </div>
    </div>
  )
}


// ─── Utilities ────────────────────────────────────────────────────────────

function formatCountdown(elapsed: number): string {
  const rem = Math.max(0, 600 - elapsed)
  const m = Math.floor(rem / 60)
  const s = Math.floor(rem % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatSeconds(s: number): string {
  if (s < 60) return `${Math.round(s)}s`
  return `${Math.floor(s / 60)}m${Math.round(s % 60).toString().padStart(2, '0')}s`
}
