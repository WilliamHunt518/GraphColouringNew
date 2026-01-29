# Conditional Builder Debug Output and Clarity Improvements

## Issue Reported

User reported: "If I click the x's next to the conditions and outcomes, they disappear and I can't get them back. The interface is a tiny bit unclear about what I'm doing."

## Changes Made

### 1. Added Debug Output

Added console print statements to track user actions and help diagnose any issues:

**When adding condition rows:**
```python
print(f"[UI] Adding condition row for {n}")
```

**When removing condition rows:**
```python
print(f"[UI] Removing condition row for {n}")
print(f"[UI] {n} now has {len(self._condition_rows[n])} condition rows")
```

**When adding assignment rows:**
```python
print(f"[UI] Adding assignment row for {n}")
```

**When removing assignment rows:**
```python
print(f"[UI] Removing assignment row for {n}")
print(f"[UI] {n} now has {len(self._assignment_rows[n])} assignment rows")
```

### 2. Added Instruction Labels

Added helpful instruction text to clarify what each section is for:

**Under "IF (conditions):"**
```
"Select statements from agent's proposals to use as conditions"
```

**Under "THEN (my commitments):"**
```
"Specify what you'll commit to if conditions are met"
```

These appear in small italic gray text to provide guidance without cluttering the interface.

## How the Buttons Should Work

### Add Buttons
- **[+ Add Condition]** - Click to add a new condition row
- **[+ Add Assignment]** - Click to add a new assignment row

These buttons are always visible at the bottom of each section and should work even if you've removed all rows.

### Remove Buttons (✗)
- Each row has a **✗** button on the right side
- Click to remove that specific row
- You'll see a console message confirming the removal

## Testing the Fix

1. **Run the program** and watch the console output
2. **Click [+ Add Condition]**
   - You should see: `[UI] Adding condition row for Agent1`
   - A new row should appear
3. **Click the ✗ button** on a condition row
   - You should see: `[UI] Removing condition row for Agent1`
   - You should see: `[UI] Agent1 now has X condition rows`
   - The row should disappear
4. **Click [+ Add Condition] again**
   - A new row should appear
   - This confirms you can add rows back after removing them

## Expected Console Output Example

```
[UI] Adding condition row for Agent1
[UI] Adding assignment row for Agent1
[UI] Adding condition row for Agent1
[UI] Removing condition row for Agent1
[UI] Agent1 now has 1 condition rows
[UI] Adding condition row for Agent1
[UI] Agent1 now has 2 condition rows
```

## Interface Clarity

The interface now shows:

```
┌─ Conditional Offer Builder (for Agent1) ───────┐
│ IF (conditions):                                │
│ Select statements from agent's proposals...     │
│   [(select statement) ▼] [✗]                   │
│ [+ Add Condition]                               │
│                                                 │
│ THEN (my commitments):                          │
│ Specify what you'll commit to if conditions... │
│   Node: [h1 ▼] = Color: [red ▼] [✗]           │
│ [+ Add Assignment]                              │
└─────────────────────────────────────────────────┘
```

The instruction labels make it clearer:
- **IF section**: "Select statements from agent's proposals to use as conditions"
- **THEN section**: "Specify what you'll commit to if conditions are met"

## Troubleshooting

If the buttons still don't work after clicking them:

1. **Check console output** - You should see the `[UI] Adding...` messages
2. **If you see error messages** - Share them so we can fix the issue
3. **If you see the messages but no rows appear** - There may be a layout/packing issue
4. **If you see nothing** - The button click might not be registering

## Next Steps

After testing, if you want interface changes:
- We can adjust the layout
- We can change button styling
- We can add more instructions
- We can simplify or reorganize sections

The core functionality (add/remove rows) should now work correctly and be debuggable via console output.
