import type {
  GameState, GameEvent, Asset, Mission, Task,
  AssetType, TaskType, AssetRequirement,
  MissionCategory, TaskComp, RecoveryOption,
  PendingAllocation, MissionBlueprint, Complexity,
} from '../types'
import type { GameAction } from './actions'
import {
  HUB, ASSET_SPEED, TASK_BASE_TIME, TASK_PRIMARY, TASK_SUBSTITUTE,
  TASK_SUB_BASE_TIME, ZONE_RADIUS, CATEGORY_PENALTY_RATE, TASK_WEIGHT,
  TASK_SECTION_DEADLINES,
  generateSessionPlan, createInitialAssets, travelTime,
  SESSION_DURATION_BY_COMPLEXITY,
  LAMBDA, CATEGORY_WEIGHTS, CATEGORIES, FLEET, TUTORIAL_FLEET,
  FAILURE_COUNT_CONST, FAILURE_GAP_CONST, FAILURE_JITTER_CONST, FAILURE_PROB_CONST,
} from '../utils/missionGen'
import { generateStrategies, CONSERVATIVE_TOP_UP, CONSERVATIVE_REDUNDANCY_BUFFER } from '../utils/copilot'
import { findSchedulingCycle } from '../utils/scheduling'
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

// ─── Tutorial second-mission blueprint (agent-introduction phase) ──────────
// Fixed 3-task mission: T2 Recon + T2 Recon + T4 Precision Supply.
// Two T2s push Aggressive's parallel-sum well above its sequential floor while
// Conservative stays near that floor, so the two strategy cards always show
// visibly different drone counts — unlike a randomly-drawn single-task mission,
// where the two formulas can coincide.

const TUTORIAL_SECOND_BLUEPRINT: MissionBlueprint = {
  id: 'T002',
  arrivalTime: 0,  // overridden by FORCE_MISSION_ARRIVAL
  category: 'D',
  taskTypes: [2, 2, 4],
  zoneCenter: { x: 700, y: 250 },
  waypoints: [
    { x: 684, y: 210 },  // T2 — northwest
    { x: 730, y: 215 },  // T2 — northeast
    { x: 705, y: 295 },  // T4 — south
  ],
  willFail: false,
  droneFailureTimes: [],
}

// ─── Initial state factory ─────────────────────────────────────────────────

// Per-session complexity: sessionComplexities[sessionNumber-1] when set (study builder),
// otherwise every session falls back to the single config.complexity.
export function complexityForSession(config: StudyConfig, sessionNumber: number): Complexity {
  return config.sessionComplexities?.[sessionNumber - 1] ?? config.complexity
}

// Fast-test collapses every session to 10s so the whole flow can be walked quickly.
function sessionDurationFor(config: StudyConfig, complexity: Complexity): number {
  return config.fastTest ? 10 : SESSION_DURATION_BY_COMPLEXITY[complexity]
}

function categoryForecastFor(complexity: Complexity): Record<MissionCategory, number> {
  const forecast: Record<MissionCategory, number> = { A: 0, B: 0, C: 0, D: 0, E: 0 }
  switch (complexity) {
    case 'balanced':  Object.assign(forecast, { A: 0.20, B: 0.30, C: 0.28, D: 0.17, E: 0.05 }); break
    case 'strategic': Object.assign(forecast, { A: 0.40, B: 0.38, C: 0.16, D: 0.05, E: 0.01 }); break
    case 'tactical':  Object.assign(forecast, { A: 0.03, B: 0.08, C: 0.22, D: 0.42, E: 0.25 }); break
    case 'full':      Object.assign(forecast, { A: 0.05, B: 0.15, C: 0.28, D: 0.32, E: 0.20 }); break
    case 'quick':     Object.assign(forecast, { A: 0.35, B: 0.30, C: 0.20, D: 0.12, E: 0.03 }); break
  }
  return forecast
}

export function buildInitialState(config: StudyConfig): GameState {
  const complexity = complexityForSession(config, 1)
  // In tutorial mode the two fixed-position tutorial zones are prepended below; seed the generator's
  // keep-out with their centres so free-play missions don't spawn on top of them.
  const seedCenters = config.tutorialMode
    ? [TUTORIAL_FIRST_BLUEPRINT.zoneCenter, TUTORIAL_SECOND_BLUEPRINT.zoneCenter]
    : []
  const generated = generateSessionPlan(new SeededRNG(config.seed ^ 1), complexity, undefined, seedCenters)
  const blueprints = config.tutorialMode
    ? [TUTORIAL_FIRST_BLUEPRINT, TUTORIAL_SECOND_BLUEPRINT, ...generated]
    : generated

  return {
    config,
    phase: config.collectDemographics ? 'demographics' : 'playing',
    demographics: null,
    sessionNumber: 1,
    elapsed: 0,
    sessionStartMs: null,
    assets: createInitialAssets(complexity, config.tutorialMode ? TUTORIAL_FLEET : undefined),
    missions: [],
    pendingBlueprints: blueprints,
    score: 0,
    penaltyAccrued: 0,
    completedSessionScores: [],
    sessionDuration: sessionDurationFor(config, complexity),
    categoryForecast: categoryForecastFor(complexity),
    strategicModal: null,
    trustProbeActive: false,
    nextTrustProbeAt: TRUST_PROBE_INTERVAL,
    events: Array.from({ length: config.numSessions }, () => []),
    eventSeq: 0,
  }
}

// ─── Helper: log event ────────────────────────────────────────────────────

// Distributive Omit so it works across the discriminated union
type EventPayload = GameEvent extends infer E
  ? E extends { seq: number; timestamp: number; wallClock: string; sessionId: string; sessionNumber: number; elapsed: number; reserveState: AssetRequirement }
    ? Omit<E, 'seq' | 'timestamp' | 'wallClock' | 'sessionId' | 'sessionNumber' | 'elapsed' | 'reserveState'>
    : never
  : never

function logEvent(state: GameState, event: EventPayload): GameState {
  const full: GameEvent = {
    ...event,
    seq: state.eventSeq,
    timestamp: Math.round(state.elapsed * 1000),
    wallClock: new Date().toISOString(),
    sessionId: `${state.config.participantId}_${state.config.seed}_s${state.sessionNumber}`,
    sessionNumber: state.sessionNumber,
    elapsed: state.elapsed,
    reserveState: reserveCount(state.assets),
  } as GameEvent
  const idx = state.sessionNumber - 1
  const updated = [...state.events]
  updated[idx] = [...updated[idx], full]
  return { ...state, events: updated, eventSeq: state.eventSeq + 1 }
}

// ─── Helper: current reserve ──────────────────────────────────────────────

// Reserve = available drones. When `missions` is passed, drones already committed to a mission's
// pending tactical plan (strategically allocated but not yet deployed) are excluded, so the
// displayed reserve reflects what can actually still be committed elsewhere. Omitting `missions`
// gives the raw physical hub inventory (used for the logged reserveState envelope).
export function reserveCount(assets: Asset[], missions?: Mission[]): AssetRequirement {
  const locked = new Set<string>()
  if (missions) {
    for (const m of missions) {
      if (m.tacticalPending && m.pendingAllocation) {
        for (const id of m.pendingAllocation.dronePool) locked.add(id)
      }
    }
  }
  const avail = assets.filter(a => a.status === 'available' && !locked.has(a.id))
  return {
    Blue:  avail.filter(a => a.type === 'Blue').length,
    Red:   avail.filter(a => a.type === 'Red').length,
    Green: avail.filter(a => a.type === 'Green').length,
  }
}

// Greedy redundancy: a stable spot on the mission-zone perimeter (hub-facing arc) where a
// drone waits when it has no task. Deterministic per drone id so a loitering drone keeps the
// same slot frame-to-frame. All committed drones sit at the zone edge so they can cover a
// failure quickly; they only return to the reserve once every task is done.
function loiterSlot(mission: Mission, droneId: string): { x: number; y: number } {
  const { x: cx, y: cy } = mission.zoneCenter
  const r = mission.zoneRadius
  const hubAngle = Math.atan2(HUB.y - cy, HUB.x - cx)
  const arc = Math.PI * 0.9
  const frac = (hashId(droneId) % 997) / 997   // 0..1, stable per drone
  const a = hubAngle - arc / 2 + arc * frac
  return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) }
}

