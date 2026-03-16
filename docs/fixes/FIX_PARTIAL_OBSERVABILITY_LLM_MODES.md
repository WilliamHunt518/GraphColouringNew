# Fix: Partial Observability Violations in LLM Modes

**Date**: 2026-02-13
**Issue**: Agents in LLM_TOOL and LLM_REACT modes were violating partial observability constraints by mentioning nodes they couldn't see.

---

## Problem Description

From the user's logs:

```
[Agent2] Hi there! Could you please change the color of node h1 from red to blue?
This change would help clear up some conflicts with the neighboring nodes h2 and h3
I'm dealing with. Thanks for considering th
```

**Why this is wrong**:
- Agent2's boundary nodes: `['b2']` (only b2)
- Agent2's visible neighbors: Should only be Human nodes connected to b2
- But Agent2 mentioned: h1, h2, h3 - nodes it shouldn't know about!

**Root cause**: The backend LLM prompt was showing ALL neighbor assignments:

```python
**Neighbor assignments**: {self.neighbour_assignments}
```

This leaked hidden topology information, allowing Agent2 to "see" h1, h2, h3, h4, h5 even though only h3 has an edge to Agent2's cluster.

---

## Solution

### 1. Compute Visible Neighbor Nodes (Partial Observability Filter)

Added logic to identify which neighbor nodes have edges to this agent's cluster:

```python
# CRITICAL: Identify VISIBLE neighbor nodes (partial observability)
# Only show neighbor nodes that have edges to this agent's cluster
visible_neighbor_nodes = set()
for u, v in self.problem.edges:
    if u in self.nodes and v not in self.nodes:
        visible_neighbor_nodes.add(v)
    elif v in self.nodes and u not in self.nodes:
        visible_neighbor_nodes.add(u)

# Filter neighbor assignments to only visible nodes
visible_neighbor_assignments = {
    node: color for node, color in self.neighbour_assignments.items()
    if node in visible_neighbor_nodes
}
```

**Example**: If Agent2 controls b1-b5 and only b2 has an edge to h3:
- `visible_neighbor_nodes = {'h3'}`
- `visible_neighbor_assignments = {'h3': 'green'}`
- Agent2 does NOT see h1, h2, h4, h5

### 2. Identity-Based Framing

Changed prompt from generic "You are a graph coloring agent" to:

```
You are "{self.name}", a graph coloring agent.

**IDENTITY**:
- Your name: Agent2
- Your cluster: The nodes you control
- Your role: Coordinate with neighbors to resolve conflicts

**YOUR NODES** (you control these):
- INTERNAL nodes: b1, b3, b4, b5 (modify these freely, silently)
- BOUNDARY nodes: b2 (coordinate these with neighbors)
- Current assignments: {assignments}

**VISIBLE NEIGHBOR NODES** (partial observability - you can ONLY see these):
- Visible nodes: h3
- Their assignments: {'h3': 'green'}
- You CANNOT see other neighbor nodes (they don't have edges to your cluster)
```

### 3. Strengthened Constraints

Added explicit partial observability constraints to MESSAGE RULES:

```
**CRITICAL MESSAGE RULES** (PARTIAL OBSERVABILITY):
Your messages must ONLY mention:
- YOUR BOUNDARY NODES: b2
- VISIBLE NEIGHBOR NODES: h3
- NEVER YOUR INTERNAL NODES: b1, b3, b4, b5
- NEVER INVISIBLE NODES: You cannot mention nodes you don't have edges to!

**Examples of BAD messages (DO NOT DO THIS)**:
❌ "Change h1, h2, h3" (mentions nodes not in your visible set - VIOLATES PARTIAL OBSERVABILITY!)
```

---

## Files Modified

### Tool Calling Agent (`agents/tool_calling_cluster_agent.py`)

**Lines 337-359**: `_build_system_prompt()` method
- Compute `visible_neighbor_nodes` from graph edges
- Filter `visible_neighbor_assignments`
- Show only visible nodes in prompt

**Lines 389-404**: MESSAGE RULES section
- List VISIBLE NEIGHBOR NODES explicitly
- Add bad example for invisible nodes
- Emphasize "ONLY VISIBLE NODES"

**Lines 438-447**: Output format specification
- Update "reason" field documentation
- Clarify: "ONLY your boundary nodes and VISIBLE neighbor nodes"

### ReAct Agent (`agents/react_cluster_agent.py`)

**Lines 220-242**: `_build_context()` method
- Same filtering logic as tool calling agent
- Compute and filter visible neighbor nodes

**Lines 272-298**: MESSAGE RULES section
- Same strengthened constraints
- Add partial observability bad example

**Lines 179-219**: System prompt (`_load_react_prompt()`)
- Add partial observability guidelines
- Define visible vs invisible neighbor nodes
- Update Final Answer format

---

## Testing

Created `tests/test_partial_observability_llm_modes.py`:

```python
def test_visible_neighbor_filtering():
    """Verify agents correctly identify visible neighbor nodes."""

    # Agent2 controls b1-b5
    # Only h3 has edge to b2

    visible_neighbor_nodes = compute_visible_nodes(agent2_nodes, edges)

    assert visible_neighbor_nodes == {"h3"}
    assert "h1" not in visible_neighbor_nodes
    assert "h2" not in visible_neighbor_nodes
    # ... h4, h5 also not visible
```

**Test results**: ✓ All tests pass

---

## Expected Behavior Now

### Before Fix
```
[Agent2] Hi there! Could you please change the color of node h1 from red to blue?
This change would help clear up some conflicts with the neighboring nodes h2 and h3
I'm dealing with.
```

**Problem**: Mentions h1, h2, h3 (Agent2 shouldn't see h1, h2)

### After Fix
```
[Agent2] Hi! I notice my boundary node b2=red conflicts with your h3=red.
Could you change h3 to blue? That would resolve the conflict.
```

**Correct**: Only mentions b2 (own boundary) and h3 (visible neighbor)

---

## Key Insights

1. **LLMs don't automatically respect partial observability** - You must explicitly filter the information they see in prompts.

2. **Identity-based framing helps** - "You are Agent2" clarifies who the agent is and what they should know.

3. **Explicit lists are critical** - Listing "VISIBLE NEIGHBOR NODES: h3" prevents LLMs from hallucinating other nodes.

4. **Bad examples matter** - Showing "❌ Change h1, h2, h3 (VIOLATES PARTIAL OBSERVABILITY!)" reinforces the constraint.

5. **Filter data, don't just warn** - Don't show `{h1: red, h2: blue, h3: green}` and say "ignore h1, h2". Instead, only show `{h3: green}`.

---

## Related Documentation

- `CLAUDE.md`: Partial observability constraints (system overview)
- `docs/MULTI_LAYER_LLM_ARCHITECTURE.md`: LLM_TOOL and LLM_REACT architecture
- `tests/test_partial_observability_llm_modes.py`: Automated tests

---

## Future Improvements

1. **Validation layer**: Check LLM output for mentions of invisible nodes, reject if found
2. **Logging**: Log when LLM attempts to mention invisible nodes (helps debug prompt issues)
3. **Speech layer filtering**: SpeechLLMLayer could also filter out invisible node mentions
4. **API guards**: API functions could reject operations on invisible nodes

The current fix addresses the root cause (prompt leakage) - validation would add defense-in-depth.
