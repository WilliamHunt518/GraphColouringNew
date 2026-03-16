# Fix: First Message After Announcement (LLM_TOOL & LLM_REACT)

**Date**: 2026-02-11
**Issue**: Agents only sent config announcement, no substantive first message
**Status**: ✅ Fixed

---

## Problem

After clicking "Announce Configuration", the new LLM_TOOL and LLM_REACT agents would:
1. Send announcement: "Here's my initial configuration: a2=blue, a4=red"
2. Then stay silent (no substantive message)

Other modes (RB, LLM_RB, LLM_API) behave differently:
1. Send announcement
2. **Immediately send substantive message** (suggestion, request, or acceptance based on conflicts)

**User feedback**: "That works for initial config, however the first message is an announcement of the config instead of any kind of suggestion... Prompting it after an exchange of configs so it can see any issues and request changes if possible (or alter its own colouring around me)."

---

## Root Cause

The `_handle_announce_config()` method in both agents had two issues:

### Issue 1: Config Lock Prevented Follow-up Messages

```python
def _handle_announce_config(self, recipient: str) -> None:
    self._config_announced = True
    self._config_locked = True  # ← This prevented any further messages
    self._phase = "bargain"

    # Send announcement
    self.send(recipient, announcement)
    # END - no follow-up logic
```

The `step()` method checked this lock:
```python
def step(self) -> None:
    if self._config_locked:
        return  # Skip step entirely
```

This prevented the agent from running `step()` after announcement, so no substantive message was generated.

### Issue 2: No Logic to Generate First Message

Even after removing the lock, there was no logic to analyze the situation and generate a substantive first message based on:
- Current conflicts
- Penalty value
- Neighbor assignments

---

## Solution

### Change 1: Remove Config Lock

**Before**:
```python
self._config_locked = True  # Lock to prevent spam
```

**After**:
```python
# Removed - lock was preventing substantive messages
```

Also removed lock check from `step()` method:
```python
# REMOVED:
# if self._config_locked:
#     return
```

### Change 2: Add First Message Generation Logic

Added conditional call to generate substantive message:

```python
def _handle_announce_config(self, recipient: str) -> None:
    # ... send announcement ...

    # Generate first substantive message if there are conflicts
    # This mimics the behavior of other modes (RB, LLM_RB, LLM_API)
    if self.backend_llm is not None:
        penalty, _ = self.api.get_current_penalty()
        if penalty > 0:
            self._generate_first_message_after_announcement(recipient)
```

### Change 3: Implement Generation Method

Added new method to both agents:

**For ToolCallingClusterAgent** (`tool_calling_cluster_agent.py`):
```python
def _generate_first_message_after_announcement(self, recipient: str) -> None:
    """Generate first substantive message after config announcement.

    This checks for conflicts and uses backend LLM to generate
    a meaningful first message (suggestion, request, or acceptance).
    """
    if self.backend_llm is None:
        return

    # Check current state
    penalty, conflicts = self.api.get_current_penalty()

    # Build prompt
    prompt = f"""You have just announced your initial configuration.

    Current state:
    - Your penalty: {penalty}
    - Conflicts: {len(conflicts)} conflicts detected

    Based on the current state:
    1. If there are conflicts: Suggest changes
    2. If penalty > 0: Analyze and suggest improvements
    3. If penalty == 0: Express satisfaction

    Generate an appropriate first message."""

    # Call backend LLM with tool calling
    # ... (full implementation in code)
```

**For ReActClusterAgent** (`react_cluster_agent.py`):
Similar implementation but uses ReAct reasoning pattern instead of tool calling.

---

## Behavior After Fix

### Without API Key (No Backend LLM)
```
[Agent1] Here's my initial configuration: a2=blue, a4=red
[... waits for human input ...]
```
- Only sends announcement
- No substantive message (no LLM available)

### With API Key, No Conflicts (penalty == 0)
```
[Agent1] Here's my initial configuration: a2=blue, a4=red
[... waits for human input ...]
```
- Only sends announcement
- No conflicts, so no need for substantive message

### With API Key, With Conflicts (penalty > 0) ✅
```
[Agent1] Here's my initial configuration: a2=blue, a4=red
[Agent1] I notice there's a conflict between my a2 (blue) and your h1 (blue).
         Would you be able to change h1 to red? That would resolve the issue.
```
- Sends announcement
- **Immediately sends substantive message** analyzing conflicts and making suggestions
- Matches behavior of other modes (RB, LLM_RB, LLM_API)

---

## Files Modified

### tool_calling_cluster_agent.py

**Lines Modified**:
- Line 690: Removed `self._config_locked = True`
- Lines 707-710: Added conditional call to generate first message
- Lines 712-820: Added `_generate_first_message_after_announcement()` method
- Lines 388-390: Removed lock check in `step()` method

**Total Changes**: ~120 new lines, 4 removed lines

### react_cluster_agent.py

**Lines Modified**:
- Line 557: Removed `self._config_locked = True`
- Lines 580-583: Added conditional call to generate first message
- Lines 585-675: Added `_generate_first_message_after_announcement()` method
- Lines 232-234: Removed lock check in `step()` method

**Total Changes**: ~100 new lines, 4 removed lines

---

## Testing

### Test 1: Existing Tests Still Pass ✅

