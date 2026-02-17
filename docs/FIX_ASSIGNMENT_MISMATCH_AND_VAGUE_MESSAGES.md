# Fix: Assignment Mismatch and Vague Messages in LLM Modes

**Date**: 2026-02-13
**Issues**: Two problems in LLM_TOOL and LLM_REACT modes:
1. Agent says "a4 is green" but UI shows a4 as red (assignment mismatch)
2. Agent says "make a change" instead of "change h4 from red to blue" (vague messages)

---

## Issue 1: Assignment Mismatch (a4 green vs red)

### Problem

From communication logs:
```
Line 4: Agent1->Human  __SILENT__ [report: {"a2": "blue", "a4": "red", "a5": "blue"}]
        (Announcement: a4 is RED)

Line 6: Agent1->Human  I propose changing h4 from red to blue. This would help avoid
        a conflict with my boundary node a4, which is currently green.
        [report: {"assignments": {"a3": "red", "a4": "green", "a5": "red"}}]
        (Agent thinks a4 is GREEN, says it in message)
```

**What happened**:
1. Agent1 announced: a4=red ✓ (UI updated correctly)
2. Agent1 received human message (h1=red, h4=red)
3. Agent1's backend LLM modified internal assignments: a4→green
4. Agent1 sent report: `{"assignments": {"a4": "green"}}`
5. UI did NOT update a4 to green ✗ (still showed red)

### Root Cause

**Speech layer wrapped assignments in nested structure**:
```python
# WRONG - nested format
report = {"assignments": content["my_assignments"]}
nl_message += f" [report: {json.dumps(report)}]"
# Result: [report: {"assignments": {"a4": "green"}}]
```

**UI expects flat format**:
```python
# UI code
for node, col in report.items():  # Expects (node, color) pairs
    self._known_neighbour_colours[str(node)] = col
```

When UI receives `{"assignments": {"a4": "green"}}`, it tries to do:
```python
self._known_neighbour_colours["assignments"] = {"a4": "green"}  # WRONG!
```

Instead of:
```python
self._known_neighbour_colours["a4"] = "green"  # CORRECT
```

### Solution

Changed speech layer to use flat format:

**Before**:
```python
report = {"assignments": content["my_assignments"]}
nl_message += f" [report: {json.dumps(report)}]"
```

**After**:
```python
# Flat format for UI extraction
nl_message += f" [report: {json.dumps(content['my_assignments'])}]"
```

**Result**:
- Before: `[report: {"assignments": {"a4": "green"}}]` ✗
- After: `[report: {"a4": "green"}]` ✓

### Files Modified

`comm/speech_llm_layer.py`:
- Line 332-334: LLM rendering
- Line 450-453: Template rendering (LLM announcement messages)
- Line 498-501: Template rendering (regular messages)

All three locations now use flat format: `json.dumps(assignments)` instead of `json.dumps({"assignments": assignments})`.

---

## Issue 2: Vague Messages

### Problem

Agent2 said:
```
"I've assigned the colors as follows: b1 and b4 are green, while b2, and b5 are red.
However, due to no alternative colors being available for the boundary nodes h2 and h5,
and to address ongoing conflicts, I suggest we consider changing the color of a
neighboring node that is visible. What do you think?"
```

**Issues**:
- ❌ "a neighboring node that is visible" - which node?
- ❌ "changing the color" - to what color?
- ❌ Not actionable like RB mode

**Should be like RB mode**:
- ✓ "Could you change h4 from red to blue?"
- ✓ Specific node (h4), specific colors (red→blue)

### Root Cause

LLMs are naturally conversational/polite and avoid being overly direct. The prompt said "be specific" but didn't FORCE specificity with:
1. Strong bad examples of vague language
2. Required output format enforcing node-color pairs
3. Explicit templates to follow

### Solution

Strengthened prompts in **three ways**:

#### 1. Added More Bad Examples

**Before**:
```
**Examples of BAD messages (DO NOT DO THIS)**:
❌ "Could you adjust your colors?" (too vague, not actionable)
```

**After**:
```
**Examples of BAD messages (DO NOT DO THIS)**:
❌ "Could you adjust your colors?" (too vague, not actionable)
❌ "I suggest we consider changing the color of a neighboring node" (VAGUE - which node? what color?)
❌ "Please make a change to resolve conflicts" (VAGUE - what specific change?)
❌ "We should modify some boundary nodes" (VAGUE - which nodes? what colors?)
```

#### 2. Strengthened Output Format Requirements

**Before**:
```
"structured_content": {
  "reason": "SPECIFIC request with ONLY boundary nodes...",
  "requested_changes": {"neighbor_node": "color", ...}
}
```

