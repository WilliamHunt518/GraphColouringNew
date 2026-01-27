# Test Plan: Conditional Builder UI

## Quick Verification

Run these checks to verify the conditional builder is working correctly.

## Test 1: UI Elements Appear

1. **Launch:**
   ```bash
   python launch_menu.py
   ```

2. **Select:**
   - Communication mode: "Rule-based (RB)"
   - Problem preset: "PRESET_EASY_1_FIXED_NODE"
   - Click "Launch Experiment"

3. **Check UI Layout:**
   - ✓ Left panel: Graph visualization
   - ✓ Middle panel: Chat panes for Agent1 and Agent2
   - ✓ Right panel: "Active Conditionals" sidebar

4. **Check RB Message Builder:**
   - Find the "Send RB Message" section in one of the chat panes
   - ✓ Move dropdown shows: Propose, ConditionalOffer, CounterProposal, Accept, Commit
   - ✓ Node and Color dropdowns present
   - ✓ Justification dropdown present

## Test 2: Conditional Builder Shows/Hides

1. **Select "ConditionalOffer"** from move dropdown

2. **Verify conditional builder appears:**
   - ✓ "Conditional Offer Builder" frame visible
   - ✓ "IF (conditions):" section visible
   - ✓ "+ Add Condition" button visible
   - ✓ "THEN (my commitments):" section visible
   - ✓ "+ Add Assignment" button visible

3. **Select "Propose"** from move dropdown

4. **Verify conditional builder hides:**
   - ✓ "Conditional Offer Builder" frame hidden
   - ✓ Regular node/color dropdowns visible

5. **Select "Accept"** from move dropdown

6. **Verify accept frame appears:**
   - ✓ "Accept Offer" frame visible
   - ✓ "Select offer to accept:" dropdown visible

## Test 3: Add/Remove Condition Rows

1. **Select "ConditionalOffer"** from move dropdown

2. **Click "+ Add Condition"**
   - ✓ New row appears
   - ✓ Dropdown shows "(select statement)"
   - ✓ Remove button (✗) present

3. **Click the dropdown**
   - ✓ Opens without error
   - ✓ Shows "(select statement)" option
   - ✓ May show recent agent statements (if any)

4. **Click "+ Add Condition" again**
   - ✓ Second row appears
   - ✓ Both rows independent

5. **Click ✗ on first row**
   - ✓ First row removed
   - ✓ Second row still present

## Test 4: Add/Remove Assignment Rows

1. **Click "+ Add Assignment"**
   - ✓ New row appears
   - ✓ "Node:" dropdown shows human's nodes (h1, h2, h3, h4)
   - ✓ Color dropdown shows colors (red, green, blue)
   - ✓ Remove button (✗) present

2. **Select a node**
   - ✓ Node dropdown works
   - ✓ Selection persists

3. **Select a color**
   - ✓ Color dropdown works
   - ✓ Selection persists

4. **Click "+ Add Assignment" again**
   - ✓ Second row appears
   - ✓ Independent from first row

5. **Click ✗ on assignment row**
   - ✓ Row removed

## Test 5: Agent Proposals Populate Conditions

1. **Wait for agent to send proposals** (or click "Pass" to let agent speak)

2. **Observe chat transcript:**
   - Agent should send messages like "Propose a2=blue"

3. **Select "ConditionalOffer"** from move dropdown

4. **Click "+ Add Condition"**

5. **Click the condition dropdown**
   - ✓ Shows recent agent statements
   - ✓ Format: "#0: a2=blue (Propose)"
   - ✓ Only shows statements from that specific agent

## Test 6: Send Conditional Offer

1. **Build a conditional:**
   - Select "ConditionalOffer"
   - Add condition: Select agent's proposal
   - Add assignment: Select your node + color

2. **Click "Send RB Message"**
   - ✓ No error in console
   - ✓ Message appears in chat transcript
   - ✓ Format: "ConditionalOffer: If a2=blue then h1=red"

3. **Check conditionals sidebar:**
   - Note: Human offers won't show in sidebar (only incoming agent offers)

## Test 7: Accept Agent Offer (if available)

1. **Wait for agent to send a ConditionalOffer** (may not happen immediately)

2. **Check conditionals sidebar:**
   - ✓ Agent's offer appears as a card
   - ✓ Shows "Offer #1 from Agent1"
   - ✓ Shows IF section with conditions
   - ✓ Shows THEN section with assignments
   - ✓ Shows "Accept" and "Counter" buttons

3. **Method 1 - Via sidebar:**
   - Click "Accept" button on the card
   - ✓ Accept message sent
   - ✓ Card updates to show "✓ Accepted"

4. **Method 2 - Via message builder:**
   - Select "Accept" from move dropdown
   - ✓ "Accept Offer" frame appears
   - Click offer dropdown
   - ✓ Shows pending offers
   - Select an offer
   - Click "Send RB Message"
   - ✓ Accept message sent

## Test 8: Committed Node Visualization

1. **Send a Commit message:**
   - Select "Commit"
   - Select node and color
   - Click "Send RB Message"

2. **Check graph visualization:**
   - ✓ Committed node has gold ring around it
   - ✓ Small lock icon (🔒) in corner
   - ✓ Different from fixed nodes (orange dashed ring)

## Console Checks

Throughout testing, check console output for:

```
[RB UI] Sending ConditionalOffer: 1 conditions, 1 assignments
[RB UI] Sending Accept for offer offer_1234567
[RB UI] Sending RB message: move=Commit, node=h1, color=red
```

No errors should appear.

## Common Issues

### Issue: Conditional builder doesn't appear
- **Fix**: Make sure you selected "ConditionalOffer" (not "Propose")
- **Check**: Move dropdown should show "ConditionalOffer"

### Issue: Condition dropdown is empty
- **Reason**: Agent hasn't sent any proposals yet
- **Fix**: Click "Pass" to let agent speak first
- **Alternative**: Wait for agent to initiate

### Issue: Cannot send ConditionalOffer
- **Check console for**: "Cannot send ConditionalOffer: no conditions specified"
- **Fix**: Add at least one condition row with valid selection
- **Check console for**: "Cannot send ConditionalOffer: no assignments specified"
- **Fix**: Add at least one assignment row with valid node/color

### Issue: Accept dropdown shows "(no pending offers)"
- **Reason**: No active conditional offers from agents
- **Fix**: Agents may not generate ConditionalOffers in every scenario
- **Alternative**: Test Accept with sidebar method when agent does send one

## Success Criteria

All of these should work:

- ✓ Conditional builder UI appears/hides correctly
- ✓ Can add/remove condition rows
- ✓ Can add/remove assignment rows
- ✓ Condition dropdown populates from agent statements
- ✓ Can send ConditionalOffer messages
- ✓ Can accept offers via sidebar or dropdown
- ✓ Committed nodes show gold ring + lock icon
- ✓ No console errors during normal operation

## Notes

- Agents may not always generate ConditionalOffers (depends on scenario)
- Human-created ConditionalOffers don't appear in sidebar (only incoming agent offers)
- The system logs all moves to console with `[RB UI]` prefix
- Syntax errors are caught early by py_compile checks
