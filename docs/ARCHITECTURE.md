# Architecture

## Participants and clusters

In the default main experiment, the graph is partitioned into 3 clusters:

`Agent1 — Human — Agent2`

Inter-cluster edges are sparse and connect via **boundary nodes**.

Each participant controls exactly one subgraph (cluster), and coordinates through messages that discuss boundary nodes.

## Data flow (async UI)

1. Human edits colours by clicking owned nodes.
2. Human sends a message in chat pane (Agent1 or Agent2).
3. UI invokes `on_send(neigh, msg, current_assignments)` in a background thread.
4. Simulation routes the message to the relevant agent controller.
5. Agent updates beliefs about neighbour boundary colours, runs its local solver, and responds.
6. UI receives the response and updates:
   - chat transcript
   - known neighbour colours (from `[report: {...}]`)
   - graph rendering (neighbour node fill colours, conflict edges)

## Correctness constraints

- Do **not** leak hidden topology.
- Neighbour node colours must not be shown unless:
  - they are boundary nodes connected to the local cluster, and
  - the colour is known (assignment exists) or was explicitly reported.

## Debugging hooks

The debug window takes:
- `debug_agents`: list of agent objects
- `debug_get_visible_graph_fn(owner_name)`: provides the visible graph for that participant

The UI tries to show:
- visible graph summary
- satisfaction state
- reasoning history tail
- state snapshot / assignments
