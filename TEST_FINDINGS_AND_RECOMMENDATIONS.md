# Agent Testing - Findings and Recommendations

**Generated:** 2026-01-15

## Executive Summary

After implementing comprehensive test infrastructure and running initial tests, several critical issues have been identified in the LLM agent communication system. This report summarizes findings and provides actionable recommendations.

## Test Infrastructure Created

1. **Human Emulator Agent** (`tests/human_emulator_agent.py`)
   - Emulates realistic human behavior (accepts suggestions 60%, imposes constraints 30%, asks questions 20%)
   - Makes random explorations
   - Marks satisfied after max turns or zero penalty

2. **Comprehensive Test Suite** (`tests/comprehensive_agent_test.py`)
   - Tests all modes: RB, LLM_U, LLM_C, LLM_F
   - Analyzes message quality (hallucinations, repetitions, topic switching, clarity)
   - Tracks convergence behavior
   - Generates detailed reports with metrics

3. **Simple Test Runner** (`simple_test_runner.py`)
   - Quick validation of each mode
   - Measures penalty, iterations, messages, elapsed time

## Initial Test Results

### Rule-Based (RB) Baseline
- **Status:** ✓ SUCCESS
- **Final Penalty:** 0.0
- **Iterations:** 20
- **Time:** 2.96s
- **Assessment:** Works correctly, achieves zero penalty consistently

### LLM Modes (Based on Log Analysis)
Based on examination of `results/llm_u/communication_log.txt` and `results/llm_c/communication_log.txt`:

#### LLM_U (Utility/Cost List)
**Critical Issues Identified:**

1. **Message Repetition & Vagueness**
   - Agents repeatedly send "I currently think your boundary colours are..."
   - Messages like "all is fine" without clear numerical proposals
   - **Impact:** Human can't make informed decisions

2. **Lack of Clear Conditional Proposals**
   - Should say: "If you set h1=red, h4=blue, I can score 9"
   - Actually says: "Alternatives I can support..." (vague)
   - **Impact:** Human doesn't understand tradeoffs

3. **Current Setting Filtered Out**
   - Only shows "alternatives", not current option
   - Human can't compare current vs. alternatives
   - **Impact:** No baseline for comparison

**Fixes Applied:**
- ✓ Changed message format to show top 5 feasible options INCLUDING current
- ✓ Added clear numbering: "1. If you set h1=red, h4=blue, I can score 9. ← YOUR CURRENT SETTING"
- ✓ Removed filtering of current configuration

#### LLM_C (Constraints)
**Critical Issues Identified:**

1. **Only Shows Individual Node Constraints**
   - Says: "h1 ∈ {green, blue}; h4 ∈ {red}"
   - Doesn't enumerate complete valid configurations
   - **Impact:** Human must mentally compute Cartesian product

2. **No Prioritization**
   - All constraint combinations treated equally
   - Doesn't indicate which are "better"
   - **Impact:** Human has no guidance on which to choose

**Fixes Applied:**
- ✓ Added enumeration of complete valid configurations
- ✓ Format: "1. h1=green, h4=red\n2. h1=blue, h4=red"
- ✓ Limited to top 10 to avoid overwhelming human
- ✓ Still shows per-node summary for reference

## Critical Bug Fixed

**Bug:** `UnboundLocalError: local variable 're' referenced before assignment`
- **Location:** `agents/cluster_agent.py` line 1324
- **Cause:** `import re` was inside a conditional block (only executed for human messages)
- **Impact:** All non-human agent messages crashed when parsing
- **Fix:** Added `import re` at line 1324 before use
- **Status:** ✓ FIXED

## Issues Still Requiring Investigation

### 1. Agent Hallucination (High Priority)
**Symptom:** Agents claim "I changed X to Y" but report shows different color

**Example from logs:**
```
Agent says: "I changed b2 to blue"
Report shows: [report: {'b2': 'red'}]
```

**Root Cause:** Message generated BEFORE snap-to-best runs
- Greedy assigns color
- Message generated based on greedy result
- Snap-to-best OVERRIDES assignment
- Message sent with stale information

**Fix Applied (needs verification):**
- Added `assignments_actually_changed` flag recomputed AFTER snap-to-best
- Updated conversational response to use final state
- Added defensive verification in `_respond_to_human_conversationally`

**Testing Needed:** Run LLM_U test and verify no discrepancies in logs

### 2. Satisfaction Not Reset on Boundary Changes (Medium Priority)
**Symptom:** Agent stays satisfied even when human changes boundary colors

**Root Cause:** No tracking of previous boundary state

**Fix Applied (needs verification):**
- Added `_previous_neighbour_assignments` tracking
- Detect changes and reset `satisfied=False`
- Log "NEIGHBOR BOUNDARY CHANGED" with details

**Testing Needed:** Mark agent satisfied, change human boundary, verify satisfaction resets

### 3. Topic Switching & Rambling (Medium Priority)
**Symptom:** LLM agents mention multiple unrelated concepts in single message

**Potential Causes:**
- LLM prompts too open-ended
- No explicit format constraints
- Conversation history causing drift

**Recommended Fixes:**
- Add structured templates to LLM prompts
- Use few-shot examples of good vs. bad messages
- Limit message to single purpose (either proposal OR question, not both)

### 4. Convergence Issues (Low Priority)
**Symptom:** Agents may oscillate or get stuck

**Potential Causes:**
- Snap-to-best threshold too aggressive
- Greedy algorithm limitations
- Boundary conflicts not resolved

