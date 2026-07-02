// Analytic demand/balance harness — the fast inner loop for scenario tuning.
//
// Drives the REAL generateSessionPlan over many seeds and measures per-colour drone-seconds of
// demand (primary compositions: execution + hub↔waypoint round-trip travel) against fleet supply.
// Reads live constants from missionGen.ts, so editing ASSET_SPEED / LAMBDA / CATEGORY_WEIGHTS /
// archetype weights and re-running immediately reflects the change — no duplicated task tables.
//
//   npx tsx sim/demand.mts [--seeds=400]
//
// Reports, per complexity: per-colour utilisation, the max−min colour spread (balance target),
// and the total-util ratio of tactical vs strategic (cross-scenario parity target).
import {
  generateSessionPlan, createInitialAssets, HUB, ASSET_SPEED, TASK_PRIMARY, TASK_BASE_TIME,
} from '../src/utils/missionGen.ts'
import { SeededRNG } from '../src/utils/prng.ts'
import type { Complexity, AssetType, TaskType } from '../src/types/index.ts'

const TYPES: AssetType[] = ['Blue', 'Red', 'Green']
const SCEN: Complexity[] = ['balanced', 'tactical', 'strategic', 'full']
const DUR = 480
const seedArg = process.argv.find(a => a.startsWith('--seeds='))
const N = seedArg ? parseInt(seedArg.split('=')[1], 10) : 400
const dist = (a: { x: number; y: number }, b: { x: number; y: number }) => Math.hypot(a.x - b.x, a.y - b.y)

function fleetOf(c: Complexity): Record<AssetType, number> {
  const a = createInitialAssets(c)
  return {
    Blue: a.filter(x => x.type === 'Blue').length,
    Red: a.filter(x => x.type === 'Red').length,
    Green: a.filter(x => x.type === 'Green').length,
  }
}

// Mean per-colour utilisation (demand-seconds ÷ supply-seconds) and mean mission/task counts.
function analyse(c: Complexity) {
  const fleet = fleetOf(c)
  const utilSum: Record<AssetType, number> = { Blue: 0, Red: 0, Green: 0 }
  let missions = 0, tasks = 0, travelDS = 0, execDS = 0
  for (let s = 0; s < N; s++) {
    const seed = (1234567 + s * 2654435761) >>> 0
    const bps = generateSessionPlan(new SeededRNG(seed), c, DUR)
    missions += bps.length
    const ds: Record<AssetType, number> = { Blue: 0, Red: 0, Green: 0 }
    for (const bp of bps) {
      tasks += bp.taskTypes.length
      bp.taskTypes.forEach((type, i) => {
        const comp = TASK_PRIMARY[type as TaskType]
        const base = TASK_BASE_TIME[type as TaskType]
        const wp = bp.waypoints[i]
        const trip = dist(HUB, wp)
        for (const tp of TYPES) {
          const n = comp[tp]
          if (n > 0) {
            const exec = n * base
            const travel = n * (2 * trip / ASSET_SPEED[tp])
            ds[tp] += exec + travel
            execDS += exec; travelDS += travel
          }
        }
      })
    }
    for (const tp of TYPES) utilSum[tp] += ds[tp] / (fleet[tp] * DUR)
  }
  const util: Record<AssetType, number> = {
    Blue: utilSum.Blue / N, Red: utilSum.Red / N, Green: utilSum.Green / N,
  }
  const vals = TYPES.map(t => util[t])
  const spread = Math.max(...vals) - Math.min(...vals)
  const total = vals.reduce((a, b) => a + b, 0) / TYPES.length
  return { fleet, util, spread, total, missions: missions / N, tasks: tasks / N, travelShare: travelDS / (travelDS + execDS) }
}

console.log(`Demand/balance model — ${N} seeds, ${DUR}s, fleet supply = count × ${DUR}s`)
console.log(`Speeds: Blue ${ASSET_SPEED.Blue} / Red ${ASSET_SPEED.Red} / Green ${ASSET_SPEED.Green}  (spread ${(ASSET_SPEED.Blue / ASSET_SPEED.Green).toFixed(2)}×)`)
const totals: Partial<Record<Complexity, number>> = {}
for (const c of SCEN) {
  const r = analyse(c)
  totals[c] = r.total
  const bal = r.spread <= 0.05 ? '✅' : r.spread <= 0.08 ? '🟡' : '🔴'
  console.log(
    `\n=== ${c.toUpperCase()} ===  fleet ${r.fleet.Blue}/${r.fleet.Red}/${r.fleet.Green}` +
    `  missions ${r.missions.toFixed(1)}  tasks ${r.tasks.toFixed(1)}  travelShare ${(100 * r.travelShare).toFixed(0)}%`,
  )
  console.log(
    `    util  Blue ${(100 * r.util.Blue).toFixed(0)}%  Red ${(100 * r.util.Red).toFixed(0)}%  Green ${(100 * r.util.Green).toFixed(0)}%` +
    `   | spread ${(100 * r.spread).toFixed(1)}pts ${bal}   | total ${(100 * r.total).toFixed(0)}%`,
  )
}
if (totals.tactical && totals.strategic) {
  const ratio = totals.tactical / totals.strategic
  const par = ratio >= 0.9 && ratio <= 1.1 ? '✅' : '🔴'
  console.log(`\nParity  tactical/strategic total-util ratio = ${ratio.toFixed(2)} ${par}` +
    `  (tac ${(100 * totals.tactical).toFixed(0)}%  strat ${(100 * totals.strategic).toFixed(0)}%)`)
}
