"""Simple standalone test runner for evaluating agent modes."""

import sys
from pathlib import Path
from datetime import datetime

# Import project modules
from cluster_simulation import run_clustered_simulation


def test_mode(mode_name: str, output_subdir: str):
    """Test a single communication mode.

    Parameters
    ----------
    mode_name : str
        One of: "RB", "LLM_U", "LLM_C", "LLM_F"
    output_subdir : str
        Subdirectory name for outputs
    """
    print(f"\n{'='*80}")
    print(f"Testing Mode: {mode_name}")
    print(f"{'='*80}\n")

    # Define simple 3-agent configuration
    agent1_nodes = ["a1", "a2", "a3"]
    agent2_nodes = ["b1", "b2", "b3"]
    agent3_nodes = ["c1", "c2", "c3"]

    clusters = {
        "Agent1": agent1_nodes,
        "Agent2": agent2_nodes,
        "Agent3": agent3_nodes,
    }

    # Create adjacency (fully connected clusters + some cross-cluster edges)
    adjacency = {
        # Agent1 internal
        "a1": ["a2", "a3"],
        "a2": ["a1", "a3"],
        "a3": ["a1", "a2"],
        # Agent2 internal
        "b1": ["b2", "b3"],
        "b2": ["b1", "b3"],
        "b3": ["b1", "b2"],
        # Agent3 internal
        "c1": ["c2", "c3"],
        "c2": ["c1", "c3"],
        "c3": ["c1", "c2"],
    }

    # Add cross-cluster edges
    adjacency["a2"].append("b1")
    adjacency["b1"].append("a2")
    adjacency["b3"].append("c1")
    adjacency["c1"].append("b3")
    adjacency["c2"].append("a3")
    adjacency["a3"].append("c2")

    # Ownership
    owners = {}
    for n in agent1_nodes:
        owners[n] = "Agent1"
    for n in agent2_nodes:
        owners[n] = "Agent2"
    for n in agent3_nodes:
        owners[n] = "Agent3"

    # Configure message types
    if mode_name == "RB":
        message_types = {"Agent1": "rule_based", "Agent2": "rule_based", "Agent3": "rule_based"}
    elif mode_name == "LLM_U":
        message_types = {"Agent1": "cost_list", "Agent2": "cost_list", "Agent3": "cost_list"}
    elif mode_name == "LLM_C":
        message_types = {"Agent1": "constraints", "Agent2": "constraints", "Agent3": "constraints"}
    elif mode_name == "LLM_F":
        message_types = {"Agent1": "free_text", "Agent2": "free_text", "Agent3": "free_text"}
    else:
        raise ValueError(f"Unknown mode: {mode_name}")

    output_dir = f"test_results/{output_subdir}/{mode_name}"
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    start_time = datetime.now()

    try:
        print(f"Starting simulation...")
        print(f"Output directory: {output_dir}")

        run_clustered_simulation(
            node_names=agent1_nodes + agent2_nodes + agent3_nodes,
            clusters=clusters,
            adjacency=adjacency,
            owners=owners,
            cluster_algorithms={"Agent1": "greedy", "Agent2": "greedy", "Agent3": "greedy"},
            cluster_message_types=message_types,
            domain=["red", "green", "blue"],
            max_iterations=20,
            interactive=False,
            manual_mode=False,  # Use actual LLM calls for LLM modes
            human_owners=[],  # No human
            use_ui=False,
            output_dir=output_dir,
            convergence_k=3,
            stop_on_soft=True,
            stop_on_hard=False,
            counterfactual_utils=True,
            fixed_constraints=False,  # Don't fix any nodes
        )

        elapsed = (datetime.now() - start_time).total_seconds()

        # Parse results
        results = parse_results(Path(output_dir))
        results["mode"] = mode_name
        results["elapsed_seconds"] = elapsed

        print(f"\n[SUCCESS]")
        print(f"  Time: {elapsed:.2f}s")
        print(f"  Final Penalty: {results.get('final_penalty', 'N/A')}")
        print(f"  Iterations: {results.get('iterations', 'N/A')}")
        print(f"  Messages: {results.get('message_count', 'N/A')}")

        return results

    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\n[FAILED]: {e}")
        import traceback
        traceback.print_exc()

        return {
            "mode": mode_name,
            "success": False,
            "elapsed_seconds": elapsed,
            "error": str(e)
        }


def parse_results(output_dir: Path):
    """Parse simulation results from output files."""
    import re

    results = {"success": True}

    # Parse iteration summary
    summary_file = output_dir / "iteration_summary.txt"
    if summary_file.exists():
        with open(summary_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        iter_lines = [l for l in lines if l.startswith("Iteration")]
        results["iterations"] = len(iter_lines)

        if iter_lines:
            # Extract penalty from last iteration
            match = re.search(r"penalty=([\d.]+)", iter_lines[-1])
            if match:
                results["final_penalty"] = float(match.group(1))

    # Parse communication log
    comm_file = output_dir / "communication_log.txt"
    if comm_file.exists():
        with open(comm_file, "r", encoding="utf-8") as f:
            comm_lines = f.readlines()
        results["message_count"] = len([l for l in comm_lines if "->" in l])

    return results


def main():
    """Run simple tests for each mode."""
    import argparse

    parser = argparse.ArgumentParser(description="Simple agent testing")
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["RB"],
        choices=["RB", "LLM_U", "LLM_C", "LLM_F"],
        help="Modes to test"
    )
    args = parser.parse_args()

    print("="*80)
    print("SIMPLE AGENT TESTING")
    print("="*80)
    print(f"Modes: {', '.join(args.modes)}")
    print("="*80)

    all_results = []
    for mode in args.modes:
        result = test_mode(mode, "simple")
        all_results.append(result)

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    for result in all_results:
        mode = result["mode"]
        if result.get("success"):
            print(f"{mode}: SUCCESS - penalty={result.get('final_penalty', 'N/A')}, "
                  f"iterations={result.get('iterations', 'N/A')}")
        else:
            print(f"{mode}: FAILED - {result.get('error', 'Unknown error')}")


if __name__ == "__main__":
    main()
