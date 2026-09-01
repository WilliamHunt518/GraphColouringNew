// ─── Study configuration ───────────────────────────────────────────────────

export type Complexity = 'balanced' | 'strategic' | 'tactical' | 'full' | 'quick'
export type Mode = 'no-agent' | 'agent'
export type Condition = 'HH' | 'LH' | 'HL' | 'LL' | 'none'

export interface StudyConfig {
  participantId: string
  condition: Condition
  mode: Mode
  complexity: Complexity
  sessionComplexities?: Complexity[]  // per-session complexity override; falls back to `complexity` for any missing index
  seed: number
  agentErrorRate: number   // epsilonStrategic — error rate for Strategic Agent
  epsilonTactical: number  // error rate for Tactical Agent
  tacticalMode: 'plan-all' | 'greedy'
  testingMode: boolean
  // Scheduling-deadlock policy. Default (omitted or true) is auto-fix: the agent silently reroutes
  // the cyclic chains, every task still completes, and nothing is surfaced — so a participant can
  // never reach a stuck deadlock, which is why the tutorial teaches no lockout lesson. Explicit
  // false restores "help needed" (surfaced in red, drones freed and parked, operator re-plans or
  // abandons). Read it through isFixLockouts() in utils/config — never inline, the fallback used to
  // differ between the reducer, the tutorial, and the session_start log.
  fixLockouts?: boolean
  // Post-failure grace window (seconds). Once a drone fails on a mission, that mission is exempt
  // from further failure rolls until this long AFTER its recovery is resolved, so an operator can
  // never be handed a second failure on the same mission while still fixing the first. Omitted ⇒
  // FAILURE_GRACE_SECONDS (30). 0 disables the grace entirely (pre-study-v1.5 behaviour).
  failureGraceSeconds?: number
  tutorialMode: boolean
  skipToFreePlay?: boolean
  numSessions: number
  fullPathsOnHover?: boolean   // when true, hovering a drone/mission on the strategic map reveals full planned paths
  collectDemographics?: boolean  // when true, a demographics/experience questionnaire runs before session 1
  fastTest?: boolean             // dev only: 10s sessions + relaxed form validation, so the full flow can be walked quickly
}

// ─── Assets ───────────────────────────────────────────────────────────────

export type AssetType = 'Blue' | 'Red' | 'Green'
export type AssetStatus = 'available' | 'deployed' | 'returning' | 'failed'

export interface Asset {
  id: string
  type: AssetType
  status: AssetStatus
  currentMissionId: string | null
  currentTaskId: string | null
  position: { x: number; y: number }
  travelFrom: { x: number; y: number }
  targetPosition: { x: number; y: number }
  travelStartElapsed: number
  travelEndElapsed: number
  availableAt: number
  failedAt: number | null       // elapsed (s) when drone failed; null = healthy
  replacementAt: number | null  // elapsed (s) when replacement arrives at hub; null = no replacement scheduled
}

// ─── Pending tactical allocation ──────────────────────────────────────────

export interface PendingAllocation {
  strategyName: 'Aggressive' | 'Conservative' | 'Manual'
  composition: AssetRequirement
  dronePool: string[]                         // specific asset IDs committed for tactical assignment
  taskAssignments: Record<string, string[]>  // taskId → assetId[] (empty in manual mode until user assigns)
  taskOrder: string[]                         // taskIds in planned execution order
  expectedCompletionTime: number              // seconds
  isAgentSuggested: boolean
  isBadSuggestion: boolean
  badSuggestionType: 'over' | 'under' | null
  hasTacticalError: boolean                   // true when tactical agent suppressed one task
  suppressedTaskId: string | null             // the task the tactical agent omitted from its plan
}

// ─── Recovery options (drone failure) ────────────────────────────────────

export interface RecoveryOption {
  type: 'reserve' | 'redistribute'
  label: string
  description: string
  taskId: string
  newAssetId: string | null          // 'reserve': the specific reserve drone; null = none available
  redistributeToAssetId: string | null  // 'redistribute': existing mission drone to take over
  expectedTimeImpact: number         // extra seconds
  feasible: boolean
}

// ─── Tasks ────────────────────────────────────────────────────────────────

export type TaskType = 1 | 2 | 3 | 4 | 5
export type TaskStatus = 'pending' | 'traveling' | 'executing' | 'completed' | 'failed'

