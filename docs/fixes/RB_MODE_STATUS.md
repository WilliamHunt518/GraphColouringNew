# RB Mode: Current Status and Known Issues

**Last Updated**: 2026-01-28

## Current State

RB (Rule-Based) mode is **mostly working** but has some limitations.

### ✅ What Works

1. **Agents send configuration announcements** when you click "Announce Config"
2. **Agents send status updates** when you click "Pass" and their boundary nodes change
3. **Agents accept good offers** when you propose beneficial configurations
4. **Agents reject bad offers** that would increase their penalty
5. **Agents generate conditional offers** with IF/THEN structure when conflicts exist
6. **Agents learn from rejections** and try to propose alternatives (with bugs - see below)
7. **UI displays offers properly** in conditionals panel and chat transcript

### ⚠️ Known Issues

#### Issue #1: Alternatives Have Same Penalty

**Problem**: When you reject an offer, agent tries to find alternatives but often they have the same penalty. Agent was refusing to propose them because they weren't "better", so it sends nothing.

**Status**: JUST FIXED (needs restart)
- Agent now accepts alternatives with same penalty or up to +20 penalty threshold
- Agent will explore suboptimal solutions after rejection

**How to Verify**:
```bash
# Restart UI, then check logs after rejecting an offer:
grep "Found alternative solution" results/rb/Agent1_log.txt
# Should see: "Found alternative solution with penalty=10.000 (was 10.000)"
```

#### Issue #2: Limited Alternative Exploration

**Problem**: Agent's exhaustive search might not find many alternatives if the problem is highly constrained.

**Example**: If there are only 2-3 valid configurations and you reject the best one, agent might struggle to find acceptable alternatives.

**Workaround**:
- Try adjusting your own colors to create more flexibility
- Use "Announce Config" to restart negotiation with different initial state

#### Issue #3: No Negative Conditionals

**Problem**: You cannot tell the agent "IF you insist on h4=green, THEN I cannot satisfy constraints."

**Current**: You can only Reject (says "no") but not explain WHY (impossible configuration).

**Status**: Feature not implemented yet
- Rejection learning helps but doesn't solve this completely
- Agent learns "Human rejected h4=green" but not "h4=green makes Human's problem unsolvable"

**Possible Solutions**:
1. Add "Reject with reason" button that lets you specify which nodes are problematic
2. Add negative conditional builder: "IF [conditions] THEN IMPOSSIBLE"
3. Add free-text explanation field for rejections

### 📝 Session History

All debug notes and fix documentation moved to `docs/session-notes/`:

**Key Documents**:
- `BUGS_FIXED_SUMMARY.md` - Original 4 critical bugs fixed
- `FIX_COMPLETE.md` - Priority 0 boundary announcements
- `PASS_BUTTON_FIXED.md` - Status updates now visible in UI
- `CONDITIONAL_OFFERS_FIXED.md` - Agents generate IF/THEN proposals
- `REJECTION_LEARNING_FIXED.md` - Agents learn from rejections
- `CRITICAL_ISSUES_FOUND.md` - Root cause analysis

### 🧪 Testing Workflow

**Successful negotiation example**:

```
1. Launch: python launch_menu.py
2. Select RB mode
3. Click "Announce Config" ONCE
4. Wait for agent config announcements
5. Click "Pass" on each agent → Status updates appear
6. Click "Pass" again → Conditional offers appear (IF/THEN)
7. Accept good offers OR reject and repeat step 6
8. Agents adapt proposals based on rejections
9. Eventually converge to mutual agreement
```

**Check logs**:
```bash
# Agent responses:
tail -50 results/rb/communication_log.txt

# Agent reasoning:
grep "Priority 0\|Priority 2\|Priority 4" results/rb/Agent1_log.txt | tail -20

# Rejection learning:
grep "Stored rejected\|Finding alternative" results/rb/Agent1_log.txt
```

### 🔧 Files Modified (This Session)

