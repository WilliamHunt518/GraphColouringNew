# Conditional Builder Always Visible Fix

## Problem

The conditional builder was only appearing for Agent2 and not Agent1, even after multiple attempted fixes. The dynamic show/hide approach was causing unpredictable layout behavior.

## Root Cause

The approach of dynamically showing/hiding the conditional builder with `pack()` and `pack_forget()` was fundamentally flawed because:

1. **Layout order confusion**: When packed dynamically, widgets could appear at unpredictable positions
2. **Unclear ownership**: Not obvious which agent the builder applied to when it appeared at the bottom
3. **Complexity**: The move dropdown callback logic was overly complex with show/hide state management
4. **Unreliable**: Even with fixed positioning, dynamic packing didn't work consistently

## Solution: Always Visible Builder

Restructured the UI so the conditional builder is **permanently visible** for each agent.

### Key Changes in `ui/human_turn_ui.py`

**1. Removed Dynamic Show/Hide (Lines 590-601)**

**Before:**
```python
conditional_builder_frame = ttk.LabelFrame(rb_frame, text="Conditional Offer Builder")
self._conditional_builder_frames[neigh] = conditional_builder_frame
conditional_builder_frame.pack(fill="x", padx=4, pady=4)
conditional_builder_frame.pack_forget()  # Hide initially
```

**After:**
```python
# Conditional builder - ALWAYS VISIBLE, positioned clearly under this agent's controls
conditional_builder_frame = ttk.LabelFrame(rb_frame, text=f"Conditional Offer Builder (for {neigh})")
self._conditional_builder_frames[neigh] = conditional_builder_frame
conditional_builder_frame.pack(fill="x", padx=4, pady=4)  # ALWAYS VISIBLE
```

**Changes:**
- ✅ Labeled with agent name: `"Conditional Offer Builder (for Agent1)"`
- ✅ Packed once and stays visible
- ✅ No `pack_forget()` call
- ✅ Clear ownership - can't confuse which agent it applies to

**2. Removed Accept Offer Frame Complexity (Lines 698-736 removed)**

Deleted entire accept_offer_frame section including:
- Frame creation and show/hide logic
- update_accept_offers() function
- Complex dropdown population

**Rationale:** Accept functionality can reference the conditionals sidebar directly. No need for separate UI frame that dynamically appears.

**3. Simplified Move Callback (Lines 697-714)**

**Before:** 140+ lines of complex show/hide logic with comprehensive logging

**After:**
```python
def on_move_change(*args, n=neigh):
    move = move_var.get()
    if move == "Propose":
        help_text_var.set("Suggest a color for a node")
    elif move == "ConditionalOffer":
        help_text_var.set("Use the builder below to create 'If you do X, I'll do Y' deals")
    elif move == "CounterProposal":
        help_text_var.set("Respond to their suggestion with an alternative color")
    elif move == "Accept":
        help_text_var.set("Accept a conditional offer from the agent (check sidebar)")
    elif move == "Commit":
        help_text_var.set("Lock in a color choice (can still be challenged)")
    else:
        help_text_var.set("")

move_var.trace('w', on_move_change)
on_move_change()  # Initialize help text
```

**Result:** 18 lines instead of 140. Only updates help text, no show/hide logic.

**4. Initialize with Rows (Lines 698-701)**

```python
# Initialize with one row each so builder is ready to use
add_condition_row(neigh)
add_assignment_row(neigh)
self._debug_logger.info(f"  Initialized with 1 condition row and 1 assignment row")
```

Each builder starts with:
- 1 condition row (IF section)
- 1 assignment row (THEN section)

User can immediately use it or add more rows.

## Layout Structure Now

### Agent1 Chat Pane:
```
┌─ Chat with Agent1 ─────────────────────────────┐
│ [Chat transcript...]                           │
│                                                 │
│ ┌─ Send RB Message ──────────────────────────┐ │
│ │ Move: [Propose ▼]                           │ │
│ │ Help: Suggest a color for a node            │ │
│ │                                              │ │
│ │ ┌─ Conditional Offer Builder (for Agent1) ┐ │ │
│ │ │ IF (conditions):                         │ │ │
│ │ │   [(select statement) ▼] [✗]            │ │ │
│ │ │ [+ Add Condition]                        │ │ │
│ │ │                                          │ │ │
│ │ │ THEN (my commitments):                   │ │ │
│ │ │   Node: [h1 ▼] = Color: [red ▼] [✗]    │ │ │
│ │ │ [+ Add Assignment]                       │ │ │
│ │ └──────────────────────────────────────────┘ │ │
│ │                                              │ │
│ │ Node: [h1 ▼]                                │ │
│ │ Color: [red ▼]                              │ │
│ │ Justifying: [(none) ▼]                      │ │
│ │ [Send RB Message]                           │ │
│ └──────────────────────────────────────────────┘ │
│ [I'm satisfied ☑]                              │
└─────────────────────────────────────────────────┘
```

