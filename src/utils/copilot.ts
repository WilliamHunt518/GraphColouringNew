import type { Task, AssetRequirement, Strategy, TaskType, TaskComp } from '../types'
import type { SeededRNG } from './prng'
import type { TaskComposition } from './missionGen'
import { TASK_PRIMARY, TASK_SUBSTITUTE, TASK_BASE_TIME, TASK_SUB_BASE_TIME, HUB, ASSET_SPEED, travelTime } from './missionGen'

const SESSION_DURATION = 480

// ─── Virtual-timeline simulator ───────────────────────────────────────────

/**
 * Simulate completing `tasks` with a fixed pool of asset tokens.
 * Tokens reuse sequentially — freed from task A they travel directly to B.
 * Tasks are scheduled T5→T1 (most-constrained first).
 * Returns elapsed time when the last task completes (0 if no tasks).
 */
// Tasks passed in already in the desired execution order (caller is responsible for sorting).
function simulatePool(
  tasks: Task[],
  comps: Map<string, { comp: TaskComposition; baseTime: number }>,
  pool: AssetRequirement,
): number {
  interface VT { type: 'Blue' | 'Red' | 'Green'; freeAt: number; pos: { x: number; y: number } }
  const tokens: VT[] = [
    ...Array.from({ length: pool.Blue },  () => ({ type: 'Blue'  as const, freeAt: 0, pos: { ...HUB } })),
    ...Array.from({ length: pool.Red },   () => ({ type: 'Red'   as const, freeAt: 0, pos: { ...HUB } })),
    ...Array.from({ length: pool.Green }, () => ({ type: 'Green' as const, freeAt: 0, pos: { ...HUB } })),
  ]

  const pickEarliest = (type: 'Blue' | 'Red' | 'Green', n: number): VT[] =>
    tokens.filter(v => v.type === type).sort((a, b) => a.freeAt - b.freeAt).slice(0, n)

  let maxTime = 0

  for (const task of tasks) {
    const c = comps.get(task.id)
    if (!c || c.comp.Blue + c.comp.Red + c.comp.Green === 0) continue  // zero-asset tasks always skippable

    // Pool permanently lacks tokens for this task — can never complete all tasks
    if (
      tokens.filter(v => v.type === 'Blue').length  < c.comp.Blue  ||
      tokens.filter(v => v.type === 'Red').length   < c.comp.Red   ||
      tokens.filter(v => v.type === 'Green').length < c.comp.Green
    ) return Infinity

    const picked = [
      ...pickEarliest('Blue',  c.comp.Blue),
      ...pickEarliest('Red',   c.comp.Red),
      ...pickEarliest('Green', c.comp.Green),
    ]

    const startTime = picked.length
      ? Math.max(...picked.map(v => v.freeAt + travelTime(v.pos, task.waypoint, ASSET_SPEED[v.type])))
      : 0
    const endTime = startTime + c.baseTime
    if (endTime > maxTime) maxTime = endTime
    for (const v of picked) { v.freeAt = endTime; v.pos = { ...task.waypoint } }
  }

  return maxTime
}

// ─── Utilities ────────────────────────────────────────────────────────────

function cap(pool: AssetRequirement, reserve: AssetRequirement): AssetRequirement {
  return {
    Blue:  Math.min(pool.Blue,  reserve.Blue),
    Red:   Math.min(pool.Red,   reserve.Red),
    Green: Math.min(pool.Green, reserve.Green),
  }
}

function minPool(
  tasks: Task[],
  comps: Map<string, { comp: TaskComposition; baseTime: number }>,
): AssetRequirement {
  let Blue = 0, Red = 0, Green = 0
  for (const task of tasks) {
    const c = comps.get(task.id)
    if (!c) continue
    Blue  = Math.max(Blue,  c.comp.Blue)
    Red   = Math.max(Red,   c.comp.Red)
    Green = Math.max(Green, c.comp.Green)
  }
  return { Blue, Red, Green }
}

function toTaskComps(
  tasks: Task[],
  comps: Map<string, { comp: TaskComposition; baseTime: number }>,
  primaryComps: Map<string, { comp: TaskComposition; baseTime: number }>,
): Record<string, TaskComp> {
  const result: Record<string, TaskComp> = {}
  for (const task of tasks) {
    const c = comps.get(task.id)!
    const p = primaryComps.get(task.id)!
    const isSub = c.comp.Blue !== p.comp.Blue || c.comp.Red !== p.comp.Red || c.comp.Green !== p.comp.Green
    result[task.id] = { Blue: c.comp.Blue, Red: c.comp.Red, Green: c.comp.Green, baseTime: c.baseTime, useSubstitute: isSub }
  }
  return result
}

