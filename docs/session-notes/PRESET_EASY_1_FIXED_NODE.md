# Preset Configuration: 1 Fixed Node Per Agent (EASY Difficulty)

## Configuration
- **Fixed Nodes Per Agent**: 1
- **Random Seed**: 42 (deterministic)
- **Domain**: [red, green, blue]
- **Difficulty**: EASY ⭐☆☆
- **Spinbox Setting**: 1

**See also**:
- `PRESET_MEDIUM_2_FIXED_NODES.md` for harder scenarios with tighter constraints
- `PRESET_COMPARISON.md` for full comparison of difficulty levels

## Resulting Fixed Nodes

With this configuration, the system will automatically select 1 internal node per agent to fix:

### Agent1
- **Internal Nodes**: a1, a3 (nodes with no external connections)
- **Fixed**: One of these will be fixed to **green** (determined by seed 42)
- **Boundary Nodes**: h1, h4 (human nodes that Agent1 connects to)

### Agent2
- **Internal Nodes**: b1, b3, b4, b5
- **Fixed**: One of these will be fixed to **green** (determined by seed 42)
- **Boundary Nodes**: h2, h5 (human nodes that Agent2 connects to)

### Human
- **Internal Nodes**: h3 (only internal node)
- **Fixed**: h3 = **green**
- **Boundary Nodes**: a2, a4, a5, b2 (agent nodes that connect to human)

## Expected Test Dynamics

This configuration creates the renegotiation scenario you requested:

### Phase 1: Initial Conflict
When you start, the default initialization sets all nodes to **red** (the first color in the domain).
- **h3 is immediately corrected to green** (fixed)
- Both agents will detect conflicts with their initial assignments
- Agents will suggest boundary changes

### Phase 2: Satisfying One Agent
- You can choose boundary colors that satisfy **Agent1** (e.g., h1=green, h4=red)
- Agent1 becomes satisfied ✓
- But Agent2 may still have conflicts with h2/h5

### Phase 3: Forced Renegotiation
- You adjust boundary to satisfy **Agent2** (e.g., h2=blue, h5=green)
- Agent2 becomes satisfied ✓
- **But now Agent1 might have conflicts!** (if h1 or h4 changed)

### Phase 4: Finding Global Solution
You need to find a configuration where:
- h1 satisfies Agent1's constraints
- h4 satisfies Agent1's constraints
- h2 satisfies Agent2's constraints
- h5 satisfies Agent2's constraints
- h3 = green (your fixed constraint)
- All other h-nodes (h1, h2, h4, h5) are colored such that no conflicts occur

## Why This Creates Good Test Dynamics

1. **Local vs Global Optimization**: Each agent can achieve penalty=0 with many boundary configurations, but not all are compatible with BOTH agents simultaneously.

2. **Negotiation Required**: You can't just satisfy one agent - you need to coordinate between both.

3. **Multiple Valid Solutions**: There are usually several valid global solutions, so you can test different negotiation paths.

4. **Realistic Constraint**: With only 1 fixed node per agent, solutions exist (not over-constrained), but require coordination (not trivial).

## How to Use

1. Launch with default settings (now automatically 1 fixed node)
2. Check `ground_truth_analysis.txt` to see which specific node was fixed for each agent
3. Observe which boundary configurations work for Agent1
4. Observe which boundary configurations work for Agent2
5. Find the intersection - configurations that work for BOTH

## Example Scenario

If the fixed nodes are:
- Agent1: a1 = green
- Agent2: b1 = blue
- Human: h3 = green

Then a typical negotiation might look like:

1. **You set**: h1=green, h4=red → Agent1 happy ✓, Agent2 unhappy ✗
2. **Agent2 says**: "h2=blue, h5=green would work for me"
3. **You try**: h1=green, h4=red, h2=blue, h5=green
4. **Result**: Both agents happy ✓✓ (if this is a valid global solution)

Or you might need to iterate:

1. **You set**: h1=green, h4=red → Agent1 happy ✓
2. **You adjust for Agent2**: h2=blue, h5=green → Agent2 happy ✓, but now Agent1 conflicts!
3. **Agent1 says**: "h1 needs to be blue instead"
4. **You adjust**: h1=blue, h4=red, h2=blue, h5=green → Both happy ✓✓

This back-and-forth is the **renegotiation dynamic** you wanted to test!

---

**Note**: Run the experiment to generate `ground_truth_analysis.txt` which will show you the EXACT fixed nodes and ALL valid solutions for your specific configuration.
