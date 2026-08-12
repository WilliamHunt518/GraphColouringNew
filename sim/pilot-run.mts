/**
 * Scripted pilot run — drives the REAL gameReducer through a full two-session study
 * (Strategic Heavy → Tactical Heavy) with a semi-random but SEEDED "operator", and writes the
 * export exactly as GameShell's Download Data would.
 *
 * Purpose: exercise the whole collection pipeline end to end and give the analysis code real
 * input. The operator policy is identical across both sessions, so any difference between the
 * two logs is scenario-driven, not policy-driven.
 *
 * Run: npx tsx sim/pilot-run.mts [--pid=P-PILOT] [--seed=4242]
 */
console.debug = () => {}
import { writeFileSync, mkdirSync } from 'node:fs'
import { buildInitialState, gameReducer, reserveCount } from '../src/store/gameReducer.ts'
import { TASK_PRIMARY, TASK_SUBSTITUTE } from '../src/utils/missionGen.ts'
import { SeededRNG } from '../src/utils/prng.ts'
import type {
  GameState, GameAction, StudyConfig, AssetType, TaskType, AssetRequirement, Mission, Task, Asset,
} from '../src/types/index.ts'

const arg = (k: string, d: string) => (process.argv.find(a => a.startsWith(`--${k}=`))?.split('=')[1] ?? d)
const PID = arg('pid', 'P-PILOT')
const SEED = parseInt(arg('seed', '4242'), 10)
const DT = 0.25   // 4 Hz sim step — finer than a real rAF tick, so nothing is missed
const SESSIONS: Array<'strategic' | 'tactical'> = ['strategic', 'tactical']

// LL condition (both assistants at the low-accuracy end) so that bad strategic cards AND injected
// tactical errors actually occur within a 2-session pilot — otherwise the RQ2/RQ4 fields are all
// empty and there is nothing for the analysis to chew on.
const config: StudyConfig = {
  participantId: PID,
  condition: 'LL',
  mode: 'agent',
  complexity: 'strategic',
  sessionComplexities: SESSIONS,
  seed: SEED,
  agentErrorRate: 0.40,     // epsilon_Strategic
  epsilonTactical: 0.40,    // epsilon_Tactical
  tacticalMode: 'plan-all',
  testingMode: false,
  fixLockouts: false,
  tutorialMode: false,
  numSessions: 2,
}

const rng = new SeededRNG(SEED ^ 0x91101)   // fixed operator-decision stream

// ── operator helpers ────────────────────────────────────────────────────────
const typeOf = (s: GameState, id: string) => s.assets.find(a => a.id === id)?.type

/** Cheapest set of pool drones that satisfies a task's primary (or substitute) composition. */
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

/** Build a whole-mission plan by hand from the committed pool (no agent involvement). */
function handBuild(mission: Mission, pool: string[], s: GameState): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  let free = [...pool]
  for (const t of [...mission.tasks].sort((a, b) => b.type - a.type)) {
    if (t.status === 'completed' || t.status === 'failed') continue
    const pick = staffTask(t, free, s)
    if (pick) { out[t.id] = pick; free = free.filter(id => !pick.includes(id)) }
  }
  return out
}

/**
 * Per-drone task sequence for a plan — exactly what the real planner sends alongside
 * taskAssignments. buildManualAssignments only schedules tasks that appear in some drone's
 * sequence, so omitting this silently commits nothing at all.
 */
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

// ── the operator ────────────────────────────────────────────────────────────
// One policy, applied identically in both sessions. Mixed by design: sometimes takes the agent's
// card, sometimes dismisses and reconsiders, sometimes allocates by hand; tactically sometimes
// follows Suggest, sometimes edits it, sometimes plans from scratch.
//
// Crucially it takes TIME to decide, and cannot commit to an agent card until that card has
// finished its "Analysing…" reveal — exactly the gate the real UI enforces by disabling Deploy.
// Without this the bot decides inside a single tick and every latency in the log is 0, which makes
// the RQ3 deliberation measures meaningless.
// Decisions take TIME, and an agent card cannot be committed until it has finished its
// "Analysing…" reveal — the same gate the real UI enforces by keeping Deploy disabled. Without
// this the bot decides inside a single tick, every latency in the log is 0, and the RQ3
// deliberation measures are meaningless (they even come out negative).
const thinkTime = (lo: number, hi: number) => rng.randFloat(lo, hi)

