import type { Asset, AssetType, MissionBlueprint, MissionCategory, TaskType, Complexity } from '../types'
import type { SeededRNG } from './prng'

// ─── Map constants ────────────────────────────────────────────────────────

// World is ~16:9 so it nearly matches typical monitors — the strategic map fills the window
// (cover/slice), and a near-matching aspect keeps edge-cropping minimal.
export const MAP_W = 1400
export const MAP_H = 800
export const HUB = { x: MAP_W / 2, y: MAP_H / 2 } as const
export const ZONE_RADIUS = 90   // spread of waypoints within a zone
const ZONE_MIN_HUB = 120        // ~20% closer to hub — makes asset choice matter more
const ZONE_MIN_ZONE = 200   // minimum distance between zone centers
// Keep zone CENTERS this far from the map edges. Combined with the wide world aspect, this
// keeps whole mission circles inside the cropped viewport on typical monitors.
export const ZONE_EDGE_MARGIN = 180

// ─── Physics ──────────────────────────────────────────────────────────────

export const ASSET_SPEED: Record<AssetType, number> = {
  Blue: 11.0,
  Red: 10.0,
  Green: 9.0,
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

/**
 * Sections-by-colour: fraction of task baseTime each drone type must remain present until.
 * A drone failing AFTER its deadline is a graceful exit (section complete, task continues).
 * A drone failing BEFORE its deadline triggers the normal recovery flow.
 * Types with deadline < 1.0 can gracefully exit; deadline = 1.0 types are needed throughout.
 */
export const TASK_SECTION_DEADLINES: Record<number, Partial<Record<string, number>>> = {
  1: { Blue: 1.0 },                           // T1 (1B Recce): solo pass, Blue throughout
  2: { Blue: 1.0 },                           // T2 (2B Recon): paired sweep, both Blues throughout
  3: { Red: 0.5, Green: 1.0 },               // T3 (2R+1G Supply): Reds deliver first half, Green guides full
  4: { Red: 0.5, Green: 1.0 },               // T4 (1R+2G Precision): Red carries first half, Greens place full
  5: { Blue: 0.33, Red: 0.67, Green: 1.0 }, // T5 (1B+1R+1G S&S): Blue searches, Red supplies, Green extracts
}

// ─── Session duration ─────────────────────────────────────────────────────

export const SESSION_DURATION_BY_COMPLEXITY: Record<Complexity, number> = {
  balanced:  480,
  strategic: 480,
  tactical:  480,
  full:      480,
  quick:     480,
}

// ─── Complexity parameters ────────────────────────────────────────────────

// Mean inter-arrival time (seconds).
// tactical: slow arrivals (few decisions), large missions per arrival
// strategic: fast arrivals (many decisions), small missions per arrival
// full: moderate arrivals but large missions — maximum pressure
export const LAMBDA: Record<Complexity, number> = {
  balanced:  62,
  strategic: 37,   // high strategic: frequent arrivals → constant reserve decisions
  tactical:  75,   // low strategic: infrequent (but larger) arrivals; tuned so total load ≈ strategic
  full:      48,   // high on both axes: frequent and large
  quick:     42,
}

// Category probability weights [A, B, C, D, E].
// tactical:  mostly D/E — within-mission planning is the challenge
// strategic: mostly A/B — reserve allocation frequency is the challenge
// full:      mostly C/D/E — both axes demanding
export const CATEGORY_WEIGHTS: Record<Complexity, number[]> = {
  balanced:  [20, 30, 28, 17,  5],
  strategic: [40, 38, 16,  5,  1],  // low tactical: simple missions, lots of them
  tactical:  [ 5, 13, 28, 38, 16],  // high tactical: complex missions, fewer of them
  full:      [ 5, 15, 28, 32, 20],  // high on both axes
  quick:     [35, 30, 20, 12,  3],
}

export const CATEGORIES: MissionCategory[] = ['A', 'B', 'C', 'D', 'E']

// ─── Task composition per mission category ────────────────────────────────

// Task type demands: T1=1B  T2=2B  T3=2R+1G  T4=1R+2G  T5=1B+1R+1G
//
// Archetypes weight each mission toward one drone type. The weights below are tuned (v2, see
// docs/SCENARIOS.md) so that aggregate drone-seconds of demand are ~EQUAL across Blue/Red/Green
// against the uniform 11/11/11 fleet — per-colour utilisation spread ≤ ~2 pts in every scenario
// (verify with `npx tsx sim/demand.mts`). The blue weight is raised because Blue is otherwise the
// slackest colour once the compressed speed spread (11/10/9) removes Green's travel penalty.
//
// Archetype probabilities [blue, red, green, mixed] = [38, 26, 21, 15]

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
    [38, 26, 21, 15],
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
  const margin = Math.max(ZONE_RADIUS + 10, ZONE_EDGE_MARGIN)
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
  // Last resort: scan a fine polar grid. A non-overlapping spot (clearance ≥ noOverlapMin) always
  // wins when one exists. When the map is genuinely saturated and we must overlap, prefer overlapping
  // the earliest-arriving zone (lowest index in `existing` — most likely already completed by the
  // time this later mission spawns) rather than a recent/active one.
  const ANGLES = 144
  type Cand = { pt: { x: number; y: number }; overlapping: boolean; clearance: number; earliestConflict: number }
  let best: Cand | null = null
  const isBetter = (c: Cand, b: Cand | null): boolean => {
    if (!b) return true
    if (c.overlapping !== b.overlapping) return !c.overlapping           // non-overlapping wins
    if (!c.overlapping) return c.clearance > b.clearance                 // both clear: more room
    if (c.earliestConflict !== b.earliestConflict)                       // both overlap: prefer older
      return c.earliestConflict < b.earliestConflict
    return c.clearance > b.clearance
  }
  for (let a = 0; a < ANGLES; a++) {
    const angle = (a / ANGLES) * Math.PI * 2
    for (let rr = ZONE_MIN_HUB; rr <= 380; rr += 15) {
      const pt = {
        x: Math.min(MAP_W - margin, Math.max(margin, HUB.x + Math.cos(angle) * rr)),
        y: Math.min(MAP_H - margin, Math.max(margin, HUB.y + Math.sin(angle) * rr)),
      }
      let clearance = noOverlapMin, earliestConflict = Infinity
      if (existing.length > 0) {
        clearance = Infinity
        for (let idx = 0; idx < existing.length; idx++) {
          const d = dist(pt, existing[idx])
          if (d < clearance) clearance = d
          if (d < noOverlapMin && idx < earliestConflict) earliestConflict = idx
        }
      }
      const cand: Cand = { pt, overlapping: earliestConflict !== Infinity, clearance, earliestConflict }
      if (isBetter(cand, best)) best = cand
    }
  }
  return best ? best.pt : { x: HUB.x, y: HUB.y - ZONE_MIN_HUB - 30 }
}

