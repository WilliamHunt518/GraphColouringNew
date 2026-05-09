// ─── Study configuration ───────────────────────────────────────────────────

export type Condition = 'HH' | 'LH' | 'HL' | 'LL' | 'PP'
export type Complexity = 'easy' | 'medium' | 'hard'

export interface StudyConfig {
  participantId: string
  condition: Condition
  complexity: Complexity
  seed: number
  epsilonCopilot: number
  epsilonMeta: number
}

// ─── Assets ───────────────────────────────────────────────────────────────

export type AssetType = 'Blue' | 'Red' | 'Green'
export type AssetStatus = 'available' | 'deployed' | 'returning'

export interface Asset {
  id: string
  type: AssetType
  status: AssetStatus
  currentMissionId: string | null
  currentTaskId: string | null
  // Animation — position interpolated between travelFrom → position at elapsed ∈ [travelStartElapsed, travelEndElapsed]
  position: { x: number; y: number }   // current rendered position (updated on tick)
  travelFrom: { x: number; y: number }
  targetPosition: { x: number; y: number }
  travelStartElapsed: number
  travelEndElapsed: number
  // Availability
  availableAt: number   // session elapsed (s) when asset is back at hub (0 = available now)
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
  allocatedAt: number | null          // elapsed (s) when assets started traveling to waypoint
  travelTime: number                  // seconds hub→waypoint for slowest assigned asset
  baseTime: number                    // seconds to execute at waypoint
  startTime: number | null            // elapsed (s) when execution begins = allocatedAt + travelTime
  completionTime: number | null       // elapsed (s) = startTime + baseTime
  useSubstitute: boolean              // false = primary composition; true = substitute composition
  recallDelay: number                 // extra seconds Co-Pilot delays recall after task completion (ε_C noise)
}

// ─── Missions ─────────────────────────────────────────────────────────────

export type MissionCategory = 'A' | 'B' | 'C' | 'D' | 'E'
export type MissionStatus = 'queued' | 'active' | 'completed' | 'failed'

export interface Mission {
  id: string
  category: MissionCategory
  status: MissionStatus
  zoneCenter: { x: number; y: number }
  zoneRadius: number
  tasks: Task[]
  arrivalTime: number       // elapsed (s) when mission appeared
  allocationTime: number | null
  completionTime: number | null
  // Track which Co-Pilot interaction occurred (for follow-rate logging)
  copilotInteraction: 'none' | 'shown' | 'followed' | 'modified' | 'dismissed'
}

// ─── Co-Pilot ─────────────────────────────────────────────────────────────

export interface AssetRequirement {
  Blue: number
  Red: number
  Green: number
}

export interface TaskComp {
  Blue: number; Red: number; Green: number; baseTime: number; useSubstitute: boolean
}

export interface Strategy {
  name: 'Fastest Possible' | 'Complete in Time' | 'Asset-Preserving'
  description: string
  assets: AssetRequirement
  expectedCompletionTime: number  // seconds
  reserveAfter: AssetRequirement
  speedScore: number    // 0–1
  reserveScore: number  // 0–1
  taskComps: Record<string, TaskComp>  // keyed by task.id — drives greedyAssign
}

export interface CopilotModal {
  missionId: string
  strategies: Strategy[]
  selectedIndex: number | null
  editedAllocation: AssetRequirement | null
  priorityTaskIds: string[]           // tasks user marked for priority scheduling
}

// ─── Meta-Co-Pilot ────────────────────────────────────────────────────────

export type Posture = 'Aggressive' | 'Conservative' | 'Hold'
export type AssetChip = 'commit freely' | 'commit cautiously' | 'hold'

export interface MetaRecommendation {
  posture: Posture
  rationale: string
  chips: Record<AssetType, AssetChip>
  timestamp: number  // elapsed (s)
}

// ─── Map view state (BroadcastChannel payload — omits event log) ─────────

export interface MapViewState {
  assets: Asset[]
  missions: Mission[]
  elapsed: number
  sessionNumber: 1 | 2 | 3
  score: number
  phase: GamePhase
  pendingBlueprints: MissionBlueprint[]
  copilotMissionId: string | null   // which mission's allocation modal is open
  priorityTaskIds: string[]          // tasks currently in the priority queue
}

// ─── Game state ───────────────────────────────────────────────────────────

export type GamePhase =
  | 'playing'
  | 'survey'
  | 'between'   // 30s between-session screen
  | 'done'

export interface GameState {
  config: StudyConfig
  phase: GamePhase
  sessionNumber: 1 | 2 | 3

