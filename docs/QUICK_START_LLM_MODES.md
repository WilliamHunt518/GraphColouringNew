# Quick Start: LLM_TOOL and LLM_REACT Modes

## What Are These Modes?

**LLM_TOOL** and **LLM_REACT** are new agent modes that use LLMs for reasoning, not just communication:

| Mode | Backend | Communication | Best For |
|------|---------|---------------|----------|
| LLM_API (existing) | Algorithmic | LLM formatting | Baseline comparison |
| **LLM_TOOL** | LLM with function calling | Speech LLM | Structured problem-solving |
| **LLM_REACT** | LLM with ReAct pattern | Speech LLM | Explainable reasoning traces |

## Prerequisites

### 1. OpenAI API Key

Create `api_key.txt` in the project root:
```bash
echo "sk-your-api-key-here" > api_key.txt
```

**Note**: Without API key, agents fall back to algorithmic mode.

### 2. OpenAI Package Version

Ensure you have openai >= 2.20.0:
```bash
pip install --upgrade openai
python -c "import openai; print(openai.__version__)"
```

Should output: `2.20.0` or higher

## Running from GUI (Recommended)

### Step 1: Launch Menu
```bash
python launch_menu.py
```

### Step 2: Select Mode
- Choose **LLM_TOOL** or **LLM_REACT** from "Communication Mode" dropdown

### Step 3: Configure (Optional)
- Check "Use participant UI" for interactive experiments
- Check "Use greedy algorithm" (recommended for faster iterations)
- Other settings can use defaults

### Step 4: Start
- Click **Start**
- UI will open with graph view and chat panes

### Step 5: Announce Configuration
- Click **Announce Configuration** button
- Agents will send initial boundary assignments
- Example: `"Here's my initial configuration: a2=blue, a4=red"`
- Node colors should appear in graph view

### Step 6: Negotiate
- Send messages to agents via chat panes
- Agents will respond with proposals, questions, acceptances
- Continue until consensus reached

## Running from Command Line

### LLM_TOOL Mode
```bash
python run_experiment.py --method LLM_TOOL --use_ui true
```

### LLM_REACT Mode
```bash
python run_experiment.py --method LLM_REACT --use_ui true
```

### Additional Options
```bash
python run_experiment.py \
  --method LLM_TOOL \
  --use_ui true \
  --algorithm greedy \
  --graph_file experiments/graphs/3cluster_example.json
```

## What to Expect

### LLM_TOOL Behavior
Agents use OpenAI function calling to:
1. Analyze current state
2. Call API functions (compute_assignments, enumerate_alternatives, etc.)
3. Reason about results
4. Generate natural language messages

Example conversation:
```
[Agent1] Here's my initial configuration: a2=blue, a4=red
[Human] Can you change a2 to green?
[Agent1] I propose a2=green, a4=blue. This resolves the conflict and works with your constraints.
[Human] That works for me
[Agent1] Great! I'll keep a2=green, a4=blue then.
```

### LLM_REACT Behavior
Agents use explicit reasoning traces:
```
Thought: I need to check if there are conflicts with my current assignment.
Action: get_current_penalty()
Observation: {"penalty": 2, "conflicts": [("a2", "h1")]}

Thought: Let me explore alternatives for a2.
Action: enumerate_alternatives(["a2"])
Observation: [{"a2": "green"}, {"a2": "yellow"}]

Thought: I'll propose green for a2.
Final Answer: [sends natural language proposal]
```

## Troubleshooting

### No Agent Responses

**Symptom**: Click "Announce Configuration", nothing happens

**Solutions**:
1. Check console for errors
2. Verify API key is valid
3. Check OpenAI package version: `pip show openai`

### Raw JSON in Chat

**Symptom**: Messages show `{'type': 'announcement', ...}` instead of natural language

**Solutions**:
1. Verify you're using the updated code (after 2026-02-11)
2. Run test: `python test_announcement_nl_format.py`
3. Check that SpeechLLMLayer has `format_content()` method

### Node Colors Don't Update

**Symptom**: Announcement appears but nodes stay grey

**Solutions**:
1. Check message includes `[report: {...}]` tag
2. Verify report format: `[report: {"node": "color"}]`
3. Run test: `python test_announcement_nl_format.py`

### Backend LLM Not Used

**Symptom**: Agents behave like algorithmic mode

**Solutions**:
1. Check `api_key.txt` exists and has valid key
2. Check console for "Backend LLM not available" warning
3. Verify model name is "gpt-4-turbo" or "gpt-4"

## Testing

### Verify Installation
```bash
# Run all tests (should take ~10 seconds)
python test_multi_layer_llm.py
python test_integration_new_modes.py
python test_announcement_nl_format.py
```

