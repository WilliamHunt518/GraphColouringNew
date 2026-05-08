import type { AssetRequirement, AssetType, AssetChip, MissionCategory, MetaRecommendation, Posture } from '../types'
import type { SeededRNG } from './prng'

// ─── Expected value of each posture ──────────────────────────────────────

/**
 * Rough EV calculation for each posture given current reserve and forecast.
 * Noise ε_M perturbs the perceived forecast before computing EVs.
 */
function postureEV(
  posture: Posture,
  reserve: AssetRequirement,
  activeMissions: number,
  forecast: Record<MissionCategory, number>,
  epsilonM: number,
  rng: SeededRNG,
): number {
  // Perturb forecast
  const perturbedForecast = { ...forecast }
  let total = 0
  for (const cat of ['A', 'B', 'C', 'D', 'E'] as MissionCategory[]) {
    perturbedForecast[cat] = Math.max(0, forecast[cat] + epsilonM * rng.noise())
    total += perturbedForecast[cat]
  }
  if (total > 0) {
    for (const cat of ['A', 'B', 'C', 'D', 'E'] as MissionCategory[]) {
      perturbedForecast[cat] /= total
    }
  }

  // Simplified heuristic:
  // Aggressive: high EV when reserve is full and next mission is likely low-complexity
  // Conservative: high EV when reserve is thin or high-complexity arrival likely
  // Hold: high EV when active missions are many (queue already full)

  const totalReserve = reserve.Blue + reserve.Red * 1.5 + reserve.Green * 3
  const heavyProb = perturbedForecast.D + perturbedForecast.E
  const queueLoad = activeMissions / 4  // 0–1 proxy for how busy things are

  switch (posture) {
    case 'Aggressive':
      return totalReserve * 0.3 - heavyProb * 20 - queueLoad * 10
    case 'Conservative':
      return heavyProb * 30 - (totalReserve - 10) * 0.2 + queueLoad * 5
    case 'Hold':
      return queueLoad * 20 - totalReserve * 0.1
  }
}

// ─── Per-asset chip logic ─────────────────────────────────────────────────

function chipFor(
  type: AssetType,
  reserve: AssetRequirement,
  heavyProb: number,
): AssetChip {
  const count = reserve[type]
  const total = type === 'Blue' ? 18 : type === 'Red' ? 9 : 3

  if (count / total > 0.6 && heavyProb < 0.2) return 'commit freely'
  if (count / total < 0.2 || (type === 'Green' && heavyProb > 0.4)) return 'hold'
  return 'commit cautiously'
}

// ─── Main evaluator ───────────────────────────────────────────────────────

export function evaluatePosture(
  reserve: AssetRequirement,
  activeMissions: number,
  forecast: Record<MissionCategory, number>,
  epsilonM: number,
  rng: SeededRNG,
  elapsed: number,
): MetaRecommendation {
  const postures: Posture[] = ['Aggressive', 'Conservative', 'Hold']
  const evs = postures.map(p => ({
    posture: p,
    ev: postureEV(p, reserve, activeMissions, forecast, epsilonM, rng),
  }))
  const best = evs.reduce((a, b) => (b.ev > a.ev ? b : a))

  const heavyProb = forecast.D + forecast.E
  const chips: Record<AssetType, AssetChip> = {
    Blue: chipFor('Blue', reserve, heavyProb),
    Red: chipFor('Red', reserve, heavyProb),
    Green: chipFor('Green', reserve, heavyProb),
  }

  const rationale = buildRationale(best.posture, reserve, heavyProb, activeMissions)

  return { posture: best.posture, rationale, chips, timestamp: elapsed }
}

function buildRationale(
  posture: Posture,
  reserve: AssetRequirement,
  heavyProb: number,
  activeMissions: number,
): string {
  const thinReserve = reserve.Green < 2 || reserve.Red < 3
  const manyActive = activeMissions >= 3

  switch (posture) {
    case 'Aggressive':
      return `Reserve is strong. ${(heavyProb * 100).toFixed(0)}% chance of Tier D–E next. Recommend Aggressive.`
    case 'Conservative':
      return thinReserve
        ? `Reserve is thin. ${(heavyProb * 100).toFixed(0)}% Tier D–E probability. Recommend Conservative.`
        : `High-complexity arrival likely (${(heavyProb * 100).toFixed(0)}%). Preserve specialists. Recommend Conservative.`
    case 'Hold':
      return manyActive
        ? `${activeMissions} missions active. Queue full — recommend Hold until assets return.`
        : `Balanced conditions. Hold posture optimal given current state.`
  }
}
