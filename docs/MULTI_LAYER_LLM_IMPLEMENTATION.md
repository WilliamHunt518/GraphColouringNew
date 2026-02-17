# Multi-Layer LLM Architecture Implementation

**Implementation Date**: 2026-02-11
**Status**: ✅ Complete and tested

## Overview

This document describes the implementation of a multi-layer LLM architecture for the ClusterAgent system, introducing two new agent modes: **LLM_TOOL** (OpenAI function calling) and **LLM_REACT** (ReAct reasoning pattern).

## Architecture

### Three-Layer Design

```
Human (Natural Language)
         ↕
Speech LLM Layer (Bidirectional Translation)
         ↕
Backend LLM (Reasoning + Function Calling)
         ↕
API Library (Algorithmic Functions)
```

### Key Components

1. **API Library** (`agents/cluster_agent_api.py`)
   - Exposes 11 algorithmic functions for LLM use
   - Clean interface for graph coloring operations
   - Examples: compute_assignments, enumerate_alternatives, test_configuration

2. **Speech LLM Layer** (`comm/speech_llm_layer.py`)
   - Translates human natural language → structured backend protocol
   - Renders backend structured output → natural language for human
   - Preserves report tags for UI color updates

3. **Tool Calling Agent** (`agents/tool_calling_cluster_agent.py`)
   - Uses OpenAI function calling pattern
   - Backend LLM calls API functions to solve problems
   - Comprehensive logging of tool calls

4. **ReAct Agent** (`agents/react_cluster_agent.py`)
   - Uses ReAct (Reasoning and Acting) pattern
   - Thought → Action → Observation loop
   - Explicit reasoning traces for research analysis

## Implementation Details

### Phase 1: API Library (cluster_agent_api.py)

Created clean API with 11 functions:

```python
class ClusterAgentAPI:
    """API library for graph coloring operations exposed to backend LLM."""

    def compute_assignments(self, algorithm: str = "greedy") -> Dict[str, str]:
        """Run local solver and return node assignments."""

    def get_current_penalty(self) -> Tuple[float, List[Tuple[str, str]]]:
        """Return current penalty and list of conflicts."""

    def enumerate_alternatives(self, nodes: List[str]) -> List[Dict[str, str]]:
        """Enumerate alternative colorings for specified nodes."""

    def test_configuration(self, assignments: Dict[str, str]) -> Dict[str, Any]:
        """Test a proposed configuration and return penalty, conflicts, feasibility."""

    def get_neighbor_constraints(self, recipient: str) -> Dict[str, Any]:
        """Get constraints from neighbor's perspective."""

    def get_boundary_nodes(self, recipient: str) -> List[str]:
        """Get boundary nodes for a specific neighbor."""

    def check_feasibility(self, node: str, color: str) -> bool:
        """Check if a specific assignment is locally feasible."""

    def get_available_colors(self, node: str) -> List[str]:
        """Get available colors for a node given current constraints."""

    def simulate_neighbor_change(self, neighbor_nodes: Dict[str, str]) -> Dict[str, Any]:
        """Simulate impact of neighbor changing their assignments."""

    def get_conflict_resolution_options(self) -> List[Dict[str, Any]]:
        """Generate options for resolving current conflicts."""

    def get_best_response_to(self, neighbor_assignments: Dict[str, str], algorithm: str = "greedy") -> Dict[str, str]:
        """Compute best response to specific neighbor assignments."""
```

### Phase 2: Tool Calling Agent

**Key Features**:
- OpenAI function calling with automatic dispatch
- Tool execution loop handles multiple function calls per turn
- Structured logging to `llm_trace.jsonl`
- Integrates with speech layer for natural language output

**Tool Definition Example**:
```python
{
    "type": "function",
    "function": {
        "name": "compute_assignments",
        "description": "Run local graph coloring solver and return node-to-color assignments",
        "parameters": {
            "type": "object",
            "properties": {
                "algorithm": {
                    "type": "string",
                    "enum": ["greedy", "exhaustive"],
                    "description": "Solver algorithm to use"
                }
            },
            "required": []
        }
    }
}
```

