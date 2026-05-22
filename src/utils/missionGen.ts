import type { Asset, AssetType, MissionBlueprint, MissionCategory, TaskType, Complexity } from '../types'
import type { SeededRNG } from './prng'

// ─── Map constants ────────────────────────────────────────────────────────

export const HUB = { x: 500, y: 400 } as const
export const MAP_W = 1000
export const MAP_H = 800
export const ZONE_RADIUS = 96   // ~20% larger spread of waypoints within a zone
const ZONE_MIN_HUB = 120        // ~20% closer to hub — makes asset choice matter more
const ZONE_MIN_ZONE = 200   // minimum distance between zone centers

// ─── Physics ──────────────────────────────────────────────────────────────

export const ASSET_SPEED: Record<AssetType, number> = {
  Blue: 9.0,
  Red: 6.0,
  Green: 4.2,
}

/** Base execution time (seconds) per task type, primary composition */
export const TASK_BASE_TIME: Record<TaskType, number> = {
  1: 10,   // T1 Recce
  2: 20,   // T2 Recon
  3: 20,   // T3 Minor Drop
  4: 30,   // T4 Major Drop
  5: 30,   // T5 Search & Supply
}

// ─── Asset requirements ───────────────────────────────────────────────────

export interface TaskComposition {
  Blue: number
  Red: number
  Green: number
}

/**
 * Primary and substitute compositions per task type.
 * T1 Recce and T5 Search & Supply have no substitute.
 * T2 Recon / T3 Minor Drop / T4 Major Drop all have slower all-Blue (or Blue-heavy) substitutes.
 */
export const TASK_PRIMARY: Record<TaskType, TaskComposition> = {
  1: { Blue: 1, Red: 0, Green: 0 },   // T1 Recce: 1 Blue
  2: { Blue: 3, Red: 0, Green: 1 },   // T2 Recon: 3 Blues + 1 Green (thermal)
  3: { Blue: 1, Red: 1, Green: 0 },   // T3 Minor Drop: 1 Blue + 1 Red
  4: { Blue: 1, Red: 2, Green: 0 },   // T4 Major Drop: 1 Blue + 2 Reds
  5: { Blue: 0, Red: 1, Green: 1 },   // T5 Search & Supply: 1 Red + 1 Green
}

/** Substitute composition (null = no substitute exists) */
export const TASK_SUBSTITUTE: Record<TaskType, TaskComposition | null> = {
  1: null,
  2: null,
  3: { Blue: 3, Red: 0, Green: 0 },   // T3 Minor Drop sub: 3 Blues (lighter payload)
  4: { Blue: 3, Red: 1, Green: 0 },   // T4 Major Drop sub: 3 Blues + 1 Red
  5: null,
}

/** Base time when using substitute composition — same as primary; penalty is the extra drones required */
export const TASK_SUB_BASE_TIME: Record<TaskType, number> = {
  1: 10,
  2: 20,
  3: 20,
  4: 30,
  5: 30,
}

// ─── Session duration ─────────────────────────────────────────────────────

export const SESSION_DURATION_BY_COMPLEXITY: Record<Complexity, number> = {
  standard:  600,
  surge:     600,
  precision: 600,
  campaign:  600,
  quick:     600,  // 10 minutes
}

// ─── Complexity parameters ────────────────────────────────────────────────

// Mean inter-arrival time (seconds). Scales inversely with fleet so load-per-drone stays constant.
const LAMBDA: Record<Complexity, number> = {
  standard:  60,
  surge:     45,   // 1.33× fleet → 1.33× missions
  precision: 90,   // 0.67× fleet → 0.67× missions
  campaign:  50,   // large fleet, slower due to mission complexity
  quick:     42,   // small fleet, fast missions → busier throughput
}

