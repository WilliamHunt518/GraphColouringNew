import type { AssetRequirement } from '../types'

export type GameAction =
  // ── Simulation clock ────────────────────────────────────────────────────
  | { type: 'TICK'; nowMs: number }

  // ── Strategic allocation ─────────────────────────────────────────────────
  | { type: 'OPEN_STRATEGIC'; missionId: string }          // open strategic panel
  | { type: 'CLOSE_STRATEGIC' }                             // dismiss without allocating
  | { type: 'PICK_STRATEGY'; strategyIndex: number }        // select agent strategy card
  | { type: 'EDIT_MANUAL'; allocation: AssetRequirement }   // adjust manual count
  | {
      type: 'APPLY_STRATEGIC'
      missionId: string
      source: 'agent' | 'manual'
      strategyIndex: number | null          // null if manual
      manualAllocation: AssetRequirement | null  // used when source='manual'
      editedFromStrategy?: string | null    // set when manual was seeded from a strategy card
    }

  // ── Tactical confirmation (agent mode — from map sidebar) ────────────────
  | { type: 'CONFIRM_TACTICAL'; missionId: string; taskAssignments?: Record<string, string[]>; droneSequences?: Record<string, string[]> }
  | { type: 'OVERRIDE_TACTICAL'; missionId: string }        // user wants to edit tactical

  // ── Drone failure recovery ───────────────────────────────────────────────
  | { type: 'ACCEPT_RECOVERY'; missionId: string; recoveryType: 'redistribute' }
  | { type: 'APPLY_MANUAL_RECOVERY'; missionId: string; taskId: string; newAssetId: string }
  | { type: 'CONFIRM_FAILURE_RECOVERY'; missionId: string; taskAssignments: Record<string, string[]> }
  | { type: 'ABANDON_MISSION'; missionId: string }

  // ── In-mission operations ────────────────────────────────────────────────
  | { type: 'RECALL_ASSET'; assetId: string }
  | { type: 'REPRIORITISE_TASK'; missionId: string; taskId: string; direction: 'up' | 'down' | 'top' }

  // ── Surveys / probes ─────────────────────────────────────────────────────
  | { type: 'SUBMIT_TRUST_PROBE'; trust: number; workload: number }
  | { type: 'SUBMIT_SURVEY'; surveyName: string; responses: Record<string, number> }
  | { type: 'FINISH_SURVEYS' }
  | { type: 'DISMISS_TRUST_PROBE' }

  // ── Testing / tutorial mode ──────────────────────────────────────────────
  | { type: 'FORCE_MISSION_ARRIVAL' }
  | { type: 'FORCE_DRONE_FAILURE' }
  | { type: 'FORCE_SESSION_END' }
  | { type: 'TUTORIAL_OVERRIDE_TEAM' }          // replace Mission 1 team with 2B+1R+1G for chaining practice
  | { type: 'TUTORIAL_FORCE_ABANDON_SCENARIO' }  // set first active mission into unrecoverable failure so operator must abandon

  // ── Session flow ─────────────────────────────────────────────────────────
  | { type: 'NEXT_SESSION' }
  | { type: 'END_STUDY' }
