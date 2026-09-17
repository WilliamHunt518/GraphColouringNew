/**
 * Measures the real completion-time cost of the ε_Tactical route-detour fault (study-v1.10/v1.11),
 * for the "lazy operator" path the mechanism is deliberately bounded around: click Suggest, then
 * Deploy without editing anything (MapDisplay.tsx handleSuggest hands the operator
 * `pending.taskAssignments` as-is when a fault fired, instead of recomputing a clean plan).
 *
 * Drives the REAL gameReducer headlessly, PAIRED by seed: for the identical mission stream and
 * identical strategic card choice (ε_Strategic pinned at 0, so only the tactical effect is being
 * measured — see docs/STUDY_BUILD.md §17-18), run once with epsilonTactical=0 (clean baseline) and
 * once at the configured rate, then diff each mission's completion time. Missions touched by the
 * (unrelated) ambient drone-failure hazard in either run are excluded from the paired diff, since
 * that's a separate random confound with its own roll stream.
 *
 * Run:  npx tsx sim/tactical-fault-cost.mts [--eps=0.8] [--seeds=150] [--duration=480]
 */
console.debug = () => {}  // silence greedyAssign trace
import { buildInitialState, gameReducer } from '../src/store/gameReducer.ts'
import { TASK_PRIMARY } from '../src/utils/missionGen.ts'
import type { GameState, GameAction, StudyConfig, Complexity, AssetType, TaskType, AssetRequirement, PendingAllocation } from '../src/types/index.ts'

type CardPolicy = 'Aggressive' | 'Conservative'
const SCENARIOS: Complexity[] = ['balanced', 'tactical', 'strategic', 'full']
const DT = 0.5

const durArg = process.argv.find(a => a.startsWith('--duration='))
const DURATION = durArg ? parseInt(durArg.split('=')[1], 10) : 480
const seedArg = process.argv.find(a => a.startsWith('--seeds='))
const N_SEEDS = seedArg ? parseInt(seedArg.split('=')[1], 10) : 150
const epsArg = process.argv.find(a => a.startsWith('--eps='))
const EPS_T = epsArg ? parseFloat(epsArg.split('=')[1]) : 0.8

function baseConfig(complexity: Complexity, seed: number, epsilonTactical: number): StudyConfig {
  return {
    participantId: 'SIM', condition: 'none', mode: 'agent', complexity, seed,
    agentErrorRate: 0,                          // ε_Strategic OFF — isolate the tactical effect only
    epsilonTactical,
    agentFailuresEnabled: epsilonTactical > 0,
    tacticalMode: 'plan-all',                   // study default (greedy would clip most detour effect)
    testingMode: false, tutorialMode: false, numSessions: 1,
    fixLockouts: true,
  } as StudyConfig
}

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
function neededCount(type: number): number {
  const c = TASK_PRIMARY[type as TaskType]; return c.Blue + c.Red + c.Green
}
function penaltyOrder(cat: string): number { return { A: 1, B: 2, C: 3, D: 4, E: 5 }[cat] ?? 0 }

// Mirrors MapDisplay's droneSequences chain-order memo: a drone with no detour falls back to the
// mission's canonical task order; a drone the fault touched uses its own drawn walk (detour(s) then
// its real task(s)), filtered down to tasks it's a genuine taskAssignments member of — which for a
// faulted drone is exactly [detours[0], ...real] (later decorative hops are logged-only, never real
// membership — see buildTacticalFailurePlan's docstring).
function chainOrderFor(pending: PendingAllocation): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  const allDroneIds = new Set(Object.values(pending.taskAssignments).flat())
  for (const droneId of allDroneIds) {
    const walk = pending.agentDroneSequences?.[droneId]
    const fullOrder = walk && walk.length > 0 ? walk : pending.taskOrder
    out[droneId] = fullOrder.filter(tid => (pending.taskAssignments[tid] ?? []).includes(droneId))
  }
  return out
}

function operate(state: GameState, policy: CardPolicy): GameState {
  let s = state
  const D = (a: GameAction) => { s = gameReducer(s, a) }

  // 1. Resolve any pending failure recoveries (smart operator always recovers) — same handling as
  //    sim/engine.mts, so the ambient drone-failure hazard doesn't just stall missions outright.
  for (const m of s.missions) {
    if (!m.failureRecoveryPending) continue
    const opt = m.pendingRecoveryOptions?.find(o => o.type === 'redistribute')
    if (opt?.feasible) { D({ type: 'ACCEPT_RECOVERY', missionId: m.id, recoveryType: 'redistribute' }); continue }
    const failedTask = m.tasks.find(t => t.status === 'pending' && t.assignedAssetIds.length < neededCount(t.type))
      ?? m.tasks.find(t => t.status === 'pending')
    if (!failedTask) continue
    const need = TASK_PRIMARY[failedTask.type as TaskType]
    const wantType = (['Green', 'Red', 'Blue'] as AssetType[]).find(tp => need[tp] > 0)
    const drone = s.assets.find(a => a.status === 'available' && (!wantType || a.type === wantType))
      ?? s.assets.find(a => a.status === 'available')
    if (drone) D({ type: 'APPLY_MANUAL_RECOVERY', missionId: m.id, taskId: failedTask.id, newAssetId: drone.id })
  }

  // 2. Allocate queued missions with the fixed strategy card (Aggressive or Conservative), then
  //    Suggest + Deploy the tactical plan exactly as shown — the "lazy operator" path.
  const queued = s.missions.filter(m => m.status === 'queued')
    .sort((a, b) => penaltyOrder(b.category) - penaltyOrder(a.category))
  for (const m of queued) {
    const reserve = reserveOf(s)
    const fl = floor(m.tasks)
    if (reserve.Blue < fl.Blue || reserve.Red < fl.Red || reserve.Green < fl.Green) continue

    D({ type: 'OPEN_STRATEGIC', missionId: m.id })
    const modal = s.strategicModal
    if (!modal || modal.missionId !== m.id) continue
    const idx = modal.strategies.findIndex(st => st.name === policy)
    const use = idx >= 0 ? idx : (modal.strategies.length ? 0 : -1)
    if (use < 0) { D({ type: 'CLOSE_STRATEGIC' }); continue }
    D({ type: 'APPLY_STRATEGIC', missionId: m.id, source: 'agent', strategyIndex: use, manualAllocation: null })

    const mm = s.missions.find(x => x.id === m.id)
    if (mm?.tacticalPending && mm.pendingAllocation) {
      D({ type: 'TACTICAL_SUGGEST', missionId: m.id })
      const pending = mm.pendingAllocation
      D({
        type: 'CONFIRM_TACTICAL', missionId: m.id,
        taskAssignments: pending.taskAssignments,
        droneSequences: chainOrderFor(pending),
      })
    }
  }
  return s
}

