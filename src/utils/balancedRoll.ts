// Balanced (stratified) failure draws — study-v1.11.
//
// The ε_Strategic/ε_Tactical "does it fire this check?" roll (study-v1.10) was an independent
// Bernoulli draw per check (`rng.randFloat(0,1) < epsilon`). Independent draws are unbiased in
// expectation but have real variance at the check counts one participant actually sees (roughly
// 6-20 missions per session): two participants on the identical epsilon can end up with visibly
// different realized failure counts just from bad luck, which is exactly the kind of between-subject
// noise a between-subjects reliability manipulation needs to minimise.
//
// Fix: draw from a pre-built, seeded-shuffled BATCH of exactly round(epsilon * batchSize) hits
// out of `batchSize` slots, consumed one per check. Every full batch a participant completes
// contains exactly the configured proportion of fires, in an unpredictable (but seed-reproducible)
// order — no participant can get "extra unlucky" or "extra lucky" over a full batch the way
// independent draws allow. When a batch is exhausted mid-session (or spanning into the next), a
// fresh batch is drawn from the next slice of the seed's randomness, so the sequence is still fully
// reproducible from `seed` alone (see docs/STUDY_BUILD.md "Reproducing a session from its log").
import { SeededRNG } from './prng'

// 20 was picked to roughly match the total number of missions (hence strategic-modal-opens /
// tactical-plans) one participant sees across BOTH their sessions combined (~19-22 across a
// strategic-heavy + tactical-heavy pair) — see docs/SCENARIOS.md. So in the common case a
// participant's whole run is close to exactly one balanced batch, not several partial ones.
export const FAILURE_BALANCE_BATCH_SIZE = 20

export interface BalancedRollState {
  queue: boolean[]
  index: number
  batchNumber: number   // how many batches have been drawn so far (seeds each new batch uniquely)
}

export const initialBalancedRollState: BalancedRollState = { queue: [], index: 0, batchNumber: 0 }

/**
 * Draws the next "does this check fire?" outcome. Pass the SAME `state` back in on every call for
 * a given mechanism (one queue for ε_Strategic, a separate one for ε_Tactical — use a different
 * `salt` for each so they don't share a randomness stream), threading the returned `state` through.
 *
 * epsilon <= 0 short-circuits without touching the queue — this keeps a disabled mechanism
 * (agentFailuresEnabled=false, or a between-subjects arm with one epsilon at 0) from ever consuming
 * a slot, matching how `effectiveEpsilonStrategic`/`effectiveEpsilonTactical` already gate to 0.
 */
export function drawBalancedRoll(
  state: BalancedRollState,
  epsilon: number,
  seed: number,
  salt: number,
  batchSize: number = FAILURE_BALANCE_BATCH_SIZE,
): { fired: boolean; state: BalancedRollState } {
  if (epsilon <= 0) return { fired: false, state }

  let { queue, index, batchNumber } = state
  if (index >= queue.length) {
    const hits = Math.round(epsilon * batchSize)
    const batch = Array.from({ length: batchSize }, (_, i) => i < hits)
    // Fisher-Yates, seeded off (seed, salt, batchNumber) so batch N+1 never repeats batch N's order.
    const rng = new SeededRNG((seed ^ salt ^ Math.imul(batchNumber + 1, 0x9e3779b1)) >>> 0)
    for (let i = batch.length - 1; i > 0; i--) {
      const j = rng.randInt(0, i + 1)
      const tmp = batch[i]; batch[i] = batch[j]; batch[j] = tmp
    }
    queue = batch
    index = 0
    batchNumber = batchNumber + 1
  }

  const fired = queue[index]
  return { fired, state: { queue, index: index + 1, batchNumber } }
}

// Distinct salts so the strategic and tactical queues never draw from the same randomness stream
// even when they share `seed` (which they always do — one seed per participant).
export const STRATEGIC_FAILURE_SALT = 0xba1a
export const TACTICAL_FAILURE_SALT = 0xba1b