**Execution Flow**:
1. Build system prompt with current graph state
2. Call backend LLM with tool definitions
3. Execute any requested tool calls
4. Continue conversation with tool results
5. Extract final decision from LLM response
6. Send message via speech layer

### Phase 3: ReAct Agent

**Key Features**:
- Thought → Action → Observation reasoning loop
- Explicit traces for research analysis
- Configurable max iterations (default: 5)
- Same API library as tool calling mode

**ReAct Format**:
```
Thought: I need to check if there are any conflicts with my current assignment.
Action: get_current_penalty()
Observation: {"penalty": 2, "conflicts": [("a2", "h1"), ("a5", "h2")]}

Thought: There are 2 conflicts. Let me explore alternative colorings for a2 and a5.
Action: enumerate_alternatives(["a2", "a5"])
Observation: [{"a2": "blue", "a5": "green"}, {"a2": "green", "a5": "red"}, ...]

Thought: The first alternative looks good. Let me test it.
Action: test_configuration({"a2": "blue", "a5": "green"})
Observation: {"penalty": 0, "feasible": true}

Thought: Perfect! I'll propose this to the human.
Final Answer: {
  "should_send_message": true,
  "recipient": "Human",
  "structured_content": {
    "message_type": "proposal",
    "my_assignments": {"a2": "blue", "a5": "green"},
    "reason": "Resolves conflicts with h1 and h2"
  }
}
```

### Phase 4: Speech LLM Layer

**Bidirectional Translation**:

1. **Human → Backend** (`human_to_backend()`):
   - Extracts structured information from natural language
   - Identifies: type, requested changes, constraints, conditions, sentiment
   - Uses LLM parsing with heuristic fallback

2. **Backend → Human** (`backend_to_human()`):
   - Converts structured output to natural language
   - Preserves report tags for UI updates
   - Uses LLM generation with template fallback

**Critical Method: `format_content()`**:
```python
def format_content(self, sender: str, recipient: str, content: Any) -> str:
    """Format structured message content into transmissible string."""
    if isinstance(content, str):
        return content

    if isinstance(content, dict):
        msg_type = content.get("type", "")

        # Handle announcement type (preserve report tag!)
        if msg_type == "announcement":
            data = content.get("data", {})
            report = content.get("report", {})
            assignments = data.get("assignments", {})
            if assignments:
                assignments_str = ", ".join(
                    f"{node}={color}" for node, color in assignments.items()
                )
                nl_message = f"Here's my initial configuration: {assignments_str}"
            else:
                nl_message = "Here's my initial configuration."

            # CRITICAL: Append report tag for UI color extraction
            nl_message += f" [report: {json.dumps(report)}]"
            return nl_message

        return self.backend_to_human(sender, recipient, content)

    return str(content)
```

### Phase 5: Integration

**Modified Files**:

1. **launch_menu.py** (line 71):
   - Added "LLM_TOOL" and "LLM_REACT" to dropdown

2. **cluster_simulation.py** (lines 388-422):
   - Added agent creation logic for both new modes
   - Instantiates SpeechLLMLayer
   - Passes to agent constructors

3. **run_experiment.py**:
   - Line 186: Added to argument choices
   - Lines 151-154: Added method validation

### Phase 6: Testing

**Test Files**:

1. **test_multi_layer_llm.py**: Tests API library and basic integration
2. **test_integration_new_modes.py**: Tests agent instantiation and operations
3. **test_announcement_nl_format.py**: Tests natural language formatting

**All Tests Passing** ✅

## Announcement Phase Support

Both new agent types support the two-phase workflow:

### Configure Phase
- Agent computes assignments but doesn't send messages
- Waits for `__ANNOUNCE_CONFIG__` signal from UI

### Announcement
- Human clicks "Announce Configuration" button
- Agents transition to bargain phase
- Send initial boundary assignments as natural language
- Format: `"Here's my initial configuration: a2=blue, a4=red [report: {...}]"`

### Bargain Phase
- Normal negotiation proceeds
- Backend LLM generates proposals, questions, acceptances, rejections
- Speech layer translates to natural language

## Message Format Examples

### Announcements
```
[Agent1] Here's my initial configuration: a2=blue, a4=red, a5=green [report: {"a2": "blue", "a4": "red", "a5": "green"}]
```

