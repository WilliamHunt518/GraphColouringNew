// Verifies that in GREEDY tactical mode, CONFIRM_TACTICAL keeps the operator's own multi-hop chain
// instead of collapsing it to a single first step. "Greedy" applies to the agent's baseline (built
// single-step in APPLY_STRATEGIC) and to live replan of UNassigned tasks — never to a path the
// operator deliberately drew.
// Run: npx tsx scripts/test-greedy-preserves-user-chain.ts
import { buildInitialState, gameReducer } from '../src/store/gameReducer'
import type { GameState, StudyConfig, Mission, Task, Asset, PendingAllocation } from '../src/types'

let failures = 0
const check = (label: string, cond: boolean) => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}`)
  if (!cond) failures++
}

const config: StudyConfig = {
  participantId: 'TEST', condition: 'HH', mode: 'agent', complexity: 'balanced',
  seed: 1, agentErrorRate: 0, epsilonTactical: 0, tacticalMode: 'greedy',
  testingMode: true, tutorialMode: false, numSessions: 1,
}

const HUBP = { x: 700, y: 400 }
const WP1 = { x: 500, y: 300 }
const WP2 = { x: 900, y: 500 }

// Two T1 (Recce, 1 Fast each) tasks. The operator chains ONE fast drone B1 across BOTH: B1: t1 -> t2.
function t1(id: string, wp: { x: number; y: number }): Task {
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

const pending: PendingAllocation = {
  strategyName: 'Manual', composition: { Blue: 1, Red: 0, Green: 0 },
  dronePool: ['B1'], taskAssignments: { 't1': ['B1'] }, taskOrder: ['t1', 't2'],
  expectedCompletionTime: 0, isAgentSuggested: false, isBadSuggestion: false,
  badSuggestionType: null, hasTacticalError: false, suppressedTaskId: null,
}

const mission: Mission = {
  id: 'M1', category: 'A', status: 'active', zoneCenter: WP1, zoneRadius: 80,
  tasks: [t1('t1', WP1), t1('t2', WP2)],
  arrivalTime: 0, allocationTime: 0, completionTime: null,
  agentInteraction: 'shown', chosenStrategyName: 'Manual', manualPriorityIds: [],
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

// Operator confirms their OWN chain: B1 does t1 THEN t2 (a 2-hop path).
s = gameReducer(s, {
  type: 'CONFIRM_TACTICAL', missionId: 'M1',
  taskAssignments: { t1: ['B1'], t2: ['B1'] },
  droneSequences: { B1: ['t1', 't2'] },
} as any)

const m = s.missions[0]
check('user 2-hop chain preserved in greedy mode (B1: t1 -> t2)',
  JSON.stringify(m.droneSequences.B1) === JSON.stringify(['t1', 't2']))
check('both chained tasks committed (not collapsed to just the first)',
  m.tasks.filter(t => t.assignedAssetIds.includes('B1')).length === 2)

// Drive it: B1 should complete t1, then follow its chain to t2 — both done, no extra drone needed.
for (let e = 1; e <= 300 && m.status === 'active' && s.missions[0].status === 'active'; e++) {
  s = gameReducer(s, { type: 'TICK', nowMs: e * 1000 } as any)
}
check('both tasks completed by the single chained drone', s.missions[0].tasks.every(t => t.status === 'completed'))

console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILED`)
process.exit(failures === 0 ? 0 : 1)