// ─── Co-Pilot task ordering ───────────────────────────────────────────────

/**
 * Builds the task execution order with optional noise.
 * At errorRate=0: optimal T5→T1 (most-constrained first).
 * At errorRate>0: each scheduling step has a errorRate probability of picking a random
 * remaining task instead of the optimal next one.
 */
export function buildNoisyTaskOrder(tasks: Task[], errorRate: number, rng: SeededRNG): Task[] {
  if (tasks.length === 0) return []
  const remaining = [...tasks].sort((a, b) => b.type - a.type)  // T5→T1 optimal
  if (errorRate === 0) return remaining
  const result: Task[] = []
  while (remaining.length > 0) {
    if (remaining.length > 1 && rng.randFloat(0, 1) < errorRate) {
      const idx = rng.randInt(0, remaining.length - 1)
      result.push(remaining.splice(idx, 1)[0])
    } else {
      result.push(remaining.shift()!)
    }
  }
  return result
}

// ─── Strategy generation ──────────────────────────────────────────────────

/**
 * Generates exactly two strategies for agent mode: Aggressive and Conservative.
 *
 * Aggressive = maximum parallelism (parallel sum of all task requirements, capped by reserve).
 * Conservative = reserve-pressure-chosen compositions + 30% top-up (reserve-balanced logic).
 *
 * Bad-agent errors (probability = agentErrorRate):
 *   'over' — displayed assets increased by 2–3 on one random type; reserve looks worse than it is
 *   'under' — displayed assets decreased by 2–3; displayed time is optimistic (computed from bad counts)
 * In both cases, trueAssets/trueTaskComps hold the correct values used by greedyAssign.
 * The displayed assets/time are intentionally wrong so the operator is misled.
 */
