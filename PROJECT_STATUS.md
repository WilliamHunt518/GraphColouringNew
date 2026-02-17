# Project Status - Graph Coloring Negotiation System

**Last Updated**: 2026-02-17
**Status**: ✅ Working (all critical bugs fixed)

## Quick Start

```bash
python launch_menu.py
```

Select mode:
- **LLM_TOOL**: Tool calling with backend LLM reasoning
- **LLM_REACT**: ReAct-style reasoning with explicit thoughts
- **LLM_RB**: Rule-based with natural language interface
- **RB**: Pure rule-based (baseline)

## Recent Fixes (2026-02-17)

### Critical Fix: Announcement Phase
**Problem**: Agents announced random colors causing conflicts in first message.
**Solution**: Agents now recompute assignments before announcing to respect human's colors.
**Status**: ✅ Fixed and tested

### LLM Path Auto-Completion
**Problem**: LLM generated incomplete neighbor configs causing incorrect penalties.
**Solution**: Post-processing auto-completes all neighbor configs before execution.
**Status**: ✅ Fixed and tested

## System Architecture

```
Human (NL) ↔ Speech LLM ↔ Backend LLM ↔ API Library
```

- **Speech LLM**: Translates between natural language and structured protocol
- **Backend LLM**: Reasons about graph coloring using API functions
- **API Library**: Provides graph coloring operations (11 functions)

## Key Files

### Core System
- `launch_menu.py` - GUI launcher
- `cluster_simulation.py` - Main simulation loop
- `run_experiment.py` - Programmatic experiment runner

### Agents
- `agents/tool_calling_cluster_agent.py` - LLM_TOOL mode
- `agents/react_cluster_agent.py` - LLM_REACT mode
- `agents/cluster_agent_api.py` - API library
- `agents/cluster_agent.py` - Base cluster agent

### Communication
- `comm/speech_llm_layer.py` - NL translation layer
- `comm/communication_layer.py` - Base communication

### UI
- `ui/human_turn_ui.py` - Tkinter GUI

## Testing

Run all tests:
```bash
python run_all_tests.py
```

Key test files:
- `tests/test_announcement_flow_final.py` - Announcement phase
- `tests/test_llm_incomplete_neighbor_fix.py` - LLM auto-completion
- `tests/test_complete_neighbor_simulation.py` - Fallback completeness

## Documentation

See `docs/` directory:
- `FIX_HISTORY.md` - Complete fix history
- `MULTI_LAYER_LLM_ARCHITECTURE.md` - Architecture details
- `SYSTEM_OVERVIEW.md` - System overview
- `QUICK_START_LLM_MODES.md` - Getting started

## Known Issues

None currently - system working as expected.

## API Key

Place OpenAI API key in `api_key.txt` (gitignored).

Required for LLM modes: LLM_TOOL, LLM_REACT, LLM_RB
Not required for: RB mode
