import type {
  GameState, GameEvent, Asset, Mission, Task,
  AssetType, TaskType, AssetRequirement,
  MissionCategory, TaskComp, RecoveryOption,
  PendingAllocation, MissionBlueprint,
} from '../types'
import type { GameAction } from './actions'
import {
  HUB, ASSET_SPEED, TASK_BASE_TIME, TASK_PRIMARY, TASK_SUBSTITUTE,
  TASK_SUB_BASE_TIME, ZONE_RADIUS, CATEGORY_PENALTY_RATE, TASK_WEIGHT,
  generateSessionPlan, createInitialAssets, travelTime,
  SESSION_DURATION_BY_COMPLEXITY,
} from '../utils/missionGen'
import { generateStrategies } from '../utils/copilot'
import { SeededRNG } from '../utils/prng'
import { debugLog } from '../utils/debugLog'
import type { StudyConfig } from '../types'

// ─── Constants ────────────────────────────────────────────────────────────

const TRUST_PROBE_INTERVAL = 90  // seconds

function hashId(id: string): number {
  return id.split('').reduce((acc, c, i) => (acc ^ (c.charCodeAt(0) * (i + 7))) >>> 0, 0)
}

// ─── Tutorial first-mission blueprint ─────────────────────────────────────
// Fixed 4-task mission: T1 Recce + T1 Recce + T3 Supply + T5 Search & Service
// Uses all three drone types; the two T1s naturally demonstrate chaining.
// No failures so the tutorial flow stays clean.

const TUTORIAL_FIRST_BLUEPRINT: MissionBlueprint = {
  id: 'T001',
  arrivalTime: 0,  // overridden by FORCE_MISSION_ARRIVAL
  category: 'C',
  taskTypes: [1, 1, 3, 5],
  zoneCenter: { x: 220, y: 180 },
  waypoints: [
    { x: 200, y: 155 },  // T1 — northwest
    { x: 248, y: 162 },  // T1 — north-northeast
    { x: 255, y: 205 },  // T3 — east
    { x: 195, y: 220 },  // T5 — south
  ],
  willFail: false,
  droneFailureTimes: [],
}

// ─── Initial state factory ─────────────────────────────────────────────────

export function buildInitialState(config: StudyConfig): GameState {
  const generated = generateSessionPlan(new SeededRNG(config.seed ^ 1), config.complexity)
  const blueprints = config.tutorialMode
    ? [TUTORIAL_FIRST_BLUEPRINT, ...generated]
    : generated

  const baseCategories: Record<MissionCategory, number> = { A: 0, B: 0, C: 0, D: 0, E: 0 }
  const initialForecast = { ...baseCategories }
  // Default to complexity-appropriate prior
  switch (config.complexity) {
    case 'balanced':  Object.assign(initialForecast, { A: 0.20, B: 0.30, C: 0.28, D: 0.17, E: 0.05 }); break
    case 'strategic': Object.assign(initialForecast, { A: 0.40, B: 0.38, C: 0.16, D: 0.05, E: 0.01 }); break
    case 'tactical':  Object.assign(initialForecast, { A: 0.03, B: 0.08, C: 0.22, D: 0.42, E: 0.25 }); break
    case 'full':      Object.assign(initialForecast, { A: 0.05, B: 0.15, C: 0.28, D: 0.32, E: 0.20 }); break
    case 'quick':     Object.assign(initialForecast, { A: 0.35, B: 0.30, C: 0.20, D: 0.12, E: 0.03 }); break
  }

  return {
    config,
    phase: 'playing',
    sessionNumber: 1,
    elapsed: 0,
    sessionStartMs: null,
    assets: createInitialAssets(config.complexity),
    missions: [],
    pendingBlueprints: blueprints,
    score: 0,
    penaltyAccrued: 0,
    completedSessionScores: [],
    sessionDuration: SESSION_DURATION_BY_COMPLEXITY[config.complexity],
    categoryForecast: initialForecast,
    strategicModal: null,
    trustProbeActive: false,
    nextTrustProbeAt: TRUST_PROBE_INTERVAL,
    events: [[], [], []],
  }
}

// ─── Helper: log event ────────────────────────────────────────────────────

// Distributive Omit so it works across the discriminated union
type EventPayload = GameEvent extends infer E
  ? E extends { timestamp: number; sessionNumber: number; elapsed: number; reserveState: AssetRequirement }
    ? Omit<E, 'timestamp' | 'sessionNumber' | 'elapsed' | 'reserveState'>
    : never
  : never

function logEvent(state: GameState, event: EventPayload): GameState {
  const full: GameEvent = {
    ...event,
    timestamp: Math.round(state.elapsed * 1000),
    sessionNumber: state.sessionNumber,
    elapsed: state.elapsed,
    reserveState: reserveCount(state.assets),
  } as GameEvent
  const idx = state.sessionNumber - 1
  const updated = [...state.events]
  updated[idx] = [...updated[idx], full]
  return { ...state, events: updated }
}

// ─── Helper: current reserve ──────────────────────────────────────────────

export function reserveCount(assets: Asset[]): AssetRequirement {
  return {
    Blue:  assets.filter(a => a.type === 'Blue'  && a.status === 'available').length,
    Red:   assets.filter(a => a.type === 'Red'   && a.status === 'available').length,
    Green: assets.filter(a => a.type === 'Green' && a.status === 'available').length,
  }
}

// Returns assets that are available AND not already locked into another mission's pending plan.
// Prevents double-allocation when multiple missions are in the tactical-pending state simultaneously.
function availableExcludingPending(assets: Asset[], missions: Mission[], excludeMissionId: string): Asset[] {
  const locked = new Set<string>()
  for (const m of missions) {
    if (m.id === excludeMissionId) continue
    if (m.tacticalPending && m.pendingAllocation) {
      for (const id of m.pendingAllocation.dronePool) locked.add(id)
    }
  }
  return assets.filter(a => a.status === 'available' && !locked.has(a.id))
}

// ─── Helper: greedy asset assignment with sequential reuse ────────────────

interface TaskAssignment {
  taskId: string
  assetIds: string[]
  startTime: number      // absolute elapsed time when execution begins
  travelTime: number     // effective wait from allocation moment (for task record)
  baseTime: number
  useSubstitute: boolean
}

/**
 * Assigns assets to tasks using a virtual-timeline scheduler.
 */
function greedyAssign(
  tasks: Task[],
  availableAssets: Asset[],
  committed: AssetRequirement,
  now: number,
  plan?: Record<string, TaskComp>,
  taskOrderIds: string[] = [],
): TaskAssignment[] {
  interface VAsset { id: string; type: AssetType; freeAt: number; pos: { x: number; y: number } }

  const vPool: VAsset[] = [
    ...availableAssets.filter(a => a.type === 'Blue').slice(0, committed.Blue)
      .map(a => ({ id: a.id, type: 'Blue' as AssetType, freeAt: now, pos: { ...HUB } })),
    ...availableAssets.filter(a => a.type === 'Red').slice(0, committed.Red)
      .map(a => ({ id: a.id, type: 'Red' as AssetType, freeAt: now, pos: { ...HUB } })),
    ...availableAssets.filter(a => a.type === 'Green').slice(0, committed.Green)
      .map(a => ({ id: a.id, type: 'Green' as AssetType, freeAt: now, pos: { ...HUB } })),
  ]

  // Sort tasks: if taskOrderIds provided, use that order, else T5→T1
  let sorted: Task[]
  if (taskOrderIds.length > 0) {
    const priorityTasks = taskOrderIds
      .map(id => tasks.find(t => t.id === id))
      .filter((t): t is Task => t !== undefined)
    const remaining = tasks
      .filter(t => !taskOrderIds.includes(t.id))
      .sort((a, b) => b.type - a.type)
    sorted = [...priorityTasks, ...remaining]
  } else {
    sorted = [...tasks].sort((a, b) => b.type - a.type)
  }

  const assignments: TaskAssignment[] = []

  const pickEarliest = (type: AssetType, n: number): VAsset[] =>
    vPool.filter(v => v.type === type)
         .sort((a, b) => a.freeAt - b.freeAt)
         .slice(0, n)

  for (const task of sorted) {
    // ── Determine composition ───────────────────────────────────────────────
    let reqBlue: number, reqRed: number, reqGreen: number
    let baseTime: number, useSubstitute: boolean

    const planned = plan?.[task.id]
    if (planned) {
      reqBlue = planned.Blue; reqRed = planned.Red; reqGreen = planned.Green
      baseTime = planned.baseTime; useSubstitute = planned.useSubstitute
    } else {
      // Manual: primary → substitute
      const prim = TASK_PRIMARY[task.type as TaskType]
      const sub  = TASK_SUBSTITUTE[task.type as TaskType]
      const avB = vPool.filter(v => v.type === 'Blue').length
      const avR = vPool.filter(v => v.type === 'Red').length
      const avG = vPool.filter(v => v.type === 'Green').length
      if (avB >= prim.Blue && avR >= prim.Red && avG >= prim.Green) {
        reqBlue = prim.Blue; reqRed = prim.Red; reqGreen = prim.Green
        baseTime = TASK_BASE_TIME[task.type as TaskType]; useSubstitute = false
      } else if (sub && avB >= sub.Blue && avR >= sub.Red && avG >= sub.Green) {
        reqBlue = sub.Blue; reqRed = sub.Red; reqGreen = sub.Green
        baseTime = TASK_SUB_BASE_TIME[task.type as TaskType]; useSubstitute = true
      } else {
        debugLog('greedyAssign: skip task (no comp fits)', { taskId: task.id, type: task.type, avB, avR, avG })
        continue
      }
    }

    // ── Pick earliest-available tokens ─────────────────────────────────────
    {
      const avB = vPool.filter(v => v.type === 'Blue').length
      const avR = vPool.filter(v => v.type === 'Red').length
      const avG = vPool.filter(v => v.type === 'Green').length
      if ((avB < reqBlue || avR < reqRed || avG < reqGreen) && !useSubstitute) {
        const sub = TASK_SUBSTITUTE[task.type as TaskType]
        if (sub && avB >= sub.Blue && avR >= sub.Red && avG >= sub.Green) {
          reqBlue = sub.Blue; reqRed = sub.Red; reqGreen = sub.Green
          baseTime = TASK_SUB_BASE_TIME[task.type as TaskType]; useSubstitute = true
        }
      }
    }

    const blueV  = pickEarliest('Blue',  reqBlue)
    const redV   = pickEarliest('Red',   reqRed)
    const greenV = pickEarliest('Green', reqGreen)

    if (blueV.length < reqBlue || redV.length < reqRed || greenV.length < reqGreen) {
      debugLog('greedyAssign: skip task (pool exhausted)', { taskId: task.id, reqBlue, reqRed, reqGreen })
      continue
    }

    const picked = [...blueV, ...redV, ...greenV]

    const startTime = Math.max(
      now,
      ...picked.map(v => v.freeAt + travelTime(v.pos, task.waypoint, ASSET_SPEED[v.type])),
    )
    const completionTime = startTime + baseTime

    for (const v of picked) {
      v.freeAt = completionTime
      v.pos = { ...task.waypoint }
    }

    assignments.push({
      taskId: task.id,
      assetIds: picked.map(v => v.id),
      startTime,
      travelTime: startTime - now,
      baseTime,
      useSubstitute,
    })
  }

  debugLog('greedyAssign result', {
    committed, taskCount: tasks.length, assigned: assignments.length,
    tasks: assignments.map(a => ({ taskId: a.taskId, assetIds: a.assetIds, startTime: Math.round(a.startTime) })),
  })

  return assignments
}

