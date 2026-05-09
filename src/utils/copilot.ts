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

  const sorted = [...tasks].sort((a, b) => b.type - a.type)
  let maxTime = 0

  for (const task of sorted) {
    const c = comps.get(task.id)
    if (!c || c.comp.Blue + c.comp.Red + c.comp.Green === 0) continue

    // Skip if pool lacks sufficient tokens
    if (
      tokens.filter(v => v.type === 'Blue').length  < c.comp.Blue  ||
      tokens.filter(v => v.type === 'Red').length   < c.comp.Red   ||
      tokens.filter(v => v.type === 'Green').length < c.comp.Green
    ) continue

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

// ─── Strategy generation ──────────────────────────────────────────────────

/**
 * Generates four Co-Pilot strategy cards.
 *
 * 1. "Fastest Possible"   — all primaries, parallel pool (max parallelism)
 * 2. "Complete in Time"   — all primaries, minimum pool that finishes within
 *                           90% of remaining session time (sequential reuse)
 * 3. "Asset-Preserving"   — substitutes on T2/T3/T4 (no Green for T4!),
 *                           primary only on T1/T5; max 1 Green committed
 * 4. "Balanced"           — primaries on T4/T5, substitutes on T2/T3;
 *                           up to 2 Green committed
 *
 * PP condition (ε=0): strategies returned in natural order, labels intact.
 * ε>0: objective weights perturbed by noise — simulates inaccurate AI.
 */
export function generateStrategies(
  tasks: Task[],
  reserve: AssetRequirement,
  epsilonC: number,
  rng: SeededRNG,
  elapsed: number,
): Strategy[] {
  const sorted = [...tasks].sort((a, b) => b.type - a.type)
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
  const fastTime = simulatePool(sorted, primComps, fastPool)

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
  const citTime = simulatePool(sorted, primComps, citPool)

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
  const presTime = simulatePool(sorted, presComps, presPool)

  // ── Normalise display scores ──────────────────────────────────────────────
  const times    = [fastTime, citTime, presTime]
  const minT     = Math.min(...times)
  const spanT    = Math.max(...times) - minT || 1

  const specialists = (a: AssetRequirement) => a.Green * 3 + a.Red
  const maxSpec     = Math.max(...[fastPool, citPool, presPool].map(specialists)) || 1

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
      assets: fastPool,
      expectedCompletionTime: fastTime,
      reserveAfter: reserveAfter(fastPool),
      speedScore: 1,
      reserveScore: 1 - specialists(fastPool) / maxSpec,
      taskComps: toTaskComps(sorted, primComps, primComps),
    },
    {
      name: 'Complete in Time',
      description: `Minimum assets finishing before the ${Math.round(deadline)}s deadline — assets cycle sequentially between tasks.`,
      assets: citPool,
      expectedCompletionTime: citTime,
      reserveAfter: reserveAfter(citPool),
      speedScore: 1 - (citTime - minT) / spanT,
      reserveScore: 1 - specialists(citPool) / maxSpec,
      taskComps: toTaskComps(sorted, primComps, primComps),
    },
    {
      name: 'Asset-Preserving',
      description: 'Substitutes on all but Specialist Ops — commits at most 1 Green, maximises reserve.',
      assets: presPool,
      expectedCompletionTime: presTime,
      reserveAfter: reserveAfter(presPool),
      speedScore: 1 - (presTime - minT) / spanT,
      reserveScore: 1 - specialists(presPool) / maxSpec,
      taskComps: toTaskComps(sorted, presComps, primComps),
    },
  ]

  // ── Perfect mode (ε=0): natural order, labels intact ────────────────────
  if (epsilonC === 0) {
    return raw.filter(s => isFeasible(s.assets, reserve))
  }

  // ── Apply ε noise — perturbs objective weights before ranking ─────────────
  const weights = raw.map(s => {
    const tw = 0.5 + epsilonC * rng.noise()
    return tw * s.speedScore + (1 - tw) * s.reserveScore
  })

  const ranked = raw
    .map((s, i) => ({ ...s, _w: weights[i] }))
    .sort((a, b) => b._w - a._w)

  const names: Strategy['name'][] = ['Fastest Possible', 'Complete in Time', 'Asset-Preserving']
  const descs = [
    'Maximum parallel deployment — all tasks run simultaneously for minimum mission time.',
    'Minimum assets finishing before the deadline — assets cycle sequentially between tasks.',
    'Substitutes on all but Specialist Ops — commits at most 1 Green, maximises reserve.',
  ]

  return ranked
    .map((s, i) => ({ ...s, name: names[i], description: descs[i] }))
    .filter(s => isFeasible(s.assets, reserve))
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
  return simulatePool(tasks, comps, pool)
}
