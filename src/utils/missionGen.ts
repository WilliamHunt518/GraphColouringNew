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
  1: 15,
  2: 30,
  3: 45,
  4: 30,
  5: 45,
}

// ─── Asset requirements ───────────────────────────────────────────────────

export interface TaskComposition {
  Blue: number
  Red: number
  Green: number
}

/**
 * Primary and substitute compositions per task type.
 * T1 and T5 have no substitute.
 */
export const TASK_PRIMARY: Record<TaskType, TaskComposition> = {
  1: { Blue: 1, Red: 0, Green: 0 },
  2: { Blue: 1, Red: 1, Green: 0 },
  3: { Blue: 1, Red: 2, Green: 0 },
  4: { Blue: 3, Red: 0, Green: 1 },
  5: { Blue: 0, Red: 1, Green: 1 },
}

/** Substitute composition (null = no substitute exists) */
export const TASK_SUBSTITUTE: Record<TaskType, TaskComposition | null> = {
  1: null,
  2: { Blue: 3, Red: 0, Green: 0 },
  3: { Blue: 3, Red: 1, Green: 0 },
  4: { Blue: 8, Red: 0, Green: 0 },
  5: null,
}

/** Base time multiplier when using substitute composition */
export const TASK_SUB_BASE_TIME: Record<TaskType, number> = {
  1: 15,   // unused (no sub)
  2: 45,
  3: 60,
  4: 65,
  5: 45,   // unused (no sub)
}

// ─── Complexity parameters ────────────────────────────────────────────────

// Mean inter-arrival time (seconds). Scales inversely with fleet so load-per-drone stays constant.
const LAMBDA: Record<Complexity, number> = {
  standard:  60,
  surge:     45,   // 1.33× fleet → 1.33× missions
  precision: 90,   // 0.67× fleet → 0.67× missions
  campaign:  50,   // large fleet, slower due to mission complexity
}

// Category probability weights [A, B, C, D, E].
// standard/surge: lighter mix (more small allocations per session)
// precision/campaign: heavier mix (each allocation is a bigger decision)
const CATEGORY_WEIGHTS: Record<Complexity, number[]> = {
  standard:  [25, 35, 25, 12,  3],
  surge:     [40, 35, 17,  7,  1],
  precision: [ 5, 20, 30, 30, 15],
  campaign:  [ 5, 20, 28, 30, 17],
}

const CATEGORIES: MissionCategory[] = ['A', 'B', 'C', 'D', 'E']

// ─── Task composition per mission category ────────────────────────────────

function buildTaskList(rng: SeededRNG, category: MissionCategory): TaskType[] {
  switch (category) {
    case 'A': {
      const t1 = rng.randInt(3, 5)  // 3 or 4
      const t2 = rng.randInt(2, 4)  // 2 or 3
      return [...Array<TaskType>(t1).fill(1), ...Array<TaskType>(t2).fill(2), 3]
    }
    case 'B':
      return rng.randFloat(0, 1) < 0.5
        ? [5, 4, 3, 3, 2, 2, 1, 1]   // with specialist tasks (needs Green)
        : [3, 3, 2, 2, 2, 1, 1, 1]   // logistics-only (no Green required)
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
  duration = 600,
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
    const taskTypes = buildTaskList(rng, category)
    // Only check against the last 5 zone centres — earlier missions will have completed
    // and their map space is available again.
    const zoneCenter = placeZone(rng, usedCenters.slice(-5))
    usedCenters.push(zoneCenter)

    const waypoints = taskTypes.map(() =>
      sampleInCircle(rng, zoneCenter.x, zoneCenter.y, ZONE_RADIUS),
    )

    blueprints.push({
      id: `M${String(++seq).padStart(3, '0')}`,
      arrivalTime: time,
      category,
      taskTypes,
      zoneCenter,
      waypoints,
    })
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
      })
    }
  }
  return assets
}

// Tactical mode: large unconstrained pool so reserve is never the limiting factor.
// 30B/15R/6G covers any conceivable concurrent task combination with slack.
const TACTICAL_FLEET: [AssetType, number][] = [['Blue', 30], ['Red', 15], ['Green', 6]]

export function createTacticalAssets(): Asset[] {
  const assets: Asset[] = []
  for (const [type, count] of TACTICAL_FLEET) {
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
