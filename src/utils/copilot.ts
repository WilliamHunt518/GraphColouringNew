import type { Task, AssetRequirement, Strategy, TaskType, TaskComp } from '../types'
import type { SeededRNG } from './prng'
import type { TaskComposition } from './missionGen'
import { TASK_PRIMARY, TASK_SUBSTITUTE, TASK_BASE_TIME, TASK_SUB_BASE_TIME, HUB, ASSET_SPEED, travelTime } from './missionGen'

const SESSION_DURATION = 600

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

function isFeasible(needed: AssetRequirement, reserve: AssetRequirement): boolean {
  return needed.Blue <= reserve.Blue && needed.Red <= reserve.Red && needed.Green <= reserve.Green
}

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
 * Builds the Co-Pilot's task execution order with ε_C noise.
 * At ε_C=0: optimal T5→T1 (most-constrained first).
 * At ε_C>0: each scheduling step has a ε_C probability of picking a random
 * remaining task instead of the optimal next one.
 */
export function buildNoisyTaskOrder(tasks: Task[], epsilonC: number, rng: SeededRNG): Task[] {
  if (tasks.length === 0) return []
  const remaining = [...tasks].sort((a, b) => b.type - a.type)  // T5→T1 optimal
  if (epsilonC === 0) return remaining
  const result: Task[] = []
  while (remaining.length > 0) {
    if (remaining.length > 1 && rng.randFloat(0, 1) < epsilonC) {
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
 * Generates Meta-Co-Pilot strategy cards (asset allocation recommendations).
 *
 * 1. "Fastest Possible"  — all primaries, parallel pool (max parallelism)
 * 2. "Complete in Time"  — minimum pool finishing within 90% of remaining time
 * 3. "Asset-Preserving"  — substitutes on T2/T3/T4; max 1 Green committed
 *
 * ε_M=0: correct counts returned.
 * ε_M>0: each strategy's pool has a ε_M probability of ±1 on a random asset
 *        type, simulating an inaccurate Meta-Co-Pilot recommendation.
 */
export function generateStrategies(
  tasks: Task[],
  reserve: AssetRequirement,
  epsilonM: number,
  rng: SeededRNG,
  elapsed: number,
  priorityTaskIds?: string[],
): Strategy[] {
  // Priority tasks run first; remaining fall back to T5→T1 (most-constrained first).
  const prioritySet = new Set(priorityTaskIds ?? [])
  const priorityOrder = (priorityTaskIds ?? [])
    .map(id => tasks.find(t => t.id === id))
    .filter((t): t is Task => t !== undefined)
  const rest = [...tasks].filter(t => !prioritySet.has(t.id)).sort((a, b) => b.type - a.type)
  const sorted = [...priorityOrder, ...rest]
  const remaining = Math.max(30, SESSION_DURATION - elapsed)

  // ─── Primary compositions (all strategies share this base) ───────────────
  const primComps = new Map<string, { comp: TaskComposition; baseTime: number }>()
  for (const task of sorted) {
    primComps.set(task.id, {
      comp:     TASK_PRIMARY[task.type as TaskType],
      baseTime: TASK_BASE_TIME[task.type as TaskType],
    })
  }

  // ── Strategy 1: Fastest Possible ─────────────────────────────────────────
  // Parallel pool = sum of all task requirements (capped by reserve).
  // All primaries — maximum speed.
  const parallelSum: AssetRequirement = { Blue: 0, Red: 0, Green: 0 }
  for (const task of sorted) {
    const c = primComps.get(task.id)!
    parallelSum.Blue  += c.comp.Blue
    parallelSum.Red   += c.comp.Red
    parallelSum.Green += c.comp.Green
  }
  const fastPool = cap(parallelSum, reserve)

  // ── Strategy 2: Complete in Time ─────────────────────────────────────────
  // Search for the smallest pool completing within deadline (90% of remaining).
  // Blue is fixed at the single-task maximum (can't go lower without skipping tasks).
  // Search over Green (minG..3) and Red (minR..minR+4).
  const deadline = remaining * 0.90

  const minB = sorted.reduce((m, t) => Math.max(m, TASK_PRIMARY[t.type as TaskType].Blue),  0)
  const minR = sorted.reduce((m, t) => Math.max(m, TASK_PRIMARY[t.type as TaskType].Red),   0)
  const minG = sorted.some(t => TASK_PRIMARY[t.type as TaskType].Green > 0) ? 1 : 0

  let citPool: AssetRequirement | null = null

  outer:
  for (let g = minG; g <= Math.min(reserve.Green, 3); g++) {
    for (let r = minR; r <= Math.min(reserve.Red, minR + 4); r++) {
      const candidate: AssetRequirement = { Blue: minB, Red: r, Green: g }
      if (!isFeasible(candidate, reserve)) continue
      if (simulatePool(sorted, primComps, candidate) <= deadline) {
        citPool = candidate
        break outer
      }
    }
  }
  // Fallback: use the same pool as "Fastest" (best we can do if deadline is unreachable)
  if (!citPool) citPool = { ...fastPool }

  // ── Strategy 3: Asset-Preserving ─────────────────────────────────────────
  // Substitute on T2, T3, T4 (avoids Green on T4; reduces Red on T2/T3).
  // Primary on T1 and T5 (T5 must use Green; no substitute exists for T1/T5).
  // Pool capped at 1 Green — only T5 tasks need the Green specialist.
  const presComps = new Map<string, { comp: TaskComposition; baseTime: number }>()
  for (const task of sorted) {
    const sub = TASK_SUBSTITUTE[task.type as TaskType]
    if (sub && (task.type === 2 || task.type === 3 || task.type === 4)) {
      presComps.set(task.id, { comp: sub, baseTime: TASK_SUB_BASE_TIME[task.type as TaskType] })
    } else {
      presComps.set(task.id, { comp: TASK_PRIMARY[task.type as TaskType], baseTime: TASK_BASE_TIME[task.type as TaskType] })
    }
  }
  const presMin = minPool(sorted, presComps)
  // Cap Green at 1 (preserve specialists)
  const presPool = cap({ ...presMin, Green: Math.min(presMin.Green, 1) }, reserve)

  // ── Perturb pool counts with ε_M noise ───────────────────────────────────
  // With probability ε_M, adjusts one asset type's count by ±1 (capped to
  // [0, reserve]). Simulates the MCP over- or under-recommending assets.
  // If noise renders the pool unable to complete all tasks, the original is kept —
  // we never suggest a plan that leaves tasks incomplete.
  function perturbPool(
    pool: AssetRequirement,
    comps: Map<string, { comp: TaskComposition; baseTime: number }>,
  ): AssetRequirement {
    if (epsilonM === 0 || rng.randFloat(0, 1) > epsilonM) return { ...pool }
    const types: Array<keyof AssetRequirement> = ['Blue', 'Red', 'Green']
    const type = types[rng.randInt(0, 2)]
    const delta = rng.randFloat(0, 1) < 0.5 ? -1 : 1
    const noisy = {
      ...pool,
      [type]: Math.max(0, Math.min(reserve[type], pool[type] + delta)),
    }
    return simulatePool(sorted, comps, noisy) < Infinity ? noisy : { ...pool }
  }

  const noisyFastPool = perturbPool(fastPool, primComps)
  const noisyCitPool  = perturbPool(citPool,  primComps)
  const noisyPresPool = perturbPool(presPool, presComps)

  // Recompute ETAs from noisy pools (so displayed time matches displayed counts)
  const noisyFastTime = simulatePool(sorted, primComps, noisyFastPool)
  const noisyCitTime  = simulatePool(sorted, primComps, noisyCitPool)
  const noisyPresTime = simulatePool(sorted, presComps, noisyPresPool)

  // ── Normalise display scores ──────────────────────────────────────────────
  const times   = [noisyFastTime, noisyCitTime, noisyPresTime]
  const minT    = Math.min(...times)
  const spanT   = Math.max(...times) - minT || 1

  const specialists = (a: AssetRequirement) => a.Green * 3 + a.Red
  const maxSpec     = Math.max(...[noisyFastPool, noisyCitPool, noisyPresPool].map(specialists)) || 1

  function reserveAfter(a: AssetRequirement): AssetRequirement {
    return {
      Blue:  Math.max(0, reserve.Blue  - a.Blue),
      Red:   Math.max(0, reserve.Red   - a.Red),
      Green: Math.max(0, reserve.Green - a.Green),
    }
  }

  const raw: Strategy[] = [
    {
      name: 'Fastest Possible',
      description: 'Maximum parallel deployment — all tasks run simultaneously for minimum mission time.',
      assets: noisyFastPool,
      expectedCompletionTime: noisyFastTime,
      reserveAfter: reserveAfter(noisyFastPool),
      speedScore: 1,
      reserveScore: 1 - specialists(noisyFastPool) / maxSpec,
      taskComps: toTaskComps(sorted, primComps, primComps),
    },
    {
      name: 'Complete in Time',
      description: `Minimum assets finishing before the ${Math.round(deadline)}s deadline — assets cycle sequentially between tasks.`,
      assets: noisyCitPool,
      expectedCompletionTime: noisyCitTime,
      reserveAfter: reserveAfter(noisyCitPool),
      speedScore: 1 - (noisyCitTime - minT) / spanT,
      reserveScore: 1 - specialists(noisyCitPool) / maxSpec,
      taskComps: toTaskComps(sorted, primComps, primComps),
    },
    {
      name: 'Asset-Preserving',
      description: 'Substitutes on all but Specialist Ops — commits at most 1 Green, maximises reserve.',
      assets: noisyPresPool,
      expectedCompletionTime: noisyPresTime,
      reserveAfter: reserveAfter(noisyPresPool),
      speedScore: 1 - (noisyPresTime - minT) / spanT,
      reserveScore: 1 - specialists(noisyPresPool) / maxSpec,
      taskComps: toTaskComps(sorted, presComps, primComps),
    },
  ]

  return raw.filter(s => isFeasible(s.assets, reserve) && s.expectedCompletionTime < Infinity)
}

/**
 * Estimates completion time for a given asset pool and task list (primary compositions).
 * Used by ManualAllocator to show live ETA preview as the user adjusts counts.
 */
export function previewAllocation(tasks: Task[], pool: AssetRequirement): number {
  const comps = new Map<string, { comp: TaskComposition; baseTime: number }>()
  for (const task of tasks) {
    comps.set(task.id, {
      comp:     TASK_PRIMARY[task.type as TaskType],
      baseTime: TASK_BASE_TIME[task.type as TaskType],
    })
  }
  const sorted = [...tasks].sort((a, b) => b.type - a.type)
  return simulatePool(sorted, comps, pool)
}
