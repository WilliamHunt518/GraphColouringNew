# Multi-Layer LLM Architecture

## Overview

This document describes the multi-layer LLM architecture implemented for the graph coloring negotiation system. This architecture addresses a fundamental limitation of the original LLM_API mode: agents used **pure algorithmic solvers** (greedy/exhaustive search) with only a "speech LLM" layer for message formatting, creating a mismatch between sophisticated language capabilities and rigid algorithmic decision-making.

The new architecture introduces **true LLM-based reasoning** where agents use reasoning and function calling to solve the graph coloring problem, not just format messages.

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                         Human User                           │
│                   (Natural Language)                         │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ↓
┌─────────────────────────────────────────────────────────────┐
│                   Speech LLM Layer                           │
│   • Human NL → Backend Structured Messages                   │
│   • Backend Structured → Human NL                            │
│   • Preserves [report: {...}] tags for UI updates            │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ↓
┌─────────────────────────────────────────────────────────────┐
│                   Backend LLM Layer                          │
│   Two Modes:                                                 │
│   • LLM_TOOL: OpenAI Function/Tool Calling                   │
│   • LLM_REACT: ReAct (Reasoning and Acting) Pattern          │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ↓
┌─────────────────────────────────────────────────────────────┐
│                    API Library                               │
│   • compute_assignments()                                    │
│   • enumerate_alternatives()                                 │
│   • test_configuration()                                     │
│   • get_current_penalty()                                    │
│   • ... (10+ graph coloring operations)                      │
└─────────────────────────────────────────────────────────────┘
```

## Two Implementation Modes

### LLM_TOOL: OpenAI Function Calling

**Pattern**: Structured API with automatic function dispatch

**How it works**:
1. Agent defines OpenAI function schemas for all API methods
2. Backend LLM calls functions using structured tool_calls
3. Agent executes functions and returns results to LLM
4. LLM continues reasoning until ready to respond
5. Final decision is translated to natural language via speech LLM

**Advantages**:
- Structured and predictable
- Clean separation between reasoning and action
- Easy to debug and trace
- Well-supported by OpenAI API

**Use case**: When you want reliable, structured decision-making with clear auditability

**Example flow**:
```json
[Backend LLM] → tool_call: get_current_penalty()
[Agent]       → result: {"penalty": 2, "conflicts": [("a2", "h1")]}
[Backend LLM] → tool_call: enumerate_alternatives(nodes=["a2"])
[Agent]       → result: [{"a2": "blue"}, {"a2": "green"}]
[Backend LLM] → tool_call: test_configuration({"a2": "blue"})
[Agent]       → result: {"penalty": 0, "feasible": true}
[Backend LLM] → decision: {"should_send_message": true, ...}
[Speech LLM]  → "I propose changing a2 to blue to resolve the conflict."
```

### LLM_REACT: ReAct Pattern

**Pattern**: Thought → Action → Observation loop

**How it works**:
1. Agent provides ReAct system prompt with examples
2. Backend LLM generates: Thought + Action
3. Agent executes action, returns observation
4. LLM continues with next Thought + Action
5. After several cycles, LLM provides Final Answer
6. Final answer is translated to natural language via speech LLM

**Advantages**:
- Explicit reasoning traces (valuable for research)
- Human-readable thought process
- Flexible and exploratory
- Can recover from errors through reasoning

**Use case**: When you want to study agent reasoning processes and need interpretable decision traces

**Example flow**:
```
[Backend LLM] Thought: I need to check if my current assignment has conflicts.
              Action: get_current_penalty()
[Agent]       Observation: {"penalty": 2, "conflicts": [("a2", "h1")]}

[Backend LLM] Thought: There are 2 conflicts. Let me explore alternatives for a2.
              Action: enumerate_alternatives(nodes=["a2"])
[Agent]       Observation: [{"a2": "blue"}, {"a2": "green"}]

[Backend LLM] Thought: Blue looks promising. Let me test it.
              Action: test_configuration({"a2": "blue"})
[Agent]       Observation: {"penalty": 0, "feasible": true}

