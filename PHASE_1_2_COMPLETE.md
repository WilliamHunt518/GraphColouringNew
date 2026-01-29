# Phase 1 & 2 Implementation Complete

## Phase 1: Bug Fix ✓

### Issue
The "Add Condition" button wasn't working due to parameter conflict in closure.

### Fix Applied
**File**: `ui/human_turn_ui.py` (lines 547, 658)

- Removed default parameters from `add_condition_row()` function
- Moved parameter capture inside function body using closure
- Simplified button command to direct function reference

**Before:**
```python
def add_condition_row(n=neigh, container=conditions_container):
    ...
command=lambda n=neigh, c=conditions_container: add_condition_row(n, c)
```

**After:**
```python
def add_condition_row():
    n = neigh
    container = conditions_container
    ...
command=add_condition_row
```

## Phase 2: Feasibility Query Feature ✓

### Overview
Human can now query agent about feasibility of conditions WITHOUT committing to an offer.

### Files Modified

#### 1. Protocol Extension (`comm/rb_protocol.py`)
- Added `FeasibilityQuery` and `FeasibilityResponse` to `ALLOWED_MOVES`
- Extended `RBMove` dataclass with fields:
  - `query_id`: Unique query identifier
  - `is_feasible`: Boolean result
  - `feasibility_penalty`: Penalty value if feasible
  - `feasibility_details`: Human-readable explanation
- Updated `to_dict()`, `parse_rb()`, and `pretty_rb()` to handle new move types

#### 2. Agent Handler (`agents/rule_based_cluster_agent.py`)
- Added `FeasibilityQuery` handler in `_process_rb_move()` (before ConditionalOffer handler)
- Logic:
  1. Extracts conditions from query
  2. Builds hypothetical neighbor configuration
  3. Runs exhaustive search (or tests current config for large boundaries)
  4. Evaluates best penalty achievable
  5. Builds `FeasibilityResponse` with:
     - Feasible: yes/no
     - Penalty: best achievable value
     - Details: human-friendly explanation
  6. Sends response immediately (no queuing)

#### 3. UI Components (`ui/human_turn_ui.py`)

**Data Structure** (line ~92):
```python
self._feasibility_queries: Dict[str, List[Dict[str, Any]]] = {}
```

**Check Feasibility Button** (line ~878-973):
- Function `check_feasibility(n)`:
  1. Extracts conditions from conditional builder
  2. Validates at least one condition exists
  3. Builds `FeasibilityQuery` message with unique query_id
  4. Displays query in transcript
  5. Stores query in `_feasibility_queries` dict
  6. Sends via background thread (same pattern as offers)
  7. Updates conditionals display

**Button Placement** (line ~1013):
- Between "Pass" and "Send Offer" buttons
- Label: "Check Feasibility"

**Query Cards Rendering** (line ~1373-1455):
- Added to `_render_conditional_cards()` method
- Renders AFTER offer cards but BEFORE scroll region update
- Card displays:
  - Query ID (last 8 chars)
  - Conditions: "IF h2=red AND h5=blue"
  - Result (when available):
    - ✓ Feasible (penalty=X.X) in green
    - ✗ Not Feasible in red
    - Details text below
  - Dismiss button to remove query card

**Response Processing** (line ~2719-2731):
- Added to `_flush_incoming()` method
- Parses incoming messages for `FeasibilityResponse`
- Matches response to query via `refers_to` field
- Updates query dict with results
- Triggers `_render_conditional_cards()` to show result

### User Flow
1. Human builds conditions in conditional builder (IF part)
2. Clicks "Check Feasibility"
3. Query sent to agent → appears in transcript
4. Query card appears in conditionals sidebar (pending)
5. Agent evaluates → sends response
6. Query card updates with result (green ✓ or red ✗)
7. Human can dismiss query or use info to decide on offer

### Testing Checklist for Phases 1-2

**Bug Fix:**
- [x] Start RB mode
- [x] Click "Build Conditional Offer"
- [ ] Click "+ Add Condition" - should add new row
- [ ] Toggle "Custom" mode - should work
- [ ] Remove row - should work without errors

**Feasibility Query:**
- [ ] Start RB mode
- [ ] Add conditions: h2=red, h5=blue
- [ ] Click "Check Feasibility"
- [ ] Verify query appears in sidebar (pending state)
- [ ] Wait for agent response
- [ ] Verify result shows in card (feasible/not feasible + penalty)
- [ ] Click "Dismiss" to remove query card
- [ ] Try query with no conditions - should show warning

**Integration:**
- [ ] Query with feasible conditions → green result
- [ ] Query with infeasible conditions → red result
- [ ] Multiple queries to different agents
- [ ] Query during agent's turn (should queue normally)

## Next: Phase 3

Enhanced Granular Rejection - Allow marking:
1. Individual conditions as impossible (h1=red NEVER acceptable)
2. Combinations as impossible (h1=red AND h4=green together not acceptable, but each OK separately)

Files to modify:
- `ui/human_turn_ui.py` - Enhanced rejection dialog
- `comm/rb_protocol.py` - Add `impossible_combinations` field
- `agents/rule_based_cluster_agent.py` - Track and filter combinations
