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

  return { participantId, mode, complexity, seed, agentErrorRate: 0.20 }
}

export function randomSeed(): number {
  return Math.floor(Math.random() * 99999) + 1
}
