import { useState, useEffect, useRef, useMemo } from 'react'

import type { MapViewState, Asset, Mission, AssetType, TaskType, Task, PendingAllocation } from '../types'
import { HUB, MAP_W, MAP_H, ASSET_SPEED, droneLabel, TASK_PRIMARY, TASK_BASE_TIME, TASK_SUBSTITUTE, TASK_SUB_BASE_TIME } from '../utils/missionGen'
import { DRONE_ICON, TASK_ICON } from '../utils/icons'
import { computeTacticalSuggestion, computeRecoverySuggestion } from '../utils/tacticalSuggest'
import { tasksInCycles } from '../utils/scheduling'

// ─── Helpers ──────────────────────────────────────────────────────────────

function formatSeconds(s: number): string {
  if (s < 60) return `${Math.round(s)}s`
  return `${Math.floor(s / 60)}m${Math.round(s % 60).toString().padStart(2, '0')}s`
}

function missionEntryAngle(waypoint: { x: number; y: number }, cx: number, cy: number, r: number): number {
  const dx = waypoint.x - HUB.x, dy = waypoint.y - HUB.y
  const fx = HUB.x - cx, fy = HUB.y - cy
  const a = dx * dx + dy * dy
  const b = 2 * (fx * dx + fy * dy)
  const c = fx * fx + fy * fy - r * r
  const disc = b * b - 4 * a * c
  if (disc < 0 || a < 0.001) return Math.atan2(waypoint.y - cy, waypoint.x - cx)
  const t = (-b - Math.sqrt(disc)) / (2 * a)
  return Math.atan2(HUB.y + t * dy - cy, HUB.x + t * dx - cx)
}

function buildCompLabel(counts: { Blue: number; Red: number; Green: number }, req: { Blue: number; Red: number; Green: number }): string {
  const parts: string[] = []
  if (req.Blue > 0)  parts.push(`${counts.Blue}/${req.Blue}F`)
  if (req.Red > 0)   parts.push(`${counts.Red}/${req.Red}L`)
  if (req.Green > 0) parts.push(`${counts.Green}/${req.Green}C`)
  return parts.join(' ') || '—'
}

function compToLabel(comp: { Blue: number; Red: number; Green: number }, time: number): string {
  const parts: string[] = []
  if (comp.Blue > 0) parts.push(`${comp.Blue}F`)
  if (comp.Red > 0) parts.push(`${comp.Red}L`)
  if (comp.Green > 0) parts.push(`${comp.Green}C`)
  return `${parts.join(' + ')} (${time}s)`
}

// ─── Constants ────────────────────────────────────────────────────────────

const ASSET_COLOR: Record<AssetType, string> = {
  Blue:  '#60a5fa',
  Red:   '#f87171',
  Green: '#4ade80',
}

const TASK_TYPE_NAMES: Record<number, string> = {
  1: 'Recce', 2: 'Recon', 3: 'Supply Drop', 4: 'Prec Supply Drop', 5: 'Search & Service',
}

const CAT_NAMES: Record<string, string> = {
  A: 'Search', B: 'Recovery', C: 'Supply', D: 'Recon', E: 'Command',
}

// ─── Props ────────────────────────────────────────────────────────────────

interface Props {
  state: MapViewState
  onReprioritiseTop?: (missionId: string, taskId: string) => void
}

// ─── Main component ───────────────────────────────────────────────────────

