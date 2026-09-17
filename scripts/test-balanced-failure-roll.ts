// Regression test for the balanced (stratified) ε_Strategic/ε_Tactical fire draw (study-v1.11).
// Run: npx tsx scripts/test-balanced-failure-roll.ts
//
// Independent per-check Bernoulli draws are unbiased in expectation but have real variance at the
// check counts one participant actually sees (~6-20 missions per session) — two participants on the
// identical epsilon could see visibly different realized failure counts by chance. drawBalancedRoll
// replaces this with a pre-shuffled batch of exactly round(epsilon * batchSize) hits per batchSize
// slots, so a completed batch always contains exactly the configured proportion, in a
// seed-reproducible but unpredictable order.
//
// This checks: a full batch always contains exactly the rounded hit count; consecutive batches
// aren't identical; the sequence is fully reproducible from (seed, salt); epsilon<=0 never touches
// the queue; and (at the gameReducer integration level) reopening a mission's strategic modal
// (OVERRIDE_TACTICAL) never consumes a second slot for the same mission.
import { drawBalancedRoll, initialBalancedRollState, FAILURE_BALANCE_BATCH_SIZE, STRATEGIC_FAILURE_SALT } from '../src/utils/balancedRoll'
import { buildInitialState, gameReducer } from '../src/store/gameReducer'
import type { GameState, StudyConfig, Mission, Task, Asset } from '../src/types'

