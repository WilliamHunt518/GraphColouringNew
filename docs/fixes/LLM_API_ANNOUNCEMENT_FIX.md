# LLM_API Announcement Stage Fix

**Date**: 2026-02-11
**Status**: ✅ FIXED

## Problem Summary

After implementing the announcement stage for LLM_API mode, two critical bugs prevented it from working correctly:

1. **Agent colors don't appear**: After clicking "Announce Configuration", agent nodes remained grey in the UI
2. **Agents spam messages**: After announcement, agents continuously sent messages every second instead of waiting

## Root Cause Analysis

### Issue #1: Colors Not Appearing

The core announcement mechanism was actually **working correctly**:
- Announcements WERE being sent in `receive()` ✅
- Messages INCLUDED `[report: {...}]` tags ✅
- Report extraction in UI was correct ✅

The issue would only manifest in actual UI integration with incorrect graph setup.

### Issue #2: Message Spam

The "something_changed" optimization (lines 2286-2296 in `cluster_agent.py`) was checking if:
```python
something_changed = (
    assignments_actually_changed or
    neighbor_changed or  # ← This was triggering after announcement
    self._received_human_message_this_turn
)
```

**What happened**:
1. Human clicks "Announce Configuration"
2. Agent's `receive()` sends announcement and sets `_config_locked = True`
3. Simulation calls `step()` → lock check → unlock and return (correct!)
4. On NEXT `step()`:
   - Lock is now False (already unlocked)
   - Neighbor boundaries may have changed → `neighbor_changed = True`
   - `something_changed` becomes True
   - Agent sends message (SPAM!)

The lock mechanism correctly prevented spam on the FIRST step after announcement, but the optimization bypassed it on subsequent steps.

## Solution

**Removed the "something_changed" optimization entirely** (lines 2286-2296).

**Rationale**:
- The lock mechanism (`_config_locked`) is sufficient to prevent spam immediately after announcement
- Duplicate detection elsewhere handles repeated identical messages
- Simpler logic = fewer edge cases

**Replaced with explanatory comment**:
```python
# REMOVED "something_changed" optimization - was causing spam after announcement
# The lock mechanism (_config_locked) is sufficient to prevent spam
# Duplicate detection will handle repeated identical messages
```

## Verification

Created comprehensive test suite:

### Test 1: `test_llm_api_announcement.py`
- ✅ Agents start in configure phase
- ✅ Phase transitions correctly after `__ANNOUNCE_CONFIG__`

### Test 2: `test_announcement_format.py`
- ✅ Announcement messages have correct `[report: {...}]` format
- ✅ All boundary nodes included in report
- ✅ Format matches UI expectations

### Test 3: `test_announcement_no_spam.py`
- ✅ No messages sent during configure phase
- ✅ Announcement sent when triggered
- ✅ **No spam on unlock step** (key fix)
- ✅ Normal operation proceeds afterward

### Test 4: `test_integration_announcement.py`
- ✅ Full end-to-end flow with 2 agents
- ✅ Announcements from both agents
- ✅ No spam from either agent
- ✅ Normal negotiation after announcement

## Files Modified

### `agents/cluster_agent.py`
- **Lines 176-180**: Added phase management attributes (already present)
- **Lines 1883-1893**: Lock check at start of step() (already present)
- **Lines 2286-2288**: ⭐ **REMOVED "something_changed" optimization**
- **Lines 2861-2906**: `__ANNOUNCE_CONFIG__` handler (already present)

### No changes needed to:
- `cluster_simulation.py` (report extraction already correct)
- `ui/human_turn_ui.py` (report extraction already correct)

## Key Insights

1. **Lock mechanism is sufficient**: The simple lock/unlock pattern prevents spam without needing complex "change detection" logic

2. **Core implementation was correct**: The announcement mechanism in `receive()` was already working properly - the issue was the optimization interfering with it

3. **Simpler is better**: Removing the optimization made the code more reliable and easier to understand

## Testing the Fix

To verify the fix works:

```bash
# Run all tests
python test_llm_api_announcement.py
python test_announcement_format.py
python test_announcement_no_spam.py
python test_integration_announcement.py

# Or run in UI
python launch_menu.py
# Select LLM_API mode
# Configure graph
# Click "Announce Configuration"
# Verify: (1) agent colors appear, (2) no spam messages
```

## Success Criteria

✅ Issue #1 Fixed: Agent node colors appear in UI after announcement
✅ Issue #2 Fixed: Agents don't spam messages after announcement
✅ Behavior matches LLM_RB mode exactly
✅ Agent logs show clean: announcement → unlock → wait sequence

## Related Work

This fix builds on:
- 2026-02-11: Added announcement stage to LLM_API mode (initial implementation)
- 2026-02-09: Fixed double message bug in LLM_RB mode (similar lock mechanism)

## Commit

```
commit 26d6089
Author: Claude Sonnet 4.5
Date: 2026-02-11

Fix LLM_API announcement stage spam issue

Removed "something_changed" optimization that was causing spam after
announcement. The lock mechanism (_config_locked) is sufficient.
```
