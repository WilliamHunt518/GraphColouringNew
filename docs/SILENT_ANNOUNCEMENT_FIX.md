# Silent Announcement Fix

## Problem

In LLM_TOOL and LLM_REACT modes, agents were sending two types of messages:
1. Initial configuration announcement: "Here's my initial configuration: a1=red, a2=blue"
2. Substantive offer after seeing human's announcement

Both appeared in the chat panel, but the announcement was redundant - the colors were already visible in the UI graph.

## Solution

### Changes Made

**1. Silent Announcement Marker** (`comm/speech_llm_layer.py` lines 114-120)
   - Announcements now use `__SILENT__` marker instead of text
   - Format: `__SILENT__ [report: {...}]`
   - Still includes report tag for UI color updates
   - No human-readable text (won't clutter chat)

**2. UI Filter** (`ui/human_turn_ui.py` lines 3698-3706)
   - Check for `__SILENT__` marker before displaying
   - Skip appending silent messages to transcript
   - Still extract report tag and update graph colors

**3. Agent Wait Logic** (`agents/tool_calling_cluster_agent.py` & `agents/react_cluster_agent.py`)
   - After announcement, agent waits for human to announce
   - Only generates substantive message after receiving human's announcement
   - First chat message is now a proper offer/proposal

## Flow

### Before
```
1. Agent announces: "Here's my initial configuration: a1=red, a2=blue"
   → Shows in chat ✗
2. Agent generates another message immediately
   → Shows in chat ✗
3. Human announces
4. No substantive response
```

### After
```
1. Agent announces: "__SILENT__ [report: {...}]"
   → Updates UI colors ✓
   → Does NOT show in chat ✓
2. Agent waits (no message)
3. Human announces
4. Agent generates substantive offer: "I propose a1=blue to resolve conflicts"
   → Shows in chat ✓
   → First visible message is meaningful ✓
```

## Benefits

1. **Cleaner chat**: No redundant "here's my config" messages
2. **Better UX**: First message is substantive and actionable
3. **Correct flow**: Agent responds to human's announcement, not just announces itself
4. **Faster**: Announcement is template-based (no LLM), only substantive response uses LLM

## Testing

Run `tests/test_silent_announcement.py` to verify:
- Announcement has `__SILENT__` marker
- Announcement has `[report:]` tag
- UI skips displaying silent messages
- First visible message is substantive

## Implementation Notes

- Both LLM_TOOL and LLM_REACT use the same SpeechLLMLayer, so fix applies to both
- The `__SILENT__` marker is a simple string prefix that's easy to detect
- Existing RB and LLM_RB modes are unaffected (they don't use this announcement format)
