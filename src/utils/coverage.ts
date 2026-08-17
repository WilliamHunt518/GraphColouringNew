import type { Asset, AssetRequirement, Mission, Task, TaskType } from '../types'
import { TASK_PRIMARY, TASK_SUBSTITUTE } from './missionGen'

/** Drone counts by type. */
export function countByType(assets: Asset[]): AssetRequirement {
  const c: AssetRequirement = { Blue: 0, Red: 0, Green: 0 }
  for (const a of assets) c[a.type]++
  return c
}

/**
 * Can `task` still be executed by a team drawn from `pool`?
 *
 * Deliberately mirrors the tactical planner's Deploy/Reassign gate (primary OR substitute
 * composition, WITHOUT the section-credit exemptions `taskMeetsComposition` grants) — so a task
 * this returns false for is one the operator physically cannot cover: the planner will sit on
 * "Reassign (incomplete)" no matter how they drag. Being the stricter of the two rules, a false
 * here always implies a disabled Reassign.
 */
export function taskCoverableBy(task: Task, pool: Asset[]): boolean {
  const counts = countByType(pool)
  const prim = TASK_PRIMARY[task.type as TaskType]
  const sub = TASK_SUBSTITUTE[task.type as TaskType]
  const meets = (c: AssetRequirement) =>
    counts.Blue >= c.Blue && counts.Red >= c.Red && counts.Green >= c.Green
  return meets(prim) || (!!sub && meets(sub))
}

/** Tasks still to be done — the rows the recovery planner shows. */
export function unfinishedTasks(mission: Mission): Task[] {
  return mission.tasks.filter(t => t.status !== 'completed' && t.status !== 'failed')
}

/** The drones a recovery plan may draw on: this mission's subswarm, never the hub reserve. */
export function onMissionDrones(mission: Mission, assets: Asset[]): Asset[] {
  return assets.filter(a => a.currentMissionId === mission.id && a.status === 'deployed')
}

/**
 * Can the operator still fix this mission with the drones left on it? False means every route
 * out except "Abandon Mission" is closed — which is exactly when the tutorial's abort lesson is
 * truthful, and when a recovery step must stop demanding a reassignment.
 */
export function recoveryFeasible(mission: Mission, assets: Asset[]): boolean {
  const pool = onMissionDrones(mission, assets)
  return unfinishedTasks(mission).every(t => taskCoverableBy(t, pool))
}
