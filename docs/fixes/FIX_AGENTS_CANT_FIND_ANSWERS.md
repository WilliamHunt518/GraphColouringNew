# Fix: Agents Can't Find Answers (Using Wrong Tools)

**Date**: 2026-02-13
**Issue**: Agents appear stuck and say they "can't find answers" instead of asking the human to change colors.

---

## Problem

From Agent1 logs:
```
[TOOL] Executing: check_feasibility({'node': 'h4', 'color': 'blue'})
[API] check_feasibility(h4, blue) -> Node not in cluster

[TOOL] Executing: simulate_neighbor_change({})
[TOOL] Error: missing required argument: 'neighbor_nodes'

[TOOL] Backend decision: Based on the feasibility checks, changing the color of h4 to
either blue or green would still result in conflicts, indicating that these changes
alone are not sufficient to resolve the existing issues...
```

**What happened**:
1. Agent tried to use `check_feasibility()` on h4 (a neighbor node) ✗
2. API returned "Node not in cluster" because h4 is not Agent1's node
3. Agent tried `simulate_neighbor_change()` with empty dict `{}` ✗
4. Got an error for missing argument
5. Agent gave up and said "can't resolve conflicts"

**Root cause**: Agent used the WRONG tool for testing neighbor color changes!

---

## Why This Happened

### The Confusion

The API has multiple tools that sound similar:

1. **check_feasibility(node, color)**: Tests if one of YOUR nodes can be assigned a color
   - Use case: "Can I set my node a4 to blue?"
   - Only works for nodes YOU control

2. **simulate_neighbor_change(neighbor_nodes={...})**: Tests hypothetical neighbor colors
   - Use case: "What if the human changes h4 to blue?"
   - This is THE tool for testing neighbor changes

The agent confused these and tried to use `check_feasibility()` on a neighbor node (h4), which failed.

### Why Agent Didn't Recover

After the first tool failed, the agent tried `simulate_neighbor_change()` but called it with an empty dict instead of:
```python
simulate_neighbor_change(neighbor_nodes={"h4": "blue"})
```

So it got another error and concluded it couldn't find a solution.

---

## Solution

### 1. Clarified Tool Categories

Changed tool descriptions from flat list to categorized:

**Before**:
```
**Available tools**:
- compute_assignments: Run local solver
- check_feasibility: Test specific node-color assignment
- simulate_neighbor_change: Test neighbor recoloring impact
...
```

**After**:
```
**Available tools** (use the RIGHT tool for each task):

**For testing YOUR nodes**:
- check_feasibility(node="a4", color="blue"): Test if YOUR node can be a color
- compute_assignments(algorithm="greedy"): Run local solver on your nodes

**For testing NEIGHBOR node changes** (CRITICAL FOR NEGOTIATION):
- simulate_neighbor_change(neighbor_nodes={"h4": "blue"}): Test if neighbor changing h4 to blue resolves conflicts
  * This is THE tool to use when testing "what if the human changes h4 to blue?"
  * Returns penalty with that hypothetical change
  * Example: simulate_neighbor_change(neighbor_nodes={"h4": "blue", "h1": "green"})
```

### 2. Added Explicit Workflow Example

**Before**: Generic examples of good messages

**After**: Step-by-step workflow showing tool usage:
```
**Example workflow for requesting neighbor change**:
1. Call get_current_penalty() → sees conflict on edge (a4, h4)
2. Call simulate_neighbor_change(neighbor_nodes={"h4": "blue"}) → penalty=0
3. Send message: "Could you change h4 from red to blue?"
4. Fill requested_changes: {"h4": "blue"}
```

### 3. Enhanced Negotiation Strategy

**Before**:
```
PHASE 2 - Boundary Negotiation:
1. If conflicts remain, call simulate_neighbor_change() with SPECIFIC node-color pairs
2. Test each option: {"h4": "blue"}, {"h4": "green"}, etc.
```

**After**:
```
PHASE 2 - Boundary Negotiation (ASK NEIGHBOR TO CHANGE):
1. **CRITICAL**: Use simulate_neighbor_change() to test neighbor color changes:
   - Example: simulate_neighbor_change(neighbor_nodes={"h4": "blue"})
   - This tests "what if h4 becomes blue?" without actually changing it
   - Try multiple options: {"h4": "blue"}, {"h4": "green"}, {"h4": "yellow"}

2. Find which change gives penalty=0:
   - If simulate_neighbor_change({"h4": "blue"}) returns penalty=0 → ask for h4=blue

**COMMON MISTAKES TO AVOID**:
❌ DON'T use check_feasibility(node="h4", color="blue") for neighbor nodes
   → This only works for YOUR nodes, not neighbor nodes!
✓ DO use simulate_neighbor_change(neighbor_nodes={"h4": "blue"}) for neighbor nodes
   → This is the correct tool for testing neighbor color changes!
```

