"""Master Test Runner - Execute all agent tests and generate comprehensive analysis.

This script:
1. Runs all-agent tests (3 agents, no human)
2. Runs human-emulator tests (2 agents + emulated human)
3. Compares results across all communication modes
4. Generates detailed analysis report with recommendations
"""

import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime


def run_all_agent_tests():
    """Run the 3-agent (no human) test suite."""
    print("\n" + "="*80)
    print("PHASE 1: ALL-AGENT TESTS (3 agents, no human)")
    print("="*80 + "\n")

    cmd = [
        sys.executable,
        "test_agent_modes.py",
        "--modes", "RB", "LLM_U",  # Start with these two modes
        "--trials", "2",
        "--output-dir", "./test_results/all_agents"
    ]

    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


def run_comprehensive_tests():
    """Run the comprehensive test suite with human emulator."""
    print("\n" + "="*80)
    print("PHASE 2: COMPREHENSIVE TESTS (2 agents + human emulator)")
    print("="*80 + "\n")

    cmd = [
        sys.executable,
        "tests/comprehensive_agent_test.py",
        "--modes", "RB", "LLM_U", "LLM_C",  # Test all main modes
        "--trials", "2",
        "--output-dir", "./test_results/comprehensive",
        "--use-emulator"
    ]

    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


