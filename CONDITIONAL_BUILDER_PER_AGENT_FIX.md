# Conditional Builder Per-Agent Fix

## Issue Fixed

**Problem:** The conditional builder UI was only showing up for Agent2 (the lower chat pane), not for Agent1.

**Root Cause:** The conditional builder frames and row tracking variables were local variables within the loop that creates chat panes. Each iteration of the loop would overwrite the previous values, so only the last neighbor (Agent2) would have working conditional builders.

## Solution

Changed from local variables to **per-neighbor dictionaries** so each agent has its own independent conditional builder UI.

### Changes Made

**File:** `ui/human_turn_ui.py`

#### 1. Added Per-Neighbor Tracking Dictionaries (Lines 77-80)

```python
# Per-neighbor conditional builder frames (so each neighbor has independent UI)
self._conditional_builder_frames: Dict[str, ttk.Frame] = {}
self._accept_offer_frames: Dict[str, ttk.Frame] = {}
self._condition_rows: Dict[str, List] = {}  # {neighbor: [(frame, var), ...]}
self._assignment_rows: Dict[str, List] = {}  # {neighbor: [(frame, node_var, color_var), ...]}
```

#### 2. Store Frames in Dictionaries (Lines 577-583)

**Before:**
```python
conditional_builder_frame = ttk.LabelFrame(rb_frame, text="Conditional Offer Builder")
condition_rows = []
assignment_rows = []
```

**After:**
```python
conditional_builder_frame = ttk.LabelFrame(rb_frame, text="Conditional Offer Builder")
self._conditional_builder_frames[neigh] = conditional_builder_frame  # Store per neighbor

self._condition_rows[neigh] = []      # Independent list per neighbor
self._assignment_rows[neigh] = []     # Independent list per neighbor
```

#### 3. Updated add_condition_row() and add_assignment_row()

Changed from appending to local list:
```python
condition_rows.append((row_frame, statement_var))  # ❌ Local variable
```

To appending to neighbor-specific list:
```python
self._condition_rows[n].append((row_frame, statement_var))  # ✓ Dictionary lookup
```

#### 4. Updated on_move_change() Function

**Before:**
```python
def on_move_change(*args):
    conditional_builder_frame.pack(...)  # ❌ Only shows last neighbor's frame
```

**After:**
```python
def on_move_change(*args, n=neigh):
    # Get this neighbor's frames from dictionaries
    cond_builder = self._conditional_builder_frames.get(n)
    accept_frame = self._accept_offer_frames.get(n)

    if cond_builder:
        cond_builder.pack(...)  # ✓ Shows correct neighbor's frame
```

#### 5. Updated send_rb_message() Function

**Before:**
```python
def send_rb_message(n=neigh, ..., cond_rows=condition_rows, assign_rows=assignment_rows):
    # Used captured local variables
```

**After:**
```python
def send_rb_message(n=neigh, ...):
    # Get condition and assignment rows for this neighbor
    cond_rows = self._condition_rows.get(n, [])
    assign_rows = self._assignment_rows.get(n, [])
```

## How It Works Now

### Data Structure

```python
# Each neighbor has its own independent tracking
_conditional_builder_frames = {
    "Agent1": <LabelFrame for Agent1>,
    "Agent2": <LabelFrame for Agent2>
}

_condition_rows = {
    "Agent1": [(frame1, var1), (frame2, var2), ...],
    "Agent2": [(frame1, var1), ...]
}

_assignment_rows = {
    "Agent1": [(frame1, node_var1, color_var1), ...],
    "Agent2": [(frame1, node_var1, color_var1), ...]
}
```

### Flow

1. User selects "ConditionalOffer" for Agent1
2. `on_move_change()` looks up `self._conditional_builder_frames["Agent1"]`
3. Shows Agent1's conditional builder (not Agent2's)
4. User adds condition rows → stored in `self._condition_rows["Agent1"]`
5. User adds assignment rows → stored in `self._assignment_rows["Agent1"]`
6. User clicks "Send" → `send_rb_message()` retrieves Agent1's rows
7. Conditional offer sent to Agent1 only

**Agent2 works independently:**
- Has its own frame, rows, and state
- Completely separate from Agent1
- Both can have conditional builders open simultaneously

## Testing

### Test 1: Both Agents Show Builder

1. Run: `python launch_menu.py`
2. Select RB mode, launch
3. In **Agent1** chat pane:
   - Select "ConditionalOffer" from dropdown
   - ✓ Conditional builder should appear
4. In **Agent2** chat pane:
   - Select "ConditionalOffer" from dropdown
   - ✓ Conditional builder should appear
5. ✓ Both builders should be visible simultaneously

### Test 2: Independent Row Tracking

1. In Agent1 builder:
   - Add 2 condition rows
   - Add 1 assignment row
2. In Agent2 builder:
   - Add 1 condition row
   - Add 3 assignment rows
3. ✓ Rows should NOT interfere with each other
4. Send from Agent1
   - ✓ Should use Agent1's rows only
5. Send from Agent2
   - ✓ Should use Agent2's rows only

### Test 3: Show/Hide Works for Both

1. Select "ConditionalOffer" for Agent1 → ✓ Builder shows
2. Select "Propose" for Agent1 → ✓ Builder hides
3. Select "ConditionalOffer" for Agent2 → ✓ Builder shows (Agent1's still hidden)
4. Select "Accept" for Agent2 → ✓ Agent2's builder hides, Accept frame shows
5. ✓ Each agent's UI state is independent

## Benefits

- ✅ Both Agent1 and Agent2 can build conditional offers
- ✅ Each has independent UI state (rows, visibility)
- ✅ Can work on both conditionals simultaneously
- ✅ No more shared/overwritten state
- ✅ Cleaner separation of concerns

## Files Modified

- `ui/human_turn_ui.py`
  - Lines 77-80: Added per-neighbor dictionaries
  - Lines 577-583: Store frames in dictionaries
  - Lines 620-626: Updated add_condition_row()
  - Lines 667-673: Updated add_assignment_row()
  - Lines 683-685: Store accept_offer_frame in dictionary
  - Lines 715-751: Updated on_move_change()
  - Lines 814-822: Updated send_rb_message()

## Summary

Changed from **single shared UI** (last-neighbor-wins) to **per-neighbor independent UI** (each has their own).

**Before:**
```
Agent1 chat pane → [references shared variables]
Agent2 chat pane → [references same shared variables] ← overwrites!
```

**After:**
```
Agent1 chat pane → [references self._*["Agent1"]]
Agent2 chat pane → [references self._*["Agent2"]]
```

The conditional builder now works for **both agents**! 🎉
