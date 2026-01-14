# Developer Guide

## Where to change things
- Message style/prompting: `comm/communication_layer.py`
- Counterfactual enumeration: `agents/cluster_agent.py`
- UI behaviour: `ui/human_turn_ui.py`
- Orchestration/logging: `cluster_simulation.py`

## Adding a mode
1. Add mode in launcher dropdown/config.
2. Implement comm layer in `comm/`.
3. Wire agent creation to use it.
4. Ensure logs include LLM traces if required.

## Testing
Run each mode from `launch_menu.py` and verify UI, messaging, neighbour visibility, and logs.
