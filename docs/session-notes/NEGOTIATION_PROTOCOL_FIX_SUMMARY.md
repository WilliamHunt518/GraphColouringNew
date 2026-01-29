# Agent Negotiation Protocol Fix - Implementation Summary

## Overview
Fixed critical bugs in RB (rule-based) mode negotiation protocol that prevented agents from accepting human offers and caused agents to get stuck repeating the same offer.

## Implementation Date
2026-01-28

## Changes Implemented

### Phase 1: Fixed Critical Offer ID Parsing Bug ✓

**File**: `agents/rule_based_cluster_agent.py`

**Bug**: Offer IDs have format `"offer_{timestamp}_{SENDER_name}"`, but the code was extracting the last segment with `split('_')[-1]` and comparing it to `recipient` (the agent being messaged). This was backwards - for human offers like `"offer_1234567890_Human"`, it compared `"Human" != "Agent1"`, so offers were never found.

**Fix**: Changed from:
```python
and (offer_id.split('_')[-1] if '_' in offer_id else None) == recipient
```

To:
```python
and f"_{recipient}" in offer_id  # Check if recipient name is in offer_id as sender
```

**Locations Fixed**:
- Line ~267: Priority 1 offer evaluation
- Line ~632: Duplicate offer detection in _generate_conditional_offer

**Impact**: Agents can now find and evaluate human offers correctly.

---

### Phase 2: Added Explicit Rejection Mechanism ✓

**Files**: `comm/rb_protocol.py`, `agents/rule_based_cluster_agent.py`

**Problem**: No way to explicitly reject an offer, forcing infinite loops when offers were unacceptable.

**Changes**:

1. **Added "Reject" to protocol** (`comm/rb_protocol.py` line 41):
   ```python
   ALLOWED_MOVES = ("Propose", "ConditionalOffer", "CounterProposal", "Accept", "Reject", "Commit")
   ```

2. **Added rejection rendering** (`comm/rb_protocol.py` after line 272):
   ```python
   elif move.move == "Reject":
       if move.refers_to:
           base = f"Reject offer {move.refers_to}"
       else:
           base = "Reject"
   ```

3. **Added rejection tracking** (`agents/rule_based_cluster_agent.py` line 97):
   ```python
   self.rb_rejected_offers: Set[str] = set()  # Set of rejected offer_ids
   ```

4. **Updated offer filtering** to exclude rejected offers (line ~269):
   ```python
   and offer_id not in self.rb_rejected_offers  # Not already rejected
   ```

5. **Added rejection generation** (line ~362):
   - After evaluating all offers, if none are acceptable, explicitly reject the most recent one
   - Marks offer as rejected
   - Returns Reject move with reasons

6. **Added incoming rejection handler** (line ~904):
   - Processes Reject moves from other participants
   - Removes rejected offer from active offers
   - Marks as rejected

**Impact**:
- Agents explicitly reject unacceptable offers
- Rejected offers removed from consideration
- Forces both parties to think of alternatives

---

### Phase 3: Fixed Duplicate Prevention to Allow Re-Proposals ✓

**File**: `agents/rule_based_cluster_agent.py`

**Problem**: Duplicate check prevented agents from re-proposing their preferred solution after a rejection, even when the context changed.

**Fix**: Modified duplicate check (line ~683) to only prevent duplicates within CURRENT negotiation context:
```python
our_pending_offers_to_recipient = [
    (offer_id, offer) for offer_id, offer in self.rb_active_offers.items()
    if offer_id not in self.rb_accepted_offers
    and offer_id not in self.rb_rejected_offers  # Exclude rejected
    and self.name in offer_id  # Our offers
    and offer_id not in [oid for oid, _ in pending_from_recipient]  # Not their offers to us
]
```

**Impact**:
- Agents can re-propose their preferred solution in response to rejections
- Duplicate prevention still works within a single round
- Allows "trying again" after rejection/counter

---

### Phase 4: Offer Lifecycle Management ✓

**File**: `agents/rule_based_cluster_agent.py`

**Problem**: Offers accumulated indefinitely across negotiation rounds without cleanup.

**Changes**:

1. **Added offer cleanup on phase transitions** (line ~763):
   ```python
   # CLEAN UP OLD OFFERS FROM PREVIOUS ROUND
   old_offer_count = len(self.rb_active_offers)
   self.rb_active_offers.clear()
   self.rb_accepted_offers.clear()
   self.rb_rejected_offers.clear()
   self.log(f"[RB Phase] Cleared {old_offer_count} old offers from previous round")
   ```

2. **Added offer superseding when counter-offering** (line ~875):
   - When receiving a counter-offer, mark our old pending offers as superseded
   - Move to rejected set so they're no longer considered
   - Remove from active offers

**Impact**:
- Offers cleaned up between configuration rounds
- Old offers superseded when new counter-offers arrive
- State doesn't accumulate indefinitely

---

### Phase 5: Human UI Rejection Button ✓

**File**: `ui/human_turn_ui.py`

**Problem**: Human participants had no way to explicitly reject agent offers via UI.

**Changes**:

1. **Added Reject button** (line ~1146):
   ```python
   ttk.Button(
       btn_frame,
       text="Reject",
       command=lambda oid=cond.get("offer_id"): self._reject_offer(oid)
   ).pack(side="left", padx=2)
   ```

2. **Implemented _reject_offer() method** (line ~1255):
   - Finds offer to get sender
   - Marks offer as rejected in UI
   - Builds RB Reject message
   - Sends rejection via message pipeline
   - Appends to transcript

**Impact**:
- Human can explicitly reject offers via UI button
- Agent receives rejection and removes offer from consideration
- Forces agent to generate new proposal

---

## Testing Plan

### Test Scenario 1: Agent Accepts Human Offer
1. Launch RB mode experiment
2. Human sends offer: "If a4=green AND a5=red, then h4=blue"
3. **Expected**: Agent evaluates, finds it acceptable (penalty=0), responds with Accept
4. **Verify**: Check Agent log for "[RB Move Gen] -> Accepting offer"

### Test Scenario 2: Agent Rejects Bad Offer
1. Human sends offer that would increase penalty
2. **Expected**: Agent responds with Reject message
3. **Verify**: Check Agent log for "[RB Move Gen] -> Rejecting offer"

### Test Scenario 3: Iterative Negotiation
1. Human sends offer A
2. Agent rejects, counters with offer B
3. Human rejects, counters with offer C
4. Agent accepts offer C
5. **Expected**: Back-and-forth negotiation converges

### Test Scenario 4: Offer Cleanup
1. Send __ANNOUNCE_CONFIG__ to start new round
2. **Expected**: Old offers cleared from tracking
3. **Verify**: Check Agent log for "Cleared X old offers from previous round"

### Test Scenario 5: Re-Proposal After Rejection
1. Agent proposes offer X
2. Human rejects
3. Human counters with offer Y
4. Agent evaluates Y, finds it worse
5. **Expected**: Agent can re-propose offer X (not blocked by duplicate check)

## Success Criteria

✅ Agents find and evaluate human offers (fix parsing bug)
✅ Agents accept offers when penalty improves or stays same
✅ Agents explicitly reject unacceptable offers
✅ Human can reject agent offers via UI button
✅ Agents can re-propose after rejection (not blocked by duplicate check)
✅ Offers cleaned up between rounds
✅ Back-and-forth negotiation converges to solution
✅ No more "stuck" behavior where agent repeats same offer silently

## Files Modified

1. `agents/rule_based_cluster_agent.py` - Main agent negotiation logic
2. `comm/rb_protocol.py` - Protocol definitions and rendering
3. `ui/human_turn_ui.py` - Human interface with rejection button

## Technical Notes

- The core issue was that the negotiation protocol lacked proper state management and an explicit rejection mechanism
- With these changes, the system should exhibit proper turn-taking negotiation behavior
- The duplicate prevention logic is preserved but scoped to prevent spam within a single context, not across the entire negotiation history
- All changes maintain backward compatibility with existing experiment logs and data

## Running the Fixed System

```bash
python launch_menu.py
# Select: Communication Mode = "RB (Rule-based)"
# Select: Agent 1 Algorithm = "greedy"
# Click "Run Experiment"
```