def generate_master_report():
    """Generate master analysis report combining all test results."""
    print("\n" + "="*80)
    print("GENERATING MASTER ANALYSIS REPORT")
    print("="*80 + "\n")

    report_path = Path("test_results/MASTER_ANALYSIS.md")
    report_path.parent.mkdir(exist_ok=True)

    # Load results from both test suites
    all_agent_results = Path("test_results/all_agents/test_summary.json")
    comprehensive_results = Path("test_results/comprehensive/test_summary.json")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Master Agent Testing Analysis Report\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("## Executive Summary\n\n")
        f.write("This report combines results from two complementary test suites:\n\n")
        f.write("1. **All-Agent Tests**: 3 agents negotiating without human intervention\n")
        f.write("2. **Comprehensive Tests**: 2 agents + human emulator with detailed behavior analysis\n\n")

        # Load and summarize all-agent results
        if all_agent_results.exists():
            with open(all_agent_results, "r") as af:
                all_agent_data = json.load(af)

            f.write("### All-Agent Test Results\n\n")
            f.write("| Mode | Success Rate | Avg Penalty | Avg Iterations | Avg Messages |\n")
            f.write("|------|-------------|-------------|----------------|-------------|\n")

            modes = sorted(set(r["mode"] for r in all_agent_data))
            for mode in modes:
                mode_results = [r for r in all_agent_data if r["mode"] == mode]
                success_count = len([r for r in mode_results if r.get("success")])
                successful = [r for r in mode_results if r.get("success")]

                if successful:
                    avg_penalty = sum(r.get("final_penalty", 0) for r in successful) / len(successful)
                    avg_iter = sum(r.get("iterations", 0) for r in successful) / len(successful)
                    avg_msgs = sum(r.get("message_count", 0) for r in successful) / len(successful)

                    f.write(f"| {mode} | {success_count}/{len(mode_results)} | {avg_penalty:.2f} | {avg_iter:.1f} | {avg_msgs:.1f} |\n")
                else:
                    f.write(f"| {mode} | 0/{len(mode_results)} | N/A | N/A | N/A |\n")

            f.write("\n")

        # Load and summarize comprehensive results
        if comprehensive_results.exists():
            with open(comprehensive_results, "r") as cf:
                comprehensive_data = json.load(cf)

            f.write("### Comprehensive Test Results (with Human Emulator)\n\n")
            f.write("| Mode | Success Rate | Avg Penalty | Quality Score | Converged |\n")
            f.write("|------|-------------|-------------|---------------|----------|\n")

            modes = sorted(set(r["mode"] for r in comprehensive_data))
            for mode in modes:
                mode_results = [r for r in comprehensive_data if r["mode"] == mode]
                success_count = len([r for r in mode_results if r.get("success")])
                successful = [r for r in mode_results if r.get("success")]

                if successful:
                    avg_penalty = sum(r.get("final_penalty", 0) for r in successful) / len(successful)
                    avg_quality = sum(r.get("message_quality", {}).get("quality_score", 0) for r in successful) / len(successful)
                    converged = sum(1 for r in successful if r.get("convergence", {}).get("converged", False))

                    f.write(f"| {mode} | {success_count}/{len(mode_results)} | {avg_penalty:.2f} | {avg_quality:.1f}/100 | {converged}/{len(successful)} |\n")
                else:
                    f.write(f"| {mode} | 0/{len(mode_results)} | N/A | N/A | N/A |\n")

            f.write("\n")

        # Cross-test analysis
        f.write("## Cross-Test Analysis\n\n")

        if all_agent_results.exists() and comprehensive_results.exists():
            with open(all_agent_results, "r") as af:
                all_agent_data = json.load(af)
            with open(comprehensive_results, "r") as cf:
                comprehensive_data = json.load(cf)

            # Compare modes present in both
            all_agent_modes = set(r["mode"] for r in all_agent_data if r.get("success"))
            comprehensive_modes = set(r["mode"] for r in comprehensive_data if r.get("success"))
            common_modes = all_agent_modes & comprehensive_modes

            if common_modes:
                f.write("### Mode Comparison Across Test Types\n\n")

                for mode in sorted(common_modes):
                    aa_results = [r for r in all_agent_data if r["mode"] == mode and r.get("success")]
                    comp_results = [r for r in comprehensive_data if r["mode"] == mode and r.get("success")]

                    aa_avg_penalty = sum(r.get("final_penalty", 0) for r in aa_results) / len(aa_results) if aa_results else float('inf')
                    comp_avg_penalty = sum(r.get("final_penalty", 0) for r in comp_results) / len(comp_results) if comp_results else float('inf')

                    aa_avg_iter = sum(r.get("iterations", 0) for r in aa_results) / len(aa_results) if aa_results else 0
                    comp_avg_iter = sum(r.get("iterations", 0) for r in comp_results) / len(comp_results) if comp_results else 0

                    f.write(f"**{mode}:**\n")
                    f.write(f"- All-agent: penalty={aa_avg_penalty:.2f}, iterations={aa_avg_iter:.1f}\n")
                    f.write(f"- With emulator: penalty={comp_avg_penalty:.2f}, iterations={comp_avg_iter:.1f}\n")

                    if comp_avg_penalty < aa_avg_penalty:
                        f.write(f"- ✓ Human emulator improves outcomes (penalty reduced by {aa_avg_penalty - comp_avg_penalty:.2f})\n")
                    elif comp_avg_penalty > aa_avg_penalty:
                        f.write(f"- ⚠ Human emulator worsens outcomes (penalty increased by {comp_avg_penalty - aa_avg_penalty:.2f})\n")
                    else:
                        f.write(f"- = Similar outcomes with/without human\n")

                    f.write("\n")

        # Key findings
        f.write("## Key Findings\n\n")

        if comprehensive_results.exists():
            with open(comprehensive_results, "r") as cf:
                comprehensive_data = json.load(cf)

            successful = [r for r in comprehensive_data if r.get("success")]

            if successful:
                # Find modes with quality issues
                modes_with_issues = []

                for mode in set(r["mode"] for r in successful):
                    mode_results = [r for r in successful if r["mode"] == mode]
                    total_hallucinations = sum(r.get("message_quality", {}).get("hallucination_indicators", 0) for r in mode_results)
                    total_messages = sum(r.get("message_quality", {}).get("total_messages", 1) for r in mode_results)

                    if total_messages > 0 and (total_hallucinations / total_messages) > 0.1:
                        modes_with_issues.append((mode, "hallucination", (total_hallucinations / total_messages) * 100))

                    total_repetitions = sum(r.get("message_quality", {}).get("repetition_count", 0) for r in mode_results)
                    if total_repetitions > 5:
                        modes_with_issues.append((mode, "repetition", total_repetitions))

                if modes_with_issues:
                    f.write("### Critical Issues Detected\n\n")
                    for mode, issue_type, severity in modes_with_issues:
                        if issue_type == "hallucination":
                            f.write(f"- **{mode}**: Hallucination rate {severity:.1f}% (agents claim changes that don't match reality)\n")
                        elif issue_type == "repetition":
                            f.write(f"- **{mode}**: {int(severity)} message repetitions detected\n")
                    f.write("\n")

        # Recommendations
        f.write("## Recommendations\n\n")

        f.write("### High Priority\n\n")
        f.write("1. **Fix message generation timing** (especially for LLM_U and LLM_C)\n")
        f.write("   - Ensure messages reflect FINAL assignments after all optimizations\n")
        f.write("   - Add verification step: compare claimed changes to actual state\n")
        f.write("   - Log warnings when discrepancies detected\n\n")

        f.write("2. **Improve message clarity** (especially for LLM_U)\n")
        f.write("   - Use explicit numbered proposals with clear if-then structure\n")
        f.write("   - Always include current state in proposals (not just alternatives)\n")
        f.write("   - Avoid vague language ('all is fine', 'looks good')\n\n")

        f.write("3. **Enhance constraint communication** (especially for LLM_C)\n")
        f.write("   - Enumerate complete valid configurations, not just per-node constraints\n")
        f.write("   - Limit to top 5-10 options to avoid overwhelming human\n")
        f.write("   - Include rationale for why these configurations work\n\n")

        f.write("### Medium Priority\n\n")
        f.write("4. **Add message deduplication**\n")
        f.write("   - Track recent messages and avoid sending identical content\n")
        f.write("   - Only send new message if state has meaningfully changed\n\n")

        f.write("5. **Improve convergence detection**\n")
        f.write("   - Reset satisfaction when boundary nodes change\n")
        f.write("   - Add oscillation detection (same penalty values repeating)\n")
        f.write("   - Implement timeout to prevent infinite loops\n\n")

        f.write("6. **Enhance LLM prompts**\n")
        f.write("   - Provide more explicit format examples\n")
        f.write("   - Emphasize numerical precision over natural language fluency\n")
        f.write("   - Include negative examples (what NOT to say)\n\n")

        # Detailed logs reference
        f.write("\n## Detailed Results\n\n")
        f.write("For detailed per-trial results, see:\n\n")
        f.write("- All-agent tests: `test_results/all_agents/`\n")
        f.write("- Comprehensive tests: `test_results/comprehensive/`\n")
        f.write("- Comprehensive report: `test_results/comprehensive/TEST_REPORT.md`\n\n")

        # Testing methodology
        f.write("## Testing Methodology\n\n")
        f.write("### All-Agent Tests\n")
        f.write("- Configuration: 3 agents (Agent1, Agent2, Agent3)\n")
        f.write("- Topology: Ring structure with cross-cluster edges\n")
        f.write("- Goal: Validate agent-to-agent negotiation without human intervention\n\n")

        f.write("### Comprehensive Tests\n")
        f.write("- Configuration: 2 agents + human emulator\n")
        f.write("- Topology: Star-like structure (human has more connections)\n")
        f.write("- Goal: Validate agent-human interaction with behavior analysis\n")
        f.write("- Human emulator:\n")
        f.write("  - Accepts suggestions with 60% probability\n")
        f.write("  - Imposes constraints with 30% probability\n")
        f.write("  - Asks questions with 20% probability\n")
        f.write("  - Makes random changes with 30% probability\n")
        f.write("  - Maximum 30 turns before marking satisfied\n\n")

    print(f"✓ Master report generated: {report_path}")


