# LLM_API Agent Test Results

## Test Setup

Running manual test of agent conversation flow to verify hypothetical query handling.

**Graph Structure:**
- Human cluster: h1, h2, h3, h4, h5
- Agent1 cluster: a1, a2, a3, a4, a5
- Cross-cluster edges:
  - h1 ↔ a2
  - h4 ↔ a4
  - h4 ↔ a5

**Test Scenario:**
1. Turn 1: Human sets boundary to {h1: green, h4: red}
2. Turn 2: Human says "h1 may need to be red. Can you plan a colouring around this change or not?"

## Key Findings

### ✓ FIXED: Message Type Configuration
- **Problem**: Test was using wrong message_type
- **Solution**: Changed from "free_text" to "api" for LLM_API mode
- **Result**: `_last_tested_boundary_configs` now populated (was 0, now 9 configs)

### ✓ FIXED: Message Content Format
- **Problem**: Sending `{"type": "free_text", "data": "..."}` polluted neighbour_assignments with "type" and "data" keys
- **Solution**: Send just the string message directly
- **Result**: neighbour_assignments now clean: `{'h1': 'red', 'h4': 'red'}`

### ❌ CRITICAL ISSUE: All h1=red Configurations Show penalty=0.00

**Test Results:**
```
Tested 9 boundary configurations:
  1. {'h1': 'red', 'h4': 'red'}: penalty=0.00
  2. {'h1': 'red', 'h4': 'green'}: penalty=0.00
  3. {'h1': 'red', 'h4': 'blue'}: penalty=0.00
  4. {'h1': 'green', 'h4': 'red'}: penalty=0.00
  ...
```

**Expected Behavior (from user):**
All h1=red configurations should FAIL (penalty > 0), because:
- h1 is red
- h1 connects to a2
- a2 needs to avoid red
- This creates conflicts

**Possible Explanations:**
1. Test graph topology doesn't match actual experiment graph
2. Agent's penalty computation is incorrect
3. User's expectation is based on different graph structure
4. Cross-cluster edges not properly defined in test

## Next Steps

Need to:
1. Verify the test graph matches the actual experimental graph from run_experiment.py
2. Check if cross-cluster edges are correctly creating conflicts
3. Manually compute what the penalty SHOULD be for h1=red, h4=red
4. Compare test graph structure with actual LLM_API run logs
