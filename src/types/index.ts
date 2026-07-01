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
  tutorialMode: boolean
  skipToFreePlay?: boolean
  numSessions: number
  fullPathsOnHover?: boolean   // when true, hovering a drone/mission on the operational map reveals full planned paths
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
  droneFailureTimes: number[]   // seconds after arrivalTime for each scheduled failure
  droneFailuresFired: number    // how many failure events have triggered so far
  failedDroneId: string | null
  // Failure recovery state
  failureRecoveryPending: boolean
  pendingRecoveryOptions: RecoveryOption[] | null
  // Tactical agent error tracking
  tacticallySuppressedTaskId: string | null   // set after Deploy when tactical error was active
  // Abandon tracking
  abandonedAt: number | null     // elapsed (s) when operator abandoned; null = not abandoned
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
  willFail: boolean
  droneFailureTimes: number[]   // seconds after arrivalTime for each scheduled failure; [] if none
}

// ─── Events (data logging) ────────────────────────────────────────────────

export interface BaseEvent {
  type: string
  seq: number             // strictly increasing across the whole study (all sessions), tie-breaks same-ms events
  timestamp: number        // ms from session start (monotonic within session)
  wallClock: string         // ISO-8601 real wall-clock time of emission
  sessionId: string          // `${participantId}_${seed}_s${sessionNumber}`
  sessionNumber: number
  elapsed: number         // seconds
  reserveState: AssetRequirement
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
  failureCount: number
  failureGap: number
  failureJitter: number
  conservativeTopUp: number
  conservativeRedundancyBuffer: number
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
  scheduledFailureTimes: number[]
  penaltyRate: number
  maxReward: number
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
}

export interface TacticalSuggestUsedEvent extends BaseEvent {
  type: 'tactical_suggest_used'
  missionId: string
  missionCategory: MissionCategory
  suggestCountThisMission: number   // 1-based index of this Suggest click within the current tactical allocation
  timeRemainingInSession: number
}

export interface DroneFailureEvent extends BaseEvent {
  type: 'drone_failure'
  missionId: string
  missionCategory: MissionCategory
  droneId: string
  droneType: AssetType
  taskId: string
  taskType: TaskType
  timeRemainingInSession: number
}

export interface FailureRecoveryEvent extends BaseEvent {
  type: 'failure_recovery'
  missionId: string
  missionCategory: MissionCategory
  recoveryType: 'reserve' | 'redistribute' | 'manual'
  wasAgentSuggested: boolean
  timeRemainingInSession: number
}

export interface TaskCompletedEvent extends BaseEvent {
  type: 'task_completed'
  missionId: string
  taskId: string
  taskType: TaskType
  assetsUsed: string[]
  completionTime: number
}

export interface TaskFailedEvent extends BaseEvent {
  type: 'task_failed'
  missionId: string
  taskId: string
  reason: 'asset_recalled' | 'session_ended' | 'drone_failure' | 'tactical_lockout' | 'mission_abandoned'
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
  | DroneFailureEvent
  | FailureRecoveryEvent
  | TaskCompletedEvent
  | TaskFailedEvent
  | AssetRecalledEvent
  | TaskReprioritisedEvent
  | SessionEndedEvent
  | TrustProbeEvent
  | TrustProbeDismissedEvent
  | SurveyResponseEvent
  | MissionAbandonedEvent
