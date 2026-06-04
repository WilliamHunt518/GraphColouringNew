import type { GameState } from '../types'

// First tactical-window step index (steps ≥ this are shown in TacticalTutorial)
export const TACTICAL_STEP_FIRST = 17
export const TACTICAL_STEP_LAST  = 44   // tac-deploy2 at index 44 (last inMapWindow step)

// Step index where agent-introduction phase begins (triggers second mission spawn)
export const AGENT_INTRO_STEP = 34

// Step index where Tutorial.tsx begins trying to force a drone failure
export const FAILURE_DEMO_STEP = 29

// Step index where Tutorial.tsx dispatches TUTORIAL_OVERRIDE_TEAM
export const ALLOCATION_OVERRIDE_STEP = 14

export interface TutorialStep {
  id: string
  title: string
  body: string[]
  highlight?: string         // data-tutorial selector
  cardSide?: 'right' | 'left' | 'bottom' | 'top' | 'center'
  allowClickThrough?: boolean
  /** No Next button — user MUST perform the action; autoAdvanceWhen fires */
  mustInteract?: boolean
  /** Override the default "Perform the highlighted action…" mustInteract hint text */
  mustInteractHint?: string
  /** Show a "Try it" hint but keep Next button */
  tryIt?: boolean
  /** Override the default tryIt hint text */
  tryItHint?: string
  autoAdvanceWhen?: (state: GameState) => boolean
  /** Delay in ms before auto-advancing (default 500) */
  autoAdvanceDelay?: number
  spotlightPadding?: number
  /** Suppress ALL dim/spotlight overlay — card floats freely, full UI visible and interactive */
  noOverlay?: boolean
  /** Rendered in TacticalTutorial (map window), not primary Tutorial */
  inMapWindow?: boolean
  /** inMapWindow steps normally black out the primary window; this suppresses that overlay so the strategic view stays visible */
  noOverlayOnPrimary?: boolean
  /** StrategicPanel shows agent cards greyed-out and forces manual-only flow */
  forceManual?: boolean
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
      'Green drones are slowest (4.2 units/s) but carry a thermal camera that some tasks specifically require.',
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
      'A mission has arrived — you can see it here. We will run through a complete manual workflow first: allocate a team, plan the drone assignments, and deploy. After that you will try both AI agents.',
      'Missions are grouped by status: Incoming (awaiting allocation), Active (drones deployed), and Completed. Keep Incoming short.',
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
    autoAdvanceDelay: 0,
    spotlightPadding: 6,
    forceManual: true,
  },

  // ── 12. Panel intro — greyed agent cards, must click manual toggle ───────────
  {
    id: 'panel-intro',
    title: 'Manual Allocation',
    body: [
      'The allocation panel has two modes. The greyed-out cards are agent suggestions — we will cover those on the next mission.',
      'Click "Set manually instead" below to switch to manual mode.',
    ],
    highlight: 'first-strategic-panel',
    cardSide: 'right',
    allowClickThrough: true,
    mustInteract: true,
    forceManual: true,
    spotlightPadding: 6,
  },

  // ── 13. Set allocation & deploy (mustInteract — advances when tacticalPending) ──
  {
    id: 'manual-picker',
    title: 'Set Your Allocation & Deploy',
    body: [
      'Check the task bars to see what drone types each task requires. Use the ± buttons to set your allocation — the number after the slash is your available reserve.',
      'The ETA preview updates as you adjust. When you are happy, click "Deploy" to commit the team. The tutorial will advance automatically.',
    ],
    highlight: 'first-mission-card',
    cardSide: 'right',
    allowClickThrough: true,
    mustInteract: true,
    autoAdvanceWhen: state => state.missions.some(m => m.tacticalPending),
    forceManual: true,
    spotlightPadding: 8,
  },

  // ── 14. Allocation override notice (NEW) ─────────────────────────────────────
  // Tutorial.tsx dispatches TUTORIAL_OVERRIDE_TEAM when this step is entered.
  {
    id: 'allocation-override',
    title: 'Training Team Assigned',
    body: [
      'For this training mission we have set your drone team to 2 Blue + 1 Red + 1 Green — enough to practise every control in the tactical planner.',
      'In the real session you always choose your own allocation. Click Next to open the Tactical Planner.',
    ],
    cardSide: 'center',
  },

  // ── 15. Tactical pending ──────────────────────────────────────────────────────
  {
    id: 'tactical-pending',
    title: 'Tactical Planning Pending',
    body: [
      'The mission is now waiting for a tactical plan. A drone team has been committed but the drones have not yet departed — you still need to confirm which drone goes to which task.',
      'This is handled in the Tactical Planner. You can review and modify the plan before the drones leave.',
    ],
    highlight: 'first-tactical-pending',
    cardSide: 'right',
  },

  // ── 16. Map overview — no "click button" prompt ───────────────────────────────
  {
    id: 'map-overview',
    title: 'The Operational Map',
    body: [
      'The map shows your hub (blue circle), all mission zones (coloured circles), and drone travel routes. Zone colours: amber = queued, blue = active.',
      'Switch to the Tactical Planner window now — it should already be open on your second screen. The tutorial will continue there.',
    ],
    highlight: 'tactical-btn',
    cardSide: 'bottom',
    spotlightPadding: 6,
  },

  // ════════════════════ MAP WINDOW STEPS — PHASE 1 (inMapWindow: true) ══════════

  // ── 17. Tactical welcome ──────────────────────────────────────────────────────
  {
    id: 'tac-welcome',
    title: 'The Tactical Planner',
    body: [
      'Welcome. This window is where you plan exactly which drones do which tasks and in what order before the team departs.',
      'Use the Back and Next buttons on this card to navigate.',
    ],
    cardSide: 'center',
    inMapWindow: true,
  },

  // ── 18. Mission queue sidebar ─────────────────────────────────────────────────
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

  // ── 19. Select mission (mustInteract — advances when mission clicked) ─────────
  {
    id: 'tac-select',
    title: 'Select Your Mission',
    body: [
      'Click on the pending mission in the left panel to open its tactical plan. You should see a mission with a yellow border — that is the one you just allocated.',
    ],
    highlight: 'tac-mission-list',
    cardSide: 'right',
    allowClickThrough: true,
    mustInteract: true,
    inMapWindow: true,
  },

  // ── 20. Planner header ────────────────────────────────────────────────────────
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

  // ── 21. SVG zone ─────────────────────────────────────────────────────────────
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

  // ── 22. Task requirements ─────────────────────────────────────────────────────
  {
    id: 'tac-task-reqs',
    title: 'Check Task Requirements',
    body: [
      'Before assigning drones, look at the task schedule on the right. Each row shows which drone types a task needs to execute — a task cannot start until its requirements are met.',
      'Tasks that need Green drones are the most constrained — you have fewer of those in the team. Plan those assignments first.',
    ],
    highlight: 'tac-schedule',
    cardSide: 'left',
    inMapWindow: true,
  },

  // ── 23. Unassigned drones panel ──────────────────────────────────────────────
  {
    id: 'tac-unassigned',
    title: 'Your Available Drones',
    body: [
      'This panel lists drones that have not yet been assigned to any task. Each chip shows the drone type icon and its callsign.',
      'Cross-reference with the task schedule below to plan which drones to assign where. Drag a chip onto a task circle on the map to assign it.',
    ],
    highlight: 'tac-unassigned',
    cardSide: 'left',
    inMapWindow: true,
  },

  // ── 24. Manual assignment (mustInteract — advances when first drag fires) ───────
  {
    id: 'tac-manual',
    title: 'Assigning Drones to Tasks',
    body: [
      'Drag a drone icon from the mission zone map onto a task circle to assign it — a dashed arrow will appear. You can also drag a chip from the Unassigned panel above onto a task circle.',
      'A normal drag moves the drone exclusively to that task. Practise now: drag one drone onto a task circle to continue.',
    ],
    highlight: 'tac-svg-container',
    cardSide: 'left',
    allowClickThrough: true,
    mustInteract: true,
    inMapWindow: true,
  },

  // ── 25. Chaining (mustInteract — 2 Shift+drags required) ────────────────────
  {
    id: 'tac-chain',
    title: 'Chaining One Drone Through Multiple Tasks',
    body: [
      'A drone can visit more than one task before returning to the hub. Hold Shift while dragging a drone icon onto a second task circle — the drone keeps its current assignment and is added to the new task.',
      'Example: drag a Blue drone to the first T1 Recce, then Shift+drag the same Blue to a second task. That drone will fly hub → T1 → next task in one trip.',
      'Practise now: Shift+drag a drone onto a second task twice. The tutorial advances after two successful chains.',
    ],
    highlight: 'tac-svg-container',
    cardSide: 'left',
    allowClickThrough: true,
    mustInteract: true,
    inMapWindow: true,
  },

  // ── 26. Complete the plan (mustInteract — advances when canDeploy flips true) ──
  {
    id: 'tac-fill',
    title: 'Complete the Plan',
    body: [
      'Good — you\'ve practised chaining. Now assign drones to any remaining tasks. Every row in the schedule panel must show at least one drone before you can deploy.',
      'Check the task types: T1 needs Blue, T3 needs Red, T5 needs Green. Use normal drags for new assignments and Shift+drag to add a drone to an additional task.',
      'The tutorial advances automatically once all tasks are covered.',
    ],
    highlight: 'tac-svg-container',
    cardSide: 'left',
    allowClickThrough: true,
    mustInteract: true,
    inMapWindow: true,
  },

  // ── 27. Task schedule ─────────────────────────────────────────────────────────
  {
    id: 'tac-schedule',
    title: 'Task Schedule',
    body: [
      'The schedule lists each task with its required drone composition, assigned drones (drag chips here to reassign or click × to remove), and estimated start and end times.',
      'A task turns green when its composition requirement is fully met. The footer shows the overall estimated completion time.',
    ],
    highlight: 'tac-schedule',
    cardSide: 'left',
    inMapWindow: true,
  },

  // ── 27. DEPLOY from tactical manually (mustInteract) ─────────────────────────
  {
    id: 'tac-deploy',
    title: 'Deploy the Mission',
    body: [
      'When you are satisfied with the assignments, click "Deploy ✓" to dispatch the drones. They will depart from the hub and navigate to their tasks.',
      'You have now completed the full manual workflow. Once deployed, we will demo a drone failure — then you will try both AI agents.',
    ],
    highlight: 'tac-deploy-btn',
    cardSide: 'left',
    allowClickThrough: true,
    mustInteract: true,
    autoAdvanceWhen: state => state.missions.some(m => m.status === 'active' || m.status === 'completed'),
    inMapWindow: true,
  },

  // ════════════════ FAILURE DEMO (all in tactical window) ════════════════════

  // ── 29. Watch the deployment, wait for failure to fire (PRIMARY window) ──
  {
    id: 'failure-incoming',
    title: 'Watch the Deployment',
    body: [
      'Your drones have departed — switch to the map window to watch them flying. This is what a live mission looks like.',
      'A drone is about to experience a technical fault. Watch the mission queue here: the affected mission will appear with a red border when the failure triggers.',
    ],
    cardSide: 'right',
    noOverlay: true,
    mustInteract: true,
    mustInteractHint: 'Waiting for the failure to trigger — this step advances automatically.',
    autoAdvanceWhen: state => state.missions.some(m => m.failureRecoveryPending),
    autoAdvanceDelay: 1200,
  },

  // ── 30. failure-tac-view (TACTICAL inMapWindow, primary stays visible) ─────────
  {
    id: 'failure-tac-view',
    title: 'Mission Failure Alert',
    body: [
      'Mission 1 now has a red border and a "FAIL" badge in the queue. Click it to open its recovery plan.',
    ],
    highlight: 'tac-mission-list',
    cardSide: 'right',
    allowClickThrough: true,
    mustInteract: true,
    mustInteractHint: 'Click the red-bordered mission in the queue to continue.',
    inMapWindow: true,
    noOverlayOnPrimary: true,
  },

  // ── 31. failure-recovery-explain (TACTICAL — read-only intro to the recovery planner) ─
  {
    id: 'failure-recovery-explain',
    title: 'Recovery Planner',
    body: [
      'The planner has switched to recovery mode. The failed drone has been removed from its task — that task is now uncovered and highlighted.',
      'Your remaining team drones are still available. Drag one onto the uncovered task circle to cover the gap, then click "Reassign ✓" to dispatch.',
    ],
    cardSide: 'left',
    noOverlay: true,
    inMapWindow: true,
  },

  // ── 32. failure-recovery-do (TACTICAL — mustInteract, noOverlay keeps planner accessible) ─
  {
    id: 'failure-recovery-do',
    title: 'Reassign Now',
    body: [
      'Drag an available drone onto the uncovered task circle, then click "Reassign ✓". The tutorial advances automatically once recovery is confirmed.',
    ],
    cardSide: 'left',
    noOverlay: true,
    mustInteract: true,
    mustInteractHint: 'Drag a drone to the uncovered task, then click "Reassign ✓".',
    inMapWindow: true,
  },

  // ── 31. failure-lesson (PRIMARY) ─────────────────────────────────────────────
  {
    id: 'failure-lesson',
    title: 'Why Redundancy Matters',
    body: [
      'Failures like that happen in the real session too. Allocating extra drones above the mission minimum creates a buffer — one failure still leaves the task coverable.',
      "The Strategic Agent's Aggressive strategy always includes one redundant drone per type. In the manual picker the \"N can fail\" hint shows the same buffer for your own allocation.",
    ],
    cardSide: 'center',
  },

  // ════════════════ AGENT INTRODUCTION — STRATEGIC (back in primary) ════════════

  // ── 32. Agent intro ───────────────────────────────────────────────────────────
  {
    id: 'agent-intro',
    title: 'Now Try the Agents',
    body: [
      'Good work — you have completed the full manual workflow. A second mission has arrived.',
      'This time you will use the Strategic Agent to choose the allocation, then let the Tactical Agent plan the assignments in the Tactical Planner.',
    ],
    cardSide: 'center',
  },

  // ── 33. CLICK ALLOCATE on mission 2 (mustInteract) ───────────────────────────
  {
    id: 'allocate-agent',
    title: 'Allocate the Second Mission',
    body: [
      'Click the amber Allocate button on the queued mission to open the allocation panel. This time agent suggestions will be active.',
    ],
    highlight: 'first-allocate-btn',
    cardSide: 'right',
    allowClickThrough: true,
    mustInteract: true,
    autoAdvanceWhen: state => state.strategicModal !== null,
    autoAdvanceDelay: 0,
    spotlightPadding: 6,
  },

  // ── 34. Agent panel intro ─────────────────────────────────────────────────────
  {
    id: 'agent-panel-intro',
    title: 'The Strategic Agent',
    body: [
      'The Strategic Agent offers two pre-computed strategies — Aggressive (more drones, faster mission) and Conservative (fewer drones, preserves your reserve).',
      'Both meet the mission\'s task requirements. Compare them and choose the one that fits your situation. You can also use "Set manually instead" for full control.',
    ],
    highlight: 'first-strategic-panel',
    cardSide: 'right',
  },

  // ── 35. Strategy card details ─────────────────────────────────────────────────
  {
    id: 'strategy-detail',
    title: 'Reading a Strategy Card',
    body: [
      'Each card shows: the drone composition (e.g. 2 Blue, 1 Red, 1 Green), the estimated completion time for all tasks, and how many drones of each type remain in reserve after deployment.',
    ],
    highlight: 'first-strategy-card',
    cardSide: 'right',
  },

  // ── 36. Score bars ────────────────────────────────────────────────────────────
  {
    id: 'score-bars',
    title: 'Strategy Score Bars',
    body: [
      'Three bars summarise each strategy: Speed (mission completion time), Reserve (drones left available), and Resilience (redundancy against failures).',
      'There is no single correct choice — weigh speed against keeping reserve for upcoming missions.',
    ],
    highlight: 'first-strategy-card',
    cardSide: 'right',
  },

  // ── 37. SELECT & DEPLOY with agent (mustInteract) ────────────────────────────
  {
    id: 'deploy-agent',
    title: 'Select a Strategy & Deploy',
    body: [
      'Click one of the strategy cards to select it (a blue ✓ will appear), then click "Deploy Selected" to commit that drone team. The mission will move to tactical planning.',
    ],
    highlight: 'first-strategic-panel',
    cardSide: 'right',
    allowClickThrough: true,
    mustInteract: true,
    autoAdvanceWhen: state => state.missions.filter(m => m.tacticalPending).length >= 1,
    spotlightPadding: 6,
  },

  // ════════════════════ MAP WINDOW STEPS — PHASE 2 (inMapWindow: true) ══════════

  // ── 38. Tactical agent intro card ────────────────────────────────────────────
  {
    id: 'tac-suggest-intro',
    title: 'The Tactical Agent',
    body: [
      'Mission 2 is waiting for tactical planning. This time, instead of assigning drones manually, you will use the Tactical Agent.',
      'The agent fills in all drone-to-task assignments automatically. You can then accept the plan or drag to override individual assignments before deploying.',
    ],
    cardSide: 'center',
    inMapWindow: true,
  },

  // ── 40. Select mission 2 in the tactical queue ───────────────────────────────
  {
    id: 'tac-select-m2',
    title: 'Select Mission 2',
    body: [
      'Mission 2 is waiting in the queue with a yellow border. Click it to open its plan in the planner.',
    ],
    highlight: 'tac-mission-list',
    cardSide: 'right',
    allowClickThrough: true,
    mustInteract: true,
    mustInteractHint: 'Click mission 2 in the queue to continue.',
    inMapWindow: true,
  },

  // ── 41. Click Suggest (mustInteract — advances on tutorial-suggest-clicked) ──
  {
    id: 'tac-suggest',
    title: 'Let the Tactical Agent Fill the Plan',
    body: [
      'Click the "Suggest" button in the planner header. The agent fills in all drone-to-task assignments automatically.',
      'You will see dashed arrows appear on the map and the schedule update.',
    ],
    highlight: 'tac-suggest-btn',
    cardSide: 'bottom',
    allowClickThrough: true,
    mustInteract: true,
    mustInteractHint: 'Click the "Suggest" button to continue.',
    inMapWindow: true,
  },

  // ── 41. Review and override ───────────────────────────────────────────────────
  {
    id: 'tac-override',
    title: 'Review and Override',
    body: [
      'The agent has filled in a plan. You can accept it as-is, or drag any drone to a different task to override individual assignments.',
      'When the Deploy button reads "Deploy ✓" all tasks are covered. Click Next when ready.',
    ],
    highlight: 'tac-svg-container',
    cardSide: 'left',
    allowClickThrough: true,
    tryIt: true,
    tryItHint: 'Optionally drag to override an assignment, then click Next →.',
    inMapWindow: true,
  },

  // ── 42. DEPLOY mission 2 (mustInteract) ──────────────────────────────────────
  {
    id: 'tac-deploy2',
    title: 'Deploy Mission 2',
    body: [
      'When you are satisfied with the assignments, click "Deploy ✓" to dispatch the drones.',
    ],
    highlight: 'tac-deploy-btn',
    cardSide: 'left',
    allowClickThrough: true,
    mustInteract: true,
    autoAdvanceWhen: state =>
      state.missions.filter(m => m.status === 'active' || m.status === 'completed').length >= 2,
    inMapWindow: true,
  },

  // ── 43. Finish ───────────────────────────────────────────────────────────────
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
