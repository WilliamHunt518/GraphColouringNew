# Agent Decision Flow - Visual Summary

This document provides a visual flowchart of the agent decision process.

## High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                      AGENT.step() CALLED                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │ Receive        │
                    │ Message?       │
                    └───┬────────┬───┘
                        │ Yes    │ No
                        ▼        │
              ┌─────────────────┐│
              │ Parse Message   ││
              │ Extract:        ││
              │ - Forced colors ││
              │ - Boundary info ││
              └────────┬────────┘│
                       │         │
                       └────┬────┘
                            │
                            ▼
              ┌──────────────────────┐
              │ Log Current State:   │
              │ - My assignments     │
              │ - Boundary knowledge │
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │ COMPUTE_ASSIGNMENTS  │◄────────────────────┐
              │ (Greedy/MaxSum)      │                     │
              │                      │                     │
              │ Respects:            │                     │
              │ 1. Fixed nodes       │                     │
              │ 2. Forced requests   │                     │
              │ 3. Boundary conflicts│                     │
              └──────────┬───────────┘                     │
                         │                                 │
                         ▼                                 │
              ┌──────────────────────┐                     │
              │ Assignments          │                     │
              │ Changed?             │                     │
              └──┬────────────────┬──┘                     │
                 │ Yes            │ No                     │
                 │                │                        │
   ┌─────────────┘                └──────────┐             │
   │                                          │             │
   │ LOG: "Updated from X to Y"               │             │
   │                                          │             │
   │                           LOG: "Unchanged"            │
   │                           LOG: "Penalty still > 0"    │
   │                                          │             │
   └──────────────┬───────────────────────────┘             │
                  │                                         │
                  ▼                                         │
        ┌─────────────────┐                                │
        │ Apply New       │                                │
        │ Assignments     │                                │
        └────────┬────────┘                                │
                 │                                         │
                 ▼                                         │
        ┌─────────────────┐                                │
        │ Forced Colors   │                                │
        │ Were Used?      │                                │
        └────┬────────┬───┘                                │
             │ Yes    │ No                                 │
             │        │                                    │
    Clear    │        │                                    │
    Forced   │        │                                    │
             └────┬───┘                                    │
                  │                                        │
                  ▼                                        │
        ┌──────────────────────┐                          │
        │ SNAP-TO-BEST         │                          │
        │ DECISION LOGIC       │                          │
        └──────────┬───────────┘                          │
                   │                                       │
        ┌──────────┼──────────────────────────────┐       │
        │          │                               │       │
        ▼          ▼                               ▼       │
   Forced     Assignments                      Greedy      │
   Used?      Changed?                         Stuck?      │
     YES         YES                             NO        │
     │           │                               │         │
     │           │                               │         │
     └───┬───────┴───────┬───────────────────────┘         │
         │               │                                 │
         ▼               ▼                                 │
    SKIP SNAP       SKIP SNAP                              │
    (Respect        (Trust                                 │
     human)         greedy)                                │
                                                           │
                        │                                  │
                        │                                  │
                        ▼                                  │
                 ┌────────────┐                            │
                 │ Check      │                            │
                 │ Improvement│                            │
                 └─────┬──────┘                            │
                       │                                   │
            ┌──────────┼──────────┐                        │
            │                     │                        │
            ▼                     ▼                        │
     Big Improvement?      Small Improvement?              │
     (> threshold)         (< threshold)                   │
            │                     │                        │
            │                     ▼                        │
            │                SKIP SNAP                     │
            │                (Not worth it)                │
            │                                              │
            ▼                                              │
    ┌───────────────┐                                      │
    │ RUN SNAP!     │                                      │
    │ Exhaustive    │──────────────────────────────────────┘
    │ Search Best   │
    └───────┬───────┘
            │
            │ Override assignments
            │ with best found
            │
            └───────┬─────────────────────────────┐
                    │                             │
                    ▼                             ▼
          ┌─────────────────┐         ┌─────────────────┐
          │ Update          │         │ Compute         │
          │ Satisfaction    │         │ Satisfaction    │
          │ Flag            │         └────────┬────────┘
          └────────┬────────┘                  │
                   │                            │
                   │    ┌───────────────────────┘
                   │    │
                   ▼    ▼
          ┌──────────────────────┐
          │ Check Satisfaction:  │
          │                      │
          │ 1. Penalty = 0?      │──No──┐
          │ 2. At optimum?       │      │
          └──────────┬───────────┘      │
                     │ Yes               │
                     │                   ▼
                     │          satisfied = False
                     │          LOG: "Not satisfied"
                     │
                     ▼
            satisfied = True
            LOG: "Satisfied"
                     │
                     │
           ┌─────────┴────────────┐
           │                      │
           ▼                      ▼
    ┌──────────────┐    ┌───────────────────┐
    │ Human        │    │ Other Agents      │
    │ Message?     │    │                   │
    └──────┬───────┘    └────────┬──────────┘
           │ Yes                 │
           │                     │
           ▼                     ▼
  ┌─────────────────┐   ┌────────────────────┐
  │ Generate LLM    │   │ Compute            │
  │ Response:       │   │ Counterfactuals:   │
  │                 │   │                    │
  │ "I changed X"   │   │ "If you set h2=R   │
  │ "Conflict at Y" │   │  I can score N"    │
  │ "Try changing Z"│   │                    │
  └────────┬────────┘   └────────┬───────────┘
           │                     │
           │                     │
           └─────────┬───────────┘
                     │
                     ▼
            ┌────────────────┐
            │ Send Messages  │
            └────────────────┘
                     │
                     ▼
            ┌────────────────┐
            │   TURN ENDS    │
            └────────────────┘
