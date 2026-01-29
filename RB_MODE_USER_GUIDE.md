# Rule-Based (RB) Mode - User Guide

## Overview

This is a **working baseline implementation** of rule-based negotiation with conditional offers. Human and agents negotiate graph coloring solutions using structured conditional proposals.

## Quick Start

1. **Launch**: `python launch_menu.py`
2. **Select**: Communication mode = `RB`
3. **Configure**: Default settings work out of the box
4. **Click**: Start Experiment

## Interface Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│ [Graph View]     │ [Agent1 Chat]        │ [Conditional Offers]     │
│                  │ [Agent2 Chat]        │ [Feasibility Queries]    │
│ Your nodes       │ Transcripts          │ Active deals            │
│ (click to edit)  │ Conditional Builder  │ Query results           │
└─────────────────────────────────────────────────────────────────────┘
```

## How to Negotiate

### 1. Check Feasibility (Optional)
Before committing, test if agents can work with your proposed colors:

1. Click **"Build Conditional Offer"** for an agent
2. Click **"+ Add Condition"**
3. Toggle **"Custom"** checkbox
4. Select YOUR node (e.g., h2) and color (e.g., blue)
5. Add more conditions if desired
6. Click **"Check Feasibility"** (NOT "Send Offer")
7. Wait ~1 second for result in right sidebar:
   - ✅ **Valid Coloring Possible** = Agent can achieve zero conflicts
   - ✗ **No Valid Coloring** = Can't work with those conditions

**Purpose**: "IF I set h2=blue AND h5=green, can YOU find a valid coloring?"

### 2. Send Conditional Offers
Propose: "IF you do X, THEN I'll do Y"

1. Click **"Build Conditional Offer"** for an agent
2. **IF section** (conditions - what you want from agent):
   - Click **"+ Add Condition"**
   - Select from dropdown (previous agent statements) OR
   - Toggle "Custom" to specify agent's nodes
3. **THEN section** (assignments - what you'll commit to):
   - Click **"+ Add Assignment"**
   - Select YOUR node and color
4. Click **"Send Offer"**

**Example**: "IF a2=red AND a3=blue THEN h5=green"

### 3. Respond to Agent Offers
When an agent sends a conditional offer, you see it in the right sidebar:

- **Accept**: Commits you to the conditions (your nodes change automatically)
- **Reject**: Opens dialog to mark impossible conditions:
  - **Individual**: Check conditions that are NEVER acceptable alone
  - **Combinations**: Build sets of 2+ conditions impossible together
- **Counter**: Modify the offer and send back

### 4. Pass Turn
Click **"Pass (let agent speak)"** if you have nothing to say but want the agent to act.

### 5. Reach Consensus
When satisfied with the solution:
1. Verify penalty = 0 (shown in HUD)
2. Agent will auto-signal satisfaction
3. UI closes automatically

## Key Features

### Feasibility Queries ✨
- **Non-binding**: Check without committing
- **Fast**: ~1 second response
- **Accurate**: Uses exhaustive search (guaranteed correct)
- **Persistent**: Results stay visible until dismissed

### Granular Rejection ✨
Mark specific impossibilities:
- **Individual**: "h1=red is NEVER acceptable"
- **Combination**: "h1=red AND h4=green together don't work, but each alone is OK"

Agents remember and avoid these in future offers.

### Conditional Builder
Per-agent builders allow different deals with each neighbor:
- Build offer for Agent1: "IF a2=red THEN h5=blue"
- Build different offer for Agent2: "IF b3=green THEN h2=red"

## Tips

### Understanding Feasibility
- ✅ **Valid Coloring Possible** = Zero conflicts achievable
- ✗ **No Valid Coloring** = Some conflicts remain
- **Only accept "Valid Coloring"** - any penalty means conflicts exist

### When to Use Feasibility Checks
- Before committing to colors with fixed nodes
- Testing if specific color combinations work
- Avoiding wasted offers that agents will reject

### Negotiation Strategy
1. **Start**: Check console hint for one valid solution
2. **Test**: Query if your preferred colors are feasible
3. **Offer**: Send conditional proposals
4. **Iterate**: Reject with specific impossibilities
5. **Accept**: When agent offers zero-conflict solution

## Console Output

At startup, you'll see:
```
============================================================
HINT: Here is one valid coloring solution for this problem:
============================================================
  Agent1: a1=red, a2=blue, a3=green
  Agent2: b1=green, b2=red, b3=blue
  Human: h1=red, h2=blue, h3=green
