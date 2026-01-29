# Marking Impossible Conditions - User Guide

## What is This Feature?

When an agent proposes a conditional offer like "IF h4=green AND h5=red THEN...", you can now tell the agent that specific conditions (like h4=green) are **impossible** for you to satisfy. The agent will remember this and never propose that condition again in ANY combination.

## How It Works

### Before This Feature

- Agent: "IF h4=green AND h5=red THEN I'll do X"
- You: Reject
- Agent: "IF h4=green AND h5=blue THEN I'll do Y" (tries different h5 color)
- You: Reject again
- Agent: "IF h4=green AND h5=yellow THEN I'll do Z" (still trying h4=green!)
- **Problem**: Agent doesn't know h4=green is the issue

### With This Feature

- Agent: "IF h4=green AND h5=red THEN I'll do X"
- You: Reject + mark h4=green as impossible
- Agent: "IF h4=red AND h5=blue THEN I'll do Y" (different h4 color!)
- **Result**: Faster convergence, no wasted rounds

## Using the Dialog

### Step 1: Agent Makes an Offer

You'll see a card showing the agent's conditional offer:
```
┌─────────────────────────────────────┐
│ ConditionalOffer from Agent1        │
│                                     │
│ IF h4=green AND h5=red             │
│ THEN a2=blue AND a3=yellow         │
│                                     │
│ [Accept] [Reject] [Counter]        │
└─────────────────────────────────────┘
```

### Step 2: Click "Reject"

A dialog window appears:
```
┌─────────────────────────────────────┐
│ Reject Offer from Agent1            │
├─────────────────────────────────────┤
│                                     │
│ Which conditions are IMPOSSIBLE     │
│ for you?                            │
│                                     │
│ Select conditions that you can      │
│ NEVER satisfy. The agent will avoid │
│ future offers containing these.     │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ Conditions in this offer:       │ │
│ │                                 │ │
│ │ ☐ h4 = green                    │ │
│ │ ☐ h5 = red                      │ │
│ │                                 │ │
│ └─────────────────────────────────┘ │
│                                     │
│      [Reject Offer]  [Cancel]       │
└─────────────────────────────────────┘
```

### Step 3: Select Impossible Conditions

Check the boxes for conditions you can NEVER satisfy:
- Check h4=green if "h4 cannot be green in any situation"
- Check h5=red if "h5 cannot be red in any situation"
- Check both if both are impossible
- Check neither if you just don't like this particular combination

### Step 4: Confirm or Cancel

- **Click "Reject Offer"**: Send rejection with marked conditions
- **Click "Cancel"**: Go back without rejecting (offer stays pending)

## When to Mark Conditions as Impossible

### Good Reasons to Mark

✓ **Local constraint**: "h4 cannot be green because it conflicts with h1"
✓ **Resource limit**: "h5 cannot be red because I'm out of red tokens"
✓ **Hard requirement**: "h4 must be blue (pre-fixed), so green is impossible"
✓ **Certain knowledge**: "I know for sure this will never work"

### Bad Reasons to Mark

✗ **Current state**: "h4 is red right now" (you might change it later)
✗ **Preference**: "I prefer h4 to be blue" (preference ≠ impossible)
✗ **Uncertainty**: "I'm not sure if h4=green works" (try it first)
✗ **Temporary**: "h4 can't be green for the next 2 rounds" (not permanent)

## Examples

### Example 1: Fixed Node

**Scenario**: h1 is pre-fixed to red. h4 is adjacent to h1.

**Agent offers**: "IF h4=red THEN..."

**What to do**:
1. Click "Reject"
2. Check ☑ h4=red
3. Click "Reject Offer"

**Why**: h4 can never be red (conflicts with adjacent h1=red). Agent will never propose h4=red again.

### Example 2: Multiple Impossible Conditions

**Scenario**: h4 and h5 are both adjacent to a pre-fixed blue node.

**Agent offers**: "IF h4=blue AND h5=blue THEN..."

**What to do**:
1. Click "Reject"
2. Check ☑ h4=blue
3. Check ☑ h5=blue
4. Click "Reject Offer"

**Why**: Both conditions are impossible. Mark both so agent knows immediately.

### Example 3: Just Don't Like This Combination

**Scenario**: Agent offers "IF h4=green AND h5=red THEN...". You want to try h4=red AND h5=green instead.

**What to do**:
1. Click "Reject"
2. Don't check anything
3. Click "Reject Offer"

**Why**: Individual conditions aren't impossible, you just don't like this specific pairing. Agent will remember this combination is rejected but can still propose h4=green with different h5 colors.

### Example 4: Changed Your Mind

**Scenario**: You accidentally clicked "Reject" but want to keep the offer pending.

**What to do**:
1. Click "Cancel" in the dialog

**Result**: Offer stays in "Pending" state, no message sent.

## Tips

1. **Be honest**: Only mark conditions that are truly impossible. False marking wastes search space.

2. **Be specific**: If only h4=green is problematic, don't mark h5=red too.

3. **Use sparingly**: Marking many conditions makes it harder for agents to find solutions.

4. **Check logs**: See what conditions are marked impossible in `results/rb/Agent1_log.txt`:
   ```
   [RB Process] Stored IMPOSSIBLE condition from Human: h4=green
   ```

5. **It's permanent**: Once marked impossible, agents never propose it again (for this session).

## Troubleshooting

### "Agent stopped making offers"

**Possible cause**: Too many conditions marked impossible.

**Check logs**:
```bash
grep "All configurations contain impossible conditions" results/rb/Agent1_log.txt
```

**Solution**: Restart experiment, mark fewer conditions.

### "Agent keeps proposing same thing"

**Possible cause**: You rejected but didn't mark conditions.

**Solution**: Next time, check the specific impossible conditions in the dialog.

### "Dialog doesn't show conditions"

**Possible cause**: Agent sent unconditional status update (no conditions to mark).

**Expected**: Status updates don't have a "Reject" button.

## Summary

- Mark conditions you can **NEVER** satisfy
- Agent remembers forever (this session)
- Agent filters ALL future offers containing marked conditions
- Helps agent converge faster
- Optional - backward compatible with simple rejection
