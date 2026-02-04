# Impossible Conditions Feature - Quick Start

## What's New?

When rejecting an agent's conditional offer, you can now mark specific conditions as **impossible** (e.g., "h4 can never be green"). The agent will remember this and never propose that condition again in ANY combination, leading to faster convergence.

## Implementation Status

✅ **COMPLETE** - All tests pass, code compiles, ready for use.

## Quick Demo

1. Launch RB mode:
   ```bash
   python launch_menu.py
   # Select "RB (Rule-based)" mode
   ```

2. Wait for agent to send conditional offer

3. Click "Reject" → Dialog appears with checkboxes

4. Check conditions you can NEVER satisfy → Click "Reject Offer"

5. Agent's next offer won't contain marked conditions!

## Key Files

### Implementation
- `comm/rb_protocol.py` - Protocol extension (impossible_conditions field)
- `agents/rule_based_cluster_agent.py` - Agent logic (storage + filtering)
- `ui/human_turn_ui.py` - Rejection dialog (checkboxes)

### Documentation
- `IMPOSSIBLE_CONDITIONS_IMPLEMENTATION.md` - Technical details
- `docs/IMPOSSIBLE_CONDITIONS_USER_GUIDE.md` - User-facing guide
- `IMPOSSIBLE_CONDITIONS_DIAGRAM.txt` - Visual architecture
- `IMPLEMENTATION_COMPLETE.md` - Implementation summary

### Testing
- `test_impossible_conditions.py` - Automated test suite (all pass ✓)

## How It Works

**Before:**
```
Agent: "IF h4=green AND h5=red THEN..."
Human: Reject (no details)
Agent: "IF h4=green AND h5=blue..." (tries again with h4=green)
Human: Reject again (wasted round)
```

**After:**
```
Agent: "IF h4=green AND h5=red THEN..."
Human: Reject + mark h4=green as impossible
Agent: "IF h4=red AND h5=blue..." (different h4 color!)
Human: Accept (faster convergence!)
```

## Architecture

```
┌─────────────────────────────────────┐
│ User rejects offer, marks h4=green │
└────────────────┬────────────────────┘
                 ▼
┌──────────────────────────────────────────────┐
│ UI sends: impossible_conditions: [h4=green] │
└────────────────┬─────────────────────────────┘
                 ▼
┌────────────────────────────────────────────────┐
│ Agent stores: rb_impossible_conditions["Human"]│
│              = {('h4', 'green')}               │
└────────────────┬───────────────────────────────┘
                 ▼
┌──────────────────────────────────────────┐
│ Agent filters ALL configs with h4=green │
└────────────────┬─────────────────────────┘
                 ▼
┌────────────────────────────────────────┐
│ Agent proposes alternative with h4=red │
└────────────────────────────────────────┘
```

## Storage Model

Agent maintains two separate rejection stores:

```python
# Full tuple rejection (existing)
rb_rejected_conditions["Human"] = {
    (('h4', 'green'), ('h5', 'red'))  # Exact combination
}

# Individual impossible pairs (NEW!)
rb_impossible_conditions["Human"] = {
    ('h4', 'green')  # Never use in ANY combo
}
```

## Testing

### Automated
```bash
python test_impossible_conditions.py
# Result: ALL TESTS PASSED
```

### Manual
```bash
python launch_menu.py
# Select RB mode, test rejection dialog
```

### Verify in Logs
```bash
# Check agent processing:
grep "IMPOSSIBLE condition" results/rb/Agent1_log.txt

# Check filtering:
grep "Filtered out.*impossible" results/rb/Agent1_log.txt
```

## Changes Summary

```
3 files modified:
  comm/rb_protocol.py              +37 lines
  agents/rule_based_cluster_agent.py  +343 lines
  ui/human_turn_ui.py              +475 lines

Total: +855 lines
```

## Features

- ✓ Dialog with scrollable checkbox list
- ✓ Two-tier filtering (pairs + tuples)
- ✓ Backward compatible
- ✓ Comprehensive logging
- ✓ Pretty printing
- ✓ Cancel option
- ✓ Accumulates across rejections

## Benefits

1. **Faster convergence** - No wasted rounds
2. **More expressive** - Communicate what's impossible
3. **Better search** - Agent prunes search space
4. **Maintains privacy** - No need to explain why
5. **Granular control** - Mark 0, 1, or all conditions
6. **Backward compatible** - Works with existing code

## When to Mark Conditions

### ✓ Good Reasons
- Local constraint (h4 conflicts with h1)
- Fixed node (h4 must be blue)
- Resource limit (out of red tokens)

### ✗ Bad Reasons
- Current preference (prefer h4=blue)
- Uncertainty (not sure if works)
- Temporary (only for 2 rounds)

## Example Scenarios

### Scenario 1: Fixed Node
```
h1 (red, fixed) ─── h4 (?)
Agent: "IF h4=red THEN..."
Action: Mark h4=red as impossible
Result: Agent never proposes h4=red again
```

### Scenario 2: Multiple Impossible
```
Agent: "IF h4=blue AND h5=blue THEN..."
Action: Mark both h4=blue AND h5=blue
Result: Agent filters both in all future offers
```

### Scenario 3: Just Bad Combo
```
Agent: "IF h4=green AND h5=red THEN..."
Action: Mark nothing, just reject
Result: Agent remembers combo but can retry h4=green with different h5
```

## Logging Output

```
Agent1_log.txt:
[RB Process] Stored IMPOSSIBLE condition from Human: h4=green
[ConditionalOffer Gen] Filtered out 16 configs with impossible conditions

communication_log.txt:
[Human → Agent1] Reject offer_123 (marking as impossible: h4=green)
```

## Troubleshooting

### "Agent stopped making offers"
**Cause**: Too many conditions marked impossible
**Check**: `grep "All configurations contain impossible" results/rb/Agent1_log.txt`
**Fix**: Restart, mark fewer conditions

### "Agent keeps proposing same thing"
**Cause**: Conditions not marked in dialog
**Fix**: Use dialog checkboxes to mark specific conditions

## Next Steps

1. **Test manually**: Run RB mode, try rejection dialog
2. **Check logs**: Verify filtering behavior
3. **User feedback**: Get feedback on dialog UX
4. **Edge cases**: Test with many conditions, all impossible, etc.

## Documentation Index

- `README_IMPOSSIBLE_CONDITIONS.md` (this file) - Quick start
- `IMPOSSIBLE_CONDITIONS_IMPLEMENTATION.md` - Technical details
- `docs/IMPOSSIBLE_CONDITIONS_USER_GUIDE.md` - User guide
- `IMPOSSIBLE_CONDITIONS_DIAGRAM.txt` - Visual architecture
- `IMPLEMENTATION_COMPLETE.md` - Full implementation summary

## Contact

For questions or issues, check:
- Implementation docs in this directory
- Code comments in modified files
- Test cases in `test_impossible_conditions.py`

---

**Status**: ✅ READY FOR USE

**Last Updated**: 2026-01-28

**Tests**: ALL PASS

**Compilation**: SUCCESS
