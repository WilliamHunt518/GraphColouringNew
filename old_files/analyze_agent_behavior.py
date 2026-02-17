#!/usr/bin/env python3
"""
Analyze the most recent agent log to show the disconnect between
what the agent computes and what it says to the human.
"""

def analyze_log(log_path):
    """Extract key information from agent log."""

    with open(log_path, 'r') as f:
        lines = f.readlines()

    print("=" * 80)
    print("AGENT BEHAVIOR ANALYSIS")
    print("=" * 80)
    print()

    # Find the turn where human says "h1 may need to be red"
    for i, line in enumerate(lines):
        if "h1 may need to be red" in line.lower():
            print(f"FOUND AT LINE {i+1}: Human says 'h1 may need to be red. Can you plan around this?'")
            print()

            # Show what the agent computed
            print("WHAT THE AGENT COMPUTED:")
            print("-" * 80)

            # Look ahead for the constraint computation
            for j in range(i, min(i+100, len(lines))):
                line_content = lines[j]

                if "Computing valid boundary configs with constraints:" in line_content:
                    print(f"Line {j+1}: {line_content.strip()}")

                if "Config {'h1': 'red'" in line_content:
                    print(f"Line {j+1}: {line_content.strip()}")

                if "Computed 4 valid boundary configurations" in line_content or "Computed 0 valid boundary configurations" in line_content:
                    print(f"Line {j+1}: {line_content.strip()}")
                    print()
                    break

            # Now show what the agent SAID
            print("WHAT THE AGENT SAID TO HUMAN:")
            print("-" * 80)

            for j in range(i, min(i+100, len(lines))):
                line_content = lines[j]

                if "Sent message to Human:" in line_content:
                    # Extract just the message text
                    msg_start = line_content.find("Sent message to Human:") + len("Sent message to Human:")
                    message = line_content[msg_start:].strip()
                    print(f"Line {j+1}:")
                    print(f"  {message}")
                    print()
                    break

            print("=" * 80)
            print("THE PROBLEM:")
            print("=" * 80)
            print()
            print("1. Agent computed with constraints: {}")
            print("   (EMPTY - not using h1=red as a constraint!)")
            print()
            print("2. Agent tested ALL 9 combinations including h1=green, h1=blue")
            print()
            print("3. Agent found 4 valid configs (all with h1=green or h1=blue)")
            print()
            print("4. Agent suggested h1=green or h1=blue to human")
            print()
            print("5. Human gets frustrated: 'h1 HAS TO BE RED!'")
            print()
            print("=" * 80)
            print("WHAT SHOULD HAVE HAPPENED:")
            print("=" * 80)
            print()
            print("1. Agent detects hypothetical query: 'h1 may need to be red'")
            print()
            print("2. Agent treats h1=red as temporary constraint")
            print()
            print("3. Agent tests ONLY: h1=red with h4=red/green/blue")
            print()
            print("4. Agent finds ALL fail (penalty > 0)")
            print()
            print("5. Agent responds:")
            print("   'With h1=red, I tested all h4 values. None work.")
            print("    All gave penalty > 0. For a solution, h1 would need")
            print("    to be green or blue instead.'")
            print()
            break

if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Find most recent log
    log_path = Path(r"E:\Files\PhD-Main\GC-New\GIT_LOCAL_ROOT\GraphColouringNew\results\llm_api\Agent1_log.txt")

    if not log_path.exists():
        print(f"ERROR: Log file not found at {log_path}")
        sys.exit(1)

    analyze_log(log_path)
