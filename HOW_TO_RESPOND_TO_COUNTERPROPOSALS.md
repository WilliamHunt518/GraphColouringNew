# How to Respond to CounterProposals

## What is a CounterProposal?

A **CounterProposal** is when the agent suggests a different color for a node, usually because there's a conflict.

### Example:
```
You: Propose h4=red
Agent: CounterProposal h4=blue (instead of h4=red)
       Reason: conflicts with my a2=red
```

The agent is saying: "Instead of h4=red, how about h4=blue? Because my node a2 is already red and it conflicts."

## How to Respond

You have 3 options:

### Option 1: Accept the CounterProposal (Easiest)

**If you agree with their suggestion:**

1. Select move type: **"Commit"**
2. Select the node they suggested (e.g., h4)
3. Select the color they suggested (e.g., blue)
4. Click "Send RB Message"

This says: "OK, I'll do what you suggested"

### Option 2: Make Your Own CounterProposal

**If you have a different idea:**

1. Select move type: **"CounterProposal"**
2. Select the node in question (e.g., h4)
3. Select a different color (e.g., green)
4. Click "Send RB Message"

This says: "How about this instead?"

### Option 3: Explain Why You Can't Change

**If your color is fixed or you have a good reason:**

1. Click on the graph to change the node to a different color (if possible)
2. OR select move type: **"Propose"**
3. Select your node
4. Select your preferred color
5. Add a justification from the dropdown (if available)
6. Click "Send RB Message"

This says: "I need to keep it this way because..."

## Visual Example Workflow

```
┌─────────────────────────────────────────────────────┐
│ SCENARIO: You both want red on adjacent nodes      │
└─────────────────────────────────────────────────────┘

You:    h4 = red  ──conflicts with──  a2 = red  :Agent

Agent sends: CounterProposal h4=blue

┌─────────────────────────────────────────────────────┐
│ Your Options:                                       │
├─────────────────────────────────────────────────────┤
│                                                     │
│ ✓ ACCEPT IT                                         │
│   Move: Commit                                      │
│   Node: h4                                          │
│   Color: blue                                       │
│   → "OK, I'll make h4 blue"                         │
│                                                     │
│ ✓ COUNTER IT                                        │
│   Move: CounterProposal                             │
│   Node: h4                                          │
│   Color: green                                      │
│   → "How about h4=green instead?"                   │
│                                                     │
│ ✓ HOLD FIRM                                         │
│   Move: Propose                                     │
│   Node: h4                                          │
│   Color: red                                        │
│   → "I really need h4=red"                          │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## What Happens After You Respond?

### If you Commit:
- Your node changes to the suggested color
- The conflict is resolved
- Agent might Commit their node too
- Everyone's happy! ✓

### If you CounterProposal:
- Agent considers your alternative
- They might:
  - Accept your counter (Commit to it)
  - Make another counter
  - Propose something for their node instead

### If you Propose the same thing:
- Agent realizes you're holding firm
- They might:
  - Change their node instead
  - Make another CounterProposal
  - Try a ConditionalOffer

## Common Patterns

### Pattern 1: Quick Agreement
```
Agent: CounterProposal h4=blue
You:   Commit h4=blue
Agent: Commit a2=red
✓ Done in 2 moves!
```

### Pattern 2: Negotiation
```
Agent: CounterProposal h4=blue
You:   CounterProposal h4=green
Agent: Commit a2=blue (changes their node instead)
You:   Commit h4=red (keep yours)
✓ Both compromise
```

### Pattern 3: Conditional Deal
```
Agent: CounterProposal h4=blue
You:   ConditionalOffer: If a2=blue then h4=red
Agent: Accept offer
✓ Complex deal reached
```

## Tips

1. **Check the graph** - Look at which nodes are adjacent and what colors conflict
2. **Read the reason** - The agent explains why they're suggesting the change
3. **Consider their proposal** - Often their suggestion resolves the conflict
4. **Don't feel pressured** - You can always make a counter-counter-proposal
5. **Use conditionals** - For complex situations, build a conditional offer

## UI Quick Reference

### To Accept a CounterProposal:
```
┌─ Send RB Message ───────────────┐
│ Move: [Commit ▼]                │
│ Node: [h4    ▼]  ← Their node   │
│ Color: [blue  ▼]  ← Their color │
│                                 │
│ [Send RB Message]               │
└─────────────────────────────────┘
```

### To Counter a CounterProposal:
```
┌─ Send RB Message ───────────────┐
│ Move: [CounterProposal ▼]       │
│ Node: [h4    ▼]  ← Same node    │
│ Color: [green ▼]  ← Your color  │
│                                 │
│ [Send RB Message]               │
└─────────────────────────────────┘
```

## What NOT to Do

❌ **Don't ignore it** - The agent expects a response
❌ **Don't repeat your original proposal** without explaining why
❌ **Don't change unrelated nodes** - Stay on topic
❌ **Don't commit to the wrong color** - Make sure you select what they suggested

## Still Confused?

Remember: A CounterProposal is just a suggestion!

- Think of it like negotiating: "What if we try this instead?"
- You're not forced to accept it
- The goal is to find colors that don't conflict
- Communication helps you both find a solution

## Real Example from a Run

```
[Iteration 1]
Human: Propose h4=red

[Iteration 2]
Agent1: CounterProposal h4=blue
        Reason: your_h4_conflicts_with_my_a2

[Iteration 3]
Human: Commit h4=blue
       (Accepts the suggestion)

[Iteration 4]
Agent1: Commit a2=red
        (Confirms their color)

Result: No conflicts! h4=blue, a2=red ✓
```
