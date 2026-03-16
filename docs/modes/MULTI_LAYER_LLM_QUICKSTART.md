# Multi-Layer LLM Quick Start Guide

## TL;DR

The system now has **two new LLM-based modes** where agents use actual LLM reasoning (not just message formatting):

- **LLM_TOOL**: Agents use OpenAI function calling to solve graph coloring
- **LLM_REACT**: Agents use ReAct (thought→action→observation) pattern

## 5-Minute Start

### 1. Setup (one-time)

```bash
# Add your OpenAI API key
echo "sk-your-api-key-here" > api_key.txt

# Verify installation
python test_multi_layer_llm.py
```

### 2. Run Experiment

```bash
# Launch GUI
python launch_menu.py

# Select:
# - Condition: "LLM_TOOL" or "LLM_REACT"
# - Algorithm: "greedy" (fast) or "maxsum" (optimal)
# - Use participant UI: Check
# - Max iterations: 10

# Click "Start"
```

### 3. What to Expect

1. **Announcement Phase**: Agents declare initial boundary colors
2. **Negotiation**: Agents reason about conflicts and propose solutions
3. **Messages**: Natural language with embedded color updates
4. **Logs**: Full reasoning traces in `results/` directory

## What's Different?

### Original LLM_API Mode
```
Human → Speech LLM → [Algorithmic Solver] → Speech LLM → Human
                     (greedy/maxsum only)
```

### New LLM_TOOL/REACT Modes
```
Human → Speech LLM → [Backend LLM + API Library] → Speech LLM → Human
                     (LLM reasoning + function calls)
```

## Choosing a Mode

### Use LLM_TOOL when:
- You want **structured, predictable** reasoning
- You need **clean audit trails** of function calls
- You value **reliability** over exploratory behavior
- You're okay with **moderate API costs**

### Use LLM_REACT when:
- You want to **study agent reasoning** explicitly
- You need **interpretable thought processes**
- You value **transparency** over efficiency
- You're doing **research on AI decision-making**

### Use LLM_API (original) when:
- You want **fast, cheap** baseline
- You need **algorithmic guarantees**
- You're comparing **LLM vs non-LLM** approaches

## Key Files

```
agents/
  cluster_agent_api.py          # API library (10+ graph coloring functions)
  tool_calling_cluster_agent.py # LLM_TOOL implementation
  react_cluster_agent.py         # LLM_REACT implementation

comm/
  speech_llm_layer.py            # Natural language translation layer

docs/
  MULTI_LAYER_LLM_ARCHITECTURE.md   # Full documentation
  MULTI_LAYER_LLM_QUICKSTART.md     # This file

test_multi_layer_llm.py         # Tests & examples
```

## Example: LLM_TOOL Flow

```python
# 1. Human says: "Can you change a2 to blue?"

# 2. Speech LLM parses to:
{
  "type": "proposal",
  "requested_changes": {"a2": "blue"},
  "sentiment": "neutral"
}

# 3. Backend LLM reasons:
# - Calls get_current_penalty() → penalty=2
# - Calls test_configuration({"a2": "blue"}) → feasible=true
# - Decides to accept

# 4. Backend LLM outputs:
{
  "should_send_message": true,
  "message_type": "acceptance",
  "structured_content": {
    "my_assignments": {"a1": "red", "a2": "blue", "a3": "green"},
    "reason": "That works! It resolves the conflict."
  }
}

# 5. Speech LLM renders:
"That works! Changing a2 to blue resolves the conflict. [report: {...}]"
```

## Example: LLM_REACT Flow

```
[Human] Can you fix the conflicts?

[Backend LLM] Thought: I need to identify current conflicts.
              Action: get_current_penalty()
[Agent]       Observation: {"penalty": 2, "conflicts": [("a2", "h1")]}

[Backend LLM] Thought: a2 conflicts with h1. Let me explore alternatives.
              Action: enumerate_alternatives(nodes=["a2"])
[Agent]       Observation: [{"a2": "blue"}, {"a2": "green"}]

[Backend LLM] Thought: Blue looks promising. Let me test it.
              Action: test_configuration({"a2": "blue"})
[Agent]       Observation: {"penalty": 0, "feasible": true}

[Backend LLM] Thought: Perfect! This resolves the conflict.
              Final Answer: {
                "should_send_message": true,
                "message_type": "proposal",
                "structured_content": {
                  "my_assignments": {"a1": "red", "a2": "blue", "a3": "green"},
                  "reason": "Changing a2 to blue resolves the conflict with h1."
                }
              }

[Speech LLM]  I found a solution! If I change a2 to blue, it resolves the
              conflict with h1. [report: {...}]
```

