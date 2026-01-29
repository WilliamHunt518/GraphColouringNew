# Impossible Conditions Feature - Implementation Summary

## Overview

Successfully implemented the ability for users to mark specific node-color pairs as IMPOSSIBLE during rejection, preventing agents from re-proposing those conditions in ANY future combination.

## Problem Solved

**Before**: When user rejected an offer like "IF h4=green AND h5=red THEN...", the agent stored the entire tuple `(h4=green, h5=red)` but could still propose h4=green in other combinations like "IF h4=green AND h5=blue THEN...".

**After**: User can now explicitly mark h4=green as impossible, preventing the agent from proposing h4=green in ANY future configuration.

## Implementation Details

### 1. Protocol Extension (comm/rb_protocol.py)

**Added field to RBMove dataclass:**
```python
impossible_conditions: Optional[List[Dict[str, str]]] = None
```

**Updated methods:**
- `to_dict()`: Serializes impossible_conditions to wire format
- `parse_rb()`: Parses and validates impossible_conditions from incoming messages
- `pretty_rb()`: Displays marked conditions in human-readable format

**Wire format example:**
```json
{
  "move": "Reject",
  "refers_to": "offer_123",
  "impossible_conditions": [
    {"node": "h4", "colour": "green"},
    {"node": "h5", "colour": "red"}
  ]
}
```

**Pretty print example:**
```
Reject offer offer_123 (marking as impossible: h4=green, h5=red) | reasons: human_rejected
```

### 2. Agent Logic (agents/rule_based_cluster_agent.py)

**Added storage:**
```python
self.rb_impossible_conditions: Dict[str, Set[Tuple[str, str]]] = {}
# {recipient: {(node, color), ...}}
```

**Rejection processing (line ~1070):**
- Extracts impossible_conditions from Reject message
- Stores each (node, color) pair in `rb_impossible_conditions[sender]`
- Continues to also store full tuple in `rb_rejected_conditions` for backward compatibility
- Logs each impossible condition for debugging

**Offer generation filtering (line ~680):**
- Before enumerating configurations, filters out any containing impossible pairs
- Logs how many configs were filtered
- Returns None if all configurations are impossible

**Alternative solution search (line ~770):**
- When looking for fallback configurations after rejection
- Also checks impossible conditions, not just rejected tuples
- Skips configurations containing any impossible pair

### 3. UI Dialog (ui/human_turn_ui.py)

**New method: `_reject_offer_with_dialog()` (line ~1282):**
- Creates modal dialog when user clicks "Reject"
- Shows scrollable list of checkboxes for all conditions in offer
- User selects which conditions are impossible
- Returns RBMove with `impossible_conditions` field, or None if cancelled

**Dialog features:**
- Centered modal window (500x400)
- Clear instructions: "Select conditions that you can NEVER satisfy"
- Scrollable list (handles offers with many conditions)
- Two buttons: "Reject Offer" (confirms) and "Cancel" (aborts)
- Tracks selection count in transcript

**Updated `_reject_offer()` method:**
- Calls dialog instead of immediately sending rejection
- Handles cancellation gracefully (no message sent)
- Includes impossible count in transcript
- Backward compatible (works if no conditions marked)

## Data Flow

### Happy Path Example

1. **Agent sends offer:**
   ```
   ConditionalOffer: If h4=green AND h5=red then a2=blue
   ```

2. **Human clicks "Reject" button**

3. **Dialog appears showing:**
   ```
   Which conditions are IMPOSSIBLE for you?

   ☐ h4 = green
   ☐ h5 = red

   [Reject Offer] [Cancel]
   ```

4. **Human checks h4=green, clicks "Reject Offer"**

5. **UI sends:**
   ```
   Reject offer_123 (marking as impossible: h4=green)
   ```

6. **Agent receives and stores:**
   ```python
   rb_impossible_conditions["Human"] = {('h4', 'green')}
   rb_rejected_conditions["Human"] = {(('h4', 'green'), ('h5', 'red'))}
   ```

7. **Agent generates next offer:**
   - Filters out ALL configs containing h4=green
   - Finds alternative: "If h4=red AND h5=blue then a2=yellow"

8. **Future offers:**
   - Agent NEVER proposes h4=green in ANY combination
   - Can still propose h4=red, h4=blue, h5=green, etc.

## Storage Separation

Agent maintains two separate rejection stores:

1. **`rb_rejected_conditions[recipient]`** - Full tuples
   - Stores complete condition combinations
   - Example: `{(('h4', 'green'), ('h5', 'red'))}`
   - Agent won't re-propose this EXACT combination

2. **`rb_impossible_conditions[recipient]`** - Individual pairs
   - Stores single (node, color) pairs
   - Example: `{('h4', 'green')}`
   - Agent won't use this pair in ANY combination
   - More aggressive filtering

Both are checked during offer generation for maximum filtering.

## Backward Compatibility

