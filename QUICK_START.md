# Quick Start Guide - After Fixes

## TL;DR - Running the System

```bash
# 1. Quick test (no LLM calls, just validate fixes)
python simple_test_runner.py --modes RB

# 2. Full test with LLM calls (requires API key)
python simple_test_runner.py --modes LLM_U LLM_C

# 3. Interactive mode (play as human)
python launch_menu.py
# Select mode: LLM_U or LLM_C
# Click nodes to change colors
# Type messages to agents
# Click "I'm satisfied" when done

# 4. Comprehensive test suite with metrics
python tests/comprehensive_agent_test.py --modes RB LLM_U LLM_C --trials 2
```

## What Was Fixed

### 1. Critical Bug (CRASH FIX) ✓
**Problem:** System crashed with `UnboundLocalError: local variable 're' referenced before assignment`
**Fix:** Added `import re` at the right place
**Result:** All modes now work without crashing

### 2. LLM Message Quality ✓
**Problem:** Agents said vague things like "all is fine" or "maybe try alternatives"
**Fix:** Rewrote LLM prompts with explicit rules and examples
**Result:** Messages now precise, concrete, with numbers

### 3. Message Repetition ✓
**Problem:** Same message sent repeatedly even when nothing changed
**Fix:** Added message deduplication system (tracks last 5 messages)
**Result:** No more annoying repetitions

### 4. LLM_U Format ✓
**Problem:** Only showed "alternatives", not current setting
**Fix:** Now shows top 5 options INCLUDING current with marker
**Result:** Human can compare all viable options

### 5. LLM_C Format ✓
**Problem:** Only showed "h1 ∈ {green, blue}", human had to compute Cartesian product
**Fix:** Enumerates complete valid configurations (up to 10)
**Result:** Human sees concrete complete options

### 6. Solution Hint ✓
**Problem:** Hard problem, no guidance on what to aim for
**Fix:** Prints valid solution at startup when found
**Result:** Human has a concrete goal

## Before vs After Examples

### LLM_U Messages

**BEFORE:**
```
I currently think your boundary colours are h1=red, h4=green.
My score: 8.
Alternatives I can support (conflict-free):
- If you set h2=blue, h5=red → I can score 10 (penalty: 0).
```
Issues: Vague, doesn't include current, no clear comparison

**AFTER:**
```
Here are the conflict-free configurations I can support:
1. If you set h1=red, h4=blue, I can score 12. ← YOUR CURRENT SETTING
2. If you set h1=blue, h4=red, I can score 14.
3. If you set h1=green, h4=green, I can score 10.
```
Benefits: Clear, numbered, shows current, easy to compare

### LLM_C Messages

**BEFORE:**
```
Proposed constraints for your boundary nodes: h1 ∈ {green, blue}; h4 ∈ {red, green}.
```
Issues: Human must compute which combinations are valid

**AFTER:**
```
Here are the complete configurations that would work for me:
1. h1=green, h4=red
2. h1=blue, h4=red
3. h1=green, h4=green

In summary, the allowed colors per node are:
h1 ∈ {green, blue}; h4 ∈ {red, green}.
```
Benefits: Concrete complete options, still shows summary

## Testing Your Changes

### Step 1: Verify No Crashes
```bash
python simple_test_runner.py --modes RB
```
**Expected output:**
```
[SUCCESS]
  Time: ~3s
  Final Penalty: 0.0
  Iterations: 20
  Messages: 120
```

### Step 2: Test LLM Modes (requires API key)
```bash
# Make sure api_key.txt exists with your OpenAI key
python simple_test_runner.py --modes LLM_U
```
**What to check:**
- No crashes
- Messages are concrete and specific
- Logs show "Skipping duplicate message" (deduplication working)
- Final penalty is low or zero

### Step 3: Check Message Quality
```bash
python tests/comprehensive_agent_test.py --modes LLM_U --trials 1
```
**Look for in the report:**
- Quality score >70/100
- Hallucination rate <5%
- Repetition count <3
- Clear proposal count >80% of messages

### Step 4: Interactive Test
```bash
python launch_menu.py
```
**Test scenarios:**
1. **Repetition check:** Don't change anything for 3 turns, verify agents don't send identical messages
2. **Clarity check:** Read agent messages, verify they're specific and actionable
3. **Satisfaction reset:** Mark satisfied, then change a boundary node, verify agent unmarks
4. **Constraint check:** Say "h1 can't be green", verify agent respects this

## What to Look For (Success Indicators)

