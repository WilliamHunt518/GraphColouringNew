import type { Complexity, Mode, StudyConfig } from '../types'

export function parseURLConfig(): StudyConfig | null {
  const p = new URLSearchParams(window.location.search)
  const participantId = p.get('pid') ?? ''
  const complexity = p.get('complexity') as Complexity | null
  const seedStr = p.get('seed')

  if (!participantId || !complexity || !seedStr) return null

  const validComplexities: Complexity[] = ['standard', 'surge', 'precision', 'campaign']
  if (!validComplexities.includes(complexity)) return null

  const seed = parseInt(seedStr, 10)
  if (isNaN(seed)) return null

  const validModes: Mode[] = ['no-agent', 'agent']
  const modeParam = p.get('mode') as Mode | null
  const mode: Mode = modeParam && validModes.includes(modeParam) ? modeParam : 'no-agent'

  const parseEpsilon = (raw: string | null, fallback: number): number => {
    if (raw === null) return fallback
    const v = parseFloat(raw)
    return isNaN(v) ? fallback : Math.min(0.95, Math.max(0, v))
  }

  const agentErrorRate  = parseEpsilon(p.get('eps_s'), 0.20)
  const epsilonTactical = parseEpsilon(p.get('eps_t'), 0.20)
  const testingMode = p.get('test') === '1'

  return {
    participantId, condition: 'none', mode, complexity, seed,
    agentErrorRate, epsilonTactical, testingMode,
  }
}

export function randomSeed(): number {
  return Math.floor(Math.random() * 99999) + 1
}