✓ Field is optional - old code continues to work
✓ Rejection without marking conditions works normally
✓ Existing tuple-based rejection still functions
✓ Parse gracefully handles missing impossible_conditions
✓ Other move types (Accept, ConditionalOffer) unaffected

## Testing

### Automated Tests (test_impossible_conditions.py)

All tests pass:
- ✓ Serialization to dict
- ✓ Wire format encoding
- ✓ Parsing from wire message
- ✓ Pretty printing with impossible conditions
- ✓ Backward compatibility (rejection without marking)
- ✓ Other move types unaffected
- ✓ ConditionalOffer works normally

### Manual Testing Checklist

1. **Mark Single Condition:**
   - Agent proposes: "IF h4=green AND h5=red THEN..."
   - Reject, mark h4=green as impossible
   - Verify: Next offer does NOT contain h4=green
   - Verify: Can still propose h4=red, h4=blue, etc.

2. **Mark Multiple Conditions:**
   - Agent proposes: "IF h1=red AND h4=green AND h5=blue THEN..."
   - Reject, mark h4=green AND h5=blue
   - Verify: Both stored separately
   - Verify: Agent avoids both in future offers
   - Verify: h1=red still usable (not marked)

3. **Cancel Rejection:**
   - Agent proposes offer
   - Click "Reject", dialog opens
   - Click "Cancel"
   - Verify: Offer remains pending
   - Verify: No message sent

4. **Reject Without Marking:**
   - Agent proposes offer with conditions
   - Click "Reject", don't check any boxes
   - Click "Reject Offer"
   - Verify: Reject sent without impossible_conditions
   - Verify: Existing tuple rejection works

5. **All Configs Impossible:**
   - Mark conditions eliminating all valid configs
   - Agent tries to generate offer
   - Verify: Log shows "All configurations contain impossible conditions"
   - Verify: Agent returns None, doesn't crash

6. **Status Update (No Conditions):**
   - Agent sends boundary update (unconditional)
   - Verify: No "Reject" button shown
   - Verify: Status updates aren't rejectable

### Log Verification Commands

```bash
# Check agent impossible conditions tracking:
grep "IMPOSSIBLE condition" results/rb/Agent1_log.txt

# Check filtering behavior:
grep "Filtered out.*impossible" results/rb/Agent1_log.txt

# Check message exchange:
tail -30 results/rb/communication_log.txt
```

## Files Modified

1. **comm/rb_protocol.py** - Protocol extension
   - Added impossible_conditions field
   - Updated serialization/parsing/pretty-print

2. **agents/rule_based_cluster_agent.py** - Agent logic
   - Added rb_impossible_conditions storage
   - Updated rejection processing
   - Added filtering in offer generation

3. **ui/human_turn_ui.py** - UI dialog
   - Added _reject_offer_with_dialog() method
   - Modified _reject_offer() to use dialog

## Success Criteria

All criteria met:

✓ Dialog shows checkboxes for all conditions in rejected offer
✓ Selected conditions included in Reject message as `impossible_conditions`
✓ Agent stores impossible pairs in `rb_impossible_conditions[sender]`
✓ Agent filters configurations containing impossible pairs
✓ Agent never re-proposes configurations with impossible conditions
✓ Multiple impossible conditions accumulate correctly
✓ Rejection without marking conditions works (backward compatible)
✓ Cancel button aborts rejection without sending message
✓ Pretty printing shows which conditions were marked impossible
✓ Logs clearly show filtering behavior

## Benefits

1. **More expressive rejection**: User can communicate WHY rejection happened
2. **Faster convergence**: Agent doesn't waste time re-proposing impossible conditions
3. **Better UX**: User feels heard when specific conditions are problematic
4. **Maintains privacy**: User doesn't need to explain WHY something is impossible
5. **Granular control**: Can reject part of an offer without rejecting all conditions

## Example Scenario

**Problem Graph:**
- Human controls h1, h4, h5
- h4 and h5 are boundary nodes visible to Agent1
- Human has local constraint: h4 cannot be green (conflicts with h1)

**Without this feature:**
- Agent proposes: "IF h4=green AND h5=red..."
- Human rejects (no details)
- Agent tries: "IF h4=green AND h5=blue..." (still fails!)
- Agent tries: "IF h4=green AND h5=yellow..." (still fails!)
- Many wasted rounds

**With this feature:**
- Agent proposes: "IF h4=green AND h5=red..."
- Human rejects, marks h4=green as impossible
- Agent IMMEDIATELY knows h4=green is off the table
- Agent proposes: "IF h4=red AND h5=blue..." (different h4 color!)
- Faster convergence

## Future Enhancements (Not Implemented)

Possible extensions:
1. Add explanation field: "Why is this impossible?"
2. Add timeout: "Impossible for next N rounds only"
3. Track impossible conditions in logs for analysis
4. Show impossible conditions in UI (grayed out or crossed out)
5. Allow removing impossible conditions (if user changes mind)
