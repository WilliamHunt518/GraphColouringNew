# Graph Coloring Negotiation System - Complete Architecture

## Overview

This is a research system for studying **human-agent coordination via language** in a **distributed graph coloring problem** with **partial observability**. The system enables controlled experiments comparing different communication modalities while maintaining identical underlying optimization constraints.

## Core Problem: Distributed Graph Coloring

### Problem Definition

Given:
- A graph `G = (V, E)` with nodes `V` and edges `E`
- A set of colors `D = {red, blue, green, yellow, ...}`
- A partition of nodes into clusters: `V = V_agent1 ∪ V_human ∪ V_agent2`

Goal:
- Assign colors to nodes such that no adjacent nodes share the same color
- Minimize penalty function: `penalty = Σ_{(u,v) ∈ E} [color(u) == color(v)]`

Constraint:
- **Partial observability**: Each participant sees only their own cluster fully; they see neighbor clusters' boundary nodes only

### Example Graph

```
Cluster 1 (Agent1)    Cluster 2 (Human)    Cluster 3 (Agent2)
    a1 ─────────────── h1 ────────────────── b1
    │                   │                     │
    a2 ─────────────── h2                     b2
    │                   │                     │
    a3                  h3 ────────────────── b3
    │                   │
    a4 ─────────────── h4
    │                   │
    a5 ─────────────── h5
```

