# Conditional-Only Protocol Refactoring

## Overview

The argumentation protocol has been simplified to use **only conditional offers** throughout, making reasoning explicit and eliminating the complexity of Propose/Challenge/Justify/Commit cycles.

## New Protocol Structure

### Move Types (Only 2!)

1. **ConditionalOffer** - Core negotiation primitive
   - **Empty conditions** (unconditional): "I'll set my nodes to X"
   - **With conditions** (conditional): "If you set your nodes to X, I'll set mine to Y"

2. **Accept** - Accept an offer and commit to the chain
   - Marks an offer as accepted
   - Both parties commit to their respective sides
   - Chain dependencies are automatically resolved

### Removed Move Types

The following old move types have been **removed**:
- ❌ Propose (replaced by ConditionalOffer with empty conditions)
- ❌ Challenge (replaced by ConditionalOffer with alternative conditions)
- ❌ Justify (unnecessary - reasoning is explicit in conditions)
- ❌ Commit (replaced by Accept)
- ❌ CounterProposal (replaced by ConditionalOffer)

## Agent Behavior

### Move Generation Priority Order

1. **Accept beneficial offers** - If there's a pending offer that reduces penalty, accept it
2. **Make conditional offers for conflicts** - If conflicts exist, propose "If you do X, I'll do Y"
3. **Make unconditional offers** - Propose assignments with no conditions (equivalent to old Propose)
4. **Try optimization offers** - Even without conflicts, suggest win-win configurations
5. **Mark satisfaction** - When penalty=0 and all nodes are offered, mark as satisfied

### Offer Generation Strategy

- **Counterfactual reasoning**: Enumerate possible configurations of neighbor's nodes, find best mutual response
- **Conflict resolution**: When conflicts detected, generate conditional offer proposing resolution
- **Unconditional proposals**: For initial assignments or updates, use empty conditions
- **Win-win search**: Even without conflicts, search for zero-penalty configurations

## File Changes

### `agents/rule_based_cluster_agent.py`

#### Simplified State Variables (lines 91-101)
```python
# Removed:
# - rb_pending_attacks (no Challenge/Justify)
# - rb_dialogue_state (no phases)
# - rb_last_move (unused)

# Kept:
self.rb_commitments: Dict[str, Dict[str, Any]] = {}  # Agreed assignments
self.rb_awaiting_response: Set[str] = set()  # Who we need to respond to
self.rb_proposed_nodes: Dict[str, Dict[str, Any]] = {}  # What we've proposed
self.rb_active_offers: Dict[str, Any] = {}  # Active offers
self.rb_accepted_offers: Set[str] = set()  # Accepted offer IDs
```

#### Refactored `_generate_rb_move()` (lines 177-274)

**Old approach**: Complex phase-based state machine with 6+ move types

**New approach**: Simple priority-based system with 2 move types
1. Accept beneficial offers
2. Generate conditional offers (with or without conditions)
3. Mark satisfaction when complete

No more phases ("init", "proposing", "negotiating", "committed", "challenged")

#### Simplified `_process_rb_move()` (lines 619-684)

**Before**: 200+ lines handling 6 move types with complex state transitions

**After**: ~60 lines handling 2 move types:
- ConditionalOffer: Store and update beliefs
- Accept: Mark accepted and commit to chain

### `agents/cluster_agent.py` (Base class)

No changes needed - base class remains unchanged.

## Benefits

### 1. **Clarity**
- Every move explicitly states its reasoning (conditions → assignments)
- No implicit state transitions or phases
- Easier to understand agent reasoning

### 2. **Simplicity**
- Only 2 move types instead of 6
- No complex state machine
- Fewer edge cases and bugs

### 3. **Explicit Reasoning**
- Conditions make dependencies clear: "If h1=red AND h4=green, then a2=blue"
- Chain acceptance automatically resolves dependencies
- Counterfactual reasoning is explicit in offer structure

### 4. **Better UI**
- Conditional offers display naturally as IF-THEN statements
- Accept buttons provide clear action
- Chain dependencies visible to human

### 5. **Research Value**
- Protocol matches human intuition about negotiation
- Easier to analyze and explain in papers
- More interpretable agent behavior

## Testing Checklist

- [ ] Agents generate unconditional offers (empty conditions) for initial proposals
- [ ] Agents generate conditional offers when conflicts exist
- [ ] Agents accept beneficial offers
- [ ] Accept triggers chain commitment on both sides
- [ ] UI displays both conditional and unconditional offers
- [ ] UI Accept button works and sends Accept move
- [ ] Satisfaction detected when penalty=0 and all nodes proposed
- [ ] No references to old move types (Propose/Challenge/Justify/Commit)

## Migration Notes

### For Existing Code

If you have test code or scripts that reference old move types:

```python
# OLD (no longer works):
move = RBMove(move="Propose", node="a1", colour="red", reasons=[...])
move = RBMove(move="Commit", node="a1", colour="red", reasons=[...])

# NEW (use ConditionalOffer):
# Unconditional (equivalent to Propose):
move = RBMove(
    move="ConditionalOffer",
    offer_id="offer_123_Agent1",
    conditions=[],  # Empty = unconditional
    assignments=[Assignment(node="a1", colour="red")],
    reasons=[...]
)

# Conditional (with dependencies):
move = RBMove(
    move="ConditionalOffer",
    offer_id="offer_123_Agent1",
    conditions=[Condition(node="h1", colour="red", owner="Human")],
    assignments=[Assignment(node="a1", colour="blue")],
    reasons=[...]
)

# Accept (equivalent to Commit):
move = RBMove(move="Accept", refers_to="offer_123_Agent1", reasons=[...])
```

### For UI Code

The UI needs updating to:
1. Generate ConditionalOffers instead of Propose/Commit
2. Display Accept button for incoming offers
3. Remove Challenge/Justify UI elements

## Related Files

- `agents/rule_based_cluster_agent.py` - Agent implementation ✅ Updated
- `comm/rb_protocol.py` - Protocol definitions (check if updates needed)
- `ui/human_turn_ui.py` - UI implementation (needs updating for sending moves)
- `cluster_simulation.py` - Simulation orchestration (no changes needed)

## Next Steps

1. Update UI to generate ConditionalOffers instead of old move types
2. Test full human-agent interaction
3. Verify logs show correct protocol
4. Update any test scripts or examples
5. Document in paper/thesis
