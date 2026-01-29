# Conditional Builder UI Guide

## Overview

The conditional builder allows humans to create complex conditional proposals in RB mode using a visual interface.

## How It Works

### 1. Select "ConditionalOffer" Move Type

When you select "ConditionalOffer" from the move type dropdown, the conditional builder UI appears with two sections:

- **IF (conditions)**: Select from previous statements made by the agent
- **THEN (my commitments)**: Specify what nodes you'll assign to what colors

### 2. Building Conditions (IF part)

**What are conditions?**
Conditions reference proposals/assignments that the agent has already made. You're saying "IF you do what you said..."

**How to add conditions:**
1. Click "+ Add Condition"
2. A dropdown appears with previous statements from the agent
3. Select a statement like "#3: h1=red (Propose)"
4. This means "IF you assign h1=red"
5. Add multiple conditions to create "AND" logic
6. Click "✗" to remove a condition

**Example conditions:**
- "IF h1=red" (one condition)
- "IF h1=red AND h4=green" (two conditions)
- "IF h1=red AND h4=green AND h2=blue" (three conditions)

### 3. Building Assignments (THEN part)

**What are assignments?**
Assignments are your commitments - what nodes YOU will assign to what colors.

**How to add assignments:**
1. Click "+ Add Assignment"
2. Select a node you control from the dropdown
3. Select a color from the dropdown
4. Add multiple assignments to commit to multiple nodes
5. Click "✗" to remove an assignment

**Example assignments:**
- "THEN a2=blue" (one assignment)
- "THEN a2=blue AND a3=yellow" (two assignments)
- "THEN a2=blue AND a3=yellow AND a5=green" (three assignments)

### 4. Sending the Conditional Offer

Once you've added at least one condition and one assignment:
1. Click "Send RB Message"
2. The system builds a ConditionalOffer like:
   ```
   ConditionalOffer: If h1=red AND h4=green then a2=blue AND a3=yellow
   ```
3. The offer appears in the conditionals sidebar for the agent to see

### 5. Accepting Offers

When an agent sends you a conditional offer:

1. The offer appears in the **conditionals sidebar** (right panel)
2. Each offer is shown as a card with:
   - Offer ID and sender
   - IF section (conditions you must meet)
   - THEN section (what they'll do)
   - Accept/Counter buttons

**To accept an offer:**
- **Option 1**: Click "Accept" button on the conditional card in the sidebar
- **Option 2**: Select "Accept" from move type dropdown, choose the offer, click "Send RB Message"

## Example Workflow

### Scenario: Negotiating boundary node colors

**Initial State:**
- You control nodes: h1, h2, h3, h4
- Agent controls nodes: a1, a2, a3, a4
- Boundary conflicts at h1-a2 and h4-a3

**Turn 1: Agent proposes**
```
Agent1 → You: Propose a2=blue
Agent1 → You: Propose a3=yellow
```

**Turn 2: You make a conditional offer**
1. Select move type: "ConditionalOffer"
2. Add conditions:
   - Click "+ Add Condition"
   - Select "#1: a2=blue (Propose)"
   - Click "+ Add Condition"
   - Select "#2: a3=yellow (Propose)"
3. Add assignments:
   - Click "+ Add Assignment"
   - Select node: h1, color: red
   - Click "+ Add Assignment"
   - Select node: h4, color: green
4. Click "Send RB Message"

**Result:**
```
You → Agent1: ConditionalOffer: If a2=blue AND a3=yellow then h1=red AND h4=green
```

**Turn 3: Agent accepts**
```
Agent1 → You: Accept offer offer_1234567_Human
```

**Turn 4: Both commit**
```
Agent1 → You: Commit a2=blue
Agent1 → You: Commit a3=yellow
You → Agent1: Commit h1=red
You → Agent1: Commit h4=green
```

## UI Elements

### Move Type Dropdown
```
[Propose ▼]
 - Propose
 - ConditionalOffer      ← Select this!
 - CounterProposal
 - Accept
 - Commit
```

### Conditional Builder (when ConditionalOffer selected)
```
┌─ Conditional Offer Builder ───────────────────────┐
│                                                    │
│ IF (conditions):                                   │
│   [(select statement) ▼]  [✗]                     │
│   [+ Add Condition]                                │
│                                                    │
│ THEN (my commitments):                             │
│   Node: [h1 ▼] = [red ▼]  [✗]                     │
│   [+ Add Assignment]                               │
│                                                    │
└────────────────────────────────────────────────────┘
```

### Accept Frame (when Accept selected)
```
┌─ Accept Offer ─────────────────────────────────────┐
│                                                     │
│ Select offer to accept:                             │
│ [offer_1234567: If h1=red... ▼]                    │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Conditionals Sidebar (always visible)
```
┌─ Active Conditionals ──────────────────────────────┐
│                                                     │
│ ┌─────────────────────────────────────────────┐   │
│ │ Offer #1 from Agent1                        │   │
│ │                                             │   │
│ │ IF:                                         │   │
│ │   • h1 = red                                │   │
│ │   • h4 = green                              │   │
│ │                                             │   │
│ │ THEN:                                       │   │
│ │   • a2 = blue                               │   │
│ │   • a3 = yellow                             │   │
│ │                                             │   │
│ │ [Accept] [Counter]                          │   │
│ └─────────────────────────────────────────────┘   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Technical Details

### Wire Format

When you send a ConditionalOffer, it's encoded as:

```json
{
  "move": "ConditionalOffer",
  "offer_id": "offer_1643234567_Human",
  "conditions": [
    {"node": "a2", "colour": "blue", "owner": "Agent1"},
    {"node": "a3", "colour": "yellow", "owner": "Agent1"}
  ],
  "assignments": [
    {"node": "h1", "colour": "red"},
    {"node": "h4", "colour": "green"}
  ],
  "reasons": ["human_proposed"]
}
```

### Statement Tracking

The UI tracks all previous RB moves in `self._rb_arguments` per neighbor:
```python
{
  "Agent1": [
    {"sender": "Agent1", "move": "Propose", "node": "a2", "color": "blue"},
    {"sender": "Agent1", "move": "Propose", "node": "a3", "color": "yellow"},
    {"sender": "Human", "move": "ConditionalOffer", ...},
  ]
}
```

This allows the condition dropdown to show only relevant statements from that specific neighbor.

## Tips

1. **Start simple**: Begin with one condition and one assignment
2. **Reference recent proposals**: The condition dropdown shows recent statements - pick the most relevant ones
3. **Use sidebar for acceptance**: Clicking Accept on the sidebar card is faster than using the dropdown
4. **Build incrementally**: Add one row at a time, check it looks right, then add more
5. **Remove mistakes**: Use the ✗ button to remove rows if you made a mistake

## Limitations

1. **No custom text**: Conditions must reference previous statements - you can't type arbitrary conditions
2. **Node ownership**: You can only assign your own nodes in the THEN section
3. **No OR logic**: Conditions are always ANDed together (all must be true)
4. **No negation**: You can't say "IF NOT h1=red"

## Future Enhancements

- Counter-proposal builder (build alternative offers)
- Offer revision (modify existing offers)
- Visual preview of what the graph will look like if accepted
- Offer expiration indicators
- Partial acceptance (accept some conditions but not all)
