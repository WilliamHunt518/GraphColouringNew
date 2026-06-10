/**
 * Faithful achievability engine — drives the REAL gameReducer headlessly.
 *
 * Nothing here re-implements game logic: missions spawn, drones travel, tasks
 * execute, drones fail, replacements arrive, greedy loiter/recovery all run
 * through the actual reducer. We only supply an automated "operator" that
 * dispatches the same actions the UI would, under a selectable policy.
 *
 * Run:  npx tsx sim/engine.mts [--duration=480] [--seeds=80]
 */

console.debug = () => {}  // silence greedyAssign trace
import { buildInitialState, gameReducer } from '../src/store/gameReducer.ts'
import { generateSessionPlan, TASK_PRIMARY, ASSET_SPEED, createInitialAssets } from '../src/utils/missionGen.ts'
import { SeededRNG } from '../src/utils/prng.ts'
import type { GameState, GameAction, StudyConfig, Complexity, AssetType, TaskType, AssetRequirement, Asset } from '../src/types/index.ts'

type Policy = 'redundant' | 'lean'
const SCENARIOS: Complexity[] = ['balanced', 'tactical', 'strategic', 'full']
const TYPES: AssetType[] = ['Blue', 'Red', 'Green']
const DT = 0.5  // seconds per tick

const durArg = process.argv.find(a => a.startsWith('--duration='))
const DURATION = durArg ? parseInt(durArg.split('=')[1], 10) : 480
const seedArg = process.argv.find(a => a.startsWith('--seeds='))
const N_SEEDS = seedArg ? parseInt(seedArg.split('=')[1], 10) : 80

// ─── Candidate rebalance package (edit + re-run to tune) ─────────────────────
// Speeds mutate the real ASSET_SPEED object (shared by reducer + strategies).
// Fleets/λ override per scenario. Set PACKAGE.speeds=null to test current code.
interface Pkg {
  speeds: Record<AssetType, number> | null
  fleet: Record<Complexity, Record<AssetType, number>> | null
  lambdaScale: Record<Complexity, number>
}
// Real fleet straight from the source FLEET table (via createInitialAssets).
function liveFleet(c: Complexity): Record<AssetType, number> {
  const a = createInitialAssets(c)
  return { Blue: a.filter(x => x.type === 'Blue').length, Red: a.filter(x => x.type === 'Red').length, Green: a.filter(x => x.type === 'Green').length }
}
const CURRENT_FLEET: Record<Complexity, Record<AssetType, number>> = {
  balanced: liveFleet('balanced'), tactical: liveFleet('tactical'), strategic: liveFleet('strategic'),
  full: liveFleet('full'), quick: liveFleet('quick'),
}
const pkgArg = process.argv.find(a => a.startsWith('--pkg='))
const PKG_NAME = pkgArg ? pkgArg.split('=')[1] : 'baseline'

function uniform(b: number, r: number, g: number): Record<Complexity, Record<AssetType, number>> {
  const f = { Blue: b, Red: r, Green: g }
  return { balanced: f, tactical: f, strategic: f, full: f, quick: { Blue: 5, Red: 5, Green: 5 } }
}
function noScale(): Record<Complexity, number> { return { balanced: 1, tactical: 1, strategic: 1, full: 1, quick: 1 } }
// Per-scenario λ override (scale>1 = slower arrivals / fewer missions).
function scales(balanced: number, tactical: number, strategic: number, full: number): Record<Complexity, number> {
  return { balanced, tactical, strategic, full, quick: 1 }
}