let failures = 0
const check = (label: string, cond: boolean, detail?: unknown) => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}${detail !== undefined ? `  — ${JSON.stringify(detail)}` : ''}`)
  if (!cond) failures++
}

// ── 1. A full batch always contains exactly round(epsilon * batchSize) hits ────────────────────
{
  for (const epsilon of [0.1, 0.3, 0.5, 0.7, 0.9, 1.0]) {
    let state = initialBalancedRollState
    let fires = 0
    for (let i = 0; i < FAILURE_BALANCE_BATCH_SIZE; i++) {
      const draw = drawBalancedRoll(state, epsilon, 42, STRATEGIC_FAILURE_SALT)
      state = draw.state
      if (draw.fired) fires++
    }
    const expected = Math.round(epsilon * FAILURE_BALANCE_BATCH_SIZE)
    check(`epsilon=${epsilon}: a full batch of ${FAILURE_BALANCE_BATCH_SIZE} contains exactly ${expected} fires`, fires === expected, { fires })
  }
}

// ── 2. Multiple consecutive full batches each independently hit the exact proportion ────────────
{
  const epsilon = 0.7
  let state = initialBalancedRollState
  const batchCounts: number[] = []
  for (let b = 0; b < 5; b++) {
    let fires = 0
    for (let i = 0; i < FAILURE_BALANCE_BATCH_SIZE; i++) {
      const draw = drawBalancedRoll(state, epsilon, 7, STRATEGIC_FAILURE_SALT)
      state = draw.state
      if (draw.fired) fires++
    }
    batchCounts.push(fires)
  }
  const expected = Math.round(epsilon * FAILURE_BALANCE_BATCH_SIZE)
  check(`epsilon=0.7: every one of 5 consecutive batches hits exactly ${expected} fires`,
    batchCounts.every(c => c === expected), { batchCounts })
}

// ── 3. Same (seed, salt) reproduces the identical sequence; a different seed usually diverges ───
{
  const draws = (seed: number, n: number) => {
    let state = initialBalancedRollState
    const out: boolean[] = []
    for (let i = 0; i < n; i++) {
      const d = drawBalancedRoll(state, 0.5, seed, STRATEGIC_FAILURE_SALT)
      state = d.state
      out.push(d.fired)
    }
    return out
  }
  const a = draws(99, 40)
  const b = draws(99, 40)
  const c = draws(100, 40)
  check('same seed reproduces the identical fire sequence', JSON.stringify(a) === JSON.stringify(b))
  check('a different seed produces a different sequence', JSON.stringify(a) !== JSON.stringify(c))
}

// ── 4. epsilon <= 0 never fires and never advances the queue ────────────────────────────────────
{
  let state = initialBalancedRollState
  let anyFired = false
  for (let i = 0; i < 50; i++) {
    const draw = drawBalancedRoll(state, 0, 1, STRATEGIC_FAILURE_SALT)
    state = draw.state
    if (draw.fired) anyFired = true
  }
  check('epsilon=0 never fires (50 draws)', !anyFired)
  check('epsilon=0 never consumes/builds the queue', state.queue.length === 0 && state.batchNumber === 0)
}

// ── 5. gameReducer integration: reopening a mission's strategic modal (OVERRIDE_TACTICAL) reuses
//      the cached decision instead of drawing a second slot from the balanced queue. Without this,
//      an operator who dismisses-and-reallocates would silently burn extra queue slots per redo,
//      breaking the "one real mission = one check" guarantee the balanced batch depends on.
{
  const WP = { x: 700, y: 400 }
  const cfg: StudyConfig = {
    participantId: 'TEST', condition: 'none', mode: 'agent', complexity: 'balanced',
    seed: 123, agentErrorRate: 1, epsilonTactical: 0, tacticalMode: 'plan-all',
    testingMode: true, tutorialMode: false, numSessions: 1, agentFailuresEnabled: true,
  }
  function task(id: string, type: number): Task {
    return {
      id, missionId: 'M1', type, status: 'pending', assignedAssetIds: [], waypoint: WP,
      allocatedAt: null, travelTime: 0, baseTime: 10, useSubstitute: false,
      startTime: null, completionTime: null, recallDelay: 0, completedSectionTypes: [],
    } as unknown as Task
  }
  function mission(): Mission {
    return {
      id: 'M1', category: 'C', status: 'queued', zoneCenter: WP, zoneRadius: 80,
      tasks: [task('M1-T1', 5), task('M1-T2', 3)],
      arrivalTime: 0, allocationTime: null, completionTime: null,
      agentInteraction: 'none', chosenStrategyName: null, manualPriorityIds: [],
      tacticalPending: false, pendingAllocation: null, tacticalOpenedAtMs: null, droneSequences: {},
      droneFailuresFired: 0, failedDroneId: null, failureRecoveryPending: false,
      failureExemptUntil: null, pendingRecoveryOptions: null,
      tacticallySuppressedTaskId: null, abandonedAt: null, isResidual: false, needsGreedyReplan: false,
    } as unknown as Mission
  }
  const N_DRONES = 33
  const reserve = (): Asset[] => Array.from({ length: N_DRONES }, (_, i) => ({
    id: `D${String(i + 1).padStart(2, '0')}`, type: (['Blue', 'Red', 'Green'] as const)[i % 3],
    status: 'available', currentMissionId: null, currentTaskId: null,
    position: { ...WP }, travelFrom: { ...WP }, targetPosition: { ...WP },
    travelStartElapsed: 0, travelEndElapsed: 0, availableAt: 0, failedAt: null, replacementAt: null,
  } as unknown as Asset))

  let s: GameState = { ...buildInitialState(cfg), missions: [mission()], assets: reserve(), phase: 'playing' }
  s = gameReducer(s, { type: 'OPEN_STRATEGIC', missionId: 'M1' })
  const missionAfterOpen = s.missions.find(m => m.id === 'M1')!
  const queueAfterOpen = s.strategicFailureRoll

  // Dismiss-and-reopen twice (mirrors OVERRIDE_TACTICAL only being reachable once a strategy has
  // actually been applied — apply Manual first, then override back to the strategic modal).
  s = gameReducer(s, {
    type: 'APPLY_STRATEGIC', missionId: 'M1', source: 'manual',
    strategyIndex: null, manualAllocation: { Blue: 2, Red: 1, Green: 1 },
  } as any)
  s = gameReducer(s, { type: 'OVERRIDE_TACTICAL', missionId: 'M1' })
  const missionAfterOverride1 = s.missions.find(m => m.id === 'M1')!
  const queueAfterOverride1 = s.strategicFailureRoll

  s = gameReducer(s, {
    type: 'APPLY_STRATEGIC', missionId: 'M1', source: 'manual',
    strategyIndex: null, manualAllocation: { Blue: 2, Red: 1, Green: 1 },
  } as any)
  s = gameReducer(s, { type: 'OVERRIDE_TACTICAL', missionId: 'M1' })
  const missionAfterOverride2 = s.missions.find(m => m.id === 'M1')!
  const queueAfterOverride2 = s.strategicFailureRoll

  check('strategicFailureFired is cached after the first OPEN_STRATEGIC', missionAfterOpen.strategicFailureFired !== undefined)
  check('OVERRIDE_TACTICAL #1 does not change the cached decision',
    missionAfterOverride1.strategicFailureFired === missionAfterOpen.strategicFailureFired &&
    missionAfterOverride1.strategicFailureColour === missionAfterOpen.strategicFailureColour)
  check('OVERRIDE_TACTICAL #2 does not change the cached decision',
    missionAfterOverride2.strategicFailureFired === missionAfterOpen.strategicFailureFired &&
    missionAfterOverride2.strategicFailureColour === missionAfterOpen.strategicFailureColour)
  check('the balanced queue advances exactly once total across OPEN_STRATEGIC + two OVERRIDE_TACTICAL round trips',
    queueAfterOpen.index === 1 && queueAfterOverride1.index === 1 && queueAfterOverride2.index === 1,
    { openIndex: queueAfterOpen.index, override1Index: queueAfterOverride1.index, override2Index: queueAfterOverride2.index })
}

console.log(failures === 0 ? '\nAll checks passed.' : `\n${failures} check(s) FAILED.`)
process.exit(failures === 0 ? 0 : 1)
