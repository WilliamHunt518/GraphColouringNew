// Regression test for the recovery planner's "Suggest" button (study-v1.5).
// Run: npx tsx scripts/test-failure-recovery-suggest.ts
//
// Bug: during a drone-failure recovery, clicking "Suggest" did nothing at all — no drones appeared,
// no message, nothing. Two causes, both exercised here:
//
//  1. computeRecoverySuggestion drew only on drones that were idle at that instant. After a failure
//     that pool IS the broken task's survivors — by construction exactly one drone short of the
//     composition that just broke — so tryAssign failed for every task and the function returned
//     {}. The worst case is a solo-Blue T1 Recce: its Blue dies, nothing is released at all, and
//     every other Blue on the mission is en route to a task that has not started yet.
//  2. Even once the agent could propose chaining a drone off a not-yet-started task,
//     CONFIRM_FAILURE_RECOVERY only ever re-committed 'pending' tasks. The drone flew to the broken
//     task while the 'traveling' task it came from still listed it — that task then stalled.
//
// Scenario: T1 Recce (solo Fast B1) has just lost B1. The mission's other two Fasts are mid-flight
// to a T2 Recon that has not started. The only possible fix is to chain one of them back.
import { buildInitialState, gameReducer } from '../src/store/gameReducer'
import { computeRecoverySuggestion } from '../src/utils/tacticalSuggest'
import { taskCoverableBy } from '../src/utils/coverage'
import type { GameState, StudyConfig, Mission, Task, Asset, PendingAllocation } from '../src/types'

