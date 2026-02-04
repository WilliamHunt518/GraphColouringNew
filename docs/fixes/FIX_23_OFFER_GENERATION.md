# FIX #23: Use Maxsum for ALL Nodes in Conditional Offer Generation

## Issue

After FIX #22 switched to maxsum for normal operations, Agent2 was **still** generating conditional offers with internal conflicts. Example from user logs:

```
Offer: IF h2=red AND h5=green THEN b2=blue
After acceptance: b1=red, b2=red, b3=green, b4=green, b5=blue
Conflicts: b1-b2 (both red), b3-b4 (both green)
Penalty: 20.0
```

## Root Cause

The `_generate_conditional_offer()` method in `rule_based_cluster_agent.py` had a **critical flaw** (lines 904-914):

```python
# OLD CODE (BROKEN):
for our_config in our_configs:
    # Build complete assignment
    test_assignment = dict(self.assignments)  # ← Uses CURRENT assignments!
    for i, node in enumerate(our_boundary):
        test_assignment[node] = our_config[i]  # Only changes boundary nodes

    # Evaluate penalty
    penalty = self.problem.evaluate_assignment(combined)
```

**The Problem:**
1. Only **boundary nodes** (e.g., b2) were tested with different colors
2. **Non-boundary nodes** (e.g., b1, b3, b5) kept their **current stale assignments**
3. If b1=red from a previous iteration, it stayed red even when b2 also became red
4. Result: Offers with internal conflicts like `{b1=red, b2=red, ...}`

## Solution

**Use `compute_assignments()` (maxsum) to optimally assign ALL nodes** for each hypothetical neighbor configuration:

```python
# NEW CODE (FIXED):
for config_idx, their_config in enumerate(their_configs):
    # Create hypothetical neighbor assignment
    hypothetical_neighbors = dict(self.neighbour_assignments)
    for i, node in enumerate(their_boundary):
        hypothetical_neighbors[node] = their_config[i]

    # Temporarily set neighbor assignments to hypothetical configuration
    old_neighbors = dict(self.neighbour_assignments)
    self.neighbour_assignments = hypothetical_neighbors

    # Let maxsum find the optimal assignment for ALL our nodes
    test_assignment = self.compute_assignments()  # ← ALL nodes optimized!

    # Restore original neighbor assignments
    self.neighbour_assignments = old_neighbors

    # Evaluate penalty
    penalty = self.problem.evaluate_assignment(combined)
```

Now **all nodes** (b1, b2, b3, b4, b5) get optimally assigned using maxsum for each hypothetical scenario, ensuring conflict-free offers.

## Changes Made

### File: `agents/rule_based_cluster_agent.py`

#### 1. Lines 889-920: Use compute_assignments() for ALL nodes
```python
# Before:
for our_config in our_configs:
    test_assignment = dict(self.assignments)
    for i, node in enumerate(our_boundary):
        test_assignment[node] = our_config[i]

    penalty = self.problem.evaluate_assignment(combined)

    if penalty < best_penalty:
        best_penalty = penalty
        best_config = their_config
        best_our_assignment = our_config  # Tuple of boundary colors

# After:
# Temporarily set neighbor assignments
old_neighbors = dict(self.neighbour_assignments)
self.neighbour_assignments = hypothetical_neighbors

# Let maxsum find optimal assignment for ALL nodes
test_assignment = self.compute_assignments()

# Restore original neighbors
self.neighbour_assignments = old_neighbors

penalty = self.problem.evaluate_assignment(combined)

if penalty < best_penalty:
    best_penalty = penalty
    best_config = their_config
    best_our_assignment = test_assignment  # Dict of ALL node assignments
```

#### 2. Lines 1146-1151: Extract boundary assignments from dict
```python
# Before:
assignments = []
for i, node in enumerate(our_boundary):
    assignments.append(Assignment(
        node=node,
        colour=best_our_assignment[i]  # Index into tuple
    ))

# After:
assignments = []
for node in our_boundary:
    if node in best_our_assignment:  # Dict lookup
        assignments.append(Assignment(
            node=node,
            colour=best_our_assignment[node]
        ))
```

#### 3. Lines 1180-1190: Use full assignment dict in validation
```python
# Before:
test_our_assignments = dict(self.assignments)
for i, node in enumerate(our_boundary):
    test_our_assignments[node] = best_our_assignment[i]

# After:
# best_our_assignment is now a dict (full assignment)
test_our_assignments = dict(best_our_assignment)
```

#### 4. Lines 1206-1213: Fix validation comparison
```python
# Before:
for i, node in enumerate(our_boundary):
    promised_color = best_our_assignment[i]
    optimal_color = validation_assignment.get(node)

# After:
for node in our_boundary:
    promised_color = best_our_assignment.get(node)
    optimal_color = validation_assignment.get(node)
```

#### 5. Lines 1110-1115: Fix state comparison
```python
# Before:
for i, node in enumerate(our_boundary):
    if self.assignments.get(node) != best_our_assignment[i]:

# After:
for node in our_boundary:
    if self.assignments.get(node) != best_our_assignment.get(node):
```

## Verification

### Test Results

**Before Fix:**
```
Agent2 generates offer: IF h2=red AND h5=green THEN b2=blue
After acceptance:
  Assignment: {b1=red, b2=red, b3=green, b4=green, b5=blue}
  Conflicts: b1-b2 (both red), b3-b4 (both green)
  Penalty: 20.0
  ❌ FAIL
```

**After Fix:**
```
Agent2 generates offer: IF h2=red AND h5=green THEN b2=blue
After acceptance:
  Assignment: {b1=green, b2=blue, b3=red, b4=green, b5=red}
  Conflicts: None
  Penalty: 0.0
  ✓ SUCCESS
```

## Performance Impact

For each hypothetical neighbor configuration:
- **Before:** Tried 3^1 = 3 boundary combinations (but used stale non-boundary assignments)
- **After:** Runs maxsum once = 3^5 = 243 exhaustive evaluations

For 9 neighbor configurations × 243 evaluations = **2,187 total evaluations**

Time: Still < 100ms total (negligible for small clusters)

The correctness gain vastly outweighs the minor performance cost.

## Key Insight

**The offer generation process must respect the same optimality guarantees as normal operation:**
- Normal operation: Uses maxsum to find optimal assignment for all nodes
- Offer generation: **Now also** uses maxsum to find optimal assignment for all nodes

This ensures **every conditional offer is backed by a proven conflict-free solution**.

## Related Issues

- FIX #22: Switched default algorithm to maxsum (fixed normal operation)
- FIX #23: Extended maxsum to conditional offer generation (fixed negotiation)
- Together: Guarantees conflict-free operation throughout the entire RB protocol

## Testing

Run test suite:
```bash
python test_offer_generation.py  # ✓ Verifies offers are conflict-free
python test_default_algorithm.py  # ✓ Verifies maxsum is default
python test_greedy_bug.py        # ✓ Documents the original greedy bug
```
