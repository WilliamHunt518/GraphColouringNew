# LLM_TOOL Mode: Function Calling Architecture

## Overview

LLM_TOOL mode implements a **multi-layer LLM architecture** where a backend Large Language Model uses **function calling** (also called "tool use") to reason about the graph coloring problem. This is the first mode where the LLM is the primary decision-maker, not just a communication formatter.

## Theoretical Foundation

### Function Calling / Tool Use Paradigm

Function calling extends LLMs with the ability to:
1. **Recognize when external tools are needed** to answer queries
2. **Generate structured function calls** with correct parameters
3. **Interpret function results** and continue reasoning
4. **Make final decisions** based on tool outputs

This paradigm was popularized by:
- **OpenAI Function Calling** (GPT-3.5/4, June 2023)
- **Anthropic Tool Use** (Claude 2/3, 2023-2024)
- Research: Schick et al. "Toolformer" (2023), Patil et al. "Gorilla" (2023)

### Why Function Calling for Graph Coloring?

Traditional LLMs struggle with constraint satisfaction problems because:
- ❌ Can't reliably count or verify constraints
- ❌ Make arithmetic errors in penalty calculation
- ❌ Hallucinate about graph structure

Function calling solves this by:
- ✅ **Offloading computation** to reliable API functions
- ✅ **Grounding reasoning** in actual problem state
- ✅ **Enabling systematic exploration** of solution space

## Architecture

### Three-Layer Design

```
┌──────────────────────────────────────────────────────────────┐
│                         Human (Natural Language)              │
│                    "Can you change a2 to green?"              │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                    Speech LLM Layer                           │
│  • Translates Human NL ↔ Backend Protocol                     │
│  • Adds [report: {...}] tags for UI updates                   │
│  • Renders structured decisions as natural language           │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                    Backend LLM (GPT-4)                        │
│  • Reasons about graph coloring problem                       │
│  • Calls API functions to explore solutions                   │
│  • Makes strategic decisions                                  │
│  • Returns structured output                                  │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                    API Library                                │
│  • compute_assignments()                                      │
│  • get_current_penalty()                                      │
│  • enumerate_alternatives()                                   │
│  • test_configuration()                                       │
│  • get_conflict_resolution_options()                          │
│  • ... 11 functions total                                     │
└──────────────────────────────────────────────────────────────┘
```

### Layer 1: API Library (`cluster_agent_api.py`)

The API library exposes 11 functions to the backend LLM:

```python
class ClusterAgentAPI:
    def __init__(self, agent: ClusterAgent):
        self.agent = agent

    def compute_assignments(self, algorithm: str = "greedy") -> Dict[str, str]:
        """Run local solver (greedy or maxsum) and return assignments."""

    def get_current_penalty(self) -> Tuple[float, List[Tuple[str, str]]]:
        """Return current penalty and list of conflicting edges."""

    def enumerate_alternatives(
        self, nodes: List[str], max_alternatives: int = 10
    ) -> List[Dict[str, str]]:
        """Generate alternative colorings for specified nodes."""

    def test_configuration(
        self, assignments: Dict[str, str]
    ) -> Dict[str, Any]:
        """Test a proposed configuration, return penalty and feasibility."""

    def get_conflict_resolution_options(
        self, max_options: int = 5
    ) -> List[Dict[str, Any]]:
        """Get specific options for resolving current conflicts."""

    def get_boundary_nodes(self, recipient: str = None) -> List[str]:
        """Get boundary nodes connecting to specific neighbor or all."""

    def get_neighbor_constraints(self, recipient: str) -> Dict[str, Any]:
        """Get constraints from neighbor's perspective."""

    def simulate_neighbor_change(
        self, neighbor_nodes: Dict[str, str]
    ) -> Dict[str, Any]:
        """Simulate impact of neighbor changing assignments."""

    def check_feasibility(self, node: str, color: str) -> bool:
        """Check if specific node-color assignment creates conflicts."""

    def get_available_colors(self, node: str) -> List[str]:
        """Get colors available for node given current constraints."""

    def get_best_response_to(
        self, neighbor_assignments: Dict[str, str], algorithm: str = "greedy"
    ) -> Dict[str, str]:
        """Compute best response to specific neighbor configuration."""
```

