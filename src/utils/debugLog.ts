import type { GameState, AssetRequirement } from '../types'
import { reserveCount, complexityForSession } from '../store/gameReducer'

// ─── Internal trace log (greedyAssign, etc.) ─────────────────────────────────

const traceEntries: string[] = []

export function debugLog(msg: string, data?: unknown): void {
  const ts = new Date().toISOString()
  const line = data !== undefined
    ? `[${ts}] ${msg} ${JSON.stringify(data, null, 0)}`
    : `[${ts}] ${msg}`
  traceEntries.push(line)
  console.debug('[DBG]', msg, data ?? '')
}

// ─── Mid-session study snapshot ───────────────────────────────────────────────
// Produces the same JSON structure as the final study download, so it can be
// analysed at any point during the session (e.g. after a crash or mid-test review).

export function downloadStudySnapshot(state: GameState): void {
  const config = state.config
  const now = new Date().toISOString()

  // Current reserve excluding drones in pending allocations
  const pendingIds = new Set(
    state.missions
      .filter(m => m.tacticalPending && m.pendingAllocation)
      .flatMap(m => m.pendingAllocation!.dronePool)
  )
  const effectiveReserve: AssetRequirement = {
    Blue:  state.assets.filter(a => a.type === 'Blue'  && a.status === 'available' && !pendingIds.has(a.id)).length,
    Red:   state.assets.filter(a => a.type === 'Red'   && a.status === 'available' && !pendingIds.has(a.id)).length,
    Green: state.assets.filter(a => a.type === 'Green' && a.status === 'available' && !pendingIds.has(a.id)).length,
  }

  const payload = {
    // ── Metadata ──────────────────────────────────────────────────────────────
    snapshotTime: now,
    snapshotType: 'mid_session' as const,

    // ── Study config (matches final download) ─────────────────────────────────
    participantId:    config.participantId,
    condition:        config.condition,
    mode:             config.mode,
    complexity:       complexityForSession(config, state.sessionNumber),
    seed:             config.seed,
    epsilonStrategic: config.agentErrorRate,
    epsilonTactical:  config.epsilonTactical,
    testingMode:      config.testingMode,

    // ── Progress ──────────────────────────────────────────────────────────────
    sessionNumber:    state.sessionNumber,
    elapsed:          Math.round(state.elapsed * 10) / 10,
    score:            state.score,
    penaltyAccrued:   state.penaltyAccrued,
    sessionScores:    state.completedSessionScores,   // completed sessions only

    // ── Live session state (in-progress data not yet in events) ───────────────
    liveSession: {
      elapsed:       Math.round(state.elapsed * 10) / 10,
      score:         state.score,
      penaltyAccrued: state.penaltyAccrued,
      reserve:       reserveCount(state.assets),
      effectiveReserve,
      missions: state.missions.map(m => ({
        id:             m.id,
        category:       m.category,
        status:         m.status,
        allocationTime: m.allocationTime !== null ? Math.round(m.allocationTime * 10) / 10 : null,
        completionTime: m.completionTime !== null ? Math.round(m.completionTime * 10) / 10 : null,
        agentInteraction: m.agentInteraction,
        chosenStrategy: m.chosenStrategyName,
        tacticalPending: m.tacticalPending,
        failureRecoveryPending: m.failureRecoveryPending,
        tacticallySuppressedTaskId: m.tacticallySuppressedTaskId,
        tasks: m.tasks.map(t => ({
          id:     t.id,
          type:   t.type,
          status: t.status,
          assignedAssetIds: t.assignedAssetIds,
          startTime:      t.startTime !== null ? Math.round(t.startTime * 10) / 10 : null,
          completionTime: t.completionTime !== null ? Math.round(t.completionTime * 10) / 10 : null,
        })),
      })),
      assets: state.assets.map(a => ({
        id:               a.id,
        type:             a.type,
        status:           a.status,
        currentMissionId: a.currentMissionId,
        currentTaskId:    a.currentTaskId,
        failedAt:         a.failedAt,
      })),
    },

    // ── Events (matches final download — all sessions, current session partial) ─
    sessions: state.events,

    // ── Internal debug trace (greedyAssign calls etc.) ────────────────────────
    debugTrace: [...traceEntries],
  }

  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `sar_snapshot_${config.participantId}_s${state.sessionNumber}_${Math.round(state.elapsed)}s_${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
}
