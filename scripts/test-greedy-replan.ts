// Focused test for the parallel-greedy replan policy.
// Run: npx tsx scripts/test-greedy-replan.ts
import { applyGreedyReplan } from '../src/store/gameReducer'
import type { GameState, Task, Asset } from '../src/types'

let failures = 0
const check = (label: string, cond: boolean) => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}`)
  if (!cond) failures++
}

function task(id: string, type: number): Task {
  return {
    id, missionId: 'M1', type, status: 'pending',
    assignedAssetIds: [], waypoint: { x: 700, y: 400 },
    allocatedAt: null, travelTime: 0, baseTime: 0, useSubstitute: false,
    startTime: null, completionTime: null, recallDelay: 0,
  } as unknown as Task
}

function drone(id: string, type: 'Blue' | 'Red' | 'Green'): Asset {
  return {
    id, type, status: 'deployed',
    currentMissionId: 'M1', currentTaskId: null,
    position: { x: 780, y: 400 },   // loitering on the zone edge
  } as unknown as Asset
}

// 4 pending tasks: T5 (1B1R1G), T3 (2R1G), T1 (1B), T1 (1B).
// Pool: 3 Blue, 3 Red, 2 Green = exactly enough to cover all four in parallel.
const tasks = [task('M1-T5', 5), task('M1-T3', 3), task('M1-T1a', 1), task('M1-T1b', 1)]
const assets = [
  drone('B1', 'Blue'), drone('B2', 'Blue'), drone('B3', 'Blue'),
  drone('R1', 'Red'), drone('R2', 'Red'), drone('R3', 'Red'),
  drone('G1', 'Green'), drone('G2', 'Green'),
]

const state = {
  missions: [{ id: 'M1', status: 'active', tasks, tacticallySuppressedTaskId: null, droneSequences: {} }],
  assets,
} as unknown as GameState

const out = applyGreedyReplan(state, 100)
const m = out.missions[0]

const traveling = m.tasks.filter(t => t.status === 'traveling')
check('all 4 tasks dispatched in parallel', traveling.length === 4)

const engaged = out.assets.filter(a => a.currentTaskId !== null)
check('all 8 drones engaged (none idle)', engaged.length === 8)

// consume-once: no drone assigned to two tasks
const allAssigned = m.tasks.flatMap(t => t.assignedAssetIds)
check('no drone double-assigned', new Set(allAssigned).size === allAssigned.length)

// each task got a comp that satisfies its primary requirement
const typeOf = (id: string) => assets.find(a => a.id === id)!.type
const comp = (ids: string[]) => ({
  Blue: ids.filter(i => typeOf(i) === 'Blue').length,
  Red: ids.filter(i => typeOf(i) === 'Red').length,
  Green: ids.filter(i => typeOf(i) === 'Green').length,
})
const t5 = comp(m.tasks.find(t => t.id === 'M1-T5')!.assignedAssetIds)
const t3 = comp(m.tasks.find(t => t.id === 'M1-T3')!.assignedAssetIds)
check('T5 covered 1B/1R/1G', t5.Blue >= 1 && t5.Red >= 1 && t5.Green >= 1)
check('T3 covered 2R/1G', t3.Red >= 2 && t3.Green >= 1)

// ── Constrained pool: only 1B/1R/1G — should cover ONLY T5, leave the rest pending,
//    and still leave NO drone idle (all 3 consumed by T5). ──
const tasks2 = [task('M1-T5', 5), task('M1-T3', 3), task('M1-T1a', 1)]
const assets2 = [drone('B1', 'Blue'), drone('R1', 'Red'), drone('G1', 'Green')]
const state2 = {
  missions: [{ id: 'M1', status: 'active', tasks: tasks2, tacticallySuppressedTaskId: null, droneSequences: {} }],
  assets: assets2,
} as unknown as GameState
const out2 = applyGreedyReplan(state2, 100)
const m2 = out2.missions[0]
check('constrained: only the coverable task dispatched', m2.tasks.filter(t => t.status === 'traveling').length === 1)
check('constrained: no drone left idle', out2.assets.every(a => a.currentTaskId !== null))

console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILED`)
process.exit(failures === 0 ? 0 : 1)
