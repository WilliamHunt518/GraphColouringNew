# FIX #21: Comprehensive Offer Validation and Logging

## Date: 2026-02-04

## Problem

Offers are being generated that claim to achieve penalty=0, but when accepted, they result in conflicts. It's unclear whether:
A) The offers are bad (agent generates invalid offers)
B) The implementation is bad (offers are good but applied incorrectly)

## Solution

Added comprehensive validation that:
1. Logs the complete offer in plain English
2. Simulates accepting the offer
3. Validates the resulting penalty matches the claim
4. Detects conflicts in the resulting configuration
5. Fails and refuses to send bad offers

## Implementation

**File**: `agents/rule_based_cluster_agent.py`
**Lines**: 1167-1256 (replaced previous simple validation)

### What Changed

**Before**: Simple validation that only checked if solver penalty matched claimed penalty

**After**: Comprehensive validation that:
- Logs offer in human-readable format: "IF recipient sets X, THEN agent sets Y"
- Logs complete resulting configuration (all nodes)
- Validates penalty with promised assignments
- Validates penalty with optimal assignments
- Detects assignment mismatches (promising one thing, optimal is different)
- Detects obvious conflicts in resulting configuration
- Refuses to send offers that don't match their claims

### Validation Steps

1. **Log Offer Intent**:
   ```
   [OFFER VALIDATION] IF Human sets: h1=blue, h4=red
   [OFFER VALIDATION] THEN Agent1 will set: a2=red, a4=green, a5=blue
   [OFFER VALIDATION] Claimed Agent1 penalty: 0.000
   ```

2. **Build Complete Configuration**:
   - Combine promised neighbor assignments (conditions)
   - Combine promised own assignments (assignments)
   - Log full resulting state

3. **Simulate Acceptance**:
   - Apply hypothetical neighbor state
   - Apply promised assignments
   - Run maxsum to find optimal response
   - Compare optimal vs promised

4. **Validate Penalty**:
   - Compute penalty with promised assignments
   - Compute penalty with optimal assignments
   - Check if claimed penalty matches actual penalty
   - Tolerance: 0.1 (for numerical precision)