// On strategic allocation the committed team sets off toward the mission immediately, flying to
// their loiter slots on the zone edge. If they arrive before a tactical plan is confirmed they
// simply wait there for instructions (the TICK loiter block holds them while the mission is
// tactical-pending). Only touches idle ('available') pool drones — anything already deployed is
// left alone.
function launchToLoiter(assets: Asset[], mission: Mission, dronePool: string[], now: number): Asset[] {
  const pool = new Set(dronePool)
  return assets.map(asset => {
    if (!pool.has(asset.id) || asset.status !== 'available') return asset
    const slot = loiterSlot(mission, asset.id)
    const tt = travelTime(HUB, slot, ASSET_SPEED[asset.type])
    return {
      ...asset,
      status: 'deployed' as const,
      currentMissionId: mission.id,
      currentTaskId: null,
      position: { ...HUB },
      travelFrom: { ...HUB },
      targetPosition: slot,
      travelStartElapsed: now,
      travelEndElapsed: now + tt,
      availableAt: now + tt,
    }
  })
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
    tacticalOpenedAtMs: null,
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

function buildTaskCompositions(tasks: Task[]): Record<string, { primary: AssetRequirement; substitute: AssetRequirement | null; baseTime: number; subBaseTime: number | null }> {
  const out: Record<string, { primary: AssetRequirement; substitute: AssetRequirement | null; baseTime: number; subBaseTime: number | null }> = {}
  for (const t of tasks) {
    const substitute = TASK_SUBSTITUTE[t.type]
    out[t.id] = {
      primary: TASK_PRIMARY[t.type],
      substitute,
      baseTime: TASK_BASE_TIME[t.type],
      subBaseTime: substitute ? TASK_SUB_BASE_TIME[t.type] : null,
    }
  }
  return out
}

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

// Which task should a drone fly to FIRST? The first task in its own chain sequence — this honours
// the operator's ordering, which matters for deadlocks: if two drones are chained into a cycle
// (Fast t1→t2, Lifter t2→t1) they must set off to DIFFERENT tasks so the deadlock is physically
// real. Falling back to earliest start time would send both to the same task (the cyclic plan's
// start times are inconsistent), silently dissolving the deadlock the operator built. Only when a
// drone has no explicit sequence do we fall back to earliest start.
function pickFirstAssignment(myAsgns: TaskAssignment[], seq: string[] | undefined): TaskAssignment {
  if (seq && seq.length) {
    const firstTid = seq.find(tid => myAsgns.some(a => a.taskId === tid))
    if (firstTid) return myAsgns.find(a => a.taskId === firstTid)!
  }
  return myAsgns.reduce((min, a) => a.startTime < min.startTime ? a : min)
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
  loiterAll = false,
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

  const poolSet = new Set(pending.dronePool)
  const updatedAssets = state.assets.map(asset => {
    const myAsgns = assignments.filter(a => a.assetIds.includes(asset.id))
    if (myAsgns.length === 0) {
      // Greedy: a committed-but-unassigned drone still flies out to the mission edge and
      // waits there as a redundancy backup (covers failures quickly). Other modes: stays put.
      if (loiterAll && poolSet.has(asset.id) && asset.status === 'available') {
        const slot = loiterSlot(mission, asset.id)
        const tt = travelTime(HUB, slot, ASSET_SPEED[asset.type])
        return {
          ...asset,
          status: 'deployed' as const,
          currentMissionId: mission.id,
          currentTaskId: null,
          travelFrom: { ...HUB },
          targetPosition: slot,
          travelStartElapsed: now,
          travelEndElapsed: now + tt,
          availableAt: now + tt,
        }
      }
      return asset
    }
    // Assignable if idle at the hub, or already loitering on THIS mission (launched at strategic
    // time). Don't touch a drone that is committed/executing elsewhere (stale pending pool).
    const loiteringHere = asset.status === 'deployed' && asset.currentMissionId === mission.id && asset.currentTaskId === null
    if (asset.status !== 'available' && !loiteringHere) return asset
    // Travel starts from wherever the drone actually is now — the hub if idle, or its current
    // in-flight/loiter position if it already set off toward the zone.
    const origin = loiteringHere ? interpolateAssetPosition(asset, now) : { ...HUB }
    const firstAsgn = pickFirstAssignment(myAsgns, droneSequences[asset.id])
    const task = updatedTasks.find(t => t.id === firstAsgn.taskId)!
    const tt = travelTime(origin, task.waypoint, ASSET_SPEED[asset.type])
    return {
      ...asset,
      status: 'deployed' as const,
      currentMissionId: mission.id,
      currentTaskId: task.id,
      position: origin,
      travelFrom: origin,
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

  const agentPlan = pending.taskOrder
    .filter(tid => (pending.taskAssignments[tid] ?? []).length > 0)
    .map((tid, order) => {
      const task = mission.tasks.find(t => t.id === tid)!
      return { taskId: tid, taskType: task.type, assetIds: pending.taskAssignments[tid], order }
    })
  const finalPlan = taskOrder
    .map((tid, order) => {
      const asgn = assignments.find(a => a.taskId === tid)
      if (!asgn) return null
      const task = mission.tasks.find(t => t.id === tid)!
      return { taskId: tid, taskType: task.type, assetIds: asgn.assetIds, order }
    })
    .filter((x): x is { taskId: string; taskType: TaskType; assetIds: string[]; order: number } => x !== null)

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
    latencyMs: mission.tacticalOpenedAtMs !== null ? Math.round(now * 1000) - mission.tacticalOpenedAtMs : 0,
    suggestUsedCount: mission.tacticalSuggestCount ?? 0,
    agentPlan,
    finalPlan,
  })

  return s
}

// ─── Helper: build assignments from manual drag-and-drop ──────────────────

/**
 * Computes task start times respecting the user's per-drone chain order.
 * Uses bounded relaxation (taskStarts only ever grows) so multi-drone, multi-hop
 * chains — where a task's true start depends on a drone that's still finishing an
 * earlier task, whose own start was itself raised by a THIRD drone — converge to a
 * consistent fixed point rather than an under-estimate from a single naive sweep.
 *
 * NOTE on cross-drone chain cycles (e.g. Blue chained task1→task2 while Red is chained
 * task2→task1): these never reach a consistent fixed point — each task waits on a drone
 * that is itself waiting on the other task — so relaxation just keeps inflating their
 * starts until the pass cap. We deliberately DON'T reject them here: the operator/agent
 * is allowed to build a deadlocking plan. The inflated (finite) start means the drones
 * still fly out and then sit idle at the zone; the live deadlock detector in TICK
 * (findSchedulingCycle on the running mission) is what notices they're genuinely stuck
 * and fails one task to break it. Keeping this pure/schedule-only avoids second-guessing
 * the operator at build time.
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

  // Relaxation: taskStarts only ever grows, so this converges within (task count) passes
  // for an acyclic dependency graph; a deadlocking (cyclic) plan just runs to the cap with
  // inflated starts, and is caught live in TICK rather than here.
  const taskStarts: Record<string, number> = {}
  const maxPasses = Object.keys(taskAssignments).length + 1

  for (let pass = 0; pass < maxPasses; pass++) {
    // Reset per-drone state at start of each pass. A drone that already set off toward the zone
    // (deployed/loitering) starts its travel from its current position, not the hub.
    const droneFreeAt: Record<string, number> = {}
    const dronePos: Record<string, { x: number; y: number }> = {}
    for (const id of allDroneIds) {
      droneFreeAt[id] = elapsed
      const a = assetById.get(id)
      dronePos[id] = (a && a.status === 'deployed') ? interpolateAssetPosition(a, elapsed) : { ...HUB }
    }

    // Forward-sweep each drone's sequence, accumulating max arrivals per task
    let changed = false
    for (const droneId of allDroneIds) {
      const asset = assetById.get(droneId)
      if (!asset) continue
      const speed = ASSET_SPEED[asset.type]
      const seq = droneSequences[droneId] ?? []

      for (const taskId of seq) {
        const task = mission.tasks.find(t => t.id === taskId)
        if (!task) continue
        const arrival = droneFreeAt[droneId] + travelTime(dronePos[droneId], task.waypoint, speed)
        const prevStart = taskStarts[taskId]
        const nextStart = prevStart === undefined ? arrival : Math.max(prevStart, arrival)
        if (nextStart !== prevStart) changed = true
        taskStarts[taskId] = nextStart
        // Drone departs after the task finishes (using updated taskStart from this pass)
        const baseTime = getManualBaseTime(task, taskAssignments[taskId] ?? [], assetById)
        droneFreeAt[droneId] = taskStarts[taskId] + baseTime
        dronePos[droneId] = { ...task.waypoint }
      }
    }
    if (!changed) break
  }

  // Build TaskAssignment records from converged start times
  const result: TaskAssignment[] = []
  for (const [taskId, droneIds] of Object.entries(taskAssignments)) {
    const task = mission.tasks.find(t => t.id === taskId)
    if (!task || droneIds.length === 0 || taskStarts[taskId] === undefined) continue
    // Guard: only dispatch tasks whose assigned drones meet primary or substitute composition
    if (!taskMeetsComposition(task, droneIds, assetById)) continue
    const startTime = taskStarts[taskId]
    const baseTime = getManualBaseTime(task, droneIds, assetById)
    const useSubstitute = isUsingSubstitute(task, droneIds, assetById)
    result.push({ taskId, assetIds: droneIds, startTime, travelTime: startTime - elapsed, baseTime, useSubstitute })
  }
  return result
}

/**
 * Recomputes start times for a set of not-yet-started tasks (their drones idle and free)
 * from the drones' CURRENT positions. Used after a scheduling deadlock is broken: the
 * surviving tasks in the cycle were carrying inflated/stale starts computed while the
 * cycle was unresolved, so the freed drones would otherwise wait far too long. Only
 * 'traveling'/'pending' tasks are touched — anything already executing/completed/failed
 * is left exactly as-is.
 */
function rescheduleTasks(mission: Mission, assets: Asset[], taskIds: string[], elapsed: number): Task[] {
  const taskAssignments: Record<string, string[]> = {}
  for (const tid of taskIds) {
    const t = mission.tasks.find(x => x.id === tid)
    if (t && (t.status === 'traveling' || t.status === 'pending') && t.assignedAssetIds.length > 0) {
      taskAssignments[tid] = t.assignedAssetIds
    }
  }
  if (Object.keys(taskAssignments).length === 0) return mission.tasks

  const seqs: Record<string, string[]> = {}
  for (const [id, seq] of Object.entries(mission.droneSequences ?? {})) {
    const f = seq.filter(tid => taskAssignments[tid])
    if (f.length) seqs[id] = f
  }

  const fresh = buildManualAssignments(mission, assets, taskAssignments, seqs, elapsed)
  const byId = new Map(fresh.map(a => [a.taskId, a]))
  return mission.tasks.map(t => {
    const a = byId.get(t.id)
    if (!a || (t.status !== 'traveling' && t.status !== 'pending')) return t
    return {
      ...t,
      status: 'traveling' as const,
      startTime: a.startTime,
      completionTime: a.startTime + a.baseTime,
      baseTime: a.baseTime,
      travelTime: Math.max(0, a.startTime - elapsed),
      useSubstitute: a.useSubstitute,
    }
  })
}

/**
 * Repairs a scheduling deadlock WITHOUT failing anything (fixLockouts = on). The cyclic tasks'
 * drones disagree on visit order (e.g. Fast t1→t2, Lifter t2→t1); we reorder just those tasks
 * onto ONE canonical order (most-constrained task first) so every drone visits the shared tasks
 * in the same direction — the dependency graph becomes acyclic. Then the not-yet-started tasks are
 * rescheduled from the drones' current positions and each freed drone is redirected to the first
 * task in its new order. Every task keeps its drones — nothing is dropped, nothing fails.
 */
function rerouteDeadlock(
  mission: Mission,
  assets: Asset[],
  cycleTaskIds: string[],
  elapsed: number,
): { tasks: Task[]; assets: Asset[]; droneSequences: Record<string, string[]> } {
  const cyc = new Set(cycleTaskIds)
  const rank = new Map<string, number>()
  ;[...mission.tasks]
    .filter(t => cyc.has(t.id))
    .sort((a, b) => (b.type - a.type) || (a.id < b.id ? -1 : 1))   // most-constrained first, then stable by id
    .forEach((t, i) => rank.set(t.id, i))

  // Reorder ONLY the cyclic-task slots of each drone's sequence onto the canonical order.
  const newSeqs: Record<string, string[]> = {}
  for (const [id, seq] of Object.entries(mission.droneSequences ?? {})) {
    const ordered = seq.filter(t => cyc.has(t)).sort((a, b) => rank.get(a)! - rank.get(b)!)
    let k = 0
    newSeqs[id] = seq.map(t => cyc.has(t) ? ordered[k++] : t)
  }

  const notStartedIds = mission.tasks
    .filter(t => (t.status === 'traveling' || t.status === 'pending') && t.assignedAssetIds.length > 0)
    .map(t => t.id)
  const tasks = rescheduleTasks({ ...mission, droneSequences: newSeqs }, assets, notStartedIds, elapsed)

  // Redirect each deployed, non-executing drone to the first not-yet-finished task in its new order.
  const taskById = new Map(tasks.map(t => [t.id, t]))
  const newAssets = assets.map(asset => {
    if (asset.currentMissionId !== mission.id || asset.status !== 'deployed') return asset
    const cur = asset.currentTaskId ? taskById.get(asset.currentTaskId) : undefined
    if (cur && cur.status === 'executing') return asset   // never yank a drone off a running task
    const seq = newSeqs[asset.id] ?? []
    const firstTid = seq.find(tid => {
      const t = taskById.get(tid)
      return t && t.status !== 'completed' && t.status !== 'failed'
    })
    if (!firstTid || firstTid === asset.currentTaskId) return asset
    const target = taskById.get(firstTid)!
    const pos = interpolateAssetPosition(asset, elapsed)
    const tt = travelTime(pos, target.waypoint, ASSET_SPEED[asset.type])
    return {
      ...asset,
      currentTaskId: firstTid,
      position: pos,
      travelFrom: { ...pos },
      targetPosition: { ...target.waypoint },
      travelStartElapsed: elapsed,
      travelEndElapsed: elapsed + tt,
    }
  })

  return { tasks, assets: newAssets, droneSequences: newSeqs }
}

function taskMeetsComposition(task: Task, droneIds: string[], assetById: Map<string, Asset>): boolean {
  const prim = TASK_PRIMARY[task.type as TaskType]
  const sub  = TASK_SUBSTITUTE[task.type as TaskType]
  const done = new Set(task.completedSectionTypes ?? [])
  const comp: AssetRequirement = { Blue: 0, Red: 0, Green: 0 }
  for (const id of droneIds) { const a = assetById.get(id); if (a) comp[a.type]++ }
  // A type whose section is already done doesn't need to be in the new assignment
  const meetsPrim = (done.has('Blue') || comp.Blue >= prim.Blue) &&
                    (done.has('Red')  || comp.Red  >= prim.Red)  &&
                    (done.has('Green')|| comp.Green >= prim.Green)
  const meetsSub  = !!sub &&
                    (done.has('Blue') || comp.Blue >= sub.Blue) &&
                    (done.has('Red')  || comp.Red  >= sub.Red)  &&
                    (done.has('Green')|| comp.Green >= sub.Green)
  return meetsPrim || meetsSub
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

// ─── Greedy one-step replanning ─────────────────────────────────────────────

// Pick the drones needed to cover a task from a pool of free drones (primary comp, else
// substitute). Returns null if the free pool can't cover it right now.
function pickDronesForTask(task: Task, free: Asset[]): { ids: string[]; useSubstitute: boolean; baseTime: number } | null {
  const tryComp = (req: AssetRequirement, baseTime: number, useSub: boolean) => {
    const ids: string[] = []
    for (const col of ['Blue', 'Red', 'Green'] as AssetType[]) {
      const cands = free.filter(a => a.type === col && !ids.includes(a.id)).slice(0, req[col]).map(a => a.id)
      if (cands.length < req[col]) return null
      ids.push(...cands)
    }
    return { ids, useSubstitute: useSub, baseTime }
  }
  const prim = tryComp(TASK_PRIMARY[task.type as TaskType], TASK_BASE_TIME[task.type as TaskType], false)
  if (prim) return prim
  const sub = TASK_SUBSTITUTE[task.type as TaskType]
  if (sub) {
    const subPick = tryComp(sub, TASK_SUB_BASE_TIME[task.type as TaskType], true)
    if (subPick) return subPick
  }
  return null
}

// Greedy mode commits one step at a time, but engages EVERY drone each step: whenever a
// mission has drones loitering on-mission and pending (unscheduled) tasks, assign as many of
// those tasks as the free drones can cover RIGHT NOW, in parallel — most-constrained first.
// One drone per task this wave (no chaining); tasks it can't cover stay pending ("to plan")
// until drones free up. This runs every tick, so a drone that finishes never sits idle while a
// coverable task remains.
export function applyGreedyReplan(state: GameState, elapsed: number): GameState {
  let missions = state.missions
  let assets = state.assets
  let changed = false

  for (const mission of state.missions) {
    if (mission.status !== 'active') continue
    // A lockout awaiting operator recovery is the operator's to fix — don't let greedy replan
    // silently re-fill the reverted tasks and dissolve the "help needed" state.
    if (mission.failureRecoveryPending && mission.recoveryReason === 'lockout') continue

    const free = assets.filter(a =>
      a.currentMissionId === mission.id && a.status === 'deployed' && a.currentTaskId === null)
    if (free.length === 0) continue

    const pendingTasks = mission.tasks
      .filter(t => t.status === 'pending' && t.assignedAssetIds.length === 0 && t.id !== mission.tacticallySuppressedTaskId)
      .sort((a, b) => b.type - a.type)   // most-constrained first
    if (pendingTasks.length === 0) continue

    // Greedily cover as many pending tasks as possible this wave, each drone used once.
    const used = new Set<string>()
    const taskUpdate = new Map<string, { ids: string[]; useSubstitute: boolean; baseTime: number; startTime: number }>()
    const assetTarget = new Map<string, { taskId: string; waypoint: { x: number; y: number } }>()
    for (const task of pendingTasks) {
      const avail = free.filter(a => !used.has(a.id))
      const pick = pickDronesForTask(task, avail)
      if (!pick) continue   // can't cover yet — leave pending for a later wave
      const startTime = elapsed + Math.max(...pick.ids.map(id => {
        const a = assets.find(x => x.id === id)!
        return travelTime(a.position, task.waypoint, ASSET_SPEED[a.type])
      }))
      pick.ids.forEach(id => used.add(id))
      taskUpdate.set(task.id, { ids: pick.ids, useSubstitute: pick.useSubstitute, baseTime: pick.baseTime, startTime })
      for (const id of pick.ids) assetTarget.set(id, { taskId: task.id, waypoint: task.waypoint })
    }
    if (taskUpdate.size === 0) continue

    missions = missions.map(m => m.id !== mission.id ? m : {
      ...m,
      tasks: m.tasks.map(t => {
        const u = taskUpdate.get(t.id)
        if (!u) return t
        return {
          ...t,
          status: 'traveling' as const,
          assignedAssetIds: u.ids,
          allocatedAt: elapsed,
          useSubstitute: u.useSubstitute,
          baseTime: u.baseTime,
          travelTime: Math.max(0, u.startTime - elapsed),
          startTime: u.startTime,
          completionTime: u.startTime + u.baseTime,
          recallDelay: 0,
        }
      }),
      droneSequences: {
        ...m.droneSequences,
        ...Object.fromEntries([...taskUpdate].flatMap(([tid, u]) => u.ids.map(id => [id, [tid]]))),
      },
    })
    assets = assets.map(a => {
      const tgt = assetTarget.get(a.id)
      if (!tgt) return a
      return {
        ...a,
        currentTaskId: tgt.taskId,
        travelFrom: { ...a.position },
        targetPosition: { ...tgt.waypoint },
        travelStartElapsed: elapsed,
        travelEndElapsed: elapsed + travelTime(a.position, tgt.waypoint, ASSET_SPEED[a.type]),
      }
    })
    changed = true
  }
  return changed ? { ...state, missions, assets } : state
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
      const isGreedy = state.config.tacticalMode === 'greedy'

      let s: GameState = { ...state, elapsed, sessionStartMs }

      if (state.sessionStartMs === null) {
        const cfg = state.config
        const sessionComplexity = complexityForSession(cfg, state.sessionNumber)
        s = logEvent(s, {
          type: 'session_start',
          participantId: cfg.participantId,
          condition: cfg.condition,
          mode: cfg.mode,
          complexity: sessionComplexity,
          seed: cfg.seed,
          epsilonStrategic: cfg.agentErrorRate,
          epsilonTactical: cfg.epsilonTactical,
          tacticalMode: cfg.tacticalMode,
          fixLockouts: cfg.fixLockouts !== false,
          numSessions: cfg.numSessions,
          sessionDuration: state.sessionDuration,
          fleet: (cfg.tutorialMode ? TUTORIAL_FLEET : FLEET[sessionComplexity]).reduce(
            (acc, [type, count]) => ({ ...acc, [type]: count }),
            { Blue: 0, Red: 0, Green: 0 } as AssetRequirement,
          ),
          assetSpeeds: ASSET_SPEED,
          taskBaseTime: TASK_BASE_TIME,
          taskSubBaseTime: TASK_SUB_BASE_TIME,
          taskPrimary: TASK_PRIMARY,
          taskSubstitute: TASK_SUBSTITUTE,
          taskWeight: TASK_WEIGHT,
          categoryPenaltyRate: CATEGORY_PENALTY_RATE,
          categoryWeights: Object.fromEntries(
            CATEGORIES.map((cat, i) => [cat, CATEGORY_WEIGHTS[sessionComplexity][i]])
          ) as Record<MissionCategory, number>,
          arrivalLambda: LAMBDA[sessionComplexity],
          failureCount: FAILURE_COUNT_CONST,
          failureGap: FAILURE_GAP_CONST,
          failureJitter: FAILURE_JITTER_CONST,
          failureProb: FAILURE_PROB_CONST,
          conservativeTopUp: CONSERVATIVE_TOP_UP,
          conservativeRedundancyBuffer: CONSERVATIVE_REDUNDANCY_BUFFER,
        })
      }

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
            taskCompositions: buildTaskCompositions(m.tasks),
            scheduledFailureTimes: m.droneFailureTimes,
            penaltyRate: CATEGORY_PENALTY_RATE[m.category],
            maxReward: m.tasks.reduce((sum, t) => sum + TASK_WEIGHT[t.type], 0),
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

          // Sections-by-colour: check if this drone type's section is already complete
          const sectionDeadline = TASK_SECTION_DEADLINES[failedTask.type as number]?.[failedDrone.type] ?? 1.0
          const isGracefulExit = sectionDeadline < 1.0 &&
            failedTask.startTime !== null &&
            elapsed >= failedTask.startTime + failedTask.baseTime * sectionDeadline

          // On a non-graceful failure the task reverts to pending. Fully release the task's OTHER
          // drones back to loitering (rather than leaving them half-staffing a stalled task) so the
          // task becomes cleanly re-coverable — the greedy replanner only fills tasks with no drones,
          // and a half-staffed pending task with its remaining drones stuck on it would freeze forever.
          const releaseIds = isGracefulExit ? [] : failedTask.assignedAssetIds.filter(id => id !== failedDrone.id)
          const releaseSet = new Set(releaseIds)
          const updatedAssets = s.assets.map(a => {
            if (a.id === failedDrone.id) {
              return { ...a, status: 'failed' as const, failedAt: elapsed, currentMissionId: null, currentTaskId: null, replacementAt: elapsed + replacementDelay }
            }
            if (releaseSet.has(a.id)) {
              const slot = loiterSlot(mission, a.id)
              const tt = travelTime(a.position, slot, ASSET_SPEED[a.type])
              return { ...a, currentTaskId: null, travelFrom: { ...a.position }, targetPosition: slot,
                travelStartElapsed: elapsed, travelEndElapsed: elapsed + tt, availableAt: elapsed + tt }
            }
            return a
          })

          let updatedMissions: typeof s.missions
          if (isGracefulExit) {
            // Section done — drone gracefully exits; task continues without it, no recovery dialog
            updatedMissions = s.missions.map(m => {
              if (m.id !== mission.id) return m
              return {
                ...m,
                droneFailuresFired: m.droneFailuresFired + 1,
                failedDroneId: failedDrone.id,
                tasks: m.tasks.map(t =>
                  t.id === failedTask.id ? {
                    ...t,
                    assignedAssetIds: t.assignedAssetIds.filter(id => id !== failedDrone.id),
                    completedSectionTypes: [...new Set([...(t.completedSectionTypes ?? []), failedDrone.type])],
                  } : t
                ),
              }
            })
          } else {
            // Section incomplete — revert task to pending, offer recovery
            updatedMissions = s.missions.map(m => {
              if (m.id !== mission.id) return m
              return {
                ...m,
                droneFailuresFired: m.droneFailuresFired + 1,
                failedDroneId: failedDrone.id,
                failureRecoveryPending: true,
                tasks: m.tasks.map(t =>
                  t.id === failedTask.id
                    ? { ...t, status: 'pending' as const, assignedAssetIds: [], startTime: null, completionTime: null }
                    : t
                ),
                pendingRecoveryOptions: buildRecoveryOptions(m, failedTask, failedDrone.id, updatedAssets, elapsed),
              }
            })
          }

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
      const assetSnap = new Map(s.assets.map(a => [a.id, a]))
      const updatedMissions = s.missions.map(mission => {
        if (mission.status !== 'active') return mission

        let missionChanged = false
        const updatedTasks = mission.tasks.map(task => {
          if (task.status === 'traveling' && task.startTime !== null && elapsed >= task.startTime) {
            missionChanged = true
            return { ...task, status: 'executing' as const }
          }
          if (task.status === 'executing') {
            // Sections-by-colour safety net: each drone type must cover its active window
            if (task.startTime !== null && task.baseTime > 0) {
              const prog = Math.min(1, (elapsed - task.startTime) / task.baseTime)
              const sections = TASK_SECTION_DEADLINES[task.type as number] ?? {}
              const prim = TASK_PRIMARY[task.type as TaskType]
              const done = new Set(task.completedSectionTypes ?? [])
              let sectionFail = false
              for (const [droneType, deadline] of Object.entries(sections) as [string, number][]) {
                if (done.has(droneType)) continue                    // already recorded as done
                if (deadline < 1.0 && prog >= deadline) continue    // non-full-duration section passed
                const required = prim[droneType as AssetType] ?? 0
                if (required === 0) continue
                const present = task.assignedAssetIds.filter(id => {
                  const a = assetSnap.get(id)
                  return a && a.status !== 'failed' && a.currentTaskId === task.id && a.type === droneType
                }).length
                if (present < required) { sectionFail = true; break }
              }
              if (sectionFail) {
                missionChanged = true
                return { ...task, status: 'failed' as const }
              }
            }
            if (task.completionTime !== null && elapsed >= task.completionTime) {
              missionChanged = true
              return { ...task, status: 'completed' as const }
            }
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

      // 3a. Mission completion events (check before reassigning s.missions to updatedMissions)
      for (let mi = 0; mi < updatedMissions.length; mi++) {
        const oldM = s.missions[mi]
        const newM = updatedMissions[mi]
        if (oldM && newM && oldM.status !== 'completed' && newM.status === 'completed') {
          s = logEvent(s, {
            type: 'mission_completed',
            missionId: newM.id,
            missionCategory: newM.category,
            completionTime: elapsed,
            tasksCompleted: newM.tasks.filter(t => t.status === 'completed').length,
            tasksFailed: newM.tasks.filter(t => t.status === 'failed').length,
            rewardEarned: newM.tasks.reduce((sum, t) => sum + (t.status === 'completed' ? TASK_WEIGHT[t.type] : 0), 0),
            penaltyAccrued: computePenaltyAccrued([newM], elapsed),
          })
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

      // 3c. Live scheduling-deadlock detection (runs on the ACTUAL running mission, not at
      // build time). A cross-drone chain cycle — Fast chained task1→task2 while Lifter is
      // chained task2→task1 — leaves each task waiting on a drone that is itself waiting on
      // the other task, so no drone can ever make progress. We deliberately let the operator/
      // agent commit such a plan and let the drones fly out; only once the cycle's drones have
      // physically ARRIVED and are sitting idle (deadlocked — not merely idle for any reason,
      // and not while one is still en route or actively executing) do we act.
      //
      // config.fixLockouts (default true) chooses what "act" means:
      //  • true  — the agent repairs it silently: reroute the conflicting drone chains onto one
      //            consistent order so the graph is acyclic, reschedule and redirect. Every task
      //            still completes and nothing fails.
      //  • false — surface it to the operator as "help needed" (same class as a drone failure): free
      //            the stuck drones, revert the deadlocked tasks to pending, and flag the mission for
      //            recovery so the operator re-plans a good allocation. Greedy replan is paused for the
      //            mission (see applyGreedyReplan) so the operator — not the agent — resolves it.
      const fixLockouts = state.config.fixLockouts !== false   // default ON: agent auto-reroutes
      for (const mission of s.missions) {
        if (mission.status !== 'active' || mission.failureRecoveryPending) continue
        const incomplete = mission.tasks.filter(t => t.status !== 'completed' && t.status !== 'failed')
        const taskAssignments: Record<string, string[]> = {}
        for (const t of incomplete) if (t.assignedAssetIds.length > 0) taskAssignments[t.id] = t.assignedAssetIds
        const seqs: Record<string, string[]> = {}
        for (const [id, seq] of Object.entries(mission.droneSequences ?? {})) {
          const f = seq.filter(tid => taskAssignments[tid])
          if (f.length) seqs[id] = f
        }
        const cyc = findSchedulingCycle(taskAssignments, seqs)
        if (!cyc) continue

        // Require every drone forming the cycle to have arrived at its waypoint and be idle
        // (not executing) — i.e. genuinely stuck because of the cycle, per the brief.
        const cycleDrones = [...new Set(cyc.flatMap(tid => taskAssignments[tid] ?? []))]
        const stuck = cycleDrones.length > 0 && cycleDrones.every(id => {
          const a = s.assets.find(x => x.id === id)
          if (!a || a.status !== 'deployed') return false
          if (elapsed < (a.travelEndElapsed ?? Infinity)) return false     // still travelling to its waypoint
          const t = mission.tasks.find(tt => tt.id === a.currentTaskId)
          return !t || t.status !== 'executing'                            // not actively working a task
        })
        if (!stuck) continue

        if (fixLockouts) {
          // Repair: reroute so every task still completes; nothing fails.
          const { tasks, assets: reroutedAssets, droneSequences } = rerouteDeadlock(mission, s.assets, cyc, elapsed)
          s = {
            ...s,
            assets: reroutedAssets,
            missions: s.missions.map(m => m.id === mission.id ? { ...mission, tasks, droneSequences } : m),
          }
          s = logEvent(s, {
            type: 'lockout_detected', missionId: mission.id, missionCategory: mission.category,
            taskIds: cyc, droneIds: cycleDrones, resolution: 'rerouted',
          })
        } else {
          // Help needed: surface it like a drone failure. Free the stuck cycle drones (loiter on-
          // mission at their slots so they stay available for reassignment), revert the deadlocked
          // tasks to pending, and flag the mission for operator recovery.
          const cycTaskSet = new Set(cyc)
          const cycleDroneSet = new Set(cycleDrones)
          s = {
            ...s,
            assets: s.assets.map(a => {
              if (!cycleDroneSet.has(a.id) || a.status !== 'deployed') return a
              const slot = loiterSlot(mission, a.id)
              const pos = interpolateAssetPosition(a, elapsed)
              const tt = travelTime(pos, slot, ASSET_SPEED[a.type])
              return {
                ...a, currentTaskId: null, position: pos, travelFrom: { ...pos }, targetPosition: slot,
                travelStartElapsed: elapsed, travelEndElapsed: elapsed + tt, availableAt: elapsed + tt,
              }
            }),
            missions: s.missions.map(m => m.id === mission.id ? {
              ...m,
              failureRecoveryPending: true,
              recoveryReason: 'lockout' as const,
              failedDroneId: null,
              pendingRecoveryOptions: [],
              droneSequences: Object.fromEntries(
                Object.entries(m.droneSequences ?? {}).map(([id, seq]) => [id, seq.filter(t => !cycTaskSet.has(t))]),
              ),
              tasks: m.tasks.map(t => cycTaskSet.has(t.id)
                ? { ...t, status: 'pending' as const, assignedAssetIds: [], startTime: null, completionTime: null, allocatedAt: null }
                : t),
            } : m),
          }
          s = logEvent(s, {
            type: 'lockout_detected', missionId: mission.id, missionCategory: mission.category,
            taskIds: cyc, droneIds: cycleDrones, resolution: 'help_needed',
          })
        }
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

        // When task completes (or fails, e.g. via the sections-by-colour safety net): redirect
        // to next sequential task, or return to hub. A failed task never becomes 'completed', so
        // without also matching 'failed' here a drone still assigned to it would sit with
        // currentTaskId pointed at a dead task forever — this is what used to orphan drones.
        if (asset.status === 'deployed' && asset.currentTaskId) {
          const currentMission = s.missions.find(m => m.id === asset.currentMissionId)
          const task = currentMission?.tasks.find(t => t.id === asset.currentTaskId)

          const recallReady = task?.status === 'failed' ||
            (task?.status === 'completed' && elapsed >= (task.completionTime ?? 0) + task.recallDelay)

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

            // No next task. In greedy mode the drone stays on-mission as a redundancy backup:
            // it flies to its slot on the zone edge and waits there. It only returns to the
            // reserve once ALL of the mission's tasks are done (handled in the loiter block).
            if (isGreedy && currentMission && currentMission.status === 'active') {
              const slot = loiterSlot(currentMission, asset.id)
              const tt = travelTime(newPos, slot, ASSET_SPEED[asset.type])
              return {
                ...asset,
                currentTaskId: null,                 // free, loitering on-mission
                travelFrom: { ...newPos },
                targetPosition: slot,
                travelStartElapsed: elapsed,
                travelEndElapsed: elapsed + tt,
                position: newPos,
              }
            }

            // Return to hub
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

        // Loitering drone (waiting at the zone edge): either a strategically-committed drone that
        // set off before its tactical plan was confirmed, or a greedy redundancy backup between
        // tasks. Hold while the mission is still awaiting tactical planning OR active; once it is
        // finished/abandoned, return to the reserve.
        if (asset.status === 'deployed' && asset.currentTaskId === null && asset.currentMissionId) {
          const loiterMission = s.missions.find(m => m.id === asset.currentMissionId)
          const stillOnMission = !!loiterMission && (loiterMission.status === 'active' || loiterMission.tacticalPending)
          if (!stillOnMission) {
            const returnTime = travelTime(asset.position, HUB, ASSET_SPEED[asset.type])
            return {
              ...asset,
              status: 'returning' as const,
              currentMissionId: null,
              currentTaskId: null,
              travelFrom: { ...asset.position },
              targetPosition: { ...HUB },
              travelStartElapsed: elapsed,
              travelEndElapsed: elapsed + returnTime,
              availableAt: elapsed + returnTime,
              position: newPos,
            }
          }
          return { ...asset, position: newPos }   // keep loitering in place
        }

        return { ...asset, status: newStatus, position: newPos }
      })

      s = { ...s, assets: updatedAssets }

      // 4b. Greedy one-step replanning: dispatch the next task from on-mission drones once
      // the current step is done.
      if (isGreedy) s = applyGreedyReplan(s, elapsed)

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
      const openedAtMs = Math.round(state.elapsed * 1000)
      let s: GameState = {
        ...state,
        strategicModal: {
          missionId: action.missionId,
          strategies,
          selectedStrategyIndex: null,
          manualAllocation: { Blue: 0, Red: 0, Green: 0 },
          openedAtMs,
        },
      }
      s = logEvent(s, {
        type: 'strategic_modal_opened',
        missionId: mission.id,
        missionCategory: mission.category,
        timeRemainingInSession: Math.max(0, state.sessionDuration - state.elapsed),
        activeMissions: state.missions.filter(m => m.status === 'active').length,
        currentPenaltyAccrued: state.penaltyAccrued,
        strategiesPresented: strategies.map(st => ({
          name: st.name,
          description: st.description,
          displayedAssets: st.assets,
          trueAssets: st.trueAssets,
          displayedCompletionTime: st.expectedCompletionTime,
          reserveAfter: st.reserveAfter,
          speedScore: st.speedScore,
          reserveScore: st.reserveScore,
          redundancyScore: st.redundancyScore,
          isBadSuggestion: st.isBadSuggestion,
          badSuggestionType: st.badSuggestionType,
        })),
      })
      return s
    }

    // ── CLOSE_STRATEGIC ──────────────────────────────────────────────────
    case 'CLOSE_STRATEGIC': {
      const modal = state.strategicModal
      const mission = modal ? state.missions.find(m => m.id === modal.missionId) : undefined
      if (!modal || !mission) return { ...state, strategicModal: null }
      const s = logEvent(state, {
        type: 'strategic_dismissed',
        missionId: modal.missionId,
        missionCategory: mission.category,
        latencyMs: Math.round(state.elapsed * 1000) - modal.openedAtMs,
        timeRemainingInSession: Math.max(0, state.sessionDuration - state.elapsed),
      })
      return { ...s, strategicModal: null }
    }

    // ── PICK_STRATEGY ────────────────────────────────────────────────────
    case 'PICK_STRATEGY': {
      if (!state.strategicModal) return state
      const modal = state.strategicModal
      let s: GameState = {
        ...state,
        strategicModal: { ...modal, selectedStrategyIndex: action.strategyIndex },
      }
      // Deliberation signal: which card the operator highlighted, and when. Toggling between
      // Aggressive/Conservative before applying shows they engaged with both options.
      const mission = state.missions.find(m => m.id === modal.missionId)
      const name = modal.strategies[action.strategyIndex]?.name
      if (mission && (name === 'Aggressive' || name === 'Conservative')) {
        s = logEvent(s, {
          type: 'strategic_card_previewed',
          missionId: modal.missionId,
          missionCategory: mission.category,
          strategyIndex: action.strategyIndex,
          strategyName: name,
          latencyMs: Math.round(state.elapsed * 1000) - modal.openedAtMs,
          timeRemainingInSession: Math.max(0, state.sessionDuration - state.elapsed),
        })
      }
      return s
    }

    // ── EDIT_MANUAL ──────────────────────────────────────────────────────
    case 'EDIT_MANUAL': {
      if (!state.strategicModal) return state
      const modal = state.strategicModal
      let s: GameState = {
        ...state,
        strategicModal: { ...modal, manualAllocation: action.allocation },
      }
      // Deliberation signal: the running manual drone counts + when each adjustment happened, so
      // the manual-build path and effort (number of edits, time spent) are recoverable.
      const mission = state.missions.find(m => m.id === modal.missionId)
      if (mission) {
        s = logEvent(s, {
          type: 'manual_allocation_edited',
          missionId: modal.missionId,
          missionCategory: mission.category,
          allocation: action.allocation,
          latencyMs: Math.round(state.elapsed * 1000) - modal.openedAtMs,
          timeRemainingInSession: Math.max(0, state.sessionDuration - state.elapsed),
        })
      }
      return s
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
        // Greedy: commit the WHOLE team (assigned drones + any redundant spares in the
        // composition) to the mission so every committed drone flies to the zone edge and
        // waits — spares provide quick failure cover. Other modes keep the assigned subset.
        if (state.config.tacticalMode === 'greedy') {
          const full: string[] = []
          for (const type of ['Blue', 'Red', 'Green'] as AssetType[]) {
            full.push(...available.filter(a => a.type === type).slice(0, composition[type]).map(a => a.id))
          }
          dronePool = [...new Set([...dronePool, ...full])]
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

      // Greedy: the suggested baseline only ever holds the first step (no future tasks).
      if (state.config.tacticalMode === 'greedy') {
        const f = taskOrder[0]
        taskAssignmentMap = taskAssignmentMap[f] ? { [f]: taskAssignmentMap[f] } : {}
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

      const diffAssets = (a: AssetRequirement, b: AssetRequirement): AssetRequirement =>
        ({ Blue: a.Blue - b.Blue, Red: a.Red - b.Red, Green: a.Green - b.Green })
      const aggressiveCard = modal.strategies.find(st => st.name === 'Aggressive')
      const conservativeCard = modal.strategies.find(st => st.name === 'Conservative')

      let s = logEvent(state, {
        type: 'strategic_choice',
        missionId: mission.id,
        missionCategory: mission.category,
        choiceType: strategyName === 'Aggressive' ? 'aggressive' : strategyName === 'Conservative' ? 'conservative' : 'manual',
        wasAgentSuggestion: action.source === 'agent',
        agentSuggestionWasBad: isBad,
        badSuggestionType: badType,
        assetsChosen: composition,
        editedFromStrategy: action.editedFromStrategy ?? null,
        timeRemainingInSession: Math.max(0, state.sessionDuration - now),
        latencyMs: Math.round(now * 1000) - modal.openedAtMs,
        deltaVsAggressive: aggressiveCard ? diffAssets(composition, aggressiveCard.trueAssets) : null,
        deltaVsConservative: conservativeCard ? diffAssets(composition, conservativeCard.trueAssets) : null,
        strategyCardCount: modal.strategies.length,
        manualBeforeCardsLoaded: action.source === 'manual' ? (action.manualBeforeCardsLoaded ?? null) : null,
        cardsLoadedAtManualSwitch: action.source === 'manual' ? (action.cardsLoadedAtManualSwitch ?? null) : null,
      })

      const tacticalOpenedAtMs = Math.round(now * 1000)
      const agentPlanForLog = taskOrder
        .filter(tid => (taskAssignmentMap[tid] ?? []).length > 0)
        .map((tid, order) => {
          const task = mission.tasks.find(t => t.id === tid)!
          return { taskId: tid, taskType: task.type, assetIds: taskAssignmentMap[tid], order }
        })
      s = logEvent(s, {
        type: 'tactical_opened',
        missionId: mission.id,
        missionCategory: mission.category,
        strategyChosen: strategyName,
        agentPlan: agentPlanForLog,
        timeRemainingInSession: Math.max(0, state.sessionDuration - now),
      })

      // Both modes: set tacticalPending for tactical assignment step. The committed team also sets
      // off toward the mission zone right away and loiters there until the tactical plan is confirmed.
      s = {
        ...s,
        missions: s.missions.map(m => m.id === mission.id ? {
          ...m,
          tacticalPending: true,
          pendingAllocation,
          agentInteraction: action.source === 'agent' ? 'shown' : 'manual',
          chosenStrategyName: strategyName,
          tacticalOpenedAtMs,
          tacticalSuggestCount: 0,
        } : m),
        assets: launchToLoiter(s.assets, mission, dronePool, now),
        strategicModal: null,
      }
      return s
    }

    // ── TACTICAL_SUGGEST ─────────────────────────────────────────────────
    // Operator clicked "Suggest" to pull the agent's plan into the (empty) tactical
    // planner. Logged so consultation of the tactical agent can be measured directly
    // rather than inferred from modifiedFromAgentPlan (the planner starts blank, so
    // suggestUsedCount === 0 on a confirm means the agent plan was never consulted).
    case 'TACTICAL_SUGGEST': {
      const mission = state.missions.find(m => m.id === action.missionId)
      if (!mission || !mission.tacticalPending || !mission.pendingAllocation) return state
      const suggestCountThisMission = (mission.tacticalSuggestCount ?? 0) + 1
      let s: GameState = {
        ...state,
        missions: state.missions.map(m => m.id === mission.id ? { ...m, tacticalSuggestCount: suggestCountThisMission } : m),
      }
      s = logEvent(s, {
        type: 'tactical_suggest_used',
        missionId: mission.id,
        missionCategory: mission.category,
        suggestCountThisMission,
        timeRemainingInSession: Math.max(0, state.sessionDuration - state.elapsed),
      })
      return s
    }

    // ── TACTICAL_ASSIGN_CHANGED (logging only — captures each drag while building a plan) ──
    case 'TACTICAL_ASSIGN_CHANGED': {
      const mission = state.missions.find(m => m.id === action.missionId)
      if (!mission) return state
      const droneType = state.assets.find(a => a.id === action.droneId)?.type ?? null
      const taskType = action.taskId
        ? (mission.tasks.find(t => t.id === action.taskId)?.type ?? null)
        : null
      return logEvent(state, {
        type: 'tactical_assignment_changed',
        missionId: mission.id,
        missionCategory: mission.category,
        op: action.op,
        droneId: action.droneId,
        droneType,
        taskId: action.taskId,
        taskType,
        recoveryMode: action.recoveryMode,
        timeRemainingInSession: Math.max(0, state.sessionDuration - state.elapsed),
      })
    }

    // ── CONFIRM_TACTICAL ─────────────────────────────────────────────────
    case 'CONFIRM_TACTICAL': {
      const mission = state.missions.find(m => m.id === action.missionId)
      if (!mission || !mission.tacticalPending || !mission.pendingAllocation) return state

      const pending = mission.pendingAllocation
      const isGreedy = state.config.tacticalMode === 'greedy'
      // Commit exactly what the operator confirmed — including any multi-hop chains they drew.
      // "Greedy" applies to the AGENT, not the operator: the agent's suggested baseline is already
      // collapsed to a single first step in APPLY_STRATEGIC, and greedy replan (needsGreedyReplan)
      // later fills only the tasks the operator left UNASSIGNED as drones free up. An operator-
      // specified path longer than one hop is always honoured and never trimmed here.
      const ta: Record<string, string[]> | undefined = action.taskAssignments
      const droneSeqs = action.droneSequences ?? {}
      let assignments: TaskAssignment[]

      const userProvidedAssignments = !!ta
      if (userProvidedAssignments) {
        assignments = buildManualAssignments(mission, state.assets, ta!, droneSeqs, state.elapsed)
      } else {
        // Auto-fill fallback: assign from the committed pool (already launched and loitering at the
        // zone), not the hub reserve — otherwise it would deploy fresh drones and orphan the team.
        const poolDrones = state.assets.filter(a => pending.dronePool.includes(a.id))
        assignments = greedyAssign(mission.tasks, poolDrones, pending.composition, state.elapsed, undefined, pending.taskOrder)
      }

      if (assignments.length === 0) return state

      // modifiedFromAgentPlan / changedTaskIds: did the operator alter the drones on any task the
      // AGENT actually suggested? Compare ONLY over the agent's own task keys (pending.taskAssignments).
      // In greedy the agent's committed baseline is a single first step, so steps the operator adds
      // beyond it are expected greedy workflow — NOT an override — and must not count. In plan-all the
      // agent suggests every task, so the same comparison naturally spans the whole plan.
      const norm = (ids: string[] | undefined) => [...(ids ?? [])].sort().join()
      const changedTaskIds = userProvidedAssignments
        ? Object.keys(pending.taskAssignments).filter(tid => norm(pending.taskAssignments[tid]) !== norm(ta![tid]))
        : []
      const modifiedFromAgentPlan = changedTaskIds.length > 0

      // chainingUsed: true if any drone appears in more than one task's assignment list
      const chainingUsed = userProvidedAssignments
        ? (() => {
            const allIds = Object.values(ta!).flat()
            return allIds.some((id, _, arr) => arr.filter(x => x === id).length > 1)
          })()
        : false
      let s = applyTacticalAllocation(state, action.missionId, assignments, pending, pending.taskOrder, modifiedFromAgentPlan, droneSeqs, chainingUsed, changedTaskIds, isGreedy)
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
      const openedAtMs = Math.round(state.elapsed * 1000)
      let s: GameState = {
        ...state,
        missions: state.missions.map(m => m.id === action.missionId ? { ...m, tacticalPending: false, pendingAllocation: null } : m),
        strategicModal: { missionId: action.missionId, strategies, selectedStrategyIndex: null, manualAllocation: null, openedAtMs },
      }
      s = logEvent(s, {
        type: 'strategic_modal_opened',
        missionId: mission.id,
        missionCategory: mission.category,
        timeRemainingInSession: Math.max(0, state.sessionDuration - state.elapsed),
        activeMissions: state.missions.filter(m => m.status === 'active').length,
        currentPenaltyAccrued: state.penaltyAccrued,
        strategiesPresented: strategies.map(st => ({
          name: st.name,
          description: st.description,
          displayedAssets: st.assets,
          trueAssets: st.trueAssets,
          displayedCompletionTime: st.expectedCompletionTime,
          reserveAfter: st.reserveAfter,
          speedScore: st.speedScore,
          reserveScore: st.reserveScore,
          redundancyScore: st.redundancyScore,
          isBadSuggestion: st.isBadSuggestion,
          badSuggestionType: st.badSuggestionType,
        })),
      })
      return s
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
        // Guard: only dispatch if adding this drone satisfies primary or substitute composition
        const totalIds = [...task.assignedAssetIds.filter(id => id !== opt.redistributeToAssetId), opt.redistributeToAssetId!]
        const assetByIdR = new Map(s.assets.map(a => [a.id, a]))
        if (taskMeetsComposition(task, totalIds, assetByIdR)) {
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
                assignedAssetIds: totalIds,
                allocatedAt: s.elapsed,
                travelTime: tt,
                startTime,
                completionTime,
              } : t),
            } : m),
          }
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
      // Guard: only dispatch if the total composition (existing + new) meets requirements
      const totalIdsM = [...task.assignedAssetIds.filter(id => id !== action.newAssetId), action.newAssetId]
      const assetByIdM = new Map(state.assets.map(a => [a.id, a]))
      if (!taskMeetsComposition(task, totalIdsM, assetByIdM)) return state
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
      const assetById = new Map(state.assets.map(a => [a.id, a]))

      // (Re)assign PENDING tasks using the mission's own subswarm — drones already deployed on this
      // mission (idle/loitering after a failure release) — which is exactly what the recovery planner
      // offers. Reserve drones are also accepted if somehow provided. (Previously this only accepted
      // 'available' reserve drones, so the on-mission drones the planner hands you were silently
      // dropped and the task stayed frozen.)
      const recoverable = (id: string) => {
        const a = assetById.get(id)
        return !!a && a.status !== 'failed' &&
          (a.status === 'available' || (a.status === 'deployed' && a.currentMissionId === mission.id))
      }
      const recoveryTaskAssignments: Record<string, string[]> = {}
      for (const task of mission.tasks) {
        if (task.status !== 'pending') continue
        const ids = (action.taskAssignments[task.id] ?? []).filter(recoverable)
        if (ids.length > 0) recoveryTaskAssignments[task.id] = ids
      }

      // Per-drone sequences: planner chain order (filtered to the pending tasks the drone covers),
      // falling back to pending-task order when the planner didn't supply sequences. Persisting these
      // onto the mission is what lets the strategic map's hover reveal a reassigned drone's full
      // remaining path, and lets TICK chain the drone through its tasks in order.
      const recoverySeqs: Record<string, string[]> = {}
      const recoveryDroneIds = [...new Set(Object.values(recoveryTaskAssignments).flat())]
      for (const id of recoveryDroneIds) {
        const fromAction = action.droneSequences?.[id]
        const seq = (fromAction && fromAction.length > 0)
          ? fromAction.filter(tid => (recoveryTaskAssignments[tid] ?? []).includes(id))
          : Object.keys(recoveryTaskAssignments).filter(tid => recoveryTaskAssignments[tid].includes(id))
        if (seq.length > 0) recoverySeqs[id] = seq
      }

      // Reuse the canonical converger so chained (multi-task) reassignments get correct start times.
      const recoveryAssignments = buildManualAssignments(mission, state.assets, recoveryTaskAssignments, recoverySeqs, now)
      const asgnByTask = new Map(recoveryAssignments.map(a => [a.taskId, a]))

      const newTasks = mission.tasks.map(task => {
        const asgn = asgnByTask.get(task.id)
        if (!asgn || task.status !== 'pending') return task
        return {
          ...task,
          status: 'traveling' as const,
          assignedAssetIds: [
            ...task.assignedAssetIds.filter(id => !asgn.assetIds.includes(id)),
            ...asgn.assetIds,
          ],
          allocatedAt: now,
          travelTime: asgn.travelTime,
          baseTime: asgn.baseTime,
          useSubstitute: asgn.useSubstitute,
          startTime: asgn.startTime,
          completionTime: asgn.startTime + asgn.baseTime,
          recallDelay: 0,
        }
      })

      // Deploy each reassigned drone to the FIRST task in its sequence; later tasks are picked up
      // by the sequential chaining in TICK once the current step completes.
      const newAssets = state.assets.map(asset => {
        const myAsgns = recoveryAssignments.filter(a => a.assetIds.includes(asset.id))
        if (myAsgns.length === 0 || !recoverable(asset.id)) return asset
        const firstAsgn = pickFirstAssignment(myAsgns, recoverySeqs[asset.id])
        const task = newTasks.find(t => t.id === firstAsgn.taskId)!
        // Travel from where the drone actually is — its loiter/current position if already on-mission,
        // else the hub.
        const origin = asset.status === 'deployed' ? interpolateAssetPosition(asset, now) : { ...HUB }
        const tt = travelTime(origin, task.waypoint, ASSET_SPEED[asset.type])
        return {
          ...asset,
          status: 'deployed' as const,
          currentMissionId: mission.id,
          currentTaskId: task.id,
          position: origin,
          travelFrom: origin,
          targetPosition: { ...task.waypoint },
          travelStartElapsed: now,
          travelEndElapsed: now + tt,
          availableAt: now + tt + firstAsgn.baseTime + travelTime(task.waypoint, HUB, ASSET_SPEED[asset.type]),
        }
      })

      let s = logEvent(state, {
        type: 'failure_recovery',
        missionId: mission.id,
        missionCategory: mission.category,
        recoveryType: 'manual',
        wasAgentSuggested: false,
        timeRemainingInSession: Math.max(0, state.sessionDuration - now),
      })

      return {
        ...s,
        assets: newAssets,
        missions: s.missions.map(m => m.id === action.missionId ? {
          ...m,
          tasks: newTasks,
          droneSequences: { ...m.droneSequences, ...recoverySeqs },
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
          ? { ...m, status: 'abandoned' as const, abandonedAt: elapsed, abandonedReason: 'operator' as const, failureRecoveryPending: false, pendingRecoveryOptions: null }
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

    // ── SUBMIT_DEMOGRAPHICS ──────────────────────────────────────────────
    case 'SUBMIT_DEMOGRAPHICS': {
      if (state.phase !== 'demographics') return state
      const s = logEvent({ ...state, demographics: action.responses }, {
        type: 'phase_change', fromPhase: state.phase, toPhase: 'playing',
      })
      return { ...s, phase: 'playing' }
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
      const toPhase = state.sessionNumber < state.config.numSessions ? 'between' : 'done'
      const s = logEvent(state, { type: 'phase_change', fromPhase: state.phase, toPhase })
      return { ...s, phase: toPhase }
    }

    // ── NEXT_SESSION ─────────────────────────────────────────────────────
    case 'NEXT_SESSION': {
      if (state.phase !== 'between') return state
      const nextSession = state.sessionNumber + 1
      const complexity = complexityForSession(state.config, nextSession)
      const blueprints = generateSessionPlan(new SeededRNG(state.config.seed ^ nextSession), complexity)
      const s = logEvent(state, { type: 'phase_change', fromPhase: state.phase, toPhase: 'playing' })

      return {
        ...s,
        phase: 'playing',
        sessionNumber: nextSession,
        elapsed: 0,
        sessionStartMs: null,
        assets: createInitialAssets(complexity, state.config.tutorialMode ? TUTORIAL_FLEET : undefined),
        missions: [],
        pendingBlueprints: blueprints,
        score: 0,
        penaltyAccrued: 0,
        sessionDuration: sessionDurationFor(state.config, complexity),
        categoryForecast: categoryForecastFor(complexity),
        strategicModal: null,
        trustProbeActive: false,
        nextTrustProbeAt: TRUST_PROBE_INTERVAL,
      }
    }

    // ── END_STUDY ────────────────────────────────────────────────────────
    case 'END_STUDY': {
      const s = logEvent(state, { type: 'phase_change', fromPhase: state.phase, toPhase: 'done' })
      return { ...s, phase: 'done' }
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
        taskCompositions: buildTaskCompositions(mission.tasks),
        scheduledFailureTimes: mission.droneFailureTimes,
        penaltyRate: CATEGORY_PENALTY_RATE[mission.category],
        maxReward: mission.tasks.reduce((sum, t) => sum + TASK_WEIGHT[t.type], 0),
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
      const now = state.elapsed
      // The operator's chosen team already set off toward the zone on strategic allocation. Recall
      // them to the hub so we can swap in the fixed training team, then launch that team instead.
      const recalled = state.assets.map(a => pending.dronePool.includes(a.id)
        ? { ...a, status: 'available' as const, currentMissionId: null, currentTaskId: null,
            position: { ...HUB }, travelFrom: { ...HUB }, targetPosition: { ...HUB }, availableAt: now }
        : a)
      const allAvailable = availableExcludingPending(recalled, state.missions, mission.id)
      const want = { Blue: 2, Red: 1, Green: 1 }
      const blues  = allAvailable.filter(a => a.type === 'Blue').slice(0, want.Blue)
      const reds   = allAvailable.filter(a => a.type === 'Red').slice(0, want.Red)
      const greens = allAvailable.filter(a => a.type === 'Green').slice(0, want.Green)
      const newPool = [...blues, ...reds, ...greens].map(a => a.id)
      if (newPool.length === 0) return state
      const newComposition: AssetRequirement = { Blue: blues.length, Red: reds.length, Green: greens.length }
      const taskOrder = [...mission.tasks].sort((a, b) => b.type - a.type).map(t => t.id)
      const poolAssets = recalled.filter(a => newPool.includes(a.id))
      const assignments = greedyAssign(mission.tasks, poolAssets, newComposition, now, undefined, taskOrder)
      const taskAssignmentMap = Object.fromEntries(assignments.map(a => [a.taskId, a.assetIds]))
      const expectedCompletionTime = assignments.length > 0
        ? Math.max(...assignments.map(a => a.startTime + a.baseTime))
        : pending.expectedCompletionTime
      return {
        ...state,
        assets: launchToLoiter(recalled, mission, newPool, now),
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
    // Fails the mission's Red drone so its task becomes genuinely uncoverable:
    // failure recovery only draws from the deployed subswarm, which now has no Red
    // to spare. With no feasible recovery the operator's only option is to abandon.
    case 'TUTORIAL_FORCE_ABANDON_SCENARIO': {
      const mission = state.missions.find(m => m.status === 'active' && !m.failureRecoveryPending)
      if (!mission) return state

      // Prefer the Red drone (the training mission has only one) so the Red-requiring
      // task is left with no substitute in the subswarm. Fall back to any deployed drone.
      const deployed = state.assets.filter(
        a => a.currentMissionId === mission.id && a.status === 'deployed' && a.currentTaskId
      )
      const failedDrone = deployed.find(a => a.type === 'Red') ?? deployed[0]

      // No deployed drone with a task yet — fall back to the bare unrecoverable flag.
      if (!failedDrone) {
        return {
          ...state,
          missions: state.missions.map(m => m.id === mission.id ? {
            ...m,
            failureRecoveryPending: true,
            failedDroneId: null,
            pendingRecoveryOptions: [],
          } : m),
        }
      }

      const failedTask = mission.tasks.find(t => t.id === failedDrone.currentTaskId)!
      const updatedAssets = state.assets.map(a =>
        a.id === failedDrone.id
          ? { ...a, status: 'failed' as const, failedAt: state.elapsed, currentMissionId: null, currentTaskId: null }
          : a
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
          pendingRecoveryOptions: [],   // empty = no feasible recovery, operator must abandon
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
      // Release the failed task's remaining drones back to loitering so it can be re-covered cleanly
      // (see the scheduled-failure handler in TICK for why a half-staffed pending task freezes).
      const releaseIds = failedTask.assignedAssetIds.filter(id => id !== failedDrone.id)
      const releaseSet = new Set(releaseIds)
      const updatedAssets = state.assets.map(a => {
        if (a.id === failedDrone.id) return { ...a, status: 'failed' as const, failedAt: state.elapsed, currentMissionId: null, currentTaskId: null }
        if (releaseSet.has(a.id)) {
          const slot = loiterSlot(mission, a.id)
          const tt = travelTime(a.position, slot, ASSET_SPEED[a.type])
          return { ...a, currentTaskId: null, travelFrom: { ...a.position }, targetPosition: slot,
            travelStartElapsed: state.elapsed, travelEndElapsed: state.elapsed + tt, availableAt: state.elapsed + tt }
        }
        return a
      })
      const updatedMissions = state.missions.map(m => {
        if (m.id !== mission.id) return m
        return {
          ...m,
          droneFailuresFired: m.droneFailuresFired + 1,
          failedDroneId: failedDrone.id,
          failureRecoveryPending: true,
          tasks: m.tasks.map(t =>
            t.id === failedTask.id
              ? { ...t, status: 'pending' as const, assignedAssetIds: [], startTime: null, completionTime: null }
              : t
          ),
          pendingRecoveryOptions: buildRecoveryOptions(m, failedTask, failedDrone.id, updatedAssets, state.elapsed),
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
      return endSession(state, 'forced')
    }

    default:
      return state
  }
}

// ─── End-session helper ───────────────────────────────────────────────────

function endSession(s: GameState, reason: 'timer' | 'forced' = 'timer'): GameState {
  // Inflight before failing tasks below, so we capture what was still in motion
  const inFlightMissionIds = s.missions
    .filter(m => m.status === 'queued' || m.status === 'active')
    .map(m => m.id)

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

  const tacticalFollowRate = (() => {
    const plans = evs.filter(e => e.type === 'tactical_confirmed') as Array<{ wasAgentSuggested: boolean; modifiedFromAgentPlan: boolean }>
    const agentPlans = plans.filter(e => e.wasAgentSuggested)
    const unmodified = agentPlans.filter(e => !e.modifiedFromAgentPlan).length
    return agentPlans.length > 0 ? unmodified / agentPlans.length : 0
  })()

  let s2 = logEvent({ ...s, missions: failedMissions, score, penaltyAccrued }, {
    type: 'session_ended',
    score,
    penaltyAccrued,
    completionPoints,
    greenEfficiency: greenEff,
    meanMissionTime: meanTime,
    agentFollowRate,
    tacticalFollowRate,
    reason,
    inFlightMissionIds,
  })

  s2 = logEvent(s2, { type: 'phase_change', fromPhase: s.phase, toPhase: 'survey' })

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
