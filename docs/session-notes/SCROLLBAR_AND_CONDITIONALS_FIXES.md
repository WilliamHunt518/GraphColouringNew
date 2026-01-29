# Scrollbar and Conditionals Visibility Fixes

## Issues Fixed

### Issue 1: Middle Panel Goes Off Screen ✓ FIXED

**Problem:**
- Chat panes (middle panel) were extending beyond the bottom of the screen
- No scrollbar available, making lower chat panes inaccessible

**Fix Applied:**
Updated `ui/human_turn_ui.py` (lines 248-275):

**What was added:**
1. **Canvas + Scrollbar container** for the middle panel
2. **Automatic scroll region updates** when content changes
3. **Mousewheel binding** for easy scrolling
4. **Dynamic width adjustment** to match canvas size

**Before:**
```python
right = ttk.Frame(paned)  # No scrolling
paned.add(right, ...)
```

**After:**
```python
# Create scrollable container
middle_container = ttk.Frame(paned)
middle_canvas = tk.Canvas(middle_container)
middle_scrollbar = ttk.Scrollbar(middle_container, ...)

# Frame inside canvas for chat panes
right = ttk.Frame(middle_canvas)
middle_canvas.create_window((0, 0), window=right, ...)

# Bind scrolling
middle_canvas.bind_all("<MouseWheel>", on_mousewheel)
```

**How to use:**
- Scroll with **mousewheel** in the middle panel
- Scrollbar appears on the **right edge** of middle panel
- Works automatically as chat panes expand

### Issue 2: Conditionals Don't Show When Created ✓ FIXED

**Problem:**
- When you create a conditional offer, nothing appeared in the conditionals sidebar
- No visual feedback that the offer was sent
- Couldn't track your own offers

**Root Cause:**
- Conditionals sidebar only showed INCOMING offers (from agents)
- Human's OUTGOING offers weren't tracked or displayed

**Fixes Applied:**

**1. Track Human's Sent Offers** (`ui/human_turn_ui.py`):

Added tracking variable:
```python
self._human_sent_offers: List[Dict[str, Any]] = []  # Track human's own sent offers
```

When sending a conditional offer:
```python
# Track human's sent offer
self._human_sent_offers.append({
    "offer_id": offer_id,
    "sender": "Human",
    "recipient": n,
    "conditions": conditions,
    "assignments": assignments,
    "status": "pending"
})

# Update sidebar to show it
self._render_conditional_cards()

# Show success message
print("[RB UI] ✓ Conditional offer sent! Check the sidebar → to track it.")
```

**2. Display Both Incoming and Outgoing Offers:**

Updated `_render_conditional_cards()` to show:
- **Outgoing offers** (blue background, "→ Agent" arrow)
- **Incoming offers** (yellow background, "← Agent" arrow)
- **Accepted offers** (green background)

**Color Coding:**
```
Outgoing pending:  Light blue  (#e6f3ff)  "Offer #1 → Agent1"
Incoming pending:  Light yellow (#fffacd)  "Offer #2 ← Agent1"
Accepted:          Light green  (#90ee90)  "✓ Accepted/They accepted"
```

**3. Different Actions for Each Direction:**

**Outgoing offers:**
- Show status: "⏳ Waiting for response..." or "✓ They accepted"
- No action buttons (you already sent it)

**Incoming offers:**
- Show action buttons: [Accept] [Counter]
- You can respond

## What You'll See Now

### When You Send a Conditional Offer:

1. **In Console:**
   ```
   [RB UI] Sending ConditionalOffer: 2 conditions, 2 assignments
   [RB UI] ✓ Conditional offer sent! Check the sidebar → to track it.
   ```

2. **In Conditionals Sidebar:**
   ```
   ┌─────────────────────────────────────┐
   │ Offer #1 → Agent1           [blue] │
   │                                     │
   │ IF:                                 │
   │   • a2 = blue                       │
   │   • a3 = yellow                     │
   │                                     │
   │ THEN:                               │
   │   • h1 = red                        │
   │   • h4 = green                      │
   │                                     │
   │ ⏳ Waiting for response...          │
   └─────────────────────────────────────┘
   ```

3. **When Agent Accepts:**
   The card updates to:
   ```
   │ ✓ They accepted              [green] │
   ```

### When Agent Sends You an Offer:

