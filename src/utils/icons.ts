import droneBlue  from '../../icons/drone-blue.svg'
import droneRed   from '../../icons/drone-red.svg'
import droneGreen from '../../icons/drone-green.svg'
import catA from '../../icons/mission-cat-a.svg'
import catB from '../../icons/mission-cat-b.svg'
import catC from '../../icons/mission-cat-c.svg'
import catD from '../../icons/mission-cat-d.svg'
import catE from '../../icons/mission-cat-e.svg'
import taskT1 from '../../icons/task-t1-recce.svg'
import taskT2 from '../../icons/task-t2-minor-drop.svg'
import taskT3 from '../../icons/task-t3-major-drop.svg'
import taskT4 from '../../icons/task-t4-area-recon.svg'
import taskT5 from '../../icons/task-t5-search-triage.svg'
import type { AssetType, MissionCategory } from '../types'

export const DRONE_ICON: Record<AssetType, string> = {
  Blue:  droneBlue,
  Red:   droneRed,
  Green: droneGreen,
}

export const CAT_ICON: Record<MissionCategory, string> = {
  A: catA, B: catB, C: catC, D: catD, E: catE,
}

export const TASK_ICON: Record<number, string> = {
  1: taskT1, 2: taskT2, 3: taskT3, 4: taskT4, 5: taskT5,
}
