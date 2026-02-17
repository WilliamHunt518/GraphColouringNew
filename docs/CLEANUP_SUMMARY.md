# Project Cleanup Summary

## Overview

Organized 180+ files from the root directory into proper subdirectories for better maintainability.

## Directory Structure

```
GraphColouringNew/
├── logs/                           # All log files
│   ├── old_debug/                  # Historical debug logs (120+ files)
│   │   └── conditional_builder_debug_*.log
│   ├── test_output/                # Old test output directories
│   ├── test_results/               # Old test results
│   ├── rb_test_full.log
│   ├── test_output.txt
│   └── test_*.txt                  # Various test output files
│
├── docs/                           # Documentation
│   ├── fixes/                      # Implementation and fix documentation
│   │   ├── CRITICAL_BUGS_FIXED.md
│   │   ├── CRITICAL_SOLVABILITY_FIX.md
│   │   ├── FEASIBILITY_FIXES.md
│   │   ├── IMPLEMENTATION_COMPLETE.md
│   │   ├── IMPLEMENTATION_COMPLETE_ALL_PHASES.md
│   │   ├── IMPOSSIBLE_CONDITIONS_IMPLEMENTATION.md
│   │   ├── PHASE_1_2_COMPLETE.md
│   │   ├── SESSION_COMPLETE.md
│   │   ├── SESSION_SUMMARY.md
│   │   └── WHAT_WAS_FIXED.md
│   ├── QUICK_REFERENCE.md
│   └── README_IMPOSSIBLE_CONDITIONS.md
│
├── tests/                          # All test scripts (moved from root)
│   ├── test_accept_satisfaction.py
│   ├── test_accept_with_announce.py
│   ├── test_agent_conversation.py
│   ├── test_agent_modes.py
│   ├── test_complete_workflow.py
│   ├── test_conditional_offers.py
│   ├── test_conditional_protocol.py
│   ├── test_constraint_extraction.py
│   ├── test_full_rb_workflow.py
│   ├── test_h1_red_query.py
│   ├── test_h1_red_validation.py
│   ├── test_impossible_conditions.py
│   ├── test_offer_expiry.py
│   ├── test_openai_api.py
│   ├── test_pass_button.py
│   ├── test_rb_complete.py
│   ├── test_rb_dialogue.py
│   ├── test_rb_fixes.py
│   ├── test_rb_negotiation.py
│   ├── test_rb_negotiation_debug.py
│   └── test_user_workflow.py
│
└── (root)                          # Clean root directory
    ├── README.md                   # Main documentation
    ├── CLAUDE.md                   # Claude Code instructions
    ├── launch_menu.py              # Main launcher
    ├── run_experiment.py           # CLI runner
    ├── cluster_simulation.py       # Core simulation
    ├── test_default_algorithm.py   # New verification test (FIX #22)
    ├── test_greedy_bug.py          # Bug reproduction test (FIX #22)
    └── test_offer_generation.py    # Offer validation test (FIX #23)

```

## Files Organized

### Moved to `logs/old_debug/` (120+ files)
- All `conditional_builder_debug_YYYYMMDD_HHMMSS.log` files from January-February 2026

### Moved to `logs/` (10+ files)
- `rb_test_full.log`
- `test_output.txt`
- `test_*.txt` (various test output files)
- `test_output/` directory
- `test_results/` directory

### Moved to `docs/fixes/` (10 files)
- `CRITICAL_BUGS_FIXED.md`
- `CRITICAL_SOLVABILITY_FIX.md`
- `FEASIBILITY_FIXES.md`
- `IMPLEMENTATION_COMPLETE.md`
- `IMPLEMENTATION_COMPLETE_ALL_PHASES.md`
- `IMPOSSIBLE_CONDITIONS_IMPLEMENTATION.md`
- `PHASE_1_2_COMPLETE.md`
- `SESSION_COMPLETE.md`
- `SESSION_SUMMARY.md`
- `WHAT_WAS_FIXED.md`

### Moved to `docs/` (2 files)
- `QUICK_REFERENCE.md`
- `README_IMPOSSIBLE_CONDITIONS.md`

### Moved to `tests/` (20+ files)
- All old test scripts (test_*.py) except the three new verification tests

### Kept in Root (3 new test files)
These are verification tests for the latest fixes (FIX #22 and #23):
- `test_default_algorithm.py` - Verifies maxsum is now the default
- `test_greedy_bug.py` - Documents the greedy node-ordering bug
- `test_offer_generation.py` - Verifies offers are conflict-free

### Removed
- `NUL` (Windows artifact file)

## Result

The root directory is now clean with only:
- Core project files (launch_menu.py, run_experiment.py, etc.)
- Main documentation (README.md, CLAUDE.md)
- Three new verification test scripts
- Standard Python project files (venv/, results/, etc.)

All historical logs, fix documentation, and old test files are properly organized in subdirectories.