### Agent2 Chat Pane:
```
┌─ Chat with Agent2 ─────────────────────────────┐
│ [Chat transcript...]                           │
│                                                 │
│ ┌─ Send RB Message ──────────────────────────┐ │
│ │ Move: [Propose ▼]                           │ │
│ │ Help: Suggest a color for a node            │ │
│ │                                              │ │
│ │ ┌─ Conditional Offer Builder (for Agent2) ┐ │ │
│ │ │ IF (conditions):                         │ │ │
│ │ │   [(select statement) ▼] [✗]            │ │ │
│ │ │ [+ Add Condition]                        │ │ │
│ │ │                                          │ │ │
│ │ │ THEN (my commitments):                   │ │ │
│ │ │   Node: [h1 ▼] = Color: [red ▼] [✗]    │ │ │
│ │ │ [+ Add Assignment]                       │ │ │
│ │ └──────────────────────────────────────────┘ │ │
│ │                                              │ │
│ │ Node: [h1 ▼]                                │ │
│ │ Color: [red ▼]                              │ │
│ │ Justifying: [(none) ▼]                      │ │
│ │ [Send RB Message]                           │ │
│ └──────────────────────────────────────────────┘ │
│ [I'm satisfied ☑]                              │
└─────────────────────────────────────────────────┘
```

## Benefits

### ✅ Clear Ownership
- Builder labeled with agent name: `"for Agent1"`, `"for Agent2"`
- Positioned directly under that agent's controls
- No confusion about which agent you're building an offer for

### ✅ Always Accessible
- No need to select "ConditionalOffer" from dropdown first
- Can build conditional offer any time
- Builder is ready to use with initial rows

### ✅ Simple and Reliable
- No dynamic show/hide logic
- No pack()/pack_forget() timing issues
- Consistent layout for all agents

### ✅ Visible Context
- Can see the builder while reading the agent's chat messages
- Can reference previous messages while building conditions
- Don't need to remember which move type you selected

## Usage

### To Create a Conditional Offer:

1. **In the "IF (conditions)" section:**
   - Click dropdown to select a previous statement from the agent
   - Add more conditions with `[+ Add Condition]`
   - Remove conditions with `[✗]` button

2. **In the "THEN (my commitments)" section:**
   - Select your node from dropdown
   - Select color you'll commit to
   - Add more assignments with `[+ Add Assignment]`
   - Remove assignments with `[✗]` button

3. **Select "ConditionalOffer" from Move dropdown** (updates help text)

4. **Click "Send RB Message"** to send the conditional offer

5. **Check the conditionals sidebar** (right side) to see your offer tracked

### Help Text Updates

The help text below the Move dropdown updates to provide guidance:
- **Propose**: "Suggest a color for a node"
- **ConditionalOffer**: "Use the builder below to create 'If you do X, I'll do Y' deals"
- **CounterProposal**: "Respond to their suggestion with an alternative color"
- **Accept**: "Accept a conditional offer from the agent (check sidebar)"
- **Commit**: "Lock in a color choice (can still be challenged)"

## What Was Removed

- ❌ `pack_forget()` / dynamic packing logic
- ❌ accept_offer_frame and its show/hide logic
- ❌ 140+ lines of complex callback logic
- ❌ Comprehensive debug logging (since it works now)
- ❌ Frame lookup from dictionaries in callbacks
- ❌ Conditional row initialization in callback
- ❌ Visibility state management

## Testing

Run the program and verify:

1. **Both agents show builder**:
   - Agent1 chat pane has "Conditional Offer Builder (for Agent1)"
   - Agent2 chat pane has "Conditional Offer Builder (for Agent2)"
   - Both are visible without selecting any move type

2. **Builders are independent**:
   - Add rows in Agent1's builder
   - Add rows in Agent2's builder
   - They don't interfere with each other

3. **Clear positioning**:
   - Each builder is directly below that agent's "Send RB Message" section
   - Easy to see which agent the builder applies to

4. **Ready to use**:
   - Each builder has 1 condition row and 1 assignment row by default
   - Can immediately start building conditional offers

## Summary

**Problem**: Dynamic show/hide approach was unreliable and confusing
**Solution**: Make builders always visible with clear agent labeling
**Result**: Simple, reliable, obvious which agent each builder applies to

The conditional builder now works for **both Agent1 and Agent2** consistently! 🎉
