# Directory Organization - Cleanup Summary

**Date**: 2026-02-17

## What Was Done

Organized scattered files into proper directories for better project structure.

## Directory Structure

```
GraphColouringNew/
├── Root (essential files only)
│   ├── CLAUDE.md                    # Project instructions
│   ├── README.md                    # Main documentation
│   ├── PROJECT_STATUS.md            # Current status summary
│   ├── launch_menu.py               # Main launcher (GUI)
│   ├── run_experiment.py            # Programmatic runner
│   ├── cluster_simulation.py        # Simulation loop
│   └── api_key.txt                  # OpenAI key (gitignored)
│
├── agents/                          # Agent implementations
│   ├── cluster_agent.py             # Base cluster agent
│   ├── cluster_agent_api.py         # API library (11 functions)
│   ├── tool_calling_cluster_agent.py # LLM_TOOL mode
│   ├── react_cluster_agent.py       # LLM_REACT mode
│   └── ...
│
├── comm/                            # Communication layers
│   ├── speech_llm_layer.py          # NL translation
│   ├── communication_layer.py       # Base comm layer
│   └── ...
│
├── ui/                              # User interface
│   └── human_turn_ui.py             # Tkinter GUI
│
├── tests/ (91 test files)           # All test files
│   ├── test_announcement_flow_final.py
│   ├── test_llm_incomplete_neighbor_fix.py
│   ├── test_complete_neighbor_simulation.py
│   ├── test_phase3_uses_simulations.py
│   └── ...
│
├── docs/ (62 documentation files)   # All documentation
│   ├── FIX_HISTORY.md               # Complete fix history
│   ├── COMPLETE_NEIGHBOR_FIX_SUMMARY.md
│   ├── LLM_PATH_FIX_SUMMARY.md
│   ├── MULTI_LAYER_LLM_ARCHITECTURE.md
│   ├── SYSTEM_OVERVIEW.md
│   └── ...
│
├── old_files/ (7 archived files)    # Old/deprecated files
│   ├── cluster_agent.py             # Old version
│   ├── cluster_agent_fixed.py       # Old version
│   ├── analyze_agent_behavior.py    # Analysis script
│   └── ...
│
├── problems/                        # Problem definitions
├── results/                         # Experiment outputs (gitignored)
└── venv/                            # Python virtual environment
```

## Files Moved

### To `tests/`
- test_api_neighbor_constraints.py
- test_announcement_respects_neighbors.py
- test_announcement_flow_final.py
- test_api_direct.py
- test_llm_tool_*.py
- (All test files now in tests/ directory)

### To `docs/`
- COMPLETE_NEIGHBOR_FIX_SUMMARY.md
- LLM_PATH_FIX_SUMMARY.md
- All FIX_*.md files
- All IMPLEMENTATION_*.md files
- All STATUS_*.md files
- FEATURE_SUMMARY.txt
- (All documentation now in docs/ directory)

### To `old_files/`
- cluster_agent.py (old version)
- cluster_agent_fixed.py (old version)
- analyze_agent_behavior.py
- check_human_state.py
- diagnose_convergence.py
- SUCCESSFUL_TEST_*.txt (old logs)

### Removed
- test_output.txt
- test_output2.txt
- Weirdly named files

## Root Directory (Clean)

Only essential files remain in root:
- Launch scripts (launch_menu.py, run_experiment.py)
- Main system files (cluster_simulation.py)
- Documentation (CLAUDE.md, README.md, PROJECT_STATUS.md)
- Configuration (api_key.txt)

## Benefits

✅ **Cleaner root directory** - Only essential files visible
✅ **Organized tests** - All 91 tests in one place
✅ **Consolidated docs** - All 62 docs in one place
✅ **Archived old files** - Preserved but out of the way
✅ **Easier navigation** - Clear structure for developers

## Quick Access

- **Start system**: `python launch_menu.py`
- **Run tests**: `python run_all_tests.py`
- **View docs**: See `docs/FIX_HISTORY.md`
- **Check status**: See `PROJECT_STATUS.md`

## Git Status

Many files moved/deleted in git. Before committing:
1. Review changes with `git status`
2. Add new files: `git add docs/ tests/ old_files/ PROJECT_STATUS.md`
3. Commit: `git commit -m "Reorganize project structure - move tests, docs, and archive old files"`
