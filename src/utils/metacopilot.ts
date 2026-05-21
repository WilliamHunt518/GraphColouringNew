// metacopilot.ts — Tactical Agent (stub; not yet extracted into its own module).
//
// The Tactical Agent operates at the within-mission level: once a strategic
// allocation has been committed, it advises on how to assign specific drone
// assets to individual tasks (which drone IDs do which tasks, in what order).
//
// Currently this logic lives inline in gameReducer.ts via greedyAssign().
// ε_T (epsilonTactical from StudyConfig) will control noise in the agent's
// suggested assignments when this module is implemented.
//
// NOTE: There is NO reserve-posture widget, NO preserve/maintain/spend-down
// recommendation. That concept was removed. This is purely drone→task planning.
export {}
