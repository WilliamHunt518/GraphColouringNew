// Tactical / recovery suggestion helpers (React-free so they can be unit-tested).
// Mirrors the reducer's greedyAssign logic for the "Suggest" button in the tactical planner.
import type { Asset, AssetType, Mission, PendingAllocation, TaskType } from '../types'
import { HUB, ASSET_SPEED, TASK_PRIMARY, TASK_BASE_TIME, TASK_SUBSTITUTE, TASK_SUB_BASE_TIME } from './missionGen'

export function computeTacticalSuggestion(
  dronePool: string[],
  taskOrder: string[],
  tasks: Mission['tasks'],
  assets: Asset[],
  greedy = false,
): Record<string, string[]> {
  const assetById = new Map(assets.map(a => [a.id, a]))
  const freeAt: Record<string, number> = Object.fromEntries(dronePool.map(id => [id, 0]))
  const freePos: Record<string, { x: number; y: number }> = Object.fromEntries(dronePool.map(id => [id, { ...HUB }]))
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
      const pickEarliest = (type: AssetType, n: number) =>
        dronePool
          .filter(id => assetById.get(id)?.type === type && (!greedy || !used.has(id)))
          .sort((a, b) => freeAt[a] - freeAt[b])
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

// Recovery suggestion: the agent proposes a fix for a drone-failure/lockout recovery. It only
// (re)plans the tasks that still need coverage (status 'pending') and only uses the idle on-mission
// drones — drones busy on other tasks are left running. This mirrors what CONFIRM_FAILURE_RECOVERY
// actually commits (it reassigns pending tasks only), so the Suggest preview matches the outcome.
export function computeRecoverySuggestion(
  mission: Mission,
  pending: PendingAllocation,
  assets: Asset[],
): Record<string, string[]> {
  const assetById = new Map(assets.map(a => [a.id, a]))
  const pendingTasks = pending.taskOrder.filter(
    tid => mission.tasks.find(t => t.id === tid)?.status === 'pending'
  )
  const idlePool = pending.dronePool.filter(id => {
    const a = assetById.get(id)
    if (!a) return false
    if (a.currentTaskId == null) return true            // loitering / freed after failure or lockout
    const t = mission.tasks.find(tt => tt.id === a.currentTaskId)
    return !t || t.status === 'pending'                  // not actually busy on a running task
  })
  // Recovery ALWAYS chains (plan-all), never greedy consume-once. Completing the remaining tasks
  // with a limited on-mission drone set inherently needs drones shared across tasks — that's the
  // whole shape of a lockout (two tasks sharing the same Blue+Red, e.g. two T5s with no substitute).
  // Greedy would assign each shared drone to only ONE task, leaving the other unstaffed, so the
  // "fix" would be undeployable (Deploy stays disabled). Chaining routes the shared drones through
  // both tasks in canonical order → every task covered → acyclic → deployable.
  return computeTacticalSuggestion(idlePool, pendingTasks, mission.tasks, assets, /* greedy */ false)
}
