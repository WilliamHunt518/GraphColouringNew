import type { GameState } from '../types'

// First tactical-window step index (steps ≥ this are shown in TacticalTutorial)
export const TACTICAL_STEP_FIRST = 24
export const TACTICAL_STEP_LAST  = 33

export interface TutorialStep {
  id: string
  title: string
  body: string[]
  highlight?: string         // data-tutorial selector
  cardSide?: 'right' | 'left' | 'bottom' | 'top' | 'center'
  allowClickThrough?: boolean
  /** No Next button — user MUST perform the action; autoAdvanceWhen fires */
  mustInteract?: boolean
  /** Show a "Try it" hint but keep Next button */
  tryIt?: boolean
  autoAdvanceWhen?: (state: GameState) => boolean
  spotlightPadding?: number
  /** Rendered in TacticalTutorial (map window), not primary Tutorial */
  inMapWindow?: boolean
}

export const TUTORIAL_STEPS: TutorialStep[] = [

  // ── 0. Welcome ─────────────────────────────────────────────────────────────
  {
    id: 'welcome',
    title: 'Welcome to SAR Command',
    body: [
      'You are the operator of a search-and-rescue drone fleet. When distress signals are detected, missions arrive and it is your job to allocate drone teams to respond.',
      'This tutorial walks you through every part of the interface step by step. Click Next to proceed at your own pace, or Skip to go straight to the real session.',
    ],
    cardSide: 'center',
  },

  // ── 1. Session & score ──────────────────────────────────────────────────────
  {
    id: 'session-score',
    title: 'Sessions & Scoring',
    body: [
      'Each session lasts 10 minutes. When it ends you will answer a short survey before the next one begins.',
      'Your goal is to maximise your score. Points are earned by completing mission tasks. Waiting too long costs penalty points — so speed matters.',
    ],
    cardSide: 'center',
  },

  // ── 2. Header ───────────────────────────────────────────────────────────────
  {
    id: 'header',
    title: 'The Header Bar',
    body: [
      'The header gives you a constant at-a-glance view of the session state. Let\'s step through its parts.',
    ],
    highlight: 'header',
    cardSide: 'bottom',
  },

  // ── 3. Timer ────────────────────────────────────────────────────────────────
  {
    id: 'timer',
    title: 'Session Timer',
    body: [
      'The amber countdown shows time remaining in the session. When it reaches zero the session ends and a brief survey appears.',
      'Any mission not completed by the end of the session will not score further points, so time pressure is real.',
    ],
    highlight: 'timer',
    cardSide: 'bottom',
  },

  // ── 4. Score ────────────────────────────────────────────────────────────────
  {
    id: 'score',
    title: 'Your Score',
    body: [
      'Your live score is shown here. The green number shows completion points earned from finished tasks. The red number shows accumulated wait penalty.',
      'Score = completion points − penalty. Complete tasks quickly to keep that gap wide.',
    ],
    highlight: 'score',
    cardSide: 'bottom',
  },

  // ── 5. Reserve strip ────────────────────────────────────────────────────────
  {
    id: 'reserve',
    title: 'Your Drone Reserve',
    body: [
      'This strip shows how many drones are available at the hub. The bold number is ready to deploy; smaller text shows how many are deployed on missions or flying back.',
      'Watch your reserve — if it runs low you cannot respond to new missions quickly.',
    ],
    highlight: 'reserve-strip',
    cardSide: 'bottom',
    spotlightPadding: 6,
  },

  // ── 6. Drone types ──────────────────────────────────────────────────────────
  {
    id: 'drone-types',
    title: 'Three Drone Types',
    body: [
      'Blue drones are fastest (9 units/s) and handle reconnaissance tasks.',
      'Red drones are mid-speed (6 units/s) and handle supply drops and precision deliveries.',
      'Green drones are slowest (4.2 units/s) but carry a thermal camera that some tasks specifically require. Keep an eye on how many you have available.',
    ],
    highlight: 'reserve-strip',
    cardSide: 'bottom',
    spotlightPadding: 6,
  },

  // ── 7. Mission queue ────────────────────────────────────────────────────────
  {
    id: 'mission-queue',
    title: 'The Mission Queue',
    body: [
      'Missions appear here as they arrive during the session. Each is a multi-task rescue operation that needs a drone team assigned to it.',
      'They are grouped by status: Incoming (awaiting allocation), Active (drones deployed), and Completed. Keep Incoming short.',
    ],
    highlight: 'mission-list',
    cardSide: 'right',
    spotlightPadding: 6,
  },

  // ── 8. Mission card ──────────────────────────────────────────────────────────
  {
    id: 'mission-card',
    title: 'Reading a Mission Card',
    body: [
      'Each card shows the mission ID, a category badge (A = Routine through E = Mass Casualty), and task completion status.',
      'Higher-category missions score more points but require more varied drone types. The amber border means it is waiting for drone allocation.',
    ],
    highlight: 'first-mission-card',
    cardSide: 'right',
  },

  // ── 9. Task progress bar ─────────────────────────────────────────────────────
  {
    id: 'task-progress',
    title: 'Task Progress Bar',
    body: [
      'This bar shows each task\'s status. Segment width reflects the task\'s point value.',
      'Gray = pending, blue = drone traveling to task, amber = executing, green = complete. A red border at the top grows with penalty urgency.',
    ],
    highlight: 'first-task-progress',
    cardSide: 'right',
    spotlightPadding: 4,
  },

  // ── 10. Penalty histogram ────────────────────────────────────────────────────
  {
    id: 'penalty',
    title: 'Penalty Histogram',
    body: [
      'The histogram below shows how penalty has accumulated over time. Each bar is a time interval since the mission arrived — taller bars mean faster accrual.',
      'The red number shows total penalty so far. Each task that completes immediately reduces the growth rate.',
    ],
    highlight: 'first-penalty',
    cardSide: 'right',
    spotlightPadding: 4,
  },

  // ── 11. CLICK ALLOCATE (mustInteract) ────────────────────────────────────────
  {
    id: 'allocate',
    title: 'Allocating a Mission',
    body: [
      'When a mission is queued, an amber Allocate button appears on its card. Click it now to open the allocation panel.',
    ],
    highlight: 'first-allocate-btn',
    cardSide: 'right',
    allowClickThrough: true,
    mustInteract: true,
    autoAdvanceWhen: state => state.strategicModal !== null,
    spotlightPadding: 6,
  },

  // ── 12. Panel intro ──────────────────────────────────────────────────────────
  {
    id: 'panel-intro',
    title: 'The Allocation Panel',
    body: [
      'This panel is where you decide which drones to send on the mission. There are two ways to do it: manually, using sliders, or by accepting a suggestion from the Strategic Agent.',
      'We will start with the manual approach so you understand what the agent is doing when we get to that.',
    ],
    highlight: 'first-strategic-panel',
    cardSide: 'right',
  },

  // ── 13. Manual mode introduction ─────────────────────────────────────────────
  {
    id: 'manual-first',
    title: 'Manual Allocation — Try It First',
    body: [
      'Click the "Set manually instead" link at the bottom of the panel to switch to manual mode. This reveals sliders for each drone type.',
    ],
    highlight: 'first-manual-toggle',
    cardSide: 'right',
    allowClickThrough: true,
    tryIt: true,
    spotlightPadding: 6,
  },

  // ── 14. Manual picker ────────────────────────────────────────────────────────
  {
    id: 'manual-picker',
    title: 'Manual Allocation Sliders',
    body: [
      'The ± buttons let you choose exactly how many of each drone type to commit. The number in bold is your current choice; the number after the slash is how many are available.',
      'Try adjusting the numbers. Notice how the ETA preview at the bottom updates in real time as you add or remove drones.',
    ],
    highlight: 'first-manual-picker',
    cardSide: 'right',
  },

  // ── 15. ETA & composition ────────────────────────────────────────────────────
  {
    id: 'eta-preview',
    title: 'ETA & Composition',
    body: [
      'The ETA shows how long all tasks will take given the drones you have chosen. Each task type has specific drone requirements — if you do not meet them, the task cannot execute and the ETA will be infinite.',
      'Manual allocation gives you full control but requires you to know what each task needs. The agent handles this automatically.',
    ],
    highlight: 'first-manual-picker',
    cardSide: 'right',
  },

  // ── 16. Back to agent suggestions ────────────────────────────────────────────
  {
    id: 'back-to-agents',
    title: 'Switching Back to Agent Suggestions',
    body: [
      'Now click "← Back to suggestions" to return to the agent view. This shows you the two pre-computed strategies that the Strategic Agent recommends.',
    ],
    highlight: 'first-manual-toggle',
    cardSide: 'right',
    allowClickThrough: true,
    tryIt: true,
    spotlightPadding: 6,
  },

  // ── 17. Strategy cards overview ──────────────────────────────────────────────
  {
    id: 'strategy-cards',
    title: 'The Strategic Agent',
    body: [
      'The Strategic Agent offers two pre-computed strategies — typically Aggressive (more drones, faster mission) and Conservative (fewer drones, preserves your reserve).',
      'Both were computed to meet the mission\'s task requirements. Compare them and choose the one that fits your current reserve and workload.',
    ],
    highlight: 'first-strategic-panel',
    cardSide: 'right',
  },

  // ── 18. Strategy card details ─────────────────────────────────────────────────
  {
    id: 'strategy-detail',
    title: 'Reading a Strategy Card',
    body: [
      'Each card shows: the drone composition (e.g. 2 Blue, 1 Red, 1 Green), the estimated completion time for all tasks, and how many drones of each type remain in reserve after deployment.',
      'Click a card to select it — a blue ✓ appears. You can change your selection before deploying.',
    ],
    highlight: 'first-strategy-card',
    cardSide: 'right',
  },

  // ── 19. Score bars ────────────────────────────────────────────────────────────
  {
    id: 'score-bars',
    title: 'Strategy Score Bars',
    body: [
      'Three bars summarise each strategy: Speed (mission completion time), Reserve (drones left available), and Resilience (redundancy against failures).',
      'There is no single correct choice — it depends on your situation. The agent\'s suggestions are a starting point, not a guarantee.',
    ],
    highlight: 'first-strategy-card',
    cardSide: 'right',
  },

  // ── 20. DEPLOY (mustInteract) ─────────────────────────────────────────────────
  {
    id: 'deploy',
    title: 'Select a Strategy & Deploy',
    body: [
      'Select one of the strategy cards and then click "Deploy Selected" to commit that drone team. The mission will move to tactical planning.',
    ],
    highlight: 'first-deploy-btn',
    cardSide: 'right',
    allowClickThrough: true,
    mustInteract: true,
    autoAdvanceWhen: state => state.missions.some(m => m.tacticalPending),
    spotlightPadding: 6,
  },

  // ── 21. Tactical pending ──────────────────────────────────────────────────────
  {
    id: 'tactical-pending',
    title: 'Tactical Planning Pending',
    body: [
      'The mission is now waiting for a tactical plan. A drone team has been committed but the drones have not yet departed — you still need to confirm which drone goes to which task.',
      'This is the Tactical Agent\'s job. You can review and modify its plan before the drones leave.',
    ],
    highlight: 'first-tactical-pending',
    cardSide: 'right',
  },

  // ── 22. Map overview ──────────────────────────────────────────────────────────
  {
    id: 'map-overview',
    title: 'The Operational Map',
    body: [
      'The map shows your hub (blue circle), all mission zones (coloured circles), and drone travel routes. Deployed drones animate as they move.',
      'Zone colours: amber = queued, blue = active, grey = complete. You can click a queued zone directly on the map to open its allocation panel.',
    ],
    highlight: 'embedded-map',
    cardSide: 'left',
    spotlightPadding: 6,
  },

  // ── 23. Open tactical ────────────────────────────────────────────────────────
  {
    id: 'open-tactical',
    title: 'Opening the Tactical Planner',
    body: [
      'Click "Tactical →" to open the Tactical Planner in a new window. It is where you confirm or modify the drone-to-task assignment plan.',
      'Once it is open, click Next here — the tutorial will continue inside that window.',
    ],
    highlight: 'tactical-btn',
    cardSide: 'bottom',
    allowClickThrough: true,
    tryIt: true,
    spotlightPadding: 6,
  },

  // ════════════════════ MAP WINDOW STEPS (inMapWindow: true) ════════════════════

  // ── 24. Tactical welcome ──────────────────────────────────────────────────────
  {
    id: 'tac-welcome',
    title: 'The Tactical Planner',
    body: [
      'Welcome. This window is where you plan exactly which drones do which tasks and in what order before the team departs.',
      'The tutorial continues here — use the Back and Next buttons on this card to navigate. The primary window shows a progress indicator.',
    ],
    cardSide: 'center',
    inMapWindow: true,
  },

  // ── 25. Mission queue sidebar ─────────────────────────────────────────────────
  {
    id: 'tac-queue',
    title: 'Mission Queue',
    body: [
      'This left panel lists missions that are waiting for tactical planning (yellow border) or have a drone failure needing recovery (red border).',
      'Click a mission to open its plan in the main area.',
    ],
    highlight: 'tac-mission-list',
    cardSide: 'right',
    inMapWindow: true,
  },

  // ── 26. Select mission ────────────────────────────────────────────────────────
  {
    id: 'tac-select',
    title: 'Select Your Mission',
    body: [
      'Click on the pending mission in the left panel to open its tactical plan. You should see a mission with a yellow border — that is the one you just allocated.',
    ],
    highlight: 'tac-mission-list',
    cardSide: 'right',
    allowClickThrough: true,
    tryIt: true,
    inMapWindow: true,
  },

  // ── 27. Planner header ────────────────────────────────────────────────────────
  {
    id: 'tac-header',
    title: 'Planner Header',
    body: [
      'The header shows the mission ID, category, and mode. The buttons on the right let you Reset assignments, ask the agent to re-Suggest, change the drone team (Change Team), or deploy.',
      '"Drag → assign · Shift+drag → chain" summarises the controls — we will practise these shortly.',
    ],
    highlight: 'tac-header',
    cardSide: 'bottom',
    inMapWindow: true,
  },

  // ── 28. SVG zone ─────────────────────────────────────────────────────────────
  {
    id: 'tac-zone',
    title: 'The Mission Zone',
    body: [
      'The main area shows the mission zone as a blue circle. The dashed line and "HUB" label show the direction back to base.',
      'Drone icons sit around the zone perimeter — one icon per drone in the team. Task circles inside the zone represent the work to be done.',
    ],
    highlight: 'tac-svg-container',
    cardSide: 'left',
    inMapWindow: true,
  },

  // ── 29. Unassigned drones panel ──────────────────────────────────────────────
  {
    id: 'tac-unassigned',
    title: 'Unassigned Drones',
    body: [
      'The top of the right panel lists drones that have not yet been assigned to any task. Each chip shows the drone type icon and its callsign.',
      'Drag a chip from here and drop it onto a task circle on the map to assign it. That drone will then fly to that task when the mission deploys.',
    ],
    highlight: 'tac-unassigned',
    cardSide: 'left',
    inMapWindow: true,
  },

  // ── 30. Manual assignment walkthrough ────────────────────────────────────────
  {
    id: 'tac-manual',
    title: 'Assigning Manually',
    body: [
      'Try it: drag one of the unassigned drone chips and drop it onto a task circle. A dashed arrow appears showing the assignment. Step numbers on the arrows indicate execution order.',
      'Hold Shift while dragging to chain a drone through multiple tasks in sequence — useful when one drone can complete several tasks back-to-back.',
    ],
    cardSide: 'center',
    tryIt: true,
    inMapWindow: true,
  },

  // ── 31. Task schedule ─────────────────────────────────────────────────────────
  {
    id: 'tac-schedule',
    title: 'Task Schedule',
    body: [
      'The schedule lists each task with its required drone composition, assigned drones (drag the chips here to reassign or click × to remove), and estimated start and end times.',
      'A task turns green when its composition requirement is fully met. The footer shows the overall estimated completion time.',
    ],
    highlight: 'tac-schedule',
    cardSide: 'left',
    inMapWindow: true,
  },

  // ── 32. Tactical Agent plan ───────────────────────────────────────────────────
  {
    id: 'tac-agent',
    title: 'The Tactical Agent\'s Plan',
    body: [
      'Click "Reset" in the header to restore the Tactical Agent\'s original suggestion. Look at the arrows — this is the pre-planned assignment the agent computed when you chose a strategy.',
      'The agent fills all tasks automatically based on drone availability and task requirements. You can accept the plan as-is, or drag to adjust any assignment before deploying.',
    ],
    cardSide: 'center',
    tryIt: true,
    inMapWindow: true,
  },

  // ── 33. DEPLOY from tactical (mustInteract) ───────────────────────────────────
  {
    id: 'tac-deploy',
    title: 'Deploy the Mission',
    body: [
      'When you are satisfied with the assignments, click "Deploy ✓" to dispatch the drones. They will depart from the hub and navigate to their tasks.',
    ],
    highlight: 'tac-deploy-btn',
    cardSide: 'left',
    allowClickThrough: true,
    mustInteract: true,
    autoAdvanceWhen: state => state.missions.some(m => m.status === 'active' || m.status === 'completed'),
    inMapWindow: true,
  },

  // ── 34. Finish ───────────────────────────────────────────────────────────────
  {
    id: 'ready',
    title: "You're Ready — Good Luck!",
    body: [
      'That covers the full interface. Key things to remember: complete tasks quickly to keep penalty low, watch your drone reserve, and treat agent suggestions as helpful guidance — not guaranteed truth.',
      'You are always in control and can override any suggestion. Press Finish to close this tutorial.',
    ],
    cardSide: 'center',
  },
]