#### Function Design Principles

1. **Idempotent**: Functions don't modify state (except compute_assignments)
2. **Informative**: Return structured data with metadata
3. **Composable**: Can be chained to build complex queries
4. **Fail-safe**: Return error dicts rather than raising exceptions

### Layer 2: Backend LLM with Function Calling

The backend LLM (ToolCallingClusterAgent) orchestrates problem-solving:

```python
class ToolCallingClusterAgent(ClusterAgent):
    def __init__(self, *args, backend_model="gpt-4-turbo", **kwargs):
        super().__init__(*args, **kwargs)
        self.api = ClusterAgentAPI(self)
        self.backend_llm = OpenAI(api_key=...)
        self.tool_definitions = self._build_tool_definitions()

    def _build_tool_definitions(self) -> List[Dict]:
        """Build OpenAI function calling schema for all API functions."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_current_penalty",
                    "description": "Get current penalty and conflicts",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            # ... 10 more function definitions
        ]

    def step(self) -> None:
        """Execute one reasoning step using backend LLM + tool calling."""

        # 1. Build system prompt with current state
        system_prompt = self._build_system_prompt()

        # 2. Initial LLM call
        messages = [{"role": "system", "content": system_prompt}]

        response = self.backend_llm.chat.completions.create(
            model=self.backend_model,
            messages=messages,
            tools=self.tool_definitions,
            tool_choice="auto"
        )

        # 3. Tool calling loop
        while response.choices[0].message.tool_calls:
            # Execute each tool call
            for tool_call in response.choices[0].message.tool_calls:
                result = self._execute_tool_call(tool_call)

                # Add to conversation
                messages.append({
                    "role": "assistant",
                    "tool_calls": response.choices[0].message.tool_calls
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result)
                })

            # Continue conversation
            response = self.backend_llm.chat.completions.create(
                model=self.backend_model,
                messages=messages,
                tools=self.tool_definitions
            )

        # 4. Extract final decision
        backend_output = self._parse_backend_response(
            response.choices[0].message.content
        )

        # 5. Send via Speech LLM if decided to communicate
        if backend_output.get("should_send_message"):
            self._send_backend_decision(backend_output)
```

#### System Prompt Structure

```
You are a graph coloring agent controlling cluster "Agent1".

**Your nodes**: a1, a2, a3, a4, a5
**Your current assignments**: {a1: red, a2: blue, a3: green, ...}
**Boundary nodes** (neighbors): h1, h2, h4, h5
**Neighbor assignments**: {h1: red, h2: blue, h4: ?, h5: ?}
**Available colors**: red, blue, green, yellow

**Current state**:
- Penalty: 2
- Conflicts: 2 edge conflicts
- Feasible: No

**Your goal**: Coordinate with neighbors to achieve penalty=0

**Available tools**: [list of 11 functions]

**Decision process**:
1. Analyze current state
2. Use tools to explore options
3. Decide on action
4. Return structured output

**Output format**:
{
  "should_send_message": true/false,
  "recipient": "Human" | "Agent1" | "Agent2",
  "message_type": "proposal" | "question" | "acceptance" | "rejection",
  "structured_content": {
    "my_assignments": {"node": "color", ...},
    "reason": "Explanation",
    "dependencies": {"neighbor_node": "color", ...}  // optional
  }
}
```

### Layer 3: Speech LLM Layer

The Speech LLM translates between human natural language and backend protocol:

