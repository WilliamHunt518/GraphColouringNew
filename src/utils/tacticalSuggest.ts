// Tactical / recovery suggestion helpers (React-free so they can be unit-tested).
// Mirrors the reducer's greedyAssign logic for the "Suggest" button in the tactical planner.
import type { Asset, AssetType, Mission, PendingAllocation, Task, TaskType } from '../types'
import { HUB, ASSET_SPEED, TASK_PRIMARY, TASK_BASE_TIME, TASK_SUBSTITUTE, TASK_SUB_BASE_TIME } from './missionGen'
import { taskCoverableBy } from './coverage'
import type { SeededRNG } from './prng'

export function computeTacticalSuggestion(
  dronePool: string[],
  taskOrder: string[],
  tasks: Mission['tasks'],
  assets: Asset[],
  greedy = false,
  // Recovery only: start each drone from where it ACTUALLY is (already on-mission, often parked at
  // a waypoint) instead of the hub, and prefer the drone that can reach the task soonest. The
  // pre-deploy planner keeps the hub origin so its preview matches greedyAssign in the reducer,
  // which is what actually gets committed.
  useLivePositions = false,
): Record<string, string[]> {
  const assetById = new Map(assets.map(a => [a.id, a]))
  const freeAt: Record<string, number> = Object.fromEntries(dronePool.map(id => [id, 0]))
  const originOf = (id: string) => {
    const a = assetById.get(id)
    return (useLivePositions && a && a.status === 'deployed') ? { ...a.position } : { ...HUB }
  }
  const freePos: Record<string, { x: number; y: number }> = Object.fromEntries(dronePool.map(id => [id, originOf(id)]))
  const result: Record<string, string[]> = {}
  // Greedy: engage EVERY drone in the first wave by covering as many tasks as possible in
  // parallel, one drone per task (no chaining onto future tasks). Tasks the pool can't cover
  // now stay empty and are filled by replanning as drones free up. Non-greedy keeps the old
  // behaviour: chain drones through the whole task order.
  const used = new Set<string>()

  for (const tid of taskOrder) {
    const task = tasks.find(t => t.id === tid)
    if (!task) continue
    const prim = TASK_PRIMARY[task.type as TaskType]
    const sub = TASK_SUBSTITUTE[task.type as TaskType]

    const tryAssign = (req: { Blue: number; Red: number; Green: number }, baseTime: number): boolean => {
      // Arrival = when the drone is free again + how long it takes to get here from wherever it
      // will be then. With hub origins that collapses to freeAt (every drone is equidistant at
      // the start), so this only changes ordering in the live-position (recovery) case.
      const arrivalAt = (id: string) => {
        const asset = assetById.get(id)
        if (!asset) return Infinity
        return freeAt[id] + Math.hypot(freePos[id].x - task.waypoint.x, freePos[id].y - task.waypoint.y) / ASSET_SPEED[asset.type]
      }
      const pickEarliest = (type: AssetType, n: number) =>
        dronePool
          .filter(id => assetById.get(id)?.type === type && (!greedy || !used.has(id)))
          .sort((a, b) => useLivePositions ? arrivalAt(a) - arrivalAt(b) : freeAt[a] - freeAt[b])
          .slice(0, n)

      const blues = pickEarliest('Blue', req.Blue)
      const reds = pickEarliest('Red', req.Red)
      const greens = pickEarliest('Green', req.Green)
      if (blues.length < req.Blue || reds.length < req.Red || greens.length < req.Green) return false

      const picked = [...blues, ...reds, ...greens]
      const startTime = Math.max(...picked.map(id => {
        const asset = assetById.get(id)!
        const tt = Math.hypot(freePos[id].x - task.waypoint.x, freePos[id].y - task.waypoint.y) / ASSET_SPEED[asset.type]
        return freeAt[id] + tt
      }))
      for (const id of picked) {
        freeAt[id] = startTime + baseTime
        freePos[id] = { ...task.waypoint }
        if (greedy) used.add(id)   // consume-once: one task per drone this wave
      }
      result[tid] = picked
      return true
    }

    if (!tryAssign(prim, TASK_BASE_TIME[task.type as TaskType])) {
      if (sub) tryAssign(sub, TASK_SUB_BASE_TIME[task.type as TaskType])
    }
  }
  return result
}

// ─── ε_Tactical route failure (study-v1.10) ────────────────────────────────

// Tunable via testing mode (state.config.testingMode) — see docs/STUDY_BUILD.md §17 for why these
// aren't the "5-10" first sketched: every droneSequences entry is a FULL task-dwell (buildManualAssignments
// keeps a drone at a task for its whole baseTime, not a cheap waypoint pass), so even a handful of
// detours is already a large delay relative to TASK_BASE_TIME (10-45s) and the 480s session.
export const TACTICAL_FAILURE_MIN_HOPS = 2
export const TACTICAL_FAILURE_MAX_HOPS = 4

