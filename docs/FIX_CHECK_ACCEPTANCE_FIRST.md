# Fix: Agents Asking for Changes When Current Config Already Works

**Date**: 2026-02-13
**Issue**: Agents requesting changes even when penalty=0 achievable with current configuration
**Status**: ✅ Fixed

## Problem Description

User reported: *"STILL it's asking for changes when I know I've given it a colouring that it can fit a config around! Part of the thinking process should include best response and whether the best response is penalty-free"*

Agents were asking for changes even when:
- Human provided a valid configuration
- Agent could achieve penalty=0 with current human colors
- No negotiation needed

**Example**:
```
Human sets: h1=red, h2=blue
Agent CAN achieve penalty=0 with: a1=blue, a2=blue, a3=red
But agent says: "Could you change h1 to green?" ← WRONG!
Agent should say: "Great! That works, penalty=0" ← CORRECT!
```

## Root Cause

Agents were not checking if current configuration already works **before** proposing changes.

**Missing workflow step**:
1. ~~Check if current neighbor config allows penalty=0~~ ← **SKIPPED THIS!**
2. If not, propose changes

The agent prompts had negotiation strategies but didn't emphasize checking acceptance FIRST.

## Solution

Added **PHASE 0** to negotiation strategy: Check if current config already works.

### Changes to Tool Calling Agent

**File**: `agents/tool_calling_cluster_agent.py`

**Added PHASE 0** (lines 463-479):
```python
PHASE 0 - Check if Current Config Already Works (ALWAYS DO THIS FIRST!):
1. Call get_current_penalty() to see current state
2. **CRITICAL**: Call get_best_response_to() with CURRENT neighbor assignments
   - Example: get_best_response_to(neighbor_assignments={{"h4": "red", "h1": "blue"}})
   - This finds YOUR optimal assignments given their CURRENT colors
3. If result has penalty=0: **ACCEPT IT!**
   - Set message_type="acceptance"
   - Set my_assignments to the result from get_best_response_to()
   - Set reason="Great! With your current settings, I can achieve penalty=0."
   - Set requested_changes={{}} (empty - no changes needed!)
   - Send message and STOP (don't proceed to Phase 2)
4. If penalty > 0: Proceed to PHASE 2 (negotiation)

**IMPORTANT**: ALWAYS check if current config works BEFORE asking for changes!
```

**Updated workflow section** (lines 512-521):
```python
**CRITICAL WORKFLOW** (follow this order EVERY TIME):
1. Call get_best_response_to(neighbor_assignments=<CURRENT neighbor colors>)
2. Check the penalty result
3. If penalty=0 → message_type="acceptance", requested_changes={{}}
4. If penalty > 0 → Test alternatives, then message_type="proposal" with specific requested_changes
```

**Enhanced message type description** (line 513):
```python
- **acceptance**: You checked get_best_response_to() with CURRENT neighbor colors and found penalty=0 → ACCEPT IT! Set requested_changes={{}} (empty)
```

### Changes to ReAct Agent

**File**: `agents/react_cluster_agent.py`

**Added Example 1** showing acceptance workflow (lines 166-183):
```python
**Example 1** (ALWAYS CHECK ACCEPTANCE FIRST):
Thought: First, I should check if I can achieve penalty=0 with the human's CURRENT settings.
Action: get_best_response_to(neighbor_assignments={"h4": "red", "h1": "blue"})
Observation: {"a1": "green", "a2": "red", "a3": "red", "a4": "blue", "penalty": 0}

Thought: Perfect! I can achieve penalty=0 with their current settings. I should accept this!
Final Answer: {
  "should_send_message": true,
  "recipient": "Human",
  "message_type": "acceptance",
  "structured_content": {
    "my_assignments": {"a1": "green", "a2": "red", "a3": "red", "a4": "blue"},
    "reason": "Great! With your current settings, I can achieve penalty=0.",
    "requested_changes": {}
  }
}
```

**Updated Example 2** to show checking current config before negotiating (lines 185-195):
```python
Thought: Let me check if I can find a penalty-free solution with their CURRENT colors first.
Action: get_best_response_to(neighbor_assignments={"h4": "red", "h1": "red"})
Observation: {"a1": "green", "a2": "blue", "a3": "red", "a4": "blue", "penalty": 20}

Thought: Still penalty=20, so I need to request changes. Let me test if changing h4 to blue would help.
```

