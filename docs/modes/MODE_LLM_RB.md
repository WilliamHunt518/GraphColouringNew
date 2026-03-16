# LLM_RB Mode: Natural Language ↔ Rule-Based Grammar

## Overview

LLM_RB mode bridges natural language and structured argumentation by **translating between human natural language and rule-based (RB) grammar**. This enables humans to communicate naturally while agents use precise, structured reasoning.

## Motivation

### The Problem

- **RB mode** is powerful (precise, complete, deterministic) but **unnatural** for humans
- **Free NL modes** are natural but **ambiguous** (what does "that won't work" mean?)
- Need: **Natural interface** with **structured backend**

### The Solution

```
Human NL → [LLM Translation] → RB Grammar → [Agent RB Engine] → RB Response
                                                                      ↓
Human NL ← [LLM Rendering] ←─────────────────────────────────────────┘
```

Human gets natural conversation, agent gets structured messages.

## Architecture

### Communication Flow

```
┌──────────────────────────────────────────────────────────────┐
│                    Human Types Natural Language               │
│          "Can you change a2 to green? That would help"        │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                LLM_RB Communication Layer                     │
│                  (llm_rb_comm_layer.py)                       │
│  ┌───────────────────────────────────────────────────────┐   │
│  │ Stage 1: LLM Translation (NL → RB Grammar)            │   │
│  │  • Extract intent (query, proposal, constraint)       │   │
│  │  • Parse assignments {node: color}                    │   │
│  │  • Detect conditions (if-then, impossible_when)       │   │
│  │  • Format as RBMove structure                         │   │
│  └───────────────────────────────────────────────────────┘   │
│  ┌───────────────────────────────────────────────────────┐   │
│  │ Fallback: Heuristic Parser (if LLM fails)            │   │
│  │  • Regex patterns for assignments                     │   │
│  │  • Keyword detection ("impossible", "if", "when")     │   │
│  │  • Simple condition parsing                           │   │
│  └───────────────────────────────────────────────────────┘   │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                   RBMove (Structured)                         │
│  {                                                            │
│    "type": "proposal",                                        │
│    "proposed_nodes": {"a2": "green"},                         │
│    "dependencies": {"h1": "red", "h2": "blue"},               │
│    "impossible_conditions": [{"node": "a2", "colour": "red"}],│
│    "impossible_combinations": [[{...}, {...}]]                │
│  }                                                            │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│          RuleBasedClusterAgent (RB Reasoning Engine)          │
│  • Processes RBMove via RB logic                              │
│  • Updates belief state (constraints, dependencies)           │
│  • Generates RBMove response                                  │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                LLM_RB Communication Layer                     │
│  ┌───────────────────────────────────────────────────────┐   │
│  │ Stage 2: LLM Rendering (RB Grammar → NL)             │   │
│  │  • Converts RBMove to natural language                │   │
│  │  • Adds conversational tone                           │   │
│  │  • Preserves [report: {...}] tags                     │   │
│  └───────────────────────────────────────────────────────┘   │
│  ┌───────────────────────────────────────────────────────┐   │
│  │ Fallback: Template Rendering (if LLM fails)          │   │
│  │  • Pre-written templates for each RBMove type         │   │
│  │  • Guaranteed to work                                 │   │
│  └───────────────────────────────────────────────────────┘   │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                 Human Receives Natural Language               │
│    "If you set h1 to red and h2 to blue, then I can do       │
│     a1=yellow, a2=green, a3=red. How does that sound?"       │
└──────────────────────────────────────────────────────────────┘
```

## RB Grammar Structures

### RBMove: Complete Message Format

```python
class RBMove:
    type: str  # "query", "proposal", "conditional_offer", "acceptance", etc.

    # Proposed assignments
    proposed_nodes: Dict[str, str]  # {node: color}

    # Dependencies (conditions for my proposal)
    dependencies: Dict[str, str]    # {neighbor_node: required_color}

    # Simple infeasibility constraints
    impossible_conditions: List[Dict[str, str]]  # [{"node": n, "colour": c}]
    # Meaning: node n cannot be color c (simple constraint)

    # Conditional infeasibility
    impossible_combinations: List[List[Dict[str, str]]]
    # Example: [[{"node": "a2", "colour": "green"}, {"node": "h1", "colour": "red"}]]
    # Meaning: a2=green is impossible WHEN h1=red (conditional constraint)

    # Query-specific
    feasibility_query: Dict[str, str]  # {node: color} to check
    multi_condition_query: Dict[str, List[str]]  # {node: [colors]} to check

    # Response-specific
    response_to: str  # Message ID this responds to
    feasible: bool    # Answer to feasibility query
```

### Message Type Taxonomy

| Type | Description | Example RBMove |
|------|-------------|----------------|
| **query** | Ask if configuration is feasible | `{"type": "query", "feasibility_query": {"h1": "red", "h2": "blue"}}` |
| **proposal** | Suggest configuration | `{"type": "proposal", "proposed_nodes": {"a2": "green"}}` |
| **conditional_offer** | "If you do X, I'll do Y" | `{"type": "conditional_offer", "proposed_nodes": {"a2": "green"}, "dependencies": {"h1": "red"}}` |
| **acceptance** | Accept proposal | `{"type": "acceptance", "response_to": "msg_123"}` |
| **rejection** | Reject with constraints | `{"type": "rejection", "response_to": "msg_123", "impossible_conditions": [...]}` |
| **announcement** | Declare boundary assignments | `{"type": "announcement", "proposed_nodes": {"a1": "red", "a2": "blue"}}` |
| **conditional_rejection** | "X won't work when Y" | `{"type": "conditional_rejection", "impossible_combinations": [[...]]}` |

## Translation: NL → RB Grammar

### LLM-Based Translation

```python
def _nl_to_rbmove_llm(self, sender: str, recipient: str, nl_text: str) -> RBMove:
    """Translate natural language to RBMove using LLM."""

    prompt = f"""You are translating natural language into structured RBMove format for graph coloring negotiation.

**Human message**: "{nl_text}"

**Your task**: Extract structured information and return JSON.

**Detect**:
1. **Message type**: query | proposal | conditional_offer | acceptance | rejection | constraint
2. **Proposed assignments**: {{node: color}} pairs mentioned
3. **Dependencies**: "if X then Y" conditions
4. **Simple constraints**: "X cannot be Y" (impossible_conditions)
5. **Conditional constraints**: "X cannot be Y when Z is W" (impossible_combinations)
6. **Feasibility queries**: "Can you do X?" or "Would X work?"

**Output format**:
{{
  "type": "proposal",
  "proposed_nodes": {{"a2": "green", "a5": "blue"}},
  "dependencies": {{"h1": "red"}},  // if mentioned
  "impossible_conditions": [{{"node": "a2", "colour": "red"}}],  // if mentioned
  "impossible_combinations": [
    [{{"node": "a2", "colour": "green"}}, {{"node": "h1", "colour": "red"}}]
  ],  // if conditional constraints mentioned
  "feasibility_query": {{"h1": "red"}},  // if asking feasibility
  "reason": "Brief explanation of intent"
}}

**Examples**: