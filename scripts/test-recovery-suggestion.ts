// Regression test for the tactical recovery "Suggest" button.
// Run: npx tsx scripts/test-recovery-suggestion.ts
//
// Bug: after a lockout (fixLockouts off), clicking Suggest with a PERFECT agent produced a plan
// that left one task unstaffed, so Deploy stayed disabled. Root cause: the recovery suggestion ran
// the greedy "consume-once" assigner, so two tasks that must SHARE the same Blue+Red (the classic
// lockout shape — two T5s, no substitute) could not both be covered. Fix: recovery always chains
// (plan-all), routing the shared drones through both tasks.
import { computeRecoverySuggestion, computeTacticalSuggestion } from '../src/utils/tacticalSuggest'
import { findSchedulingCycle, tasksInCycles } from '../src/utils/scheduling'
import type { Asset, Mission, PendingAllocation, Task } from '../src/types'

let failures = 0
const check = (label: string, cond: boolean) => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}`)
  if (!cond) failures++
}

const WP_A = { x: 700, y: 400 }
const WP_B = { x: 760, y: 440 }

function t5(id: string, waypoint: { x: number; y: number }): Task {
  return {
    id, missionId: 'M1', type: 5, status: 'pending',
    assignedAssetIds: [], waypoint,
    allocatedAt: null, travelTime: 0, baseTime: 45, useSubstitute: false,
    startTime: null, completionTime: null, recallDelay: 0, completedSectionTypes: [],
  } as unknown as Task
}

// Freed lockout drones: parked on-mission, currentTaskId null, sharing B1/R1 across the two T5s.
function drone(id: string, type: 'Blue' | 'Red' | 'Green', at: { x: number; y: number }): Asset {
  return {
    id, type, status: 'deployed', currentMissionId: 'M1', currentTaskId: null,
    position: { ...at }, travelFrom: { ...at }, targetPosition: { ...at },
    travelStartElapsed: 0, travelEndElapsed: 0, availableAt: 0, failedAt: null, replacementAt: null,
  } as unknown as Asset
}

const mission = {
  id: 'M1', tasks: [t5('t5a', WP_A), t5('t5b', WP_B)],
} as unknown as Mission

const assets: Asset[] = [
  drone('B1', 'Blue', WP_A), drone('R1', 'Red', WP_B),
  drone('G1', 'Green', WP_A), drone('G2', 'Green', WP_B),
]

const pending = {
  dronePool: ['B1', 'R1', 'G1', 'G2'],
  taskOrder: ['t5a', 't5b'],
} as unknown as PendingAllocation

const req5 = { Blue: 1, Red: 1, Green: 1 }
const meetsIn = (pool: Asset[]) => (ids: string[] | undefined) => {
  const c = { Blue: 0, Red: 0, Green: 0 }
  for (const id of ids ?? []) c[pool.find(a => a.id === id)!.type]++
  return c.Blue >= req5.Blue && c.Red >= req5.Red && c.Green >= req5.Green
}
const meets = meetsIn(assets)

// ── The fix: recovery suggestion covers BOTH shared tasks (chained). ──
const rec = computeRecoverySuggestion(mission, pending, assets)
check('recovery suggestion staffs t5a fully (1F 1L 1C)', meets(rec['t5a']))
check('recovery suggestion staffs t5b fully (1F 1L 1C)', meets(rec['t5b']))
check('shared Blue B1 chained through BOTH tasks', rec['t5a']?.includes('B1') && rec['t5b']?.includes('B1'))
check('shared Red R1 chained through BOTH tasks', rec['t5a']?.includes('R1') && rec['t5b']?.includes('R1'))

// ── Proof of the original bug: greedy consume-once leaves t5b unstaffed. ──
const greedyBad = computeTacticalSuggestion(pending.dronePool, pending.taskOrder, mission.tasks, assets, true)
check('(regression witness) greedy consume-once would leave t5b unstaffed',
  meets(greedyBad['t5a']) && !meets(greedyBad['t5b']))

// ── Recovery only re-plans PENDING tasks; a busy drone is left alone. ──
{
  const mission2 = {
    id: 'M2',
    tasks: [
      { ...t5('t2a', WP_A), status: 'executing', assignedAssetIds: ['B9'] } as Task,  // busy
      t5('t2b', WP_B),                                                                 // pending
    ],
  } as unknown as Mission
  const assets2: Asset[] = [
    { ...drone('B9', 'Blue', WP_A), currentTaskId: 't2a' },  // busy on executing task
    drone('R2', 'Red', WP_B), drone('G3', 'Green', WP_B), drone('B2', 'Blue', WP_B),
  ]
  const pending2 = { dronePool: ['B9', 'R2', 'G3', 'B2'], taskOrder: ['t2a', 't2b'] } as unknown as PendingAllocation
  const meets2 = meetsIn(assets2)
  const rec2 = computeRecoverySuggestion(mission2, pending2, assets2)
  check('busy executing task not re-planned', rec2['t2a'] === undefined)
  check('pending task staffed without pulling the busy drone', meets2(rec2['t2b']) && !(rec2['t2b'] ?? []).includes('B9'))
}

// ── Three pending tasks sharing one Blue + one Red (post-lockout-revert) all get staffed. ──
{
  const WP_C = { x: 690, y: 470 }
  const mission3 = {
    id: 'M3', tasks: [t5('t3a', WP_A), t5('t3b', WP_B), t5('t3c', WP_C)],
  } as unknown as Mission
  const assets3: Asset[] = [
    drone('B1', 'Blue', WP_A), drone('R1', 'Red', WP_B),
    drone('G1', 'Green', WP_A), drone('G2', 'Green', WP_B), drone('G3', 'Green', WP_C),
  ]
  const pending3 = { dronePool: ['B1', 'R1', 'G1', 'G2', 'G3'], taskOrder: ['t3a', 't3b', 't3c'] } as unknown as PendingAllocation
  const meets3 = meetsIn(assets3)
  const rec3 = computeRecoverySuggestion(mission3, pending3, assets3)
  check('3 shared tasks: all three staffed by chaining the single Blue+Red',
    meets3(rec3['t3a']) && meets3(rec3['t3b']) && meets3(rec3['t3c']))
}

// ── Deploy-gate logic: the loaded deadlocked plan is still cyclic (Reassign must be blocked);
//    the canonical order that Suggest/reorder produces is acyclic (Reassign unblocks). ──
{
  const taskAssignments = { t5a: ['B1', 'R1', 'G1'], t5b: ['B1', 'R1', 'G2'] }
  // Seeded (deadlocked) sequences: Blue does t5a→t5b, Red does t5b→t5a → cycle.
  const cyclicSeqs = { B1: ['t5a', 't5b'], R1: ['t5b', 't5a'], G1: ['t5a'], G2: ['t5b'] }
  check('loaded deadlocked plan is detected as still cyclic (Reassign blocked)',
    findSchedulingCycle(taskAssignments, cyclicSeqs) !== null)
  // Canonical order (both shared drones visit t5a then t5b) — what Suggest/reorder yields.
  const canonicalSeqs = { B1: ['t5a', 't5b'], R1: ['t5a', 't5b'], G1: ['t5a'], G2: ['t5b'] }
  check('canonical (Suggested) order is acyclic (Reassign unblocks)',
    findSchedulingCycle(taskAssignments, canonicalSeqs) === null)
}

// ── tasksInCycles flags only the mutually-blocking pair, not a downstream starved task. ──
// Two Supply Drops deadlock (each holds what the other needs); a Search & Service downstream is
// merely starved of drones stuck in that cycle — it must NOT be flagged as blocking.
{
  const taskAssignments = { supA: ['L1', 'C1'], supB: ['L1', 'C1'], sns: ['B1', 'L1', 'C1'] }
  const seqs = { L1: ['supA', 'supB', 'sns'], C1: ['supB', 'supA', 'sns'], B1: ['sns'] }
  const inCyc = tasksInCycles(taskAssignments, seqs)
  check('tasksInCycles flags the mutually-blocking pair (supA, supB)', inCyc.has('supA') && inCyc.has('supB'))
  check('tasksInCycles does NOT flag the downstream starved task (sns)', !inCyc.has('sns'))
  // Untangling the order (canonical: both shared drones visit supA→supB→sns) clears the cycle.
  const canonical = { L1: ['supA', 'supB', 'sns'], C1: ['supA', 'supB', 'sns'], B1: ['sns'] }
  check('tasksInCycles empty once the order is untangled', tasksInCycles(taskAssignments, canonical).size === 0)
}

console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILED`)
process.exit(failures === 0 ? 0 : 1)