// Category probability weights [A, B, C, D, E].
// standard/surge: lighter mix (more small allocations per session)
// precision/campaign: heavier mix (each allocation is a bigger decision)
// quick: favours A/B — mostly 3-4 task missions
const CATEGORY_WEIGHTS: Record<Complexity, number[]> = {
  standard:  [25, 35, 25, 12,  3],
  surge:     [40, 35, 17,  7,  1],
  precision: [ 5, 20, 30, 30, 15],
  campaign:  [ 5, 20, 28, 30, 17],
  quick:     [35, 30, 20, 12,  3],
}

const CATEGORIES: MissionCategory[] = ['A', 'B', 'C', 'D', 'E']

// ─── Task composition per mission category ────────────────────────────────

function buildTaskList(rng: SeededRNG, category: MissionCategory, complexity: Complexity): TaskType[] {
  if (complexity === 'quick') {
    // 3–5 tasks per mission — compact but still varied
    switch (category) {
      case 'A': return rng.randFloat(0, 1) < 0.5
        ? [3, 2, 1]     // T3 + T2 + T1 (3 tasks, no Green)
        : [2, 2, 1]     // T2 + T2 + T1 (3 tasks, no Green)
      case 'B': return rng.randFloat(0, 1) < 0.5
        ? [5, 3, 2, 1]  // T5 + T3 + T2 + T1 (4 tasks, 1 Green needed)
        : [4, 3, 2]     // T4 + T3 + T2 (3 tasks, no Green)
      case 'C': return [5, 4, 3, 2]    // 4 tasks (1 Green needed)
      case 'D': return [5, 4, 3, 2, 1] // 5 tasks (1 Green needed)
      case 'E': return [5, 4, 4, 3, 2] // 5 tasks, two T4s (1 Green needed)
    }
  }

  switch (category) {
    case 'A': {
      const t1 = rng.randInt(3, 5)  // 3 or 4
      const t2 = rng.randInt(2, 4)  // 2 or 3
      return [...Array<TaskType>(t1).fill(1), ...Array<TaskType>(t2).fill(2), 3]
    }
    case 'B':
      return rng.randFloat(0, 1) < 0.5
        ? [5, 4, 3, 3, 2, 2, 1, 1]   // T5+T4 heavy variant
        : [3, 3, 2, 2, 2, 1, 1, 1]   // lighter T3/T2/T1 mix
    case 'C': return [5, 4, 4, 3, 3, 2, 2, 1]
    case 'D': return [5, 5, 4, 4, 3, 3, 2, 2]
    case 'E': return [5, 5, 5, 4, 4, 3, 3, 2, 1]
  }
}

// ─── Spatial helpers ──────────────────────────────────────────────────────

