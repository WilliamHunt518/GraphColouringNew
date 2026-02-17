# Fix: Runtime Message Validation (Partial Observability + Specificity)

**Date**: 2026-02-13
**Issues**:
1. Agents mentioning h nodes they can't see (partial observability violations)
2. Messages not conveying clear questions/requests (vague messages)
**Status**: ✅ Fixed

## Problem Description

User reported two ongoing issues:
1. *"it's asking about my h nodes it can't see sometimes"*
2. *"it still doesn't always convey a clear question or request about my nodes"*

Despite having prompts instructing proper behavior, LLMs sometimes violated these rules:
- Mentioning invisible neighbor nodes (partial observability violations)
- Sending vague messages without specific requests
- Requesting changes to agent's own nodes

**Example violations**:
```
Agent2 can only see h3 (has edge b2-h3)
But Agent2 says: "Could you change h1, h2, and h3?"  <- h1 and h2 are INVISIBLE!

Agent1 says: "Let's review this setup to reduce conflicts"  <- VAGUE, no specific request!
```

## Root Cause

Prompts alone are insufficient - **LLMs don't always follow instructions perfectly**.

The system had validation methods (`_validate_message_specificity()`) but:
1. Validation was incomplete (didn't check partial observability)
2. Validation only logged warnings - **didn't block invalid messages**
3. Bad messages still got sent to users

**Line 714** (tool_calling_cluster_agent.py):
```python
if not is_valid:
    self.log(f"[VALIDATION WARNING] {error_msg}")
    # For now, just log the warning but still send the message  <- PROBLEM!
```

## Solution

Enhanced validation to be **comprehensive and blocking**:

### 1. Added Partial Observability Checks

**Both agents** (tool_calling_cluster_agent.py lines 875-900, react_cluster_agent.py lines 762-787):

```python
# CRITICAL: Check for partial observability violations FIRST
# Compute visible neighbor nodes (only those with edges to our cluster)
visible_neighbor_nodes = set()
for node in self.nodes:
    for neighbor in self.problem.get_neighbors(node):
        if neighbor not in self.nodes:
            visible_neighbor_nodes.add(neighbor)

# Check if message mentions invisible nodes
all_neighbor_nodes = set(self.neighbour_assignments.keys())
invisible_nodes = all_neighbor_nodes - visible_neighbor_nodes

for invisible_node in invisible_nodes:
    # Check both reason and requested_changes
    if invisible_node in reason or invisible_node in requested:
        return False, f"PARTIAL OBSERVABILITY VIOLATION: Message mentions '{invisible_node}' which is NOT visible (no edges to your cluster). Visible nodes: {sorted(visible_neighbor_nodes)}"

# Check requested_changes only mentions visible nodes
if requested:
    for node in requested.keys():
        if node in self.nodes:
            return False, f"OWNERSHIP VIOLATION: requested_changes contains YOUR node '{node}' (should only request NEIGHBOR nodes)"
        if node not in visible_neighbor_nodes:
            return False, f"PARTIAL OBSERVABILITY VIOLATION: requested_changes mentions '{node}' which is NOT visible. Visible nodes: {sorted(visible_neighbor_nodes)}"
```

### 2. Enhanced Vague Message Detection

Added clearer error categories:

```python
# Check for vague phrases
vague_phrases = [
    "make a change", "adjust colors", "modify", "reconsider",
    "let's", "we should", "might need", "consider changing",
    "a neighboring node", "some boundary nodes", "certain colors",
    "review this setup", "further reduce", "different color"
]

for phrase in vague_phrases:
    if phrase.lower() in reason.lower():
        return False, f"VAGUE MESSAGE: Contains phrase '{phrase}' - must be specific with exact node names and colors"
```

### 3. Added Empty/Short Message Detection

```python
# Check reason contains actual specifics (not just empty/generic)
if message_type in ["proposal", "info"] and len(reason.strip()) < 10:
    return False, f"EMPTY REASON: Message reason is too short or empty"
```

### 4. Made Validation BLOCKING (Not Just Logging)

**tool_calling_cluster_agent.py** (lines 709-718):
```python
# BEFORE:
if not is_valid:
    self.log(f"[VALIDATION WARNING] {error_msg}")
    # Just log the warning but still send the message  <- BAD!
self._send_backend_decision(backend_output)  # Always sent

# AFTER:
if not is_valid:
    self.log(f"[VALIDATION FAILED] {error_msg}")
    self.log(f"[VALIDATION FAILED] Invalid message content: {structured_content}")
    self.log(f"[VALIDATION FAILED] Message BLOCKED - not sending to prevent errors")
    # Do NOT send invalid messages
else:
    # Message passed validation - send it
    self._send_backend_decision(backend_output)
```

**react_cluster_agent.py** (lines 514-522): Same changes

## Validation Rules

The system now enforces these rules **at runtime**:

### Rule 1: Partial Observability
- ✅ ALLOW: Mention only visible neighbor nodes (nodes with edges to agent's cluster)
- ❌ BLOCK: Mention invisible neighbor nodes
- ❌ BLOCK: Request changes to invisible nodes

### Rule 2: Node Ownership
- ✅ ALLOW: Request changes to neighbor nodes
- ❌ BLOCK: Request changes to agent's own nodes

### Rule 3: Specificity
- ✅ ALLOW: Specific requests with exact node names and colors
- ❌ BLOCK: Vague phrases like "make a change", "modify nodes", "a neighboring node"

### Rule 4: Substantiveness
- ✅ ALLOW: Messages with concrete content (reason > 10 chars)
- ❌ BLOCK: Empty or too-short messages

## Testing

**Test file**: `tests/test_message_validation.py`

Five test cases verify:
1. ✅ Valid message with visible nodes accepted
2. ✅ Invalid message mentioning invisible h2 blocked
3. ✅ Specific message accepted
4. ✅ Vague message blocked
5. ✅ Ownership violation blocked

All tests pass:
```
Test 1: Valid message (only visible nodes)
[PASS] Valid message accepted

Test 2: Invalid message (mentions invisible h2)
Error: PARTIAL OBSERVABILITY VIOLATION: Message mentions 'h2' which is NOT visible
[PASS] Invalid message blocked (mentions invisible h2)

Test 3: Specific message (good)
[PASS] Specific message accepted

Test 4: Vague message (bad)
Error: VAGUE MESSAGE: Contains phrase 'make a change'
[PASS] Vague message blocked

Test 5: Request to change own node (bad)
Error: OWNERSHIP VIOLATION: requested_changes contains YOUR node 'a1'
[PASS] Ownership violation blocked
```

## Expected Behavior After Fix

### Before Fix

**Partial observability violation**:
```
Agent2 (can only see h3): "Could you change h1, h2, and h3?"
User: "But you can't even see h1 and h2!"
```

**Vague message**:
```
Agent1: "Let's review this setup to reduce conflicts"
User: "What do you want me to change??"
```

### After Fix

**Partial observability enforced**:
```
Agent2 tries to mention h1 (invisible)
Validation: BLOCKED - "h1 is NOT visible. Visible nodes: ['h3']"
Agent2: [No message sent]
[Log shows validation failure]
```

**Specificity enforced**:
```
Agent1 tries: "make a change to reduce conflicts"
Validation: BLOCKED - "VAGUE MESSAGE: Contains phrase 'make a change'"
Agent1: [No message sent]
[Log shows validation failure]
```

**Valid messages get through**:
```
Agent2: "Could you change h3 from red to blue?"  <- Specific, mentions only visible h3
Validation: PASSED
User receives message: "Could you change h3 from red to blue?"
```

## Files Modified

1. **`agents/tool_calling_cluster_agent.py`**
   - Lines 875-930: Enhanced `_validate_message_specificity()` with partial observability checks
   - Lines 709-718: Made validation blocking (reject invalid messages)

2. **`agents/react_cluster_agent.py`**
   - Lines 762-816: Enhanced `_validate_message_specificity()` with partial observability checks
   - Lines 514-522: Made validation blocking (reject invalid messages)

3. **`tests/test_message_validation.py`** (new file)
   - Comprehensive validation tests
   - Tests all violation types

## Key Insights

1. **Prompts alone aren't enough**: LLMs don't always follow instructions perfectly
2. **Runtime validation is essential**: Catch and block violations before they reach users
3. **Validation must be blocking**: Logging warnings isn't enough - must prevent bad messages
4. **Compute visibility dynamically**: Don't trust LLM to know which nodes are visible
5. **Clear error categories**: Help debugging by categorizing violations (PARTIAL OBSERVABILITY, VAGUE MESSAGE, etc.)

## Validation Flow

```
LLM generates message
    |
    v
_validate_message_specificity()
    |
    +-> Check partial observability (visible nodes only)
    +-> Check ownership (no agent's own nodes)
    +-> Check specificity (no vague phrases)
    +-> Check substantiveness (not empty/short)
    |
    v
is_valid?
    |
    +-> YES: Send message
    +-> NO:  Block message, log failure
```

## Related Fixes

This fix builds on:
- **Fix: Partial Observability in Prompts** (added visible_neighbor_nodes filtering to prompts)
- **Fix: Vague Messages** (added templates and bad examples to prompts)
- **Fix: Node Ownership** (added CRITICAL sections about node ownership)

But those fixes only added **instructions** (prompts).
This fix adds **enforcement** (runtime validation).

**Key difference**: Prompts say "don't do this", validation says "I won't let you do this".
