/**
 * Log-fidelity audit: run the REAL gameReducer headlessly (same approach as sim/engine.mts),
 * then check the emitted event log against the reducer's own final state (ground truth).
 *
 * Run: npx tsx <this file> [--seeds=20] [--duration=480] [--complexity=balanced]
 */
console.debug = () => {}
import { buildInitialState, gameReducer } from '../src/store/gameReducer.ts'
import { generateSessionPlan, TASK_PRIMARY, TASK_SUBSTITUTE } from '../src/utils/missionGen.ts'
import { SeededRNG } from '../src/utils/prng.ts'
import type { GameState, GameAction, StudyConfig, Complexity, AssetType, TaskType, AssetRequirement } from '../src/types/index.ts'

const arg = (k: string, d: string) => (process.argv.find(a => a.startsWith(`--${k}=`))?.split('=')[1] ?? d)
const N_SEEDS = parseInt(arg('seeds', '20'), 10)
const DURATION = parseInt(arg('duration', '480'), 10)
const COMPLEXITY = arg('complexity', 'balanced') as Complexity
const POLICY = arg('policy', 'redundant') as 'redundant' | 'lean'
const DT = 0.5

function baseConfig(complexity: Complexity, seed: number): StudyConfig {
  return {
    participantId: 'AUDIT', condition: 'none', mode: 'agent', complexity, seed,
    agentErrorRate: 0, epsilonTactical: 0, tacticalMode: 'plan-all',
    testingMode: false, tutorialMode: false, numSessions: 1, fixLockouts: true,
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
    Blue: state.assets.filter(a => a.type === 'Blue' && a.status === 'available').length,
    Red: state.assets.filter(a => a.type === 'Red' && a.status === 'available').length,
    Green: state.assets.filter(a => a.type === 'Green' && a.status === 'available').length,
  }
}
function neededCount(type: number): number {
  const c = TASK_PRIMARY[type as TaskType]; return c.Blue + c.Red + c.Green
}
function penaltyOrder(cat: string): number { return ({ A: 1, B: 2, C: 3, D: 4, E: 5 } as any)[cat] ?? 0 }

const recoveryTries = new Map<string, number>()

/** Smallest set of `pool` drones satisfying a task's primary (or substitute) composition. */
function staffTask(task: any, pool: string[], s: GameState): string[] | null {
  const typeOf = (id: string) => s.assets.find(a => a.id === id)?.type
  for (const comp of [TASK_PRIMARY[task.type as TaskType], TASK_SUBSTITUTE[task.type as TaskType]]) {
    if (!comp) continue
    const picked: string[] = []
    const left: any = { ...comp }
    for (const id of pool) {
      const t = typeOf(id) as AssetType | undefined
      if (t && left[t] > 0) { picked.push(id); left[t]-- }
    }
    if (left.Blue <= 0 && left.Red <= 0 && left.Green <= 0) return picked
  }
  return null
}

