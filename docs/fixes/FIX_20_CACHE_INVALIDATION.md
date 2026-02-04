# FIX #20: Feasibility Cache Premature Invalidation

## Date: 2026-02-04

## Problem

After accepting a feasibility response, the agent still has conflicts (penalty > 0) even though the feasibility check said penalty=0.

## Root Cause

The feasibility cache was being invalidated prematurely in `step()` BEFORE the human clicked the button to apply the configuration.

### Timeline of the Bug

1. Human asks: "Can h1=blue?" (h1 is currently red)
2. Agent checks feasibility with h1=blue, finds penalty=0
3. Agent caches solution: `rb_feasibility_solution = {'a1': 'green', 'a2': 'red', 'a3': 'blue', 'a4': 'green', 'a5': 'blue'}`
4. Agent caches key: `rb_feasibility_key = frozenset({('h1', 'blue')})`
5. Agent responds: "Yes, feasible if h4=red"
6. **BUG**: Agent's `step()` is called (regular iteration)
7. **BUG**: In `step()`, lines 136-166 check if cache is still valid
8. **BUG**: Checks if h1==blue in current neighbour_assignments
9. **BUG**: h1 is still red (human hasn't clicked button yet!)
10. **BUG**: Cache is invalidated and cleared
11. Human clicks "✓ Set h4=red" button
12. Human applies h1=blue, h4=red
13. Human sends `__ANNOUNCE_CONFIG__`
14. Agent receives announcement
15. **FIX #17 can't run**: Cache is already gone (`rb_feasibility_key is None`)
16. Agent recomputes using greedy algorithm
17. Agent finds different solution with penalty=20 (not the cached maxsum solution with penalty=0)

### Evidence from Logs

```
[RB Feasibility] Cached solution: {'a1': 'green', 'a2': 'red', 'a3': 'blue', 'a4': 'green', 'a5': 'blue'}
[RB Feasibility] Cached key: frozenset({('h1', 'blue')})
[RB Feasibility] Cache invalidated - human conditions changed  <-- PREMATURE!
[RB Feasibility] Cached key: frozenset({('h1', 'blue')})
[RB Feasibility] Current key: frozenset({('h1', 'red')})  <-- h1 still red, human hasn't clicked yet!

... later ...

[RB Phase] Received __ANNOUNCE_CONFIG__ from Human
[RB Phase] Neighbour assignments: {'h1': 'blue', 'h4': 'red'}  <-- h1 is NOW blue!
[RB Phase] Current assignments: {'a1': 'green', 'a2': 'blue', 'a3': 'red', 'a4': 'green', 'a5': 'red'}
[RB Phase] Current penalty: 20.0  <-- WRONG! Should be 0!
```

Notice:
- Cached solution: `a2=red, a3=blue, a5=blue` → penalty=0
- Actual solution: `a2=blue, a3=red, a5=red` → penalty=20
- Cache was cleared before human applied config

## The Fix

**File**: `agents/rule_based_cluster_agent.py`
**Lines**: 135-169

**Changed**: Removed cache checking/invalidation from `step()` method

**Rationale**: The cache should persist until `__ANNOUNCE_CONFIG__` is received, where we can definitively check if the human applied the feasibility conditions. Checking in `step()` causes premature invalidation before the human makes their decision.

### Before (lines 135-169):
```python
# Match based on the specific human conditions that were validated, not full neighbor state
if (self.rb_feasibility_solution is not None and
    self.rb_feasibility_key is not None):

    # Extract current state of the nodes that were in the feasibility query
    feasibility_nodes = {node for node, color in self.rb_feasibility_key}
    current_key_state = frozenset(...)

    if current_key_state == self.rb_feasibility_key:
        # Use cached solution
        new_assignment = dict(self.rb_feasibility_solution)
    else:
        # Clear stale cache  <-- THIS WAS THE BUG!
        self.rb_feasibility_solution = None
        self.rb_feasibility_neighbors = None
        self.rb_feasibility_key = None
        new_assignment = self.compute_assignments()
else:
    new_assignment = self.compute_assignments()
```

### After (lines 135-145):
```python
# FIX #20: Don't check/invalidate feasibility cache here in step()
# The cache should persist until __ANNOUNCE_CONFIG__ is received, where we can
# definitively check if the human applied the feasibility conditions or not.
# Checking here causes premature invalidation before the human clicks the button.
#
# The cache will be properly checked and applied in __ANNOUNCE_CONFIG__ handler (lines 1339-1372)
# where we have the human's final decision.

# Just compute normally - if there's a valid cache, __ANNOUNCE_CONFIG__ will handle it
new_assignment = self.compute_assignments()
```

## How It Works Now

1. Human asks: "Can h1=blue?"
2. Agent caches maxsum solution with penalty=0
3. Agent's `step()` continues normally (cache is NOT checked or cleared)
4. Human clicks "✓ Set h4=red" button
5. Human applies h1=blue, h4=red
6. Human sends `__ANNOUNCE_CONFIG__`
7. Agent receives announcement in `__ANNOUNCE_CONFIG__` handler (lines 1293+)
8. **FIX #17 runs** (lines 1339-1372): Checks if cache is still valid
9. h1==blue matches cached key → cache is valid!
10. Agent applies cached solution: `{'a1': 'green', 'a2': 'red', 'a3': 'blue', 'a4': 'green', 'a5': 'blue'}`
11. Agent penalty = 0
12. Agent reports satisfaction via FIX #18
13. Both sides satisfied!

## Testing

### Expected Behavior

1. `python launch_menu.py` → RB mode
2. Pick colors with conflicts
3. Announce configuration
4. Agent sends conditional offer: "IF h1=green THEN ..."
5. Send feasibility query: "Can h1=blue instead?"
6. Agent responds: "Yes, feasible if h4=red"
7. Click "✓ Set h4=red" button ONCE
8. **Check graph**: All edges should be gray (no conflicts!)
9. **Check console**:
   ```
   [RB Phase FIX #17] Human accepted feasibility response - applying cached solution
   [RB Phase FIX #17] Applied: a2: blue -> red (locked)
   [Satisfaction FIX #18] Achieved satisfaction despite incomplete proposed_nodes (penalty=0, solution is valid)
   ```
10. **Check debug panel**: Penalty should be 0

### Log Signatures

**Cache created**:
```
[RB Feasibility] Cached solution: {...}
[RB Feasibility] Cached key: frozenset({('h1', 'blue')})
```

**Cache NOT invalidated in step()** (absence of this line):
```
[RB Feasibility] Cache invalidated - human conditions changed
```

**Cache applied in __ANNOUNCE_CONFIG__**:
```
[RB Phase FIX #17] Human accepted feasibility response - applying cached solution
[RB Phase FIX #17] Current assignments: {...}
[RB Phase FIX #17] Cached solution: {...}
[RB Phase FIX #17] Applied: a2: blue -> red (locked)
[RB Phase FIX #17] New assignments: {...}
[RB Phase FIX #17] Feasibility solution applied - keeping cache for next iteration
```

**Satisfaction achieved**:
```
[Satisfaction FIX #18] Achieved satisfaction despite incomplete proposed_nodes (penalty=0, solution is valid)
```

## Related Fixes

- **FIX #17**: UI removes feasibility query from display after button click
- **FIX #18**: Agent reports satisfaction when penalty=0
- **FIX #19**: Feasibility response includes all required sender nodes, no proactive offer
- **FIX #20**: Don't invalidate cache prematurely in step()

All four fixes work together to make feasibility acceptance work correctly:
- FIX #19: Agent sends correct required_assignments
- User clicks button
- FIX #17: UI removes query, applies config, announces
- FIX #20: Cache persists until announcement
- FIX #17 (in __ANNOUNCE_CONFIG__): Cached solution is applied
- FIX #18: Agent reports satisfaction with penalty=0

## Edge Cases

1. **Human changes mind**: If human doesn't click the button and instead changes colors manually, the cache will be invalidated in __ANNOUNCE_CONFIG__ when it detects different conditions

2. **Multiple feasibility queries**: Each new query overwrites the previous cache - only the most recent is kept

3. **Cache across iterations**: Cache persists across multiple step() calls until invalidated by announcement

## Integration Notes

- No breaking changes
- Cache lifetime extended from "until next step()" to "until __ANNOUNCE_CONFIG__"
- Simpler logic: cache management centralized in __ANNOUNCE_CONFIG__
- Better UX: feasibility acceptance actually works!

## Files Modified

- `agents/rule_based_cluster_agent.py`: Lines 135-145 (removed premature cache invalidation)

## Rollback

If issues occur:
```bash
git diff agents/rule_based_cluster_agent.py
# Revert lines 135-145 to restore cache checking in step()
```

System will revert to checking cache in every step() call, which causes premature invalidation.
