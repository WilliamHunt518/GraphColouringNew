# Implementation Complete: All Three Phases

## Summary

Successfully implemented bug fix + two major features for the rule-based negotiation system:

1. **Phase 1**: Fixed "Add Condition" button bug
2. **Phase 2**: Added feasibility query feature (check without committing)
3. **Phase 3**: Enhanced granular rejection (mark individuals + combinations)

---

## Phase 1: Bug Fix ✅

### Problem
"Add Condition" button in conditional builder wasn't working after recent UI changes.

### Root Cause
Parameter conflict in closure - default parameters in function definition AND explicit parameters in lambda command.

### Solution
**File**: `ui/human_turn_ui.py` (lines 547, 660)

```python
# BEFORE (broken):
def add_condition_row(n=neigh, container=conditions_container):
    ...
command=lambda n=neigh, c=conditions_container: add_condition_row(n, c)

# AFTER (fixed):
def add_condition_row():
    n = neigh
    container = conditions_container
    ...
command=add_condition_row
```

---

## Phase 2: Feasibility Query Feature ✅

### Overview
Human can now ask "IF h2=red AND h5=blue, can you work with that?" WITHOUT committing to an offer. Agent evaluates and responds with feasibility + penalty.

### User Flow
1. Build conditions in conditional builder (IF part)
2. Click "Check Feasibility" button
3. Query appears in conditionals sidebar (pending)
4. Agent evaluates best response to those conditions
5. Response updates card: ✓ Feasible (penalty=X) or ✗ Not Feasible
6. Human uses info to decide whether to send actual offer

### Files Modified

#### 1. Protocol (`comm/rb_protocol.py`)
- Added `FeasibilityQuery` and `FeasibilityResponse` to `ALLOWED_MOVES`
- Extended `RBMove` dataclass:
  ```python
  query_id: Optional[str] = None
  is_feasible: Optional[bool] = None
  feasibility_penalty: Optional[float] = None
  feasibility_details: Optional[str] = None
  ```
- Updated serialization (`to_dict`, `parse_rb`, `pretty_rb`)

#### 2. Agent Handler (`agents/rule_based_cluster_agent.py`)
- Added handler in `_process_rb_move()` (line ~1148, before ConditionalOffer)
- Logic:
  1. Extracts conditions from query
  2. Builds hypothetical neighbor configuration
  3. Runs exhaustive search (or greedy for large boundaries)
  4. Evaluates best achievable penalty
  5. Sends `FeasibilityResponse` immediately
- Response includes:
  - `is_feasible`: boolean
  - `feasibility_penalty`: best penalty value
  - `feasibility_details`: human-friendly explanation

#### 3. UI Components (`ui/human_turn_ui.py`)

**Data Structure** (line ~92):
```python
self._feasibility_queries: Dict[str, List[Dict[str, Any]]] = {}
```

**Check Feasibility Button** (line ~878-973):
- Placement: Between "Pass" and "Send Offer" buttons
- Function extracts conditions from builder
- Validates at least 1 condition exists
- Builds query with unique ID: `query_{timestamp}_Human_{neighbor}`
- Sends via background thread (same pattern as offers)
- Stores query for tracking

**Query Cards Rendering** (line ~1455-1533):
- Added to `_render_conditional_cards()` method
- Renders after offer cards, before scroll region update
- Card shows:
  - Query ID (last 8 chars)
  - Conditions: "IF h2=red AND h5=blue"
  - Result when available:
    - ✓ Feasible (penalty=X.X) - green
    - ✗ Not Feasible - red
    - Details text
  - "Dismiss" button

**Response Processing** (line ~2719-2731):
- Added to `_flush_incoming()` method
- Parses `FeasibilityResponse` from agent
- Matches response to query via `refers_to` field
- Updates query dict and re-renders cards

---

## Phase 3: Enhanced Granular Rejection ✅

### Overview
When rejecting an offer, human can now mark:
1. **Individual conditions** as impossible (e.g., "h1=red NEVER acceptable")
2. **Combinations** as impossible (e.g., "h1=red AND h4=green together not OK, but each OK separately")

