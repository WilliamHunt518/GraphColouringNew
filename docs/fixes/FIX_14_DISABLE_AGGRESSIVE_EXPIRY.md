# FIX #14: Disable Aggressive Offer Expiry

## The Bug

Offers were **auto-expiring after just 45 seconds** (15 iterations at 3s each), removing them from the UI before users could interact with them!

### What You Experienced

From your screenshots and logs:

1. **14:34:04** - Agent2 sends offer: "If h2=red AND h5=green then b2=blue"
2. **14:34:49** - Agent1 sends new offer (45 seconds later)
3. **Agent2's offer disappeared!** (expired after 15 iterations)
4. **14:35:28** - You reject Agent1's offer with h4=green as impossible
5. **14:35:28** - Agent1 sends new offer: "If h1=red AND h4=blue..."
6. **~14:36** - You try to accept this offer
7. **Offer expired and disappeared before you could click!**

From Agent1's log:
```
[RB Expiry] Offer offer_1770129328_Agent1 expired after 15 iterations with no response - allowing new offers
```

### The Bug Chain

1. Agent sends offer and tracks it in `rb_active_offers`
2. AutoSuggest triggers agent steps every 3 seconds
3. Each step increments expiry counter for pending offers
4. After **15 iterations (~45 seconds)**, offer **AUTO-EXPIRES**
5. Agent removes offer from `rb_active_offers`
6. Next AutoSuggest calls `_get_active_conditionals()` → returns `[]`
7. UI calls `update_conditionals([])` → **removes all offers from UI**
8. Your Accept button click finds nothing to accept

## The Fix

Changed expiry from 15 iterations (45 seconds) to **100 iterations (~5 minutes)**:

```python
# CRITICAL FIX #14: Much longer expiry for human interaction (5 minutes)
# Humans need time to read, think, and interact with offers
OFFER_EXPIRY_ITERATIONS = 100  # Expire after 100 iterations (~5 minutes at 3s/iteration)
```

**Location**: `agents/rule_based_cluster_agent.py:644`

## Why This Was So Bad

**45 seconds is WAY too short for human interaction!** Humans need to:
- Read and understand the offer
- Think about implications
- Possibly check other offers or agent states
- Click buttons

With 2 agents sending offers, the first offer could easily expire before you even finish reading the second one!

## Impact

- ✓ Offers now stay visible for 5 minutes
- ✓ Users have time to read, think, and respond
- ✓ No more mysteriously disappearing offers
- ✓ Accept buttons actually work because offers are still there

## Testing

Run your workflow again:
1. Announce configuration
2. Wait for offers from both agents
3. Take your time reading them
4. Reject/Accept as needed
5. **Offers should stay visible for 5 minutes** instead of disappearing after 45 seconds

## Related Issues

This fix addresses:
- **Issue 1**: Agent2's initial offer (h2=red, h5=green) disappeared after 45 seconds
- **Issue 2**: Agent1's offer (h1=red, h4=blue) disappeared before you could accept it
- **Issue 3**: Accept button finding nothing to accept because offer already expired

## Files Modified

- `agents/rule_based_cluster_agent.py:644` - Increased OFFER_EXPIRY_ITERATIONS from 15 to 100