### Proposals (with API key)
```
[Agent1] I propose a2=blue, a4=green. This resolves the conflict with h1. [report: {"a2": "blue", "a4": "green"}]
```

### Questions (with API key)
```
[Agent1] I'm wondering: Would you be able to change h1 to red? [report: {}]
```

### Acceptances (with API key)
```
[Agent1] That works for me. I'll use a2=blue, a4=green. Thanks! [report: {"a2": "blue", "a4": "green"}]
```

## Error Handling & Fallbacks

### Without OpenAI API Key

The system gracefully degrades when `api_key.txt` is missing or invalid:

1. **Speech Layer**: Falls back to template-based translation
   - Heuristic parsing for human messages
   - Template rendering for agent messages

2. **Backend LLM**: Not available
   - Warning logged: "Backend LLM not available, using algorithmic mode"
   - Agents fall back to pure algorithmic solving (greedy/exhaustive)
   - Still use speech layer for message formatting

3. **Result**: System remains functional, but loses:
   - LLM-based reasoning capabilities
   - Natural language variation
   - Adaptive problem-solving strategies

### With API Key

Full functionality:
- Backend LLM uses tool calling or ReAct reasoning
- Speech LLM generates natural, varied language
- Comprehensive traces in `llm_trace.jsonl`

## Performance Considerations

1. **Token Optimization**: Use gpt-4-turbo for cost/speed balance
2. **Caching**: Results cached within a turn (enumerate_alternatives is expensive)
3. **Timeouts**: Set max_tokens and timeout for LLM calls
4. **Rate Limiting**: Handles OpenAI rate limits gracefully

## Logging & Observability

### Tool Calling Mode (`llm_trace.jsonl`)
```json
{
  "timestamp": "2026-02-11T14:30:00",
  "agent": "Agent1",
  "event": "tool_call",
  "function": "enumerate_alternatives",
  "arguments": {"nodes": ["a2", "a5"]},
  "result": [{"a2": "blue", "a5": "green"}, ...]
}
```

### ReAct Mode (`react_trace.jsonl`)
```json
{
  "timestamp": "2026-02-11T14:30:00",
  "agent": "Agent1",
  "iteration": 0,
  "thought": "I need to check conflicts...",
  "action": "get_current_penalty()",
  "observation": {"penalty": 2, "conflicts": [...]}
}
```

## Usage Instructions

### From GUI (Recommended)

```bash
python launch_menu.py
```

1. Select "LLM_TOOL" or "LLM_REACT" from dropdown
2. Check "Use participant UI" for interactive mode
3. Click "Start"
4. Click "Announce Configuration" to begin
5. Negotiate via chat interface

### From Command Line

```bash
# Tool calling mode
python run_experiment.py --method LLM_TOOL --use_ui true

# ReAct mode
python run_experiment.py --method LLM_REACT --use_ui true
```

## Files Created

### New Files (7)

1. `agents/cluster_agent_api.py` (600 lines) - API library
2. `agents/tool_calling_cluster_agent.py` (450 lines) - Tool calling agent
3. `agents/react_cluster_agent.py` (450 lines) - ReAct agent
4. `comm/speech_llm_layer.py` (430 lines) - Speech layer
5. `test_multi_layer_llm.py` (200 lines) - API tests
6. `test_integration_new_modes.py` (200 lines) - Integration tests
7. `test_announcement_nl_format.py` (140 lines) - Format tests

### Modified Files (3)

1. `launch_menu.py` - Added LLM_TOOL and LLM_REACT to dropdown
2. `cluster_simulation.py` - Agent creation logic for new modes
3. `run_experiment.py` - CLI args and method validation

## Critical Implementation Details

### Why Structured Dicts for Announcements?

**Initial Approach (Failed)**:
```python
# Agents sent plain strings
nl_message = f"Here's my initial configuration: {assignments_str}"
nl_message += f" [report: {json.dumps(report)}]"
self.send(recipient, nl_message)
```

**Problem**: Plain strings bypass proper comm layer formatting, risk losing report tags

