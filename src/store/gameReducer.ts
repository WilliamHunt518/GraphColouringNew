import type {
  GameState, GameEvent, Asset, Mission, Task,
  AssetType, TaskType, AssetRequirement,
  MissionCategory, TaskComp,
} from '../types'
import type { GameAction } from './actions'
import {
  HUB, ASSET_SPEED, TASK_BASE_TIME, TASK_PRIMARY, TASK_SUBSTITUTE,
  TASK_SUB_BASE_TIME, ZONE_RADIUS, generateSessionPlan, createInitialAssets, travelTime,
} from '../utils/missionGen'
import { generateStrategies } from '../utils/copilot'
import { evaluatePosture } from '../utils/metacopilot'
import { SeededRNG } from '../utils/prng'
import { debugLog } from '../utils/debugLog'
import type { StudyConfig } from '../types'

// ─── Constants ────────────────────────────────────────────────────────────

const SESSION_DURATION = 600  // seconds
const TRUST_PROBE_INTERVAL = 90  // seconds

// ─── Initial state factory ─────────────────────────────────────────────────

export function buildInitialState(config: StudyConfig): GameState {
  const blueprints = generateSessionPlan(new SeededRNG(config.seed ^ 1), config.complexity)

  const baseCategories: Record<MissionCategory, number> = { A: 0, B: 0, C: 0, D: 0, E: 0 }
  const initialForecast = { ...baseCategories }
  // Default to complexity-appropriate prior
  switch (config.complexity) {
    case 'easy':   Object.assign(initialForecast, { A: 0.50, B: 0.35, C: 0.10, D: 0.05, E: 0.00 }); break
    case 'medium': Object.assign(initialForecast, { A: 0.15, B: 0.35, C: 0.35, D: 0.12, E: 0.03 }); break
    case 'hard':   Object.assign(initialForecast, { A: 0.05, B: 0.15, C: 0.35, D: 0.30, E: 0.15 }); break
  }

  return {
    config,
    phase: 'playing',
    sessionNumber: 1,
    elapsed: 0,
    sessionStartMs: null,
    assets: createInitialAssets(),
    missions: [],
    pendingBlueprints: blueprints,
    score: 0,
    completedSessionScores: [],
    categoryForecast: initialForecast,
    metaRec: null,
    metaPostureOverride: null,
    copilotModal: null,
    trustProbeActive: false,
    nextTrustProbeAt: TRUST_PROBE_INTERVAL,
    events: [[], [], []],
  }
}

// ─── Helper: log event ────────────────────────────────────────────────────

// Distributive Omit so it works across the discriminated union
type EventPayload = GameEvent extends infer E
  ? E extends { timestamp: number; sessionNumber: number }
    ? Omit<E, 'timestamp' | 'sessionNumber'>
    : never
  : never

function logEvent(state: GameState, event: EventPayload): GameState {
  const full: GameEvent = {
    ...event,
    timestamp: Math.round(state.elapsed * 1000),
    sessionNumber: state.sessionNumber,
  } as GameEvent
  const idx = state.sessionNumber - 1
  const updated = [...state.events]
  updated[idx] = [...updated[idx], full]
  return { ...state, events: updated }
}

// ─── Helper: current reserve ──────────────────────────────────────────────

