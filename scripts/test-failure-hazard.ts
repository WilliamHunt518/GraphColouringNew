// Regression test: the ambient drone-failure hazard must be frame-rate independent and must fire
// at FAILURE_RATE_PER_DRONE_SECOND. Run: npx tsx scripts/test-failure-hazard.ts
//
// Until study-v1.4 the hazard rolled once per rAF frame with p = rate × dt, reseeding a SeededRNG
// per (drone, tick) and reading its FIRST output. That draw's lower tail is not uniform over the
// seed family the scheme can reach, so the realized rate fell away as dt shrank: about right at
// 60 fps, ~4× low at 120 fps, and identically ZERO at ≥144 fps. A participant on a high-refresh
// display therefore met no drone failures at all — the study build's only scripted adversity —
// while sim/engine.mts (0.25–1 s steps, safely inside the working regime) calibrated as if they
// had. Confirmed live: a full two-session browser run on a ~170 Hz display logged 0 failures
// against ~5,700 deployed drone-seconds (≈6.3 expected).
//
// Now the roll happens on a fixed simulated grid (FAILURE_ROLL_INTERVAL), so tick rate cannot
// change the hazard at all. Both properties are pinned below.
import { buildInitialState, gameReducer } from '../src/store/gameReducer'
import type { GameState, StudyConfig, Mission, Task, Asset } from '../src/types'
import { FAILURE_RATE_PER_DRONE_SECOND } from '../src/utils/missionGen'

let failures = 0
const check = (label: string, cond: boolean) => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}`)
  if (!cond) failures++
}

const WP = { x: 700, y: 400 }
const cfg = (seed: number): StudyConfig => ({
  participantId: 'TEST', condition: 'HH', mode: 'agent', complexity: 'balanced',
  seed, agentErrorRate: 0, epsilonTactical: 0, tacticalMode: 'plan-all',
  testingMode: false, tutorialMode: false, numSessions: 1,
})

// A never-startable pending task keeps the mission 'active' (so its drones stay eligible) without
// anything completing; the drones loiter unassigned, which is the branch that needs no recovery.
function idleMission(): Mission {
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
    droneFailuresFired: 0, failedDroneId: null, failureRecoveryPending: false, pendingRecoveryOptions: null,
    tacticallySuppressedTaskId: null, abandonedAt: null, isResidual: false, needsGreedyReplan: false,
  } as unknown as Mission
}

const N_DRONES = 33
function loiterers(): Asset[] {
  return Array.from({ length: N_DRONES }, (_, i) => ({
    id: `B${String(i + 1).padStart(2, '0')}`, type: (['Blue', 'Red', 'Green'] as const)[i % 3],
    status: 'deployed', currentMissionId: 'M1', currentTaskId: null,
    position: { ...WP }, travelFrom: { ...WP }, targetPosition: { ...WP },
    travelStartElapsed: 0, travelEndElapsed: 0, availableAt: 0, failedAt: null, replacementAt: null,
  } as unknown as Asset))
}

// Run `seconds` of simulated time at `fps`, return the drone_failure events logged.
function runSession(seed: number, fps: number, seconds: number) {
  let s: GameState = {
    ...buildInitialState(cfg(seed)), config: cfg(seed), phase: 'playing', sessionStartMs: 0,
    elapsed: 0, missions: [idleMission()], assets: loiterers(),
  }
  const dt = 1 / fps
  for (let e = dt; e <= seconds; e += dt) s = gameReducer(s, { type: 'TICK', nowMs: e * 1000 } as any)
  return s.events[0].filter((e: any) => e.type === 'drone_failure')
    .map((e: any) => `${e.droneId}@${Math.round(e.elapsed)}`)
}

// ── 1. Identical outcome at every tick rate (the actual bug) ──────────────
{
  const SECONDS = 150
  const at1 = runSession(7, 1, SECONDS)         // headless harness cadence
  const at60 = runSession(7, 60, SECONDS)       // 60 Hz display
  const at165 = runSession(7, 165, SECONDS)     // high-refresh display — used to be silent
  console.log(`   failures in ${SECONDS}s @1fps/60fps/165fps: ${at1.length}/${at60.length}/${at165.length}`)
  check('hazard fires at all on a high-refresh tick rate', at165.length > 0)
  check('165 fps === 60 fps (same drones, same seconds)', at165.join() === at60.join())
  check('165 fps === 1 fps  (same drones, same seconds)', at165.join() === at1.join())
}

// ── 2. Rate calibration: mean failures ≈ analytic expectation ─────────────
{
  const SECONDS = 300, SEEDS = 25
  let total = 0
  for (let seed = 1; seed <= SEEDS; seed++) total += runSession(seed, 2, SECONDS).length
  const mean = total / SEEDS
  // Failed drones leave the eligible pool, so exposure decays: E = N·(1 − e^(−rate·T)).
  const expected = N_DRONES * (1 - Math.exp(-FAILURE_RATE_PER_DRONE_SECOND * SECONDS))
  const ratio = mean / expected
  console.log(`   mean over ${SEEDS} seeds = ${mean.toFixed(2)} vs expected ${expected.toFixed(2)} (ratio ${ratio.toFixed(2)})`)
  check('realized rate within 25% of FAILURE_RATE_PER_DRONE_SECOND', ratio > 0.75 && ratio < 1.25)
}

console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILED`)
process.exit(failures === 0 ? 0 : 1)
