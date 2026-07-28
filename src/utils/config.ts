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

// Canonical study seed. Every participant who doesn't explicitly override the seed
// (Randomise button or ?seed= URL param) gets this exact run — same mission sequence,
// zones, task compositions, and failure schedule. Edit here to change the canonical scenario.
export const STUDY_SEED = 42

export function randomSeed(): number {
  return Math.floor(Math.random() * 99999) + 1
}