// ─── Helper: spawn mission from blueprint ────────────────────────────────

function spawnMission(bp: ReturnType<typeof generateSessionPlan>[0]): Mission {
  const tasks: Task[] = bp.taskTypes.map((type, i) => ({
    id: `${bp.id}-T${i + 1}`,
    missionId: bp.id,
    type,
    status: 'pending' as const,
    waypoint: bp.waypoints[i],
    assignedAssetIds: [],
    allocatedAt: null,
    travelTime: 0,
    baseTime: TASK_BASE_TIME[type],
    startTime: null,
    completionTime: null,
    useSubstitute: false,
    recallDelay: 0,
  }))

  return {
    id: bp.id,
    category: bp.category,
    status: 'queued',
    zoneCenter: bp.zoneCenter,
    zoneRadius: ZONE_RADIUS,
    tasks,
    arrivalTime: bp.arrivalTime,
    allocationTime: null,
    completionTime: null,
    agentInteraction: 'none',
    chosenStrategyName: null,
    manualPriorityIds: [],
    tacticalPending: false,
    pendingAllocation: null,
    droneSequences: {},
    droneFailureTimes: bp.droneFailureTimes,
    droneFailuresFired: 0,
    failedDroneId: null,
    failureRecoveryPending: false,
    pendingRecoveryOptions: null,
    tacticallySuppressedTaskId: null,
    abandonedAt: null,
    isResidual: false,
    needsGreedyReplan: false,
  }
}

// ─── Helper: interpolate asset position ──────────────────────────────────

function interpolateAssetPosition(asset: Asset, elapsed: number): { x: number; y: number } {
  const { travelStartElapsed, travelEndElapsed, travelFrom, targetPosition } = asset
  if (travelEndElapsed <= travelStartElapsed) return { ...targetPosition }
  const frac = Math.min(1, Math.max(0,
    (elapsed - travelStartElapsed) / (travelEndElapsed - travelStartElapsed),
  ))
  return {
    x: travelFrom.x + (targetPosition.x - travelFrom.x) * frac,
    y: travelFrom.y + (targetPosition.y - travelFrom.y) * frac,
  }
}

// ─── Helper: compute session score metrics ───────────────────────────────

function computeCompletionPoints(missions: Mission[]): number {
  let pts = 0
  for (const m of missions) {
    for (const t of m.tasks) {
      if (t.status === 'completed') pts += TASK_WEIGHT[t.type]
    }
  }
  return pts
}

function computePenaltyAccrued(missions: Mission[], elapsed: number): number {
  let penalty = 0
  for (const m of missions) {
    const totalWeight = m.tasks.reduce((s, t) => s + TASK_WEIGHT[t.type], 0)
    if (totalWeight === 0) continue
    const missionRate = CATEGORY_PENALTY_RATE[m.category]
    for (const t of m.tasks) {
      const taskRate = missionRate * TASK_WEIGHT[t.type] / totalWeight
      const endTime = t.completionTime ?? elapsed
      penalty += taskRate * Math.max(0, endTime - m.arrivalTime)
    }
  }
  return Math.round(penalty)
}

function computeScore(missions: Mission[], elapsed: number): { score: number; penaltyAccrued: number } {
  const completion = computeCompletionPoints(missions)
  const penalty = computePenaltyAccrued(missions, elapsed)
  return { score: Math.max(0, completion - penalty), penaltyAccrued: penalty }
}

function computeGreenEfficiency(missions: Mission[]): number {
  let greenOnT45 = 0
  let greenTotal = 0
  for (const m of missions) {
    for (const t of m.tasks) {
      if (!t.completionTime || !t.startTime) continue
      const time = t.completionTime - t.startTime
      const greenAssigned = t.assignedAssetIds.some(id => id.startsWith('G'))
      if (greenAssigned) {
        greenTotal += time
        if (t.type === 4 || t.type === 5) greenOnT45 += time
      }
    }
  }
  return greenTotal > 0 ? greenOnT45 / greenTotal : 1
}

function computeMeanMissionTime(missions: Mission[]): number {
  const completed = missions.filter(m => m.status === 'completed' && m.completionTime && m.allocationTime)
  if (completed.length === 0) return 0
  const sum = completed.reduce((acc, m) => acc + (m.completionTime! - m.allocationTime!), 0)
  return sum / completed.length
}

// ─── Helper: build recovery options ───────────────────────────────────────

function buildRecoveryOptions(
  mission: Mission,
  failedTask: Task,
  failedDroneId: string,
  assets: Asset[],
  _elapsed: number,
): RecoveryOption[] {
  // Only redistribution — operators must fix failures with their deployed subswarm
  const otherDrone = assets.find(a =>
    a.currentMissionId === mission.id &&
    a.id !== failedDroneId &&
    a.status === 'deployed' &&
    mission.tasks.find(t => t.id === a.currentTaskId)?.status !== 'executing'
  )
  return [{
    type: 'redistribute',
    label: 'Redistribute',
    description: otherDrone
      ? `Reassign task to ${otherDrone.id} (currently between tasks)`
      : 'No available drone within mission to reassign',
    taskId: failedTask.id,
    newAssetId: null,
    redistributeToAssetId: otherDrone?.id ?? null,
    expectedTimeImpact: otherDrone ? 60 : 0,
    feasible: otherDrone !== undefined,
  }]
}

// ─── Helper: apply tactical allocation ────────────────────────────────────

function applyTacticalAllocation(
  state: GameState,
  missionId: string,
  assignments: TaskAssignment[],
  pending: PendingAllocation,
  taskOrder: string[],
  modifiedFromAgentPlan: boolean,
  droneSequences: Record<string, string[]> = {},
  chainingUsed = false,
  changedTaskIds: string[] = [],
): GameState {
  const mission = state.missions.find(m => m.id === missionId)!
  const now = state.elapsed

  const allAssignedIds = [...new Set(assignments.flatMap(a => a.assetIds))]

  const updatedTaskMap = new Map<string, Task>()
  for (const task of mission.tasks) {
    const asgn = assignments.find(a => a.taskId === task.id)
    updatedTaskMap.set(task.id, asgn ? {
      ...task,
      status: 'traveling' as const,
      assignedAssetIds: asgn.assetIds,
      allocatedAt: now,
      travelTime: asgn.travelTime,
      baseTime: asgn.baseTime,
      useSubstitute: asgn.useSubstitute,
      startTime: asgn.startTime,
      completionTime: asgn.startTime + asgn.baseTime,
      recallDelay: 0,
    } : task)
  }

  const updatedTasks: Task[] = taskOrder
    .map(id => updatedTaskMap.get(id))
    .filter((t): t is Task => t !== undefined)

  // Also include tasks not in taskOrder (shouldn't normally happen, but be safe)
  const tasksInOrder = new Set(taskOrder)
  for (const task of mission.tasks) {
    if (!tasksInOrder.has(task.id)) {
      const existing = updatedTaskMap.get(task.id)
      if (existing) updatedTasks.push(existing)
    }
  }

  const updatedMission: Mission = {
    ...mission,
    status: 'active',
    tasks: updatedTasks,
    allocationTime: now,
    tacticalPending: false,
    pendingAllocation: null,
    droneSequences,
    agentInteraction: modifiedFromAgentPlan ? 'overridden' : pending.isAgentSuggested ? 'followed' : 'manual',
    chosenStrategyName: pending.strategyName,
    manualPriorityIds: [],
  }

  const updatedAssets = state.assets.map(asset => {
    const myAsgns = assignments.filter(a => a.assetIds.includes(asset.id))
    if (myAsgns.length === 0) return asset
    // Safety: don't re-deploy a drone that is already deployed elsewhere (stale pending pool)
    if (asset.status !== 'available') return asset
    const firstAsgn = myAsgns.reduce((min, a) => a.startTime < min.startTime ? a : min)
    const task = updatedTasks.find(t => t.id === firstAsgn.taskId)!
    const tt = travelTime(HUB, task.waypoint, ASSET_SPEED[asset.type])
    return {
      ...asset,
      status: 'deployed' as const,
      currentMissionId: mission.id,
      currentTaskId: task.id,
      travelFrom: { ...HUB },
      targetPosition: task.waypoint,
      travelStartElapsed: now,
      travelEndElapsed: now + tt,
      availableAt: now + tt + firstAsgn.baseTime + travelTime(task.waypoint, HUB, ASSET_SPEED[asset.type]),
    }
  })

  let s: GameState = {
    ...state,
    missions: state.missions.map(m => m.id === missionId ? updatedMission : m),
    assets: updatedAssets,
  }

  s = logEvent(s, {
    type: 'tactical_confirmed',
    missionId: mission.id,
    missionCategory: mission.category,
    wasAgentSuggested: pending.isAgentSuggested,
    modifiedFromAgentPlan,
    changedTaskIds,
    chainingUsed,
    assetsDeployed: allAssignedIds,
    timeRemainingInSession: Math.max(0, state.sessionDuration - now),
  })

  return s
}