function dist(a: { x: number; y: number }, b: { x: number; y: number }) {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

/** Uniform random point strictly inside a circle */
function sampleInCircle(rng: SeededRNG, cx: number, cy: number, r: number) {
  for (;;) {
    const x = cx + rng.randFloat(-r, r)
    const y = cy + rng.randFloat(-r, r)
    if ((x - cx) ** 2 + (y - cy) ** 2 < r * r) return { x, y }
  }
}

/** Random point inside a circle, at least minDist from all existing points */
function sampleInCircleNoOverlap(
  rng: SeededRNG,
  cx: number, cy: number, r: number,
  existing: Array<{ x: number; y: number }>,
  minDist: number,
): { x: number; y: number } {
  // Try with full minDist
  for (let attempt = 0; attempt < 250; attempt++) {
    const pt = sampleInCircle(rng, cx, cy, r)
    if (existing.every(e => Math.hypot(pt.x - e.x, pt.y - e.y) >= minDist)) return pt
  }
  // Relax progressively
  for (let d = minDist * 0.75; d >= 25; d *= 0.8) {
    for (let attempt = 0; attempt < 100; attempt++) {
      const pt = sampleInCircle(rng, cx, cy, r)
      if (existing.every(e => Math.hypot(pt.x - e.x, pt.y - e.y) >= d)) return pt
    }
  }
  // Last resort: pick the candidate that maximises minimum distance from existing
  let best = sampleInCircle(rng, cx, cy, r)
  let bestMin = 0
  for (let attempt = 0; attempt < 150; attempt++) {
    const pt = sampleInCircle(rng, cx, cy, r)
    const minD = existing.length === 0 ? Infinity : Math.min(...existing.map(e => Math.hypot(pt.x - e.x, pt.y - e.y)))
    if (minD > bestMin) { bestMin = minD; best = pt }
  }
  return best
}

function placeZone(
  rng: SeededRNG,
  existing: Array<{ x: number; y: number }>,
): { x: number; y: number } {
  const margin = ZONE_RADIUS + 10
  // Hard minimum: circles must not visually overlap (slightly tighter than ZONE_MIN_ZONE)
  const noOverlapMin = ZONE_RADIUS * 2 + 4

  // Primary: satisfy full preferred spacing
  for (let attempt = 0; attempt < 200; attempt++) {
    const x = rng.randFloat(margin, MAP_W - margin)
    const y = rng.randFloat(margin, MAP_H - margin)
    const pt = { x, y }
    if (dist(pt, HUB) < ZONE_MIN_HUB) continue
    if (existing.some(z => dist(pt, z) < ZONE_MIN_ZONE)) continue
    return pt
  }
  // Secondary: relax spacing but guarantee no visual overlap
  for (let attempt = 0; attempt < 200; attempt++) {
    const x = rng.randFloat(margin, MAP_W - margin)
    const y = rng.randFloat(margin, MAP_H - margin)
    const pt = { x, y }
    if (dist(pt, HUB) < ZONE_MIN_HUB) continue
    if (existing.some(z => dist(pt, z) < noOverlapMin)) continue
    return pt
  }
  // Last resort: find the candidate that maximises minimum clearance from existing zones
  let bestPt: { x: number; y: number } = { x: HUB.x, y: HUB.y - ZONE_MIN_HUB - 30 }
  let bestDist = 0
  for (let a = 0; a < 72; a++) {
    const angle = (a / 72) * Math.PI * 2
    for (let rr = ZONE_MIN_HUB; rr <= 350; rr += 30) {
      const pt = {
        x: Math.min(MAP_W - margin, Math.max(margin, HUB.x + Math.cos(angle) * rr)),
        y: Math.min(MAP_H - margin, Math.max(margin, HUB.y + Math.sin(angle) * rr)),
      }
      const minD = existing.length === 0 ? noOverlapMin : Math.min(...existing.map(z => dist(pt, z)))
      if (minD > bestDist) { bestDist = minD; bestPt = pt }
    }
  }
  return bestPt
}

// ─── Session plan generator ───────────────────────────────────────────────

/**
 * Pre-generates the complete mission schedule for a 600-second session.
 * All randomness drawn from the provided SeededRNG so the session is
 * fully reproducible from the seed alone.
 */
export function generateSessionPlan(
  rng: SeededRNG,
  complexity: Complexity,
  duration = SESSION_DURATION_BY_COMPLEXITY[complexity],
): MissionBlueprint[] {
  const lambda = LAMBDA[complexity]
  const blueprints: MissionBlueprint[] = []
  const usedCenters: Array<{ x: number; y: number }> = []
  let time = 0
  let seq = 0

  while (true) {
    const interval = rng.exponential(lambda)
    // Guarantee ≥3 missions in the first 2 minutes
    const n = blueprints.length
    const cappedInterval = n === 0 ? Math.min(interval, 3) : n <= 2 ? Math.min(interval, 60) : interval
    time += cappedInterval
    if (time > duration) break

    const category = rng.weightedChoice(CATEGORIES, CATEGORY_WEIGHTS[complexity])
    const taskTypes = buildTaskList(rng, category, complexity)
    // Only check against the last 5 zone centres — earlier missions will have completed
    // and their map space is available again.
    const zoneCenter = placeZone(rng, usedCenters.slice(-5))
    usedCenters.push(zoneCenter)

    const waypoints: Array<{ x: number; y: number }> = []
    for (let i = 0; i < taskTypes.length; i++) {
      waypoints.push(sampleInCircleNoOverlap(rng, zoneCenter.x, zoneCenter.y, ZONE_RADIUS, waypoints, 50))
    }

    blueprints.push({
      id: `M${String(++seq).padStart(3, '0')}`,
      arrivalTime: time,
      category,
      taskTypes,
      zoneCenter,
      waypoints,
      willFail: false,
      droneFailureRelativeTime: null,
    })
  }

  // Assign drone failures using a deck-of-cards approach:
  // missions are split into batches of FAILURE_BATCH_SIZE; within each batch
  // exactly floor(FAILURE_RATE * FAILURE_BATCH_SIZE) missions fail, at a
  // seeded-random position. This guarantees the configured rate is met
  // precisely over any multiple of FAILURE_BATCH_SIZE missions.
  const FAILURE_RATE = 0.20
  const FAILURE_BATCH_SIZE = 5
  const failuresPerBatch = Math.floor(FAILURE_RATE * FAILURE_BATCH_SIZE)  // = 1

  for (let batchStart = 0; batchStart < blueprints.length; batchStart += FAILURE_BATCH_SIZE) {
    const batchEnd = Math.min(batchStart + FAILURE_BATCH_SIZE, blueprints.length)
    const batchLen = batchEnd - batchStart
    // Shuffle [0..batchLen-1] with Fisher-Yates using the seeded RNG
    const order = Array.from({ length: batchLen }, (_, i) => i)
    for (let i = order.length - 1; i > 0; i--) {
      const j = rng.randInt(0, i + 1)
      ;[order[i], order[j]] = [order[j], order[i]]
    }
    // The first failuresPerBatch indices in the shuffled order are the failures
    const failSet = new Set(order.slice(0, Math.min(failuresPerBatch, batchLen)))
    for (let i = 0; i < batchLen; i++) {
      const willFail = failSet.has(i)
      const droneFailureRelativeTime = willFail
        ? 30 + rng.randFloat(0, 60)   // fail between 30–90s after arrival
        : null
      blueprints[batchStart + i] = { ...blueprints[batchStart + i], willFail, droneFailureRelativeTime }
    }
  }

  return blueprints
}

// ─── Scoring constants ────────────────────────────────────────────────────

/**
 * Penalty accrual rate in points per second while a mission is alive and incomplete.
 * Penalty runs from arrivalTime until completionTime (or session end if never finished).
 * Higher category = faster penalty = must be prioritised.
 */
export const CATEGORY_PENALTY_RATE: Record<MissionCategory, number> = {
  A: 0.05,
  B: 0.10,
  C: 0.15,
  D: 0.25,
  E: 0.40,
}

/** Completion reward per completed task (×10 vs legacy to give penalties room to bite). */
export const TASK_WEIGHT: Record<TaskType, number> = { 1: 10, 2: 20, 3: 30, 4: 40, 5: 50 }

/** Penalty is charged at this interval (seconds); each charge = CATEGORY_PENALTY_RATE × CHARGE_INTERVAL. */
export const CHARGE_INTERVAL = 15

// ─── Asset pool ───────────────────────────────────────────────────────────

// Fleet sizes per preset.  Surge/campaign reach 24B/12R/4G for higher volume.
const FLEET: Record<Complexity, [AssetType, number][]> = {
  standard:  [['Blue', 18], ['Red',  9], ['Green', 3]],
  surge:     [['Blue', 24], ['Red', 12], ['Green', 4]],
  precision: [['Blue', 12], ['Red',  6], ['Green', 2]],
  campaign:  [['Blue', 24], ['Red', 12], ['Green', 4]],
  quick:     [['Blue', 12], ['Red',  6], ['Green', 2]],
}

// Arthurian knight callsigns — unique per drone, readable, UK military tradition
export const ASSET_CALLSIGNS: Record<string, string> = {
  // Blue — fast recce drones (premier Round Table knights, B01–B24)
  B01: 'Arthur',    B02: 'Lancelot',  B03: 'Galahad',   B04: 'Gawain',    B05: 'Percival',
  B06: 'Tristram',  B07: 'Bors',      B08: 'Gareth',    B09: 'Gaheris',   B10: 'Kay',
  B11: 'Bedivere',  B12: 'Lamorak',   B13: 'Geraint',   B14: 'Palamedes', B15: 'Lucan',
  B16: 'Agravaine', B17: 'Lionel',    B18: 'Ywain',
  B19: 'Dinadan',   B20: 'Griflet',   B21: 'Sagramore', B22: 'Torre',     B23: 'Pellas',
  B24: 'Marhalt',
  // Red — standard supply/extract drones (allied kings and companion knights, R01–R12)
  R01: 'Ector',     R02: 'Lot',       R03: 'Uriens',    R04: 'Leodegrance', R05: 'Caradoc',
  R06: 'Bagdemagus',R07: 'Brunor',    R08: 'Safer',     R09: 'Pellinore',
  R10: 'Colgrevance', R11: 'Meliodas', R12: 'Agglovale',
  // Green — heavy specialist drones (legendary figures, G01–G04)
  G01: 'Balin',     G02: 'Balan',     G03: 'Elyan',     G04: 'Nimue',
}

// NATO phonetic / aircraft callsigns extended to cover surge/campaign fleet
export const ASSET_CALLSIGNS_NATO: Record<string, string> = {
  // Blue — A through R (B01–B18), then aircraft names (B19–B24)
  B01: 'Alpha',    B02: 'Bravo',    B03: 'Charlie',  B04: 'Delta',    B05: 'Echo',
  B06: 'Foxtrot',  B07: 'Golf',     B08: 'Hotel',    B09: 'India',    B10: 'Juliet',
  B11: 'Kilo',     B12: 'Lima',     B13: 'Mike',     B14: 'November', B15: 'Oscar',
  B16: 'Papa',     B17: 'Quebec',   B18: 'Romeo',
  B19: 'Lancer',   B20: 'Viper',    B21: 'Raptor',   B22: 'Typhoon',  B23: 'Hornet',
  B24: 'Phantom',
  // Red — S through Z + Niner (R01–R09), then callsigns (R10–R12)
  R01: 'Sierra',   R02: 'Tango',    R03: 'Uniform',  R04: 'Victor',   R05: 'Whiskey',
  R06: 'X-ray',    R07: 'Yankee',   R08: 'Zulu',     R09: 'Niner',
  R10: 'Ranger',   R11: 'Spartan',  R12: 'Nomad',
  // Green — extended specialist class (G01–G04)
  G01: 'Jade',     G02: 'Ember',    G03: 'Onyx',     G04: 'Flint',
}

export function createInitialAssets(complexity: Complexity): Asset[] {
  const assets: Asset[] = []
  for (const [type, count] of FLEET[complexity]) {
    for (let i = 1; i <= count; i++) {
      const id = `${type[0]}${String(i).padStart(2, '0')}`
      assets.push({
        id,
        type,
        status: 'available',
        currentMissionId: null,
        currentTaskId: null,
        position: { ...HUB },
        travelFrom: { ...HUB },
        targetPosition: { ...HUB },
        travelStartElapsed: 0,
        travelEndElapsed: 0,
        availableAt: 0,
        failedAt: null,
      })
    }
  }
  return assets
}

// ─── Travel time helpers ──────────────────────────────────────────────────

export function travelTime(
  from: { x: number; y: number },
  to: { x: number; y: number },
  speed: number,
): number {
  return dist(from, to) / speed
}

/**
 * Computes travel time hub → waypoint for the slowest asset type in a composition.
 * The task can only begin when ALL required assets have arrived.
 */
export function taskTravelTime(
  waypoint: { x: number; y: number },
  composition: TaskComposition,
): number {
  let maxTravel = 0
  for (const [type, count] of Object.entries(composition) as [AssetType, number][]) {
    if (count > 0) {
      const t = dist(HUB, waypoint) / ASSET_SPEED[type]
      if (t > maxTravel) maxTravel = t
    }
  }
  return maxTravel
}