interface Decision {
  decideAt: number
  path: number              // allocation route chosen when the modal opened
  idx: number               // which card, if taking one
  target: AssetRequirement  // manual counts, if building by hand
  reopened: boolean
}
const stratDecision = new Map<string, Decision>()
const tacticalAt = new Map<string, number>()
const recoveryAt = new Map<string, number>()

function operate(s0: GameState): GameState {
  let s = s0
  const D = (a: GameAction) => { s = gameReducer(s, a) }
  const now = () => s.elapsed

  // 1. Anything asking for help gets triaged first — after a beat to read the situation.
  for (const m of s.missions.filter(m => m.failureRecoveryPending)) {
    if (!recoveryAt.has(m.id)) { recoveryAt.set(m.id, now() + thinkTime(5, 20)); continue }
    if (now() < recoveryAt.get(m.id)!) continue
    recoveryAt.delete(m.id)
    const roll = rng.next()
    const idle = s.assets.filter(a =>
      a.currentMissionId === m.id && a.status === 'deployed' &&
      m.tasks.find(t => t.id === a.currentTaskId)?.status !== 'executing').map(a => a.id)
    const pendingTasks = m.tasks.filter(t => t.status === 'pending')
    const plan: Record<string, string[]> = {}
    let free = [...idle]
    for (const t of pendingTasks) {
      const pick = staffTask(t, free, s)
      if (pick) { plan[t.id] = pick; free = free.filter(id => !pick.includes(id)) }
    }
    const canFix = pendingTasks.length > 0 && pendingTasks.every(t => plan[t.id])
    if (!canFix || roll > 0.92) { D({ type: 'ABANDON_MISSION', missionId: m.id }); continue }
    if (roll < 0.6) D({ type: 'TACTICAL_SUGGEST', missionId: m.id, recoveryMode: true })
    D({ type: 'CONFIRM_FAILURE_RECOVERY', missionId: m.id, taskAssignments: plan,
        droneSequences: sequencesFor(plan, pendingTasks.map(t => t.id)), wasAgentSuggested: roll < 0.6 })
  }

  // 2. Tactical planning for anything already allocated — also not instantaneous.
  for (const m of s.missions.filter(m => m.tacticalPending && m.pendingAllocation)) {
    if (!tacticalAt.has(m.id)) { tacticalAt.set(m.id, now() + thinkTime(4, 16)); continue }
    if (now() < tacticalAt.get(m.id)!) continue
    tacticalAt.delete(m.id)
    const pool = m.pendingAllocation!.dronePool
    const tac = rng.next()
    if (tac < 0.40) {
      // Consult the agent and go with it.
      D({ type: 'TACTICAL_SUGGEST', missionId: m.id })
      D({ type: 'CONFIRM_TACTICAL', missionId: m.id })
    } else if (tac < 0.70) {
      // Consult the agent, then move one drone before committing.
      D({ type: 'TACTICAL_SUGGEST', missionId: m.id })
      const plan: Record<string, string[]> = {}
      for (const [tid, ids] of Object.entries(m.pendingAllocation!.taskAssignments)) plan[tid] = [...ids]
      const tids = Object.keys(plan)
      if (tids.length >= 2) {
        const from = tids[0], to = tids[1]
        const spare = pool.find(id => !Object.values(plan).flat().includes(id))
        const moved = spare ?? plan[from][plan[from].length - 1]
        if (moved && (spare || plan[from].length > 1)) {
          if (!spare) plan[from] = plan[from].filter(id => id !== moved)
          plan[to] = [...plan[to], moved]
          D({ type: 'TACTICAL_ASSIGN_CHANGED', missionId: m.id, op: spare ? 'assign' : 'chain',
              droneId: moved, taskId: to, recoveryMode: false })
        }
      }
      D({ type: 'CONFIRM_TACTICAL', missionId: m.id, taskAssignments: plan,
          droneSequences: sequencesFor(plan, m.pendingAllocation!.taskOrder) })
    } else {
      // Plan from scratch without ever consulting the agent.
      const plan = handBuild(m, pool, s)
      for (const [tid, ids] of Object.entries(plan)) {
        for (const id of ids) {
          D({ type: 'TACTICAL_ASSIGN_CHANGED', missionId: m.id, op: 'assign', droneId: id, taskId: tid, recoveryMode: false })
        }
      }
      if (Object.keys(plan).length === 0) D({ type: 'CONFIRM_TACTICAL', missionId: m.id })
      else D({ type: 'CONFIRM_TACTICAL', missionId: m.id, taskAssignments: plan,
          droneSequences: sequencesFor(plan, m.pendingAllocation!.taskOrder) })
    }
  }

  // 3. The strategic modal is exclusive: one at a time, and Deploy stays locked until every card
  //    has revealed. If one is open, finish that decision before starting another.
  const modal = s.strategicModal
  if (modal) {
    const dec = stratDecision.get(modal.missionId)
    const mission = s.missions.find(x => x.id === modal.missionId)
    if (!dec || !mission) { D({ type: 'CLOSE_STRATEGIC' }); return s }
    if (now() < dec.decideAt) return s          // still deliberating
    stratDecision.delete(modal.missionId)

    if (dec.path < 0.20 && modal.strategies.length > 0 && !dec.reopened) {
      // Dismiss, sit on it, then re-open and commit on the second look.
      D({ type: 'CLOSE_STRATEGIC' })
      D({ type: 'OPEN_STRATEGIC', missionId: mission.id })
      const m2 = s.strategicModal
      if (m2 && m2.missionId === mission.id) {
        const gate2 = Math.max(0, ...(m2.cardRevealDelaysMs ?? [0])) / 1000
        stratDecision.set(mission.id, { ...dec, reopened: true, decideAt: now() + gate2 + thinkTime(2, 8) })
      }
      return s
    }
    if (modal.strategies.length > 0 && dec.path < 0.65) {
      D({ type: 'PICK_STRATEGY', strategyIndex: dec.idx })
      D({ type: 'APPLY_STRATEGIC', missionId: mission.id, source: 'agent', strategyIndex: dec.idx,
          manualAllocation: null, strategyCardCount: modal.strategies.length })
    } else {
      // Build the allocation by hand, one ± click at a time.
      // Re-read the reserve NOW, not at open time: other allocations may have taken drones while
      // the operator was deliberating, and the real +/- picker caps at the live reserve.
      const live = reserveCount(s.assets, s.missions)
      const want = {
        Blue: Math.min(dec.target.Blue, live.Blue),
        Red: Math.min(dec.target.Red, live.Red),
        Green: Math.min(dec.target.Green, live.Green),
      }
      const running = { Blue: 0, Red: 0, Green: 0 }
      for (const t of ['Blue', 'Red', 'Green'] as AssetType[]) {
        for (let i = 0; i < want[t]; i++) { running[t]++; D({ type: 'EDIT_MANUAL', allocation: { ...running } }) }
      }
      if (running.Blue + running.Red + running.Green === 0) { D({ type: 'CLOSE_STRATEGIC' }); return s }
      D({ type: 'APPLY_STRATEGIC', missionId: mission.id, source: 'manual', strategyIndex: null,
          manualAllocation: { ...running }, strategyCardCount: modal.strategies.length,
          manualBeforeCardsLoaded: false, cardsLoadedAtManualSwitch: modal.strategies.length })
    }
    if (s.strategicModal) D({ type: 'CLOSE_STRATEGIC' })   // apply was rejected — give up on this one
    return s
  }

  // 4. Nothing open — pick the next mission to work on (highest penalty rate first).
  const order = { A: 1, B: 2, C: 3, D: 4, E: 5 }
  for (const m of [...s.missions.filter(m => m.status === 'queued')]
      .sort((a, b) => order[b.category] - order[a.category])) {
    const avail = reserveCount(s.assets, s.missions)
    const fl = floorOf(m.tasks)
    if (avail.Blue < fl.Blue || avail.Red < fl.Red || avail.Green < fl.Green) continue

    D({ type: 'OPEN_STRATEGIC', missionId: m.id })
    const opened = s.strategicModal
    if (!opened || opened.missionId !== m.id) continue

    // Compare both cards on the way in, then sit with it until the reveal finishes.
    if (opened.strategies.length === 2) {
      D({ type: 'PICK_STRATEGY', strategyIndex: rng.next() < 0.5 ? 0 : 1 })
      if (rng.next() < 0.6) D({ type: 'PICK_STRATEGY', strategyIndex: rng.next() < 0.5 ? 0 : 1 })
    }
    const spare = rng.next() < 0.5 ? 1 : 0
    const gate = Math.max(0, ...(opened.cardRevealDelaysMs ?? [0])) / 1000
    stratDecision.set(m.id, {
      decideAt: now() + gate + thinkTime(2, 11),
      path: rng.next(),
      idx: rng.next() < 0.55 ? 0 : 1,
      target: {
        Blue: Math.min(avail.Blue, fl.Blue + spare),
        Red: Math.min(avail.Red, fl.Red + spare),
        Green: Math.min(avail.Green, fl.Green + spare),
      },
      reopened: false,
    })
    break   // one modal at a time
  }
  return s
}

