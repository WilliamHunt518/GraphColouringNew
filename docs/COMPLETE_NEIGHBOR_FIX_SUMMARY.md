# Fix Summary: Complete Neighbor Configuration Bug

**Date**: 2026-02-17
**Issue**: Agents proposing invalid configurations with conflicts
**Root Cause**: Agents calling `simulate_neighbor_change()` with incomplete neighbor dictionaries

## Problem Description

Users reported that agents were proposing "bad colorings" with conflicts:
- Agent proposed: `a2=red, a4=red` when both connect to the same neighbor (conflict!)
- Agent requested: `h4=red` without verifying it resolves conflicts
- After accepting configs, agents immediately asked for more changes

### Root Cause Analysis

The bug occurred when agents tested neighbor color changes via `simulate_neighbor_change()`:

**WRONG (before fix)**:
```python
# Agent knows: h1=red, h2=blue, h3=green, h4=red, h5=green (5 neighbors)
# Wants to test: "What if h4 becomes blue?"
simulate_neighbor_change({"h4": "blue"})  # ❌ Only h4, missing others!

# Inside API: neighbor_assignments gets updated with only h4
# Result: Penalty calculated WITHOUT considering h1, h2, h3, h5
# Leads to INCORRECT penalty → WRONG proposals
```

**CORRECT (after fix)**:
```python
# Agent knows all 5 neighbors
# Wants to test: "What if h4 becomes blue?"
simulate_neighbor_change({
    "h1": "red",    # ✅ Keep current
    "h2": "blue",   # ✅ Keep current
    "h3": "green",  # ✅ Keep current
    "h4": "blue",   # ✅ CHANGE THIS
    "h5": "green"   # ✅ Keep current
})

# Result: Penalty calculated with ALL neighbor constraints
# Leads to CORRECT penalty → VALID proposals
```

## Implementation

### Fix 1: Enhanced Phase 1 Fallback (Tool Calling Agent)

**File**: `agents/tool_calling_cluster_agent.py` (lines 396-404)

**Change**: Build COMPLETE neighbor config before calling `simulate_neighbor_change()`

```python
# Build COMPLETE neighbor config (all neighbors, only change one)
# CRITICAL: Must pass ALL neighbor assignments to get accurate penalty
complete_neighbor_config = dict(self.neighbour_assignments)
complete_neighbor_config[neighbor_node] = alt_color

api_calls.append({
    "method": "simulate_neighbor_change",
    "params": {"neighbor_nodes": complete_neighbor_config}
})
```

**Impact**: Phase 1 fallback now generates API calls with complete neighbor information for accurate penalty calculations.

### Fix 2: Updated Tool Calling Prompt Examples

**File**: `agents/tool_calling_cluster_agent.py` (lines 285-287, 309-316, 320-323)

**Changes**:
1. Updated `simulate_neighbor_change` parameter examples to show complete configs
2. Added CRITICAL warning section about complete configs
3. Updated translation strategy examples

**Before**:
```python
simulate_neighbor_change({"h4": "blue"})  # ❌ Incomplete
```

**After**:
```python
simulate_neighbor_change({"h1": "red", "h2": "blue", "h3": "green", "h4": "blue", "h5": "green"})  # ✅ Complete
```

**Added warning**:
```
**CRITICAL: Always pass COMPLETE neighbor configs to simulate_neighbor_change()**:
❌ WRONG: simulate_neighbor_change({"neighbor_nodes": {"h4": "blue"}})  # Missing other neighbors!
✅ CORRECT: simulate_neighbor_change({"neighbor_nodes": {"h1": "red", "h2": "blue", "h3": "green", "h4": "blue", "h5": "green"}})
```

### Fix 3: Updated ReAct Agent Prompt Examples

**File**: `agents/react_cluster_agent.py` (lines 192-199, 244-250)

**Changes**:
1. Updated example Thought/Action pairs to show complete configs
2. Enhanced strategy section to emphasize complete neighbor requirement

