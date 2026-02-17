# Fix Summary: LLM Path Incomplete Neighbor Configs (CRITICAL)

**Date**: 2026-02-17
**Issue**: Agents proposing conflicting configurations like "h2=red, b2=red"
**Root Cause**: LLM-generated API calls using incomplete neighbor dictionaries

## Problem Analysis

### User's Observation

```
[Agent2] Could you change h2 from blue to red and h5 from green to blue?
If you do that, then I can set b2 to red.
```

**Why This Is Wrong**:
- If edge (h2, b2) exists, then h2=red and b2=red = **COLOR CLASH**
- Agent proposes this confidently, thinking penalty=0
- Agent didn't detect the conflict during testing

### Root Cause Discovery

The previous fix (lines 396-404 in `tool_calling_cluster_agent.py`) only applied to the **FALLBACK path** (when LLM fails). The **LLM SUCCESS path** was still broken:

```python
# Line 366-375: LLM path (BROKEN BEFORE FIX)
result = json.loads(result_text)
api_calls = result.get("api_calls", [])
# ... logging ...
return api_calls  # ← RETURNED AS-IS, NO VALIDATION!
```

When the backend LLM generates:
```json
{
  "api_calls": [
    {
      "method": "simulate_neighbor_change",
      "params": {
        "neighbor_nodes": {"h2": "red", "h5": "blue"}  // ❌ INCOMPLETE!
      }
    }
  ]
}
```

This incomplete config gets executed directly, leading to:
1. Missing neighbors (h1, h3, h4) not in the dict
2. Incorrect penalty calculation (constraints not considered)
3. Agent thinks penalty=0 when it's actually > 0
4. Agent proposes conflicting configuration

## The Fix

### Fix Location 1: Tool Calling Agent (Phase 1 Post-Processing)

**File**: `agents/tool_calling_cluster_agent.py`
**Lines**: 366-395 (NEW: post-processing block)

**Change**: Added validation and auto-completion **AFTER** LLM returns API calls, **BEFORE** execution:

```python
# POST-PROCESS: Complete any incomplete neighbor_nodes in simulate_neighbor_change calls
# CRITICAL: LLM might generate {"h2": "red", "h5": "blue"} without other neighbors
# This leads to incorrect penalty calculations!
for call in api_calls:
    if call.get("method") == "simulate_neighbor_change":
        params = call.get("params", {})
        neighbor_nodes = params.get("neighbor_nodes", {})

        # Check if incomplete
        known_neighbors = set(self.neighbour_assignments.keys())
        provided_neighbors = set(neighbor_nodes.keys())
        missing_neighbors = known_neighbors - provided_neighbors

        if missing_neighbors:
            self.log(f"[TOOL][PHASE1] WARNING: LLM generated incomplete neighbor config!")
            self.log(f"  Provided: {sorted(provided_neighbors)}")
            self.log(f"  Missing: {sorted(missing_neighbors)}")
            self.log(f"  Auto-completing with current values...")

            # Fill in missing neighbors with current values
            complete_config = dict(self.neighbour_assignments)
            complete_config.update(neighbor_nodes)  # Override with LLM's intended changes
            params["neighbor_nodes"] = complete_config

            self.log(f"  Completed: {sorted(complete_config.keys())}")
```

**Key Points**:
- Runs AFTER LLM succeeds (lines 366-370)
- Scans ALL api_calls for `simulate_neighbor_change` methods
- Detects incomplete `neighbor_nodes` parameters
- Auto-completes with current neighbor values
- Logs warning for debugging

### Fix Location 2: ReAct Agent (Action Execution Post-Processing)

**File**: `agents/react_cluster_agent.py`
**Lines**: 645-664 (NEW: post-processing block)

**Change**: Added validation **BEFORE** executing action via API:

```python
# POST-PROCESS: Complete any incomplete neighbor_nodes for simulate_neighbor_change
# CRITICAL: LLM might generate neighbor_nodes={"h2": "red", "h5": "blue"} without other neighbors
if action_name == "simulate_neighbor_change" and "neighbor_nodes" in args_dict:
    neighbor_nodes = args_dict["neighbor_nodes"]
    known_neighbors = set(self.neighbour_assignments.keys())
    provided_neighbors = set(neighbor_nodes.keys())
    missing_neighbors = known_neighbors - provided_neighbors

    if missing_neighbors:
        self.log(f"[REACT] WARNING: LLM generated incomplete neighbor config in Action!")
        self.log(f"  Provided: {sorted(provided_neighbors)}")
        self.log(f"  Missing: {sorted(missing_neighbors)}")
        self.log(f"  Auto-completing with current values...")

        # Fill in missing neighbors with current values
        complete_config = dict(self.neighbour_assignments)
        complete_config.update(neighbor_nodes)  # Override with LLM's intended changes
        args_dict["neighbor_nodes"] = complete_config

        self.log(f"  Completed: {sorted(complete_config.keys())}")
```