```

---

## Key Decision Points

### 1. Should I Apply Forced Assignment?
```
IF human said "change b2 to blue":
    forced_local_assignments['b2'] = 'blue'
    → Greedy will respect this in next compute
```

### 2. Should I Run Snap-to-Best?
```
IF forced_assignments_used:
    SKIP (respect human intent)
ELIF assignments_just_changed:
    SKIP (trust greedy's new solution)
ELIF improvement < threshold:
    SKIP (not worth overriding)
ELSE:
    RUN SNAP (greedy stuck, need big improvement)
```

### 3. Am I Satisfied?
```
penalty = evaluate(my_assignments + boundary_colors)

IF penalty > 0:
    satisfied = False ❌
ELIF not_at_local_optimum:
    satisfied = False ❌
ELSE:
    satisfied = True ✓
```

---

## Example Trace: Agent2 Turn

```
Turn N:
  1. Receive: "change b2 to blue"
  2. Parse: forced_local_assignments = {'b2': 'blue'}
  3. Compute: Greedy sets b2=blue (respects forced)
  4. Check changed: YES (was red, now blue)
  5. Apply: self.assignments['b2'] = 'blue'
  6. Clear forced: forced_local_assignments = {}
  7. Snap check:
     - Forced used? YES → SKIP SNAP ✓
  8. Satisfaction:
     - Penalty = 10.0 (b2 still conflicts with h2)
     - satisfied = False
  9. Response: "I changed b2 to blue as requested"
  10. Send utility messages
```

**Result:** b2 successfully changed to blue, NOT overridden by snap!

---

## Example Trace: Snap Override (OLD BUG)

```
Turn N (BEFORE FIX):
  1. Receive: "change b2 to blue"
  2. Parse: forced = {'b2': 'blue'}
  3. Compute: Greedy sets b2=blue
  4. Check: changed = YES
  5. Apply: b2 = blue
  6. Clear forced: {} ✓
  7. Snap check:
     - Current penalty = 20.0
     - Best penalty = 10.0 (with b2=red)
     - Improvement = 10.0 > threshold
     - RUN SNAP! ❌
     - Override: b2 = red
  8. Satisfaction: False (penalty still > 0)
  9. Response: "I changed b2 to blue" (LIE! It's actually red)
```

**Problem:** Snap ran even though forced assignment was just applied!

**Fix:** Snap now checks `forced_were_used` and skips.

---

## Data Flow Diagram

```
┌─────────┐
│ Human   │
│ Message │
└────┬────┘
     │
     ▼
┌──────────────────┐
│ forced_local_    │
│ assignments      │◄────────────┐
└────┬─────────────┘             │
     │                           │
     ▼                           │
┌──────────────────┐             │
│ compute_         │             │
│ assignments()    │             │
│ (Greedy/MaxSum)  │             │
└────┬─────────────┘             │
     │                           │
     ▼                           │
┌──────────────────┐             │
│ self.assignments │             │
└────┬─────────────┘             │
     │                           │
     ▼                           │
┌──────────────────┐             │
│ Clear forced     │─────────────┘
└────┬─────────────┘
     │
     ▼
┌──────────────────┐
│ snap-to-best     │
│ (conditional)    │
└────┬─────────────┘
     │
     ▼
┌──────────────────┐
│ self.assignments │ ──┐
└──────────────────┘   │
                       │
┌──────────────────┐   │
│ neighbour_       │   │
│ assignments      │   │
└────┬─────────────┘   │
     │                 │
     └────────┬────────┘
              │
              ▼
     ┌────────────────┐
     │ evaluate()     │
     │ penalty calc   │
     └────┬───────────┘
          │
          ▼
     ┌────────────────┐
     │ self.satisfied │
     └────────────────┘
```

---

## Snap-to-Best Logic Tree

```
                   ┌────────────────┐
                   │ Should Snap?   │
                   └───────┬────────┘
                           │
              ┌────────────┼────────────┐
              │                         │
              ▼                         ▼
      ┌──────────────┐          ┌──────────────┐
      │ Forced used? │          │ Changed?     │
      └──────┬───────┘          └──────┬───────┘
             │                         │
          Yes│                      Yes│
             │                         │
             ▼                         ▼
        ┌─────────┐              ┌─────────┐
        │ SKIP    │              │ SKIP    │
        │ (Human) │              │ (Trust) │
        └─────────┘              └─────────┘
             │                         │
          No │                      No │
             │                         │
             └────────┬────────────────┘
                      │
                      ▼
              ┌───────────────┐
              │ Improvement   │
              │ > threshold?  │
              └───────┬───────┘
                      │
                 Yes  │  No
              ┌───────┴───────┐
              │               │
              ▼               ▼
        ┌─────────┐      ┌────────┐
        │ SNAP!   │      │ SKIP   │
        └─────────┘      │ (Small)│
                         └────────┘
```

---

## Logging Patterns to Look For

### ✅ Healthy Turn (Agent Changes Successfully)
```
Known boundary colors: {'h2': 'red', 'h5': 'blue'}
Updated assignments from {..., 'b2': 'red'} to {..., 'b2': 'green'}
Skipping snap-to-best: greedy just found new solution
Not satisfied: current_penalty=10.000 > 0
Response: "I changed b2 to green to avoid the clash"
```

### ✅ Healthy Turn (Forced Assignment Respected)
```
Forced local assignment requested: b2 -> blue
Known boundary colors: {'h2': 'red', 'h5': 'blue'}
Updated assignments from {..., 'b2': 'red'} to {..., 'b2': 'blue'}
Clearing forced_local_assignments: {'b2': 'blue'}
Skipping snap-to-best: forced assignments just applied
Response: "I changed b2 to blue as you requested"
```

### ❌ Problem: Snap Override (OLD BUG)
```
Updated assignments from {..., 'b2': 'red'} to {..., 'b2': 'green'}
Clearing forced_local_assignments: {'b2': 'green'}
Snapped to best local assignment (pen 20.0 -> 10.0)  ⚠️
Verification: b2 = red  ⚠️ (Changed back!)
Response: "I changed b2 to green"  ⚠️ (LIE!)
```

### ❌ Problem: Agent Stuck
```
Assignments unchanged: {'b1': 'blue', 'b2': 'red', ...}
WARNING: Assignments didn't change despite penalty=10.0
Skipping snap-to-best: improvement too small (10.0 -> 8.0)
Response: "I can't resolve this without you changing the boundary"
```

### ❌ Problem: Case Mismatch (FIXED)
```
BUG WARNING: 1 conflicts detected but penalty=0.000000
  My assignments: {'b2': 'Red'}
  Neighbor assignments: {'h2': 'red'}
```

---

## Summary

The agent's ability to change colors depends on:

1. **Human requests** (forced assignments) → Always applied unless node is fixed
2. **Greedy algorithm** → Finds new colors when boundary changes or forced
3. **Snap-to-best** → Only overrides when greedy is stuck AND big improvement exists

The key fix was making snap-to-best **conditional** rather than **always running**.