// ─── Helper: build assignments from manual drag-and-drop ──────────────────

/**
 * Computes task start times respecting the user's per-drone chain order.
 * Uses 3-pass iteration so multi-drone tasks (where each drone's arrival
 * depends on the previous task in its sequence) converge correctly.
 */
function buildManualAssignments(
  mission: Mission,
  assets: Asset[],
  taskAssignments: Record<string, string[]>,
  droneSequences: Record<string, string[]>,
  elapsed: number,
): TaskAssignment[] {
  const assetById = new Map(assets.map(a => [a.id, a]))
  const allDroneIds = [...new Set(Object.values(taskAssignments).flat())]

  // Iteratively converge task start times.
  // Pass N uses taskStarts from pass N-1 to compute drone departure times.
  const taskStarts: Record<string, number> = {}

  for (let pass = 0; pass < 3; pass++) {
    // Reset per-drone state at start of each pass
    const droneFreeAt: Record<string, number> = {}
    const dronePos: Record<string, { x: number; y: number }> = {}
    for (const id of allDroneIds) { droneFreeAt[id] = elapsed; dronePos[id] = { ...HUB } }

    // Reset task starts for re-computation this pass
    for (const taskId of Object.keys(taskAssignments)) delete taskStarts[taskId]

    // Forward-sweep each drone's sequence, accumulating max arrivals per task
    for (const droneId of allDroneIds) {
      const asset = assetById.get(droneId)
      if (!asset) continue
      const speed = ASSET_SPEED[asset.type]
      const seq = droneSequences[droneId] ?? []

      for (const taskId of seq) {
        const task = mission.tasks.find(t => t.id === taskId)
        if (!task) continue
        const arrival = droneFreeAt[droneId] + travelTime(dronePos[droneId], task.waypoint, speed)
        taskStarts[taskId] = Math.max(taskStarts[taskId] ?? arrival, arrival)
        // Drone departs after the task finishes (using updated taskStart from this pass)
        const baseTime = getManualBaseTime(task, taskAssignments[taskId] ?? [], assetById)
        droneFreeAt[droneId] = taskStarts[taskId] + baseTime
        dronePos[droneId] = { ...task.waypoint }
      }
    }
  }

  // Build TaskAssignment records from converged start times
  const result: TaskAssignment[] = []
  for (const [taskId, droneIds] of Object.entries(taskAssignments)) {
    const task = mission.tasks.find(t => t.id === taskId)
    if (!task || droneIds.length === 0 || taskStarts[taskId] === undefined) continue
    const startTime = taskStarts[taskId]
    const baseTime = getManualBaseTime(task, droneIds, assetById)
    const useSubstitute = isUsingSubstitute(task, droneIds, assetById)
    result.push({ taskId, assetIds: droneIds, startTime, travelTime: startTime - elapsed, baseTime, useSubstitute })
  }
  return result
}

function getManualBaseTime(task: Task, droneIds: string[], assetById: Map<string, Asset>): number {
  const prim = TASK_PRIMARY[task.type as TaskType]
  const sub  = TASK_SUBSTITUTE[task.type as TaskType]
  const comp: AssetRequirement = { Blue: 0, Red: 0, Green: 0 }
  for (const id of droneIds) { const a = assetById.get(id); if (a) comp[a.type]++ }
  if (sub && !(comp.Blue >= prim.Blue && comp.Red >= prim.Red && comp.Green >= prim.Green)
      && comp.Blue >= sub.Blue && comp.Red >= sub.Red && comp.Green >= sub.Green) {
    return TASK_SUB_BASE_TIME[task.type as TaskType]
  }
  return TASK_BASE_TIME[task.type as TaskType]
}

function isUsingSubstitute(task: Task, droneIds: string[], assetById: Map<string, Asset>): boolean {
  const prim = TASK_PRIMARY[task.type as TaskType]
  const sub  = TASK_SUBSTITUTE[task.type as TaskType]
  const comp: AssetRequirement = { Blue: 0, Red: 0, Green: 0 }
  for (const id of droneIds) { const a = assetById.get(id); if (a) comp[a.type]++ }
  if (!sub) return false
  return !(comp.Blue >= prim.Blue && comp.Red >= prim.Red && comp.Green >= prim.Green)
    && comp.Blue >= sub.Blue && comp.Red >= sub.Red && comp.Green >= sub.Green
}

// ─── Reducer ──────────────────────────────────────────────────────────────

