"""Comprehensive Agent Testing Suite with Behavior Analysis.

This test suite:
1. Tests all communication modes (RB, LLM_U, LLM_C, LLM_F)
2. Uses human emulator for realistic testing
3. Analyzes message quality (rambling, hallucinations, topic switching)
4. Tracks consensus achievement
5. Evaluates coloring quality
6. Generates detailed reports with recommendations
"""

import argparse
import json
import datetime
import sys
import re
from pathlib import Path
from typing import Dict, List, Any, Tuple
from collections import Counter

# Add parent directory to path to import project modules
sys.path.insert(0, str(Path(__file__).parent.parent))


def create_test_config(mode: str, use_emulator: bool = True) -> Dict[str, Any]:
    """Create a test configuration with optional human emulator.

    Parameters
    ----------
    mode : str
        Communication mode: "RB", "LLM_U", "LLM_C", "LLM_F"
    use_emulator : bool
        If True, replace one agent with human emulator

    Returns
    -------
    dict
        Configuration dictionary for run_clustered_simulation
    """
    # Define clusters
    agent1_nodes = ["a2", "a4", "a5"]
    human_nodes = ["h1", "h2", "h4", "h5"]
    agent2_nodes = ["b2"]

    clusters = {
        "Agent1": agent1_nodes,
        "Human": human_nodes,
        "Agent2": agent2_nodes,
    }

    # Create adjacency (matching the actual problem structure)
    adjacency = {
        # Agent1 internal edges
        "a2": ["a4", "a5"],
        "a4": ["a2", "a5"],
        "a5": ["a2", "a4"],
        # Human internal edges
        "h1": ["h2", "h4", "h5"],
        "h2": ["h1", "h5"],
        "h4": ["h1", "h5"],
        "h5": ["h1", "h2", "h4"],
        # Agent2 (single node)
        "b2": [],
    }

    # Add cross-cluster edges
    # Agent1 <-> Human
    adjacency["a2"].append("h1")
    adjacency["h1"].append("a2")
    adjacency["a4"].append("h4")
    adjacency["h4"].append("a4")
    adjacency["a5"].append("h1")
    adjacency["h1"].append("a5")

    # Agent2 <-> Human
    adjacency["b2"].append("h2")
    adjacency["h2"].append("b2")
    adjacency["b2"].append("h5")
    adjacency["h5"].append("b2")

    # Assign ownership
    owners = {}
    for n in agent1_nodes:
        owners[n] = "Agent1"
    for n in human_nodes:
        owners[n] = "Human"
    for n in agent2_nodes:
        owners[n] = "Agent2"

    # Configure message types based on mode
    if mode == "RB":
        message_types = {"Agent1": "rule_based", "Agent2": "rule_based", "Human": "rule_based"}
    elif mode == "LLM_U":
        message_types = {"Agent1": "cost_list", "Agent2": "cost_list", "Human": "cost_list"}
    elif mode == "LLM_C":
        message_types = {"Agent1": "constraints", "Agent2": "constraints", "Human": "constraints"}
    elif mode == "LLM_F":
        message_types = {"Agent1": "free_text", "Agent2": "free_text", "Human": "free_text"}
    else:
        raise ValueError(f"Unknown mode: {mode}")

    human_owners = ["Human"] if not use_emulator else []

    return {
        "node_names": agent1_nodes + human_nodes + agent2_nodes,
        "clusters": clusters,
        "adjacency": adjacency,
        "owners": owners,
        "cluster_algorithms": {"Agent1": "greedy", "Agent2": "greedy", "Human": "greedy"},
        "cluster_message_types": message_types,
        "domain": ["red", "green", "blue"],
        "human_owners": human_owners,
    }


