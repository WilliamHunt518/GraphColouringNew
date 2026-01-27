"""Rule-based argumentation protocol helpers.

This module implements a lightweight dialogue-game style protocol for the
RB (rule-based) experimental condition.

Design goals:
  * No LLM involvement.
  * Messages are structured and machine-parseable.
  * Humans interact via UI controls (move/node/colour/reasons), not free text.

Wire format
-----------
Messages are sent as a single string containing a tagged JSON payload:

    "... [rb:{...}] [report:{...}]"

Only the ``[rb: ...]`` payload is required. ``[report: ...]`` is optional and
is used by the participant UI to colour neighbour nodes only when explicitly
reported.

The RB payload schema is:

    {
      "move": "PROPOSE" | "ARGUE" | "ATTACK" | "CONCEDE" | "REQUEST" | "QUERY",
      "node": "h4",               # node under discussion
      "colour": "red"|"green"|"blue"|null,
      "reasons": ["..."]          # optional list of reason codes
    }

The protocol is intentionally minimal; it supports a single move per message.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# New conditional proposal grammar
ALLOWED_MOVES = ("Propose", "ConditionalOffer", "CounterProposal", "Accept", "Commit")

# Backward compatibility mapping for old logs
LEGACY_MOVES = {
    "PROPOSE": "Propose",
    "ATTACK": "CounterProposal",  # Old attacks map to counter-proposals
    "ARGUE": "Propose",           # Old argue maps to simple propose
    "CONCEDE": "Commit",
    "REQUEST": "Propose",
    "QUERY": "CounterProposal",
    "Challenge": "CounterProposal",  # Old Challenge becomes CounterProposal
    "Justify": "Propose"             # Old Justify becomes Propose
}


@dataclass
class Condition:
    """Represents a condition in a conditional offer (IF part)."""
    node: str
    colour: str
    owner: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node": self.node,
            "colour": self.colour,
            "owner": self.owner,
        }


@dataclass
class Assignment:
    """Represents an assignment in a conditional offer (THEN part)."""
    node: str
    colour: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node": self.node,
            "colour": self.colour,
        }


@dataclass
class RBMove:
    move: str
    node: Optional[str] = None           # For simple moves
    colour: Optional[str] = None
    reasons: Optional[List[str]] = None

    # NEW: For complex conditionals
    conditions: Optional[List[Condition]] = None
    assignments: Optional[List[Assignment]] = None
    offer_id: Optional[str] = None
    refers_to: Optional[str] = None      # Reference to other offer/proposal

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "move": self.move,
            "node": self.node,
            "colour": self.colour,
            "reasons": list(self.reasons or []),
        }

        # Add conditional fields if present
        if self.conditions is not None:
            result["conditions"] = [c.to_dict() for c in self.conditions]
        if self.assignments is not None:
            result["assignments"] = [a.to_dict() for a in self.assignments]
        if self.offer_id is not None:
            result["offer_id"] = self.offer_id
        if self.refers_to is not None:
            result["refers_to"] = self.refers_to

        return result


def format_rb(move: RBMove) -> str:
    """Format an RBMove into a tagged string."""
    payload = json.dumps(move.to_dict(), ensure_ascii=False)
    return f"[rb:{payload}]"


def parse_rb(text: Any) -> Optional[RBMove]:
    """Parse an RB tagged payload from ``text``.

    Accepts:
      * the raw message string (containing [rb:...])
      * a dict already matching the schema (for internal use)
    """
    if text is None:
        return None
    if isinstance(text, RBMove):
        return text
    if isinstance(text, dict):
        move = str(text.get("move", "")).strip()

        # Handle uppercase legacy moves
        if move.upper() in LEGACY_MOVES:
            import sys
            print(f"[RB Protocol] Warning: Legacy move '{move}' mapped to '{LEGACY_MOVES[move.upper()]}'", file=sys.stderr)
            move = LEGACY_MOVES[move.upper()]
        elif move in LEGACY_MOVES:
            import sys
            print(f"[RB Protocol] Warning: Legacy move '{move}' mapped to '{LEGACY_MOVES[move]}'", file=sys.stderr)
            move = LEGACY_MOVES[move]

        # Check if it's a valid move (case-sensitive for new grammar)
        if move not in ALLOWED_MOVES:
            return None

        # Parse basic fields
        node = text.get("node", None)
        if node is not None:
            node = str(node).strip() or None

        colour = text.get("colour", None)
        if colour is not None:
            colour = str(colour).strip() or None

        reasons = text.get("reasons", [])
        if isinstance(reasons, list):
            reasons = [str(r) for r in reasons if str(r).strip()]
        else:
            reasons = []

        # Parse conditional fields
        conditions = None
        if "conditions" in text and text["conditions"]:
            conditions = []
            for cond in text["conditions"]:
                if isinstance(cond, dict):
                    conditions.append(Condition(
                        node=str(cond.get("node", "")).strip(),
                        colour=str(cond.get("colour", "")).strip(),
                        owner=str(cond.get("owner", "")).strip()
                    ))

        assignments = None
        if "assignments" in text and text["assignments"]:
            assignments = []
            for assign in text["assignments"]:
                if isinstance(assign, dict):
                    assignments.append(Assignment(
                        node=str(assign.get("node", "")).strip(),
                        colour=str(assign.get("colour", "")).strip()
                    ))

        offer_id = text.get("offer_id", None)
        if offer_id is not None:
            offer_id = str(offer_id).strip() or None

        refers_to = text.get("refers_to", None)
        if refers_to is not None:
            refers_to = str(refers_to).strip() or None

        return RBMove(
            move=move,
            node=node,
            colour=colour,
            reasons=reasons,
            conditions=conditions,
            assignments=assignments,
            offer_id=offer_id,
            refers_to=refers_to
        )

    s = str(text)
    if "[rb:" not in s:
        return None
    try:
        # Find the [rb: tag
        start_idx = s.index("[rb:") + 4
        # Find the matching closing bracket by counting braces
        brace_count = 0
        end_idx = start_idx
        in_string = False
        escape_next = False

        for i in range(start_idx, len(s)):
            char = s[i]

            # Handle string escaping
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char == '"':
                in_string = not in_string
                continue

            # Only count brackets outside strings
            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break

        payload = s[start_idx:end_idx].strip()
        obj = json.loads(payload)
        return parse_rb(obj)
    except Exception:
        return None


def pretty_rb(move: RBMove) -> str:
    """Human-friendly rendering for UI/logs."""
    # Handle ConditionalOffer specially
    if move.move == "ConditionalOffer" and move.conditions and move.assignments:
        # Format: "If h1=red AND h4=green then a2=blue AND a3=yellow"
        cond_parts = [f"{c.node}={c.colour}" for c in move.conditions]
        assign_parts = [f"{a.node}={a.colour}" for a in move.assignments]
        base = f"ConditionalOffer: If {' AND '.join(cond_parts)} then {' AND '.join(assign_parts)}"
        if move.offer_id:
            base = f"{base} [id:{move.offer_id}]"
    # Handle CounterProposal
    elif move.move == "CounterProposal" and move.node and move.colour:
        base = f"CounterProposal: {move.node}={move.colour}"
        if move.refers_to:
            base = f"{base} (instead of {move.refers_to})"
    # Handle Accept
    elif move.move == "Accept":
        if move.refers_to:
            base = f"Accept offer {move.refers_to}"
        else:
            base = f"Accept ({move.node})" if move.node else "Accept"
    # Handle simple moves
    elif move.node and move.colour:
        base = f"{move.move}: {move.node}={move.colour}"
    elif move.node:
        base = f"{move.move}({move.node})"
    else:
        base = f"{move.move}"

    # Append reasons if present
    if move.reasons:
        return base + " | reasons: " + ", ".join(move.reasons)
    return base