## Logging & Debugging

### Check Logs

```bash
# View tool calls (LLM_TOOL mode)
tail -f results/LLM_TOOL_*/llm_trace.jsonl

# View reasoning traces (LLM_REACT mode)
tail -f results/LLM_REACT_*/react_trace.jsonl

# View agent-specific logs
tail -f results/*/Agent1_log.txt
```

### Log Contents

**llm_trace.jsonl** (LLM_TOOL):
```json
{"timestamp": 123.45, "agent": "Agent1", "event": "tool_call", "function": "get_current_penalty", "result": {...}}
{"timestamp": 123.46, "agent": "Agent1", "event": "backend_decision", "decision": {...}}
```

**react_trace.jsonl** (LLM_REACT):
```json
{"timestamp": 123.45, "agent": "Agent1", "iteration": 0, "thought": "...", "action": "...", "observation": {...}}
{"timestamp": 123.50, "agent": "Agent1", "event": "final_answer", "decision": {...}}
```

## API Library Functions

### Core Operations
- `compute_assignments(algorithm)` - Run local solver
- `get_current_penalty()` - Check conflicts
- `test_configuration(assignments)` - Test "what if"

### Exploration
- `enumerate_alternatives(nodes)` - Generate options
- `get_conflict_resolution_options()` - Get fix suggestions

### Neighbor Operations
- `get_boundary_nodes(recipient)` - Get boundary nodes
- `get_neighbor_constraints(recipient)` - Check neighbor needs
- `simulate_neighbor_change(neighbor_nodes)` - Test impact

### Feasibility
- `check_feasibility(node, color)` - Test assignment
- `get_available_colors(node)` - Get valid colors

### Best Response
- `get_best_response_to(neighbor_assignments)` - Optimal response

## Cost Estimates

Based on typical 3-cluster graph with 5 nodes per cluster:

| Mode | Tokens/Turn | Cost/Turn* | Turns | Total Cost* |
|------|-------------|------------|-------|-------------|
| LLM_API (original) | ~500 | $0.005 | 10 | $0.05 |
| LLM_TOOL | ~2,000 | $0.020 | 10 | $0.20 |
| LLM_REACT | ~3,000 | $0.030 | 10 | $0.30 |

*Assuming gpt-4-turbo pricing (~$10/1M tokens). Actual costs vary.

**Tips to reduce cost**:
- Use `gpt-4o` instead of `gpt-4-turbo` (cheaper)
- Set `max_tokens` limits
- Use `manual_mode=True` for template-only (no API calls)

## Troubleshooting

### Issue: "Failed to initialize OpenAI client"
**Fix**: Check `api_key.txt` exists and contains valid key

### Issue: "No backend LLM available"
**Fix**: Verify OpenAI API is accessible, check network

### Issue: Colors don't appear in UI
**Fix**: Ensure announcement phase triggered, check logs for `[report: {...}]` tags

### Issue: Too expensive
**Fix**: Use `gpt-4o` model, reduce `max_react_iterations`, or use LLM_API baseline

### Issue: Slow performance
**Fix**: Use `gpt-4o` (faster), reduce context in prompts, or use algorithmic mode

## Next Steps

1. **Try both modes**: Run experiments with LLM_TOOL and LLM_REACT
2. **Compare logs**: Look at reasoning differences between modes
3. **Read full docs**: See `MULTI_LAYER_LLM_ARCHITECTURE.md`
4. **Customize prompts**: Edit agent files to tune behavior
5. **Run experiments**: Use for research on human-AI coordination

## Resources

- **Full documentation**: `docs/MULTI_LAYER_LLM_ARCHITECTURE.md`
- **Architecture overview**: `docs/ARCHITECTURE.md`
- **Troubleshooting**: `docs/TROUBLESHOOTING.md`
- **Tests**: `test_multi_layer_llm.py`

## Support

Questions? Issues?
1. Check logs in `results/` directory
2. Run `python test_multi_layer_llm.py` to verify setup
3. Review documentation in `docs/`
4. Check project README.md
