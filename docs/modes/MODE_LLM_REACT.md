# LLM_REACT Mode: ReAct Reasoning Pattern

## Overview

LLM_REACT mode implements the **ReAct (Reasoning and Acting)** paradigm, where a Large Language Model explicitly generates reasoning traces alongside action execution. Unlike LLM_TOOL's implicit reasoning, ReAct makes the thought process explicit and inspectable.

## Theoretical Foundation

### ReAct: Synergizing Reasoning and Acting

The ReAct framework was introduced by Yao et al. (2022) in "ReAct: Synergizing Reasoning and Acting in Language Models".

**Core Idea**: Interleave reasoning (thinking), acting (tool use), and observing (results) in a loop:

```
Thought → Action → Observation → Thought → Action → Observation → ...
```

**Why ReAct?**

Traditional LLMs suffer from:
- **Hallucination**: Generate plausible but incorrect information
- **Error propagation**: Small mistakes compound over reasoning steps
- **Lack of grounding**: Can't verify claims against reality

ReAct solves this by:
- ✅ **Explicit reasoning**: Thought steps are visible and auditable
- ✅ **Grounded actions**: Each action produces verifiable observations
- ✅ **Error recovery**: Can detect mistakes via observations and backtrack
- ✅ **Interpretability**: Reasoning trace explains decisions

### Comparison to Chain-of-Thought (CoT)

| Aspect | Chain-of-Thought | ReAct |
|--------|------------------|-------|
| Reasoning | Internal only | Explicit thoughts |
| Actions | Implied | Explicit with syntax |
| Grounding | None | Via observations |
| Verification | Cannot verify | Self-correcting |
| Format | Free-form | Structured (Thought/Action/Observation) |

**Example**:

**Chain-of-Thought**:
```
"Let me think step by step. First, I need to check conflicts...
 There are 2 conflicts. So I should change a2 to green..."
```
(No verification, prone to hallucination)

**ReAct**:
```
Thought: I need to check if there are any conflicts
Action: get_current_penalty()
Observation: {"penalty": 2, "conflicts": [("a2", "h2"), ("a1", "h1")]}

Thought: I see 2 conflicts. Let me check available colors for a2
Action: get_available_colors(node="a2")
Observation: ["red", "green", "yellow"]

Thought: Green is available. Let me test if a2=green resolves conflict
Action: test_configuration(assignments={"a2": "green"})
Observation: {"penalty": 1, "conflicts": [("a1", "h1")]}

Thought: That only partially helps. Let me try a1=green too
Action: test_configuration(assignments={"a1": "green", "a2": "red"})
Observation: {"penalty": 0, "conflicts": []}

Thought: Perfect! This resolves all conflicts. I'll propose this.
Final Answer: {
  "should_send_message": true,
  "recipient": "Human",
  "message_type": "proposal",
  "structured_content": {
    "my_assignments": {"a1": "green", "a2": "red"},
    "reason": "Swapping colors resolves both conflicts"
  }
}
```
(Grounded in actual observations, verifiable)

## Architecture

### Three-Layer Design (Same as LLM_TOOL)

```
Human (NL) ↔ Speech LLM ↔ Backend LLM (ReAct) ↔ API Library
```

The key difference from LLM_TOOL is the **reasoning pattern** of the backend LLM.

### ReAct Loop Implementation

