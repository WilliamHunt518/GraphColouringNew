# Debug Conditional Builder Issue

## Debug Output Added

I've added debug statements to trace what's happening when the conditional builder is created and shown/hidden.

## How to Test

1. **Run the program:**
   ```bash
   python launch_menu.py
   ```

2. **Select RB mode and launch**

3. **Watch the console output** - you should see lines like:
   ```
   [UI DEBUG] Created conditional builder for Agent1, stored in dict
   [UI DEBUG] Created conditional builder for Agent2, stored in dict
   ```

4. **Select "ConditionalOffer" for Agent1:**
   - Watch console for:
   ```
   [UI DEBUG] on_move_change called for neighbor=Agent1, move=ConditionalOffer
   [UI DEBUG] Available frames in dict: ['Agent1', 'Agent2']
   [UI DEBUG] Retrieved cond_builder=Found for Agent1
   ```

5. **Select "ConditionalOffer" for Agent2:**
   - Watch console for similar output with Agent2

6. **Share the console output** - especially:
   - Which neighbors are listed in "Available frames in dict"
   - What neighbor name appears in "on_move_change called for neighbor=X"
   - Whether cond_builder is "Found" or "None"

## What We're Looking For

The debug output will tell us:

1. **Are both conditional builders being created?**
   - Should see "Created conditional builder" for both agents

2. **Is the correct neighbor name being used in the callback?**
   - When you select ConditionalOffer for Agent1, does it say "neighbor=Agent1"?
   - Or does it say "neighbor=Agent2" for both?

3. **Is the frame lookup succeeding?**
   - Should see "Retrieved cond_builder=Found"
   - If it says "Retrieved cond_builder=None", the lookup is failing

## Possible Issues

### Issue A: Neighbor names don't match
- Debug output might show: `created for Agent1` but callback says `neighbor=Agent2`
- This means the closure isn't capturing the neighbor correctly

### Issue B: Frames not in dictionary
- Debug output might show: `Available frames in dict: ['Agent2']` (missing Agent1)
- This means Agent1's frame isn't being stored

### Issue C: Lookup failing
- Debug output might show: `Retrieved cond_builder=None`
- This means the key doesn't match what's in the dictionary

## Run This and Share Output

Please run the program, try selecting ConditionalOffer for both agents, and share the console output that starts with `[UI DEBUG]`.

This will help us identify exactly where the issue is!
