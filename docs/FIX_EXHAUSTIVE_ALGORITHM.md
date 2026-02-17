# Fix: Agents Rejecting Valid Configurations (Algorithm Issue)

**Date**: 2026-02-13
**Issue**: Agents rejecting configurations that should work (penalty=0 achievable)
**Status**: ✅ Fixed

## Problem Description

User reported: *"There must be an issue with its algorithms or it not exhaustively searching or something, as they aren't happy with a config I know should work."*

Agents were rejecting valid penalty=0 configurations even though the configuration was known to be feasible.

## Root Cause

The issue was an inconsistency between two algorithm paths:

1. **`compute_assignments()` in API** (used during agent's normal step):
   - Defaulted to `algorithm="greedy"`
   - Greedy algorithm colors nodes sequentially (fast but NOT globally optimal)
   - May get stuck in local optima and miss optimal solutions

2. **`get_best_response_to()` in API** (used for planning):
   - Uses `_best_local_assignment_for()` internally
   - ALWAYS does exhaustive search (regardless of algorithm setting)
   - Guaranteed to find optimal solution

**Result**:
- Agents could PLAN optimal solutions (via `get_best_response_to()`)
- But couldn't EXECUTE them (via `compute_assignments()` with greedy)
- This caused agents to reject valid configurations because greedy couldn't find them

## Example Scenario

```
Graph: (a1)---(a2)---(h1)
Colors: red, blue, green
Human sets: h1=red

Greedy execution:
1. Assign a1=blue (arbitrary first choice)
2. Assign a2=red (avoids a1=blue)
3. Conflict! a2=red clashes with h1=red
4. Greedy gets stuck → penalty > 0

Exhaustive search:
- Try all 3^2=9 combinations
- Find: a1=red, a2=blue → penalty=0
- Success!
```

## Solution

Changed default algorithm from "greedy" to "maxsum" (exhaustive) in three places:

### 1. API Default Parameter

**File**: `agents/cluster_agent_api.py` (line 56)

```python
# BEFORE:
def compute_assignments(self, algorithm: str = "greedy") -> Dict[str, str]:

# AFTER:
def compute_assignments(self, algorithm: str = "maxsum") -> Dict[str, str]:
```

### 2. Tool Calling Agent Prompt

**File**: `agents/tool_calling_cluster_agent.py` (lines 445, 466)

```python
# BEFORE:
- compute_assignments(algorithm="greedy"): Run local solver on your nodes
2. Try compute_assignments(algorithm="greedy") to optimize YOUR nodes

# AFTER:
- compute_assignments(): Run exhaustive solver on your nodes (finds optimal solution)
2. Try compute_assignments() to optimize YOUR nodes (uses exhaustive search for optimal solution)
```

### 3. ReAct Agent Prompt

**File**: `agents/react_cluster_agent.py` (line 152)

```python
# BEFORE:
- compute_assignments(algorithm="greedy"): Run local solver on your nodes

# AFTER:
- compute_assignments(): Run exhaustive solver on your nodes (finds optimal solution)
```

## Updated Documentation

**File**: `agents/cluster_agent_api.py` (lines 63-81)

```python
Parameters
----------
algorithm : str, optional
    Solver algorithm to use. Options:
    - "maxsum": Exhaustive search over all combinations (default, guarantees optimal)
    - "greedy": Fast sequential greedy coloring (may miss optimal solutions)

Notes
-----
- Maxsum (exhaustive) guarantees optimal solution but runs in O(k^n)
- For small clusters (5 nodes, 3 colors = 243 combinations), exhaustive is fast
- Greedy runs in O(n*k) but may miss optimal solutions
```

## Why Exhaustive is Safe

**Clusters are small**:
- Typical cluster size: 5 nodes
- Domain size: 3 colors
- Combinations: 3^5 = 243

**Exhaustive is fast**:
- Checking 243 combinations takes milliseconds
- Cost is negligible compared to LLM API calls

**Consistency**:
- `compute_assignments()` now matches `get_best_response_to()`
- Both use exhaustive search → consistent behavior
- Agents can execute what they plan

## Testing

**Test file**: `tests/test_exhaustive_algorithm_fix.py`

Three tests verify:
1. ✅ API defaults to exhaustive search
2. ✅ `get_best_response_to()` uses exhaustive search
3. ✅ Both methods produce consistent penalty=0 results

All tests pass:
```
Test 1: API defaults to exhaustive
Result: {'a1': 'red', 'a2': 'blue'}
Agent algorithm after call: maxsum
Penalty: 0.0
[PASS] API defaults to exhaustive search and finds optimal solution

Test 2: get_best_response_to is exhaustive
Best response to h1=red: {'a1': 'red', 'a2': 'blue'}
Penalty: 0.0
[PASS] get_best_response_to() uses exhaustive search and finds optimal solution

Test 3: Consistency between methods
compute_assignments(): {'a1': 'red', 'a2': 'blue'}
get_best_response_to(): {'a1': 'red', 'a2': 'blue'}
Penalty1: 0.0, Penalty2: 0.0
[PASS] Both methods use exhaustive search and find optimal solutions
```

## Expected Behavior After Fix

**Before**:
- Agent proposes: "Could you change h4 to blue?"
- Human changes h4 to blue
- Agent recomputes with greedy: Still finds conflicts (greedy stuck)
- Agent rejects: "That doesn't work, try something else"
- Human frustrated: "But I know this should work!"

**After**:
- Agent proposes: "Could you change h4 to blue?"
- Human changes h4 to blue
- Agent recomputes with exhaustive: Finds optimal penalty=0 solution
- Agent accepts: "Great! That works, penalty=0 achieved"
- Human satisfied: System works correctly

## Files Modified

1. **`agents/cluster_agent_api.py`** (lines 56-81)
   - Changed default from "greedy" to "maxsum"
   - Updated documentation to emphasize optimality guarantee

2. **`agents/tool_calling_cluster_agent.py`** (lines 445, 466)
   - Removed `algorithm="greedy"` from prompt examples
   - Emphasized exhaustive search in tool descriptions

3. **`agents/react_cluster_agent.py`** (line 152)
   - Removed `algorithm="greedy"` from prompt
   - Updated to use default exhaustive search

4. **`tests/test_exhaustive_algorithm_fix.py`** (new file)
   - Comprehensive tests verifying exhaustive algorithm behavior
   - Tests consistency between compute and planning methods

## Key Insights

1. **Algorithm consistency matters**: If planning uses exhaustive but execution uses greedy, agents can't execute their own plans
2. **Small clusters = exhaustive is free**: With 5 nodes and 3 colors, exhaustive search is negligible overhead
3. **Defaults matter**: API defaults guide LLM behavior - wrong defaults cause systematic failures
4. **Prompt alignment**: Prompts should match API behavior (don't suggest greedy if maxsum is default)

## Related Issues

This fix resolves the following related problems:
- Agents proposing changes then rejecting them after acceptance
- Agents unable to achieve penalty=0 despite valid configuration
- Inconsistency between what agents say they'll do and what they actually do
- User frustration with "I know this works but agent says it doesn't"
