# FIX #13: Initialize _adjacency Dictionary

## The Bug

When clicking "Choose This" on feasibility results or "Accept" on conditional offers, the UI crashed with:

```
AttributeError: 'HumanTurnUI' object has no attribute '_adjacency'
```

This prevented Fix #12 from working because it needs to determine which neighbors are affected by color changes.

## Root Cause

Fix #12 added calls to `_get_affected_neighbors()` which relies on `self._adjacency` to determine which nodes are adjacent. However, `_adjacency` was never initialized in the UI.

## The Fix

Added initialization of `_adjacency` in `ui/human_turn_ui.py::run_async_chat()` right after `_edges` is set:

```python
# Build adjacency dictionary for determining affected neighbors
self._adjacency = {}
for u, v in self._edges:
    self._adjacency.setdefault(u, set()).add(v)
    self._adjacency.setdefault(v, set()).add(u)
```

**Location**: `ui/human_turn_ui.py` lines ~248-252 (after `self._edges` assignment)

## How It Works

1. When `run_async_chat()` is called, it receives the graph edges
2. We build a bidirectional adjacency dictionary mapping each node to its neighbors
3. Later, when the user accepts an offer or applies feasibility conditions:
   - `_get_affected_neighbors()` uses `_adjacency` to find which nodes are adjacent to the changed nodes
   - It determines which agents own those adjacent nodes
   - Fix #12 sends `__ANNOUNCE_CONFIG__` to those affected agents

## Impact

This fix enables Fix #12 to work correctly:
- Accepting offers now properly notifies affected agents
- Applying feasibility conditions now properly notifies affected agents
- Agents receive `__ANNOUNCE_CONFIG__` and update their view of human's colors
- Agents can become satisfied after human fulfills conditions

## Files Modified

- `ui/human_turn_ui.py` (~line 248): Added `_adjacency` initialization

## Related Fixes

- **Fix #12**: Send `__ANNOUNCE_CONFIG__` after accepting offers (depends on this fix)
- Both fixes are necessary for agents to become satisfied

## Testing

With this fix, the workflow now works without crashes:
1. Ask feasibility query
2. Click "Choose This" → No crash, colors change, agents notified ✓
3. Accept conditional offer → No crash, colors change, agents notified ✓
4. Agents receive `__ANNOUNCE_CONFIG__` and become satisfied ✓