1. **agents/rule_based_cluster_agent.py**
   - Priority 0: Boundary change announcements
   - Rejection learning: Track and avoid rejected conditions
   - Alternative exploration: Accept same-penalty or slightly worse solutions
   - Bug fixes: Offer tracking, duplicate prevention, satisfaction checks

2. **ui/human_turn_ui.py**
   - Show boundary updates in conditionals panel
   - Label them as "Status Update" (not "Offer")
   - Display rejection button
   - Hide action buttons for status updates

3. **comm/rb_protocol.py**
   - Added "Reject" to protocol
   - Pretty printing for rejection messages

4. **cluster_simulation.py**
   - Include reasons field in extracted offers
   - Pass reasons to UI for boundary_update detection

### 🚀 Next Steps

**Immediate** (requires restart):
- Test alternative proposal after rejection
- Verify agent proposes different conditions

**Short-term enhancements**:
1. Add negative conditionals: "IF X THEN IMPOSSIBLE"
2. Better alternative search (heuristics for constrained problems)
3. Track individual node-color rejections (not just combinations)
4. Add explanation field for rejections

**Medium-term**:
1. Agent preference learning (learn which configurations Human prefers)
2. Multi-round negotiation memory (remember across multiple problems)
3. Explanation generation (agent explains why it needs certain conditions)

### 📊 Success Metrics

**Good Negotiation**:
- Agent proposes 2-3 different conditional offers
- Human accepts one within 5 rounds
- System converges to penalty=0 for all agents

**Bad Negotiation** (indicates issues):
- Agent repeats same offer >3 times (rejection learning broken)
- Agent sends only status updates, no conditional offers (Priority 2/4 blocked)
- Agent proposes nothing after rejection (no alternatives found)
- System doesn't converge after 10+ rounds (problem over-constrained)

### 🐛 Debugging Commands

```bash
# Check agent phase and penalties:
grep "phase\|penalty" results/rb/Agent1_log.txt | tail -20

# Check what agent is proposing:
grep "ConditionalOffer Gen" results/rb/Agent1_log.txt | tail -20

# Check rejection learning:
grep "rejected" results/rb/Agent1_log.txt | tail -20

# Check message flow:
tail -30 results/rb/communication_log.txt

# Full agent reasoning trace:
tail -200 results/rb/Agent1_log.txt
```

### 📁 File Organization

```
GraphColouringNew/
├── CLAUDE.md                    # Main project instructions
├── README.md                    # User guide
├── RB_MODE_STATUS.md           # This file - current status
├── docs/
│   └── session-notes/          # All debug/fix documentation (48 files)
├── logs/
│   └── old/                    # Old log files (moved from root)
├── results/rb/                 # Current session logs
│   ├── Agent1_log.txt
│   ├── Agent2_log.txt
│   ├── Human_log.txt
│   └── communication_log.txt
└── [source code files...]
```

### 💡 Tips

1. **Always restart UI** after code changes (Python caches modules)
2. **Click "Announce Config" only ONCE** per round (resets negotiation state)
3. **Check logs** if behavior seems wrong (agents log every decision)
4. **Use Pass liberally** to let agents think and propose
5. **Reject freely** - agents learn from rejections and adapt
6. **Be patient** - exhaustive search can take a few seconds for complex configs

---

## Recent Changes

### 2026-01-28 Session

**Fixed**:
- ✅ Agents never accepting offers (offer ID parsing bug)
- ✅ Agents never making offers (Priority 0 blocking Priorities 2/4)
- ✅ Pass button doing nothing (boundary updates filtered out by UI)
- ✅ Agents repeating same offer (no rejection learning)
- ✅ Agents refusing alternatives with same penalty (too strict threshold)

**Added**:
- ✅ Priority 0 boundary announcements
- ✅ Rejection learning with condition tracking
- ✅ Alternative exploration after rejection
- ✅ Status update cards in UI
- ✅ Comprehensive session documentation

**Remaining**:
- ⚠️ Negative conditionals (not implemented)
- ⚠️ Limited alternatives in constrained problems (inherent limitation)
- ⚠️ No explanation for rejections (UI limitation)

