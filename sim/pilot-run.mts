/**
 * Synthetic cohort generator — drives the REAL gameReducer through complete two-session studies
 * (Strategic Heavy → Tactical Heavy) with seeded, competent "operators", writing one export per
 * participant in exactly the shape GameShell's Download Data produces.
 *
 * Purpose: (a) exercise the collection pipeline end to end, and (b) give the analysis scripts a
 * realistic multi-participant cohort so aggregate reporting can be checked before real data exists.
 *
 * The assistants are PERFECT here (epsilon_S = epsilon_T = 0): the only adversity in the study is
 * drone failure. The operator policy is identical across both sessions of a participant, so any
 * difference between the two scenarios is scenario-driven, not policy-driven — which is what makes
 * these logs usable as a scenario-calibration check.
 *
 * Run: npx tsx sim/pilot-run.mts [--participants=8] [--seed=4242] [--out=logs/Pilots/auto]
 */
console.debug = () => {}
import { writeFileSync, mkdirSync } from 'node:fs'
import { buildInitialState, gameReducer, reserveCount } from '../src/store/gameReducer.ts'
import { TASK_PRIMARY, TASK_SUBSTITUTE } from '../src/utils/missionGen.ts'
import { SeededRNG } from '../src/utils/prng.ts'
import type {
  GameState, GameAction, StudyConfig, AssetType, AssetRequirement, Mission, Task,
} from '../src/types/index.ts'

const arg = (k: string, d: string) => (process.argv.find(a => a.startsWith(`--${k}=`))?.split('=')[1] ?? d)
const N_PARTICIPANTS = parseInt(arg('participants', '8'), 10)
const BASE_SEED = parseInt(arg('seed', '4242'), 10)
const OUT_DIR = arg('out', 'logs/Pilots/auto')
const DT = 0.25   // 4 Hz sim step — finer than a real rAF tick, so nothing is missed
const SESSIONS: Array<'strategic' | 'tactical'> = ['strategic', 'tactical']

function makeConfig(pid: string, seed: number): StudyConfig {
  return {
    participantId: pid,
    condition: 'none',        // no accuracy manipulation — both assistants are perfect
    mode: 'agent',
    complexity: 'strategic',
    sessionComplexities: SESSIONS,
    seed,
    agentErrorRate: 0,        // epsilon_Strategic
    epsilonTactical: 0,       // epsilon_Tactical
    tacticalMode: 'plan-all',
    testingMode: false,
    fixLockouts: false,
    tutorialMode: false,
    numSessions: 2,
  }
}

// ── helpers ─────────────────────────────────────────────────────────────────
const typeOf = (s: GameState, id: string) => s.assets.find(a => a.id === id)?.type

/** Smallest set of `pool` drones satisfying a task's primary (or substitute) composition. */
function staffTask(task: Task, pool: string[], s: GameState): string[] | null {
  for (const comp of [TASK_PRIMARY[task.type], TASK_SUBSTITUTE[task.type]]) {
    if (!comp) continue
    const picked: string[] = []
    const left = { ...comp } as AssetRequirement
    for (const id of pool) {
      const t = typeOf(s, id) as AssetType | undefined
      if (t && left[t] > 0) { picked.push(id); left[t]-- }
    }
    if (left.Blue <= 0 && left.Red <= 0 && left.Green <= 0) return picked
  }
  return null
}

/**
 * Whole-mission plan from the committed pool. Returns null if ANY task would be left unstaffed —
 * a competent operator does not deploy a plan that strands a task, because a task committed with
 * no drones can never complete. The caller falls back to the agent's own plan in that case.
 */
function handBuild(mission: Mission, pool: string[], s: GameState): Record<string, string[]> | null {
  const out: Record<string, string[]> = {}
  let free = [...pool]
  const live = mission.tasks.filter(t => t.status !== 'completed' && t.status !== 'failed')
  for (const t of [...live].sort((a, b) => b.type - a.type)) {
    const pick = staffTask(t, free, s)
    if (!pick) return null
    out[t.id] = pick
    free = free.filter(id => !pick.includes(id))
  }
  return out
}

