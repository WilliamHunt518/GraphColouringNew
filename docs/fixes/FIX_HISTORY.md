# Fix History - LLM Agent Modes

This directory contains documentation of fixes applied to the LLM-based agent modes (LLM_TOOL, LLM_REACT).

## Critical Fixes (2026-02-17)

### 0. ReAct Agent Action Parsing Bug - MOST CRITICAL FOR LLM_REACT MODE
**File**: `FIX_REACT_ACTION_PARSING.md`

**Problem**: ReAct agents were failing to execute API function calls, causing repeated errors and eventual failure.

**Root Cause**:
- Regex pattern `r"Action:\s*(\w+)\((.*?)\)"` used non-greedy matching
- Stopped at FIRST `)`, breaking when arguments contained dictionaries
- Example: `get_best_response_to(neighbor_assignments={"h1": "red"})` captured as `neighbor_assignments={"h1": "red"` (missing closing `}`)
- Invalid JSON caused "input format" errors, LLM retried with same bad format

**Fix**: Replaced regex with parenthesis counting algorithm to correctly extract complete arguments with balanced delimiters.

**Impact**: LLM_REACT mode now works reliably - agents parse function calls correctly on first try, no more retries, both Agent1 and Agent2 work.

### 1. Announcement Phase Fix - MOST CRITICAL
**File**: `COMPLETE_NEIGHBOR_FIX_SUMMARY.md`, `LLM_PATH_FIX_SUMMARY.md`

**Problem**: Agents announced random initial colors without considering human's announced colors, causing conflicts in the very first message.

**Root Cause**:
- Agents initialized with random colors
- `_handle_announce_config()` used random assignments without recomputing
- Even though `_sync_neighbour_views()` had populated `neighbour_assignments`, agents didn't use it

**Fix**: Added recomputation in `_handle_announce_config()` and `_send_automatic_announcement()` to respect known neighbor constraints before announcing.

**Impact**: Agents now announce conflict-free configurations that respect human's colors.

### 2. LLM Incomplete Neighbor Configs
**File**: `LLM_PATH_FIX_SUMMARY.md`

**Problem**: Backend LLM generated incomplete neighbor configs like `{"h2": "red", "h5": "blue"}` without other neighbors, causing incorrect penalty calculations.

**Fix**: Added post-processing in Phase 1 (Tool Calling) and action execution (ReAct) to auto-complete any incomplete neighbor configs with current values before API execution.

**Impact**: All `simulate_neighbor_change()` calls now use complete neighbor information for accurate penalty calculations.

### 3. Phase 3 Template Fallback
**File**: `TEMPLATE_FALLBACK_FIX.md`, `FIX_VALID_PROPOSALS.md`

**Problem**: Template fallback proposed arbitrary changes without testing (e.g., "Could you change h4 to blue?" without verifying it works).

**Fix**:
- Phase 1 fallback generates comprehensive simulation calls
- Phase 3 fallback extracts simulation results (penalty=0) and proposes only TESTED alternatives

**Impact**: Agents only propose changes that have been verified to work.

## Other Fixes

### Message Validation
**File**: `MESSAGE_SPECIFICITY_IMPROVEMENTS.md`

- Enhanced validation to block vague messages
- Enforced partial observability (only mention visible nodes)
- Made validation blocking (not just warnings)

### Algorithm Consistency
**File**: `FIX_EXHAUSTIVE_ALGORITHM.md`

- Changed default from greedy to maxsum (exhaustive)
- Ensures agents can execute their own plans

### Acceptance Check
**File**: `FIX_CHECK_ACCEPTANCE_FIRST.md`

- Added Phase 0: check if current config works before negotiating
- Prevents unnecessary change requests

## Testing

All fixes are covered by tests in `tests/`:
- `test_complete_neighbor_simulation.py` - Fallback completeness
- `test_llm_incomplete_neighbor_fix.py` - LLM path auto-completion
- `test_announcement_flow_final.py` - Announcement phase fix
- `test_phase3_uses_simulations.py` - Phase 3 uses tested alternatives
- `test_message_validation.py` - Message specificity
- And more...

## Architecture Documentation

- `MULTI_LAYER_LLM_ARCHITECTURE.md` - Overall architecture
- `MULTI_LAYER_LLM_QUICKSTART.md` - Quick start guide
- `MODES_COMPARISON.md` - Comparison of different modes

## Status

✅ All critical bugs fixed
✅ Agents respect neighbor constraints
✅ No more conflicting proposals
✅ System working correctly (per user confirmation)