/**
 * Builds the agent's suggested (bad) plan when ε_Tactical fires for a mission (study-v1.10).
 *
 * Every task keeps its correct composition — nothing is ever dropped. Every drone that has ≥1 real
 * task gets a random walk of TACTICAL_FAILURE_MIN_HOPS–MAX_HOPS detour tasks through the mission's
 * own tasks (with replacement) prefixed onto its route, `droneSequences[droneId]`, with its real
 * task(s) unconditionally appended after — coverage is guaranteed by construction, not
 * probabilistically checked-and-patched, which is what makes "one task at the end of each drone's
 * path" literally true, and the full walk is what's logged (`tactical_opened.agentDroneSequences`,
 * the testing-mode hop-count badge) so the "how elaborate was the bad route" story is visible even
 * though most of it never actually executes — see below.
 *
 * ONLY THE FIRST detour is added to the returned `taskAssignments` as a redundant extra member
 * (harmless: composition checks throughout this codebase are "at least N", so an extra drone never
 * changes a task's baseTime or substitute/primary choice — see taskMeetsComposition/getManualBaseTime).
 * The rest of the walk is real data (returned in `droneSequences`) but deliberately never lands in
 * `taskAssignments`, and thus never gets deployed — MapDisplay's planner already filters a drone's
 * chain order down to tasks it's genuinely a `taskAssignments` member of
 * (`userOrder.filter(tid => assignments[tid]?.includes(id))` in the `droneSequences` memo), so a
 * detour absent from `taskAssignments` is silently dropped from what's actually committed at Deploy
 * time. This is deliberate, not a leftover bug: every `droneSequences` entry that DOES execute costs
 * a FULL task baseTime (10–45s, not a cheap waypoint pass — see buildManualAssignments), so playing
 * out every drawn hop could ADD MINUTES to a single drone's route and, worse, a redundant drone's
 * late arrival at another task can push back that task's real completion for its actually-required
 * drones too (`taskStarts` takes the MAX arrival across every drone referencing a task, redundant or
 * not). Capping real execution to one hop bounds the delay to a single task and isolates it to the
 * detouring drone alone — "a lazy operator won't notice and it won't take ages" — while the full
 * walk stays visible in the data for anyone checking how severe the underlying random walk is.
 *
 * The augmentation has to land IN `taskAssignments` (not just in the returned route) for the one hop
 * that IS real, because that's what the tactical planner's "Suggest" button hands the operator
 * wholesale when a failure fired (MapDisplay.tsx handleSuggest) instead of recomputing a fresh,
 * uncorrupted plan the way it does when no failure fired.
 *
 * If a real cross-drone scheduling cycle somehow still forms (e.g. across two drones' single real
 * detours), the existing live TICK deadlock detector (findSchedulingCycle/rerouteDeadlock in
 * gameReducer.ts, default-on via fixLockouts) reroutes it exactly as it would an operator-built one —
 * nothing extra is needed here.
 *
 * Drones with no real task (pure redundancy spares, not in `taskAssignments` at all) are left out —
 * applyTacticalAllocation's loiter-all path never consults droneSequences for them, so a walk would
 * be silently discarded anyway.
 */