export function generateStrategies(
  tasks: Task[],
  reserve: AssetRequirement,
  agentErrorRate: number,
  rng: SeededRNG,
  priorityTaskIds?: string[],
): Strategy[] {
  // Priority tasks run first; remaining fall back to T5→T1 (most-constrained first).
  const prioritySet = new Set(priorityTaskIds ?? [])
  const priorityOrder = (priorityTaskIds ?? [])
    .map(id => tasks.find(t => t.id === id))
    .filter((t): t is Task => t !== undefined)
  const rest = [...tasks].filter(t => !prioritySet.has(t.id)).sort((a, b) => b.type - a.type)
  const sorted = [...priorityOrder, ...rest]

  // ─── Primary compositions (shared base) ──────────────────────────────────
  const primComps = new Map<string, { comp: TaskComposition; baseTime: number }>()
  for (const task of sorted) {
    primComps.set(task.id, {
      comp:     TASK_PRIMARY[task.type as TaskType],
      baseTime: TASK_BASE_TIME[task.type as TaskType],
    })
  }

  // Sequential floor = max requirement per type across all tasks (minimum pool for serial completion).
  // Drones are reused between tasks, so you only need as many of a type as the hardest single task demands.
  function sequentialFloor(comps: Map<string, { comp: TaskComposition; baseTime: number }>): AssetRequirement {
    let Blue = 0, Red = 0, Green = 0
    for (const task of sorted) {
      const c = comps.get(task.id)
      if (!c) continue
      Blue  = Math.max(Blue,  c.comp.Blue)
      Red   = Math.max(Red,   c.comp.Red)
      Green = Math.max(Green, c.comp.Green)
    }
    return { Blue, Red, Green }
  }

  // Redundancy = buffer above sequential floor / total pool.
  // A pool well above the floor can absorb failures and still complete serially.
  function computeRedundancyScore(pool: AssetRequirement, floor: AssetRequirement): number {
    const total = pool.Blue + pool.Red + pool.Green
    if (total === 0) return 0
    const buffer = Math.max(0, pool.Blue  - floor.Blue)
                 + Math.max(0, pool.Red   - floor.Red)
                 + Math.max(0, pool.Green - floor.Green)
    return Math.min(1, buffer / total)
  }

  // ── Aggressive strategy: parallel sum + per-type redundancy floor ───────────
  // Start from the parallel sum (enough drones for all tasks to run simultaneously),
  // then raise each used type to at least floor+1 so one failure can't block completion.
  // The parallel sum is always >= floor, so this only adds drones for types where
  // only a single task uses that type (parallelSum == floor for that type).
  const aggFloor = sequentialFloor(primComps)
  const parallelSum: AssetRequirement = { Blue: 0, Red: 0, Green: 0 }
  for (const task of sorted) {
    const c = primComps.get(task.id)!
    parallelSum.Blue  += c.comp.Blue
    parallelSum.Red   += c.comp.Red
    parallelSum.Green += c.comp.Green
  }
  const aggWithRedundancy: AssetRequirement = {
    Blue:  aggFloor.Blue  > 0 ? Math.max(parallelSum.Blue,  aggFloor.Blue  + 1) : 0,
    Red:   aggFloor.Red   > 0 ? Math.max(parallelSum.Red,   aggFloor.Red   + 1) : 0,
    Green: aggFloor.Green > 0 ? Math.max(parallelSum.Green, aggFloor.Green + 1) : 0,
  }
  const aggTruePool = cap(aggWithRedundancy, reserve)
  const aggTrueTime = simulatePool(sorted, primComps, aggTruePool)
  const aggTrueTaskComps = toTaskComps(sorted, primComps, primComps)
  const aggMinimumAssets = aggFloor

  // ── Conservative strategy: primaries by default; substitute only when reserve
  //    cannot cover the primary requirement. Pool sized near the sequential minimum
  //    (small top-up) so tasks run mostly in series — slower but reserve-preserving.
  const consComps = new Map<string, { comp: TaskComposition; baseTime: number }>()
  for (const task of sorted) {
    const prim = TASK_PRIMARY[task.type as TaskType]
    const sub  = TASK_SUBSTITUTE[task.type as TaskType]
    const reserveLacksPrimary =
      reserve.Blue  < prim.Blue  ||
      reserve.Red   < prim.Red   ||
      reserve.Green < prim.Green
    if (reserveLacksPrimary && sub) {
      consComps.set(task.id, { comp: sub, baseTime: TASK_SUB_BASE_TIME[task.type as TaskType] })
    } else {
      consComps.set(task.id, { comp: prim, baseTime: TASK_BASE_TIME[task.type as TaskType] })
    }
  }

  const consMin  = minPool(sorted, consComps)
  const consBase = cap(consMin, reserve)
  const TOP_UP          = 0.15
  // +1 buffer only for colours that appear in the mission (robust to any single failure of a used colour)
  const REDUNDANCY_BUFFER = 1
  const consTruePool: AssetRequirement = {
    Blue:  Math.min(reserve.Blue,  consBase.Blue  + Math.floor((reserve.Blue  - consBase.Blue)  * TOP_UP) + (consBase.Blue  > 0 ? REDUNDANCY_BUFFER : 0)),
    Red:   Math.min(reserve.Red,   consBase.Red   + Math.floor((reserve.Red   - consBase.Red)   * TOP_UP) + (consBase.Red   > 0 ? REDUNDANCY_BUFFER : 0)),
    Green: Math.min(reserve.Green, consBase.Green + Math.floor((reserve.Green - consBase.Green) * TOP_UP) + (consBase.Green > 0 ? REDUNDANCY_BUFFER : 0)),
  }
  const consTrueTime = simulatePool(sorted, consComps, consTruePool)
  const consTrueTaskComps = toTaskComps(sorted, consComps, primComps)
  const consFloor = sequentialFloor(consComps)
  const consMinimumAssets = consFloor

  // ── Bad-agent perturbation ────────────────────────────────────────────────
  // When an error fires, both the displayed pool AND the true pool used for execution
  // are corrupted — so errors have real consequences, not just display confusion.
  //   'over' — commits extra drones (reserve depleted unnecessarily)
  //   'under' — commits too few drones (some tasks skipped in greedyAssign, causing lockout)
  function applyBadAgent(truePool: AssetRequirement, trueTime: number, compsForSim: Map<string, { comp: TaskComposition; baseTime: number }>): {
    displayPool: AssetRequirement; displayTime: number;
    badTruePool: AssetRequirement;  // pool used for actual execution (= displayPool when bad)
    isBad: boolean; badType: 'over' | 'under' | null
  } {
    if (rng.randFloat(0, 1) > agentErrorRate) {
      return { displayPool: { ...truePool }, displayTime: trueTime, badTruePool: { ...truePool }, isBad: false, badType: null }
    }
    const types: Array<keyof AssetRequirement> = ['Blue', 'Red', 'Green']
    const t = types[rng.randInt(0, 2)]
    const isOver = rng.randFloat(0, 1) < 0.5
    const delta = 2 + rng.randInt(0, 1)  // 2 or 3
    const badPool = { ...truePool }
    if (isOver) {
      badPool[t] = Math.min(reserve[t], truePool[t] + delta)
    } else {
      badPool[t] = Math.max(0, truePool[t] - delta)
    }
    // Displayed time computed from the bad pool — looks plausible but is misleading
    // For 'under', pool may be infeasible; show an optimistic estimate instead of Infinity
    const rawTime = simulatePool(sorted, compsForSim, badPool)
    const displayTime = rawTime < Infinity ? rawTime : trueTime * (0.7 + rng.randFloat(0, 0.2))
    return { displayPool: badPool, displayTime, badTruePool: badPool, isBad: true, badType: isOver ? 'over' : 'under' }
  }

  const aggBad = applyBadAgent(aggTruePool, aggTrueTime, primComps)
  const consBad = applyBadAgent(consTruePool, consTrueTime, consComps)

  // ── Score normalisation ───────────────────────────────────────────────────
  const displayTimes = [aggBad.displayTime, consBad.displayTime].filter(t => t < Infinity)
  const minT = displayTimes.length > 0 ? Math.min(...displayTimes) : 0
  const maxT = displayTimes.length > 0 ? Math.max(...displayTimes) : 1
  const spanT = maxT - minT || 1

  const specialists = (a: AssetRequirement) => a.Green * 3 + a.Red
  const maxSpec = Math.max(specialists(aggBad.displayPool), specialists(consBad.displayPool)) || 1

  function reserveAfter(a: AssetRequirement): AssetRequirement {
    return {
      Blue:  Math.max(0, reserve.Blue  - a.Blue),
      Red:   Math.max(0, reserve.Red   - a.Red),
      Green: Math.max(0, reserve.Green - a.Green),
    }
  }

  // ── Assemble strategies ───────────────────────────────────────────────────
  const strategies: Strategy[] = []

  // Aggressive
  if (aggTrueTime < Infinity) {
    strategies.push({
      name: 'Aggressive',
      description: 'Maximum parallel deployment — all tasks run simultaneously for minimum mission time. At least one spare drone per type deployed as a failure buffer.',
      assets: aggBad.displayPool,
      expectedCompletionTime: aggBad.displayTime,
      reserveAfter: reserveAfter(aggBad.displayPool),
      speedScore: 1,
      reserveScore: 1 - specialists(aggBad.displayPool) / maxSpec,
      redundancyScore: computeRedundancyScore(aggBad.displayPool, aggFloor),
      minimumAssets: aggMinimumAssets,
      taskComps: aggTrueTaskComps,
      isBadSuggestion: aggBad.isBad,
      badSuggestionType: aggBad.badType,
      trueAssets: aggBad.badTruePool,   // corrupted pool used for real deployment when bad
      trueTaskComps: aggTrueTaskComps,
    })
  }

  // Conservative
  if (consTrueTime < Infinity) {
    strategies.push({
      name: 'Conservative',
      description: 'Reserve-preserving deployment — commits a buffer above minimum to absorb drone failures. Tasks run in series; slower but resilient.',
      assets: consBad.displayPool,
      expectedCompletionTime: consBad.displayTime,
      reserveAfter: reserveAfter(consBad.displayPool),
      speedScore: 1 - (consBad.displayTime - minT) / spanT,
      reserveScore: 1 - specialists(consBad.displayPool) / maxSpec,
      redundancyScore: computeRedundancyScore(consBad.displayPool, consFloor),
      minimumAssets: consMinimumAssets,
      taskComps: consTrueTaskComps,
      isBadSuggestion: consBad.isBad,
      badSuggestionType: consBad.badType,
      trueAssets: consBad.badTruePool,  // corrupted pool used for real deployment when bad
      trueTaskComps: consTrueTaskComps,
    })
  }

  return strategies
}

