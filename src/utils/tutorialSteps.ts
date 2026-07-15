import type { GameState } from '../types'

// First tactical-window step index (steps ≥ this are shown in TacticalTutorial)
export const TACTICAL_STEP_FIRST = 16
export const TACTICAL_STEP_LAST  = 47   // tac-deploy2 (shifted by lockout-explain inserted before agent-intro)

// Step index where agent-introduction phase begins (triggers second mission spawn)
export const AGENT_INTRO_STEP = 37   // shifted by lockout-explain inserted before agent-intro

// Step index where Tutorial.tsx begins trying to force a drone failure
export const FAILURE_DEMO_STEP = 28

// Step index where Tutorial.tsx dispatches TUTORIAL_OVERRIDE_TEAM (tactical-pending — the team
// swap is explained later, in tac-welcome, so no dedicated "team assigned" card is shown here)
export const ALLOCATION_OVERRIDE_STEP = 14

// Step index where Tutorial.tsx dispatches TUTORIAL_FORCE_ABANDON_SCENARIO (abort-explain is shown here)
export const ABORT_EXPLAIN_STEP = 33

// First tactical-window step in PHASE 2 (abort-do) — used to keep TacticalTutorial overlay running
export const ABORT_DO_STEP = 35

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
  /** StrategicPanel hides agent cards and forces manual-only flow */
  forceManual?: boolean
  /** StrategicPanel hides the "Set manually instead" toggle so the operator can't leave the agent-card flow */
  forceAgent?: boolean
  /** Next is disabled while the Tactical Assistant's "Suggest" animation is still filling in the plan */
  waitForSuggest?: boolean
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
      'Each session lasts 8 minutes. When it ends you will answer a short survey before the next one begins.',
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
      'The amber countdown shows the time remaining in the session.',
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
      'Your reserve holds three drone types — {blue}, {red}, {green} — covered in detail next.',
      'This strip shows how many drones are available at the hub. The bold number is ready to deploy; the small text shows your total fleet of that type, and how many are currently out on missions.',
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
      '{blue} drones are your fastest type — used for reconnaissance tasks.',
      '{red} drones carry and place supplies — used for supply drops and precision deliveries.',
      '{green} drones are your slowest type, but carry the thermal camera some tasks specifically require.',
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
      'Each card shows the mission ID, a category badge ({catA} Routine through {catE} Mass Casualty), and task completion status.',
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

  // ── 12. Panel intro — agent suggestions hidden, must click manual toggle ─────
  {
    id: 'panel-intro',
    title: 'Manual Allocation',
    body: [
      'The allocation panel has two modes. Assistant suggestions are disabled for this first mission — we will cover those on the next one.',
      'Click "Set manually instead" below to switch to manual mode.',
    ],
    highlight: 'first-manual-toggle',
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
      'Check the task bars to see what drone types each task requires. A sensible minimum here is 1 {blue} + 2 {red} + 1 {green} — enough to cover every task at full speed. A second {blue} would let the two {T1} Recce tasks run in parallel instead of one after another.',
      'Use the ± buttons to set your allocation — the number after the slash is your available reserve. The ETA preview updates as you adjust. When you are happy, click "Deploy" to commit the team. The tutorial will advance automatically.',
    ],
    highlight: 'first-mission-card',
    cardSide: 'right',
    allowClickThrough: true,
    mustInteract: true,
    autoAdvanceWhen: state => state.missions.some(m => m.tacticalPending),
    forceManual: true,
    spotlightPadding: 8,
  },

  // ── 14. Tactical pending ──────────────────────────────────────────────────────
  // Tutorial.tsx dispatches TUTORIAL_OVERRIDE_TEAM when this step is entered (silently
  // swaps in the fixed training team — explained to the operator in tac-welcome, below).
  {
    id: 'tactical-pending',
    title: 'Tactical Planning Pending',
    body: [
      'Your committed team is already on its way to the mission zone — but they still need instructions on which drone handles which task.',
      'You give those instructions in the Tactical Planner. If the drones arrive before you finish planning, they simply hold at the zone edge and wait.',
    ],
    highlight: 'first-tactical-pending',
    cardSide: 'right',
  },

  // ── 16. Map overview — no "click button" prompt ───────────────────────────────
  {
    id: 'map-overview',
    title: 'The Strategic Map',
    body: [
      'A quick recap of the strategic map: the hub (blue circle), all mission zones (coloured circles), and drone travel routes. Zone colours: amber = queued, blue = active.',
      'Click Next, then follow the tutorial on the Tactical Planner screen — it should already be open on your second screen.',
    ],
    cardSide: 'center',
  },

  // ════════════════════ MAP WINDOW STEPS — PHASE 1 (inMapWindow: true) ══════════

  // ── 17. Tactical welcome ──────────────────────────────────────────────────────
  {
    id: 'tac-welcome',
    title: 'The Tactical Planner',
    body: [
      'Welcome. This window is where you plan exactly which drones do which tasks and in what order before they begin work at the zone.',
      'For this training mission we set your team to 2 {blue} + 1 {red} + 1 {green} so you can practise every control here. In the real session you always choose your own allocation.',
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
      'Different tasks need different combinations of {blue}, {red}, and {green} drones, so check each row before you start dragging.',
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
      'This panel lists drones that have not yet been assigned to any task — each chip shows the drone type icon and its callsign.',
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
      'Example: drag a {blue} drone to the first {T1} Recce, then Shift+drag the same {blue} to a second task. That drone will fly hub → {T1} → next task in one trip.',
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
      'Check the task types: {T1} Recce needs {blue} drones, {T3} Supply Drop needs {red} drones, {T5} Search & Service needs {green} drones. Use normal drags for new assignments and Shift+drag to add a drone to an additional task.',
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
      'Counters like "0/1F" mean 0 of 1 required {blue} drones are currently assigned — F/L/C are short for {blue}/{red}/{green}.',
      'A task turns green when its composition requirement is fully met. The footer shows the overall estimated completion time.',
      'One drone can cover the work of two, just slower: {T3} normally wants two {red} + one {green}, but with only one {red} a single {red} + {green} still completes it — much more slowly.',
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
      'When you are satisfied with the assignments, click "Deploy ✓" to send the drones to their tasks — they move from the zone edge straight to work.',
      'You have now completed the full manual workflow. Once deployed, we will demo a drone failure.',
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
      'The planner has switched to recovery mode. The failed drone has been removed from its task — that task is now uncovered and highlighted on the map.',
      'Your remaining team drones are still available to cover the gap. Click Next, and on the following step you will reassign one to the open task.',
    ],
    highlight: 'tac-svg-container',
    cardSide: 'left',
    spotlightPadding: 6,
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
      "The Strategic Assistant's Aggressive strategy always includes one redundant drone per type. In the manual picker the \"N can fail\" hint shows the same buffer for your own allocation.",
    ],
    cardSide: 'center',
  },

  // ════════════════ ABORT LESSON (primary + map window) ════════════════════════

  // ── 34. abort-explain (PRIMARY) — explain mission abandonment, dispatch forced scenario ──
  {
    id: 'abort-explain',
    title: 'When You Cannot Recover',
    body: [
      'Recovery can only draw on drones already deployed on that mission, not your hub reserve. If the failed drone was the only one of its type, the task can\'t be covered — and the only option is to abort.',
      'Partial completions still score; remaining tasks re-queue as a residual mission.',
      'The tutorial will now fail your {red} drone. Switch to the Tactical Planner to abort the mission.',
    ],
    cardSide: 'center',
  },

  // ── 35. abort-select (MAP WINDOW) — re-open the failed mission's recovery plan ──
  // After the first recovery the planner deselected the mission, so the operator must
  // click it again to bring up the recovery panel (and its Abandon button).
  {
    id: 'abort-select',
    title: 'Reopen the Failed Mission',
    body: [
      'Your mission has a fresh drone failure — it is back in the queue with a red border and a "FAIL" badge.',
      'Click it to reopen its recovery plan. This time you will find the failure cannot be covered.',
    ],
    highlight: 'tac-mission-list',
    cardSide: 'right',
    allowClickThrough: true,
    mustInteract: true,
    mustInteractHint: 'Click the red-bordered mission in the queue to open its recovery plan.',
    inMapWindow: true,
    noOverlayOnPrimary: true,
  },

  // ── 36. abort-do (MAP WINDOW) — mustInteract: click Abandon ─────────────────
  {
    id: 'abort-do',
    title: 'Abort the Mission',
    body: [
      'Your {red} drone has failed and there\'s no spare {red} on this mission to cover its task — the schedule shows it uncovered with "Reassign" disabled.',
      'Click "Abandon Mission" at the bottom of the recovery panel. Partial completions still score and the remaining tasks re-queue automatically.',
    ],
    cardSide: 'left',
    noOverlay: true,
    mustInteract: true,
    mustInteractHint: 'Click "Abandon Mission" at the bottom of the recovery panel.',
    autoAdvanceWhen: state => state.missions.some(m => m.status === 'abandoned'),
    inMapWindow: true,
    noOverlayOnPrimary: true,
  },

  // ── Lockout awareness (PRIMARY) — chaining deadlocks + help-needed recovery ──
  // Grouped with the "when things go wrong" lessons: shown right after the two drone-failure
  // demos (recovery + abort), before the agent introduction. A lockout surfaces exactly like a
  // drone failure, so it belongs next to them. Primary-window (not inMapWindow) explanatory card.
  {
    id: 'lockout-explain',
    title: 'Watch Out: Deadlocks',
    body: [
      'One more way things can go wrong — this time from your own plan. If you chain two drones so each waits on the other, neither task can start. For example a {red} chained "Task A → Task B" together with a {green} chained "Task B → Task A" — Task A is still missing the {green} (stuck over at Task B), and Task B is still missing the {red} (stuck over at Task A). The team locks up.',
      'If that happens the mission turns red and flags "Lockout — help needed", exactly like the drone failures you just handled. Open its recovery plan and re-assign the drones in a workable order — the easy fix is to have both visit the tasks in the same order — or abandon the mission.',
    ],
    cardSide: 'center',
  },

  // ════════════════ AGENT INTRODUCTION — STRATEGIC (back in primary) ════════════

  // ── 36. Agent intro ───────────────────────────────────────────────────────────
  {
    id: 'agent-intro',
    title: 'Now Try the Assistants',
    body: [
      'Good work — you\'ve completed the full manual workflow. A second mission has arrived.',
      'Strategic vs Tactical: the Strategic Assistant decides how many drones to commit overall; the Tactical Assistant then decides which specific drones do which tasks. You\'ll use both for this mission.',
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
    title: 'The Strategic Assistant',
    body: [
      'The Strategic Assistant offers two pre-computed strategies — Aggressive (more drones, faster mission) and Conservative (fewer drones, preserves your reserve).',
      'Both meet the mission\'s task requirements. Compare them and choose the one that fits your situation.',
    ],
    highlight: 'first-strategic-panel',
    cardSide: 'right',
    forceAgent: true,
  },

  // ── 35. Strategy card details ─────────────────────────────────────────────────
  {
    id: 'strategy-detail',
    title: 'Reading a Strategy Card',
    body: [
      'Each card shows: the drone composition (e.g. 2 {blue}, 1 {red}, 1 {green}), the estimated completion time for all tasks, and how many drones of each type remain in reserve after deployment.',
    ],
    highlight: 'first-strategy-card',
    cardSide: 'right',
    forceAgent: true,
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
    forceAgent: true,
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
    forceAgent: true,
  },

  // ════════════════════ MAP WINDOW STEPS — PHASE 2 (inMapWindow: true) ══════════

  // ── 38. Tactical agent intro card ────────────────────────────────────────────
  {
    id: 'tac-suggest-intro',
    title: 'The Tactical Assistant',
    body: [
      'Mission 2 is waiting for tactical planning. This time, instead of assigning drones manually, you will use the Tactical Assistant.',
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
    title: 'Let the Tactical Assistant Fill the Plan',
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
    waitForSuggest: true,
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
    // Mission 2 is the only mission awaiting tactical deploy at this point; advancing on
    // "no mission tacticalPending" detects its deployment regardless of mission 1's fate
    // (it was abandoned in the abort lesson, so an active/completed count would never reach 2).
    autoAdvanceWhen: state => !state.missions.some(m => m.tacticalPending),
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
