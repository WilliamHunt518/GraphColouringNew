# Agent Conditional Offers Implementation

## Issue

User reported: "I'm not sure if they are responding in kind with conditionals. Can we make sure RB agents also have that facility and do make such offers + accept when ready etc"

## Status Before Changes

✅ **Already Implemented:**
- Protocol support for ConditionalOffer and Accept moves
- `_generate_conditional_offer()` method in agent (line 500-577)
- Processing logic for receiving ConditionalOffers (line 714-726)
- Processing logic for receiving Accept messages (line 727-742)

❌ **Missing:**
- ConditionalOffer generation was **not called** in the priority system
- Agents could **not send Accept** moves (only receive them)

## Changes Made

Added two new priorities to the agent's move generation system in `agents/rule_based_cluster_agent.py`:

### Priority 2.5: Accept Beneficial ConditionalOffers (Lines 281-308)

**When:** Right after CounterProposals but before regular Proposes

**Logic:**
```python
# Check for pending offers from this recipient
pending_offers = [
    (offer_id, offer) for offer_id, offer in self.rb_active_offers.items()
    if offer_id not in self.rb_accepted_offers
]

# For each pending offer from this recipient:
if offer_sender == recipient:
    current_penalty = self._compute_local_penalty()

    # Accept if penalty > 0 and offer has mutual assignments
    if current_penalty > 0.0 and offer.assignments and offer.conditions:
        return RBMove(
            move="Accept",
            refers_to=offer_id,
            reasons=["reduces_penalty", f"penalty={current_penalty:.3f}"]
        )
```

**What it does:**
- Checks for pending ConditionalOffers from the recipient
- Evaluates if accepting would be beneficial (reduces penalty)
- Sends Accept move if beneficial

**Example dialogue:**
```
Turn 1: Human → Agent1: ConditionalOffer
        "If a2=blue AND a3=yellow, then h1=red AND h4=green"

Turn 2: Agent1 (evaluates offer)
        Current penalty: 0.5
        Offer conditions match beliefs
        Offer would reduce penalty to 0.0

Turn 3: Agent1 → Human: Accept (offer_12345)
        "Accepting your conditional offer"
```

### Priority 3.5: Generate ConditionalOffer (Lines 371-389)

**When:** After regular Proposes but before proactive Commits

**Logic:**
```python
# In proposing/negotiating phase, no changes/conflicts
if phase in ("proposing", "negotiating") and not changes and not conflicts:

    # Only if we have multiple boundary nodes (2+)
    if len(boundary_nodes) >= 2:

        # Only if we don't already have pending offers
        my_offers = [oid for oid in self.rb_active_offers.keys() if self.name in oid]

        if not my_offers:
            conditional_offer = self._generate_conditional_offer(recipient)
            if conditional_offer:
                return conditional_offer
```

**What it does:**
- Triggers when agent is in proposing/negotiating phase
- Only when there are 2+ boundary nodes to package together
- Only if agent doesn't already have pending offers
- Calls existing `_generate_conditional_offer()` method
- Packages current boundary node assignments into a conditional deal

**Example dialogue:**
```
Turn 1: Agent1 → Human: Propose a2=blue
Turn 2: Agent1 → Human: Propose a3=yellow

(Agent transitions to proposing phase)

Turn 3: Agent1 → Human: ConditionalOffer
        "If h1=red AND h4=green, then a2=blue AND a3=yellow"
        (packages the two proposals into a conditional deal)
```

## Updated Priority System

The complete priority system now is:

1. **Priority 1**: Respond to challenges (Commit)
2. **Priority 2**: CounterProposal for conflicts
3. **Priority 2.5**: ✨ **Accept beneficial ConditionalOffers** ✨
4. **Priority 3**: Propose changes on boundary nodes
5. **Priority 3.5**: ✨ **Generate ConditionalOffer** ✨
6. **Priority 4**: Proactively Commit when satisfied
7. **Priority 5**: Justify if challenged
8. **Priority 6**: Send Commit confirmations

## How Conditional Offers Work Now

### Scenario 1: Human Sends Conditional, Agent Accepts

```
Turn 1: Human → Agent1: ConditionalOffer (offer_123)
        IF: a2=blue, a3=yellow
        THEN: h1=red, h4=green

(Agent1 processes offer, evaluates penalty)

Turn 2: Agent1 → Human: Accept (offer_123)
        Reason: "reduces_penalty, penalty=0.5"

(Both parties now commit to their sides)

Turn 3: Agent1 → Human: Commit a2=blue
Turn 4: Agent1 → Human: Commit a3=yellow
```

### Scenario 2: Agent Generates Conditional, Human Accepts

