"""
Modular tests for conditional offer handling in LLM_TOOL and LLM_REACT modes.

Test message: "If I did h1=red I could do either blue or red for h4. Can this work for you?"

Expected behaviour:
- Agent receives message from Human stating TWO alternative colour assignments
  for h4, conditioned on h1=red.
- Agent should understand this as TWO scenarios to test:
    Scenario A: h1=red, h4=red
    Scenario B: h1=red, h4=blue
- Agent should call simulate_neighbor_change() / get_best_response_to()
  for BOTH scenarios (not just one).
- If both work → say so ("either works").
- If only one works → say which one ("only h4=blue works").
- If neither works → counter-propose.
- Message constitutes an offer; agent's acceptance/counter-proposal can
  reference it later.

Tests
-----
1. test_speech_layer_parsing()
       SpeechLLMLayer.human_to_backend() — does it extract both alternatives?
2. test_tool_inbound_translation()
       ToolCallingClusterAgent._translate_inbound() — does it generate
       API calls for BOTH scenarios?
3. test_tool_full_pipeline()
       ToolCallingClusterAgent.step() — does the full 3-phase response
       correctly address both alternatives?
4. test_react_full_pipeline()
       ReActClusterAgent.step() — does the ReAct loop explore both scenarios?

Run with:
    python test_conditional_offers.py
    python test_conditional_offers.py --test speech      # only test 1
    python test_conditional_offers.py --test tool_in     # only test 2
    python test_conditional_offers.py --test tool_full   # only test 3
    python test_conditional_offers.py --test react       # only test 4
"""

from __future__ import annotations

import sys
import json
import textwrap
import time
import argparse
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Problem & agent construction helpers
# ---------------------------------------------------------------------------

def _make_problem():
    """Minimal graph coloring problem with agent cluster [a4,a5] and
    human boundary nodes [h1,h4].

    Graph:
        a4 -- h1    (Agent1 ← Human)
        a5 -- h4    (Agent1 ← Human)
        a4 -- a5    (internal edge between agent nodes)

    This gives agent visibility into exactly h1 and h4 (both boundary).
    """
    from problems.graph_coloring import GraphColoring

    all_nodes = ["a4", "a5", "h1", "h4"]
    edges = [
        ("a4", "h1"),   # Agent boundary ↔ Human
        ("a5", "h4"),   # Agent boundary ↔ Human
        ("a4", "a5"),   # Internal agent edge
    ]
    domain = ["red", "blue", "green"]
    return GraphColoring(nodes=all_nodes, edges=edges, domain=domain)


def _make_owners():
    return {"a4": "Agent1", "a5": "Agent1", "h1": "Human", "h4": "Human"}


def _make_comm_layer():
    """Return a simple pass-through comm layer (no LLM, no formatting)."""
    from comm.communication_layer import PassThroughCommLayer
    return PassThroughCommLayer()


def _make_speech_layer():
    """Return a SpeechLLMLayer using the project API key."""
    from comm.speech_llm_layer import SpeechLLMLayer
    return SpeechLLMLayer(model="gpt-4-turbo", use_llm=True)


def _make_tool_agent(initial_neighbor_assignments: Dict[str, str]) -> Any:
    """Construct a ToolCallingClusterAgent for the test problem."""
    from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
    from comm.speech_llm_layer import SpeechLLMLayer

    problem = _make_problem()
    owners = _make_owners()
    comm = SpeechLLMLayer(model="gpt-4-turbo", use_llm=True)

    agent = ToolCallingClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=comm,
        local_nodes=["a4", "a5"],
        owners=owners,
        backend_model="gpt-4-turbo",
        algorithm="maxsum",
        initial_assignments={"a4": "blue", "a5": "green"},
    )
    # Inject current neighbor knowledge
    agent.neighbour_assignments.update(initial_neighbor_assignments)
    return agent


def _make_react_agent(initial_neighbor_assignments: Dict[str, str]) -> Any:
    """Construct a ReActClusterAgent for the test problem."""
    from agents.react_cluster_agent import ReActClusterAgent
    from comm.speech_llm_layer import SpeechLLMLayer

    problem = _make_problem()
    owners = _make_owners()
    comm = SpeechLLMLayer(model="gpt-4-turbo", use_llm=True)

    agent = ReActClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=comm,
        local_nodes=["a4", "a5"],
        owners=owners,
        backend_model="gpt-4-turbo",
        max_react_iterations=12,
        algorithm="maxsum",
        initial_assignments={"a4": "blue", "a5": "green"},
    )
    agent.neighbour_assignments.update(initial_neighbor_assignments)
    return agent


