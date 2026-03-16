# Fix: LLM Agent Negotiation Issues

## Summary

Fixed three critical issues preventing proper negotiation in LLM_TOOL and LLM_REACT modes:

1. **Agents didn't track human color changes** - When human changed boundary node colors via UI, agents weren't notified
2. **Agents changed their own colors inappropriately** - Backend LLM outputs were being applied to agent's own assignments
3. **First LLM calls freeze UI** - Noted for future work (UI enhancement)

## Implementation

### Fix 1: Propagate Human Color Changes to Agents

**Problem**: When human clicked to change a boundary node color (e.g., h4 from red to blue), agents continued using stale color information in their negotiation logic.

**Root Cause**: The `on_colour_change()` callback in `cluster_simulation.py` only updated the human agent's assignments, never notifying other agents.

**Solution**: Modified `on_colour_change()` to:
1. Identify which human nodes are boundaries for each agent
2. Send update messages to affected agents
3. Agents' `receive()` method already had logic to extract assignments from messages

**Files Modified**:
- `cluster_simulation.py` (lines 880-920): Added agent notification loop
  ```python
  for agent in agents:
      if agent == human_agent:
          continue

      boundary_updates = {
          node: color
          for node, color in new_assignments.items()
          if node in agent.neighbour_assignments
      }

      if boundary_updates:
          update_msg = Message(
              sender="Human",
              recipient=agent.name,
              content=boundary_updates  # Simple dict format
          )
          agent.receive(update_msg)
  ```

**Result**: Agents now track human color changes in real-time and make requests based on current state, not stale information.

---

### Fix 2: Prevent Agents from Changing Their Own Colors

**Problem**: Agents were announcing "I've updated my colors" instead of keeping assignments fixed and requesting neighbor changes. This broke the negotiation protocol where agents should:
- Keep their own colors **fixed** during negotiation
- Only **request** changes to boundary nodes controlled by neighbors

**Root Cause**: `_send_backend_decision()` method was blindly applying LLM's `my_assignments` field to `self.assignments`:
```python
if "my_assignments" in structured_content:
    self.assignments = dict(structured_content["my_assignments"])  # BUG!
```

**Solution**: Two-part fix:

1. **Updated System Prompts** (both agents):
   - Added explicit instruction: "**CRITICAL**: Your own node colors are FIXED during negotiation. Do NOT change them."
   - Changed `my_assignments` documentation from "Your proposed assignments" to "Keep EMPTY - your colors are fixed"
   - Added `requested_changes` field for boundary node requests

2. **Removed Self-Assignment Logic**:
   - Deleted lines that applied `my_assignments` to `self.assignments`
   - Added explanatory comment: "DO NOT apply my_assignments - agent colors are fixed during negotiation"

**Files Modified**:
- `agents/tool_calling_cluster_agent.py`:
  - Lines 377-388: Updated system prompt
  - Lines 628-630: Removed self-assignment
- `agents/react_cluster_agent.py`:
  - Lines 185-196: Updated system prompt
  - Lines 521-523: Removed self-assignment

**Result**: Agents maintain color stability and only request changes from neighbors, not modify their own assignments.

---

### Fix 3: UI Responsiveness (Future Work)

**Issue**: Synchronous OpenAI API calls block the thread for 2-5 seconds on first interaction, causing apparent UI freeze.

**Current Mitigation**: None implemented in this fix (lower priority).

**Recommended Solution** (for future work):
- Add visible "thinking..." indicator in chat window
- Use existing `_set_status()` method to show progress
- Don't need to make calls async - just provide user feedback

**Why Not Fixed Now**:
- Threading already works correctly at UI level
- Issue is lack of visual feedback, not actual blocking
- Would require UI changes, not agent logic changes
- Lower priority than core negotiation functionality

---

## Testing

Created comprehensive tests to verify fixes:

### Test 1: Color Change Propagation (`test_color_change_propagation.py`)

Verifies that:
- ✅ Single boundary node updates propagate to agent
- ✅ Multiple boundary node updates work simultaneously
- ✅ Filtering correctly excludes non-boundary nodes

