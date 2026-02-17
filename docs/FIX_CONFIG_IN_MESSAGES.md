# Fix: Include Configuration in Human Messages

**Date**: 2026-02-13
**Issue**: Agents not receiving human's current configuration
**Status**: ✅ Fixed

## Problem Description

Agents were not aware of the human's current configuration when receiving messages. This led to:

1. Agent asks: "Could you change h4 to blue?"
2. Human changes h4 to blue and says: "Ok" or "What about these settings?"
3. Agent receives: `"Ok"` or `"What about these settings?"` (no config info!)
4. Agent doesn't know h4 is now blue, keeps asking for it!

Looking at the logs:
```
[User] What about these settings?
[Agent2] Could you please specify which settings...
```

The agent has no idea what the current settings are!

## Root Causes

1. **Messages lack context**: `cluster_simulation.py` line 791 sent just the text without config
2. **Color updates not parsed**: Agents received `"{'h1': 'red', 'h4': 'blue'}"` as strings but didn't parse them
3. **No notification of changes**: Agents didn't know when human changed colors

## Solution

### 1. Append Config to All Human Messages

Modified `cluster_simulation.py` (lines 790-795):

```python
# BEFORE:
msg = human_agent.send(neigh, text)

# AFTER:
import json
config_report = dict(human_agent.assignments)
msg_with_config = f"{text} [config: {json.dumps(config_report)}]"
msg = human_agent.send(neigh, msg_with_config)
```

Now every human message includes the current configuration:
```
"Ok [config: {"h1": "red", "h2": "blue", "h3": "green", "h4": "blue", "h5": "green"}]"
```

### 2. Update Agent Prompts to Expect Config Tag

Modified both `tool_calling_cluster_agent.py` and `react_cluster_agent.py`:

Added to conversation history section:
```python
conversation_history += "\n**IMPORTANT**: Human messages include current config in [config: {...}] tag.\n"
conversation_history += "This tells you their CURRENT state. Extract and use this information!\n"
```

This tells agents to look for and parse the `[config: ...]` tag.

### 3. Handle Color Update Dicts Properly

Modified `receive()` method in both agents to parse dict strings:

```python
# Handle color update dicts (e.g., "{'h1': 'red', 'h4': 'blue'}")
if hasattr(msg, 'content') and isinstance(msg.content, str):
    content_str = msg.content.strip()
    if content_str.startswith('{') and content_str.endswith('}'):
        try:
            import ast
            color_update = ast.literal_eval(content_str)
            if isinstance(color_update, dict):
                self.log(f"[TOOL] Detected color update dict: {color_update}")
                self.neighbour_assignments.update(color_update)
                return  # Don't pass to parent, this was just a color notification
        except:
            pass  # Not a valid dict, treat as normal message
```

This properly handles the color change notifications from the UI.

## Files Modified

1. **cluster_simulation.py** (lines 790-795)
   - Append `[config: {...}]` to all human messages

2. **agents/tool_calling_cluster_agent.py**
   - Lines 360-365: Added note about [config: ...] tag in conversation history
   - Lines 1029-1044: Added dict parsing in receive() method

3. **agents/react_cluster_agent.py**
   - Lines 306-311: Added note about [config: ...] tag in conversation history
   - Lines 918-931: Added dict parsing in receive() method

## Before vs After

### Before Fix

```
[User] What about these settings?
[Agent] Could you please specify which settings you are referring to?
```

Agent has no context about current state!

### After Fix

```
[User] What about these settings? [config: {"h1": "red", "h2": "blue", "h3": "green", "h4": "blue", "h5": "green"}]
[Agent] With h4=blue, I can set a4=green and achieve penalty=0. Great!
```

Agent knows the current state from the [config: ...] tag!

## Additional Benefits

1. **Agents track changes**: When human changes colors by clicking, agents get notified via dict messages
2. **No repeated requests**: Agents can see the change was accepted
3. **Better context**: Every message includes full state, reducing confusion
4. **Consistent format**: Same [tag: {...}] format agents use for [report: {...}]

## Testing

Test by:
1. Start LLM_TOOL or LLM_REACT mode
2. Agent makes a request: "Could you change h4 to blue?"
3. Change h4 to blue in UI
4. Send message: "Done" or "Ok"
5. Verify agent sees the change and doesn't repeat the request

Expected behavior:
- Agent acknowledges the change
- Agent updates their own assignments if they had a plan
- Agent doesn't keep asking for h4=blue

## Technical Notes

- **[config: ...]** tag is similar to **[report: ...]** tag used by agents
- Agents should parse this tag in their backend LLM reasoning
- The tag contains the CURRENT state at message send time
- Color change dicts (`{'h1': 'red'}`) are separate notifications from UI clicks
- Both mechanisms ensure agents stay synchronized with human's state
