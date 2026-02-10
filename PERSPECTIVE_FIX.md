# Perspective Fix for LLM_RB Rendering

## Problem

User reported: `"[Agent2] If you set b2 to red, then I'll assign b2 the same color."`

This is incorrect! Agent2 owns b-nodes, so should say:
- "If **you** set h2..." (human's nodes)
- "then **I'll** set b2..." (agent's nodes)

NOT "if you set b2..." (agent's own nodes)

## Root Cause Analysis

Two possible causes:
1. **Move generation bug**: Agent creates ConditionalOffer with wrong nodes in conditions/assignments
2. **LLM rendering bug**: LLM doesn't understand which nodes belong to whom

## Fixes Implemented

### Fix 1: Enhanced LLM Prompt with Node Ownership

**File:** `comm/llm_rb_comm_layer.py` (lines 226-340)

Added explicit node ownership information to the LLM prompt:

```python
Sender: Agent2 (controls b-nodes (b1, b2, b3, etc.))
Recipient: Human (controls h-nodes (h1, h2, h3, etc.))

CRITICAL PERSPECTIVE RULES:
- 'conditions' lists = h-nodes that the RECIPIENT controls → use 'you' or 'your'
- 'assignments' lists = b-nodes that the SENDER controls → use 'I' or 'my'
- For ConditionalOffer: 'If YOU set <conditions>, then I'll set <assignments>'
- NEVER say 'if you set' followed by nodes from 'assignments' (sender's nodes)
- NEVER say 'then I'll set' followed by nodes from 'conditions' (recipient's nodes)
- Double-check: conditions should ONLY mention recipient's nodes, assignments should ONLY mention sender's nodes
```

### Fix 2: Move Ownership Validation

**File:** `comm/llm_rb_comm_layer.py` (lines 198-254)

Added validation that detects ownership bugs in move generation:

```python
# Check conditions - should only contain recipient's nodes
if sender_prefix and node.startswith(sender_prefix):
    print("*** CRITICAL BUG DETECTED ***")
    print("Condition contains sender's own node: {node}")
    print("This is a BUG in move generation!")
    # Fall back to templates (skip LLM)
    return None
```

**Effect:**
- If move has wrong node ownership, prints **clear error message**
- Falls back to template rendering (which is perspective-correct)
- Helps diagnose whether bug is in move generation or LLM rendering

### Fix 3: Template Rendering Already Correct

**File:** `comm/llm_rb_comm_layer.py` (lines 394-421)

Templates already use correct perspective:

```python
if conditions:
    cond_str = ", ".join([f"{c.node}={c.colour}" for c in conditions])
    assign_str = ", ".join([f"{a.node}={a.colour}" for a in assignments])
    return f"If you could do {cond_str}, then I could set {assign_str}."
```

- Conditions → "you could do"
- Assignments → "I could set"

## Verification

### Test File: `test_llm_rb_perspective.py`

Runs perspective tests:

```bash
python test_llm_rb_perspective.py
```

**Expected output:**
```
Agent2 -> Human:
  If you have h1 in red and h2 in blue, I will set b1 as green and b2 as yellow.
  [OK] Perspective is correct
```

### Live Debugging

When running LLM_RB mode, watch for this error:

```
======================================================================
[LLMRBCommLayer] *** CRITICAL BUG DETECTED ***
[LLMRBCommLayer] Sender: Agent2 (owns b-nodes)
[LLMRBCommLayer] Recipient: Human (owns h-nodes)
[LLMRBCommLayer] ERROR: Condition contains sender's own node: b2
[LLMRBCommLayer] Conditions should ONLY contain recipient's nodes!
[LLMRBCommLayer] Full move: {...}
======================================================================
```

**If you see this:** The bug is in **move generation** (agent code), NOT rendering.

**If you DON'T see this:** The bug is in **LLM rendering** despite our improved prompt.

## How to Test

1. Run full LLM_RB mode:
   ```bash
   python launch_menu.py
   # Select LLM_RB mode
   ```

2. Watch agent messages carefully

3. Check console for "CRITICAL BUG DETECTED" warnings

4. If bug still occurs:
   - Take screenshot of message
   - Share console output (especially the CRITICAL BUG warning if present)
   - This will help diagnose whether issue is in move generation or LLM

## Expected Behavior

### Correct Examples

**Agent1 → Human:**
```
If you could set h1 to red and h2 to blue, then I could make a1 green and a2 yellow work.
```
- h1, h2 = human's nodes → "you could set"
- a1, a2 = agent1's nodes → "I could make"

**Agent2 → Human:**
```
If you set h3 to green, I'll set b1 to red and b2 to blue.
```
- h3 = human's node → "you set"
- b1, b2 = agent2's nodes → "I'll set"

**Human → Agent1:**
```
If you set a2 to yellow, I can do h1=red and h2=blue.
```
- a2 = agent1's node → "you set"
- h1, h2 = human's nodes → "I can do"

### Incorrect Examples (BUG)

❌ **Agent2 → Human:** "If you set b2 to red..."
- b2 is Agent2's node, should be "I set b2"

❌ **Agent1 → Human:** "then I'll set h1 to blue"
- h1 is Human's node, should be "you set h1"

❌ **Human → Agent2:** "If you set h4 to green..."
- h4 is Human's own node, should be "I set h4"

## Node Ownership Reference

| Agent | Owns | Examples |
|-------|------|----------|
| Agent1 | a-nodes | a1, a2, a3, ... |
| Agent2 | b-nodes | b1, b2, b3, ... |
| Human | h-nodes | h1, h2, h3, ... |

## Fallback Behavior

If LLM rendering fails OR ownership bug detected:
1. System prints warning
2. Falls back to template rendering (always perspective-correct)
3. Experiment continues without crashing

## Summary

We've added:
1. ✅ Explicit node ownership in LLM prompt
2. ✅ Validation to detect ownership bugs
3. ✅ Clear error messages for debugging
4. ✅ Safe fallback to templates
5. ✅ Test suite for perspective correctness

The system should now:
- Generate correct perspective in LLM rendering
- Catch ownership bugs in move generation
- Fall back to templates if issues detected
- Provide clear debugging information

**Next:** Run a full experiment and watch for "CRITICAL BUG DETECTED" messages to diagnose the root cause.