**Key Points**:
- Runs BEFORE API method execution (line 668)
- Intercepts `simulate_neighbor_change` calls
- Auto-completes incomplete argument dicts
- Preserves LLM's intended changes while filling in current values for missing neighbors

## Why Auto-Completion Works

When LLM generates `{"h2": "red", "h5": "blue"}` meaning "change h2 to red and h5 to blue":

**Without fix** (WRONG):
```python
neighbor_assignments = {"h2": "red", "h5": "blue"}  # Missing h1, h3, h4!
# Penalty calculated without considering h1-h3-h4 constraints → WRONG
```

**With fix** (CORRECT):
```python
# Start with current: {"h1": "red", "h2": "blue", "h3": "green", "h4": "red", "h5": "green"}
complete_config = dict(self.neighbour_assignments)  # Copy all current
complete_config.update({"h2": "red", "h5": "blue"})  # Apply LLM's changes
# Result: {"h1": "red", "h2": "red", "h3": "green", "h4": "red", "h5": "blue"}
# Penalty calculated with ALL constraints → CORRECT
```

The fix:
1. Preserves LLM's **intent** (change h2 and h5)
2. Fills in **context** (keep h1, h3, h4 at current values)
3. Ensures **completeness** (all neighbors included)
4. Results in **accurate** penalty calculations

## Testing

### New Test: `tests/test_llm_incomplete_neighbor_fix.py`

**Test 1**: Tool Calling Agent Post-Processing
- Simulates LLM generating incomplete config
- Verifies auto-completion detects and fixes
- ✅ PASS

**Test 2**: ReAct Agent Post-Processing
- Simulates action parsing with incomplete args
- Verifies auto-completion before API execution
- ✅ PASS

### Regression Tests

1. `tests/test_complete_neighbor_simulation.py` - ✅ PASS
   (API validation, fallback completeness, prompt guidance)

2. `tests/test_phase3_uses_simulations.py` - ✅ PASS
   (Phase 3 uses tested alternatives)

3. `tests/test_no_conflict_proposals.py` - ✅ PASS
   (No conflicting color proposals)

## Expected Outcomes

After this fix:

✅ **LLM-generated configs are auto-completed** before execution
✅ **Penalty calculations are accurate** (all neighbors considered)
✅ **Agents never propose conflicting configs** like "h2=red, b2=red"
✅ **Both LLM path and fallback path work correctly**
✅ **Detailed logging** shows when auto-completion triggers

## Verification in Production

To verify the fix is working, check logs for:

**Success (no auto-completion needed)**:
```
[TOOL][PHASE1] LLM response: {"api_calls": [...]}
```
No WARNING messages → LLM generated complete configs

**Success (auto-completion applied)**:
```
[TOOL][PHASE1] WARNING: LLM generated incomplete neighbor config!
  Provided: ['h2', 'h5']
  Missing: ['h1', 'h3', 'h4']
  Auto-completing with current values...
  Completed: ['h1', 'h2', 'h3', 'h4', 'h5']
```
Warning logged → incomplete config was detected and fixed

**Failure (would have happened before fix)**:
```
[Agent2] Could you change h2 to red and h5 to blue? Then I can set b2 to red.
```
If (h2, b2) edge exists → conflict! (This should NOT happen after fix)

## Files Modified

1. **agents/tool_calling_cluster_agent.py**:
   - Lines 366-395: Added post-processing for LLM-generated API calls
   - Validates and completes `simulate_neighbor_change` neighbor_nodes

2. **agents/react_cluster_agent.py**:
   - Lines 645-664: Added post-processing before action execution
   - Validates and completes action arguments

3. **tests/test_llm_incomplete_neighbor_fix.py** (NEW):
   - Test suite for LLM path auto-completion
   - Covers both Tool Calling and ReAct agents

## Relationship to Previous Fix

**Previous Fix** (lines 396-404): Fallback path completeness
**This Fix** (lines 366-395, 645-664): LLM success path completeness

Both fixes ensure complete neighbor configs, but they target different code paths:
- **Fallback**: When LLM fails/unavailable
- **LLM Path**: When LLM succeeds but generates incomplete configs

Together, they provide **complete coverage** ensuring ALL `simulate_neighbor_change` calls use complete neighbor configs, regardless of how they're generated.

## Key Insight

**Prompts guide, but code enforces.**

Even with detailed prompts telling the LLM to use complete neighbor configs:
- LLMs may still generate shortcuts like `{"h2": "red", "h5": "blue"}`
- Natural language is inherently ambiguous
- Runtime validation is the final safety net

**Solution**: Trust but verify. Accept LLM output, detect incompleteness, auto-complete before execution.

This fix transforms the system from:
- ❌ "Hope LLM follows instructions"
To:
- ✅ "Accept LLM intent, ensure correctness"

The agent now **guarantees** complete neighbor configs regardless of LLM compliance with prompts.