**Correct Approach**:
```python
# Agents send structured dicts
announcement = {
    "type": "announcement",
    "data": {"assignments": report},
    "report": report
}
self.send(recipient, announcement)
```

**Why This Works**:
1. Preserves all metadata through agent's send() method
2. Comm layer's `format_content()` handles conversion to NL
3. Report tags guaranteed to be appended correctly
4. Consistent with existing ClusterAgent pattern

### Communication Layer Interface

Both new agent types require `SpeechLLMLayer` which implements:

```python
class SpeechLLMLayer:
    def format_content(self, sender: str, recipient: str, content: Any) -> str:
        """Convert structured message to transmissible string."""

    def parse_content(self, sender: str, recipient: str, message: str) -> Any:
        """Parse received string into structured content."""
```

This interface is required for compatibility with base agent's `send()` method.

## Troubleshooting

### Issue: Agents send raw JSON dicts

**Symptom**: UI shows `{'type': 'announcement', 'data': ...}`

**Cause**: Communication layer missing `format_content()` method

**Fix**: Ensure SpeechLLMLayer has `format_content()` that handles all message types

### Issue: Node colors don't update after announcement

**Symptom**: Announcement message appears but nodes stay grey

**Possible Causes**:
1. Report tag stripped during formatting
2. Report tag format doesn't match UI parser
3. Announcement sent as plain string (bypassing proper formatting)

**Fix**:
1. Verify announcement sent as structured dict with "announcement" type
2. Verify `format_content()` appends report tag: `[report: {json}]`
3. Test with: `python test_announcement_nl_format.py`

### Issue: Backend LLM not called

**Symptom**: Agents use algorithmic mode even with API key

**Possible Causes**:
1. OpenAI package version too old (< 2.0)
2. API key file missing or invalid
3. Model name incorrect

**Fix**:
1. Upgrade: `pip install --upgrade openai` (need >= 2.20.0)
2. Check `api_key.txt` exists and contains valid key
3. Verify model name: "gpt-4-turbo" or "gpt-4"

## Comparison with Existing Modes

### LLM_API (Existing)
- **Backend**: Pure algorithmic (greedy/exhaustive)
- **Communication**: Optional LLM for message formatting
- **Reasoning**: None - follows fixed algorithms

### LLM_TOOL (New)
- **Backend**: LLM with function calling
- **Communication**: Speech LLM (bidirectional)
- **Reasoning**: Yes - LLM decides which functions to call and when

### LLM_REACT (New)
- **Backend**: LLM with ReAct pattern
- **Communication**: Speech LLM (bidirectional)
- **Reasoning**: Yes - explicit thought-action-observation traces

## Research Applications

### What Can Be Studied

1. **Reasoning Traces**: Compare tool calling vs ReAct decision processes
2. **Communication Patterns**: Analyze natural language strategies
3. **Solution Quality**: Compare LLM reasoning vs pure algorithmic
4. **Human-Agent Coordination**: Study how humans adapt to LLM agents
5. **Computational Cost**: Token usage, API calls, latency

### Log Analysis

- `llm_trace.jsonl`: All LLM interactions (prompts, responses, tool calls)
- `react_trace.jsonl`: ReAct thought-action-observation sequences
- `communication_log.txt`: Full message exchange transcript
- `Agent1_log.txt`, `Agent2_log.txt`: Per-agent reasoning logs

## Future Enhancements

Potential improvements:
1. **Few-shot examples**: Add examples to system prompts
2. **Cost tracking**: Token usage and cost estimation
3. **Caching**: Cache expensive API calls (enumerate_alternatives)
4. **Multi-turn reasoning**: Allow longer ReAct sequences
5. **Hybrid modes**: Combine tool calling with ReAct

## Conclusion

The multi-layer LLM architecture successfully separates concerns:
- **API Library**: Provides algorithmic capabilities
- **Backend LLM**: Handles reasoning and decision-making
- **Speech LLM**: Enables natural language communication
- **Agents**: Orchestrate the full pipeline

Both LLM_TOOL and LLM_REACT modes are fully functional and ready for experiments.

---

**Status**: ✅ Implementation Complete
**Tests**: ✅ All Passing
**Documentation**: ✅ Complete
**Ready for Use**: ✅ Yes