def main():
    """Run all test suites and generate master report."""
    print("="*80)
    print("MASTER TEST RUNNER - COMPREHENSIVE AGENT EVALUATION")
    print("="*80)
    print("\nThis will run:")
    print("1. All-agent tests (3 agents, no human)")
    print("2. Comprehensive tests (2 agents + human emulator)")
    print("3. Generate master analysis report")
    print("\nEstimated time: 5-10 minutes")
    print("="*80)

    input("\nPress Enter to start tests...")

    success = True

    # Run all-agent tests
    try:
        if not run_all_agent_tests():
            print("\n⚠ All-agent tests had failures")
            success = False
    except Exception as e:
        print(f"\n✗ All-agent tests failed: {e}")
        success = False

    # Run comprehensive tests
    try:
        if not run_comprehensive_tests():
            print("\n⚠ Comprehensive tests had failures")
            success = False
    except Exception as e:
        print(f"\n✗ Comprehensive tests failed: {e}")
        success = False

    # Generate master report
    try:
        generate_master_report()
    except Exception as e:
        print(f"\n✗ Failed to generate master report: {e}")
        success = False

    # Final summary
    print("\n" + "="*80)
    print("TESTING COMPLETE")
    print("="*80)

    if success:
        print("\n✓ All tests completed successfully")
        print("\nKey outputs:")
        print("- Master report: test_results/MASTER_ANALYSIS.md")
        print("- Comprehensive report: test_results/comprehensive/TEST_REPORT.md")
        print("- All results: test_results/")
        sys.exit(0)
    else:
        print("\n⚠ Some tests failed - review outputs for details")
        sys.exit(1)


if __name__ == "__main__":
    main()