function operate(state: GameState, policy: 'redundant' | 'lean'): GameState {
  let s = state
  const D = (a: GameAction) => { s = gameReducer(s, a) }
  // Recovery through the SAME action the map window dispatches (CONFIRM_FAILURE_RECOVERY);
  // ACCEPT_RECOVERY / APPLY_MANUAL_RECOVERY are legacy and unreachable from the shipped UI.
  for (const m of s.missions.filter(mm => mm.failureRecoveryPending)) {
    const tries = (recoveryTries.get(m.id) ?? 0) + 1
    recoveryTries.set(m.id, tries)
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
      const seqs: Record<string, string[]> = {}
      for (const [tid, ids] of Object.entries(plan)) for (const id of ids) (seqs[id] ??= []).push(tid)
      D({ type: 'CONFIRM_FAILURE_RECOVERY', missionId: m.id, taskAssignments: plan, droneSequences: seqs, wasAgentSuggested: false } as GameAction)
      recoveryTries.delete(m.id)
    } else if (tries >= 8) {
      D({ type: 'ABANDON_MISSION', missionId: m.id } as GameAction)
      recoveryTries.delete(m.id)
    }
  }
  const queued = s.missions.filter(m => m.status === 'queued')
    .sort((a, b) => penaltyOrder(b.category) - penaltyOrder(a.category))
  for (const m of queued) {
    const reserve = reserveOf(s)
    const fl = floor(m.tasks)
    if (reserve.Blue < fl.Blue || reserve.Red < fl.Red || reserve.Green < fl.Green) continue
    D({ type: 'OPEN_STRATEGIC', missionId: m.id } as GameAction)
    const modal = s.strategicModal
    if (!modal || modal.missionId !== m.id) continue
    if (policy === 'redundant') {
      const idx = modal.strategies.findIndex((st: any) => st.name === 'Aggressive')
      const use = idx >= 0 ? idx : (modal.strategies.length ? 0 : -1)
      if (use < 0) { D({ type: 'CLOSE_STRATEGIC' } as GameAction); continue }
      D({ type: 'APPLY_STRATEGIC', missionId: m.id, source: 'agent', strategyIndex: use, manualAllocation: null } as GameAction)
    } else {
      D({ type: 'APPLY_STRATEGIC', missionId: m.id, source: 'manual', strategyIndex: null, manualAllocation: fl } as GameAction)
    }
    if (s.missions.find(x => x.id === m.id)?.tacticalPending) {
      D({ type: 'CONFIRM_TACTICAL', missionId: m.id } as GameAction)
    }
  }
  return s
}

interface Issue { seed: number; kind: string; detail: string }
const issues: Issue[] = []
function flag(seed: number, kind: string, detail: string) { issues.push({ seed, kind, detail }) }

const totals = {
  missions: 0, tasks: 0, tasksCompletedState: 0, tasksFailedState: 0, tasksUnresolvedState: 0,
  taskCompletedEvents: 0, taskFailedEvents: 0,
  missionsCompletedState: 0, missionsAbandonedState: 0, missionsQueuedState: 0, missionsActiveState: 0, missionsFailedState: 0,
  missionCompletedEvents: 0, missionAbandonedEvents: 0, missionArrivedEvents: 0,
  droneFailureEvents: 0, droneFailedState: 0, failureRecoveryEvents: 0,
  taskRequeuedEvents: 0, tasksRequeuedState: 0, abandonRequeued: 0, abandonLaterCompleted: 0,
  failReason: {} as Record<string, number>,
  outcome: {} as Record<string, number>,
}

