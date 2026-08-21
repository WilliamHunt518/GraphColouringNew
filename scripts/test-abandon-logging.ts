// Abandoning a mission must be logged as what it IS: the outstanding work is re-queued into a
// residual mission, not destroyed. Before this was pinned the reducer fired a task_failed
// ('mission_abandoned') for every incomplete task — so a log showed "3 tasks failed, 130 points
// forgone" while those same three tasks completed under the residual two minutes later — and the
// residual mission itself was never announced, so its task_completed events referred to a mission
// that had no mission_arrived.
//
// Pins, in order:
//   1. no task_failed on abandon while a residual carries the work
//   2. one task_requeued per carried task, naming the residual task id it becomes
//   3. mission_abandoned reports where the reward went (carried vs genuinely lost)
//   4. the residual is announced with mission_arrived + isResidual/parentMissionId
//   5. the abandoned parent stops accruing penalty at abandonedAt (the residual takes over, so
//      charging both double-billed one piece of work)
//   6. the parent keeps status 'abandoned' through session end, and its tasks are not re-failed
//
// Run: npx tsx scripts/test-abandon-logging.ts
import { buildInitialState, gameReducer } from '../src/store/gameReducer'
import { CATEGORY_PENALTY_RATE } from '../src/utils/missionGen'
import type { GameState, StudyConfig, Mission, GameEvent } from '../src/types'

