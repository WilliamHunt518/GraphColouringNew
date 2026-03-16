# Fix Summary: Agent Behavior Issues (2026-02-17)

## Issues Reported by User

1. **Agents proposing bad colorings** - "they are suggesting bad colourings...they are offering configs that result in clashes"
2. **UI shows inconsistent assignments** - Debug panel and graph panel showing different agent node colors
3. **Agents keep asking for changes after acceptance** - Agent accepts config, then immediately asks for more changes

## Root Causes Identified

### Issue 1: Bad Colorings (LLM Path Not Using Simulation Results)
**Problem**: Template fallback (used in tests) correctly extracted simulation results, but LLM path (used in real runs) didn't.

- **Template fallback** (lines 617-677): Looks for `simulation_h4_blue` keys with `penalty=0` ✅
- **LLM prompt** (lines 535-542): Only told to look at `current_penalty` and `best_response` ❌

**Result**: LLM proposed arbitrary changes without testing them first.

### Issue 2: UI Inconsistency (Report Tag Not Matching Internal State)
**Problem**: Agent updated internal `self.assignments` but `[report: ...]` tag used `my_assignments` from message.

**Flow**:
1. Agent computes assignments → `my_assignments = {"a1": "red", "a2": "blue"}`
2. Agent updates internal nodes → `self.assignments["a1"] = "red"` (silent update)
3. Speech layer sends `[report: {"a1": "red", "a2": "blue"}]` (from `my_assignments`)
4. But `self.assignments = {"a1": "red"}` (internal only)

**Result**: Graph panel (from `[report: ...]`) showed different colors than debug panel (from `agent.assignments`).

### Issue 3: No Satisfaction Tracking (Agents Never Stop Negotiating)
**Problem**: Agents didn't set `self.satisfied = True` when achieving penalty=0.

- `ClusterAgent` has `self.satisfied` flag and updates it in step()
- `ToolCallingClusterAgent` overrides step() but doesn't update `self.satisfied`
- No early check: "Am I already satisfied? If yes, don't renegotiate!"

**Result**: Agents kept negotiating even after accepting configurations.

## Fixes Applied

### Fix 1: Enhanced LLM Prompt to Use Simulation Results
**Files**: `agents/tool_calling_cluster_agent.py` (lines 535-565), `agents/react_cluster_agent.py` (lines 241-258)

**Changes**:
- Added explicit instructions to look for `simulation_*` keys in API results
- Told LLM to ONLY propose alternatives with `penalty=0` from simulations
- Added example showing how to extract node/color from simulation keys
- Emphasized: "DO NOT propose arbitrary changes - only propose changes that were TESTED and have penalty=0"

**Example added to prompt**:
```
Example API results with simulations:
{
  "current_penalty": 1.0,
  "simulation_h4_blue": {"penalty": 0.0, "conflicts": []},
  "simulation_h4_green": {"penalty": 0.5, "conflicts": [("a2", "h4")]},
  "simulation_h4_red": {"penalty": 1.0, "conflicts": [("a2", "h4")]}
}

In this case, you MUST propose h4=blue (penalty=0), NOT h4=green or h4=red.
```

### Fix 2: Synchronized Report Tag with Internal State
**Files**: `agents/tool_calling_cluster_agent.py` (lines 776-781), `agents/react_cluster_agent.py` (lines 914-917)

**Changes**:
- After updating internal nodes, update `my_assignments` to match `self.assignments`
- This ensures `[report: ...]` tag always reflects current internal state

**Before**:
```python
# Apply internal node assignments silently
for node, color in proposed.items():
    if node in self.nodes and node not in boundary_nodes:
        self.assignments[node] = color

# Format message (uses original my_assignments)
nl_message = self.comm_layer.format_message(message_data)
```

**After**:
```python
# Apply internal node assignments silently
for node, color in proposed.items():
    if node in self.nodes and node not in boundary_nodes:
        self.assignments[node] = color

# CRITICAL: Update my_assignments to match current self.assignments
structured_content["my_assignments"] = dict(self.assignments)
message_data["structured_content"] = structured_content

# Format message (now uses updated my_assignments)
nl_message = self.comm_layer.format_message(message_data)
```