// ─── Session plan generator ───────────────────────────────────────────────

/**
 * Pre-generates the complete mission schedule for a 480-second (8-minute) session.
 * All randomness drawn from the provided SeededRNG so the session is
 * fully reproducible from the seed alone.
 */
export function generateSessionPlan(
  rng: SeededRNG,
  complexity: Complexity,
  duration = SESSION_DURATION_BY_COMPLEXITY[complexity],
  seedCenters: Array<{ x: number; y: number }> = [],
): MissionBlueprint[] {
  const lambda = LAMBDA[complexity]
  const blueprints: MissionBlueprint[] = []
  // Seed the keep-out with any pre-placed zone centres (e.g. fixed tutorial missions) so generated
  // zones never land on top of them.
  const usedCenters: Array<{ x: number; y: number }> = [...seedCenters]
  let time = 0
  let seq = 0

  while (true) {
    const interval = rng.exponential(lambda)
    // Guarantee ≥3 missions in the first 2 minutes
    const n = blueprints.length
    const cappedInterval = n === 0 ? Math.min(interval, 3) : n <= 2 ? Math.min(interval, 60) : interval
    time += cappedInterval
    if (time > duration - 60) break

    const category = rng.weightedChoice(CATEGORIES, CATEGORY_WEIGHTS[complexity])
    const taskTypes = buildTaskList(rng, category, complexity)
    // Check against every zone centre placed so far (finished zones stay drawn on the map, so
    // they remain part of the keep-out) to avoid visual overlap.
    const zoneCenter = placeZone(rng, usedCenters)
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
    })
  }

  // Drone failures are no longer scheduled per mission at generation time — see
  // FAILURE_RATE_PER_DRONE_SECOND below; the live per-tick hazard in gameReducer.ts TICK
  // handles them uniformly across every deployed drone regardless of which mission it's on.

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

