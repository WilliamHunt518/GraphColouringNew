// The tutorial's two scripted drone failures must land the way their lesson cards describe:
//
//   step 32 "Reassign Now"     — the operator CAN cover the gap with the surviving subswarm
//   step 36 "Abort the Mission" — they CANNOT, so "Abandon Mission" is genuinely the only way out
//
// Before this was pinned, both picked a drone by position in a list: the first failure could take
// the training team's only Lifter (stranding a supply drop, so the recovery step had nothing to
// reassign) and the abort scenario could take a duplicated type (leaving a fix one drag away while
// the card insisted on aborting).
//
// Run: npx tsx scripts/test-tutorial-failure-demo.ts
import { buildInitialState, gameReducer } from '../src/store/gameReducer'
import { recoveryFeasible, onMissionDrones, unfinishedTasks, taskCoverableBy } from '../src/utils/coverage'
import { computeRecoverySuggestion } from '../src/utils/tacticalSuggest'
import type { GameState, StudyConfig, Mission } from '../src/types'

let failures = 0
const check = (label: string, cond: boolean, detail = '') => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}${detail ? '  — ' + detail : ''}`)
  if (!cond) failures++
}

const config: StudyConfig = {
  participantId: 'TUT', condition: 'none', mode: 'agent', complexity: 'balanced',
  seed: 42, agentErrorRate: 0, epsilonTactical: 0, tacticalMode: 'plan-all',
  testingMode: true,        // suppresses the scheduled failure roll, so only the scripted ones fire
  tutorialMode: true, fixLockouts: false, numSessions: 1,
}

const tick = (s: GameState, sec: number) => gameReducer(s, { type: 'TICK', nowMs: sec * 1000 } as any)
const mission = (s: GameState): Mission => s.missions[0]
const team = (s: GameState) => onMissionDrones(mission(s), s.assets)
  .map(a => a.type[0]).sort().join('')

// ── Walk the tutorial up to a deployed training mission ───────────────────
let s: GameState = { ...buildInitialState(config), phase: 'playing' }
s = tick(s, 0)
s = gameReducer(s, { type: 'FORCE_MISSION_ARRIVAL' } as any)
const missionId = s.missions[0].id
s = gameReducer(s, { type: 'OPEN_STRATEGIC', missionId } as any)
s = gameReducer(s, { type: 'PICK_STRATEGY', strategyIndex: 0 } as any)
s = gameReducer(s, {
  type: 'APPLY_STRATEGIC', missionId, source: 'agent', strategyIndex: 0, manualAllocation: null,
} as any)
// Step 14 swaps in the fixed 2 Fast + 1 Lifter + 1 Camera training team.
s = gameReducer(s, { type: 'TUTORIAL_OVERRIDE_TEAM' } as any)
check('training team is 2 Fast + 1 Lifter + 1 Camera', team(s) === 'BBGR', team(s))

// Deploy the plan the override built (the operator's own drags land in the same shape). The
// planner always sends per-drone sequences alongside the assignments; without them the reducer
// has no start times to converge on and drops the plan.
const plan = mission(s).pendingAllocation!
const sequences = (assignments: Record<string, string[]>, order: string[]) => {
  const out: Record<string, string[]> = {}
  for (const tid of order) for (const id of assignments[tid] ?? []) (out[id] ??= []).push(tid)
  return out
}
s = gameReducer(s, {
  type: 'CONFIRM_TACTICAL', missionId,
  taskAssignments: plan.taskAssignments,
  droneSequences: sequences(plan.taskAssignments, plan.taskOrder),
} as any)
for (let e = 1; e <= 400 && mission(s).status === 'active' &&
     !mission(s).tasks.some(t => t.status === 'executing'); e++) s = tick(s, e)
check('mission is live with work under way', mission(s).status === 'active' &&
  mission(s).tasks.some(t => t.status === 'executing'),
  `${mission(s).status}: ${mission(s).tasks.map(t => `${t.id}=${t.status}`).join(' ')}`)

// ── Act 1: the recoverable failure (step 32) ──────────────────────────────
s = gameReducer(s, { type: 'TUTORIAL_FORCE_FAILURE' } as any)
const m1 = mission(s)
check('act 1: mission is flagged for recovery', m1.failureRecoveryPending === true &&
  m1.recoveryReason === 'drone_failure' && m1.failedDroneId !== null)
check('act 1: at least one task is uncovered to reassign',
  m1.tasks.some(t => t.status === 'pending' && t.assignedAssetIds.length === 0))
check('act 1: EVERY remaining task can still be covered — "Reassign ✓" is reachable',
  recoveryFeasible(m1, s.assets),
  unfinishedTasks(m1).filter(t => !taskCoverableBy(t, onMissionDrones(m1, s.assets)))
    .map(t => `${t.id}(T${t.type})`).join(',') || 'all coverable')

// The operator re-plans exactly as the recovery planner's Suggest would: the on-mission pool
// covers the uncovered tasks, existing assignments left alone.
const recoveryPool = onMissionDrones(m1, s.assets).map(a => a.id)
const recoveryOrder = unfinishedTasks(m1).map(t => t.id)
const recoveryPlan: Record<string, string[]> = Object.fromEntries(unfinishedTasks(m1)
  .map(t => [t.id, t.assignedAssetIds.filter(id => recoveryPool.includes(id))]))
const suggested = computeRecoverySuggestion(
  m1,
  { ...m1.pendingAllocation!, dronePool: recoveryPool, taskOrder: recoveryOrder, taskAssignments: recoveryPlan },
  s.assets,
)
for (const [tid, ids] of Object.entries(suggested)) recoveryPlan[tid] = ids
s = gameReducer(s, {
  type: 'CONFIRM_FAILURE_RECOVERY', missionId,
  taskAssignments: recoveryPlan,
  droneSequences: sequences(recoveryPlan, recoveryOrder),
} as any)
check('act 1: recovery clears the help-needed flag', mission(s).failureRecoveryPending === false)

// ── Act 2: the unrecoverable failure (step 36) ────────────────────────────
for (let e = 401; e <= 430; e++) s = tick(s, e)
const beforeAbort = mission(s)
s = gameReducer(s, { type: 'TUTORIAL_FORCE_ABANDON_SCENARIO' } as any)
const m2 = mission(s)

if (beforeAbort.status !== 'active') {
  check('act 2: mission finished before the abort lesson — scenario correctly declined', !m2.failureRecoveryPending)
} else {
  check('act 2: mission is flagged for recovery', m2.failureRecoveryPending === true &&
    m2.recoveryReason === 'drone_failure' && m2.failedDroneId !== null)
  const stranded = unfinishedTasks(m2).filter(t => !taskCoverableBy(t, onMissionDrones(m2, s.assets)))
  check('act 2: some remaining task CANNOT be covered — "Reassign" stays disabled, abort is the only way out',
    stranded.length > 0,
    stranded.map(t => `${t.id}(T${t.type})`).join(',') || 'everything still coverable')
  check('act 2: the stranded task is on the board as pending, not silently failed',
    stranded.every(t => t.status === 'pending'))

  // And the lesson's ending works: abandoning resolves the mission.
  s = gameReducer(s, { type: 'ABANDON_MISSION', missionId } as any)
  check('act 2: abandoning clears the recovery flag', mission(s).status === 'abandoned' &&
    mission(s).failureRecoveryPending === false)
}

console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILED`)
process.exit(failures === 0 ? 0 : 1)