// Plausible end-of-session responses (this is where trust + workload are measured).
function submitSurveys(s0: GameState, sessionIdx: number): GameState {
  let s = s0
  const D = (a: GameAction) => { s = gameReducer(s, a) }
  const lik = (base: number) => Math.max(1, Math.min(7, Math.round(base + rng.noise() * 1.2)))
  const tlx = (base: number) => Math.max(0, Math.min(20, Math.round(base + rng.noise() * 3)))
  // Session 2 is the tactical-heavy one — a bit busier, so slightly higher demand.
  const load = sessionIdx === 0 ? 11 : 13
  D({ type: 'SUBMIT_SURVEY', surveyName: 'nasa_tlx', responses: {
    mental_demand: tlx(load), physical_demand: tlx(4), temporal_demand: tlx(load + 1),
    performance: tlx(8), effort: tlx(load), frustration: tlx(load - 3) } })
  D({ type: 'SUBMIT_SURVEY', surveyName: 'trust_strategic', responses: {
    strat_reliable: lik(4), strat_trust: lik(4), strat_performs: lik(4),
    strat_confident: lik(5), strat_useful: lik(5), strat_follow: lik(3) } })
  D({ type: 'SUBMIT_SURVEY', surveyName: 'trust_tactical', responses: {
    tact_reliable: lik(4), tact_trust: lik(4), tact_performs: lik(4),
    tact_confident: lik(4), tact_useful: lik(5), tact_follow: lik(3) } })
  D({ type: 'SUBMIT_SURVEY', surveyName: 'tam_strategic', responses: {
    strat_tam_perf: lik(5), strat_tam_useful: lik(5), strat_tam_easy_learn: lik(6), strat_tam_easy_use: lik(6) } })
  D({ type: 'SUBMIT_SURVEY', surveyName: 'tam_tactical', responses: {
    tact_tam_perf: lik(4), tact_tam_useful: lik(5), tact_tam_easy_learn: lik(6), tact_tam_easy_use: lik(5) } })
  D({ type: 'FINISH_SURVEYS' })
  return s
}