def analyze_message_quality(comm_log_path: Path) -> Dict[str, Any]:
    """Analyze message quality for signs of rambling, hallucinations, topic switching.

    Parameters
    ----------
    comm_log_path : Path
        Path to communication_log.txt

    Returns
    -------
    dict
        Analysis results with quality metrics
    """
    if not comm_log_path.exists():
        return {"error": "No communication log found"}

    with open(comm_log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Parse messages
    messages = []
    for line in lines:
        if "->" in line:
            parts = line.strip().split("\t")
            if len(parts) >= 3:
                sender = parts[1].split("->")[0]
                receiver = parts[1].split("->")[1]
                text = "\t".join(parts[2:])
                messages.append({
                    "sender": sender,
                    "receiver": receiver,
                    "text": text,
                    "length": len(text)
                })

    if not messages:
        return {"error": "No messages found in log"}

    # Quality metrics
    analysis = {
        "total_messages": len(messages),
        "avg_message_length": sum(m["length"] for m in messages) / len(messages),
        "max_message_length": max(m["length"] for m in messages),
        "min_message_length": min(m["length"] for m in messages),
        "repetition_count": 0,
        "hallucination_indicators": 0,
        "topic_switches": 0,
        "clear_proposals": 0,
        "vague_statements": 0,
    }

    # Detect repetition (same message sent multiple times in a row)
    prev_text = None
    repetition_streak = 0
    for msg in messages:
        if msg["text"] == prev_text:
            repetition_streak += 1
        else:
            if repetition_streak >= 2:
                analysis["repetition_count"] += 1
            repetition_streak = 0
        prev_text = msg["text"]

    # Analyze each message for quality indicators
    for msg in messages:
        text = msg["text"].lower()

        # Check for hallucination indicators
        hallucination_patterns = [
            r"i changed .* to .* \[report:.*\]",  # Claimed change in report
            r"verification:.*=",  # Verification mismatch
            r"updated assignments.*to.*\[report:.*\]",  # Update claim
        ]
        for pattern in hallucination_patterns:
            if re.search(pattern, text):
                # Check if report matches claim
                report_match = re.search(r"\[report: \{([^}]+)\}\]", text)
                claim_match = re.search(r"(changed|set|updated).*?(\w+).*?(red|green|blue)", text)
                if report_match and claim_match:
                    report_str = report_match.group(1)
                    node_claimed = claim_match.group(2)
                    color_claimed = claim_match.group(3)
                    # Check mismatch
                    if f"'{node_claimed}': '{color_claimed}'" not in report_str:
                        analysis["hallucination_indicators"] += 1

        # Check for topic switches (mentions multiple unrelated things)
        topic_indicators = [
            "score", "penalty", "conflict", "constraint", "option", "configuration",
            "alternative", "proposal", "suggestion"
        ]
        topics_mentioned = sum(1 for topic in topic_indicators if topic in text)
        if topics_mentioned >= 4:
            analysis["topic_switches"] += 1

        # Check for clear proposals
        proposal_patterns = [
            r"if you set .* i can score \d+",
            r"\d+\. .*=.* → .*score \d+",
            r"\d+\. h\d+=\w+, h\d+=\w+",
            r"option \d+:",
        ]
        if any(re.search(p, text) for p in proposal_patterns):
            analysis["clear_proposals"] += 1

        # Check for vague statements
        vague_patterns = [
            r"i think",
            r"maybe",
            r"perhaps",
            r"all is fine",
            r"looks good",
            r"no changes",
        ]
        if any(re.search(p, text) for p in vague_patterns):
            analysis["vague_statements"] += 1

    # Calculate quality scores (0-100)
    if analysis["total_messages"] > 0:
        analysis["repetition_rate"] = (analysis["repetition_count"] / analysis["total_messages"]) * 100
        analysis["hallucination_rate"] = (analysis["hallucination_indicators"] / analysis["total_messages"]) * 100
        analysis["topic_switch_rate"] = (analysis["topic_switches"] / analysis["total_messages"]) * 100
        analysis["clarity_rate"] = (analysis["clear_proposals"] / analysis["total_messages"]) * 100
        analysis["vagueness_rate"] = (analysis["vague_statements"] / analysis["total_messages"]) * 100

        # Overall quality score (higher is better)
        analysis["quality_score"] = max(0, 100 - (
            analysis["repetition_rate"] * 0.3 +
            analysis["hallucination_rate"] * 0.4 +
            analysis["topic_switch_rate"] * 0.2 +
            analysis["vagueness_rate"] * 0.1
        ) + analysis["clarity_rate"] * 0.2)

    return analysis


def analyze_convergence_behavior(iteration_log_path: Path) -> Dict[str, Any]:
    """Analyze how agents behave during convergence.

    Parameters
    ----------
    iteration_log_path : Path
        Path to iteration_summary.txt

    Returns
    -------
    dict
        Convergence analysis
    """
    if not iteration_log_path.exists():
        return {"error": "No iteration log found"}

    with open(iteration_log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    iterations = []
    for line in lines:
        if line.startswith("Iteration"):
            # Parse: Iteration X: penalty=Y.Y, streak=Z/W
            match = re.search(r"Iteration (\d+):.*penalty=([\d.]+).*streak=(\d+)/(\d+)", line)
            if match:
                iterations.append({
                    "iteration": int(match.group(1)),
                    "penalty": float(match.group(2)),
                    "streak": int(match.group(3)),
                    "target_streak": int(match.group(4))
                })

    if not iterations:
        return {"error": "No iterations found"}

    analysis = {
        "total_iterations": len(iterations),
        "final_penalty": iterations[-1]["penalty"],
        "converged": iterations[-1]["streak"] >= iterations[-1]["target_streak"],
        "penalty_trajectory": [it["penalty"] for it in iterations],
        "improvements": 0,
        "regressions": 0,
        "oscillations": 0,
    }

    # Analyze trajectory
    for i in range(1, len(iterations)):
        prev_penalty = iterations[i-1]["penalty"]
        curr_penalty = iterations[i]["penalty"]

        if curr_penalty < prev_penalty:
            analysis["improvements"] += 1
        elif curr_penalty > prev_penalty:
            analysis["regressions"] += 1

    # Detect oscillations (same penalty values repeating)
    penalty_counts = Counter(analysis["penalty_trajectory"])
    analysis["oscillations"] = sum(1 for count in penalty_counts.values() if count >= 3)

    # Calculate convergence speed
    if analysis["converged"]:
        # Find first iteration where penalty reached zero
        for it in iterations:
            if it["penalty"] == 0.0:
                analysis["iterations_to_zero_penalty"] = it["iteration"]
                break

    return analysis


def run_test(mode: str, trial: int, output_dir: Path, use_emulator: bool = True) -> Dict[str, Any]:
    """Run a comprehensive test trial.

    Parameters
    ----------
    mode : str
        Communication mode to test
    trial : int
        Trial number
    output_dir : Path
        Base directory for output
    use_emulator : bool
        Whether to use human emulator

    Returns
    -------
    dict
        Test results with detailed analysis
    """
    print(f"\n{'='*80}")
    print(f"Running: mode={mode}, trial={trial}, emulator={use_emulator}")
    print(f"{'='*80}")

    config = create_test_config(mode, use_emulator)
    trial_dir = output_dir / mode / f"trial_{trial}"
    trial_dir.mkdir(parents=True, exist_ok=True)

    start_time = datetime.datetime.now()

    try:
        # Import here to avoid issues
        from cluster_simulation import run_clustered_simulation

        run_clustered_simulation(
            **config,
            max_iterations=30,
            interactive=False,
            human_owners=config["human_owners"],
            use_ui=False,
            output_dir=str(trial_dir),
            convergence_k=5,
            stop_on_soft=True,
            stop_on_hard=False,
            counterfactual_utils=True,
            fixed_constraints=False,  # Make it easier to solve
            llm_trace_file=str(trial_dir / "llm_trace.jsonl"),
        )

        elapsed = (datetime.datetime.now() - start_time).total_seconds()

        # Parse basic results
        results = parse_basic_results(trial_dir)

        # Analyze message quality
        comm_log = trial_dir / "communication_log.txt"
        message_analysis = analyze_message_quality(comm_log)

        # Analyze convergence behavior
        iter_log = trial_dir / "iteration_summary.txt"
        convergence_analysis = analyze_convergence_behavior(iter_log)

        # Combine results
        results.update({
            "mode": mode,
            "trial": trial,
            "success": True,
            "elapsed_seconds": elapsed,
            "message_quality": message_analysis,
            "convergence": convergence_analysis,
        })

        print(f"[SUCCESS]")
        print(f"  Time: {elapsed:.2f}s")
        print(f"  Final Penalty: {results.get('final_penalty', 'N/A')}")
        print(f"  Iterations: {results.get('iterations', 'N/A')}")
        print(f"  Converged: {convergence_analysis.get('converged', False)}")
        print(f"  Message Quality Score: {message_analysis.get('quality_score', 0):.1f}/100")

        return results

    except Exception as e:
        elapsed = (datetime.datetime.now() - start_time).total_seconds()
        print(f"[FAILED]: {e}")
        import traceback
        traceback.print_exc()

        return {
            "mode": mode,
            "trial": trial,
            "success": False,
            "elapsed_seconds": elapsed,
            "error": str(e)
        }


def parse_basic_results(trial_dir: Path) -> Dict[str, Any]:
    """Parse basic simulation metrics.

    Parameters
    ----------
    trial_dir : Path
        Directory containing output files

    Returns
    -------
    dict
        Basic metrics
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
            # Extract penalty from last iteration
            m = re.search(r"penalty=([\d.]+)", iter_lines[-1])
            if m:
                results["final_penalty"] = float(m.group(1))

    # Parse communication log
    comm_path = trial_dir / "communication_log.txt"
    if comm_path.exists():
        with open(comm_path, "r", encoding="utf-8") as f:
            comm_lines = f.readlines()
        results["message_count"] = len([l for l in comm_lines if "->" in l])

    return results


def generate_report(all_results: List[Dict[str, Any]], output_dir: Path) -> None:
    """Generate comprehensive test report with recommendations.

    Parameters
    ----------
    all_results : list
        All test results
    output_dir : Path
        Output directory
    """
    report_path = output_dir / "TEST_REPORT.md"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Comprehensive Agent Testing Report\n\n")
        f.write(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # Summary table
        f.write("## Summary\n\n")
        f.write("| Mode | Success Rate | Avg Penalty | Avg Iterations | Quality Score | Converged |\n")
        f.write("|------|-------------|-------------|----------------|---------------|----------|\n")

        modes = sorted(set(r["mode"] for r in all_results))
        for mode in modes:
            mode_results = [r for r in all_results if r["mode"] == mode and r.get("success")]

            if not mode_results:
                f.write(f"| {mode} | 0% | N/A | N/A | N/A | N/A |\n")
                continue

            success_rate = (len(mode_results) / len([r for r in all_results if r["mode"] == mode])) * 100
            avg_penalty = sum(r.get("final_penalty", 0) for r in mode_results) / len(mode_results)
            avg_iterations = sum(r.get("iterations", 0) for r in mode_results) / len(mode_results)
            avg_quality = sum(r.get("message_quality", {}).get("quality_score", 0) for r in mode_results) / len(mode_results)
            converged_count = sum(1 for r in mode_results if r.get("convergence", {}).get("converged", False))

            f.write(f"| {mode} | {success_rate:.0f}% | {avg_penalty:.2f} | {avg_iterations:.1f} | {avg_quality:.1f}/100 | {converged_count}/{len(mode_results)} |\n")

        # Detailed analysis per mode
        f.write("\n## Detailed Analysis\n\n")

        for mode in modes:
            mode_results = [r for r in all_results if r["mode"] == mode and r.get("success")]

            if not mode_results:
                continue

            f.write(f"### {mode}\n\n")

            # Message quality issues
            f.write("**Message Quality Issues:**\n\n")
            hallucinations = sum(r.get("message_quality", {}).get("hallucination_indicators", 0) for r in mode_results)
            repetitions = sum(r.get("message_quality", {}).get("repetition_count", 0) for r in mode_results)
            topic_switches = sum(r.get("message_quality", {}).get("topic_switches", 0) for r in mode_results)
            vague_statements = sum(r.get("message_quality", {}).get("vague_statements", 0) for r in mode_results)
            clear_proposals = sum(r.get("message_quality", {}).get("clear_proposals", 0) for r in mode_results)

            f.write(f"- Hallucinations detected: {hallucinations}\n")
            f.write(f"- Message repetitions: {repetitions}\n")
            f.write(f"- Topic switches: {topic_switches}\n")
            f.write(f"- Vague statements: {vague_statements}\n")
            f.write(f"- Clear proposals: {clear_proposals}\n\n")

            # Convergence behavior
            f.write("**Convergence Behavior:**\n\n")
            avg_improvements = sum(r.get("convergence", {}).get("improvements", 0) for r in mode_results) / len(mode_results)
            avg_regressions = sum(r.get("convergence", {}).get("regressions", 0) for r in mode_results) / len(mode_results)
            avg_oscillations = sum(r.get("convergence", {}).get("oscillations", 0) for r in mode_results) / len(mode_results)

            f.write(f"- Avg improvements per run: {avg_improvements:.1f}\n")
            f.write(f"- Avg regressions per run: {avg_regressions:.1f}\n")
            f.write(f"- Avg oscillations per run: {avg_oscillations:.1f}\n\n")

        # Recommendations
        f.write("\n## Recommendations\n\n")

        # Find the worst performing mode
        mode_quality_scores = {}
        for mode in modes:
            mode_results = [r for r in all_results if r["mode"] == mode and r.get("success")]
            if mode_results:
                avg_quality = sum(r.get("message_quality", {}).get("quality_score", 0) for r in mode_results) / len(mode_results)
                mode_quality_scores[mode] = avg_quality

        if mode_quality_scores:
            worst_mode = min(mode_quality_scores, key=mode_quality_scores.get)
            best_mode = max(mode_quality_scores, key=mode_quality_scores.get)

            f.write(f"### Issues Identified\n\n")

            # Analyze worst mode
            worst_results = [r for r in all_results if r["mode"] == worst_mode and r.get("success")]
            if worst_results:
                total_hallucinations = sum(r.get("message_quality", {}).get("hallucination_indicators", 0) for r in worst_results)
                total_messages = sum(r.get("message_quality", {}).get("total_messages", 1) for r in worst_results)
                hallucination_rate = (total_hallucinations / total_messages) * 100 if total_messages > 0 else 0

                if hallucination_rate > 10:
                    f.write(f"1. **{worst_mode}: High hallucination rate ({hallucination_rate:.1f}%)**\n")
                    f.write("   - Agents claim color changes that don't match their reports\n")
                    f.write("   - Recommendation: Review message generation timing relative to snap-to-best\n")
                    f.write("   - Recommendation: Add verification step before message generation\n\n")

                total_repetitions = sum(r.get("message_quality", {}).get("repetition_count", 0) for r in worst_results)
                if total_repetitions > 5:
                    f.write(f"2. **{worst_mode}: Message repetition detected ({total_repetitions} instances)**\n")
                    f.write("   - Agents send identical messages repeatedly\n")
                    f.write("   - Recommendation: Add message history check to prevent duplicates\n")
                    f.write("   - Recommendation: Implement explicit state change detection\n\n")

                total_vague = sum(r.get("message_quality", {}).get("vague_statements", 0) for r in worst_results)
                vague_rate = (total_vague / total_messages) * 100 if total_messages > 0 else 0
                if vague_rate > 20:
                    f.write(f"3. **{worst_mode}: High vagueness rate ({vague_rate:.1f}%)**\n")
                    f.write("   - Messages contain vague statements like 'all is fine', 'looks good'\n")
                    f.write("   - Recommendation: Enforce structured message templates\n")
                    f.write("   - Recommendation: Require explicit numerical proposals\n\n")

            # Compare modes
            f.write(f"### Mode Comparison\n\n")
            f.write(f"- Best performing mode: **{best_mode}** (quality score: {mode_quality_scores[best_mode]:.1f}/100)\n")
            f.write(f"- Worst performing mode: **{worst_mode}** (quality score: {mode_quality_scores[worst_mode]:.1f}/100)\n\n")

            if "RB" in mode_quality_scores:
                f.write(f"- Rule-based (RB) baseline quality: {mode_quality_scores['RB']:.1f}/100\n")
                f.write(f"  - Use this as the minimum acceptable quality threshold\n\n")

        f.write("### General Recommendations\n\n")
        f.write("1. **Improve message consistency**: Ensure claimed changes match actual assignments\n")
        f.write("2. **Add structured templates**: Use explicit numerical proposals instead of vague language\n")
        f.write("3. **Prevent topic drift**: Keep messages focused on specific proposals or questions\n")
        f.write("4. **Enhance LLM prompts**: Provide clearer instructions on message format and content\n")
        f.write("5. **Add validation layer**: Check message claims against actual state before sending\n\n")

    print(f"\n{'='*80}")
    print(f"Report generated: {report_path}")
    print(f"{'='*80}\n")


def main():
    """Main entry point for comprehensive testing."""
    parser = argparse.ArgumentParser(description="Comprehensive agent testing with behavior analysis")
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["RB", "LLM_U", "LLM_C"],
        choices=["RB", "LLM_U", "LLM_C", "LLM_F"],
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
        default="./test_results_comprehensive",
        help="Output directory for results"
    )
    parser.add_argument(
        "--use-emulator",
        action="store_true",
        default=True,
        help="Use human emulator agent"
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("="*80)
    print("COMPREHENSIVE AGENT TESTING WITH BEHAVIOR ANALYSIS")
    print("="*80)
    print(f"Modes: {', '.join(args.modes)}")
    print(f"Trials per mode: {args.trials}")
    print(f"Output directory: {output_dir}")
    print(f"Human emulator: {args.use_emulator}")
    print("="*80)

    all_results = []
    for mode in args.modes:
        for trial in range(1, args.trials + 1):
            result = run_test(mode, trial, output_dir, args.use_emulator)
            all_results.append(result)

    # Save detailed results
    summary_path = output_dir / "test_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    # Generate comprehensive report
    generate_report(all_results, output_dir)

    # Print summary to console
    print(f"\n{'='*80}")
    print("TEST SUMMARY")
    print(f"{'='*80}")
    print(f"{'Mode':<10} {'Success':<10} {'Penalty':<10} {'Quality':<12} {'Converged':<12}")
    print(f"{'-'*80}")

    for mode in args.modes:
        mode_results = [r for r in all_results if r["mode"] == mode]
        success_count = len([r for r in mode_results if r.get("success")])
        successful = [r for r in mode_results if r.get("success")]

        if successful:
            avg_penalty = sum(r.get("final_penalty", 0) for r in successful) / len(successful)
            avg_quality = sum(r.get("message_quality", {}).get("quality_score", 0) for r in successful) / len(successful)
            converged = sum(1 for r in successful if r.get("convergence", {}).get("converged", False))

            print(f"{mode:<10} {success_count}/{len(mode_results):<9} {avg_penalty:<10.2f} {avg_quality:<12.1f} {converged}/{len(successful):<11}")
        else:
            print(f"{mode:<10} {success_count}/{len(mode_results):<9} {'N/A':<10} {'N/A':<12} {'N/A':<12}")

    print(f"{'-'*80}")
    print(f"\nDetailed results: {summary_path}")
    print(f"Full report: {output_dir / 'TEST_REPORT.md'}")

    # Return exit code
    failed_count = len([r for r in all_results if not r.get("success")])
    if failed_count > 0:
        print(f"\n[WARNING] {failed_count} test(s) failed")
        sys.exit(1)
    else:
        print(f"\n[OK] All {len(all_results)} test(s) passed")
        sys.exit(0)


if __name__ == "__main__":
    main()
