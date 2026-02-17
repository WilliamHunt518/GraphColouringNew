"""Test report extraction from actual messages."""

import re
import ast


def extract_report(text: str):
    """Extract report the same way UI does."""
    report = {}
    try:
        m = re.search(r"\[report:\s*(\{.*?\})\s*\]", text)
        if m:
            rep = ast.literal_eval(m.group(1))
            if isinstance(rep, dict):
                report.update(rep)

        m2 = re.search(r"\[mapping:\s*(\{.*\})\s*\]", text)
        if m2:
            mp = ast.literal_eval(m2.group(1))
            if isinstance(mp, dict):
                rep2 = mp.get("report") or mp.get("data", {}).get("report")
                if isinstance(rep2, dict):
                    report.update(rep2)
    except Exception as e:
        print(f"Exception: {e}")
        report = {}

    return report


# Test with actual messages from the communication log
messages = [
    "Your current assignments are: a2=blue, a4=red, a5=blue. [report: {'a2': 'blue', 'a4': 'red', 'a5': 'blue'}] [mapping: {'type': 'announcement', 'data': {'assignments': {'a2': 'blue', 'a4': 'red', 'a5': 'blue'}}, 'report': {'a2': 'blue', 'a4': 'red', 'a5': 'blue'}}]",
    "Conflict detected with current assignment b2=red. Change b2 to another color to resolve it. [report: {'b2': 'red'}] [mapping: {'type': 'announcement', 'data': {'assignments': {'b2': 'red'}}, 'report': {'b2': 'red'}}]",
]

for i, msg in enumerate(messages, 1):
    print(f"\n=== Message {i} ===")
    print(f"Text: {msg[:80]}...")
    report = extract_report(msg)
    print(f"Extracted report: {report}")
    if report:
        print(f"[OK] SUCCESS: {len(report)} nodes extracted")
        for node, color in report.items():
            print(f"  {node} = {color}")
    else:
        print(f"[FAIL] No report extracted")