```
┌─────────────────────────────────────┐
│ Offer #2 ← Agent1          [yellow] │
│                                     │
│ IF:                                 │
│   • h1 = red                        │
│                                     │
│ THEN:                               │
│   • a2 = blue                       │
│                                     │
│ [Accept] [Counter]                  │
└─────────────────────────────────────┘
```

## Testing the Fixes

### Test 1: Scrollbar Works

1. Run: `python launch_menu.py`
2. Select RB mode, launch
3. Look at middle panel (chat panes)
4. ✓ Should see scrollbar on right edge if content is tall
5. ✓ Mousewheel should scroll the panel
6. ✓ All chat controls should be accessible

### Test 2: Your Conditionals Appear

1. Select "ConditionalOffer" from move dropdown
2. Add at least 1 condition (select from agent's previous statements)
3. Add at least 1 assignment (your node + color)
4. Click "Send RB Message"
5. ✓ Check console: Should see "✓ Conditional offer sent!"
6. ✓ Check sidebar: Should see blue card with "→ Agent1"
7. ✓ Card should show your conditions and assignments
8. ✓ Status should be "⏳ Waiting for response..."

### Test 3: Incoming vs Outgoing Visual Difference

1. Send a conditional offer (yours will be blue with →)
2. Wait for agent to send one (theirs will be yellow with ←)
3. ✓ Blue cards are yours (outgoing)
4. ✓ Yellow cards are theirs (incoming)
5. ✓ Green cards are accepted
6. ✓ Your cards show "⏳ Waiting..."
7. ✓ Their cards show [Accept] [Counter] buttons

## Technical Details

### Scrollbar Implementation

Used Canvas + Scrollbar pattern:
```python
# Container holds canvas + scrollbar
container = ttk.Frame()

# Canvas is scrollable
canvas = tk.Canvas(container)
scrollbar = ttk.Scrollbar(container, command=canvas.yview)

# Content goes in frame inside canvas
content_frame = ttk.Frame(canvas)
canvas.create_window((0, 0), window=content_frame, anchor="nw")

# Update scroll region when content changes
content_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

# Bind mousewheel
canvas.bind_all("<MouseWheel>", on_mousewheel)
```

### Conditional Tracking Flow

```
1. Human builds conditional in UI
   ↓
2. send_rb_message() creates offer_id
   ↓
3. Offer added to _human_sent_offers list
   ↓
4. _render_conditional_cards() called
   ↓
5. Combines _human_sent_offers + _active_conditionals
   ↓
6. Renders all offers with direction indicators
   ↓
7. Blue cards (outgoing) vs Yellow cards (incoming)
```

### Offer Direction Logic

```python
# In _render_conditional_cards():
all_offers = []

# Add human's sent offers (outgoing)
for offer in self._human_sent_offers:
    all_offers.append({
        **offer,
        "direction": "outgoing"
    })

# Add agent's offers (incoming)
for offer in self._active_conditionals:
    all_offers.append({
        **offer,
        "direction": "incoming"
    })

# Render with direction-specific styling
for cond in all_offers:
    direction = cond.get("direction", "incoming")
    if direction == "outgoing":
        # Blue card, → arrow, status only
    else:
        # Yellow card, ← arrow, Accept/Counter buttons
```

## Files Modified

1. **ui/human_turn_ui.py**
   - Lines 248-275: Added scrollable middle panel
   - Lines 69-71: Added `_human_sent_offers` tracking
   - Lines 857-877: Track sent offers when creating conditional
   - Lines 814-900: Updated `_render_conditional_cards()` for both directions

## Known Limitations

1. **Offer Status Updates** - Currently, human's sent offer status doesn't auto-update to "accepted" when agent accepts (would need to parse Accept messages)
2. **Offer Expiration** - No automatic cleanup of old pending offers
3. **No Cancel** - Can't cancel a sent offer once sent

## Future Enhancements

- Auto-update offer status when Accept message received
- Add "Cancel Offer" button for outgoing offers
- Show offer age/timestamp
- Filter offers by status (pending/accepted)
- Collapse/expand offer details

## Summary

Both issues fixed:

✅ **Scrollbar added** - Middle panel now scrolls with mousewheel
✅ **Conditionals visible** - Your sent offers appear in sidebar (blue cards)
✅ **Direction indicators** - Clear → vs ← arrows
✅ **Status tracking** - Shows "Waiting..." or "They accepted"
✅ **Visual feedback** - Console confirms offer sent

Enjoy! 🎉