# ---------------------------------------------------------------------------
# Pretty-print helpers
# ---------------------------------------------------------------------------

SEP = "=" * 72

def banner(title: str) -> None:
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


def result(label: str, value: Any) -> None:
    print(f"\n  [{label}]")
    if isinstance(value, (dict, list)):
        for line in json.dumps(value, indent=4).splitlines():
            print(f"    {line}")
    else:
        for line in str(value).splitlines():
            print(f"    {line}")


def check(condition: bool, description: str) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"\n  [{status}] {description}")


# ---------------------------------------------------------------------------
# Scenario definition
# ---------------------------------------------------------------------------

# Neighbour state BEFORE the human's message arrives:
#   h1=green, h4=red  →  a4 conflicts with h1 (a4=blue≠green ok), a5 conflicts with h4 (a5=green≠red ok)
# Actually let's choose a state where there IS a conflict so negotiation is needed:
#   h1=blue → conflicts with a4=blue;  h4=green → conflicts with a5=green
INITIAL_NEIGHBORS = {"h1": "blue", "h4": "green"}

TEST_MESSAGE = (
    "If I did h1=red I could do either blue or red for h4. "
    "Can this work for you?"
)

# Both scenarios the message implies:
SCENARIO_A = {"h1": "red", "h4": "red"}   # Scenario A
SCENARIO_B = {"h1": "red", "h4": "blue"}  # Scenario B


# ---------------------------------------------------------------------------
# Test 1: Speech layer parsing
# ---------------------------------------------------------------------------

def test_speech_layer_parsing():
    """Test whether SpeechLLMLayer.human_to_backend() correctly parses
    the conditional dual-alternative offer.

    Expected:
    - type: 'question' or 'conditional'
    - conditions list contains TWO entries (h4=red and h4=blue conditioned on h1=red)
      OR requested_changes mentions both alternatives somehow
    - NOT treated as a simple single-color constraint
    """
    banner("TEST 1: Speech Layer Parsing (human_to_backend)")

    print(f"\n  Message: {TEST_MESSAGE!r}")
    print(f"  Initial neighbor state: {INITIAL_NEIGHBORS}")

    speech = _make_speech_layer()

    t0 = time.time()
    structured = speech.human_to_backend(
        sender="Human",
        recipient="Agent1",
        nl_text=TEST_MESSAGE,
    )
    elapsed = time.time() - t0

    result("Structured output", structured)
    print(f"\n  LLM call took {elapsed:.1f}s")

    # --- Evaluation ---
    msg_type = structured.get("type", "")
    conditions = structured.get("conditions", [])
    requested = structured.get("requested_changes", {})
    constraints = structured.get("constraints", [])

    check(
        msg_type in ("question", "conditional", "proposal"),
        f"type='{msg_type}' is question/conditional/proposal"
    )
    check(
        len(conditions) >= 1,
        f"conditions list has {len(conditions)} entries (>=1 expected for if-then)"
    )
    # The key test: did it capture BOTH h4 alternatives?
    # Accept several valid representations:
    #   - Two separate condition entries
    #   - One condition where the "then" value for h4 is a list ["blue","red"]
    #   - JSON text containing both colors alongside h4
    cond_text = json.dumps(conditions).lower()
    both_colors_present = "red" in cond_text and "blue" in cond_text
    has_both_h4 = ("h4" in cond_text) and both_colors_present
    check(
        has_both_h4,
        "conditions capture BOTH h4 alternatives (red and blue) -- "
        f"{'PASS: list-form or dual entries' if has_both_h4 else 'FAIL: only one color for h4'}"
    )
    check(
        "h1" in cond_text or "h1" in json.dumps(requested).lower(),
        "h1=red condition is captured"
    )

    return structured


# ---------------------------------------------------------------------------
# Test 2: LLM_TOOL inbound translation
# ---------------------------------------------------------------------------