let failures = 0
const check = (label: string, cond: boolean, detail = '') => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}${detail ? '  — ' + detail : ''}`)
  if (!cond) failures++
}

const config: StudyConfig = {
  participantId: 'TEST', condition: 'HH', mode: 'agent', complexity: 'balanced',
  seed: 1, agentErrorRate: 0, epsilonTactical: 0, tacticalMode: 'plan-all',
  testingMode: true,          // suppress the ambient hazard so only the scripted failure exists
  tutorialMode: false, numSessions: 1,
}

const WP_RECCE = { x: 700, y: 400 }   // t1, blanked by the failure
const WP_RECON = { x: 745, y: 435 }   // t2, drones still flying to it

function task(id: string, type: number, status: string, assigned: string[], wp: { x: number; y: number },
              baseTime: number, startTime: number | null): Task {
  return {
    id, missionId: 'M1', type, status, assignedAssetIds: assigned, waypoint: wp,
    allocatedAt: startTime === null ? null : 0, travelTime: startTime ?? 0, baseTime, useSubstitute: false,
    startTime, completionTime: startTime === null ? null : startTime + baseTime,
    recallDelay: 0, completedSectionTypes: [],
  } as unknown as Task
}

// In flight: departed the hub at t=0, still short of the waypoint at the moment of the failure.
function flying(id: string, type: 'Blue' | 'Red' | 'Green', from: { x: number; y: number },
                to: { x: number; y: number }, curTask: string): Asset {
  return {
    id, type, status: 'deployed', currentMissionId: 'M1', currentTaskId: curTask,
    position: { ...from }, travelFrom: { ...from }, targetPosition: { ...to },
    travelStartElapsed: 0, travelEndElapsed: 40, availableAt: 40, failedAt: null, replacementAt: null,
  } as unknown as Asset
}

function missionAfterFailure(): Mission {
  return {
    id: 'M1', category: 'C', status: 'active', zoneCenter: WP_RECCE, zoneRadius: 80,
    tasks: [
      task('t1', 1, 'pending', [], WP_RECCE, 10, null),                  // blanked: its only Fast died
      task('t2', 2, 'traveling', ['B2', 'B3'], WP_RECON, 15, 40),        // unstarted, drones en route
    ],
    arrivalTime: 0, allocationTime: 0, completionTime: null,
    agentInteraction: 'manual', chosenStrategyName: 'Manual', manualPriorityIds: [],
    tacticalPending: false, pendingAllocation: null, tacticalOpenedAtMs: null,
    droneSequences: { B2: ['t2'], B3: ['t2'] },
    droneFailuresFired: 1, failedDroneId: 'B1',
    failureRecoveryPending: true, recoveryReason: 'drone_failure', recoveryOpenedAtMs: 20_000,
    pendingRecoveryOptions: [],
    tacticallySuppressedTaskId: null, abandonedAt: null, isResidual: false, needsGreedyReplan: false,
  } as unknown as Mission
}

function assetsAfterFailure(): Asset[] {
  return [
    { id: 'B1', type: 'Blue', status: 'failed', currentMissionId: null, currentTaskId: null,
      position: { ...WP_RECCE }, travelFrom: { ...WP_RECCE }, targetPosition: { ...WP_RECCE },
      travelStartElapsed: 0, travelEndElapsed: 0, availableAt: 0, failedAt: 20, replacementAt: null } as unknown as Asset,
    flying('B2', 'Blue', { x: 620, y: 340 }, WP_RECON, 't2'),
    flying('B3', 'Blue', { x: 615, y: 335 }, WP_RECON, 't2'),
  ]
}

// Exactly what MapDisplay's buildRecoveryAllocation hands the planner: the mission's deployed
// subswarm, every unfinished task (executing/traveling first), pre-populated from the live plan.
function recoveryAllocation(m: Mission, assets: Asset[]): PendingAllocation {
  const pool = assets.filter(a => a.currentMissionId === m.id && a.status === 'deployed').map(a => a.id)
  const poolSet = new Set(pool)
  const order = ['t2', 't1']
  return {
    strategyName: 'Manual', composition: { Blue: 0, Red: 0, Green: 0 },
    dronePool: pool, taskOrder: order,
    taskAssignments: Object.fromEntries(order.map(tid =>
      [tid, m.tasks.find(t => t.id === tid)!.assignedAssetIds.filter(id => poolSet.has(id))])),
    expectedCompletionTime: 0, isAgentSuggested: false, isBadSuggestion: false,
    badSuggestionType: null, hasTacticalError: false, suppressedTaskId: null,
  } as unknown as PendingAllocation
}

const tick = (s: GameState, sec: number) => gameReducer(s, { type: 'TICK', nowMs: sec * 1000 } as any)

let s: GameState = {
  ...buildInitialState(config), config, phase: 'playing', sessionStartMs: 0, elapsed: 20,
  missions: [missionAfterFailure()], assets: assetsAfterFailure(),
}
const m0 = s.missions[0]
const pending = recoveryAllocation(m0, s.assets)

// 1. The agent actually proposes something.
const suggestion = computeRecoverySuggestion(m0, pending, s.assets, pending.taskAssignments)
check('Suggest returns a plan at all (the button is not a no-op)',
  Object.keys(suggestion).length > 0, JSON.stringify(suggestion))
check('Suggest staffs the broken Recce by chaining a Fast off the unstarted Recon',
  taskCoverableBy(m0.tasks.find(t => t.id === 't1')!,
    (suggestion['t1'] ?? []).map(id => s.assets.find(a => a.id === id)!)),
  (suggestion['t1'] ?? []).join(',') || 'nobody')
check('Suggest leaves the already-covered task alone (no needless reshuffle)',
  suggestion['t2'] === undefined)

// 2. Confirming it leaves BOTH tasks live — the borrowed-from task must not stall.
const plan: Record<string, string[]> = { ...pending.taskAssignments }
for (const [tid, ids] of Object.entries(suggestion)) plan[tid] = ids
const seqs: Record<string, string[]> = {}
for (const tid of pending.taskOrder) for (const id of plan[tid] ?? []) (seqs[id] ??= []).push(tid)

s = gameReducer(s, {
  type: 'CONFIRM_FAILURE_RECOVERY', missionId: 'M1', taskAssignments: plan,
  droneSequences: seqs, wasAgentSuggested: true,
} as any)
const m1 = s.missions[0]
const t2After = m1.tasks.find(t => t.id === 't2')!
check('recovery clears the help-needed flag', m1.failureRecoveryPending === false)
check('the broken Recce is dispatched', m1.tasks.find(t => t.id === 't1')!.status === 'traveling')
check('the borrowed-from Recon is still fully staffed (re-committed, not stalled)',
  taskCoverableBy(t2After, t2After.assignedAssetIds.map(id => s.assets.find(a => a.id === id)!)),
  t2After.assignedAssetIds.join(','))
const shared = Object.entries(m1.droneSequences).find(([, seq]) => seq.length > 1)
check('the shared Fast is chained through both tasks', shared !== undefined,
  shared ? `${shared[0]}: ${shared[1].join(' -> ')}` : 'no drone covers both')

// 3. And it actually plays out: both tasks finish, nothing fails.
for (let e = 21; e <= 400 && s.missions[0].status === 'active'; e++) s = tick(s, e)
const done = s.missions[0]
check('both tasks completed', done.tasks.every(t => t.status === 'completed'),
  done.tasks.map(t => `${t.id}=${t.status}`).join(' '))
check('no task failed during the repaired run',
  !s.events[0].some((e: any) => e.type === 'task_failed'))

console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILED`)
process.exit(failures === 0 ? 0 : 1)