**Added explicit workflow** (lines 218-222):
```python
**Workflow** (ALWAYS follow this order):
1. **ALWAYS check acceptance FIRST**: Call get_best_response_to() with CURRENT neighbor assignments
2. If penalty=0 → ACCEPT (message_type="acceptance", requested_changes={})
3. If penalty > 0 → Negotiate (test alternatives with simulate_neighbor_change, then make proposal)
```

**Updated Guidelines** (line 221):
```python
3. **CRITICAL**: ALWAYS check if current config works before asking for changes!
```

## Testing

**Test file**: `tests/test_agent_accepts_valid_config.py`

Two test cases:
1. ✅ Agent accepts valid configuration (penalty=0 achievable)
2. ✅ Complete workflow (acceptance vs negotiation)

Test output:
```
Test 1: Agent accepts valid configuration
Current neighbor assignments: {'h1': 'red', 'h2': 'blue'}
Best response: {'a1': 'red', 'a2': 'blue', 'a3': 'red'}
Penalty with best response: 0.0
[PASS] Agent can achieve penalty=0 with human's current configuration
[PASS] Agent should ACCEPT this config, not ask for changes!

Test 2: Complete workflow (acceptance vs negotiation)
Case 1: Human config is VALID (should ACCEPT)
Human sets: h1=red
Agent's best response: {'a1': 'red', 'a2': 'blue'}
Penalty: 0.0
[PASS] Agent should send message_type='acceptance' with requested_changes={}
```

## Expected Behavior After Fix

**Before**:
```
Human: [Sets h1=red, h2=blue]
Agent: "Could you change h1 to green?"
Human: "But this already works! Why are you asking for changes?"
```

**After**:
```
Human: [Sets h1=red, h2=blue]
Agent: [Checks get_best_response_to({"h1": "red", "h2": "blue"})]
Agent: [Sees penalty=0 achievable]
Agent: "Great! With your current settings, I can achieve penalty=0."
       [report: {"a1": "red", "a2": "blue", "a3": "red"}]
Human: "Perfect!"
```

## Key Workflow

**Correct agent reasoning**:
1. Receive message from human (with [config: ...] tag showing current colors)
2. Call `get_best_response_to(neighbor_assignments=<current_colors>)`
3. Check penalty in result:
   - If penalty=0: **ACCEPT** (message_type="acceptance", requested_changes={})
   - If penalty > 0: **NEGOTIATE** (test alternatives, make proposal)

**Critical API calls**:
```python
# Step 1: Check if current config works
result = get_best_response_to(neighbor_assignments={"h1": "red", "h2": "blue"})
# result = {"a1": "red", "a2": "blue", "a3": "red", "penalty": 0}

# Step 2: If penalty=0, accept!
if result["penalty"] == 0:
    return {
        "message_type": "acceptance",
        "my_assignments": result,  # WITHOUT "penalty" key
        "reason": "Great! With your current settings, I can achieve penalty=0.",
        "requested_changes": {}  # EMPTY!
    }
```

## Files Modified

1. **`agents/tool_calling_cluster_agent.py`**
   - Lines 463-479: Added PHASE 0 (check acceptance first)
   - Lines 512-521: Added CRITICAL WORKFLOW
   - Line 513: Enhanced acceptance message type description

2. **`agents/react_cluster_agent.py`**
   - Lines 166-183: Added Example 1 (acceptance case)
   - Lines 185-195: Updated Example 2 (check current before negotiating)
   - Lines 218-222: Added explicit workflow
   - Line 221: Updated guideline to emphasize checking current config

3. **`tests/test_agent_accepts_valid_config.py`** (new file)
   - Tests agent acceptance behavior
   - Verifies agents accept valid configs instead of asking for changes

## Key Insights

1. **Check acceptance FIRST**: Always test if current config works before proposing alternatives
2. **get_best_response_to() is the key**: This function finds optimal assignments given current neighbor colors
3. **Acceptance message format**:
   - `message_type="acceptance"`
   - `requested_changes={}` (empty!)
   - `reason="Great! With your current settings, I can achieve penalty=0."`
4. **Workflow matters**: The ORDER of operations is critical - check acceptance before negotiation

## Related Fixes

This fix builds on:
- **Fix: Exhaustive Algorithm** (agents now find optimal solutions)
- **Fix: Agent Plan Commitment** (agents know their plan via get_best_response_to())
- **Fix: Config in Messages** (agents receive current human config via [config: ...] tag)

Together, these fixes enable agents to:
1. Receive current human configuration
2. Find optimal response (exhaustive search)
3. Check if optimal response is penalty-free
4. Accept if yes, negotiate only if no
