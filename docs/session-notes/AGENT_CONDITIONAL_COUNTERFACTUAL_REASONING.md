# Agent Conditional Offers: Counterfactual Reasoning Implementation

## Problem

User reported: "I'm yet to see an agent make a conditional offer. They should be able to do this. Maybe for example they look at proposals and preset configurations given the proposals. Something argumentation typical"

## Root Cause

The original `_generate_conditional_offer()` implementation was too passive:
- Just mirrored the current state
- Said "If you keep what I think you have, I'll keep what I have"
- No actual counterfactual reasoning or search for alternatives
- Trigger condition required no conflicts (but conflicts are when you NEED conditionals!)

## Solution: Counterfactual Enumeration

Reimplemented `_generate_conditional_offer()` to do **argumentation-style counterfactual reasoning**:

### Algorithm

```
1. Identify boundary nodes (theirs and ours)
2. Enumerate possible color configurations for THEIR boundary nodes
3. For each configuration:
   a. Assume they adopt that configuration
   b. Find OUR best response (optimal colors for our boundary nodes)
   c. Evaluate combined penalty
4. Select the configuration with lowest penalty (ideally 0)
5. Package as conditional: "If you do X, I'll do Y, and penalty = 0"
```

### Key Features

**Exhaustive Search (for small boundaries):**
- If ≤ 3 boundary nodes per side: enumerate all possible color combinations
- Finds the TRUE optimal configuration

**Heuristic (for large boundaries):**
- If > 3 boundary nodes: use current state as starting point
- Avoids combinatorial explosion

**Zero-Penalty Target:**
- Stops searching when it finds a configuration with penalty = 0
- This is a win-win: no conflicts for either party

**Counterfactual Reasoning:**
- Doesn't just accept current state
- Asks "What if they used different colors?"
- Finds mutually beneficial alternatives

### Example

**Scenario:**
```
Current state:
  Our boundary: h1=red, h4=red
  Their boundary: a2=red, a3=blue
  Penalty: 2.0 (h1 conflicts with a2, h4 conflicts with a2)

Agent enumerates:
  Config 1: a2=blue, a3=yellow → Our response: h1=red, h4=green → Penalty: 0.0 ✓
  Config 2: a2=green, a3=blue → Our response: h1=red, h4=blue → Penalty: 0.0 ✓
  Config 3: a2=red, a3=blue → Our response: h1=green, h4=blue → Penalty: 0.0 ✓
  ...

Agent selects Config 1 (first zero-penalty found):
  ConditionalOffer: "If a2=blue AND a3=yellow, then h1=red AND h4=green"
  Reason: "penalty=0.000, mutual_benefit, counterfactual_reasoning"
```

## Updated Trigger Conditions

**Before:**
```python
if phase in ("proposing", "negotiating") and not changes and not conflicts:
```
- Required NO conflicts → Never triggered when you need it most!

**After:**
```python
if phase in ("proposing", "negotiating"):
    current_penalty = self._compute_local_penalty()
    has_proposals = len(self.rb_proposed_nodes.get(recipient, {})) > 0

    if (current_penalty > 0.0 or has_proposals) and len(boundary_nodes) >= 2:
```

**New conditions:**
- Trigger when penalty > 0 (conflicts exist) OR
- Trigger when proposals have been made
- Still requires 2+ boundary nodes (need something to negotiate)

## Code Changes

### 1. Reimplemented `_generate_conditional_offer()` (lines 547-690)

**Key sections:**

**Enumerate configurations:**
```python
if len(their_boundary) > 3:
    # Heuristic: use current state
    their_configs = [tuple(self.neighbour_assignments.get(n, domain[0]) for n in their_boundary)]
else:
    # Exhaustive: all possible combinations
    their_configs = list(product(domain, repeat=len(their_boundary)))
```

**Find best response:**
```python
for their_config in their_configs:
    hypothetical_neighbors = {...}  # Assume they use this config

    for our_config in our_configs:
        test_assignment = {...}  # Our response
        combined = {**hypothetical_neighbors, **test_assignment}
        penalty = self.problem.evaluate_assignment(combined)

        if penalty < best_penalty:
            best_penalty = penalty
            best_config = their_config
            best_our_assignment = our_config
```

**Only make offer if beneficial:**
```python
if best_config is None or best_penalty >= current_penalty:
    return None  # No better config found
```

### 2. Updated Trigger (lines 367-385)

```python
# Trigger when there ARE conflicts or proposals have been made
if (current_penalty > 0.0 or has_proposals) and len(boundary_nodes) >= 2:
    conditional_offer = self._generate_conditional_offer(recipient)
```

### 3. Added Comprehensive Logging

```python
self.log(f"[ConditionalOffer Gen] Our boundary: {our_boundary}, Their boundary: {their_boundary}")
self.log(f"[ConditionalOffer Gen] Current penalty: {current_penalty:.3f}")
self.log(f"[ConditionalOffer Gen] Enumerating {len(their_configs)} possible configurations")
self.log(f"[ConditionalOffer Gen] Found zero-penalty configuration!")
self.log(f"[ConditionalOffer Gen] Generated offer: {len(conditions)} conditions, {len(assignments)} assignments, penalty={best_penalty:.3f}")
```

