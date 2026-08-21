// Regression test for the "chain after Suggest drops the suggested task" bug.
//
// The planner's "Suggest" fills `assignments` but never touches `droneChainOrder`. Shift+dragging a
// Suggest-placed drone onto a second task used to write its chain order as just [newTask], so the
// task it was ALREADY on vanished from `droneSequences`. buildManualAssignments only schedules
// tasks that appear in some drone's sequence, so that task was committed with NO start time and
// never dispatched — while the planner still showed it staffed and left Deploy enabled. Observed
// live: a 2-task mission deployed with only 1 task scheduled, earning 0 of 40 points.
//
// MapDisplay.moveDrone now seeds the chain order from the drone's current effective sequence, so
// the operator's shift+drag produces [oldTask, newTask]. This test pins the reducer-side
// consequence of both sequence shapes: it is the difference between the two that the fix removes.
//
// Run: npx tsx scripts/test-chain-after-suggest.ts
import { buildInitialState, gameReducer } from '../src/store/gameReducer'
import type { GameState, StudyConfig, Mission, Task, Asset, PendingAllocation } from '../src/types'

let failures = 0
const check = (label: string, cond: boolean) => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}`)
  if (!cond) failures++
}

const config: StudyConfig = {
  participantId: 'TEST', condition: 'HH', mode: 'agent', complexity: 'balanced',
  seed: 1, agentErrorRate: 0, epsilonTactical: 0, tacticalMode: 'plan-all',
  testingMode: true, tutorialMode: false, numSessions: 1,
}

const HUBP = { x: 700, y: 400 }
const WP1 = { x: 500, y: 300 }   // t1 — Recce (1 Fast)
const WP2 = { x: 900, y: 500 }   // t2 — Recce (1 Fast)

function recce(id: string, wp: { x: number; y: number }): Task {
  return {
    id, missionId: 'M1', type: 1, status: 'pending', assignedAssetIds: [], waypoint: wp,
    allocatedAt: null, travelTime: 0, baseTime: 10, useSubstitute: false,
    startTime: null, completionTime: null, recallDelay: 0, completedSectionTypes: [],
  } as unknown as Task
}
function fast(id: string): Asset {
  return {
    id, type: 'Blue', status: 'deployed', currentMissionId: 'M1', currentTaskId: null,
    position: { ...HUBP }, travelFrom: { ...HUBP }, targetPosition: { ...HUBP },
    travelStartElapsed: 0, travelEndElapsed: 0, availableAt: 0, failedAt: null, replacementAt: null,
  } as unknown as Asset
}

// The agent suggested B1 on t1; the operator then shift+drags B1 onto t2 as well.
// Both cases send the same taskAssignments — only the drone's sequence differs.
function run(droneSequences: Record<string, string[]>): GameState {
  const pending: PendingAllocation = {
    strategyName: 'Aggressive', composition: { Blue: 1, Red: 0, Green: 0 },
    dronePool: ['B1'], taskAssignments: { t1: ['B1'] }, taskOrder: ['t1', 't2'],
    expectedCompletionTime: 0, isAgentSuggested: true, isBadSuggestion: false,
    badSuggestionType: null, hasTacticalError: false, suppressedTaskId: null,
  }
  const mission: Mission = {
    id: 'M1', category: 'A', status: 'active', zoneCenter: WP1, zoneRadius: 80,
    tasks: [recce('t1', WP1), recce('t2', WP2)],
    arrivalTime: 0, allocationTime: 0, completionTime: null,
    agentInteraction: 'shown', chosenStrategyName: 'Aggressive', manualPriorityIds: [],
    tacticalPending: true, pendingAllocation: pending, tacticalOpenedAtMs: 0,
    droneSequences: {}, droneFailuresFired: 0, failedDroneId: null,
    failureRecoveryPending: false, pendingRecoveryOptions: null,
    tacticallySuppressedTaskId: null, abandonedAt: null, isResidual: false, needsGreedyReplan: false,
  } as unknown as Mission

  let s: GameState = {
    ...buildInitialState(config),
    phase: 'playing', sessionStartMs: 0, elapsed: 0,
    missions: [mission], assets: [fast('B1')],
  }
  s = gameReducer(s, {
    type: 'CONFIRM_TACTICAL', missionId: 'M1',
    taskAssignments: { t1: ['B1'], t2: ['B1'] },
    droneSequences,
  } as any)
  for (let e = 1; e <= 400 && s.missions[0].status === 'active'; e++) {
    s = gameReducer(s, { type: 'TICK', nowMs: e * 1000 } as any)
  }
  return s
}

// ── The buggy sequence the old moveDrone produced: only the newly chained task ──
const buggy = run({ B1: ['t2'] })
const buggyConfirm = buggy.events[0].find(e => e.type === 'tactical_confirmed') as any
check('BUG SHAPE: sequence [t2] alone leaves t1 unscheduled',
  buggyConfirm.finalPlan.length === 1 && buggyConfirm.unassignedTaskIds.includes('t1'))
check('BUG SHAPE: t1 never completes', buggy.missions[0].tasks.find(t => t.id === 't1')!.status !== 'completed')

// ── The sequence the fixed moveDrone produces: prior task, then the chained one ──
const fixed = run({ B1: ['t1', 't2'] })
const fixedConfirm = fixed.events[0].find(e => e.type === 'tactical_confirmed') as any
check('FIXED SHAPE: both tasks scheduled', fixedConfirm.finalPlan.length === 2)
check('FIXED SHAPE: nothing left unassigned', fixedConfirm.unassignedTaskIds.length === 0)
check('FIXED SHAPE: chaining is recorded', fixedConfirm.chainingUsed && fixedConfirm.chainedDroneIds.includes('B1'))
check('FIXED SHAPE: the single chained drone completes both tasks',
  fixed.missions[0].tasks.every(t => t.status === 'completed'))

console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILED`)
process.exit(failures === 0 ? 0 : 1)
