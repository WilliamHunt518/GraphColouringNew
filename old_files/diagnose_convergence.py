"""Diagnose convergence issues in RB mode."""

import re
import json

def parse_rb_message(text):
    """Extract RB payload from message."""
    if "[rb:" not in text:
        return None
    try:
        start = text.index("[rb:") + 4
        brace_count = 0
        end = start
        for i in range(start, len(text)):
            if text[i] == '{':
                brace_count += 1
            elif text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break
        payload = text[start:end]
        return json.loads(payload)
    except:
        return None

def main():
    print("=" * 70)
    print("CONVERGENCE DIAGNOSTIC")
    print("=" * 70)

    # Read communication log to get latest state
    with open("results/rb/communication_log.txt", "r") as f:
        lines = f.readlines()

    print("\n1. LATEST MESSAGES (last 10):")
    print("-" * 70)
    for line in lines[-10:]:
        print(line.strip())

    # Parse last few messages to understand state
    print("\n2. LATEST AGENT ASSIGNMENTS:")
    print("-" * 70)

    agent1_assignments = None
    agent2_assignments = None

    for line in reversed(lines):
        if "Agent1->Human" in line and "assignments" in line:
            data = parse_rb_message(line)
            if data and data.get("assignments"):
                if agent1_assignments is None:
                    agent1_assignments = data["assignments"]
                    print(f"Agent1: {agent1_assignments}")

        if "Agent2->Human" in line and "assignments" in line:
            data = parse_rb_message(line)
            if data and data.get("assignments"):
                if agent2_assignments is None:
                    agent2_assignments = data["assignments"]
                    print(f"Agent2: {agent2_assignments}")

        if agent1_assignments and agent2_assignments:
            break

    # Check iteration summary
    print("\n3. PENALTY OVER TIME:")
    print("-" * 70)
    with open("results/rb/iteration_summary.txt", "r") as f:
        summary_lines = f.readlines()

    penalties = []
    for line in summary_lines[-20:]:
        if "penalty=" in line:
            match = re.search(r"penalty=([\d.]+)", line)
            if match:
                penalties.append(float(match.group(1)))

    print(f"Last 20 penalties: {penalties}")
    print(f"Current penalty: {penalties[-1] if penalties else 'unknown'}")
    print(f"Stuck at same penalty: {len(set(penalties[-10:])) == 1 if len(penalties) >= 10 else False}")

    # Check Agent1 log for impossible conditions
    print("\n4. IMPOSSIBLE CONDITIONS:")
    print("-" * 70)
    try:
        with open("results/rb/Agent1_log.txt", "r") as f:
            agent1_log = f.read()

        impossible_matches = re.findall(r"Stored IMPOSSIBLE condition from Human: ([^\\n]+)", agent1_log)
        if impossible_matches:
            print(f"Agent1 knows these conditions are impossible:")
            for cond in impossible_matches:
                print(f"  - {cond}")
        else:
            print("No impossible conditions stored")

        # Check how many configs were filtered
        filtered_matches = re.findall(r"Filtered out (\d+) configs with impossible conditions", agent1_log)
        if filtered_matches:
            print(f"\nAgent1 filtered out: {filtered_matches[-1]} configurations")

        remaining_matches = re.findall(r"Remaining configs: (\d+)", agent1_log)
        if remaining_matches:
            print(f"Agent1 remaining configs: {remaining_matches[-1]}")
    except Exception as e:
        print(f"Error reading Agent1 log: {e}")

    # Check if agents think solution exists
    print("\n5. AGENT SEARCH RESULTS:")
    print("-" * 70)
    try:
        with open("results/rb/Agent1_log.txt", "r") as f:
            agent1_log = f.readlines()

        for line in reversed(agent1_log[-100:]):
            if "No beneficial configuration found" in line:
                print(f"Agent1: {line.strip()}")
                break
            if "Found zero-penalty configuration" in line:
                print(f"Agent1: {line.strip()}")
                break
    except:
        pass

    try:
        with open("results/rb/Agent2_log.txt", "r") as f:
            agent2_log = f.readlines()

        for line in reversed(agent2_log[-100:]):
            if "No beneficial configuration found" in line:
                print(f"Agent2: {line.strip()}")
                break
            if "Found zero-penalty configuration" in line:
                print(f"Agent2: {line.strip()}")
                break
    except:
        pass

    # Check ground truth
    print("\n6. GROUND TRUTH VALIDATION:")
    print("-" * 70)
    try:
        with open("results/rb/ground_truth_analysis.txt", "r") as f:
            gt_content = f.read()

        # Count valid configurations for Agent1
        agent1_section = gt_content.split("Agent1 - Exhaustive Boundary Analysis:")[1].split("Agent2")[0]
        valid_count_match = re.search(r"Valid Configurations \(penalty=0\): (\d+)", agent1_section)
        if valid_count_match:
            valid_count = int(valid_count_match.group(1))
            print(f"Agent1: Ground truth shows {valid_count} valid configurations (penalty=0)")

            # Check which ones involve h4=green
            h4_green_configs = re.findall(r"Boundary: \{[^}]*h4=green[^}]*\}", agent1_section)
            print(f"  - {len(h4_green_configs)} involve h4=green (marked impossible)")
            print(f"  - {valid_count - len(h4_green_configs)} remaining valid configs")

        # Check Agent2
        if "Agent2 - Exhaustive Boundary Analysis:" in gt_content:
            agent2_section = gt_content.split("Agent2 - Exhaustive Boundary Analysis:")[1]
            valid_count_match = re.search(r"Valid Configurations \(penalty=0\): (\d+)", agent2_section)
            if valid_count_match:
                print(f"Agent2: Ground truth shows {valid_count_match.group(1)} valid configurations")
    except Exception as e:
        print(f"Error reading ground truth: {e}")

    print("\n" + "=" * 70)
    print("DIAGNOSIS COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()
