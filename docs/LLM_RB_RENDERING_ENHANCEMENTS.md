# LLM_RB Rendering Enhancements

**Date:** 2026-02-10
**Purpose:** Enable LLM-based rendering for Agent→Human messages and generate richer conditional offers

## Changes Made

### 1. LLM-Based Agent→Human Rendering

**File:** `comm/llm_rb_comm_layer.py`

**Problem:**
- Agent→Human messages used template-based rendering only (reliable but robotic)
- Human→Agent parsing used LLM (natural and flexible)
- Asymmetry violated experiment requirements for bidirectional LLM translation

**Solution:**
Added LLM-based rendering for Agent→Human messages with template fallback:

```python
class LLMRBCommLayer(LLMCommLayer):
    def __init__(self, *args, use_llm_rendering: bool = True, **kwargs):
        """
        Parameters
        ----------
        use_llm_rendering : bool
            If True (default), use LLM to render Agent→Human messages.
            Falls back to templates if LLM fails.
        """
```

**Key features:**
- **LLM-first approach:** Tries LLM rendering before templates
- **Graceful fallback:** Uses templates if LLM times out or fails
- **Natural variation:** LLM produces varied, conversational language
- **Configurable:** Can disable via `use_llm_rendering=False`

**Example outputs:**

*Template (old):*
```
If you could set h1=red, h2=blue, then I could set b1=green, b2=yellow. Sound good?
```

*LLM-generated (new):*
```
If you set h1 to red, h2 to blue, and h5 to green, then I can assign
b1 to yellow, b2 to red and b3 to blue. How does that sound?
```

Notice the variation and natural phrasing!

### 2. Disabled Priority 0 Unconditional Announcements

**File:** `agents/rule_based_cluster_agent.py`

**Problem:**
- Priority 0 sent unconditional boundary updates ("I'm planning a2=blue")
- These announcements provided little negotiation value
- Conflicted with pure RB mode principle: "conditionals first, always"

**Solution:**
Priority 0 now detects boundary changes but **does NOT send unconditional announcements**. Instead:
1. Detects when boundary nodes have changed
2. Sets `rb_force_conditional` flag for that recipient
3. Falls through to Priority 2/4 to generate conditional offers

**Before:**
```
[Agent1] I'm planning to set a2 to blue. Does that create any conflicts?
```

**After:**
```
[Agent1] If you could set h1 to red and h2 to green, then I could
make a2 blue and a3 yellow work. What do you think?
```

### 3. More Aggressive Conditional Offer Generation

**File:** `agents/rule_based_cluster_agent.py` (Priority 2)

**Problem:**
- Priority 2 only fired when `conflicts=True` (direct color clashes detected)
- Missed cases where penalty > 0 but no direct clashes detected
- Result: Agents sent simple announcements instead of rich conditionals

**Solution:**
Relaxed Priority 2 condition from:
```python
if conflicts and current_penalty > 0.0:
```

To:
```python
if current_penalty > 0.0:
```

**Effect:**
- Priority 2 fires whenever penalty > 0 (not just direct conflicts)
- Generates conditional offers more frequently
- Produces richer negotiations with "if you do X, I'll do Y" structure

## Testing

**Test file:** `test_llm_rb_rendering.py`

Verifies:
1. ✓ LLM rendering enabled by default
2. ✓ Can disable LLM rendering via parameter
3. ✓ Conditional offers render with "if...then" structure
4. ✓ Unconditional announcements (if any) don't use conditional structure
5. ✓ Reject with impossible_combinations renders correctly
6. ✓ LLM produces natural, varied language (not templates)
7. ✓ LLM shows variation across multiple calls

## Backwards Compatibility

- **Pure RB mode:** Unchanged (uses UI buttons, not LLM)
- **LLM_U/LLM_C/LLM_F modes:** Unchanged (different protocols)
- **LLM_RB with API failure:** Falls back to templates gracefully
- **Manual mode:** Template rendering still available via `manual=True`

## Experiment Validity

These changes ensure LLM_RB mode:
1. **Uses LLM bidirectionally** (Human→Agent AND Agent→Human)
2. **Generates rich conditional offers** (not simple announcements)
3. **Matches RB mode behavior** (conditionals first, always)
4. **Maintains reliability** (template fallback prevents failures)

## Configuration

To disable LLM rendering (use templates only):

```python
comm_layer = LLMRBCommLayer(use_llm_rendering=False)
```

To enable manual mode (bypasses LLM entirely):

```python
comm_layer = LLMRBCommLayer(manual=True)
```

Default (recommended for experiments):

```python
comm_layer = LLMRBCommLayer()  # use_llm_rendering=True by default
```

## Logging

LLM rendering calls are logged to `results/*/llm_trace.jsonl`:

```json
{
  "event": "render",
  "move": "ConditionalOffer",
  "prompt": "Convert this structured dialogue move...",
  "response": "If you set h1 to red, then I can make b1 green work...",
  "timestamp": "2026-02-10T..."
}
```

## Known Issues

None currently identified.

## Future Enhancements

Potential improvements:
1. **Adaptive rendering:** Switch between LLM and templates based on success rate
2. **Context-aware prompts:** Include prior messages for coherence
3. **Persona control:** Vary agent communication style (formal/casual)
4. **Multi-language support:** Render in languages other than English