export function reserveCount(assets: Asset[]): AssetRequirement {
  return {
    Blue: assets.filter(a => a.type === 'Blue' && a.status === 'available').length,
    Red: assets.filter(a => a.type === 'Red' && a.status === 'available').length,
    Green: assets.filter(a => a.type === 'Green' && a.status === 'available').length,
  }
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
 *
 * Each committed asset is tracked as a virtual token with a `freeAt` time and
 * `position`.  Tasks are processed T5→T1 (most-constrained first).  For each
 * task the scheduler picks the n tokens with the earliest freeAt, computes the
 * actual startTime (when all required assets arrive), then advances each token's
 * freeAt to the task's completionTime and its position to the task's waypoint.
 *
 * This means a single Green token can be scheduled for T5 then T4 sequentially —
 * satisfying both even though only 1 Green was committed.
 *
 * Tasks that cannot be covered (not enough tokens) are skipped rather than
 * causing a complete failure, so a partial commitment still executes whatever
 * tasks it can.
 *
 * When `plan` is provided (from a Co-Pilot strategy), the exact per-task
 * compositions are used.  Without a plan (manual), the scheduler tries the
 * primary composition first, then the substitute.
 */
function greedyAssign(
  tasks: Task[],
  availableAssets: Asset[],
  committed: AssetRequirement,
  now: number,
  plan?: Record<string, TaskComp>,
  priorityTaskIds: string[] = [],
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

  // Priority tasks first (user-specified order), then remaining T5→T1
  const priorityTasks = priorityTaskIds
    .map(id => tasks.find(t => t.id === id))
    .filter((t): t is Task => t !== undefined)
  const remaining = tasks
    .filter(t => !priorityTaskIds.includes(t.id))
    .sort((a, b) => b.type - a.type)
  const sorted = [...priorityTasks, ...remaining]
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
    const blueV  = pickEarliest('Blue',  reqBlue)
    const redV   = pickEarliest('Red',   reqRed)
    const greenV = pickEarliest('Green', reqGreen)

    if (blueV.length < reqBlue || redV.length < reqRed || greenV.length < reqGreen) {
      debugLog('greedyAssign: skip task (pool exhausted)', { taskId: task.id, reqBlue, reqRed, reqGreen })
      continue
    }

    const picked = [...blueV, ...redV, ...greenV]

    // ── Compute startTime: when the last required asset arrives ─────────────
    const startTime = Math.max(
      now,
      ...picked.map(v => v.freeAt + travelTime(v.pos, task.waypoint, ASSET_SPEED[v.type])),
    )
    const completionTime = startTime + baseTime

    // ── Advance virtual tokens (sequential reuse) ───────────────────────────
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
    copilotInteraction: 'none',
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

const TASK_WEIGHT: Record<TaskType, number> = { 1: 1, 2: 2, 3: 3, 4: 4, 5: 5 }

function computeScore(missions: Mission[]): number {
  let score = 0
  for (const m of missions) {
    for (const t of m.tasks) {
      if (t.status === 'completed') score += TASK_WEIGHT[t.type]
    }
  }
  return score
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

function computeCpFollowRate(events: GameEvent[]): number {
  const shown = events.filter(e => e.type === 'copilot_shown').length
  const followed = events.filter(e => e.type === 'allocation_applied' && (e as any).source === 'copilot_as_proposed').length
  return shown > 0 ? followed / shown : 0
}

function computeMcpFollowRate(events: GameEvent[]): number {
  const followed = events.filter(e => e.type === 'metacopilot_followed').length
  const overridden = events.filter(e => e.type === 'metacopilot_overridden').length
  const ignored = events.filter(e => e.type === 'metacopilot_ignored').length
  const total = followed + overridden + ignored
  return total > 0 ? followed / total : 0
}

// ─── Reducer ──────────────────────────────────────────────────────────────

export function gameReducer(state: GameState, action: GameAction): GameState {
  switch (action.type) {

    // ── TICK ────────────────────────────────────────────────────────────────
    case 'TICK': {
      if (state.phase !== 'playing') return state

      // Initialise wall-clock reference on first tick
      const sessionStartMs = state.sessionStartMs ?? action.nowMs
      const elapsed = Math.min(SESSION_DURATION, (action.nowMs - sessionStartMs) / 1000)

      let s: GameState = { ...state, elapsed, sessionStartMs }

      // 1. Spawn missions whose arrivalTime has passed
      const toSpawn = s.pendingBlueprints.filter(bp => bp.arrivalTime <= elapsed)
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
          })
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
          if (oldT.status !== 'completed' && newT.status === 'completed') {
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

      // 4. Update asset availability and positions
      const updatedAssets = s.assets.map(asset => {
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
            // Look for a next task in the same mission this asset is scheduled for
            const nextTask = currentMission?.tasks.find(t =>
              t.id !== asset.currentTaskId &&
              t.assignedAssetIds.includes(asset.id) &&
              t.status !== 'completed' &&
              t.status !== 'failed',
            )

            if (nextTask) {
              // Sequential reuse: redirect directly to the next task's waypoint
              const tt = travelTime(task.waypoint, nextTask.waypoint, ASSET_SPEED[asset.type])
              debugLog('TICK: asset sequential redirect', {
                assetId: asset.id, from: asset.currentTaskId, to: nextTask.id,
                elapsed: Math.round(elapsed), tt: Math.round(tt),
              })
              return {
                ...asset,
                currentTaskId: nextTask.id,
                travelFrom: { ...task.waypoint },
                targetPosition: { ...nextTask.waypoint },
                travelStartElapsed: elapsed,
                travelEndElapsed: elapsed + tt,
                position: newPos,
              }
            }

            // No next task — return to hub
            const returnTime = travelTime(task.waypoint, HUB, ASSET_SPEED[asset.type])
            return {
              ...asset,
              status: 'returning' as const,
              currentMissionId: null,
              currentTaskId: null,
              travelFrom: { ...task.waypoint },
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

      // 5. Recalculate score
      s = { ...s, score: computeScore(s.missions) }

      // 6. Trust probe
      if (!s.trustProbeActive && elapsed >= s.nextTrustProbeAt) {
        s = { ...s, trustProbeActive: true }
      }

      // 7. Category forecast update (after spawning new missions)
      if (toSpawn.length > 0) {
        s = { ...s, categoryForecast: computeForecast(s.pendingBlueprints) }
      }

      // 8. Meta-Co-Pilot recommendation — update every 30 s or on new mission arrival
      const metaEpoch = Math.floor(elapsed / 30)
      const prevMetaEpoch = Math.floor(state.elapsed / 30)
      if (toSpawn.length > 0 || metaEpoch !== prevMetaEpoch) {
        const metaRng = new SeededRNG(state.config.seed ^ state.sessionNumber * 10000 ^ metaEpoch)
        s = {
          ...s,
          metaRec: evaluatePosture(
            reserveCount(s.assets),
            s.missions.filter(m => m.status === 'active').length,
            s.categoryForecast,
            state.config.epsilonMeta,
            metaRng,
            elapsed,
          ),
        }
      }

      // 9. Session end check
      if (elapsed >= SESSION_DURATION) {
        s = endSession(s)
      }

      return s
    }

    // ── OPEN_ALLOCATE ────────────────────────────────────────────────────
    case 'OPEN_ALLOCATE': {
      const mission = state.missions.find(m => m.id === action.missionId)
      if (!mission || mission.status !== 'queued') return state

      const reserve = reserveCount(state.assets)
      const copilotRng = new SeededRNG(state.config.seed ^ mission.id.charCodeAt(1))
      const strategies = generateStrategies(
        mission.tasks,
        reserve,
        state.config.epsilonMeta,
        copilotRng,
        state.elapsed,
      )

      let s = logEvent(state, { type: 'allocation_started', missionId: mission.id, triggeredBy: 'operator' })
      s = logEvent(s, { type: 'copilot_shown', missionId: mission.id, strategies })

      // Mark mission as having had Co-Pilot shown
      s = {
        ...s,
        missions: s.missions.map(m =>
          m.id === mission.id ? { ...m, copilotInteraction: 'shown' } : m,
        ),
        copilotModal: { missionId: mission.id, strategies, selectedIndex: null, editedAllocation: null, priorityTaskIds: [] },
      }

      return s
    }

    // ── SELECT_STRATEGY ──────────────────────────────────────────────────
    case 'SELECT_STRATEGY': {
      if (!state.copilotModal) return state
      const strat = state.copilotModal.strategies[action.strategyIndex]
      if (!strat) return state
      let s = logEvent(state, {
        type: 'copilot_strategy_selected',
        missionId: state.copilotModal.missionId,
        strategyIndex: action.strategyIndex,
        strategyName: strat.name,
      })
      s = {
        ...s,
        copilotModal: {
          ...s.copilotModal!,
          selectedIndex: action.strategyIndex,
          editedAllocation: null,
        },
      }
      return s
    }

    // ── EDIT_ALLOCATION ──────────────────────────────────────────────────
    case 'EDIT_ALLOCATION': {
      if (!state.copilotModal) return state
      return {
        ...state,
        copilotModal: { ...state.copilotModal, editedAllocation: action.allocation },
      }
    }

    // ── APPLY_ALLOCATION ─────────────────────────────────────────────────
    case 'APPLY_ALLOCATION': {
      const mission = state.missions.find(m => m.id === action.missionId)
      if (!mission || mission.status !== 'queued') return state

      const now = state.elapsed
      const available = state.assets.filter(a => a.status === 'available')
      const selectedStrat = action.selectedIndex !== null ? action.strategies[action.selectedIndex] : null
      const plan = action.source !== 'manual' ? selectedStrat?.taskComps : undefined
      const priorityTaskIds = state.copilotModal?.priorityTaskIds ?? []

      debugLog('APPLY_ALLOCATION attempt', {
        missionId: action.missionId, source: action.source,
        allocation: action.allocation, hasPlan: !!plan,
      })

      const assignments = greedyAssign(mission.tasks, available, action.allocation, now, plan, priorityTaskIds)

      // Compute Co-Pilot recall delays (ε_C noise — how long drones linger after task completion)
      const epsilonC = state.config.epsilonCopilot
      const recallRng = new SeededRNG(state.config.seed ^ (mission.id.charCodeAt(2) || 0) ^ 0xabcd)
      const recallDelays = new Map<string, number>()
      for (const asgn of assignments) {
        recallDelays.set(asgn.taskId, epsilonC > 0 ? recallRng.exponential(epsilonC * 45) : 0)
      }
      if (assignments.length === 0) {
        debugLog('APPLY_ALLOCATION: greedyAssign returned empty — aborting')
        return state
      }

      // Unique asset IDs across all assignments (sequential reuse → same ID may appear in multiple)
      const allAssignedIds = [...new Set(assignments.flatMap(a => a.assetIds))]

      // Update tasks — unassigned tasks remain 'pending' in the active mission
      const updatedTasks: Task[] = mission.tasks.map(task => {
        const asgn = assignments.find(a => a.taskId === task.id)
        if (!asgn) return task
        return {
          ...task,
          status: 'traveling' as const,
          assignedAssetIds: asgn.assetIds,
          allocatedAt: now,
          travelTime: asgn.travelTime,
          baseTime: asgn.baseTime,
          useSubstitute: asgn.useSubstitute,
          startTime: asgn.startTime,
          completionTime: asgn.startTime + asgn.baseTime,
          recallDelay: recallDelays.get(task.id) ?? 0,
        }
      })

      // Mark mission as active
      const updatedMission: Mission = {
        ...mission,
        status: 'active',
        tasks: updatedTasks,
        allocationTime: now,
        copilotInteraction: action.source === 'copilot_as_proposed'
          ? 'followed'
          : action.source === 'copilot_modified'
            ? 'modified'
            : 'dismissed',
      }

      // Deploy each asset to its FIRST assigned task (earliest startTime).
      // Assets scheduled for later tasks (sequential reuse) start with the first
      // task — TICK redirects them to subsequent tasks as each completes.
      const updatedAssets = state.assets.map(asset => {
        const myAsgns = assignments.filter(a => a.assetIds.includes(asset.id))
        if (myAsgns.length === 0) return asset

        // First task = lowest startTime
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
          // rough estimate — updated by TICK when the asset eventually returns
          availableAt: now + tt + firstAsgn.baseTime + travelTime(task.waypoint, HUB, ASSET_SPEED[asset.type]),
        }
      })

      let s: GameState = {
        ...state,
        missions: state.missions.map(m => m.id === mission.id ? updatedMission : m),
        assets: updatedAssets,
        copilotModal: null,
      }

      // Log modification if operator edited the strategy allocation
      if (action.source === 'copilot_modified' && action.selectedIndex !== null) {
        const original = action.strategies[action.selectedIndex]
        s = logEvent(s, {
          type: 'copilot_strategy_modified',
          missionId: mission.id,
          originalStrategy: original,
          modifiedAssets: action.allocation,
        })
      }

      s = logEvent(s, {
        type: 'allocation_applied',
        missionId: mission.id,
        assetsAllocated: allAssignedIds,
        source: action.source,
      })

      // Log MCP interaction
      if (s.metaRec) {
        const recPosture = s.metaRec.posture
        const chosenPosture = s.metaPostureOverride ?? recPosture
        if (s.metaPostureOverride && s.metaPostureOverride !== recPosture) {
          s = logEvent(s, { type: 'metacopilot_overridden', missionId: mission.id, recommendedPosture: recPosture, chosenPosture })
        } else if (mission.copilotInteraction === 'none') {
          s = logEvent(s, { type: 'metacopilot_ignored', missionId: mission.id })
        } else {
          s = logEvent(s, { type: 'metacopilot_followed', missionId: mission.id, recommendedPosture: recPosture, chosenPosture })
        }
      }

      return { ...s, metaPostureOverride: null }
    }

    // ── DISMISS_COPILOT ──────────────────────────────────────────────────
    case 'DISMISS_COPILOT': {
      let s = logEvent(state, { type: 'copilot_dismissed', missionId: action.missionId })
      s = {
        ...s,
        missions: s.missions.map(m =>
          m.id === action.missionId ? { ...m, copilotInteraction: 'dismissed' } : m,
        ),
        copilotModal: null,
      }
      return s
    }

    // ── RECALL_ASSET ─────────────────────────────────────────────────────
    case 'RECALL_ASSET': {
      const asset = state.assets.find(a => a.id === action.assetId)
      if (!asset || asset.status === 'available' || asset.status === 'returning') return state

      const taskId = asset.currentTaskId!
      const missionId = asset.currentMissionId!
      const elapsed = state.elapsed
      const returnTime = travelTime(asset.position, HUB, ASSET_SPEED[asset.type])

      // If the task is already completed (0-cost recall / auto-recall window),
      // just redirect the asset to hub without failing the task.
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

      const pending = mission.tasks.filter(t => t.status === 'pending')
      const idx = pending.findIndex(t => t.id === action.taskId)
      if (idx < 0) return state

      const newIdx = action.direction === 'top' ? 0 : action.direction === 'up' ? Math.max(0, idx - 1) : Math.min(pending.length - 1, idx + 1)
      const reordered = [...pending]
      ;[reordered[idx], reordered[newIdx]] = [reordered[newIdx], reordered[idx]]

      const nonPending = mission.tasks.filter(t => t.status !== 'pending')
      const updatedMission = { ...mission, tasks: [...nonPending, ...reordered] }

      let s = logEvent(state, {
        type: 'task_reprioritised',
        missionId: action.missionId,
        taskId: action.taskId,
        newPosition: newIdx,
      })
      return { ...s, missions: s.missions.map(m => m.id === action.missionId ? updatedMission : m) }
    }

    // ── TOGGLE_TASK_PRIORITY ─────────────────────────────────────────────
    case 'TOGGLE_TASK_PRIORITY': {
      if (!state.copilotModal) return state
      const ids = state.copilotModal.priorityTaskIds
      const newIds = ids.includes(action.taskId)
        ? ids.filter(id => id !== action.taskId)
        : [...ids, action.taskId]
      return {
        ...state,
        copilotModal: { ...state.copilotModal, priorityTaskIds: newIds },
      }
    }

    // ── SET_META_POSTURE ─────────────────────────────────────────────────
    case 'SET_META_POSTURE': {
      return { ...state, metaPostureOverride: action.posture }
    }

    // ── SUBMIT_TRUST_PROBE ───────────────────────────────────────────────
    case 'SUBMIT_TRUST_PROBE': {
      let s = logEvent(state, { type: 'trust_probe', trust: action.trust, workload: action.workload })
      s = { ...s, trustProbeActive: false, nextTrustProbeAt: state.elapsed + TRUST_PROBE_INTERVAL }
      return s
    }

    case 'DISMISS_TRUST_PROBE': {
      return { ...state, trustProbeActive: false, nextTrustProbeAt: state.elapsed + TRUST_PROBE_INTERVAL }
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
      if (state.sessionNumber < 3) return { ...state, phase: 'between' }
      return { ...state, phase: 'done' }
    }

    // ── NEXT_SESSION ─────────────────────────────────────────────────────
    case 'NEXT_SESSION': {
      if (state.phase !== 'between') return state
      const nextSession = (state.sessionNumber + 1) as 1 | 2 | 3
      const blueprints = generateSessionPlan(new SeededRNG(state.config.seed ^ nextSession), state.config.complexity)

      return {
        ...state,
        phase: 'playing',
        sessionNumber: nextSession,
        elapsed: 0,
        sessionStartMs: null,
        assets: createInitialAssets(),
        missions: [],
        pendingBlueprints: blueprints,
        score: 0,
        metaRec: null,
        metaPostureOverride: null,
        copilotModal: null,
        trustProbeActive: false,
        nextTrustProbeAt: TRUST_PROBE_INTERVAL,
      }
    }

    // ── END_STUDY ────────────────────────────────────────────────────────
    case 'END_STUDY': {
      return { ...state, phase: 'done' }
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
  const score = computeScore(failedMissions)
  const greenEff = computeGreenEfficiency(failedMissions)
  const meanTime = computeMeanMissionTime(failedMissions)
  const cpRate = computeCpFollowRate(evs)
  const mcpRate = computeMcpFollowRate(evs)

  let s2 = logEvent({ ...s, missions: failedMissions, score }, {
    type: 'session_ended',
    score,
    greenEfficiency: greenEff,
    meanMissionTime: meanTime,
    cpFollowRate: cpRate,
    mcpFollowRate: mcpRate,
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
    // No more missions coming — show uniform
    return { A: 0.2, B: 0.2, C: 0.2, D: 0.2, E: 0.2 }
  }
  // Use the next few pending missions to estimate the distribution
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