### In Logs
✓ No "UnboundLocalError" crashes
✓ Messages like: "Skipping duplicate message to Human (same content recently sent)"
✓ Messages like: "FINAL changes after all processing: {'b2': ('red', 'blue')}"
✓ Messages like: "Resetting satisfied=False due to neighbor boundary changes"

### In Communication
✓ Numbered lists with explicit scores
✓ "← YOUR CURRENT SETTING" markers
✓ Concrete node=color specifications
✓ No vague language ("all is fine", "maybe", "looks good")
✓ No repeated identical messages

### In Behavior
✓ Agents reach zero penalty
✓ Convergence in <30 iterations
✓ Satisfaction resets when boundary changes
✓ Constraints are respected

## Common Issues and Solutions

### Issue: "No API key found"
**Solution:** Create `api_key.txt` in project root with your OpenAI API key

### Issue: Messages still vague
**Solution:** Check `comm/communication_layer.py` line 539-562, verify improved prompt is there

### Issue: Still getting repeated messages
**Solution:** Check `agents/cluster_agent.py` lines 1305-1312, verify deduplication is active

### Issue: Agent hallucinating changes
**Solution:** Check `agents/cluster_agent.py` lines 650-680, verify `assignments_actually_changed` is computed AFTER snap-to-best

### Issue: Satisfaction not resetting
**Solution:** Check `agents/cluster_agent.py` lines 743-767, verify neighbor change detection is active

## Advanced: Running Full Test Suite

```bash
# Run everything (takes 5-10 minutes)
python run_all_tests.py
```

This will:
1. Run all-agent tests (3 agents, no human)
2. Run comprehensive tests (2 agents + human emulator)
3. Generate master analysis report with recommendations

**Output files:**
- `test_results/MASTER_ANALYSIS.md` - Overall findings
- `test_results/comprehensive/TEST_REPORT.md` - Detailed metrics
- `test_results/comprehensive/test_summary.json` - Raw data
- Individual trial outputs in `test_results/`

## Performance Expectations

### RB Mode (Rule-Based Baseline)
- Time: 2-3 seconds
- Final penalty: 0.0
- Iterations: ~20
- Success rate: 100%

### LLM_U Mode (Utility-based)
- Time: 10-30 seconds (depends on LLM calls)
- Final penalty: 0.0-5.0
- Iterations: 15-30
- Success rate: >80% (target)

### LLM_C Mode (Constraint-based)
- Time: 10-30 seconds (depends on LLM calls)
- Final penalty: 0.0-5.0
- Iterations: 15-30
- Success rate: >80% (target)

## File Structure After Fixes

```
GraphColouringNew/
├── agents/
│   └── cluster_agent.py         # Core agent logic (all fixes)
├── comm/
│   └── communication_layer.py   # LLM prompts and formatting
├── tests/                       # NEW test infrastructure
│   ├── __init__.py
│   ├── human_emulator_agent.py
│   └── comprehensive_agent_test.py
├── simple_test_runner.py        # NEW quick testing script
├── run_all_tests.py             # NEW master test runner
├── FIXES_IMPLEMENTED.md         # This summary
├── QUICK_START.md               # This guide
├── TEST_FINDINGS_AND_RECOMMENDATIONS.md  # Detailed analysis
└── api_key.txt                  # Your OpenAI API key (not in git)
```

## Questions?

**Q: Do I need to re-run tests after changes?**
A: Yes, always run at least `python simple_test_runner.py --modes RB` after any code changes.

**Q: How do I know if message deduplication is working?**
A: Look for "Skipping duplicate message" in agent logs.

**Q: What if agents still hallucinate?**
A: Check that `assignments_actually_changed` is computed AFTER snap-to-best (line 650-680).

**Q: Can I use different LLM models?**
A: Yes, edit `comm/communication_layer.py` line 221 to change model (currently "gpt-3.5-turbo").

**Q: How do I debug message quality issues?**
A: Enable LLM trace: add `llm_trace_file` parameter when calling `run_clustered_simulation`.

## Next Steps

1. **Verify your setup:** Run `python simple_test_runner.py --modes RB`
2. **Test LLM modes:** Run `python simple_test_runner.py --modes LLM_U LLM_C`
3. **Check message quality:** Look at `test_results/simple/LLM_U/communication_log.txt`
4. **Try interactive mode:** Run `python launch_menu.py` and play as human
5. **Run full analysis:** Run `python tests/comprehensive_agent_test.py --modes RB LLM_U LLM_C --trials 2`

Good luck! The system should now work properly with clear, actionable agent messages.
