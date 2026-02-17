"""Check what the human's current assignment is."""

import re

# Read iteration summary to find final state
with open("results/rb/iteration_summary.txt", "r") as f:
    lines = f.readlines()

print("=== CHECKING HUMAN STATE ===\n")

# Find the last few iterations with full state
for line in reversed(lines[-50:]):
    if "penalty=" in line:
        print(line.strip())
        # Try to extract more info if available

# Check ground truth for what valid configs exist WITHOUT h4=green
print("\n=== VALID CONFIGS (excluding h4=green) ===\n")

with open("results/rb/ground_truth_analysis.txt", "r") as f:
    gt = f.read()

# Extract Agent1's valid configs
agent1_section = gt.split("VALID CONFIGURATIONS:")[1].split("INVALID CONFIGURATIONS")[0]

configs = re.findall(r"\d+\.\s+Boundary: \{([^}]+)\} ->", agent1_section)

print("According to ground truth, Agent1 can achieve penalty=0 with:")
for i, config in enumerate(configs, 1):
    if "h4=green" not in config:
        print(f"  {i}. {config}")

print("\n=== CHECKING IF HUMAN CAN SATISFY ANY OF THESE ===\n")

# The problem: we need to know what h1, h2, h3, h4, h5 currently are
# Let me check if there are any status messages showing human state

print("Checking communication log for human assignments...")
with open("results/rb/communication_log.txt", "r") as f:
    comm_lines = f.readlines()

# Look for any messages from Human that might show their state
human_messages = [line for line in comm_lines if "Human->" in line and "rb:" in line]

if human_messages:
    print(f"\nFound {len(human_messages)} messages from Human")
    for msg in human_messages[-5:]:
        print(msg.strip())
else:
    print("\nNo RB messages from Human found (only config announcements)")

print("\n=== DIAGNOSIS ===\n")

print("The graph IS solvable (4 valid configs remain after filtering h4=green)")
print("But agents report 'best penalty=10.0', meaning they can't find penalty=0")
print("\nPossible reasons:")
print("1. Human's current h1/h4 don't match any of the 4 remaining valid configs")
print("2. Human changed colors after marking h4=green impossible")
print("3. Agents have stale neighbor information")
print("4. There's a coordination issue between Agent1 and Agent2")
print("\nTo fix: Try changing h1 or h4 to match one of the valid configs above")
print("and click 'Pass' to let agents re-evaluate.")
