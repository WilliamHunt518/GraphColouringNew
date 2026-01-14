"""Automated testing for agent-only simulations.

This script runs 3-agent (no human) simulations across different communication
modes (RB, LLM_U, LLM_RB, mixed modes) to validate and compare their performance.

Usage:
    python test_agent_modes.py --modes RB LLM_U --trials 3
    python test_agent_modes.py --modes LLM_RB --trials 5 --output-dir ./my_results
"""

import argparse
import json
import datetime
import sys
from pathlib import Path
from typing import Dict, List, Any


def create_test_config(mode: str) -> Dict[str, Any]:
    """Create a 3-agent test configuration for the specified mode.

    Parameters
    ----------
    mode : str
        Communication mode: "RB", "LLM_U", "LLM_RB", or "MIXED_RB_U"

    Returns
    -------
    dict
        Configuration dictionary for run_clustered_simulation
    """
    # Define 3 agents with 3 nodes each
    agent1_nodes = ["a1", "a2", "a3"]
    agent2_nodes = ["b1", "b2", "b3"]
    agent3_nodes = ["c1", "c2", "c3"]

    clusters = {
        "Agent1": agent1_nodes,
        "Agent2": agent2_nodes,
        "Agent3": agent3_nodes,
    }

    # Create internal edges (cycles within each cluster)
    adjacency = {
        # Agent1 cluster: a1-a2-a3-a1 cycle
        "a1": ["a2", "a3"],
        "a2": ["a1", "a3"],
        "a3": ["a1", "a2"],
        # Agent2 cluster: b1-b2-b3-b1 cycle
        "b1": ["b2", "b3"],
        "b2": ["b1", "b3"],
        "b3": ["b1", "b2"],
        # Agent3 cluster: c1-c2-c3-c1 cycle
        "c1": ["c2", "c3"],
        "c2": ["c1", "c3"],
        "c3": ["c1", "c2"],
    }

    # Add cross-cluster edges (creating boundary constraints)
    # Agent1 <-> Agent2
    adjacency["a2"].append("b1")
    adjacency["b1"].append("a2")

    # Agent2 <-> Agent3
    adjacency["b3"].append("c1")
    adjacency["c1"].append("b3")

    # Agent3 <-> Agent1 (closes the ring)
    adjacency["c2"].append("a3")
    adjacency["a3"].append("c2")

    # Assign ownership
    owners = {}
    for n in agent1_nodes:
        owners[n] = "Agent1"
    for n in agent2_nodes:
        owners[n] = "Agent2"
    for n in agent3_nodes:
        owners[n] = "Agent3"

    # Configure message types based on mode
    if mode == "RB":
        message_types = {"Agent1": "rule_based", "Agent2": "rule_based", "Agent3": "rule_based"}
    elif mode == "LLM_U":
        message_types = {"Agent1": "cost_list", "Agent2": "cost_list", "Agent3": "cost_list"}
    elif mode == "LLM_RB":
        message_types = {"Agent1": "llm_rb", "Agent2": "llm_rb", "Agent3": "llm_rb"}
    elif mode == "MIXED_RB_U":
        message_types = {"Agent1": "rule_based", "Agent2": "cost_list", "Agent3": "cost_list"}
    else:
        raise ValueError(f"Unknown mode: {mode}")

    return {
        "node_names": agent1_nodes + agent2_nodes + agent3_nodes,
        "clusters": clusters,
        "adjacency": adjacency,
        "owners": owners,
        "cluster_algorithms": {"Agent1": "greedy", "Agent2": "greedy", "Agent3": "greedy"},
        "cluster_message_types": message_types,
        "domain": ["red", "green", "blue"],
    }


def run_test(mode: str, trial: int, output_dir: Path) -> Dict[str, Any]:
    """Run a single test trial and return results.

    Parameters
    ----------
    mode : str
        Communication mode to test.
    trial : int
        Trial number (for reproducibility and logging).
    output_dir : Path
        Base directory for output files.

    Returns
    -------
    dict
        Test results including success status, timing, and metrics.
    """
    print(f"\nRunning: mode={mode}, trial={trial}")

    config = create_test_config(mode)
    trial_dir = output_dir / mode / f"trial_{trial}"
    trial_dir.mkdir(parents=True, exist_ok=True)

    start_time = datetime.datetime.now()

    try:
        # Import here to avoid issues if module not in path
        from cluster_simulation import run_clustered_simulation

        run_clustered_simulation(
            **config,
            max_iterations=50,
            interactive=False,
            manual_mode=True,  # Don't use LLM API in automated tests
            human_owners=[],  # No human participants
            use_ui=False,
            output_dir=str(trial_dir),
            convergence_k=3,
            stop_on_soft=True,
            stop_on_hard=False,
            counterfactual_utils=True,
            fixed_constraints=True,
            num_fixed_nodes=1,
        )

        elapsed = (datetime.datetime.now() - start_time).total_seconds()
        results = parse_results(trial_dir)
        results.update({
            "mode": mode,
            "trial": trial,
            "success": True,
            "elapsed_seconds": elapsed
        })

        print(f"[OK] Success in {elapsed:.2f}s, penalty={results.get('final_penalty', 'N/A')}, "
              f"iterations={results.get('iterations', 'N/A')}")
        return results

    except Exception as e:
        elapsed = (datetime.datetime.now() - start_time).total_seconds()
        print(f"[FAIL] Failed: {e}")
        return {
            "mode": mode,
            "trial": trial,
            "success": False,
            "elapsed_seconds": elapsed,
            "error": str(e)
        }