export interface Task {
  id: string
  missionId: string
  type: TaskType
  status: TaskStatus
  waypoint: { x: number; y: number }
  assignedAssetIds: string[]
  allocatedAt: number | null
  travelTime: number
  baseTime: number
  startTime: number | null
  completionTime: number | null
  useSubstitute: boolean
  recallDelay: number
  /** Drone types whose sections are already complete (graceful exits). Preserved across recovery re-dispatches. */
  completedSectionTypes?: string[]
}

// ─── Missions ─────────────────────────────────────────────────────────────

export type MissionCategory = 'A' | 'B' | 'C' | 'D' | 'E'
export type MissionStatus = 'queued' | 'active' | 'completed' | 'failed' | 'abandoned'

export interface Mission {
  id: string
  category: MissionCategory
  status: MissionStatus
  zoneCenter: { x: number; y: number }
  zoneRadius: number
  tasks: Task[]
  arrivalTime: number
  allocationTime: number | null
  completionTime: number | null
  // Interaction tracking
  agentInteraction: 'none' | 'shown' | 'followed' | 'overridden' | 'manual'
  chosenStrategyName: 'Aggressive' | 'Conservative' | 'Manual' | null
  manualPriorityIds: string[]
  // Tactical allocation state (agent mode: awaits sidebar confirmation)
  tacticalPending: boolean
  pendingAllocation: PendingAllocation | null
  tacticalOpenedAtMs: number | null   // session-elapsed ms when the tactical planner opened (for latency)
  tacticalSuggestCount?: number       // times the operator clicked "Suggest" in the tactical planner this allocation (0/undefined = agent tactical plan never consulted)
  // Per-drone task execution order (droneId → ordered taskId[]) — set on tactical confirm
  droneSequences: Record<string, string[]>
  // Drone failure
  droneFailuresFired: number    // how many failure events have triggered so far (live per-tick hazard, study-v1.3+; no precomputed schedule)
  failedDroneId: string | null
  // Failure recovery state
  failureRecoveryPending: boolean
  recoveryReason?: 'drone_failure' | 'lockout'  // why help is needed (a drone died vs a scheduling deadlock the operator must re-plan around)
  recoveryOpenedAtMs?: number | null            // session-elapsed ms when help-needed was raised (for failure_recovery latency)
  pendingRecoveryOptions: RecoveryOption[] | null
  // study-v1.5: elapsed (s) before which this mission cannot draw another drone failure. Set when a
  // failure fires and refreshed to `elapsed + failureGraceSeconds` when the recovery is resolved.
  failureExemptUntil?: number | null
  // Tactical agent error tracking
  tacticallySuppressedTaskId: string | null   // set after Deploy when tactical error was active
  // Abandon tracking
  abandonedAt: number | null     // elapsed (s) when abandoned; null = not abandoned
  abandonedReason?: 'operator' | 'lockout'  // why the mission was abandoned (operator gave up vs unbreakable scheduling deadlock)
  isResidual: boolean            // true if this mission was re-queued from an abandoned one
  needsGreedyReplan: boolean     // true when greedy mode is active; auto-replans after each task
}

// ─── Strategies ───────────────────────────────────────────────────────────

export interface AssetRequirement {
  Blue: number
  Red: number
  Green: number
}

export interface TaskComp {
  Blue: number; Red: number; Green: number; baseTime: number; useSubstitute: boolean
}

export interface Strategy {
  name: 'Aggressive' | 'Conservative'
  description: string
  assets: AssetRequirement            // displayed counts (may be wrong if isBadSuggestion)
  expectedCompletionTime: number      // displayed time (may be wrong if isBadSuggestion)
  reserveAfter: AssetRequirement
  speedScore: number
  reserveScore: number
  redundancyScore: number             // 0–1: buffer drones above mission minimum / pool size
  minimumAssets: AssetRequirement     // sum of all primary task compositions (floor allocation)
  taskComps: Record<string, TaskComp>
  isBadSuggestion: boolean
  badSuggestionType: 'over' | 'under' | null
  // True (correct) values — never shown to user, used by reducer for actual assignment
  trueAssets: AssetRequirement
  trueTaskComps: Record<string, TaskComp>
}

// ─── Game state UI ────────────────────────────────────────────────────────

export interface StrategicModal {
  missionId: string
  strategies: Strategy[]    // length 2 in agent mode, [] in no-agent mode
  selectedStrategyIndex: number | null
  manualAllocation: AssetRequirement | null
  openedAtMs: number         // session-elapsed ms when the modal opened (for latency)
  cardRevealDelaysMs: number[]  // per-card simulated "Analysing…" reveal delay (ms), drawn from the seeded RNG at open; Deploy is gated until all cards resolve
}

// ─── Map view state ───────────────────────────────────────────────────────

