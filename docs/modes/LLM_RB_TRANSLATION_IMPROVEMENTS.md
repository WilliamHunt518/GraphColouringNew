# LLM_RB Translation Improvements

## Overview

Enhanced the LLM_RB communication layer (`comm/llm_rb_comm_layer.py`) to support full parity with the rule-based (RB) UI button functionality. All operations that can be performed via buttons in pure RB mode are now available through natural language in LLM_RB mode.

## New Features

### 1. Conditional Rejections (impossible_combinations)

**What it does**: Allows users to reject specific combinations of assignments, not just individual assignments.

**Examples**:
- "h4 can't be green when h1 is red" → marks the combination {h4=green, h1=red} as impossible
- "I can't use h2=blue and h3=red together" → marks {h2=blue, h3=red} as impossible combination

**RB Grammar**:
```json
{
  "move": "Reject",
  "impossible_combinations": [
    [
      {"node": "h4", "colour": "green"},
      {"node": "h1", "colour": "red"}
    ]
  ]
}
```

**Implementation**:
- **LLM prompt**: Added examples for conditional rejections (lines 363-366)
- **Heuristic parser**: Detects patterns like "when", "if", "together" (lines 520-534)
- **NL rendering**: Converts back to natural language like "I can't use h4=green and h1=red together" (lines 252-261)

### 2. Multi-Condition Feasibility Queries

**What it does**: Allows users to ask about multiple conditions at once.

**Examples**:
- "Would h2=blue and h3=red work for you?" → queries feasibility of both conditions together

**RB Grammar**:
```json
{
  "move": "FeasibilityQuery",
  "conditions": [
    {"node": "h2", "colour": "blue", "owner": "neighbor"},
    {"node": "h3", "colour": "red", "owner": "neighbor"}
  ]
}
```

**Implementation**:
- **LLM prompt**: Added example for multi-condition queries (lines 373-374)
- **Heuristic parser**: Already supported via assignment extraction (lines 485-492)

### 3. Improved Feasibility Responses

**What it does**: Better detection of yes/no responses to feasibility queries.

**Examples**:
- "Yes, that would work on my side" → FeasibilityResponse(is_feasible=True)
- "No, that won't work for me" → FeasibilityResponse(is_feasible=False)

**Implementation**:
- **LLM prompt**: Added explicit negative response example (line 379)
- **Heuristic parser**: Enhanced to distinguish feasibility responses from general accepts/rejects (lines 446-471)

### 4. Enhanced Conditional Offers

**What it does**: Better parsing of complex conditional offers with multiple conditions and assignments.

**Examples**:
- "If you do h1=red AND h2=blue, then I can do a3=green AND a4=yellow"

**RB Grammar**:
```json
{
  "move": "ConditionalOffer",
  "conditions": [
    {"node": "h1", "colour": "red", "owner": "neighbor"},
    {"node": "h2", "colour": "blue", "owner": "neighbor"}
  ],
  "assignments": [
    {"node": "a3", "colour": "green"},
    {"node": "a4", "colour": "yellow"}
  ]
}
```

**Implementation**:
- **LLM prompt**: Added example for multi-condition/multi-assignment offers (lines 347-348)
- **Heuristic parser**: Improved position-based detection with better node-color matching (lines 413-458)

## Testing

To test these improvements:

1. Launch in LLM_RB mode:
   ```bash
   python launch_menu.py
   ```
   Select "LLM_RB" mode

2. Test conditional rejections:
   - Type: "h4 can't be green when h1 is red"
   - Verify it's parsed as Reject with impossible_combinations

3. Test multi-condition feasibility:
   - Type: "Would h2=blue and h3=red work for you?"
   - Verify it's parsed as FeasibilityQuery with multiple conditions

4. Test feasibility responses:
   - Type: "Yes, that would work"
   - Type: "No, that won't work"
   - Verify both are parsed as FeasibilityResponse with correct is_feasible value

## Architecture Notes

### Translation Flow

1. **Human → RB Grammar (parse_content)**:
   - Try LLM-based parsing with enhanced prompt (lines 334-391)
   - Fall back to heuristic parser if LLM fails (lines 392-557)

2. **RB Grammar → Human (format_content)**:
   - Template-based rendering for reliability (lines 31-127)
   - Special handling for impossible_conditions and impossible_combinations (lines 234-264)

### Key Files

- `comm/llm_rb_comm_layer.py`: Main translation layer
- `comm/rb_protocol.py`: RBMove data structures and parsing
- `agents/rule_based_cluster_agent.py`: Agent-side processing of RB moves

## Backward Compatibility

All changes are backward compatible:
- Old simple rejections still work (e.g., "h4 cannot be green")
- Old single-condition queries still work (e.g., "Would h2=blue work?")
- LLM prompt includes both simple and complex examples
- Heuristic parser falls back to simpler interpretations when patterns don't match

## Future Improvements

Potential enhancements:
- Support for OR logic in conditions ("h4=green OR h4=blue")
- Support for negated conditions ("NOT h1=red")
- Better handling of implicit context (pronoun resolution)
- Learning from user corrections
