# RB Mode Fixes - Complete Summary

## Issues Fixed

### 1. Agent2 Boundary Update Spam ✅
**File**: `agents/rule_based_cluster_agent.py:402-405`

**Problem**: Agent2 was sending identical "boundary_update" messages repeatedly when satisfied and nothing changed.

**Fix**: Added check to suppress updates when `self.satisfied=True` and `needs_update=False`:
```python
if self.satisfied:
    self.log(f"[RB Move Gen] ✓ Already satisfied and no changes - not sending redundant boundary update")
    return None
```

---

### 2. RB Protocol JSON Misinterpretation ✅
**File**: `agents/cluster_agent.py:3001-3005`

**Problem**: Parent class was extracting assignments from RB protocol JSON messages, treating `impossible_conditions` as actual assignments.

**Fix**: Skip assignment extraction from RB protocol messages:
```python
is_rb_protocol = text.strip().startswith('[rb:{')
if not is_complaint and not is_rb_protocol and text.strip():
    # Only extract from non-RB messages
```

---

### 3. Overly Strict Self-Validation ✅
**File**: `agents/rule_based_cluster_agent.py:1212-1216`

**Problem**: Self-validation rejected offers with penalty>0 even when that was the best available.

**Fix**: Removed the check that required penalty≈0 after filtering impossible conditions.

---

### 4. Accepted Assignments Not Locked ✅
**File**: `agents/rule_based_cluster_agent.py:1608-1615`

**Problem**: After accepting an offer, the greedy solver immediately overwrote the accepted assignments.

**Fix**: Lock accepted assignments using `forced_local_assignments`:
```python
# CRITICAL FIX: Lock accepted assignments so solver doesn't overwrite them
self.forced_local_assignments[assignment.node] = assignment.colour
self.log(f"[RB Process] -> LOCKED {assignment.node}={assignment.colour}")
```

---

### 5. Require Penalty≈0 for ALL Conditional Offers ✅
**File**: `agents/rule_based_cluster_agent.py:950-978` and `1018-1034`

**Problem**: Agents were sending conditional offers with penalty=10 instead of penalty=0.

**Fix**: Enforced strict requirement that ALL conditional offers must achieve penalty ≤ 0.1:
```python
# CRITICAL FIX: ALL conditional offers must achieve penalty≈0
penalty_tolerance = 0.1
if best_config is None or best_penalty > penalty_tolerance:
    self.log(f"[RB Move Gen] REJECTED - All conditional offers must achieve penalty≈0")
    return None
```

Also fixed alternative solution logic to require penalty≈0:
```python
# CRITICAL: Only accept zero-penalty alternatives
penalty_tolerance = 0.1
if alt_penalty <= penalty_tolerance:
    # Accept
else:
    return None
```

---

### 6. Auto-Send Conditional Offer After Feasibility Check ✅
**File**: `agents/rule_based_cluster_agent.py:1744-1775`

**Problem**: After answering a feasibility query with "Yes, if...", the agent didn't proactively offer that configuration. The human had no way to signal they'd chosen those colors without manually clicking "Send Config".

**Fix**: After sending a positive feasibility response, automatically generate and send a conditional offer with those exact conditions:
```python
# CRITICAL: Proactively send a conditional offer with these exact conditions
self.log(f"[RB Feasibility] Generating proactive conditional offer...")
self.rb_force_conditional_generation[sender] = True
try:
    offer = self._generate_conditional_offer(sender)
    if offer:
        msg_text = format_rb(offer) + " " + pretty_rb(offer)
        self.send(sender, msg_text)
        self.log(f"[RB Feasibility] ✓ Sent proactive conditional offer")
        # Track offer...
finally:
    self.rb_force_conditional_generation.pop(sender, None)
```

---

### 7. UI Logging Spam ✅
**File**: `ui/human_turn_ui.py:3784-3827`

**Problem**: Convergence check was printing verbose logs every 400ms (even when nothing changed), creating console spam that made debugging impossible.

**Fix**: Reduce convergence check logging spam:
```python
def _check_rb_full_commitment(self) -> bool:
    # Removed verbose logging - only log when convergence achieved
    # print(f"[RB Convergence] Checking commitment...")

    # Only keep error logging and final success message
    print("[RB Convergence] All parties satisfied - consensus reached!")
    return True
```

---

### 8. JSON Parsing Error in Transcript ✅
**File**: `ui/human_turn_ui.py:3010-3118`

**Problem**: UI was using a fragile regex to extract JSON from RB protocol messages, causing "Extra data: line 1 column 225" errors during parsing. The regex `\[rb:(\{.+\})\]` with greedy matching was error-prone with nested JSON.

