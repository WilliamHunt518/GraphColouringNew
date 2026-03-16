# LLM_RB Mode: Architecture and Design

## Overview

LLM_RB is a hybrid experimental condition that combines:
- **RB (Rule-Based) protocol**: Structured argumentation grammar with moves like ConditionalOffer, Reject, Accept
- **LLM translation layer**: Bidirectional natural language ↔ RB grammar translation

**Key principle**: The LLM is used ONLY for communication translation, NOT for problem-solving. Agents use deterministic algorithms (greedy/maxsum) for constraint solving.

## Architecture Components

### 1. RB Protocol (`comm/rb_protocol.py`)

Defines the structured dialogue grammar:

```python
@dataclass
class RBMove:
    move: str  # "Propose", "ConditionalOffer", "Reject", "Accept", etc.

    # Simple moves
    node: Optional[str] = None
    colour: Optional[str] = None

    # Conditional offers
    conditions: Optional[List[Condition]] = None      # IF part
    assignments: Optional[List[Assignment]] = None     # THEN part

    # Rejections
    impossible_conditions: Optional[List[Dict]] = None      # Simple: h4≠green
    impossible_combinations: Optional[List[List[Dict]]] = None  # Conditional: h4≠green WHEN h1=red

    # Other fields...
```

**Wire format**: Messages are sent as `[rb:{...}]` JSON payloads embedded in text.

### 2. LLM Translation Layer (`comm/llm_rb_comm_layer.py`)

Handles bidirectional translation:

#### Human → Agent (Parsing)
- Input: Natural language text from human
- Process: LLM prompt with few-shot examples
- Output: RBMove object
- Fallback: Heuristic parser if LLM fails

#### Agent → Human (Rendering)
- Input: RBMove object from agent
- Process: Template-based rendering (reliable)
- Output: Natural language text
- Note: Templates are preferred over LLM for consistency

### 3. Agent Processing (`agents/rule_based_cluster_agent.py`)

When agent receives a message:

1. **Parse** (NEW!): `comm_layer.parse_content()` converts NL → RBMove
2. **Process**: `_process_rb_move()` updates agent state:
   - Accept: Commit to assignments
   - Reject: Store impossible_conditions/combinations
   - ConditionalOffer: Store offer for consideration
3. **Generate**: `_generate_conditional_offer()` creates new offers:
   - Filters out impossible_conditions
   - Enumerates feasible configurations
   - Uses counterfactual reasoning

## Message Flow: Human Types → Agent Responds

### Example: "h4 can't be green"

```
1. Human types in UI input box
   ↓
2. UI calls on_send("Agent1", "h4 can't be green")
   ↓
3. human_agent.send() creates Message
   ↓
4. agent1.receive(msg) is called
   ↓
5. NEW: Agent calls comm_layer.parse_content()
   ↓
6. LLM parses: "h4 can't be green" → RBMove(move="Reject", impossible_conditions=[{"node": "h4", "colour": "green"}])
   ↓
7. Agent calls _process_rb_move()
   ↓
8. Agent stores: rb_impossible_conditions["Human"] = {("h4", "green")}
   ↓
9. agent1.step() is called
   ↓
10. Agent calls _generate_conditional_offer()
   ↓
11. Agent enumerates configs for Human's boundary nodes
   ↓
12. Agent FILTERS OUT any config where h4=green
   ↓
13. Agent finds valid config (e.g., h4=blue) that achieves penalty=0
   ↓
14. Agent sends ConditionalOffer with new conditions
```

## LLM Prompting Strategy

### Few-Shot Learning Approach

The LLM prompt uses **explicit few-shot examples** to teach the model how to parse:

```python
prompt = (
    "Parse the human's message into a structured move. Return ONLY valid JSON.\n\n"
    "CRITICAL DISTINCTION:\n"
    "- QUESTIONS → FeasibilityQuery or Propose\n"
    "- NEGATIONS → Reject with impossible_conditions\n"
    "- MULTIPLE nodes → FeasibilityQuery with multiple conditions\n\n"
    "Examples:\n"
    "Input: 'What about h4=red and h1=green?'\n"
    "Output: {\"move\": \"FeasibilityQuery\", \"conditions\": [...]}\n\n"
    "Input: 'H4 can't ever be green'\n"
    "Output: {\"move\": \"Reject\", \"impossible_conditions\": [{\"node\": \"h4\", \"colour\": \"green\"}]}\n\n"
    # ... more examples ...
    f"Now parse this message:\n'{text}'\n\n"
)
```

### Key Prompt Design Principles

1. **Explicit distinctions**: Clear rules for ambiguous cases
   - "Could we do X?" → FeasibilityQuery (NOT Reject!)
   - "X can't be Y" → Reject with impossible_conditions

2. **Multiple examples per pattern**: Reinforce correct parsing
   - "What about X and Y?"
   - "Could we do X and Y?"
   - Both → FeasibilityQuery with multiple conditions

3. **Critical fields highlighted**:
   - "CRITICAL: If message mentions MULTIPLE node-color pairs, you MUST include ALL of them"
   - Ensures LLM captures all nodes, not just the first one

