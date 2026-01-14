"""LLM-mediated RB protocol communication layer.

This module provides LLMRBCommLayer, which translates between natural language
and the formal RBMove dialogue protocol (Parsons & Tang 2006) for argumentation-based
graph coloring negotiation.

The layer enables human participants to use free-form text while maintaining
compatibility with the structured PROPOSE/ATTACK/CONCEDE protocol used by
rule-based agents.
"""

from __future__ import annotations

from typing import Any, Optional
import json
import re

from .communication_layer import LLMCommLayer


class LLMRBCommLayer(LLMCommLayer):
    """LLM translator for RB protocol.

    This layer extends LLMCommLayer to support bidirectional translation between:
    - Structured RBMove objects (PROPOSE/ATTACK/CONCEDE moves)
    - Natural language text suitable for human participants

    The translation uses GPT-based prompting with heuristic fallbacks for robustness.
    """

    def format_content(self, sender: str, recipient: str, content: Any) -> str:
        """Format RBMove or structured content into natural language.

        Parameters
        ----------
        sender : str
            Identifier of the sending agent.
        recipient : str
            Identifier of the receiving agent.
        content : Any
            Structured content (RBMove, dict, or other).

        Returns
        -------
        str
            Natural language representation with embedded structured protocol.
        """
        # Try to parse as RBMove
        rb_move = None
        if hasattr(content, 'move'):
            # Already an RBMove object
            rb_move = content
        elif isinstance(content, dict) and "move" in content:
            # Dictionary representation of RBMove
            try:
                from .rb_protocol import parse_rb
                rb_move = parse_rb(content)
            except Exception:
                pass

        if rb_move:
            nl_text = self._rbmove_to_nl(sender, recipient, rb_move)
            # Also include structured format for reliable parsing
            try:
                from .rb_protocol import format_rb
                structured = format_rb(rb_move)
                return f"{nl_text} {structured}"
            except Exception:
                return nl_text

        # Fall back to parent implementation for non-RB content
        return super().format_content(sender, recipient, content)

    def parse_content(self, sender: str, recipient: str, message: str) -> Any:
        """Parse natural language into RBMove or structured content.

        Parameters
        ----------
        sender : str
            Identifier of the sending agent.
        recipient : str
            Identifier of the receiving agent.
        message : str
            The raw message string (may contain NL + structured protocol).

        Returns
        -------
        Any
            Parsed RBMove object, or fallback to parent parsing.
        """
        # First, try to extract existing structured RBMove from message
        try:
            from .rb_protocol import parse_rb
            existing_rb = parse_rb(message)
            if existing_rb:
                return existing_rb
        except Exception:
            pass

        # Try LLM-based NL → RBMove translation
        rb_move = self._nl_to_rbmove(sender, recipient, message)
        if rb_move:
            return rb_move

        # Fall back to parent implementation
        return super().parse_content(sender, recipient, message)

    def _rbmove_to_nl(self, sender: str, recipient: str, move: Any) -> str:
        """Convert RBMove to natural language using LLM or template fallback.

        Parameters
        ----------
        sender : str
            Sending agent name.
        recipient : str
            Receiving agent name.
        move : RBMove
            The structured dialogue move.

        Returns
        -------
        str
            Natural language representation.
        """
        # Try LLM translation if available
        if not self.manual:
            prompt = (
                f"Translate this structured dialogue move to natural language.\n"
                f"Sender: {sender}, Recipient: {recipient}\n"
                f"Move: {json.dumps(move.to_dict() if hasattr(move, 'to_dict') else str(move))}\n\n"
                f"Guidelines:\n"
                f"- PROPOSE: 'I propose setting node X to Y'\n"
                f"- ATTACK: 'Your assignment of node X conflicts with my constraints'\n"
                f"- CONCEDE: 'Okay, I agree to change node X to Y'\n\n"
                f"Return only the natural language sentence (one line)."
            )

            nl_text = self._call_openai(prompt, max_tokens=60)
            if nl_text:
                return nl_text.strip()

        # Fallback template-based translation
        move_type = move.move if hasattr(move, 'move') else str(move)
        node = move.node if hasattr(move, 'node') else None
        colour = move.colour if hasattr(move, 'colour') else None

        if move_type == "PROPOSE":
            if node and colour:
                return f"I propose: {node} = {colour}"
            return f"I propose my current assignment"

        elif move_type == "ATTACK":
            if node:
                return f"Your {node} conflicts with my nodes"
            return f"There's a conflict with your assignment"

        elif move_type == "CONCEDE":
            if node and colour:
                return f"Okay, I'll change {node} to {colour}"
            return f"I accept your proposal"

        # Generic fallback
        try:
            from .rb_protocol import pretty_rb
            return pretty_rb(move)
        except Exception:
            return str(move)

    def _nl_to_rbmove(self, sender: str, recipient: str, text: str) -> Optional[Any]:
        """Convert natural language to RBMove using LLM or heuristic fallback.

        Parameters
        ----------
        sender : str
            Sending agent name.
        recipient : str
            Receiving agent name.
        text : str
            Natural language message.

        Returns
        -------
        RBMove or None
            Parsed dialogue move, or None if parsing fails.
        """
        # Try LLM-based parsing if available
        if not self.manual:
            prompt = (
                f"Parse this natural language message into a structured dialogue move.\n"
                f"Message: '{text}'\n\n"
                f"Extract JSON with this format:\n"
                f'{{\"move\": \"PROPOSE|ATTACK|CONCEDE\", \"node\": \"nodeID\", \"colour\": \"red|green|blue\"}}\n\n'
                f"Examples:\n"
                f"'I propose h4 should be red' → {{\"move\": \"PROPOSE\", \"node\": \"h4\", \"colour\": \"red\"}}\n"
                f"'Your a2 conflicts' → {{\"move\": \"ATTACK\", \"node\": \"a2\", \"colour\": null}}\n"
                f"'Okay, b3 will be green' → {{\"move\": \"CONCEDE\", \"node\": \"b3\", \"colour\": \"green\"}}\n\n"
                f"Return only valid JSON (one line)."
            )

            response = self._call_openai(prompt, max_tokens=80)
            if response:
                try:
                    # Try to extract JSON from response
                    obj = json.loads(response)
                    from .rb_protocol import parse_rb
                    return parse_rb(obj)
                except Exception:
                    pass

        # Fallback to heuristic parsing
        return self._heuristic_nl_to_rbmove(text)

    def _heuristic_nl_to_rbmove(self, text: str) -> Optional[Any]:
        """Heuristic-based NL → RBMove parser (no LLM required).

        Parameters
        ----------
        text : str
            Natural language message.

        Returns
        -------
        RBMove or None
            Parsed move, or None if no clear interpretation.
        """
        text_lower = text.lower()

        # Extract node identifiers (e.g., h1, a2, b3)
        nodes = re.findall(r'\b([hab]\d+)\b', text_lower)

        # Extract color mentions
        colors = re.findall(r'\b(red|green|blue)\b', text_lower)

        if not nodes:
            return None

        node = nodes[0]
        color = colors[0] if colors else None

        # Classify move type based on keywords
        if any(kw in text_lower for kw in ['propose', 'suggest', 'set', 'assign', 'i think']):
            move_type = "PROPOSE"
        elif any(kw in text_lower for kw in ['conflict', 'clash', 'attack', 'problem', 'wrong']):
            move_type = "ATTACK"
        elif any(kw in text_lower for kw in ['okay', 'agree', 'concede', 'accept', 'yes', 'fine']):
            move_type = "CONCEDE"
        else:
            # Default to PROPOSE if unclear
            move_type = "PROPOSE"

        try:
            from .rb_protocol import RBMove
            return RBMove(move=move_type, node=node, colour=color, reasons=[])
        except Exception:
            return None
