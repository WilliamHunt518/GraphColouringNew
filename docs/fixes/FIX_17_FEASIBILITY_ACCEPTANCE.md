# Fix #17: Agents Don't Apply Feasibility Solutions When User Accepts

## Problem

When user clicks **"any configuration works"** button after a feasibility query, they're accepting the agent's feasibility response. However, agents weren't applying the solution they calculated.

### User Workflow

1. User asks: "Can I set h1=blue?"
2. Agent responds: "✓ Feasible if h4=red" (internally calculates and caches working solution)
3. User clicks **"any configuration works"** → accepts this, applies h1=blue, h4=red
4. **Expected**: Agent applies the solution it calculated
5. **Actual**: Agent discards solution, penalty remains high

### Root Cause

**Location**: `agents/rule_based_cluster_agent.py` lines 1327-1330 (before fix)

When `__ANNOUNCE_CONFIG__` arrives (triggered by "any configuration works" button):

```python
# ADD: Clear feasibility cache on config change
self.rb_feasibility_solution = None  # ← DELETES the cached solution!
self.rb_feasibility_neighbors = None
self.rb_feasibility_key = None
```

This **unconditionally clears** the feasibility cache, even when the human accepted the exact configuration the agent validated!

### The Bug Chain

1. User sends feasibility query for h1=blue
2. Agent runs exhaustive search, finds solution with h1=blue, h4=red
3. Agent **caches solution** in `rb_feasibility_solution` (line 1738)
4. Agent responds "Yes, feasible if h4=red"
5. User clicks "any configuration works" → applies h1=blue, h4=red
6. UI sends `__ANNOUNCE_CONFIG__` to agent
7. Agent receives `__ANNOUNCE_CONFIG__` → **CLEARS cached solution** ✗
8. Agent steps → no cached solution → computes NEW random assignments
9. New assignments might not match → penalty stays high

## Solution

**Fix #17**: Only clear feasibility cache if human changed to a DIFFERENT configuration

**Location**: `agents/rule_based_cluster_agent.py` lines 1324-1350

```python
# FIX #17: Only clear feasibility cache if human's config CHANGED
# If they accepted our feasibility response, preserve the solution!
if self.rb_feasibility_key is not None:
    # Check if human's new config matches our cached feasibility key
    feasibility_nodes = {node for node, color in self.rb_feasibility_key}
    current_key_state = frozenset(
        (node, self.neighbour_assignments.get(node))
        for node in feasibility_nodes
        if node in self.neighbour_assignments
    )

    if current_key_state == self.rb_feasibility_key:
        # Human accepted our feasibility response - KEEP the cached solution!
        self.log(f"[RB Phase FIX #17] Preserving feasibility cache - human accepted our response")
        self.log(f"[RB Phase FIX #17] Cached solution will be applied: {self.rb_feasibility_solution}")
    else:
        # Human changed to different config - clear cache
        self.log(f"[RB Phase FIX #17] Clearing feasibility cache - human changed config")
        self.rb_feasibility_solution = None
        self.rb_feasibility_neighbors = None
        self.rb_feasibility_key = None
else:
    # No cached solution anyway
    self.rb_feasibility_solution = None
    self.rb_feasibility_neighbors = None
    self.rb_feasibility_key = None
```

## Expected Behavior After Fix

### Scenario: User Accepts Feasibility Response

**Before Fix #17**:
1. User: "Can I set h1=blue?"
2. Agent: "✓ Yes if h4=red" (caches solution internally)
3. User clicks "any configuration works"
4. Agent: **Clears cache**, computes random assignments
5. Penalty: **Stays high** ✗

**After Fix #17**:
1. User: "Can I set h1=blue?"
2. Agent: "✓ Yes if h4=red" (caches solution internally)
3. User clicks "any configuration works"
4. Agent: **Keeps cache**, applies validated solution
5. Penalty: **Goes to 0.000** ✓

### Scenario: User Changes Mind After Query

**Behavior (unchanged)**:
1. User: "Can I set h1=blue?"
2. Agent: "✓ Yes if h4=red" (caches solution with h1=blue, h4=red)
3. User clicks different config → h1=red, h4=blue (different!)
4. Agent: Detects mismatch, clears cache ✓
5. Agent: Computes new solution for new config ✓

## How It Works

The fix compares the **cached feasibility key** with the **current neighbor state**:

- **Cached key**: `frozenset({('h1', 'blue'), ('h4', 'red')})` (from feasibility check)
- **Current state**: Extracted from `neighbour_assignments` after announcement
- **Match**: Human accepted our response → keep cache
- **Mismatch**: Human changed config → clear cache

## Log Messages

```
[RB Phase FIX #17] Preserving feasibility cache - human accepted our response
[RB Phase FIX #17] Cached solution will be applied: {'a1': 'green', 'a2': 'blue', ...}

[RB Feasibility] Using cached solution from feasibility check
[RB Feasibility] Cached assignments: {'a1': 'green', 'a2': 'blue', ...}
[RB Feasibility] Cache still valid (key matched: frozenset({('h1', 'blue'), ('h4', 'red')}))
```

## Testing

1. Start RB mode
2. Set initial config
3. Send feasibility query: "Can I set h1=blue?"
4. Agent responds: "✓ Feasible if h4=red"
5. Click **"any configuration works"** button
6. **Expected**:
   - Agent applies cached solution from feasibility check
   - Penalty drops significantly or to 0.000
   - Log shows "Preserving feasibility cache"
   - Log shows "Using cached solution"

## Files Modified

- `agents/rule_based_cluster_agent.py`
  - Lines 1324-1350: Fix #17 - preserve feasibility cache when human accepts response

## Impact

This fix completes the feasibility query workflow:
- Users can now ask "what if" questions
- Agents provide validated solutions
- When users accept, agents **actually apply those solutions**
- Result: Cooperative problem-solving through feasibility queries
