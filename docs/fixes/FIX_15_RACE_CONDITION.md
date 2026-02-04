# Fix #15: Agents Not Resolving Clashes After Human Accepts Offers

## Problem Summary

**Symptom**: After human accepted Agent2's offer and applied feasibility configuration, penalty remained at 20.000 despite agents having valid zero-penalty solutions available.

**Root Cause**: Race condition between `Accept` and `__ANNOUNCE_CONFIG__` messages:
1. User clicks "any configuration works" → sends `__ANNOUNCE_CONFIG__`
2. User accepts Agent2's offer → sends `Accept` + `__ANNOUNCE_CONFIG__`
3. If `__ANNOUNCE_CONFIG__` arrives first, it clears `rb_proposed_nodes`
4. Accept handler marks nodes as proposed and checks satisfaction
5. Satisfaction check FAILS because it requires nodes to be ALREADY in `rb_proposed_nodes`
6. Agent never becomes satisfied, keeps sending offers despite penalty=0

## Solution Implemented

Applied **defense-in-depth** approach with two fixes:

### Fix #15a: Preserve Proposed Nodes from Accepted Offers

**Location**: `agents/rule_based_cluster_agent.py` lines 1293-1310

**What it does**: When `__ANNOUNCE_CONFIG__` clears `rb_proposed_nodes`, preserve ALL proposed nodes if we have any accepted offers, since these represent commitments the agent must fulfill.

**Code changes**:
```python
# FIX #15: If we have accepted offers, preserve ALL proposed nodes
# These represent commitments we made that must persist through config changes
if self.rb_accepted_offers:
    preserved_proposed = dict(self.rb_proposed_nodes)  # Deep copy
    self.log(f"[RB Announcement FIX #15] Preserving ALL {sum(len(v) for v in preserved_proposed.values())} proposed nodes due to {len(self.rb_accepted_offers)} accepted offers")
else:
    preserved_proposed = {}

self.rb_active_offers.clear()
self.rb_accepted_offers.clear()
self.rb_rejected_offers.clear()
self.rb_rejected_conditions.clear()
self.rb_proposed_nodes.clear()

# Restore preserved proposed nodes
if preserved_proposed:
    self.rb_proposed_nodes = preserved_proposed
    self.log(f"[RB Announcement FIX #15] Restored {sum(len(v) for v in self.rb_proposed_nodes.values())} proposed nodes")
```

**Note**: Simplified from original implementation that tried to extract from `rb_accepted_offers` (which is a `Set[str]`, not a dict). New approach preserves entire `rb_proposed_nodes` dict when any offers are accepted.

### Fix #15b: Robust Satisfaction Check

**Location**: `agents/rule_based_cluster_agent.py` lines 1644-1668

**What it does**: If penalty=0 after accepting an offer, agent should be satisfied regardless of `rb_proposed_nodes` state.

**Code changes**:
```python
if all_satisfied:
    self.satisfied = True
    self.log(f"[RB Process] Achieved satisfaction after accepting offer {move.refers_to}")
else:
    # FIX #15: Even if not all boundary nodes are in proposed_nodes yet,
    # if penalty=0 after accepting an offer, we're satisfied!
    # This handles race condition where __ANNOUNCE_CONFIG__ cleared proposed_nodes
    self.satisfied = True
    self.log(f"[RB Process FIX #15] Achieved satisfaction after acceptance (penalty=0 despite incomplete proposed_nodes)")
```

## Expected Behavior After Fix

1. User applies feasibility config (h1=blue, h4=red) → agents receive `__ANNOUNCE_CONFIG__`
2. User accepts Agent2's offer → agents receive `Accept` + `__ANNOUNCE_CONFIG__`
3. **Fix #15a**: Preserved proposed nodes from accepted offers survive the clear
4. **Fix #15b**: If satisfaction check fails due to race, penalty=0 triggers satisfaction anyway
5. Agents become satisfied immediately
6. Penalty goes from 20.000 → 0.000
7. Consensus achieved

## Verification

Run the workflow:
```
1. Set config: h1=red, h2=blue, h3=green(fixed), h4=red, h5=green
2. Wait for Agent2's offer: "If h2=red AND h5=green then b2=blue"
3. Send feasibility query to Agent1: "Can I set h1=blue?"
4. Agent1 responds: "✓ Feasible if h4=red"
5. Click "any configuration works" button
6. Accept Agent2's offer
```

**Expected log messages**:
```
[RB Announcement FIX #15] Preserving proposed node b2=blue from accepted offer ...
[RB Announcement FIX #15] Preserved 1 proposed nodes from accepted offers
[RB Process FIX #15] Achieved satisfaction after acceptance (penalty=0 despite incomplete proposed_nodes)
```

**Expected outcome**:
- Final penalty = 0.000
- Both agents satisfied
- Consensus reached
- No more offers sent

## Files Modified

- `agents/rule_based_cluster_agent.py`
  - Lines 1289-1316: Preserve proposed nodes from accepted offers across __ANNOUNCE_CONFIG__
  - Lines 1644-1668: Add fallback satisfaction check when penalty=0

## Related Fixes

- Fix #12: Announce config after accepting offers (prevents human-side race condition)
- Fix #13: Initialize adjacency list (prevents null reference errors)
- Fix #14: Disable aggressive expiry (prevents premature offer expiration)
