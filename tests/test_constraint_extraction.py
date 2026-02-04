import re

text = "I have to make h1 red. Is this something you'll be able to plan around?"

print("Testing constraint extraction patterns on:")
print(f"  '{text}'")
print()

# Updated requirement patterns from cluster_agent.py (line ~2603)
requirement_patterns = [
    r"\b(\w+)\s+(?:must|has to|needs to)\s+be\s+(red|green|blue)\b",
    r"\b(?:must|have to|need to)\s+(?:make|set|keep)\s+(\w+)\s+(red|green|blue)\b",
]

print("Pattern 1: node + must/has to/needs to + be + color")
pattern = re.compile(requirement_patterns[0], re.IGNORECASE)
for match in pattern.finditer(text):
    print(f"  Match: {match.groups()}")
    print(f"  Node: {match.group(1)}, Color: {match.group(2)}")

print()
print("Pattern 2: must/have to/need to + make/set/keep + node + color")
pattern = re.compile(requirement_patterns[1], re.IGNORECASE)
for match in pattern.finditer(text):
    print(f"  Match: {match.groups()}")
    print(f"  Node: {match.group(1)}, Color: {match.group(2)}")

print()
if not any(re.search(p, text, re.IGNORECASE) for p in requirement_patterns):
    print("[FAIL] NO PATTERNS MATCHED!")
else:
    print("[OK] At least one pattern matched!")
