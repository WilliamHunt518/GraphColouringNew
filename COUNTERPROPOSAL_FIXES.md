# CounterProposal Fixes

## Issues Fixed

### Issue 1: Agent sending "colour=None" ✓ FIXED

**Problem:**
- Agent was sending `Challenge` moves with `colour=None`
- These got mapped to `CounterProposal` with no colour specified
- Resulted in confusing messages like "CounterProposal h4=None"

**Root Cause:**
- Old Challenge logic from previous protocol version
- Challenges didn't require specifying an alternative colour

**Fix Applied:**
Updated `agents/rule_based_cluster_agent.py` (lines 230-276):
- Changed `move="Challenge"` to `move="CounterProposal"`
- Added logic to find an alternative colour that doesn't conflict
- Now always suggests a specific colour

**Before:**
```python
return RBMove(
    move="Challenge",
    node=conflicting_nbr,
    colour=None,  # ❌ No colour specified
    reasons=reasons
)
```

**After:**
```python
# Find an alternative colour that doesn't conflict
alternative_color = None
for color in domain:
    if color != my_color and color != current_color:
        alternative_color = color
        break

return RBMove(
    move="CounterProposal",
    node=conflicting_nbr,
    colour=alternative_color,  # ✓ Specific colour suggested
    reasons=reasons
)
```

### Issue 2: Unclear how to respond to CounterProposals ✓ FIXED

**Problem:**
- Users didn't understand what CounterProposal meant
- No guidance on how to respond

**Fixes Applied:**

**1. In-UI Help Text** (`ui/human_turn_ui.py`):
- Added help label that changes based on selected move
- Shows context-appropriate guidance

**Move Type → Help Text:**
- `Propose` → "Suggest a color for a node"
- `ConditionalOffer` → "Make a deal: 'If you do X, I'll do Y'"
- `CounterProposal` → "Respond to their suggestion with an alternative color"
- `Accept` → "Accept a conditional offer from the agent"
- `Commit` → "Lock in a color choice (can still be challenged)"

**2. Comprehensive Documentation:**
Created `HOW_TO_RESPOND_TO_COUNTERPROPOSALS.md` with:
- Clear explanation of what CounterProposal means
- 3 response options (Accept, Counter, Hold Firm)
- Visual workflow examples
- UI quick reference guide
- Real examples from runs

## How to Respond to CounterProposals (Quick Guide)

### What is a CounterProposal?

The agent is suggesting a different color because of a conflict.

**Example:**
```
You:   Propose h4=red
Agent: CounterProposal h4=blue (conflicts with my a2=red)
```

### Your 3 Options:

**Option 1: Accept It** (Recommend if it makes sense)
```
Move: Commit
Node: h4
Color: blue  ← Use the color they suggested
```

**Option 2: Make Your Own Counter**
```
Move: CounterProposal
Node: h4
Color: green  ← Suggest a different alternative
```

**Option 3: Hold Your Ground**
```
Move: Propose (or Commit)
Node: h4
Color: red  ← Keep your original choice
```

## Testing the Fixes

### Test 1: Verify No More "colour=None"

1. Run: `python launch_menu.py`
2. Select RB mode, launch
3. Propose a node with a color that conflicts with agent
4. Wait for agent response
5. ✓ Should see "CounterProposal h4=blue" (specific colour)
6. ✗ Should NOT see "CounterProposal h4=None"

### Test 2: Verify Help Text Appears

1. In RB message builder section
2. Select different moves from dropdown
3. ✓ Help text should change based on selection
4. ✓ "CounterProposal" should show helpful explanation

### Test 3: Test Response Flow

1. Receive CounterProposal from agent
2. Read the help text for CounterProposal
3. Select "Commit" to accept it
4. Choose the node and color they suggested
5. Send message
6. ✓ Conflict should be resolved

## Code Changes Summary

### Files Modified:

1. **agents/rule_based_cluster_agent.py**
   - Lines 230-276: Updated conflict detection logic
   - Changed Challenge → CounterProposal
   - Added alternative colour selection algorithm

2. **ui/human_turn_ui.py**
   - Added help_text_var and help_label
   - Updated on_move_change() to set contextual help
   - Help text visible below move type dropdown

### Files Created:

1. **HOW_TO_RESPOND_TO_COUNTERPROPOSALS.md**
   - Complete user guide
   - Visual examples
   - Response patterns
   - UI quick reference

2. **COUNTERPROPOSAL_FIXES.md** (this file)
   - Summary of fixes
   - Quick reference
   - Testing guide

## Expected Behavior Now

### When Conflict Detected:

**Old Behavior:**
```
Agent → You: Challenge h4=None
                      ↑↑↑↑
                      Confusing!
```

**New Behavior:**
```
Agent → You: CounterProposal h4=blue
             Reason: conflicts with my a2=red
             ↑↑↑↑
             Clear suggestion!
```

### When You Respond:

**UI Help Text Visible:**
```
┌─ Send RB Message ──────────────────────────────────┐
│ Move: [CounterProposal ▼]                          │
│ Respond to their suggestion with an alternative    │
│ ───────────────────────────────────────────────── │
│ Node: [h4 ▼]                                       │
│ Color: [green ▼]                                   │
│                                                    │
│ [Send RB Message]                                  │
└────────────────────────────────────────────────────┘
```

## Additional Improvements

### Algorithm for Finding Alternative Colours:

The agent now intelligently selects alternative colours by:
1. Getting the domain (available colours)
2. Eliminating the conflicting colour (their current assignment)
3. Eliminating the colour that causes conflict (your assignment)
4. Suggesting the first available alternative
5. Fallback to any different colour if no perfect match

**Example Logic:**
```
Domain: [red, green, blue]
Your h4: red (conflicts with agent's a2)
Agent's a2: red
Available alternatives: [green, blue]
Agent suggests: green (first available)
```

### Backward Compatibility:

Old "Challenge" moves from previous logs will still work:
- Protocol layer maps Challenge → CounterProposal
- Parser handles both old and new formats
- Warnings logged for legacy moves

## Common Scenarios

### Scenario 1: Boundary Conflict
```
[Turn 1]
You:   Propose h4=red
Agent: (detects conflict with a2=red)

[Turn 2]
Agent: CounterProposal h4=blue
       (Suggests blue as alternative)

[Turn 3]
You:   Commit h4=blue
       (Accept suggestion)

[Turn 4]
Agent: Commit a2=red
       (Confirms their color)

Result: ✓ No conflicts!
```

### Scenario 2: Negotiation
```
[Turn 1]
You:   Propose h4=red
Agent: CounterProposal h4=blue

[Turn 2]
You:   CounterProposal h4=green
       (Different alternative)

[Turn 3]
Agent: Commit a2=blue
       (Changes their node instead)

[Turn 4]
You:   Commit h4=red
       (Keep original)

Result: ✓ Both compromise!
```

## Troubleshooting

### Still seeing "colour=None"?
- Clear any cached Python files: `del *.pyc`
- Restart the program
- Check you're running the updated code

### Help text not appearing?
- Check console for errors
- Verify move dropdown is properly initialized
- Try selecting different moves

### Agent not making CounterProposals?
- Agent only counters when conflicts detected
- Try proposing colors that definitely conflict
- Check agent's boundary nodes overlap with yours

## Next Steps

Users should now:
1. ✓ See clear colour suggestions in CounterProposals
2. ✓ Have in-UI guidance for responding
3. ✓ Understand the 3 response options
4. ✓ Be able to resolve conflicts effectively

Enjoy smoother negotiations! 🎉
