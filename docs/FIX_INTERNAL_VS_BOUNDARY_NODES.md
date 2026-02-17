# Fix: Internal vs Boundary Node Distinction

## Problem Summary

After the initial negotiation fix, two critical issues remained:

1. **Agents couldn't resolve internal conflicts**: They said "I'll take care of it internally" but never actually updated their own internal nodes
2. **Agents talked about irrelevant nodes**: They mentioned internal nodes (b1, b3, b5) to the human, who doesn't control or care about those nodes

## Root Cause

The original fix was **too restrictive** - it prevented agents from modifying ANY of their own nodes, but the correct behavior is:

- ✅ Agents CAN modify **internal nodes** (nodes with no external edges)
- ❌ Agents CANNOT modify **boundary nodes** (nodes with edges to other clusters)

### Key Distinction

For an agent controlling nodes {a1, a2, a3, a4, a5}:

- **Internal nodes**: a1, a3 (only connect within the cluster)
- **Boundary nodes**: a2, a4, a5 (connect to other clusters/human)
- **Neighbor nodes**: h1, h2, h3, etc. (controlled by others)

## Solution

### Part 1: Allow Internal Node Modifications

Updated `_send_backend_decision()` to filter `my_assignments`:

```python
# Identify boundary nodes
boundary_nodes = set()
for node in self.nodes:
    for neighbor in self.problem.get_neighbors(node):
        if neighbor not in self.nodes:
            boundary_nodes.add(node)
            break

# Only apply changes to internal nodes
for node, color in proposed.items():
    if node in self.nodes and node not in boundary_nodes:
        self.assignments[node] = color  # ✅ Apply
        self.log(f"Updated internal node {node} -> {color}")
    elif node in boundary_nodes:
        self.log(f"SKIPPED boundary node {node} (requires coordination)")
```

**Files Modified**:
- `agents/tool_calling_cluster_agent.py` (lines 634-653)
- `agents/react_cluster_agent.py` (lines 524-543)

### Part 2: Update System Prompts

**Before** (incorrect):
```
**Your nodes**: a1, a2, a3, a4, a5
**Boundary nodes** (owned by neighbors): a2, a4, a5  ❌ WRONG!

1. You CONTROL your own nodes - you can change these freely
2. You CANNOT control boundary nodes - neighbors control these
```

**After** (correct):
```
**Your INTERNAL nodes**: a1, a3 (you can modify these freely)
**Your BOUNDARY nodes**: a2, a4, a5 (require coordination with neighbors)

1. You CAN freely change INTERNAL nodes to resolve conflicts
2. You CANNOT change BOUNDARY nodes - these require coordination
3. You CANNOT control neighbor nodes - only request changes
4. When talking to neighbors, ONLY mention boundary nodes and neighbor nodes
5. NEVER mention internal nodes in messages - neighbors don't need to know about them
```

**Files Modified**:
- `agents/tool_calling_cluster_agent.py` (lines 333-357)
- `agents/react_cluster_agent.py` (lines 219-243)

### Part 3: Clarify Message Content Rules

Added explicit rule to system prompts:

> **When talking to neighbors, ONLY mention boundary nodes and neighbor nodes. NEVER mention internal nodes in messages - neighbors don't need to know about them.**

This prevents agents from saying things like:
- ❌ "I've assigned b1=green, b2=red, b3=red, b4=green, b5=red"
- ✅ "I've set b2 (our boundary) to red. Could you change h2 to blue?"

## Expected Behavior

### Example 1: Agent Resolves Internal Conflict

**Setup**:
- Agent1 controls: a1, a2, a3, a4, a5
- Boundary nodes: a2, a4, a5
- Internal nodes: a1, a3
- Initial: a1=blue, a2=blue, a3=blue, a4=red, a5=blue
- Problem: a1 and a2 have same color (internal conflict)

**Agent Behavior**:
1. Agent detects conflict between a1 and a2
2. Agent changes a1 to green (internal node - allowed)
3. Agent leaves a2 as blue (boundary node - don't modify without coordination)
4. Agent messages human: "h4 conflicts with a4=red. Could you change h4 to blue?"
   - ✅ Mentions a4 (boundary node)
   - ✅ Mentions h4 (neighbor node)
   - ✅ Does NOT mention a1, a3 (internal nodes)

### Example 2: Agent Requests Boundary Change

**Setup**:
- Agent2 controls: b1, b2, b3, b4, b5
- Boundary: b2
- Internal: b1, b3, b4, b5
- Human: h1=red, h2=red

**Agent Behavior**:
1. Agent detects h2=red conflicts with desired b2=red
2. Agent resolves internal conflicts by changing b1, b3, b4, b5 as needed
3. Agent messages human: "Could you change h2 to blue? That would let me set b2 to red."
   - ✅ Mentions b2 (boundary node)
   - ✅ Mentions h2 (neighbor node)
   - ✅ Does NOT mention b1, b3, b4, b5 (internal nodes)

## Testing

### New Test: `test_internal_vs_boundary_nodes.py`

Verifies:
1. ✅ Boundary nodes are correctly identified
2. ✅ Internal nodes can be modified
3. ✅ Boundary nodes are protected from modification

**Sample Output**:
```
[Test] Simulating LLM decision with my_assignments: {'a1': 'blue', 'a2': 'green', 'a3': 'red'}
[Test] After _send_backend_decision, agent assignments: {'a1': 'blue', 'a2': 'green', 'a3': 'blue'}
                                                          ^^^^^^^ ^^^^^^^^^ ^^^^^^^^
                                                          Updated Updated  Protected
                                                          (internal) (internal) (boundary)
[Test] [PASS] Internal nodes modified, boundary nodes protected!
```

### Updated Test: `test_agent_color_stability.py`

Updated expectations to allow internal node changes while protecting boundaries.

## Impact

### Issue 1 Resolution: Agents Now Resolve Internal Conflicts

**Before**: Agent says "I'll take care of the remaining conflicts with my nodes internally" but never does
**After**: Agent actually modifies internal nodes (a1, a3) to resolve conflicts

### Issue 2 Resolution: Agents Only Mention Relevant Nodes

**Before**: Agent2 says "I've assigned colors to nodes b1, b2, b3, b4, b5..."
**After**: Agent2 says "I've set b2 to red. Could you change h2 to blue?"

## Key Takeaway

The distinction between **internal** and **boundary** nodes is critical:

- **Internal nodes**: Private to the agent, can be freely modified, should NOT be mentioned in messages
- **Boundary nodes**: Shared interface with neighbors, require coordination, SHOULD be mentioned in messages
- **Neighbor nodes**: Controlled by others, can only request changes, SHOULD be mentioned in messages

This mirrors the design principle: **agents solve their local subproblems while coordinating at the boundaries**.

## Files Changed

| File | Lines | Change |
|------|-------|--------|
| `tool_calling_cluster_agent.py` | 333-357 | Updated system prompt context |
| `tool_calling_cluster_agent.py` | 372-393 | Updated negotiation strategy |
| `tool_calling_cluster_agent.py` | 634-653 | Filter my_assignments (internal only) |
| `react_cluster_agent.py` | 186-206 | Updated final answer format |
| `react_cluster_agent.py` | 219-243 | Updated context building |
| `react_cluster_agent.py` | 524-543 | Filter my_assignments (internal only) |

## Related Documentation

- `docs/FIX_LLM_AGENT_NEGOTIATION.md` - Original fix (now superseded)
- `tests/test_internal_vs_boundary_nodes.py` - Verification tests
- `CLAUDE.md` - Partial observability constraints
