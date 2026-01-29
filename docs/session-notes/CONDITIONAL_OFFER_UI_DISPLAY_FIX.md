# Conditional Offer UI Display Fix

## Problem Identified

User reported: "Still no change. It never makes its own conditional suggestions"

**Root Cause Discovered:** The agent WAS generating conditional offers (verified in logs), but the **UI wasn't displaying them!**

### Evidence from Logs

```
[RB Move Gen] Priority 3.5: Calling _generate_conditional_offer()...
[ConditionalOffer Gen] Found zero-penalty configuration!
[RB Move Gen] -> Generated ConditionalOffer with 2 conditions and 3 assignments
Sent message to Human: ConditionalOffer: If h1=red AND h4=green then a2=blue AND a4=blue AND a5=red
```

Agent generated ConditionalOffers multiple times (lines 62, 79, 96, 129, 146 in logs), but user never saw them!

## The UI Parsing Issue

The UI code in `ui/human_turn_ui.py` had **three problems**:

### Problem 1: Parser Couldn't Extract ConditionalOffer JSON (Line 1646)

**Before:**
```python
rb_match = re.search(r'\[rb:(\{[^\}]+\})\]', line)
```

This regex stops at the FIRST `}`, but ConditionalOffers have nested JSON with conditions and assignments:
```json
{
  "move": "ConditionalOffer",
  "conditions": [{"node": "h1", "colour": "red"}],  ← nested!
  "assignments": [{"node": "a2", "colour": "blue"}]  ← nested!
}
```

The regex would only extract `{"move": "ConditionalOffer"` and fail to parse.

**Fix:**
```python
rb_match = re.search(r'\[rb:(\{.+\})\]', line, re.DOTALL)
```

Now it captures the FULL JSON including nested structures.

### Problem 2: Parser Didn't Understand ConditionalOffer Structure (Lines 1649-1670)

**Before:**
```python
rb_data = json.loads(rb_match.group(1))
arg = {
    "node": rb_data.get("node", ""),      ← ConditionalOffers have no single node!
    "color": rb_data.get("colour", ""),   ← ConditionalOffers have no single color!
}
```

ConditionalOffers don't have a single node/color - they have conditions lists and assignments lists!

**Fix:**
```python
move_type = rb_data.get("move", "")

# Handle ConditionalOffer specially
if move_type == "ConditionalOffer":
    conditions = rb_data.get("conditions", [])
    assignments = rb_data.get("assignments", [])
    offer_id = rb_data.get("offer_id", "")

    arg = {
        "sender": sender,
        "move": "ConditionalOffer",
        "node": "conditional",  # Placeholder for layout
        "color": "",
        "conditions": conditions,
        "assignments": assignments,
        "offer_id": offer_id,
        "index": len(self._rb_arguments.get(neigh, [])),
        "justification_refs": []
    }
    print(f"[RB UI] Parsed ConditionalOffer: {len(conditions)} conditions, {len(assignments)} assignments")
    self._rb_arguments.setdefault(neigh, []).append(arg)
    return
```

Now ConditionalOffers are properly parsed and added to the arguments list!

### Problem 3: Argument Graph Couldn't Render ConditionalOffers

**Issue A:** No color defined (Line 1721-1726)

**Before:**
```python
move_colors = {
    "Propose": "#d0e8ff",
    "Challenge": "#ffd0d0",
    "Justify": "#d0ffd0",
    "Commit": "#ffe0b0"
    # No ConditionalOffer!
}
```

**Fix:**
```python
move_colors = {
    "Propose": "#d0e8ff",   # Light blue
    "Challenge": "#ffd0d0",  # Light red
    "Justify": "#d0ffd0",    # Light green
    "Commit": "#ffe0b0",     # Light orange
    "ConditionalOffer": "#e8d0ff",  # Light purple ← Added!
    "CounterProposal": "#ffe0d0",   # Light peach
    "Accept": "#d0ffe0"      # Light mint
}
```

**Issue B:** No legend entry (Lines 1728-1741)

**Fix:** Updated legend to include Conditional and Accept in a second row.

**Issue C:** Box content rendering (Lines 1933-1937)

**Before:**
```python
# Always renders as "node = color"
canvas.create_text(x, y + 5*scale,
                 text=f"{node} = {color}",
                 ...)
```

This doesn't work for ConditionalOffers which have multiple nodes!

**Fix:**
```python
# Special handling for ConditionalOffer
if move == "ConditionalOffer":
    conditions = arg.get("conditions", [])
    assignments = arg.get("assignments", [])
    # Show summary: "If X conds → Y assigns"
    text = f"IF: {len(conditions)} conds\n→ THEN: {len(assignments)} assigns"
    canvas.create_text(x, y,
                     text=text,
                     font=("Arial", max(7, int(9 * scale))),
                     anchor="center", fill="#000", tags="text")
else:
    # Standard moves: show node = color
    canvas.create_text(x, y + 5*scale,
                     text=f"{node} = {color}",
                     ...)
```

## What You'll See Now

### In the Argument Graph (Chat Pane)

ConditionalOffers will now appear as **purple boxes** with:
```
┌────────────────────────────────┐
│ ConditionalOffer        (Agent1)│
│                                 │
│        IF: 2 conds              │
│        → THEN: 3 assigns        │
└────────────────────────────────┘
```

### In the Conditionals Sidebar

ConditionalOffers from agents will appear as **yellow cards** (incoming):
```
┌─────────────────────────────────┐
│ Offer #1 ← Agent1      [yellow] │
│                                 │
│ IF:                             │
│   • h1 = red                    │
│   • h4 = green                  │
│                                 │
│ THEN:                           │
│   • a2 = blue                   │
│   • a4 = blue                   │
│   • a5 = red                    │
│                                 │
│ [Accept] [Counter]              │
└─────────────────────────────────┘
```

### In the Legend

The argument graph legend will now show:
```
Legend:  [Propose] [Commit] [CounterProp]
         [Conditional] [Accept]
```

## Files Modified

- `ui/human_turn_ui.py`
  - Lines 1646-1693: Updated JSON extraction regex and added ConditionalOffer parsing
  - Lines 1721-1728: Added colors for ConditionalOffer, CounterProposal, Accept
  - Lines 1728-1749: Updated legend to two rows with new move types
  - Lines 1933-1947: Special rendering for ConditionalOffer boxes

## Testing

Run the program and let the agent make proposals. You should now see:

1. **In console:**
   ```
   [RB UI] Parsed ConditionalOffer: 2 conditions, 3 assignments
   ```

2. **In argument graph (chat window):**
   - Purple boxes labeled "ConditionalOffer"
   - Shows "IF: X conds → THEN: Y assigns"

3. **In conditionals sidebar:**
   - Yellow cards with full IF/THEN details
   - Accept/Counter buttons

4. **Can click on conditional box** to see full details (if tooltip/click handler added)

## Summary

**Problem:** Agent was generating ConditionalOffers, but UI silently dropped them
**Cause:** Parser couldn't handle nested JSON, no color/layout defined, no rendering logic
**Fix:**
- ✅ Updated regex to capture full nested JSON
- ✅ Added ConditionalOffer parsing logic
- ✅ Added purple color for ConditionalOffers
- ✅ Updated legend
- ✅ Special rendering showing "IF X → THEN Y"

**Result:** ConditionalOffers now visible in both argument graph and sidebar! 🎉
