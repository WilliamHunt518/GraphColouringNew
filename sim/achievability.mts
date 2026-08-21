/**
 * Achievability engine for SAR Command scenarios.
 *
 * Imports the REAL mission generator, constants, fleet, and strategy logic so
 * every number below is exactly what the game uses — nothing is re-derived.
 *
 * Two complementary analyses per scenario:
 *   1. Offered-load capacity — intrinsic drone-second demand vs supply, per type.
 *      Duration-independent steady-state utilisation ρ. ρ ≪ 1 ⇒ a competent
 *      operator keeps the queue bounded. ρ ≥ 1 ⇒ structurally impossible.
 *   2. Discrete-event simulation — a greedy operator (Conservative strategy,
 *      the reserve-preserving choice) drives the fleet through the real mission
 *      stream. Reports completion %, queue length, wait times, and final score.
 *
 * Run:  npx tsx sim/achievability.mts [--duration=480]
 */

import {
  generateSessionPlan, createInitialAssets, travelTime,
  SESSION_DURATION_BY_COMPLEXITY, HUB, ASSET_SPEED,
  CATEGORY_PENALTY_RATE, TASK_WEIGHT, FAILURE_RATE_PER_DRONE_SECOND,
  TASK_PRIMARY, TASK_SUBSTITUTE, TASK_BASE_TIME, TASK_SUB_BASE_TIME,
} from '../src/utils/missionGen.ts'
import type { TaskType } from '../src/types/index.ts'
import { generateStrategies } from '../src/utils/copilot.ts'
import { SeededRNG } from '../src/utils/prng.ts'
import type { Complexity, AssetType, AssetRequirement, Task, MissionBlueprint } from '../src/types/index.ts'

const SCENARIOS: Complexity[] = ['balanced', 'tactical', 'strategic', 'full', 'quick']
const N_SEEDS = 200
const TYPES: AssetType[] = ['Blue', 'Red', 'Green']

// ─── CLI ────────────────────────────────────────────────────────────────────
const durArg = process.argv.find(a => a.startsWith('--duration='))
const DURATION_OVERRIDE = durArg ? parseInt(durArg.split('=')[1], 10) : null
// Optional per-scenario lambda scaling (to simulate retuned arrival rates).
const lambdaArg = process.argv.find(a => a.startsWith('--lambdaScale='))
const LAMBDA_SCALE = lambdaArg ? parseFloat(lambdaArg.split('=')[1]) : 1

// ─── Helpers ──────────────────────────────────────────────────────────────

function fleetCounts(complexity: Complexity): Record<AssetType, number> {
  const assets = createInitialAssets(complexity)
  return {
    Blue:  assets.filter(a => a.type === 'Blue').length,
    Red:   assets.filter(a => a.type === 'Red').length,
    Green: assets.filter(a => a.type === 'Green').length,
  }
}

/** Build the minimal Task[] the strategy generator needs (id, type, waypoint). */
function tasksOf(bp: MissionBlueprint): Task[] {
  return bp.taskTypes.map((type, i) => ({
    id: `${bp.id}-T${i + 1}`, missionId: bp.id, type,
    status: 'pending', waypoint: bp.waypoints[i], assignedAssetIds: [],
    allocatedAt: null, travelTime: 0, baseTime: 0, startTime: null,
    completionTime: null, useSubstitute: false, recallDelay: 0,
  })) as Task[]
}

