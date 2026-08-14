// Does the team actually deployed match the composition the strategy card advertises?
//
// The card's headline for Aggressive is "At least one spare drone per type deployed as a failure
// buffer", and its Reserve line / Resilience bar are computed from that composition. This checks
// the drone pool APPLY_STRATEGIC actually commits, in both tactical modes, with eps = 0 so no
// display noise is involved.
import { gameReducer, buildInitialState } from '../src/store/gameReducer'
import type { StudyConfig, GameState, AssetRequirement } from '../src/types'

let failures = 0
function check(label: string, ok: boolean, detail = '') {
  if (!ok) failures++
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? '  — ' + detail : ''}`)
}

function comp(state: GameState, ids: string[]): AssetRequirement {
  const r: AssetRequirement = { Blue: 0, Red: 0, Green: 0 }
  for (const id of ids) {
    const a = state.assets.find(x => x.id === id)!
    r[a.type]++
  }
  return r
}
const fmt = (c: AssetRequirement) => `${c.Blue}F ${c.Red}L ${c.Green}C`

function run(tacticalMode: 'plan-all' | 'greedy', strategyIndex: number) {
  const config: StudyConfig = {
    participantId: 'T', condition: 'none', mode: 'agent', complexity: 'balanced', seed: 77777,
    agentErrorRate: 0, epsilonTactical: 0, tacticalMode,
    testingMode: true, tutorialMode: true, fixLockouts: false, numSessions: 1,
  } as StudyConfig

  let s: GameState = { ...buildInitialState(config), phase: 'playing' }
  s = gameReducer(s, { type: 'TICK', nowMs: 0 } as any)
  s = gameReducer(s, { type: 'FORCE_MISSION_ARRIVAL' } as any)
  const missionId = s.missions[0].id
  s = gameReducer(s, { type: 'OPEN_STRATEGIC', missionId } as any)

  const strat = s.strategicModal!.strategies[strategyIndex]
  // eps = 0, so what the card shows and the true values must already agree.
  check(`${tacticalMode}/${strat.name}: card shows the true composition (eps=0)`,
    JSON.stringify(strat.assets) === JSON.stringify(strat.trueAssets),
    `shown ${fmt(strat.assets)} vs true ${fmt(strat.trueAssets)}`)

  s = gameReducer(s, { type: 'PICK_STRATEGY', strategyIndex } as any)
  s = gameReducer(s, { type: 'APPLY_STRATEGIC', missionId, source: 'agent', strategyIndex } as any)

  const pool = s.missions.find(m => m.id === missionId)!.pendingAllocation!.dronePool
  const deployed = comp(s, pool)
  check(`${tacticalMode}/${strat.name}: deploys the advertised team`,
    JSON.stringify(deployed) === JSON.stringify(strat.assets),
    `card ${fmt(strat.assets)} → deployed ${fmt(deployed)}`)
}

for (const mode of ['plan-all', 'greedy'] as const) {
  for (const idx of [0, 1]) run(mode, idx)
}

console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILED`)
process.exit(failures === 0 ? 0 : 1)
