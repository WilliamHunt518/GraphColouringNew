import { useState, useEffect, useRef, useMemo } from 'react'

const LOG = true
import type { MapViewState, Asset, Mission, AssetType, TaskType, Task, PendingAllocation } from '../types'
import { HUB, ASSET_SPEED, ASSET_CALLSIGNS, ASSET_CALLSIGNS_NATO, TASK_PRIMARY, TASK_BASE_TIME, TASK_SUBSTITUTE, TASK_SUB_BASE_TIME } from '../utils/missionGen'
import { DRONE_ICON, TASK_ICON } from '../utils/icons'

// ─── Types ────────────────────────────────────────────────────────────────

type CallsignMode = 'id' | 'arthurian' | 'nato'

// ─── Helpers ──────────────────────────────────────────────────────────────

function resolveCallsign(assetId: string, mode: CallsignMode): string {
  if (mode === 'arthurian') return ASSET_CALLSIGNS[assetId] ?? assetId
  if (mode === 'nato')      return ASSET_CALLSIGNS_NATO[assetId] ?? assetId
  return assetId
}

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
  if (req.Blue > 0)  parts.push(`${counts.Blue}/${req.Blue}B`)
  if (req.Red > 0)   parts.push(`${counts.Red}/${req.Red}R`)
  if (req.Green > 0) parts.push(`${counts.Green}/${req.Green}G`)
  return parts.join(' ') || '—'
}

function compToLabel(comp: { Blue: number; Red: number; Green: number }, time: number): string {
  const parts: string[] = []
  if (comp.Blue > 0) parts.push(`${comp.Blue}B`)
  if (comp.Red > 0) parts.push(`${comp.Red}R`)
  if (comp.Green > 0) parts.push(`${comp.Green}G`)
  return `${parts.join(' + ')} (${time}s)`
}

// ─── Constants ────────────────────────────────────────────────────────────

const ASSET_COLOR: Record<AssetType, string> = {
  Blue:  '#60a5fa',
  Red:   '#f87171',
  Green: '#4ade80',
}

const TASK_TYPE_NAMES: Record<number, string> = {
  1: 'Recce', 2: 'Recon', 3: 'Minor Drop', 4: 'Major Drop', 5: 'Search & Supply',
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
  const channelRef = useRef<BroadcastChannel | null>(null)

  useEffect(() => {
    const ch = new BroadcastChannel('sar-study')
    channelRef.current = ch
    return () => ch.close()
  }, [])

  function handleMapAction(action: object) {
    channelRef.current?.postMessage(action)
  }

  // Mirror primary window's mission selection into the tactical view
  useEffect(() => {
    LOG && console.log('[MAP DISPLAY] state.openMissionId changed to:', state.openMissionId)
    setTacticalMissionId(state.openMissionId)
    LOG && console.log('[MAP DISPLAY] setTacticalMissionId →', state.openMissionId)
  }, [state.openMissionId])

  const tacticalMission = tacticalMissionId
    ? state.missions.find(m => m.id === tacticalMissionId &&
        ((m.tacticalPending && !!m.pendingAllocation) || m.failureRecoveryPending || m.status === 'active')) ?? null
    : null

  if (tacticalMission) {
    const isRecovery = tacticalMission.failureRecoveryPending
    const isReadOnly = !isRecovery && !tacticalMission.tacticalPending && tacticalMission.status === 'active'
    let overrideAlloc: PendingAllocation | undefined
    let recoveryReserveIds: Set<string> | undefined
    let recoveryFailedDroneId: string | null = null
    if (isRecovery) {
      const result = buildRecoveryAllocation(tacticalMission, state.assets)
      overrideAlloc = result.allocation
      recoveryReserveIds = result.reserveIds
      recoveryFailedDroneId = result.failedDroneId
    } else if (isReadOnly) {
      overrideAlloc = buildActiveAllocation(tacticalMission, state.assets)
    }
    return (
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
      />
    )
  }

  const pending = state.missions.filter(m =>
    (m.tacticalPending && !!m.pendingAllocation) || m.failureRecoveryPending
  )
  return <WaitingScreen pending={pending} onSelect={setTacticalMissionId} state={state} />
}

// ─── Waiting screen ───────────────────────────────────────────────────────

