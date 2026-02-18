import difflib
import sys

with open('temp_ui_old.py', 'r', encoding='utf-8', errors='replace') as f:
    old = f.readlines()
with open('ui/human_turn_ui.py', 'r', encoding='utf-8', errors='replace') as f:
    new = f.readlines()

diff = list(difflib.unified_diff(old, new, n=3, lineterm=''))
with open('ui_diff.txt', 'w', encoding='utf-8', errors='replace') as f:
    f.write(f'Total diff lines: {len(diff)}\n')
    f.write(''.join(diff))
print(f"Written {len(diff)} diff lines to ui_diff.txt")