**After**:
```
"structured_content": {
  "my_assignments": {"a1": "red", "a3": "blue"},  // Concrete example
  "reason": "Could you change h4 from red to blue? That would resolve the conflict with my boundary node a4.",
  "requested_changes": {"h4": "blue"}  // REQUIRED: Exact node names and target colors!
}

**CRITICAL REQUIREMENTS FOR "reason" FIELD**:
1. Must use TEMPLATE: "Could you change [exact_node] from [current_color] to [new_color]?"
2. Must specify EXACT node names (e.g., "h4", not "a neighboring node")
3. Must specify EXACT colors (e.g., "blue", not "a different color")
4. NEVER say "make a change" or "adjust colors" - always specify exact node and color!

**CRITICAL REQUIREMENTS FOR "requested_changes" FIELD**:
1. Must contain at least one specific node-color pair if making a proposal
2. Example: {"h4": "blue", "h1": "green"} (exact nodes, exact colors)
3. Never leave empty if you're requesting changes!
```

#### 3. Enhanced Negotiation Strategy

**Before**:
```
PHASE 2 - Boundary Negotiation (message to neighbor):
- If conflicts remain at boundaries, make SPECIFIC request
- Be SPECIFIC like RB mode, not vague
```

**After**:
```
PHASE 2 - Boundary Negotiation (message to neighbor):
1. If conflicts remain, call simulate_neighbor_change() with SPECIFIC node-color pairs
2. Test each option: {"h4": "blue"}, {"h4": "green"}, etc.
3. Choose the BEST specific solution (lowest penalty)
4. Make SPECIFIC request with EXACT nodes and colors:
   - Template: "Could you change [exact_node] from [current_color] to [target_color]?"
   - Example: "Could you change h4 from red to blue?"
   - Fill requested_changes with: {"h4": "blue"}
5. NEVER say "make a change" or "adjust colors" - always specify exact node and color!
```

### Files Modified

#### Tool Calling Agent (`agents/tool_calling_cluster_agent.py`)

- **Lines 410-418**: Added 3 more bad examples of vague messages
- **Lines 431-450**: Enhanced negotiation strategy with step-by-step instructions
- **Lines 451-480**: Strengthened output format with explicit templates and requirements

#### ReAct Agent (`agents/react_cluster_agent.py`)

- **Lines 268-277**: Added 3 more bad examples
- **Lines 190-196**: Enhanced strategy with specific action steps
- **Lines 195-220**: Strengthened Final Answer format with templates and requirements

---

## Expected Behavior

### Before Fixes

**Issue 1 - Assignment Mismatch**:
```
Agent1: "...my boundary node a4, which is currently green"
UI: Shows a4 as red (doesn't match what agent said)
```

**Issue 2 - Vague Messages**:
```
Agent2: "I suggest we consider changing the color of a neighboring node that is visible"
```

### After Fixes

**Issue 1 - Fixed**:
```
Agent1: "...my boundary node a4, which is currently green"
UI: Shows a4 as green (matches!)
```

**Issue 2 - More Specific**:
```
Agent2: "Could you change h3 from green to blue? That would resolve the conflict with my boundary node b2."
```

---

## Key Design Principles

1. **Force specificity through structure**: Require `requested_changes` dict with explicit node-color pairs
2. **Provide templates**: Give exact format like "Could you change [node] from [color] to [color]?"
3. **Show bad examples**: Explicitly demonstrate what NOT to do ("make a change")
4. **Guide with strategy**: Step-by-step instructions including which API calls to make
5. **Preserve LLM_TOOL ethos**: Use prompting, not hard validation/rejection (respects LLM autonomy)

---

## Testing

Test both issues:

1. **Assignment Mismatch**:
   - Run LLM_TOOL mode
   - After agent changes internal nodes, check if UI colors match agent's statements
   - Report tags should use flat format: `[report: {"a4": "green"}]`

2. **Message Specificity**:
   - Run LLM_TOOL/LLM_REACT mode
   - Agent messages should specify exact nodes and colors
   - Look for phrases like "Could you change h4 from red to blue?"
   - Should NOT see "make a change" or "adjust colors"

---

## Future Enhancements

If vague messages persist, consider:

1. **Validation layer**: Check `requested_changes` dict is non-empty for proposals
2. **Retry mechanism**: If message is vague, ask LLM to be more specific
3. **Template enforcement**: Parse "reason" field and ensure it matches template
4. **Logging**: Track when LLM generates vague messages for prompt iteration

But current approach (strong prompting) respects LLM_TOOL architecture while significantly improving specificity.
