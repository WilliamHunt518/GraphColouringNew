# Preset Configuration: 2 Fixed Nodes Per Agent (MEDIUM Difficulty)

## Configuration
- **Fixed Nodes Per Agent**: 2
- **Random Seed**: 42 (deterministic)
- **Domain**: [red, green, blue]
- **Difficulty**: MEDIUM

## Resulting Fixed Nodes

With 2 fixed nodes per agent, the constraint space becomes significantly tighter:

### Agent1
- **Fixed Nodes**: a1=green, a3=blue (determined by seed 42)
- **Free Nodes**: a2, a4, a5
- **Boundary Nodes**: h1, h4

### Agent2
- **Fixed Nodes**: b1=blue, b3=green (determined by seed 42)
- **Free Nodes**: b2, b4, b5
- **Boundary Nodes**: h2, h5

### Human
- **Fixed Nodes**: h3=green
- **Free Nodes**: h1, h2, h4, h5
- **Boundary Nodes**: a2, a4, a5, b2

## Why This Is HARDER Than Easy Mode

### Easy Mode (1 Fixed Node)
- Agent1 had **6 valid boundary configs** out of 9 possible
- h1 could be: red, green, OR blue
- h4 could be: red, green, OR blue
- Very flexible - easy to find solutions

### Medium Mode (2 Fixed Nodes)
- Agent1 has **4 valid boundary configs** out of 9 possible (33% fewer)
- **h1 can ONLY be: green OR blue** (red is IMPOSSIBLE!)
- **h4 can ONLY be: green OR red** (blue is IMPOSSIBLE!)
- Much tighter constraints - requires careful planning

## Why h1=red Becomes Impossible

Looking at Agent1's connections:
```
h1 <-> a2
a2 <-> a1 (FIXED=green)
a2 <-> a3 (FIXED=blue)
a2 <-> a5
```

If h1=red:
- a2 cannot be red (conflicts with h1)
- a2 cannot be green (conflicts with FIXED a1=green)
- a2 cannot be blue (conflicts with FIXED a3=blue)
- **No valid color for a2!** → h1=red is impossible

This creates a **planning challenge**: You can't just set h1 to any color anymore. You need to understand the constraint network.

## Expected Test Dynamics (MEDIUM)

### Phase 1: Discovery
- You try: h1=red (natural choice)
- Agent1: "❌ Impossible! h1=red conflicts with my fixed nodes. Try h1=green or h1=blue instead."
- **You learn**: Not all boundary values are viable

### Phase 2: Valid Config for Agent1
- You try: h1=green, h4=red
- Agent1: "✓ Works for me!"
- Agent2: "❌ h2=red, h5=blue doesn't work"

### Phase 3: Coordinate Both Agents
Now you need to find (h1, h4, h2, h5) such that:
- h1 ∈ {green, blue} only
- h4 ∈ {green, red} only
- h2, h5 satisfy Agent2's constraints
- No global conflicts

### Phase 4: Renegotiation Under Constraints
- You adjust h2, h5 for Agent2
- Agent2 becomes happy ✓
- But now Agent1 might conflict if the change affected shared nodes
- **Key challenge**: Finding the intersection of valid configs for both agents

## Comparison: Valid Boundary Configurations

### Agent1 (Easy = 1 fixed vs Medium = 2 fixed)

**Easy Mode (1 fixed node):**
```
Valid configs: ~6 out of 9
h1: ANY color works (red/green/blue)
h4: ANY color works (red/green/blue)
```

**Medium Mode (2 fixed nodes):**
```
Valid configs: 4 out of 9
h1: ONLY green or blue (red IMPOSSIBLE)
h4: ONLY green or red (blue IMPOSSIBLE)

Valid:
1. h1=green, h4=red   ✓
2. h1=green, h4=green ✓
3. h1=blue, h4=red    ✓
4. h1=blue, h4=green  ✓

Invalid:
5. h1=red, h4=red     ❌ (a2 has no valid color)
6. h1=red, h4=green   ❌ (a2 has no valid color)
7. h1=red, h4=blue    ❌ (a2 has no valid color)
8. h1=green, h4=blue  ❌ (conflicts with a4/a5)
9. h1=blue, h4=blue   ❌ (conflicts with a4/a5)
```

### Agent2 (Similar tightening)

**Easy Mode:**
- More flexible boundary configs
- Both h2 and h5 can take most values

**Medium Mode:**
- Only 2 valid configs out of 9
- h2 and h5 must be carefully coordinated
- b2 (the shared connection point) becomes a bottleneck

## Skills Tested (MEDIUM)

1. **Constraint Understanding**: Recognizing that not all values are viable
2. **Multi-step Planning**: Can't just try random configs - need to understand dependencies
3. **Coordination**: Finding configs that satisfy BOTH agents simultaneously
4. **Backtracking**: When one agent's solution breaks another's, need to rethink
5. **Communication**: Agents must clearly explain WHY certain values don't work

## How to Use

1. **In launcher**, change "Fixed nodes per cluster" spinbox to **2**
2. Launch experiment
3. Check `ground_truth_analysis.txt` for the exact valid configurations
4. Try to find a global solution through negotiation
5. Observe how agents explain why certain values are impossible

## Expected Agent Behavior

When you say "h1 must be red", Agent1 should now respond:

> "I tested h1=red with all h4 values (red, green, blue). All resulted in conflicts because h1=red conflicts with my fixed node a2=red, which must satisfy connections to both a1=green and a3=blue. For a solution, h1 needs to be green or blue instead."

This is more sophisticated reasoning than easy mode!

## Difficulty Rating

**Easy Mode**: ⭐☆☆ (1 fixed node)
- Most configs work
- Easy to find solutions by trial and error

**Medium Mode**: ⭐⭐☆ (2 fixed nodes) ← **YOU ARE HERE**
- ~50% fewer valid configs than easy
- Requires understanding constraints
- Some intuitive choices (like h1=red) are impossible

**Hard Mode**: ⭐⭐⭐ (3 fixed nodes)
- Very few valid configs
- May require computational search
- Some problems may have NO solution!

---

**Recommendation**: Start with EASY mode to test agent communication, then move to MEDIUM to test agent reasoning under tighter constraints.
