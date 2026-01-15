# Agent Decision Process

This document explains the step-by-step process agents follow when making decisions in the graph coloring task. This is critical for understanding **when and why** agents change (or don't change) their color assignments.

## Overview

Each agent controls a cluster of nodes and tries to find a valid coloring while coordinating with the human and other agents through messages. The agent's behavior depends on:
- Its internal optimization algorithm (greedy or maxsum)
- Communication mode (LLM_U, LLM_C, LLM_F, or RB)
- Current knowledge of boundary node colors
- Human requests for specific color assignments

---

## Agent Step() Flow

Every time an agent takes a turn, it follows this process:

### 1. **Receive Message** (if any)
```
IF message from human:
    - Parse message text for color assignments
    - Extract forced assignments: "change b2 to green" → forced_local_assignments['b2'] = 'green'
    - Update neighbour_assignments with reported boundary colors
    - Store human's message text for response generation
END IF
```

**Key Point:** Forced assignments are marked but NOT yet applied. They'll be used in step 3.

---

### 2. **Log Current State**
```
base_beliefs = neighbour_assignments (what we know about boundary nodes)
LOG: "Known boundary colors: {base_beliefs}"

IF base_beliefs is empty:
    LOG: "WARNING: No known boundary colors"
END IF
```

**Why This Matters:** If an agent doesn't know boundary colors, it can't reason about conflicts.

---

### 3. **Compute New Assignments** (Core Algorithm)

This is where the agent decides what colors to use for its nodes.

#### For Greedy Algorithm:
```
INPUT:
    - self.nodes (e.g., ['b1', 'b2', 'b3', 'b4', 'b5'])
    - self.domain (e.g., ['red', 'green', 'blue'])
    - fixed_local_nodes (immutable assignments, if any)
    - forced_local_assignments (human requests, if any)
    - neighbour_assignments (known boundary colors)

PROCESS:
    new_assignment = {}

    # Priority order: fixed > forced > optimized
    constrained = merge(forced_local_assignments, fixed_local_nodes)

    FOR each node in self.nodes:
        IF node in constrained:
            # This node is fixed or forced - use that color
            new_assignment[node] = constrained[node]
            CONTINUE
        END IF

        # Find best color for this node
        best_color = None
        best_penalty = infinity

        FOR each color in domain:
            penalty = 0

            # Check internal conflicts (with other nodes in our cluster)
            FOR each edge (u, v) in problem.edges:
                IF (node == u AND v in new_assignment):
                    IF color == new_assignment[v]:
                        penalty += conflict_penalty
                    END IF
                ELIF (node == v AND u in new_assignment):
                    IF color == new_assignment[u]:
                        penalty += conflict_penalty
                    END IF
                END IF
            END FOR

            # Check boundary conflicts (with external nodes)
            FOR each edge (u, v) in problem.edges:
                IF (node == u AND v is external):
                    external_color = neighbour_assignments[v]
                    IF external_color exists AND color == external_color:
                        penalty += conflict_penalty
                    END IF
                ELIF (node == v AND u is external):
                    external_color = neighbour_assignments[u]
                    IF external_color exists AND color == external_color:
                        penalty += conflict_penalty
                    END IF
                END IF
            END FOR

            # Subtract preferences (higher preference → lower effective penalty)
            penalty -= problem.preferences[node][color]

            IF penalty < best_penalty:
                best_penalty = penalty
                best_color = color
            END IF
        END FOR

        new_assignment[node] = best_color
    END FOR

OUTPUT: new_assignment
```

**Critical Behavior:**
- **Forced assignments are RESPECTED** - if human said "b2=blue", greedy will set b2=blue
- **Boundary conflicts ARE considered** - greedy tries to avoid clashing with neighbour_assignments
- **Nodes colored sequentially** - order matters! Later nodes see earlier assignments

---

### 4. **Check if Assignments Changed**
```
old_assignments = self.assignments
assignments_changed = (new_assignment != old_assignments)

IF assignments_changed:
    LOG: "Updated assignments from {old} to {new}"
ELSE:
    LOG: "Assignments unchanged: {old}"
    IF penalty > 0:
        LOG: "WARNING: Assignments didn't change despite penalty={penalty}"
    END IF
END IF
```

**Why This Matters:** This flag determines whether snap-to-best runs (see step 6).

---

### 5. **Apply New Assignments**
```
self.assignments = new_assignment
```

At this point, the agent's assignments are updated to what greedy computed.

---

### 6. **Clear Forced Assignments**
```
forced_were_used = (forced_local_assignments is not empty)

IF forced_were_used:
    LOG: "Clearing forced_local_assignments: {forced_local_assignments}"
    forced_local_assignments = {}
END IF
```

**Key Point:** Forced assignments are one-time use. After being applied, they're cleared.

---

### 7. **Snap-to-Best Logic** (CRITICAL - Source of Many Bugs!)

This step tries to improve the solution by exhaustively searching for the best assignment.

```
should_snap = False

IF forced_were_used:
    LOG: "Skipping snap: forced assignments just applied (respecting human intent)"
ELIF assignments_changed:
    LOG: "Skipping snap: greedy just found new solution (trusting its choice)"
ELSE:
    # Greedy got stuck (no change) - check if snap would help
    current_penalty = evaluate({neighbour_assignments, self.assignments})
    best_penalty, best_assignment = exhaustive_search({neighbour_assignments})

    improvement_threshold = 5.0
    IF current_penalty > best_penalty + improvement_threshold:
        should_snap = True
        LOG: "Snapping: significant improvement available (pen {current} -> {best})"
    ELSE:
        LOG: "Skipping snap: improvement too small"
    END IF
END IF

IF should_snap:
    self.assignments = best_assignment
    assignments_changed = True
    LOG: "Snapped to best local assignment"
END IF
```

**CRITICAL BEHAVIOR:**
- **Does NOT run if forced assignments were used** - respects human intent
- **Does NOT run if greedy just changed** - trusts greedy's new solution
- **Only runs if greedy got stuck AND big improvement available**

**Why This Exists:** Small clusters (5 nodes, 3 colors = 3^5 = 243 combinations) make exhaustive search cheap. Snap ensures we don't get stuck in local optima.

**Historical Bug:** Before the fix, snap would ALWAYS run and override greedy's solution, causing agents to:
- Say "I'll change b2 to green"
- Greedy sets b2=green
- Snap overrides to b2=red (lower penalty)
- Agent reports b2=red, appearing to lie

---

### 8. **Update Satisfaction Flag**
```
satisfied = _compute_satisfied()

FUNCTION _compute_satisfied():
    base = neighbour_assignments
    current_penalty = evaluate({base, self.assignments})

    # Defensive check: manually count boundary conflicts
    conflict_count = 0
    FOR each my_node in self.nodes:
        my_color = self.assignments[my_node]
        FOR each neighbour in my_node.neighbors:
            IF neighbour is external:
                neighbour_color = base[neighbour]
                IF neighbour_color exists AND my_color == neighbour_color (case-insensitive):
                    conflict_count += 1
                    LOG: "BOUNDARY CONFLICT: {my_node}({my_color}) <-> {neighbour}({neighbour_color})"
                END IF
            END IF
        END FOR
    END FOR

    # BUG DETECTION: If conflicts exist but penalty is 0, something is wrong!
    IF conflict_count > 0 AND current_penalty < 0.001:
        LOG: "BUG WARNING: {conflict_count} conflicts but penalty={current_penalty}"
        RETURN False  # Force unsatisfied
    END IF

    # Never satisfied if there are conflicts
    IF current_penalty > 0.001:
        LOG: "Not satisfied: penalty={current_penalty} > 0"
        RETURN False
    END IF

    # No conflicts - check if at local optimum
    best_penalty, _ = exhaustive_search({base})
    RETURN (current_penalty <= best_penalty + 0.001)
END FUNCTION

LOG: "Satisfied: {satisfied}"

# Double-check satisfaction claim
IF satisfied == True:
    verify_penalty = evaluate({neighbour_assignments, self.assignments})
    IF verify_penalty > 0.001:
        LOG: "CRITICAL BUG: Agent claims satisfied but penalty={verify_penalty}!"
        satisfied = False  # Force correction
    END IF
END IF
```

**CRITICAL:** Satisfaction is ONLY True if:
1. **Penalty = 0** (no conflicts, including boundary)
2. **At local optimum** (can't improve given boundary constraints)

Boundary conflicts ALWAYS make satisfied=False, even if the agent can't fix them locally.

---

### 9. **Generate Response to Human** (if human sent message)

This only runs if the human sent a message this turn.

```
IF human_message_received:
    # Build context
    conflicts = detect_boundary_conflicts()
    changes = compare(old_assignments, self.assignments)
    current_penalty = evaluate({neighbour_assignments, self.assignments})

    # Build LLM prompt
    prompt = """
    You are agent '{name}' collaborating on graph coloring.

    Human said: "{human_message}"

    CRITICAL: Your assignments {'DID' if assignments_changed else 'DID NOT'} change this turn.
    Changes: {changes}

    VERIFICATION:
    - Current penalty: {current_penalty} (0 = no conflicts, >0 = conflicts exist)
    - Detected conflicts: {conflicts}
    - If penalty > 0, you CANNOT claim to have a valid solution

    Current state: {self.assignments}
    Known boundary: {neighbour_assignments}

    Generate response that:
    1. Answers human's question directly
    2. Is TRUTHFUL about whether you changed
    3. Acknowledges conflicts if penalty > 0
    4. Suggests specific fixes if conflicts exist
    """

    response = call_llm(prompt)
    send_message(recipient="Human", content=response)

    # Clear human message so we don't keep responding
    human_message = ""
END IF
```

**Why LLM Can Still Lie:** Even with verification in the prompt, the LLM might:
- Misinterpret the state
- Hallucinate changes that didn't happen
- Claim satisfaction when penalty > 0

The defensive logging helps catch these cases.

---

### 10. **Send Utility Messages to Other Agents**

```
FOR each recipient in {other agents}:
    # Build counterfactual analysis
    boundary_nodes = {nodes adjacent to recipient's cluster}
    options = []

    FOR each possible boundary configuration:
        hypothetical_neighbour_assignments = {boundary config}
        best_penalty, best_agent_assignment = exhaustive_search(hypothetical_neighbour_assignments)

        agent_score = score(best_agent_assignment)
        human_score = score(boundary config)

        options.append({
            'human': boundary config,
            'penalty': best_penalty,
            'agent_score': agent_score,
            'human_score': human_score,
            'combined': agent_score + human_score
        })
    END FOR

    # Find current configuration
    current_option = find_option_matching(current_boundary)

    # CRITICAL FIX: Recompute penalty using ACTUAL assignments, not best possible
    actual_penalty = evaluate({neighbour_assignments, self.assignments})
    current_option['penalty'] = actual_penalty  # Replace optimistic penalty

    # Rank options
    sorted_options = sort(options, by=['penalty', 'combined_score'])

    # Format as natural language via LLM
    message = format_utility_message(sorted_options, current_option)
    send_message(recipient=recipient, content=message)
END FOR
```

**Key Point:** The "current" penalty is recomputed using ACTUAL agent assignments, not the best possible assignments for that boundary. This prevents agents from understating their current penalty.

---

## Summary of When Agents Change Colors

An agent changes its color assignments when:

1. **Forced by human** - "change b2 to blue"
   - Applied immediately in compute_assignments()
   - NOT overridden by snap-to-best (fixed in latest version)

2. **Greedy finds better solution** - boundary changes make new colors viable
   - assignments_changed=True
   - NOT overridden by snap-to-best (fixed in latest version)

3. **Snap-to-best triggers** - greedy got stuck and exhaustive search finds major improvement
   - Only if: no forced assignments, greedy didn't change, improvement > threshold
   - Uses exhaustive search to find optimal assignment given boundary

An agent does NOT change colors when:

1. **Current assignment is locally optimal** - no better option given boundary
2. **Greedy already changed this turn** - trust greedy's choice
3. **Human forced specific colors** - respect human intent
4. **Improvement too small** - snap threshold not met

---

## Common Issues and Debugging

### Issue: "Agent says it will change but doesn't"

**Cause:** Snap-to-best was overriding greedy/forced assignments

**Fix:** Snap now skips when:
- Forced assignments were just applied
- Greedy just found a new solution

**How to Verify:**
Check agent log for:
```
Clearing forced_local_assignments: {'b2': 'blue'}
Skipping snap-to-best: forced assignments just applied
```

### Issue: "Agent claims satisfied but penalty > 0"

**Cause:** Color case mismatch (neighbor="red", assignment="Red")

**Fix:**
- All colors now normalized to domain casing
- Defensive conflict detection with case-insensitive comparison
- Double-check satisfaction against actual penalty

**How to Verify:**
Check agent log for:
```
BOUNDARY CONFLICT DETECTED: b2(red) <-> h2(red)
Not satisfied: current_penalty=10.000 > 0
```

If you see "CRITICAL BUG: Agent claims satisfied but penalty>0", the bug is still present.

### Issue: "Agent never changes even when it should"

**Possible Causes:**
1. **Greedy stuck** - current assignment locally optimal given boundary
2. **Fixed nodes** - nodes locked to specific colors
3. **Snap threshold too high** - improvement exists but < 5.0

**How to Debug:**
Check agent log for:
```
Assignments unchanged: {'b1': 'blue', 'b2': 'red', ...}
WARNING: Assignments didn't change despite penalty=10.0
Skipping snap-to-best: improvement too small (pen 10.0 -> 8.0, threshold=5.0)
```

If snap threshold is too high, reduce `improvement_threshold` in cluster_agent.py:644

---

## Pseudocode for Full Agent Turn

```
AGENT.step():
    # 1. Receive and parse message
    IF message received:
        parse_message()
        extract_forced_assignments()
        update_neighbour_assignments()
    END IF

    # 2. Log state
    LOG current_state, boundary_knowledge

    # 3. Run optimization algorithm
    old = self.assignments
    new = compute_assignments()  # Respects forced, considers boundary
    changed = (new != old)

    # 4-5. Apply assignments
    self.assignments = new

    # 6. Clear forced
    forced_used = has_forced_assignments()
    clear_forced_assignments()

    # 7. Snap-to-best (with safeguards)
    IF not forced_used AND not changed AND big_improvement_available():
        self.assignments = exhaustive_search_best()
        changed = True
    END IF

    # 8. Update satisfaction
    self.satisfied = compute_satisfied()  # Defensive conflict checks

    # 9. Respond to human
    IF human_message:
        response = generate_llm_response()
        send_to_human(response)
    END IF

    # 10. Send utility messages to other agents
    FOR each other_agent:
        utility_msg = compute_counterfactuals()
        send_to_agent(utility_msg)
    END FOR
END FUNCTION
```

---

## Recommendations for Improvement

1. **Make snap threshold configurable** - different problems may need different thresholds
2. **Add "explain decision" mode** - agent logs WHY it chose each color
3. **Visualize greedy vs snap** - show what greedy wanted vs what snap forced
4. **Track satisfaction history** - detect oscillation (satisfied → unsatisfied → satisfied...)
5. **Log counterfactual reasoning** - show agent's belief about "if human changes X, I could do Y"
