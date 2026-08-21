import type {
  GameState, GameEvent, Asset, Mission, Task,
  AssetType, TaskType, AssetRequirement,
  MissionCategory, TaskComp, RecoveryOption,
  PendingAllocation, MissionBlueprint, Complexity, EventContext,
} from '../types'
import type { GameAction } from './actions'
import {
  HUB, ASSET_SPEED, TASK_BASE_TIME, TASK_PRIMARY, TASK_SUBSTITUTE,
  TASK_SUB_BASE_TIME, ZONE_RADIUS, CATEGORY_PENALTY_RATE, TASK_WEIGHT,
  TASK_SECTION_DEADLINES,
  generateSessionPlan, createInitialAssets, travelTime,
  SESSION_DURATION_BY_COMPLEXITY,
  LAMBDA, CATEGORY_WEIGHTS, CATEGORIES, FLEET, TUTORIAL_FLEET,
  FAILURE_RATE_PER_DRONE_SECOND,
} from '../utils/missionGen'
import { generateStrategies, CONSERVATIVE_TOP_UP, CONSERVATIVE_REDUNDANCY_BUFFER } from '../utils/copilot'
import { findSchedulingCycle } from '../utils/scheduling'
import { onMissionDrones, taskCoverableBy, unfinishedTasks } from '../utils/coverage'
import { SeededRNG } from '../utils/prng'
import { isFixLockouts } from '../utils/config'
import { debugLog } from '../utils/debugLog'
import type { StudyConfig } from '../types'

// ─── Constants ────────────────────────────────────────────────────────────

const TRUST_PROBE_INTERVAL = 90  // seconds
// Cadence of the periodic full-state dump (state_snapshot). 10 s over an 8-minute session is
// ~48 snapshots — enough to reconstruct the screen at any moment (including long idle stretches
// where no operator action fires an event) without dominating the log.
const STATE_SNAPSHOT_INTERVAL = 10  // seconds

// Build identifier stamped into session_start, so collected data can be tied to a code version.
// Kept identical to the git tag: `git show study-v1.0` is exactly what a session logging
// "study-v1.0" ran. Note this is the BUILD version — distinct from the scenario parameter-set
// versions (v1/v2/v2.1) in docs/SCENARIOS.md, which this build pins at v2.1.
// Bump it and add a section to docs/STUDY_BUILD.md whenever scoring, mission generation, agent
// behaviour, or any of the decisions recorded there changes — then tag the commit to match.
const APP_VERSION = 'study-v1.3'

// Largest slice of simulated time a single TICK may advance. See the stall-absorption comment in
// the TICK handler: without it, a suspended requestAnimationFrame loop replayed the whole
// hidden-window gap in one frame.
const MAX_TICK_GAP_MS = 2000

function hashId(id: string): number {
  return id.split('').reduce((acc, c, i) => (acc ^ (c.charCodeAt(0) * (i + 7))) >>> 0, 0)
}

// Simulated "Analysing…" reveal delay (ms) per strategy card. Deploy stays gated until every card
// has resolved, so this is a forced wait baked into strategic_choice.latencyMs — it is drawn from
// the seeded RNG (never Math.random) so a session replays identically, and logged on
// strategic_modal_opened / strategic_choice so it can be subtracted post hoc.
const CARD_REVEAL_MIN_MS = 4000
const CARD_REVEAL_SPAN_MS = 1000
function drawCardRevealDelays(seed: number, missionId: string, count: number): number[] {
  const rng = new SeededRNG((seed ^ hashId(missionId) ^ 0x5ea1) >>> 0)
  return Array.from({ length: count }, () => Math.round(CARD_REVEAL_MIN_MS + rng.next() * CARD_REVEAL_SPAN_MS))
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
}

// ─── Initial state factory ─────────────────────────────────────────────────

// Per-session complexity: sessionComplexities[sessionNumber-1] when set (study builder),
// otherwise every session falls back to the single config.complexity.
export function complexityForSession(config: StudyConfig, sessionNumber: number): Complexity {
  return config.sessionComplexities?.[sessionNumber - 1] ?? config.complexity
}

// Fast-test collapses every session to 10s so the whole flow can be walked quickly.
// The tutorial runs on the same clock as a real session but takes as long as the operator needs to
// read ~49 cards, so an 8-minute budget always expired mid-walkthrough — the header sat at 0:00
// and the score drifted deeply negative while the "Session Timer" and "Your Score" steps were
// still being explained. Give it a budget it will not exhaust, so the countdown still demonstrates
// the concept truthfully.
const TUTORIAL_SESSION_DURATION = 45 * 60

function sessionDurationFor(config: StudyConfig, complexity: Complexity): number {
  if (config.fastTest) return 10
  if (config.tutorialMode) return TUTORIAL_SESSION_DURATION
  return SESSION_DURATION_BY_COMPLEXITY[complexity]
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
    lastTickMs: null,
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
    nextSnapshotAt: 0,   // first snapshot on the opening tick, then every STATE_SNAPSHOT_INTERVAL
    events: Array.from({ length: config.numSessions }, () => []),
    eventSeq: 0,
  }
}

// ─── Helper: log event ────────────────────────────────────────────────────

// Distributive Omit so it works across the discriminated union
type EventPayload = GameEvent extends infer E
  ? E extends { seq: number; timestamp: number; wallClock: string; sessionId: string; sessionNumber: number; elapsed: number; reserveState: AssetRequirement }
    ? Omit<E, 'seq' | 'timestamp' | 'wallClock' | 'sessionId' | 'sessionNumber' | 'elapsed' | 'reserveState' | 'reserveStateAvailable' | 'context'>
    : never
  : never

