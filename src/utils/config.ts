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
  const fixLockouts = p.get('fixLockouts') !== '0'   // default ON (agent auto-fix); ?fixLockouts=0 for help-needed
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
 * Default is ON = the agent silently reroutes a scheduling deadlock so every task still completes
 * and nothing fails. A participant therefore cannot end up in a stuck-deadlock state, which is why
 * the tutorial does not teach one — see the note on `fixLockouts` in CLAUDE.md. `?fixLockouts=0`
 * (or unticking the StartScreen checkbox) restores the "help needed" branch, which surfaces the
 * lockout in red for the operator to re-plan or abandon; it is still fully implemented and tested
 * (`scripts/test-scheduling-deadlock.ts` covers both), just not what the study runs.
 *
 * Read the flag through here, never inline: the fallback for an omitted flag used to disagree
 * between the reducer, the tutorial, and the `session_start` log, so the log could contradict the
 * behaviour.
 */
export function isFixLockouts(cfg: { fixLockouts?: boolean }): boolean {
  return cfg.fixLockouts !== false
}

// Canonical study seed. Every participant who doesn't explicitly override the seed
// (Randomise button or ?seed= URL param) gets this exact run — same mission sequence,
// zones, task compositions, and failure schedule. Edit here to change the canonical scenario.
export const STUDY_SEED = 42

export function randomSeed(): number {
  return Math.floor(Math.random() * 99999) + 1
}
