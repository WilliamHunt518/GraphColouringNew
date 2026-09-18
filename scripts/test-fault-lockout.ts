// Does the live TICK-time deadlock detector (gameReducer step 3c, findSchedulingCycle/
// rerouteDeadlock) also catch and fix a cycle that comes from the ε_Tactical FAULT mechanism
// (buildTacticalFailurePlan's redundant detour hops), not just a hand-built operator cycle?
//
// test-scheduling-deadlock.ts already pins the hand-built case. This one drives the actual fault
// function across many seeds, filters each drone's sequence down to what MapDisplay would really
// commit (userOrder.filter(tid => assignments[tid]?.includes(id)) — see tacticalSuggest.ts's
// docstring), detects which seeds happen to produce a genuine cross-drone cycle, and for every one
// of those runs it through the real TICK path to confirm fixLockouts=true (the study default)
// always reroutes it cleanly: nothing fails, the mission completes, resolution='rerouted'.
//
// Run: npx tsx scripts/test-fault-lockout.ts
import { buildInitialState, gameReducer } from '../src/store/gameReducer'
import { buildTacticalFailurePlan } from '../src/utils/tacticalSuggest'
import { findSchedulingCycle } from '../src/utils/scheduling'
import { SeededRNG } from '../src/utils/prng'
import type { GameState, StudyConfig, Mission, Task, Asset } from '../src/types'