export default function MapDisplay({ state, onReprioritiseTop: _onReprioritiseTop }: Props) {
  const [tacticalMissionId, setTacticalMissionId] = useState<string | null>(null)
  const [suggestLoading, setSuggestLoading] = useState(false)
  const channelRef = useRef<BroadcastChannel | null>(null)

  useEffect(() => {
    const ch = new BroadcastChannel('sar-study')
    channelRef.current = ch
    return () => ch.close()
  }, [])

  function handleMapAction(action: object) {
    channelRef.current?.postMessage(action)
  }

  // Auto-clear local selection when the selected mission is no longer pending/active
  useEffect(() => {
    setTacticalMissionId(prev => {
      if (!prev) return null
      const m = state.missions.find(m => m.id === prev)
      if (!m) return null
      if (!m.tacticalPending && !m.failureRecoveryPending && m.status !== 'active') return null
      return prev
    })
  }, [state.missions])

  const pending = state.missions.filter(m =>
    (m.tacticalPending && !!m.pendingAllocation) || m.failureRecoveryPending
  )

  const tacticalMission = tacticalMissionId
    ? state.missions.find(m => m.id === tacticalMissionId &&
        ((m.tacticalPending && !!m.pendingAllocation) || m.failureRecoveryPending || m.status === 'active')) ?? null
    : null

  const isRecovery = !!(tacticalMission?.failureRecoveryPending)
  const isReadOnly = !!tacticalMission && !isRecovery && !tacticalMission.tacticalPending && tacticalMission.status === 'active'
  let overrideAlloc: PendingAllocation | undefined
  let recoveryReserveIds: Set<string> | undefined
  let recoveryFailedDroneId: string | null = null
  if (tacticalMission && isRecovery) {
    const result = buildRecoveryAllocation(tacticalMission, state.assets)
    overrideAlloc = result.allocation
    recoveryReserveIds = result.reserveIds
    recoveryFailedDroneId = result.failedDroneId
  } else if (tacticalMission && isReadOnly) {
    overrideAlloc = buildActiveAllocation(tacticalMission, state.assets)
  }

  return (
    <div className="flex flex-col h-full bg-gray-950 overflow-hidden">
      {/* Tactical frame — amber ring + banner reinforces the within-mission decision tier */}
      <div className="pointer-events-none fixed inset-0 z-50 border-[5px] border-amber-500/70" />
      <div className="flex-none flex items-center gap-3 px-5 py-2 bg-amber-950/40 border-b-2 border-amber-700/60">
        <span className="text-sm font-extrabold uppercase tracking-[0.25em] text-amber-300 px-2.5 py-1 rounded bg-amber-950/70 border border-amber-600/60">
          Tactical
        </span>
        <span className="text-xs text-amber-200/70 uppercase tracking-wide">Within-mission drone → task assignment</span>
      </div>
      <div className="flex flex-1 overflow-hidden">
        <MissionQueuePanel
          pending={pending}
          selectedId={tacticalMissionId}
          onSelect={setTacticalMissionId}
          state={state}
          disabled={suggestLoading}
        />
        <div className="flex-1 min-w-0">
          {tacticalMission ? (
            <TacticalPlannerView
              mission={tacticalMission}
              state={state}
              onBack={() => setTacticalMissionId(null)}
              onMapAction={handleMapAction}
              overrideAllocation={overrideAlloc}
              recoveryMode={isRecovery}
              recoveryReserveIds={recoveryReserveIds}
              failedDroneId={recoveryFailedDroneId}
              readOnly={isReadOnly}
              onSuggestLoadingChange={setSuggestLoading}
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-full gap-2 text-gray-300">
              <p className="text-lg">Select a mission from the panel</p>
              {pending.length === 0 && (
                <p className="text-lg text-gray-400">No missions currently require tactical assignment</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}


// ─── Mission queue panel (persistent left sidebar) ────────────────────────

function MissionQueuePanel({ pending, selectedId, onSelect, state, disabled }: {
  pending: Mission[]
  selectedId: string | null
  onSelect: (id: string) => void
  state: MapViewState
  disabled?: boolean
}) {
  const active = state.missions.filter(m => m.status === 'active').length
  const queued = state.missions.filter(m => m.status === 'queued').length

  return (
    <div data-tutorial="tac-mission-list" className="flex flex-col w-64 flex-none bg-gray-900 border-r border-gray-800 h-full overflow-hidden">
      {/* Status bar */}
      <div className="flex-none px-3 py-2 border-b border-gray-800 space-y-0.5">
        <div className="text-lg font-semibold text-gray-400">Session {state.sessionNumber}/{state.numSessions}</div>
        <div className="text-lg text-gray-500">{active} active · {queued} queued</div>
        <div className="text-lg">
          Score: <span className="text-white font-mono font-bold">{state.score}</span>
          <span className="text-red-400 font-mono ml-1">−{state.penaltyAccrued}</span>
        </div>
        <div className="text-sm text-gray-600 font-mono">{formatSeconds(state.elapsed)}</div>
      </div>

      {/* Header */}
      <div className="flex-none px-3 pt-2 pb-1">
        <span className="text-sm text-gray-500 uppercase tracking-wider">
          Pending{pending.length > 0 ? ` (${pending.length})` : ''}
        </span>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-1">
        {pending.length === 0 ? (
          <p className="text-lg text-gray-700 text-center mt-4">No missions pending</p>
        ) : (
          <>
            {pending.map(m => {
              const isRecov = m.failureRecoveryPending
              const isSelected = m.id === selectedId
              const isLocked = !!disabled && !isSelected
              return (
                <button
                  key={m.id}
                  disabled={isLocked}
                  title={isLocked ? 'Wait for the current Suggest to finish before switching missions' : undefined}
                  onClick={() => { onSelect(m.id); document.dispatchEvent(new CustomEvent('tutorial-mission-selected')) }}
                  className={`relative w-full text-left px-3 py-2.5 rounded border-2 transition-colors ${isLocked ? 'opacity-60 cursor-not-allowed' : ''} ${
                    isSelected
                      ? isRecov
                        ? 'border-red-500 bg-red-900/40'
                        : 'border-yellow-500 bg-yellow-900/40'
                      : isRecov
                        ? 'border-red-500 bg-red-900/30 hover:bg-red-900/50'
                        : 'border-yellow-500 bg-yellow-900/30 hover:bg-yellow-900/50'
                  }`}
                >
                  {!isSelected && (
                    <div className={`absolute inset-0 rounded border-2 pointer-events-none animate-pulse ${isRecov ? 'border-red-400/60' : 'border-yellow-400/60'}`} />
                  )}
                  <div className="flex items-center justify-between gap-1">
                    <span className={`font-mono font-bold text-lg ${isRecov ? 'text-red-200' : 'text-yellow-200'}`}>{m.id}</span>
                    {isRecov ? (
                      <span className="px-1.5 py-0.5 bg-red-900/70 border border-red-600/70 rounded text-sm font-bold text-red-300">{m.recoveryReason === 'lockout' ? 'LOCKOUT' : 'FAIL'}</span>
                    ) : (
                      <span className="text-sm text-yellow-600">{m.pendingAllocation?.dronePool.length ?? 0} drones</span>
                    )}
                  </div>
                  <div className={`text-sm mt-0.5 ${isRecov ? 'text-red-400/80' : 'text-yellow-600/80'}`}>
                    Cat {m.category}
                    {!isRecov && m.pendingAllocation && ` · ${m.pendingAllocation.taskOrder.length} tasks`}
                    {isRecov && <span className="ml-1">reassign pending</span>}
                  </div>
                </button>
              )
            })}
          </>
        )}
      </div>
    </div>
  )
}

// ─── Timing computation ───────────────────────────────────────────────────

interface Timings {
  taskStarts: Record<string, number>
  droneWaits: Record<string, Record<string, number>>
}

function computeTimings(
  dronePool: string[],
  droneSequences: Record<string, string[]>,
  assignments: Record<string, string[]>,
  assets: Asset[],
  tasks: Mission['tasks'],
): Timings {
  const droneArrivals: Record<string, Record<string, number>> = {}
  for (const droneId of dronePool) {
    const asset = assets.find(a => a.id === droneId)
    if (!asset) continue
    const speed = ASSET_SPEED[asset.type]
    const seq = droneSequences[droneId] ?? []
    droneArrivals[droneId] = {}
    let prevPos = asset.position
    let prevTime = 0
    for (const taskId of seq) {
      const task = tasks.find(t => t.id === taskId)
      if (!task) continue
      const travel = Math.hypot(task.waypoint.x - prevPos.x, task.waypoint.y - prevPos.y) / speed
      droneArrivals[droneId][taskId] = prevTime + travel
      prevTime = droneArrivals[droneId][taskId] + task.baseTime
      prevPos = task.waypoint
    }
  }

  const taskStarts: Record<string, number> = {}
  const droneWaits: Record<string, Record<string, number>> = {}
  for (const taskId of Object.keys(assignments)) {
    const assigned = assignments[taskId] ?? []
    if (!assigned.length) continue
    const arrivals = assigned
      .map(id => droneArrivals[id]?.[taskId] ?? null)
      .filter((t): t is number => t !== null)
    if (!arrivals.length) continue
    const ts = Math.max(...arrivals)
    taskStarts[taskId] = ts
    droneWaits[taskId] = {}
    for (const id of assigned) {
      const arr = droneArrivals[id]?.[taskId]
      if (arr === undefined) continue
      const w = ts - arr
      if (w > 3) droneWaits[taskId][id] = Math.round(w)
    }
  }
  return { taskStarts, droneWaits }
}

// ─── Drone positions on zone boundary ────────────────────────────────────

function computeDronePositions(
  dronePool: string[],
  assignments: Record<string, string[]>,
  taskOrder: string[],
  mission: Mission,
): Record<string, { x: number; y: number }> {
  if (dronePool.length === 0) return {}
  const { zoneCenter: { x: cx, y: cy }, zoneRadius: r } = mission
  const hubAngle = Math.atan2(HUB.y - cy, HUB.x - cx)
  const droneR = r + 28  // all drones at this radius from zone center
  const TWO_PI = Math.PI * 2

  // Desired angle: assigned → entry angle of first task; unassigned → hub angle
  const desiredAngles: Record<string, number> = {}
  for (const id of dronePool) {
    const firstTid = taskOrder.find(tid => (assignments[tid] ?? []).includes(id))
    if (firstTid) {
      const task = mission.tasks.find(t => t.id === firstTid)!
      desiredAngles[id] = missionEntryAngle(task.waypoint, cx, cy, r)
    } else {
      desiredAngles[id] = hubAngle
    }
  }

  // Sort by normalized desired angle
  const norm = (a: number) => ((a % TWO_PI) + TWO_PI) % TWO_PI
  const sorted = [...dronePool].sort((a, b) => norm(desiredAngles[a]) - norm(desiredAngles[b]))

  // Minimum angular gap so icon circles don't touch — add clearance
  const minGap = Math.min(22 / droneR, TWO_PI / sorted.length)

  // Unwrap angles monotonically
  const angles = sorted.map(id => norm(desiredAngles[id]))
  for (let i = 1; i < sorted.length; i++) {
    while (angles[i] < angles[i - 1]) angles[i] += TWO_PI
  }

  // Forward pass: enforce minimum gap
  for (let i = 1; i < sorted.length; i++) {
    if (angles[i] < angles[i - 1] + minGap) angles[i] = angles[i - 1] + minGap
  }

  // If total span exceeds available arc, compress
  const span = sorted.length > 1 ? angles[sorted.length - 1] - angles[0] : 0
  const maxSpan = TWO_PI - minGap
  if (span > maxSpan) {
    const scale = maxSpan / span
    for (let i = 1; i < sorted.length; i++) angles[i] = angles[0] + (angles[i] - angles[0]) * scale
  }

  // Centre: shift so the median drone sits at its desired angle (minimises drift)
  const mid = Math.floor(sorted.length / 2)
  const shift = norm(desiredAngles[sorted[mid]]) - angles[mid]
  for (let i = 0; i < sorted.length; i++) angles[i] += shift

  const positions: Record<string, { x: number; y: number }> = {}
  for (let i = 0; i < sorted.length; i++) {
    positions[sorted[i]] = { x: cx + droneR * Math.cos(angles[i]), y: cy + droneR * Math.sin(angles[i]) }
  }
  return positions
}

// Physically-present drones per task: a freed lockout drone is parked at the task waypoint it
// deadlocked on, so matching each drone to its nearest task waypoint tells us who actually reached
// where. Used to surface the "right now" allocation (distinct from the planned assignment) both on
// the map and in the right panel during a lockout recovery.
function computePresentByTask(
  dronePool: string[],
  taskOrder: string[],
  tasks: Task[],
  assets: Asset[],
): Record<string, { Blue: number; Red: number; Green: number }> {
  const out: Record<string, { Blue: number; Red: number; Green: number }> = {}
  const pts = taskOrder
    .map(tid => { const t = tasks.find(x => x.id === tid); return t ? { tid, wp: t.waypoint } : null })
    .filter((x): x is { tid: string; wp: { x: number; y: number } } => x !== null)
  for (const id of dronePool) {
    const a = assets.find(x => x.id === id)
    if (!a) continue
    let best: { tid: string; d: number } | null = null
    for (const { tid, wp } of pts) {
      const d = Math.hypot(a.position.x - wp.x, a.position.y - wp.y)
      if (!best || d < best.d) best = { tid, d }
    }
    if (best && best.d < 20) (out[best.tid] ??= { Blue: 0, Red: 0, Green: 0 })[a.type]++
  }
  return out
}

// ─── Active-mission view-only allocation ─────────────────────────────────

function buildActiveAllocation(mission: Mission, assets: Asset[]): PendingAllocation {
  const activeTasks = mission.tasks.filter(t => t.status !== 'completed' && t.status !== 'failed')
  const statusPriority: Record<string, number> = { executing: 0, traveling: 1, pending: 2 }
  const taskOrder = [...activeTasks]
    .sort((a, b) => (statusPriority[a.status] ?? 3) - (statusPriority[b.status] ?? 3) || b.type - a.type)
    .map(t => t.id)
  const dronePoolSet = new Set<string>()
  const taskAssignments: Record<string, string[]> = {}
  for (const task of activeTasks) {
    taskAssignments[task.id] = [...task.assignedAssetIds]
    for (const id of task.assignedAssetIds) dronePoolSet.add(id)
  }
  // Include any deployed drones returning from completed tasks
  for (const a of assets) {
    if (a.currentMissionId === mission.id && a.status === 'deployed') dronePoolSet.add(a.id)
  }
  return {
    strategyName: 'Manual',
    composition: { Blue: 0, Red: 0, Green: 0 },
    dronePool: [...dronePoolSet],
    taskAssignments,
    taskOrder,
    expectedCompletionTime: 0,
    isAgentSuggested: false,
    isBadSuggestion: false,
    badSuggestionType: null,
    hasTacticalError: false,
    suppressedTaskId: null,
  }
}

// ─── Recovery allocation builder ─────────────────────────────────────────

function buildRecoveryAllocation(mission: Mission, assets: Asset[]): { allocation: PendingAllocation; reserveIds: Set<string>; failedDroneId: string | null } {
  // Only deployed mission drones — operators fix failures with their subswarm, not reserve
  const deployedDrones = assets.filter(a =>
    a.currentMissionId === mission.id && a.status === 'deployed'
  )

  const reserveIds = new Set<string>()  // no reserve access during failure recovery
  const dronePool = deployedDrones.map(a => a.id)
  const dronePoolSet = new Set(dronePool)

  // All non-completed tasks — sorted for display
  const statusPriority: Record<string, number> = { executing: 0, traveling: 1, pending: 2 }
  const taskOrder = mission.tasks
    .filter(t => t.status !== 'completed' && t.status !== 'failed')
    .sort((a, b) => (statusPriority[a.status] ?? 3) - (statusPriority[b.status] ?? 3) || b.type - a.type)
    .map(t => t.id)

  // Pre-populate from task.assignedAssetIds — preserves the full chain; the failed drone
  // was already filtered out of assignedAssetIds by the reducer at failure time
  const taskAssignments: Record<string, string[]> = {}
  for (const tid of taskOrder) {
    const task = mission.tasks.find(t => t.id === tid)!
    taskAssignments[tid] = task.assignedAssetIds.filter(id => dronePoolSet.has(id))
  }

  return {
    allocation: {
      strategyName: 'Manual',
      composition: { Blue: 0, Red: 0, Green: 0 },
      dronePool,
      taskAssignments,
      taskOrder,
      expectedCompletionTime: 0,
      isAgentSuggested: false,
      isBadSuggestion: false,
      badSuggestionType: null,
      hasTacticalError: false,
      suppressedTaskId: null,
    },
    reserveIds,
    failedDroneId: mission.failedDroneId,
  }
}

// ─── Tactical planner (SVG + right panel) ────────────────────────────────

function TacticalPlannerView({ mission, state, onBack, onMapAction, overrideAllocation, recoveryMode, recoveryReserveIds, failedDroneId, readOnly, onSuggestLoadingChange }: {
  mission: Mission
  state: MapViewState
  onBack: () => void
  onMapAction: (action: object) => void
  overrideAllocation?: PendingAllocation
  recoveryMode?: boolean
  recoveryReserveIds?: Set<string>
  failedDroneId?: string | null
  readOnly?: boolean
  onSuggestLoadingChange?: (loading: boolean) => void
}) {
  const pending = overrideAllocation ?? mission.pendingAllocation!

  // Recovery / read-only views pre-populate from the existing plan stored in pendingAllocation —
  // including a LOCKOUT recovery, which loads the CURRENT (deadlocked) plan so the operator sees
  // and edits what actually deadlocked. It's kept legible (not read as auto-fixed) by the "now"
  // present indicators and a red "!" on every task still stuck waiting for drones. A NEW tactical
  // plan starts empty so the operator assigns manually or via "Suggest".
  const startsEmpty = !recoveryMode && !readOnly
  function buildInitialAssignments(): Record<string, string[]> {
    if (!startsEmpty) {
      return Object.fromEntries(Object.entries(pending.taskAssignments).map(([k, v]) => [k, [...v]]))
    }
    return Object.fromEntries(Object.keys(pending.taskAssignments).map(k => [k, []]))
  }

  // Lockout recovery seeds the chain order from the mission's existing (cyclic) sequences, so the
  // planner shows the ACTUAL deadlocked plan — the cycle is then detectable and Deploy is blocked
  // until the operator breaks it. Every other flow starts with no explicit order (canonical fallback).
  function buildInitialChainOrder(): Record<string, string[]> {
    if (!(recoveryMode && mission.recoveryReason === 'lockout')) return {}
    const poolSet = new Set(pending.dronePool)
    const taskSet = new Set(pending.taskOrder)
    const out: Record<string, string[]> = {}
    for (const [id, seq] of Object.entries(mission.droneSequences ?? {})) {
      if (!poolSet.has(id)) continue
      const f = seq.filter(t => taskSet.has(t))
      if (f.length > 0) out[id] = f
    }
    return out
  }

  const [assignments, setAssignments] = useState<Record<string, string[]>>(buildInitialAssignments)
  // droneChainOrder: droneId → taskIds in the order the user assigned them (not strategic order)
  const [droneChainOrder, setDroneChainOrder] = useState<Record<string, string[]>>(buildInitialChainOrder)
  const [suggestQueue, setSuggestQueue] = useState<Array<{ taskId: string; droneId: string }>>([])
  // Recovery only: whether the operator consulted the agent's fix via "Suggest" before confirming.
  const [recoverySuggestUsed, setRecoverySuggestUsed] = useState(false)
  const isSuggestLoading = suggestQueue.length > 0
  useEffect(() => {
    onSuggestLoadingChange?.(isSuggestLoading)
    // TacticalTutorial lives in a sibling component tree (no shared props) — broadcast via a
    // DOM event so it can gate the "Next" button until the Suggest animation finishes.
    document.dispatchEvent(new CustomEvent('tutorial-suggest-loading', { detail: isSuggestLoading }))
    return () => onSuggestLoadingChange?.(false)
  }, [isSuggestLoading]) // eslint-disable-line react-hooks/exhaustive-deps
  const [dragging, setDragging] = useState<{ droneId: string; svgX: number; svgY: number } | null>(null)
  const [hoverTask, setHoverTask] = useState<string | null>(null)
  const [hoverDrone, setHoverDrone] = useState<string | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [containerSize, setContainerSize] = useState({ w: 1200, h: 800 })
  const recoveryReserveIdsRef = useRef<Set<string> | undefined>(recoveryReserveIds)
  const failedDroneIdRef = useRef<string | null | undefined>(failedDroneId)

  useEffect(() => {
    const ro = new ResizeObserver(entries => {
      const e = entries[0]
      setContainerSize({ w: e.contentRect.width, h: e.contentRect.height })
    })
    if (containerRef.current) ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [])

  // Reset when pending pool/order changes
  const pendingKey = pending.dronePool.join(',') + pending.taskOrder.join(',')
  const prevKey = useRef(pendingKey)
  useEffect(() => {
    if (prevKey.current !== pendingKey) {
      setAssignments(buildInitialAssignments())
      setDroneChainOrder(buildInitialChainOrder())
      setRecoverySuggestUsed(false)
      prevKey.current = pendingKey
    }
  }, [pendingKey])

  // Return to waiting when deployed / recovery resolved (not for read-only active-mission views)
  const onBackRef = useRef(onBack)
  onBackRef.current = onBack
  const initiallyReadOnly = useRef(readOnly)
  useEffect(() => {
    if (initiallyReadOnly.current) return
    if (recoveryMode ? !mission.failureRecoveryPending : !mission.tacticalPending) onBackRef.current()
  }, [mission.tacticalPending, mission.failureRecoveryPending, recoveryMode])

  // Zone geometry — computed before dronePositions so recovery HUB corner can reference them
  const { x: cx, y: cy } = mission.zoneCenter
  const r = mission.zoneRadius
  const hubAngle = Math.atan2(HUB.y - cy, HUB.x - cx)
  const hubEdgeX = cx + r * Math.cos(hubAngle)
  const hubEdgeY = cy + r * Math.sin(hubAngle)
  const hubLabelX = cx + (r + 22) * Math.cos(hubAngle)
  const hubLabelY = cy + (r + 22) * Math.sin(hubAngle)
  // Recovery mode: fixed anchor in HUB direction for reserve drones
  const hubCornerX = cx + Math.cos(hubAngle) * (r + 80)
  const hubCornerY = cy + Math.sin(hubAngle) * (r + 80)

  // Drone sequences: droneId → taskIds in the order the user assigned them
  const droneSequences = useMemo(() => {
    const seqs: Record<string, string[]> = {}
    for (const id of pending.dronePool) {
      const userOrder = droneChainOrder[id]
      if (userOrder && userOrder.length > 0) {
        seqs[id] = userOrder.filter(tid => (assignments[tid] ?? []).includes(id))
      } else {
        seqs[id] = pending.taskOrder.filter(tid => (assignments[tid] ?? []).includes(id))
      }
    }
    return seqs
  }, [assignments, droneChainOrder, pending.dronePool, pending.taskOrder])

  // Drone icon positions — stable while user reassigns; only recalculates when pool/order changes
  const dronePositions = useMemo(() => {
    const positions = computeDronePositions(pending.dronePool, pending.taskAssignments, pending.taskOrder, mission)
    if (recoveryMode && recoveryReserveIdsRef.current) {
      // Arrange reserve drones in a compact grid at hub corner, grouped by type
      const reserveArr = pending.dronePool.filter(id => recoveryReserveIdsRef.current!.has(id))
      const perpAngle = hubAngle + Math.PI / 2
      const colSpacing = 11   // perpendicular to hub angle
      const rowSpacing = 13   // along hub angle (away from zone)
      const maxCols = Math.min(reserveArr.length, 6)
      reserveArr.forEach((id, i) => {
        const col = i % maxCols
        const row = Math.floor(i / maxCols)
        const perpOff = (col - (maxCols - 1) / 2) * colSpacing
        const hubDirOff = row * rowSpacing
        positions[id] = {
          x: hubCornerX + Math.cos(perpAngle) * perpOff + Math.cos(hubAngle) * hubDirOff,
          y: hubCornerY + Math.sin(perpAngle) * perpOff + Math.sin(hubAngle) * hubDirOff,
        }
      })
    }
    return positions
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingKey])

  // Timings
  const timings = useMemo(
    () => computeTimings(pending.dronePool, droneSequences, assignments, state.assets, mission.tasks),
    [pending.dronePool, droneSequences, assignments, state.assets, mission.tasks]
  )

  // Lockout recovery: which tasks in the CURRENT plan are genuinely blocking each other (on a
  // dependency cycle)? Only these get the red "!" — a task merely starved of drones stuck upstream
  // (e.g. an S&S waiting on a Blue that isn't itself contended) is NOT flagged. While any cycle
  // remains the deadlock is unresolved and Deploy stays blocked until the operator breaks it (by
  // reordering drones or clicking Suggest). The planner is seeded with the actual deadlocked order,
  // so a freshly-opened lockout starts blocked; this is what stops it reading as "already fixed",
  // and because it's derived from the live plan, breaking the cycle clears the flags immediately.
  const lockoutRecovery = !!recoveryMode && mission.recoveryReason === 'lockout'
  const cycleTasks = useMemo(
    () => lockoutRecovery ? tasksInCycles(assignments, droneSequences) : new Set<string>(),
    [lockoutRecovery, assignments, droneSequences]
  )
  const hasUnresolvedDeadlock = cycleTasks.size > 0

  // ViewBox: tight around zone + all drone icons (dynamic margin)
  const maxDroneExtent = Object.values(dronePositions).reduce(
    (max, pos) => Math.max(max, Math.hypot(pos.x - cx, pos.y - cy)),
    r + 30
  )
  const margin = Math.max(22, maxDroneExtent - r + 12)
  const aspect = containerSize.w / containerSize.h
  const halfW = (r + margin) * Math.max(1, aspect)
  const halfH = (r + margin) * Math.max(1, 1 / aspect)
  const vx = cx - halfW, vy = cy - halfH, vw = halfW * 2, vh = halfH * 2

  // Deploy readiness — accepts primary OR substitute composition.
  // Greedy plans one step ahead, so only the FIRST task must be covered to deploy; the rest
  // are filled by replanning. Other modes require every task covered.
  // Suppressed task (tactical error) is exempt: it appears allocated so Deploy stays enabled.
  // Recovery mode always validates all tasks — the greedy "first task only" shortcut doesn't apply
  const deployCheckTasks = (state.tacticalMode === 'greedy' && !recoveryMode) ? pending.taskOrder.slice(0, 1) : pending.taskOrder
  const canDeploy = !hasUnresolvedDeadlock && deployCheckTasks.every(tid => {
    if (pending.hasTacticalError && tid === pending.suppressedTaskId) return true  // deceptively "complete"
    const task = mission.tasks.find(t => t.id === tid)!
    const prim = TASK_PRIMARY[task.type as TaskType]
    const sub = TASK_SUBSTITUTE[task.type as TaskType]
    const assigned = assignments[tid] ?? []
    const counts = { Blue: 0, Red: 0, Green: 0 }
    for (const id of assigned) {
      const tp = state.assets.find(a => a.id === id)?.type ?? 'Blue'
      counts[tp as AssetType]++
    }
    const meetsPrim = counts.Blue >= prim.Blue && counts.Red >= prim.Red && counts.Green >= prim.Green
    const meetsSub = !!sub && counts.Blue >= sub.Blue && counts.Red >= sub.Red && counts.Green >= sub.Green
    return meetsPrim || meetsSub
  })

  // Lockout recovery only: which drones are physically parked at each task "right now". Shown
  // alongside the planned composition so the operator can read the deadlock's real state.
  const presentByTask = useMemo(
    () => lockoutRecovery ? computePresentByTask(pending.dronePool, pending.taskOrder, mission.tasks, state.assets) : {},
    [lockoutRecovery, pending.dronePool, pending.taskOrder, mission.tasks, state.assets]
  )

  // Fire tutorial-plan-complete on the rising edge of canDeploy
  const prevCanDeployRef = useRef(false)
  useEffect(() => {
    if (canDeploy && !prevCanDeployRef.current) {
      document.dispatchEvent(new CustomEvent('tutorial-plan-complete'))
    }
    prevCanDeployRef.current = canDeploy
  }, [canDeploy])

  // Unified move/chain handler — maintains droneChainOrder so sequences follow assignment order.
  // Deadlocking chains (e.g. Fast task1→task2 while Lifter task2→task1) are intentionally NOT
  // blocked here — the operator is free to build any plan; a genuine deadlock is detected and
  // failed live in the reducer (findSchedulingCycle in TICK) once the drones are actually stuck.
  function moveDrone(droneId: string, taskId: string, chain: boolean) {
    if (!readOnly) onMapAction({ _mapAction: 'TACTICAL_ASSIGN_CHANGED', missionId: mission.id, op: chain ? 'chain' : 'assign', droneId, taskId, recoveryMode })
    setAssignments(prev => {
      if (!chain) {
        const next = Object.fromEntries(
          Object.entries(prev).map(([tid, ids]) => [tid, ids.filter(id => id !== droneId)])
        )
        if (!(next[taskId] ?? []).includes(droneId)) {
          next[taskId] = [...(next[taskId] ?? []), droneId]
        }
        return next
      } else {
        if ((prev[taskId] ?? []).includes(droneId)) return prev
        return { ...prev, [taskId]: [...(prev[taskId] ?? []), droneId] }
      }
    })
    // Seed from the drone's CURRENT effective sequence when it has no explicit chain order
    // yet — the same fallback `droneSequences` uses. "Suggest" fills `assignments` without
    // ever touching `droneChainOrder`, so chaining a Suggest-placed drone used to rewrite its
    // whole sequence as just [taskId], silently dropping the task it was already on:
    // buildManualAssignments only schedules tasks that appear in some drone's sequence, so
    // that task was committed with no start time and never dispatched (the planner still
    // showed it staffed and Deploy stayed enabled).
    const existingSeq = droneChainOrder[droneId] ?? pending.taskOrder.filter(tid => (assignments[tid] ?? []).includes(droneId))
    const chainIsNoop = chain && existingSeq.includes(taskId)
    setDroneChainOrder(prev => {
      if (!chain) return { ...prev, [droneId]: [taskId] }
      const existing = prev[droneId] ?? pending.taskOrder.filter(tid => (assignments[tid] ?? []).includes(droneId))
      if (existing.includes(taskId)) return prev
      return { ...prev, [droneId]: [...existing, taskId] }
    })
    // Tutorial signals are dispatched OUTSIDE the state updater. React re-invokes updater
    // functions (StrictMode does it every render in dev), so a dispatch placed inside fired
    // 2–4× per drag: `tac-manual` then advanced two steps and skipped the whole `tac-chain`
    // lesson, and `tac-chain` was satisfied by a single Shift+drag instead of two.
    if (!chain) document.dispatchEvent(new CustomEvent('tutorial-drone-assigned'))
    else if (!chainIsNoop) document.dispatchEvent(new CustomEvent('tutorial-drone-chained'))
  }

  function removeDrone(droneId: string, taskId: string) {
    if (!readOnly) onMapAction({ _mapAction: 'TACTICAL_ASSIGN_CHANGED', missionId: mission.id, op: 'remove', droneId, taskId, recoveryMode })
    setAssignments(prev => ({
      ...prev,
      [taskId]: (prev[taskId] ?? []).filter(id => id !== droneId),
    }))
    setDroneChainOrder(prev => ({
      ...prev,
      [droneId]: (prev[droneId] ?? []).filter(tid => tid !== taskId),
    }))
  }

  function unassignDrone(droneId: string) {
    if (!readOnly) onMapAction({ _mapAction: 'TACTICAL_ASSIGN_CHANGED', missionId: mission.id, op: 'unassign', droneId, taskId: null, recoveryMode })
    setAssignments(prev =>
      Object.fromEntries(
        Object.entries(prev).map(([tid, ids]) => [tid, ids.filter(id => id !== droneId)])
      )
    )
    setDroneChainOrder(prev => ({ ...prev, [droneId]: [] }))
  }

  function toSVG(e: React.PointerEvent<SVGSVGElement>): { x: number; y: number } {
    const rect = e.currentTarget.getBoundingClientRect()
    return {
      x: (e.clientX - rect.left) / rect.width * vw + vx,
      y: (e.clientY - rect.top) / rect.height * vh + vy,
    }
  }

  function handleDeploy() {
    if (recoveryMode) {
      onMapAction({ _mapAction: 'CONFIRM_FAILURE_RECOVERY', missionId: mission.id, taskAssignments: assignments, droneSequences, wasAgentSuggested: recoverySuggestUsed })
    } else {
      onMapAction({ _mapAction: 'CONFIRM_TACTICAL', missionId: mission.id, taskAssignments: assignments, droneSequences })
    }
  }

  function handleReset() {
    setSuggestQueue([])
    setAssignments(buildInitialAssignments())
    setDroneChainOrder(buildInitialChainOrder())   // lockout: restores the shown (deadlocked) order
    setRecoverySuggestUsed(false)
  }

  function handleStopSuggest() {
    setSuggestQueue([])
  }

  function handleSuggest() {
    // Lockout: if the current allocation already staffs every pending task (the usual deadlock case
    // — tasks fully staffed, just cyclically ordered), BUILD ON IT: keep the exact assignment and
    // only untangle the order (clear chain order → canonical → acyclic), rather than reassigning
    // from scratch. Falls through to a full re-plan only if the current allocation is incomplete.
    if (lockoutRecovery) {
      const pendingIds = pending.taskOrder.filter(tid => mission.tasks.find(t => t.id === tid)?.status === 'pending')
      const meetsComp = (tid: string) => {
        const task = mission.tasks.find(t => t.id === tid)!
        const prim = TASK_PRIMARY[task.type as TaskType]
        const sub = TASK_SUBSTITUTE[task.type as TaskType]
        const c = { Blue: 0, Red: 0, Green: 0 }
        for (const id of (assignments[tid] ?? [])) c[(state.assets.find(a => a.id === id)?.type ?? 'Blue') as AssetType]++
        const mp = c.Blue >= prim.Blue && c.Red >= prim.Red && c.Green >= prim.Green
        const ms = !!sub && c.Blue >= sub.Blue && c.Red >= sub.Red && c.Green >= sub.Green
        return mp || ms
      }
      if (pendingIds.length > 0 && pendingIds.every(meetsComp)) {
        setDroneChainOrder({})            // untangle in place — canonical order is acyclic
        setRecoverySuggestUsed(true)
        if (!readOnly) onMapAction({ _mapAction: 'TACTICAL_SUGGEST', missionId: mission.id, recoveryMode: true })
        document.dispatchEvent(new CustomEvent('tutorial-suggest-clicked'))
        return
      }
    }

    const greedy = state.tacticalMode === 'greedy'
    // Recovery: the agent only re-plans the tasks still needing coverage using the idle drones.
    // Normal tactical: the agent plans the whole mission from the committed pool.
    const suggestion = recoveryMode
      ? computeRecoverySuggestion(mission, pending, state.assets)
      : computeTacticalSuggestion(pending.dronePool, pending.taskOrder, mission.tasks, state.assets, greedy)
    // Re-apply tactical error: keep the same task suppressed even after re-suggesting
    if (pending.hasTacticalError && pending.suppressedTaskId) {
      delete suggestion[pending.suppressedTaskId]
    }
    // Flatten to one entry per drone, ordered by task priority then drone order within each task
    const entries: Array<{ taskId: string; droneId: string }> = []
    for (const tid of pending.taskOrder) {
      for (const droneId of (suggestion[tid] ?? [])) {
        entries.push({ taskId: tid, droneId })
      }
    }
    if (recoveryMode) {
      // Keep the current plan for tasks the agent doesn't re-plan (in-progress tasks); only the
      // tasks it fixes are cleared, then re-revealed progressively. Preserves "show the current
      // plan" while swapping in the agent's proposed fix for the broken part.
      // NOTE: do NOT strip suggested drones from the kept tasks — a chained recovery legitimately
      // reuses the same drone across several tasks (that's the whole point of chaining), so a
      // shared drone must be allowed to appear on both a kept task and a re-planned one. Stripping
      // it wiped kept tasks that shared drones with the fix, leaving them empty and undeployable.
      const suggestedTasks = new Set(entries.map(e => e.taskId))
      const suggestedDrones = new Set(entries.map(e => e.droneId))
      setAssignments(prev => Object.fromEntries(
        Object.entries(prev).filter(([tid]) => !suggestedTasks.has(tid))
      ))
      setDroneChainOrder(prev => Object.fromEntries(
        Object.entries(prev).filter(([id]) => !suggestedDrones.has(id))
      ))
      setRecoverySuggestUsed(true)
    } else {
      setAssignments({})
      setDroneChainOrder({})
    }
    setSuggestQueue(entries)
    document.dispatchEvent(new CustomEvent('tutorial-suggest-clicked'))
    // Log that the operator consulted the tactical agent (the planner starts empty; this is the
    // only way the agent's plan enters it). Recovery consultation is logged here too: relying on
    // `recoverySuggestUsed` alone lost it whenever the pending pool changed mid-recovery.
    if (!readOnly) {
      onMapAction({ _mapAction: 'TACTICAL_SUGGEST', missionId: mission.id, recoveryMode })
    }
  }

  // Progressive reveal: add one drone every 2 s until queue is empty
  useEffect(() => {
    if (suggestQueue.length === 0) return
    const timer = window.setTimeout(() => {
      const [{ taskId, droneId }, ...rest] = suggestQueue
      setAssignments(prev => ({ ...prev, [taskId]: [...(prev[taskId] ?? []), droneId] }))
      setSuggestQueue(rest)
    }, 1000)
    return () => clearTimeout(timer)
  }, [suggestQueue])

  return (
    <div className="flex flex-col h-full bg-gray-950">
      {/* Header */}
      <div data-tutorial="tac-header" className="flex items-center gap-4 px-6 py-4 bg-gray-900 border-b border-gray-800 flex-none">
        <button onClick={onBack} className="text-lg text-gray-400 hover:text-white transition-colors">← Back</button>
        <div className="h-8 w-px bg-gray-700" />
        <span className="font-mono text-xl text-white font-bold">{mission.id}</span>
        <span className="text-lg text-gray-400">Cat {mission.category} · {CAT_NAMES[mission.category] ?? ''}</span>
        {recoveryMode ? (
          <span className="text-lg px-2.5 py-1 rounded bg-red-900/40 text-red-300 border border-red-700/50">⚠ DRONE FAILURE — Reassign</span>
        ) : readOnly ? (
          <span className="text-lg px-2.5 py-1 rounded bg-gray-700/60 text-gray-400 border border-gray-600/50">View Only</span>
        ) : (
          <span className="text-lg px-2.5 py-1 rounded bg-yellow-900/40 text-yellow-300 border border-yellow-700/50">Tactical View</span>
        )}
        <div className="flex-1" />
        {!readOnly && <span className="text-lg text-gray-500">Drag → assign · Shift+drag → chain · hover a drone for its full path</span>}
        {!readOnly && <button onClick={handleReset} className="px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 text-lg transition-colors">Reset</button>}
        {/* Suggest stays available in every mode, including the tutorial's recovery step. It used
            to be hidden there to force manual practice, but the recovery panel's own copy tells the
            operator to "click Suggest for a fix" — and when the surviving drones have already flown
            home there is nothing to drag, so hiding it left the step unsatisfiable. */}
        {!readOnly && state.mode === 'agent' && (
          <button data-tutorial="tac-suggest-btn" onClick={handleSuggest} disabled={isSuggestLoading}
            className="px-4 py-3 bg-purple-800 hover:bg-purple-700 disabled:opacity-60 disabled:cursor-not-allowed rounded text-purple-200 text-lg transition-colors flex items-center gap-1.5">
            {isSuggestLoading
              ? <><span className="w-3 h-3 rounded-full border border-purple-400 border-t-transparent animate-spin inline-block" />Suggesting…</>
              : 'Suggest'}
          </button>
        )}
        {!readOnly && !recoveryMode && (
          <button onClick={() => onMapAction({ _mapAction: 'OVERRIDE_TACTICAL', missionId: mission.id })}
            className="px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 text-lg transition-colors">Abort Mission</button>
        )}
      </div>

      {/* Body: SVG + right panel */}
      <div className="flex-1 flex overflow-hidden">
        {/* SVG area */}
        <div data-tutorial="tac-svg-container" ref={containerRef} className="flex-1 overflow-hidden relative">
          <svg
            ref={svgRef}
            viewBox={`${vx} ${vy} ${vw} ${vh}`}
            className="w-full h-full"
            preserveAspectRatio="none"
            onPointerDown={e => {
              if (readOnly) return
              const el = (e.target as Element).closest('[data-drone]')
              if (!el) return
              const droneId = el.getAttribute('data-drone')!
              e.currentTarget.setPointerCapture(e.pointerId)
              const { x, y } = toSVG(e)
              setDragging({ droneId, svgX: x, svgY: y })
            }}
            onPointerMove={e => {
              if (!dragging) return
              const { x, y } = toSVG(e)
              setDragging(prev => prev ? { ...prev, svgX: x, svgY: y } : null)
              let closest: string | null = null, minD = 18
              for (const task of mission.tasks) {
                if (task.status === 'completed') continue
                const d = Math.hypot(x - task.waypoint.x, y - task.waypoint.y)
                if (d < minD) { minD = d; closest = task.id }
              }
              setHoverTask(closest)
            }}
            onPointerUp={e => {
              if (!dragging) return
              if (hoverTask) {
                moveDrone(dragging.droneId, hoverTask, e.shiftKey)
              } else if (e.shiftKey) {
                // Shift+drag to empty space: back out only the final hop of this drone's path.
                const seq = droneSequences[dragging.droneId] ?? []
                const last = seq[seq.length - 1]
                if (last) removeDrone(dragging.droneId, last)
              } else {
                // Normal drag to empty space: clear the drone's whole path.
                unassignDrone(dragging.droneId)
              }
              setDragging(null)
              setHoverTask(null)
            }}
          >
            <defs>
              <marker id="arr-blue" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="#60a5fa" />
              </marker>
              <marker id="arr-red" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="#f87171" />
              </marker>
              <marker id="arr-green" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="#4ade80" />
              </marker>
              <marker id="arr-drag" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="#94a3b8" />
              </marker>
            </defs>

            {/* Terrain background — same /map-bg.jpg in world coords as the strategic map.
                The dynamic viewBox here crops it to this mission zone, so it's a true
                zoomed-in view of the same landscape, aligned to the strategic map. */}
            <image href="/map-bg.jpg" x="0" y="0" width={MAP_W} height={MAP_H} preserveAspectRatio="none" />
            <rect x="0" y="0" width={MAP_W} height={MAP_H} fill="#0b1220" opacity="0.28" />

            {/* Zone */}
            <circle cx={cx} cy={cy} r={r} fill="rgba(11,18,32,0.34)" stroke="#3b82f6" strokeWidth="2" />

            {/* HUB indicator */}
            <line x1={cx} y1={cy} x2={hubEdgeX} y2={hubEdgeY} stroke="#64748b" strokeWidth="1" strokeDasharray="5 3" />
            <line x1={hubEdgeX} y1={hubEdgeY} x2={hubLabelX} y2={hubLabelY} stroke="#94a3b8" strokeWidth="1" markerEnd="url(#arr-drag)" />
            <text x={hubLabelX} y={hubLabelY} textAnchor="middle" dy="3" fill="#cbd5e1" fontSize="8" fontFamily="monospace"
              style={{ paintOrder: 'stroke' }} stroke="#0b1220" strokeWidth="2" strokeLinejoin="round">HUB</text>


            {/* Recovery: failed drone icon (greyed out, informational) */}
            {recoveryMode && failedDroneIdRef.current && (() => {
              const fd = state.assets.find(a => a.id === failedDroneIdRef.current)
              if (!fd) return null
              const type: AssetType = fd.type
              const fx = hubLabelX + 18
              const fy = hubLabelY
              return (
                <g key="failed-drone" opacity={0.45}>
                  <circle cx={fx} cy={fy} r={9} fill="#1e293b" stroke="#6b7280" strokeWidth={1.5} strokeDasharray="3 2" />
                  <image href={DRONE_ICON[type]} x={fx - 6} y={fy - 6} width={12} height={12}
                    style={{ pointerEvents: 'none', filter: 'grayscale(1)' }} />
                  <text x={fx} y={fy + 15} textAnchor="middle" fill="#cbd5e1" fontSize="7" fontFamily="monospace"
                    style={{ pointerEvents: 'none', paintOrder: 'stroke' }} stroke="#0b1220" strokeWidth="2" strokeLinejoin="round">{droneLabel(fd.id)}</text>
                  <line x1={fx - 7} y1={fy - 7} x2={fx + 7} y2={fy + 7} stroke="#ef4444" strokeWidth={1.5} />
                  <line x1={fx + 7} y1={fy - 7} x2={fx - 7} y2={fy + 7} stroke="#ef4444" strokeWidth={1.5} />
                </g>
              )
            })()}

            {/* Assignment arrows — bezier curves with per-drone perpendicular offset at destination */}
            {(() => {
              // For each task, ordered list of assigned drones → drives curve offset
              const taskAssignees: Record<string, string[]> = {}
              for (const task of mission.tasks) {
                taskAssignees[task.id] = pending.dronePool.filter(
                  id => (assignments[task.id] ?? []).includes(id)
                )
              }
              return pending.dronePool.map(droneId => {
                const seq = droneSequences[droneId] ?? []
                if (seq.length === 0) return null
                const asset = state.assets.find(a => a.id === droneId)
                const type: AssetType = asset?.type ?? 'Blue'
                const color = ASSET_COLOR[type]
                const markerId = `arr-${type.toLowerCase()}`
                const pos = dronePositions[droneId]
                if (!pos) return null
                const isHighlighted = hoverDrone === droneId

                const points: Array<{ x: number; y: number; taskId: string | null }> = [
                  { ...pos, taskId: null },
                ]
                for (const tid of seq) {
                  const task = mission.tasks.find(t => t.id === tid)
                  if (task) points.push({ ...task.waypoint, taskId: tid })
                }

                return (
                  <g key={droneId}>
                    {/* First leg only by default; hovering the drone reveals its full chain */}
                    {points.slice(0, isHighlighted ? -1 : 1).map((from, i) => {
                      const to = points[i + 1]
                      // Perpendicular offset: fan parallel lines arriving at same task
                      let ctrlX = (from.x + to.x) / 2
                      let ctrlY = (from.y + to.y) / 2
                      if (to.taskId) {
                        const assignees = taskAssignees[to.taskId] ?? []
                        const n = assignees.length
                        if (n > 1) {
                          const idx = assignees.indexOf(droneId)
                          const spread = (idx - (n - 1) / 2) * 10
                          const dx = to.x - from.x, dy = to.y - from.y
                          const len = Math.hypot(dx, dy) || 1
                          ctrlX += (-dy / len) * spread
                          ctrlY += (dx / len) * spread
                        }
                      }
                      // Bezier midpoint at t=0.5: 0.25·from + 0.5·ctrl + 0.25·to
                      const bmx = 0.25 * from.x + 0.5 * ctrlX + 0.25 * to.x
                      const bmy = 0.25 * from.y + 0.5 * ctrlY + 0.25 * to.y
                      return (
                        <g key={i}>
                          <path
                            d={`M ${from.x} ${from.y} Q ${ctrlX} ${ctrlY} ${to.x} ${to.y}`}
                            fill="none"
                            stroke={color}
                            strokeWidth={isHighlighted ? '2.5' : '1.5'}
                            strokeOpacity={isHighlighted ? 1.0 : 0.6}
                            strokeDasharray="6 4"
                            markerEnd={`url(#${markerId})`}
                          />
                          <circle cx={bmx} cy={bmy} r={4.5} fill={color} opacity="0.9" />
                          <text x={bmx} y={bmy} textAnchor="middle" dominantBaseline="central"
                            fill="white" fontSize="5.5" fontWeight="bold" fontFamily="monospace"
                            style={{ pointerEvents: 'none' }}>
                            {i + 1}
                          </text>
                        </g>
                      )
                    })}
                  </g>
                )
              })
            })()}

            {/* Live drag wire */}
            {dragging && (() => {
              const pos = dronePositions[dragging.droneId]
              const type = state.assets.find(a => a.id === dragging.droneId)?.type ?? 'Blue'
              const color = ASSET_COLOR[type as AssetType]
              const snap = hoverTask ? mission.tasks.find(t => t.id === hoverTask) : null
              const tx = snap ? snap.waypoint.x : dragging.svgX
              const ty = snap ? snap.waypoint.y : dragging.svgY
              const fromPos = pos ?? { x: cx, y: cy }
              return (
                <line x1={fromPos.x} y1={fromPos.y} x2={tx} y2={ty}
                  stroke={color} strokeWidth="2" strokeDasharray="5 3" opacity="0.75"
                  markerEnd="url(#arr-drag)"
                />
              )
            })()}

            {/* Task waypoints — circle, icon, name, colored comp badge, alt comp, wait times */}
            {mission.tasks.map(task => {
              const req = TASK_PRIMARY[task.type as TaskType]
              const sub = TASK_SUBSTITUTE[task.type as TaskType]
              const assigned = assignments[task.id] ?? []
              const counts = { Blue: 0, Red: 0, Green: 0 }
              for (const id of assigned) {
                const tp = state.assets.find(a => a.id === id)?.type ?? 'Blue'
                counts[tp as AssetType]++
              }
              const meetsPrimComp = counts.Blue >= req.Blue && counts.Red >= req.Red && counts.Green >= req.Green
              const meetsSubComp = !!sub && counts.Blue >= sub.Blue && counts.Red >= sub.Red && counts.Green >= sub.Green
              // Tactical error: suppressed task is deceptively shown as complete
              const isSuppressed = pending.hasTacticalError && task.id === pending.suppressedTaskId
              const complete = isSuppressed ? true : (meetsPrimComp || meetsSubComp)
              const isHovered = hoverTask === task.id && !!dragging

              // Lockout recovery: the physically-present ("now") composition is shown for every
              // pending deadlock task, but the red "!" flag goes ONLY on tasks that are genuinely
              // blocking each other (on a dependency cycle) — not a task merely starved of drones
              // stuck upstream. `isBlocking` is derived from the live plan, so breaking the cycle
              // (reorder / Suggest) clears it right away.
              const presentComp = (lockoutRecovery && task.status === 'pending')
                ? (presentByTask[task.id] ?? { Blue: 0, Red: 0, Green: 0 })
                : null
              const isBlocking = lockoutRecovery && cycleTasks.has(task.id)

              // Completed tasks — always greyed out
              if (task.status === 'completed') {
                const R_RING = 14, circ_c = 2 * Math.PI * R_RING
                return (
                  <g key={task.id}>
                    <circle
                      cx={task.waypoint.x} cy={task.waypoint.y} r={R_RING}
                      fill="none" stroke="#10b981" strokeWidth={2} opacity={0.5}
                      strokeDasharray={`${circ_c} ${circ_c}`} strokeDashoffset={0}
                      transform={`rotate(-90 ${task.waypoint.x} ${task.waypoint.y})`}
                      style={{ pointerEvents: 'none' }}
                    />
                    <circle
                      cx={task.waypoint.x} cy={task.waypoint.y} r={11}
                      fill="rgba(16,185,129,0.06)" stroke="#374151"
                      strokeWidth={1} opacity={0.6}
                    />
                    <image
                      href={TASK_ICON[task.type as TaskType]}
                      x={task.waypoint.x - 6.5} y={task.waypoint.y - 6.5}
                      width={13} height={13}
                      style={{ pointerEvents: 'none', opacity: 0.35 }}
                    />
                    <text x={task.waypoint.x} y={task.waypoint.y + 24}
                      textAnchor="middle" fill="#94a3b8" fontSize="8" fontFamily="sans-serif"
                      style={{ pointerEvents: 'none', paintOrder: 'stroke' }} stroke="#0b1220" strokeWidth="2" strokeLinejoin="round">
                      {TASK_TYPE_NAMES[task.type]}
                    </text>
                    <text x={task.waypoint.x} y={task.waypoint.y + 33}
                      textAnchor="middle" fill="#94a3b8" fontSize="7" fontFamily="monospace"
                      style={{ pointerEvents: 'none', paintOrder: 'stroke' }} stroke="#0b1220" strokeWidth="2" strokeLinejoin="round">✓ done</text>
                  </g>
                )
              }

              // Failed tasks — greyed out like completed ones, but red. Without this branch they
              // fell through to the normal pending rendering and were drawn as an ordinary
              // uncovered task with a "0/2L 0/1C" composition badge, so the map claimed drones
              // were still needed for work the schedule panel had already written off.
              if (task.status === 'failed') {
                return (
                  <g key={task.id}>
                    <circle
                      cx={task.waypoint.x} cy={task.waypoint.y} r={11}
                      fill="rgba(239,68,68,0.06)" stroke="#7f1d1d"
                      strokeWidth={1} opacity={0.6}
                    />
                    <image
                      href={TASK_ICON[task.type as TaskType]}
                      x={task.waypoint.x - 6.5} y={task.waypoint.y - 6.5}
                      width={13} height={13}
                      style={{ pointerEvents: 'none', opacity: 0.3 }}
                    />
                    <text x={task.waypoint.x} y={task.waypoint.y + 24}
                      textAnchor="middle" fill="#94a3b8" fontSize="8" fontFamily="sans-serif"
                      style={{ pointerEvents: 'none', paintOrder: 'stroke' }} stroke="#0b1220" strokeWidth="2" strokeLinejoin="round">
                      {TASK_TYPE_NAMES[task.type]}
                    </text>
                    <text x={task.waypoint.x} y={task.waypoint.y + 33}
                      textAnchor="middle" fill="#f87171" fontSize="7" fontFamily="monospace"
                      style={{ pointerEvents: 'none', paintOrder: 'stroke' }} stroke="#0b1220" strokeWidth="2" strokeLinejoin="round">✕ failed</text>
                  </g>
                )
              }

              // Status badge shown in recovery mode for executing/traveling tasks (still interactive)
              const recoveryStatusLabel = recoveryMode && task.status !== 'pending'
                ? (task.status === 'executing' ? '⟳' : task.status === 'traveling' ? '→' : null)
                : null

              // Active / interactive task
              const execProgress = task.status === 'executing' && task.startTime !== null && task.baseTime > 0
                ? Math.min(1, Math.max(0, (state.elapsed - task.startTime) / task.baseTime))
                : 0
              const R_ACT = 14, circ_a = 2 * Math.PI * R_ACT
              return (
                <g key={task.id}
                  onDragOver={(e: React.DragEvent<SVGGElement>) => { e.preventDefault(); setHoverTask(task.id) }}
                  onDragLeave={(_e: React.DragEvent<SVGGElement>) => setHoverTask(null)}
                  onDrop={(e: React.DragEvent<SVGGElement>) => {
                    e.preventDefault()
                    const droneId = e.dataTransfer.getData('droneId')
                    if (droneId) moveDrone(droneId, task.id, e.shiftKey)
                    setHoverTask(null)
                  }}
                >
                  {execProgress > 0 && (
                    <circle
                      cx={task.waypoint.x} cy={task.waypoint.y} r={R_ACT}
                      fill="none" stroke="#3b82f6" strokeWidth={2}
                      strokeDasharray={`${circ_a} ${circ_a}`}
                      strokeDashoffset={circ_a * (1 - execProgress)}
                      transform={`rotate(-90 ${task.waypoint.x} ${task.waypoint.y})`}
                      style={{ pointerEvents: 'none' }}
                    />
                  )}
                  <circle
                    cx={task.waypoint.x} cy={task.waypoint.y} r={isHovered ? 14 : 11}
                    fill={isBlocking ? 'rgba(220,38,38,0.14)'
                      : complete ? 'rgba(16,185,129,0.15)'
                      : recoveryStatusLabel ? 'rgba(245,158,11,0.08)'
                      : isHovered ? 'rgba(59,130,246,0.25)' : 'rgba(15,23,42,0.9)'}
                    stroke={isBlocking ? '#dc2626'
                      : complete ? '#10b981'
                      : recoveryStatusLabel ? '#f59e0b'
                      : isHovered ? '#3b82f6' : '#475569'}
                    strokeWidth={isHovered || isBlocking ? 2 : 1.5}
                  />
                  {recoveryStatusLabel && (
                    <text x={task.waypoint.x + 10} y={task.waypoint.y - 8}
                      textAnchor="middle" fill={recoveryStatusLabel === '⟳' ? '#f59e0b' : '#60a5fa'}
                      fontSize="9" fontFamily="monospace" style={{ pointerEvents: 'none' }}>
                      {recoveryStatusLabel}
                    </text>
                  )}
                  <image
                    href={TASK_ICON[task.type as TaskType]}
                    x={task.waypoint.x - 6.5} y={task.waypoint.y - 6.5}
                    width={13} height={13}
                    style={{ pointerEvents: 'none' }}
                  />
                  <text x={task.waypoint.x} y={task.waypoint.y + 21}
                    textAnchor="middle" fill="#cbd5e1" fontSize="8" fontFamily="sans-serif"
                    style={{ pointerEvents: 'none', paintOrder: 'stroke' }} stroke="#0b1220" strokeWidth="2" strokeLinejoin="round">
                    {TASK_TYPE_NAMES[task.type]}
                  </text>
                  {/* A blocking deadlocked task never reads as complete — even though its PLANNED
                      comp is met, it's part of the cycle, so show the composition (+ red styling),
                      not a green ✓. */}
                  {complete && !isBlocking ? (
                    <text x={task.waypoint.x} y={task.waypoint.y + 33}
                      textAnchor="middle" fill="#4ade80" fontSize="7" fontFamily="monospace"
                      style={{ pointerEvents: 'none' }}>✓</text>
                  ) : (
                    <>
                      {/* Primary comp — per-type color (B=blue, R=red, G=green) */}
                      <text x={task.waypoint.x} y={task.waypoint.y + 33}
                        textAnchor="middle" fontSize="7" fontFamily="monospace"
                        style={{ pointerEvents: 'none', paintOrder: 'stroke' }} stroke="#0b1220" strokeWidth="2" strokeLinejoin="round">
                        {[
                          req.Blue  > 0 ? { c: counts.Blue,  r: req.Blue,  key: 'F', col: '#60a5fa' } : null,
                          req.Red   > 0 ? { c: counts.Red,   r: req.Red,   key: 'L', col: '#f87171' } : null,
                          req.Green > 0 ? { c: counts.Green, r: req.Green, key: 'C', col: '#86efac' } : null,
                        ].filter((p): p is { c: number; r: number; key: string; col: string } => p !== null)
                          .map((p, i) => (
                            <tspan key={p.key} fill={
                              meetsPrimComp ? '#4ade80'
                              : meetsSubComp ? '#facc15'
                              : p.c >= p.r  ? '#9ca3af'
                              : p.col
                            }>
                              {i > 0 ? ' ' : ''}{p.c}/{p.r}{p.key}
                            </tspan>
                          ))}
                      </text>
                      {/* Alt comp — hidden during lockout recovery (the "now" line takes its place) */}
                      {sub && !presentComp && (
                        <text x={task.waypoint.x} y={task.waypoint.y + 42}
                          textAnchor="middle" fill="#9ca3af" fontSize="6.5" fontFamily="monospace"
                          style={{ pointerEvents: 'none', paintOrder: 'stroke' }} stroke="#0b1220" strokeWidth="1.6" strokeLinejoin="round">
                          {`OR ${[sub.Blue > 0 ? `${sub.Blue}F` : null, sub.Red > 0 ? `${sub.Red}L` : null, sub.Green > 0 ? `${sub.Green}C` : null].filter(Boolean).join('+')} `}
                        </text>
                      )}
                    </>
                  )}
                  {/* Lockout recovery: "right now" present-at-site composition under the plan text.
                      Each type keeps its OWN drone colour (F=blue, L=red, C=green) so it's clear which
                      is which; an understocked type is prefixed with "!" to show what's actually
                      missing. The OR line is hidden (above), so this sits at y+42. */}
                  {presentComp && (() => {
                    const parts = [
                      req.Blue  > 0 ? { c: presentComp.Blue,  r: req.Blue,  key: 'F', col: '#60a5fa' } : null,
                      req.Red   > 0 ? { c: presentComp.Red,   r: req.Red,   key: 'L', col: '#f87171' } : null,
                      req.Green > 0 ? { c: presentComp.Green, r: req.Green, key: 'C', col: '#86efac' } : null,
                    ].filter((p): p is { c: number; r: number; key: string; col: string } => p !== null)
                    return (
                      <text x={task.waypoint.x} y={task.waypoint.y + 42}
                        textAnchor="middle" fontSize="6.5" fontFamily="monospace"
                        style={{ pointerEvents: 'none', paintOrder: 'stroke' }} stroke="#0b1220" strokeWidth="1.6" strokeLinejoin="round">
                        <tspan fill="#94a3b8">now </tspan>
                        {parts.map((p, i) => {
                          const missing = p.c < p.r
                          return (
                            <tspan key={p.key} fill={p.col} fontWeight={missing ? 'bold' : 'normal'}>
                              {i > 0 ? ' ' : ''}{missing ? '!' : ''}{p.c}/{p.r}{p.key}
                            </tspan>
                          )
                        })}
                      </text>
                    )
                  })()}
                  {/* Blocking flag: this task is part of the deadlock cycle (mutually blocking) */}
                  {isBlocking && (
                    <g style={{ pointerEvents: 'none' }}>
                      <circle cx={task.waypoint.x + 11} cy={task.waypoint.y - 11} r={5}
                        fill="#dc2626" stroke="#0b1220" strokeWidth={0.8} />
                      <text x={task.waypoint.x + 11} y={task.waypoint.y - 11} textAnchor="middle"
                        dominantBaseline="central" fill="#fff" fontSize="7.5" fontWeight="bold" fontFamily="sans-serif">!</text>
                    </g>
                  )}
                </g>
              )
            })}

            {/* Drone icons on zone boundary — all drones; assigned at task angles, unassigned fanned near hub */}
            {pending.dronePool.filter(id => !!dronePositions[id]).map(droneId => {
              const pos = dronePositions[droneId]!
              const asset = state.assets.find(a => a.id === droneId)
              const type: AssetType = asset?.type ?? 'Blue'
              const color = ASSET_COLOR[type]
              const cs = droneLabel(droneId)
              const isDraggingThis = dragging?.droneId === droneId
              const isHoveredDrone = hoverDrone === droneId
              return (
                <g key={droneId} data-drone={droneId}
                  style={{ cursor: isDraggingThis ? 'grabbing' : 'grab' }}
                  onMouseEnter={() => !dragging && setHoverDrone(droneId)}
                  onMouseLeave={() => setHoverDrone(null)}
                >
                  <circle cx={pos.x} cy={pos.y} r={8} fill="#1e293b"
                    stroke={isHoveredDrone ? '#fbbf24' : color}
                    strokeWidth={isDraggingThis || isHoveredDrone ? 2.5 : 1.5} />
                  <image href={DRONE_ICON[type]} x={pos.x - 5} y={pos.y - 5} width={10} height={10} style={{ pointerEvents: 'none' }} />
                  <text x={pos.x} y={pos.y + 14} textAnchor="middle" fill={color} fontSize="6.5" fontFamily="monospace"
                    style={{ pointerEvents: 'none', paintOrder: 'stroke' }} stroke="#0b1220" strokeWidth="1.6" strokeLinejoin="round">{cs}</text>
                </g>
              )
            })}
          </svg>
        </div>

        {/* Right panel */}
        <TacticalRightPanel
          pending={pending}
          assignments={assignments}
          assets={state.assets}
          tasks={mission.tasks}
          timings={timings}
          onRemove={removeDrone}
          canDeploy={canDeploy}
          isSuggestLoading={isSuggestLoading}
          onDeploy={handleDeploy}
          onStopSuggest={handleStopSuggest}
          recoveryMode={!!recoveryMode}
          recoveryReason={mission.recoveryReason}
          deadlockUnresolved={hasUnresolvedDeadlock}
          cycleTasks={cycleTasks}
          failedDroneId={failedDroneIdRef.current ?? null}
          suppressedTaskId={pending.suppressedTaskId}
          missionId={mission.id}
          onMapAction={onMapAction}
        />
      </div>
    </div>
  )
}

// ─── Tactical right panel ─────────────────────────────────────────────────

function TacticalRightPanel({ pending, assignments, assets, tasks, timings, onRemove, canDeploy, isSuggestLoading, onDeploy, onStopSuggest, recoveryMode, recoveryReason, deadlockUnresolved, cycleTasks, failedDroneId, suppressedTaskId, missionId, onMapAction }: {
  pending: PendingAllocation
  assignments: Record<string, string[]>
  assets: Asset[]
  tasks: Task[]
  timings: { taskStarts: Record<string, number>; droneWaits: Record<string, Record<string, number>> }
  onRemove: (droneId: string, taskId: string) => void
  canDeploy: boolean
  isSuggestLoading?: boolean
  onDeploy: () => void
  onStopSuggest?: () => void
  recoveryMode?: boolean
  recoveryReason?: 'drone_failure' | 'lockout'
  deadlockUnresolved?: boolean
  cycleTasks?: Set<string>
  failedDroneId?: string | null
  suppressedTaskId?: string | null
  missionId?: string
  onMapAction?: (action: object) => void
}) {
  const ASSET_COLOR_TEXT: Record<AssetType, string> = { Blue: 'text-blue-400', Red: 'text-red-400', Green: 'text-green-400' }
  const ASSET_BG: Record<AssetType, string> = { Blue: 'bg-blue-900/50 border-blue-700/50', Red: 'bg-red-900/50 border-red-700/50', Green: 'bg-emerald-900/50 border-emerald-700/50' }

  // Unassigned drones (for reference list)
  const unassigned = pending.dronePool.filter(id =>
    !pending.taskOrder.some(tid => (assignments[tid] ?? []).includes(id))
  )

  function getType(id: string): AssetType { return assets.find(a => a.id === id)?.type ?? 'Blue' }
  function getCS(id: string): string { return droneLabel(id) }

  // Physically-present drones per task ("Present at site: 2/2 L · 0/1 C") — lockout recovery only,
  // so the operator can see which drones actually reached which task and what's still missing.
  const presentByTask = (recoveryMode && recoveryReason === 'lockout')
    ? computePresentByTask(pending.dronePool, pending.taskOrder, tasks, assets)
    : {}

  // Sort tasks by actual execution start time; unassigned tasks go to end
  const sortedTaskOrder = [...pending.taskOrder].sort((a, b) => {
    const ta = timings.taskStarts[a]
    const tb = timings.taskStarts[b]
    if (ta !== undefined && tb !== undefined) return ta - tb
    if (ta !== undefined) return -1
    if (tb !== undefined) return 1
    return pending.taskOrder.indexOf(a) - pending.taskOrder.indexOf(b)
  })

  // Overall ETA: latest task completion across all assigned tasks
  const overallETA = (() => {
    let latest: number | null = null
    for (const taskId of pending.taskOrder) {
      const ts = timings.taskStarts[taskId]
      if (ts === undefined) continue
      const task = tasks.find(t => t.id === taskId)
      if (!task) continue
      const end = ts + task.baseTime
      if (latest === null || end > latest) latest = end
    }
    return latest !== null ? Math.round(latest) : null
  })()

  return (
    <div data-tutorial="tac-right-panel" className="w-[560px] flex-none border-l border-gray-800 bg-gray-900 flex flex-col overflow-hidden">
      {/* Help-needed banner: scheduling lockout (no failed drone) */}
      {recoveryMode && recoveryReason === 'lockout' && (
        <div className="flex-none px-3 py-2 border-b border-red-900/60 bg-red-950/30 space-y-1">
          <span className="text-red-400 text-sm font-bold uppercase tracking-wider">⚠ Lockout — help needed</span>
          <p className="text-sm text-gray-500">These drones deadlocked (each waiting on the other). The current — still broken — plan is shown below. Change it into a workable order (drag drones to reorder) or click <span className="text-purple-300 font-medium">Suggest</span> for a fix, then Reassign. Or abandon.</p>
          {deadlockUnresolved && (
            <p className="text-sm font-semibold text-red-400">Still deadlocked — Reassign is disabled until the cycle is broken.</p>
          )}
        </div>
      )}
      {/* Help-needed banner: drone failure */}
      {recoveryMode && recoveryReason !== 'lockout' && failedDroneId && (() => {
        const fd = assets.find(a => a.id === failedDroneId)
        if (!fd) return null
        return (
          <div className="flex-none px-3 py-2 border-b border-red-900/60 bg-red-950/30 space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-red-400 text-sm font-bold uppercase tracking-wider">⚠ Drone Failed</span>
              <div className="flex items-center gap-1 px-1.5 py-0.5 rounded border border-red-800/50 bg-red-900/20">
                <img src={DRONE_ICON[fd.type]} className="w-3.5 h-3.5 flex-none grayscale opacity-50" alt="" />
                <span className="font-mono text-sm text-gray-500 line-through">{getCS(failedDroneId)}</span>
              </div>
            </div>
            <p className="text-sm text-gray-500">Reassign its task using remaining mission drones (or click <span className="text-purple-300 font-medium">Suggest</span> for a fix), or abandon.</p>
          </div>
        )
      })()}
      {/* Unassigned reference list */}
      {unassigned.length > 0 && (
        <div data-tutorial="tac-unassigned" className="flex-none p-3 border-b border-gray-800">
          <p className="text-sm text-gray-500 uppercase tracking-wider mb-2">
            Unassigned ({unassigned.length})
          </p>
          <div className="flex flex-wrap gap-1">
            {unassigned.map(id => {
              const type = getType(id)
              const cs = getCS(id)
              return (
                <div key={id}
                  draggable
                  onDragStart={e => e.dataTransfer.setData('droneId', id)}
                  className={`flex items-center gap-1 px-1.5 py-0.5 rounded border text-lg cursor-grab select-none ${ASSET_BG[type]}`}
                  title="Drag to task on map · hold Shift to chain"
                >
                  <img src={DRONE_ICON[type]} className="w-3.5 h-3.5 flex-none" alt="" />
                  <span className={`font-mono font-bold ${ASSET_COLOR_TEXT[type]}`}>{cs}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Task schedule — sorted by actual execution order */}
      <div data-tutorial="tac-schedule" className="flex-1 overflow-y-auto p-3 space-y-2">
        <p className="text-sm text-gray-500 uppercase tracking-wider mb-1">Task Schedule</p>
        {sortedTaskOrder.map((taskId, idx) => {
          const task = tasks.find(t => t.id === taskId)
          if (!task) return null
          const req = TASK_PRIMARY[task.type as TaskType]
          const sub = TASK_SUBSTITUTE[task.type as TaskType]
          const subTime = TASK_SUB_BASE_TIME[task.type as TaskType]
          const baseTime = TASK_BASE_TIME[task.type as TaskType]
          const assigned = assignments[taskId] ?? []
          const counts = { Blue: 0, Red: 0, Green: 0 }
          for (const id of assigned) { counts[getType(id) as AssetType]++ }
          const meetsPrimRP = counts.Blue >= req.Blue && counts.Red >= req.Red && counts.Green >= req.Green
          const meetsSubRP = !!sub && counts.Blue >= sub.Blue && counts.Red >= sub.Red && counts.Green >= sub.Green
          const isSuppressedRP = taskId === suppressedTaskId
          const complete = isSuppressedRP ? true : (meetsPrimRP || meetsSubRP)
          const tStart = timings.taskStarts[taskId]
          const tEnd = tStart !== undefined ? Math.round(tStart + baseTime) : null

          return (
            <div key={taskId}
              className={`rounded border p-2 text-lg space-y-1.5 ${complete ? 'border-green-800/60 bg-green-950/10' : 'border-gray-700 bg-gray-800/40'}`}
            >
              {/* Header */}
              <div className="flex items-center gap-1.5">
                <span className="text-sm text-gray-500 font-mono">#{idx + 1}</span>
                <img src={TASK_ICON[task.type as TaskType]} className="w-4 h-4 flex-none" alt="" />
                <span className={`font-medium ${complete ? 'text-green-300' : 'text-gray-200'}`}>
                  {TASK_TYPE_NAMES[task.type]}
                </span>
                {complete && <span className="ml-auto text-green-400 text-sm">✓</span>}
              </div>

              {/* Required composition */}
              <div className="space-y-0.5">
                <div className="flex items-center gap-1">
                  <span className="text-sm text-gray-500 w-8">Req:</span>
                  <span className="text-gray-300 font-mono text-sm">{compToLabel(req, baseTime)}</span>
                </div>
                {sub && (
                  <div className="flex items-center gap-1">
                    <span className="text-sm text-gray-600 w-8">OR:</span>
                    <span className="text-gray-500 font-mono text-sm">{compToLabel(sub, subTime)}</span>
                  </div>
                )}
              </div>

              {/* Present-at-site (lockout recovery): drones physically at this task, each in its own
                  drone colour with a "!" prefix on an understocked type. A red "!" pill + "blocking"
                  appears only when the task is part of the deadlock cycle (mutually blocking). */}
              {recoveryMode && recoveryReason === 'lockout' && task.status === 'pending' && (() => {
                const present = presentByTask[taskId] ?? { Blue: 0, Red: 0, Green: 0 }
                const isBlocking = !!cycleTasks?.has(taskId)
                const parts = [
                  req.Blue  > 0 ? { c: present.Blue,  r: req.Blue,  key: 'F', cls: 'text-blue-400' } : null,
                  req.Red   > 0 ? { c: present.Red,   r: req.Red,   key: 'L', cls: 'text-red-400' } : null,
                  req.Green > 0 ? { c: present.Green, r: req.Green, key: 'C', cls: 'text-green-400' } : null,
                ].filter((p): p is { c: number; r: number; key: string; cls: string } => p !== null)
                return (
                  <div className="flex items-center gap-1.5">
                    {isBlocking && (
                      <span className="inline-flex items-center justify-center w-4 h-4 flex-none rounded-full bg-red-600 text-white text-xs font-bold leading-none">!</span>
                    )}
                    <span className="text-sm text-gray-500">Present now:</span>
                    <span className="font-mono text-sm">
                      {parts.map((p, i) => (
                        <span key={p.key} className={`${p.cls} ${p.c < p.r ? 'font-bold' : ''}`}>{i > 0 ? ' ' : ''}{p.c < p.r ? '!' : ''}{p.c}/{p.r}{p.key}</span>
                      ))}
                    </span>
                    {isBlocking && <span className="text-sm text-red-400/80">blocking</span>}
                  </div>
                )
              })()}

              {/* Assigned drones */}
              {assigned.length > 0 && (
                <div className="space-y-0.5">
                  <div className="flex flex-wrap gap-1">
                    {assigned.map(id => {
                      const tp = getType(id)
                      const cs = getCS(id)
                      return (
                        <div key={id}
                          className={`flex items-center gap-0.5 px-1 py-0.5 rounded border ${ASSET_BG[tp]}`}>
                          <span className={`font-mono text-sm ${ASSET_COLOR_TEXT[tp]}`}>{cs}</span>
                          <button
                            onClick={() => onRemove(id, taskId)}
                            className="ml-0.5 text-red-400 hover:text-red-300 leading-none"
                            title="Remove"
                          >×</button>
                        </div>
                      )
                    })}
                  </div>
                  {/* Status badge for in-progress tasks in recovery */}
                  {recoveryMode && task.status !== 'pending' && (
                    <div className={`text-sm font-mono ${task.status === 'executing' ? 'text-amber-400' : 'text-blue-400'}`}>
                      {task.status === 'executing' ? '⟳ executing' : '→ traveling'}
                    </div>
                  )}
                  {/* Comp progress */}
                  {!complete && (
                    <div className={`font-mono text-sm ${meetsPrimRP ? 'text-green-400' : meetsSubRP ? 'text-yellow-400' : 'text-amber-400'}`}>
                      {buildCompLabel(counts, req)}
                    </div>
                  )}
                </div>
              )}

              {assigned.length === 0 && (
                <p className="text-gray-600 text-sm italic">No drones assigned</p>
              )}

              {/* Timing */}
              {tStart !== undefined && (
                <div className="text-gray-500 text-sm font-mono border-t border-gray-700/50 pt-1">
                  Start ~{Math.round(tStart)}s · Done ~{tEnd}s
                </div>
              )}

              {/* Wait times — only shown when comp fully met */}
              {complete && Object.entries(timings.droneWaits[taskId] ?? {}).map(([droneId, wait]) => (
                <div key={droneId} className="text-sm text-orange-400">
                  {getCS(droneId)} waiting {wait} seconds
                </div>
              ))}
            </div>
          )
        })}
      </div>

      {/* Footer: ETA + Stop Assistant + Deploy + Abandon.
          The floating ZoomControls widget is pinned to the window's bottom-right corner and sat on
          top of the Deploy button's right-hand end, so leave room for it. */}
      <div className="flex-none p-3 pb-14 border-t border-gray-800 space-y-2">
        {overallETA !== null && (
          <div className="text-lg text-gray-400">
            Est. completion: <span className="text-white font-mono font-bold">~{overallETA}s</span>
          </div>
        )}
        {isSuggestLoading && onStopSuggest && (
          <button
            onClick={onStopSuggest}
            className="w-full py-2 bg-amber-900/40 hover:bg-amber-800/50 border border-amber-700/60 hover:border-amber-600 rounded text-amber-300 hover:text-amber-200 text-lg transition-colors"
          >
            Stop Assistant — take over
          </button>
        )}
        <button
          data-tutorial="tac-deploy-btn"
          onClick={onDeploy}
          // While the assistant is still revealing its plan, hold Deploy until it finishes — the
          // operator can click "Stop Assistant" to take over early. Matches the tutorial's behaviour.
          disabled={!canDeploy || (!recoveryMode && isSuggestLoading)}
          className="w-full py-8 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed rounded text-white text-lg font-semibold transition-colors"
        >
          {recoveryMode
            ? (canDeploy ? 'Reassign ✓' : deadlockUnresolved ? 'Reassign (still deadlocked)' : 'Reassign (incomplete)')
            : isSuggestLoading
              ? 'Deploy (allocation in progress…)'
              : canDeploy ? 'Deploy ✓' : 'Deploy (incomplete)'}
        </button>
        {recoveryMode && missionId && onMapAction && (
          <button
            data-tutorial="tac-abandon-btn"
            onClick={() => onMapAction({ _mapAction: 'ABANDON_MISSION', missionId })}
            className="w-full py-1.5 bg-transparent hover:bg-red-950/40 border border-red-800/60 hover:border-red-700 rounded text-red-500 hover:text-red-300 text-lg transition-colors"
          >
            Abandon Mission
          </button>
        )}
      </div>
    </div>
  )
}

export type { MapViewState }