```python
class SpeechLLMLayer:
    def human_to_backend(
        self, sender: str, recipient: str, nl_text: str
    ) -> Dict[str, Any]:
        """Translate human NL to structured backend protocol."""
        prompt = f"""
        You are translating human natural language into structured messages
        for a graph coloring agent.

        Human message: "{nl_text}"

        Extract:
        1. Type: question | proposal | acceptance | rejection | constraint
        2. Requested changes: {{node: color}}
        3. Constraints mentioned
        4. Conditions (if-then statements)
        5. Sentiment: positive | neutral | negative

        Return JSON.
        """
        # Call LLM, parse response
        return structured_message

    def backend_to_human(
        self, sender: str, recipient: str, structured: Dict[str, Any]
    ) -> str:
        """Translate backend structured output to natural language."""
        prompt = f"""
        Translate agent's structured output into natural language.

        Structured output: {json.dumps(structured, indent=2)}

        Generate natural, conversational message. Be clear about:
        - What you're proposing
        - Constraints and conflicts
        - Be friendly and collaborative

        Return only the natural language message.
        """
        # Call LLM, return NL text
        return nl_message
```

## Execution Flow

### Example: Handling Conflict After Announcement

```
[Initial State]
Agent1: {a1: red, a2: blue}
Human:  {h1: red, h2: blue}
Penalty: 1 (conflict: a2-h2)

[1] Human clicks "Announce Configuration"
    → __ANNOUNCE_CONFIG__ token sent to Agent1

[2] Agent1.receive(__ANNOUNCE_CONFIG__)
    → Generates announcement
    → Sets flag: _should_generate_first_message = True

[3] Agent1.step() called by UI
    → Detects flag is True
    → Calls _generate_first_message_after_announcement("Human")

[4] Backend LLM reasoning begins:

    System Prompt:
      "You are Agent1. Penalty=1, conflicts=[(a2, h2)]..."

    User Prompt:
      "You just announced to Human. Analyze conflicts and generate
       appropriate first message."

    LLM generates tool calls:
      Thought: "I need to check what colors are available for a2"
      Tool Call: get_available_colors(node="a2")

[5] Tool Execution:
    Result: ["red", "green", "yellow"]  # blue excluded (conflict with h2)

[6] LLM continues reasoning:
    Thought: "green and yellow are available. Let me test green"
    Tool Call: test_configuration(assignments={"a2": "green"})

[7] Tool Execution:
    Result: {"penalty": 0, "feasible": true, "conflicts": []}

[8] LLM makes final decision:
    {
      "should_send_message": true,
      "recipient": "Human",
      "message_type": "proposal",
      "structured_content": {
        "my_assignments": {"a2": "green"},
        "reason": "Changing a2 to green resolves conflict with h2"
      }
    }

[9] Speech LLM renders to natural language:
    Backend input:
      {"type": "proposal", "my_assignments": {"a2": "green"}, ...}

    Speech LLM output:
      "I propose a2=green. Changing a2 to green resolves the conflict
       with h2, bringing our penalty to zero. [report: {"a2": "green"}]"

[10] Message sent to Human via UI
     → Graph updates (a2 becomes green)
     → Chat shows proposal message
```

## Pseudocode

### Complete Step() Flow

