// Regression test: a task deployed on its SUBSTITUTE composition must be allowed to run.
// Run: npx tsx scripts/test-substitute-composition.ts
//
// The tactical planner offers each task a substitute ("OR 1F (38s)" under a 2F Recon) and the
// Deploy gate in coverage.ts accepts it, so an operator — or the agent, via pickDronesForTask's
// fallback when the reserve is thin — can legitimately staff a task with fewer drones than the
// primary composition.
//
// Until study-v1.4 the sections-by-colour safety net in TICK step 2 compared presence against
// TASK_PRIMARY regardless of `task.useSubstitute`, so EVERY substitute-staffed task failed on its
// first executing tick — and was logged as `task_failed(reason: 'drone_failure')` with no drone
// having failed and no `drone_failure` event to join against. Observed live in a full browser run
// (P-CHROME1, 2026-08-24) before it was found.
import { buildInitialState, gameReducer } from '../src/store/gameReducer'
import type { GameState, StudyConfig, Mission, Task, Asset } from '../src/types'
import { TASK_SUB_BASE_TIME, TASK_BASE_TIME } from '../src/utils/missionGen'

let failures = 0
const check = (label: string, cond: boolean) => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}`)
  if (!cond) failures++
}

const config: StudyConfig = {
  participantId: 'TEST', condition: 'HH', mode: 'agent', complexity: 'balanced',
  seed: 1, agentErrorRate: 0, epsilonTactical: 0, tacticalMode: 'plan-all',
  testingMode: true,          // no ambient drone failures — isolates the section safety net
  tutorialMode: false, numSessions: 1,
}
const WP = { x: 700, y: 400 }

function task(id: string, type: number, assigned: string[], baseTime: number, useSubstitute: boolean): Task {
  return {
    id, missionId: 'M1', type, status: 'traveling', assignedAssetIds: assigned, waypoint: WP,
    allocatedAt: 0, travelTime: 5, baseTime, useSubstitute,
    startTime: 5, completionTime: 5 + baseTime, recallDelay: 0, completedSectionTypes: [],
  } as unknown as Task
}

function drone(id: string, type: 'Blue' | 'Red' | 'Green', curTask: string): Asset {
  return {
    id, type, status: 'deployed', currentMissionId: 'M1', currentTaskId: curTask,
    position: { ...WP }, travelFrom: { ...WP }, targetPosition: { ...WP },
    travelStartElapsed: 0, travelEndElapsed: 0, availableAt: 0, failedAt: null, replacementAt: null,
  } as unknown as Asset
}

function mission(t: Task): Mission {
  return {
    id: 'M1', category: 'C', status: 'active', zoneCenter: WP, zoneRadius: 80, tasks: [t],
    arrivalTime: 0, allocationTime: 0, completionTime: null,
    agentInteraction: 'manual', chosenStrategyName: 'Manual', manualPriorityIds: [],
    tacticalPending: false, pendingAllocation: null, tacticalOpenedAtMs: null,
    droneSequences: Object.fromEntries(t.assignedAssetIds.map(a => [a, [t.id]])),
    droneFailuresFired: 0, failedDroneId: null, failureRecoveryPending: false, pendingRecoveryOptions: null,
    tacticallySuppressedTaskId: null, abandonedAt: null, isResidual: false, needsGreedyReplan: false,
  } as unknown as Mission
}

const tick = (s: GameState, e: number) => gameReducer(s, { type: 'TICK', nowMs: e * 1000 } as any)

function run(label: string, t: Task, assets: Asset[]) {
  let s: GameState = {
    ...buildInitialState(config), config, phase: 'playing', sessionStartMs: 0, elapsed: 0,
    missions: [mission(t)], assets,
  }
  for (let e = 1; e <= 130 && !['completed', 'failed'].includes(s.missions[0].tasks[0].status); e++) s = tick(s, e)
  const final = s.missions[0].tasks[0].status
  const phantom = s.events[0].filter((e: any) => e.type === 'task_failed' && e.reason === 'drone_failure')
  check(`${label} completes`, final === 'completed')
  check(`${label} logs no phantom drone_failure`, phantom.length === 0)
}

// Control: primary compositions must still work (and the safety net must still be armed for them).
run('T2 Recon on PRIMARY 2F  ', task('t2p', 2, ['B1', 'B2'], TASK_BASE_TIME[2], false),
  [drone('B1', 'Blue', 't2p'), drone('B2', 'Blue', 't2p')])

// The regression: every substitute the planner offers.
run('T2 Recon on SUB 1F      ', task('t2s', 2, ['B1'], TASK_SUB_BASE_TIME[2], true),
  [drone('B1', 'Blue', 't2s')])
run('T3 Supply on SUB 1L+1C  ', task('t3s', 3, ['R1', 'G1'], TASK_SUB_BASE_TIME[3], true),
  [drone('R1', 'Red', 't3s'), drone('G1', 'Green', 't3s')])
run('T4 Precision on SUB 1L+1C', task('t4s', 4, ['R1', 'G1'], TASK_SUB_BASE_TIME[4], true),
  [drone('R1', 'Red', 't4s'), drone('G1', 'Green', 't4s')])

// The safety net itself must still bite: a task whose drone genuinely vanished still fails.
{
  let s: GameState = {
    ...buildInitialState(config), config, phase: 'playing', sessionStartMs: 0, elapsed: 0,
    missions: [mission(task('t2u', 2, ['B1', 'B2'], TASK_BASE_TIME[2], false))],
    // Only ONE of the two Blues the primary composition needs is actually on the task.
    assets: [drone('B1', 'Blue', 't2u'), { ...drone('B2', 'Blue', 't2u'), currentTaskId: null }],
  }
  for (let e = 1; e <= 40 && s.missions[0].tasks[0].status !== 'failed'; e++) s = tick(s, e)
  check('understaffed PRIMARY still fails (net still armed)', s.missions[0].tasks[0].status === 'failed')
}

console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILED`)
process.exit(failures === 0 ? 0 : 1)
