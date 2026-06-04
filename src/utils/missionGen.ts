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
  2: 15,   // T2 Recon
  3: 25,   // T3 Supply Drop
  4: 30,   // T4 Precision Supply Drop
  5: 45,   // T5 Search and Service
}

// ─── Asset requirements ───────────────────────────────────────────────────

export interface TaskComposition {
  Blue: number
  Red: number
  Green: number
}

/**
 * Primary compositions — paired drones (2X) where meaningful.
 * Blue = fast fixed-wing (recce/recon). Red = rotary supply. Green = slow specialist.
 *
 * T3 Supply Drop: two Reds brute-force carry, Green guides — sub drops one Red (2R→1R).
 * T4 Precision Drop: one Red carries carefully, two Greens guide — sub drops one Green (2G→1G).
 * Substitutes always use the same types as primary, just one fewer of the paired type, ~2.5× time.
 * T5 has no substitute — Search and Service requires the full team.
 */
export const TASK_PRIMARY: Record<TaskType, TaskComposition> = {
  1: { Blue: 1, Red: 0, Green: 0 },   // T1 Recce: solo fixed-wing pass
  2: { Blue: 2, Red: 0, Green: 0 },   // T2 Recon: paired fast sweep
  3: { Blue: 0, Red: 2, Green: 1 },   // T3 Supply Drop: two Reds carry, Green guides
  4: { Blue: 0, Red: 1, Green: 2 },   // T4 Precision Supply Drop: Red carries, two Greens place
  5: { Blue: 1, Red: 1, Green: 1 },   // T5 Search and Service: full mixed team
}

/** Substitutes use the same drone types but one fewer of the paired type (2→1), ~2.5× base time. */
export const TASK_SUBSTITUTE: Record<TaskType, TaskComposition | null> = {
  1: null,
  2: { Blue: 1, Red: 0, Green: 0 },   // T2 sub: 1 Blue solo (2B→1B)
  3: { Blue: 0, Red: 1, Green: 1 },   // T3 sub: 1 Red + Green (2R→1R)
  4: { Blue: 0, Red: 1, Green: 1 },   // T4 sub: Red + 1 Green (2G→1G)
  5: null,                             // T5: no substitute — full team required
}

/** Base time when using substitute composition — approximately 2.5× primary time */
export const TASK_SUB_BASE_TIME: Record<TaskType, number> = {
  1: 10,
  2: 38,
  3: 62,
  4: 75,
  5: 45,   // unused (T5 has no sub), kept for type completeness
}

// ─── Session duration ─────────────────────────────────────────────────────

export const SESSION_DURATION_BY_COMPLEXITY: Record<Complexity, number> = {
  balanced:  600,
  strategic: 600,
  tactical:  600,
  full:      600,
  quick:     600,
}

// ─── Complexity parameters ────────────────────────────────────────────────

// Mean inter-arrival time (seconds).
// tactical: slow arrivals (few decisions), large missions per arrival
// strategic: fast arrivals (many decisions), small missions per arrival
// full: moderate arrivals but large missions — maximum pressure
const LAMBDA: Record<Complexity, number> = {
  balanced:  65,
  strategic: 38,   // high strategic: frequent arrivals → constant reserve decisions
  tactical:  90,   // low strategic: infrequent arrivals → fewer allocation decisions
  full:      50,   // high on both axes: frequent and large
  quick:     42,
}

// Category probability weights [A, B, C, D, E].
// tactical:  mostly D/E — within-mission planning is the challenge
// strategic: mostly A/B — reserve allocation frequency is the challenge
// full:      mostly C/D/E — both axes demanding
const CATEGORY_WEIGHTS: Record<Complexity, number[]> = {
  balanced:  [20, 30, 28, 17,  5],
  strategic: [40, 38, 16,  5,  1],  // low tactical: simple missions, lots of them
  tactical:  [ 5, 13, 28, 38, 16],  // high tactical: complex missions, fewer of them
  full:      [ 5, 15, 28, 32, 20],  // high on both axes
  quick:     [35, 30, 20, 12,  3],
}

const CATEGORIES: MissionCategory[] = ['A', 'B', 'C', 'D', 'E']

// ─── Task composition per mission category ────────────────────────────────

// Task type demands: T1=1B  T2=2B  T3=2R+1G  T4=1R+2G  T5=1B+1R+1G
//
// Archetypes weight toward one drone type per mission, breaking the old
// always-equal demand pattern. Over many missions the aggregate demand is
// approximately Blue > Red > Green, matching fleet composition.
//
// Archetype probabilities [blue, red, green, mixed] = [35, 28, 22, 15]
// Avg per category:  A≈1.7B/1.6R/1.4G  B≈2.6B/2.3R/2.0G  C≈3.5B/2.8R/2.7G
//                    D≈4.1B/4.2R/3.7G   E≈5.3B/4.9R/4.5G