  // Session clock
  elapsed: number      // seconds since current session start
  sessionStartMs: number | null  // wall-clock ms when session started (null until first tick)

  // Simulation
  assets: Asset[]
  missions: Mission[]              // all arrived missions for current session
  pendingBlueprints: MissionBlueprint[]  // pre-computed arrivals not yet spawned

  // Score
  score: number
  completedSessionScores: number[]

  // Forecast (updated on each mission arrival)
  categoryForecast: Record<MissionCategory, number>

  // AI
  metaRec: MetaRecommendation | null
  metaPostureOverride: Posture | null  // operator manual override

  // UI state
  copilotModal: CopilotModal | null
  trustProbeActive: boolean
  nextTrustProbeAt: number   // elapsed (s) when next probe appears; 90s intervals

  // Data logging — one array per session, indexed by sessionNumber-1
  events: GameEvent[][]
}

// Blueprint pre-computed at session start (before dynamic allocation)
export interface MissionBlueprint {
  id: string
  arrivalTime: number   // seconds from session start
  category: MissionCategory
  taskTypes: TaskType[] // sorted T5→T1 (execution priority order)
  zoneCenter: { x: number; y: number }
  waypoints: { x: number; y: number }[]  // parallel to taskTypes
}

// ─── Events (data logging) ────────────────────────────────────────────────

export interface BaseEvent {
  type: string
  timestamp: number     // milliseconds from session start
  sessionNumber: number
}

export interface MissionArrivedEvent extends BaseEvent {
  type: 'mission_arrived'
  missionId: string
  category: MissionCategory
  tasks: Array<{ id: string; type: TaskType }>
  zoneCenter: { x: number; y: number }
  arrivalTime: number
}

export interface AllocationStartedEvent extends BaseEvent {
  type: 'allocation_started'
  missionId: string
  triggeredBy: 'operator'
}

export interface CopilotShownEvent extends BaseEvent {
  type: 'copilot_shown'
  missionId: string
  strategies: Strategy[]
}

export interface CopilotStrategySelectedEvent extends BaseEvent {
  type: 'copilot_strategy_selected'
  missionId: string
  strategyIndex: number
  strategyName: string
}

export interface CopilotStrategyModifiedEvent extends BaseEvent {
  type: 'copilot_strategy_modified'
  missionId: string
  originalStrategy: Strategy
  modifiedAssets: AssetRequirement
}

export interface CopilotDismissedEvent extends BaseEvent {
  type: 'copilot_dismissed'
  missionId: string
}

export interface AllocationAppliedEvent extends BaseEvent {
  type: 'allocation_applied'
  missionId: string
  assetsAllocated: string[]
  source: 'copilot_as_proposed' | 'copilot_modified' | 'manual'
}

export interface MetaRecommendationEvent extends BaseEvent {
  type: 'metacopilot_recommendation'
  posture: Posture
  rationale: string
  perAssetChips: Record<AssetType, AssetChip>
}

export interface MetaFollowedEvent extends BaseEvent {
  type: 'metacopilot_followed'
  missionId: string
  recommendedPosture: Posture
  chosenPosture: Posture
}

export interface MetaOverriddenEvent extends BaseEvent {
  type: 'metacopilot_overridden'
  missionId: string
  recommendedPosture: Posture
  chosenPosture: Posture
}

export interface MetaIgnoredEvent extends BaseEvent {
  type: 'metacopilot_ignored'
  missionId: string
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
  reason: 'asset_recalled' | 'session_ended'
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
  greenEfficiency: number
  meanMissionTime: number
  cpFollowRate: number
  mcpFollowRate: number
}

export interface TrustProbeEvent extends BaseEvent {
  type: 'trust_probe'
  trust: number
  workload: number
}

export interface SurveyResponseEvent extends BaseEvent {
  type: 'survey_response'
  surveyName: string
  responses: Record<string, number>
}

export type GameEvent =
  | MissionArrivedEvent
  | AllocationStartedEvent
  | CopilotShownEvent
  | CopilotStrategySelectedEvent
  | CopilotStrategyModifiedEvent
  | CopilotDismissedEvent
  | AllocationAppliedEvent
  | MetaRecommendationEvent
  | MetaFollowedEvent
  | MetaOverriddenEvent
  | MetaIgnoredEvent
  | TaskCompletedEvent
  | TaskFailedEvent
  | AssetRecalledEvent
  | TaskReprioritisedEvent
  | SessionEndedEvent
  | TrustProbeEvent
  | SurveyResponseEvent