export interface FreePlayAchievement {
  id: string
  label: string
  done: boolean
}

export interface MapViewState {
  assets: Asset[]
  missions: Mission[]
  elapsed: number
  sessionNumber: number
  numSessions: number
  score: number
  penaltyAccrued: number
  phase: GamePhase
  pendingBlueprints: MissionBlueprint[]
  mode: Mode
  tacticalMode: 'plan-all' | 'greedy'
  reserve: AssetRequirement
  strategicModal: StrategicModal | null
  openMissionId: string | null
  tutorialActive: boolean
  tutorialStep: number
  freePlayActive: boolean
  freePlayAchievements: FreePlayAchievement[]
  freePlaySecondsLeft: number
  freePlayCanFinish: boolean
}

// ─── Game state ───────────────────────────────────────────────────────────

export type GamePhase = 'demographics' | 'playing' | 'survey' | 'between' | 'done'

export interface GameState {
  config: StudyConfig
  phase: GamePhase
  demographics: Record<string, string | number> | null  // pre-study questionnaire answers (null until submitted / not collected)
  sessionNumber: number
  elapsed: number
  sessionStartMs: number | null
  /** `nowMs` of the previous TICK, used to detect and absorb stalls (see MAX_TICK_GAP_MS). */
  lastTickMs: number | null
  assets: Asset[]
  missions: Mission[]
  pendingBlueprints: MissionBlueprint[]
  score: number
  penaltyAccrued: number
  completedSessionScores: number[]
  sessionDuration: number
  categoryForecast: Record<MissionCategory, number>
  // UI state
  strategicModal: StrategicModal | null
  trustProbeActive: boolean
  nextTrustProbeAt: number
  nextSnapshotAt: number   // elapsed (s) at which the next state_snapshot is due
  nextFailureRollAt: number   // elapsed (s) at which the next ambient drone-failure roll is due
  // Data logging — one array per session
  events: GameEvent[][]
  eventSeq: number   // monotonically increasing across the whole study (all sessions), never resets
}

// ─── Blueprints ───────────────────────────────────────────────────────────

export interface MissionBlueprint {
  id: string
  arrivalTime: number
  category: MissionCategory
  taskTypes: TaskType[]
  zoneCenter: { x: number; y: number }
  waypoints: { x: number; y: number }[]
}

// ─── Events (data logging) ────────────────────────────────────────────────

/**
 * Situational context stamped on EVERY event. Exists so that "how many X were there when Y
 * happened?" is answerable from the event alone, without replaying the whole session — the
 * operator's load at the moment of any decision is the covariate RQ3 (deferral by tier ×
 * complexity) needs, and RQ2/RQ4 both want to know what else was competing for attention when
 * a suggestion was accepted, overridden, or a failure was handled.
 */
export interface EventContext {
  score: number                    // running score at log time
  penaltyAccrued: number           // running penalty at log time
  missionsQueued: number           // arrived, not yet allocated
  missionsActive: number
  missionsCompleted: number
  missionsFailed: number
  missionsAbandoned: number
  tasksPending: number             // across all non-terminal missions
  tasksTraveling: number
  tasksExecuting: number
  tasksCompletedTotal: number
  tasksFailedTotal: number
  dronesAvailable: number          // status 'available' (raw hub inventory)
  dronesDeployed: number
  dronesReturning: number
  dronesFailed: number
  tacticalPendingMissionIds: string[]   // awaiting a tactical plan confirmation
  recoveryPendingMissionIds: string[]   // awaiting failure/lockout recovery
  strategicModalMissionId: string | null  // strategic modal open on this mission (null = closed)
}

export interface BaseEvent {
  type: string
  seq: number             // strictly increasing across the whole study (all sessions), tie-breaks same-ms events
  timestamp: number        // ms from session start (monotonic within session)
  wallClock: string         // ISO-8601 real wall-clock time of emission
  sessionId: string          // `${participantId}_${seed}_s${sessionNumber}`
  sessionNumber: number
  elapsed: number         // seconds
  reserveState: AssetRequirement           // raw hub inventory: every asset with status 'available'
  reserveStateAvailable: AssetRequirement  // reserve as DISPLAYED to the operator: hub-available MINUS drones already committed to other missions' pending tactical plans (reserveCount(assets, missions))
  context: EventContext                    // world state at log time — see EventContext
}