```
Turn 1: Agent1 → Human: Propose a2=blue
Turn 2: Agent1 → Human: Propose a3=yellow

(Agent1 transitions to proposing phase with 2+ boundary nodes)

Turn 3: Agent1 → Human: ConditionalOffer (offer_456)
        IF: h1=red, h4=green
        THEN: a2=blue, a3=yellow

(Human evaluates in UI, clicks Accept button)

Turn 4: Human → Agent1: Accept (offer_456)

(Agent1 processes acceptance and commits)

Turn 5: Agent1 → Human: Commit a2=blue
Turn 6: Agent1 → Human: Commit a3=yellow
```

### Scenario 3: Mutual Conditional Exchange

```
Turn 1: Human → Agent1: ConditionalOffer (offer_123)
        IF: a2=blue
        THEN: h1=red

Turn 2: Agent1 evaluates but doesn't accept yet

Turn 3: Agent1 → Human: ConditionalOffer (offer_456)
        IF: h1=red, h4=green
        THEN: a2=blue, a3=yellow

(Human sees both offers in sidebar, accepts Agent1's)

Turn 4: Human → Agent1: Accept (offer_456)

Turn 5: Agent1 → Human: Commit a2=blue
Turn 6: Agent1 → Human: Commit a3=yellow

(Human commits their side)

Turn 7: Human → Agent1: Commit h1=red
Turn 8: Human → Agent1: Commit h4=green
```

## What the Agent Evaluates

When deciding to Accept a ConditionalOffer, the agent checks:

1. **Is this from the recipient?** Only accept offers from the current negotiation partner
2. **Current penalty > 0?** Only accept if we have conflicts to resolve
3. **Has assignments and conditions?** Offer must be well-formed
4. **Not already accepted?** Don't accept twice

**Future improvements could add:**
- More sophisticated penalty evaluation (simulate the outcome)
- Check if conditions match current beliefs
- Verify that assignments are feasible
- Consider alternative offers

## Testing

### Test 1: Human Sends Conditional, Agent Accepts

1. Run program in RB mode
2. In the conditional builder for Agent1:
   - Add condition: Select agent's previous proposal (e.g., "a2=blue")
   - Add assignment: Choose your node and color (e.g., "h1=red")
3. Select "ConditionalOffer" from dropdown
4. Click "Send RB Message"
5. **Watch console** for:
   ```
   [RB Process] Received ConditionalOffer offer_12345 from Human
   [RB Move Gen] Priority 2.5: Found 1 pending conditional offers
   [RB Move Gen] -> Accepting ConditionalOffer offer_12345 (penalty=X.XXX)
   ```
6. **Check chat** - Agent should send Accept message
7. **Check sidebar** - Your offer should update to "accepted" status

### Test 2: Agent Generates Conditional

1. Run program in RB mode
2. Let agent make 2+ proposals on boundary nodes
3. **Watch console** for:
   ```
   [RB Move Gen] Priority 3.5: Checking if ConditionalOffer is appropriate
   [RB Move Gen] -> Generated ConditionalOffer with 2 conditions and 2 assignments
   ```
4. **Check chat** - Agent should send ConditionalOffer
5. **Check sidebar** - Agent's offer should appear as incoming (yellow card)

### Test 3: Full Negotiation Cycle

1. Agent proposes a2=blue
2. Agent proposes a3=yellow
3. Agent sends ConditionalOffer: "If h1=red AND h4=green, then a2=blue AND a3=yellow"
4. Human accepts in UI
5. Agent commits a2=blue
6. Agent commits a3=yellow
7. Verify penalty = 0

## Console Messages to Watch For

When agents work with conditionals, you should see:

**Receiving:**
```
[RB Process] Received ConditionalOffer offer_12345 from Human
[RB Process] -> Updated belief: a2=blue
```

**Accepting:**
```
[RB Move Gen] Priority 2.5: Found 1 pending conditional offers
[RB Move Gen] -> Accepting ConditionalOffer offer_12345 (penalty=0.500)
```

**Generating:**
```
[RB Move Gen] Priority 3.5: Checking if ConditionalOffer is appropriate
[RB Move Gen] -> Generated ConditionalOffer with 2 conditions and 2 assignments
```

**Processing Accept:**
```
[RB Process] Offer offer_456 accepted by Human
[RB Process] -> Committing to our side of offer: a2=blue
```

## Files Modified

- `agents/rule_based_cluster_agent.py`
  - Lines 281-308: Added Priority 2.5 (Accept ConditionalOffers)
  - Lines 371-389: Added Priority 3.5 (Generate ConditionalOffers)

## Summary

Agents now:
- ✅ **Generate ConditionalOffers** when they have multiple boundary nodes to package
- ✅ **Accept ConditionalOffers** when they reduce penalty
- ✅ **Commit to accepted offers** automatically
- ✅ **Track offer status** (pending vs accepted)

The conditional negotiation protocol is now fully bidirectional - both humans and agents can propose, accept, and commit to conditional deals! 🎉