### User Flow
1. Agent sends conditional offer: "IF h1=red AND h4=green AND h7=blue THEN..."
2. Human clicks "Reject"
3. Enhanced dialog appears with TWO sections:
   - **Individual conditions**: Checkboxes for each condition
   - **Combinations**: Multi-select dropdowns to build custom combinations
4. Human can:
   - Check h1=red as individually impossible
   - Build combination: h4=green + h7=blue (together impossible)
   - Click "Add to List" to mark the combination
5. Click "Reject Offer"
6. Agent receives rejection with both individual + combination constraints
7. Future offers respect BOTH types of constraints

### Files Modified

#### 1. Protocol (`comm/rb_protocol.py`)
- Extended `RBMove` dataclass:
  ```python
  impossible_conditions: Optional[List[Dict[str, str]]] = None  # Individuals
  impossible_combinations: Optional[List[List[Dict[str, str]]]] = None  # Combinations
  ```
- Updated serialization methods:
  - `to_dict()`: Serializes both fields
  - `parse_rb()`: Validates structure for combinations (list of lists)
  - `pretty_rb()`: Displays combinations as "(h1=red AND h4=green)"

#### 2. Agent Storage & Processing (`agents/rule_based_cluster_agent.py`)

**Data Structure** (line ~99):
```python
self.rb_impossible_conditions: Dict[str, Set[Tuple[str, str]]] = {}
# {recipient: {(node, color), ...}} - individual impossibilities

self.rb_impossible_combinations: Dict[str, Set[FrozenSet[Tuple[str, str]]]] = {}
# {recipient: {frozenset({(n1,c1), (n2,c2)}), ...}} - combination impossibilities
```

**Rejection Processing** (line ~1287-1324):
- Parses `impossible_combinations` from rejection message
- Converts each combination to `frozenset` of tuples
- Stores in `rb_impossible_combinations[sender]`
- Logs each stored combination

**Filtering Logic** (line ~772-797):
- **Individual filtering** (existing):
  - Checks if any condition in config is in `rb_impossible_conditions`
  - Filters out configs containing ANY impossible individual condition

- **Combination filtering** (NEW):
  - Checks if ANY impossible combo is subset of config
  - Uses `frozenset.issubset()` for efficient matching
  - Filters out configs where combination appears together
  - Logs filtered count

**Phase Transition** (line ~1078-1080):
- Clears both `rb_impossible_conditions` and `rb_impossible_combinations`
- Ensures clean slate for new bargaining round

#### 3. Enhanced Rejection Dialog (`ui/human_turn_ui.py`)

**Structure** (line ~1550-1768):
- Larger dialog: 600x600px
- Scrollable content area

**Section 1: Individual Conditions**
- Header: "Individual conditions (NEVER acceptable):"
- Checkboxes for each condition in offer
- Marks conditions impossible by themselves

**Section 2: Combinations**
- Header: "Combinations (only impossible TOGETHER):"
- Dynamic dropdown builder:
  - Starts with 2 dropdowns
  - "+ Add Another Condition" button for more
  - "✗" button to remove dropdown
- "✓ Add to List" button validates and adds combination
- List of marked combinations with remove buttons
- Each combo displayed as: "• (h1=red AND h4=green) [✗ Remove]"

**Validation**:
- Combination requires 2+ conditions
- Duplicate combinations rejected with info message
- Section hidden if offer has < 2 conditions

**Result Collection**:
```python
result = {
    "impossible_individuals": [{"node": "h1", "colour": "red"}],
    "impossible_combinations": [
        [{"node": "h1", "colour": "red"}, {"node": "h4", "colour": "green"}]
    ]
}
```

**Move Building**:
- Creates `RBMove` with both fields populated
- Logs counts of individuals and combinations

---

## Testing Checklist

### Phase 1: Bug Fix
- [ ] Start RB mode
- [ ] Open conditional builder
- [ ] Click "+ Add Condition" → row appears
- [ ] Toggle "Custom" mode → works
- [ ] Remove row → no errors

