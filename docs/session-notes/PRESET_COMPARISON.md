# Preset Comparison: Test Scenario Difficulty Levels

## Quick Reference

| Difficulty | Fixed Nodes | Spinbox Value | Valid Configs (Agent1) | h1 Options | h4 Options | Recommended Use |
|------------|-------------|---------------|------------------------|------------|------------|-----------------|
| **EASY** | 1 per agent | 1 | ~6/9 (67%) | Any color | Any color | Test communication & basic negotiation |
| **MEDIUM** | 2 per agent | 2 | 4/9 (44%) | green/blue only | green/red only | Test reasoning under constraints |
| **HARD** | 3 per agent | 3 | ~2/9 (22%) | Very limited | Very limited | Test advanced planning (may be unsolvable!) |

## Detailed Comparison

### EASY Mode (1 Fixed Node) ⭐☆☆
**File**: `PRESET_EASY_1_FIXED_NODE.md`

**Spinbox Setting**: 1

**Fixed Nodes**:
- Agent1: 1 internal node (e.g., a1=green)
- Agent2: 1 internal node (e.g., b1=blue)
- Human: h3=green

**Characteristics**:
- ✅ Most boundary configurations work
- ✅ Easy to find solutions by trial and error
- ✅ Agents rarely say "impossible"
- ✅ Good for testing basic communication flow
- ⚠️ May not require deep planning

**Example Dialogue**:
```
You: "h1=red, h4=red"
Agent1: "Your boundary works! No conflicts."
```

**Use Cases**:
- First-time testing
- Verifying agent communication works
- Testing basic negotiation between agents
- Quick iteration on prompts/responses

---

### MEDIUM Mode (2 Fixed Nodes) ⭐⭐☆ **← RECOMMENDED**
**File**: `PRESET_MEDIUM_2_FIXED_NODES.md`

**Spinbox Setting**: 2

**Fixed Nodes**:
- Agent1: a1=green, a3=blue
- Agent2: b1=blue, b3=green
- Human: h3=green

**Characteristics**:
- ⚠️ Some boundary values are **impossible** (e.g., h1=red fails)
- ✅ Solutions exist but require understanding constraints
- ✅ Forces agents to explain "why not" clearly
- ✅ Requires coordination between both agents
- ✅ Tests renegotiation dynamics you wanted

**Example Dialogue**:
```
You: "I need to make h1 red"
Agent1: "h1=red doesn't work - conflicts with my fixed nodes a1=green and a3=blue.
         Try h1=green or h1=blue instead."

You: "OK, h1=green, h4=red"
Agent1: "That works for me!"
Agent2: "But h2=red, h5=blue doesn't work for me. Try h2=blue, h5=green."

You: [Find global solution that satisfies both]
```

**Use Cases**:
- **Testing agent reasoning** about constraints
- **Testing "impossible" scenario handling**
- Simulating realistic coordination problems
- Testing multi-step negotiation
- **Your stated use case**: "need to renegotiate" dynamics

**Why It's Better Than Easy**:
- Actually tests if agents understand their constraints
- Forces explicit reasoning about WHY things don't work
- Creates realistic back-and-forth negotiation
- Not trivial, but not unsolvable

---

### HARD Mode (3 Fixed Nodes) ⭐⭐⭐
**File**: `PRESET_HARD_3_FIXED_NODES.md` (not yet created)

**Spinbox Setting**: 3

**Fixed Nodes**:
- Agent1: 3 internal/boundary nodes fixed
- Agent2: 3 internal/boundary nodes fixed
- Human: h3=green + possibly more

**Characteristics**:
- ⚠️ Very constrained search space (~20% valid configs)
- ⚠️ **May have NO SOLUTION** for some scenarios
- ⚠️ Requires exhaustive search to verify
- ✅ Tests advanced planning capabilities
- ❌ May be frustrating for human participants

**Example Dialogue**:
```
You: "Can we make h1=red?"
Agent1: "No, impossible with my 3 fixed nodes."

You: "What about h1=green?"
Agent1: "h1=green only works if h4=red."

You: "OK, h1=green, h4=red"
Agent1: "That works for me."
Agent2: "But there's NO configuration of h2 and h5 that works given your h1 and h4!"

You: [Stuck - may need to backtrack completely]
```

**Use Cases**:
- Testing agent behavior when problems are unsolvable
- Testing backtracking and explanation
- Research scenarios (not participant studies)
- Stress testing search algorithms

**Warning**: This may be TOO hard. Some configurations may genuinely have no solution, which could be frustrating for testing.

---

## Recommendation

### For Your Use Case ("renegotiation dynamics")

**Use MEDIUM (2 fixed nodes)** because:

1. ✅ Creates the renegotiation you wanted
   - "Agent1 happy → adjust for Agent2 → Agent1 now conflicts → renegotiate"

2. ✅ Solutions exist (not impossible)
   - You can always find a global solution with enough coordination

3. ✅ Tests constraint reasoning
   - Agents must explain WHY certain values don't work
   - Not just "penalty > 0" but "because X conflicts with fixed node Y"

4. ✅ Representative difficulty
   - Mimics real distributed constraint problems
   - Not trivial, not impossible

### How to Switch Between Presets

**In the launcher**:
1. Find "Fixed nodes per cluster (0-3)" spinbox
2. Set to **1** for EASY
3. Set to **2** for MEDIUM
4. Set to **3** for HARD (if you create it)

**Current Default**: The launcher now defaults to **1** (EASY mode)

**To use MEDIUM**: Just change the spinbox to **2** before launching

---

## Observed Ground Truth (From Last Run)

When you ran with **2 fixed nodes**, the ground truth showed:

### Agent1
```
Valid Configurations: 4/9 (44%)
  1. h1=green, h4=red    ✓
  2. h1=green, h4=green  ✓
  3. h1=blue, h4=red     ✓
  4. h1=blue, h4=green   ✓

Invalid: ALL h1=red configs (5/9)
```

### Agent2
```
Valid Configurations: 2/9 (22%)
  1. h2=green, h5=blue   ✓
  2. h2=blue, h5=green   ✓

Invalid: All other configs (7/9)
```

**This is PERFECT MEDIUM difficulty**: Constrained but solvable!

---

## Testing Workflow

### Phase 1: Test EASY (Spinbox = 1)
1. Verify agents communicate clearly
2. Test basic negotiation
3. Confirm UI works
4. **Expected time**: 5-10 minutes

### Phase 2: Test MEDIUM (Spinbox = 2) ← **YOUR TARGET**
1. Test "impossible value" handling (e.g., h1=red)
2. Test agent explanations of WHY
3. Test multi-agent coordination
4. Observe renegotiation dynamics
5. **Expected time**: 10-15 minutes

### Phase 3: (Optional) Test HARD (Spinbox = 3)
1. Test behavior under extreme constraints
2. Test detection of unsolvable scenarios
3. Research use only
4. **Expected time**: 15+ minutes (or may not solve)

---

## Summary

- **EASY (1 fixed)**: Communication testing
- **MEDIUM (2 fixed)**: Coordination testing ← **USE THIS**
- **HARD (3 fixed)**: Stress testing (may be unsolvable)

The **MEDIUM** preset is exactly what you described: forces renegotiation, creates constraint challenges, but remains solvable.
