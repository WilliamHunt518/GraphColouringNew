// Focused test for the LIVE cross-drone scheduling-deadlock handling (gameReducer TICK step 3c).
// Run: npx tsx scripts/test-scheduling-deadlock.ts
//
// Scenario: two T5 tasks (each needs 1 Fast + 1 Lifter + 1 Camera) sharing one Fast (B1) and one
// Lifter (R1). The operator chained them into a deadlock:
//   Fast  B1 : t5a -> t5b     (does t5a first)
//   Lifter R1: t5b -> t5a     (does t5b first)
// So t5a waits on R1 (busy with t5b) and t5b waits on B1 (busy with t5a) — neither can ever start.
// The drones have already flown out and are sitting idle at their first waypoints (deadlocked).
//
// fixLockouts ON (the default, and what the study runs): reroute both drones onto one order → BOTH
//                          tasks complete, NOTHING fails.
// fixLockouts OFF (?fixLockouts=0): surface it as "help needed" for the operator to re-plan.
// Both branches are passed explicitly here, so this test is unaffected by the default.
import { buildInitialState, gameReducer } from '../src/store/gameReducer'
import type { GameState, StudyConfig, Mission, Task, Asset } from '../src/types'

let failures = 0
const check = (label: string, cond: boolean) => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}`)
  if (!cond) failures++
}

const config: StudyConfig = {
  participantId: 'TEST', condition: 'HH', mode: 'agent', complexity: 'balanced',
  seed: 1, agentErrorRate: 0.1, epsilonTactical: 0.1, tacticalMode: 'plan-all',
  testingMode: true,            // suppress scheduled drone failures so we isolate the deadlock path
  tutorialMode: false, numSessions: 1,
}

const WP_A = { x: 700, y: 400 }
const WP_B = { x: 760, y: 440 }

function t5(id: string, waypoint: { x: number; y: number }, assigned: string[]): Task {
  return {
    id, missionId: 'M1', type: 5, status: 'traveling',
    assignedAssetIds: assigned, waypoint,
    allocatedAt: 0, travelTime: 500, baseTime: 45, useSubstitute: false,
    startTime: 500, completionTime: 545, recallDelay: 0,   // inflated start (cycle never converged)
    completedSectionTypes: [],
  } as unknown as Task
}

// deployed + already ARRIVED at `at` (travelEndElapsed in the past), idle (task not executing)
function drone(id: string, type: 'Blue' | 'Red' | 'Green', at: { x: number; y: number }, curTask: string): Asset {
  return {
    id, type, status: 'deployed', currentMissionId: 'M1', currentTaskId: curTask,
    position: { ...at }, travelFrom: { ...at }, targetPosition: { ...at },
    travelStartElapsed: 0, travelEndElapsed: 0, availableAt: 0,
    failedAt: null, replacementAt: null,
  } as unknown as Asset
}

function deadlockMission(): Mission {
  return {
    id: 'M1', category: 'C', status: 'active', zoneCenter: WP_A, zoneRadius: 80,
    tasks: [t5('t5a', WP_A, ['B1', 'R1', 'G1']), t5('t5b', WP_B, ['B1', 'R1', 'G2'])],
    arrivalTime: 0, allocationTime: 0, completionTime: null,
    agentInteraction: 'manual', chosenStrategyName: 'Manual', manualPriorityIds: [],
    tacticalPending: false, pendingAllocation: null, tacticalOpenedAtMs: null,
    droneSequences: { B1: ['t5a', 't5b'], R1: ['t5b', 't5a'], G1: ['t5a'], G2: ['t5b'] },
    droneFailuresFired: 0, failedDroneId: null,
    failureRecoveryPending: false, pendingRecoveryOptions: null,
    tacticallySuppressedTaskId: null, abandonedAt: null, isResidual: false, needsGreedyReplan: false,
  } as unknown as Mission
}

function deadlockAssets(): Asset[] {
  return [
    drone('B1', 'Blue', WP_A, 't5a'),   // Fast sitting on t5a
    drone('R1', 'Red', WP_B, 't5b'),    // Lifter sitting on t5b
    drone('G1', 'Green', WP_A, 't5a'),  // Camera for t5a
    drone('G2', 'Green', WP_B, 't5b'),  // Camera for t5b
  ]
}

const tick = (s: GameState, elapsedSec: number) =>
  gameReducer(s, { type: 'TICK', nowMs: elapsedSec * 1000 } as any)

// ── fixLockouts ON (default): reroute → both tasks complete, nothing fails. ──
{
  let s: GameState = {
    ...buildInitialState({ ...config, fixLockouts: true }),
    config: { ...config, fixLockouts: true },
    phase: 'playing', sessionStartMs: 0, elapsed: 0,
    missions: [deadlockMission()], assets: deadlockAssets(),
  }
  s = tick(s, 3)   // drones arrived + idle + deadlocked → reroute fires
  const m = () => s.missions[0]
  const anyFailedNow = m().tasks.some(t => t.status === 'failed')
  check('ON: no task failed on detection (rerouted, not failed)', !anyFailedNow)
  check('ON: drone R1 redirected off t5b (reordered onto t5a-first)',
    s.assets.find(a => a.id === 'R1')!.currentTaskId === 't5a')
  check('ON: lockout_detected logged with resolution=rerouted',
    s.events[0].some((e: any) => e.type === 'lockout_detected' && e.resolution === 'rerouted'))

  for (let e = 4; e <= 300 && m().status === 'active'; e++) s = tick(s, e)
  check('ON: BOTH tasks completed', m().tasks.every(t => t.status === 'completed'))
  check('ON: mission completed (not failed/abandoned)', m().status === 'completed')
  const dlFails = s.events[0].filter((e: any) => e.type === 'task_failed' && e.reason === 'scheduling_deadlock')
  check('ON: zero scheduling_deadlock failures logged', dlFails.length === 0)
}

// ── fixLockouts OFF: surfaced as "help needed" — operator re-plans to fix, mission NOT auto-failed. ──
{
  let s: GameState = {
    ...buildInitialState({ ...config, fixLockouts: false }),
    config: { ...config, fixLockouts: false },
    phase: 'playing', sessionStartMs: 0, elapsed: 0,
    missions: [deadlockMission()], assets: deadlockAssets(),
  }
  s = tick(s, 3)
  const m0 = s.missions[0]
  check('OFF: mission NOT auto-abandoned (still active)', m0.status === 'active')
  check('OFF: flagged for recovery with reason=lockout', m0.failureRecoveryPending === true && m0.recoveryReason === 'lockout')
  check('OFF: deadlocked tasks reverted to pending but KEEP their plan (shown, not wiped)',
    m0.tasks.every(t => t.status === 'pending') &&
    m0.tasks.find(t => t.id === 't5a')!.assignedAssetIds.slice().sort().join() === ['B1', 'R1', 'G1'].sort().join() &&
    m0.tasks.find(t => t.id === 't5b')!.assignedAssetIds.slice().sort().join() === ['B1', 'R1', 'G2'].sort().join())
  check('OFF: stuck drones freed on-mission (no current task, still loitering here)',
    s.assets.filter(a => ['B1', 'R1', 'G1', 'G2'].includes(a.id))
      .every(a => a.currentTaskId === null && a.currentMissionId === 'M1' && a.status === 'deployed'))
  check('OFF: lockout_detected logged with resolution=help_needed',
    s.events[0].some((e: any) => e.type === 'lockout_detected' && e.resolution === 'help_needed'))

  // Operator re-plans a NON-cyclic allocation (both shared drones visit t5a then t5b) and confirms.
  s = gameReducer(s, {
    type: 'CONFIRM_FAILURE_RECOVERY', missionId: 'M1',
    taskAssignments: { t5a: ['B1', 'R1', 'G1'], t5b: ['B1', 'R1', 'G2'] },
    droneSequences: { B1: ['t5a', 't5b'], R1: ['t5a', 't5b'], G1: ['t5a'], G2: ['t5b'] },
  } as any)
  check('OFF: recovery clears the help-needed flag', s.missions[0].failureRecoveryPending === false)
  for (let e = 4; e <= 300 && s.missions[0].status === 'active'; e++) s = tick(s, e)
  check('OFF: after operator re-plan, both tasks complete', s.missions[0].tasks.every(t => t.status === 'completed'))
  check('OFF: mission completed (operator fixed the lockout)', s.missions[0].status === 'completed')
}

// ── OFF + orphaned shared task: a 3rd task sharing the cycle's drones must also revert. ──
// Reproduces the P-7021 snapshot bug: cycle was [t5a,t5b] but a traveling task tc shared the same
// Blue+Red. Freeing them orphaned tc, and recovery Suggest left tc unstaffed → forced abandon.
{
  const WP_C = { x: 690, y: 470 }
  const mission3: Mission = {
    ...deadlockMission(),
    tasks: [
      t5('t5a', WP_A, ['B1', 'R1', 'G1']),
      t5('t5b', WP_B, ['B1', 'R1', 'G2']),
      // tc: a THIRD task, still "traveling", that shares the cycle's B1+R1 (chained after the cycle)
      t5('tc', WP_C, ['B1', 'R1', 'G3']),
    ],
    droneSequences: { B1: ['t5a', 't5b', 'tc'], R1: ['t5b', 't5a', 'tc'], G1: ['t5a'], G2: ['t5b'], G3: ['tc'] },
  } as unknown as Mission
  let s: GameState = {
    ...buildInitialState({ ...config, fixLockouts: false }),
    config: { ...config, fixLockouts: false },
    phase: 'playing', sessionStartMs: 0, elapsed: 0,
    missions: [mission3],
    assets: [
      drone('B1', 'Blue', WP_A, 't5a'), drone('R1', 'Red', WP_B, 't5b'),
      drone('G1', 'Green', WP_A, 't5a'), drone('G2', 'Green', WP_B, 't5b'),
      drone('G3', 'Green', WP_C, 'tc'),
    ],
  }
  s = tick(s, 3)
  const m = s.missions[0]
  check('orphan: ALL three tasks reverted to pending (incl. the shared traveling task tc)',
    m.tasks.every(t => t.status === 'pending'))
  check('orphan: tc keeps its plan shown (not wiped)',
    m.tasks.find(t => t.id === 'tc')!.assignedAssetIds.slice().sort().join() === ['B1', 'R1', 'G3'].sort().join())
  check('orphan: tc-only drone G3 also freed/parked',
    s.assets.find(a => a.id === 'G3')!.currentTaskId === null)

  // Operator (or Suggest) re-plans all three in one canonical chain and confirms.
  s = gameReducer(s, {
    type: 'CONFIRM_FAILURE_RECOVERY', missionId: 'M1',
    taskAssignments: { t5a: ['B1', 'R1', 'G1'], t5b: ['B1', 'R1', 'G2'], tc: ['B1', 'R1', 'G3'] },
    droneSequences: { B1: ['t5a', 't5b', 'tc'], R1: ['t5a', 't5b', 'tc'], G1: ['t5a'], G2: ['t5b'], G3: ['tc'] },
  } as any)
  for (let e = 4; e <= 400 && s.missions[0].status === 'active'; e++) s = tick(s, e)
  check('orphan: after re-plan, ALL three tasks complete', s.missions[0].tasks.every(t => t.status === 'completed'))
  check('orphan: mission completed (no forced abandon)', s.missions[0].status === 'completed')
}

// ── Negative 1: same deadlock but drones still EN ROUTE (not arrived) → must NOT act yet. ──
{
  let s: GameState = {
    ...buildInitialState(config),
    phase: 'playing', sessionStartMs: 0, elapsed: 0,
    missions: [deadlockMission()],
    assets: deadlockAssets().map(a => ({ ...a, position: { x: 500, y: 400 }, travelFrom: { x: 500, y: 400 }, travelEndElapsed: 40 })),
  }
  s = tick(s, 3)
  check('en-route drones: deadlock NOT acted on while still travelling',
    !s.missions[0].tasks.some(t => t.status === 'failed') && s.missions[0].status === 'active')
}

// ── Negative 2: a VALID acyclic chain (both drones same order) → must never be touched. ──
{
  let s: GameState = {
    ...buildInitialState(config),
    phase: 'playing', sessionStartMs: 0, elapsed: 0,
    missions: [{
      ...deadlockMission(),
      tasks: [
        { ...t5('t5a', WP_A, ['B1', 'R1', 'G1']), startTime: 3, completionTime: 48 } as Task,
        { ...t5('t5b', WP_B, ['B1', 'R1', 'G2']), startTime: 60, completionTime: 105 } as Task,
      ],
      droneSequences: { B1: ['t5a', 't5b'], R1: ['t5a', 't5b'], G1: ['t5a'], G2: ['t5b'] }, // same order → acyclic
    } as Mission],
    assets: [
      drone('B1', 'Blue', WP_A, 't5a'), drone('R1', 'Red', WP_A, 't5a'),
      drone('G1', 'Green', WP_A, 't5a'), drone('G2', 'Green', WP_B, 't5b'),
    ],
  }
  for (let e = 3; e <= 300 && s.missions[0].status === 'active'; e++) s = tick(s, e)
  const dlFired = s.events[0].some((e: any) => e.type === 'task_failed' && e.reason === 'scheduling_deadlock')
  check('valid acyclic chain: no false deadlock, both tasks completed',
    !dlFired && s.missions[0].tasks.every(t => t.status === 'completed'))
}

console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILED`)
process.exit(failures === 0 ? 0 : 1)
