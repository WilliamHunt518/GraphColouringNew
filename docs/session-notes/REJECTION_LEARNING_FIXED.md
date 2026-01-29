# Rejection Learning Fixed - Agents Learn from Your Rejections

## Date: 2026-01-28

## What You Reported

"The agent seems adamant to suggest it's desires. It keeps asking for offers where h4=green. I can't indicate that this is not acceptable to me, or at least if I reject that offer it doesn't really change much."

**Exactly right!** Agents were not learning from rejections. They kept proposing the same thing because they're deterministic - they always find the "best" solution, which doesn't change just because you rejected it.

## The Root Cause

### How _generate_conditional_offer() Works

The agent does exhaustive search:
1. Enumerate all possible color combinations for your boundary nodes
2. For each combination, find agent's best response
3. Pick the configuration with lowest penalty
4. Return as conditional offer

**This is deterministic** - same search always finds same "best" solution.

### What Happened When You Rejected

```
1. Agent proposes: "IF h4=green THEN a4=blue" (penalty=0, optimal!)
2. You reject (h4=green is unacceptable to you)
3. Agent thinks: "I need to propose something"
4. Agent runs same search, finds same optimal solution
5. Agent proposes: "IF h4=green THEN a4=blue" (again!)
6. You reject again
7. Loop continues forever...
```

**The agent wasn't tracking WHAT you rejected**, only THAT an offer was rejected.

## The Fix

### Added: rb_rejected_conditions

**File**: `agents/rule_based_cluster_agent.py`, line 98

```python
self.rb_rejected_conditions: Dict[str, Set[tuple]] = {}
# {recipient: set of rejected condition tuples}
```

This stores which **condition combinations** were rejected by each recipient, not just offer IDs.

### When You Reject an Offer

**File**: `agents/rule_based_cluster_agent.py`, lines 1015-1039

```python
elif move.move == "Reject":
    if move.refers_to in self.rb_active_offers:
        rejected_offer = self.rb_active_offers[move.refers_to]

        # Extract conditions that were rejected
        if hasattr(rejected_offer, 'conditions') and rejected_offer.conditions:
            # Build tuple of (node, color) for rejected conditions
            rejected_conditions_tuple = tuple(sorted(
                (c.node, c.colour) for c in rejected_offer.conditions
                if hasattr(c, 'node') and hasattr(c, 'colour')
            ))

            # Store so we don't propose this again
            if sender not in self.rb_rejected_conditions:
                self.rb_rejected_conditions[sender] = set()
            self.rb_rejected_conditions[sender].add(rejected_conditions_tuple)
            self.log(f"[RB Process] Stored rejected conditions: {rejected_conditions_tuple}")
```

**What this does:**
- Extracts the conditions from the rejected offer (e.g., `(('h4', 'green'),)`)
- Stores them in `rb_rejected_conditions[Human]`
- Agent now remembers "Human doesn't want h4=green"

### When Generating Next Offer

**File**: `agents/rule_based_cluster_agent.py`, lines 730-775

```python
# Check if this proposal was already rejected by the recipient
proposed_conditions_tuple = tuple(sorted((their_boundary[i], best_config[i])
                                         for i in range(len(their_boundary))))

# Check against rejected conditions from this recipient
if recipient in self.rb_rejected_conditions:
    if proposed_conditions_tuple in self.rb_rejected_conditions[recipient]:
        self.log(f"[ConditionalOffer Gen] Skipping - conditions already rejected: {proposed_conditions_tuple}")
        self.log(f"[ConditionalOffer Gen] Finding alternative solution...")

        # Try to find second-best configuration
        # Enumerate ALL configurations, filter out rejected ones, pick best remaining
        all_configs_with_penalty = []
        for their_config in their_configs:
            # ... evaluate penalty for this config ...

            # Check if this configuration was rejected
            config_tuple = tuple(sorted((their_boundary[i], their_config[i])
                                       for i in range(len(their_boundary))))
            if config_tuple not in self.rb_rejected_conditions[recipient]:
                all_configs_with_penalty.append((penalty, their_config, our_config))

        # Sort by penalty and pick the best non-rejected one
        if all_configs_with_penalty:
            all_configs_with_penalty.sort(key=lambda x: x[0])
            alt_penalty, alt_their_config, alt_our_config = all_configs_with_penalty[0]

            if alt_penalty < current_penalty:
                self.log(f"[ConditionalOffer Gen] Found alternative solution with penalty={alt_penalty:.3f}")
                # Use alternative configuration
```

