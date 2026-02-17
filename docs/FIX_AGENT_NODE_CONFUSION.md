# Fix: Agents Asking to Change Their Own Nodes + Useless Messages

**Date**: 2026-02-13
**Issues**:
1. Agents asking human to change agent's own nodes
2. Agents sending useless "still working" messages
3. JSON import bug causing UnboundLocalError

**Status**: ✅ Fixed

## Problems

### Problem 1: Agent Asks to Change Their OWN Nodes

From the logs:
```
[Agent1] Could you change h4 from its current color to blue? Also, could you change a5 from blue to green?
```

**a5 is Agent1's node!** Not the human's node!

- Agent1 controls: a1, a2, a3, a4, a5
- Human controls: h1, h2, h3, h4, h5

Agent1 should NEVER ask human to change a5. They should just update it themselves silently.

### Problem 2: Useless "Still Working" Messages

From the logs:
```
[Agent2] I've assigned colors to some nodes: , b2 is red, , and . I'm currently analyzing conflicts
and trying to find a better way to format my response. I'll keep you updated if I need any specific changes.
```

This is useless! The agent has nothing concrete to say. Messages should only be sent when:
- **Proposal**: Concrete request with plan ("change h4 to blue, then I'll set a4=green")
- **Acceptance**: "That works, I accept"
- **Rejection**: "No, but try X instead"

### Problem 3: JSON Import Bug

```
UnboundLocalError: local variable 'json' referenced before assignment
```

The `import json` was inside an if-block but used outside it.

## Solutions

### Fix 1: Add CRITICAL Section to Prompts

Added prominent warning in both agent prompts (tool_calling and react):

```python
**CRITICAL - READ CAREFULLY**:
- YOU control nodes: {agent_nodes} ← These are YOUR nodes
- NEIGHBOR controls: {neighbor_nodes} ← These are THEIR nodes
- ❌ NEVER ask neighbor to change YOUR nodes!
- ✅ ONLY ask neighbor to change THEIR nodes!
- If you need to change YOUR nodes, just do it silently (update my_assignments)
```

This makes absolutely clear which nodes belong to whom.

### Fix 2: Update Validation Checkpoints

Added validation rules to prevent requesting own nodes:

**Tool Calling Agent** (lines 537-551):
```python
**VALIDATION RULE**: Before submitting your Final Answer, check:
- **CRITICAL**: Are ALL nodes in requested_changes NEIGHBOR nodes? (NOT your own nodes!)

**CHECKPOINT**: Before returning your response:
4. **Verify NONE of the nodes in requested_changes are YOUR nodes** ← CRITICAL!
   - YOUR nodes: {agent_nodes}
   - NEIGHBOR nodes: {neighbor_nodes}
   - Check: Is every node in requested_changes a NEIGHBOR node?
5. If requested_changes contains YOUR OWN nodes: REMOVE them! Only request NEIGHBOR nodes!
6. If you have nothing concrete to say: DON'T send a message!
```

**ReAct Agent** (similar changes in validation checklist).

### Fix 3: Add "When to Send Message" Rule

Added clear guidance on when messages should be sent:

```python
**When to send a message**:
- proposal: You have a concrete request (change h4 to blue) with a plan
- acceptance: Neighbor's suggestion works, you accept it
- rejection: Neighbor's suggestion doesn't work, offer alternative
- DON'T send "still working" or "analyzing" messages - these are useless!
- If you have nothing concrete: Set should_send_message=false
```

This prevents useless "still working" messages.

### Fix 4: JSON Import Bug

Moved `import json` to top of `on_send()` function in `cluster_simulation.py`:

```python
def on_send(neigh: str, text: str) -> str:
    nonlocal human_actions, ui_iteration_counter
    import json  # Import at function level (BEFORE any usage)
    ...
```

## Files Modified

1. **cluster_simulation.py** (line 758)
   - Moved `import json` to top of function
   - Removed duplicate import

2. **agents/tool_calling_cluster_agent.py**
   - Lines 375-387: Added CRITICAL section showing which nodes are whose
   - Lines 503-509: Added "When to send message" rule
   - Lines 537-551: Enhanced validation with node ownership checks

3. **agents/react_cluster_agent.py**
   - Lines 317-329: Added CRITICAL section showing which nodes are whose
   - Lines 227-233: Added "When to send message" rule
   - Lines 265-274: Enhanced validation with node ownership checks

## Before vs After

### Before - Problem 1
```
[Agent1] Could you change a5 from blue to green?
```
❌ Agent asking human to change agent's own node!

### After - Problem 1
```
[Agent1] Could you change h4 from red to blue? Then I can set a5=green, giving us penalty=0.
```
✓ Agent changes their own node (a5) silently, only requests human node (h4)

### Before - Problem 2
```
[Agent2] I'm currently analyzing conflicts and trying to find a better way to format my response.
```
❌ Useless message with no substance!

### After - Problem 2
Agent sets `should_send_message=false` if they have nothing concrete to say.
✓ No useless messages sent

## Key Insights

1. **Explicit node ownership** is critical - LLMs need clear boundaries
2. **Visual separators** (❌ and ✅) help emphasize critical rules
3. **Validation checkpoints** catch mistakes before sending
4. **Message substance requirement** prevents spam

## Testing

Test by:
1. Start LLM_TOOL or LLM_REACT mode
2. Let agents make proposals
3. Verify agents ONLY request changes to human nodes (h1-h5)
4. Verify agents don't send "still working" messages
5. Verify no JSON errors in logs

Expected behavior:
- Agents request changes ONLY to neighbor nodes
- Agents update their own nodes silently via my_assignments
- Agents only send substantive messages (proposals, acceptances, rejections)
- No crashes from JSON import errors
