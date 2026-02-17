# Fix: Announcement Then First Message Flow

**Date**: 2026-02-11
**Issue**: First message generated before receiving human's config
**Status**: ✅ Fixed

---

## Problem

The agent was generating its first substantive message **immediately** after sending its announcement, before receiving the human's configuration. This meant:

1. Agent announces: "Here's my initial configuration: a2=blue"
2. Agent immediately generates message: "I propose..." ← **TOO EARLY**
3. Human's config arrives later

**User feedback**: "The key here is it SHOULD do the initial announcement, but directly upon the nodes, not in the chat box. After that, it should be looking at the configs (Mine sent to them as well remember) and prompt the LLM engine to go ahead and make an offer"

---

## Desired Flow

1. **Announcement Phase** (updates node colors in graph):
   - Human clicks "Announce Configuration"
   - Human agent sends human's boundary config to agents
   - Agent sends announcement → updates agent node colors in UI

2. **Agent Receives Human's Config**:
   - Agent's `neighbour_assignments` gets updated with human's boundary nodes

3. **First Substantive Message** (appears in chat):
   - Agent analyzes full situation (agent config + human config)
   - Generates meaningful offer/request/acceptance
   - Appears in chat transcript

---

## Solution

Changed from **immediate generation** to **deferred generation**:

### Before (Immediate)
```python
def _handle_announce_config(self, recipient: str) -> None:
    # Send announcement
    self.send(recipient, announcement)

    # Generate first message IMMEDIATELY
    self._generate_first_message_after_announcement(recipient)  # ← Too early!
```

**Problem**: Human's config hasn't arrived yet, so agent analyzes incomplete information.

### After (Deferred)
```python
def _handle_announce_config(self, recipient: str) -> None:
    # Send announcement
    self.send(recipient, announcement)

    # Mark that we should generate first message on NEXT step()
    if self.backend_llm is not None:
        self._should_generate_first_message = True
```

Then in `step()`:
```python
def step(self) -> None:
    # ... phase checks ...

    # Check if we should generate first message after announcement
    if self._should_generate_first_message:
        self._should_generate_first_message = False
        # NOW we have received human's config, can analyze full situation
        for neigh in self.neighbour_assignments.keys():
            self._generate_first_message_after_announcement(neigh)
        return

    # ... normal step logic ...
```

---

## Implementation Details

### 1. Added Flag to Track State

**In `__init__()`:**
```python
# Flag to generate first message after announcement
self._should_generate_first_message = False
```

### 2. Set Flag in Announcement Handler

**In `_handle_announce_config()`:**
```python
# Mark that we should generate first message on next step()
# This allows us to receive human's config first, then analyze full situation
if self.backend_llm is not None:
    self._should_generate_first_message = True
```

### 3. Check Flag in Step Method

**In `step()`:**
```python
# Check if we should generate first message after announcement
if self._should_generate_first_message:
    self._should_generate_first_message = False
    # Generate first substantive message for each neighbor
    for neigh in self.neighbour_assignments.keys():
        self._generate_first_message_after_announcement(neigh)
    return
```

---

## Timeline of Events (After Fix)

### Turn 0: Initial State
```
Human: h1=?, h2=? (unassigned)
Agent: a2=?, a4=? (unassigned)
```

### Turn 1: Human Clicks "Announce Configuration"

**Human agent announces:**
```
Message to Agent1: __ANNOUNCE_CONFIG__
Human's boundary: h1=red, h2=blue (sent to agent)
```

**Agent1 receives __ANNOUNCE_CONFIG__:**
```python
# In receive():
agent.neighbour_assignments = {"h1": "red", "h2": "blue"}  # Human's config

# In _handle_announce_config():
agent.send("Human", announcement)  # Sends: "Here's my initial configuration: a2=blue, a4=red"
agent._should_generate_first_message = True  # Flag set
```

**UI State:**
```
Human nodes: h1=red, h2=blue (visible in graph)
Agent nodes: a2=blue, a4=red (visible in graph)
Chat: [announcement message appears]
```

