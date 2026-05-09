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

const LAMBDA: Record<Complexity, number> = {
  easy:   90,   // ~1 per 90s
  medium: 45,   // ~1 per 45s
  hard:   30,   // ~1 per 30s
}

const CATEGORY_WEIGHTS: Record<Complexity, number[]> = {
  easy:   [50, 35, 10,  5,  0],
  medium: [15, 35, 35, 12,  3],
  hard:   [ 5, 15, 35, 30, 15],
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
  for (let attempt = 0; attempt < 60; attempt++) {
    const x = rng.randFloat(margin, MAP_W - margin)
    const y = rng.randFloat(margin, MAP_H - margin)
    const pt = { x, y }
    if (dist(pt, HUB) < ZONE_MIN_HUB) continue
    if (existing.some(z => dist(pt, z) < ZONE_MIN_ZONE)) continue
    return pt
  }
  // Fallback: place at a valid angle from hub ignoring zone conflicts
  const angle = rng.randFloat(0, Math.PI * 2)
  const r = ZONE_MIN_HUB + rng.randFloat(30, 180)
  return {
    x: Math.min(MAP_W - margin, Math.max(margin, HUB.x + Math.cos(angle) * r)),
    y: Math.min(MAP_H - margin, Math.max(margin, HUB.y + Math.sin(angle) * r)),
  }
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
    const zoneCenter = placeZone(rng, usedCenters)
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

// ─── Asset pool ───────────────────────────────────────────────────────────

const POOL: [AssetType, number][] = [
  ['Blue', 18],
  ['Red', 9],
  ['Green', 3],
]

export function createInitialAssets(): Asset[] {
  const assets: Asset[] = []
  for (const [type, count] of POOL) {
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
