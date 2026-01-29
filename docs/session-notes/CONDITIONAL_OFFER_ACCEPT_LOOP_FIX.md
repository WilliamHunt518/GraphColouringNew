# Conditional Offer Accept Loop Fix

## Critical Bug Found

Looking at the agent logs, I discovered why agents weren't generating conditional offers:

**The agent was stuck in an infinite loop accepting the same offer over and over!**

### Evidence from Logs

```
[RB Move Gen] Priority 2.5: Found 1 pending conditional offers
[RB Move Gen] -> Accepting ConditionalOffer offer_1769436480_Human (penalty=10.000)
... (repeats 30+ times)
```

The agent kept:
1. Finding the pending offer
2. Accepting it
3. Next turn: finding the SAME pending offer again
4. Accepting it AGAIN
5. Loop forever...

**Result:** Agent never reached Priority 3.5 where it would generate its own conditional offers!

## Root Cause

When the agent sent an Accept move, it wasn't marking the offer as accepted locally:

```python
# OLD CODE (BUGGY):
if current_penalty > 0.0 and offer.assignments and offer.conditions:
    self.log(f"[RB Move Gen] -> Accepting ConditionalOffer {offer_id}")
    return RBMove(
        move="Accept",
        refers_to=offer_id,
        reasons=[...]
    )
    # BUG: offer_id never added to self.rb_accepted_offers!
```

**Next turn:**
- `pending_offers` filters by `offer_id not in self.rb_accepted_offers`
- Since offer was never added to `rb_accepted_offers`, it's still "pending"
- Agent accepts it again... forever!

## Fix Applied

### Change 1: Mark Offer as Accepted BEFORE Returning (Lines 302-313)

```python
if current_penalty > 0.0 and offer.assignments and offer.conditions:
    self.log(f"[RB Move Gen] -> Accepting ConditionalOffer {offer_id} (penalty={current_penalty:.3f})")

    # CRITICAL: Mark as accepted BEFORE returning
    self.rb_accepted_offers.add(offer_id)
    self.log(f"[RB Track] Marked offer {offer_id} as accepted")

    return RBMove(
        move="Accept",
        refers_to=offer_id,
        reasons=["reduces_penalty", f"penalty={current_penalty:.3f}"]
    )
```

**Now:**
- Offer is marked as accepted immediately
- Next turn: `pending_offers` won't include it
- Agent moves on to other priorities (like generating its own conditionals!)

### Change 2: Add Extensive Logging to Priority 3.5 (Lines 375-399)

Added detailed logging at every decision point:

```python
current_penalty = self._compute_local_penalty()
has_proposals = len(self.rb_proposed_nodes.get(recipient, {})) > 0

# Log BEFORE checking conditions
self.log(f"[RB Move Gen] Priority 3.5 CHECK: phase={phase}, penalty={current_penalty:.3f}, proposals={has_proposals}, boundary_nodes={len(boundary_nodes)}")

if phase in ("proposing", "negotiating"):
    if (current_penalty > 0.0 or has_proposals) and len(boundary_nodes) >= 2:
        self.log(f"[RB Move Gen] Priority 3.5: ConditionalOffer eligible")

        my_offers = [oid for oid in self.rb_active_offers.keys() if self.name in oid]
        self.log(f"[RB Move Gen] Priority 3.5: My pending offers: {my_offers}")

        if not my_offers:
            self.log(f"[RB Move Gen] Priority 3.5: Calling _generate_conditional_offer()...")
            conditional_offer = self._generate_conditional_offer(recipient)
            if conditional_offer:
                self.log(f"[RB Move Gen] -> Generated ConditionalOffer with {len(conditional_offer.conditions)} conditions and {len(conditional_offer.assignments)} assignments")
                return conditional_offer
            else:
                self.log(f"[RB Move Gen] Priority 3.5: _generate_conditional_offer() returned None")
        else:
            self.log(f"[RB Move Gen] Priority 3.5: Already have pending offers: {my_offers}")
    else:
        self.log(f"[RB Move Gen] Priority 3.5: Not eligible - phase={phase}, penalty={current_penalty:.3f}, proposals={has_proposals}, boundary_nodes={len(boundary_nodes)}")
else:
    self.log(f"[RB Move Gen] Priority 3.5: Wrong phase (phase={phase}, need 'proposing' or 'negotiating')")
```

**Why this logging?**

Now we can see exactly why Priority 3.5 succeeds or fails:
- Is the phase correct?
- Is penalty > 0?
- Are there boundary nodes?
- Does the agent already have pending offers?
- Did `_generate_conditional_offer()` return something or None?

## Expected Behavior Now

### Turn 1-3: Agent Makes Proposals
```
[RB Move Gen] Phase: init
[RB Move Gen] -> Proposing a2=red
[RB Move Gen] -> Proposing a4=green
[RB Move Gen] -> Proposing a5=green
(Phase transitions to "proposing")
```

### Turn 4: Human Sends Conditional
```
[RB Process] Received ConditionalOffer offer_123 from Human
```

### Turn 5: Agent Accepts (ONCE!)
```
[RB Move Gen] Priority 2.5: Found 1 pending conditional offers
[RB Move Gen] -> Accepting ConditionalOffer offer_123 (penalty=10.000)
[RB Track] Marked offer offer_123 as accepted  ← FIXED!
```

### Turn 6: Agent Generates Its Own Conditional
```
[RB Move Gen] Priority 2.5: Found 0 pending conditional offers  ← No longer stuck!
[RB Move Gen] Priority 3.5 CHECK: phase=proposing, penalty=10.000, proposals=True, boundary_nodes=3
[RB Move Gen] Priority 3.5: ConditionalOffer eligible
[RB Move Gen] Priority 3.5: My pending offers: []
[RB Move Gen] Priority 3.5: Calling _generate_conditional_offer()...
[ConditionalOffer Gen] Our boundary: ['a2', 'a4', 'a5'], Their boundary: ['h4', 'h1']
[ConditionalOffer Gen] Current penalty: 10.000
[ConditionalOffer Gen] Enumerating 16 possible configurations
[ConditionalOffer Gen] Found zero-penalty configuration!
[ConditionalOffer Gen] Generated offer: 2 conditions, 2 assignments, penalty=0.000
[RB Move Gen] -> Generated ConditionalOffer with 2 conditions and 2 assignments
```

### Turn 7+: Negotiation Continues
```
(Agent and human exchange messages, eventually reach consensus)
```

## Testing

Run the program and watch the console. You should now see:

1. **When agent accepts your conditional:**
   ```
   [RB Track] Marked offer offer_xxx as accepted
   ```

2. **Next turn after accepting:**
   ```
   [RB Move Gen] Priority 2.5: Found 0 pending conditional offers  ← Not stuck!
   [RB Move Gen] Priority 3.5 CHECK: ...
   ```

3. **Agent generating its own conditional:**
   ```
   [RB Move Gen] Priority 3.5: Calling _generate_conditional_offer()...
   [ConditionalOffer Gen] Enumerating X possible configurations
   [ConditionalOffer Gen] Found zero-penalty configuration!
   ```

## Files Modified

- `agents/rule_based_cluster_agent.py`
  - Lines 302-313: Mark offer as accepted before returning Accept move
  - Lines 375-399: Add extensive logging to Priority 3.5

## Summary

**Bug:** Agent stuck in infinite accept loop, never generating own conditionals
**Fix:** Mark offers as accepted immediately when sending Accept move
**Benefit:** Agent can now move past Priority 2.5 to Priority 3.5 and generate conditionals!

Agents should now generate conditional offers as intended! 🎉