```bash
$ python test_announcement_nl_format.py
[OK] ALL ANNOUNCEMENT FORMAT TESTS PASSED!

$ python test_integration_new_modes.py
[OK] ALL INTEGRATION TESTS PASSED!
```

### Test 2: First Message Generation ✅

Created new test: `test_first_message_after_announcement.py`

```bash
$ python test_first_message_after_announcement.py
[OK] FIRST MESSAGE TESTS PASSED!
```

Verifies:
- Announcement sent correctly
- Substantive message generated when conflicts exist
- No extra messages when no conflicts

---

## Comparison with Other Modes

### RB Mode (Existing)
1. Announcement: "I'm planning a2=blue, a4=red"
2. **First message**: "If you set h1 to red, I can do a2=blue. Does that work?"

### LLM_RB Mode (Existing)
1. Announcement: "Here are my initial assignments: a2=blue, a4=red"
2. **First message**: "I notice there's a conflict with h1. Could you change it to red?"

### LLM_API Mode (Existing)
1. Announcement: "My configuration: a2=blue, a4=red"
2. **First message**: "Would you be able to adjust h1 to avoid conflicts?"

### LLM_TOOL Mode (After Fix) ✅
1. Announcement: "Here's my initial configuration: a2=blue, a4=red"
2. **First message**: Backend LLM analyzes conflicts and generates suggestion via tool calling

### LLM_REACT Mode (After Fix) ✅
1. Announcement: "Here's my initial configuration: a2=blue, a4=red"
2. **First message**: Backend LLM uses ReAct reasoning to analyze and suggest changes

---

## Key Design Decisions

### Decision 1: Only Generate Message if Penalty > 0

**Rationale**: If there are no conflicts (penalty == 0), the agent doesn't need to send a substantive message. This matches the behavior of other modes and avoids unnecessary messages.

**Implementation**:
```python
if self.backend_llm is not None:
    penalty, _ = self.api.get_current_penalty()
    if penalty > 0:
        self._generate_first_message_after_announcement(recipient)
```

### Decision 2: Require Backend LLM

**Rationale**: Without an API key, there's no backend LLM to generate intelligent first messages. In this case, the agent just sends the announcement and waits for human input (same as before).

**Result**: Graceful degradation when no API key available.

### Decision 3: Use Same Backend LLM Reasoning

**Rationale**: The first message should use the same reasoning process as subsequent messages. For LLM_TOOL, this means tool calling. For LLM_REACT, this means ReAct pattern.

**Result**: Consistent reasoning traces throughout the experiment.

---

## Example Interaction (With API Key)

```
[UI] User clicks "Announce Configuration"

[Agent1] Here's my initial configuration: a2=blue, a4=red

[Agent1] I've analyzed our configurations and notice that my a2 (blue)
         conflicts with your h1 (blue). I could change a2 to green, or
         alternatively, if you could set h1 to red, that would also work.
         What would you prefer?

[Human] I can change h1 to red

[Agent1] Perfect! That resolves the conflict. My configuration remains
         a2=blue, a4=red. We now have penalty=0.

[Human] ✓ I'm satisfied (checked)
[Agent1] satisfied=True

[System] Consensus reached. Experiment complete.
```

---

## Logging

Backend LLM calls for first message generation are logged:

**LLM_TOOL Mode**:
```json
{
  "timestamp": "2026-02-11T15:30:00",
  "agent": "Agent1",
  "event": "first_message_generation",
  "penalty": 2.0,
  "conflicts": [["a2", "h1"]],
  "tool_calls": ["get_current_penalty", "enumerate_alternatives"],
  "decision": "suggest_change_to_human"
}
```

**LLM_REACT Mode**:
```json
{
  "timestamp": "2026-02-11T15:30:00",
  "agent": "Agent1",
  "event": "first_message_generation",
  "penalty": 2.0,
  "react_trace": {
    "iteration": 0,
    "thought": "I need to check conflicts...",
    "action": "get_current_penalty()",
    "observation": {"penalty": 2.0, "conflicts": [["a2", "h1"]]}
  }
}
```

---

## Troubleshooting

### Issue: Still no first message after announcement

**Possible causes**:
1. No API key → Backend LLM not available
2. No conflicts → penalty == 0, so no message needed
3. Backend LLM error → Check logs for exceptions

**Debug**:
```python
# Check if backend LLM exists
print(f"Backend LLM: {agent.backend_llm}")

# Check penalty
penalty, conflicts = agent.api.get_current_penalty()
print(f"Penalty: {penalty}, Conflicts: {conflicts}")
```

### Issue: Too many messages sent

This shouldn't happen anymore since we:
1. Removed the lock (which was preventing messages)
2. Only generate first message if penalty > 0
3. Use proper duplicate detection elsewhere

If it does happen, check for logic errors in the new method.

---

## Summary

**Problem**: Agents sent announcement but no substantive first message

**Root Cause**:
1. Config lock prevented follow-up messages
2. No logic to generate first message based on conflicts

**Solution**:
1. Removed config lock
2. Added conditional first message generation (only if penalty > 0 and backend LLM available)
3. Implemented `_generate_first_message_after_announcement()` for both agents

**Result**: ✅ Agents now behave like other modes - announce config, then immediately send substantive message if there are conflicts

**Status**: Complete and tested

---

*Last updated: 2026-02-11*
*Fix verified with all existing tests passing*