export function gameReducer(state: GameState, action: GameAction): GameState {
  switch (action.type) {

    // ── TICK ────────────────────────────────────────────────────────────────
    case 'TICK': {
      if (state.phase !== 'playing') return state

      // Initialise wall-clock reference on first tick
      const sessionStartMs = state.sessionStartMs ?? action.nowMs
      const rawElapsed = (action.nowMs - sessionStartMs) / 1000
      const elapsed = state.config.testingMode ? rawElapsed : Math.min(state.sessionDuration, rawElapsed)

      let s: GameState = { ...state, elapsed, sessionStartMs }

      // 1. Spawn missions whose arrivalTime has passed (suppressed in testing mode)
      const toSpawn = state.config.testingMode ? [] : s.pendingBlueprints.filter(bp => bp.arrivalTime <= elapsed)
      if (toSpawn.length > 0) {
        const newMissions: Mission[] = toSpawn.map(spawnMission)
        s = { ...s, pendingBlueprints: s.pendingBlueprints.filter(bp => bp.arrivalTime > elapsed) }
        for (const m of newMissions) {
          s = { ...s, missions: [...s.missions, m] }
          s = logEvent(s, {
            type: 'mission_arrived',
            missionId: m.id,
            category: m.category,
            tasks: m.tasks.map(t => ({ id: t.id, type: t.type })),
            zoneCenter: m.zoneCenter,
            arrivalTime: m.arrivalTime,
            timeRemainingInSession: Math.max(0, state.sessionDuration - elapsed),
          })
        }
      }

      // 1b. Drone failure check (suppressed in testing mode)
      // Each mission has multiple scheduled failure times; fire at most one per tick,
      // and wait for any pending recovery to be resolved before the next failure.
      if (!state.config.testingMode) {
        for (const mission of s.missions) {
          if (mission.status !== 'active') continue
          if (mission.droneFailuresFired >= mission.droneFailureTimes.length) continue
          if (mission.failureRecoveryPending) continue  // wait for operator to resolve previous failure
          const nextFailTime = mission.droneFailureTimes[mission.droneFailuresFired]
          if (elapsed < mission.arrivalTime + nextFailTime) continue

          // Pick a random deployed drone on this mission that is currently executing
          const executingDrones = s.assets.filter(
            a => a.currentMissionId === mission.id && (a.status === 'deployed') &&
              mission.tasks.find(t => t.id === a.currentTaskId)?.status === 'executing'
          )
          if (executingDrones.length === 0) continue  // no executing drones yet, wait

          // Seeded random pick — seed varies by fired count so each failure picks a different drone
          const failRng = new SeededRNG(s.config.seed ^ mission.id.charCodeAt(1) ^ 0xfa11 ^ mission.droneFailuresFired)
          const failedDrone = executingDrones[failRng.randInt(0, executingDrones.length - 1)]
          const failedTask = mission.tasks.find(t => t.id === failedDrone.currentTaskId)!

          // Mark drone as failed; schedule replacement arrival at hub in 30–45 s
          const replaceRng = new SeededRNG(s.config.seed ^ 0x4E3B ^ mission.droneFailuresFired)
          const replacementDelay = 30 + replaceRng.randFloat(0, 15)
          const updatedAssets = s.assets.map(a =>
            a.id === failedDrone.id
              ? { ...a, status: 'failed' as const, failedAt: elapsed, currentMissionId: null, currentTaskId: null, replacementAt: elapsed + replacementDelay }
              : a
          )
          // Revert task to pending, clear its assignment
          const updatedMissions = s.missions.map(m => {
            if (m.id !== mission.id) return m
            return {
              ...m,
              droneFailuresFired: m.droneFailuresFired + 1,
              failedDroneId: failedDrone.id,
              failureRecoveryPending: true,
              tasks: m.tasks.map(t =>
                t.id === failedTask.id
                  ? { ...t, status: 'pending' as const, assignedAssetIds: t.assignedAssetIds.filter(id => id !== failedDrone.id), startTime: null, completionTime: null }
                  : t
              ),
              pendingRecoveryOptions: buildRecoveryOptions(m, failedTask, failedDrone.id, s.assets, elapsed),
            }
          })

          s = { ...s, assets: updatedAssets, missions: updatedMissions }
          s = logEvent(s, {
            type: 'drone_failure',
            missionId: mission.id,
            missionCategory: mission.category,
            droneId: failedDrone.id,
            droneType: failedDrone.type,
            taskId: failedTask.id,
            taskType: failedTask.type,
            timeRemainingInSession: Math.max(0, state.sessionDuration - elapsed),
          })
          break  // at most one new failure per tick
        }
      }

      // 2. Advance task status based on elapsed time
      const updatedMissions = s.missions.map(mission => {
        if (mission.status !== 'active') return mission

        let missionChanged = false
        const updatedTasks = mission.tasks.map(task => {
          if (task.status === 'traveling' && task.startTime !== null && elapsed >= task.startTime) {
            missionChanged = true
            return { ...task, status: 'executing' as const }
          }
          if (task.status === 'executing' && task.completionTime !== null && elapsed >= task.completionTime) {
            missionChanged = true
            return { ...task, status: 'completed' as const }
          }
          return task
        })

        if (!missionChanged) return mission

        const allDone = updatedTasks.every(t => t.status === 'completed' || t.status === 'failed')
        return {
          ...mission,
          tasks: updatedTasks,
          status: allDone ? ('completed' as const) : ('active' as const),
          completionTime: allDone ? elapsed : mission.completionTime,
        }
      })

      // 3. Collect task completion events
      for (let mi = 0; mi < s.missions.length; mi++) {
        const oldM = s.missions[mi]
        const newM = updatedMissions[mi]
        for (let ti = 0; ti < oldM.tasks.length; ti++) {
          const oldT = oldM.tasks[ti]
          const newT = newM.tasks[ti]
          if (oldT && newT && oldT.status !== 'completed' && newT.status === 'completed') {
            s = logEvent(s, {
              type: 'task_completed',
              missionId: newM.id,
              taskId: newT.id,
              taskType: newT.type,
              assetsUsed: newT.assignedAssetIds,
              completionTime: elapsed,
            })
          }
        }
      }

      s = { ...s, missions: updatedMissions }

      // 3b. Tactical lockout: detect suppressed tasks that will never receive drones
      // When all other tasks in the mission are complete/failed, fail the suppressed task.
      for (const mission of s.missions) {
        if (mission.status !== 'active' || !mission.tacticallySuppressedTaskId) continue
        const suppTask = mission.tasks.find(t => t.id === mission.tacticallySuppressedTaskId)
        if (!suppTask || suppTask.status !== 'pending' || suppTask.assignedAssetIds.length > 0) continue
        const othersDone = mission.tasks
          .filter(t => t.id !== suppTask.id)
          .every(t => t.status === 'completed' || t.status === 'failed')
        if (!othersDone) continue
        s = {
          ...s,
          missions: s.missions.map(m => m.id === mission.id ? {
            ...m,
            tasks: m.tasks.map(t => t.id === suppTask.id ? { ...t, status: 'failed' as const } : t),
          } : m),
        }
        s = logEvent(s, {
          type: 'task_failed',
          missionId: mission.id,
          taskId: suppTask.id,
          reason: 'tactical_lockout',
        })
      }

      // 4. Update asset availability and positions
      const updatedAssets = s.assets.map(asset => {
        // Replacement drone arrives at hub
        if (asset.status === 'failed' && asset.replacementAt !== null && elapsed >= asset.replacementAt) {
          return {
            ...asset,
            status: 'available' as const,
            failedAt: null,
            replacementAt: null,
            currentMissionId: null,
            currentTaskId: null,
            position: { ...HUB },
            travelFrom: { ...HUB },
            targetPosition: { ...HUB },
            availableAt: elapsed,
          }
        }
        // Don't move failed assets (with no pending replacement)
        if (asset.status === 'failed') return asset

        const newPos = interpolateAssetPosition(asset, elapsed)
        let newStatus = asset.status

        if (asset.status === 'returning' && elapsed >= asset.availableAt) {
          newStatus = 'available'
        }

        // When task completes: redirect to next sequential task, or return to hub
        if (asset.status === 'deployed' && asset.currentTaskId) {
          const currentMission = s.missions.find(m => m.id === asset.currentMissionId)
          const task = currentMission?.tasks.find(t => t.id === asset.currentTaskId)

          const recallReady = task?.status === 'completed' &&
            elapsed >= (task.completionTime ?? 0) + task.recallDelay

          if (recallReady) {
            // Find next task using per-drone sequence (respects user's chain order)
            const seq = currentMission?.droneSequences?.[asset.id] ?? []
            const curIdx = seq.indexOf(asset.currentTaskId!)
            const nextTaskId = curIdx >= 0
              ? seq.slice(curIdx + 1).find(tid => {
                  const t = currentMission?.tasks.find(t => t.id === tid)
                  return t && t.status !== 'completed' && t.status !== 'failed'
                })
              : undefined
            // Fallback: any assigned incomplete task
            // Used when no explicit sequence exists, OR in greedy mode (sequences trimmed to 1 task)
            const nextTask = nextTaskId
              ? currentMission?.tasks.find(t => t.id === nextTaskId)
              : (seq.length === 0 || currentMission?.needsGreedyReplan)
                ? currentMission?.tasks.find(t =>
                    t.id !== asset.currentTaskId &&
                    t.assignedAssetIds.includes(asset.id) &&
                    t.status !== 'completed' &&
                    t.status !== 'failed',
                  )
                : undefined

            if (nextTask) {
              // Sequential reuse: redirect directly to the next task's waypoint
              const tt = travelTime(task!.waypoint, nextTask.waypoint, ASSET_SPEED[asset.type])
              return {
                ...asset,
                currentTaskId: nextTask.id,
                travelFrom: { ...task!.waypoint },
                targetPosition: { ...nextTask.waypoint },
                travelStartElapsed: elapsed,
                travelEndElapsed: elapsed + tt,
                position: newPos,
              }
            }

            // No next task — return to hub
            const returnTime = travelTime(task!.waypoint, HUB, ASSET_SPEED[asset.type])
            return {
              ...asset,
              status: 'returning' as const,
              currentMissionId: null,
              currentTaskId: null,
              travelFrom: { ...task!.waypoint },
              targetPosition: { ...HUB },
              travelStartElapsed: elapsed,
              travelEndElapsed: elapsed + returnTime,
              availableAt: elapsed + returnTime,
              position: newPos,
            }
          }
        }

        return { ...asset, status: newStatus, position: newPos }
      })

      s = { ...s, assets: updatedAssets }

      // 5. Recalculate score (snapshot — penalty grows continuously)
      const { score: newScore, penaltyAccrued: newPenalty } = computeScore(s.missions, elapsed)
      s = { ...s, score: newScore, penaltyAccrued: newPenalty }

      // 6. Trust probe
      if (!s.trustProbeActive && elapsed >= s.nextTrustProbeAt) {
        s = { ...s, trustProbeActive: true }
      }

      // 7. Category forecast update (after spawning new missions)
      if (toSpawn.length > 0) {
        s = { ...s, categoryForecast: computeForecast(s.pendingBlueprints) }
      }

      // 8. Session end check (suppressed in testing mode)
      if (!state.config.testingMode && elapsed >= state.sessionDuration) {
        s = endSession(s)
      }

      return s
    }

    // ── OPEN_STRATEGIC ───────────────────────────────────────────────────
    case 'OPEN_STRATEGIC': {
      const mission = state.missions.find(m => m.id === action.missionId)
      if (!mission || mission.status !== 'queued') return state
      // Exclude drones already locked into other pending tactical plans
      const effectiveAvail = availableExcludingPending(state.assets, state.missions, action.missionId)
      const reserve = {
        Blue:  effectiveAvail.filter(a => a.type === 'Blue').length,
        Red:   effectiveAvail.filter(a => a.type === 'Red').length,
        Green: effectiveAvail.filter(a => a.type === 'Green').length,
      }
      const agentRng = new SeededRNG(state.config.seed ^ hashId(mission.id))
      const strategies = state.config.mode === 'agent'
        ? generateStrategies(mission.tasks, reserve, state.config.agentErrorRate, agentRng)
        : []
      let s: GameState = {
        ...state,
        strategicModal: {
          missionId: action.missionId,
          strategies,
          selectedStrategyIndex: null,
          manualAllocation: { Blue: 0, Red: 0, Green: 0 },
        },
      }
      s = logEvent(s, {
        type: 'strategic_modal_opened',
        missionId: mission.id,
        missionCategory: mission.category,
        timeRemainingInSession: Math.max(0, state.sessionDuration - state.elapsed),
        strategiesPresented: strategies.map(st => ({
          name: st.name,
          description: st.description,
          displayedAssets: st.assets,
          trueAssets: st.trueAssets,
          displayedCompletionTime: st.expectedCompletionTime,
          reserveAfter: st.reserveAfter,
          speedScore: st.speedScore,
          reserveScore: st.reserveScore,
          isBadSuggestion: st.isBadSuggestion,
          badSuggestionType: st.badSuggestionType,
        })),
      })
      return s
    }

    // ── CLOSE_STRATEGIC ──────────────────────────────────────────────────
    case 'CLOSE_STRATEGIC': {
      return { ...state, strategicModal: null }
    }

    // ── PICK_STRATEGY ────────────────────────────────────────────────────
    case 'PICK_STRATEGY': {
      if (!state.strategicModal) return state
      return {
        ...state,
        strategicModal: { ...state.strategicModal, selectedStrategyIndex: action.strategyIndex },
      }
    }

    // ── EDIT_MANUAL ──────────────────────────────────────────────────────
    case 'EDIT_MANUAL': {
      if (!state.strategicModal) return state
      return {
        ...state,
        strategicModal: { ...state.strategicModal, manualAllocation: action.allocation },
      }
    }

    // ── APPLY_STRATEGIC ──────────────────────────────────────────────────
    case 'APPLY_STRATEGIC': {
      const mission = state.missions.find(m => m.id === action.missionId)
      if (!mission || mission.status !== 'queued') return state

      const modal = state.strategicModal
      if (!modal) return state

      // Determine the allocation and task comps to use
      let composition: AssetRequirement
      let strategyName: 'Aggressive' | 'Conservative' | 'Manual'
      let taskComps: Record<string, TaskComp> | undefined
      let isBad = false
      let badType: 'over' | 'under' | null = null

      if (action.source === 'agent' && action.strategyIndex !== null) {
        const strat = modal.strategies[action.strategyIndex]
        if (!strat) return state
        composition = strat.trueAssets      // use TRUE assets for actual deployment
        taskComps = strat.trueTaskComps
        strategyName = strat.name
        isBad = strat.isBadSuggestion
        badType = strat.badSuggestionType
      } else {
        composition = action.manualAllocation ?? { Blue: 0, Red: 0, Green: 0 }
        strategyName = 'Manual'
        taskComps = undefined  // let greedyAssign pick compositions automatically
      }

      const now = state.elapsed
      // Exclude drones already reserved in other pending tactical plans to prevent double-allocation
      const available = availableExcludingPending(state.assets, state.missions, mission.id)
      const taskOrder = [...mission.tasks].sort((a, b) => b.type - a.type).map(t => t.id)

      let dronePool: string[]
      let taskAssignmentMap: Record<string, string[]>
      let expectedCompletionTime = 0

      if (action.source === 'agent') {
        // Agent mode: run greedyAssign to produce suggested drone→task assignments.
        // Bad 'under' suggestions may yield partial assignments (some tasks skipped) — allow this.
        const assignments = greedyAssign(mission.tasks, available, composition, now, taskComps, taskOrder)
        // Only bail if the pool itself is empty (nothing to deploy at all)
        const poolEmpty = composition.Blue === 0 && composition.Red === 0 && composition.Green === 0
        if (poolEmpty) return state
        dronePool = [...new Set(assignments.flatMap(a => a.assetIds))]
        if (dronePool.length === 0) {
          // Under-allocation so severe nothing was assignable — still form pool from available assets
          const avB = available.filter(a => a.type === 'Blue').slice(0, composition.Blue)
          const avR = available.filter(a => a.type === 'Red').slice(0, composition.Red)
          const avG = available.filter(a => a.type === 'Green').slice(0, composition.Green)
          dronePool = [...avB, ...avR, ...avG].map(a => a.id)
          if (dronePool.length === 0) return state
        }
        taskAssignmentMap = Object.fromEntries(assignments.map(a => [a.taskId, a.assetIds]))
        expectedCompletionTime = assignments.length > 0
          ? Math.max(...assignments.map(a => a.startTime + a.baseTime))
          : 0
      } else {
        // Manual mode: reserve matching drones
        const avB = available.filter(a => a.type === 'Blue')
        const avR = available.filter(a => a.type === 'Red')
        const avG = available.filter(a => a.type === 'Green')
        if (avB.length < composition.Blue || avR.length < composition.Red || avG.length < composition.Green) return state
        dronePool = [
          ...avB.slice(0, composition.Blue).map(a => a.id),
          ...avR.slice(0, composition.Red).map(a => a.id),
          ...avG.slice(0, composition.Green).map(a => a.id),
        ]
        if (state.config.mode === 'agent') {
          // In agent mode, generate tactical suggestions even for a manually-set composition
          const agentAssignments = greedyAssign(mission.tasks, available, composition, now, undefined, taskOrder)
          taskAssignmentMap = Object.fromEntries(agentAssignments.map(a => [a.taskId, a.assetIds]))
          if (agentAssignments.length > 0) {
            expectedCompletionTime = Math.max(...agentAssignments.map(a => a.startTime + a.baseTime))
          }
        } else {
          taskAssignmentMap = {}  // no-agent mode: operator assigns drones to tasks manually
        }
      }

      // ── Tactical error injection (agent mode only) ─────────────────────────
      // With probability epsilonTactical, remove one task from the tactical plan.
      // The suppressed task will appear allocated in the UI (deception) but has no drone.
      let hasTacticalError = false
      let suppressedTaskId: string | null = null
      if (action.source === 'agent' && state.config.epsilonTactical > 0) {
        const tacRng = new SeededRNG(state.config.seed ^ (mission.id.charCodeAt(2) ?? 0) ^ 0x7ac1)
        if (tacRng.randFloat(0, 1) < state.config.epsilonTactical) {
          // Only suppress a task that actually has drones assigned to it
          const suppressable = taskOrder.filter(tid => (taskAssignmentMap[tid] ?? []).length > 0)
          if (suppressable.length > 0) {
            suppressedTaskId = suppressable[tacRng.randInt(0, suppressable.length - 1)]
            taskAssignmentMap = { ...taskAssignmentMap }
            delete taskAssignmentMap[suppressedTaskId]
            hasTacticalError = true
          }
        }
      }

      const pendingAllocation: PendingAllocation = {
        strategyName,
        composition,
        dronePool,
        taskAssignments: taskAssignmentMap,
        taskOrder,
        expectedCompletionTime,
        isAgentSuggested: action.source === 'agent',
        isBadSuggestion: isBad,
        badSuggestionType: badType,
        hasTacticalError,
        suppressedTaskId,
      }

      let s = logEvent(state, {
        type: 'strategic_choice',
        missionId: mission.id,
        missionCategory: mission.category,
        choiceType: strategyName === 'Aggressive' ? 'aggressive' : strategyName === 'Conservative' ? 'conservative' : 'manual',
        wasAgentSuggestion: action.source === 'agent',
        agentSuggestionWasBad: isBad,
        badSuggestionType: badType,
        assetsChosen: composition,
        timeRemainingInSession: Math.max(0, state.sessionDuration - now),
      })

      // Both modes: set tacticalPending for tactical assignment step
      s = {
        ...s,
        missions: s.missions.map(m => m.id === mission.id ? {
          ...m,
          tacticalPending: true,
          pendingAllocation,
          agentInteraction: action.source === 'agent' ? 'shown' : 'manual',
          chosenStrategyName: strategyName,
        } : m),
        strategicModal: null,
      }
      return s
    }

    // ── CONFIRM_TACTICAL ─────────────────────────────────────────────────
    case 'CONFIRM_TACTICAL': {
      const mission = state.missions.find(m => m.id === action.missionId)
      if (!mission || !mission.tacticalPending || !mission.pendingAllocation) return state

      const pending = mission.pendingAllocation
      const rawDroneSeqs = action.droneSequences ?? {}
      // In greedy mode, trim each drone's sequence to its first task only
      const isGreedy = state.config.tacticalMode === 'greedy'
      const droneSeqs = isGreedy
        ? Object.fromEntries(Object.entries(rawDroneSeqs).map(([id, seq]) => [id, seq.slice(0, 1)]))
        : rawDroneSeqs
      let assignments: TaskAssignment[]

      const userProvidedAssignments = !!action.taskAssignments
      if (userProvidedAssignments) {
        assignments = buildManualAssignments(mission, state.assets, action.taskAssignments!, droneSeqs, state.elapsed)
      } else {
        const available = state.assets.filter(a => a.status === 'available')
        assignments = greedyAssign(mission.tasks, available, pending.composition, state.elapsed, undefined, pending.taskOrder)
      }

      if (assignments.length === 0) return state

      // modifiedFromAgentPlan: true if the user's assignments differ from the greedy suggestion stored in pending
      const taskAssignmentsEqual = (a: Record<string, string[]>, b: Record<string, string[]>) => {
        const keysA = Object.keys(a).sort(), keysB = Object.keys(b).sort()
        if (keysA.join() !== keysB.join()) return false
        return keysA.every(k => [...(a[k] ?? [])].sort().join() === [...(b[k] ?? [])].sort().join())
      }
      const modifiedFromAgentPlan = userProvidedAssignments &&
        !taskAssignmentsEqual(action.taskAssignments!, pending.taskAssignments)

      // Per-task diff: which task IDs had drone assignments changed from the greedy suggestion
      const changedTaskIds = userProvidedAssignments
        ? Object.keys(action.taskAssignments!).filter(tid => {
            const before = [...(pending.taskAssignments[tid] ?? [])].sort().join()
            const after  = [...(action.taskAssignments![tid]  ?? [])].sort().join()
            return before !== after
          })
        : []

      // chainingUsed: true if any drone appears in more than one task's assignment list
      const chainingUsed = userProvidedAssignments
        ? (() => {
            const allIds = Object.values(action.taskAssignments!).flat()
            return allIds.some((id, _, arr) => arr.filter(x => x === id).length > 1)
          })()
        : false
      let s = applyTacticalAllocation(state, action.missionId, assignments, pending, pending.taskOrder, modifiedFromAgentPlan, droneSeqs, chainingUsed, changedTaskIds)
      // Persist the suppressed task ID onto the mission so TICK can detect the lockout
      if (pending.hasTacticalError && pending.suppressedTaskId) {
        s = { ...s, missions: s.missions.map(m => m.id === action.missionId
          ? { ...m, tacticallySuppressedTaskId: pending.suppressedTaskId }
          : m) }
      }
      // In greedy mode, mark mission for auto-replan after each task completion
      if (isGreedy) {
        s = { ...s, missions: s.missions.map(m => m.id === action.missionId
          ? { ...m, needsGreedyReplan: true }
          : m) }
      }
      return s
    }

    // ── OVERRIDE_TACTICAL ────────────────────────────────────────────────
    case 'OVERRIDE_TACTICAL': {
      const mission = state.missions.find(m => m.id === action.missionId)
      if (!mission || !mission.tacticalPending) return state
      // Clear pending state and open the strategic modal again for re-allocation.
      // When computing reserve, exclude drones in OTHER missions' pending pools
      // (this mission's own pool is being released, so include those drones back).
      const missionsWithoutThis = state.missions.map(m =>
        m.id === action.missionId ? { ...m, tacticalPending: false, pendingAllocation: null } : m
      )
      const ovEffAvail = availableExcludingPending(state.assets, missionsWithoutThis, action.missionId)
      const reserve = {
        Blue:  ovEffAvail.filter(a => a.type === 'Blue').length,
        Red:   ovEffAvail.filter(a => a.type === 'Red').length,
        Green: ovEffAvail.filter(a => a.type === 'Green').length,
      }
      const agentRng = new SeededRNG(state.config.seed ^ hashId(mission.id))
      const strategies = state.config.mode === 'agent'
        ? generateStrategies(mission.tasks, reserve, state.config.agentErrorRate, agentRng)
        : []
      return {
        ...state,
        missions: state.missions.map(m => m.id === action.missionId ? { ...m, tacticalPending: false, pendingAllocation: null } : m),
        strategicModal: { missionId: action.missionId, strategies, selectedStrategyIndex: null, manualAllocation: null },
      }
    }

    // ── ACCEPT_RECOVERY ──────────────────────────────────────────────────
    case 'ACCEPT_RECOVERY': {
      const mission = state.missions.find(m => m.id === action.missionId)
      if (!mission || !mission.failureRecoveryPending || !mission.pendingRecoveryOptions) return state
      const opt = mission.pendingRecoveryOptions.find(o => o.type === action.recoveryType)
      if (!opt || !opt.feasible) return state

      let s = logEvent(state, {
        type: 'failure_recovery',
        missionId: mission.id,
        missionCategory: mission.category,
        recoveryType: action.recoveryType,
        wasAgentSuggested: true,
        timeRemainingInSession: Math.max(0, state.sessionDuration - state.elapsed),
      })

      if (action.recoveryType === 'redistribute' && opt.redistributeToAssetId) {
        // Redirect an existing drone to the failed task
        const task = mission.tasks.find(t => t.id === opt.taskId)
        const asset = s.assets.find(a => a.id === opt.redistributeToAssetId)
        if (!task || !asset) return state
        const currentPos = interpolateAssetPosition(asset, s.elapsed)
        const tt = travelTime(currentPos, task.waypoint, ASSET_SPEED[asset.type])
        const startTime = s.elapsed + tt
        const completionTime = startTime + task.baseTime
        s = {
          ...s,
          assets: s.assets.map(a => a.id === opt.redistributeToAssetId ? {
            ...a,
            currentTaskId: task.id,
            travelFrom: currentPos,
            targetPosition: { ...task.waypoint },
            travelStartElapsed: s.elapsed,
            travelEndElapsed: s.elapsed + tt,
            availableAt: completionTime + travelTime(task.waypoint, HUB, ASSET_SPEED[a.type]),
          } : a),
          missions: s.missions.map(m => m.id === mission.id ? {
            ...m,
            failureRecoveryPending: false,
            pendingRecoveryOptions: null,
            tasks: m.tasks.map(t => t.id === task.id ? {
              ...t,
              status: 'traveling' as const,
              assignedAssetIds: [...t.assignedAssetIds, opt.redistributeToAssetId!],
              allocatedAt: s.elapsed,
              travelTime: tt,
              startTime,
              completionTime,
            } : t),
          } : m),
        }
      }

      return s
    }

    // ── APPLY_MANUAL_RECOVERY ────────────────────────────────────────────
    case 'APPLY_MANUAL_RECOVERY': {
      const mission = state.missions.find(m => m.id === action.missionId)
      const task = mission?.tasks.find(t => t.id === action.taskId)
      const asset = state.assets.find(a => a.id === action.newAssetId)
      if (!mission || !task || !asset || asset.status !== 'available') return state
      const tt = travelTime(HUB, task.waypoint, ASSET_SPEED[asset.type])
      const startTime = state.elapsed + tt
      const completionTime = startTime + task.baseTime
      let s = logEvent(state, {
        type: 'failure_recovery',
        missionId: mission.id,
        missionCategory: mission.category,
        recoveryType: 'manual',
        wasAgentSuggested: false,
        timeRemainingInSession: Math.max(0, state.sessionDuration - state.elapsed),
      })
      s = {
        ...s,
        assets: s.assets.map(a => a.id === action.newAssetId ? {
          ...a, status: 'deployed' as const,
          currentMissionId: mission.id, currentTaskId: task.id,
          travelFrom: { ...HUB }, targetPosition: { ...task.waypoint },
          travelStartElapsed: s.elapsed, travelEndElapsed: s.elapsed + tt,
          availableAt: completionTime + travelTime(task.waypoint, HUB, ASSET_SPEED[a.type]),
        } : a),
        missions: s.missions.map(m => m.id === mission.id ? {
          ...m,
          failureRecoveryPending: false,
          pendingRecoveryOptions: null,
          tasks: m.tasks.map(t => t.id === task.id ? {
            ...t, status: 'traveling' as const,
            assignedAssetIds: [...t.assignedAssetIds, action.newAssetId],
            allocatedAt: s.elapsed, travelTime: tt, startTime, completionTime,
          } : t),
        } : m),
      }
      return s
    }

    // ── CONFIRM_FAILURE_RECOVERY ─────────────────────────────────────────
    case 'CONFIRM_FAILURE_RECOVERY': {
      const mission = state.missions.find(m => m.id === action.missionId)
      if (!mission || !mission.failureRecoveryPending) return state
      const now = state.elapsed

      let newAssets = [...state.assets]
      const newTasks = mission.tasks.map(task => {
        if (task.status !== 'pending') return task
        const assignedIds = action.taskAssignments[task.id] ?? []
        if (assignedIds.length === 0) return task

        const travelTimes = assignedIds.map(id => {
          const asset = newAssets.find(a => a.id === id)
          if (!asset || asset.status !== 'available') return 0
          return Math.hypot(task.waypoint.x - HUB.x, task.waypoint.y - HUB.y) / ASSET_SPEED[asset.type]
        })
        const startTime = now + Math.max(0, ...travelTimes)
        const completionTime = startTime + task.baseTime

        for (const droneId of assignedIds) {
          const assetIdx = newAssets.findIndex(a => a.id === droneId)
          if (assetIdx < 0) continue
          const asset = newAssets[assetIdx]
          if (asset.status !== 'available') continue
          const tt = Math.hypot(task.waypoint.x - HUB.x, task.waypoint.y - HUB.y) / ASSET_SPEED[asset.type]
          newAssets[assetIdx] = {
            ...asset,
            status: 'deployed' as const,
            currentMissionId: mission.id,
            currentTaskId: task.id,
            travelFrom: { ...HUB },
            targetPosition: { ...task.waypoint },
            travelStartElapsed: now,
            travelEndElapsed: now + tt,
            availableAt: completionTime + Math.hypot(task.waypoint.x - HUB.x, task.waypoint.y - HUB.y) / ASSET_SPEED[asset.type],
          }
        }

        const newAssignedIds = [
          ...task.assignedAssetIds.filter(id => !assignedIds.includes(id)),
          ...assignedIds.filter(id => {
            const asset = newAssets.find(a => a.id === id)
            return asset?.status === 'deployed' && asset.currentTaskId === task.id
          }),
        ]
        return {
          ...task,
          assignedAssetIds: newAssignedIds,
          startTime,
          completionTime,
          status: 'traveling' as const,
        }
      })

      return {
        ...state,
        assets: newAssets,
        missions: state.missions.map(m => m.id === action.missionId ? {
          ...m,
          tasks: newTasks,
          failureRecoveryPending: false,
          pendingRecoveryOptions: null,
        } : m),
      }
    }

    // ── ABANDON_MISSION ──────────────────────────────────────────────────
    case 'ABANDON_MISSION': {
      const mission = state.missions.find(m => m.id === action.missionId)
      if (!mission || mission.status !== 'active') return state
      const elapsed = state.elapsed

      // Return all deployed drones from this mission to hub
      const updatedAssets = state.assets.map(asset => {
        if (asset.currentMissionId !== mission.id) return asset
        const returnTime = travelTime(asset.position, HUB, ASSET_SPEED[asset.type])
        return {
          ...asset,
          status: 'returning' as const,
          currentMissionId: null as string | null,
          currentTaskId: null as string | null,
          travelFrom: { ...asset.position },
          targetPosition: { ...HUB },
          travelStartElapsed: elapsed,
          travelEndElapsed: elapsed + returnTime,
          availableAt: elapsed + returnTime,
        }
      })

      // Collect incomplete tasks for residual mission
      const incompleteTasks = mission.tasks.filter(
        t => t.status === 'pending' || t.status === 'traveling' || t.status === 'executing'
      )

      // Build residual mission if there is anything left to do
      let residualMission: Mission | null = null
      if (incompleteTasks.length > 0) {
        const residualTasks: Task[] = incompleteTasks.map((t, i) => {
          const execSoFar = t.status === 'executing' && t.startTime !== null
            ? Math.max(0, elapsed - t.startTime)
            : 0
          const remainingBase = Math.max(5, t.baseTime - execSoFar)
          return {
            ...t,
            id: `${mission.id}-R-T${i + 1}`,
            missionId: `${mission.id}-R`,
            status: 'pending' as const,
            assignedAssetIds: [],
            allocatedAt: null,
            travelTime: 0,
            baseTime: remainingBase,
            startTime: null,
            completionTime: null,
            useSubstitute: false,
            recallDelay: 0,
          }
        })

        // Schedule failures proportional to task count (~1 per 5 tasks)
        const failureCount = Math.round(residualTasks.length / 5)
        const residualRng = new SeededRNG(state.config.seed ^ mission.id.charCodeAt(0) ^ 0xABBA)
        const residualFailureTimes: number[] = []
        for (let f = 0; f < failureCount; f++) {
          residualFailureTimes.push(30 + f * 60 + residualRng.randFloat(0, 30))
        }

        residualMission = {
          ...mission,
          id: `${mission.id}-R`,
          status: 'queued' as const,
          tasks: residualTasks,
          allocationTime: null,
          completionTime: null,
          arrivalTime: elapsed,
          agentInteraction: 'none',
          chosenStrategyName: null,
          manualPriorityIds: [],
          tacticalPending: false,
          pendingAllocation: null,
          droneSequences: {},
          droneFailureTimes: residualFailureTimes,
          droneFailuresFired: 0,
          failedDroneId: null,
          failureRecoveryPending: false,
          pendingRecoveryOptions: null,
          tacticallySuppressedTaskId: null,
          abandonedAt: null,
          isResidual: true,
          needsGreedyReplan: false,
        }
      }

      let s: GameState = state

      // Log task_failed for every task that won't carry over to the residual
      for (const t of incompleteTasks) {
        s = logEvent(s, {
          type: 'task_failed',
          missionId: mission.id,
          taskId: t.id,
          reason: 'mission_abandoned',
        })
      }

      s = logEvent(s, {
        type: 'mission_abandoned' as const,
        missionId: mission.id,
        missionCategory: mission.category,
        completedTaskCount: mission.tasks.filter(t => t.status === 'completed').length,
        remainingTaskCount: incompleteTasks.length,
      })

      const updatedMissions = s.missions.map(m =>
        m.id === mission.id
          ? { ...m, status: 'abandoned' as const, abandonedAt: elapsed, failureRecoveryPending: false, pendingRecoveryOptions: null }
          : m
      )

      return {
        ...s,
        assets: updatedAssets,
        missions: residualMission ? [...updatedMissions, residualMission] : updatedMissions,
      }
    }

    // ── RECALL_ASSET ─────────────────────────────────────────────────────
    case 'RECALL_ASSET': {
      const asset = state.assets.find(a => a.id === action.assetId)
      if (!asset || asset.status === 'available' || asset.status === 'returning' || asset.status === 'failed') return state

      const taskId = asset.currentTaskId!
      const missionId = asset.currentMissionId!
      const elapsed = state.elapsed
      const returnTime = travelTime(asset.position, HUB, ASSET_SPEED[asset.type])

      const currentTask = state.missions
        .find(m => m.id === missionId)
        ?.tasks.find(t => t.id === taskId)
      const taskAlreadyDone = currentTask?.status === 'completed' || currentTask?.status === 'failed'

      let s = logEvent(state, { type: 'asset_recalled', assetId: asset.id, missionId, taskId })

      const updatedAssets = s.assets.map(a => {
        if (a.id !== asset.id) return a
        return {
          ...a,
          status: 'returning' as const,
          currentMissionId: null,
          currentTaskId: null,
          travelFrom: { ...a.position },
          targetPosition: { ...HUB },
          travelStartElapsed: elapsed,
          travelEndElapsed: elapsed + returnTime,
          availableAt: elapsed + returnTime,
        }
      })

      if (taskAlreadyDone) {
        return { ...s, assets: updatedAssets }
      }

      s = logEvent(s, { type: 'task_failed', missionId, taskId, reason: 'asset_recalled' })

      const updatedMissions = s.missions.map(m => {
        if (m.id !== missionId) return m
        return {
          ...m,
          tasks: m.tasks.map(t => t.id === taskId ? { ...t, status: 'failed' as const } : t),
        }
      })

      return { ...s, assets: updatedAssets, missions: updatedMissions }
    }

    // ── REPRIORITISE_TASK ────────────────────────────────────────────────
    case 'REPRIORITISE_TASK': {
      const mission = state.missions.find(m => m.id === action.missionId)
      if (!mission) return state

      if (action.direction === 'top') {
        const current = mission.manualPriorityIds
        const alreadyIn = current.includes(action.taskId)
        const newPriorityIds = alreadyIn
          ? current.filter(id => id !== action.taskId)
          : [action.taskId, ...current]

        const allMovable = mission.tasks.filter(t => t.status === 'pending' || t.status === 'traveling')
        const validPriorityIds = newPriorityIds.filter(id => allMovable.some(t => t.id === id))
        const priorityTaskList = validPriorityIds.map(id => allMovable.find(t => t.id === id)!)
        const restMovable = allMovable
          .filter(t => !validPriorityIds.includes(t.id))
          .sort((a, b) => b.type - a.type)
        const fixed = mission.tasks.filter(t => t.status !== 'pending' && t.status !== 'traveling')

        let taskOverrides = new Map<string, Partial<Task>>()
        let updatedAssets = state.assets

        if (!alreadyIn) {
          const pTask = allMovable.find(t => t.id === action.taskId)
          if (pTask) {
            let newStartTime = 0

            updatedAssets = state.assets.map(asset => {
              if (!pTask.assignedAssetIds.includes(asset.id)) return asset
              if (asset.status !== 'deployed') return asset
              if (asset.currentMissionId !== mission.id) return asset

              if (asset.currentTaskId === pTask.id) {
                newStartTime = Math.max(newStartTime, asset.travelEndElapsed)
                return asset
              }

              if (state.elapsed >= asset.travelEndElapsed) return asset

              const currentPos = interpolateAssetPosition(asset, state.elapsed)
              const tt = travelTime(currentPos, pTask.waypoint, ASSET_SPEED[asset.type])
              const arrival = state.elapsed + tt
              newStartTime = Math.max(newStartTime, arrival)
              return {
                ...asset,
                currentTaskId: pTask.id,
                travelFrom: currentPos,
                targetPosition: { ...pTask.waypoint },
                travelStartElapsed: state.elapsed,
                travelEndElapsed: arrival,
                position: currentPos,
              }
            })

            taskOverrides.set(pTask.id, {
              startTime: newStartTime,
              completionTime: newStartTime + pTask.baseTime,
            })
          }
        }

        const applyOverride = (t: Task) => {
          const ov = taskOverrides.get(t.id)
          return ov ? { ...t, ...ov } : t
        }

        const updatedMission = {
          ...mission,
          tasks: [...fixed, ...priorityTaskList, ...restMovable].map(applyOverride),
          manualPriorityIds: validPriorityIds,
        }
        let s = logEvent(state, {
          type: 'task_reprioritised',
          missionId: action.missionId,
          taskId: action.taskId,
          newPosition: alreadyIn ? -1 : 0,
        })
        return {
          ...s,
          missions: s.missions.map(m => m.id === action.missionId ? updatedMission : m),
          assets: updatedAssets,
        }
      }

      // 'up'/'down': reorder pending tasks only
      const pending = mission.tasks.filter(t => t.status === 'pending')
      const idx = pending.findIndex(t => t.id === action.taskId)
      if (idx < 0) return state
      const newIdx = action.direction === 'up' ? Math.max(0, idx - 1) : Math.min(pending.length - 1, idx + 1)
      const reordered = [...pending]
      ;[reordered[idx], reordered[newIdx]] = [reordered[newIdx], reordered[idx]]
      const nonPending = mission.tasks.filter(t => t.status !== 'pending')
      const updatedMission2 = { ...mission, tasks: [...nonPending, ...reordered] }
      let s = logEvent(state, {
        type: 'task_reprioritised',
        missionId: action.missionId,
        taskId: action.taskId,
        newPosition: newIdx,
      })
      return { ...s, missions: s.missions.map(m => m.id === action.missionId ? updatedMission2 : m) }
    }

    // ── SUBMIT_TRUST_PROBE ───────────────────────────────────────────────
    case 'SUBMIT_TRUST_PROBE': {
      let s = logEvent(state, { type: 'trust_probe', trust: action.trust, workload: action.workload })
      s = { ...s, trustProbeActive: false, nextTrustProbeAt: state.elapsed + TRUST_PROBE_INTERVAL }
      return s
    }

    case 'DISMISS_TRUST_PROBE': {
      let s = logEvent(state, { type: 'trust_probe_dismissed' })
      return { ...s, trustProbeActive: false, nextTrustProbeAt: state.elapsed + TRUST_PROBE_INTERVAL }
    }

    // ── SUBMIT_SURVEY ────────────────────────────────────────────────────
    case 'SUBMIT_SURVEY': {
      return logEvent(state, {
        type: 'survey_response',
        surveyName: action.surveyName,
        responses: action.responses,
      })
    }

    // ── FINISH_SURVEYS ────────────────────────────────────────────────────
    case 'FINISH_SURVEYS': {
      if (state.sessionNumber < state.config.numSessions) return { ...state, phase: 'between' }
      return { ...state, phase: 'done' }
    }

    // ── NEXT_SESSION ─────────────────────────────────────────────────────
    case 'NEXT_SESSION': {
      if (state.phase !== 'between') return state
      const nextSession = state.sessionNumber + 1
      const blueprints = generateSessionPlan(new SeededRNG(state.config.seed ^ nextSession), state.config.complexity)

      return {
        ...state,
        phase: 'playing',
        sessionNumber: nextSession,
        elapsed: 0,
        sessionStartMs: null,
        assets: createInitialAssets(state.config.complexity),
        missions: [],
        pendingBlueprints: blueprints,
        score: 0,
        penaltyAccrued: 0,
        strategicModal: null,
        trustProbeActive: false,
        nextTrustProbeAt: TRUST_PROBE_INTERVAL,
      }
    }

    // ── END_STUDY ────────────────────────────────────────────────────────
    case 'END_STUDY': {
      return { ...state, phase: 'done' }
    }

    // ── FORCE_MISSION_ARRIVAL (testing mode) ─────────────────────────────
    case 'FORCE_MISSION_ARRIVAL': {
      if (!state.config.testingMode) return state
      const bp = state.pendingBlueprints[0]
      if (!bp) return state
      const mission = spawnMission({ ...bp, arrivalTime: state.elapsed })
      let s: GameState = {
        ...state,
        pendingBlueprints: state.pendingBlueprints.slice(1),
        missions: [...state.missions, mission],
      }
      s = logEvent(s, {
        type: 'mission_arrived',
        missionId: mission.id,
        category: mission.category,
        tasks: mission.tasks.map(t => ({ id: t.id, type: t.type })),
        zoneCenter: mission.zoneCenter,
        arrivalTime: mission.arrivalTime,
        timeRemainingInSession: Math.max(0, state.sessionDuration - state.elapsed),
      })
      return s
    }

    // ── TUTORIAL_OVERRIDE_TEAM ───────────────────────────────────────────
    // Replaces Mission 1's pending drone pool with 2 Blue + 1 Red + 1 Green
    // so the chaining exercise in the tutorial is always exercisable.
    case 'TUTORIAL_OVERRIDE_TEAM': {
      const mission = state.missions.find(m => m.tacticalPending && m.pendingAllocation)
      if (!mission || !mission.pendingAllocation) return state
      const pending = mission.pendingAllocation
      const allAvailable = availableExcludingPending(state.assets, state.missions, mission.id)
      const want = { Blue: 2, Red: 1, Green: 1 }
      const blues  = allAvailable.filter(a => a.type === 'Blue').slice(0, want.Blue)
      const reds   = allAvailable.filter(a => a.type === 'Red').slice(0, want.Red)
      const greens = allAvailable.filter(a => a.type === 'Green').slice(0, want.Green)
      const newPool = [...blues, ...reds, ...greens].map(a => a.id)
      if (newPool.length === 0) return state
      const newComposition: AssetRequirement = { Blue: blues.length, Red: reds.length, Green: greens.length }
      const now = state.elapsed
      const taskOrder = [...mission.tasks].sort((a, b) => b.type - a.type).map(t => t.id)
      const allAssets = state.assets
      const poolAssets = allAssets.filter(a => newPool.includes(a.id))
      const assignments = greedyAssign(mission.tasks, poolAssets, newComposition, now, undefined, taskOrder)
      const taskAssignmentMap = Object.fromEntries(assignments.map(a => [a.taskId, a.assetIds]))
      const expectedCompletionTime = assignments.length > 0
        ? Math.max(...assignments.map(a => a.startTime + a.baseTime))
        : pending.expectedCompletionTime
      return {
        ...state,
        missions: state.missions.map(m => m.id === mission.id ? {
          ...m,
          pendingAllocation: {
            ...pending,
            composition: newComposition,
            dronePool: newPool,
            taskAssignments: taskAssignmentMap,
            taskOrder,
            expectedCompletionTime,
          },
        } : m),
      }
    }

    // ── TUTORIAL_FORCE_ABANDON_SCENARIO ─────────────────────────────────
    // Sets the first active mission into an unrecoverable failure state (no feasible
    // recovery options) so the tutorial's abort step can make the operator abandon it.
    case 'TUTORIAL_FORCE_ABANDON_SCENARIO': {
      const mission = state.missions.find(m => m.status === 'active' && !m.failureRecoveryPending)
      if (!mission) return state
      return {
        ...state,
        missions: state.missions.map(m => m.id === mission.id ? {
          ...m,
          failureRecoveryPending: true,
          failedDroneId: null,
          pendingRecoveryOptions: [],   // empty = no feasible recovery, operator must abandon
        } : m),
      }
    }

    // ── FORCE_DRONE_FAILURE (testing mode) ───────────────────────────────
    case 'FORCE_DRONE_FAILURE': {
      if (!state.config.testingMode) return state
      // Find first active mission without a pending failure (ignore scheduled-failure-count limit in testing mode)
      const mission = state.missions.find(
        m => m.status === 'active' && !m.failureRecoveryPending
      )
      if (!mission) return state
      const deployedDrones = state.assets.filter(
        a => a.currentMissionId === mission.id && a.status === 'deployed' && a.currentTaskId
      )
      const executingDrones = deployedDrones.filter(
        a => mission.tasks.find(t => t.id === a.currentTaskId)?.status === 'executing'
      )
      // Prefer an executing drone; fall back to any deployed drone with a task (may still be traveling)
      const candidateDrones = executingDrones.length > 0 ? executingDrones : deployedDrones
      if (candidateDrones.length === 0) return state
      const failedDrone = candidateDrones[0]
      const failedTask = mission.tasks.find(t => t.id === failedDrone.currentTaskId)!
      const updatedAssets = state.assets.map(a =>
        a.id === failedDrone.id ? { ...a, status: 'failed' as const, failedAt: state.elapsed, currentMissionId: null, currentTaskId: null } : a
      )
      const updatedMissions = state.missions.map(m => {
        if (m.id !== mission.id) return m
        return {
          ...m,
          droneFailuresFired: m.droneFailuresFired + 1,
          failedDroneId: failedDrone.id,
          failureRecoveryPending: true,
          tasks: m.tasks.map(t =>
            t.id === failedTask.id
              ? { ...t, status: 'pending' as const, assignedAssetIds: t.assignedAssetIds.filter(id => id !== failedDrone.id), startTime: null, completionTime: null }
              : t
          ),
          pendingRecoveryOptions: buildRecoveryOptions(m, failedTask, failedDrone.id, state.assets, state.elapsed),
        }
      })
      let s: GameState = { ...state, assets: updatedAssets, missions: updatedMissions }
      s = logEvent(s, {
        type: 'drone_failure',
        missionId: mission.id,
        missionCategory: mission.category,
        droneId: failedDrone.id,
        droneType: failedDrone.type,
        taskId: failedTask.id,
        taskType: failedTask.type,
        timeRemainingInSession: Math.max(0, state.sessionDuration - state.elapsed),
      })
      return s
    }

    // ── FORCE_SESSION_END (testing/tutorial mode) ────────────────────────
    case 'FORCE_SESSION_END': {
      if (!state.config.testingMode) return state
      return endSession(state)
    }

    default:
      return state
  }
}