const PACKAGES: Record<string, Pkg> = {
  baseline: { speeds: null, fleet: null, lambdaScale: { balanced: 1, tactical: 1, strategic: 1, full: 1, quick: 1 } },
  P1: {
    speeds: { Blue: 9.0, Red: 7.0, Green: 5.5 },
    fleet: {
      balanced:  { Blue: 11, Red: 11, Green: 12 },
      tactical:  { Blue: 11, Red: 11, Green: 12 },
      strategic: { Blue: 11, Red: 11, Green: 12 },
      full:      { Blue: 13, Red: 14, Green: 15 },
      quick:     { Blue: 5,  Red: 5,  Green: 5 },
    },
    lambdaScale: { balanced: 1, tactical: 1, strategic: 1, full: 1, quick: 1 },
  },
  // Leaner fleets, slightly bigger Green speed buff.
  P2: {
    speeds: { Blue: 9.0, Red: 7.0, Green: 6.0 },
    fleet: {
      balanced:  { Blue: 10, Red: 10, Green: 10 },
      tactical:  { Blue: 10, Red: 10, Green: 10 },
      strategic: { Blue: 10, Red: 10, Green: 10 },
      full:      { Blue: 12, Red: 13, Green: 13 },
      quick:     { Blue: 5,  Red: 5,  Green: 5 },
    },
    lambdaScale: { balanced: 1, tactical: 1, strategic: 1, full: 1, quick: 1 },
  },
  // Smallest speed buff ("a little"), lean Green-focused fleet bump.
  P3: {
    speeds: { Blue: 9.0, Red: 6.8, Green: 5.4 },
    fleet: {
      balanced:  { Blue: 10, Red: 10, Green: 11 },
      tactical:  { Blue: 10, Red: 10, Green: 11 },
      strategic: { Blue: 10, Red: 10, Green: 11 },
      full:      { Blue: 12, Red: 13, Green: 14 },
      quick:     { Blue: 5,  Red: 5,  Green: 5 },
    },
    lambdaScale: { balanced: 1, tactical: 1, strategic: 1, full: 1, quick: 1 },
  },
  // Uniform-fleet candidates (same fleet every scenario; identity = mission size + λ only).
  U1: { speeds: { Blue: 9.0, Red: 6.8, Green: 5.4 }, fleet: uniform(11, 11, 12), lambdaScale: noScale() },
  U2: { speeds: { Blue: 9.0, Red: 6.8, Green: 5.4 }, fleet: uniform(12, 12, 13), lambdaScale: noScale() },
  U3: { speeds: { Blue: 9.0, Red: 6.8, Green: 5.4 }, fleet: uniform(12, 13, 14), lambdaScale: noScale() },
  // Uniform fleet + λ tuned to equalise difficulty (harden the lighter scenarios).
  UFa: { speeds: { Blue: 9.0, Red: 6.8, Green: 5.4 }, fleet: uniform(11, 11, 12), lambdaScale: scales(0.85, 0.80, 1, 1) },
  UFb: { speeds: { Blue: 9.0, Red: 6.8, Green: 5.4 }, fleet: uniform(12, 12, 13), lambdaScale: scales(0.82, 0.78, 0.95, 1) },
  // FINAL: modest speed buffs ("a little", colours stay distinct 9>6.8>5.4),
  // Green-focused fleet bumps (the bottleneck), all ≤15, λ + mission sizes untouched.
  PF: {
    speeds: { Blue: 9.0, Red: 6.8, Green: 5.4 },
    fleet: {
      balanced:  { Blue: 10, Red: 10, Green: 11 },
      tactical:  { Blue: 10, Red: 10, Green: 11 },
      strategic: { Blue: 10, Red: 10, Green: 12 },
      full:      { Blue: 12, Red: 13, Green: 14 },
      quick:     { Blue: 5,  Red: 5,  Green: 5 },
    },
    lambdaScale: { balanced: 1, tactical: 1, strategic: 1, full: 1, quick: 1 },
  },
}
const PACKAGE = PACKAGES[PKG_NAME] ?? PACKAGES.baseline
if (PACKAGE.speeds) Object.assign(ASSET_SPEED, PACKAGE.speeds)

function buildFleet(counts: Record<AssetType, number>): Asset[] {
  const assets: Asset[] = []
  for (const type of ['Blue', 'Red', 'Green'] as AssetType[]) {
    for (let i = 1; i <= counts[type]; i++) {
      assets.push({
        id: `${type[0]}${String(i).padStart(2, '0')}`, type, status: 'available',
        currentMissionId: null, currentTaskId: null,
        position: { x: 500, y: 400 }, travelFrom: { x: 500, y: 400 }, targetPosition: { x: 500, y: 400 },
        travelStartElapsed: 0, travelEndElapsed: 0, availableAt: 0, failedAt: null, replacementAt: null,
      } as Asset)
    }
  }
  return assets
}

function baseConfig(complexity: Complexity, seed: number): StudyConfig {
  return {
    participantId: 'SIM', condition: 'none', mode: 'agent', complexity, seed,
    agentErrorRate: 0, epsilonTactical: 0, tacticalMode: 'greedy',
    testingMode: false, tutorialMode: false, numSessions: 1,
  } as StudyConfig
}