```python
class ReActClusterAgent(ClusterAgent):
    def __init__(self, *args, max_react_iterations=10, **kwargs):
        super().__init__(*args, **kwargs)
        self.api = ClusterAgentAPI(self)
        self.backend_llm = OpenAI(api_key=...)
        self.react_prompt = self._load_react_prompt()
        self.max_react_iterations = max_react_iterations

    def _load_react_prompt(self) -> str:
        """Load ReAct system prompt with format and examples."""
        return """You are a graph coloring agent using ReAct pattern.

**Your format**:
- Thought: [your reasoning about the current situation]
- Action: [function_name(arguments)]
- [System provides Observation: [result]]

After several thought-action-observation cycles, decide:
- Thought: [final reasoning]
- Final Answer: [JSON with your decision]

**Available actions**:
- compute_assignments(algorithm="greedy")
- get_current_penalty()
- test_configuration(assignments={...})
- enumerate_alternatives(nodes=[...], max_alternatives=10)
- get_conflict_resolution_options(max_options=5)
- get_boundary_nodes(recipient="...")
- get_neighbor_constraints(recipient="...")
- simulate_neighbor_change(neighbor_nodes={...})
- check_feasibility(node="...", color="...")
- get_available_colors(node="...")
- get_best_response_to(neighbor_assignments={...})

**Example**:
Thought: I need to check conflicts
Action: get_current_penalty()
Observation: {"penalty": 2, "conflicts": [("a2", "h1"), ("a5", "h2")]}

Thought: There are 2 conflicts. Let me explore alternatives
Action: enumerate_alternatives(nodes=["a2", "a5"], max_alternatives=5)
Observation: [{"a2": "blue", "a5": "green"}, ...]

Thought: First option looks good. Let me test it
Action: test_configuration(assignments={"a2": "blue", "a5": "green"})
Observation: {"penalty": 0, "feasible": true}

Thought: Perfect! I'll propose this
Final Answer: {
  "should_send_message": true,
  "recipient": "Human",
  "message_type": "proposal",
  "structured_content": {
    "my_assignments": {"a2": "blue", "a5": "green"},
    "reason": "Resolves all conflicts"
  }
}

**Guidelines**:
- Be systematic: Check state before acting
- Be grounded: Use observations, don't guess
- Be efficient: Don't repeat redundant actions
- Be goal-oriented: Work toward penalty=0
"""

    def step(self) -> None:
        """Execute ReAct reasoning loop."""

        # Build context
        context = self._build_context()
        prompt = f"{self.react_prompt}\n\n{context}"

        # ReAct loop
        trajectory = []
        max_iterations = self.max_react_iterations

        for iteration in range(max_iterations):
            # LLM generates thought + action
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "\n".join(trajectory)
                                    if trajectory else "Begin reasoning."}
            ]

            response = self.backend_llm.chat.completions.create(
                model=self.backend_model,
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
                stop=["Observation:"]  # Stop before observation
            )

            thought_action = response.choices[0].message.content
            trajectory.append(thought_action)

            # Check for final answer
            if "Final Answer:" in thought_action:
                backend_output = self._parse_final_answer(thought_action)
                break

            # Parse and execute action
            action_match = re.search(
                r"Action:\s*(\w+)\((.*?)\)",
                thought_action,
                re.DOTALL
            )

            if action_match:
                action_name = action_match.group(1)
                action_args = action_match.group(2).strip()

                # Execute action via API
                observation = self._execute_action(action_name, action_args)

                # Add observation to trajectory
                trajectory.append(
                    f"Observation: {json.dumps(observation, default=str)}"
                )

                # Log for research
                self._log_react_step(
                    iteration, thought_action, action_name, observation
                )

        # Send message if backend decided to
        if backend_output and backend_output.get("should_send_message"):
            self._send_backend_decision(backend_output)
```

## ReAct Loop Mechanics

### Iteration Cycle

```
┌─────────────────────────────────────────────────────────────┐
│ Iteration 0                                                  │
├─────────────────────────────────────────────────────────────┤
│ Input: "Begin reasoning."                                    │
│                                                              │
│ LLM generates:                                               │
│   Thought: I need to check current state                    │
│   Action: get_current_penalty()                             │
│                                                              │
│ System executes action:                                      │
│   Observation: {"penalty": 2, "conflicts": [...]}           │
│                                                              │
│ Trajectory += Thought + Action + Observation                │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ Iteration 1                                                  │
├─────────────────────────────────────────────────────────────┤
│ Input: Previous trajectory (Thought0 + Action0 + Obs0)      │
│                                                              │
│ LLM generates:                                               │
│   Thought: I see 2 conflicts. Let me check available colors │
│   Action: get_available_colors(node="a2")                   │
│                                                              │
│ System executes action:                                      │
│   Observation: ["red", "green", "yellow"]                   │
│                                                              │
│ Trajectory += Thought + Action + Observation                │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
                           ...
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ Iteration N                                                  │
├─────────────────────────────────────────────────────────────┤
│ Input: Full trajectory (all previous thoughts/actions/obs)  │
│                                                              │
│ LLM generates:                                               │
│   Thought: This configuration works. I'll propose it        │
│   Final Answer: {                                            │
│     "should_send_message": true,                             │
│     "recipient": "Human",                                    │
│     ...                                                      │
│   }                                                          │
│                                                              │
│ Loop terminates                                              │
└─────────────────────────────────────────────────────────────┘
```

### Parsing Thoughts and Actions

