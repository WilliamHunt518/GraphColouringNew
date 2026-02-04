# FIX #22: Switch to Exhaustive Search (Maxsum) Algorithm

## Issue

Agents were using the greedy algorithm by default, which has a **fundamental node-ordering problem** that causes internal conflicts even when valid solutions exist.

### Example Bug

In the logs, Agent2 showed:
```
Assignment: {'b1': 'red', 'b2': 'red', 'b3': 'green', 'b4': 'green', 'b5': 'blue'}
Penalty: 20.0
```

**Conflicts:**
- b1 and b2 both red (connected by edge b1<->b2)
- b3 and b4 both green (connected by edge b3<->b4)

### Root Cause

The greedy algorithm processes nodes sequentially in list order: `['b1', 'b2', 'b3', 'b4', 'b5']`

1. **b1** (processed first): All colors score 0.0 (no neighbors colored yet), so it picks 'red' arbitrarily
2. **b2** (processed second): Now trapped in impossible situation:
   - `b2=red`: Conflicts with b1 (internal) → penalty = 10.0
   - `b2=green`: Conflicts with h5=green (external) → penalty = 10.0
   - `b2=blue`: Conflicts with h2=blue (external) → penalty = 10.0
3. All colors have equal penalty, so greedy picks first in domain ('red'), creating the clash

**Debug Log Evidence:**
```
[GREEDY DEBUG] Processing node: b2
[GREEDY DEBUG]   Current new_assignment: {'b1': 'red'}
[GREEDY DEBUG]   Scores for b2: {'red': 10.0, 'green': 10.0, 'blue': 10.0}
[GREEDY DEBUG]   Chose b2=red (score=10.0)  ← Creates conflict!
```

The greedy algorithm makes locally-optimal decisions without backtracking. Early node choices can trap later nodes in impossible situations.

## Solution

**Switch default algorithm from `greedy` to `maxsum` (exhaustive search)**

The `maxsum` algorithm:
- Tries all possible color combinations using `itertools.product`
- Finds the globally optimal solution (lowest penalty)
- For 5 nodes with 3 colors: searches 3^5 = 243 combinations (trivial)
- Already used for offer validation, now used for all assignments

## Changes Made

### 1. `launch_menu.py` (line 56)
```python
# Before:
alg_var = tk.StringVar(value=saved_config.get("algorithm", "greedy"))

# After:
alg_var = tk.StringVar(value=saved_config.get("algorithm", "maxsum"))
```

### 2. `cluster_simulation.py` (line 352)
```python
# Before:
algorithm = cluster_algorithms.get(owner, "greedy")

# After:
algorithm = cluster_algorithms.get(owner, "maxsum")
```

### 3. `run_experiment.py`

#### Line 36 - Constant
```python
# Before:
AGENT_ALG = "greedy"  # "greedy" or "maxsum" (exhaustive)

# After:
AGENT_ALG = "maxsum"  # "greedy" or "maxsum" (exhaustive) - default changed to maxsum for correctness
```

#### Line 50 - Function parameter
```python
# Before:
agent_algorithm: str = "greedy",

# After:
agent_algorithm: str = "maxsum",  # Changed default from "greedy" to "maxsum" for correctness
```

### 4. `agents/cluster_agent.py`

#### Line 102 - Constructor parameter
```python
# Before:
algorithm: str = "greedy",

# After:
algorithm: str = "maxsum",  # Changed default from "greedy" to "maxsum" for correctness
```

#### Lines 78-80 - Docstring
```python
# Before:
algorithm : str, optional
    Name of the internal optimisation algorithm to use.  Supported
    values are ``"greedy"`` and ``"maxsum"``.  Defaults to
    ``"greedy"``.

# After:
algorithm : str, optional
    Name of the internal optimisation algorithm to use.  Supported
    values are ``"greedy"`` and ``"maxsum"`` (exhaustive search).
    Defaults to ``"maxsum"`` for correctness on small problems.
```

### 5. `agents/rule_based_cluster_agent.py`

#### Line 75 - Constructor parameter
```python
# Before:
algorithm: str = "greedy",

# After:
algorithm: str = "maxsum",  # Changed default from "greedy" to "maxsum" for correctness
```

#### Lines 50-53 - Docstring
```python
# Before:
algorithm : str, optional
    Name of the internal optimisation algorithm to use.  Supported
    values are ``"greedy"`` and ``"maxsum"``.  Defaults to
    ``"greedy"``.

# After:
algorithm : str, optional
    Name of the internal optimisation algorithm to use.  Supported
    values are ``"greedy"`` and ``"maxsum"`` (exhaustive search).
    Defaults to ``"maxsum"`` for correctness on small problems.
```

## Verification

### Test Results

**Before (greedy):**
```
Assignment: {'b1': 'red', 'b2': 'red', 'b3': 'green', 'b4': 'green', 'b5': 'blue'}
CONFLICTS FOUND:
  - b1=red CLASHES with b2=red
  - b3=green CLASHES with b4=green
Total penalty: 20.0
```

**After (maxsum):**
```
Assignment: {'b1': 'green', 'b2': 'red', 'b3': 'blue', 'b4': 'green', 'b5': 'blue'}
No conflicts found
Total penalty: 0.0
```

## Performance Impact

For typical cluster sizes (5 nodes, 3 colors):
- Exhaustive search: 3^5 = 243 evaluations
- Time: < 1ms (negligible)

The small problem size makes exhaustive search **both faster and more correct** than trying to optimize with greedy heuristics.

## Notes

- Greedy algorithm remains available for experimentation but is **not recommended**
- RB protocol already used maxsum for offer validation (line 60 in Agent2 logs)
- This fix ensures **deterministic, correct solutions** for research experiments

## Related Issues

- Initial observation: Agent2 logs showed penalty=20.0 with internal conflicts
- Diagnosis: Debug logging revealed greedy tie-breaking issue
- Test case: `test_greedy_bug.py` reproduces and verifies fix