4. **JSON-only output**: "Return ONLY valid JSON"
   - Simplifies parsing, reduces errors

### Handling Multi-Node Queries

**Problem**: "What about h4=red and h1=green?" might be parsed as single-node Propose

**Solution**:
- Add explicit rule: "MULTIPLE nodes → FeasibilityQuery"
- Provide exact examples with "and" conjunction
- Mark Propose as "SINGLE node only"

## Common Parsing Patterns

| Human Input | Correct Parse | Common Mistake |
|-------------|---------------|----------------|
| "h4 can't be green" | Reject with impossible_conditions | Reject without conditions |
| "Could we do h4=red?" | FeasibilityQuery | Reject (wrong!) |
| "What about h4=red and h1=green?" | FeasibilityQuery with 2 conditions | Propose with 1 node |
| "That works!" | Accept | (usually correct) |
| "If you do X, I'll do Y" | ConditionalOffer | (usually correct) |

## Configuration and Settings

### Manual Mode
```python
LLMRBCommLayer(manual=False)  # Use LLM (default)
LLMRBCommLayer(manual=True)   # Heuristic fallback only
```

### API Key
- Located in `api_key.txt` at project root
- Required for LLM parsing
- Silent fallback to heuristics if missing

### Logging
- `llm_trace.jsonl`: Records all LLM calls (prompt, response, parse result)
- `communication_log.txt`: Records all messages exchanged
- `Agent*_log.txt`: Agent internal reasoning logs

## Key Features and Constraints

### Impossible Conditions vs. Combinations

**Impossible Conditions** (simple):
```python
impossible_conditions = [{"node": "h4", "colour": "green"}]
# Meaning: h4 can NEVER be green
```

**Impossible Combinations** (conditional):
```python
impossible_combinations = [[
    {"node": "h4", "colour": "green"},
    {"node": "h1", "colour": "red"}
]]
# Meaning: h4 can't be green WHEN h1 is red
```

### Persistence Across Config Changes

Impossible conditions persist through configuration announcements:
```python
# In receive() when __ANNOUNCE_CONFIG__ received:
self.rb_impossible_conditions.clear()  # DON'T clear these!
# They represent fundamental constraints
```

### Filtering During Offer Generation

Agent filters configurations before proposing:
```python
# In _generate_conditional_offer():
for config in their_configs:
    config_pairs = [(their_boundary[i], config[i]) for i in range(len(their_boundary))]
    has_impossible = any(pair in impossible_set for pair in config_pairs)
    if not has_impossible:
        filtered_configs.append(config)
```

## Troubleshooting

### Issue: Agent repeats rejected offer

**Symptom**: Agent proposes h4=green again after "h4 can't be green"

**Cause**: Parsing not happening - impossible_conditions not extracted

**Fix**: Ensure `comm_layer.parse_content()` is called in `receive()`

### Issue: Only first node captured in multi-node query

**Symptom**: "What about h4=red and h1=green?" → only h4=red parsed

**Cause**: LLM defaults to single-node Propose instead of multi-condition FeasibilityQuery

**Fix**:
- Add explicit "MULTIPLE nodes" rule to prompt
- Provide exact example: "What about X and Y?"
- Mark Propose as "SINGLE node only"

### Issue: Questions parsed as Reject

**Symptom**: "Could we do X?" → Reject with impossible_conditions

**Cause**: LLM confuses questions with negations

**Fix**:
- Add CRITICAL DISTINCTION section
- Show contrast: "Could we X?" → FeasibilityQuery vs. "X can't" → Reject

### Issue: LLM not being called (manual mode)

**Check**:
1. `manual=False` in LLMRBCommLayer constructor?
2. API key exists in `api_key.txt`?
3. OpenAI package installed?
4. Check console for "[LLMRBCommLayer] Calling LLM to parse"

## Future Enhancements

### LLM-Based Agent→Human Rendering

Currently uses templates for reliability. Could add LLM rendering for more natural language:

```python
def _rbmove_to_nl_llm(self, sender, recipient, move):
    prompt = f"Convert this RBMove to natural language: {move.to_dict()}"
    return self._call_openai(prompt, max_tokens=100)
```

Tradeoff: More natural language vs. less reliability

### Adaptive Prompting

Learn from parsing failures to improve prompts dynamically:
- Track which patterns fail most often
- Add them as examples to prompt
- Personalize prompts per user

### Multi-Turn Context

Currently each parse is stateless. Could add conversation context:
```python
LLMRBCommLayer(use_history=True)  # Include prior messages in prompt
```

## References

- `comm/llm_rb_comm_layer.py`: Translation layer implementation
- `comm/rb_protocol.py`: RB grammar definitions
- `agents/rule_based_cluster_agent.py`: Agent message processing
- `docs/LLM_RB_TRANSLATION_IMPROVEMENTS.md`: Earlier translation enhancements
- `docs/LLM_RB_RENDERING_ENHANCEMENTS.md`: Agent→Human rendering work
