# LLM_RB Rich Conditional Offers

## Overview

This document describes enhancements to LLM_RB mode to ensure conditional offers are as rich and multi-node as pure RB mode offers.

## Changes Made (2026-02-10)

### Problem

In RB mode, agents make rich multi-node conditional offers like:
- "If you could do h1=red, h2=blue, h5=green, then I could handle b1=yellow, b2=red, b3=blue"

But in LLM_RB mode, the UI guidance was weak:
- Help text: "Type natural language messages (e.g., 'I think h1 should be red')"
- Placeholder: "Type a message…"
- This encouraged simple single-node proposals instead of rich conditional offers

### Solution

Enhanced multiple components to encourage and support rich multi-node conditional offers:

#### 1. UI Help Text Enhancement (`ui/human_turn_ui.py:597-603`)

**Before:**
```
BARGAIN PHASE: Type natural language messages (e.g., 'I think h1 should be red')
```

**After:**
```
BARGAIN PHASE: Make conditional offers using natural language
Example: 'If you could do h1=red and h2=blue, then I could handle b1=green and b2=yellow'
```

#### 2. Placeholder Text Enhancement (`ui/human_turn_ui.py:3006-3012`)

**Before:**
```python
placeholder = "Type a message…"
```

**After:**
```python
# Mode-aware placeholder text
llm_rb_mode = getattr(self, '_llm_rb_mode', False)
if llm_rb_mode:
    placeholder = "If you do X, then I'll do Y…"
else:
    placeholder = "Type a message…"
```

#### 3. Agent→Human Rendering Enhancement (`comm/llm_rb_comm_layer.py:198-227`)

Made conditional offer rendering more explicit about multi-node coordination:

**Before:**
```python
if len(conditions) == 1:
    return f"If you could set {cond_str}, then I could make {assign_str} work on my side. Would that help?"
else:
    return f"If you could do {cond_str}, then I could handle {assign_str}. Does that work?"
```

**After:**
```python
# Emphasize multi-node coordination when applicable
if len(conditions) > 1 and len(assignments) > 1:
    return f"Here's a solution: if you could do {cond_str}, then I could handle {assign_str}. This should resolve all conflicts. What do you think?"
elif len(conditions) == 1 and len(assignments) > 1:
    return f"If you could set {cond_str}, then I could make {assign_str} work on my side. Would that resolve things?"
# ... etc for other combinations
```

#### 4. LLM Parsing Prompt Enhancement (`comm/llm_rb_comm_layer.py:345-375`)

Enhanced the LLM prompt to emphasize multi-node extraction:

**Added:**
```
- ConditionalOffer: "if you do X, I'll do Y" (ALWAYS extract ALL nodes from both condition and action parts)

IMPORTANT: For ConditionalOffer, extract ALL nodes mentioned in BOTH the IF and THEN parts.
Multi-node offers are common and expected. Don't omit any nodes!

Example:
Input: 'If you could set h1 to red, h2 to blue, and h5 to green, then I could handle b1=yellow, b2=red, and b3=blue'
Output: {"move": "ConditionalOffer", "conditions": [{"node": "h1", "colour": "red", "owner": "neighbor"}, {"node": "h2", "colour": "blue", "owner": "neighbor"}, {"node": "h5", "colour": "green", "owner": "neighbor"}], "assignments": [{"node": "b1", "colour": "yellow"}, {"node": "b2", "colour": "red"}, {"node": "b3", "colour": "blue"}]}
```

#### 5. Heuristic Parser Enhancement (`comm/llm_rb_comm_layer.py:466-520`)

Added comments and logging to clarify that ALL nodes should be captured:

```python
# ENHANCED: Process ALL extracted assignments (not just first occurrence)
# This ensures we capture multi-node offers like "h1=red, h2=blue, h3=green"

# IMPORTANT: Add ALL nodes in condition (not just first)
conditions.append(Condition(node=node, colour=color, owner="neighbor"))

# IMPORTANT: Add ALL nodes in action (not just first)
my_assignments.append(Assignment(node=node, colour=color))
```

## Result

### Human Experience

When using LLM_RB mode, humans now:
1. See guidance encouraging conditional offers with multiple nodes
2. Have a placeholder that prompts IF-THEN structure
3. Receive agent messages that explicitly highlight multi-node coordination

### Agent Behavior

Agents in LLM_RB mode:
1. Generate the same rich conditional offers as pure RB mode (no change needed - already using same `_generate_conditional_offer()`)
2. Translate offers to natural language with explicit multi-node structure
3. Properly parse human natural language back into rich RBMove structures

### Example Exchange

**Agent → Human:**
```
Here's a solution: if you could do h1=red, h2=blue, then I could handle b1=green, b2=yellow.
This should resolve all conflicts. What do you think?
```

**Human → Agent:**
```
If you could set b3 to red and b4 to blue, then I could make h5=green and h6=yellow work
```

Both directions now support rich multi-node conditional offers that match RB mode's expressiveness.

## Files Modified

- `ui/human_turn_ui.py` - Help text, placeholder
- `comm/llm_rb_comm_layer.py` - Rendering, LLM prompt, heuristic parser

## Testing

Run LLM_RB mode and verify:
1. Help text shows conditional offer example
2. Placeholder encourages IF-THEN structure
3. Agent messages include multiple nodes in conditions and assignments
4. Human can type multi-node conditional offers and they parse correctly
5. Live translation preview shows all nodes being captured
