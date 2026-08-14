import type { Complexity, Mode, StudyConfig } from '../types'

export function parseURLConfig(): StudyConfig | null {
  const p = new URLSearchParams(window.location.search)
  const participantId = p.get('pid') ?? ''
  const complexity = p.get('complexity') as Complexity | null
  const seedStr = p.get('seed')

  if (!participantId || !complexity || !seedStr) return null

  const validComplexities: Complexity[] = ['balanced', 'strategic', 'tactical', 'full', 'quick']
  if (!validComplexities.includes(complexity)) return null

  const seed = parseInt(seedStr, 10)
  if (isNaN(seed)) return null

  const validModes: Mode[] = ['no-agent', 'agent']
  const modeParam = p.get('mode') as Mode | null
  const mode: Mode = modeParam && validModes.includes(modeParam) ? modeParam : 'agent'

  const parseEpsilon = (raw: string | null, fallback: number): number => {
    if (raw === null) return fallback
    const v = parseFloat(raw)
    return isNaN(v) ? fallback : Math.min(0.95, Math.max(0, v))
  }

  const agentErrorRate  = parseEpsilon(p.get('eps_s'), 0.0)
  const epsilonTactical = parseEpsilon(p.get('eps_t'), 0.0)
  const tacticalMode: StudyConfig['tacticalMode'] = p.get('tacticalMode') === 'greedy' ? 'greedy' : 'plan-all'
  const testingMode = p.get('test') === '1'
  const fullPathsOnHover = p.get('fullpaths') === '1'
  const fixLockouts = p.get('fixLockouts') === '1'   // default OFF (help-needed); ?fixLockouts=1 for auto-fix
  const numSessionsRaw = parseInt(p.get('numSessions') ?? '1', 10)
  const numSessions = isNaN(numSessionsRaw) || numSessionsRaw < 1 ? 1 : numSessionsRaw

  return {
    participantId, condition: 'none', mode, complexity, seed,
    agentErrorRate, epsilonTactical, tacticalMode, testingMode, tutorialMode: false, numSessions,
    fullPathsOnHover, fixLockouts,
  }
}

/**
 * Single source of truth for the lockout policy.
 *
 * Default is OFF = "help needed": a scheduling deadlock is surfaced to the operator in red and
 * they re-plan or abandon it. `?fixLockouts=1` (or the StartScreen checkbox) turns on the agent's
 * silent reroute. Both real entry points already set the flag explicitly; this helper only decides
 * what an OMITTED flag means, and it used to disagree in three places — `gameReducer` read
 * `!== false` (auto-fix ON), `Tutorial.tsx` read it as plain-falsy (auto-fix OFF), and the
 * `session_start` log recorded the reducer's reading, so the log could contradict the behaviour.
 */
export function isFixLockouts(cfg: { fixLockouts?: boolean }): boolean {
  return cfg.fixLockouts === true
}

// Canonical study seed. Every participant who doesn't explicitly override the seed
// (Randomise button or ?seed= URL param) gets this exact run — same mission sequence,
// zones, task compositions, and failure schedule. Edit here to change the canonical scenario.
export const STUDY_SEED = 42

export function randomSeed(): number {
  return Math.floor(Math.random() * 99999) + 1
}