### Phase 2: Feasibility Query
- [ ] Start RB mode
- [ ] Add conditions: h2=red, h5=blue
- [ ] Click "Check Feasibility"
- [ ] Query card appears (pending)
- [ ] Agent response arrives
- [ ] Card updates with result (green/red)
- [ ] Test with infeasible conditions
- [ ] Dismiss query card
- [ ] Try with no conditions → warning

### Phase 3: Enhanced Rejection
- [ ] Receive conditional offer (3+ conditions)
- [ ] Click "Reject"
- [ ] Check 1 individual: h1=red
- [ ] Build combination: h4=green + h7=blue
- [ ] Click "Add to List"
- [ ] Verify combo appears in list
- [ ] Click "Reject Offer"
- [ ] Check agent log for both stored
- [ ] Receive new offer → verifies constraints respected
- [ ] Test with 2-condition offer (combination section)
- [ ] Test with 1-condition offer (no combination section)

### Integration Testing
1. **Query + Reject Flow**:
   - Query: h2=red AND h5=blue → feasible?
   - If feasible, send actual offer
   - Agent counters
   - Reject with granular marking
   - Verify next offer respects constraints

2. **Multiple Agents**:
   - Query Agent1 and Agent2 separately
   - Mark different constraints for each
   - Verify filtering is per-agent

3. **Phase Transition**:
   - Mark impossibilities in bargain phase
   - Announce new configuration
   - Verify constraints cleared for new round

4. **Edge Cases**:
   - Query with all conditions impossible → red result
   - Reject with all individuals marked
   - Reject with only combinations marked
   - Reject with both individuals + combinations
   - Duplicate combination attempt → info message
   - Remove combination from list before rejecting

---

## Key Design Decisions

### 1. Feasibility Queries Are Immediate
- Agent responds immediately (no queuing with other offers)
- Allows human to quickly test multiple scenarios
- Query doesn't consume agent's deliberation turn

### 2. Combinations Use Frozenset
- Efficient subset matching: `combo.issubset(config_set)`
- Order-independent: (h1=red, h4=green) == (h4=green, h1=red)
- Hashable for set storage

### 3. UI Shows Queries as Persistent Cards
- User preference: queries stay visible until dismissed
- Allows comparison of multiple query results
- Clear ✓/✗ visual feedback

### 4. Dialog Validates Combinations
- Must select 2+ conditions for combination
- Prevents duplicate combinations
- Section hidden if < 2 conditions available

### 5. Filtering Happens in Offer Generation
- Agent filters BEFORE proposing
- Reduces unnecessary communication
- Logs show filtered count for transparency

---

## Code Statistics

| File | Lines Added | Lines Modified | Purpose |
|------|-------------|----------------|---------|
| `comm/rb_protocol.py` | ~60 | ~40 | Protocol extensions |
| `agents/rule_based_cluster_agent.py` | ~130 | ~30 | Query handler + filtering |
| `ui/human_turn_ui.py` | ~300 | ~50 | UI components + dialog |
| **Total** | **~490** | **~120** | **All features** |

---

## Error Handling

### Feasibility Query
- No conditions → Warning dialog
- Agent error → Logged, no response (query stays pending)
- Parse error → Caught in _flush_incoming

### Rejection Dialog
- < 2 conditions for combo → Warning message
- Duplicate combo → Info message (no error)
- Cancel → Returns None, no rejection sent

### Agent Filtering
- No configs remain → Logs warning, returns None (no offer)
- Large boundary (>3 nodes) → Uses current config only (performance)

---

## Future Enhancements (Not Implemented)

1. **Query History**: Persist queries across turns
2. **Explain Why**: Agent explains why config is infeasible
3. **Suggest Alternative**: Agent proposes similar feasible conditions
4. **Auto-Query**: UI suggests queries based on offer history
5. **Batch Queries**: Test multiple condition sets at once

---

## Related Files

- `PHASE_1_2_COMPLETE.md` - Intermediate progress document
- `README.md` - Project overview
- `docs/DEVELOPER_GUIDE.md` - Where to change things
- `CLAUDE.md` - Project instructions for Claude Code

---

## Implementation Date
2026-01-29

## Implemented By
Claude Code (Sonnet 4.5)

## User Approval
Awaiting testing and user feedback