/** Per-drone task order — the planner always sends this, and without it nothing gets scheduled. */
function sequencesFor(plan: Record<string, string[]>, taskOrder: string[]): Record<string, string[]> {
  const seqs: Record<string, string[]> = {}
  for (const id of [...new Set(Object.values(plan).flat())]) {
    const seq = taskOrder.filter(tid => (plan[tid] ?? []).includes(id))
    if (seq.length) seqs[id] = seq
  }
  return seqs
}

function floorOf(tasks: Task[]): AssetRequirement {
  const f = { Blue: 0, Red: 0, Green: 0 }
  for (const t of tasks) {
    const p = TASK_PRIMARY[t.type]
    f.Blue = Math.max(f.Blue, p.Blue); f.Red = Math.max(f.Red, p.Red); f.Green = Math.max(f.Green, p.Green)
  }
  return f
}

/** Sum of every task's primary demand — what it takes to run the whole mission in parallel. */
function parallelDemand(tasks: Task[]): AssetRequirement {
  const d = { Blue: 0, Red: 0, Green: 0 }
  for (const t of tasks) {
    const p = TASK_PRIMARY[t.type]
    d.Blue += p.Blue; d.Red += p.Red; d.Green += p.Green
  }
  return d
}

// ── one participant ─────────────────────────────────────────────────────────
function runParticipant(pid: string, seed: number) {
  const config = makeConfig(pid, seed)
  const rng = new SeededRNG(seed ^ 0x91101)
  const thinkTime = (lo: number, hi: number) => rng.randFloat(lo, hi)

  interface Decision { decideAt: number; path: number; idx: number; reopened: boolean }
  const stratDecision = new Map<string, Decision>()
  const tacticalAt = new Map<string, number>()
  const recoveryAt = new Map<string, number>()
  const recoveryTries = new Map<string, number>()

  function operate(s0: GameState): GameState {
    let s = s0
    const D = (a: GameAction) => { s = gameReducer(s, a) }
    const now = () => s.elapsed
    const timeLeft = () => s.sessionDuration - s.elapsed

    // 1. Triage anything asking for help.
    for (const m of s.missions.filter(m => m.failureRecoveryPending)) {
      if (!recoveryAt.has(m.id)) { recoveryAt.set(m.id, now() + thinkTime(4, 14)); continue }
      if (now() < recoveryAt.get(m.id)!) continue
      recoveryAt.delete(m.id)

      // Staff from the mission's own idle drones FIRST, then top up from the hub reserve —
      // CONFIRM_FAILURE_RECOVERY accepts both, and ignoring the reserve is what made an earlier
      // version of this operator abandon missions it could easily have saved.
      const onMission = s.assets.filter(a =>
        a.currentMissionId === m.id && a.status === 'deployed' &&
        m.tasks.find(t => t.id === a.currentTaskId)?.status !== 'executing').map(a => a.id)
      const reserve = s.assets.filter(a => a.status === 'available').map(a => a.id)
      const pendingTasks = m.tasks.filter(t => t.status === 'pending')
      const plan: Record<string, string[]> = {}
      let free = [...onMission, ...reserve]
      let ok = pendingTasks.length > 0
      for (const t of pendingTasks) {
        const pick = staffTask(t, free, s)
        if (!pick) { ok = false; break }
        plan[t.id] = pick
        free = free.filter(id => !pick.includes(id))
      }
      if (ok) {
        const consult = rng.next() < 0.6
        if (consult) D({ type: 'TACTICAL_SUGGEST', missionId: m.id, recoveryMode: true })
        D({ type: 'CONFIRM_FAILURE_RECOVERY', missionId: m.id, taskAssignments: plan,
            droneSequences: sequencesFor(plan, pendingTasks.map(t => t.id)), wasAgentSuggested: consult })
        recoveryTries.delete(m.id)
      } else {
        // Can't cover it right now — a replacement drone reaches the hub within 30–45 s, so wait
        // and look again rather than throwing the mission away. Give up only if it stays
        // impossible, or there is no time left to finish it anyway.
        const tries = (recoveryTries.get(m.id) ?? 0) + 1
        recoveryTries.set(m.id, tries)
        if (tries >= 4 || timeLeft() < 45) { D({ type: 'ABANDON_MISSION', missionId: m.id }); recoveryTries.delete(m.id) }
        else recoveryAt.set(m.id, now() + thinkTime(12, 22))
      }
    }

    // 2. Tactical planning for anything already allocated.
    for (const m of s.missions.filter(m => m.tacticalPending && m.pendingAllocation)) {
      if (!tacticalAt.has(m.id)) { tacticalAt.set(m.id, now() + thinkTime(4, 14)); continue }
      if (now() < tacticalAt.get(m.id)!) continue
      tacticalAt.delete(m.id)
      const pool = m.pendingAllocation!.dronePool
      const tac = rng.next()

      if (tac < 0.50) {
        // Consult the agent and go with it.
        D({ type: 'TACTICAL_SUGGEST', missionId: m.id })
        D({ type: 'CONFIRM_TACTICAL', missionId: m.id })
      } else if (tac < 0.75) {
        // Consult, then put a spare drone on another task before committing. Only ever ADDS a
        // drone, so the plan stays fully staffed.
        D({ type: 'TACTICAL_SUGGEST', missionId: m.id })
        const plan: Record<string, string[]> = {}
        for (const [tid, ids] of Object.entries(m.pendingAllocation!.taskAssignments)) plan[tid] = [...ids]
        const tids = Object.keys(plan)
        const spare = pool.find(id => !Object.values(plan).flat().includes(id))
        if (tids.length >= 1 && spare) {
          const to = tids[tids.length - 1]
          plan[to] = [...plan[to], spare]
          D({ type: 'TACTICAL_ASSIGN_CHANGED', missionId: m.id, op: 'assign', droneId: spare, taskId: to, recoveryMode: false })
        }
        D({ type: 'CONFIRM_TACTICAL', missionId: m.id, taskAssignments: plan,
            droneSequences: sequencesFor(plan, m.pendingAllocation!.taskOrder) })
      } else {
        // Plan from scratch — but only commit if every task ends up staffed; otherwise defer to
        // the agent rather than deploying something that strands a task.
        const plan = handBuild(m, pool, s)
        if (!plan) { D({ type: 'CONFIRM_TACTICAL', missionId: m.id }) }
        else {
          for (const [tid, ids] of Object.entries(plan)) {
            for (const id of ids) {
              D({ type: 'TACTICAL_ASSIGN_CHANGED', missionId: m.id, op: 'assign', droneId: id, taskId: tid, recoveryMode: false })
            }
          }
          D({ type: 'CONFIRM_TACTICAL', missionId: m.id, taskAssignments: plan,
              droneSequences: sequencesFor(plan, m.pendingAllocation!.taskOrder) })
        }
      }
    }

    // 3. The strategic modal is exclusive, and Deploy stays locked until every card has revealed.
    const modal = s.strategicModal
    if (modal) {
      const dec = stratDecision.get(modal.missionId)
      const mission = s.missions.find(x => x.id === modal.missionId)
      if (!dec || !mission) { D({ type: 'CLOSE_STRATEGIC' }); return s }
      if (now() < dec.decideAt) return s          // still deliberating
      stratDecision.delete(modal.missionId)

      if (dec.path < 0.15 && modal.strategies.length > 0 && !dec.reopened) {
        // Dismiss, sit on it, then re-open and commit on the second look.
        D({ type: 'CLOSE_STRATEGIC' })
        D({ type: 'OPEN_STRATEGIC', missionId: mission.id })
        const m2 = s.strategicModal
        if (m2 && m2.missionId === mission.id) {
          const gate2 = Math.max(0, ...(m2.cardRevealDelaysMs ?? [0])) / 1000
          stratDecision.set(mission.id, { ...dec, reopened: true, decideAt: now() + gate2 + thinkTime(2, 7) })
        }
        return s
      }
      if (modal.strategies.length > 0 && dec.path < 0.80) {
        D({ type: 'PICK_STRATEGY', strategyIndex: dec.idx })
        D({ type: 'APPLY_STRATEGIC', missionId: mission.id, source: 'agent', strategyIndex: dec.idx,
            manualAllocation: null, strategyCardCount: modal.strategies.length })
      } else {
        // Manual, but SOUND: aim at the mission's full parallel demand rather than the bare
        // sequential floor, capped by what is actually free right now.
        const live = reserveCount(s.assets, s.missions)
        const want = parallelDemand(mission.tasks.filter(t => t.status !== 'completed' && t.status !== 'failed'))
        const target = {
          Blue: Math.min(want.Blue, live.Blue),
          Red: Math.min(want.Red, live.Red),
          Green: Math.min(want.Green, live.Green),
        }
        const running = { Blue: 0, Red: 0, Green: 0 }
        for (const t of ['Blue', 'Red', 'Green'] as AssetType[]) {
          for (let i = 0; i < target[t]; i++) { running[t]++; D({ type: 'EDIT_MANUAL', allocation: { ...running } }) }
        }
        if (running.Blue + running.Red + running.Green === 0) { D({ type: 'CLOSE_STRATEGIC' }); return s }
        D({ type: 'APPLY_STRATEGIC', missionId: mission.id, source: 'manual', strategyIndex: null,
            manualAllocation: { ...running }, strategyCardCount: modal.strategies.length,
            manualBeforeCardsLoaded: false, cardsLoadedAtManualSwitch: modal.strategies.length })
      }
      if (s.strategicModal) D({ type: 'CLOSE_STRATEGIC' })   // apply rejected — don't sit on a dead modal
      return s
    }

    // 4. Nothing open — start on the next mission (highest penalty rate first).
    const order = { A: 1, B: 2, C: 3, D: 4, E: 5 }
    for (const m of [...s.missions.filter(m => m.status === 'queued')]
        .sort((a, b) => order[b.category] - order[a.category])) {
      const avail = reserveCount(s.assets, s.missions)
      const fl = floorOf(m.tasks)
      if (avail.Blue < fl.Blue || avail.Red < fl.Red || avail.Green < fl.Green) continue

      D({ type: 'OPEN_STRATEGIC', missionId: m.id })
      const opened = s.strategicModal
      if (!opened || opened.missionId !== m.id) continue

      // Compare both cards on the way in, then wait out the reveal.
      if (opened.strategies.length === 2) {
        D({ type: 'PICK_STRATEGY', strategyIndex: rng.next() < 0.5 ? 0 : 1 })
        if (rng.next() < 0.6) D({ type: 'PICK_STRATEGY', strategyIndex: rng.next() < 0.5 ? 0 : 1 })
      }
      const gate = Math.max(0, ...(opened.cardRevealDelaysMs ?? [0])) / 1000
      stratDecision.set(m.id, {
        decideAt: now() + gate + thinkTime(2, 9),
        path: rng.next(),
        idx: rng.next() < 0.65 ? 0 : 1,     // lean Aggressive — the redundant card absorbs failures
        reopened: false,
      })
      break   // one modal at a time
    }
    return s
  }

  // End-of-session questionnaires — the only place trust and workload are measured.
  function submitSurveys(s0: GameState, sessionIdx: number): GameState {
    let s = s0
    const D = (a: GameAction) => { s = gameReducer(s, a) }
    const lik = (base: number) => Math.max(1, Math.min(7, Math.round(base + rng.noise() * 1.3)))
    const tlx = (base: number) => Math.max(0, Math.min(20, Math.round(base + rng.noise() * 3.5)))
    const load = sessionIdx === 0 ? 11 : 12
    D({ type: 'SUBMIT_SURVEY', surveyName: 'nasa_tlx', responses: {
      mental_demand: tlx(load), physical_demand: tlx(4), temporal_demand: tlx(load + 1),
      performance: tlx(7), effort: tlx(load), frustration: tlx(load - 3) } })
    D({ type: 'SUBMIT_SURVEY', surveyName: 'trust_strategic', responses: {
      strat_reliable: lik(5), strat_trust: lik(5), strat_performs: lik(5),
      strat_confident: lik(5), strat_useful: lik(6), strat_follow: lik(4) } })
    D({ type: 'SUBMIT_SURVEY', surveyName: 'trust_tactical', responses: {
      tact_reliable: lik(5), tact_trust: lik(5), tact_performs: lik(5),
      tact_confident: lik(5), tact_useful: lik(5), tact_follow: lik(4) } })
    D({ type: 'SUBMIT_SURVEY', surveyName: 'tam_strategic', responses: {
      strat_tam_perf: lik(5), strat_tam_useful: lik(6), strat_tam_easy_learn: lik(6), strat_tam_easy_use: lik(6) } })
    D({ type: 'SUBMIT_SURVEY', surveyName: 'tam_tactical', responses: {
      tact_tam_perf: lik(5), tact_tam_useful: lik(5), tact_tam_easy_learn: lik(6), tact_tam_easy_use: lik(5) } })
    D({ type: 'FINISH_SURVEYS' })
    return s
  }

  let state = buildInitialState(config)
  for (let sess = 0; sess < SESSIONS.length; sess++) {
    const steps = Math.ceil(state.sessionDuration / DT) + 8
    for (let i = 0; i <= steps; i++) {
      state = gameReducer(state, { type: 'TICK', nowMs: i * DT * 1000 })
      if (state.phase !== 'playing') break
      state = operate(state)
    }
    // Operator memory is per-session: mission ids repeat across sessions.
    stratDecision.clear(); tacticalAt.clear(); recoveryAt.clear(); recoveryTries.clear()
    state = submitSurveys(state, sess)
    if (sess < SESSIONS.length - 1) state = gameReducer(state, { type: 'NEXT_SESSION' })
  }
  state = gameReducer(state, { type: 'END_STUDY' })

  return {
    participantId: config.participantId,
    condition: config.condition,
    mode: config.mode,
    complexities: SESSIONS,
    seed: config.seed,
    epsilonStrategic: config.agentErrorRate,
    epsilonTactical: config.epsilonTactical,
    demographics: null,
    sessionScores: state.completedSessionScores,
    totalScore: state.completedSessionScores.reduce((a, b) => a + b, 0),
    sessions: state.events,
  }
}

// ── cohort ──────────────────────────────────────────────────────────────────
mkdirSync(OUT_DIR, { recursive: true })
console.log(`generating ${N_PARTICIPANTS} participants → ${OUT_DIR}`)
for (let p = 0; p < N_PARTICIPANTS; p++) {
  const pid = `P-SIM${String(p + 1).padStart(2, '0')}`
  const seed = (BASE_SEED + p * 7919) >>> 0
  const payload = runParticipant(pid, seed)
  const path = `${OUT_DIR}/study_${pid}_${payload.condition}_${seed}.json`
  writeFileSync(path, JSON.stringify(payload, null, 2))
  const lines = payload.sessions.map((evs, i) => {
    const se = evs.find(e => e.type === 'session_ended') as any
    return `${SESSIONS[i]} score=${se?.score} pts=${se?.completionPoints} pen=${se?.penaltyAccrued}`
  })
  console.log(`  ${pid} seed=${seed}  ${lines.join('  |  ')}`)
}
console.log('done')
