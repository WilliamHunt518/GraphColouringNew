// Regression test for the ε_Strategic agent-reliability failure (study-v1.10).
// Run: npx tsx scripts/test-strategic-failure.ts
//
// The manipulation was redesigned from "nudge each card's numbers independently" to a single
// per-mission roll that, when it fires, corrupts BOTH cards with the SAME mistake:
//   'over'  — +STRATEGIC_OVER_DELTA drones of one random colour (wastes reserve, no feasibility risk)
//   'under' — -1 drone from a colour that carries redundancy buffer, floored at that card's own
//             sequential minimum (never causes infeasibility or a dropped task — only removes slack)
// This checks: both cards are corrupted consistently when it fires; a card is never pushed below
// its feasible floor; firing frequency roughly matches the configured epsilon; and the master
// agentFailuresEnabled gate actually suppresses everything when off.
import { generateStrategies } from '../src/utils/copilot'
import { effectiveEpsilonStrategic } from '../src/utils/config'
import { SeededRNG } from '../src/utils/prng'
import type { AssetRequirement, Task } from '../src/types'

let failures = 0
const check = (label: string, cond: boolean, detail?: unknown) => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}${detail !== undefined ? `  — ${JSON.stringify(detail)}` : ''}`)
  if (!cond) failures++
}

function task(id: string, type: number, waypoint: { x: number; y: number }): Task {
  return {
    id, missionId: 'M1', type, status: 'pending',
    assignedAssetIds: [], waypoint,
    allocatedAt: null, travelTime: 0, baseTime: 0, useSubstitute: false,
    startTime: null, completionTime: null, recallDelay: 0, completedSectionTypes: [],
  } as unknown as Task
}

const RESERVE: AssetRequirement = { Blue: 11, Red: 11, Green: 11 }
const MISSION_TASKS: Task[] = [
  task('t1', 5, { x: 700, y: 400 }), task('t2', 3, { x: 740, y: 430 }), task('t3', 2, { x: 680, y: 420 }),
]

// ── 1. epsilon = 0 never fires, across many seeds ──────────────────────────
{
  let anyBad = false
  for (let seed = 0; seed < 200; seed++) {
    const strategies = generateStrategies(MISSION_TASKS, RESERVE, 0, new SeededRNG(seed))
    if (strategies.some(s => s.isBadSuggestion)) anyBad = true
  }
  check('epsilon=0 never produces a bad suggestion (200 seeds)', !anyBad)
}

// ── 2. epsilon = 1 always fires, and both cards get the SAME failure type when both are affected ──
{
  let bothAffected = 0
  let typeMismatch = 0
  let neverInfeasible = true
  for (let seed = 0; seed < 300; seed++) {
    const strategies = generateStrategies(MISSION_TASKS, RESERVE, 1, new SeededRNG(seed))
    const agg = strategies.find(s => s.name === 'Aggressive')
    const cons = strategies.find(s => s.name === 'Conservative')
    if (!agg || !cons) continue
    // Feasibility: trueAssets must never be negative or exceed reserve.
    for (const s of [agg, cons]) {
      for (const t of ['Blue', 'Red', 'Green'] as const) {
        if (s.trueAssets[t] < 0 || s.trueAssets[t] > RESERVE[t]) neverInfeasible = false
      }
    }
    if (agg.isBadSuggestion && cons.isBadSuggestion) {
      bothAffected++
      if (agg.badSuggestionType !== cons.badSuggestionType) typeMismatch++
    }
  }
  check('epsilon=1: trueAssets never negative or over reserve (300 seeds)', neverInfeasible)
  check('epsilon=1: when both cards are affected, they share the same failure type', typeMismatch === 0, { bothAffected, typeMismatch })
  check('epsilon=1: both cards are affected in the common case (mission has buffer on both)', bothAffected > 250, { bothAffected })
}

// ── 3. 'under' never drops a card below its own feasible floor (== minimumAssets) ──────────────
{
  let everBelowFloor = false
  for (let seed = 0; seed < 300; seed++) {
    const strategies = generateStrategies(MISSION_TASKS, RESERVE, 1, new SeededRNG(seed))
    for (const s of strategies) {
      if (s.badSuggestionType !== 'under') continue
      for (const t of ['Blue', 'Red', 'Green'] as const) {
        if (s.trueAssets[t] < s.minimumAssets[t]) everBelowFloor = true
      }
    }
  }
  check("'under' never drops trueAssets below minimumAssets (300 seeds)", !everBelowFloor)
}

// ── 4. Firing frequency roughly matches epsilon ─────────────────────────────
{
  const epsilon = 0.3
  const trials = 4000
  let fired = 0
  for (let seed = 0; seed < trials; seed++) {
    const strategies = generateStrategies(MISSION_TASKS, RESERVE, epsilon, new SeededRNG(seed * 7919 + 13))
    if (strategies.some(s => s.isBadSuggestion)) fired++
  }
  const rate = fired / trials
  check(`epsilon=0.3 fires at roughly the configured rate (got ${rate.toFixed(3)})`, Math.abs(rate - epsilon) < 0.03, { rate })
}

// ── 5. Both cards fail, or neither does — never one card only ──────────────────────────────────
{
  let asymmetric = 0
  for (let seed = 0; seed < 2000; seed++) {
    const strategies = generateStrategies(MISSION_TASKS, RESERVE, 0.5, new SeededRNG(seed))
    const agg = strategies.find(s => s.name === 'Aggressive')
    const cons = strategies.find(s => s.name === 'Conservative')
    if (!agg || !cons) continue
    if (agg.isBadSuggestion !== cons.isBadSuggestion) asymmetric++
  }
  check('never exactly one card marked bad (2000 seeds, epsilon=0.5)', asymmetric === 0, { asymmetric })
}

// ── 6. Materiality: 'over' always adds real headroom, 'under' always targets a NEEDED colour ────
{
  // Baseline (epsilon=0) is deterministic regardless of seed — no rng is consumed for a corruption
  // that never fires, and the pool math itself doesn't touch rng.
  const baseline = generateStrategies(MISSION_TASKS, RESERVE, 0, new SeededRNG(0))
  const baseAgg = baseline.find(s => s.name === 'Aggressive')!
  const baseCons = baseline.find(s => s.name === 'Conservative')!

  let overNeverAddsZero = true
  let underAlwaysNeeded = true
  let underAlwaysReduces = true
  for (let seed = 0; seed < 2000; seed++) {
    const strategies = generateStrategies(MISSION_TASKS, RESERVE, 0.5, new SeededRNG(seed))
    for (const s of strategies) {
      if (!s.isBadSuggestion || !s.badSuggestionColour) continue
      const base = s.name === 'Aggressive' ? baseAgg : baseCons
      const t = s.badSuggestionColour
      if (s.badSuggestionType === 'over' && s.trueAssets[t] <= base.trueAssets[t]) overNeverAddsZero = false
      if (s.badSuggestionType === 'under') {
        if (s.minimumAssets[t] <= 0) underAlwaysNeeded = false        // must be a genuinely required colour
        if (s.trueAssets[t] >= base.trueAssets[t]) underAlwaysReduces = false
      }
    }
  }
  check("'over' always adds at least one real drone of the targeted colour (2000 seeds)", overNeverAddsZero)
  check("'under' only ever targets a colour the mission actually needs (minimumAssets > 0) (2000 seeds)", underAlwaysNeeded)
  check("'under' always actually reduces the targeted colour vs the uncorrupted baseline (2000 seeds)", underAlwaysReduces)
}

// ── 7. The reported bug: an all-Blue mission must never have its unused Green spare "removed" as
//      a fake 'under' failure — Conservative's blanket top-up can leave Green > 0 despite floor 0.
{
  const ALL_BLUE_TASKS: Task[] = [
    task('t1', 1, { x: 700, y: 400 }), task('t2', 2, { x: 720, y: 410 }), task('t3', 1, { x: 690, y: 420 }),
  ]
  let everTargetedUnneededColour = false
  for (let seed = 0; seed < 2000; seed++) {
    const strategies = generateStrategies(ALL_BLUE_TASKS, RESERVE, 0.5, new SeededRNG(seed))
    for (const s of strategies) {
      if (s.isBadSuggestion && s.badSuggestionType === 'under' && s.badSuggestionColour) {
        if (s.minimumAssets[s.badSuggestionColour] <= 0) everTargetedUnneededColour = true
      }
    }
  }
  check('all-Blue mission: under-failure never targets Red/Green (unneeded, just top-up spares) (2000 seeds)',
    !everTargetedUnneededColour)
}

// ── 8. Global no-op sweep: across many mission shapes AND reserve levels (including tight ones,
//      which is exactly where a no-op is most likely — e.g. a scarce colour already maxed by
//      reserve before any failure), a card marked bad must NEVER equal its own epsilon=0 baseline on
//      the targeted colour. This is the user-facing bar directly: "an error that produces the same
//      result as no error isn't an error."
{
  const TASK_SETS: Record<string, Task[]> = {
    B1: [task('t1', 1, { x: 700, y: 400 }), task('t2', 3, { x: 720, y: 410 }), task('t3', 4, { x: 690, y: 420 })],
    B2: [task('t1', 2, { x: 700, y: 400 }), task('t2', 4, { x: 720, y: 410 }), task('t3', 3, { x: 690, y: 420 })],
    C1: [task('t1', 5, { x: 700, y: 400 }), task('t2', 3, { x: 720, y: 410 })],
    D1: [task('t1', 4, { x: 700, y: 400 }), task('t2', 4, { x: 720, y: 410 }), task('t3', 3, { x: 690, y: 420 }), task('t4', 5, { x: 680, y: 390 })],
    E1: [task('t1', 1, { x: 700, y: 400 }), task('t2', 1, { x: 720, y: 410 }), task('t3', 2, { x: 690, y: 420 }), task('t4', 3, { x: 680, y: 390 }), task('t5', 4, { x: 670, y: 410 }), task('t6', 5, { x: 660, y: 400 })],
  }
  const RESERVES: AssetRequirement[] = [
    { Blue: 5, Red: 5, Green: 3 },    // the exact tight case reported live (Green is the scarce colour)
    { Blue: 11, Red: 11, Green: 11 },
    { Blue: 6, Red: 4, Green: 2 },
    { Blue: 3, Red: 3, Green: 3 },
    { Blue: 1, Red: 1, Green: 1 },
    { Blue: 8, Red: 2, Green: 5 },
  ]
  let noOps = 0
  let totalBadCards = 0
  for (const tasks of Object.values(TASK_SETS)) {
    for (const res of RESERVES) {
      const baseline = generateStrategies(tasks, res, 0, new SeededRNG(0))
      const baseAgg = baseline.find(s => s.name === 'Aggressive')
      const baseCons = baseline.find(s => s.name === 'Conservative')
      if (!baseAgg || !baseCons) continue
      for (let seed = 0; seed < 300; seed++) {
        const strategies = generateStrategies(tasks, res, 1, new SeededRNG(seed))
        for (const [s, base] of [[strategies.find(x => x.name === 'Aggressive'), baseAgg], [strategies.find(x => x.name === 'Conservative'), baseCons]] as const) {
          if (!s || !s.isBadSuggestion || !s.badSuggestionColour) continue
          totalBadCards++
          if (s.trueAssets[s.badSuggestionColour] === base.trueAssets[s.badSuggestionColour]) noOps++
        }
      }
    }
  }
  check(`no bad-marked card is ever a no-op vs its own baseline (${totalBadCards} bad cards checked across 5 mission shapes × 6 reserve levels)`,
    noOps === 0, { noOps, totalBadCards })
}

// ── 9. Master toggle forces the effective epsilon to 0 regardless of configured rate ────────────
{
  check('agentFailuresEnabled=false forces effective epsilon to 0',
    effectiveEpsilonStrategic({ agentErrorRate: 0.9, agentFailuresEnabled: false }) === 0)
  check('agentFailuresEnabled=undefined (omitted) defaults to 0',
    effectiveEpsilonStrategic({ agentErrorRate: 0.9 }) === 0)
  check('agentFailuresEnabled=true passes the configured rate through',
    effectiveEpsilonStrategic({ agentErrorRate: 0.9, agentFailuresEnabled: true }) === 0.9)
}

console.log(failures === 0 ? '\nAll checks passed.' : `\n${failures} check(s) FAILED.`)
process.exit(failures === 0 ? 0 : 1)
