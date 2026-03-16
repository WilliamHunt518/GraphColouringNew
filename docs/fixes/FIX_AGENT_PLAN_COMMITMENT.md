# Fix: Agent Plan Commitment

**Date**: 2026-02-13
**Issue**: Agents request changes without concrete plans
**Status**: ✅ Fixed

## Problem Description

Agents were asking for color changes without having a **concrete plan** for what they would do if the request was accepted. This led to nonsensical interactions:

1. Agent asks: "Could you change h4 to blue?"
2. Human accepts and changes h4 to blue
3. Agent responds: "I'm analyzing conflicts..." (no plan to use!)

This doesn't make sense - why ask for a change if you don't know what you'll do with it?

## Root Cause

Agents were using the negotiation workflow:
1. Call `simulate_neighbor_change({"h4": "blue"})` → penalty=0 ✓
2. Request h4=blue ✓
3. **MISSING**: Call `get_best_response_to({"h4": "blue"})` to get their OWN assignments ✗

The agents verified that h4=blue would be good, but didn't figure out what THEY should do in response.

## Expected Behavior (RB Mode)

In RB mode, agents make **conditional offers** = package deals:
```
"If you set h4=blue, then I'll set a4=green and a5=red"
```

This is:
- What the human should do: h4=blue
- What the agent will do: a4=green, a5=red
- A complete plan that achieves penalty=0

## Solution

Updated agent prompts to require calling `get_best_response_to()` before making requests.

### New Workflow (PHASE 2)

```
1. Call get_current_penalty() → sees conflicts on (a4, h4)
2. Call simulate_neighbor_change({"h4": "blue"}) → penalty=0 ✓
3. Call get_best_response_to({"h4": "blue"}) → returns {"a1": "green", "a2": "red", "a4": "green"}
4. Make proposal: "Could you change h4 to blue? Then I can set a4=green, giving us penalty=0."
5. Fill structured_content:
   - requested_changes: {"h4": "blue"} (what human should do)
   - my_assignments: {"a1": "green", "a2": "red", "a4": "green"} (what agent will do)
```

### Key Changes

**1. Added Step 3 to negotiation strategy** (both agents):
```
3. **GET YOUR PLAN**: Call get_best_response_to() to find YOUR assignments:
   - Example: get_best_response_to(neighbor_assignments={"h4": "blue"})
   - This returns YOUR optimal assignments if h4 becomes blue
   - **CRITICAL**: You MUST call this to know what YOU'LL do if the request is accepted!
```

**2. Updated example workflow**:
```
**Before**:
1. Call get_current_penalty() → sees conflict on edge (a4, h4)
2. Call simulate_neighbor_change({"h4": "blue"}) → penalty=0
3. Send message: "Could you change h4 from red to blue?"
4. Fill requested_changes: {"h4": "blue"}

**After**:
1. Call get_current_penalty() → sees conflict on edge (a4, h4)
2. Call simulate_neighbor_change({"h4": "blue"}) → penalty=0
3. Call get_best_response_to({"h4": "blue"}) → returns {"a1": "green", "a2": "red", "a4": "green"}
4. Send message: "Could you change h4 to blue? Then I can set a2=red and a4=green, giving penalty=0."
5. Fill requested_changes: {"h4": "blue"} and my_assignments: {"a1": "green", "a2": "red", "a4": "green"}
```

**3. Added requirements for my_assignments field**:
```
**CRITICAL REQUIREMENTS FOR "my_assignments" FIELD**:
1. **REQUIRED**: Must be from get_best_response_to(neighbor_assignments={...})
2. This is YOUR PLAN - what YOU will do if requested_changes is accepted
3. Example: If requesting h4=blue, call get_best_response_to({"h4": "blue"}) to get your plan
4. This makes it a PACKAGE DEAL: "You do X, I'll do Y, we both win"
```

**4. Updated validation checklist**:
```
**CHECKPOINT**: Before returning your response:
1. Verify requested_changes contains EXACT node names
2. Verify requested_changes contains EXACT colors
3. **Verify my_assignments came from get_best_response_to(requested_changes)** ← CRITICAL!
4. If missing get_best_response_to(), go back and call it now!
```

**5. Updated ReAct example** to show full workflow with get_best_response_to().

## Files Modified

### Agent Prompts
1. `agents/tool_calling_cluster_agent.py`
   - Lines 467-478: Added step 3 (get_best_response_to)
   - Lines 403-407: Updated example workflow
   - Lines 501-505: Updated my_assignments requirements
   - Lines 527-531: Updated validation checkpoint

2. `agents/react_cluster_agent.py`
   - Lines 207-217: Added step 4 (get_best_response_to)
   - Lines 175-189: Updated example with get_best_response_to()
   - Lines 225-233: Updated my_assignments requirements
   - Lines 246-251: Updated validation checklist

## Testing

Created `tests/test_agent_plan_commitment.py` to verify:
1. Agent makes specific requests (not vague)
2. Agent mentions their plan ("I'll set a4=green")
3. Agent applies plan when human accepts

## Example: Before vs After

### Before Fix
```
[Agent1] Could you change h4 from red to blue? This adjustment should help resolve some conflicts.
[Human] OK, I changed h4 to blue
[Agent1] I'm currently analyzing conflicts and trying a different approach.
```
❌ Agent asked for change but has no plan!

### After Fix
```
[Agent1] Could you change h4 from red to blue? Then I can set a4=green, giving us penalty=0.
[Human] OK, I changed h4 to blue
[Agent1] Great! I've updated my assignments: a4=green. Our penalty is now 0.
```
✓ Agent has a concrete plan and executes it!

## Why This Matters

This fix aligns LLM agent behavior with RB agent behavior:
- **RB agents**: Always make conditional offers (package deals)
- **LLM agents (before)**: Just asked for changes without plans
- **LLM agents (after)**: Make package deals like RB agents

This is critical for:
1. **Coherent negotiation**: "You do X, I'll do Y" is a complete proposal
2. **Commitment**: Agent can execute their plan when request is accepted
3. **Trust**: Human knows what will happen if they accept
4. **Research validity**: LLM and RB modes are now comparable

## Next Steps

1. Test in UI mode to verify messages display correctly
2. Check that agents actually apply my_assignments from get_best_response_to()
3. Verify this works for multi-neighbor scenarios (Agent1 ↔ Human ↔ Agent2)

## Technical Note

The `get_best_response_to(neighbor_assignments)` function:
- Takes hypothetical neighbor colors
- Runs the local solver (greedy or maxsum)
- Returns optimal agent assignments for those neighbor colors
- Does NOT modify agent state (pure function)

This is exactly what we need for planning: "If they do X, what should I do?"