let failures = 0
const check = (label: string, cond: boolean, detail = '') => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}${detail ? '  — ' + detail : ''}`)
  if (!cond) failures++
}

const config: StudyConfig = {
  participantId: 'ABANDON', condition: 'none', mode: 'agent', complexity: 'balanced',
  seed: 42, agentErrorRate: 0, epsilonTactical: 0, tacticalMode: 'plan-all',
  testingMode: true,          // manual mission spawn, no scheduled failure roll
  tutorialMode: false, numSessions: 1, fixLockouts: true,
}

const tick = (s: GameState, sec: number) => gameReducer(s, { type: 'TICK', nowMs: sec * 1000 } as any)
const events = (s: GameState) => (s.events[0] ?? []) as GameEvent[]
const byType = <T extends GameEvent['type']>(s: GameState, t: T) =>
  events(s).filter(e => e.type === t) as Extract<GameEvent, { type: T }>[]
const missionById = (s: GameState, id: string): Mission => s.missions.find(m => m.id === id)!

// ── Deploy a mission, then abandon it part-way ────────────────────────────
let s: GameState = { ...buildInitialState(config), phase: 'playing' }
s = tick(s, 0)
s = gameReducer(s, { type: 'FORCE_MISSION_ARRIVAL' } as any)
const missionId = s.missions[0].id

s = gameReducer(s, { type: 'OPEN_STRATEGIC', missionId } as any)
s = gameReducer(s, {
  type: 'APPLY_STRATEGIC', missionId, source: 'agent', strategyIndex: 0, manualAllocation: null,
} as any)
const plan = missionById(s, missionId).pendingAllocation!
const sequences = (assignments: Record<string, string[]>, order: string[]) => {
  const out: Record<string, string[]> = {}
  for (const tid of order) for (const id of assignments[tid] ?? []) (out[id] ??= []).push(tid)
  return out
}
s = gameReducer(s, {
  type: 'CONFIRM_TACTICAL', missionId,
  taskAssignments: plan.taskAssignments,
  droneSequences: sequences(plan.taskAssignments, plan.taskOrder),
} as any)

// Run far enough that at least one task is genuinely in flight, but not to completion.
for (let t = 1; t <= 20; t++) s = tick(s, t)
const beforeAbandon = missionById(s, missionId)
const incomplete = beforeAbandon.tasks.filter(t => t.status !== 'completed' && t.status !== 'failed')
check('mission has incomplete tasks to carry over', incomplete.length > 0, `${incomplete.length} incomplete`)

const abandonAt = s.elapsed
s = gameReducer(s, { type: 'ABANDON_MISSION', missionId } as any)

// ── 1 + 2. carried work is re-queued, never "failed" ──────────────────────
const failedOnAbandon = byType(s, 'task_failed').filter(e => e.reason === 'mission_abandoned')
const requeued = byType(s, 'task_requeued')
check('no task_failed logged for carried work', failedOnAbandon.length === 0,
  `${failedOnAbandon.length} task_failed(mission_abandoned)`)
check('one task_requeued per incomplete task', requeued.length === incomplete.length,
  `${requeued.length} requeued vs ${incomplete.length} incomplete`)

const residualId = `${missionId}-R`
const residual = missionById(s, residualId)
check('residual mission exists', !!residual)
check('every task_requeued names a real residual task',
  requeued.every(e => e.residualMissionId === residualId &&
    residual.tasks.some(t => t.id === e.residualTaskId)),
  requeued.map(e => `${e.taskId}→${e.residualTaskId}`).join(' '))
check('task_requeued carries reward forward',
  requeued.every(e => e.rewardDeferred > 0))

// ── 3. mission_abandoned accounts for the reward ──────────────────────────
const ab = byType(s, 'mission_abandoned')[0]
check('mission_abandoned points at the residual', ab.residualMissionId === residualId, String(ab.residualMissionId))
check('mission_abandoned carriedTaskIds matches remainingTaskCount',
  ab.carriedTaskIds.length === ab.remainingTaskCount,
  `${ab.carriedTaskIds.length} vs ${ab.remainingTaskCount}`)
check('mission_abandoned reports nothing lost when everything carried',
  ab.rewardLost === 0 && ab.rewardCarriedOver > 0,
  `carried=${ab.rewardCarriedOver} lost=${ab.rewardLost}`)

// ── 4. the residual is announced ──────────────────────────────────────────
const arrivals = byType(s, 'mission_arrived')
const resArrival = arrivals.find(e => e.missionId === residualId)
check('residual gets a mission_arrived', !!resArrival)
check('residual arrival is flagged as residual with its parent',
  !!resArrival && resArrival.isResidual === true && resArrival.parentMissionId === missionId,
  resArrival ? `isResidual=${resArrival.isResidual} parent=${resArrival.parentMissionId}` : '')
check('organic arrival is not flagged residual',
  arrivals.filter(e => e.missionId === missionId).every(e => e.isResidual === false && e.parentMissionId === null))
check('residual arrival lists every carried task',
  !!resArrival && resArrival.tasks.length === requeued.length,
  resArrival ? `${resArrival.tasks.length} tasks` : '')

// ── 5. the abandoned parent stops accruing penalty ────────────────────────
const penaltyAtAbandon = s.penaltyAccrued
const WINDOW = 60
let sLater = s
for (let t = Math.ceil(abandonAt) + 1; t <= Math.ceil(abandonAt) + WINDOW; t++) sLater = tick(sLater, t)
const parentAfter = missionById(sLater, missionId)
check('abandoned parent keeps status abandoned while the session runs',
  parentAfter.status === 'abandoned', parentAfter.status)
check('abandoned parent records abandonedAt', parentAfter.abandonedAt !== null)

// The residual is left unallocated, so over this window exactly one mission's worth of outstanding
// work should be billed. If the parent were still accruing too (the old behaviour) the growth would
// be ~2x the category rate — the operator charged twice for one outstanding job.
const rate = CATEGORY_PENALTY_RATE[beforeAbandon.category]
const growth = sLater.penaltyAccrued - penaltyAtAbandon
const oneMission = rate * WINDOW
check('penalty grows at one mission\'s rate, not two',
  growth > oneMission * 0.5 && growth < oneMission * 1.5,
  `grew ${growth} over ${WINDOW}s; one mission ≈ ${oneMission.toFixed(1)}, two ≈ ${(oneMission * 2).toFixed(1)}`)

// ── 6. session end does not re-fail the parent's carried tasks ────────────
const sEnd = gameReducer(sLater, { type: 'FORCE_SESSION_END' } as any)
const endFails = (sEnd.events[0] as GameEvent[]).filter(
  e => e.type === 'task_failed' && (e as any).missionId === missionId)
check('parent tasks are not failed again at session end', endFails.length === 0,
  `${endFails.length} task_failed on the abandoned parent`)
check('parent still reads as abandoned in the final state',
  missionById(sEnd, missionId).status === 'abandoned',
  missionById(sEnd, missionId).status)

const se = (sEnd.events[0] as GameEvent[]).find(e => e.type === 'session_ended') as any
check('session_ended ledger counts the re-queue separately from failures',
  se.taskOutcomes.requeued === requeued.length &&
  se.taskOutcomes.failed === (sEnd.events[0] as GameEvent[]).filter(e => e.type === 'task_failed').length,
  JSON.stringify(se.taskOutcomes))
check('session_ended failure reasons add up to the failure count',
  Object.values(se.taskOutcomes.failuresByReason as Record<string, number>)
    .reduce((a, b) => a + b, 0) === se.taskOutcomes.failed,
  JSON.stringify(se.taskOutcomes.failuresByReason))

console.log(failures === 0 ? '\nAll checks passed.' : `\n${failures} check(s) FAILED.`)
process.exit(failures === 0 ? 0 : 1)
