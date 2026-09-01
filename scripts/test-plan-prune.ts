// Regression test for the tactical/recovery planner's plan reconciliation (study-v1.6).
// Run: npx tsx scripts/test-plan-prune.ts
//
// Bug: the planner rebuilt its local plan from scratch whenever the drone pool or the task order
// changed. In a recovery the task list IS the mission's unfinished tasks, so an unrelated task
// merely COMPLETING while the operator was mid-drag removed it from `taskOrder`, changed the reset
// key, and wiped every assignment they had made — back to "No drones assigned", Reassign disabled,
// no explanation. It fired during the study-v1.5 browser test: a Supply Drop finished while the
// agent's Suggest was animating in and the whole fix vanished.
//
// `prunePlan` keeps the operator's work and drops only what genuinely no longer exists.
import { prunePlan } from '../src/utils/planPrune'
import type { TacticalPlan } from '../src/types'

let failures = 0
const check = (label: string, cond: boolean, detail = '') => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}${detail ? '  — ' + detail : ''}`)
  if (!cond) failures++
}
const eq = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)

// The shape the browser test hit: mid-recovery, Fast-4 chained across three tasks, two supply
// drops still running with their own drones.
const plan: TacticalPlan = {
  assignments: {
    t_supply1: ['L5', 'L6', 'C4'],
    t_supply2: ['L5', 'L6', 'C4'],
    t_sns:     ['F4', 'L4', 'C3'],
    t_recon:   ['F4'],
    t_recce:   ['F4'],
  },
  chainOrder: {
    F4: ['t_sns', 't_recon', 't_recce'],
    L5: ['t_supply1', 't_supply2'],
    L6: ['t_supply1', 't_supply2'],
    C4: ['t_supply1', 't_supply2'],
  },
}
const POOL = ['F4', 'L4', 'L5', 'L6', 'C3', 'C4']
const ORDER = ['t_supply1', 't_supply2', 't_sns', 't_recon', 't_recce']

// 1. The bug itself: a task completes, everything else survives untouched.
{
  const after = prunePlan(plan, POOL, ORDER.filter(t => t !== 't_supply1'))
  check('a completed task drops out of the plan', after.assignments.t_supply1 === undefined)
  check('the operator\'s work on every OTHER task survives',
    eq(after.assignments.t_sns, ['F4', 'L4', 'C3']) &&
    eq(after.assignments.t_recon, ['F4']) &&
    eq(after.assignments.t_recce, ['F4']) &&
    eq(after.assignments.t_supply2, ['L5', 'L6', 'C4']),
    JSON.stringify(after.assignments))
  check('a chain across surviving tasks is kept whole',
    eq(after.chainOrder.F4, ['t_sns', 't_recon', 't_recce']), JSON.stringify(after.chainOrder.F4))
  check('a chain through the completed task loses only that hop',
    eq(after.chainOrder.L5, ['t_supply2']), JSON.stringify(after.chainOrder.L5))
}

// 2. A drone leaving the pool (a second failure, or a return to reserve) is removed everywhere —
//    the plan must never keep dispatching a drone that is gone.
{
  const after = prunePlan(plan, POOL.filter(d => d !== 'F4'), ORDER)
  check('a drone that left the pool is stripped from every task',
    !Object.values(after.assignments).some(ids => ids.includes('F4')),
    JSON.stringify(after.assignments))
  check('its chain entry goes with it', after.chainOrder.F4 === undefined)
  check('the tasks it was on remain in the plan (blocked, not deleted)',
    eq(after.assignments.t_sns, ['L4', 'C3']) && eq(after.assignments.t_recce, []),
    JSON.stringify(after.assignments))
  check('other drones are untouched by an unrelated drone leaving',
    eq(after.assignments.t_supply1, ['L5', 'L6', 'C4']))
}

// 3. A task appearing in the order (never happens in recovery, but the planner shares this path
//    with the fresh-allocation view) starts empty rather than undefined.
{
  const after = prunePlan(plan, POOL, [...ORDER, 't_new'])
  check('a new task gets an empty entry, not undefined', eq(after.assignments.t_new, []))
}

// 4. No-op prune is genuinely a no-op — pruning must never quietly reorder or drop anything.
{
  const after = prunePlan(plan, POOL, ORDER)
  check('pruning against an unchanged pool/order preserves the plan exactly',
    eq(after.assignments, plan.assignments) && eq(after.chainOrder, plan.chainOrder),
    JSON.stringify(after))
}

// 5. A chain hop is dropped when the drone is no longer assigned to that task, so a stale entry
//    can't resurrect the drone in `droneSequences`.
{
  const stale: TacticalPlan = {
    assignments: { t_a: ['F4'], t_b: [] },
    chainOrder: { F4: ['t_a', 't_b'] },
  }
  const after = prunePlan(stale, ['F4'], ['t_a', 't_b'])
  check('a chain hop to a task the drone is not assigned to is dropped',
    eq(after.chainOrder.F4, ['t_a']), JSON.stringify(after.chainOrder))
}

console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILED`)
process.exit(failures === 0 ? 0 : 1)