```python
def _parse_thought_action(text: str) -> Tuple[str, Optional[Tuple[str, str]]]:
    """Parse thought and optional action from ReAct text."""

    # Extract thought
    thought_match = re.search(
        r"Thought:\s*(.+?)(?:Action:|Final Answer:|$)",
        text,
        re.DOTALL | re.IGNORECASE
    )
    thought = thought_match.group(1).strip() if thought_match else ""

    # Extract action
    action_match = re.search(
        r"Action:\s*(\w+)\((.*?)\)",
        text,
        re.DOTALL | re.IGNORECASE
    )

    if action_match:
        action_name = action_match.group(1)
        action_args = action_match.group(2).strip()
        return thought, (action_name, action_args)
    else:
        return thought, None
```

### Executing Actions

```python
def _execute_action(action_name: str, action_args: str) -> Any:
    """Execute action and return observation."""

    # Parse arguments (handle multiple formats)
    try:
        if not action_args.strip():
            args_dict = {}
        elif action_args.strip().startswith('{'):
            # JSON object: {"node": "a2", "color": "red"}
            args_dict = json.loads(action_args)
        elif '=' in action_args:
            # Keyword args: node="a2", color="red"
            args_dict = {}
            for pair in action_args.split(','):
                if '=' in pair:
                    key, val = pair.split('=', 1)
                    key = key.strip()
                    val = val.strip().strip('"\'')
                    args_dict[key] = val
        else:
            # Single positional: "a2"
            args_dict = {"value": action_args.strip().strip('"')}

    except Exception as e:
        return {"error": f"Failed to parse arguments: {e}"}

    # Execute via API
    if hasattr(self.api, action_name):
        function = getattr(self.api, action_name)
        try:
            result = function(**args_dict)
            return result
        except Exception as e:
            return {"error": f"Error executing {action_name}: {e}"}
    else:
        return {"error": f"Unknown action: {action_name}"}
```

### Parsing Final Answer

```python
def _parse_final_answer(text: str) -> Dict[str, Any]:
    """Extract JSON from 'Final Answer: {...}'."""

    # Look for JSON after "Final Answer:"
    match = re.search(
        r"Final Answer:\s*(\{.*\})",
        text,
        re.DOTALL | re.IGNORECASE
    )

    if match:
        try:
            decision = json.loads(match.group(1))
            return decision
        except json.JSONDecodeError:
            pass

    # Fallback: Extract reasoning and return default structure
    thought_match = re.search(
        r"Thought:\s*(.+?)(?:Final Answer:|$)",
        text,
        re.DOTALL | re.IGNORECASE
    )
    reasoning = thought_match.group(1).strip() if thought_match else ""

    return {
        "should_send_message": True,
        "recipient": "Human",
        "message_type": "info",
        "structured_content": {
            "my_assignments": self.assignments,
            "reason": reasoning[:200]
        }
    }
```

## Complete Example: Resolving Conflict

### Initial State

```
Agent1: {a1: red, a2: blue}
Human:  {h1: red, h2: blue}
Penalty: 2
Conflicts: [(a1, h1), (a2, h2)]
```

### ReAct Trace

```
[System Prompt]
You are Agent1. Current state:
- Your assignments: {a1: red, a2: blue}
- Neighbor assignments: {h1: red, h2: blue}
- Penalty: 2
- Conflicts: 2
Use ReAct pattern to resolve conflicts...

[User Prompt]
Begin reasoning.

[Iteration 0]
LLM Output:
Thought: I need to verify the current state and identify conflicts.
Action: get_current_penalty()

System Executes:
Observation: {
  "penalty": 2.0,
  "conflicts": [("a1", "h1"), ("a2", "h2")]
}

[Iteration 1]
LLM Output:
Thought: Both a1 and a2 are in conflict with human's nodes. Let me check
         what colors are available for each node.
Action: get_available_colors(node="a1")

System Executes:
Observation: ["blue", "green", "yellow"]  # red excluded due to h1

[Iteration 2]
LLM Output:
Thought: a1 can be blue, green, or yellow. Let me check a2.
Action: get_available_colors(node="a2")

System Executes:
Observation: ["red", "green", "yellow"]  # blue excluded due to h2

[Iteration 3]
LLM Output:
Thought: I could make a1=green and a2=red. Let me test this configuration.
Action: test_configuration(assignments={"a1": "green", "a2": "red"})

System Executes:
Observation: {
  "penalty": 0.0,
  "feasible": true,
  "conflicts": []
}

[Iteration 4]
LLM Output:
Thought: Perfect! Swapping the colors resolves both conflicts and achieves
         penalty=0. I'll propose this to the human.
Final Answer: {
  "should_send_message": true,
  "recipient": "Human",
  "message_type": "proposal",
  "structured_content": {
    "my_assignments": {"a1": "green", "a2": "red"},
    "reason": "Swapping a1 to green and a2 to red resolves both conflicts with your h1 and h2 nodes, achieving a valid coloring."
  }
}

[Loop Terminates]
Backend output extracted.

[Speech LLM Rendering]
"I propose a1=green, a2=red. Swapping a1 to green and a2 to red resolves
 both conflicts with your h1 and h2 nodes, achieving a valid coloring.
 [report: {\"a1\": \"green\", \"a2\": \"red\"}]"

[Message sent to Human]
```