**Fix**: Use the existing `parse_rb()` function which has proper brace-counting logic:
```python
# OLD (fragile):
rb_match = re.search(r'\[rb:(\{.+\})\]', line, re.DOTALL)
if rb_match:
    rb_data = json.loads(rb_match.group(1))

# NEW (robust):
from comm.rb_protocol import parse_rb
rb_move = parse_rb(line)
if rb_move:
    rb_data = {
        "move": rb_move.move,
        "node": rb_move.node,
        # ... extract all fields from rb_move object
    }
```

---

### 9. Agents Auto-Announcing at Startup ✅
**File**: `ui/human_turn_ui.py:3707-3725`

**Problem**: Agents were automatically announcing configurations at UI startup, breaking the blind announcement workflow where the human should announce first.

**Fix**: Disable auto-start in RB mode:
```python
def _agent_start(self, neigh: str) -> None:
    # In RB mode, agents shouldn't auto-announce at startup
    # The human announces first by clicking "Announce Configuration" button
    if hasattr(self, '_rb_structured_mode') and self._rb_structured_mode:
        return  # Don't start agents automatically
```

---

### 10. Config Offers Blocking Agent Messages ✅
**File**: `agents/rule_based_cluster_agent.py:1357-1361`

**Problem**: After announcing configurations, agents tracked config offers as "active offers" requiring responses. This made agents wait forever for acknowledgments and go silent (not sending conditional offers).

**Fix**: Don't track config offers - they're informational announcements, not proposals:
```python
# CRITICAL FIX: Do NOT track config offers as active offers!
# Config announcements are informational - they don't require responses.
# If we track them, agents will wait forever for acknowledgments.
print(f"[{self.name}] Config offer {offer_id} NOT tracked (announcements don't need responses)")
```

---

### 11. Agents Not Becoming Satisfied After Acceptance ✅ **CRITICAL**
**File**: `agents/rule_based_cluster_agent.py:1607-1610`

**Problem**: When human accepted an offer, agent locked the assignments but DIDN'T mark them as "proposed" to the human. The satisfaction check failed because it thought the human hadn't been informed about those nodes yet.

**Fix**: Mark accepted assignments as "proposed" to sender:
```python
# CRITICAL FIX: Mark as proposed to sender so satisfaction check passes
# When human accepts our offer, we've now "proposed" these nodes to them
self.rb_proposed_nodes.setdefault(sender, {})[assignment.node] = assignment.colour
self.log(f"[RB Process] -> MARKED AS PROPOSED: {sender} now knows {assignment.node}={assignment.colour}")
```

**This was the final missing piece!** Agents now correctly become satisfied when you accept their offers.

---

## Expected Workflow Now

1. **Human Configuration** (BLIND): Human sets their initial node colors without seeing agent configurations
2. **Human Announcement**: Human clicks "Announce Configuration" button
3. **Phase Transition**: UI sends `__ANNOUNCE_CONFIG__` to each agent, triggering transition from "configure" to "bargain" phase
4. **Agent Configuration**: Agents announce their initial boundary states with empty conditions
5. **Conditional Offers**: Agents ONLY send offers with penalty≈0
6. **Feasibility Query**:
   - Human: "Is h1=green feasible?"
   - Agent: "Yes, if h4=red" (feasibility response)
   - Agent: **Immediately sends** "If h1=green AND h4=red, then a2=..., a4=..., a5=..." (conditional offer)
7. **Acceptance**:
   - Human accepts the conditional offer
   - Agent locks those assignments (can't be overwritten by solver)
   - Agent becomes satisfied if penalty=0
8. **Satisfaction**: Agent stops sending messages when satisfied and nothing changes

## Key Principles

1. **Phase transition is required** - agents need `__ANNOUNCE_CONFIG__` to start
2. **ALL conditional offers must have penalty≈0** - just like feasibility checks
3. **Accepted assignments are locked** - solver respects commitments
4. **Feasibility checks trigger proactive offers** - closing the communication loop
5. **Satisfied agents don't spam** - once done, stay quiet
6. **Minimal logging** - convergence checks run every 400ms but only log when state changes
7. **Robust parsing** - use `parse_rb()` function for proper JSON extraction, not fragile regex

## Testing

To verify fixes work:
1. Run RB mode: `python run_experiment.py --method RB --use-ui`
2. Reject an agent's first offer marking a condition impossible
3. Ask a feasibility query about a different configuration
4. Agent should respond with feasibility AND immediately send a matching conditional offer
5. Accept that offer
6. Agent should lock assignments and become satisfied
7. Agent should stop sending messages (no spam)