function buildTaskList(rng: SeededRNG, category: MissionCategory, complexity: Complexity): TaskType[] {
  if (complexity === 'quick') {
    switch (category) {
      case 'A': return rng.randFloat(0, 1) < 0.5 ? [2, 3] : [1, 3]
      case 'B': return [1, 2, 3, 4]
      case 'C': return [1, 2, 3, 4, 5]
      case 'D': return [1, 2, 3, 4, 5, 5]
      case 'E': return [1, 1, 2, 3, 4, 5]
    }
  }

  const archetype = rng.weightedChoice(
    ['blue', 'red', 'green', 'mixed'],
    [35, 28, 22, 15],
  )

  switch (category) {
    case 'A':   // 2 tasks
      if (archetype === 'blue')  return [1, 2]           // 3B
      if (archetype === 'red')   return [3, 5]           // 1B+3R+2G
      if (archetype === 'green') return [4, 5]           // 1B+2R+3G
      return [1, 3]                                      // 1B+2R+1G

    case 'B':   // 3 tasks
      if (archetype === 'blue')  return [1, 2, 2]        // 5B
      if (archetype === 'red')   return [3, 3, 5]        // 1B+5R+3G
      if (archetype === 'green') return [1, 4, 4]        // 1B+2R+4G
      return [1, 3, 5]                                   // 2B+3R+2G

    case 'C':   // 4 tasks
      if (archetype === 'blue')  return [1, 1, 2, 2]     // 6B
      if (archetype === 'red')   return [3, 3, 5, 5]     // 2B+6R+4G
      if (archetype === 'green') return [1, 4, 4, 4]     // 1B+3R+6G
      return [1, 2, 3, 5]                                // 4B+3R+2G

    case 'D':   // 5 tasks
      if (archetype === 'blue')  return [1, 1, 2, 2, 5]  // 7B+1R+1G
      if (archetype === 'red')   return [3, 3, 3, 5, 5]  // 2B+8R+5G
      if (archetype === 'green') return [1, 4, 4, 4, 5]  // 2B+4R+7G
      return [1, 2, 3, 3, 5]                             // 4B+5R+3G

    case 'E':   // 6 tasks
      if (archetype === 'blue')  return [1, 1, 2, 2, 2, 5]   // 9B+1R+1G
      if (archetype === 'red')   return [3, 3, 3, 5, 5, 5]   // 3B+9R+6G
      if (archetype === 'green') return [4, 4, 4, 1, 5, 5]   // 3B+5R+8G
      return [1, 2, 3, 3, 4, 5]                              // 4B+6R+5G
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
      droneFailureTimes: [],
    })
  }

  // Schedule multiple drone failures per mission.
  // Each mission gets FAILURE_COUNT failure events staggered over time so that
  // redundancy planning (extra drones in the allocation) is essential.
  const FAILURE_COUNT = 2   // failures per mission; raise to 3 for higher pressure
  const FAILURE_GAP   = 60  // minimum seconds between successive failures
  const FAILURE_JITTER = 30 // random jitter added to each failure time

  for (let i = 0; i < blueprints.length; i++) {
    const times: number[] = []
    for (let f = 0; f < FAILURE_COUNT; f++) {
      // Failure 1 ≈ 30–60s, failure 2 ≈ 90–120s, etc.
      times.push(30 + f * FAILURE_GAP + rng.randFloat(0, FAILURE_JITTER))
    }
    blueprints[i] = { ...blueprints[i], willFail: true, droneFailureTimes: times }
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

// Fleet is slightly Blue-heavy to match average demand: Blue returns fastest (9 u/s) so each Blue
// covers more missions per hour, meaning you need marginally more of them per unit of total demand.
// Ratio is small — 10/9/8 keeps utilisation rates nearly equal across all three types.
const FLEET: Record<Complexity, [AssetType, number][]> = {
  balanced:  [['Blue', 10], ['Red',  9],  ['Green', 8]],   // ~27 total
  strategic: [['Blue',  9], ['Red',  8],  ['Green', 7]],   // ~24 — smaller fleet, small missions
  tactical:  [['Blue', 10], ['Red',  9],  ['Green', 8]],   // ~27 — same size, large missions
  full:      [['Blue', 12], ['Red', 11],  ['Green', 10]],  // ~33 — stretched by volume + size
  quick:     [['Blue',  5], ['Red',  5],  ['Green',  5]],
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
  // Green — specialist thermal/precision drones (Arthurian figures, G01–G10)
  G01: 'Balin',     G02: 'Balan',     G03: 'Elyan',     G04: 'Nimue',
  G05: 'Merlin',    G06: 'Morgana',   G07: 'Lynette',   G08: 'Elaine',
  G09: 'Enid',      G10: 'Luned',
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
  // Green — specialist class (G01–G10)
  G01: 'Jade',     G02: 'Ember',    G03: 'Onyx',     G04: 'Flint',
  G05: 'Kilo',     G06: 'Lima',     G07: 'Mike',     G08: 'November',
  G09: 'Oscar',    G10: 'Papa',
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
        replacementAt: null,
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