## Expected Console Output

When the agent generates a conditional offer, you'll see:

```
[RB Move Gen] Priority 3.5: ConditionalOffer check (penalty=2.000, proposals=True)
[ConditionalOffer Gen] Our boundary: ['h1', 'h4'], Their boundary: ['a2', 'a3']
[ConditionalOffer Gen] Current penalty: 2.000
[ConditionalOffer Gen] Enumerating 16 possible configurations
[ConditionalOffer Gen] Found zero-penalty configuration!
[ConditionalOffer Gen] Generated offer: 2 conditions, 2 assignments, penalty=0.000
[RB Move Gen] -> Generated ConditionalOffer with 2 conditions and 2 assignments
```

Then in chat, the agent sends:
```
ConditionalOffer:
  IF: a2=blue, a3=yellow
  THEN: h1=red, h4=green
  Reason: penalty=0.000, mutual_benefit, counterfactual_reasoning
```

## When Agents Generate Conditionals

**Trigger conditions (all must be met):**
1. Phase is "proposing" or "negotiating" ✓
2. Either:
   - Current penalty > 0 (conflicts exist) OR
   - Proposals have been made
3. At least 2 boundary nodes ✓
4. No existing pending offers from this agent ✓

**Common scenarios:**

**Scenario 1: After initial proposals**
```
Turn 1: Agent: Propose a2=red
Turn 2: Agent: Propose a3=blue
(Phase transitions to "proposing", has_proposals=True)
Turn 3: Agent: ConditionalOffer "If h1=blue AND h4=green, then a2=red AND a3=blue"
```

**Scenario 2: When conflicts detected**
```
Turn 1: Agent: Propose a2=red
Turn 2: You: Commit h1=red (conflicts with a2=red!)
Turn 3: Agent detects penalty > 0
Turn 4: Agent: ConditionalOffer "If h1=blue, then a2=red" (suggests resolution)
```

**Scenario 3: During negotiation**
```
Turn 1-5: Back and forth proposals
(Phase = "negotiating", penalty still > 0)
Turn 6: Agent: ConditionalOffer (tries to package a deal)
```

## Testing

### Test 1: Let Agent Make Proposals First

1. Run program in RB mode
2. Don't send any messages initially
3. Let agent make 2+ proposals
4. **Watch console** for:
   ```
   [RB Move Gen] Priority 3.5: ConditionalOffer check
   [ConditionalOffer Gen] Enumerating X possible configurations
   [ConditionalOffer Gen] Found zero-penalty configuration!
   ```
5. **Check chat** - Agent should send ConditionalOffer
6. **Check sidebar** - Offer appears as incoming (yellow card)

### Test 2: Create a Conflict

1. Run program in RB mode
2. Propose/commit a color that conflicts with agent's boundary node
3. Let agent respond
4. **Watch console** for penalty > 0 detection
5. Agent should generate ConditionalOffer to resolve conflict

### Test 3: Multiple Boundary Nodes

1. Use a graph with 2+ boundary nodes between you and agent
2. Let negotiation proceed
3. Agent should attempt to package multiple nodes into single conditional

### Test 4: Check the Offer Quality

1. When agent sends ConditionalOffer, check the conditions
2. Verify the conditions are actually different from current state
3. Check if penalty would truly be 0 if you accepted

## Comparison: Before vs After

### Before (Passive Mirroring)

```python
# Just take current state
conditions = [what I believe you have now]
assignments = [what I have now]
# Offer: "Keep doing what you're doing, I'll keep doing what I'm doing"
```

**Problems:**
- No search for alternatives
- No argumentation
- Just confirms status quo
- Rarely beneficial

### After (Active Counterfactual Reasoning)

```python
# Enumerate alternatives
for their_config in all_possible_configs:
    for our_config in all_possible_configs:
        if penalty(their_config + our_config) == 0:
            # Found win-win!
            return offer(their_config, our_config)
```

**Benefits:**
- ✅ Searches for better alternatives
- ✅ Finds zero-penalty configurations
- ✅ True argumentation: "If you do X, I can do Y"
- ✅ Maximizes mutual benefit

## Complexity Analysis

**Small boundaries (≤ 3 nodes):**
- Configurations to check: |domain|^(their_nodes + our_nodes)
- For domain size 4, 2 nodes per side: 4^4 = 256 configs
- Very fast, exhaustive search

**Large boundaries (> 3 nodes):**
- Falls back to heuristic (current state only)
- Could be extended to use more sophisticated search (genetic algorithms, etc.)

## Files Modified

- `agents/rule_based_cluster_agent.py`
  - Lines 547-690: Reimplemented `_generate_conditional_offer()` with counterfactual reasoning
  - Lines 367-385: Updated trigger conditions to fire when conflicts exist or proposals made

## Summary

Agents now use **argumentation-style counterfactual reasoning**:
- ✅ Enumerate possible configurations of boundary nodes
- ✅ Find optimal mutual assignments
- ✅ Propose configurations that achieve zero penalty
- ✅ Generate offers when conflicts exist (not avoid them!)
- ✅ True argumentation: "If you do X, I can do Y, and we'll both be satisfied"

The conditional offer generation is now much more intelligent and should trigger frequently in actual negotiations! 🎉