for (let k = 0; k < N_SEEDS; k++) {
  const seed = 1000 + k
  const cfg = baseConfig(COMPLEXITY, seed)
  let state = buildInitialState(cfg)
  const bps = generateSessionPlan(new SeededRNG(seed ^ 1), COMPLEXITY, DURATION)
  state = { ...state, sessionDuration: DURATION, pendingBlueprints: bps }

  const steps = Math.ceil(DURATION / DT) + 8
  for (let i = 0; i <= steps; i++) {
    state = gameReducer(state, { type: 'TICK', nowMs: i * DT * 1000 })
    if (state.phase !== 'playing') break
    state = operate(state, POLICY)
  }

  // ── ground truth from the reducer's own state ──
  const missions = state.missions
  const events = state.events[0] ?? []
  const ev = (t: string) => events.filter((e: any) => e.type === t)

  totals.missions += missions.length
  totals.missionArrivedEvents += ev('mission_arrived').length
  if (ev('mission_arrived').length !== missions.length) {
    flag(seed, 'mission_arrived-count', `${ev('mission_arrived').length} events vs ${missions.length} missions in state`)
  }
  // every residual in state must be announced AND flagged; every flagged arrival must be a residual
  for (const m of missions.filter(mm => mm.isResidual)) {
    const a = (ev('mission_arrived') as any[]).find(e => e.missionId === m.id)
    if (!a) flag(seed, 'residual-not-announced', `${m.id} has no mission_arrived`)
    else if (!a.isResidual || !a.parentMissionId) flag(seed, 'residual-not-flagged', `${m.id} isResidual=${a.isResidual} parent=${a.parentMissionId}`)
  }
  for (const e of (ev('mission_arrived') as any[]).filter(x => x.isResidual)) {
    const m = missions.find(mm => mm.id === e.missionId)
    if (!m?.isResidual) flag(seed, 'arrival-flagged-residual-but-isnt', `${e.missionId}`)
  }

  for (const m of missions) {
    if (m.status === 'completed') totals.missionsCompletedState++
    else if (m.status === 'abandoned') totals.missionsAbandonedState++
    else if (m.status === 'queued') totals.missionsQueuedState++
    else if (m.status === 'active') totals.missionsActiveState++
    else if (m.status === 'failed') totals.missionsFailedState++
  }
  totals.missionCompletedEvents += ev('mission_completed').length
  totals.missionAbandonedEvents += ev('mission_abandoned').length
  for (const e of ev('mission_completed') as any[]) totals.outcome[e.outcome] = (totals.outcome[e.outcome] || 0) + 1

  // per-task audit
  const compEv = new Map<string, any[]>()
  const failEv = new Map<string, any[]>()
  const requeueEv = new Map<string, any[]>()
  for (const e of events as any[]) {
    if (e.type === 'task_completed') { const a = compEv.get(e.taskId) ?? []; a.push(e); compEv.set(e.taskId, a) }
    if (e.type === 'task_failed') { const a = failEv.get(e.taskId) ?? []; a.push(e); failEv.set(e.taskId, a) }
    if (e.type === 'task_requeued') { const a = requeueEv.get(e.taskId) ?? []; a.push(e); requeueEv.set(e.taskId, a) }
  }
  totals.taskRequeuedEvents += (events as any[]).filter(e => e.type === 'task_requeued').length
  totals.taskCompletedEvents += (events as any[]).filter(e => e.type === 'task_completed').length
  totals.taskFailedEvents += (events as any[]).filter(e => e.type === 'task_failed').length
  for (const e of events as any[]) if (e.type === 'task_failed') totals.failReason[e.reason] = (totals.failReason[e.reason] || 0) + 1

  for (const m of missions) {
    for (const t of m.tasks) {
      totals.tasks++
      const c = compEv.get(t.id) ?? []
      const f = failEv.get(t.id) ?? []
      if (t.status === 'completed') {
        totals.tasksCompletedState++
        if (c.length !== 1) flag(seed, 'completed-task-event-count', `${t.id} status=completed but ${c.length} task_completed events`)
        if (f.length > 0) flag(seed, 'completed-task-also-failed', `${t.id} completed in state but has ${f.length} task_failed (${f.map(x => x.reason)})`)
      } else if (t.status === 'failed') {
        totals.tasksFailedState++
        if (f.length !== 1) flag(seed, 'failed-task-event-count', `${t.id} status=failed but ${f.length} task_failed events (${f.map(x => x.reason)})`)
        if (c.length > 0) flag(seed, 'failed-task-also-completed', `${t.id} failed in state but has ${c.length} task_completed`)
      } else if (m.status === 'abandoned') {
        // Left mid-flight on an abandoned parent: its resolution is a task_requeued naming the
        // residual copy that inherited the work — it must NOT also be reported as failed.
        totals.tasksRequeuedState++
        const rq = requeueEv.get(t.id) ?? []
        if (rq.length !== 1) flag(seed, 'carried-task-requeue-count', `${t.id} on abandoned ${m.id} has ${rq.length} task_requeued`)
        if (f.length > 0) flag(seed, 'carried-task-also-failed', `${t.id} was re-queued but has ${f.length} task_failed`)
        if (rq[0] && !missions.some(mm => mm.id === rq[0].residualMissionId && mm.tasks.some(tt => tt.id === rq[0].residualTaskId))) {
          flag(seed, 'requeue-points-nowhere', `${t.id} → ${rq[0]?.residualTaskId} which does not exist`)
        }
      } else {
        totals.tasksUnresolvedState++
        if (c.length || f.length) flag(seed, 'unresolved-task-has-event', `${t.id} status=${t.status} but ${c.length} completed / ${f.length} failed events`)
      }
    }
  }

  // mission-level cross-check
  for (const m of missions) {
    const mc = (ev('mission_completed') as any[]).filter(e => e.missionId === m.id)
    const ma = (ev('mission_abandoned') as any[]).filter(e => e.missionId === m.id)
    // A mission cut off by the buzzer is relabelled 'completed' in state if ANY task finished, but
    // it never fired mission_completed — that pair is only legitimate when the mission was still in
    // flight at the end, which session_ended.inFlightMissionIds records.
    const cutOff = ((ev('session_ended') as any[])[0]?.inFlightMissionIds ?? []).includes(m.id)
    if (m.status === 'completed' && mc.length !== 1 && !cutOff) flag(seed, 'mission_completed-count', `${m.id} completed but ${mc.length} events and not in inFlightMissionIds`)
    if (m.status === 'abandoned' && ma.length !== 1) flag(seed, 'mission_abandoned-count', `${m.id} abandoned but ${ma.length} events`)
    if (m.status !== 'completed' && mc.length > 0) flag(seed, 'mission_completed-spurious', `${m.id} status=${m.status} but ${mc.length} mission_completed`)
    for (const e of mc) {
      const realDone = m.tasks.filter(t => t.status === 'completed').length
      const realFail = m.tasks.filter(t => t.status === 'failed').length
      if (e.tasksCompleted !== realDone) flag(seed, 'mission_completed-tasksCompleted', `${m.id} event=${e.tasksCompleted} state=${realDone}`)
      if (e.tasksFailed !== realFail) flag(seed, 'mission_completed-tasksFailed', `${m.id} event=${e.tasksFailed} state=${realFail}`)
    }
  }

  if (process.argv.includes('--debug') && k === 0) {
    const fr = ev('failure_recovery') as any[]
    const byType: Record<string, number> = {}
    for (const e of fr) byType[e.recoveryType] = (byType[e.recoveryType] || 0) + 1
    console.log('DEBUG failure_recovery total', fr.length, JSON.stringify(byType))
    console.log('DEBUG first 10:', fr.slice(0, 10).map(e => `${e.missionId}@${e.timestamp}ms/${e.recoveryType}/${e.repairedTaskIds}`).join(' | '))
    console.log('DEBUG drone_failure:', (ev('drone_failure') as any[]).map(e => `${e.missionId}@${e.timestamp}ms`).join(' | '))
  }

  // session_ended cross-check
  const se = (ev('session_ended') as any[])[0]
  if (!se) flag(seed, 'no-session_ended', 'session_ended missing')
  else {
    if (se.score !== state.score) flag(seed, 'session_ended-score', `event=${se.score} state=${state.score}`)
    if (se.penaltyAccrued !== state.penaltyAccrued) flag(seed, 'session_ended-penalty', `event=${se.penaltyAccrued} state=${state.penaltyAccrued}`)
    // completionPoints must equal the sum of rewards on task_completed events
    const rewardSum = (events as any[]).filter(e => e.type === 'task_completed').reduce((a, e) => a + (e.rewardEarned ?? 0), 0)
    if (se.completionPoints !== rewardSum) flag(seed, 'completionPoints-vs-task_completed', `session_ended=${se.completionPoints} sum(task_completed.rewardEarned)=${rewardSum}`)
  }

  // drone_failure events vs failures the reducer actually fired (mission.droneFailuresFired)
  const firedInState = missions.reduce((a, m) => a + (m.droneFailuresFired ?? 0), 0)
  totals.droneFailureEvents += ev('drone_failure').length
  totals.droneFailedState += firedInState
  if (ev('drone_failure').length !== firedInState) {
    flag(seed, 'drone_failure-count', `${ev('drone_failure').length} events vs ${firedInState} droneFailuresFired in state`)
  }

  // Residual-mission audit: the carried work must be traceable and never double-reported.
  for (const e of ev('mission_abandoned') as any[]) {
    const residual = missions.find(m => m.id === e.residualMissionId)
    const failedHere = (events as any[]).filter(x => x.type === 'task_failed' && x.reason === 'mission_abandoned' && x.missionId === e.missionId).length
    const requeuedHere = (events as any[]).filter(x => x.type === 'task_requeued' && x.missionId === e.missionId).length
    totals.abandonRequeued += requeuedHere
    if (failedHere + requeuedHere !== e.remainingTaskCount) {
      flag(seed, 'abandon-remainder-unaccounted', `${e.missionId}: ${e.remainingTaskCount} remaining but ${requeuedHere} requeued + ${failedHere} failed`)
    }
    if (residual) {
      const done = residual.tasks.filter(t => t.status === 'completed').length
      totals.abandonLaterCompleted += done
      if (requeuedHere !== residual.tasks.length) {
        flag(seed, 'requeue-count-vs-residual', `${e.missionId}: ${requeuedHere} task_requeued vs ${residual.tasks.length} residual tasks`)
      }
    }
  }

  totals.failureRecoveryEvents += ev('failure_recovery').length
  if (ev('failure_recovery').length > ev('drone_failure').length + ev('lockout_detected').length) {
    flag(seed, 'recovery>failures', `${ev('failure_recovery').length} recoveries vs ${ev('drone_failure').length} failures`)
  }
  // a task_failed(drone_failure) needs a drone_failure on the same mission at or before it
  for (const e of (events as any[]).filter(x => x.type === 'task_failed' && x.reason === 'drone_failure')) {
    const prior = (events as any[]).some(x => x.type === 'drone_failure' && x.missionId === e.missionId && x.timestamp <= e.timestamp)
    if (!prior) flag(seed, 'orphan-drone_failure-taskfail', `${e.taskId} failed reason=drone_failure with no prior drone_failure on ${e.missionId}`)
  }

  // seq monotonic + timestamps non-decreasing
  let lastSeq = -1, lastTs = -1
  for (const e of events as any[]) {
    if (e.seq <= lastSeq) flag(seed, 'seq-not-monotonic', `seq ${e.seq} after ${lastSeq} (${e.type})`)
    lastSeq = e.seq
    if (e.timestamp < lastTs - 1) flag(seed, 'timestamp-regression', `${e.type} ts=${e.timestamp} after ${lastTs}`)
    lastTs = Math.max(lastTs, e.timestamp)
  }
}