```python
def step():
    # Skip if in configure phase
    if phase == "configure" and not config_announced:
        return

    # Handle first message after announcement
    if should_generate_first_message:
        should_generate_first_message = False
        for each neighbor:
            generate_first_message_after_announcement(neighbor)
        return

    # Normal turn-taking
    if not received_human_message_this_turn:
        return  # Wait for human input

    # Build context
    system_prompt = build_system_prompt()
    # Includes: nodes, assignments, penalty, conflicts, tools

    # Initialize conversation
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": format_human_message()}
    ]

    # Call backend LLM
    response = backend_llm.chat.completions.create(
        model="gpt-4-turbo",
        messages=messages,
        tools=tool_definitions,
        tool_choice="auto"
    )

    # Tool calling loop (max 10 iterations)
    iteration = 0
    while response.has_tool_calls and iteration < 10:
        iteration += 1

        # Execute all tool calls
        for tool_call in response.tool_calls:
            function_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)

            # Call API function
            result = getattr(api, function_name)(**arguments)

            # Log for observability
            log_tool_call(function_name, arguments, result)

            # Add to conversation
            messages.append({
                "role": "assistant",
                "tool_calls": [tool_call]
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result)
            })

        # Continue conversation
        response = backend_llm.chat.completions.create(
            model="gpt-4-turbo",
            messages=messages,
            tools=tool_definitions
        )

    # Extract final decision
    final_text = response.choices[0].message.content
    backend_output = parse_backend_response(final_text)
    # Expected: {"should_send_message": true, "recipient": "...", ...}

    # Send message if decided
    if backend_output.get("should_send_message"):
        recipient = backend_output["recipient"]
        structured_content = backend_output["structured_content"]

        # Render via Speech LLM
        nl_message = speech_llm.backend_to_human(
            sender=agent_name,
            recipient=recipient,
            structured=structured_content
        )

        # Add report tag for UI updates
        if "my_assignments" in structured_content:
            nl_message += f" [report: {json.dumps(structured_content['my_assignments'])}]"

        # Send message
        send(recipient, nl_message)

    # Update internal state
    if "my_assignments" in backend_output.get("structured_content", {}):
        assignments.update(backend_output["structured_content"]["my_assignments"])
```

### Tool Execution Pseudocode

```python
def _execute_tool_call(tool_call):
    function_name = tool_call.function.name
    arguments_json = tool_call.function.arguments

    # Parse arguments
    try:
        arguments = json.loads(arguments_json)
    except:
        return {"error": "Invalid JSON arguments"}

    # Dispatch to API function
    if hasattr(api, function_name):
        function = getattr(api, function_name)

        try:
            result = function(**arguments)
            return result
        except Exception as e:
            return {"error": str(e)}
    else:
        return {"error": f"Unknown function: {function_name}"}
```

## Key Features

### 1. Fail-Fast Error Handling

```python
def __init__(self, *args, **kwargs):
    try:
        from openai import OpenAI
        api_key = self._load_api_key()
        self.backend_llm = OpenAI(api_key=api_key)
    except FileNotFoundError as e:
        error_msg = f"FATAL: {e}\nLLM_TOOL mode requires API key."
        raise SystemExit(error_msg)
```

No fallback to algorithmic mode - LLM_TOOL requires LLM.

### 2. Deferred First Message Generation

```python
# In _handle_announce_config():
self._config_announced = True
self._phase = "bargain"
send_announcement(recipient)
self._should_generate_first_message = True  # Flag for next step()

# In step():
if self._should_generate_first_message:
    # Generate first substantive message NOW
    # (Announcement already sent in previous call)
    for neighbor in neighbours:
        generate_first_message(neighbor)
    return
```

Why? UI runs announcement in background thread. Slow LLM calls (5+ seconds) would block. Solution: Split announcement (fast) from first message (slow).

### 3. Nested JSON Parsing

```python
def _parse_backend_response(response: str) -> Dict:
    # Try full response as JSON
    if response.strip().startswith('{') and response.strip().endswith('}'):
        return json.loads(response.strip())

    # Otherwise extract from first { to last }
    start = response.find('{')
    end = response.rfind('}')
    if start != -1 and end != -1:
        json_str = response[start:end+1]
        return json.loads(json_str)

    # Fallback: default structure
    return {
        "should_send_message": True,
        "recipient": "Human",
        "message_type": "info",
        "structured_content": {"reason": response[:200]}
    }
```

Handles LLM responses that may have preamble/postscript around JSON.

### 4. Comprehensive Logging