let failures = 0
const check = (label: string, cond: boolean) => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}`)
  if (!cond) failures++
}

const config: StudyConfig = {
  participantId: 'TEST', condition: 'HH', mode: 'agent', complexity: 'balanced',
  seed: 1, agentErrorRate: 0.1, epsilonTactical: 0.1, tacticalMode: 'plan-all',
  testingMode: true, tutorialMode: false, numSessions: 1, fixLockouts: true,
}

const WPS = [{ x: 700, y: 400 }, { x: 760, y: 440 }, { x: 640, y: 460 }]

// A type-5 task (needs exactly 1 Blue + 1 Red + 1 Green — mirrors test-scheduling-deadlock.ts's
// t5 helper, the one composition already proven to TICK through to completion cleanly).
function t5(id: string, waypoint: { x: number; y: number }, assigned: string[]): Task {
  return {
    id, missionId: 'M1', type: 5, status: 'traveling',
    assignedAssetIds: assigned, waypoint,
    allocatedAt: 0, travelTime: 500, baseTime: 45, useSubstitute: false,
    startTime: 500, completionTime: 545, recallDelay: 0, completedSectionTypes: [],
  } as unknown as Task
}

function drone(id: string, type: 'Blue' | 'Red' | 'Green', at: { x: number; y: number }, curTask: string): Asset {
  return {
    id, type, status: 'deployed', currentMissionId: 'M1', currentTaskId: curTask,
    position: { ...at }, travelFrom: { ...at }, targetPosition: { ...at },
    travelStartElapsed: 0, travelEndElapsed: 0, availableAt: 0,
    failedAt: null, replacementAt: null,
  } as unknown as Asset
}

const tick = (s: GameState, elapsedSec: number) =>
  gameReducer(s, { type: 'TICK', nowMs: elapsedSec * 1000 } as any)

/** Builds an N-task mission where task i's real crew is Blue{i}/Red{i}/Green{i}, runs the real
 *  fault function to get each drone's redundant detour, filters to what actually gets committed,
 *  and reports whether the result is cyclic. */
function buildFaultedMission(nTasks: number, seed: number) {
  const taskIds = Array.from({ length: nTasks }, (_, i) => `t${i}`)
  const tasks = taskIds.map(id => ({ id } as unknown as Task))
  const realTaskAssignments: Record<string, string[]> = {}
  const realTaskOf: Record<string, string> = {}   // droneId -> its one real task
  taskIds.forEach((tid, i) => {
    const ids = [`B${i}`, `R${i}`, `G${i}`]
    realTaskAssignments[tid] = ids
    for (const id of ids) realTaskOf[id] = tid
  })

  const { taskAssignments: augmented, droneSequences: raw } =
    buildTacticalFailurePlan(tasks, realTaskAssignments, new SeededRNG(seed))

  // MapDisplay's own filter: a drone's committed chain is only the entries it's a genuine
  // taskAssignments member of (tacticalSuggest.ts docstring, "MapDisplay's planner already
  // filters...").
  const filtered: Record<string, string[]> = {}
  for (const [droneId, seq] of Object.entries(raw)) {
    filtered[droneId] = seq.filter(tid => augmented[tid]?.includes(droneId))
  }

  const cycle = findSchedulingCycle(augmented, filtered)
  return { taskIds, augmented, filtered, realTaskOf, cycle }
}

function droneType(id: string): 'Blue' | 'Red' | 'Green' {
  return id[0] === 'B' ? 'Blue' : id[0] === 'R' ? 'Red' : 'Green'
}

/** Drives the faulted plan through the real TICK path and asserts fixLockouts=true resolves it
 *  cleanly, the same bar test-scheduling-deadlock.ts holds the hand-built cycle to. */
function assertResolvesCleanly(seed: number, nTasks: number,
  built: ReturnType<typeof buildFaultedMission>) {
  const { taskIds, augmented, filtered } = built
  const tasks = taskIds.map((tid, i) => t5(tid, WPS[i], augmented[tid]))
  const allDrones = new Set(Object.keys(filtered))
  const assets = [...allDrones].map(id => {
    const seq = filtered[id]
    const firstTaskId = seq[0]   // pickFirstAssignment: flies to the first task in its own chain
    return drone(id, droneType(id), WPS[taskIds.indexOf(firstTaskId)], firstTaskId)
  })

  const mission = {
    id: 'M1', category: 'C', status: 'active', zoneCenter: WPS[0], zoneRadius: 80,
    tasks, arrivalTime: 0, allocationTime: 0, completionTime: null,
    agentInteraction: 'agent', chosenStrategyName: 'Aggressive', manualPriorityIds: [],
    tacticalPending: false, pendingAllocation: null, tacticalOpenedAtMs: null,
    droneSequences: filtered,
    droneFailuresFired: 0, failedDroneId: null,
    failureRecoveryPending: false, pendingRecoveryOptions: null,
    tacticallySuppressedTaskId: null, abandonedAt: null, isResidual: false, needsGreedyReplan: false,
  } as unknown as Mission

  let s: GameState = {
    ...buildInitialState(config), config, phase: 'playing', sessionStartMs: 0, elapsed: 0,
    missions: [mission], assets,
  }
  s = tick(s, 3)   // drones arrived + idle + deadlocked (if cyclic) → reroute should fire this tick
  for (let e = 4; e <= 400 && s.missions[0].status === 'active'; e++) s = tick(s, e)

  const m = s.missions[0]
  const dlFails = s.events[0].filter((e: any) => e.type === 'task_failed' && e.reason === 'scheduling_deadlock')
  const rerouted = s.events[0].some((e: any) => e.type === 'lockout_detected' && e.resolution === 'rerouted')
  const ok = m.status === 'completed' && m.tasks.every(t => t.status === 'completed') && dlFails.length === 0 && rerouted
  check(`seed ${seed} (${nTasks} tasks): cyclic fault plan reroutes cleanly (completed=${m.status}, ` +
    `dlFails=${dlFails.length}, rerouted=${rerouted})`, ok)
}

// ── 1. Deterministic case: 2 tasks, 6 real drones. With only one OTHER task to land a detour on,
//    `first` has exactly one candidate — every drone's redundant hop is forced onto the other
//    task, so a T0<->T1 cycle forms on every seed. Regression-pins the simplest possible shape. ──
{
  const built = buildFaultedMission(2, 42)
  check('2-task case: fault plan is cyclic (forced, no seed dependence)', built.cycle !== null)
  assertResolvesCleanly(42, 2, built)
}

// ── 2. Fuzzed case: 3 tasks, 9 real drones. Each drone picks its detour randomly between the
//    OTHER two tasks, so cycle shape (or absence of one) genuinely varies by seed. Every seed that
//    happens to produce a cycle must still resolve cleanly under fixLockouts=true. ──
{
  const N = 300
  let cyclic = 0
  for (let seed = 1; seed <= N; seed++) {
    const built = buildFaultedMission(3, seed)
    if (built.cycle) {
      cyclic++
      assertResolvesCleanly(seed, 3, built)
    }
  }
  check(`3-task fuzz: at least some of ${N} seeds produced a real cycle (got ${cyclic}) — ` +
    'a 0 here would mean this test isn\'t exercising the deadlock path at all', cyclic > 0)
  console.log(`  (${cyclic}/${N} seeds cyclic; each one asserted above)`)
}

console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILED`)
process.exit(failures === 0 ? 0 : 1)