// ── drive the whole study ───────────────────────────────────────────────────
let state = buildInitialState(config)
for (let sess = 0; sess < SESSIONS.length; sess++) {
  const dur = state.sessionDuration
  const steps = Math.ceil(dur / DT) + 8
  for (let i = 0; i <= steps; i++) {
    state = gameReducer(state, { type: 'TICK', nowMs: i * DT * 1000 })
    if (state.phase !== 'playing') break
    state = operate(state)
  }
  // Operator memory is per-session: mission ids repeat (M001...) across sessions, so a stale
  // timer would make session 2 sit on a decision it thinks it already started.
  stratDecision.clear(); tacticalAt.clear(); recoveryAt.clear()
  const evs = state.events[sess]
  const ended = evs.find(e => e.type === 'session_ended') as any
  console.log(`session ${sess + 1} (${SESSIONS[sess]}): ${evs.length} events, ` +
    `score=${ended?.score}, penalty=${ended?.penaltyAccrued}, points=${ended?.completionPoints}`)
  state = submitSurveys(state, sess)
  if (sess < SESSIONS.length - 1) state = gameReducer(state, { type: 'NEXT_SESSION' })
}
state = gameReducer(state, { type: 'END_STUDY' })

const payload = {
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
const dir = 'logs/Pilots/auto'
mkdirSync(dir, { recursive: true })
const path = `${dir}/study_${config.participantId}_${config.condition}_${config.seed}.json`
writeFileSync(path, JSON.stringify(payload, null, 2))
const kb = (JSON.stringify(payload).length / 1024).toFixed(0)
console.log(`\nwrote ${path}  (${kb} KB, ${state.events.flat().length} events total)`)