def test_tool_inbound_translation():
    """Test whether ToolCallingClusterAgent._translate_inbound() generates
    API calls for BOTH conditional scenarios.

    Expected API calls:
    - At least two simulate_neighbor_change() or get_best_response_to() calls
    - One for (h1=red, h4=red), one for (h1=red, h4=blue)
    """
    banner("TEST 2: LLM_TOOL Inbound Translation (_translate_inbound)")

    print(f"\n  Message: {TEST_MESSAGE!r}")
    print(f"  Agent nodes: a4, a5")
    print(f"  Visible neighbor nodes: h1 (via a4-h1 edge), h4 (via a5-h4 edge)")
    print(f"  Initial neighbor assignments: {INITIAL_NEIGHBORS}")
    print(f"  Agent assignments: a4=blue, a5=green")

    agent = _make_tool_agent(INITIAL_NEIGHBORS)

    t0 = time.time()
    api_calls = agent._translate_inbound(TEST_MESSAGE)
    elapsed = time.time() - t0

    result("Generated API calls", api_calls)
    print(f"\n  LLM call took {elapsed:.1f}s")

    # --- Evaluation ---
    methods = [c.get("method", "") for c in api_calls]
    neighbor_configs = []
    for c in api_calls:
        if c.get("method") in ("simulate_neighbor_change", "get_best_response_to"):
            params = c.get("params", {})
            cfg = params.get("neighbor_nodes") or params.get("neighbor_assignments") or {}
            if cfg:
                neighbor_configs.append(cfg)

    print(f"\n  Neighbor configs tested: {neighbor_configs}")

    check(
        len(api_calls) >= 2,
        f"{len(api_calls)} API calls generated (>=2 expected for dual alternatives)"
    )
    check(
        any(m in ("simulate_neighbor_change", "get_best_response_to") for m in methods),
        "At least one simulation/best-response call present"
    )

    # Check if BOTH scenarios appear in configs
    def config_matches(cfg, target):
        return all(cfg.get(k) == v for k, v in target.items())

    scenario_a_tested = any(config_matches(cfg, SCENARIO_A) for cfg in neighbor_configs)
    scenario_b_tested = any(config_matches(cfg, SCENARIO_B) for cfg in neighbor_configs)

    check(scenario_a_tested, f"Scenario A tested: h1=red, h4=red => {SCENARIO_A}")
    check(scenario_b_tested, f"Scenario B tested: h1=red, h4=blue => {SCENARIO_B}")
    check(
        scenario_a_tested and scenario_b_tested,
        "BOTH alternatives are tested (key requirement)"
    )

    return api_calls


# ---------------------------------------------------------------------------
# Test 3: LLM_TOOL full pipeline
# ---------------------------------------------------------------------------

def test_tool_full_pipeline():
    """Test the full 3-phase LLM_TOOL pipeline response to the conditional offer.

    Injects the test message, calls step(), captures the outbound message.

    Expected:
    - Response acknowledges BOTH scenarios (or explains which one works)
    - Response is specific about h4 color options
    - If one scenario is infeasible, response says which one works
    - If both work, response says either is fine
    """
    banner("TEST 3: LLM_TOOL Full Pipeline (step)")

    print(f"\n  Message: {TEST_MESSAGE!r}")
    print(f"  Agent nodes: a4, a5  (current: a4=blue, a5=green)")
    print(f"  Initial neighbor state: {INITIAL_NEIGHBORS}")
    print(f"  Expected: Agent tests both h4=red and h4=blue with h1=red")

    from agents.base_agent import Message

    agent = _make_tool_agent(INITIAL_NEIGHBORS)
    # Skip the configure/announcement phase so step() goes straight to bargaining
    agent._config_announced = True
    agent._phase = "bargain"

    # Intercept outgoing messages
    sent_messages: List[Dict] = []
    original_send = agent.send

    def capture_send(recipient, content):
        sent_messages.append({"recipient": recipient, "content": content})
        print(f"\n  [CAPTURED OUTBOUND to {recipient}]")
        if isinstance(content, dict):
            for line in json.dumps(content, indent=4).splitlines():
                print(f"    {line}")
        else:
            for line in str(content).splitlines():
                print(f"    {line}")
        return original_send(recipient, content)

    agent.send = capture_send

    # Simulate receiving the message (receive() takes a Message dataclass)
    msg = Message(sender="Human", recipient="Agent1", content=TEST_MESSAGE)
    agent.receive(msg)

    t0 = time.time()
    agent.step()
    elapsed = time.time() - t0

    print(f"\n  step() completed in {elapsed:.1f}s")

    # --- Evaluation ---
    check(
        len(sent_messages) >= 1,
        f"Agent sent {len(sent_messages)} message(s) (>=1 expected)"
    )

    if sent_messages:
        response_text = str(sent_messages[0].get("content", "")).lower()

        # Check for specificity about both options
        mentions_h4 = "h4" in response_text
        mentions_red = "red" in response_text
        mentions_blue = "blue" in response_text
        mentions_both = mentions_red and mentions_blue

        check(mentions_h4, "Response mentions h4")
        check(
            mentions_both,
            "Response mentions both red and blue (acknowledging alternatives)"
        )
        check(
            "h1" in response_text,
            "Response mentions h1 (the conditional node)"
        )

    return sent_messages


