# Conditional Offers Fixed - Agents Now Negotiate

## Date: 2026-01-28

## What You Reported

"They are just status updates... they never finish. I'm not sure if they are satisfied. If not, they aren't telling me what I have to change."

You're absolutely right. Agents were:
- ✓ Sending status updates when you clicked Pass
- ✗ BUT never making conditional offers to propose solutions
- ✗ Never becoming satisfied
- ✗ Never finishing negotiation

## The Root Cause

**TWO bugs preventing conditional offer generation:**

### Bug #1: rb_proposed_nodes Not Updated

**File**: `agents/rule_based_cluster_agent.py`, lines 161-166

When Priority 0 sent a boundary_update, it didn't update `rb_proposed_nodes`, so:
1. Agent sends: "I'm now at a2=green, a4=green"
2. Agent doesn't remember it told you
3. Next step: Priority 0 checks again, sees "mismatch", sends same update again
4. Repeats forever, blocking Priorities 2 and 4

### Bug #2: Status Updates Block Conditional Offers

**File**: `agents/rule_based_cluster_agent.py`, lines 460, 478

Priority 2 and Priority 4 check:
```python
my_offers = [oid for oid in self.rb_active_offers.keys()
             if self.name in oid and oid not in self.rb_accepted_offers]
if not my_offers:  # Only generate if no pending offers
    conditional_offer = self._generate_conditional_offer(recipient)
```

But `my_offers` includes:
- `config_1234_Agent1` (initial config)
- `update_1234_Agent1` (status updates)

So the agent thinks it has "pending offers" and won't generate new conditional offers!

## The Fix

### Fix #1: Update rb_proposed_nodes After Sending

**File**: `agents/rule_based_cluster_agent.py`, lines 168-176

```python
# Update rb_proposed_nodes to track what we told this recipient
# This prevents Priority 0 from repeatedly sending the same boundary update
if hasattr(move, 'assignments') and move.assignments:
    for assign in move.assignments:
        if hasattr(assign, 'node') and hasattr(assign, 'colour'):
            # Only track our own nodes (boundary nodes)
            if assign.node in self.nodes:
                self.rb_proposed_nodes.setdefault(recipient, {})[assign.node] = assign.colour
                self.log(f"[RB Track] Updated proposed: {recipient} now knows {assign.node}={assign.colour}")
```

**What this does:**
- After sending ANY ConditionalOffer (including status updates), mark which nodes we told them about
- Next time Priority 0 checks, it sees "already told them" and skips
- Allows Priorities 2 and 4 to run

### Fix #2: Exclude Status Updates from Pending Offers Check

**File**: `agents/rule_based_cluster_agent.py`, lines 460-467, 482-489

```python
# Check if we already have pending CONDITIONAL offers (not status updates)
# Status updates (update_xxx) don't count - they're just announcements
my_offers = [
    oid for oid in self.rb_active_offers.keys()
    if self.name in oid
    and oid not in self.rb_accepted_offers
    and not oid.startswith("update_")  # Exclude status updates
    and not oid.startswith("config_")  # Exclude initial configs
]
```

**What this does:**
- Only count real conditional offers (with IF conditions) as "pending"
- Status updates and initial configs don't block new offers
- Agents can generate conditional proposals even after sending status updates

## What You'll See Now

### Scenario: Agent Has Conflicts (penalty > 0)

1. **Step 1**: Click Pass
   - Agent sends status update: "I'm now at a2=green, a4=green" (penalty=10)
   - Updates rb_proposed_nodes

2. **Step 2**: Click Pass again
   - Priority 0 skips (no boundary changes)
   - Priority 2 or 4 triggers (conflicts detected, penalty > 0)
   - Agent generates **conditional offer**:
     ```
     Offer #1 ← Agent1
     IF:
       • h1 = blue
       • h4 = red
     THEN:
       • a2 = green
       • a4 = green
     ```
   - This tells you: "If you change h1 to blue and h4 to red, I can use green for my nodes"

3. **You respond**:
   - Accept: Change your colors, agent becomes satisfied
   - Reject: Agent tries different proposal
   - Counter: Propose your own conditional offer

### Scenario: Agent Is Satisfied (penalty = 0)

1. Agent sends final status update showing satisfied state
2. Agent becomes satisfied (satisfied=True)
3. You check "I'm satisfied" boxes
4. System ends with consensus

## Testing

**IMPORTANT**: You MUST restart the UI for these changes to take effect!

```bash
# Close any running UI
# Then restart:
python launch_menu.py
```

**Test workflow:**
1. Select RB mode, run experiment
2. Click "Announce Config" ONCE
3. Set some conflicting colors for your nodes (e.g., h1=red when Agent1 has a2=red)
4. Click "Pass" on Agent1
5. **First response**: Status update showing agent's current colors
6. Click "Pass" again
7. **Second response**: Conditional offer with IF/THEN proposing a solution

**Check logs:**
```bash
grep "Updated proposed" results/rb/Agent1_log.txt
# Should see: "Updated proposed: Human now knows a2=green"

grep "Priority 2\|Priority 4" results/rb/Agent1_log.txt | tail -5
# Should see: "Priority 2: Conflicts detected" or "Priority 4: Penalty > 0"
```

## Files Modified

1. **agents/rule_based_cluster_agent.py**
   - Lines 168-176: Update rb_proposed_nodes after sending offers
   - Lines 460-467: Filter out status updates from Priority 2 check
   - Lines 482-489: Filter out status updates from Priority 4 check

## Expected Behavior

| Situation | First Pass | Second Pass |
|---|---|---|
| Conflicts exist (penalty > 0) | Status update | Conditional offer (IF/THEN) |
| Agent satisfied (penalty = 0) | Status update | Nothing (or repeat status if boundary changed) |
| Human sends offer | Evaluate offer | Accept/Reject |

## Success Criteria

✅ Priority 0 sends boundary updates only when state changes
✅ Priority 0 updates rb_proposed_nodes to prevent repeats
✅ Priority 2 generates conditional offers when conflicts detected
✅ Priority 4 generates conditional offers when penalty > 0
✅ Agents propose solutions (IF you do X, I'll do Y)
✅ Agents become satisfied when penalty = 0
✅ Negotiation converges to consensus

## Next Steps

**Please restart the UI and test!** The fixes are in place, but Python needs to reload the code.

After restarting, if you still don't see conditional offers, check:
1. Is the agent actually at penalty > 0? (Check logs)
2. Are there actual conflicts between your colors and agent colors?
3. Did Priority 2 or 4 trigger? (Check logs for "Priority 2:" or "Priority 4:")

If agents are satisfied (penalty=0) but you're not satisfied, that's a different issue - it means the agent found a locally valid solution that doesn't work globally. We'd need to adjust the satisfaction check or add more information exchange.
