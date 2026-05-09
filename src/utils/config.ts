import type { Condition, StudyConfig } from '../types'

const EPSILON: Record<string, number> = { H: 0.10, L: 0.40, P: 0.00 }

export function conditionToEpsilons(condition: Condition) {
  return {
    epsilonCopilot: EPSILON[condition[0]] ?? 0,
    epsilonMeta:    EPSILON[condition[1]] ?? 0,
  }
}

/** Parse URL search params into a StudyConfig, or return null if any required field is missing/invalid. */
export function parseURLConfig(): StudyConfig | null {
  const p = new URLSearchParams(window.location.search)
  const participantId = p.get('pid') ?? ''
  const condition = p.get('condition') as Condition | null
  const complexity = p.get('complexity') as StudyConfig['complexity'] | null
  const seedStr = p.get('seed')

  if (!participantId || !condition || !complexity || !seedStr) return null

  const validConditions: Condition[] = ['HH', 'LH', 'HL', 'LL', 'PP']
  const validComplexities = ['easy', 'medium', 'hard']
  if (!validConditions.includes(condition)) return null
  if (!validComplexities.includes(complexity)) return null

  const seed = parseInt(seedStr, 10)
  if (isNaN(seed)) return null

  return { participantId, condition, complexity, seed, ...conditionToEpsilons(condition) }
}

/** Generate a random seed suitable as a default. */
export function randomSeed(): number {
  return Math.floor(Math.random() * 99999) + 1
}