### Turn 2: Agent Step (First Message Generation)

**Agent's step() is called:**
```python
if self._should_generate_first_message:  # True!
    self._should_generate_first_message = False
    self._generate_first_message_after_announcement("Human")
    return
```

**Agent analyzes full situation:**
```python
# Agent now has BOTH configs:
agent.assignments = {"a2": "blue", "a4": "red"}  # Own config
agent.neighbour_assignments = {"h1": "red", "h2": "blue"}  # Human's config

# Check for conflicts
penalty, conflicts = agent.api.get_current_penalty()
# If conflict between a2=blue and h1=blue, penalty > 0

# Generate substantive message
backend_output = agent._generate_first_message_after_announcement("Human")
# Returns: "I notice a2 conflicts with h1. Can you change h1 to green?"
```

**UI State:**
```
Chat:
  [Agent1] Here's my initial configuration: a2=blue, a4=red
  [Agent1] I notice there's a conflict between my a2 (blue) and your h1 (blue).
           Would you be able to change h1 to green? That would resolve the issue.
```

---

## Key Benefits

### 1. Complete Information
Agent has **both configs** before generating message:
- Agent's own assignments
- Human's boundary assignments (from `neighbour_assignments`)

### 2. Meaningful Analysis
Backend LLM can properly analyze:
- Conflicts between agent and human nodes
- Alternative solutions that work for both parties
- Trade-offs and suggestions

### 3. Correct Timing
- Announcement updates colors first (graph view)
- First message analyzes situation (chat transcript)
- Matches user mental model of workflow

---

## Files Modified

### tool_calling_cluster_agent.py

**Lines Modified**:
- Line 101: Added `self._should_generate_first_message = False` in `__init__`
- Line 709: Changed to set flag instead of immediate call
- Lines 400-405: Added flag check in `step()` method

### react_cluster_agent.py

**Lines Modified**:
- Line 108: Added `self._should_generate_first_message = False` in `__init__`
- Line 582: Changed to set flag instead of immediate call
- Lines 240-245: Added flag check in `step()` method

---

## Testing

All tests pass ✅:

```bash
$ python test_announcement_nl_format.py
[OK] ALL ANNOUNCEMENT FORMAT TESTS PASSED!

$ python test_integration_new_modes.py
[OK] ALL INTEGRATION TESTS PASSED!
```

---

## Behavior Comparison

### Without API Key (No Backend LLM)
```
[Agent1] Here's my initial configuration: a2=blue, a4=red
[... waits for human input ...]
```
- Only announcement sent
- No backend LLM to generate first message

### With API Key (Backend LLM Available) ✅
```
[Agent1] Here's my initial configuration: a2=blue, a4=red
[Agent1] I see we both have blue on our boundary nodes. I could change
         my a2 to green to resolve this. Does that work for you?
```
- Announcement sent (colors update)
- Agent receives human's config
- First substantive message generated based on **full situation**

---

## Troubleshooting

### Issue: Agent still sends message too early

**Check**:
1. Is `_should_generate_first_message` flag set correctly?
2. Is `step()` being called after announcement?
3. Has human's config been received (`neighbour_assignments` updated)?

### Issue: No first message sent at all

**Possible causes**:
1. No backend LLM (no API key)
2. `step()` not being called after announcement
3. Flag not being set in `_handle_announce_config()`

**Debug**:
```python
# Add logging to check flag
self.log(f"[DEBUG] _should_generate_first_message = {self._should_generate_first_message}")
```

---

## Summary

**Problem**: Agent generated first message before receiving human's config

**Root Cause**: Immediate generation in `_handle_announce_config()`

**Solution**:
1. Set flag in announcement handler
2. Generate message on next `step()` call
3. By then, human's config has been received

**Result**: ✅ Agent analyzes **complete** situation (own + human config) before generating first message

---

*Last updated: 2026-02-11*
*Fix verified with all tests passing*
