# Announcement Flow Fix

## Problem

After making announcements silent, agents were announcing their config but then not sending any messages at all:

```
1. Human clicks "Announce Config"
2. Agents announce (silent - colors appear in UI)
3. Agents wait for human to announce
4. But human never announces!  ← PROBLEM
5. No chat messages appear
```

## Root Cause

The "Announce Config" button was only triggering agents to announce via `__ANNOUNCE_CONFIG__` token, but was NOT sending the human's configuration to the agents. The agents were waiting for the human's message that never arrived.

## Solution

Modified `ui/human_turn_ui.py` `_announce_configuration()` method to send TWO sets of messages:

1. **First**: Send `__ANNOUNCE_CONFIG__` to each agent
   - Agents respond with silent announcement
   - Colors update in UI
   - No chat message

2. **Second**: Send human's configuration to each agent
   - Format: `"Here's my configuration: h1=red, h2=blue [report: {...}]"`
   - Agents receive this as a regular message
   - Triggers `_received_human_message_this_turn = True`
   - Next step() generates substantive response

## Changes Made

**File**: `ui/human_turn_ui.py` (lines 4494-4518)
- After agents announce, wait 0.5s for announcements to complete
- Build human's announcement message with all assignments
- Send to each agent in separate thread

**Files**: `agents/tool_calling_cluster_agent.py` & `agents/react_cluster_agent.py`
- Removed `_should_generate_first_message` flag setting
- Agents wait for actual human messages (not flags)

## Flow Diagram

### Before Fix
```
User clicks "Announce Config"
  └─> UI sends __ANNOUNCE_CONFIG__
      └─> Agents announce (silent)
          └─> Agents wait... (no messages received)
              └─> No response ✗
```

### After Fix
```
User clicks "Announce Config"
  └─> UI sends __ANNOUNCE_CONFIG__
      └─> Agents announce (silent, colors visible)
          └─> UI sends human's config
              └─> Agents receive human message
                  └─> Agents generate substantive response ✓
```

## Expected Behavior

1. **Agent colors visible immediately**: Agents compute and announce colors on startup (silent)
2. **No announcement in chat**: Silent messages update UI but don't clutter chat
3. **First chat message is substantive**: After seeing human's config, agents make proposals like "I propose a1=blue to resolve conflicts"

## Testing

Run the full UI flow:
```bash
python launch_menu.py
```

Select LLM_TOOL or LLM_REACT mode, then:
1. Verify agent colors appear in graph (not in chat)
2. Click "Announce Config"
3. Verify first chat message is substantive offer (not "here's my config")
