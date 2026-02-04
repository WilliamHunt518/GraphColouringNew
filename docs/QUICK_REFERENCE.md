# Quick Reference: New Features

## For Users

### How to Check Feasibility (Phase 2)
1. Open conditional builder for an agent
2. Add conditions using "+ Add Condition" button
3. Click **"Check Feasibility"** button
4. Wait for agent response
5. Check result in conditionals sidebar:
   - ✓ Green = Feasible (shows penalty)
   - ✗ Red = Not feasible
6. Click "Dismiss" to remove query card

**Use case**: Test if agent can work with `h2=red AND h5=blue` before committing to a full offer.

### How to Mark Impossible Conditions (Phase 3)
1. Receive conditional offer from agent
2. Click **"Reject"** button
3. In dialog, you can mark:

   **Individual conditions** (NEVER acceptable):
   - ☑ Check any condition that's impossible by itself
   - Example: Check "h1=red" if h1 can NEVER be red

   **Combinations** (only impossible together):
   - Select 2+ conditions from dropdowns
   - Click "✓ Add to List"
   - Example: h4=green + h7=blue together impossible, but each OK separately
   - Use "✗ Remove" to remove from list

4. Click **"Reject Offer"**
5. Agent remembers constraints for future offers

**Use case**: Tell agent "h1=red is impossible" OR "h1=red AND h4=green together don't work, but each alone is OK"

---

## For Developers

### Code Locations

#### Feasibility Query
- **Protocol**: `comm/rb_protocol.py` lines 41, 100-104, 128-133, 242-247, 352-366
- **Agent**: `agents/rule_based_cluster_agent.py` lines 1150-1228
- **UI Button**: `ui/human_turn_ui.py` lines 878-973, 1013-1015
- **UI Cards**: `ui/human_turn_ui.py` lines 1455-1533
- **Response Processing**: `ui/human_turn_ui.py` lines 2719-2731

#### Enhanced Rejection
- **Protocol**: `comm/rb_protocol.py` lines 98-99, 125-126, 230-244, 351-358
- **Agent Storage**: `agents/rule_based_cluster_agent.py` line 100
- **Agent Processing**: `agents/rule_based_cluster_agent.py` lines 1300-1324
- **Agent Filtering**: `agents/rule_based_cluster_agent.py` lines 772-797
- **UI Dialog**: `ui/human_turn_ui.py` lines 1550-1768

### Data Structures

#### Feasibility Query (UI)
```python
self._feasibility_queries: Dict[str, List[Dict[str, Any]]] = {}
# {neighbor: [{query_id, conditions, is_feasible, penalty, details}, ...]}
```

#### Impossible Combinations (Agent)
```python
self.rb_impossible_combinations: Dict[str, Set[FrozenSet[Tuple[str, str]]]] = {}
# {recipient: {frozenset({(node1, color1), (node2, color2)}), ...}}
```

### Protocol Messages

#### FeasibilityQuery
```json
{
  "move": "FeasibilityQuery",
  "query_id": "query_1234567890_Human_Agent1",
  "conditions": [
    {"node": "h2", "colour": "red", "owner": "Agent1"},
    {"node": "h5", "colour": "blue", "owner": "Agent1"}
  ],
  "reasons": ["feasibility_check"]
}
```

#### FeasibilityResponse
```json
{
  "move": "FeasibilityResponse",
  "refers_to": "query_1234567890_Human_Agent1",
  "is_feasible": true,
  "feasibility_penalty": 5.0,
  "feasibility_details": "Workable with penalty=5.0",
  "reasons": ["feasibility_evaluation"]
}
```

#### Reject with Combinations
```json
{
  "move": "Reject",
  "refers_to": "offer_xyz",
  "impossible_conditions": [
    {"node": "h1", "colour": "red"}
  ],
  "impossible_combinations": [
    [
      {"node": "h4", "colour": "green"},
      {"node": "h7", "colour": "blue"}
    ]
  ],
  "reasons": ["human_rejected", "unacceptable_terms"]
}
```

### Testing Commands

```bash
# Start RB mode
python launch_menu.py
# Select: RB mode, default graph

# Manual test script (create this)
python test_new_features.py
```

### Debug Logging

Look for these log messages:

**Feasibility Query:**
```
[RB Process] Received feasibility query from Human
[RB Feasibility] Evaluating with h2=red
[RB Feasibility] Result: feasible=True, penalty=5.0
[RB Feasibility] Sent response to Human
```

**Enhanced Rejection:**
```
[RB Process] Stored IMPOSSIBLE condition from Human: h1=red
[RB Process] Stored impossible COMBINATION: (h4=green AND h7=blue)
[RB Process] Total combinations from Human: 1
[ConditionalOffer Gen] Filtered 15 configs with impossible combos
```

---

## Common Issues

### Query not working
- Check: At least 1 condition added
- Check: Agent supports FeasibilityQuery (RB mode)
- Check: `_on_send` callback registered

### Rejection dialog issues
- Check: Offer has conditions (dialog needs conditions)
- Check: 2+ conditions required for combinations section
- Check: Click "Add to List" after selecting conditions

### Agent not respecting constraints
- Check: Phase didn't transition (clears constraints)
- Check: Correct recipient (constraints are per-agent)
- Check: Filtering logic in `_generate_conditional_offer()`

---

## Performance Notes

- Feasibility queries use exhaustive search for boundaries ≤3 nodes
- Large boundaries (>3) use current assignment only
- Combination filtering uses efficient `frozenset.issubset()`
- Queries don't block agent's normal deliberation

---

## Backward Compatibility

- Old protocol messages still work (no breaking changes)
- New fields optional in RBMove dataclass
- Agents without query handler ignore FeasibilityQuery
- UI gracefully handles missing feasibility response

---

## Next Steps

1. Test all features with real graphs
2. Gather user feedback on UI/UX
3. Consider enhancements:
   - Query history persistence
   - Batch queries
   - Agent explains why infeasible
   - Auto-suggest queries

---

## Files to Read

- `IMPLEMENTATION_COMPLETE_ALL_PHASES.md` - Full implementation details
- `FEATURE_SUMMARY.txt` - Visual summary
- `PHASE_1_2_COMPLETE.md` - Phases 1-2 only
