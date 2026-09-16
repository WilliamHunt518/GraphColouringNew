// Regression test for the ε_Tactical route failure (study-v1.10).
// Run: npx tsx scripts/test-tactical-failure.ts
//
// Replaces the old "silently drop a task from the plan" mechanism (too obvious — a task with zero
// drones is an unmissable red flag) with a route failure: every drone that has real work still gets
// it — composition is never REMOVED, only ever ADDED to — but its route is prefixed with a few
// random detours through this mission's own tasks before its real one. A lazy operator who deploys
// without editing gets a slow-but-complete mission, not a broken one.
//
// Critically, the detour additions have to land IN the returned taskAssignments (not just in a
// separate route field) — see the docstring on buildTacticalFailurePlan for why: the tactical
// planner's chain-order memo filters a drone's route down to tasks it's actually assigned to, so a
// route-only corruption would be silently discarded the moment the operator clicked Suggest.
//
// This checks: the ORIGINAL assignments are always still present (superset, nothing dropped);
// every drone with real work ends its route on that real work ("one task at the end of each drone's
// path"); every detour hop is reflected as real membership in the augmented map; hop counts stay in
// the configured range; and the master gate works the same way it does for the strategic side.
import { buildTacticalFailurePlan, TACTICAL_FAILURE_MIN_HOPS, TACTICAL_FAILURE_MAX_HOPS } from '../src/utils/tacticalSuggest'
import { effectiveEpsilonTactical } from '../src/utils/config'
import { SeededRNG } from '../src/utils/prng'
import type { Task } from '../src/types'

