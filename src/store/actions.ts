import type { AssetRequirement, Posture, Strategy } from '../types'

export type GameAction =
  // ── Simulation clock ────────────────────────────────────────────────────
  | { type: 'TICK'; nowMs: number }          // wall-clock ms; reducer computes elapsed

  // ── Mission lifecycle ────────────────────────────────────────────────────
  | { type: 'OPEN_ALLOCATE'; missionId: string }          // operator clicks "Allocate"
  | { type: 'SELECT_STRATEGY'; strategyIndex: number }    // Co-Pilot card selected
  | { type: 'EDIT_ALLOCATION'; allocation: AssetRequirement }  // operator tweaks assets
  | {
      type: 'APPLY_ALLOCATION'
      missionId: string
      allocation: AssetRequirement
      source: 'copilot_as_proposed' | 'copilot_modified' | 'manual'
      strategies: Strategy[]    // current Co-Pilot strategies (for follow-rate tracking)
      selectedIndex: number | null
    }
  | { type: 'DISMISS_COPILOT'; missionId: string }

  // ── In-mission operations ────────────────────────────────────────────────
  | { type: 'RECALL_ASSET'; assetId: string }
  | { type: 'REPRIORITISE_TASK'; missionId: string; taskId: string; direction: 'up' | 'down' }

  // ── Meta-Co-Pilot ────────────────────────────────────────────────────────
  | { type: 'SET_META_POSTURE'; posture: Posture }   // operator overrides MCP posture

  // ── Surveys / probes ─────────────────────────────────────────────────────
  | { type: 'SUBMIT_TRUST_PROBE'; trust: number; workload: number }
  | { type: 'SUBMIT_SURVEY'; surveyName: string; responses: Record<string, number> }
  | { type: 'FINISH_SURVEYS' }   // called once after all survey pages are submitted
  | { type: 'DISMISS_TRUST_PROBE' }

  // ── Session flow ─────────────────────────────────────────────────────────
  | { type: 'NEXT_SESSION' }   // operator clicks Continue after between-session screen
  | { type: 'END_STUDY' }
