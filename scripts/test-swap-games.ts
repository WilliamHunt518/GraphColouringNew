// Regression test for the game-order swap (study-v1.13, StudyConfig.swapGames).
// Run: npx tsx scripts/test-swap-games.ts
//
// With the fixed study seed, each session's mission stream is generated from seed ^ (game index),
// and the game index used to be the session number. So session 1 and session 2 were always the same
// two games whichever scenario ran in them, and game difficulty (which differs up to ~1.9x in
// workload) was confounded with scenario order. swapGames reverses the index so the SAME games are
// played in the opposite order -- which is only useful if "the same games" is literally true.
//
// This checks: planSeedIndex's mapping; a swapped session n reproduces the unswapped session
// (numSessions + 1 - n) blueprint-for-blueprint, in both scenario orders; the unswapped path is
// byte-identical to the pre-v1.13 behaviour (seed ^ sessionNumber); and -- the strongest check --
// a swapped tactical-first session 1 reproduces the Tactical game P12 actually played in session 2,
// mission for mission, straight from the participant log.
import { readFileSync } from 'fs'
import { buildInitialState, gameReducer } from '../src/store/gameReducer'
import { generateSessionPlan } from '../src/utils/missionGen'
import { SeededRNG } from '../src/utils/prng'
import { planSeedIndex, STUDY_SEED } from '../src/utils/config'
import type { GameState, StudyConfig, MissionBlueprint } from '../src/types'

let failures = 0
const check = (label: string, cond: boolean, detail?: unknown) => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}${detail !== undefined ? `  — ${JSON.stringify(detail)}` : ''}`)
  if (!cond) failures++
}

function config(order: [StudyConfig['complexity'], StudyConfig['complexity']], swapGames: boolean): StudyConfig {
  return {
    participantId: 'TEST', condition: 'none', mode: 'agent', complexity: order[0], sessionComplexities: order,
    seed: STUDY_SEED, agentErrorRate: 0, epsilonTactical: 0, tacticalMode: 'plan-all', testingMode: false,
    tutorialMode: false, numSessions: 2, fixLockouts: true, swapGames,
  } as StudyConfig
}

function sessionPlans(cfg: StudyConfig): [MissionBlueprint[], MissionBlueprint[]] {
  const s1 = buildInitialState(cfg)
  const between = { ...s1, phase: 'between' } as GameState
  const s2 = gameReducer(between, { type: 'NEXT_SESSION' } as never)
  return [s1.pendingBlueprints, s2.pendingBlueprints]
}

const same = (a: MissionBlueprint[], b: MissionBlueprint[]) => JSON.stringify(a) === JSON.stringify(b)

// ── 1. The index mapping ────────────────────────────────────────────────────────────────────────
check('unswapped: index = session number', planSeedIndex({ numSessions: 2 }, 1) === 1 && planSeedIndex({ numSessions: 2 }, 2) === 2)
check('swapped: session 1 plays game 2', planSeedIndex({ numSessions: 2, swapGames: true }, 1) === 2)
check('swapped: session 2 plays game 1', planSeedIndex({ numSessions: 2, swapGames: true }, 2) === 1)
check('single-session run ignores the swap', planSeedIndex({ numSessions: 1, swapGames: true }, 1) === 1)

// ── 2. Swapped session n == unswapped session (3 - n), in both scenario orders ────────────────
for (const order of [['strategic', 'tactical'], ['tactical', 'strategic']] as const) {
  const [u1, u2] = sessionPlans(config([order[0], order[1]], false))
  // The swapped participant plays the SAME scenario order; what changes is which game each gets.
  // So swapped session 1 (scenario order[0], game 2) must equal the unswapped run of that scenario
  // as game 2, i.e. the opposite order's session 2.
  const [o1, o2] = sessionPlans(config([order[1], order[0]], false))
  const [w1, w2] = sessionPlans(config([order[0], order[1]], true))
  check(`${order.join('-first/')}: swapped session 1 == ${order[0]} as game 2`, same(w1, o2), { n: w1.length })
  check(`${order.join('-first/')}: swapped session 2 == ${order[1]} as game 1`, same(w2, o1), { n: w2.length })
  check(`${order.join('-first/')}: swap actually changes the games`, !same(w1, u1) && !same(w2, u2))
}

// ── 3. The unswapped path is unchanged from pre-v1.13 (seed ^ sessionNumber) ──────────────────
{
  const [u1, u2] = sessionPlans(config(['strategic', 'tactical'], false))
  check('unswapped session 1 == seed ^ 1', same(u1, generateSessionPlan(new SeededRNG(STUDY_SEED ^ 1), 'strategic')))
  check('unswapped session 2 == seed ^ 2', same(u2, generateSessionPlan(new SeededRNG(STUDY_SEED ^ 2), 'tactical')))
}

// ── 4. Against real data: swapped tactical-first session 1 == P12's logged session 2 ─────────
{
  const log = JSON.parse(readFileSync(new URL('../logs/Participants/P12.json', import.meta.url), 'utf-8'))
  const sess = log.sessions[1]
  const evs: any[] = (Array.isArray(sess) ? sess : Object.values(sess)).filter((e: any) => e && typeof e === 'object')
  const start = evs.find(e => e.type === 'session_start')
  const logged = evs.filter(e => e.type === 'mission_arrived' && !e.isResidual)
    .map(e => ({ id: e.missionId, category: e.category, arrival: e.arrivalTime, tasks: e.tasks.map((t: any) => t.type) }))
  const [w1] = sessionPlans(config(['tactical', 'strategic'], true))
  const planned = w1.filter(bp => bp.arrivalTime < start.sessionDuration)
    .map(bp => ({ id: bp.id, category: bp.category, arrival: bp.arrivalTime, tasks: bp.taskTypes }))
  check('P12 session 2 was tactical, seed 42', start.complexity === 'tactical' && start.seed === STUDY_SEED)
  check('swapped tactical-first session 1 reproduces P12\'s tactical game mission-for-mission',
    JSON.stringify(planned) === JSON.stringify(logged), { planned: planned.length, logged: logged.length })
}

// ── 5. session_start logs the swap and the game index ─────────────────────────────────────────
{
  const s = buildInitialState(config(['tactical', 'strategic'], true))
  const ticked = gameReducer({ ...s, phase: 'playing' } as GameState, { type: 'TICK', nowMs: 1000 } as never)
  const start: any = ((ticked.events as any)[0] ?? []).find((e: any) => e.type === 'session_start')
  check('session_start logs swapGames and planSeedIndex', start?.swapGames === true && start?.planSeedIndex === 2,
    start ? { swapGames: start.swapGames, planSeedIndex: start.planSeedIndex, appVersion: start.appVersion } : 'no session_start')
}

console.log(failures ? `\n${failures} FAILED` : '\nall passed')
process.exit(failures ? 1 : 0)