/**
 * Completion reward per completed task (×10 vs legacy to give penalties room to bite; study-v1.3
 * doubled it again — ×20 vs legacy — for friendlier scores. Penalty accrual is charged as a RATIO
 * of TASK_WEIGHT[type]/totalWeight (see computePenaltyAccrued), so scaling every entry by the same
 * factor leaves penalty-per-second untouched: only completion points, and therefore score
 * headroom, actually doubled. Difficulty/pacing is unaffected.
 */
export const TASK_WEIGHT: Record<TaskType, number> = { 1: 20, 2: 40, 3: 60, 4: 80, 5: 100 }

/** Penalty is charged at this interval (seconds); each charge = CATEGORY_PENALTY_RATE × CHARGE_INTERVAL. */
export const CHARGE_INTERVAL = 15

// ─── Drone failure hazard rate (study-v1.3) ────────────────────────────────

/**
 * Chance per second that any single currently-deployed drone fails, checked live every tick
 * (gameReducer.ts TICK step 1b) rather than precomputed per mission — so total failures scale
 * with actual drone-seconds deployed (utilisation), uniformly across type and mission, instead of
 * with mission count or a fixed per-mission schedule. Replaces the old
 * FAILURE_COUNT/GAP/JITTER/PROB_CONST scheme (E[1.5] failures/mission), whose selection RNG turned
 * out to be Blue-biased — see docs/STUDY_BUILD.md.
 * Calibrated via `npx tsx sim/engine.mts --seeds=40`: at 1/900 the SMART operator completes 83%
 * of tasks in both study scenarios (strategic 83%, tactical 83%), matching the historical 83-85%
 * target — see docs/STUDY_BUILD.md.
 */
export const FAILURE_RATE_PER_DRONE_SECOND = 1 / 900

// ─── Asset pool ───────────────────────────────────────────────────────────

// Uniform 11/11/11 fleet across every real study scenario — difficulty differences come only
// from the tactical/strategic weighting (mission size via CATEGORY_WEIGHTS + arrival rate via
// LAMBDA), not fleet composition. quick stays small for dev.
// NOTE (v2 tuning, docs/SCENARIOS.md): with the compressed speeds (11/10/9) and balanced archetype
// weights, per-colour demand is equal (fleet needn't be Green-heavy any more), and λ_tactical was
// lowered to 78 so tactical and strategic carry ~equal total load and reach ~equal difficulty
// (SMART operator ~83–85% of missions in both). Re-run sim/demand.mts + sim/engine.mts if any of
// speeds / fleet / LAMBDA / CATEGORY_WEIGHTS / archetype weights change.
export const STUDY_FLEET: [AssetType, number][] = [['Blue', 11], ['Red', 11], ['Green', 11]]
export const FLEET: Record<Complexity, [AssetType, number][]> = {
  balanced:  STUDY_FLEET,
  strategic: STUDY_FLEET,
  tactical:  STUDY_FLEET,
  full:      STUDY_FLEET,
  quick:     [['Blue', 5], ['Red', 5], ['Green', 5]],
}

// Smaller fleet for the tutorial — easier to count and reason about while learning the reserve.
export const TUTORIAL_FLEET: [AssetType, number][] = [['Blue', 6], ['Red', 6], ['Green', 6]]

// Simple functional naming: refer to drone types by what they do, not their colour
// (still coloured blue/red/green in the UI). Individual drone IDs (e.g. "B07") display
// as "Fast-7" / "Lifter-7" / "Camera-7".
export const ASSET_TYPE_LABEL: Record<AssetType, string> = { Blue: 'Fast', Red: 'Lifter', Green: 'Camera' }
const DRONE_ID_PREFIX_LABEL: Record<string, string> = { B: 'Fast', R: 'Lifter', G: 'Camera' }

export function droneLabel(assetId: string): string {
  const prefix = DRONE_ID_PREFIX_LABEL[assetId[0]]
  if (!prefix) return assetId
  return `${prefix}-${parseInt(assetId.slice(1), 10)}`
}

export function createInitialAssets(complexity: Complexity, fleetOverride?: [AssetType, number][]): Asset[] {
  const assets: Asset[] = []
  for (const [type, count] of fleetOverride ?? FLEET[complexity]) {
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