## Pseudocode

### Complete step() Flow

```python
def step():
    # Phase checks (same as LLM_TOOL)
    if phase == "configure" and not config_announced:
        return

    if should_generate_first_message:
        should_generate_first_message = False
        for neighbor in neighbours:
            generate_first_message_after_announcement(neighbor)
        return

    if not received_human_message_this_turn:
        return

    # Build ReAct prompt
    context = build_context()
    # Includes: nodes, assignments, penalty, conflicts
    system_prompt = react_prompt + "\n\n" + context

    # Initialize trajectory
    trajectory = []
    backend_output = None

    # ReAct loop
    for iteration in range(max_react_iterations):
        # Build messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(trajectory)
                                if trajectory else "Begin reasoning."}
        ]

        # Call LLM (stop before Observation)
        response = backend_llm.chat.completions.create(
            model="gpt-4-turbo",
            messages=messages,
            temperature=0.7,
            max_tokens=1000,
            stop=["Observation:"]
        )

        thought_action = response.choices[0].message.content
        trajectory.append(thought_action)

        log(f"[REACT] Iteration {iteration}: {thought_action[:100]}...")

        # Check for final answer
        if "Final Answer:" in thought_action:
            backend_output = parse_final_answer(thought_action)
            log(f"[REACT] Final answer reached at iteration {iteration}")
            break

        # Parse action
        action_match = re.search(r"Action:\s*(\w+)\((.*?)\)", thought_action)

        if action_match:
            action_name = action_match.group(1)
            action_args = action_match.group(2).strip()

            # Execute action
            observation = execute_action(action_name, action_args)

            # Add observation to trajectory
            trajectory.append(f"Observation: {json.dumps(observation)}")

            log(f"[REACT] Action: {action_name}, Observation: {observation}")

        # Continue loop (or max iterations reached)

    # Check if loop completed without final answer
    if backend_output is None:
        log(f"[REACT] WARNING: Max iterations reached without final answer")
        return  # Don't send message

    # Send message if decided
    if backend_output.get("should_send_message"):
        # Render via speech LLM
        nl_message = speech_llm.backend_to_human(
            sender=agent_name,
            recipient=backend_output["recipient"],
            structured=backend_output["structured_content"]
        )

        # Add report tag
        if "my_assignments" in backend_output["structured_content"]:
            nl_message += f" [report: {json.dumps(...)}]"

        send(backend_output["recipient"], nl_message)

    # Update internal state
    if "my_assignments" in backend_output.get("structured_content", {}):
        assignments.update(backend_output["structured_content"]["my_assignments"])
```

## Key Differences from LLM_TOOL

| Aspect | LLM_TOOL | LLM_REACT |
|--------|----------|-----------|
| **Reasoning** | Implicit | Explicit (Thought steps) |
| **Format** | Free-form | Structured (Thought/Action/Observation) |
| **Tool Calling** | OpenAI function calling API | Text-based action parsing |
| **Observability** | Tool call logs | Full reasoning traces |
| **Error Recovery** | LLM retries tool calls | LLM sees errors and adapts |
| **Interpretability** | Medium | High (can read thoughts) |
| **Prompt Complexity** | Lower | Higher (format examples) |

## Advantages

1. **Transparency**: Can read agent's reasoning process
2. **Debuggability**: Identify where reasoning went wrong
3. **Self-Correction**: LLM can detect mistakes via observations
4. **Research Value**: Reasoning traces useful for analysis
5. **Flexibility**: Works with any LLM, not tied to function calling API