/** Sequential floor of a mission's tasks (max primary requirement per type). */
function floor(tasks: { type: number }[]): AssetRequirement {
  const r: AssetRequirement = { Blue: 0, Red: 0, Green: 0 }
  for (const t of tasks) {
    const c = TASK_PRIMARY[t.type as TaskType]
    r.Blue = Math.max(r.Blue, c.Blue); r.Red = Math.max(r.Red, c.Red); r.Green = Math.max(r.Green, c.Green)
  }
  return r
}

function reserveOf(state: GameState): AssetRequirement {
  return {
    Blue:  state.assets.filter(a => a.type === 'Blue'  && a.status === 'available').length,
    Red:   state.assets.filter(a => a.type === 'Red'   && a.status === 'available').length,
    Green: state.assets.filter(a => a.type === 'Green' && a.status === 'available').length,
  }
}

// ─── Automated operator ─────────────────────────────────────────────────────

function operate(state: GameState, policy: Policy): GameState {
  let s = state
  const D = (a: GameAction) => { s = gameReducer(s, a) }

  // 1. Resolve any pending failure recoveries (smart operator always recovers).
  for (const m of s.missions) {
    if (!m.failureRecoveryPending) continue
    const opt = m.pendingRecoveryOptions?.find(o => o.type === 'redistribute')
    if (opt?.feasible) { D({ type: 'ACCEPT_RECOVERY', missionId: m.id, recoveryType: 'redistribute' }); continue }
    // Manual recovery: assign an available drone of a type the failed task needs.
    const failedTask = m.tasks.find(t => t.status === 'pending' && t.assignedAssetIds.length < neededCount(t.type))
      ?? m.tasks.find(t => t.status === 'pending')
    if (!failedTask) continue
    const need = TASK_PRIMARY[failedTask.type as TaskType]
    const wantType = (['Green', 'Red', 'Blue'] as AssetType[]).find(tp => need[tp] > 0)
    const drone = s.assets.find(a => a.status === 'available' && (!wantType || a.type === wantType))
      ?? s.assets.find(a => a.status === 'available')
    if (drone) D({ type: 'APPLY_MANUAL_RECOVERY', missionId: m.id, taskId: failedTask.id, newAssetId: drone.id })
    // else: wait — the failed drone re-enters the reserve shortly.
  }

  // 2. Allocate queued missions (highest penalty category first), while reserve allows.
  const queued = s.missions.filter(m => m.status === 'queued')
    .sort((a, b) => penaltyOrder(b.category) - penaltyOrder(a.category))
  for (const m of queued) {
    const reserve = reserveOf(s)
    const fl = floor(m.tasks)
    if (reserve.Blue < fl.Blue || reserve.Red < fl.Red || reserve.Green < fl.Green) continue  // can't even start; wait

    D({ type: 'OPEN_STRATEGIC', missionId: m.id })
    const modal = s.strategicModal
    if (!modal || modal.missionId !== m.id) continue
    if (policy === 'redundant') {
      const idx = modal.strategies.findIndex(st => st.name === 'Aggressive')
      const use = idx >= 0 ? idx : (modal.strategies.length ? 0 : -1)
      if (use < 0) { D({ type: 'CLOSE_STRATEGIC' }); continue }
      D({ type: 'APPLY_STRATEGIC', missionId: m.id, source: 'agent', strategyIndex: use, manualAllocation: null })
    } else {
      // lean: commit the minimal sequential floor manually (no redundancy spares)
      D({ type: 'APPLY_STRATEGIC', missionId: m.id, source: 'manual', strategyIndex: null, manualAllocation: fl })
    }
    // Confirm tactical plan (greedy auto-fills from available drones).
    if (s.missions.find(x => x.id === m.id)?.tacticalPending) {
      D({ type: 'CONFIRM_TACTICAL', missionId: m.id })
    }
  }
  return s
}

function neededCount(type: number): number {
  const c = TASK_PRIMARY[type as TaskType]; return c.Blue + c.Red + c.Green
}
function penaltyOrder(cat: string): number { return { A: 1, B: 2, C: 3, D: 4, E: 5 }[cat] ?? 0 }

// ─── Single session ─────────────────────────────────────────────────────────

interface Result {
  missions: number; missionsDone: number; tasks: number; tasksDone: number
  score: number; penalty: number; meanDone: number; unallocated: number; failures: number
}

