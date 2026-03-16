# Study Questions — All Sections

Edit the question text in each section below and return this file. Do **not** change the `id` values — they are used as keys in the data output.

---

## Tutorial Text

Shown once before the first condition begins.

```
TASK OVERVIEW
━━━━━━━━━━━━━
Your task is to colour every node in a graph using three colours
(red, green, blue) so that no two connected nodes share the same colour.

The graph is split into three regions:
  • YOUR cluster (centre) — you control these nodes directly
  • Agent 1's cluster (left side)  — managed automatically
  • Agent 2's cluster (right side) — managed automatically

Fixed nodes (shown with a darker/locked border) have pre-assigned colours
that cannot be changed.  These create the constraint structure for the puzzle.


HOW TO INTERACT
━━━━━━━━━━━━━━━
• Click a node in YOUR cluster to cycle its colour:
      grey → red → green → blue → grey …
• The constraint panel on the right updates in real time as you click
• Agent nodes colour themselves — you do not need to interact with them


READING THE CONSTRAINT PANEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The right-hand panel shows how your current colour choices interact with the
neighbouring clusters.  It tells you whether a valid (conflict-free) colouring
is still possible given your current choices, and may give more detail
depending on the condition.

Use this information to guide which colours you choose for your nodes.


FINISHING A CONDITION
━━━━━━━━━━━━━━━━━━━━━
• When you are satisfied with your colouring, simply close the experiment window
• A short questionnaire will follow before the next condition begins
• You can close at any point — there is no time limit


TIPS
━━━━
• You only colour YOUR nodes — agents handle their own clusters
• Every edge must connect nodes of DIFFERENT colours
• If you are stuck, try changing one node at a time and watch the panel update
• It is fine to close the window before finding a perfect solution
```

---

## Section 1 — Pre-Study Questionnaire

Shown once at the start, before any conditions.

| id | type | Question / Label | Options / Scale |
|----|------|-----------------|-----------------|
| `age` | text entry | Age | — |
| `gender` | text entry | Gender (optional) | — |
| `education` | radio | Highest level of education completed | Secondary / High school · Undergraduate degree · Postgraduate / Masters · PhD or higher · Prefer not to say |
| `puzzle_freq` | 7-pt Likert | How often do you engage with logic puzzles or strategy games? | 1 = Never … 7 = Daily |
| `cs_familiarity` | 7-pt Likert | How familiar are you with graph problems or constraint satisfaction? | 1 = Not at all … 7 = Expert |
| `ai_experience` | radio | Prior experience with AI collaboration or decision-support tools? | None · A little · Regularly · I work in AI/ML |
| `pre_comments` | open text | Any other comments before we start? (optional) | — |

---

## Section 2 — Inter-Condition Questionnaire

Shown after **each** condition (repeated for every condition the participant completes).

| id | type | Question / Label | Scale |
|----|------|-----------------|-------|
| `info_clarity` | 7-pt Likert | How easy was it to understand the constraint information shown? | 1 = Very hard … 7 = Very easy |
| `info_useful` | 7-pt Likert | How useful was the information for solving the puzzle? | 1 = Not useful … 7 = Extremely useful |
| `confidence` | 7-pt Likert | How confident are you in the solution you found? | 1 = Not confident … 7 = Very confident |
| `mental_demand` | 7-pt Likert | How mentally demanding was this condition? | 1 = Very low … 7 = Very high |
| `satisfaction` | 7-pt Likert | How satisfied are you with this condition overall? | 1 = Very dissatisfied … 7 = Very satisfied |
| `inter_comments` | open text | Any comments about this condition? (optional) | — |

---

## Section 3 — Final Questionnaire

Shown once after all conditions are complete.

| id | type | Question / Label | Options |
|----|------|-----------------|---------|
| `most_helpful` | radio | Which condition did you find MOST helpful overall? | [auto-populated from selected conditions] |
| `least_helpful` | radio | Which condition did you find LEAST helpful overall? | [auto-populated from selected conditions] |
| `easiest` | radio | Which condition was EASIEST to understand? | [auto-populated from selected conditions] |
| `comparison` | open text | How would you compare the different conditions you experienced? | — |
| `final_comments` | open text | Any other feedback or suggestions? (optional) | — |
