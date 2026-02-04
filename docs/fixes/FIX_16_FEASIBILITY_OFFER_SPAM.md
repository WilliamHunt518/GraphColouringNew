# Fix #16: Feasibility Handler Generates Duplicate Offers

## Problem

Even with Fix #15b (preserving pending offers), agents were still generating multiple offers because the **feasibility query handler** bypasses the normal suppression logic.

### Evidence from Logs

```
[UI update_conditionals] Called with 3 conditionals
  [0] offer_1770132505_Agent1: 2 conds  <-- FIRST OFFER
  [1] offer_1770132537_Agent1: 2 conds  <-- SECOND OFFER (DUPLICATE!)
  [2] offer_1770132505_Agent2: 2 conds
```

Agent1 generated TWO offers:
1. `offer_1770132505_Agent1` - Initial conditional offer
2. `offer_1770132537_Agent1` - Generated during feasibility query response

### Root Cause

The feasibility query handler (`_handle_feasibility_query`) has code to generate a "proactive conditional offer" after responding to queries:

```python
# Line 1788-1809 (before fix)
self._send_feasibility_response(sender, move, True, ...)
self.log(f"[RB Feasibility] Generating proactive conditional offer...")
self.rb_force_conditional_generation[sender] = True
offer = self._generate_conditional_offer(sender)  # GENERATES NEW OFFER
# Adds to rb_active_offers → NOW WE HAVE DUPLICATE!
```

This **bypasses** the normal suppression logic in `_generate_move()` which checks for pending offers.

### Why This Happens

**Normal offer generation** (lines 332-352):
```python
my_pending_offers = [oid for oid in self.rb_active_offers.keys() if ...]
if my_pending_offers:
    return None  # SUPPRESSED - don't generate new offer
```

**Feasibility handler** (lines 1788-1809):
- Sends feasibility response ✓
- Generates new offer **WITHOUT checking for pending offers** ✗
- Adds to `rb_active_offers` → creates duplicate

## Solution

**Fix #16**: Check for pending offers before generating proactive offer in feasibility handler

**Location**: `agents/rule_based_cluster_agent.py` lines 1788-1827

**Changes**:
```python
# FIX #16: Check if we already have pending offers before generating new one
my_pending_offers = [
    oid for oid in self.rb_active_offers.keys()
    if self.name in oid
    and oid not in self.rb_accepted_offers
    and oid not in self.rb_rejected_offers
    and oid.startswith("offer_")
]

if my_pending_offers:
    self.log(f"[RB Feasibility FIX #16] ⏸️ Skipping proactive offer - already have pending offers: {my_pending_offers}")
    self.log(f"[RB Feasibility FIX #16] Human can accept existing offer or we'll update after their response")
else:
    # Generate proactive offer ONLY if no pending offers exist
    self.log(f"[RB Feasibility] Generating proactive conditional offer...")
    self.rb_force_conditional_generation[sender] = True
    try:
        offer = self._generate_conditional_offer(sender)
        ...
```

## Expected Behavior After Fix

### Scenario: Human Sends Feasibility Query When Agent Has Pending Offer

**Before Fix #16**:
1. Agent sends offer A
2. Human sends feasibility query "Can I set h1=blue?"
3. Agent responds with feasibility result
4. Agent **ALSO generates offer B** (duplicate!)
5. UI shows TWO offers from same agent ✗

**After Fix #16**:
1. Agent sends offer A
2. Human sends feasibility query "Can I set h1=blue?"
3. Agent responds with feasibility result
4. Agent **SKIPS generating new offer** (already has pending offer A)
5. UI shows ONE offer from agent ✓

### Scenario: Human Sends Feasibility Query When Agent Has NO Pending Offers

**Behavior (unchanged)**:
1. Agent sends offer A
2. Human accepts offer A → no longer pending
3. Human sends feasibility query "Can I set h2=red?"
4. Agent responds with feasibility result
5. Agent **generates new offer B** (no pending offers)
6. UI shows ONE new offer ✓

## Log Messages to Look For

```
[RB Feasibility FIX #16] ⏸️ Skipping proactive offer - already have pending offers: ['offer_XXX_Agent1']
[RB Feasibility FIX #16] Human can accept existing offer or we'll update after their response
```

If you see these messages, it means the fix is working and duplicate offers are being suppressed.

## Testing

1. Start RB mode experiment
2. Wait for agents to send initial offers
3. **Verify**: Each agent shows ONE offer
4. Send feasibility query: "Can I set h1=blue?"
5. **Verify**: Agent responds with feasibility result
6. **Verify**: UI STILL shows ONE offer per agent (no duplicate)
7. Accept an offer
8. Send another feasibility query
9. **Verify**: Agent can now generate a NEW offer (old one was accepted)

## Files Modified

- `agents/rule_based_cluster_agent.py`
  - Lines 1788-1827: Added Fix #16 - check for pending offers before generating proactive offer

## Relationship to Other Fixes

- **Fix #15a**: Preserve proposed nodes from accepted offers
- **Fix #15b**: Preserve pending offers across config changes
- **Fix #16**: Prevent feasibility handler from creating duplicate offers

All three fixes work together to ensure **ONE offer per agent at a time**:
- Fix #15b maintains pending offers through config changes
- Fix #16 prevents feasibility handler from bypassing suppression
- Result: Clean, single-offer UI experience