function runSession(complexity: Complexity, seed: number): Record<Policy, Result> {
  const out = {} as Record<Policy, Result>
  for (const policy of ['redundant', 'lean'] as Policy[]) {
    const cfg = baseConfig(complexity, seed)
    let state = buildInitialState(cfg)
    // Override duration + regenerate the mission plan for the target session length.
    const lScale = PACKAGE.lambdaScale[complexity] ?? 1
    let bps = generateSessionPlan(new SeededRNG(seed ^ 1), complexity, DURATION / lScale)
    if (lScale !== 1) bps = bps.map(b => ({ ...b, arrivalTime: b.arrivalTime * lScale })).filter(b => b.arrivalTime <= DURATION)
    const fleetCounts = PACKAGE.fleet?.[complexity] ?? CURRENT_FLEET[complexity]
    state = { ...state, sessionDuration: DURATION, pendingBlueprints: bps, assets: buildFleet(fleetCounts) }

    const steps = Math.ceil(DURATION / DT) + 4
    for (let i = 0; i <= steps; i++) {
      const nowMs = i * DT * 1000
      state = gameReducer(state, { type: 'TICK', nowMs })
      state = operate(state, policy)
      if (state.elapsed >= DURATION) break
    }

    const spawned = state.missions
    const tasks = spawned.reduce((s, m) => s + m.tasks.length, 0)
    const tasksDone = spawned.reduce((s, m) => s + m.tasks.filter(t => t.status === 'completed').length, 0)
    const done = spawned.filter(m => m.status === 'completed')
    const compTimes = done.map(m => (m.completionTime ?? DURATION) - m.arrivalTime)
    const failures = state.events.flat().filter(e => e.type === 'drone_failure').length
    out[policy] = {
      missions: spawned.length, missionsDone: done.length, tasks, tasksDone,
      score: state.score, penalty: state.penaltyAccrued,
      meanDone: compTimes.length ? compTimes.reduce((a, b) => a + b, 0) / compTimes.length : 0,
      unallocated: spawned.filter(m => m.status === 'queued').length,
      failures,
    }
  }
  return out
}

// ─── Aggregate & report ───────────────────────────────────────────────────

function mean(xs: number[]) { return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0 }

function run() {
  console.log(`\n${'═'.repeat(100)}`)
  console.log(`FAITHFUL ENGINE   pkg=${PKG_NAME}  speeds ${ASSET_SPEED.Blue}/${ASSET_SPEED.Red}/${ASSET_SPEED.Green}  duration=${DURATION}s  seeds=${N_SEEDS}`)
  console.log('═'.repeat(100))

  for (const complexity of SCENARIOS) {
    const fc = PACKAGE.fleet?.[complexity] ?? CURRENT_FLEET[complexity]
    const acc: Record<Policy, Result[]> = { redundant: [], lean: [] }
    for (let s = 0; s < N_SEEDS; s++) {
      const seed = (98765 + s * 1013904223) >>> 0
      const r = runSession(complexity, seed)
      acc.redundant.push(r.redundant); acc.lean.push(r.lean)
    }
    console.log(`\n▌ ${complexity.toUpperCase()}   (${DURATION}s, fleet ${fc.Blue}B/${fc.Red}R/${fc.Green}G, λ×${(PACKAGE.lambdaScale[complexity] ?? 1)})`)
    for (const policy of ['redundant', 'lean'] as Policy[]) {
      const rs = acc[policy]
      const mDone = mean(rs.map(r => r.missionsDone)), mTot = mean(rs.map(r => r.missions))
      const tDone = mean(rs.map(r => r.tasksDone)), tTot = mean(rs.map(r => r.tasks))
      console.log(`  ${policy === 'redundant' ? 'SMART (redundant/Aggressive)' : 'LEAN  (minimal floor)       '}` +
        `  missions ${mDone.toFixed(1)}/${mTot.toFixed(1)} (${(100 * mDone / (mTot || 1)).toFixed(0)}%)` +
        `  tasks ${(100 * tDone / (tTot || 1)).toFixed(0)}%` +
        `  score ${mean(rs.map(r => r.score)).toFixed(0)}` +
        `  meanTime ${mean(rs.map(r => r.meanDone)).toFixed(0)}s` +
        `  failures ${mean(rs.map(r => r.failures)).toFixed(1)}`)
    }
  }
  console.log(`\n${'═'.repeat(100)}\n`)
}

run()