// ─── End-session helper ───────────────────────────────────────────────────

function endSession(s: GameState): GameState {
  // Fail all incomplete tasks
  const failedMissions = s.missions.map(m => {
    if (m.status === 'completed') return m
    const tasks = m.tasks.map(t =>
      t.status === 'pending' || t.status === 'traveling' || t.status === 'executing'
        ? { ...t, status: 'failed' as const }
        : t,
    )
    return { ...m, tasks, status: (tasks.some(t => t.status === 'completed') ? 'completed' : 'failed') as Mission['status'] }
  })

  const idx = s.sessionNumber - 1
  const evs = s.events[idx]
  const { score, penaltyAccrued } = computeScore(failedMissions, s.elapsed)
  const completionPoints = computeCompletionPoints(failedMissions)
  const greenEff = computeGreenEfficiency(failedMissions)
  const meanTime = computeMeanMissionTime(failedMissions)

  const agentFollowRate = (() => {
    const choices = evs.filter(e => e.type === 'strategic_choice') as Array<{ wasAgentSuggestion: boolean }>
    const followed = choices.filter(e => e.wasAgentSuggestion).length
    return choices.length > 0 ? followed / choices.length : 0
  })()

  let s2 = logEvent({ ...s, missions: failedMissions, score, penaltyAccrued }, {
    type: 'session_ended',
    score,
    penaltyAccrued,
    completionPoints,
    greenEfficiency: greenEff,
    meanMissionTime: meanTime,
    agentFollowRate,
  })

  s2 = {
    ...s2,
    completedSessionScores: [...s2.completedSessionScores, score],
    phase: 'survey',
  }

  return s2
}

// ─── Forecast helper ──────────────────────────────────────────────────────

function computeForecast(
  pending: GameState['pendingBlueprints'],
): Record<MissionCategory, number> {
  if (pending.length === 0) {
    return { A: 0.2, B: 0.2, C: 0.2, D: 0.2, E: 0.2 }
  }
  const window = pending.slice(0, Math.min(5, pending.length))
  const counts: Record<MissionCategory, number> = { A: 0, B: 0, C: 0, D: 0, E: 0 }
  window.forEach(bp => counts[bp.category]++)
  const total = window.length
  return {
    A: counts.A / total,
    B: counts.B / total,
    C: counts.C / total,
    D: counts.D / total,
    E: counts.E / total,
  }
}

// Re-export for consumers
export type { GameState }
