# Complete RB Mode User Guide - Step by Step to Convergence

## How RB Mode Works

RB (Rule-Based) mode is a structured negotiation protocol where you and autonomous agents coordinate to find a valid graph coloring.

## Complete Workflow from Start to Convergence

### Phase 1: CONFIGURATION (Blind Announcement)

**Step 1:** Launch RB mode
```bash
python launch_menu.py
```
Select "RB" mode and click Start.

**Step 2:** Set YOUR initial node colors (BLIND)
- Click on your nodes (h1, h2, h3, h4, h5) to set colors
- Your fixed node (h3=green) is already set
- Set the others to your preferred starting colors
- **Agents cannot see your colors yet!**

**Step 3:** Click "Announce Configuration" button
- This sends your configuration to agents
- Agents transition from "configure" to "bargain" phase
- Agents announce THEIR initial configurations
- You'll see messages like: "📢 Configuration Announced: a2=blue, a4=red, a5=blue"

### Phase 2: BARGAINING (Conditional Offers)

**Step 4:** Agents send conditional offers
- Agents analyze your announced colors
- They send offers like: "If h1=green AND h4=red, then I'll do a2=red, a4=green, a5=blue"
- **ALL offers have penalty≈0** (guaranteed valid coloring if you accept their conditions)
- Offers appear as cards in the UI

**Step 5:** YOU respond to offers (choose ONE):

**Option A: Accept an Offer**
1. Review the conditional offer card
2. Check if you're willing to set the required colors (the "IF" conditions)
3. Click "Accept" on the offer
4. **Agent locks those assignments** - they won't change them
5. Agent becomes "satisfied" if penalty=0
6. Agent stops sending new offers

**Option B: Reject with Impossible Conditions**
1. Click "Reject" on the offer
2. Mark specific conditions as impossible (e.g., "h4=red is impossible for me")
3. Agent remembers these constraints
4. Agent generates NEW offers avoiding those impossible conditions

**Option C: Ask Feasibility Query**
1. Use the "Feasibility Query" builder
2. Ask: "Is h1=green feasible?"
3. Agent responds: "Yes, if h4=red" OR "No, impossible"
4. If YES, agent **automatically sends a matching conditional offer**
5. You can then accept that offer

**Option D: Send YOUR Conditional Offer**
1. Use the "Build Conditional Offer" tool
2. Specify: "IF a2=blue AND a5=red THEN I'll set h1=green, h4=red"
3. Send to agent
4. Agent evaluates and responds (Accept/Reject/Counter)

### Phase 3: CONVERGENCE

**Step 6:** Repeat bargaining until satisfied
- Accept compatible offers from agents
- Agents lock their commitments
- When penalty=0, agents become satisfied
- Continue until YOU are also satisfied with the coloring

**Step 7:** Mark yourself satisfied
- Check the "I'm satisfied with Agent1" checkbox
- Check the "I'm satisfied with Agent2" checkbox
- When ALL parties (you + both agents) are satisfied, the UI ends

**Step 8:** View results
- Final coloring is saved
- Check `results/rb/` directory for logs

## Key Principles for Success

1. **Agents ONLY send penalty≈0 offers**
   - If an agent can't find a valid solution, it won't send an offer
   - If no offers appear, try changing YOUR colors or asking feasibility queries

2. **Accepted offers are LOCKED**
   - Once you accept "If h1=green then a2=red", agent commits to a2=red
   - Agent won't change a2 even if solver finds "better" solutions

3. **Feasibility queries are powerful**
   - Ask "Is h1=green feasible?" to explore options
   - Agent automatically sends matching conditional offer if yes

4. **Impossible conditions help agents adapt**
   - Rejecting with "h4=red is impossible" helps agent understand your constraints
   - Agent generates new offers avoiding those conditions

5. **You control the negotiation**
   - Agents wait for YOUR responses to their offers
   - You can change your own colors anytime
   - Click "(Re-)Announce Configuration" to send updates to agents

## Example: Complete Run to Convergence

```
[YOU] Set h1=red, h2=blue, h3=green (fixed), h4=red, h5=green
[YOU] Click "Announce Configuration"

[Agent1] Announces: a2=blue, a4=red, a5=blue (current penalty=2)
[Agent2] Announces: b2=green, b5=red (current penalty=0) ✓ satisfied

[Agent1] Sends offer: "If h1=green AND h4=red, then a2=red, a4=green, a5=blue [penalty=0.000]"
[Agent2] Already satisfied, no new offers

[YOU] Review Agent1's offer
[YOU] Decide: I can change h1 to green
[YOU] Click "Accept" on Agent1's offer

[Agent1] Locks: a2=red, a4=green, a5=blue
[Agent1] Penalty=0 ✓ satisfied

[YOU] Change h1 from red to green (to fulfill the accepted condition)
[YOU] Check "I'm satisfied with Agent1"
[YOU] Check "I'm satisfied with Agent2"

[SYSTEM] All parties satisfied - consensus reached!
[SYSTEM] UI closes with end_reason="consensus"
```

## Troubleshooting

**Problem:** No offers appear from agents
- **Cause:** Agents can't find penalty≈0 solutions with your current colors
- **Solution:** Try different colors for your nodes, or ask feasibility queries

**Problem:** Agent sends offer but then changes it
- **Cause:** You changed your colors after agent sent offer
- **Solution:** Keep colors stable while considering offers, or re-announce after changes

**Problem:** Can't achieve convergence
- **Cause:** Graph may not be colorable with current fixed constraints
- **Solution:** Check the ground truth hint in console - it shows one valid solution

**Problem:** Agent keeps sending same offer
- **Cause:** Bug (should be fixed now!)
- **Solution:** Report this - agents should stop when satisfied

## Files and Logs

After running, check `results/rb/` for:
- `communication_log.txt` - All messages exchanged
- `Agent1_log.txt` - Agent1's reasoning and decisions
- `Agent2_log.txt` - Agent2's reasoning and decisions
- `Human_log.txt` - Your interactions
- `ground_truth_analysis.txt` - One valid solution for reference

## Summary

RB mode is about **structured negotiation**:
1. You announce your colors (blind)
2. Agents announce theirs
3. Agents propose conditional swaps ("If you do X, I'll do Y")
4. You accept compatible offers
5. Repeat until everyone is satisfied (penalty=0)
6. Mark yourself satisfied to end

The key is that **agents guarantee valid colorings** - all their offers have penalty≈0, so accepting them leads to valid solutions!