// Situational context stamped on every event, so "how many X when Y happened" is answerable from
// a single event rather than by replaying the session. Cheap: pure counting over current state.
function buildContext(state: GameState): EventContext {
  const c: EventContext = {
    score: state.score,
    penaltyAccrued: state.penaltyAccrued,
    missionsQueued: 0, missionsActive: 0, missionsCompleted: 0, missionsFailed: 0, missionsAbandoned: 0,
    tasksPending: 0, tasksTraveling: 0, tasksExecuting: 0, tasksCompletedTotal: 0, tasksFailedTotal: 0,
    dronesAvailable: 0, dronesDeployed: 0, dronesReturning: 0, dronesFailed: 0,
    tacticalPendingMissionIds: [],
    recoveryPendingMissionIds: [],
    strategicModalMissionId: state.strategicModal?.missionId ?? null,
  }
  for (const m of state.missions) {
    if (m.status === 'queued') c.missionsQueued++
    else if (m.status === 'active') c.missionsActive++
    else if (m.status === 'completed') c.missionsCompleted++
    else if (m.status === 'failed') c.missionsFailed++
    else if (m.status === 'abandoned') c.missionsAbandoned++
    if (m.tacticalPending) c.tacticalPendingMissionIds.push(m.id)
    if (m.failureRecoveryPending) c.recoveryPendingMissionIds.push(m.id)
    for (const t of m.tasks) {
      if (t.status === 'pending') c.tasksPending++
      else if (t.status === 'traveling') c.tasksTraveling++
      else if (t.status === 'executing') c.tasksExecuting++
      else if (t.status === 'completed') c.tasksCompletedTotal++
      else if (t.status === 'failed') c.tasksFailedTotal++
    }
  }
  for (const a of state.assets) {
    if (a.status === 'available') c.dronesAvailable++
    else if (a.status === 'deployed') c.dronesDeployed++
    else if (a.status === 'returning') c.dronesReturning++
    else if (a.status === 'failed') c.dronesFailed++
  }
  return c
}

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
    // What the operator actually sees in the reserve panel / allocation picker: the same
    // pending-adjusted call the UI makes (PrimaryDisplay `reserveCount(state.assets, state.missions)`).
    reserveStateAvailable: reserveCount(state.assets, state.missions),
    context: buildContext(state),
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
      // A task stops accruing only when it is genuinely COMPLETED. `completionTime` is a PLANNED
      // finish time from the moment a task is scheduled, so a traveling/executing task — or one
      // killed mid-execution (drone failure, section safety-net, tactical lockout, session end) —
      // must be charged against live `elapsed`, not against a future time it never reached.
      //
      // An ABANDONED mission's clock stops at `abandonedAt`: every one of its incomplete tasks is
      // re-queued into a residual mission that starts accruing from that same instant, so charging
      // the parent against live `elapsed` too billed the operator twice for one piece of
      // outstanding work (and kept an abandoned mission's penalty visibly climbing forever).
      const cutoff = m.status === 'abandoned' && m.abandonedAt !== null ? m.abandonedAt : elapsed
      const endTime = t.status === 'completed' ? (t.completionTime ?? cutoff) : cutoff
      penalty += taskRate * Math.max(0, endTime - m.arrivalTime)
    }
  }
  return Math.round(penalty)
}

// mission_arrived payload builder — used by the timed spawn, the testing-mode force, and the
// residual re-queue on abandonment, so all three announce a mission with identical detail. The
// residual passes `parentMissionId`; everything else is organic new demand.
function missionArrivedPayload(mission: Mission, sessionDuration: number, parentMissionId: string | null = null) {
  return {
    type: 'mission_arrived' as const,
    missionId: mission.id,
    category: mission.category,
    tasks: mission.tasks.map(t => ({ id: t.id, type: t.type })),
    zoneCenter: mission.zoneCenter,
    arrivalTime: mission.arrivalTime,
    timeRemainingInSession: Math.max(0, sessionDuration - mission.arrivalTime),
    taskCompositions: buildTaskCompositions(mission.tasks),
    penaltyRate: CATEGORY_PENALTY_RATE[mission.category],
    maxReward: mission.tasks.reduce((sum, t) => sum + TASK_WEIGHT[t.type], 0),
    isResidual: parentMissionId !== null,
    parentMissionId,
  }
}

