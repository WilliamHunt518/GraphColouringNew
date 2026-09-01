// Tactical / recovery suggestion helpers (React-free so they can be unit-tested).
// Mirrors the reducer's greedyAssign logic for the "Suggest" button in the tactical planner.
import type { Asset, AssetType, Mission, PendingAllocation, TaskType } from '../types'
import { HUB, ASSET_SPEED, TASK_PRIMARY, TASK_BASE_TIME, TASK_SUBSTITUTE, TASK_SUB_BASE_TIME } from './missionGen'
import { taskCoverableBy } from './coverage'

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
