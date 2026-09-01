import type { TacticalPlan } from '../types'

/**
 * Reconcile a half-built tactical/recovery plan with a pool and task list that moved underneath it.
 *
 * The tactical planner used to REBUILD its local `assignments` from scratch whenever the drone pool
 * or the task order changed. In a failure recovery that was destructive: the planner's task list is
 * the mission's unfinished tasks, so an unrelated task simply *completing* while the operator was
 * still dragging removed it from `taskOrder`, changed the reset key, and wiped every assignment
 * they had made — the plan went back to "No drones assigned" and Reassign went disabled with no
 * explanation. A recovery routinely runs 30 s+ while the mission's other tasks are still finishing,
 * so it was easy to hit (it fired mid-run during the study-v1.5 browser test).
 *
 * Pruning keeps the operator's work and drops only what genuinely no longer exists:
 *   - tasks that have left `taskOrder` (completed, failed) lose their entry entirely;
 *   - tasks that are new to `taskOrder` start empty;
 *   - drones that have left `dronePool` (failed, returned to reserve) are removed everywhere.
 *
 * Nothing here needs to *validate* the result: the planner's Deploy/Reassign gate re-derives
 * coverage from the live plan on every render, so a plan left short by a prune is already blocked.
 *
 * Switching mission or planner mode remounts the planner (see the `key` on TacticalPlannerView),
 * so this only ever runs within a single plan the operator is actively building.
 */
export function prunePlan(
  plan: TacticalPlan,
  dronePool: readonly string[],
  taskOrder: readonly string[],
): TacticalPlan {
  const poolSet = new Set(dronePool)
  const taskSet = new Set(taskOrder)

  const assignments: Record<string, string[]> = {}
  for (const taskId of taskOrder) {
    assignments[taskId] = (plan.assignments[taskId] ?? []).filter(id => poolSet.has(id))
  }

  const chainOrder: Record<string, string[]> = {}
  for (const [droneId, seq] of Object.entries(plan.chainOrder)) {
    if (!poolSet.has(droneId)) continue
    // Keep only hops that still exist AND that the drone is still assigned to — a chain entry
    // pointing at a task the drone has been pruned off would resurrect it in `droneSequences`.
    const kept = seq.filter(taskId => taskSet.has(taskId) && assignments[taskId]?.includes(droneId))
    if (kept.length > 0) chainOrder[droneId] = kept
  }

  return { assignments, chainOrder }
}
