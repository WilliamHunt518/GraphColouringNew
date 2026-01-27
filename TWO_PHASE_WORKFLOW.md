# Two-Phase Workflow: Configure → Bargain

## Overview

Implemented a two-phase workflow for conditional offer negotiation:

1. **Configure Phase**: Everyone sets up their initial assignments independently (blind)
2. **Bargain Phase**: Conditional offers based on initial configurations

## User Workflow

### Phase 1: Configure

1. **Human** sets up graph by clicking nodes to assign colors
2. **Agents** compute their local optimal assignments (done automatically)
3. **Human** clicks "Announce Configuration" button when ready
4. System transitions to Bargain phase

### Phase 2: Bargain

1. Agents announce their initial configurations as unconditional offers
2. Human can now:
   - Select specific agent assignments as conditions
   - Build conditional offers: "IF agent does X, THEN I'll do Y"
   - Accept/counter agent's conditional offers
3. If configuration is impossible: Click "Impossible to Continue"

## UI Changes

### Top Button Bar (RB Mode Only)

Added three new controls:

1. **Phase Label**: Shows current phase ("Phase: Configure" or "Phase: Bargain")
2. **"Announce Configuration" Button**:
   - Enabled in Configure phase
   - Transitions to Bargain phase when clicked
   - Sends `__ANNOUNCE_CONFIG__` to agents
3. **"Impossible to Continue" Button**:
   - Disabled in Configure phase
   - Enabled in Bargain phase
   - Signals deadlock (`__IMPOSSIBLE__`)

### Conditional Offer Builder

**Configure Phase**:
- Disabled (grayed out)
- Help text: "CONFIGURE PHASE: Set up your graph, then click 'Announce Configuration' to begin bargaining" (red text)

**Bargain Phase**:
- Enabled
- Help text: "BARGAIN PHASE: Build conditional offers..." (gray text)

## Agent Behavior

### Configure Phase

- Agents compute local optimal assignments
- **No messages sent** - agents wait silently
- Assignments are computed but not announced

### Receiving `__ANNOUNCE_CONFIG__`

When agent receives this message:
1. Logs phase transition
2. Sets `self.rb_phase = "bargain"`
3. **Immediately sends configuration announcement** as ConditionalOffer with:
   - Empty conditions (unconditional)
   - All boundary node assignments in one message
   - Reason: "initial_configuration"

Example:
```
ConditionalOffer: IF [] THEN a1=red AND a2=blue AND a3=green
Reasons: ["initial_configuration", "phase_transition"]
```

### UI Updates from Configuration Announcement

When UI receives configuration announcement:
1. **Updates `_known_neighbour_colours`**: Agent node colors stored
2. **Redraws graph**: Neighbor nodes now show their colors
3. **Displays special message**: "📢 Configuration Announced: a1=red, a2=blue, a3=green"
4. **Populates condition dropdown**: Each assignment becomes selectable

### Bargain Phase

- Agents send one unconditional offer per boundary node for subsequent changes
- Each assignment is selectable by human as a condition
- Normal conditional offer protocol proceeds
- Graph continuously updated with neighbor colors

## Implementation Details

### UI State (ui/human_turn_ui.py)

```python
# Added state variables:
self._phase: str = "configure"  # Track current phase
self._initial_configs: Dict[str, Dict[str, str]] = {}  # Store initial configs
self._rb_help_labels: Dict[str, tk.Label] = {}  # Update help text per phase
```

### UI Methods

```python
def _announce_configuration(self):
    """Transition from configure to bargain phase."""
    # 1. Store human's configuration
    # 2. Send __ANNOUNCE_CONFIG__ to all agents
    # 3. Update phase to "bargain"
    # 4. Enable conditional builders
    # 5. Update UI labels/buttons

def _signal_impossible(self):
    """Signal that configuration is impossible."""
    # Send __IMPOSSIBLE__ to all agents
    # Log the event
```

### Agent State (agents/rule_based_cluster_agent.py)

```python
# Added state variable:
self.rb_phase: str = "configure"  # Track agent's phase
```

### Agent Logic

```python
def step(self):
    # ... compute assignments ...

    # In configure phase, don't send any moves
    if self.rb_phase == "configure":
        return

    # In bargain phase, proceed with move generation
    # ...

def receive(self, message):
    # Handle __ANNOUNCE_CONFIG__
    if message.content == "__ANNOUNCE_CONFIG__":
        self.rb_phase = "bargain"
        # On next step, announce configuration
        return

    # Handle __IMPOSSIBLE__
    if message.content == "__IMPOSSIBLE__":
        self.log("Configuration impossible")
        return

    # Normal RB protocol parsing
    # ...
```

### Simulation Layer (cluster_simulation.py)

Added special tokens to `is_special` check:
```python
is_special = (text in ["__INIT__", "__PASS__", "__ANNOUNCE_CONFIG__", "__IMPOSSIBLE__"])
```