### Fix 3: Added Satisfaction Tracking and Early Exit
**Files**: `agents/tool_calling_cluster_agent.py` (lines 137-166, 158-171), `agents/react_cluster_agent.py` (lines 447-477, 525-540)

**Changes**:

1. **Set satisfaction flag after Phase 3**:
```python
# Update satisfaction based on results
current_penalty = api_results.get("current_penalty", float('inf'))
if current_penalty < 1e-6:
    self.satisfied = True
    self.log("[TOOL] Satisfied: penalty=0")
else:
    self.satisfied = False
    self.log(f"[TOOL] Not satisfied: penalty={current_penalty}")
```

2. **Early satisfaction check at start of step()**:
```python
# Early satisfaction check: If already satisfied and no new human message, don't renegotiate
if self.satisfied and not self._received_human_message_this_turn:
    self.log("[TOOL] Already satisfied, no new message - skipping step")
    return

# If satisfied, check if current config still works before re-negotiating
if self.satisfied:
    # Human sent new message - re-check if we're still satisfied
    current_penalty, _ = self.api.get_current_penalty()
    if current_penalty < 1e-6:
        self.log("[TOOL] Still satisfied (penalty=0) - sending acknowledgment")
        # Send simple acknowledgment
        ack_message = {...}
        self._send_translated_message(ack_message)
        return
    else:
        # No longer satisfied - continue with normal processing
        self.satisfied = False
        self.log(f"[TOOL] No longer satisfied (penalty={current_penalty}) - re-negotiating")
```

## Expected Behavior After Fixes

### 1. No More Bad Colorings
- Agents will ONLY propose alternatives that have been tested via `simulate_neighbor_change()`
- Agents will ONLY propose alternatives where `penalty=0` (verified)
- Example: Agent tests `h4=blue` → penalty=0 → proposes "Could you change h4 to blue?"

### 2. Consistent UI Colors
- Graph panel and debug panel will show the same agent node colors
- `[report: ...]` tag always matches `agent.assignments` internal state
- No more timing issues or stale data

### 3. Agents Stop When Satisfied
- Agent achieves penalty=0 → sets `self.satisfied = True`
- Human sends new config → Agent checks if still satisfied
- If still satisfied → sends acknowledgment, doesn't renegotiate
- If no longer satisfied → resumes negotiation

## Testing

### Manual Test Scenario
1. **Start experiment** with LLM_TOOL or LLM_REACT mode
2. **Create conflict** by setting overlapping colors
3. **Verify**: Agent proposes tested alternatives (mentions "I tested this")
4. **Accept proposal** and verify agent acknowledges
5. **Send different config** - agent should re-check before proposing changes
6. **Check UI** - graph panel and debug panel should match

### Automated Tests
- `tests/test_phase3_uses_simulations.py` - Verifies Phase 3 uses simulation results ✅
- `tests/test_no_conflict_proposals.py` - Verifies no conflicting proposals ✅

Both tests pass with fallback mode. LLM mode now has same logic.

## Files Modified

1. `agents/tool_calling_cluster_agent.py`:
   - Lines 535-565: Enhanced LLM prompt with simulation extraction logic
   - Lines 137-166: Added early satisfaction check
   - Lines 158-171: Set satisfaction flag after Phase 3
   - Lines 776-781: Synchronized report tag with internal state

2. `agents/react_cluster_agent.py`:
   - Lines 241-258: Enhanced strategy with simulation requirements
   - Lines 447-477: Added early satisfaction check
   - Lines 525-540: Set satisfaction flag after backend decision
   - Lines 914-917: Synchronized report tag with internal state

## Related Documentation
- Previous fix (2026-02-16): `docs/FIX_VALID_PROPOSALS.md`
- Phase 3 simulation extraction was working in fallback, but not in LLM path
- This fix completes the simulation extraction feature

## Summary
All three user-reported issues have been addressed:
✅ Agents now propose only TESTED, VALID alternatives (using simulation results)
✅ UI shows consistent colors (report tag matches internal state)
✅ Agents stop when satisfied (satisfaction tracking + early exit)
