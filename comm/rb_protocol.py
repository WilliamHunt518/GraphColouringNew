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


ALLOWED_MOVES = ("PROPOSE", "ARGUE", "ATTACK", "CONCEDE", "REQUEST", "QUERY")


@dataclass
class RBMove:
    move: str
    node: str
    colour: Optional[str] = None
    reasons: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "move": self.move,
            "node": self.node,
            "colour": self.colour,
            "reasons": list(self.reasons or []),
        }


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
        move = str(text.get("move", "")).upper().strip()
        if move not in ALLOWED_MOVES:
            return None
        node = str(text.get("node", "")).strip()
        if not node:
            return None
        colour = text.get("colour", None)
        if colour is not None:
            colour = str(colour).strip()
        reasons = text.get("reasons", [])
        if isinstance(reasons, list):
            reasons = [str(r) for r in reasons if str(r).strip()]
        else:
            reasons = []
        return RBMove(move=move, node=node, colour=colour or None, reasons=reasons)

    s = str(text)
    if "[rb:" not in s:
        return None
    try:
        after = s.split("[rb:", 1)[1]
        payload = after.split("]", 1)[0].strip()
        obj = json.loads(payload)
        return parse_rb(obj)
    except Exception:
        return None


def pretty_rb(move: RBMove) -> str:
    """Human-friendly rendering for UI/logs."""
    if move.colour:
        base = f"{move.move} assign({move.node}={move.colour})"
    else:
        base = f"{move.move}({move.node})"
    if move.reasons:
        return base + " | reasons: " + ", ".join(move.reasons)
    return base