These don't count as human actions and don't deliver messages to agents - just trigger steps.

## Button Closure Bug Fix

### Problem

Clicking "Add Condition" or "Add Assignment" in Agent1's panel was adding rows to Agent2's panel (the last panel in the loop).

### Root Cause

Lambda closures were capturing references to loop variables that changed by the time buttons were clicked.

### Solution

Capture both neighbor ID and container in lambda's **default arguments** (evaluated at definition time):

```python
# Before (WRONG):
add_condition_btn = ttk.Button(..., command=lambda n=neigh: add_condition_row(n))

# After (CORRECT):
add_condition_btn = ttk.Button(..., command=lambda n=neigh, c=conditions_container: add_condition_row(n, c))
```

This ensures each button captures its own unique container reference at loop iteration time.

## Benefits

### 1. Clearer Workflow
- Explicit phase separation
- No confusion about when to start bargaining
- Human controls timing of phase transition

### 2. Better Starting Point
- Agents announce their actual working configurations
- Human can see what agents computed
- Conditional offers build on real assignments, not abstract proposals

### 3. Meaningful Conditionals
- Conditions reference specific actual assignments
- "IF a1=red" means "if agent keeps their announced color"
- More concrete and actionable

### 4. Deadlock Detection
- "Impossible to Continue" provides explicit signal
- Can log and analyze failure cases
- Could trigger automatic reconfiguration

## Testing Checklist

- [ ] Configure phase: Conditional builder is disabled
- [ ] Configure phase: Help text shows red message
- [ ] Clicking "Announce Configuration" enables conditional builder
- [ ] Clicking "Announce Configuration" transitions phase label to "Bargain"
- [ ] Agents don't send messages in configure phase
- [ ] Agents announce configuration when receiving __ANNOUNCE_CONFIG__
- [ ] "Impossible to Continue" is disabled in configure phase
- [ ] "Impossible to Continue" is enabled in bargain phase
- [ ] Clicking "Impossible to Continue" logs event
- [ ] Button closure bug fixed: Adding rows adds to correct agent panel

## Example Session

```
[CONFIGURE PHASE]
Human: Sets h1=red, h2=blue, h3=green (visible on graph)
Agent1: Computes a1=blue, a2=red (NOT visible yet)
Agent2: Computes a3=green, a4=yellow (NOT visible yet)

Human clicks: "Announce Configuration"

[System logs]
[UI] Human config stored: {h1: red, h2: blue, h3: green}
[Agent1] Received __ANNOUNCE_CONFIG__
[Agent1] Transitioning to BARGAIN phase
[Agent1] Sending configuration: a1=blue, a2=red
[Agent2] Received __ANNOUNCE_CONFIG__
[Agent2] Transitioning to BARGAIN phase
[Agent2] Sending configuration: a3=green, a4=yellow

[BARGAIN PHASE - Human sees:]

Chat Transcript:
[Agent1] 📢 Configuration Announced: a1=blue, a2=red
[Agent2] 📢 Configuration Announced: a3=green, a4=yellow

Graph Updates:
- a1, a2 nodes now show in BLUE, RED (Agent1's colors)
- a3, a4 nodes now show in GREEN, YELLOW (Agent2's colors)
- h1, h2, h3 still show your RED, BLUE, GREEN

Condition Dropdown (Agent1):
#1: a1=blue
#1: a2=red

Condition Dropdown (Agent2):
#1: a3=green
#1: a4=yellow

Human builds conditional offer:
IF a1=blue AND a2=red THEN h1=red AND h4=yellow
Human sends offer

[Conditional bargaining proceeds...]
```

## Files Modified

1. **ui/human_turn_ui.py** (lines 91-98, 261-274, 589-609, 2764-2824)
   - Added phase tracking state
   - Added phase control buttons
   - Added `_announce_configuration()` and `_signal_impossible()` methods
   - Phase-aware conditional builder (disabled in configure)
   - Fixed button closure bug

2. **agents/rule_based_cluster_agent.py** (lines 97-100, 116-121, 591-635)
   - Added `rb_phase` state variable
   - Check phase in `step()` - skip move generation in configure
   - Handle `__ANNOUNCE_CONFIG__` and `__IMPOSSIBLE__` in `receive()`

3. **cluster_simulation.py** (lines 708-713)
   - Added `__ANNOUNCE_CONFIG__` and `__IMPOSSIBLE__` to special tokens list

## Future Enhancements

1. **Visual Phase Indicator**: Color-code graph borders by phase
2. **Configuration History**: Show initial vs current assignments
3. **Automatic Reconfiguration**: On "Impossible", trigger automatic adjustment
4. **Configuration Export**: Save/load initial configurations for experiments
5. **Phase-specific Penalties**: Different penalty displays per phase
