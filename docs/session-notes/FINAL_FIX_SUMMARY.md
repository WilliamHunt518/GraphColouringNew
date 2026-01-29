# Final Fix: RB Mode Negotiation Protocol

## Date: 2026-01-28

## Critical Bugs Found and Fixed

### **Bug #1: Unicode Encoding Crash** ✅ FIXED
**Location**: `agents/rule_based_cluster_agent.py` lines 99, 324, 337, 360

**Problem**: Unicode arrow characters `→` in log messages caused `UnicodeEncodeError` on Windows console (cp1252 encoding), silently crashing agents when trying to log acceptance.

**Fix**: Replaced all `→` with ASCII `->`

---

### **Bug #2: Offer ID Parsing Bug** ✅ FIXED
**Location**: `agents/rule_based_cluster_agent.py` lines 267, 632

**Problem**: Code extracted sender from offer ID incorrectly. For `offer_123_Human`, it compared `"Human"` to `recipient` parameter, but `recipient` is who we're responding TO, not who sent the offer.

**Fix**: Changed from `offer_id.split('_')[-1] == recipient` to `f"_{recipient}" in offer_id`

---

### **Bug #3: rb_proposed_nodes Pollution** ✅ FIXED (NEW!)
**Location**: `agents/rule_based_cluster_agent.py` lines 923-928

**Problem**: When receiving offers, the code was adding THEIR boundary nodes to `rb_proposed_nodes`, which should ONLY track OUR proposals. This corrupted the "have we proposed everything?" check, making agents think they'd already sent all proposals when they hadn't.

**Evidence from logs**:
```
[RB Move Gen] No move to send. Proposed: ['a2', 'a4', 'a5', 'h4', 'h1'], Boundary: ['a2', 'a4', 'a5']
```
The agent thinks it proposed `h4` and `h1` (human nodes!), so it returns None instead of generating offers.

**Fix**: Removed lines 923-928 that tracked incoming assignment nodes in `rb_proposed_nodes`. This dict should ONLY contain nodes WE control that WE have proposed.

**Code removed**:
```python
# Track their proposed nodes from this offer
if hasattr(move, 'assignments') and move.assignments:
    for assignment in move.assignments:
        if hasattr(assignment, 'node') and hasattr(assignment, 'colour'):
            if assignment.node not in self.nodes:
                self.rb_proposed_nodes.setdefault(sender, {})[assignment.node] = assignment.colour
```

---

## Log Analysis Shows System WAS Working!

Looking at `results/rb/Agent1_log.txt`:

```
[RB Move Gen] -> Accepting offer offer_1769599935_Human: 10.000 -> 10.000
[RB Accept] Changed our assignment: a2=blue
[RB Accept] Updated neighbor belief: h1=green
Sent Accept to Human: offer_1769599935_Human
```

**The agent DID accept a human offer!** The system was partially working, but then got stuck after `__ANNOUNCE_CONFIG__` due to Bug #3.

---

## Correct Workflow for RB Mode

### Phase 1: Configure
1. Human and agents set initial node colors
2. **DO NOT send conditional offers yet** - they will be cleared

### Phase 2: Transition
1. Human clicks "Announce Config" button
2. This sends `__ANNOUNCE_CONFIG__` to all agents
3. Agents transition to "bargain" phase
4. Agents send back their configuration announcements
5. **Old offers are cleared** (this is by design!)

### Phase 3: Bargain
1. Now human can send conditional offers: "If you do X, I'll do Y"
2. Agents evaluate offers and respond with:
   - **Accept** if offer improves/maintains penalty
   - **Reject** if offer worsens penalty
3. If rejected, human sends new counter-offer
4. Repeat until consensus

### Common Mistake
❌ Sending `__ANNOUNCE_CONFIG__` multiple times clears all offers and resets state
✅ Send `__ANNOUNCE_CONFIG__` ONCE at the start of bargaining

---

## Files Modified

1. `agents/rule_based_cluster_agent.py`
   - Lines 99, 324, 337, 360: Unicode → ASCII
   - Lines 267, 632: Offer ID parsing fix
   - Lines 923-928: **REMOVED** incorrect rb_proposed_nodes tracking

2. `comm/rb_protocol.py`
   - Line 41: Added "Reject" to ALLOWED_MOVES
   - Lines 272-277: Added Reject rendering

3. `ui/human_turn_ui.py`
   - Line 1146: Added Reject button
   - Lines 1255-1305: Implemented _reject_offer() method

---

## Testing Commands

```bash
# Run the UI
python launch_menu.py

# Select "RB (Rule-based)" mode
# Click "Run Experiment"

# Workflow:
# 1. Set initial colors for your nodes (h1-h5)
# 2. Click "Announce Config" ONCE
# 3. Wait for agents to respond with their configs
# 4. Build conditional offer: "IF agent nodes = colors THEN my nodes = colors"
# 5. Click "Send Conditional"
# 6. Agent should respond with Accept or Reject
```

---

## Expected Behavior After Fix

✅ Agents find human offers
✅ Agents evaluate offers correctly
✅ Agents accept offers that improve/maintain penalty
✅ Agents reject offers that worsen penalty
✅ Agents can generate counter-offers after rejection
✅ No more "stuck" behavior
✅ No more unicode crashes
✅ rb_proposed_nodes only tracks agent's own proposals

---

## Known Limitations

1. **Accept threshold**: Agents accept if penalty stays same (`<=` instead of `<`). This prevents deadlock but might accept neutral offers.

2. **Superseding logic**: Very aggressive - any counter-offer marks ALL our pending offers as superseded. Could be refined but doesn't break core functionality.

---

## Summary

**Three critical bugs fixed**:
1. ✅ Unicode encoding crash (silent failure)
2. ✅ Offer ID parsing (agents couldn't find offers)
3. ✅ **rb_proposed_nodes pollution (NEW!)** - agents thought they'd proposed everything

The logs prove the system WAS partially working (agents accepted offers), but Bug #3 was causing "No move to send" after config announcements.

**With all three fixes, the negotiation protocol should now work correctly end-to-end.**