let failures = 0
const check = (label: string, cond: boolean, detail?: unknown) => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}${detail !== undefined ? `  — ${JSON.stringify(detail)}` : ''}`)
  if (!cond) failures++
}

function task(id: string, type: number): Task {
  return {
    id, missionId: 'M1', type, status: 'pending',
    assignedAssetIds: [], waypoint: { x: 0, y: 0 },
    allocatedAt: null, travelTime: 0, baseTime: 0, useSubstitute: false,
    startTime: null, completionTime: null, recallDelay: 0, completedSectionTypes: [],
  } as unknown as Task
}

// A mission shaped so several drones are naturally reused across more than one task (chained plan),
// which is the interesting case for route corruption.
const TASKS: Task[] = [task('t1', 5), task('t2', 3), task('t3', 2), task('t4', 4)]
const ORIGINAL: Record<string, string[]> = {
  t1: ['B01', 'R01', 'G01'],
  t2: ['R01', 'G02'],           // R01 reused from t1
  t3: ['B01', 'B02'],           // B01 reused from t1
  t4: ['R02', 'G01', 'G02'],    // G01 reused from t1
}
const ALL_DRONE_IDS = [...new Set(Object.values(ORIGINAL).flat())]

// ── 1. The original input is never mutated ──────────────────────────────────────────────────────
{
  const snapshot = JSON.stringify(ORIGINAL)
  let mutated = false
  for (let seed = 0; seed < 200; seed++) {
    buildTacticalFailurePlan(TASKS, ORIGINAL, new SeededRNG(seed))
    if (JSON.stringify(ORIGINAL) !== snapshot) mutated = true
  }
  check('the original taskAssignments object is never mutated (200 seeds)', !mutated)
}

// ── 2. The augmented plan is always a SUPERSET of the original — nothing ever dropped ───────────
{
  let everMissing = false
  for (let seed = 0; seed < 300; seed++) {
    const { taskAssignments } = buildTacticalFailurePlan(TASKS, ORIGINAL, new SeededRNG(seed))
    for (const [tid, ids] of Object.entries(ORIGINAL)) {
      for (const id of ids) {
        if (!taskAssignments[tid]?.includes(id)) everMissing = true
      }
    }
  }
  check('augmented taskAssignments always contains every original assignment (300 seeds)', !everMissing)
}

// ── 3. Every drone with real work ends its route on its real task(s), in their natural order ────
{
  let everWrongTail = false
  for (let seed = 0; seed < 300; seed++) {
    const { droneSequences } = buildTacticalFailurePlan(TASKS, ORIGINAL, new SeededRNG(seed))
    for (const droneId of ALL_DRONE_IDS) {
      const real = Object.keys(ORIGINAL).filter(tid => ORIGINAL[tid].includes(droneId))
      const seq = droneSequences[droneId]
      if (!seq) { everWrongTail = true; continue }   // every drone with real work must appear
      const tail = seq.slice(seq.length - real.length)
      if (tail.join() !== real.join()) everWrongTail = true
    }
  }
  check('every drone with real work ends its route on that work, in order (300 seeds)', !everWrongTail)
}

// ── 4. Only the FIRST drawn detour becomes real membership in taskAssignments — the rest of the
//      walk is logged data only, and (simulating exactly what MapDisplay's droneSequences memo does:
//      `userOrder.filter(tid => assignments[tid]?.includes(id))`) never survives into what's
//      actually deployed. This is the fix for "don't let this take ages" — only one hop's worth of
//      real dwell time is ever paid per drone, regardless of how many were drawn.
{
  let firstHopNotReal = 0
  let laterHopsLeakedIntoReal = 0
  let executedRouteEverLongerThanTwo = 0
  for (let seed = 0; seed < 500; seed++) {
    const { taskAssignments, droneSequences } = buildTacticalFailurePlan(TASKS, ORIGINAL, new SeededRNG(seed))
    for (const [droneId, seq] of Object.entries(droneSequences)) {
      const real = Object.keys(ORIGINAL).filter(tid => ORIGINAL[tid].includes(droneId))
      const detours = seq.slice(0, seq.length - real.length)
      if (!taskAssignments[detours[0]]?.includes(droneId)) firstHopNotReal++
      for (const tid of detours.slice(1)) {
        // A later detour MAY legitimately be a member if it happens to equal detours[0] or a real
        // task by chance (the walk samples with replacement) — only flag it if it's neither.
        if (taskAssignments[tid]?.includes(droneId) && tid !== detours[0] && !real.includes(tid)) laterHopsLeakedIntoReal++
      }
      // Simulate MapDisplay's droneSequences memo filter: keep only hops backed by real membership.
      const executed = seq.filter(tid => taskAssignments[tid]?.includes(droneId))
      if (executed.length > real.length + 1) executedRouteEverLongerThanTwo++
    }
  }
  check("the first drawn detour is always real membership (500 seeds)", firstHopNotReal === 0)
  check("later detours never leak into taskAssignments as a NEW membership (500 seeds)", laterHopsLeakedIntoReal === 0)
  check("the route MapDisplay would actually deploy never exceeds real-tasks + 1 detour hop (500 seeds)",
    executedRouteEverLongerThanTwo === 0)
}

// ── 5. Hop counts (detour prefix length, i.e. route length minus real task count) stay at or below
//      the configured max — the min can legitimately be undershot once `laterCandidates` (this
//      mission's tasks minus the drone's own real ones minus `first`) runs dry, since later draws
//      are deliberately restricted to avoid ever colliding with a real-membership task (see the
//      docstring / test 4) — with only 4 tasks total and up to 3 real per drone here, that pool is
//      small enough to exhaust before MAX_HOPS draws happen.
{
  let overMax = false
  const hopCounts: number[] = []
  for (let seed = 0; seed < 500; seed++) {
    const { droneSequences } = buildTacticalFailurePlan(TASKS, ORIGINAL, new SeededRNG(seed))
    for (const droneId of ALL_DRONE_IDS) {
      const real = Object.keys(ORIGINAL).filter(tid => ORIGINAL[tid].includes(droneId)).length
      const hops = (droneSequences[droneId]?.length ?? 0) - real
      hopCounts.push(hops)
      if (hops > TACTICAL_FAILURE_MAX_HOPS) overMax = true
    }
  }
  check(`hop count never exceeds ${TACTICAL_FAILURE_MAX_HOPS} (500 seeds)`, !overMax,
    { min: Math.min(...hopCounts), max: Math.max(...hopCounts) })
}

// ── 6. Drones with no real task are left out entirely (nothing to waste) ───────────────────────
{
  const { droneSequences } = buildTacticalFailurePlan(TASKS, ORIGINAL, new SeededRNG(1))
  check('a spare drone with no real task gets no sequence', droneSequences['SPARE-99'] === undefined)
}

// ── 7. No tasks at all → no sequences, doesn't throw ────────────────────────────────────────────
{
  const { taskAssignments, droneSequences } = buildTacticalFailurePlan([], {}, new SeededRNG(1))
  check('empty task list produces no sequences without throwing',
    Object.keys(droneSequences).length === 0 && Object.keys(taskAssignments).length === 0)
}

// ── 8. Regression guard: the per-mission RNG seed must have real entropy across a session's worth
//      of mission ids, or the "roll" collapses to one fixed coin-flip reused for every mission.
//      `gameReducer.ts` originally seeded the tactical roll with `mission.id.charCodeAt(2)` — for
//      ids shaped "M001".."M009" (nearly an entire short session — see missionGen.ts spawnMission,
//      `M${String(seq).padStart(3,'0')}`) that's the SAME character every time, so epsilon=0.5 could
//      fire for either ALL of a session's missions or NONE of them depending on one fixed draw,
//      not per-mission as intended. Fixed to use hashId(mission.id) (whole-string hash), matching
//      the strategic side's seed. This mirrors gameReducer.ts's `hashId` — keep in sync if it changes.
{
  function hashId(id: string): number {
    return id.split('').reduce((acc, c, i) => (acc ^ (c.charCodeAt(0) * (i + 7))) >>> 0, 0)
  }
  const missionIds = Array.from({ length: 15 }, (_, i) => `M${String(i + 1).padStart(3, '0')}`)
  const firstNineIds = missionIds.slice(0, 9)   // "M001".."M009" — id[2] (the tens digit) is '0' for all of them
  const BASE_SEED = 42
  const rollsOldFirstNine = firstNineIds.map(id => {
    const rng = new SeededRNG(BASE_SEED ^ (id.charCodeAt(2) ?? 0) ^ 0x7ac1)
    return rng.randFloat(0, 1) < 0.5
  })
  const rollsNew = missionIds.map(id => {
    const rng = new SeededRNG(BASE_SEED ^ hashId(id) ^ 0x7ac1)
    return rng.randFloat(0, 1) < 0.5
  })
  const oldFirstNineAllSame = rollsOldFirstNine.every(r => r === rollsOldFirstNine[0])
  const newHasVariation = !rollsNew.every(r => r === rollsNew[0])
  check('demonstrates the OLD charCodeAt(2) seed collapses to one fixed roll across "M001".."M009" (the tens digit is \'0\' for all of them)',
    oldFirstNineAllSame, { rollsOldFirstNine })
  check('the FIXED hashId(mission.id) seed varies across "M001".."M015" (not a constant roll)', newHasVariation,
    { rollsNew })
}

// ── 9. Master toggle forces the effective epsilon to 0 regardless of configured rate ────────────
{
  check('agentFailuresEnabled=false forces effective epsilon to 0',
    effectiveEpsilonTactical({ epsilonTactical: 0.9, agentFailuresEnabled: false }) === 0)
  check('agentFailuresEnabled=undefined (omitted) defaults to 0',
    effectiveEpsilonTactical({ epsilonTactical: 0.9 }) === 0)
  check('agentFailuresEnabled=true passes the configured rate through',
    effectiveEpsilonTactical({ epsilonTactical: 0.9, agentFailuresEnabled: true }) === 0.9)
}

console.log(failures === 0 ? '\nAll checks passed.' : `\n${failures} check(s) FAILED.`)
process.exit(failures === 0 ? 0 : 1)
