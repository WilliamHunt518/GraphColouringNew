# UI Simplification and Conditional Offer Granularity

## Changes Made

### Issue 1: Agent Makes Large Conditional Offers (FIXED)

**Problem**: Agent was making one big conditional offer with all boundary nodes at once, making it inflexible.

**Solution**:
- **Unconditional offers (Priority 3)**: Agent now generates **ONE offer per node** instead of bundling all nodes together
  - Before: `ConditionalOffer: IF [] THEN a1=red AND a2=blue AND a3=green`
  - After: `ConditionalOffer: IF [] THEN a1=red` (separate offers for each node)

- **Conditional offers (Priority 2/4)**: Still generates complete solutions for optimization, but human can select individual assignments as conditions in the UI

**Benefits**:
- Human can pick and choose which assignments to use as conditions
- More flexible negotiation
- Easier to understand individual commitments
- Agent still finds optimal complete solutions when needed

### Issue 2: UI Button Bug (FIXED)

**Problem**: Clicking "Add Assignment" in Agent A's panel was adding rows to Agent B's panel.

**Root Cause**: Lambda functions in button commands weren't capturing the loop variable correctly. The `assignments_container` reference was being captured from closure, pointing to the last iteration's value.

**Solution**: Updated function signatures to capture both the neighbor ID and container at definition time:
```python
# Before:
def add_assignment_row(n=neigh):
    row_frame = ttk.Frame(assignments_container)  # Wrong container!

# After:
def add_assignment_row(n=neigh, container=assignments_container):
    row_frame = ttk.Frame(container)  # Correct container captured at definition
```

Applied same fix to `add_condition_row()`.

### Issue 3: UI Simplification (DONE)

**Removed**:
- ❌ Move type dropdown (Propose, Challenge, Justify, Commit, CounterProposal, Accept)
- ❌ Node dropdown (for single-node moves)
- ❌ Color dropdown (for single-node moves)
- ❌ Justification selector
- ❌ Old move handling logic in `send_rb_message()`

**Kept** (simplified):
- ✅ Conditional offer builder (IF/THEN structure)
- ✅ Condition rows (select from agent's statements)
- ✅ Assignment rows (specify your commitments)
- ✅ "Send Offer" button
- ✅ "Pass" button

**New UI Structure**:
```
┌─────────────────────────────────────────┐
│ Make Offer to Agent1                    │
├─────────────────────────────────────────┤
│ Build conditional offers: 'If they do X,│
│ I'll do Y' (or leave conditions empty   │
│ for unconditional)                      │
├─────────────────────────────────────────┤
│ IF (conditions):                        │
│   [Select from agent's statements]      │
│   + Add Condition                       │
│                                         │
│ THEN (my commitments):                  │
│   Node: h1  = red       [✗]            │
│   + Add Assignment                      │
│                                         │
│ [Pass] [Send Offer]                     │
└─────────────────────────────────────────┘
```

## Agent Behavior Changes

### Unconditional Offers (One per Node)

```python
# Turn 1: Agent offers a1=red
ConditionalOffer: IF [] THEN a1=red

# Turn 2: Agent offers a2=blue
ConditionalOffer: IF [] THEN a2=blue

# Turn 3: Agent offers a3=green
ConditionalOffer: IF [] THEN a3=green
```

### Human Can Select Granularly

Human can now select individual assignments as conditions:
```
IF a1=red THEN h1=blue
IF a1=red AND a2=blue THEN h1=blue AND h2=green
IF a1=red THEN h1=blue
```

Each assignment from the agent appears as a selectable option in the condition dropdown.

### Conditional Offers (Complete Solutions)

When conflicts exist or optimization is needed, agent still generates complete win-win configurations:
```
ConditionalOffer: IF h1=red AND h4=green THEN a2=blue AND a5=yellow
```

This finds zero-penalty solutions through counterfactual reasoning.

## Files Modified

1. **`ui/human_turn_ui.py`** (lines 566-868)
   - Removed move type dropdown and old single-node UI
   - Fixed button closure bug by capturing container in function parameters
   - Simplified `send_rb_message()` to only handle ConditionalOffer
   - Updated button label to "Send Offer"
   - Updated condition parser to handle both single assignments and conditional offers
   - Changed help text to explain IF/THEN structure

2. **`agents/rule_based_cluster_agent.py`** (lines 281-299)
   - Changed Priority 3 to generate ONE offer per node instead of bundling
   - Kept conditional offer generation for complete solutions (Priority 2/4)

## Testing Checklist

- [ ] Agents generate unconditional offers one node at a time
- [ ] Each agent assignment appears separately in human's condition dropdown
- [ ] Adding assignments in Agent1's panel adds to Agent1 (not Agent2)
- [ ] Adding conditions in Agent1's panel adds to Agent1 (not Agent2)
- [ ] Can send unconditional offer (empty conditions, just assignments)
- [ ] Can send conditional offer (with conditions selected from agent's statements)
- [ ] Agent still generates conditional offers for conflict resolution
- [ ] UI shows simplified structure without old move types

## Example Interaction

**Agent1 (Turn 1)**:
```
ConditionalOffer: a1=red
```
(Appears in Human's condition dropdown as: "#1: a1=red")

**Agent1 (Turn 2)**:
```
ConditionalOffer: a2=blue
```
(Appears in Human's condition dropdown as: "#2: a2=blue")

**Human**:
```
IF a1=red THEN h1=green
```
(Selects "#1: a1=red" from dropdown, adds h1=green assignment)

**Agent1 (Accept)**:
```
Accept offer_123_Human
```
(Both sides committed: a1=red ↔ h1=green chain)

## Benefits

1. **Granular Selection**: Human can select any subset of agent's assignments as conditions
2. **Clearer UI**: Single clear workflow (build conditional offer → send)
3. **Fixed Bugs**: Button wiring now correct per agent
4. **Flexible Negotiation**: Can build simple or complex conditional chains
5. **Agent Clarity**: Each agent statement is a separate, understandable offer