export interface SessionStartEvent extends BaseEvent {
  type: 'session_start'
  participantId: string
  condition: Condition
  mode: Mode
  complexity: Complexity
  seed: number
  epsilonStrategic: number
  epsilonTactical: number
  tacticalMode: 'plan-all' | 'greedy'
  fixLockouts: boolean
  numSessions: number
  sessionDuration: number
  fleet: AssetRequirement
  assetSpeeds: Record<AssetType, number>
  taskBaseTime: Record<TaskType, number>
  taskSubBaseTime: Record<TaskType, number>
  taskPrimary: Record<TaskType, AssetRequirement>
  taskSubstitute: Record<TaskType, AssetRequirement | null>
  taskWeight: Record<TaskType, number>
  categoryPenaltyRate: Record<MissionCategory, number>
  categoryWeights: Record<MissionCategory, number>   // weights for this session's complexity
  arrivalLambda: number                               // mean inter-arrival seconds for this session's complexity
  failureRatePerDroneSecond: number   // chance per second any one deployed drone fails (study-v1.3+; live hazard, uniform per drone)
  failureRollIntervalSec?: number     // study-v1.4+: simulated-time cadence of that hazard roll (absent ⇒ v1.3's per-frame roll)
  failureGraceSeconds?: number        // study-v1.5+: seconds after a mission's recovery is resolved during which it is exempt from further failures (absent ⇒ no grace)
  conservativeTopUp: number
  conservativeRedundancyBuffer: number
  snapshotIntervalSec: number   // cadence of state_snapshot events
  trustProbeIntervalSec: number // cadence at which the trust/workload probe is scheduled
  // Build/runtime provenance — "which code version and what screen produced this data"
  appVersion: string
  userAgent: string
  viewport: { width: number; height: number; devicePixelRatio: number } | null
}

export interface PhaseChangeEvent extends BaseEvent {
  type: 'phase_change'
  fromPhase: GamePhase
  toPhase: GamePhase
}

export interface MissionArrivedEvent extends BaseEvent {
  type: 'mission_arrived'
  missionId: string
  category: MissionCategory
  tasks: Array<{ id: string; type: TaskType }>
  zoneCenter: { x: number; y: number }
  arrivalTime: number
  timeRemainingInSession: number
  taskCompositions: Record<string, { primary: AssetRequirement; substitute: AssetRequirement | null; baseTime: number; subBaseTime: number | null }>
  penaltyRate: number
  maxReward: number
  // A residual mission is the re-queued remainder of one the operator abandoned. It arrives like any
  // other mission (and must be announced, or its later task/strategic events reference a mission the
  // log never introduced) but it is NOT new demand: its tasks were already counted in the parent's
  // `maxReward`/`tasks`. Analysis must exclude residuals from arrival denominators or every "share of
  // available reward" figure is wrong. See docs/EVENT_LOGGING.md § Abandonment.
  isResidual: boolean
  parentMissionId: string | null
}

export interface MissionCompletedEvent extends BaseEvent {
  type: 'mission_completed'
  missionId: string
  missionCategory: MissionCategory
  completionTime: number
  tasksCompleted: number
  tasksFailed: number
  rewardEarned: number
  penaltyAccrued: number
  // A mission reaches this event once every task is completed OR failed, so "completed" alone does
  // not mean it went well. Separates the three terminal shapes for analysis.
  outcome: 'all_completed' | 'partial' | 'none_completed'
  // Mission-level outcome joined to the decisions that produced it, so RQ1/RQ2 don't need a
  // multi-event join to ask "did agent-followed allocations outperform manual ones?"
  arrivalTime: number
  allocationTime: number | null       // when the strategic choice was applied
  timeToAllocate: number | null       // allocationTime − arrivalTime (operator's queueing delay)
  durationFromAllocation: number | null  // completionTime − allocationTime (execution efficiency)
  maxReward: number                   // sum of TASK_WEIGHT over all tasks (reward if perfect)
  chosenStrategyName: 'Aggressive' | 'Conservative' | 'Manual' | null
  agentInteraction: 'none' | 'shown' | 'followed' | 'overridden' | 'manual'
  hadTacticalError: boolean           // ε_T suppressed a task in this mission's plan
  suppressedTaskId: string | null
  droneFailureCount: number           // in-mission failures that fired before it ended
}

