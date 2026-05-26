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

  // ── Testing mode ─────────────────────────────────────────────────────────
  | { type: 'FORCE_MISSION_ARRIVAL' }
  | { type: 'FORCE_DRONE_FAILURE' }

  // ── Session flow ─────────────────────────────────────────────────────────
  | { type: 'NEXT_SESSION' }
  | { type: 'END_STUDY' }
