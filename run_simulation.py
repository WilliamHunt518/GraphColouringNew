"""Simple command-line simulation for the DCOP agentic framework.

This script provides a rudimentary environment in which multiple
agents of different modes can interact on a shared DCOP.  It
demonstrates interoperability between algorithmic, LLM-orchestrated and
human-inclusive agents as described in the paper【685583168306604†L370-L375】.

The default scenario uses a three‑node path colouring problem.  Each
agent is assigned a mode based on command-line arguments (1A, 1B, 1C,
2A, 2B, 2C).  The simulation runs for a specified number of
iterations, delivering messages between agents after each step.  For
human modes the script prompts on standard input.

Usage examples
--------------

Run a two-agent graph with an algorithm-first agent and an LLM-first
agent for 5 iterations:

    python -m dcop_framework.run_simulation --nodes a1 a2 --modes 1A 1B --iters 5

Run a human-orchestrated agent against an algorithm-first agent:

    python -m dcop_framework.run_simulation --nodes h1 a1 --modes 2B 1A --iters 3

When specifying human modes (2A, 2B, 2C) the script will prompt the
user to choose colours and messages during execution.  Use the
``--no-interactive`` flag to run in a non-interactive environment
(default actions will then be used for human agents).
"""

from __future__ import annotations

import argparse
from typing import Dict, List, Type

from problems import GraphColoring
from problems.graph_coloring import create_path_graph
from comm.communication_layer import LLMCommLayer, PassThroughCommLayer
from agents import (
    AlgorithmFirstAgent,
    LLMFirstAgent,
    LLMSandwichAgent,
    HumanCLAgent,
    HumanOrchestratorAgent,
    HumanHybridAgent,
)

from agents.base_agent import Message


def build_agent(
    mode: str,
    name: str,
    problem: GraphColoring,
    interactive: bool = True,
    *,
    manual: bool = False,
    summariser: Optional[callable] = None,
):
    """Factory for creating an agent of a given mode.

    Parameters
    ----------
    mode : str
        The agent mode (e.g. "1A", "1B", "1C", "2A", "2B", "2C").
    name : str
        Name of the agent / node.
    problem : GraphColoring
        The colouring problem instance.
    interactive : bool, default True
        Whether to prompt the user for input for human modes.
    manual : bool, default False
        If True, LLM summarisation is bypassed and messages are formatted
        using the provided summariser callback (or heuristics if none).
    summariser : callable, optional
        Function invoked in manual mode to summarise dictionary messages.
    """
    mode = mode.upper()
    # choose communication layer based on mode
    # 1Z assumes a shared syntax and uses pass-through (no LLM translation)
    if mode == "1Z":
        comm_layer = PassThroughCommLayer()
        return AlgorithmFirstAgent(name, problem, comm_layer)
    # algorithmic and LLM modes use the LLM communication layer by default
    if mode in {"1A", "1B", "1C"}:
        comm_layer = LLMCommLayer(manual=manual, summariser=summariser)
    else:
        # human modes also use the LLM layer for prompts
        comm_layer = LLMCommLayer()
    if mode == "1A":
        return AlgorithmFirstAgent(name, problem, comm_layer)
    if mode == "1B":
        return LLMFirstAgent(name, problem, comm_layer)
    if mode == "1C":
        return LLMSandwichAgent(name, problem, comm_layer)
    # human-inclusive modes
    if mode == "2A":
        return HumanCLAgent(name, problem, comm_layer) if interactive else HumanCLAgent(
            name, problem, comm_layer, auto_response=lambda prompt: ""
        )
    if mode == "2B":
        return HumanOrchestratorAgent(name, problem, comm_layer) if interactive else HumanOrchestratorAgent(
            name, problem, comm_layer, auto_response=lambda prompt: ""
        )
    if mode == "2C":
        return HumanHybridAgent(name, problem, comm_layer) if interactive else HumanHybridAgent(
            name, problem, comm_layer, auto_response=lambda prompt: ""
        )
    raise ValueError(f"Unknown mode {mode}")


def run_simulation(nodes: List[str], modes: List[str], iters: int, interactive: bool) -> None:
    # create a simple path graph connecting all nodes sequentially
    edges = [(nodes[i], nodes[i + 1]) for i in range(len(nodes) - 1)]
    domain = ["red", "green", "blue"]
    problem = GraphColoring(nodes, edges, domain)
    # instantiate agents
    agents = [build_agent(mode, name, problem, interactive) for name, mode in zip(nodes, modes)]
    # message queue for delivery between iterations
    for step in range(1, iters + 1):
        print(f"\n=== Iteration {step} ===")
        # each agent performs a step
        for agent in agents:
            agent.step()
        # deliver messages
        deliveries: List[Message] = []
        for agent in agents:
            deliveries += agent.sent_messages
            # clear sent messages for next iteration
            agent.sent_messages = []
        # deliver to recipients
        for msg in deliveries:
            # find recipient agent
            for agent in agents:
                if agent.name == msg.recipient:
                    agent.receive(msg)
                    break
        # after delivery, show current assignments
        assignments = {agent.name: agent.assignment for agent in agents}
        print(f"Assignments: {assignments}")
        # compute and print global cost
        cost = problem.evaluate_assignment(assignments)
        print(f"Global penalty: {cost}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nodes", nargs="+", default=["a1", "a2"], help="List of node names")
    parser.add_argument("--modes", nargs="+", default=["1A", "1A"], help="Modes for each node")
    parser.add_argument("--iters", type=int, default=5, help="Number of iterations")
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Disable interactive prompts for human agents (auto mode)",
    )
    args = parser.parse_args()
    if len(args.nodes) != len(args.modes):
        parser.error("--nodes and --modes must have the same length")
    run_simulation(args.nodes, args.modes, args.iters, not args.no_interactive)


if __name__ == "__main__":  # pragma: no cover
    main()