[Backend LLM] Thought: Perfect! This resolves all conflicts.
              Final Answer: {
                "should_send_message": true,
                "message_type": "proposal",
                "structured_content": {
                  "my_assignments": {"a1": "red", "a2": "blue", "a3": "green"},
                  "reason": "Changing a2 to blue resolves conflicts with h1"
                }
              }
[Speech LLM]  "I found a solution! If I change a2 to blue, it resolves the conflict with h1."
```

## Components

### 1. API Library (`agents/cluster_agent_api.py`)

**Purpose**: Clean API exposing ClusterAgent's algorithmic functions for LLM use

**Key Methods**:

#### Core Operations
- `compute_assignments(algorithm)`: Run local solver (greedy/maxsum)
- `get_current_penalty()`: Get penalty and conflicts
- `test_configuration(assignments)`: Test hypothetical assignments

#### Exploration
- `enumerate_alternatives(nodes, max_alternatives)`: Generate feasible options
- `get_conflict_resolution_options(max_options)`: Get specific conflict fixes

#### Neighbor Operations
- `get_boundary_nodes(recipient)`: Get boundary nodes for neighbor
- `get_neighbor_constraints(recipient)`: Check what colors neighbors need
- `simulate_neighbor_change(neighbor_nodes)`: Test impact of neighbor recoloring

#### Feasibility Checking
- `check_feasibility(node, color)`: Test specific assignment
- `get_available_colors(node)`: Get feasible colors for node

#### Best Response
- `get_best_response_to(neighbor_assignments)`: Compute optimal local coloring

**Design Principles**:
- All methods are pure or have clear side effects documented
- Results are JSON-serializable for LLM consumption
- Comprehensive docstrings with type hints
- Logging for research traceability

### 2. Tool Calling Agent (`agents/tool_calling_cluster_agent.py`)

**Purpose**: Agent using OpenAI function calling for backend reasoning

**Key Features**:
- Builds OpenAI function schemas for all API methods
- Implements tool execution loop in `step()`
- Logs all tool calls to `llm_trace.jsonl`
- Fallback to algorithmic mode if LLM unavailable
- Integrates with speech LLM for natural language output

**Configuration**:
- `backend_model`: OpenAI model (default: "gpt-4-turbo")
- Supports announcement phase (same as ClusterAgent)
- Inherits all ClusterAgent functionality

### 3. ReAct Agent (`agents/react_cluster_agent.py`)

**Purpose**: Agent using ReAct pattern for backend reasoning

**Key Features**:
- Implements thought→action→observation loop
- Parses actions from natural language format
- Logs full reasoning trajectory to `react_trace.jsonl`
- Max iterations configurable (default: 10)
- Explicit reasoning traces for research analysis

**Configuration**:
- `backend_model`: OpenAI model (default: "gpt-4-turbo")
- `max_react_iterations`: Maximum reasoning steps (default: 10)
- Supports announcement phase (same as ClusterAgent)

### 4. Speech LLM Layer (`comm/speech_llm_layer.py`)

**Purpose**: Bidirectional translation between human NL and backend structured protocol

**Key Features**:

#### Human → Backend (`human_to_backend`)
Parses natural language to extract:
- **Type**: question | proposal | acceptance | rejection | constraint | info
- **Requested changes**: {node: color} assignments
- **Constraints**: Forbidden/required colors
- **Conditions**: If-then statements
- **Sentiment**: positive | neutral | negative

#### Backend → Human (`backend_to_human`)
Translates structured outputs to natural language:
- Maintains conversational tone
- Preserves `[report: {...}]` tags for UI updates
- Handles all message types (proposal, question, acceptance, etc.)

#### Fallback Modes
- LLM-based parsing/rendering (primary)
- Heuristic parsing (fallback if LLM unavailable)
- Template rendering (fallback for output)

## Logging & Observability

### Tool Calling Mode (`llm_trace.jsonl`)

Each tool call is logged:
```json
{
  "timestamp": 1707675000.123,
  "agent": "Agent1",
  "event": "tool_call",
  "function": "enumerate_alternatives",
  "arguments": {"nodes": ["a2", "a5"], "max_alternatives": 10},
  "result": [{"a2": "blue", "a5": "green"}, ...]
}
```

Backend decisions are logged:
```json
{
  "timestamp": 1707675001.456,
  "agent": "Agent1",
  "event": "backend_decision",
  "decision": {
    "should_send_message": true,
    "recipient": "Human",
    "message_type": "proposal",
    "structured_content": {...}
  }
}
```

### ReAct Mode (`react_trace.jsonl`)

Each reasoning step is logged:
```json
{
  "timestamp": 1707675000.123,
  "agent": "Agent1",
  "iteration": 0,
  "thought": "I need to check if my current assignment has any conflicts.",
  "action": "get_current_penalty()",
  "observation": {"penalty": 2, "conflicts": [["a2", "h1"]]}
}
```

Final answers are logged:
```json
{
  "timestamp": 1707675005.789,
  "agent": "Agent1",
  "event": "final_answer",
  "decision": {
    "should_send_message": true,
    "recipient": "Human",
    "message_type": "proposal",
    "structured_content": {...}
  }
}
```

## Usage

### Running Experiments

1. **Add OpenAI API key**:
   ```bash
   echo "sk-your-api-key" > api_key.txt
   ```

2. **Launch GUI**:
   ```bash
   python launch_menu.py
   ```

3. **Select mode**:
   - Choose "LLM_TOOL" for function calling
   - Choose "LLM_REACT" for ReAct pattern

4. **Configure settings**:
   - Algorithm: greedy (fast) or maxsum (optimal)
   - Use participant UI: Yes for human-in-the-loop
   - Max iterations: Depends on problem complexity

5. **Start experiment**:
   - Click "Start"
   - Agents will announce initial configurations
   - Negotiation proceeds with LLM reasoning

### Programmatic Usage

```python
from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
from comm.speech_llm_layer import SpeechLLMLayer
from problems.graph_coloring import GraphColoring

