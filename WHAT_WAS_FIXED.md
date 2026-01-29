# What Was Fixed: Agent2 Getting Stuck

## The Problem You Saw

Agent2 (b) would send a proposal/offer early on, and then just... wait. Forever. Even when there were still conflicts to resolve, the agent wouldn't ask for any more changes or send new offers. It looked like the agent had given up.

## What Was Actually Happening

Under the hood:

1. Agent2 sent an offer like: "If you set h2=red and h5=blue, I'll set b2=green"
2. You (the human) were busy negotiating with Agent1 and didn't respond to Agent2
3. Agent2 was being "polite" - it didn't want to spam you with offers, so it waited for a response
4. That wait became permanent, and Agent2 stopped trying to help solve the problem

Think of it like texting someone who leaves you on "read" - Agent2 was stuck waiting for a reply that never came.

## The Fix

**Offer Expiry**: Now, if Agent2 doesn't get a response to an offer after **5 turns**, the offer "expires" and the agent can move on. It's like saying "Well, they must not be interested in that offer, let me try something else."

## What Changed in the UI

### In the Console Logs
You'll now see clearer messages like:
```
[RB Move Gen] ⏳ Waiting for response before generating new offers (offers expire after 5 iterations)
[RB Expiry] Offer offer_XXX expired after 5 iterations - allowing new offers
```

### In the Debug Window
When you click "Debug", the info panel now shows:
```
--- RB Protocol State ---
Phase: bargain, Iteration: 12, Satisfied: False

Pending offers WE sent (waiting for response):
  • offer_1234_Agent2 (age: 3 iter, 2 cond, 1 assign)
  ⚠ Agent is waiting for response - may block new offers!
```

This makes it crystal clear:
- What phase the agent is in
- What offers are pending
- How old each offer is (age in iterations)
- Warning if the agent is blocked

## How to Use This

1. **Run your experiment normally** - nothing changes in how you use the system

2. **If an agent seems stuck**, open the Debug window:
   - Select the stuck agent from the dropdown
   - Look at "RB Protocol State"
   - Check if there are old pending offers

3. **The agent will auto-recover** - after 5 iterations, old offers expire automatically

4. **Adjust if needed** - the 5-iteration threshold can be changed in the code if you need different timing

## Why 5 Iterations?

- **Not too fast**: Gives you time to read and consider offers
- **Not too slow**: Prevents long deadlocks
- **Tunable**: You can change this number in `agents/rule_based_cluster_agent.py` if needed

## Testing

I created a test (`test_offer_expiry.py`) that confirms:
- Offers age correctly
- Expiry happens at the right time
- Agent can generate new offers after expiry

Run it with: `python test_offer_expiry.py`

## Bottom Line

**Before**: Agent2 could get permanently stuck waiting for a response
**After**: Agent2 waits 5 turns, then moves on and tries new offers
**Result**: Smoother negotiations, fewer deadlocks, clearer debug info

---

# Latest Fix (2026-01-29): Two Critical Improvements

## 1. Fixed: Rejected Offers Still Blocking New Offers

### The Problem
The offer expiry system was in place, but **rejected offers** were still counting as "pending" and blocking new offer generation. So if you explicitly rejected an offer (clicked "Reject"), Agent2 would still think "I have a pending offer" and stay silent.

### The Fix
Added `rb_rejected_offers` check to the pending offer filter in two places:

**agents/rule_based_cluster_agent.py:479, 507**
```python
my_offers = [
    oid for oid in self.rb_active_offers.keys()
    if self.name in oid
    and oid not in self.rb_accepted_offers
    and oid not in self.rb_rejected_offers  # ✅ NEW: Exclude rejected offers
    and not oid.startswith("update_")
    and not oid.startswith("config_")
]
```

**Result**: Rejected offers no longer block new offer generation.

## 2. Fixed: Agent Goes Silent When It Can't Improve Alone

### The Problem
Agent2 had penalty=20 but could only improve if the human ALSO changed their colors. The agent's penalty threshold required improvement (`current_penalty - 0.01`), so it couldn't make coordination offers at the same penalty. Result: Agent went silent even though conflicts existed.

### The Fix
Relaxed penalty threshold when conflicts exist:

**agents/rule_based_cluster_agent.py:816-845**
```python
has_conflicts = current_penalty > 0.0

if has_conflicts:
    # Accept same-penalty offers when coordination is needed
    penalty_threshold = current_penalty  # ✅ Allow same penalty
    self.log("Conflicts present - allowing coordination offers")
else:
    # Normal case: require improvement
    penalty_threshold = current_penalty - 0.01
```

**Result**: Agent proposes coordination solutions even when it can't improve penalty alone.

## 3. Bonus: Human-Initiated Custom Offers

### New Feature
You can now propose custom conditions on agent's boundary nodes, not just select from their offers.

**ui/human_turn_ui.py: Conditional Builder**
- Toggle "Custom" checkbox to enter custom conditions
- Select any of the agent's boundary nodes
- Specify what color you want them to use
- Send "If you do X, I'll do Y" with your own X

**Result**: More flexible negotiation - you can lead the conversation, not just react.

## Visual Summary

### Before This Fix
```
Agent2 sends offer → You reject it
          ↓
Agent checks pending offers → sees rejected offer in active list
          ↓
"Already have pending offers" → STOPS
          ↓
Agent freezes 🥶
```

### After This Fix
```
Agent2 sends offer → You reject it
          ↓
Agent checks pending offers → excludes rejected offers
          ↓
No pending offers → Generate new offer
          ↓
Has conflicts? → Allow same-penalty coordination offer
          ↓
Agent continues negotiating 🎯
```

## Complete Fix Timeline

| Date | Fix | Impact |
|------|-----|--------|
| **Earlier** | Offer expiry (5 iterations) | Expired offers no longer block |
| **2026-01-29** | Exclude rejected offers | Rejected offers no longer block |
| **2026-01-29** | Allow same-penalty coordination | Agent proposes solutions even without solo improvement |
| **2026-01-29** | Custom condition entry | Human can initiate custom offers |

## Testing the Latest Fixes

### Test 1: Rejected Offers
```bash
1. Start RB experiment
2. Agent2 sends offer
3. Click "Reject" on Agent2's offer
4. Wait 2-3 iterations
5. Check: Does Agent2 send a new offer? ✅
```

### Test 2: Coordination Offers
```bash
1. Start RB experiment
2. Get to a state where Agent2 has penalty=20
3. Check Agent2's log for: "Generating coordination offer"
4. Verify: Agent2 continues proposing solutions ✅
```

### Test 3: Custom Conditions
```bash
1. Start RB experiment
2. Click "Build Conditional Offer" for Agent2
3. Add condition row, check "Custom"
4. Select agent boundary node + color
5. Add your assignment
6. Send and verify agent processes it ✅
```

## Bottom Line (Updated)

**Before**:
- Rejected offers blocked new offers (even after fix #1)
- Agent went silent when it couldn't improve alone
- Human could only react to agent's offers

**After**:
- Rejected offers properly excluded from blocking check
- Agent proposes coordination when penalty > 0
- Human can initiate custom offers on agent nodes

**Result**: Much more robust negotiation with fewer deadlocks and more flexibility