def parse_results(trial_dir: Path) -> Dict[str, Any]:
    """Parse simulation output files to extract metrics.

    Parameters
    ----------
    trial_dir : Path
        Directory containing simulation output files.

    Returns
    -------
    dict
        Parsed metrics including iterations, final penalty, message count, etc.
    """
    results = {}

    # Parse iteration summary
    summary_path = trial_dir / "iteration_summary.txt"
    if summary_path.exists():
        with open(summary_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        iter_lines = [l for l in lines if l.startswith("Iteration")]
        results["iterations"] = len(iter_lines)

        if iter_lines:
            import re
            # Extract penalty from last iteration
            m = re.search(r"penalty=([\d.]+)", iter_lines[-1])
            if m:
                results["final_penalty"] = float(m.group(1))

            # Check if converged
            if "streak=" in iter_lines[-1]:
                m = re.search(r"streak=(\d+)/(\d+)", iter_lines[-1])
                if m:
                    streak, target = int(m.group(1)), int(m.group(2))
                    results["converged"] = (streak >= target)

    # Parse communication log
    comm_path = trial_dir / "communication_log.txt"
    if comm_path.exists():
        with open(comm_path, "r", encoding="utf-8") as f:
            comm_lines = f.readlines()
        results["message_count"] = len([l for l in comm_lines if "->" in l])

    return results


def main():
    """Main entry point for automated testing."""
    parser = argparse.ArgumentParser(description="Run automated agent-only tests")
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["RB", "LLM_U", "LLM_RB"],
        choices=["RB", "LLM_U", "LLM_RB", "MIXED_RB_U"],
        help="Communication modes to test"
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=3,
        help="Number of trials per mode"
    )
    parser.add_argument(
        "--output-dir",
        default="./test_results",
        help="Output directory for results"
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    print("="*80)
    print("AUTOMATED AGENT TESTING")
    print("="*80)
    print(f"Modes: {', '.join(args.modes)}")
    print(f"Trials per mode: {args.trials}")
    print(f"Output directory: {output_dir}")
    print("="*80)

    all_results = []
    for mode in args.modes:
        for trial in range(1, args.trials + 1):
            result = run_test(mode, trial, output_dir)
            all_results.append(result)

    # Save detailed results
    summary_path = output_dir / "test_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    # Print summary table
    print(f"\n{'='*80}")
    print("TEST SUMMARY")
    print(f"{'='*80}")
    print(f"{'Mode':<15} {'Success':<12} {'Avg Penalty':<15} {'Avg Iter':<12} {'Avg Msgs':<12}")
    print(f"{'-'*80}")

    for mode in args.modes:
        mode_results = [r for r in all_results if r["mode"] == mode]
        success_count = len([r for r in mode_results if r.get("success")])
        total_count = len(mode_results)

        penalties = [r["final_penalty"] for r in mode_results if "final_penalty" in r]
        iterations = [r["iterations"] for r in mode_results if "iterations" in r]
        messages = [r["message_count"] for r in mode_results if "message_count" in r]

        avg_pen = sum(penalties) / len(penalties) if penalties else float("nan")
        avg_iter = sum(iterations) / len(iterations) if iterations else float("nan")
        avg_msgs = sum(messages) / len(messages) if messages else float("nan")

        print(f"{mode:<15} {success_count}/{total_count:<11} {avg_pen:<15.3f} "
              f"{avg_iter:<12.1f} {avg_msgs:<12.1f}")

    print(f"{'-'*80}")
    print(f"\nDetailed results saved to: {summary_path}")
    print(f"Per-trial outputs in: {output_dir}")

    # Return exit code based on success
    failed_count = len([r for r in all_results if not r.get("success")])
    if failed_count > 0:
        print(f"\n[WARNING] {failed_count} test(s) failed")
        sys.exit(1)
    else:
        print(f"\n[SUCCESS] All {len(all_results)} test(s) passed")
        sys.exit(0)


if __name__ == "__main__":
    main()