============================================================
Solution penalty: 0.0 (must be 0)
============================================================
```

**This is just one solution** - many others may exist. Use it as a reference.

## Validation

Before launching, the system:
1. **Checks solvability** using exhaustive search
2. **Halts if unsolvable** (no valid coloring exists)
3. **Shows complete solution** (no "?" marks)

**You will NEVER launch an unsolvable problem.**

## Known Limitations

This is a **baseline implementation**:

1. **UI complexity**: Current interface has many controls for research flexibility
2. **No undo**: Accepted offers immediately change your colors
3. **Manual consensus**: Must verify penalty=0 yourself
4. **No explanation**: Agents don't explain WHY conditions are infeasible

**Future versions may simplify the interface** based on experimental findings.

## Troubleshooting

### "No conditions" warning when checking feasibility
- **Cause**: Didn't add any conditions
- **Fix**: Click "+ Add Condition" first

### Feasibility says "Not Valid" but console shows solution
- **Cause**: Fixed bug (2026-01-29)
- **Fix**: Ensure you're using latest code

### Agent keeps offering same deal after acceptance
- **Cause**: Fixed bug (2026-01-29)
- **Fix**: Ensure you're using latest code

### UI error at end of session
- **Cause**: Fixed (2026-01-29)
- **Fix**: Added safety checks for UI cleanup

## Technical Details

### Algorithms
- **Validation**: Exhaustive search (guaranteed correct)
- **Feasibility checks**: Exhaustive search (matches validation)
- **Agents**: Configurable (default: greedy, but feasibility uses exhaustive)

### Message Protocol
- **Format**: JSON in `[rb:{...}]` tags
- **Moves**: ConditionalOffer, Accept, Reject, FeasibilityQuery, FeasibilityResponse
- **Conditions**: {node, colour, owner}
- **Assignments**: {node, colour}

### Performance
- Small clusters (6-9 nodes): Near-instant (<0.1s)
- Exhaustive search: O(colors^nodes)
- Typical: 3 colors, 6-9 nodes = 729-19,683 combinations

## Files Structure

```
agents/rule_based_cluster_agent.py  - Agent negotiation logic
comm/rb_protocol.py                 - Message protocol
ui/human_turn_ui.py                 - User interface
cluster_simulation.py               - Orchestration + validation
```

## Version History

### 2026-01-29: Initial Working Version
- ✅ Conditional offers (IF-THEN)
- ✅ Feasibility queries
- ✅ Granular rejection (individuals + combinations)
- ✅ Exhaustive validation (fail-fast on unsolvable)
- ✅ Accept/Reject/Counter workflow
- ✅ Fixed critical bugs (feasibility inconsistency, accept loop)

## Future Improvements (Not Implemented)

Potential simplifications based on experimental needs:
- Streamlined UI with fewer controls
- Auto-detection of impossible conditions
- Agent explanations for rejections
- Batch feasibility testing
- Undo/redo for offers
- Visual conflict highlighting

## Support

For issues or questions:
- Check `TROUBLESHOOTING.md`
- Check `CLAUDE.md` for project overview
- See `CRITICAL_BUGS_FIXED.md` for recent fixes
- Report issues at: (add your issue tracker)

---

**This is a research prototype.** The interface prioritizes flexibility and observability over simplicity. Future versions may streamline based on experimental findings.