/**
 * Estimates completion time for a given asset pool and task list.
 * Returns Infinity if any task cannot be covered (no partial ETAs).
 */
export function previewAllocation(tasks: Task[], pool: AssetRequirement): number {
  const comps = new Map<string, { comp: TaskComposition; baseTime: number }>()
  for (const task of tasks) {
    const prim = TASK_PRIMARY[task.type as TaskType]
    const sub  = TASK_SUBSTITUTE[task.type as TaskType]
    if (pool.Blue >= prim.Blue && pool.Red >= prim.Red && pool.Green >= prim.Green) {
      comps.set(task.id, { comp: prim, baseTime: TASK_BASE_TIME[task.type as TaskType] })
    } else if (sub && pool.Blue >= sub.Blue && pool.Red >= sub.Red && pool.Green >= sub.Green) {
      comps.set(task.id, { comp: sub, baseTime: TASK_SUB_BASE_TIME[task.type as TaskType] })
    } else {
      return Infinity  // can't cover all tasks with this pool
    }
  }
  if (comps.size === 0) return 0
  const sorted = [...tasks].sort((a, b) => b.type - a.type)
  return simulatePool(sorted, comps, pool)
}

// Re-export elapsed for SESSION_DURATION usage downstream
export { SESSION_DURATION }