```python
# Log every tool call
self.log(f"[TOOL] Calling {function_name} with args {arguments}")
self.log(f"[TOOL] Result: {result}")

# Log to llm_trace.jsonl
with open("llm_trace.jsonl", "a") as f:
    f.write(json.dumps({
        "timestamp": datetime.now().isoformat(),
        "agent": self.name,
        "event": "tool_call",
        "function": function_name,
        "arguments": arguments,
        "result": result
    }) + "\n")
```

## Prompt Engineering

### Critical Prompt Requirements

1. **Explicit JSON Schema**: Always include exact output format in prompts
   ```
   **IMPORTANT**: Return JSON in this format:
   {
     "should_send_message": true,
     "recipient": "Human",
     ...
   }
   ```

2. **Example-Driven**: Include few-shot examples of tool usage
   ```
   Example:
   Thought: "I need to check current conflicts"
   Tool Call: get_current_penalty()
   Observation: {"penalty": 2, "conflicts": [("a1", "h1"), ("a2", "h2")]}
   ```

3. **Clear Goals**: State objective explicitly
   ```
   Your goal: Coordinate to achieve penalty=0 while optimizing utility
   ```

4. **Constraint Awareness**: Remind about partial observability
   ```
   Remember: You only see your own nodes and boundary neighbors
   ```

## Performance Considerations

### Token Optimization

- Use `gpt-4-turbo` or `gpt-4o` (cheaper, faster than `gpt-4`)
- Set `max_tokens=2000` to prevent runaway generation
- System prompt: ~800 tokens
- Tool definitions: ~1200 tokens
- Conversation history grows with iterations

### Latency

- Initial LLM call: ~2-4 seconds
- Tool execution: ~10-50ms per call
- Follow-up LLM calls: ~2-3 seconds each
- Total per turn: ~5-15 seconds (depends on tool calling iterations)

### Cost Estimation

Typical message exchange:
- Input tokens: ~2500 (system + history + tools)
- Output tokens: ~400 (response + tool calls)
- Tool iterations: 2-3 on average
- Cost per message: ~$0.05-0.15 (GPT-4-turbo pricing as of 2024)

## Advantages vs Other Modes

| Aspect | LLM_TOOL | LLM_API | LLM_RB |
|--------|----------|---------|---------|
| Reasoning | LLM-based | Algorithmic | Algorithmic |
| Flexibility | High (emergent) | Medium | Low (rigid) |
| Explainability | Medium (tool traces) | High | Highest |
| Performance | Slower (LLM calls) | Fast | Fast |
| Cost | High ($0.10/msg) | Medium ($0.02/msg) | Medium |
| Novel strategies | Yes | No | No |

## Limitations

1. **Non-Determinism**: LLM decisions vary between runs (even with temperature=0)
2. **Cost**: Expensive for large-scale experiments
3. **Latency**: Slow for real-time interaction
4. **Failure Modes**: LLM may:
   - Generate invalid tool calls
   - Loop indefinitely
   - Forget previous context
   - Hallucinate constraints

## Future Enhancements

1. **Caching**: Cache API results within turn to avoid redundant calls
2. **Tool Retry**: Auto-retry failed tool calls with error messages
3. **Thought Logging**: Extract LLM's chain-of-thought for analysis
4. **Multi-Agent Coordination**: Enable direct agent-agent communication
5. **Learned Heuristics**: Fine-tune LLM on successful negotiation traces

## References

- OpenAI Function Calling: https://platform.openai.com/docs/guides/function-calling
- Schick et al. "Toolformer: Language Models Can Teach Themselves to Use Tools" (2023)
- Patil et al. "Gorilla: Large Language Model Connected with Massive APIs" (2023)
- Wei et al. "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models" (2022)

## See Also

- [MODE_LLM_REACT.md](MODE_LLM_REACT.md): Alternative LLM reasoning architecture
- [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md): Overall system architecture
- [MULTI_LAYER_LLM_ARCHITECTURE.md](MULTI_LAYER_LLM_ARCHITECTURE.md): Implementation details
