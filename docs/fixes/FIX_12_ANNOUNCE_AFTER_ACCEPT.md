# FIX #12: Send __ANNOUNCE_CONFIG__ After Accepting Offers

## The Bug

When the user accepts a conditional offer in RB mode, the UI automatically changes the human's node colors to fulfill the conditions. However, **the agents are never notified of these color changes**.

### What Was Happening

1. User accepts Agent2's offer: "If h2=red AND h5=green then b2=blue"
2. UI changes h2 from blue to red (automatically)
3. UI redraws the graph
4. UI sends Accept message to Agent2
5. Agent2 locks b2=blue and marks it as proposed (fix #11)
6. **BUG: Agent2 is NEVER notified that h2 changed from blue to red**
7. Agent2's `neighbour_assignments` still has old value: h2=blue
8. Agent2 computes penalty with stale neighbor colors → penalty=10.000
9. Agent2 NOT satisfied

### The Root Cause

The committed version of `ui/human_turn_ui.py::_accept_offer()` (lines 1960-2000) only:
1. Changes human assignments
2. Redraws graph
3. Marks offer as accepted
4. Sends Accept message

It **does not send `__ANNOUNCE_CONFIG__`** to notify agents of the color changes.

## The Fix

Added code to `ui/human_turn_ui.py::_accept_offer()` after sending the Accept message (around line 2045):

```python
# CRITICAL FIX #12: Notify agents when human fulfills conditions
# When accepting an offer, agents need to know the human's colors changed!
# Without this, agents see stale neighbour_assignments and have penalty>0.
if changed_nodes or sender:
    # Determine which neighbors are affected by the changed nodes
    affected_neighbors = set()

    if changed_nodes:
        affected_neighbors = set(self._get_affected_neighbors([node for node, _ in changed_nodes]))

    # ALWAYS include the sender of the offer (they need to know their offer was accepted)
    if sender and sender in self._neighs:
        affected_neighbors.add(sender)

    if affected_neighbors:
        print(f"[Human Accept] Notifying {list(affected_neighbors)} of color changes: {[node for node, _ in changed_nodes]}")

        for n in affected_neighbors:
            def _send_announcement(neigh=n):
                try:
                    import inspect
                    sig = inspect.signature(self._on_send)
                    if len(sig.parameters) >= 3:
                        # New signature with current_assignments
                        self._on_send(neigh, "__ANNOUNCE_CONFIG__", dict(self._assignments))
                    else:
                        # Old signature without current_assignments
                        self._on_send(neigh, "__ANNOUNCE_CONFIG__")
                except Exception as e:
                    print(f"[Human Accept ERROR] Failed to notify {neigh}: {e}")
                    import traceback
                    traceback.print_exc()

            threading.Thread(target=_send_announcement, daemon=True).start()
```

## How It Works Now

1. User accepts Agent2's offer: "If h2=red AND h5=green then b2=blue"
2. UI changes h2 from blue to red
3. UI adds (h2, red) to `changed_nodes` list
4. UI sends Accept message to Agent2
5. **NEW: UI sends `__ANNOUNCE_CONFIG__` to Agent2**
6. Agent2 receives `__ANNOUNCE_CONFIG__`
7. Agent2 updates `neighbour_assignments` with h2=red (via `_sync_neighbour_views` in simulation)
8. Agent2 recomputes penalty with new neighbor colors → penalty=0.000
9. Agent2 becomes satisfied ✓

## Testing

To test this fix:

1. Launch RB mode UI
2. Set human colors: h1=red, h2=blue, h3=green, h4=red, h5=green
3. Click "Announce Configuration"
4. Agent2 will offer: "If h2=red AND h5=green then b2=blue"
5. Click "Accept" on Agent2's offer
6. **Watch for log message**: `[Human Accept] Notifying ['Agent2'] of color changes: ['h2']`
7. **Check communication log**: Should see `__ANNOUNCE_CONFIG__` after the Accept message
8. Agent2 should become satisfied (satisfied: True in debug info)

## Files Modified

- `ui/human_turn_ui.py` - Added `__ANNOUNCE_CONFIG__` sending logic after accepting offers (lines ~2045-2075)

## Related Fixes

This fix works in conjunction with:
- **Fix #11**: Mark accepted assignments as proposed to sender (agents/rule_based_cluster_agent.py:1607-1610)
- Both fixes are necessary for agents to become satisfied after acceptance

## Summary

**Problem**: Agents not satisfied after user accepts offers because they see stale neighbor colors

**Solution**: Send `__ANNOUNCE_CONFIG__` to notify agents when user fulfills conditions by changing colors

**Result**: Agents update their `neighbour_assignments`, recompute penalty, and become satisfied