function WaitingScreen({ pending, onSelect, state }: {
  pending: Mission[]
  onSelect: (id: string) => void
  state: MapViewState
}) {
  const active = state.missions.filter(m => m.status === 'active').length
  const queued = state.missions.filter(m => m.status === 'queued').length

  return (
    <div className="flex flex-col h-screen bg-gray-950 text-gray-300">
      {/* Status bar */}
      <div className="flex items-center gap-6 px-6 py-3 bg-gray-900 border-b border-gray-800 flex-none">
        <span className="text-sm font-semibold text-gray-400">Session {state.sessionNumber}/3</span>
        <span className="text-sm">
          Score: <span className="text-white font-bold font-mono">{state.score}</span>
          <span className="text-red-400 ml-1 font-mono">−{state.penaltyAccrued}</span>
        </span>
        <span className="text-sm text-gray-500">{active} active · {queued} queued</span>
        <span className="text-sm text-gray-500">{formatSeconds(state.elapsed)} elapsed</span>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col items-center justify-center gap-6 px-8">
        {pending.length === 0 ? (
          <div className="text-center space-y-3">
            <p className="text-2xl font-semibold text-gray-500">No tactical assignment active</p>
            <p className="text-sm text-gray-600">When a mission requires tactical planning, it will appear here.</p>
          </div>
        ) : (
          <div className="w-full max-w-lg space-y-4">
            <p className="text-center text-lg font-semibold text-yellow-400">Tactical Assignment Pending</p>
            <p className="text-center text-sm text-gray-500">{pending.length} mission{pending.length !== 1 ? 's' : ''} awaiting tactical planning</p>
            {pending.map(m => {
              const isRecovery = m.failureRecoveryPending
              return (
                <button
                  key={m.id}
                  onClick={() => onSelect(m.id)}
                  className={`w-full text-left px-4 py-3 rounded-lg border transition-colors ${
                    isRecovery
                      ? 'border-red-700/60 bg-red-900/10 hover:bg-red-900/25'
                      : 'border-yellow-700/60 bg-yellow-900/10 hover:bg-yellow-900/25'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="font-mono font-bold text-white text-lg">{m.id}</span>
                      <span className="text-sm text-gray-400">Cat {m.category} · {CAT_NAMES[m.category] ?? ''}</span>
                    </div>
                    <div className={`flex items-center gap-2 text-sm ${isRecovery ? 'text-red-400' : 'text-yellow-400'}`}>
                      {isRecovery ? (
                        <span className="px-1.5 py-0.5 bg-red-900/50 border border-red-700/60 rounded text-xs font-bold text-red-300">FAILURE</span>
                      ) : (
                        <span>{m.pendingAllocation?.dronePool.length ?? 0} drones</span>
                      )}
                      <span>→</span>
                      <span>Open</span>
                    </div>
                  </div>
                  {!isRecovery && m.pendingAllocation && (
                    <p className="mt-1 text-xs text-gray-500">
                      {m.pendingAllocation.strategyName} · {m.pendingAllocation.taskOrder.length} tasks
                    </p>
                  )}
                  {isRecovery && (
                    <p className="mt-1 text-xs text-red-500">
                      Drone failure — reassign pending tasks
                    </p>
                  )}
                </button>
              )
            })}
          </div>
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
  }
}

// ─── Recovery allocation builder ─────────────────────────────────────────

function buildRecoveryAllocation(mission: Mission, assets: Asset[]): { allocation: PendingAllocation; reserveIds: Set<string>; failedDroneId: string | null } {
  // Drones currently deployed on this mission (not failed, not yet returned)
  const deployedDrones = assets.filter(a =>
    a.currentMissionId === mission.id && a.status === 'deployed'
  )

  // All available reserve drones shown at hub corner — user drags any of them to assign
  const reserveBlue  = assets.filter(a => a.status === 'available' && a.type === 'Blue')
  const reserveRed   = assets.filter(a => a.status === 'available' && a.type === 'Red')
  const reserveGreen = assets.filter(a => a.status === 'available' && a.type === 'Green')
  const reserveDrones = [...reserveBlue, ...reserveRed, ...reserveGreen]
  const reserveIds = new Set(reserveDrones.map(a => a.id))

  const dronePool = [...deployedDrones.map(a => a.id), ...reserveDrones.map(a => a.id)]
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
    },
    reserveIds,
    failedDroneId: mission.failedDroneId,
  }
}

// ─── Tactical planner (SVG + right panel) ────────────────────────────────

function TacticalPlannerView({ mission, state, onBack, onMapAction, overrideAllocation, recoveryMode, recoveryReserveIds, failedDroneId, readOnly }: {
  mission: Mission
  state: MapViewState
  onBack: () => void
  onMapAction: (action: object) => void
  overrideAllocation?: PendingAllocation
  recoveryMode?: boolean
  recoveryReserveIds?: Set<string>
  failedDroneId?: string | null
  readOnly?: boolean
}) {
  const pending = overrideAllocation ?? mission.pendingAllocation!
  const callsignMode = state.callsignMode

  const [assignments, setAssignments] = useState<Record<string, string[]>>(() =>
    Object.fromEntries(Object.entries(pending.taskAssignments).map(([k, v]) => [k, [...v]]))
  )
  // droneChainOrder: droneId → taskIds in the order the user assigned them (not strategic order)
  const [droneChainOrder, setDroneChainOrder] = useState<Record<string, string[]>>({})
  const [dragging, setDragging] = useState<{ droneId: string; svgX: number; svgY: number } | null>(null)
  const [hoverTask, setHoverTask] = useState<string | null>(null)
  const [hoverHub, setHoverHub] = useState(false)
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
      setAssignments(Object.fromEntries(Object.entries(pending.taskAssignments).map(([k, v]) => [k, [...v]])))
      setDroneChainOrder({})
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

  // Deploy readiness — accepts primary OR substitute composition
  const canDeploy = pending.taskOrder.every(tid => {
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

  // Unified move/chain handler — maintains droneChainOrder so sequences follow assignment order
  function moveDrone(droneId: string, taskId: string, chain: boolean) {
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
    setDroneChainOrder(prev => {
      if (!chain) {
        return { ...prev, [droneId]: [taskId] }
      } else {
        const existing = prev[droneId] ?? []
        if (existing.includes(taskId)) return prev
        return { ...prev, [droneId]: [...existing, taskId] }
      }
    })
  }

  function removeDrone(droneId: string, taskId: string) {
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
      onMapAction({ _mapAction: 'CONFIRM_FAILURE_RECOVERY', missionId: mission.id, taskAssignments: assignments })
    } else {
      onMapAction({ _mapAction: 'CONFIRM_TACTICAL', missionId: mission.id, taskAssignments: assignments, droneSequences })
    }
  }

  function handleReset() {
    setAssignments(Object.fromEntries(Object.entries(pending.taskAssignments).map(([k, v]) => [k, [...v]])))
    setDroneChainOrder({})
  }

  return (
    <div className="flex flex-col h-screen bg-gray-950">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2 bg-gray-900 border-b border-gray-800 flex-none">
        <button onClick={onBack} className="text-xs text-gray-400 hover:text-white transition-colors">← Back</button>
        <div className="h-4 w-px bg-gray-700" />
        <span className="font-mono text-sm text-white font-bold">{mission.id}</span>
        <span className="text-xs text-gray-400">Cat {mission.category} · {CAT_NAMES[mission.category] ?? ''}</span>
        {recoveryMode ? (
          <span className="text-xs px-1.5 py-0.5 rounded bg-red-900/40 text-red-300 border border-red-700/50">⚠ DRONE FAILURE — Reassign</span>
        ) : readOnly ? (
          <span className="text-xs px-1.5 py-0.5 rounded bg-gray-700/60 text-gray-400 border border-gray-600/50">View Only</span>
        ) : (
          <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-900/40 text-yellow-300 border border-yellow-700/50">Tactical View</span>
        )}
        <div className="flex-1" />
        {!readOnly && <span className="text-xs text-gray-500">Drag → assign · Shift+drag → chain sequence</span>}
        {!readOnly && <button onClick={handleReset} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 text-xs transition-colors">Reset</button>}
        {!readOnly && !recoveryMode && (
          <button onClick={() => onMapAction({ _mapAction: 'OVERRIDE_TACTICAL', missionId: mission.id })}
            className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 text-xs transition-colors">Change Team</button>
        )}
        {!readOnly && (
          <button
            onClick={handleDeploy}
            disabled={!canDeploy}
            className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed rounded text-white text-sm font-semibold transition-colors"
          >
            Deploy{canDeploy ? ' ✓' : ''}
          </button>
        )}
      </div>

      {/* Body: SVG + right panel */}
      <div className="flex-1 flex overflow-hidden">
        {/* SVG area */}
        <div ref={containerRef} className="flex-1 overflow-hidden relative">
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
              setHoverHub(!!recoveryMode && Math.hypot(x - hubCornerX, y - hubCornerY) < 28)
            }}
            onPointerUp={e => {
              if (!dragging) return
              if (hoverHub) unassignDrone(dragging.droneId)
              else if (hoverTask) moveDrone(dragging.droneId, hoverTask, e.shiftKey)
              else unassignDrone(dragging.droneId)
              setDragging(null)
              setHoverTask(null)
              setHoverHub(false)
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

            {/* Zone */}
            <circle cx={cx} cy={cy} r={r} fill="rgba(29,78,216,0.06)" stroke="#1e40af" strokeWidth="1.5" />

            {/* HUB indicator */}
            <line x1={cx} y1={cy} x2={hubEdgeX} y2={hubEdgeY} stroke="#374151" strokeWidth="1" strokeDasharray="5 3" />
            <line x1={hubEdgeX} y1={hubEdgeY} x2={hubLabelX} y2={hubLabelY} stroke="#4b5563" strokeWidth="1" markerEnd="url(#arr-drag)" />
            <text x={hubLabelX} y={hubLabelY} textAnchor="middle" dy="3" fill="#6b7280" fontSize="8" fontFamily="monospace">HUB</text>

            {/* Recovery: HUB corner anchor — reserve drones cluster here; drag to it to unassign */}
            {recoveryMode && (
              <g>
                <circle cx={hubCornerX} cy={hubCornerY} r={24}
                  fill={hoverHub && dragging ? 'rgba(59,130,246,0.15)' : 'rgba(30,64,175,0.06)'}
                  stroke={hoverHub && dragging ? '#3b82f6' : '#1e3a8a'}
                  strokeWidth={1} strokeDasharray="4 3"
                  style={{ pointerEvents: 'none' }}
                />
                <text x={hubCornerX} y={hubCornerY - 30} textAnchor="middle"
                  fill="#60a5fa" fontSize="9" fontFamily="monospace" fontWeight="bold" style={{ pointerEvents: 'none' }}>
                  HUB RESERVE
                </text>
              </g>
            )}

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
                  <text x={fx} y={fy + 15} textAnchor="middle" fill="#6b7280" fontSize="7" fontFamily="monospace"
                    style={{ pointerEvents: 'none' }}>{resolveCallsign(fd.id, callsignMode)}</text>
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
                    {points.slice(0, -1).map((from, i) => {
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
              const complete = meetsPrimComp || meetsSubComp
              const isHovered = hoverTask === task.id && !!dragging

              // Completed tasks — always greyed out
              if (task.status === 'completed') {
                return (
                  <g key={task.id}>
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
                      textAnchor="middle" fill="#374151" fontSize="8" fontFamily="sans-serif"
                      style={{ pointerEvents: 'none' }}>
                      {TASK_TYPE_NAMES[task.type]}
                    </text>
                    <text x={task.waypoint.x} y={task.waypoint.y + 33}
                      textAnchor="middle" fill="#374151" fontSize="7" fontFamily="monospace"
                      style={{ pointerEvents: 'none' }}>✓ done</text>
                  </g>
                )
              }

              // Status badge shown in recovery mode for executing/traveling tasks (still interactive)
              const recoveryStatusLabel = recoveryMode && task.status !== 'pending'
                ? (task.status === 'executing' ? '⟳' : task.status === 'traveling' ? '→' : null)
                : null

              // Active / interactive task
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
                  <circle
                    cx={task.waypoint.x} cy={task.waypoint.y} r={isHovered ? 14 : 11}
                    fill={complete ? 'rgba(16,185,129,0.15)'
                      : recoveryStatusLabel ? 'rgba(245,158,11,0.08)'
                      : isHovered ? 'rgba(59,130,246,0.25)' : 'rgba(15,23,42,0.9)'}
                    stroke={complete ? '#10b981'
                      : recoveryStatusLabel ? '#f59e0b'
                      : isHovered ? '#3b82f6' : '#475569'}
                    strokeWidth={isHovered ? 2 : 1.5}
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
                    textAnchor="middle" fill="#94a3b8" fontSize="8" fontFamily="sans-serif"
                    style={{ pointerEvents: 'none' }}>
                    {TASK_TYPE_NAMES[task.type]}
                  </text>
                  {complete ? (
                    <text x={task.waypoint.x} y={task.waypoint.y + 33}
                      textAnchor="middle" fill="#4ade80" fontSize="7" fontFamily="monospace"
                      style={{ pointerEvents: 'none' }}>✓</text>
                  ) : (
                    <>
                      {/* Primary comp — per-type color (B=blue, R=red, G=green) */}
                      <text x={task.waypoint.x} y={task.waypoint.y + 33}
                        textAnchor="middle" fontSize="7" fontFamily="monospace"
                        style={{ pointerEvents: 'none' }}>
                        {[
                          req.Blue  > 0 ? { c: counts.Blue,  r: req.Blue,  key: 'B', col: '#60a5fa' } : null,
                          req.Red   > 0 ? { c: counts.Red,   r: req.Red,   key: 'R', col: '#f87171' } : null,
                          req.Green > 0 ? { c: counts.Green, r: req.Green, key: 'G', col: '#4ade80' } : null,
                        ].filter((p): p is { c: number; r: number; key: string; col: string } => p !== null)
                          .map((p, i) => (
                            <tspan key={p.key} fill={p.c >= p.r ? '#4ade80' : p.col}>
                              {i > 0 ? ' ' : ''}{p.c}/{p.r}{p.key}
                            </tspan>
                          ))}
                      </text>
                      {/* Alt comp */}
                      {sub && (
                        <text x={task.waypoint.x} y={task.waypoint.y + 42}
                          textAnchor="middle" fill="#6b7280" fontSize="6.5" fontFamily="monospace"
                          style={{ pointerEvents: 'none' }}>
                          {`OR ${[sub.Blue > 0 ? `${sub.Blue}B` : null, sub.Red > 0 ? `${sub.Red}R` : null, sub.Green > 0 ? `${sub.Green}G` : null].filter(Boolean).join('+')} `}
                        </text>
                      )}
                    </>
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
              const cs = resolveCallsign(droneId, callsignMode)
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
                    style={{ pointerEvents: 'none' }}>{cs}</text>
                  {(droneSequences[droneId]?.length ?? 0) > 0 && (
                    <text x={pos.x + 7} y={pos.y - 5} textAnchor="middle"
                      fill="#fb923c" fontSize="6" fontFamily="monospace"
                      style={{ pointerEvents: 'none' }}>
                      {droneSequences[droneId].length}
                    </text>
                  )}
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
          callsignMode={callsignMode}
          onRemove={removeDrone}
          canDeploy={canDeploy}
          onDeploy={handleDeploy}
          recoveryMode={!!recoveryMode}
          failedDroneId={failedDroneIdRef.current ?? null}
        />
      </div>
    </div>
  )
}

// ─── Tactical right panel ─────────────────────────────────────────────────

function TacticalRightPanel({ pending, assignments, assets, tasks, timings, callsignMode, onRemove, canDeploy, onDeploy, recoveryMode, failedDroneId }: {
  pending: PendingAllocation
  assignments: Record<string, string[]>
  assets: Asset[]
  tasks: Task[]
  timings: { taskStarts: Record<string, number>; droneWaits: Record<string, Record<string, number>> }
  callsignMode: CallsignMode
  onRemove: (droneId: string, taskId: string) => void
  canDeploy: boolean
  onDeploy: () => void
  recoveryMode?: boolean
  failedDroneId?: string | null
}) {
  const ASSET_COLOR_TEXT: Record<AssetType, string> = { Blue: 'text-blue-400', Red: 'text-red-400', Green: 'text-green-400' }
  const ASSET_BG: Record<AssetType, string> = { Blue: 'bg-blue-900/50 border-blue-700/50', Red: 'bg-red-900/50 border-red-700/50', Green: 'bg-emerald-900/50 border-emerald-700/50' }

  // Unassigned drones (for reference list)
  const unassigned = pending.dronePool.filter(id =>
    !pending.taskOrder.some(tid => (assignments[tid] ?? []).includes(id))
  )

  function getType(id: string): AssetType { return assets.find(a => a.id === id)?.type ?? 'Blue' }
  function getCS(id: string): string { return resolveCallsign(id, callsignMode) }

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
    <div className="w-[560px] flex-none border-l border-gray-800 bg-gray-900 flex flex-col overflow-hidden">
      {/* Failure banner */}
      {recoveryMode && failedDroneId && (() => {
        const fd = assets.find(a => a.id === failedDroneId)
        if (!fd) return null
        return (
          <div className="flex-none px-3 py-2 border-b border-red-900/60 bg-red-950/30 flex items-center gap-2">
            <span className="text-red-400 text-[10px] font-bold uppercase tracking-wider">⚠ Drone Failed</span>
            <div className={`flex items-center gap-1 px-1.5 py-0.5 rounded border border-red-800/50 bg-red-900/20 ml-1`}>
              <img src={DRONE_ICON[fd.type]} className="w-3.5 h-3.5 flex-none grayscale opacity-50" alt="" />
              <span className="font-mono text-[10px] text-gray-500 line-through">{getCS(failedDroneId)}</span>
            </div>
            <span className="text-gray-500 text-[9px] ml-auto">Reassign its task below</span>
          </div>
        )
      })()}
      {/* Unassigned reference list */}
      {unassigned.length > 0 && (
        <div className="flex-none p-3 border-b border-gray-800">
          <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">
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
                  className={`flex items-center gap-1 px-1.5 py-0.5 rounded border text-xs cursor-grab select-none ${ASSET_BG[type]}`}
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
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Task Schedule</p>
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
          const complete = meetsPrimRP || meetsSubRP
          const tStart = timings.taskStarts[taskId]
          const tEnd = tStart !== undefined ? Math.round(tStart + baseTime) : null

          return (
            <div key={taskId}
              className={`rounded border p-2 text-xs space-y-1.5 ${complete ? 'border-green-800/60 bg-green-950/10' : 'border-gray-700 bg-gray-800/40'}`}
            >
              {/* Header */}
              <div className="flex items-center gap-1.5">
                <span className="text-[9px] text-gray-500 font-mono">#{idx + 1}</span>
                <img src={TASK_ICON[task.type as TaskType]} className="w-4 h-4 flex-none" alt="" />
                <span className={`font-medium ${complete ? 'text-green-300' : 'text-gray-200'}`}>
                  {TASK_TYPE_NAMES[task.type]}
                </span>
                {complete && <span className="ml-auto text-green-400 text-[10px]">✓</span>}
              </div>

              {/* Required composition */}
              <div className="space-y-0.5">
                <div className="flex items-center gap-1">
                  <span className="text-[9px] text-gray-500 w-8">Req:</span>
                  <span className="text-gray-300 font-mono text-[10px]">{compToLabel(req, baseTime)}</span>
                </div>
                {sub && (
                  <div className="flex items-center gap-1">
                    <span className="text-[9px] text-gray-600 w-8">OR:</span>
                    <span className="text-gray-500 font-mono text-[10px]">{compToLabel(sub, subTime)}</span>
                  </div>
                )}
              </div>

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
                          <span className={`font-mono text-[10px] ${ASSET_COLOR_TEXT[tp]}`}>{cs}</span>
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
                    <div className={`text-[9px] font-mono ${task.status === 'executing' ? 'text-amber-400' : 'text-blue-400'}`}>
                      {task.status === 'executing' ? '⟳ executing' : '→ traveling'}
                    </div>
                  )}
                  {/* Comp progress */}
                  {!complete && (
                    <div className="text-amber-400 font-mono text-[9px]">{buildCompLabel(counts, req)}</div>
                  )}
                </div>
              )}

              {assigned.length === 0 && (
                <p className="text-gray-600 text-[10px] italic">No drones assigned</p>
              )}

              {/* Timing */}
              {tStart !== undefined && (
                <div className="text-gray-500 text-[9px] font-mono border-t border-gray-700/50 pt-1">
                  Start ~{Math.round(tStart)}s · Done ~{tEnd}s
                </div>
              )}

              {/* Wait times — only shown when comp fully met */}
              {complete && Object.entries(timings.droneWaits[taskId] ?? {}).map(([droneId, wait]) => (
                <div key={droneId} className="text-[9px] text-orange-400">
                  {getCS(droneId)} waiting {wait} seconds
                </div>
              ))}
            </div>
          )
        })}
      </div>

      {/* Footer: ETA + Deploy */}
      <div className="flex-none p-3 border-t border-gray-800 space-y-2">
        {overallETA !== null && (
          <div className="text-xs text-gray-400">
            Est. completion: <span className="text-white font-mono font-bold">~{overallETA}s</span>
          </div>
        )}
        <button
          onClick={onDeploy}
          disabled={!canDeploy}
          className="w-full py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed rounded text-white text-sm font-semibold transition-colors"
        >
          {canDeploy ? 'Deploy ✓' : 'Deploy (incomplete)'}
        </button>
      </div>
    </div>
  )
}

export type { MapViewState }
