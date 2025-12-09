# DCOP Agentic Framework

This repository contains a flexible implementation of a distributed
constraint optimisation framework (DCOP) that allows heterogeneous
agents to coordinate using either raw algorithmic messages or natural
language.  The design is inspired by research on Max–Sum and
human–agent teaming【525359495691552†L395-L402】 and supports multiple
communication and decision‑making modes.

## Agent Modes

Each agent is assigned a **mode** that determines how it makes
decisions and how it communicates.  Modes are specified as short
strings (e.g. `"1A"`, `"1Z"`) in the configuration.  They fall into
two broad categories: **algorithmic modes** (prefixed by `1`) and
**human‑inclusive modes** (prefixed by `2`).

### `1A` – Algorithm‑First with LLM Translation

* **Decision maker:** The agent runs the Max–Sum algorithm internally
  to compute utilities and choose the best colour.  This mirrors
  the standard DCOP approach.
* **Communication:** Every structured message is passed through the
  `LLMCommLayer`.  When an API key and the `openai` library are
  available, the layer calls the LLM to produce a natural‑language
  summary of the message.  Otherwise it falls back to a simple
  key–value string.  This mode is useful when agents do not share
  the same internal representation and must exchange human‑readable
  messages.

### `1Z` – Algorithm‑Only (Shared Syntax)

* **Decision maker:** The same as `1A`: Max–Sum computes utilities
  and selects the best colour.
* **Communication:** Uses the `PassThroughCommLayer`, so messages
  are sent as raw dictionaries (or simple strings) without LLM
  translation.  This mode assumes that all agents share the same
  internal data structures and thus do not need natural‑language
  messaging.  It serves as a clean baseline for benchmarking
  performance when no LLM or human translation is required.

### `1B` – LLM‑First

* **Decision maker:** The agent consults the LLM to choose its next
  assignment.  The underlying algorithm still computes utilities,
  but these are packaged into a prompt and sent to the LLM, which
  recommends the colour to use.  This mode tests the ability of a
  language model to drive the search based on structured input.
* **Communication:** Structured messages are formatted via the
  `LLMCommLayer`, just like in `1A`.

### `1C` – Hybrid ("LLM Sandwich")

* **Decision maker:** A mix of algorithmic and LLM guidance.  The
  agent iteratively runs the algorithm for a few steps, then asks
  the LLM to refine or justify the current choices.  It strikes a
  balance between deterministic optimisation and natural‑language
  reasoning.
* **Communication:** Uses `LLMCommLayer` for translating messages.

### `2A` – Human Communication Layer

The agent follows the algorithm internally but exposes the incoming
and outgoing messages to a human operator.  The human reads the
messages and manually responds (or can allow the agent to use
heuristics when run in non‑interactive mode).

### `2B` – Human Orchestrator

The underlying algorithm is available as a set of tools.  A human
operator decides which tool to run next, inspects intermediate
utilities, and then directs the agent on which colour to choose.

### `2C` – Human Hybrid

Combines automated and human control: the human sets high‑level
objectives or constraints, while the agent executes the algorithm
locally.  Useful when the human wants to intervene occasionally
without micromanaging every step.

## Additional Flags

### `manual_mode`

When set to `True`, the communication layer bypasses any API calls
and instead uses a user‑provided `summariser` function to convert
structured messages into text.  This is useful for offline testing
when no API key is available or when a researcher wants to act as
the LLM.

### `multi_node_mode`

By default, each node in the graph is controlled by its own agent.
Setting `multi_node_mode` to `True` groups nodes by their owner:

* Each owner (e.g. "Alice" or "Bob") controls all nodes listed
  under that owner in the `owners` mapping.
* A `MultiNodeAgent` will jointly optimise the colours for all of
  its nodes, evaluate candidate assignments using the problem’s
  `evaluate_assignment` method, and send its joint assignment to
  neighbouring owners.  Messages are still translated via the
  communication layer.
* `agent_modes` must then specify one mode per owner rather than
  per node.  For example, if `owners={"1":"Alice","2":"Alice","3":"Alice","4":"Bob",...}`
  then `agent_modes=["1A","1Z"]` assigns mode `1A` to Alice and
  mode `1Z` to Bob.

## Running the Simulation

The main entry point for custom experiments is the
`run_custom_simulation` function in `main.py`.  You configure the
simulation via a `CONFIG` dictionary.  Here is an example
configuration that sets up two owners ("Alice" controls nodes 1–3
and uses `1A`, "Bob" controls nodes 4–6 and uses `1Z`), defines the
adjacency (edges) and runs 50 iterations:

```
CONFIG = dict(
    node_names=["1", "2", "3", "4", "5", "6"],
    agent_modes=["1A", "1Z"],
    owners={
        "1": "Alice", "2": "Alice", "3": "Alice",
        "4": "Bob",   "5": "Bob",   "6": "Bob",
    },
    adjacency={
        "1": ["2", "4"],
        "2": ["1", "3"],
        "3": ["2", "6"],
        "4": ["5", "1"],
        "5": ["4", "6"],
        "6": ["5", "3"],
    },
    max_iterations=50,
    interactive=False,
    output_dir="./outputs",
    manual_mode=False,
    multi_node_mode=True,
)
```

After running `python main.py`, the script will generate detailed
logs for each agent, a communication log, a summary of assignments
and penalties per iteration, and a sequence of PNG images showing
how the assignments evolve.  If an API key is available and modes
like `1A` or `1B` are used, messages will be summarised via the
OpenAI API; otherwise the logs will note that heuristic formatting
was used.

For more examples and details on the implementation, see `main.py`
and `run_simulation.py`.