// ─── Single session ─────────────────────────────────────────────────────────

interface MissionRow {
  id: string; arrival: number; completionTime: number | null
  hasTacticalError: boolean; touchedByDroneFailure: boolean
}
interface SessionOut { missions: MissionRow[]; score: number; penalty: number }

function runSession(complexity: Complexity, seed: number, epsilonTactical: number, policy: CardPolicy): SessionOut {
  const cfg = baseConfig(complexity, seed, epsilonTactical)
  let state = buildInitialState(cfg)
  const steps = Math.ceil(state.sessionDuration / DT) + 4
  for (let i = 0; i <= steps; i++) {
    const nowMs = i * DT * 1000
    state = gameReducer(state, { type: 'TICK', nowMs })
    state = operate(state, policy)
    if (state.elapsed >= state.sessionDuration) break
  }

  const events = state.events.flat()
  const droneFailureMissionIds = new Set(events.filter(e => e.type === 'drone_failure').map((e: any) => e.missionId))
  const tacticalErrorMissionIds = new Set(
    events.filter((e: any) => e.type === 'tactical_opened' && e.hasTacticalError).map((e: any) => e.missionId)
  )

  const missions: MissionRow[] = state.missions.map(m => ({
    id: m.id, arrival: m.arrivalTime, completionTime: m.completionTime,
    hasTacticalError: tacticalErrorMissionIds.has(m.id),
    touchedByDroneFailure: droneFailureMissionIds.has(m.id),
  }))
  return { missions, score: state.score, penalty: state.penaltyAccrued }
}

// ─── Aggregate & report ───────────────────────────────────────────────────

function mean(xs: number[]) { return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0 }
function median(xs: number[]) {
  if (!xs.length) return 0
  const s = [...xs].sort((a, b) => a - b)
  const mid = Math.floor(s.length / 2)
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2
}

function run() {
  console.log(`\n${'═'.repeat(100)}`)
  console.log(`TACTICAL FAULT COST   epsilonTactical=${EPS_T} (vs 0 baseline)  duration=${DURATION}s  seeds=${N_SEEDS}  epsilonStrategic=0 (isolated)`)
  console.log('═'.repeat(100))

  for (const complexity of SCENARIOS) {
    console.log(`\n▌ ${complexity.toUpperCase()}`)
    for (const policy of ['Aggressive', 'Conservative'] as CardPolicy[]) {
      const overheads: number[] = []
      const relOverheads: number[] = []
      let firedCount = 0, pairedCount = 0, excludedByDroneFailure = 0, zeroOrNegative = 0
      const scoreDeltas: number[] = []
      const penaltyDeltas: number[] = []

      for (let si = 0; si < N_SEEDS; si++) {
        const seed = (98765 + si * 1013904223) >>> 0
        const base = runSession(complexity, seed, 0, policy)
        const faulty = runSession(complexity, seed, EPS_T, policy)
        scoreDeltas.push(faulty.score - base.score)
        penaltyDeltas.push(faulty.penalty - base.penalty)

        const baseById = new Map(base.missions.map(m => [m.id, m]))
        for (const fm of faulty.missions) {
          if (!fm.hasTacticalError) continue
          firedCount++
          const bm = baseById.get(fm.id)
          if (!bm) continue
          if (fm.touchedByDroneFailure || bm.touchedByDroneFailure) { excludedByDroneFailure++; continue }
          if (fm.completionTime == null || bm.completionTime == null) continue
          pairedCount++
          const overhead = fm.completionTime - bm.completionTime
          overheads.push(overhead)
          if (overhead <= 0) zeroOrNegative++
          const baseDuration = bm.completionTime - bm.arrival
          relOverheads.push(baseDuration > 0 ? overhead / baseDuration : 0)
        }
      }

      console.log(`  ${policy.padEnd(12)}` +
        `  fired ${firedCount.toString().padStart(4)}` +
        `  paired ${pairedCount.toString().padStart(4)} (excl. drone-failure ${excludedByDroneFailure})` +
        `  meanOverhead ${mean(overheads).toFixed(1)}s` +
        `  medianOverhead ${median(overheads).toFixed(1)}s` +
        `  meanRelOverhead ${(100 * mean(relOverheads)).toFixed(1)}%` +
        `  zeroOrNegative ${pairedCount ? (100 * zeroOrNegative / pairedCount).toFixed(0) : '–'}%` +
        `  ΔscoreMean ${mean(scoreDeltas).toFixed(1)}` +
        `  ΔpenaltyMean ${mean(penaltyDeltas).toFixed(1)}`)
    }
  }
  console.log(`\n${'═'.repeat(100)}\n`)
}

run()