# Create problem
problem = GraphColoring(nodes=..., edges=..., domain=...)

# Create speech layer
comm_layer = SpeechLLMLayer(model="gpt-4-turbo", use_llm=True)

# Create agent
agent = ToolCallingClusterAgent(
    name="Agent1",
    problem=problem,
    comm_layer=comm_layer,
    local_nodes=["a1", "a2", "a3"],
    owners={"a1": "Agent1", "a2": "Agent1", "a3": "Agent1", ...},
    backend_model="gpt-4-turbo",
    algorithm="greedy"
)

# Run reasoning step
agent.step()

# Check results
print(agent.assignments)
```

## Performance Considerations

### Token Optimization

- **Backend model**: Use `gpt-4-turbo` or `gpt-4o` for lower cost
- **Speech model**: Can use smaller model like `gpt-3.5-turbo`
- **System prompts**: Keep concise while providing necessary context

### Caching

- API results are cached within a turn (e.g., `enumerate_alternatives`)
- Prevents redundant expensive computations
- Cache invalidated when boundary state changes

### Timeouts & Limits

- `max_tokens`: Set appropriate limits to prevent runaway costs
- `timeout`: Configure request timeouts for reliability
- `max_iterations`: Limit ReAct loops to prevent infinite reasoning

### Rate Limiting

- Handle OpenAI rate limits gracefully
- Implement exponential backoff for retries
- Consider async processing for multiple agents

## Error Handling

### LLM API Failures
- **Strategy**: Log error, retry once, fall back to algorithmic solver
- **Benefit**: Experiment continues even if LLM unavailable
- **Logging**: All failures logged for post-hoc analysis

### Invalid Tool Calls
- **Strategy**: Return error in observation, let LLM recover
- **Benefit**: LLM can adjust strategy based on error
- **Example**: If `enumerate_alternatives` is too expensive, suggest simpler approach

### Parse Failures
- **Strategy**: Log warning, ask LLM to reformat response
- **Benefit**: Recovers from malformed JSON in Final Answer
- **Fallback**: Use template rendering if parse fails repeatedly

### Speech Layer Failures
- **Strategy**: Use template rendering as fallback
- **Benefit**: Messages always sent, even if LLM unavailable
- **Trade-off**: Less natural language quality

## Comparison with Original LLM_API Mode

| Aspect | Original LLM_API | New LLM_TOOL/REACT |
|--------|------------------|-------------------|
| **Backend reasoning** | Algorithmic only | LLM-based |
| **Decision-making** | Greedy/exhaustive search | Function calling or ReAct |
| **Flexibility** | Fixed algorithm | Adaptive reasoning |
| **Observability** | Limited | Full LLM traces |
| **Cost** | Low (no LLM backend) | Higher (2 LLMs) |
| **Speed** | Fast | Slower (multiple API calls) |
| **Research value** | Baseline | High (reasoning traces) |

## Migration Path

The original `LLM_API` mode is **still available** and can be used as:

1. **Baseline**: For comparing LLM reasoning vs algorithmic
2. **Cost-effective**: When LLM backend is too expensive
3. **Fast prototyping**: When speed is more important than flexibility

To use original mode:
- Select "LLM_API" in launcher (not "LLM_TOOL" or "LLM_REACT")
- Uses algorithmic solver + LLM formatting only

## Experimental Design Considerations

### Within-Subject Conditions

Compare reasoning patterns across modes:
- **RB**: Pure rule-based (baseline)
- **LLM_API**: Algorithmic + LLM formatting
- **LLM_TOOL**: LLM reasoning + function calling
- **LLM_REACT**: LLM reasoning + explicit thoughts

### Metrics to Track

1. **Solution Quality**:
   - Final penalty
   - Number of iterations to convergence
   - Optimality gap vs global optimum

2. **Communication**:
   - Message count
   - Message length
   - Natural language quality (human ratings)

3. **Reasoning Transparency**:
   - Number of tool calls (LLM_TOOL)
   - Thought-action cycles (LLM_REACT)
   - Human understanding of agent rationale

4. **Cost & Performance**:
   - Total tokens used
   - Wall-clock time
   - API costs

### Research Questions

1. Does LLM reasoning lead to better solutions than algorithmic?
2. Do humans prefer communicating with LLM-reasoned agents?
3. Are ReAct thought traces more interpretable than function calls?
4. What's the cost/benefit trade-off for LLM backend reasoning?

## Future Extensions

### Planned
- [ ] Support for Claude API (not just OpenAI)
- [ ] Prompt optimization via few-shot learning
- [ ] Cost tracking and budget limits
- [ ] Async multi-agent reasoning

### Experimental
- [ ] Self-reflection: LLM critiques its own reasoning
- [ ] Meta-reasoning: LLM chooses which mode to use
- [ ] Learning: Agent improves prompts based on outcomes
- [ ] Multi-modal: Visual graph representations

## Troubleshooting

### "Failed to initialize OpenAI client"
- **Cause**: Missing or invalid `api_key.txt`
- **Fix**: Create file with valid OpenAI API key

### "No backend LLM available, falling back to algorithmic mode"
- **Cause**: OpenAI client failed to initialize
- **Fix**: Check API key, network connection, OpenAI status

### "Max iterations reached without Final Answer"
- **Cause**: ReAct loop didn't converge
- **Fix**: Increase `max_react_iterations` or improve prompt

### Colors don't appear after announcement
- **Cause**: Report tag stripped from message
- **Fix**: Ensure speech layer preserves `[report: {...}]` suffix

### High API costs
- **Cause**: Too many tool calls or long conversations
- **Fix**: Use `gpt-4o` or `gpt-4-turbo`, set token limits

## References

- **OpenAI Function Calling**: https://platform.openai.com/docs/guides/function-calling
- **ReAct Paper**: "ReAct: Synergizing Reasoning and Acting in Language Models" (Yao et al., 2022)
- **Original System**: See `ARCHITECTURE.md` for base system design

## Contact & Support

For questions or issues:
- **Documentation**: See `docs/` directory
- **Examples**: See `test_multi_layer_llm.py`
- **Issues**: Report at project repository