export interface StrategicChoiceEvent extends BaseEvent {
  type: 'strategic_choice'
  missionId: string
  missionCategory: MissionCategory
  choiceType: 'aggressive' | 'conservative' | 'manual'
  wasAgentSuggestion: boolean
  agentSuggestionWasBad: boolean
  badSuggestionType: 'over' | 'under' | null
  assetsChosen: AssetRequirement
  editedFromStrategy: string | null   // strategy name if manual edit was seeded from a card
  timeRemainingInSession: number
  latencyMs: number                   // time between modal opening and this choice
  deltaVsAggressive: AssetRequirement | null    // chosen minus aggressive card (null if no agent cards shown)
  deltaVsConservative: AssetRequirement | null  // chosen minus conservative card (null if no agent cards shown)
  strategyCardCount: number                     // number of agent strategy cards this modal offered
  manualBeforeCardsLoaded: boolean | null       // true if operator switched to manual while ≥1 card was still loading (a clue they declined the agent); null if not a manual-toggle choice
  cardsLoadedAtManualSwitch: number | null      // how many cards had finished loading at the moment manual was chosen (null if n/a)
  // Decomposition of latencyMs into forced wait vs operator deliberation:
  //   deliberationMs = latencyMs − deployEnabledAtMs
  cardRevealDelaysMs: number[]                  // the per-card "Analysing…" reveal delays drawn for this modal (same order as the cards)
  deployEnabledAtMs: number                     // ms after modal open at which Deploy became enabled on the path actually taken: max(cardRevealDelaysMs) for an agent-card choice, 0 for a manual choice (manual allocation is never gated)
}

export interface StrategicDismissedEvent extends BaseEvent {
  type: 'strategic_dismissed'
  missionId: string
  missionCategory: MissionCategory
  latencyMs: number   // time between modal opening and dismissal
  timeRemainingInSession: number
}

export interface TacticalOpenedEvent extends BaseEvent {
  type: 'tactical_opened'
  missionId: string
  missionCategory: MissionCategory
  strategyChosen: 'Aggressive' | 'Conservative' | 'Manual'
  agentPlan: Array<{ taskId: string; taskType: TaskType; assetIds: string[]; order: number }>
  timeRemainingInSession: number
  // ε_Tactical realisation for THIS mission. Previously recoverable only if the error manifested
  // (as a later task_failed/'tactical_lockout'), which made "was an error injected but harmless?"
  // unanswerable — needed to separate agent accuracy from operator detection in RQ2/RQ4.
  hasTacticalError: boolean
  suppressedTaskId: string | null
  dronePool: string[]                  // drones committed by the strategic step — what the operator has to plan with
  agentProjectedCompletion: number     // agent's estimated finish (absolute elapsed s)
  unassignedTaskIds: string[]          // mission tasks the agent's plan left with no drones (includes any suppressed task)
}

export interface TacticalConfirmedEvent extends BaseEvent {
  type: 'tactical_confirmed'
  missionId: string
  missionCategory: MissionCategory
  wasAgentSuggested: boolean
  modifiedFromAgentPlan: boolean  // true if operator changed any drone→task assignment from the greedy suggestion
  changedTaskIds: string[]        // task IDs whose drone assignment differed from the greedy suggestion
  chainingUsed: boolean           // true if any drone was assigned to more than one task
  assetsDeployed: string[]
  timeRemainingInSession: number
  latencyMs: number               // time between tactical planner opening and confirmation
  suggestUsedCount: number        // times the operator clicked "Suggest" before confirming (0 = agent tactical plan never consulted; the planner starts empty)
  agentPlan: Array<{ taskId: string; taskType: TaskType; assetIds: string[]; order: number }>
  finalPlan: Array<{ taskId: string; taskType: TaskType; assetIds: string[]; order: number }>
  // Override QUALITY (RQ4): was the operator's plan actually better than the agent's, and what did
  // it cost? Projected completions are directly comparable — same units, same scheduler.
  agentProjectedCompletion: number      // agent's estimate (absolute elapsed s)
  finalProjectedCompletion: number      // committed plan's projected finish (max task start+base)
  plannedTasks: Array<{ taskId: string; taskType: TaskType; assetIds: string[]; startTime: number; baseTime: number; useSubstitute: boolean }>
  unassignedTaskIds: string[]           // mission tasks committed with NO drones — these can never complete
  substituteTaskIds: string[]           // tasks committed on the slower substitute composition
  chainedDroneIds: string[]             // drones committed to more than one task
}

export interface TacticalSuggestUsedEvent extends BaseEvent {
  type: 'tactical_suggest_used'
  missionId: string
  missionCategory: MissionCategory
  suggestCountThisMission: number   // 1-based index of this Suggest click within the current tactical allocation
  timeRemainingInSession: number
  // Consultation in the RECOVERY planner used to be recorded only as `wasAgentSuggested` on the
  // eventual failure_recovery — component state that is reset whenever the mission's pending pool
  // changes (e.g. another task completes mid-recovery), silently losing the fact. Logging the click
  // itself makes consultation a fact in the stream rather than a derived UI flag.
  recoveryMode: boolean
}