# ---------------------------------------------------------------------------
# Test 4: ReAct full pipeline
# ---------------------------------------------------------------------------

def test_react_full_pipeline():
    """Test the ReAct loop's response to the conditional offer.

    Expected:
    - Thought-action-observation trace explores BOTH scenarios
    - Actions include simulate_neighbor_change or get_best_response_to
      for (h1=red, h4=red) AND (h1=red, h4=blue)
    - Final Answer is specific and not vague
    """
    banner("TEST 4: LLM_REACT Full Pipeline (step)")

    print(f"\n  Message: {TEST_MESSAGE!r}")
    print(f"  Agent nodes: a4, a5  (current: a4=blue, a5=green)")
    print(f"  Initial neighbor state: {INITIAL_NEIGHBORS}")
    print(f"  Expected: ReAct loop uses actions to test both h4 alternatives")

    from agents.base_agent import Message

    agent = _make_react_agent(INITIAL_NEIGHBORS)
    # Skip the configure/announcement phase
    agent._config_announced = True
    agent._phase = "bargain"

    sent_messages: List[Dict] = []
    original_send = agent.send

    def capture_send(recipient, content):
        sent_messages.append({"recipient": recipient, "content": content})
        print(f"\n  [CAPTURED OUTBOUND to {recipient}]")
        if isinstance(content, dict):
            for line in json.dumps(content, indent=4).splitlines():
                print(f"    {line}")
        else:
            for line in str(content).splitlines():
                print(f"    {line}")
        return original_send(recipient, content)

    agent.send = capture_send

    # Capture the ReAct trajectory for analysis
    trajectory_lines: List[str] = []
    original_log = agent.log

    def capture_log(msg):
        original_log(msg)
        trajectory_lines.append(msg)

    agent.log = capture_log

    # Inject message (receive() takes a Message dataclass)
    msg = Message(sender="Human", recipient="Agent1", content=TEST_MESSAGE)
    agent.receive(msg)

    t0 = time.time()
    agent.step()
    elapsed = time.time() - t0

    print(f"\n  step() completed in {elapsed:.1f}s")

    # Print ReAct trajectory lines that contain Action:/Thought:/Final Answer:
    print(f"\n  [ReAct Trajectory Summary]")
    for line in trajectory_lines:
        if any(kw in line for kw in ("Thought:", "Action:", "Observation:", "Final Answer:", "[REACT]")):
            print(f"    {line[:200]}")

    # --- Evaluation ---
    traj_text = " ".join(trajectory_lines).lower()

    # Count how many simulation calls appeared in the trajectory
    sim_calls = traj_text.count("simulate_neighbor_change")
    best_calls = traj_text.count("get_best_response_to")

    check(sim_calls + best_calls >= 2,
          f"{sim_calls} simulate_neighbor_change + {best_calls} get_best_response_to calls (>=2 expected)")
    check(
        "h4" in traj_text and ("h4" in traj_text),
        "Trajectory mentions h4"
    )

    # Check if BOTH scenarios were explored
    scenario_a_in_traj = ('"h4": "red"' in " ".join(trajectory_lines) and
                          '"h1": "red"' in " ".join(trajectory_lines))
    scenario_b_in_traj = ('"h4": "blue"' in " ".join(trajectory_lines) and
                          '"h1": "red"' in " ".join(trajectory_lines))

    check(scenario_a_in_traj, "Trajectory includes Scenario A: h1=red, h4=red")
    check(scenario_b_in_traj, "Trajectory includes Scenario B: h1=red, h4=blue")

    check(
        len(sent_messages) >= 1,
        f"Agent sent {len(sent_messages)} message(s)"
    )

    if sent_messages:
        response_text = str(sent_messages[0].get("content", "")).lower()
        check("h4" in response_text, "Final response mentions h4")

    return sent_messages


# ---------------------------------------------------------------------------
# Additional quick API-only test (no LLM) to verify the API layer handles
# the two scenarios correctly
# ---------------------------------------------------------------------------

