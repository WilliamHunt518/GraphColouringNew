// Regression test for the post-failure grace window (study-v1.5).
// Run: npx tsx scripts/test-failure-grace.ts
//
// A mission that has just lost a drone is exempt from further failure rolls until
// FAILURE_GRACE_SECONDS after its recovery is RESOLVED — not merely while the recovery dialog is
// open. Without it a second drone could die on the same mission while the operator was still
// dragging the fix for the first: the plan they were editing gets rebuilt underneath them, and the
// recovery-latency measure stops meaning "how long did the operator take" and starts meaning "how
// many times were they interrupted".
//
// Only failures that OPEN a recovery start the window. A loitering drone's death and a graceful
// section exit are invisible to the operator (no dialog, nothing to fix), so they leave the hazard
// alone — otherwise the realized failure rate would fall to ~half of
// FAILURE_RATE_PER_DRONE_SECOND, which the scenario calibration in docs/SCENARIOS.md depends on.
import { buildInitialState, gameReducer } from '../src/store/gameReducer'
import { failureGraceSeconds } from '../src/utils/config'
import { FAILURE_GRACE_SECONDS } from '../src/utils/missionGen'
import type { GameState, StudyConfig, Mission, Task, Asset } from '../src/types'

let failures = 0
const check = (label: string, cond: boolean, detail = '') => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}${detail ? '  — ' + detail : ''}`)
  if (!cond) failures++
}

const WP = { x: 700, y: 400 }
const cfg = (over: Partial<StudyConfig> = {}): StudyConfig => ({
  participantId: 'TEST', condition: 'HH', mode: 'agent', complexity: 'balanced',
  seed: 3, agentErrorRate: 0, epsilonTactical: 0, tacticalMode: 'plan-all',
  testingMode: false, tutorialMode: false, numSessions: 1, ...over,
})

// A never-startable pending task keeps the mission 'active' (so its drones stay eligible) without
// anything completing. The drones loiter unassigned — the branch that opens no recovery.
function mission(over: Partial<Mission> = {}): Mission {
  return {
    id: 'M1', category: 'C', status: 'active', zoneCenter: WP, zoneRadius: 80,
    tasks: [{
      id: 'M1-T1', missionId: 'M1', type: 5, status: 'pending', assignedAssetIds: [], waypoint: WP,
      allocatedAt: null, travelTime: 0, baseTime: 45, useSubstitute: false,
      startTime: null, completionTime: null, recallDelay: 0, completedSectionTypes: [],
    } as unknown as Task],
    arrivalTime: 0, allocationTime: 0, completionTime: null,
    agentInteraction: 'manual', chosenStrategyName: 'Manual', manualPriorityIds: [],
    tacticalPending: false, pendingAllocation: null, tacticalOpenedAtMs: null, droneSequences: {},
    droneFailuresFired: 0, failedDroneId: null, failureRecoveryPending: false,
    failureExemptUntil: null, pendingRecoveryOptions: null,
    tacticallySuppressedTaskId: null, abandonedAt: null, isResidual: false, needsGreedyReplan: false,
    ...over,
  } as unknown as Mission
}

const N_DRONES = 33
const loiterers = (): Asset[] => Array.from({ length: N_DRONES }, (_, i) => ({
  id: `B${String(i + 1).padStart(2, '0')}`, type: (['Blue', 'Red', 'Green'] as const)[i % 3],
  status: 'deployed', currentMissionId: 'M1', currentTaskId: null,
  position: { ...WP }, travelFrom: { ...WP }, targetPosition: { ...WP },
  travelStartElapsed: 0, travelEndElapsed: 0, availableAt: 0, failedAt: null, replacementAt: null,
} as unknown as Asset))

// Run `seconds` of simulated time, return the drone_failure events logged.
function run(exemptUntil: number | null, seconds: number, from = 0) {
  let s: GameState = {
    ...buildInitialState(cfg()), config: cfg(), phase: 'playing', sessionStartMs: 0,
    elapsed: from, missions: [mission({ failureExemptUntil: exemptUntil })], assets: loiterers(),
  }
  for (let e = from + 1; e <= seconds; e++) s = gameReducer(s, { type: 'TICK', nowMs: e * 1000 } as any)
  return s.events[0].filter((e: any) => e.type === 'drone_failure')
}

// 1. The exemption really gates the hazard.
{
  const unprotected = run(null, 300)
  check('baseline: failures do fire on an unprotected mission', unprotected.length > 0,
    `${unprotected.length} in 300s`)
  const protectedRun = run(300, 300)
  check('no failure fires while the mission is inside its grace window',
    protectedRun.length === 0, `${protectedRun.length} in 300s`)
  const afterwards = run(150, 300).filter((e: any) => e.elapsed >= 150)
  check('failures resume once the window expires', afterwards.length > 0,
    `${afterwards.length} after t=150`)
}

// 2. A failure that opens a recovery arms the window; resolving the recovery re-arms it from
//    the moment of the fix, so the operator gets a clean run at the repaired mission.
{
  let s: GameState = {
    ...buildInitialState(cfg({ testingMode: true })), config: cfg({ testingMode: true }),
    phase: 'playing', sessionStartMs: 0, elapsed: 10,
    missions: [mission({
      tasks: [{
        id: 'M1-T1', missionId: 'M1', type: 1, status: 'executing', assignedAssetIds: ['B01'],
        waypoint: WP, allocatedAt: 0, travelTime: 0, baseTime: 200, useSubstitute: false,
        startTime: 5, completionTime: 205, recallDelay: 0, completedSectionTypes: [],
      } as unknown as Task],
    })],
    assets: loiterers().map(a => a.id === 'B01' ? { ...a, currentTaskId: 'M1-T1' } : a),
  }
  s = gameReducer(s, { type: 'FORCE_DRONE_FAILURE' } as any)
  const armed = s.missions[0]
  check('a failure that opens a recovery arms the grace window',
    armed.failureRecoveryPending === true &&
    armed.failureExemptUntil === 10 + FAILURE_GRACE_SECONDS,
    `until ${armed.failureExemptUntil}`)

  // The operator takes 25 s to drag a fix, then confirms.
  s = { ...s, elapsed: 35 }
  s = gameReducer(s, {
    type: 'CONFIRM_FAILURE_RECOVERY', missionId: 'M1',
    taskAssignments: { 'M1-T1': ['B04'] }, droneSequences: { B04: ['M1-T1'] },
  } as any)
  const fixed = s.missions[0]
  check('resolving the recovery re-arms the window from the moment of the fix',
    fixed.failureRecoveryPending === false && fixed.failureExemptUntil === 35 + FAILURE_GRACE_SECONDS,
    `until ${fixed.failureExemptUntil}`)
}

// 3. The window is configurable, and 0 genuinely disables it.
{
  check('default grace is FAILURE_GRACE_SECONDS', failureGraceSeconds({}) === FAILURE_GRACE_SECONDS)
  check('an explicit 0 disables the grace (not overridden by the default)',
    failureGraceSeconds({ failureGraceSeconds: 0 }) === 0)
  check('an explicit value is honoured', failureGraceSeconds({ failureGraceSeconds: 12 }) === 12)
}

console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILED`)
process.exit(failures === 0 ? 0 : 1)
