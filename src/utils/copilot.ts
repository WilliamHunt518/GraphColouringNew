import type { Task, AssetRequirement, AssetType, Strategy, TaskType, TaskComp } from '../types'
import type { SeededRNG } from './prng'
import type { TaskComposition } from './missionGen'
import { TASK_PRIMARY, TASK_SUBSTITUTE, TASK_BASE_TIME, TASK_SUB_BASE_TIME, HUB, ASSET_SPEED, travelTime } from './missionGen'

const SESSION_DURATION = 480

// Conservative-strategy top-up parameters (also used in session_start parameter dump)
export const CONSERVATIVE_TOP_UP = 0.15
export const CONSERVATIVE_REDUNDANCY_BUFFER = 1

// ε_Strategic 'over' failure magnitude (study-v1.10, also dumped in session_start)
export const STRATEGIC_OVER_DELTA = 3

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
 * ε_Strategic failure (study-v1.10, probability = agentErrorRate, ONE roll per mission — not per
 * card, so a failure corrupts BOTH cards with the same mistake, not two independent ones):
 *   'over'  — commits STRATEGIC_OVER_DELTA (3) extra drones of one random colour on both cards.
 *             Wastes reserve (no completion-time benefit — the extra tokens sit idle) without
 *             affecting feasibility.
 *   'under' — removes 1 drone from a colour that carries redundancy buffer above that card's own
 *             sequential floor (preferring the failure's chosen colour, else any buffered colour on
 *             that specific card). Floored at the card's minimum, so this can never make a card
 *             infeasible or drop a task — it only zeroes out the resilience margin: the mission
 *             still completes on the happy path, but a later drone failure on it has no spare to
 *             absorb.
 * Both `assets` (displayed) and `trueAssets` (used by greedyAssign at deploy time) are the SAME
 * corrupted pool — this has always been a real-consequence error, not a display-only one, despite
 * what an earlier draft of this comment claimed.
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
  // +1 buffer only for colours that appear in the mission (robust to any single failure of a used colour)
  const consTruePool: AssetRequirement = {
    Blue:  Math.min(reserve.Blue,  consBase.Blue  + Math.floor((reserve.Blue  - consBase.Blue)  * CONSERVATIVE_TOP_UP) + (consBase.Blue  > 0 ? CONSERVATIVE_REDUNDANCY_BUFFER : 0)),
    Red:   Math.min(reserve.Red,   consBase.Red   + Math.floor((reserve.Red   - consBase.Red)   * CONSERVATIVE_TOP_UP) + (consBase.Red   > 0 ? CONSERVATIVE_REDUNDANCY_BUFFER : 0)),
    Green: Math.min(reserve.Green, consBase.Green + Math.floor((reserve.Green - consBase.Green) * CONSERVATIVE_TOP_UP) + (consBase.Green > 0 ? CONSERVATIVE_REDUNDANCY_BUFFER : 0)),
  }
  const consTrueTime = simulatePool(sorted, consComps, consTruePool)
  const consTrueTaskComps = toTaskComps(sorted, consComps, primComps)
  const consFloor = sequentialFloor(consComps)
  const consMinimumAssets = consFloor

  // ── ε_Strategic failure (study-v1.10) ─────────────────────────────────────
  // ONE roll per mission (not per card) — when it fires, both cards are corrupted by the SAME
  // mistake (same failure type), not two independent ones. Both the displayed pool and the pool
  // actually used at deploy time are the corrupted one — real consequences, not just a display
  // discrepancy.
  //
  // "Fires" is necessary but not sufficient: a corruption must also be MATERIAL, or the failure is
  // invisible and undermines the whole point of the manipulation —
  //   'over'  only ever targets a colour with real reserve headroom (never "add 3 Green" when
  //           reserve.Green is already fully committed, which would silently add zero)
  //   'under' only ever targets a colour the mission actually NEEDS (floor > 0) that also carries
  //           buffer above that floor — never a top-up-only colour the mission uses zero of (e.g.
  //           Conservative's blanket CONSERVATIVE_TOP_UP can leave a lone Green sitting on an
  //           all-Blue mission; stripping that spare has no operational effect and doesn't count)
  // And EITHER BOTH cards end up corrupted, or NEITHER does — an asymmetric "only one card looks
  // wrong" defeats the "both plans are bad" premise. So a card is only marked bad once we've
  // confirmed BOTH cards have a materially-impactful colour available for the rolled type; if
  // either doesn't, the roll still "fired" (logged as such isn't needed — no card shows it) but
  // has zero effect this mission, same as reserve being too tight to matter physically.
  const strategicFailure = (() => {
    if (agentErrorRate <= 0 || rng.randFloat(0, 1) >= agentErrorRate) {
      return { fires: false, type: null as 'over' | 'under' | null, colour: null as AssetType | null }
    }
    const types: AssetType[] = ['Blue', 'Red', 'Green']
    return {
      fires: true,
      type: (rng.randFloat(0, 1) < 0.5 ? 'over' : 'under') as 'over' | 'under',
      colour: types[rng.randInt(0, 3)],   // randInt is exclusive of its upper bound — 3, not 2, to reach Green
    }
  })()

  // Computes the ACTUAL corrupted pool for a candidate colour and reports whether it genuinely
  // differs from truePool — verified by really applying the change, not inferred from a separate
  // headroom/buffer predicate that could theoretically drift out of sync with what applying it
  // actually does. "Fires" is necessary but not sufficient: only a colour that provably changes the
  // pool counts as impactful.
  function tryColour(
    truePool: AssetRequirement, floor: AssetRequirement, type: 'over' | 'under', colour: AssetType,
  ): AssetRequirement | null {
    const badPool = { ...truePool }
    if (type === 'over') {
      badPool[colour] = Math.min(reserve[colour], truePool[colour] + STRATEGIC_OVER_DELTA)
    } else {
      if (floor[colour] <= 0) return null   // not a colour the mission actually needs
      badPool[colour] = Math.max(floor[colour], truePool[colour] - 1)
    }
    return badPool[colour] !== truePool[colour] ? badPool : null
  }

  // Tries the mission-wide preferred colour first, then the other two (fixed order), returning the
  // first one that actually changes something on THIS card.
  function pickImpactfulPool(
    truePool: AssetRequirement, floor: AssetRequirement, type: 'over' | 'under', preferred: AssetType,
  ): { badPool: AssetRequirement; colour: AssetType } | null {
    const order = [preferred, ...(['Blue', 'Red', 'Green'] as AssetType[]).filter(t => t !== preferred)]
    for (const colour of order) {
      const badPool = tryColour(truePool, floor, type, colour)
      if (badPool) return { badPool, colour }
    }
    return null
  }

  const aggTrial = strategicFailure.fires ? pickImpactfulPool(aggTruePool, aggFloor, strategicFailure.type!, strategicFailure.colour!) : null
  const consTrial = strategicFailure.fires ? pickImpactfulPool(consTruePool, consFloor, strategicFailure.type!, strategicFailure.colour!) : null
  // Both cards fail, or neither does — an asymmetric "only one card looks wrong" defeats the "both
  // plans are bad" premise. If either card has nothing that actually changes anything (very tight
  // reserve, or a card with zero redundancy anywhere), the roll still "fired" but has zero visible
  // effect this mission — the same honest degrade-to-nothing as physically running out of room.
  const bothCardsCanFail = aggTrial !== null && consTrial !== null

  function applyStrategicFailure(
    truePool: AssetRequirement,
    trueTime: number,
    trial: { badPool: AssetRequirement; colour: AssetType } | null,
    compsForSim: Map<string, { comp: TaskComposition; baseTime: number }>,
  ): {
    displayPool: AssetRequirement; displayTime: number;
    badTruePool: AssetRequirement;  // pool used for actual execution (= displayPool when bad)
    isBad: boolean; badType: 'over' | 'under' | null; badColour: AssetType | null
  } {
    if (!bothCardsCanFail || !trial) {
      return { displayPool: { ...truePool }, displayTime: trueTime, badTruePool: { ...truePool }, isBad: false, badType: null, badColour: null }
    }
    const rawTime = simulatePool(sorted, compsForSim, trial.badPool)
    // 'under' never drops below the floor, so this stays finite; guarded anyway for safety.
    const displayTime = rawTime < Infinity ? rawTime : trueTime
    return { displayPool: trial.badPool, displayTime, badTruePool: trial.badPool, isBad: true, badType: strategicFailure.type, badColour: trial.colour }
  }

  const aggBad = applyStrategicFailure(aggTruePool, aggTrueTime, aggTrial, primComps)
  const consBad = applyStrategicFailure(consTruePool, consTrueTime, consTrial, consComps)

  // ── Score normalisation ───────────────────────────────────────────────────
  const clamp01 = (n: number) => (Number.isFinite(n) ? Math.max(0, Math.min(1, n)) : 0)

  // Speed = the best displayed ETA as a fraction of this card's, so the faster card reads 100% and
  // a card 20% slower reads 83%.
  //
  // This was a two-point min-max (`1 - (t - minT) / spanT`), which forced the slower card to
  // EXACTLY 0% however small the gap, and to 100% whenever the two ETAs tied — a bar with only two
  // reachable values. Across the pilot logs it read 0% on 63% of cards and tied at 100% on 37%,
  // so it carried essentially no information about how much slower the slower option actually was.
  const displayTimes = [aggBad.displayTime, consBad.displayTime].filter(t => t > 0 && t < Infinity)
  const bestT = displayTimes.length > 0 ? Math.min(...displayTimes) : 0
  const speedScoreFor = (t: number) =>
    bestT > 0 && t > 0 && t < Infinity ? clamp01(bestT / t) : 0

  // Reserve = the share of the current reserve this commitment LEAVES BEHIND. That is what the
  // Conservative card's "reserve-preserving" text claims to optimise, and what the "Res:" counts
  // printed directly under it already show the operator.
  //
  // This was `1 - (Green*3 + Red) / max`: specialists *committed*, weighted 3:1 toward Green, with
  // Blue ignored entirely, and again normalised across only the two cards so one of them always
  // read exactly 0%. It scored the card holding MORE drones back as 0% in 57% of pilot
  // presentations — the bar contradicted both the card's own text and the numbers beside it, and
  // was a large part of why Aggressive weakly dominated all three bars on ~half of all cards.
  const reserveTotal = reserve.Blue + reserve.Red + reserve.Green
  const reserveScoreFor = (a: AssetRequirement) => {
    if (reserveTotal <= 0) return 0
    const left = reserveAfter(a)   // hoisted function declaration, defined just below
    return clamp01((left.Blue + left.Red + left.Green) / reserveTotal)
  }

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
      speedScore: speedScoreFor(aggBad.displayTime),
      reserveScore: reserveScoreFor(aggBad.displayPool),
      redundancyScore: computeRedundancyScore(aggBad.displayPool, aggFloor),
      minimumAssets: aggMinimumAssets,
      taskComps: aggTrueTaskComps,
      isBadSuggestion: aggBad.isBad,
      badSuggestionType: aggBad.badType,
      badSuggestionColour: aggBad.badColour,
      trueAssets: aggBad.badTruePool,   // corrupted pool used for real deployment when bad
      trueTaskComps: aggTrueTaskComps,
    })
  }

  // Conservative
  if (consTrueTime < Infinity) {
    strategies.push({
      name: 'Conservative',
      // Was "Reserve-preserving deployment — …". That claim is not true of what this strategy
      // actually builds: the pool is the sequential minimum plus a +1 buffer per used colour plus
      // CONSERVATIVE_TOP_UP (15%) of whatever reserve is left, which on small missions commits MORE
      // drones than Aggressive for the same ETA. The old reserveScore hid this by scoring
      // specialists committed; now that Reserve reads drones-left-behind, a card headed
      // "reserve-preserving" that scores below Aggressive on Reserve would read as a contradiction.
      // Resilience is what this strategy genuinely optimises, so that is what it now claims.
      description: 'Failure-tolerant deployment — commits a spare of every type used, above the minimum needed, so one drone loss cannot stall the mission. Tasks run mostly in series.',
      assets: consBad.displayPool,
      expectedCompletionTime: consBad.displayTime,
      reserveAfter: reserveAfter(consBad.displayPool),
      speedScore: speedScoreFor(consBad.displayTime),
      reserveScore: reserveScoreFor(consBad.displayPool),
      redundancyScore: computeRedundancyScore(consBad.displayPool, consFloor),
      minimumAssets: consMinimumAssets,
      taskComps: consTrueTaskComps,
      isBadSuggestion: consBad.isBad,
      badSuggestionType: consBad.badType,
      badSuggestionColour: consBad.badColour,
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