**What Agent1 sees:**
- Full cluster: {a1, a2, a3, a4, a5} with internal edges
- Boundary neighbors: {h1, h2, h4, h5} (nodes from Human's cluster that connect)
- Neighbor colors: Only if reported via messages OR if human assigns them in UI

**What Agent1 does NOT see:**
- Human's internal structure (h3 exists, edges between h-nodes)
- Agent2's existence or structure (unless human relays information)

## System Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────────┐
│                     GUI / Experiment Launcher                    │
│                      (launch_menu.py)                            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Simulation Orchestrator                        │
│                   (cluster_simulation.py)                        │
│  • Manages simulation loop                                       │
│  • Routes messages between agents                                │
│  • Handles UI callbacks                                          │
│  • Logs all interactions                                         │
└──────┬──────────────────────┬─────────────────────┬─────────────┘
       │                      │                     │
       ▼                      ▼                     ▼
┌─────────────┐    ┌─────────────────┐    ┌─────────────┐
│   Agent1    │───▶│  Human (GUI)    │◀───│   Agent2    │
│ ClusterAgent│    │ HumanTurnUI     │    │ ClusterAgent│
└──────┬──────┘    └────────┬────────┘    └──────┬──────┘
       │                    │                     │
       │                    │                     │
       ▼                    ▼                     ▼
┌──────────────────────────────────────────────────────────┐
│              Communication Layer (Mode-Specific)          │
│  • RB: Rule-based templates                               │
│  • LLM_RB: NL ↔ RB grammar translation                    │
│  • LLM_API: Constraint-oriented messages                  │
│  • LLM_TOOL: Multi-layer with function calling            │
│  • LLM_REACT: Multi-layer with ReAct reasoning            │
└──────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│              Problem Layer                                │
│  • GraphColoring: Constraint representation               │
│  • Penalty computation                                    │
│  • Feasibility checking                                   │
└──────────────────────────────────────────────────────────┘
```

### Agent Architecture

Every agent contains:

```python
class ClusterAgent:
    # State
    nodes: List[str]              # Nodes owned by this agent
    assignments: Dict[str, str]   # Current color assignments
    neighbour_assignments: Dict   # Known neighbor colors

    # Knowledge
    problem: GraphColoring        # Problem definition
    domain: List[str]             # Available colors
    owners: Dict[str, str]        # Node ownership mapping

    # Communication
    comm_layer: BaseCommLayer     # Mode-specific communication
    sent_messages: List[Message]  # Outgoing message queue

    # Reasoning (mode-specific)
    algorithm: str                # "greedy" or "maxsum"

    # Methods
    def step(self) -> None:
        """Execute one reasoning step and generate messages"""

    def receive(self, msg: Message) -> None:
        """Process incoming message and update beliefs"""

    def _solve(self) -> Dict[str, str]:
        """Run local optimization algorithm"""
```

## Communication Modes (Experimental Conditions)

The system supports **five communication modes** as within-subject experimental conditions:

| Mode | Description | Agent Reasoning | Communication Style |
|------|-------------|-----------------|---------------------|
| **RB** | Pure rule-based | Algorithmic | Structured templates |
| **LLM_RB** | Natural language ↔ RB | Algorithmic | NL with grammar translation |
| **LLM_API** | Constraint messages | Algorithmic | Constraint-oriented NL |
| **LLM_TOOL** | Function calling | **LLM-based** | Multi-layer with tools |
| **LLM_REACT** | ReAct reasoning | **LLM-based** | Multi-layer with reasoning traces |

### Key Distinction: Algorithmic vs LLM-Based Reasoning

**Algorithmic Modes (RB, LLM_RB, LLM_API)**:
- Agent uses **hardcoded algorithms** (greedy coloring, max-sum)
- LLM is used ONLY for **message formatting** (turning structured data into natural language)
- Decision logic is deterministic and explainable

**LLM-Based Modes (LLM_TOOL, LLM_REACT)**:
- Agent uses **LLM for reasoning** about the graph coloring problem
- Backend LLM can call API functions to explore solution space
- Communication layer (Speech LLM) translates between human NL and backend protocol
- Decisions are emergent from LLM reasoning, not hardcoded

## Two-Phase Workflow

All modes follow a two-phase protocol:

### Phase 1: Configure
1. **Agents compute initial assignments** using local solver
2. **Human assigns initial colors** to their nodes via GUI
3. **Agents wait** for announcement trigger

### Phase 2: Bargain
1. **Human clicks "Announce Configuration"**
2. **Agents send announcements** to all neighbors:
   - Natural language description of boundary assignments
   - Embedded `[report: {...}]` tag for UI color updates
3. **Agents analyze** situation (conflicts, penalties)
4. **Agents send first substantive message** (if conflicts exist):
   - Proposals for changes
   - Requests to human
   - Acceptance if no conflicts
5. **Negotiation proceeds** via async chat interface

### Message Flow Example

```
[Phase 1: Configure]
Agent1: (computes a1=red, a2=blue internally, waits)
Human: (assigns h1=red, h2=blue via GUI)

[Phase 2: Announce - Triggered by human clicking button]
Agent1 → Human: "Here's my initial configuration: a1=red, a2=blue
                 [report: {"a1": "red", "a2": "blue"}]"

[Phase 2: First Substantive Message - Agent analyzes conflicts]
Agent1 → Human: "I see there's a conflict between a1 and h1 (both red).
                 I propose changing a1 to green. Would that work for you?"

[Phase 2: Negotiation - Human responds]
Human → Agent1: "Yes, but can you use blue for a1 instead? I need green for h3"

[Phase 2: Continued negotiation...]
Agent1 → Human: "That works for me. I'll use a1=blue, a2=green.
                 [report: {"a1": "blue", "a2": "green"}]"
```

## Data Flow Architecture

### Message Routing

```
Human types message in GUI chat window
        ↓
UI creates Message(sender="Human", recipient="Agent1", content="...")
        ↓
Simulation.on_send(recipient, text, assignments)
        ↓
Message routed to target agent
        ↓
Agent.receive(msg)
        ↓
Agent updates beliefs (neighbour_assignments, constraints)
        ↓
Agent.step() generates response
        ↓
Agent.send(recipient, content) via comm_layer
        ↓
Comm layer formats structured → natural language
        ↓
Message added to agent.sent_messages queue
        ↓
Simulation extracts messages from queue
        ↓
Messages returned to UI for display
        ↓
UI updates chat transcript and graph visualization
```

### Special Tokens

Certain tokens bypass normal communication layers:

- `__ANNOUNCE_CONFIG__`: Triggers configuration announcement phase
- `__IMPOSSIBLE__`: (RB mode only) Marks infeasibility

These are created directly as Message objects to preserve exact string matching.

## Logging and Observability

### Log Files (per run in `results/<mode>_<timestamp>/`)

1. **`communication_log.txt`**: All messages with timestamps
   ```
   2026-02-11T15:09:58.131    Human->Agent1    "Can you change a2 to green?"
   2026-02-11T15:10:05.421    Agent1->Human    "Yes, I propose a2=green..."
   ```

2. **`Agent1_log.txt`**, **`Agent2_log.txt`**, **`Human_log.txt`**: Per-participant traces
   - Reasoning steps
   - Belief updates
   - Internal solver calls

3. **`iteration_summary.txt`**: High-level progress
   ```
   Iteration 0: Penalty=3, Agent1={a1:red, a2:blue}, Human={h1:red, h2:blue}
   Iteration 1: Penalty=1, Agent1={a1:green, a2:blue}, Human={h1:red, h2:blue}
   ```

4. **`llm_trace.jsonl`** (LLM modes only): Complete LLM API traces
   ```json
   {"timestamp": "...", "event": "llm_call", "prompt": "...", "response": "..."}
   {"timestamp": "...", "event": "parse_result", "structured": {...}}
   ```

### UI Observability

The GUI provides real-time visibility:

- **Graph visualization**: Nodes colored according to current assignments
- **Chat transcripts**: Full message history per neighbor
- **Penalty display**: Current constraint violation count
- **Satisfaction indicators**: Checkboxes for consensus tracking

## Termination Conditions

### Important: No Auto-Termination

The system does **NOT** automatically terminate when `penalty == 0`. This is intentional for research validity:

**Why?**
- Human may be satisfied with suboptimal solution (penalty > 0)
- Human may want to continue exploring even when valid (penalty == 0)
- Consensus must be explicit to measure coordination

### Actual Termination

The run ends when **consensus** is reached:

1. **Human ticks "I'm satisfied" checkbox** for each neighbor
2. **Each agent reports** `agent.satisfied == True`
3. **UI closes** with `ui.end_reason == "consensus"`

### Fallback

- Human can manually close UI anytime (recorded as `end_reason == "manual_close"`)
- Timeout after configurable duration (default: 30 minutes)

## Partial Observability Constraints

**CRITICAL**: System must never leak hidden topology.

### What Each Agent Sees

```python
# Agent1 sees:
visible_nodes = agent.nodes + boundary_neighbors(agent.nodes)
visible_edges = [(u, v) for (u, v) in all_edges
                 if u in agent.nodes or v in agent.nodes]

# Agent1 does NOT see:
hidden_internal = human_cluster_internal_structure
hidden_agents = other_agent_clusters
```

### Example Violation (FORBIDDEN)

```python
# BAD: Agent should not know about h3's existence
agent_msg = "I know h3 connects to h1, so..."  # ❌ LEAK!

# GOOD: Agent only knows boundary nodes
agent_msg = "I see h1 and h2 connect to my cluster..."  # ✓ OK
```

### How Neighbor Colors are Learned

Agents learn neighbor colors through:

1. **Explicit reports in messages**: `[report: {"h1": "red"}]`
2. **Inference from constraints**: If human says "h1 can't be red", agent knows h1 ≠ red
3. **UI updates**: When human changes colors in GUI, agents see boundary node updates

Agents do NOT learn through:
- ❌ Accessing global graph structure
- ❌ Querying non-boundary nodes
- ❌ Inferring internal cluster structure

## Determinism and Reproducibility

For research validity, the system maintains determinism where possible:

### Deterministic Components
- Graph structure and partitioning
- Algorithmic solvers (greedy, max-sum)
- Rule-based message generation (RB mode)
- Message routing and logging

### Non-Deterministic Components
- LLM-based communication (temperature > 0)
- Human decisions and timing
- Thread scheduling in UI

### Reproducibility Strategy
- **Seed control**: Graph generation uses fixed seed
- **LLM logging**: All prompts and responses logged
- **Timestamp precision**: Microsecond-level message logs
- **Version control**: Git hash recorded in experiment metadata

## Key Design Principles

1. **Separation of Concerns**
   - Problem logic (GraphColoring) is independent of communication
   - Agents are independent of UI
   - Communication layers are pluggable

2. **Mode-Specific Behavior via Composition**
   - Different modes = different `comm_layer` instances
   - Same agent class, different communication strategy

3. **Explicit over Implicit**
   - Special tokens are explicit strings, not inferred
   - Phase transitions are explicit state changes
   - Satisfaction is explicit checkboxes, not auto-detected

4. **Observability First**
   - Every decision is logged
   - Every LLM call is traced
   - Every message is timestamped

5. **Human-in-the-Loop**
   - Human is never automated
   - Human controls when to announce, when to respond, when to end
   - Human can override any agent behavior via chat

## File Structure Summary

```
GraphColouringNew/
├── agents/
│   ├── base_agent.py              # Message class, BaseAgent
│   ├── cluster_agent.py           # Core ClusterAgent (algorithmic)
│   ├── rule_based_cluster_agent.py # RB-specific logic
│   ├── tool_calling_cluster_agent.py # LLM_TOOL mode
│   ├── react_cluster_agent.py     # LLM_REACT mode
│   └── cluster_agent_api.py       # API library for LLM modes
├── comm/
│   ├── communication_layer.py     # BaseCommLayer, LLMCommLayer
│   ├── llm_rb_comm_layer.py       # LLM_RB translation
│   └── speech_llm_layer.py        # Multi-layer LLM speech layer
├── ui/
│   └── human_turn_ui.py           # Tkinter GUI
├── problems/
│   └── graph_coloring.py          # GraphColoring problem class
├── tests/
│   └── test_*.py                  # All test files
├── docs/
│   ├── SYSTEM_OVERVIEW.md         # This file
│   ├── MODE_*.md                  # Per-mode documentation
│   └── ...                        # Other docs
├── launch_menu.py                 # GUI launcher
├── run_experiment.py              # Programmatic runner
├── cluster_simulation.py          # Main simulation orchestrator
└── api_key.txt                    # OpenAI API key (gitignored)
```

## Next Steps

For detailed information on specific modes, see:

- **[MODE_RB.md](MODE_RB.md)**: Pure rule-based communication
- **[MODE_LLM_RB.md](MODE_LLM_RB.md)**: Natural language with RB grammar
- **[MODE_LLM_API.md](MODE_LLM_API.md)**: Constraint-oriented messages
- **[MODE_LLM_TOOL.md](MODE_LLM_TOOL.md)**: Function calling with backend LLM
- **[MODE_LLM_REACT.md](MODE_LLM_REACT.md)**: ReAct reasoning pattern

For implementation guides:
- **[DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)**: Where to modify code
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)**: Common issues

For quickstart:
- **[QUICK_START_LLM_MODES.md](QUICK_START_LLM_MODES.md)**: Running LLM modes
- **[README.md](../README.md)**: Project overview