function dist(a: { x: number; y: number }, b: { x: number; y: number }) {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

/** Return-to-hub travel time for one drone of `type` from the mission zone. */
function returnTime(zoneCenter: { x: number; y: number }, type: AssetType) {
  return dist(zoneCenter, HUB) / ASSET_SPEED[type]
}

/**
 * The committed team a careful operator deploys for a mission, given the drones
 * currently free. Uses the real Conservative strategy (reserve-preserving); falls
 * back to Aggressive if Conservative is infeasible with the available reserve.
 * Returns null if neither strategy can cover the mission with `reserve` drones.
 */
function operatorChoice(tasks: Task[], reserve: AssetRequirement, seed: number) {
  const strategies = generateStrategies(tasks, reserve, 0, new SeededRNG(seed))
  const cons = strategies.find(s => s.name === 'Conservative')
  const agg  = strategies.find(s => s.name === 'Aggressive')
  const chosen = cons ?? agg
  if (!chosen || !isFinite(chosen.expectedCompletionTime)) return null
  return { pool: chosen.trueAssets, makespan: chosen.expectedCompletionTime }
}

/** Mean travel + base time of a mission's tasks — used to model failure recovery cost. */
function meanTaskCost(tasks: Task[]): number {
  let s = 0
  for (const t of tasks) {
    // primary base time is in TASK_WEIGHT-independent table; approximate recovery as
    // travel (slowest realistic = Red 6 u/s) + a typical exec of ~25s
    s += dist(HUB, t.waypoint) / ASSET_SPEED.Red + 25
  }
  return tasks.length ? s / tasks.length : 0
}

// ─── 1. Irreducible-work capacity (per type ρ) ──────────────────────────────
// The minimum drone-seconds the fleet must spend to clear the mission stream:
// for each task, its primary-composition drones fly hub→waypoint, execute the
// base time, and fly back. No loiter waste, no failures, no substitutes. This is
// the true capacity floor — if ρ_work ≥ 1 the scenario is impossible for ANY
// operator; ρ_work well below 1 leaves headroom for travel-chaining inefficiency,
// failures, and imperfect human scheduling.

interface Work { dronesSec: Record<AssetType, number>; missions: number; tasks: number }

function workLoad(bps: MissionBlueprint[]): Work {
  const dronesSec: Record<AssetType, number> = { Blue: 0, Red: 0, Green: 0 }
  let tasks = 0
  for (const bp of bps) {
    tasks += bp.taskTypes.length
    bp.taskTypes.forEach((type, i) => {
      const comp = TASK_PRIMARY[type as TaskType]
      const base = TASK_BASE_TIME[type as TaskType]
      const wp = bp.waypoints[i]
      for (const tp of TYPES) {
        const n = comp[tp]
        if (n > 0) dronesSec[tp] += n * (2 * dist(HUB, wp) / ASSET_SPEED[tp] + base)
      }
    })
  }
  return { dronesSec, missions: bps.length, tasks }
}

// ─── 2. Discrete-event simulation (greedy operator) ─────────────────────────

interface SimResult {
  missions: number; allocated: number; missionsCompleted: number
  tasksTotal: number; tasksCompleted: number
  score: number; completionPts: number; penalty: number
  maxQueue: number; maxWait: number; p95Wait: number
  peakUtil: Record<AssetType, number>
}

function simulate(bps: MissionBlueprint[], seed: number, fleet: Record<AssetType, number>, duration: number, withFailures: boolean): SimResult {
  // Each drone: time it becomes free again.
  const freeAt: Record<AssetType, number[]> = {
    Blue:  new Array(fleet.Blue).fill(0),
    Red:   new Array(fleet.Red).fill(0),
    Green: new Array(fleet.Green).fill(0),
  }
  const freeCount = (type: AssetType, t: number) => freeAt[type].filter(f => f <= t).length

  interface QM { bp: MissionBlueprint; tasks: Task[]; arrival: number; penaltyRate: number; totalWeight: number }
  const queue: QM[] = []
  let nextArrival = 0

  let allocated = 0, missionsCompleted = 0, tasksCompleted = 0, tasksTotal = 0
  const waits: number[] = []
  let maxQueue = 0
  const peakUtil: Record<AssetType, number> = { Blue: 0, Red: 0, Green: 0 }

  // Track completion times of allocated missions to count completions & task points.
  const completions: { time: number; tasks: number; weight: number }[] = []
  let completionPts = 0

  for (const bp of bps) tasksTotal += bp.taskTypes.length

  for (let t = 0; t <= duration; t++) {
    // Arrivals at time t
    while (nextArrival < bps.length && bps[nextArrival].arrivalTime <= t) {
      const bp = bps[nextArrival++]
      const tk = tasksOf(bp)
      queue.push({
        bp, tasks: tk, arrival: bp.arrivalTime,
        penaltyRate: CATEGORY_PENALTY_RATE[bp.category],
        totalWeight: tk.reduce((s, x) => s + TASK_WEIGHT[x.type], 0),
      })
    }

    // Operator: allocate as many queued missions as the free reserve allows,
    // prioritising the fastest-bleeding (highest penalty rate) first.
    queue.sort((a, b) => b.penaltyRate - a.penaltyRate || a.arrival - b.arrival)
    let i = 0
    while (i < queue.length) {
      const qm = queue[i]
      const reserve: AssetRequirement = {
        Blue: freeCount('Blue', t), Red: freeCount('Red', t), Green: freeCount('Green', t),
      }
      const choice = operatorChoice(qm.tasks, reserve, seed ^ qm.bp.id.charCodeAt(1))
      if (!choice) { i++; continue }
      const need = choice.pool
      if (reserve.Blue < need.Blue || reserve.Red < need.Red || reserve.Green < need.Green) { i++; continue }

      // Allocate: occupy `need[type]` earliest-free drones until t + hold + return.
      let hold = choice.makespan
      // Expected failures under the live per-drone-second hazard ≈ rate × team-size × exposure-time
      // (replaces the old per-mission precomputed schedule's droneFailureTimes.length).
      if (withFailures) hold += FAILURE_RATE_PER_DRONE_SECOND * (need.Blue + need.Red + need.Green) * hold * meanTaskCost(qm.tasks)
      for (const type of TYPES) {
        if (need[type] === 0) continue
        const idx = freeAt[type]
          .map((f, k) => ({ f, k })).filter(x => x.f <= t).sort((a, b) => a.f - b.f)
          .slice(0, need[type]).map(x => x.k)
        for (const k of idx) freeAt[type][k] = t + hold + returnTime(qm.bp.zoneCenter, type)
      }
      allocated++
      waits.push(t - qm.arrival)
      const compTime = t + hold
      if (compTime <= duration) {
        missionsCompleted++
        tasksCompleted += qm.tasks.length
        completionPts += qm.totalWeight
        completions.push({ time: compTime, tasks: qm.tasks.length, weight: qm.totalWeight })
      }
      queue.splice(i, 1)  // removed; do not advance i
    }

    maxQueue = Math.max(maxQueue, queue.length)
    for (const type of TYPES) {
      const busy = fleet[type] - freeCount(type, t)
      peakUtil[type] = Math.max(peakUtil[type], busy / fleet[type])
    }
  }

  // Penalty: accrue per task from mission arrival until its completion (or session end).
  // Mirror computePenaltyAccrued: taskRate = missionRate * taskWeight/totalWeight.
  let penalty = 0
  // Allocated+completed missions stop accruing at completion; everything else accrues to `duration`.
  // Build a quick lookup of completion time by reconstructing from allocation order is complex;
  // instead approximate: completed missions accrue arrival→completion, others arrival→duration.
  const completedByArrival = new Map<number, number>() // arrival → completionTime (best effort)
  // (We logged completions in allocation order; align by matching weights is messy. Use the
  //  conservative bound: completed missions accrue until their completion time.)
  // Recompute precisely by re-deriving per-mission completion below.
  // For transparency we recompute penalty in a second pass that tracks each mission individually.
  return finalisePenalty({
    missions: bps.length, allocated, missionsCompleted, tasksTotal, tasksCompleted,
    completionPts, penalty, score: 0,
    maxQueue, maxWait: Math.max(0, ...waits), p95Wait: pct(waits, 0.95), peakUtil,
  }, bps, seed, fleet, duration, withFailures)
}

function pct(xs: number[], p: number): number {
  if (xs.length === 0) return 0
  const s = [...xs].sort((a, b) => a - b)
  return s[Math.min(s.length - 1, Math.floor(p * s.length))]
}

/**
 * Second pass: replays the same greedy schedule but records each mission's
 * completion time so penalty is computed exactly per the game's formula.
 */
function finalisePenalty(partial: SimResult, bps: MissionBlueprint[], seed: number, fleet: Record<AssetType, number>, duration: number, withFailures: boolean): SimResult {
  const freeAt: Record<AssetType, number[]> = {
    Blue: new Array(fleet.Blue).fill(0), Red: new Array(fleet.Red).fill(0), Green: new Array(fleet.Green).fill(0),
  }
  const freeCount = (type: AssetType, t: number) => freeAt[type].filter(f => f <= t).length
  interface QM { bp: MissionBlueprint; tasks: Task[]; arrival: number; penaltyRate: number }
  const queue: QM[] = []
  let nextArrival = 0
  const completionByMission = new Map<string, number>()

  for (let t = 0; t <= duration; t++) {
    while (nextArrival < bps.length && bps[nextArrival].arrivalTime <= t) {
      const bp = bps[nextArrival++]
      queue.push({ bp, tasks: tasksOf(bp), arrival: bp.arrivalTime, penaltyRate: CATEGORY_PENALTY_RATE[bp.category] })
    }
    queue.sort((a, b) => b.penaltyRate - a.penaltyRate || a.arrival - b.arrival)
    let i = 0
    while (i < queue.length) {
      const qm = queue[i]
      const reserve: AssetRequirement = { Blue: freeCount('Blue', t), Red: freeCount('Red', t), Green: freeCount('Green', t) }
      const choice = operatorChoice(qm.tasks, reserve, seed ^ qm.bp.id.charCodeAt(1))
      if (!choice) { i++; continue }
      const need = choice.pool
      if (reserve.Blue < need.Blue || reserve.Red < need.Red || reserve.Green < need.Green) { i++; continue }
      let hold = choice.makespan
      // Expected failures under the live per-drone-second hazard ≈ rate × team-size × exposure-time
      // (replaces the old per-mission precomputed schedule's droneFailureTimes.length).
      if (withFailures) hold += FAILURE_RATE_PER_DRONE_SECOND * (need.Blue + need.Red + need.Green) * hold * meanTaskCost(qm.tasks)
      for (const type of TYPES) {
        if (need[type] === 0) continue
        const idx = freeAt[type].map((f, k) => ({ f, k })).filter(x => x.f <= t).sort((a, b) => a.f - b.f).slice(0, need[type]).map(x => x.k)
        for (const k of idx) freeAt[type][k] = t + hold + returnTime(qm.bp.zoneCenter, type)
      }
      completionByMission.set(qm.bp.id, t + hold)
      queue.splice(i, 1)
    }
  }

  let penalty = 0
  for (const bp of bps) {
    const tk = tasksOf(bp)
    const totalWeight = tk.reduce((s, x) => s + TASK_WEIGHT[x.type], 0)
    if (totalWeight === 0) continue
    const missionRate = CATEGORY_PENALTY_RATE[bp.category]
    const comp = completionByMission.get(bp.id)
    const end = comp !== undefined && comp <= duration ? comp : duration
    for (const tt of tk) {
      const taskRate = missionRate * TASK_WEIGHT[tt.type] / totalWeight
      penalty += taskRate * Math.max(0, end - bp.arrivalTime)
    }
  }
  penalty = Math.round(penalty)
  return { ...partial, penalty, score: Math.max(0, partial.completionPts - penalty) }
}

// ─── Aggregation & reporting ────────────────────────────────────────────────

function mean(xs: number[]) { return xs.reduce((a, b) => a + b, 0) / (xs.length || 1) }

function run() {
  const withFailures = true
  console.log(`\n${'═'.repeat(96)}`)
  console.log(`SAR ACHIEVABILITY ENGINE   seeds=${N_SEEDS}  failures=${withFailures}  lambdaScale=${LAMBDA_SCALE}` +
    (DURATION_OVERRIDE ? `  duration=${DURATION_OVERRIDE}s (override)` : '  duration=per-scenario'))
  console.log('═'.repeat(96))

  for (const complexity of SCENARIOS) {
    const baseDur = SESSION_DURATION_BY_COMPLEXITY[complexity]
    const duration = DURATION_OVERRIDE ?? baseDur
    const fleet = fleetCounts(complexity)

    const offΡ: Record<AssetType, number[]> = { Blue: [], Red: [], Green: [] }
    const offMissions: number[] = [], offTasks: number[] = []
    const compRate: number[] = [], missionCompRate: number[] = [], scores: number[] = []
    const penalties: number[] = [], maxQueues: number[] = [], p95Waits: number[] = [], maxWaits: number[] = []
    const peak: Record<AssetType, number[]> = { Blue: [], Red: [], Green: [] }

    for (let s = 0; s < N_SEEDS; s++) {
      const seed = (1234567 + s * 2654435761) >>> 0
      // generateSessionPlan reads λ from complexity internally; to simulate a retuned arrival
      // rate we stretch/shrink arrival times by 1/LAMBDA_SCALE (smaller λ → faster arrivals).
      let bps = generateSessionPlan(new SeededRNG(seed ^ 1), complexity, duration / LAMBDA_SCALE)
      if (LAMBDA_SCALE !== 1) {
        bps = bps.map(bp => ({ ...bp, arrivalTime: bp.arrivalTime * LAMBDA_SCALE }))
          .filter(bp => bp.arrivalTime <= duration)
      }

      const off = workLoad(bps)
      offMissions.push(off.missions); offTasks.push(off.tasks)
      for (const type of TYPES) offΡ[type].push(off.dronesSec[type] / (fleet[type] * duration))

      const r = simulate(bps, seed, fleet, duration, withFailures)
      compRate.push(r.tasksCompleted / (r.tasksTotal || 1))
      missionCompRate.push(r.missionsCompleted / (r.missions || 1))
      scores.push(r.score); penalties.push(r.penalty)
      maxQueues.push(r.maxQueue); p95Waits.push(r.p95Wait); maxWaits.push(r.maxWait)
      for (const type of TYPES) peak[type].push(r.peakUtil[type])
    }

    const bottleneck = TYPES.reduce((a, b) => mean(offΡ[a]) > mean(offΡ[b]) ? a : b)
    const verdict = mean(offΡ[bottleneck]) < 0.6 ? '✅ comfortable'
      : mean(offΡ[bottleneck]) < 0.8 ? '🟡 tight'
      : mean(offΡ[bottleneck]) < 1.0 ? '🟠 marginal' : '🔴 INFEASIBLE'

    console.log(`\n▌ ${complexity.toUpperCase()}   fleet ${fleet.Blue}B/${fleet.Red}R/${fleet.Green}G   duration ${duration}s`)
    console.log(`  missions/session ${mean(offMissions).toFixed(1)}   tasks/session ${mean(offTasks).toFixed(0)}`)
    console.log(`  irreducible-work ρ (min drone-sec / supply):  ` +
      TYPES.map(t => `${t[0]}=${mean(offΡ[t]).toFixed(2)}`).join('  ') + `   → bottleneck ${bottleneck}  ${verdict}`)
    console.log(`  DES greedy operator:  tasks done ${(mean(compRate) * 100).toFixed(0)}%   missions done ${(mean(missionCompRate) * 100).toFixed(0)}%` +
      `   score ${mean(scores).toFixed(0)} (pen ${mean(penalties).toFixed(0)})`)
    console.log(`  queue: max ${mean(maxQueues).toFixed(1)} (p95 wait ${mean(p95Waits).toFixed(0)}s, worst ${Math.max(...maxWaits).toFixed(0)}s)` +
      `   peak fleet use ` + TYPES.map(t => `${t[0]}=${(mean(peak[t]) * 100).toFixed(0)}%`).join(' '))
  }
  console.log(`\n${'═'.repeat(96)}\n`)
}

run()
