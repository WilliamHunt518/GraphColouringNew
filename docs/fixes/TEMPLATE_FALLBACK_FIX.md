# Template Fallback Fix - Agents Now Send Messages

**Date**: 2026-02-16
**Issue**: Agents returned `None` instead of messages
**Status**: ✅ FIXED

---

## Problem

When running the UI, agents were not sending any messages:
```
[UI] Got reply from Agent1: None...
[UI] Got reply from Agent2: None...
```

**Root Cause**: Phase 3 (outbound translation) was failing due to OpenAI rate limits and returning `should_send_message=False` instead of using a template fallback.

---

## Solution

Added **template fallback** to Phase 3 translation in `tool_calling_cluster_agent.py`:

```python
except Exception as e:
    self.log(f"[TOOL][PHASE3] Translation failed: {e}, using template fallback")

    # TEMPLATE FALLBACK: Generate message from API results
    current_penalty = api_results.get("current_penalty", 0)
    best_response = api_results.get("best_response", {})

    if penalty == 0:
        return acceptance_message
    else:
        return proposal_message_with_suggestion
```

Now when LLM translation fails (rate limits, network issues, etc.), agents **still send messages** using templates based on API results.

---

## Test Results

### With Template Fallback (No LLM):
```
Messages sent: 1
[SUCCESS] Agent sent message using template fallback
Content: That works for me. I'll use a1=blue. The current configuration works well! [report: {"a1": "blue"}]
```

✅ **Agents now send messages even without working LLM**

---

## How It Works

### Normal Flow (LLM Available):
```
Phase 1: LLM translates Human NL → API calls
Phase 2: Execute API calls → Get results
Phase 3: LLM translates API results → Human NL
→ Send rich, natural message
```

### Fallback Flow (LLM Unavailable/Rate Limited):
```
Phase 1: Use default API calls (get_current_penalty, get_best_response_to)
Phase 2: Execute API calls → Get results
Phase 3: Use template based on API results
→ Send functional message
```

---

## What Messages Look Like

### With LLM (Ideal):
```
"Could you change h4 from red to blue? Then I can set a4 to green,
giving us penalty=0."
```

### With Template Fallback (When LLM Fails):
```
Acceptance: "The current configuration works well!"
Proposal: "Could you try changing h1 to blue?"
```

Both include `[report: {...}]` tags for UI color updates.

---

## Testing

### Quick Test (No API Required):
```bash
python tests/test_template_fallback.py
```
Should output:
```
[SUCCESS] Agent sent message using template fallback
```

### UI Test:
```bash
python launch_menu.py
```
1. Select LLM_TOOL mode
2. Start experiment
3. Agents should now send messages (even with rate limits)
4. Messages will be simpler (templates) but functional

---

## Benefits

1. **Robust**: Works even when OpenAI API is down/rate limited
2. **Functional**: Messages contain useful information from API
3. **Graceful Degradation**: LLM when available, templates when not
4. **Research-Grade**: Logs show which mode was used

---

## Comparison

| Situation | Before | After |
|-----------|--------|-------|
| **LLM working** | Rich natural messages ✓ | Rich natural messages ✓ |
| **LLM rate limited** | No messages ❌ (returned None) | Template messages ✓ |
| **LLM error** | No messages ❌ | Template messages ✓ |
| **No API key** | Crash ❌ | Template messages ✓ (if use_llm=False) |

---

## Next Steps

1. **Test in UI**: Run `python launch_menu.py` and verify agents respond
2. **Check logs**: Look for `[TOOL][PHASE3] Translation failed, using template fallback`
3. **When rate limits clear**: Messages will automatically use LLM (better quality)

---

## Technical Details

### Template Fallback Logic

```python
if penalty == 0:
    # Accept current config
    message_type = "acceptance"
    reason = "The current configuration works well!"
    requested_changes = {}

else:
    # Propose a change
    message_type = "proposal"
    reason = f"Could you try changing {node} to {color}?"
    requested_changes = {node: color}
```

### API Results Used

- `current_penalty`: Determines acceptance vs proposal
- `best_response`: Provides my_assignments (what agent will do)
- `current_conflicts`: Shows which edges have issues
- `visible_neighbor_nodes`: Identifies nodes to mention

---

**Status**: ✅ Agents now send messages even with API issues
**Test**: `python tests/test_template_fallback.py` → SUCCESS
**Ready**: Yes - UI should work now
