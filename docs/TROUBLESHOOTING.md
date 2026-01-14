# Troubleshooting

## IndentationError / missing methods

Symptoms:
- `AttributeError: HumanTurnUI has no attribute ...`
- `IndentationError: unindent does not match ...`

Cause: a method was unintentionally unindented and moved outside the class.

Fix:
- ensure all `def ...` inside the class have consistent indentation
- consider moving helpers into a separate file/module.

## Agent never becomes satisfied

Cause: greedy local search can stall in a non-optimal local configuration.

Fix:
- `agents/cluster_agent.py` snaps to the best local assignment when it detects `current_penalty > best_penalty`.

## UI never terminates

The UI ends when **consensus** is reached:
- human satisfied (per chat pane) AND agent satisfied (per pane).

If it doesn't end:
- ensure `get_agent_satisfied_fn` is wired
- ensure agents update `agent.satisfied`
- check debug window "satisfied" for each agent