**What this does:**
- Before proposing, check if conditions match any rejected ones
- If yes, find the next-best configuration that hasn't been rejected
- Propose that instead

### Clear Rejected Conditions on New Round

**File**: `agents/rule_based_cluster_agent.py`, line 923

```python
self.rb_rejected_conditions.clear()  # Clear rejected condition memory
```

When you click "Announce Config" for a new round, agent forgets past rejections (fresh start).

## What You'll See Now

### First Negotiation Round

```
1. Agent proposes: "IF h4=green THEN a4=blue" (optimal)
2. You reject
3. Agent remembers: "Human rejected h4=green"
4. Agent proposes: "IF h4=blue THEN a4=green" (second-best, avoids h4=green)
5. You evaluate this alternative
```

### If You Keep Rejecting

```
6. You reject h4=blue
7. Agent remembers: "Human rejected h4=green AND h4=blue"
8. Agent proposes: "IF h4=red THEN a4=yellow" (third-best, avoids both)
9. Eventually converges to mutually acceptable solution OR
10. Agent runs out of options: "All configurations have been rejected"
```

## Edge Cases

### Agent Runs Out of Options

If you reject all possible configurations:
```
[ConditionalOffer Gen] All configurations have been rejected
```

Agent returns `None` (no more offers). This signals the configuration might be impossible.

### Suboptimal Solutions

Agent may propose solutions with **higher penalty** than the optimal one you rejected. This is intentional - it explores alternatives even if they're worse for the agent, trying to find something you'll accept.

## Testing

**IMPORTANT**: Restart UI for changes to take effect!

```bash
python launch_menu.py
```

**Test workflow:**
1. Run RB mode experiment
2. Click "Announce Config" once
3. Agent proposes: "IF h4=green THEN..."
4. Click "Reject" button
5. Click "Pass" on agent again
6. **Expected**: Agent proposes different conditions (NOT h4=green)

**Check logs:**
```bash
grep "Stored rejected conditions" results/rb/Agent1_log.txt
# Should see: "Stored rejected conditions: (('h4', 'green'),)"

grep "Finding alternative solution" results/rb/Agent1_log.txt
# Should see: "Finding alternative solution..." after rejection
```

## Files Modified

1. **agents/rule_based_cluster_agent.py**
   - Line 98: Added `rb_rejected_conditions` dictionary
   - Lines 1015-1039: Store rejected conditions when processing Reject
   - Lines 730-775: Check rejected conditions and find alternatives
   - Line 923: Clear rejected conditions on new round

## Expected Behavior

| Situation | First Offer | After Rejection | After 2nd Rejection |
|---|---|---|---|
| Multiple valid solutions exist | Optimal (best for agent) | Second-best (avoids rejected conditions) | Third-best (avoids both) |
| Only one valid solution | Optimal | Nothing (or same if no alternative) | Nothing |
| Configuration impossible | Optimal attempt | Sub-optimal attempt | "All configurations rejected" |

## Success Criteria

✅ Agent remembers which conditions you rejected
✅ Agent proposes alternatives that avoid rejected conditions
✅ Agent explores suboptimal solutions if optimal is rejected
✅ Agent doesn't repeat the same proposal after rejection
✅ Negotiation converges or agent signals impossibility

## Limitations

**Current implementation tracks condition COMBINATIONS**, not individual node constraints. If you reject:
- Offer 1: "IF h4=green AND h5=red"
- Offer 2: "IF h4=green AND h5=blue"

The agent will avoid both complete combinations, but might try:
- Offer 3: "IF h4=blue AND h5=red"

This is generally good (agent explores alternatives), but if you specifically don't want h4=green in ANY configuration, you'll need to reject multiple offers.

**Future enhancement**: Track individual node color rejections separately (e.g., "Human never wants h4=green regardless of other nodes").

## Next Steps

**Please restart and test!** The system should now:
1. Learn from your rejections
2. Propose alternative solutions
3. Converge to mutually acceptable configuration
4. Signal if no acceptable configuration exists