// Deliberation-level events inside the strategic modal — capture the path to a choice, not just
// the final choice. Each is timestamped (envelope) so per-card dwell time and manual-build effort
// are recoverable. Verbose by design (one per click); filter by type for analysis.
export interface StrategicCardPreviewedEvent extends BaseEvent {
  type: 'strategic_card_previewed'
  missionId: string
  missionCategory: MissionCategory
  strategyIndex: number                          // which card was selected/highlighted
  strategyName: 'Aggressive' | 'Conservative'    // agent cards are always ordered Aggressive, Conservative
  latencyMs: number                              // time since the strategic modal opened
  timeRemainingInSession: number
}

export interface ManualAllocationEditedEvent extends BaseEvent {
  type: 'manual_allocation_edited'
  missionId: string
  missionCategory: MissionCategory
  allocation: AssetRequirement                   // the manual drone counts after this edit
  latencyMs: number                              // time since the strategic modal opened
  timeRemainingInSession: number
}

// Every individual drone→task manipulation in the tactical planner, as the operator builds/edits a
// plan (distinct from the final tactical_confirmed). Timestamped, so the whole construction path —
// order of assignment, backtracking, chaining, per-step think time — is replayable. Emitted from
// the three user-driven mutators only (the "Suggest" auto-fill and reset write assignments
// directly and do not log). Covers both initial build and failure-recovery reassignment.
export interface TacticalAssignmentChangedEvent extends BaseEvent {
  type: 'tactical_assignment_changed'
  missionId: string
  missionCategory: MissionCategory
  op: 'assign' | 'chain' | 'remove' | 'unassign' // assign=move drone onto a task; chain=add as an extra task for a drone already assigned; remove=drop from one task; unassign=clear from all tasks
  droneId: string
  droneType: AssetType | null                    // resolved from the fleet (null if unknown)
  taskId: string | null                          // null for 'unassign'
  taskType: TaskType | null                      // resolved from the mission (null for 'unassign' or if unknown)
  recoveryMode: boolean                          // true if this drag was in the failure-recovery planner
  timeRemainingInSession: number
}

export interface DroneFailureEvent extends BaseEvent {
  type: 'drone_failure'
  missionId: string
  missionCategory: MissionCategory
  droneId: string
  droneType: AssetType
  taskId: string | null   // null when the drone hadn't reached (or been dispatched to) a task yet
  taskType: TaskType | null
  timeRemainingInSession: number
}

export interface FailureRecoveryEvent extends BaseEvent {
  type: 'failure_recovery'
  missionId: string
  missionCategory: MissionCategory
  recoveryType: 'reserve' | 'redistribute' | 'manual'
  wasAgentSuggested: boolean
  timeRemainingInSession: number
  // Pairs with recovery_opened: what the operator actually did about it, and how long they took.
  recoveryReason: 'drone_failure' | 'lockout' | null
  latencyMs: number                   // recovery_opened → resolution
  repairedTaskIds: string[]           // tasks that got drones back
  repairedAssignments: Array<{ taskId: string; assetIds: string[] }>
  tasksStillUnassigned: string[]      // pending tasks left with no drones after the fix
}

/**
 * Fired when a mission enters the "help needed" state — a drone failed, or a scheduling deadlock
 * was surfaced to the operator. The audit flagged this as a gap: `failure_recovery` only recorded
 * the RESOLUTION, so there was no record of what the operator was shown or how long they sat on it.
 * RQ4 needs both halves (observation of failures, and the quality of the response).
 */
export interface RecoveryOpenedEvent extends BaseEvent {
  type: 'recovery_opened'
  missionId: string
  missionCategory: MissionCategory
  recoveryReason: 'drone_failure' | 'lockout'
  failedDroneId: string | null
  failedDroneType: AssetType | null
  affectedTaskIds: string[]                    // tasks reverted to pending / needing drones
  affectedTaskTypes: TaskType[]
  onMissionDroneIds: string[]                  // idle drones already at the zone (what the planner offers)
  reserveAvailable: AssetRequirement           // hub drones free at that moment
  feasibleWithOnMissionDrones: boolean         // could the affected tasks be re-staffed from the mission's own subswarm?
  tasksRemaining: number                       // not yet completed/failed in this mission
  timeRemainingInSession: number
}

/**
 * Periodic full-state dump. Not tied to any operator action — it exists so any question of the
 * form "what did the screen look like at time T?" is answerable for arbitrary T, including
 * intervals where the operator did nothing at all (an important signal in itself: idle time,
 * unattended queues, drones loitering unused). Interval is `snapshotIntervalSec` in session_start.
 */