**Monitoring:**
- Track penalty trajectory
- Count improvements vs. regressions
- Detect oscillations (same penalty repeating 3+ times)

## Recommendations by Priority

### Immediate (Do Now)

1. **Verify Hallucination Fix**
   ```bash
   python simple_test_runner.py --modes LLM_U
   ```
   - Check logs for discrepancies between claimed and actual changes
   - Look for patterns: `grep "changed.*to" test_results/simple/LLM_U/communication_log.txt`
   - Compare with `[report: ...]` sections

2. **Run Comprehensive Test Suite**
   ```bash
   python tests/comprehensive_agent_test.py --modes RB LLM_U LLM_C --trials 3
   ```
   - Get quantitative metrics on message quality
   - Identify remaining issues with data

3. **Add Solution Hint at Startup**
   - ✓ Already implemented in `cluster_simulation.py` lines 235-253
   - Prints valid coloring when solvability check passes
   - Helps human understand what they're aiming for

### Short Term (This Week)

4. **Improve LLM Prompts**
   - Add explicit format requirements to `comm/communication_layer.py`
   - Include negative examples ("Don't say: 'all is fine'")
   - Use few-shot prompting with good examples

5. **Add Message Deduplication**
   - Track last N messages sent
   - Only send if content meaningfully different
   - Prevents repetition loops

6. **Test Satisfaction Reset**
   - Manual test: run system, mark satisfied, change boundary, verify reset
   - Add to automated test suite

### Medium Term (Next Sprint)

7. **Enhance Counterfactual Enumeration**
   - For LLM_C: verify all enumerated configs are actually valid
   - Add scores to each config (like LLM_U) for better comparison
   - Consider hybrid: "These 3 configs all give zero penalty, choose any"

8. **Add Oscillation Detection**
   - Track penalty history
   - If same value repeats 3+ times, trigger intervention
   - Options: random perturbation, ask human for guidance, increase exploration

9. **Improve Convergence Criteria**
   - Current: `penalty == 0`
   - Better: `penalty == 0 AND no changes in last K turns`
   - Prevents premature satisfaction

### Long Term (Future Work)

10. **LLM-Specific Tuning**
    - Fine-tune prompts per mode (LLM_U vs. LLM_C vs. LLM_F)
    - A/B test different prompt strategies
    - Consider model selection (GPT-4 vs. GPT-3.5 vs. others)

11. **Human-in-Loop Validation**
    - Run actual human trials
    - Compare human emulator behavior to real human behavior
    - Adjust emulator parameters based on findings

12. **Performance Optimization**
    - Cache LLM responses for repeated patterns
    - Reduce unnecessary counterfactual computations
    - Parallelize agent steps where possible

## Success Metrics

To evaluate fixes, track these metrics across test runs:

### Message Quality (Target: >80/100)
- Hallucination rate: < 5%
- Repetition count: < 2 per run
- Clear proposals: > 80% of messages
- Vague statements: < 10% of messages

### Convergence (Target: >90% success rate)
- Reaches zero penalty: yes/no
- Iterations to convergence: < 30
- No oscillations: penalty doesn't repeat 3+ times

### User Experience (Qualitative)
- Messages are understandable: yes/no
- Clear what action to take: yes/no
- System responsive to changes: yes/no

## Testing Checklist

Before deploying fixes:

- [x] RB baseline test passes
- [ ] LLM_U test passes (0 hallucinations)
- [ ] LLM_C test passes (valid configs enumerated)
- [ ] LLM_F test passes (if implemented)
- [ ] Hallucination fix verified in logs
- [ ] Satisfaction reset verified
- [ ] Solution hint displays correctly
- [ ] No regressions in existing functionality
- [ ] All 3 communication log fixes validated

## Running the Full Test Suite

```bash
# Quick validation (one trial each mode)
python simple_test_runner.py --modes RB LLM_U LLM_C

# Comprehensive analysis (3 trials, detailed metrics)
python tests/comprehensive_agent_test.py --modes RB LLM_U LLM_C --trials 3

# All-agent tests (no human emulator)
python test_agent_modes.py --modes RB LLM_U --trials 3

# Master runner (everything)
python run_all_tests.py
```

## Conclusion

The agent system shows promise, but LLM-based communication requires significant refinement:

**Working Well:**
- ✓ Rule-based baseline is solid
- ✓ Core optimization algorithms (greedy, snap-to-best) functional
- ✓ Graph coloring problem formulation correct

**Needs Work:**
- ✗ LLM message generation (hallucinations, vagueness, repetition)
- ✗ Satisfaction tracking (doesn't reset on boundary changes)
- ✗ Message clarity (hard to extract actionable information)

**Priority:** Focus on message generation quality first. Even perfect optimization algorithms are useless if humans can't understand or trust the agent messages.

**Next Steps:**
1. Run comprehensive tests to get quantitative data
2. Verify hallucination fix with real LLM calls
3. Iterate on LLM prompts based on test results
4. Re-test and measure improvement

---

**Test Infrastructure Status:**
- Test framework: ✓ Complete
- Human emulator: ✓ Implemented
- Message quality analysis: ✓ Implemented
- Automated testing: ✓ Ready
- Continuous integration: ⧗ Pending (run tests manually for now)

**Files Created:**
- `tests/human_emulator_agent.py` - Human behavior emulation
- `tests/comprehensive_agent_test.py` - Full test suite with analysis
- `tests/__init__.py` - Test package marker
- `simple_test_runner.py` - Quick validation script
- `run_all_tests.py` - Master test orchestrator
- `TEST_FINDINGS_AND_RECOMMENDATIONS.md` - This document