**Key addition**:
```python
3. **Action: Call simulate_neighbor_change() to TEST MULTIPLE solutions** (CRITICAL):
   - **ALWAYS pass COMPLETE neighbor assignments (all known neighbors)**
   - Only CHANGE the nodes you're testing, KEEP others at current colors
   - Example: If testing h4=blue and you know 5 neighbors, pass ALL 5:
     simulate_neighbor_change(neighbor_nodes={"h1": "red", "h2": "blue", "h3": "green", "h4": "blue", "h5": "green"})
```

### Fix 4: Added API Validation Warning

**File**: `agents/cluster_agent_api.py` (lines 445-456)

**Change**: Added validation to warn when incomplete neighbor sets are passed

```python
# VALIDATION: Warn if incomplete neighbor set provided
known_neighbors = set(self.agent.neighbour_assignments.keys())
provided_neighbors = set(neighbor_nodes.keys())
missing_neighbors = known_neighbors - provided_neighbors

if missing_neighbors:
    self.agent.log(f"[API WARNING] simulate_neighbor_change called with incomplete neighbors.")
    self.agent.log(f"  Known neighbors: {sorted(known_neighbors)}")
    self.agent.log(f"  Provided: {sorted(provided_neighbors)}")
    self.agent.log(f"  Missing: {sorted(missing_neighbors)}")
    self.agent.log(f"  This may cause incorrect penalty calculations!")
```

**Impact**: Provides safety net to catch incomplete configs during development/debugging.

## Testing

### New Test: `tests/test_complete_neighbor_simulation.py`

Created comprehensive test suite with 3 test cases:

**Test 1**: API Validation Warning
- Verifies API warns about incomplete neighbor configs
- Verifies API doesn't warn about complete configs
- ✅ PASS

**Test 2**: Complete vs Incomplete Penalty Difference
- Demonstrates that complete configs are necessary for accurate penalties
- Shows how incomplete configs can lead to incorrect calculations
- ✅ PASS

**Test 3**: Prompt Examples Verification
- Checks that prompts contain guidance about complete configs
- Verifies fallback code creates complete configs
- ✅ PASS

### Regression Tests

Ran existing tests to ensure no breakage:

1. `tests/test_phase3_uses_simulations.py` - ✅ PASS
2. `tests/test_no_conflict_proposals.py` - ✅ PASS

## Expected Outcomes

After these fixes:

✅ **Agents pass COMPLETE neighbor configs** to `simulate_neighbor_change()`
✅ **Penalty calculations are accurate** (all neighbors considered)
✅ **Agents only propose changes that work** (penalty=0 after testing)
✅ **Convergence is reached reliably** (no more bad proposals)
✅ **No more "bad colorings"** with conflicts

## Verification Steps

To verify the fix is working:

1. **Check logs for complete configs**:
   ```
   [TOOL][PHASE2] Executing: simulate_neighbor_change
     Parameters: {"neighbor_nodes": {"h1": "red", "h2": "blue", "h3": "green", "h4": "blue", "h5": "green"}}
   ```

2. **Check for API warnings** (should not appear in normal operation):
   ```
   [API WARNING] simulate_neighbor_change called with incomplete neighbors.
     Missing: ['h1', 'h3']
   ```

3. **Run terminal-based dialogue**:
   ```bash
   python run_experiment.py --method LLM_TOOL --no-ui --manual --max-iters 20
   ```
   - Agents should propose only valid changes
   - Convergence should be reached
   - No conflicting color proposals

## Files Modified

1. `agents/tool_calling_cluster_agent.py`:
   - Lines 396-404: Phase 1 fallback fix
   - Lines 285-287: Updated parameter examples
   - Lines 309-316: Added CRITICAL warning
   - Lines 320-323: Updated translation examples

2. `agents/react_cluster_agent.py`:
   - Lines 192-199: Updated example with complete configs
   - Lines 244-250: Enhanced strategy section

3. `agents/cluster_agent_api.py`:
   - Lines 445-456: Added validation warning

4. `tests/test_complete_neighbor_simulation.py` (NEW):
   - Comprehensive test suite for the fix

## Key Insight

**Template fallback must use complete neighbor information, not partial data.**

The fix changes the paradigm from:
- ❌ "Test THEN hope penalty is calculated correctly"

To:
- ✅ "Test with COMPLETE info THEN get accurate penalty"

This ensures agents can make informed decisions based on accurate penalty calculations, leading to valid proposals and reliable convergence.