console.log(`\n=== LOG AUDIT — ${COMPLEXITY}, ${N_SEEDS} seeds x ${DURATION}s, policy=${POLICY} ===`)
console.log('missions in state:', totals.missions, '| mission_arrived events:', totals.missionArrivedEvents)
console.log('  mission status:', JSON.stringify({
  completed: totals.missionsCompletedState, abandoned: totals.missionsAbandonedState,
  queued: totals.missionsQueuedState, active: totals.missionsActiveState, failed: totals.missionsFailedState,
}))
console.log('  mission_completed events:', totals.missionCompletedEvents, 'outcomes:', JSON.stringify(totals.outcome))
console.log('  mission_abandoned events:', totals.missionAbandonedEvents)
console.log('tasks in state:', totals.tasks, JSON.stringify({
  completed: totals.tasksCompletedState, failed: totals.tasksFailedState, unresolved: totals.tasksUnresolvedState,
}))
console.log('  task_completed events:', totals.taskCompletedEvents, '| task_failed events:', totals.taskFailedEvents)
console.log('  task_failed reasons:', JSON.stringify(totals.failReason))
console.log('drone_failure events:', totals.droneFailureEvents, '| droneFailuresFired in state:', totals.droneFailedState, '| failure_recovery events:', totals.failureRecoveryEvents)
console.log('  task_requeued events:', totals.taskRequeuedEvents, '| carried tasks in state:', totals.tasksRequeuedState)
console.log('abandon: tasks re-queued', totals.abandonRequeued, '| of those later COMPLETED under the residual', totals.abandonLaterCompleted)

const byKind: Record<string, Issue[]> = {}
for (const i of issues) (byKind[i.kind] ??= []).push(i)
console.log(`\nISSUES: ${issues.length}`)
for (const [kind, list] of Object.entries(byKind).sort((a, b) => b[1].length - a[1].length)) {
  console.log(`  ${kind}: ${list.length}`)
  for (const i of list.slice(0, 4)) console.log(`      seed ${i.seed}: ${i.detail}`)
}