export interface StateSnapshotEvent extends BaseEvent {
  type: 'state_snapshot'
  missions: Array<{
    id: string
    category: MissionCategory
    status: MissionStatus
    arrivalTime: number
    allocationTime: number | null
    completionTime: number | null
    chosenStrategyName: 'Aggressive' | 'Conservative' | 'Manual' | null
    agentInteraction: 'none' | 'shown' | 'followed' | 'overridden' | 'manual'
    tacticalPending: boolean
    failureRecoveryPending: boolean
    recoveryReason: 'drone_failure' | 'lockout' | null
    penaltyAccruedSoFar: number
    tasks: Array<{
      id: string
      type: TaskType
      status: TaskStatus
      assignedAssetIds: string[]
      startTime: number | null
      completionTime: number | null
      useSubstitute: boolean
    }>
    droneSequences: Record<string, string[]>
  }>
  assets: Array<{
    id: string
    type: AssetType
    status: AssetStatus
    currentMissionId: string | null
    currentTaskId: string | null
    x: number
    y: number
  }>
}

export interface TaskCompletedEvent extends BaseEvent {
  type: 'task_completed'
  missionId: string
  missionCategory: MissionCategory
  taskId: string
  taskType: TaskType
  assetsUsed: string[]
  completionTime: number        // the TASK's own completion time (what scoring charges against) — not the tick that noticed it
  detectedAtElapsed: number     // elapsed when the tick observed the completion; equals completionTime to within one frame unless the sim clock was throttled
  startTime: number | null      // when execution began
  travelTime: number            // wait from allocation to execution start
  baseTime: number              // execution duration actually used (substitute compositions are slower)
  useSubstitute: boolean        // true if the task ran on the substitute composition rather than the primary
  rewardEarned: number          // TASK_WEIGHT for this task type
  waitFromMissionArrival: number  // completionTime − mission.arrivalTime; the quantity penalty is charged on
}

export interface TaskFailedEvent extends BaseEvent {
  type: 'task_failed'
  missionId: string
  missionCategory: MissionCategory
  taskId: string
  taskType: TaskType
  reason: 'asset_recalled' | 'session_ended' | 'drone_failure' | 'tactical_lockout' | 'scheduling_deadlock' | 'mission_abandoned'
  statusBefore: TaskStatus         // what the task was doing when it died (pending = never dispatched)
  assignedAssetIds: string[]       // drones on it at the moment of failure
  startTime: number | null         // null if it never started executing
  rewardForgone: number            // TASK_WEIGHT that will now never be earned
  waitFromMissionArrival: number   // elapsed − mission.arrivalTime
  // Whether the mission had ever been allocated when this task died. The single biggest source of
  // `reason: 'session_ended'` failures is missions that were never allocated at all, and separating
  // "never started" from "in flight at the buzzer" previously needed a cross-reference to
  // strategic_choice. `false` + statusBefore 'pending' = the operator never took this mission on.
  missionWasAllocated: boolean
  missionStatusBefore: MissionStatus
}

// A task that moved to a re-queued (residual) mission when the operator abandoned its parent.
// This is deliberately NOT a task_failed: nothing was lost — the work is re-queued and is very often
// completed later under the residual's task id. Emitting task_failed here (as this used to) made
// abandonment look like mass task loss in every log. Join on residualTaskId to follow the work.
export interface TaskRequeuedEvent extends BaseEvent {
  type: 'task_requeued'
  missionId: string                // the abandoned parent
  missionCategory: MissionCategory
  taskId: string                   // id under the parent
  taskType: TaskType
  residualMissionId: string        // the mission it moved to
  residualTaskId: string           // its id under the residual — what a later task_completed will use
  statusBefore: TaskStatus         // what it was doing when the parent was abandoned
  assignedAssetIds: string[]       // drones on it at that moment (all released back to the hub)
  rewardDeferred: number           // TASK_WEIGHT still winnable via the residual
  executionProgress: number        // seconds of execution already done and preserved in the residual
  remainingBaseTime: number        // execution time the residual copy still needs
  waitFromMissionArrival: number   // elapsed − parent mission.arrivalTime
}

export interface LockoutDetectedEvent extends BaseEvent {
  type: 'lockout_detected'
  missionId: string
  missionCategory: MissionCategory
  taskIds: string[]                          // the cyclically-deadlocked tasks
  droneIds: string[]                         // drones caught in the cycle
  resolution: 'rerouted' | 'help_needed'     // agent auto-fixed (fixLockouts on) vs surfaced to the operator (off)
}