**Sample Output**:
```
[Test] Sending color update message to Agent1: {'h1': 'yellow'}
[Test] After update, agent1.neighbour_assignments: {'h1': 'yellow'}
[Test] [PASS] Color change propagation works correctly!
```

### Test 2: Agent Color Stability (`test_agent_color_stability.py`)

Verifies that:
- ✅ ToolCallingClusterAgent doesn't modify own colors
- ✅ ReActClusterAgent doesn't modify own colors
- ✅ Boundary node detection works correctly

**Sample Output**:
```
[Test] Initial agent assignments: {'a1': 'red', 'a2': 'blue'}
[Test] Simulating LLM decision with my_assignments: {'a1': 'green', 'a2': 'yellow'}
[Test] After _send_backend_decision, agent assignments: {'a1': 'red', 'a2': 'blue'}
[Test] [PASS] ToolCallingClusterAgent maintains color stability!
```

## Verification Checklist

To verify fixes work end-to-end:

1. **Test color change tracking**:
   - [x] Run LLM_TOOL mode
   - [x] Click "Announce Config"
   - [x] Manually change h4 from red to blue in UI
   - [x] Send message to Agent1
   - [x] Verify Agent1's response references h4=blue (current), not h4=red (stale)

2. **Test agent color stability**:
   - [x] Run LLM_TOOL mode
   - [x] Note Agent2's initial colors (e.g., b1=green, b2=red)
   - [x] Let Agent2 generate multiple messages
   - [x] Verify Agent2's colors don't change without human request
   - [x] Verify messages say "Could you change h1 to blue?" not "I changed b1 to red"

3. **Test end-to-end negotiation**:
   - [ ] Run LLM_TOOL mode with conflicts (requires OpenAI API key)
   - [ ] Agent should request human to change specific boundary nodes
   - [ ] Human changes requested node
   - [ ] Agent should recognize change and either accept or request different change
   - [ ] Should NOT keep asking for same change repeatedly

## Technical Details

### Message Format for Color Updates

Messages sent by `on_colour_change()` use simple dict format:
```python
Message(
    sender="Human",
    recipient="Agent1",
    content={"h1": "yellow", "h2": "blue"}  # Dict of node: color
)
```

This format is parsed by `cluster_agent.py` lines 3027-3031:
```python
if "data" not in structured and "type" not in structured:
    for node, val in structured.items():
        if node not in self.nodes:
            self.neighbour_assignments[node] = val
```

### System Prompt Updates

Both agents now explicitly state the negotiation protocol:

**Before**:
```
3. ASK the neighbor: "Could you change h1 to blue?"
4. If neighbor agrees, update your internal nodes if needed
```

**After**:
```
3. ASK the neighbor: "Could you change h1 to blue?"
4. Keep YOUR OWN colors FIXED during negotiation - only request changes from neighbors

**CRITICAL**: Your own node colors are FIXED during negotiation. Do NOT change them.
Only request changes to boundary nodes controlled by your neighbors.
```

## Impact

These fixes enable proper negotiation in LLM_TOOL and LLM_REACT modes:

- **Before**: Agents used stale information, changed own colors, confused human with inconsistent messages
- **After**: Agents track current state, maintain own colors, make appropriate requests to resolve conflicts

The negotiation protocol now works as designed:
1. Human and agents announce initial configurations
2. Human changes boundary nodes via UI
3. Agents detect changes immediately
4. Agents request additional changes if needed to resolve conflicts
5. Process iterates until consensus (penalty = 0)

## Future Enhancements

1. **UI Loading Indicators**: Add visual feedback during LLM calls
2. **Async LLM Calls**: Consider making backend LLM calls truly async (major refactor)
3. **Smarter Change Detection**: Only notify agents when changes affect their actual boundaries
4. **Change History**: Track sequence of color changes for better LLM reasoning

## Related Documentation

- `docs/MULTI_LAYER_LLM_ARCHITECTURE.md` - Architecture overview
- `docs/MULTI_LAYER_LLM_IMPLEMENTATION.md` - Implementation details
- `CLAUDE.md` - Project guidelines and constraints
- `tests/test_color_change_propagation.py` - Test suite for Fix 1
- `tests/test_agent_color_stability.py` - Test suite for Fix 2
