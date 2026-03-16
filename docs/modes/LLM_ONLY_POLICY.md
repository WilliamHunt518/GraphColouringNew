# LLM-Only Policy for LLM_TOOL and LLM_REACT Modes

**Date**: 2026-02-17
**Status**: ✅ Enforced

## Policy

**LLM_TOOL and LLM_REACT modes are LLM-ONLY. NO template fallbacks are allowed.**

These modes exist specifically to study LLM-based coordination. Using template fallbacks would:
1. Contaminate experimental data
2. Make it impossible to distinguish LLM vs non-LLM behavior
3. Defeat the purpose of having separate modes

## Enforcement

### 1. Speech LLM Layer (`comm/speech_llm_layer.py`)

**Lines 365-371**: Hard failure if speech LLM fails
```python
except Exception as e:
    print(f"FATAL ERROR: Speech LLM failed")
    print(f"LLM_TOOL mode requires working OpenAI API - no fallbacks allowed")
    raise SystemExit(f"Speech LLM FAILED: {e}") from e
```

**Lines 359-372**: Output quality validation (NEW)
```python
# CRITICAL: Validate LLM output quality (no template fallback allowed!)
if ", ," in nl_message or ", and ." in nl_message:
    error_msg = f"Speech LLM generated malformed output"
    raise ValueError(error_msg)
```

Catches malformed LLM output like "I've assigned , b2 to red, , and ." and **fails hard** instead of falling back to templates.

### 2. ReAct Agent (`agents/react_cluster_agent.py`)

**Line 602-604**: Exception handler calls parent's step()
```python
except Exception as e:
    self.log(f"[REACT] Falling back to algorithmic mode due to error")
    super().step()
```

**NOTE**: This fallback should be REMOVED for pure LLM mode. It's a safety net that shouldn't trigger in normal operation.

### 3. Backend LLM

**No fallback** - if backend LLM fails, the agent cannot generate decisions. The system fails hard.

## Verification

### What IS allowed:
- ✅ LLM generates all message content (speech layer)
- ✅ LLM generates all reasoning (backend layer)
- ✅ LLM uses API functions for graph coloring operations
- ✅ Hard failure if LLM is unavailable or generates invalid output

### What is NOT allowed:
- ❌ Template-based message generation
- ❌ Rule-based message fallbacks
- ❌ Heuristic message formatting
- ❌ Silent degradation to non-LLM behavior

## The Malformed Message Issue

**What happened**: Agent2's first message was:
```
"That works for me. Perfect! With your current settings, I can achieve penalty=0.
I've assigned , b2 to red, , and ."
```

**Analysis**:
1. Backend LLM generated correct structured content ✓
2. Speech LLM tried to format it as natural language
3. Speech LLM generated malformed text with empty placeholders

**This is NOT a template fallback** - it's the LLM making a formatting error.

**Fix**: Added output quality validation (lines 359-372) to catch and fail hard on malformed output. Forces LLM to generate correct output or fail visibly.

## How to Check

### 1. Check logs for "FATAL ERROR: Speech LLM failed"
If you see this, the system is correctly failing hard instead of falling back.

### 2. Check logs for template markers
Templates say:
- "I'll use {assignment_str}" (acceptance)
- "I propose {assignment_str}" (proposal)

LLM messages vary naturally:
- "That works for me", "Perfect!", "Great!", etc.
- Different phrasings each time

### 3. Check cluster_simulation.py initialization
```python
# Line 407
comm_layer = SpeechLLMLayer(model="gpt-4-turbo", use_llm=not manual_mode)
```

In GUI mode: `manual_mode=False` → `use_llm=True` ✓

## Removing the Exception Fallback

The fallback at line 602-604 in `react_cluster_agent.py` should be removed for pure LLM operation:

```python
except Exception as e:
    self.log(f"[REACT] ERROR in ReAct reasoning: {e}")
    self.log(f"[REACT] ERROR traceback:\n{traceback.format_exc()}")
    print(f"[{self.name}][REACT] FATAL ERROR - no fallback allowed in LLM mode")
    raise SystemExit(f"ReAct agent FAILED: {e}") from e
```

This ensures the system fails visibly if the backend LLM encounters errors, rather than silently degrading to algorithmic mode.

## Summary

✅ **LLM_TOOL and LLM_REACT modes are LLM-only**
✅ **Speech LLM layer fails hard if LLM unavailable**
✅ **Output quality validation catches malformed LLM output**
✅ **No template fallbacks allowed**
❌ **Exception handler fallback should be removed** (line 602-604 in react_cluster_agent.py)

The malformed message was the LLM making an error, not a template fallback. The new validation will catch these errors and fail hard, maintaining the LLM-only policy.
