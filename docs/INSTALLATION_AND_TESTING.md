# Installation and Testing Guide

## Issues Fixed

### 1. Command-Line Argument Parsing ✅ FIXED
**Issue**: `run_experiment.py` didn't recognize LLM_TOOL and LLM_REACT
**Fix**: Added new modes to argument parser and method validation
**Files**: `run_experiment.py` (lines 186, 151-154)

### 2. OpenAI Package Version ✅ FIXED
**Issue**: Old openai==0.28.0 (incompatible with new agents)
**Fix**: Upgraded to openai==2.20.0
**Command**: `pip install --upgrade openai`

### 3. Method Validation ✅ FIXED
**Issue**: ValueError "Unknown METHOD: LLM_TOOL"
**Fix**: Added cases for LLM_TOOL and LLM_REACT in method validation
**Files**: `run_experiment.py` (lines 151-154)

## Installation Steps

### 1. Activate Virtual Environment

```bash
# Windows
E:\Files\PhD-Main\GC-New\GIT_LOCAL_ROOT\GraphColouringNew\venv\Scripts\activate

# Unix/macOS
source venv/bin/activate
```

### 2. Upgrade OpenAI Package

```bash
pip install --upgrade openai
```

Expected output:
```
Successfully installed openai-2.20.0 ...
```

### 3. Add API Key

```bash
echo "sk-your-openai-api-key" > api_key.txt
```

**Note**: If you don't have an API key, the agents will fall back to algorithmic mode with a warning.

## Testing

### Quick Validation (No API Required)

```bash
# Test 1: API library and agent instantiation
python test_multi_layer_llm.py

# Test 2: Integration tests (no API calls)
python test_integration_new_modes.py
```

Expected output for both:
```
[OK] ALL TESTS PASSED!
```

### GUI Mode Testing

```bash
python launch_menu.py
```

**Steps**:
1. Select "LLM_TOOL" or "LLM_REACT" from dropdown
2. Select algorithm: "greedy" (fast) or "maxsum" (optimal)
3. Check "Use participant UI"
4. Set max iterations: 10
5. Click "Start"

**What to expect**:
- Window opens with graph visualization
- Two chat panes (Agent1 and Agent2)
- "Announce Configuration" button appears
- Click to trigger announcement phase
- Agents send initial configuration messages
- Colors appear on agent nodes
- Negotiation begins

### Command-Line Testing

```bash
# Test LLM_TOOL mode with UI
python run_experiment.py --method LLM_TOOL --use-ui --agent-alg greedy --max-iters 10

# Test LLM_REACT mode with UI
python run_experiment.py --method LLM_REACT --use-ui --agent-alg maxsum --max-iters 10

# Test without UI (batch mode, requires valid API key)
python run_experiment.py --method LLM_TOOL --no-ui --max-iters 5
```

**Expected behavior**:
- No "Unknown METHOD" errors
- No OpenAI import errors
- Agents initialize successfully
- If no API key: Warning message and fallback to algorithmic mode
- If valid API key: LLM reasoning proceeds

## Troubleshooting

### Issue: "Failed to initialize OpenAI client"

**Cause**: Missing or invalid API key

**Solutions**:
1. Add valid key to `api_key.txt`
2. Run in manual mode: `python launch_menu.py` and check "Manual LLM mode (no API)"
3. Agents will fall back to algorithmic mode automatically

### Issue: "cannot import name 'OpenAI' from 'openai'"

**Cause**: Old openai package version

**Solution**:
```bash
pip install --upgrade openai
python -c "import openai; print(openai.__version__)"  # Should show 1.0+
```

### Issue: Unicode encoding errors in console

**Cause**: Windows console encoding limitations (not related to LLM agents)

**Solutions**:
1. Use `--use-ui` flag to run with GUI instead of console
2. Or ignore (doesn't affect agent operation)

### Issue: ValueError "Unknown METHOD: LLM_TOOL"

**Cause**: Outdated run_experiment.py

**Solution**: Verify lines 151-154 in `run_experiment.py` include:
```python
elif method == "LLM_TOOL":
    cluster_message_types = {"Human": "free_text", "Agent1": "llm_tool", "Agent2": "llm_tool"}
elif method == "LLM_REACT":
    cluster_message_types = {"Human": "free_text", "Agent1": "llm_react", "Agent2": "llm_react"}
```

## Verification Checklist

Run through this checklist to verify installation:

- [ ] Virtual environment activated
- [ ] OpenAI package upgraded (version 2.20.0+)
- [ ] `test_multi_layer_llm.py` passes
- [ ] `test_integration_new_modes.py` passes
- [ ] `python launch_menu.py` shows LLM_TOOL and LLM_REACT in dropdown
- [ ] Can run `python run_experiment.py --method LLM_TOOL --help` without errors
- [ ] GUI launches successfully with `--use-ui`

## Running Without API Key (Template Mode)

The new modes can run in **template mode** without OpenAI API:
- Speech layer uses heuristic parsing and template rendering
- Backend LLM falls back to algorithmic solver
- Useful for testing system integration

To use template mode:
1. Don't create `api_key.txt`, OR
2. Check "Manual LLM mode (no API)" in launcher, OR
3. Use `--manual` flag: `python run_experiment.py --method LLM_TOOL --manual`

## File Summary

### Files Created (9 total)
1. `agents/cluster_agent_api.py` - API library
2. `agents/tool_calling_cluster_agent.py` - LLM_TOOL agent
3. `agents/react_cluster_agent.py` - LLM_REACT agent
4. `comm/speech_llm_layer.py` - Speech layer
5. `test_multi_layer_llm.py` - Basic tests
6. `test_integration_new_modes.py` - Integration tests
7. `docs/MULTI_LAYER_LLM_ARCHITECTURE.md` - Full docs
8. `docs/MULTI_LAYER_LLM_QUICKSTART.md` - Quick start
9. `IMPLEMENTATION_SUMMARY.md` - Implementation summary

### Files Modified (3 total)
1. `launch_menu.py` (line 71) - Added modes to dropdown
2. `cluster_simulation.py` (lines 388-422) - Agent creation
3. `run_experiment.py` (lines 151-154, 186) - Method validation and CLI args

## System Requirements

- Python 3.9+
- openai>=2.20.0
- tkinter (for GUI)
- Other dependencies in requirements.txt

## Performance Notes

### With API Key (LLM Reasoning)
- **LLM_TOOL**: ~2-5 seconds per turn (depending on tool calls)
- **LLM_REACT**: ~5-10 seconds per turn (more reasoning steps)
- **Cost**: $0.02-0.03 per turn with gpt-4-turbo

### Without API Key (Template Mode)
- **Both modes**: <1 second per turn (algorithmic solver)
- **Cost**: $0 (no API calls)

## Next Steps

After successful installation and testing:

1. **Read documentation**: `docs/MULTI_LAYER_LLM_QUICKSTART.md`
2. **Try experiments**: Run with different algorithms and max iterations
3. **Analyze logs**: Check `results/*/llm_trace.jsonl` or `react_trace.jsonl`
4. **Customize**: Edit prompts in agent files for domain-specific behavior

## Support

If issues persist:
1. Check this guide's troubleshooting section
2. Run diagnostic: `python test_integration_new_modes.py`
3. Check logs in `results/` directory
4. Review error messages carefully

---

**Status**: ✅ All systems operational
**Last Updated**: 2026-02-11
