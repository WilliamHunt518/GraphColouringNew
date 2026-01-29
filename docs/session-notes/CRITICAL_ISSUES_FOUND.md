# CRITICAL ISSUES FOUND: Agents Can't Make Offers

## Date: 2026-01-28

## Issue #1: Agents Never Proactively Make Offers

### Symptom
When user clicks "Pass", agent steps but sends NO MESSAGES. Agent's assignments change internally but human never sees them.

### Test Evidence
```
Agent status BEFORE step(): penalty=1.000
Agent status AFTER step():  penalty=0.000
Messages sent: NONE!
```

Agent resolved the conflict internally but didn't tell anyone.

### Root Cause

**File**: `agents/rule_based_cluster_agent.py`, lines 388-419

The agent has this priority order for generating moves:

1. **Priority 1**: Evaluate pending offers from recipient (Accept/Reject)
2. **Priority 2**: Generate conditional offer IF conflicts detected
3. **Priority 4**: Generate conditional offer IF penalty > 0

**BUT both Priority 2 and Priority 4 check:**
```python
my_offers = [oid for oid in self.rb_active_offers.keys()
             if self.name in oid and oid not in self.rb_accepted_offers]
if not my_offers:  # ← ONLY generate if no pending offers
    conditional_offer = self._generate_conditional_offer(recipient)
```

**The Problem**:
- Agent sends initial config: `config_1769603352_Agent1`
- This config stays in `rb_active_offers` forever (never accepted/rejected by human)
- Agent computes new assignments (changes penalty from 1.0 → 0.0)
- Agent tries to send new offer BUT `my_offers` is not empty!
- Agent blocks itself from sending because the old config is still "pending"
- Result: Agent changes assignments internally but **NEVER TELLS HUMAN**

### Why This Is Critical

1. Human has no way to know agent changed its colors
2. Human sends offers based on outdated beliefs about agent's state
3. Agent evaluates human offers using NEW state but human doesn't know this
4. Negotiation becomes impossible - parties are operating on different realities

### The Fix

Agent needs to send a NEW ConditionalOffer whenever boundary node assignments CHANGE, regardless of pending offers. The logic should be:

```python
# Check if our boundary node assignments have changed since last proposal
boundary_changes = {node: val for node, val in changes.items() if node in boundary_nodes}

if boundary_changes:
    # We MUST announce new boundary colors even if we have pending offers
    # Otherwise the other party operates on stale information
    self.log(f"[RB Move Gen] Boundary nodes changed: {boundary_changes} - sending update")
    conditional_offer = self._generate_conditional_offer(recipient)
    if conditional_offer:
        return conditional_offer
```

This should be checked BEFORE Priorities 2 and 4.

---

## Issue #2: Agent Responses Not Visible in UI

### Symptom
When agent accepts an offer, message appears in logs but NOT in UI conditionals panel.

### Where Responses Actually Appear

**Logs show agents ARE responding:**
```
communication_log.txt:
12:10:56.451  Agent1->Human  Accept offer offer_1769602256_Human
12:11:43.543  Agent1->Human  Accept offer offer_1769602303_Human
```

**But UI doesn't show them in the conditionals panel.**

### Root Cause

**File**: `cluster_simulation.py`, line 96 in `_get_active_conditionals()`

```python
if "_Human" in offer_id:
    continue  # Skip offers made BY the human TO this agent
```

This filters out human's SENT offers, so:
- Human's sent offers never appear in conditionals panel
- Accept/Reject responses to those offers also don't appear
- Human only sees the conditionals panel for AGENT offers TO human

### Where Accept Messages DO Appear

Accept messages DO go through the pipeline:
1. Agent generates Accept move (`_generate_rb_move()`)
2. Agent sends message via `agent.send()`
3. Message added to `agent.sent_messages`
4. `on_send()` collects from `sent_messages` (cluster_simulation.py:776-784)
5. `on_send()` returns reply text
6. UI calls `add_incoming(neigh, reply)` (human_turn_ui.py:817)
7. Reply appears in **chat transcript text area**

So Accept messages ARE visible, just in the text transcript, not the conditionals panel.

### The Fix

Two options:

**Option A**: Make human's sent offers appear in conditionals panel with status updates (Pending → Accepted → Completed)

**Option B**: Add a separate "My Offers" panel showing human's sent offers and their status

**Option C**: Add visual feedback in chat transcript (color-code Accept messages, add icons, etc.)

---

## Files That Need Changes

### agents/rule_based_cluster_agent.py
Add priority level to send ConditionalOffer when boundary assignments change:

```python
def _generate_rb_move(self, recipient: str, changes: Dict[str, Any]) -> Optional[Any]:
    # ... existing code ...

    boundary_nodes = self._get_boundary_nodes_for(recipient)

    # NEW: Priority 0 - Announce boundary node changes IMMEDIATELY
    # This must happen before evaluating offers, because the other party
    # needs to know our current state to evaluate their own offers correctly
    boundary_changes = {node: val for node, val in changes.items() if node in boundary_nodes}

    if boundary_changes:
        proposed_nodes = self.rb_proposed_nodes.get(recipient, {})
        # Check if ANY boundary node has changed since last proposal
        needs_update = False
        for node in boundary_nodes:
            current_color = self.assignments.get(node)
            proposed_color = proposed_nodes.get(node)
            if current_color != proposed_color:
                needs_update = True
                break

        if needs_update:
            self.log(f"[RB Move Gen] Priority 0: Boundary assignments changed, sending update")
            conditional_offer = self._generate_conditional_offer(recipient)
            if conditional_offer:
                self.log(f"[RB Move Gen] -> Sending boundary update ConditionalOffer")
                return conditional_offer

    # Priority 1: Evaluate pending offers (existing code)
    # ... rest of existing code ...
```

### cluster_simulation.py (Optional - depends on chosen fix)
If implementing Option A, modify `_get_active_conditionals()` to include human offers with status tracking.

### ui/human_turn_ui.py (Optional - depends on chosen fix)
If implementing Option B or C, add visual feedback for offer status in UI.

---

## Testing Commands

```bash
# Run RB mode
python launch_menu.py
# Select RB mode, run experiment
# Click "Pass" button
# Expected: Agent sends ConditionalOffer with current boundary colors
```

## Success Criteria

✅ When agent changes boundary assignments and user clicks "Pass", agent sends ConditionalOffer
✅ ConditionalOffer includes agent's current boundary node assignments
✅ Human can see agent's current state before sending offers
✅ Accept/Reject messages visible to human (in transcript or conditionals panel)
✅ Back-and-forth negotiation works: offer → counter → accept

---

## Priority

**BLOCKING** - Without fixing Issue #1, agents literally cannot participate in negotiation. They become passive accepters/rejecters only.
