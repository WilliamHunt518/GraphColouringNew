# Final Test Analysis: LLM_API Agent Behavior

## Summary

I've successfully created a working test that reproduces the issue and identified the ROOT CAUSE.

## Test Results

### ✓ Core Algorithm Works Correctly

The agent's boundary configuration enumeration IS working:

```
When human says: "h1 may need to be red. Can you plan a colouring around this change or not?"

Agent correctly tests:
  - {'h1': 'red', 'h4': 'red'}: penalty=10.00 ❌
  - {'h1': 'red', 'h4': 'green'}: penalty=10.00 ❌
  - {'h1': 'red', 'h4': 'blue'}: penalty=10.00 ❌
  - {'h1': 'green', 'h4': 'red'}: penalty=0.00 ✓
  - {'h1': 'green', 'h4': 'green'}: penalty=0.00 ✓
  - {'h1': 'green', 'h4': 'blue'}: penalty=0.00 ✓
  - {'h1': 'blue', 'h4': 'red'}: penalty=0.00 ✓
  - {'h1': 'blue', 'h4': 'green'}: penalty=0.00 ✓
  - {'h1': 'blue', 'h4': 'blue'}: penalty=0.00 ✓
```

The agent found that **ALL h1=red configurations fail with penalty=10.00**, which is correct.

### ❌ BUT: LLM Response Generation Produces Bad Suggestions

From actual run log (`communication_log.txt`):

```
Human: I have to change h1 to red. Can you plan around this?

Agent: I can resolve the conflict by changing my node a2 from red to green,
       aiming for a penalty-free solution.
```

**PROBLEM**: `a2` is FIXED to red! The agent cannot change it, yet suggests doing so.

## Root Cause Analysis

### Why h1=red Fails

In the experiment setup:
1. Node `a2` is **FIXED** to color `red` (cannot be changed)
2. Cross-cluster edge exists: `h1 ↔ a2`
3. When human sets `h1=red`, this creates unavoidable conflict:
   - `h1=red` connects to `a2=red` (FIXED)
   - Two adjacent red nodes = conflict
   - Penalty = 10.00

### Why Agent Suggests Changing a2

The agent's internal computation correctly identifies:
- Current penalty with h1=red: 10.00
- Cause: h1 (red) conflicts with a2 (red)
- If a2 could be green: penalty would be 0.00

But the LLM response generation:
1. ✓ Sees the computation results
2. ❌ Suggests "change a2 to green" without checking if a2 is fixed
3. ❌ Doesn't clearly state "I tested h1=red with all h4 values and none worked"

## The Missing Configuration

### What Was Wrong with Initial Test

1. **Message Type**: Test used `message_type="free_text"` instead of `message_type="api"`
   - Fixed: Changed to `"api"` for LLM_API mode
   - Result: `_last_tested_boundary_configs` now populated

2. **Message Format**: Test sent `{"type": "free_text", "data": "..."}`
   - Problem: This polluted `neighbour_assignments` with "type" and "data" keys
   - Fixed: Send just the string message directly
   - Result: Clean boundary tracking

3. **Fixed Nodes**: Test didn't include `fixed_local_nodes`
   - Problem: Agent could freely change a2, so h1=red worked!
   - Fixed: Added `fixed_local_nodes={"a2": "red"}`
   - Result: h1=red now correctly fails with penalty=10.00

### Current Test Configuration (CORRECT)

```python
agent1 = ClusterAgent(
    name="Agent1",
    problem=problem,
    comm_layer=comm_layer,
    local_nodes=agent1_nodes,
    owners=owners,
    algorithm="maxsum",              # Exhaustive search
    message_type="api",               # LLM_API mode
    counterfactual_utils=True,
    fixed_local_nodes={"a2": "red"}   # CRITICAL: a2 is fixed!
)

# Send message as plain string
msg = Message(sender="Human", recipient="Agent1", content=human_msg_2)
```

## Remaining Issue: LLM Prompt Needs Improvement

The problem is NOT in the computation but in the LLM response generation.

### What the Agent Should Say

```
"I tested setting h1=red with all possible h4 values (red, green, blue).
 Unfortunately, ALL of these configurations result in conflicts (penalty=10.00).
 This is because h1 would conflict with my node a2, which is fixed to red.

 For me to achieve a solution with no conflicts, h1 would need to be
 green or blue instead of red."
```

### What the Agent Actually Says

```
"I can resolve the conflict by changing my node a2 from red to green."
```

## Fix Required: Agents Cluster Agent

**File**: `agents/cluster_agent.py`

**Location**: LLM prompt generation (lines ~1400-1500, ~2450-2550 for API mode)

**Changes Needed**:

1. **Add fixed node awareness to prompts**:
   ```
   "CRITICAL: You have fixed nodes that CANNOT be changed:
    - a2 is FIXED to red

    NEVER suggest changing fixed nodes. They are immutable constraints."
   ```

2. **Emphasize what was tested**:
   ```
   "When human asks hypothetical ('h1 may need to be red'), you should:
    1. State what you tested: 'I tested h1=red with all h4 values...'
    2. State the results: 'All resulted in penalty > 0'
    3. Explain WHY: 'This is because h1 would conflict with my fixed node a2=red'
    4. State alternative: 'For a solution, h1 would need to be green or blue'"
   ```

3. **Use tested configs in response**:
   - The `_last_tested_boundary_configs` attribute contains all tested configs
   - LLM prompt should explicitly reference these results
   - Show which configs were tested and their penalties

## Files Created

1. **`test_agent_conversation.py`** - Manual test that reproduces the issue
2. **`TEST_RESULTS.md`** - Initial findings during debugging
3. **`FINAL_TEST_ANALYSIS.md`** - This file (comprehensive analysis)
4. **`test_conversation_log.txt`** - Test output showing all tested configs
5. **`test_full_output.txt`** - Full test run with LLM calls

## Next Steps

1. Update LLM prompts to include fixed node awareness
2. Modify response generation to explicitly state what was tested
3. Ensure agent never suggests changing fixed nodes
4. Re-run actual experiment to verify fix