All should output: `[OK] ALL TESTS PASSED!`

### Quick Smoke Test
```bash
python launch_menu.py
# Select LLM_TOOL
# Check "Use participant UI"
# Click Start
# Click "Announce Configuration"
# Verify: agents send natural language messages, colors appear
```

## Cost Considerations

### Token Usage

LLM modes use tokens for:
- Backend reasoning (major cost)
- Tool calls and observations
- Speech layer translation

Approximate costs per turn (with gpt-4-turbo):
- **LLM_TOOL**: 500-2000 tokens ($0.01-$0.04)
- **LLM_REACT**: 800-3000 tokens ($0.016-$0.06)

### Cost Optimization Tips

1. **Use greedy algorithm**: Faster iterations, fewer API calls
2. **Shorter experiments**: Set turn limits
3. **Use gpt-4o-mini**: 10x cheaper if reasoning quality acceptable
4. **Template mode**: Set `use_llm=False` in SpeechLLMLayer for testing

### Without API Key

System works without API key:
- Backend: Falls back to algorithmic mode
- Communication: Uses template-based rendering
- Result: Similar to existing LLM_API mode

## Logging

### Where to Find Logs

After running experiment, check `results/<mode>_<timestamp>/`:

- `llm_trace.jsonl`: All LLM interactions (tool calls, responses)
- `react_trace.jsonl`: ReAct reasoning traces (LLM_REACT only)
- `communication_log.txt`: Full message exchange
- `Agent1_log.txt`, `Agent2_log.txt`: Per-agent logs
- `iteration_summary.txt`: Turn-by-turn summary

### Log Format

**llm_trace.jsonl** (LLM_TOOL):
```json
{"timestamp": "...", "agent": "Agent1", "event": "tool_call", "function": "compute_assignments", "result": {...}}
```

**react_trace.jsonl** (LLM_REACT):
```json
{"timestamp": "...", "agent": "Agent1", "iteration": 0, "thought": "...", "action": "...", "observation": {...}}
```

## Comparison: Which Mode to Use?

### Use LLM_TOOL when:
- You want structured problem-solving
- You need faster iterations
- You want to analyze tool usage patterns
- You're running large-scale experiments

### Use LLM_REACT when:
- You need explainable reasoning
- You want to study decision-making processes
- You're doing qualitative analysis
- You want transparent thought traces

### Use LLM_API (existing) when:
- You need a baseline for comparison
- You want deterministic algorithmic behavior
- You're prototyping message formats
- You don't need LLM reasoning

## Advanced: Customizing Prompts

### Tool Calling System Prompt

Edit `agents/tool_calling_cluster_agent.py`, line ~150-200:
```python
def _build_system_prompt(self) -> str:
    # Customize this prompt
    return f"""You are solving a graph coloring problem...
    ...
    """
```

### ReAct Prompt Template

Edit `agents/react_cluster_agent.py`, line ~200-300:
```python
def _load_react_prompt(self) -> str:
    # Customize ReAct format here
    return """
    You are solving a graph coloring problem...
    Thought: [reasoning]
    Action: [function call]
    ...
    """
```

### Speech Layer Prompts

Edit `comm/speech_llm_layer.py`:
- Line ~196-232: Human→Backend prompt
- Line ~304-327: Backend→Human prompt

## Getting Help

### Documentation
- Full details: `docs/MULTI_LAYER_LLM_IMPLEMENTATION.md`
- Architecture: `docs/ARCHITECTURE.md`
- General help: `README.md`

### Common Questions

**Q: Do I need both API key and these modes?**
A: No. System works without API key (falls back to algorithmic mode).

**Q: Which model should I use?**
A: gpt-4-turbo is recommended (good balance of cost/quality). gpt-4o-mini works for lower cost.

**Q: How much will this cost?**
A: Approximately $0.01-$0.06 per turn with gpt-4-turbo. Track usage in OpenAI dashboard.

**Q: Can I use other LLM providers?**
A: Currently only OpenAI supported. Could extend to Anthropic/others with minor changes.

**Q: What's the difference from LLM_API mode?**
A: LLM_API uses algorithmic backend with optional LLM formatting. LLM_TOOL/LLM_REACT use LLM for reasoning.

## Next Steps

1. ✅ Install prerequisites (API key, openai package)
2. ✅ Run tests to verify installation
3. ✅ Try quick smoke test from GUI
4. ✅ Run full experiment with LLM_TOOL
5. ✅ Try LLM_REACT mode
6. ✅ Analyze logs and traces
7. ✅ Compare with existing LLM_API mode

## Status

- **Implementation**: ✅ Complete
- **Testing**: ✅ All tests passing
- **Documentation**: ✅ Complete
- **Ready for use**: ✅ Yes

Last updated: 2026-02-11
