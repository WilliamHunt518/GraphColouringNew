# Fix #15 Complete: Race Condition + Offer Spam

## Problems Fixed

### Problem 1: Race Condition - Agents Not Achieving Satisfaction
**Symptom**: After accepting offers, penalty stayed at 20.000 despite valid zero-penalty solutions existing.
**Root Cause**: `__ANNOUNCE_CONFIG__` cleared `rb_proposed_nodes` before satisfaction check could validate commitments.

### Problem 2: Multiple Offers Stacking Up
**Symptom**: Agents generate multiple offers that stack up in the UI panel.
**Root Cause**: `__ANNOUNCE_CONFIG__` cleared `rb_active_offers`, breaking the suppression logic that prevents offer spam.

## Solutions Implemented

### Fix #15a: Preserve Proposed Nodes from Accepted Offers
**Location**: `agents/rule_based_cluster_agent.py` lines 1293-1320

When `__ANNOUNCE_CONFIG__` arrives, if we have any accepted offers, preserve ALL of `rb_proposed_nodes` since these represent commitments that must persist.

```python
# FIX #15a: If we have accepted offers, preserve ALL proposed nodes
if self.rb_accepted_offers:
    preserved_proposed = dict(self.rb_proposed_nodes)
    self.log(f"[RB Announcement FIX #15a] Preserving ALL {sum(len(v) for v in preserved_proposed.values())} proposed nodes")
else:
    preserved_proposed = {}
```

### Fix #15b: Preserve Pending Offers to Prevent Spam
**Location**: `agents/rule_based_cluster_agent.py` lines 1302-1322

Preserve offers that are still pending (not accepted/rejected) so the suppression logic continues to work.

```python
# FIX #15b: Preserve PENDING offers (not accepted/rejected yet)
preserved_active_offers = {}
for offer_id, offer in self.rb_active_offers.items():
    if offer_id not in self.rb_accepted_offers and offer_id not in self.rb_rejected_offers:
        preserved_active_offers[offer_id] = offer
        self.log(f"[RB Announcement FIX #15b] Preserving pending offer {offer_id}")

# After clearing, restore preserved offers
if preserved_active_offers:
    self.rb_active_offers = preserved_active_offers
    self.log(f"[RB Announcement FIX #15b] Restored {len(self.rb_active_offers)} pending offers")
```

**Why this works**: The suppression logic (lines 395-401) checks for pending offers in `rb_active_offers`:
```python
my_pending_conditional_offers = [
    oid for oid in self.rb_active_offers.keys()
    if self.name in oid and oid not in self.rb_accepted_offers...
]
if my_pending_conditional_offers:
    return None  # Don't send new offers
```

By preserving pending offers, agents continue to wait for responses instead of spamming new offers.

### Fix #15c: Robust Satisfaction Check (Already in place)
**Location**: `agents/rule_based_cluster_agent.py` lines 1673-1677

If penalty=0 after accepting an offer, become satisfied regardless of `rb_proposed_nodes` state.

```python
else:
    # FIX #15: Even if not all boundary nodes are in proposed_nodes yet,
    # if penalty=0 after accepting an offer, we're satisfied!
    self.satisfied = True
    self.log(f"[RB Process FIX #15] Achieved satisfaction after acceptance")
```

## Expected Behavior After Fix

### Offer Management
1. ✓ Agent sends ONE offer to Human
2. ✓ Offer appears in UI panel
3. ✓ Agent WAITS for response (no new offers)
4. Human accepts/rejects offer
5. ✓ Accepted offer is removed from active offers on next `__ANNOUNCE_CONFIG__`
6. ✓ Agent can now generate a NEW offer if needed (or become satisfied)

### Satisfaction Flow
1. Human accepts Agent2's offer
2. `__ANNOUNCE_CONFIG__` arrives
3. Agent processes acceptance, applies assignments
4. Agent checks penalty → 0.0
5. ✓ Agent becomes SATISFIED immediately
6. ✓ No more offers sent
7. ✓ Consensus reached

## Log Messages to Look For

```
[RB Announcement FIX #15a] Preserving ALL N proposed nodes due to M accepted offers
[RB Announcement FIX #15a] Restored N proposed nodes

[RB Announcement FIX #15b] Preserving pending offer offer_XXX (awaiting response)
[RB Announcement FIX #15b] Restored M pending offers (prevents offer spam)

[RB Move Gen] ⏸️ Suppressing boundary update - have pending offer awaiting response
[RB Process FIX #15] Achieved satisfaction after acceptance (penalty=0 despite incomplete proposed_nodes)
```

## Testing Instructions

1. Launch application and select RB mode
2. Set initial config: h1=red, h2=blue, h3=green(fixed), h4=red, h5=green
3. **Verify**: Each agent sends ONE offer only (no stacking)
4. Send feasibility query: "Can I set h1=blue?"
5. **Verify**: Agent1 responds, still shows ONE offer per agent
6. Click "any configuration works" button
7. **Verify**: Still ONE offer per agent (old offers replaced, not stacked)
8. Accept Agent2's offer
9. **Expected**:
   - Agent becomes satisfied
   - Penalty → 0.000
   - Consensus reached
   - No new offers generated

## Files Modified

- `agents/rule_based_cluster_agent.py`
  - Lines 1293-1322: Added Fix #15a and #15b
  - Lines 1673-1677: Fix #15c already in place

## Key Insight

The fix addresses two interconnected issues:
1. **Proposed nodes** needed to persist for satisfaction checking
2. **Active offers** needed to persist for offer suppression

Both were being cleared too aggressively by `__ANNOUNCE_CONFIG__`, causing:
- Agents unable to verify satisfaction (missing proposed nodes)
- Agents generating offer spam (missing active offers to suppress against)

By preserving both data structures selectively, we maintain both correctness and user experience.