export interface AssetRecalledEvent extends BaseEvent {
  type: 'asset_recalled'
  assetId: string
  missionId: string
  taskId: string
}

export interface TaskReprioritisedEvent extends BaseEvent {
  type: 'task_reprioritised'
  missionId: string
  taskId: string
  newPosition: number
}

export interface SessionEndedEvent extends BaseEvent {
  type: 'session_ended'
  sessionNumber: number
  score: number
  penaltyAccrued: number
  completionPoints: number
  greenEfficiency: number
  meanMissionTime: number
  agentFollowRate: number  // fraction of strategic agent suggestions accepted
  tacticalFollowRate: number  // fraction of tactical agent plans confirmed unmodified
  reason: 'timer' | 'forced'
  inFlightMissionIds: string[]  // missions still active/queued when the session ended
  // Top-line task ledger, so the headline counts never have to be reconstructed by scanning (and
  // mis-binning) the event stream. requeued tasks are NOT failures; failuresByReason breaks the
  // failures down, and `neverAllocated` is the share of them whose mission was never taken on.
  taskOutcomes: {
    completed: number
    failed: number
    requeued: number
    failuresByReason: Record<string, number>
    failedOnNeverAllocatedMissions: number
  }
}

export interface StrategicModalOpenedEvent extends BaseEvent {
  type: 'strategic_modal_opened'
  missionId: string
  missionCategory: MissionCategory
  timeRemainingInSession: number
  activeMissions: number          // number of missions in 'active' status at time of opening
  currentPenaltyAccrued: number   // running penalty total at time of opening
  // What was displayed to the user (strategies array empty in no-agent mode)
  strategiesPresented: Array<{
    name: 'Aggressive' | 'Conservative'
    description: string
    displayedAssets: AssetRequirement        // counts shown in UI (may be perturbed)
    trueAssets: AssetRequirement             // counts actually used if chosen (never shown)
    displayedCompletionTime: number          // time shown in UI (may be perturbed)
    reserveAfter: AssetRequirement
    speedScore: number
    reserveScore: number
    redundancyScore: number
    isBadSuggestion: boolean
    badSuggestionType: 'over' | 'under' | null
    revealDelayMs: number                    // simulated "Analysing…" delay before THIS card became readable/selectable
  }>
}

export interface TrustProbeEvent extends BaseEvent {
  type: 'trust_probe'
  trust: number
  workload: number
}

export interface TrustProbeDismissedEvent extends BaseEvent {
  type: 'trust_probe_dismissed'
}

export interface SurveyResponseEvent extends BaseEvent {
  type: 'survey_response'
  surveyName: string
  responses: Record<string, number>
}

export interface MissionAbandonedEvent extends BaseEvent {
  type: 'mission_abandoned'
  missionId: string
  missionCategory: MissionCategory
  completedTaskCount: number
  remainingTaskCount: number
  // Where the remainder went. Every incomplete task is re-queued into the residual, so
  // `rewardLost` is normally 0 and `carriedTaskIds.length === remainingTaskCount`; the split is
  // logged explicitly so "abandoned" is never read as "this reward is gone".
  residualMissionId: string | null   // null only if nothing was left to re-queue
  carriedTaskIds: string[]           // parent task ids that moved to the residual
  rewardCarriedOver: number          // TASK_WEIGHT still winnable through the residual
  rewardLost: number                 // TASK_WEIGHT genuinely forgone (tasks with no residual copy)
}

export type GameEvent =
  | SessionStartEvent
  | PhaseChangeEvent
  | MissionArrivedEvent
  | MissionCompletedEvent
  | StrategicModalOpenedEvent
  | StrategicChoiceEvent
  | StrategicDismissedEvent
  | TacticalOpenedEvent
  | TacticalConfirmedEvent
  | TacticalSuggestUsedEvent
  | StrategicCardPreviewedEvent
  | ManualAllocationEditedEvent
  | TacticalAssignmentChangedEvent
  | DroneFailureEvent
  | FailureRecoveryEvent
  | TaskCompletedEvent
  | TaskFailedEvent
  | TaskRequeuedEvent
  | LockoutDetectedEvent
  | AssetRecalledEvent
  | TaskReprioritisedEvent
  | SessionEndedEvent
  | TrustProbeEvent
  | TrustProbeDismissedEvent
  | SurveyResponseEvent
  | MissionAbandonedEvent
  | RecoveryOpenedEvent
  | StateSnapshotEvent