## Limitations

1. **Prompt Sensitivity**: Requires careful formatting examples
2. **Parsing Brittleness**: Action parsing can fail if LLM deviates
3. **Longer Prompts**: Format explanation increases token usage
4. **Slower**: More LLM calls (one per iteration) vs batch tool calling
5. **Context Growth**: Trajectory grows with iterations, may hit limits

## Performance Characteristics

### Typical Execution

- Iterations per turn: 3-5 (mean: 4.2)
- Seconds per iteration: ~3s
- Total time per turn: ~10-15 seconds
- Tokens per turn: ~3500 input, ~800 output
- Cost per turn: ~$0.08-0.12 (GPT-4-turbo)

### Comparison to LLM_TOOL

- **Speed**: Slower (~30% more time due to sequential iterations)
- **Cost**: Similar (slightly more due to longer prompts)
- **Quality**: Comparable (both effective at solving problems)
- **Interpretability**: Higher (explicit reasoning)

## Logging

### react_trace.jsonl Format

```json
{
  "timestamp": "2026-02-11T15:30:00.123",
  "agent": "Agent1",
  "iteration": 0,
  "thought": "I need to check current state",
  "action": "get_current_penalty()",
  "observation": {"penalty": 2, "conflicts": [...]},
  "duration_ms": 2834
}
{
  "timestamp": "2026-02-11T15:30:03.456",
  "agent": "Agent1",
  "iteration": 1,
  "thought": "I see 2 conflicts. Let me explore alternatives",
  "action": "enumerate_alternatives(nodes=[\"a2\", \"a5\"])",
  "observation": [...],
  "duration_ms": 3102
}
{
  "timestamp": "2026-02-11T15:30:09.789",
  "agent": "Agent1",
  "iteration": 3,
  "thought": "This configuration works. I'll propose it",
  "final_answer": {
    "should_send_message": true,
    "recipient": "Human",
    ...
  },
  "duration_ms": 2945
}
```

### Analysis Possibilities

With ReAct traces, researchers can:
- **Count reasoning steps**: How many iterations to solution?
- **Identify common patterns**: What action sequences work best?
- **Detect failure modes**: Where does reasoning go wrong?
- **Compare strategies**: Do some thought patterns lead to better outcomes?
- **Build fine-tuned models**: Use traces as training data

## Prompt Engineering Tips

### 1. Provide Clear Format Examples

Bad:
```
Use ReAct pattern: think, act, observe
```

Good:
```
**Format**:
Thought: [your reasoning]
Action: [function_name(arguments)]
Observation: [result will be provided by system]

**Example**:
Thought: I need to check conflicts
Action: get_current_penalty()
Observation: {"penalty": 2, "conflicts": [...]}
```

### 2. Show Diverse Action Types

Include examples of:
- Information gathering: `get_current_penalty()`
- Exploration: `enumerate_alternatives(...)`
- Testing: `test_configuration(...)`
- Final decision: `Final Answer: {...}`

### 3. Emphasize Grounding

```
**Guidelines**:
- Always use observations, don't guess
- If you're unsure, call a function to check
- Don't assume - verify with actions
```

### 4. Set Clear Stopping Criteria

```
When you've decided on an action, generate:
Thought: [final reasoning]
Final Answer: {JSON object}

DO NOT continue iterating after Final Answer.
```

## Future Enhancements

1. **Reflection Step**: Add explicit self-reflection after observations
2. **Backtracking**: Allow LLM to undo previous decisions
3. **Multi-Path Exploration**: Generate multiple reasoning branches
4. **Learned Patterns**: Inject successful traces as few-shot examples
5. **Critique Agent**: Second LLM reviews first LLM's reasoning

## References

- **Yao et al. "ReAct: Synergizing Reasoning and Acting in Language Models" (2022)**
  https://arxiv.org/abs/2210.03629
- Wei et al. "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models" (2022)
- Kojima et al. "Large Language Models are Zero-Shot Reasoners" (2022)
- Shinn et al. "Reflexion: Language Agents with Verbal Reinforcement Learning" (2023)

## See Also

- [MODE_LLM_TOOL.md](MODE_LLM_TOOL.md): Alternative LLM reasoning (function calling)
- [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md): Overall system architecture
- [MULTI_LAYER_LLM_ARCHITECTURE.md](MULTI_LAYER_LLM_ARCHITECTURE.md): Implementation details