def test_api_layer_both_scenarios():
    """Non-LLM test: directly call the API with both scenarios and verify
    the deterministic layer gives sensible results.

    This is a sanity check that the API layer itself is not the bottleneck.
    """
    banner("TEST 0 (API sanity): simulate_neighbor_change for both scenarios")

    problem = _make_problem()
    owners = _make_owners()
    from comm.communication_layer import PassThroughCommLayer
    from agents.tool_calling_cluster_agent import ToolCallingClusterAgent
    from comm.speech_llm_layer import SpeechLLMLayer

    # Build agent but bypass OpenAI init to test only the API layer
    # We do this by creating a minimal stub of the agent without calling
    # the full constructor (which requires API key). Instead, test via
    # ClusterAgentAPI directly on a real ClusterAgent.
    from agents.cluster_agent import ClusterAgent
    from agents.cluster_agent_api import ClusterAgentAPI

    comm = PassThroughCommLayer()
    base_agent = ClusterAgent(
        name="Agent1",
        problem=problem,
        comm_layer=comm,
        local_nodes=["a4", "a5"],
        owners=owners,
        algorithm="maxsum",
        initial_assignments={"a4": "blue", "a5": "green"},
    )
    base_agent.neighbour_assignments.update(INITIAL_NEIGHBORS)

    api = ClusterAgentAPI(base_agent)

    print(f"\n  Problem setup:")
    print(f"    Agent nodes: a4=blue, a5=green")
    print(f"    Neighbor assignments: {INITIAL_NEIGHBORS}")
    print(f"    Edges: a4-h1, a5-h4, a4-a5")
    print(f"    Domain: red, blue, green")

    # Check current state
    penalty, conflicts = api.get_current_penalty()
    result("Current penalty", {"penalty": penalty, "conflicts": conflicts})

    # Test Scenario A: h1=red, h4=red
    print(f"\n  Testing Scenario A: {SCENARIO_A}")
    sim_a = api.simulate_neighbor_change(neighbor_nodes=SCENARIO_A)
    result("Scenario A result", sim_a)
    best_a = api.get_best_response_to(neighbor_assignments=SCENARIO_A)
    result("Best response to Scenario A", best_a)

    # Test Scenario B: h1=red, h4=blue
    print(f"\n  Testing Scenario B: {SCENARIO_B}")
    sim_b = api.simulate_neighbor_change(neighbor_nodes=SCENARIO_B)
    result("Scenario B result", sim_b)
    best_b = api.get_best_response_to(neighbor_assignments=SCENARIO_B)
    result("Best response to Scenario B", best_b)

    # Evaluate
    check(penalty > 0, f"Current state has conflicts (penalty={penalty}) — negotiation needed")
    check(
        sim_a.get("new_penalty", 1) == 0 or best_a.get("penalty", 1) == 0,
        f"Scenario A (h1=red,h4=red) achievable with penalty=0"
    )
    check(
        sim_b.get("new_penalty", 1) == 0 or best_b.get("penalty", 1) == 0,
        f"Scenario B (h1=red,h4=blue) achievable with penalty=0"
    )

    return {
        "current_penalty": penalty,
        "scenario_a": {"sim": sim_a, "best": best_a},
        "scenario_b": {"sim": sim_b, "best": best_b},
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Test conditional offer handling in LLM_TOOL and LLM_REACT modes."
    )
    parser.add_argument(
        "--test",
        choices=["api", "speech", "tool_in", "tool_full", "react", "all"],
        default="all",
        help="Which test to run (default: all)"
    )
    args = parser.parse_args()

    print(textwrap.dedent(f"""
    {SEP}
    Conditional Offer Handling Test Suite
    {SEP}
    Test message: {TEST_MESSAGE!r}

    Scenarios to check:
      A: h1=red, h4=red
      B: h1=red, h4=blue

    Initial neighbor state (before message): {INITIAL_NEIGHBORS}
    Agent nodes: a4=blue, a5=green
    Graph edges: a4-h1, a5-h4, a4-a5
    """))

    run_all = args.test == "all"

    if run_all or args.test == "api":
        test_api_layer_both_scenarios()

    if run_all or args.test == "speech":
        test_speech_layer_parsing()

    if run_all or args.test == "tool_in":
        test_tool_inbound_translation()

    if run_all or args.test == "tool_full":
        test_tool_full_pipeline()

    if run_all or args.test == "react":
        test_react_full_pipeline()

    print(f"\n{SEP}")
    print("  Tests complete.")
    print(SEP)


if __name__ == "__main__":
    main()
