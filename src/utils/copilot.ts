import type { Task, AssetRequirement, Strategy, TaskType } from '../types'
import type { SeededRNG } from './prng'
import type { TaskComposition } from './missionGen'
import { TASK_PRIMARY, TASK_SUBSTITUTE, TASK_BASE_TIME, TASK_SUB_BASE_TIME, HUB, ASSET_SPEED, travelTime } from './missionGen'

// ─── Strategy generation ──────────────────────────────────────────────────

/**
 * Computes total assets and expected completion time for a set of task compositions.
 * Expected completion = max(travel + baseTime) across all tasks (parallel execution).
 */
function computeStrategyMetrics(
  tasks: Task[],
  compositions: Map<string, { comp: TaskComposition; baseTime: number }>,
): { assets: AssetRequirement; expectedCompletionTime: number } {
  const assets: AssetRequirement = { Blue: 0, Red: 0, Green: 0 }
  let maxTime = 0

  for (const task of tasks) {
    const c = compositions.get(task.id)
    if (!c) continue
    assets.Blue += c.comp.Blue
    assets.Red += c.comp.Red
    assets.Green += c.comp.Green

    const slowest = Math.min(
      ...(['Blue', 'Red', 'Green'] as const)
        .filter(t => c.comp[t] > 0)
        .map(t => ASSET_SPEED[t]),
    ) || ASSET_SPEED.Blue

    const tt = travelTime(HUB, task.waypoint, slowest)
    const total = tt + c.baseTime
    if (total > maxTime) maxTime = total
  }

  return { assets, expectedCompletionTime: maxTime }
}

/**
 * Checks whether an allocation is feasible given the available reserve.
 */
function isFeasible(needed: AssetRequirement, reserve: AssetRequirement): boolean {
  return needed.Blue <= reserve.Blue && needed.Red <= reserve.Red && needed.Green <= reserve.Green
}

/**
 * Generates the three Co-Pilot strategy cards.
 * Noise ε_C perturbs the internal objective weights before ranking,
 * which can swap the labels in low-accuracy conditions.
 */
export function generateStrategies(
  tasks: Task[],
  reserve: AssetRequirement,
  epsilonC: number,
  rng: SeededRNG,
): Strategy[] {
  const sorted = [...tasks].sort((a, b) => b.type - a.type)

  // Build per-task compositions for "all-primary" and "all-substitute" extremes
  const primaryComps = new Map<string, { comp: TaskComposition; baseTime: number }>()
  const subComps = new Map<string, { comp: TaskComposition; baseTime: number }>()

  for (const task of sorted) {
    const prim = TASK_PRIMARY[task.type as TaskType]
    primaryComps.set(task.id, { comp: prim, baseTime: TASK_BASE_TIME[task.type as TaskType] })

    const sub = TASK_SUBSTITUTE[task.type as TaskType]
    subComps.set(task.id, sub
      ? { comp: sub, baseTime: TASK_SUB_BASE_TIME[task.type as TaskType] }
      : { comp: prim, baseTime: TASK_BASE_TIME[task.type as TaskType] },
    )
  }

  const fast = computeStrategyMetrics(sorted, primaryComps)
  const spec = computeStrategyMetrics(sorted, subComps)

  // Balanced: mix primary/substitute per task to minimise a weighted objective
  const balComps = new Map<string, { comp: TaskComposition; baseTime: number }>()
  for (const task of sorted) {
    const prim = TASK_PRIMARY[task.type as TaskType]
    const sub = TASK_SUBSTITUTE[task.type as TaskType]
    // Prefer substitute for T2–T4 (saves specialists) unless it's much slower
    if (sub && (task.type === 2 || task.type === 3)) {
      balComps.set(task.id, { comp: sub, baseTime: TASK_SUB_BASE_TIME[task.type as TaskType] })
    } else {
      balComps.set(task.id, { comp: prim, baseTime: TASK_BASE_TIME[task.type as TaskType] })
    }
  }
  const bal = computeStrategyMetrics(sorted, balComps)

  // Normalise scores for display bars
  const times = [fast.expectedCompletionTime, bal.expectedCompletionTime, spec.expectedCompletionTime]
  const minT = Math.min(...times)
  const maxT = Math.max(...times) || 1

  const specialists = (a: AssetRequirement) => a.Green * 3 + a.Red
  const specialistCounts = [fast.assets, bal.assets, spec.assets].map(specialists)
  const maxSpec = Math.max(...specialistCounts) || 1

  function reserveAfter(a: AssetRequirement): AssetRequirement {
    return {
      Blue: Math.max(0, reserve.Blue - a.Blue),
      Red: Math.max(0, reserve.Red - a.Red),
      Green: Math.max(0, reserve.Green - a.Green),
    }
  }

  const raw: Strategy[] = [
    {
      name: 'Fastest',
      description: 'Commit optimal assets — minimise mission completion time.',
      assets: fast.assets,
      expectedCompletionTime: fast.expectedCompletionTime,
      reserveAfter: reserveAfter(fast.assets),
      speedScore: 1,
      reserveScore: 1 - (specialists(fast.assets) / maxSpec),
    },
    {
      name: 'Specialist-Conserving',
      description: 'Use substitutes where possible — preserve Green and Red reserve.',
      assets: spec.assets,
      expectedCompletionTime: spec.expectedCompletionTime,
      reserveAfter: reserveAfter(spec.assets),
      speedScore: 1 - (spec.expectedCompletionTime - minT) / (maxT - minT + 1),
      reserveScore: 1,
    },
    {
      name: 'Balanced',
      description: 'Balanced trade-off between speed and reserve preservation.',
      assets: bal.assets,
      expectedCompletionTime: bal.expectedCompletionTime,
      reserveAfter: reserveAfter(bal.assets),
      speedScore: 1 - (bal.expectedCompletionTime - minT) / (maxT - minT + 1),
      reserveScore: 1 - (specialists(bal.assets) / maxSpec),
    },
  ]

  // Apply ε noise to objective weights before ranking (scrambles labels in low-accuracy conditions)
  const weights = raw.map(s => {
    const timeWeight = 0.5 + epsilonC * rng.noise()
    const reserveWeight = 1 - timeWeight
    return timeWeight * s.speedScore + reserveWeight * s.reserveScore
  })

  // Reorder by perturbed weight descending, then re-apply the canonical names/descriptions
  const ranked = raw
    .map((s, i) => ({ ...s, _w: weights[i] }))
    .sort((a, b) => b._w - a._w)

  const names: Strategy['name'][] = ['Fastest', 'Specialist-Conserving', 'Balanced']
  const descriptions = [
    'Commit optimal assets — minimise mission completion time.',
    'Use substitutes where possible — preserve Green and Red reserve.',
    'Balanced trade-off between speed and reserve preservation.',
  ]

  return ranked.map((s, i) => ({
    name: names[i],
    description: descriptions[i],
    assets: s.assets,
    expectedCompletionTime: s.expectedCompletionTime,
    reserveAfter: s.reserveAfter,
    speedScore: s.speedScore,
    reserveScore: s.reserveScore,
  }))
    .filter(s => isFeasible(s.assets, reserve))
    .slice(0, 3)
}
