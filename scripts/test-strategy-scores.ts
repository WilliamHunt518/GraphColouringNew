// Regression test for the Strategic Assistant's three card score bars.
// Run: npx tsx scripts/test-strategy-scores.ts
//
// Two bars were degenerate, and the pilot logs showed the damage:
//
//   * `speedScore` was a two-point min-max, so the slower card read EXACTLY 0% however small the
//     gap and 100% on a tie — only two reachable values. 63% of pilot cards read 0%, 37% tied.
//   * `reserveScore` was `1 - (Green*3 + Red)/max`: specialists COMMITTED, Blue ignored, again
//     normalised across the two cards so one always read 0%. It scored the card that held MORE
//     drones back as 0% in 57% of pilot presentations, contradicting the card's own
//     "reserve-preserving" text and the "Res:" counts printed beside it.
//
// Together those made Aggressive weakly dominate all three bars on ~48% of pilot cards — the
// Strategic Assistant was routinely showing a strictly-worse second option while claiming to be
// error-free (eps_S = 0).
//
// Speed is now best-ETA/this-ETA, Reserve is now the share of the reserve left behind.
import { generateStrategies } from '../src/utils/copilot'
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

// A few mission shapes, so the checks below are not a single lucky draw.
const MISSIONS: Array<{ name: string; tasks: Task[] }> = [
  { name: 'Cat A — T5 + T3',        tasks: [task('t1', 5, { x: 700, y: 400 }), task('t2', 3, { x: 740, y: 430 })] },
  { name: 'Cat B — T5 + T3 + T2',   tasks: [task('t1', 5, { x: 300, y: 300 }), task('t2', 3, { x: 340, y: 340 }), task('t3', 2, { x: 280, y: 360 })] },
  { name: 'Cat E — 2×T1 + 3×T2 + T5', tasks: [
      task('t1', 1, { x: 800, y: 200 }), task('t2', 1, { x: 830, y: 240 }),
      task('t3', 2, { x: 780, y: 260 }), task('t4', 2, { x: 810, y: 300 }), task('t5', 2, { x: 850, y: 210 }),
      task('t6', 5, { x: 820, y: 270 }),
  ] },
]

const total = (a: AssetRequirement) => a.Blue + a.Red + a.Green
const RESERVE_TOTAL = total(RESERVE)

let anyDominated = 0
let cards = 0

for (const m of MISSIONS) {
  const strategies = generateStrategies(m.tasks, RESERVE, 0, new SeededRNG(42))
  const agg = strategies.find(s => s.name === 'Aggressive')!
  const cons = strategies.find(s => s.name === 'Conservative')!
  cards++

  console.log(`\n── ${m.name}`)
  for (const s of [agg, cons]) {
    console.log(`   ${s.name.padEnd(13)} pool=${s.assets.Blue}F/${s.assets.Red}L/${s.assets.Green}C ` +
      `eta=${s.expectedCompletionTime.toFixed(0)}s  speed=${(s.speedScore * 100).toFixed(0)}%  ` +
      `reserve=${(s.reserveScore * 100).toFixed(0)}%  resilience=${(s.redundancyScore * 100).toFixed(0)}%`)
  }

  // 1. Every score is a real proportion.
  for (const s of [agg, cons]) {
    const inRange = [s.speedScore, s.reserveScore, s.redundancyScore]
      .every(v => Number.isFinite(v) && v >= 0 && v <= 1)
    check(`${m.name}: ${s.name} scores are finite and in [0,1]`, inRange,
      { speed: s.speedScore, reserve: s.reserveScore, resilience: s.redundancyScore })
  }

  // 2. Reserve reads what it says: the share of the reserve LEFT BEHIND.
  for (const s of [agg, cons]) {
    const expected = total(s.reserveAfter) / RESERVE_TOTAL
    check(`${m.name}: ${s.name} reserve score == drones left / reserve`,
      Math.abs(s.reserveScore - expected) < 1e-9,
      { got: +s.reserveScore.toFixed(4), expected: +expected.toFixed(4) })
  }

  // 3. The card committing FEWER drones must never score WORSE on reserve. This is the exact
  //    inversion the old specialists-committed metric produced.
  const aggCommitted = total(agg.assets)
  const consCommitted = total(cons.assets)
  if (aggCommitted !== consCommitted) {
    const leaner = aggCommitted < consCommitted ? agg : cons
    const heavier = aggCommitted < consCommitted ? cons : agg
    check(`${m.name}: leaner commitment (${leaner.name}) scores higher on Reserve`,
      leaner.reserveScore > heavier.reserveScore,
      { [leaner.name]: +leaner.reserveScore.toFixed(3), [heavier.name]: +heavier.reserveScore.toFixed(3) })
  }

  // 4. Speed is a ratio, not a two-valued flag: the faster card is exactly 1, and the slower one
  //    is strictly between 0 and 1 rather than pinned to 0.
  const fastest = Math.min(agg.expectedCompletionTime, cons.expectedCompletionTime)
  for (const s of [agg, cons]) {
    const expected = fastest / s.expectedCompletionTime
    check(`${m.name}: ${s.name} speed score == best ETA / own ETA`,
      Math.abs(s.speedScore - expected) < 1e-9,
      { got: +s.speedScore.toFixed(4), expected: +expected.toFixed(4) })
  }
  if (Math.abs(agg.expectedCompletionTime - cons.expectedCompletionTime) > 1e-6) {
    const slower = agg.expectedCompletionTime > cons.expectedCompletionTime ? agg : cons
    check(`${m.name}: the slower card is not pinned to 0% speed`, slower.speedScore > 0,
      { [slower.name]: +slower.speedScore.toFixed(3) })
  }

  // 5. Neither card is weakly dominated on all three bars in these shapes — a genuine trade-off
  //    is on offer, which is the whole point of presenting two cards.
  const dominates = (a: typeof agg, b: typeof agg) =>
    a.speedScore >= b.speedScore && a.reserveScore >= b.reserveScore && a.redundancyScore >= b.redundancyScore
  if (dominates(agg, cons) || dominates(cons, agg)) anyDominated++
}

console.log()
check('no mission shape presents a wholly dominated option', anyDominated === 0,
  { dominatedShapes: anyDominated, of: cards })

console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILED`)
process.exit(failures === 0 ? 0 : 1)