export function buildTacticalFailurePlan(
  tasks: Task[],
  taskAssignments: Record<string, string[]>,
  rng: SeededRNG,
  minHops = TACTICAL_FAILURE_MIN_HOPS,
  maxHops = TACTICAL_FAILURE_MAX_HOPS,
): { taskAssignments: Record<string, string[]>; droneSequences: Record<string, string[]> } {
  const taskIds = tasks.map(t => t.id)
  if (taskIds.length === 0) return { taskAssignments, droneSequences: {} }

  // Real task(s) per drone, in the tasks' own relative order (mirrors how a correct plan would
  // naturally sequence a reused drone across more than one task).
  const realTasksByDrone = new Map<string, string[]>()
  for (const tid of taskIds) {
    for (const droneId of (taskAssignments[tid] ?? [])) {
      const list = realTasksByDrone.get(droneId)
      if (list) list.push(tid)
      else realTasksByDrone.set(droneId, [tid])
    }
  }

  const augmented: Record<string, string[]> = Object.fromEntries(
    Object.entries(taskAssignments).map(([tid, ids]) => [tid, [...ids]])
  )
  const droneSequences: Record<string, string[]> = {}
  for (const [droneId, real] of realTasksByDrone) {
    const steps = rng.randInt(minHops, maxHops + 1)   // randInt is exclusive of its upper bound

    // The FIRST detour must avoid the drone's own real task(s) — landing there would put the same
    // task at both the front (as a "detour") and the tail (for real), a duplicate MapDisplay's
    // planner would deploy as two separate dwells on the same task. If nothing is eligible (e.g. a
    // 1-task mission), this drone simply gets no detour — a mission too small for the failure to
    // have anywhere to put one.
    const realSet = new Set(real)
    const firstCandidates = taskIds.filter(t => !realSet.has(t))
    if (firstCandidates.length === 0) { droneSequences[droneId] = [...real]; continue }
    const first = firstCandidates[rng.randInt(0, firstCandidates.length)]

    // Every LATER draw excludes both the real tasks AND `first` itself — those are the only two
    // task ids that carry real taskAssignments membership for this drone, so excluding them
    // guarantees none of these later "decorative" draws can coincidentally leak through
    // MapDisplay's droneSequences filter as a second, duplicate dwell on an already-real task (see
    // the docstring above for why only `first` is meant to ever actually execute).
    const laterCandidates = taskIds.filter(t => t !== first && !realSet.has(t))
    const detours = [first]
    for (let i = 1; i < steps; i++) {
      if (laterCandidates.length === 0) break   // nothing left to decorate with — stop early, harmless
      detours.push(laterCandidates[rng.randInt(0, laterCandidates.length)])
    }

    // Only detours[0] (`first`) becomes a real (redundant) assignment — see docstring for why the
    // rest stay logged-only rather than deployed.
    const held = (augmented[first] ??= [])
    if (!held.includes(droneId)) held.push(droneId)
    droneSequences[droneId] = [...detours, ...real]
  }
  return { taskAssignments: augmented, droneSequences }
}

/**
 * Recovery suggestion: the agent proposes a fix for a drone-failure / lockout recovery.
 *
 * It re-plans only the pending tasks whose CURRENT plan is short of a workable composition, and
 * draws on every drone on the mission except those actually executing a task — chaining a drone
 * that is already booked on another pending task onto the short one is exactly the repair an
 * operator makes by hand (shift+drag), and is legal because the recovery planner's sequences
 * follow one global task order and so can never be cyclic.
 *
 * Before study-v1.5 the pool was only the drones that happened to be idle, which after a failure
 * was the broken task's survivors — by construction one drone short of the composition that had
 * just broken. `tryAssign` therefore failed for every task and the whole function returned `{}`,
 * so clicking "Suggest" during a recovery visibly did nothing. (The reducer now also parks the
 * mission's other unstarted drones at failure time — see suspendUnstartedPlan — so this pool is
 * genuinely available rather than mid-flight elsewhere.)
 *
 * Recovery ALWAYS chains (plan-all), never greedy consume-once. Completing the remaining tasks
 * with a limited on-mission drone set inherently needs drones shared across tasks — that's the
 * whole shape of a lockout (two tasks sharing the same Blue+Red, e.g. two T5s with no substitute).
 * Greedy would assign each shared drone to only ONE task, leaving the other unstaffed, so the
 * "fix" would be undeployable (Deploy stays disabled).
 */
export function computeRecoverySuggestion(
  mission: Mission,
  pending: PendingAllocation,
  assets: Asset[],
  // The plan as it stands in the planner right now (the operator may have edited it since it
  // opened). Falls back to the allocation the planner was seeded with.
  currentAssignments?: Record<string, string[]>,
): Record<string, string[]> {
  const assetById = new Map(assets.map(a => [a.id, a]))
  const taskById = new Map(mission.tasks.map(t => [t.id, t]))
  const current = currentAssignments ?? pending.taskAssignments ?? {}

  const pendingTasks = pending.taskOrder.filter(tid => taskById.get(tid)?.status === 'pending')
  // Tasks already staffed in the current plan are left untouched — handleSuggest only clears the
  // tasks the agent returns, so the operator's work survives and the reveal animation stays short.
  const short = pendingTasks.filter(tid => {
    const task = taskById.get(tid)!
    const held = (current[tid] ?? []).map(id => assetById.get(id)).filter((a): a is Asset => !!a)
    return !taskCoverableBy(task, held)
  })
  if (short.length === 0) return {}

  const pool = pending.dronePool.filter(id => {
    const a = assetById.get(id)
    if (!a) return false
    if (a.currentTaskId == null) return true                  // loitering / freed after failure or lockout
    const t = taskById.get(a.currentTaskId)
    return !t || t.status !== 'executing'                     // not actively working a task
  })

  return computeTacticalSuggestion(pool, short, mission.tasks, assets, /* greedy */ false, /* useLivePositions */ true)
}