// task_failed payload builder — used by all five failure paths so they log the same detail.
// The bare {missionId, taskId, reason} of the original made it impossible to ask what was lost
// (reward forgone, how far the task had got, which drones were on it) without a full replay.
function taskFailedPayload(
  mission: Mission,
  task: Task,
  reason: 'asset_recalled' | 'session_ended' | 'drone_failure' | 'tactical_lockout' | 'scheduling_deadlock' | 'mission_abandoned',
  elapsed: number,
) {
  return {
    type: 'task_failed' as const,
    missionId: mission.id,
    missionCategory: mission.category,
    taskId: task.id,
    taskType: task.type,
    reason,
    statusBefore: task.status,
    assignedAssetIds: [...task.assignedAssetIds],
    startTime: task.startTime,
    rewardForgone: TASK_WEIGHT[task.type],
    waitFromMissionArrival: Math.max(0, elapsed - mission.arrivalTime),
    // Most 'session_ended' failures are tasks of missions the operator never took on at all; without
    // this the two very different stories ("never allocated" vs "cut off mid-flight") are
    // indistinguishable without joining against strategic_choice.
    missionWasAllocated: mission.allocationTime !== null,
    missionStatusBefore: mission.status,
  }
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

// recovery_opened payload — what the operator was actually shown when a mission asked for help.
// `feasibleWithOnMissionDrones` is the key RQ4 discriminator: it separates "operator failed to fix
// a fixable problem" from "nothing could have been done", which the resolution event alone can't.
function recoveryOpenedPayload(
  mission: Mission,
  assets: Asset[],
  missions: Mission[],
  reason: 'drone_failure' | 'lockout',
  failedDroneId: string | null,
  affectedTasks: Task[],
  elapsed: number,
  sessionDuration: number,
) {
  const failedDrone = failedDroneId ? assets.find(a => a.id === failedDroneId) : undefined
  // Drones already at the zone and not mid-task — exactly what the recovery planner offers.
  const onMission = assets.filter(a =>
    a.currentMissionId === mission.id && a.status === 'deployed' &&
    mission.tasks.find(t => t.id === a.currentTaskId)?.status !== 'executing'
  )
  const byId = new Map(assets.map(a => [a.id, a]))
  const pool = onMission.map(a => a.id)
  const feasible = affectedTasks.every(t => taskMeetsComposition(t, pool, byId))
  return {
    type: 'recovery_opened' as const,
    missionId: mission.id,
    missionCategory: mission.category,
    recoveryReason: reason,
    failedDroneId,
    failedDroneType: failedDrone?.type ?? null,
    affectedTaskIds: affectedTasks.map(t => t.id),
    affectedTaskTypes: affectedTasks.map(t => t.type),
    onMissionDroneIds: pool,
    reserveAvailable: reserveCount(assets, missions),
    feasibleWithOnMissionDrones: feasible,
    tasksRemaining: mission.tasks.filter(t => t.status !== 'completed' && t.status !== 'failed').length,
    timeRemainingInSession: Math.max(0, sessionDuration - elapsed),
  }
}

// Full-state dump for state_snapshot. Positions are interpolated to `elapsed` (the stored
// `position` only updates on tick) and rounded — sub-pixel precision is noise here.
function buildStateSnapshot(state: GameState, elapsed: number) {
  return {
    type: 'state_snapshot' as const,
    missions: state.missions.map(m => ({
      id: m.id,
      category: m.category,
      status: m.status,
      arrivalTime: m.arrivalTime,
      allocationTime: m.allocationTime,
      completionTime: m.completionTime,
      chosenStrategyName: m.chosenStrategyName,
      agentInteraction: m.agentInteraction,
      tacticalPending: m.tacticalPending,
      failureRecoveryPending: m.failureRecoveryPending,
      recoveryReason: m.recoveryReason ?? null,
      penaltyAccruedSoFar: computePenaltyAccrued([m], elapsed),
      tasks: m.tasks.map(t => ({
        id: t.id,
        type: t.type,
        status: t.status,
        assignedAssetIds: [...t.assignedAssetIds],
        startTime: t.startTime,
        completionTime: t.completionTime,
        useSubstitute: t.useSubstitute,
      })),
      droneSequences: m.droneSequences,
    })),
    assets: state.assets.map(a => {
      const p = interpolateAssetPosition(a, elapsed)
      return {
        id: a.id,
        type: a.type,
        status: a.status,
        currentMissionId: a.currentMissionId,
        currentTaskId: a.currentTaskId,
        x: Math.round(p.x),
        y: Math.round(p.y),
      }
    }),
  }
}

// ─── Helper: build recovery options ───────────────────────────────────────

function buildRecoveryOptions(
  mission: Mission,
  failedTask: Task,
  failedDroneId: string,
  assets: Asset[],
  _elapsed: number,
): RecoveryOption[] {
  // Only redistribution — operators must fix failures with their deployed subswarm.
  // The candidate must be one that ACCEPT_RECOVERY will actually accept: its guard requires the
  // resulting composition to satisfy the task, so test that here rather than offering any spare
  // drone as "feasible" and having the dispatch silently reject it.
  const byId = new Map(assets.map(a => [a.id, a]))
  const satisfies = (droneId: string) => taskMeetsComposition(
    failedTask,
    [...failedTask.assignedAssetIds.filter(id => id !== droneId && id !== failedDroneId), droneId],
    byId,
  )
  const otherDrone = assets.find(a =>
    a.currentMissionId === mission.id &&
    a.id !== failedDroneId &&
    a.status === 'deployed' &&
    mission.tasks.find(t => t.id === a.currentTaskId)?.status !== 'executing' &&
    satisfies(a.id)
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

/**
 * Fail `failedDrone` on `mission` and open the recovery planner. Shared by the tutorial's two
 * scripted failures; mirrors the scheduled-failure branch in TICK.
 *
 * The drone's own task — plus any `alsoRevertTaskIds` the caller has determined are now
 * uncoverable — revert to pending and their OTHER drones are released back to loitering rather
 * than left half-staffing a stalled task (see the TICK handler for why a half-staffed pending task
 * freezes). `elapsed` positions are left alone; the released drones simply fly to their loiter slot.
 */
function applyForcedDroneFailure(
  state: GameState,
  mission: Mission,
  failedDrone: Asset,
  alsoRevertTaskIds: string[] = [],
): GameState {
  const wanted = new Set<string>(alsoRevertTaskIds)
  if (failedDrone.currentTaskId) wanted.add(failedDrone.currentTaskId)
  // A chained drone is booked on later tasks too. Leaving those "traveling" behind a dead drone
  // strands them silently — they never start, and the recovery planner doesn't show them as
  // uncovered because they still hold an assignment. Revert them with the rest (same reasoning as
  // the lockout branch in TICK); anything already executing has its drones on site and is left be.
  for (const t of mission.tasks) {
    if (t.status !== 'executing' && t.assignedAssetIds.includes(failedDrone.id)) wanted.add(t.id)
  }
  const revertTasks = mission.tasks.filter(
    t => wanted.has(t.id) && t.status !== 'completed' && t.status !== 'failed'
  )
  // The task the failure is reported against: the one the drone was working, else the first
  // task its loss strands.
  const failedTask = revertTasks.find(t => t.id === failedDrone.currentTaskId) ?? revertTasks[0]
  if (!failedTask) return state

  const revertIds = new Set(revertTasks.map(t => t.id))
  const releaseSet = new Set(
    revertTasks.flatMap(t => t.assignedAssetIds).filter(id => id !== failedDrone.id)
  )
  const elapsed = state.elapsed

  const updatedAssets = state.assets.map(a => {
    if (a.id === failedDrone.id) {
      return { ...a, status: 'failed' as const, failedAt: elapsed, currentMissionId: null, currentTaskId: null }
    }
    if (releaseSet.has(a.id)) {
      const slot = loiterSlot(mission, a.id)
      const tt = travelTime(a.position, slot, ASSET_SPEED[a.type])
      return { ...a, currentTaskId: null, travelFrom: { ...a.position }, targetPosition: slot,
        travelStartElapsed: elapsed, travelEndElapsed: elapsed + tt, availableAt: elapsed + tt }
    }
    return a
  })

  const updatedMissions = state.missions.map(m => m.id === mission.id ? {
    ...m,
    droneFailuresFired: m.droneFailuresFired + 1,
    failedDroneId: failedDrone.id,
    failureRecoveryPending: true,
    recoveryReason: 'drone_failure' as const,
    recoveryOpenedAtMs: Math.round(elapsed * 1000),
    tasks: m.tasks.map(t => revertIds.has(t.id)
      ? { ...t, status: 'pending' as const, assignedAssetIds: [], startTime: null, completionTime: null }
      : t),
    pendingRecoveryOptions: buildRecoveryOptions(m, failedTask, failedDrone.id, updatedAssets, elapsed),
  } : m)

  let s: GameState = { ...state, assets: updatedAssets, missions: updatedMissions }
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
  const recM = s.missions.find(m => m.id === mission.id)!
  s = logEvent(s, recoveryOpenedPayload(recM, s.assets, s.missions, 'drone_failure', failedDrone.id,
    recM.tasks.filter(t => revertIds.has(t.id)), elapsed, state.sessionDuration))
  return s
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

  // Override quality (RQ4): the committed plan's projected finish, directly comparable with the
  // agent's own estimate. `unassignedTaskIds` is the operator-visible failure mode that matters —
  // a task committed with no drones can never complete.
  const assignedTaskIds = new Set(assignments.map(a => a.taskId))
  const droneUseCount = new Map<string, number>()
  for (const a of assignments) for (const id of a.assetIds) droneUseCount.set(id, (droneUseCount.get(id) ?? 0) + 1)

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
    agentProjectedCompletion: pending.expectedCompletionTime,
    finalProjectedCompletion: assignments.length > 0
      ? Math.max(...assignments.map(a => a.startTime + a.baseTime))
      : 0,
    plannedTasks: assignments.map(a => ({
      taskId: a.taskId,
      taskType: mission.tasks.find(t => t.id === a.taskId)!.type,
      assetIds: a.assetIds,
      startTime: a.startTime,
      baseTime: a.baseTime,
      useSubstitute: a.useSubstitute,
    })),
    unassignedTaskIds: mission.tasks
      .filter(t => t.status !== 'completed' && t.status !== 'failed' && !assignedTaskIds.has(t.id))
      .map(t => t.id),
    substituteTaskIds: assignments.filter(a => a.useSubstitute).map(a => a.taskId),
    chainedDroneIds: [...droneUseCount.entries()].filter(([, n]) => n > 1).map(([id]) => id),
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
      let sessionStartMs = state.sessionStartMs ?? action.nowMs
      // Absorb stalls. `elapsed` is derived from the wall clock, but the tick loop is driven by
      // requestAnimationFrame, which the browser SUSPENDS whenever the primary window is hidden
      // or minimised. The clock kept running regardless, so the first frame after the window came
      // back applied the entire gap in a single tick: drones teleported across the map, tasks
      // completed and penalty accrued with the operator seeing none of it (measured: elapsed
      // jumped 1s → 4m34s in one frame, taking a just-deployed mission to complete). Capping the
      // per-tick advance and pushing the session origin forward turns that into a pause instead —
      // the session still runs for its full simulated duration.
      // The cap sits above every deliberate step size used by the headless harnesses
      // (sim/pilot-run 250ms, sim/engine 500ms, scripts/test-chain-after-suggest 1000ms) so they
      // are unaffected.
      const lastTickMs = state.lastTickMs ?? action.nowMs
      const gapMs = action.nowMs - lastTickMs
      if (gapMs > MAX_TICK_GAP_MS) sessionStartMs += gapMs - MAX_TICK_GAP_MS

      const rawElapsed = (action.nowMs - sessionStartMs) / 1000
      const elapsed = state.config.testingMode ? rawElapsed : Math.min(state.sessionDuration, rawElapsed)
      const isGreedy = state.config.tacticalMode === 'greedy'

      let s: GameState = { ...state, elapsed, sessionStartMs, lastTickMs: action.nowMs }

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
          fixLockouts: isFixLockouts(cfg),
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
          failureRatePerDroneSecond: FAILURE_RATE_PER_DRONE_SECOND,
          conservativeTopUp: CONSERVATIVE_TOP_UP,
          conservativeRedundancyBuffer: CONSERVATIVE_REDUNDANCY_BUFFER,
          snapshotIntervalSec: STATE_SNAPSHOT_INTERVAL,
          trustProbeIntervalSec: TRUST_PROBE_INTERVAL,
          // Provenance: which build and what screen produced this data. Guarded because the
          // reducer also runs headless under node in sim/ (no window).
          appVersion: APP_VERSION,
          userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : 'headless',
          viewport: typeof window !== 'undefined'
            ? { width: window.innerWidth, height: window.innerHeight, devicePixelRatio: window.devicePixelRatio }
            : null,
        })
      }

      // 1. Spawn missions whose arrivalTime has passed (suppressed in testing mode)
      const toSpawn = state.config.testingMode ? [] : s.pendingBlueprints.filter(bp => bp.arrivalTime <= elapsed)
      if (toSpawn.length > 0) {
        const newMissions: Mission[] = toSpawn.map(spawnMission)
        s = { ...s, pendingBlueprints: s.pendingBlueprints.filter(bp => bp.arrivalTime > elapsed) }
        for (const m of newMissions) {
          s = { ...s, missions: [...s.missions, m] }
          s = logEvent(s, missionArrivedPayload(m, state.sessionDuration))
        }
      }

      // 1b. Drone failure check (suppressed in testing mode)
      // study-v1.3: every deployed drone independently rolls a failure each tick with probability
      // FAILURE_RATE_PER_DRONE_SECOND × dt — uniform per drone per second regardless of type or
      // mission, so total failures scale purely with actual drone-seconds deployed (utilisation),
      // not with mission count. Replaces the old per-mission precomputed schedule, whose RNG seed
      // (`mission.id.charCodeAt(1)`) barely varied across a session's mission ids and reliably
      // picked a low-index (Blue) drone — see docs/STUDY_BUILD.md.
      // At most one failure fires per tick (dt is always small — capped rAF frames, or the fixed
      // 0.25–1s steps the headless harnesses use — so a genuine multi-roll tick is effectively
      // impossible at this rate; the cap is just a safety net matching prior behaviour).
      if (!state.config.testingMode) {
        const dt = Math.max(0, elapsed - state.elapsed)
        if (dt > 0 && FAILURE_RATE_PER_DRONE_SECOND > 0) {
          const missionById = new Map(s.missions.map(m => [m.id, m]))
          const eligibleDrones = s.assets.filter(a => {
            if (a.status !== 'deployed' || !a.currentMissionId) return false
            const m = missionById.get(a.currentMissionId)
            return m !== undefined && m.status === 'active' && !m.failureRecoveryPending
          })

          const pFail = FAILURE_RATE_PER_DRONE_SECOND * dt
          const tickSalt = Math.floor(elapsed * 1000) >>> 0
          const failedDrone = eligibleDrones.find(a => {
            const rollRng = new SeededRNG((s.config.seed ^ hashId(a.id) ^ tickSalt ^ 0xF411) >>> 0)
            return rollRng.next() < pFail
          })

          if (failedDrone) {
          const mission = missionById.get(failedDrone.currentMissionId!)!
          const failedTask = mission.tasks.find(t => t.id === failedDrone.currentTaskId) ?? null

          // Mark drone as failed; schedule replacement arrival at hub in 30–45 s
          const replaceRng = new SeededRNG((s.config.seed ^ hashId(failedDrone.id) ^ 0x4E3B ^ mission.droneFailuresFired) >>> 0)
          const replacementDelay = 30 + replaceRng.randFloat(0, 15)

          if (failedTask === null) {
            // Drone was still loitering — never dispatched to a task (e.g. an Aggressive/
            // Conservative buffer spare the operator hadn't used, or the whole team pre-tactical-
            // confirm). Nothing to recover: it's simply one fewer drone in the committed pool.
            const updatedAssets = s.assets.map(a => a.id === failedDrone.id
              ? { ...a, status: 'failed' as const, failedAt: elapsed, currentMissionId: null, currentTaskId: null, replacementAt: elapsed + replacementDelay }
              : a)
            s = {
              ...s,
              assets: updatedAssets,
              missions: s.missions.map(m => m.id === mission.id
                ? { ...m, droneFailuresFired: m.droneFailuresFired + 1, failedDroneId: failedDrone.id }
                : m),
            }
            s = logEvent(s, {
              type: 'drone_failure',
              missionId: mission.id,
              missionCategory: mission.category,
              droneId: failedDrone.id,
              droneType: failedDrone.type,
              taskId: null,
              taskType: null,
              timeRemainingInSession: Math.max(0, state.sessionDuration - elapsed),
            })
          } else {
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
              // Use the live interpolated position, not the stale snapshot field — a released
              // drone may still be mid-flight toward the task (not just already arrived), now
              // that failures can hit a task before every assigned drone has landed on it.
              const pos = interpolateAssetPosition(a, elapsed)
              const slot = loiterSlot(mission, a.id)
              const tt = travelTime(pos, slot, ASSET_SPEED[a.type])
              return { ...a, position: pos, currentTaskId: null, travelFrom: { ...pos }, targetPosition: slot,
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
          // A graceful exit needs no operator action, so only the non-graceful branch opens recovery.
          if (!isGracefulExit) {
            const recM = s.missions.find(m => m.id === mission.id)!
            const recTask = recM.tasks.find(t => t.id === failedTask.id)
            s = logEvent(s, recoveryOpenedPayload(recM, s.assets, s.missions, 'drone_failure',
              failedDrone.id, recTask ? [recTask] : [], elapsed, state.sessionDuration))
            s = { ...s, missions: s.missions.map(m => m.id === mission.id
              ? { ...m, recoveryReason: 'drone_failure' as const, recoveryOpenedAtMs: Math.round(elapsed * 1000) }
              : m) }
          }
          }
          }
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
              missionCategory: newM.category,
              taskId: newT.id,
              taskType: newT.type,
              assetsUsed: newT.assignedAssetIds,
              // The TASK's own completion time — this is what scoring charges against. Logging
              // `elapsed` here instead made the penalty impossible to reconstruct from the log
              // whenever ticks were coarse (they diverge by the tick gap).
              completionTime: newT.completionTime ?? elapsed,
              detectedAtElapsed: elapsed,
              startTime: newT.startTime,
              travelTime: newT.travelTime,
              baseTime: newT.baseTime,
              useSubstitute: newT.useSubstitute,
              rewardEarned: TASK_WEIGHT[newT.type],
              waitFromMissionArrival: Math.max(0, (newT.completionTime ?? elapsed) - newM.arrivalTime),
            })
          }
          // The sections-by-colour safety net in step 2 is the only place a task fails in this pass:
          // a required drone type is no longer present for its section window, which today only
          // happens after a drone failure. It used to fail the task silently — the most common
          // failure mode in a session produced no event at all.
          if (oldT && newT && oldT.status !== 'failed' && newT.status === 'failed') {
            s = logEvent(s, taskFailedPayload(newM, oldT, 'drone_failure', elapsed))
          }
        }
      }

      // 3a. Mission completion events (check before reassigning s.missions to updatedMissions)
      for (let mi = 0; mi < updatedMissions.length; mi++) {
        const oldM = s.missions[mi]
        const newM = updatedMissions[mi]
        if (oldM && newM && oldM.status !== 'completed' && newM.status === 'completed') {
          // A mission reaches 'completed' once every task is completed OR failed, so this event
          // also fires for missions that finished with nothing done. Record which shape it was.
          const nDone = newM.tasks.filter(t => t.status === 'completed').length
          s = logEvent(s, {
            type: 'mission_completed',
            missionId: newM.id,
            missionCategory: newM.category,
            completionTime: elapsed,
            outcome: nDone === 0 ? 'none_completed' : nDone === newM.tasks.length ? 'all_completed' : 'partial',
            tasksCompleted: newM.tasks.filter(t => t.status === 'completed').length,
            tasksFailed: newM.tasks.filter(t => t.status === 'failed').length,
            rewardEarned: newM.tasks.reduce((sum, t) => sum + (t.status === 'completed' ? TASK_WEIGHT[t.type] : 0), 0),
            penaltyAccrued: computePenaltyAccrued([newM], elapsed),
            arrivalTime: newM.arrivalTime,
            allocationTime: newM.allocationTime,
            timeToAllocate: newM.allocationTime !== null ? newM.allocationTime - newM.arrivalTime : null,
            durationFromAllocation: newM.allocationTime !== null ? elapsed - newM.allocationTime : null,
            maxReward: newM.tasks.reduce((sum, t) => sum + TASK_WEIGHT[t.type], 0),
            chosenStrategyName: newM.chosenStrategyName,
            agentInteraction: newM.agentInteraction,
            hadTacticalError: newM.tacticallySuppressedTaskId !== null,
            suppressedTaskId: newM.tacticallySuppressedTaskId,
            droneFailureCount: newM.droneFailuresFired,
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
        s = logEvent(s, taskFailedPayload(mission, suppTask, 'tactical_lockout', elapsed))
      }

      // 3c. Live scheduling-deadlock detection (runs on the ACTUAL running mission, not at
      // build time). A cross-drone chain cycle — Fast chained task1→task2 while Lifter is
      // chained task2→task1 — leaves each task waiting on a drone that is itself waiting on
      // the other task, so no drone can ever make progress. We deliberately let the operator/
      // agent commit such a plan and let the drones fly out; only once the cycle's drones have
      // physically ARRIVED and are sitting idle (deadlocked — not merely idle for any reason,
      // and not while one is still en route or actively executing) do we act.
      //
      // config.fixLockouts (default ON — see isFixLockouts) chooses what "act" means:
      //  • true  — the agent repairs it silently: reroute the conflicting drone chains onto one
      //            consistent order so the graph is acyclic, reschedule and redirect. Every task
      //            still completes and nothing fails.
      //  • false — surface it to the operator as "help needed" (same class as a drone failure): free
      //            the stuck drones, revert the deadlocked tasks to pending, and flag the mission for
      //            recovery so the operator re-plans a good allocation. Greedy replan is paused for the
      //            mission (see applyGreedyReplan) so the operator — not the agent — resolves it.
      //            Not what the study runs (?fixLockouts=0 opts in), so no tutorial step covers it.
      const fixLockouts = isFixLockouts(state.config)
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
          // Help needed: surface it like a drone failure. Free the stuck cycle drones (currentTaskId
          // cleared so they can be reassigned) but LEAVE THEM PARKED AT THEIR CURRENT POSITION — the
          // task waypoint they deadlocked on — rather than flying them back to a loiter slot. This
          // makes the lockout legible: the operator can see which drones physically reached which
          // task (so a task can be "2/2 Red present, 0/2 Green present"), which is the crux of the
          // deadlock. Revert the deadlocked tasks to pending BUT keep their assignedAssetIds so the
          // recovery planner shows the current (deadlocked) plan rather than a blank slate.
          //
          // Crucially, the cycle drones are usually SHARED (chained) with other not-yet-finished
          // tasks in the same mission. Freeing them orphans those tasks — a task left "traveling"
          // whose drones are no longer heading to it can never complete, and the recovery Suggest
          // couldn't fill it (its drones looked busy). So also revert EVERY non-completed,
          // non-executing task that shares a freed drone, and park all of their drones too. Tasks
          // actively executing (drones on-site working) are left untouched.
          const cycleDroneSet = new Set(cycleDrones)
          const affectedTaskSet = new Set<string>(cyc)
          for (const t of mission.tasks) {
            if (t.status === 'completed' || t.status === 'failed' || t.status === 'executing') continue
            if (t.assignedAssetIds.some(id => cycleDroneSet.has(id))) affectedTaskSet.add(t.id)
          }
          // Park every drone belonging to an affected task (except any actively executing a task we
          // are NOT reverting), so the whole broken chain is freed for a clean re-plan.
          const freedDroneSet = new Set<string>()
          for (const t of mission.tasks) {
            if (!affectedTaskSet.has(t.id)) continue
            for (const id of t.assignedAssetIds) freedDroneSet.add(id)
          }
          s = {
            ...s,
            assets: s.assets.map(a => {
              if (!freedDroneSet.has(a.id) || a.status !== 'deployed') return a
              const cur = mission.tasks.find(tt => tt.id === a.currentTaskId)
              if (cur && cur.status === 'executing' && !affectedTaskSet.has(cur.id)) return a  // leave active workers
              const pos = interpolateAssetPosition(a, elapsed)
              return {
                ...a, currentTaskId: null, position: pos, travelFrom: { ...pos }, targetPosition: { ...pos },
                travelStartElapsed: elapsed, travelEndElapsed: elapsed, availableAt: elapsed,
              }
            }),
            missions: s.missions.map(m => m.id === mission.id ? {
              ...m,
              failureRecoveryPending: true,
              recoveryReason: 'lockout' as const,
              failedDroneId: null,
              pendingRecoveryOptions: [],
              // Keep the existing (cyclic) droneSequences intact — the recovery planner seeds its
              // chain order from them so it shows the ACTUAL deadlocked plan, detects the cycle, and
              // blocks Deploy until the operator breaks it (reorder or Suggest). They're inert while
              // the mission is recovery-pending (detector + greedy replan both skip it) and get
              // overridden by the operator's revised plan on CONFIRM_FAILURE_RECOVERY.
              tasks: m.tasks.map(t => affectedTaskSet.has(t.id)
                ? { ...t, status: 'pending' as const, startTime: null, completionTime: null, allocatedAt: null }
                : t),
            } : m),
          }
          s = logEvent(s, {
            type: 'lockout_detected', missionId: mission.id, missionCategory: mission.category,
            taskIds: cyc, droneIds: cycleDrones, resolution: 'help_needed',
          })
          const lockM = s.missions.find(m => m.id === mission.id)!
          s = logEvent(s, recoveryOpenedPayload(lockM, s.assets, s.missions, 'lockout', null,
            lockM.tasks.filter(t => affectedTaskSet.has(t.id)), elapsed, state.sessionDuration))
          s = { ...s, missions: s.missions.map(m => m.id === mission.id
            ? { ...m, recoveryOpenedAtMs: Math.round(elapsed * 1000) } : m) }
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

      // 5b. Periodic full-state dump. Emitted on a fixed elapsed-time grid (not wall clock) so it
      // stays deterministic and so a throttled/backgrounded tab can't silently skip one. Runs after
      // the score update so the snapshot and its envelope agree.
      if (elapsed >= s.nextSnapshotAt) {
        s = logEvent(s, buildStateSnapshot(s, elapsed))
        // Advance past any grid points a long tick jumped over, so we don't emit a burst.
        const missed = Math.floor((elapsed - s.nextSnapshotAt) / STATE_SNAPSHOT_INTERVAL) + 1
        s = { ...s, nextSnapshotAt: s.nextSnapshotAt + missed * STATE_SNAPSHOT_INTERVAL }
      }

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
      const cardRevealDelaysMs = drawCardRevealDelays(state.config.seed, mission.id, strategies.length)
      let s: GameState = {
        ...state,
        strategicModal: {
          missionId: action.missionId,
          strategies,
          selectedStrategyIndex: null,
          manualAllocation: { Blue: 0, Red: 0, Green: 0 },
          openedAtMs,
          cardRevealDelaysMs,
        },
      }
      s = logEvent(s, {
        type: 'strategic_modal_opened',
        missionId: mission.id,
        missionCategory: mission.category,
        timeRemainingInSession: Math.max(0, state.sessionDuration - state.elapsed),
        activeMissions: state.missions.filter(m => m.status === 'active').length,
        currentPenaltyAccrued: state.penaltyAccrued,
        strategiesPresented: strategies.map((st, i) => ({
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
          revealDelayMs: cardRevealDelaysMs[i] ?? 0,
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
        // Commit the WHOLE composition (assigned drones + any redundant spares) to the mission,
        // not just the subset greedyAssign actually put on a task — greedyAssign reuses a drone
        // across tasks as it frees up, so a composition's "spare per type" buffer (e.g. Aggressive's
        // stated failure buffer) can otherwise never be assigned to anything and silently vanish
        // from the pool: never launched, never shown in the tactical planner, contradicting what
        // the strategy card told the operator it was committing. Every committed drone flies to
        // the zone edge and waits, same as the manual branch below already does correctly.
        const full: string[] = []
        for (const type of ['Blue', 'Red', 'Green'] as AssetType[]) {
          full.push(...available.filter(a => a.type === type).slice(0, composition[type]).map(a => a.id))
        }
        dronePool = [...new Set([...dronePool, ...full])]
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
        // Forced wait vs deliberation: an agent-card choice could not Deploy until the last card
        // resolved; a manual allocation was never gated. deliberationMs = latencyMs − deployEnabledAtMs.
        cardRevealDelaysMs: modal.cardRevealDelaysMs ?? [],
        deployEnabledAtMs: action.source === 'agent' ? Math.max(0, ...(modal.cardRevealDelaysMs ?? [])) : 0,
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
        // The ε_T draw for this mission, logged whether or not it ever manifests as a failed task.
        hasTacticalError,
        suppressedTaskId,
        dronePool,
        agentProjectedCompletion: expectedCompletionTime,
        unassignedTaskIds: mission.tasks.filter(t => (taskAssignmentMap[t.id] ?? []).length === 0).map(t => t.id),
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
      if (!mission) return state
      // Recovery-planner Suggest fires while the mission is ACTIVE and recovery-pending, not
      // tactical-pending, so the pending-allocation guard only applies to the initial planner.
      const isRecovery = !!action.recoveryMode
      if (!isRecovery && (!mission.tacticalPending || !mission.pendingAllocation)) return state
      if (isRecovery && !mission.failureRecoveryPending) return state
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
        recoveryMode: isRecovery,
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
      const cardRevealDelaysMs = drawCardRevealDelays(state.config.seed, mission.id, strategies.length)
      let s: GameState = {
        ...state,
        missions: state.missions.map(m => m.id === action.missionId ? { ...m, tacticalPending: false, pendingAllocation: null } : m),
        strategicModal: { missionId: action.missionId, strategies, selectedStrategyIndex: null, manualAllocation: null, openedAtMs, cardRevealDelaysMs },
      }
      s = logEvent(s, {
        type: 'strategic_modal_opened',
        missionId: mission.id,
        missionCategory: mission.category,
        timeRemainingInSession: Math.max(0, state.sessionDuration - state.elapsed),
        activeMissions: state.missions.filter(m => m.status === 'active').length,
        currentPenaltyAccrued: state.penaltyAccrued,
        strategiesPresented: strategies.map((st, i) => ({
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
          revealDelayMs: cardRevealDelaysMs[i] ?? 0,
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

      // NOTE: the failure_recovery event is logged only once the redistribution has actually been
      // applied (below). Logging it up front recorded a "repaired" event for every click that the
      // composition guard then rejected, leaving the mission still asking for help while the log
      // claimed it had been fixed — and an operator can click a rejected option repeatedly.
      let s = state

      if (action.recoveryType === 'redistribute' && opt.redistributeToAssetId) {
        // Redirect an existing drone to the failed task
        const task = mission.tasks.find(t => t.id === opt.taskId)
        const asset = s.assets.find(a => a.id === opt.redistributeToAssetId)
        if (!task || !asset) return state
        // Guard: only dispatch if adding this drone satisfies primary or substitute composition
        const totalIds = [...task.assignedAssetIds.filter(id => id !== opt.redistributeToAssetId), opt.redistributeToAssetId!]
        const assetByIdR = new Map(s.assets.map(a => [a.id, a]))
        if (taskMeetsComposition(task, totalIds, assetByIdR)) {
          s = logEvent(s, {
            type: 'failure_recovery',
            missionId: mission.id,
            missionCategory: mission.category,
            recoveryType: action.recoveryType,
            wasAgentSuggested: true,
            timeRemainingInSession: Math.max(0, state.sessionDuration - state.elapsed),
            recoveryReason: mission.recoveryReason ?? null,
            latencyMs: mission.recoveryOpenedAtMs != null ? Math.round(state.elapsed * 1000) - mission.recoveryOpenedAtMs : 0,
            repairedTaskIds: opt.taskId ? [opt.taskId] : [],
            repairedAssignments: [{ taskId: task.id, assetIds: totalIds }],
            tasksStillUnassigned: mission.tasks
              .filter(t => t.status === 'pending' && t.id !== opt.taskId && t.assignedAssetIds.length === 0)
              .map(t => t.id),
          })
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
        recoveryReason: mission.recoveryReason ?? null,
        latencyMs: mission.recoveryOpenedAtMs != null ? Math.round(state.elapsed * 1000) - mission.recoveryOpenedAtMs : 0,
        repairedTaskIds: [task.id],
        repairedAssignments: [{ taskId: task.id, assetIds: totalIdsM }],
        tasksStillUnassigned: mission.tasks
          .filter(t => t.status === 'pending' && t.id !== task.id && t.assignedAssetIds.length === 0)
          .map(t => t.id),
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
          // Replace outright: a recovered pending task is rebuilt from the operator's revised plan,
          // so any drone the operator dropped must not linger. (Harmless for the drone-failure flow
          // where the task was blanked, but the lockout flow now keeps the pre-deadlock ids that the
          // operator may have removed — merging would silently re-add them.)
          assignedAssetIds: [...asgn.assetIds],
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
        // True when the operator pulled in the agent's plan via "Suggest" in the recovery planner
        // (they may still have edited it afterwards — this only records that the agent was consulted).
        wasAgentSuggested: action.wasAgentSuggested ?? false,
        timeRemainingInSession: Math.max(0, state.sessionDuration - now),
        recoveryReason: mission.recoveryReason ?? null,
        latencyMs: mission.recoveryOpenedAtMs != null ? Math.round(now * 1000) - mission.recoveryOpenedAtMs : 0,
        repairedTaskIds: Object.keys(recoveryTaskAssignments),
        repairedAssignments: Object.entries(recoveryTaskAssignments).map(([taskId, assetIds]) => ({ taskId, assetIds })),
        // Pending tasks the operator's fix still leaves with nobody on them — these can never complete,
        // so this is the direct measure of an incomplete recovery.
        tasksStillUnassigned: mission.tasks
          .filter(t => t.status === 'pending' && (recoveryTaskAssignments[t.id] ?? []).length === 0)
          .map(t => t.id),
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

      // Build residual mission if there is anything left to do.
      // `carryOver` records parent-task → residual-task so the log can say where each piece of work
      // WENT rather than claiming it was lost.
      let residualMission: Mission | null = null
      const carryOver: Array<{ task: Task; residualTaskId: string; execSoFar: number; remainingBase: number }> = []
      if (incompleteTasks.length > 0) {
        const residualTasks: Task[] = incompleteTasks.map((t, i) => {
          const execSoFar = t.status === 'executing' && t.startTime !== null
            ? Math.max(0, elapsed - t.startTime)
            : 0
          const remainingBase = Math.max(5, t.baseTime - execSoFar)
          carryOver.push({ task: t, residualTaskId: `${mission.id}-R-T${i + 1}`, execSoFar, remainingBase })
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

        // No separate failure schedule needed — a residual mission is 'active'/'queued' like any
        // other, so the ambient per-tick hazard in TICK step 1b covers it automatically once it's
        // allocated and has deployed drones.
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

      // Abandoning does NOT destroy the outstanding work: every incomplete task is re-queued into the
      // residual and is very often completed later. So each carried task gets a `task_requeued`
      // naming its residual id, and only a task with no residual copy is logged as a real failure.
      // (This loop used to fire task_failed for the carried tasks — the log then reported an
      // abandonment as mass task loss while the same tasks were finishing minutes later.)
      const carriedIds = new Set(carryOver.map(c => c.task.id))
      for (const c of carryOver) {
        s = logEvent(s, {
          type: 'task_requeued' as const,
          missionId: mission.id,
          missionCategory: mission.category,
          taskId: c.task.id,
          taskType: c.task.type,
          residualMissionId: `${mission.id}-R`,
          residualTaskId: c.residualTaskId,
          statusBefore: c.task.status,
          assignedAssetIds: [...c.task.assignedAssetIds],
          rewardDeferred: TASK_WEIGHT[c.task.type],
          executionProgress: Math.round(c.execSoFar * 10) / 10,
          remainingBaseTime: c.remainingBase,
          waitFromMissionArrival: Math.max(0, elapsed - mission.arrivalTime),
        })
      }
      // Defensive: if residual-building rules ever stop carrying a task, it really is lost — log it.
      const lostTasks = incompleteTasks.filter(t => !carriedIds.has(t.id))
      for (const t of lostTasks) {
        s = logEvent(s, taskFailedPayload(mission, t, 'mission_abandoned', elapsed))
      }

      s = logEvent(s, {
        type: 'mission_abandoned' as const,
        missionId: mission.id,
        missionCategory: mission.category,
        completedTaskCount: mission.tasks.filter(t => t.status === 'completed').length,
        remainingTaskCount: incompleteTasks.length,
        residualMissionId: residualMission ? residualMission.id : null,
        carriedTaskIds: carryOver.map(c => c.task.id),
        rewardCarriedOver: carryOver.reduce((sum, c) => sum + TASK_WEIGHT[c.task.type], 0),
        rewardLost: lostTasks.reduce((sum, t) => sum + TASK_WEIGHT[t.type], 0),
      })

      // Announce the residual like any other arrival. Without this its later strategic_choice /
      // tactical_confirmed / task_completed events referred to a mission that never appeared in the
      // log, and task/reward denominators built from mission_arrived silently omitted it.
      if (residualMission) {
        s = logEvent(s, missionArrivedPayload(residualMission, s.sessionDuration, mission.id))
      }

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

      const recallMission = s.missions.find(m => m.id === missionId)
      if (recallMission && currentTask) {
        s = logEvent(s, taskFailedPayload(recallMission, currentTask, 'asset_recalled', elapsed))
      }

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
        lastTickMs: null,
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
        nextSnapshotAt: 0,
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
      s = logEvent(s, missionArrivedPayload(mission, state.sessionDuration))
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

    // ── TUTORIAL_FORCE_FAILURE ───────────────────────────────────────────
    // First act of the failure demo: a fault the operator CAN fix, so the recovery lesson
    // ("drag a drone onto the uncovered task, then Reassign") is actually performable. Picks a
    // drone whose loss leaves every remaining task coverable by the rest of the subswarm —
    // failing the team's only Red would strand a supply drop and leave nothing but Abandon.
    case 'TUTORIAL_FORCE_FAILURE': {
      const mission = state.missions.find(m => m.status === 'active' && !m.failureRecoveryPending)
      if (!mission) return state
      const working = state.assets.filter(
        a => a.currentMissionId === mission.id && a.status === 'deployed' && a.currentTaskId
      )
      if (working.length === 0) return state
      const pool = onMissionDrones(mission, state.assets)
      const recoverable = working.filter(d => {
        const survivors = pool.filter(a => a.id !== d.id)
        return unfinishedTasks(mission).every(t => taskCoverableBy(t, survivors))
      })
      // Prefer a drone that is actually working (the on-screen story is clearer). If no failure
      // is recoverable at all, still fire one — the demo has to happen for the tutorial to move
      // on, and the recovery step's unsatisfiableWhen gate offers Next when it can't be fixed.
      const executing = (list: Asset[]) => list.find(
        d => mission.tasks.find(t => t.id === d.currentTaskId)?.status === 'executing'
      )
      const failedDrone = executing(recoverable) ?? recoverable[0] ?? executing(working) ?? working[0]
      return applyForcedDroneFailure(state, mission, failedDrone)
    }

    // ── TUTORIAL_FORCE_ABANDON_SCENARIO ─────────────────────────────────
    // Second act: a fault that genuinely cannot be recovered, so "Abandon Mission" is the only
    // way out and the abort lesson tells the truth. Recovery may only draw on the deployed
    // subswarm, so we need a drone whose loss leaves some remaining task short of a type no
    // survivor can supply (typically the training team's single Red on a supply drop).
    case 'TUTORIAL_FORCE_ABANDON_SCENARIO': {
      const mission = state.missions.find(m => m.status === 'active' && !m.failureRecoveryPending)
      if (!mission) return state

      const pool = onMissionDrones(mission, state.assets)
      const remaining = unfinishedTasks(mission)
      // Red first: the training team carries exactly one, so it reads as the obvious dead end.
      const candidates = [...pool].sort((a, b) => (a.type === 'Red' ? 0 : 1) - (b.type === 'Red' ? 0 : 1))
      let failedDrone: Asset | undefined
      let strandedTasks: Task[] = []
      for (const d of candidates) {
        const survivors = pool.filter(a => a.id !== d.id)
        const stranded = remaining.filter(t => !taskCoverableBy(t, survivors))
        if (stranded.length === 0) continue
        failedDrone = d
        strandedTasks = stranded
        break
      }
      // Nothing left that failing one drone can strand (e.g. only paired-Blue recce tasks remain).
      // Rather than stage a "you cannot recover" lesson the operator could trivially recover from,
      // leave the mission alone — abort-select/abort-do detect the missing failure and offer Next.
      if (!failedDrone) return state

      return applyForcedDroneFailure(state, mission, failedDrone, strandedTasks.map(t => t.id))
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
      return applyForcedDroneFailure(state, mission, candidateDrones[0])
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

  // Fail all incomplete tasks.
  // An ABANDONED mission is left exactly as it was: it already reached a terminal state the operator
  // chose, its leftovers live on in the residual mission, and its tasks are excluded from the sweep
  // so they are neither re-failed nor re-counted. Overwriting its status here also made the final
  // state contradict the mission_abandoned event (abandoned missions came out as 'failed'/'completed').
  const failedMissions = s.missions.map(m => {
    if (m.status === 'completed' || m.status === 'abandoned') return m
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

  // Log every task the session end just failed. Without this the stream ends with tasks that
  // simply never resolved, and "failed at the buzzer" is indistinguishable from "never logged".
  // Abandoned missions are skipped: their outstanding tasks were re-queued into a residual mission
  // and already logged as task_requeued, so failing them here would count one piece of work twice.
  let sEnd: GameState = { ...s, missions: failedMissions, score, penaltyAccrued }
  for (let mi = 0; mi < s.missions.length; mi++) {
    const before = s.missions[mi]
    const after = failedMissions[mi]
    if (before.status === 'abandoned') continue
    for (let ti = 0; ti < before.tasks.length; ti++) {
      if (before.tasks[ti].status !== 'failed' && after.tasks[ti].status === 'failed') {
        // `before.tasks[ti]` so statusBefore/assignedAssetIds reflect what it was doing at the buzzer
        sEnd = logEvent(sEnd, taskFailedPayload(before, before.tasks[ti], 'session_ended', s.elapsed))
      }
    }
  }

  // Task ledger over the WHOLE session (sEnd already holds this session's session_ended-time
  // failures), so the headline counts are in the log rather than left to be re-derived — which is
  // where "everything failed" readings came from.
  const finalEvents = sEnd.events[idx] ?? []
  const failuresByReason: Record<string, number> = {}
  let failedOnNeverAllocated = 0
  for (const e of finalEvents as Array<{ type: string; reason?: string; missionWasAllocated?: boolean }>) {
    if (e.type !== 'task_failed') continue
    const r = e.reason ?? 'unknown'
    failuresByReason[r] = (failuresByReason[r] ?? 0) + 1
    if (e.missionWasAllocated === false) failedOnNeverAllocated++
  }
  const taskOutcomes = {
    completed: finalEvents.filter((e: { type: string }) => e.type === 'task_completed').length,
    failed: finalEvents.filter((e: { type: string }) => e.type === 'task_failed').length,
    requeued: finalEvents.filter((e: { type: string }) => e.type === 'task_requeued').length,
    failuresByReason,
    failedOnNeverAllocatedMissions: failedOnNeverAllocated,
  }

  let s2 = logEvent(sEnd, {
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
    taskOutcomes,
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