5. **Detect Conflicts**:
   - Check all edges in the graph
   - Find edges where both nodes have same color
   - Log conflicts (with caveat that some may be in recipient's cluster)

6. **Decision**:
   - If validation fails: Return None (don't send offer)
   - If validation passes: Log success and send offer

### Log Output Format

**Successful Offer**:
```
[OFFER VALIDATION] ========== VALIDATING OFFER ==========
[OFFER VALIDATION] Offer ID: offer_1770206837_Agent1
[OFFER VALIDATION] Recipient: Human
[OFFER VALIDATION] IF Human sets: h1=blue, h4=red
[OFFER VALIDATION] THEN Agent1 will set: a2=red, a4=green, a5=blue
[OFFER VALIDATION] Claimed Agent1 penalty: 0.000
[OFFER VALIDATION] Resulting neighbor state: {'h1': 'blue', 'h4': 'red'}
[OFFER VALIDATION] Resulting Agent1 assignments: {'a1': 'green', 'a2': 'red', 'a3': 'blue', 'a4': 'green', 'a5': 'blue'}
[OFFER VALIDATION] Penalty with promised assignments: 0.000
[OFFER VALIDATION] Penalty with optimal assignments: 0.000
[OFFER VALIDATION] ✓ VALIDATION PASSED
[OFFER VALIDATION] Offer achieves claimed penalty: 0.000 ≈ 0.000
[OFFER VALIDATION] ========================================
```

**Failed Offer** (conflicts detected):
```
[OFFER VALIDATION] ========== VALIDATING OFFER ==========
[OFFER VALIDATION] Offer ID: offer_1770206837_Agent2
[OFFER VALIDATION] Recipient: Human
[OFFER VALIDATION] IF Human sets: h2=red, h5=green
[OFFER VALIDATION] THEN Agent2 will set: b2=blue
[OFFER VALIDATION] Claimed Agent2 penalty: 0.000
[OFFER VALIDATION] Resulting neighbor state: {'h2': 'red', 'h5': 'green'}
[OFFER VALIDATION] Resulting Agent2 assignments: {'b1': 'red', 'b2': 'blue'}
[OFFER VALIDATION] Penalty with promised assignments: 2.000
[OFFER VALIDATION] Penalty with optimal assignments: 2.000
[OFFER VALIDATION] ❌ FAILED - claimed penalty=0.000 but actually 2.000
[OFFER VALIDATION] This offer would create conflicts!
```

**Warning** (promised ≠ optimal):
```
[OFFER VALIDATION] ⚠️  WARNING: a2 - promising red but optimal is blue
[OFFER VALIDATION] ⚠️  WARNING: Promised assignments differ from optimal
[OFFER VALIDATION] This might indicate a bug in offer generation
```

## Benefits

1. **Diagnostic**: Immediately see if offers are bad or implementation is bad
2. **Prevention**: Bad offers are caught before being sent
3. **Transparency**: Every offer is logged with complete details
4. **Debugging**: Can trace exactly what configuration an offer proposes
5. **Quality**: Only validated offers are sent to recipients

## Testing

### Expected Behavior

When running RB mode, check console for validation logs after each offer:

1. **Good Offer** (penalty=0):
   ```bash
   grep "OFFER VALIDATION" results/rb/Agent1_log.txt
   ```
   Should show: `✓ VALIDATION PASSED` with matching penalties

2. **Bad Offer** (penalty>0):
   ```bash
   grep "FAILED" results/rb/Agent1_log.txt
   ```
   Should show: `❌ FAILED - claimed penalty=X but actually Y`
   Offer should NOT appear in communication_log.txt

3. **Conflict Detection**:
   ```bash
   grep "CONFLICTS detected" results/rb/Agent*_log.txt
   ```
   Shows which edges have conflicts in resulting config

### Manual Test

1. `python launch_menu.py` → RB mode
2. Set colors with conflicts
3. Announce configuration
4. Check Agent logs for `[OFFER VALIDATION]` sections
5. For each offer:
   - Verify claimed penalty matches validated penalty
   - Verify no `❌ FAILED` messages
   - If conflicts exist, they should be logged

6. Accept an offer
7. Check if penalty actually becomes 0 (or matches claim)
8. If not, the validation logs will show where the discrepancy occurred

## Edge Cases

1. **Partial Observability**: Agent can only see boundary nodes, so some conflicts in recipient's cluster are invisible. Validation logs these with caveat.

2. **Assignment Mismatch**: If promised assignments differ from optimal, this indicates a bug in offer generation logic. Logged as warning.

3. **Numerical Precision**: Tolerance of 0.1 allows for floating-point rounding errors.

4. **No Edges**: If graph has no edges, conflict detection is skipped (no conflicts possible).

## Related Fixes

- **FIX #17**: UI removes feasibility query after button click
- **FIX #18**: Agent satisfied when penalty=0
- **FIX #19**: Feasibility includes all required nodes, no proactive offer
- **FIX #20**: Cache persists until announcement
- **FIX #21**: Comprehensive offer validation (THIS FIX)

## Diagnosis Guide

If you see offers with conflicts after this fix:

### Case 1: Validation shows ✓ PASSED but conflicts still occur
→ **Implementation bug**: Offer is good, but acceptance/application is broken
→ Check: UI button handlers, announcement logic, cache application

### Case 2: Validation shows ❌ FAILED
→ **Generation bug**: Offer generation logic is creating bad offers
→ Check: `_generate_conditional_offer` logic, counterfactual enumeration

### Case 3: Validation shows ⚠️ WARNING (promised ≠ optimal)
→ **Generation bug**: Offer promises assignments that aren't actually optimal
→ Check: Why `best_our_assignment` differs from maxsum result

### Case 4: Validation shows conflicts but penalty=0
→ **Partial observability**: Conflicts are in recipient's cluster (invisible to agent)
→ This is expected if recipient has internal constraints agent can't see

## Files Modified

- `agents/rule_based_cluster_agent.py`: Lines 1167-1256 (enhanced validation)

## Rollback

If issues occur:
```bash
git diff agents/rule_based_cluster_agent.py
# Revert lines 1167-1256 to restore simple validation
```

System will revert to basic validation that only checks penalty match.

## Performance Impact

- Minimal: Validation only runs when generating offers (not every step)
- Maxsum is already run during offer generation
- Extra logging adds ~50 log lines per offer
- No performance degradation expected
