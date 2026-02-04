# Agent2 Deadlock Fix - Summary

## Problem

Agent2 (b) was getting stuck and not asking for changes in RB mode. The agent would:

1. Send a conditional offer early in the negotiation
2. Wait indefinitely for a response (Accept/Reject)
3. Block generation of new offers because an old offer was still "pending"
4. Get stuck in an infinite loop showing: `[RB Move Gen] No move to send`

**Root Cause**: The human focused on negotiating with Agent1 and never responded to Agent2's initial offer. The agent's move generation logic prevented new offers when there were already pending offers (to avoid spamming), but this created a deadlock when the human simply ignored the offer.

## Solution

Implemented an **offer expiry mechanism** with the following changes:

### 1. Offer Tracking (rule_based_cluster_agent.py)

Added three new fields to track offer lifecycle:
```python
self.rb_offer_timestamps: Dict[str, float] = {}    # When offer was sent
self.rb_offer_iteration: Dict[str, int] = {}       # Iteration when sent
self.rb_iteration_counter: int = 0                  # Current iteration
```

### 2. Automatic Expiry

Added `_expire_old_offers()` method that runs at the start of each `step()`:
- Checks all pending offers that WE sent
- If an offer has received no response after **5 iterations**, it expires
- Expired offers are moved to `rb_rejected_offers`
- This allows the agent to generate new offers

### 3. Better Debug Logging

Added informative logging when offers block new generation:
```
[RB Move Gen] ⏳ Skipping Priority 4 - already have 1 pending offer(s): ['offer_XXX']
[RB Move Gen] ⏳ Waiting for response before generating new offers (offers expire after 5 iterations)
```

### 4. Enhanced Debug Window

Updated `ui/debug_window.py` to show RB protocol state:
- Phase and iteration counter
- Pending offers WE sent (with age)
- Pending offers FROM others
- Warning when agent is waiting for response

This makes it immediately clear in the debug window when an agent is blocked.

## Files Modified

1. `agents/rule_based_cluster_agent.py`:
   - Added offer tracking fields
   - Added `_expire_old_offers()` method
   - Enhanced logging in move generation priorities
   - Track timestamps when offers are sent/received

2. `ui/debug_window.py`:
   - Enhanced info pane to show RB protocol state
   - Display pending offers with age
   - Show warnings when agent is blocked

## Testing

Created `test_offer_expiry.py` to verify the fix:
- Simulates Agent2 sending offers without human response
- Verifies offers expire after 5 iterations
- Confirms agent can then generate new offers
- **Test PASSES** ✓

## Behavior Changes

**Before**:
- Agent sends offer → Human ignores it → Agent stuck forever
- No indication in logs why agent isn't generating offers
- Deadlock requires manual intervention

**After**:
- Agent sends offer → Human ignores it → Offer expires after 5 iterations
- Clear logging shows "Waiting for response (offers expire after 5 iterations)"
- Agent automatically recovers and generates new offers
- Debug window shows pending offer age and warnings

## Configuration

The expiry threshold is set in `_expire_old_offers()`:
```python
OFFER_EXPIRY_ITERATIONS = 5  # Adjust if needed
```

Higher values give more time for human response, lower values allow faster recovery.

## Impact on Experiments

- **Positive**: Prevents deadlock in multi-agent negotiations
- **Minimal**: Only affects cases where human doesn't respond for 5+ iterations
- **Transparent**: Expiry is logged and visible in debug window
- **Recoverable**: Agents can still reach consensus after expiry