### 4. Updated ReAct Example

Changed the ReAct example to show iterative testing with correct tool:

```python
Thought: I have conflicts on edges (a4, h4) and (a2, h1). Let me test if changing h4 to blue would help.
Action: simulate_neighbor_change(neighbor_nodes={"h4": "blue"})
Observation: {"penalty": 10, "conflicts": [("a2", "h1")], "feasible": false}

Thought: That only partially helps. Let me test changing both h4 AND h1.
Action: simulate_neighbor_change(neighbor_nodes={"h4": "blue", "h1": "green"})
Observation: {"penalty": 0, "conflicts": [], "feasible": true}

Thought: Perfect! Ask them to make these changes.
```

---

## Files Modified

### Tool Calling Agent (`agents/tool_calling_cluster_agent.py`)

**Lines 422-450**: Categorized tool descriptions with clear use cases
- "For testing YOUR nodes" section
- "For testing NEIGHBOR node changes (CRITICAL FOR NEGOTIATION)" section
- Explicit examples with correct arguments

**Lines 403-408**: Added workflow example showing correct tool usage sequence

**Lines 452-479**: Enhanced negotiation strategy with common mistakes section
- Shows simulate_neighbor_change() usage step-by-step
- Warns against using check_feasibility() for neighbor nodes
- Provides concrete examples: `{"h4": "blue"}`, `{"h4": "green"}`

### ReAct Agent (`agents/react_cluster_agent.py`)

**Lines 145-171**: Categorized action descriptions (same structure as tool calling agent)

**Lines 158-191**: Updated example showing iterative testing with simulate_neighbor_change()
- Shows testing single change, then multiple changes
- Demonstrates correct response when penalty=0

---

## Key Differences in Tools

| Tool | Purpose | Works On | Example |
|------|---------|----------|---------|
| `check_feasibility(node, color)` | Test if YOUR node can be assigned a color | Your cluster nodes only | `check_feasibility(node="a4", color="blue")` |
| `simulate_neighbor_change(neighbor_nodes={...})` | Test if neighbor changes would resolve conflicts | Neighbor nodes | `simulate_neighbor_change(neighbor_nodes={"h4": "blue"})` |
| `compute_assignments(algorithm)` | Find best coloring for YOUR nodes | Your cluster nodes only | `compute_assignments(algorithm="greedy")` |
| `get_best_response_to(neighbor_assignments)` | Find best coloring given neighbor colors | Your cluster nodes | `get_best_response_to(neighbor_assignments={"h4": "blue"})` |

---

## Expected Behavior

### Before Fix

```
Agent: Let me test if h4=blue works...
Action: check_feasibility(node="h4", color="blue")
Result: Error - "Node not in cluster"
Agent: I can't find a solution.
```

### After Fix

```
Agent: Let me test if h4=blue works...
Action: simulate_neighbor_change(neighbor_nodes={"h4": "blue"})
Result: penalty=0, conflicts=[]
Agent: "Could you change h4 from red to blue? That would resolve all conflicts."
```

---

## Testing

Run LLM_TOOL mode and check Agent1_log.txt:

**Should see**:
```
[TOOL] Executing: simulate_neighbor_change({"h4": "blue"})
[API] simulate_neighbor_change(...) -> penalty=0
[TOOL] Sending: "Could you change h4 from red to blue?"
```

**Should NOT see**:
```
[TOOL] Executing: check_feasibility({'node': 'h4', 'color': 'blue'})
[API] check_feasibility(h4, blue) -> Node not in cluster
```

---

## Why Agents Aren't Treating Human Colors as Fixed

The user suspected agents were treating human assignments as fixed constraints. Actually:

1. **Human colors ARE visible** to agents (via `neighbour_assignments`)
2. **Human colors are NOT treated as fixed** - agents can request changes
3. **The problem was tool confusion** - agents tried to test changes but used wrong tool

The solver (`_best_local_assignment_for`) uses current neighbor colors as input to find the best LOCAL response, but this doesn't prevent requesting NEIGHBOR changes. It's designed as:
- Phase 1: Find best response to CURRENT neighbor colors
- Phase 2: If still have conflicts, ask neighbor to change

The bug was that Phase 2 (asking neighbor to change) was using the wrong tool and failing.

---

## Future Improvements

1. **API guard**: Make `check_feasibility()` give clearer error: "h4 is not your node. Use simulate_neighbor_change() to test neighbor colors."
2. **Validation**: Check if LLM tries to use wrong tool and suggest correction
3. **Tool descriptions**: Add "ONLY for YOUR nodes" to every tool that doesn't work on neighbor nodes
4. **Examples in every prompt**: Repeat the simulate_neighbor_change() example multiple times

The current fix (clear categorization + examples + mistakes to avoid) should significantly improve agent tool selection!
