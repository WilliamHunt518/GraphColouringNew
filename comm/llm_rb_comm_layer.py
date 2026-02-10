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
        print(f"[LLMRBCommLayer] format_content called: sender={sender}, content type={type(content).__name__}")

        # Check for special control tokens - pass through unchanged
        if isinstance(content, str) and content.startswith("__") and content.endswith("__"):
            print(f"[LLMRBCommLayer] Passing through special token: {content}")
            return content

        # Try to parse as RBMove
        rb_move = None
        if hasattr(content, 'move'):
            # Already an RBMove object
            rb_move = content
            print(f"[LLMRBCommLayer] Content is RBMove: {content.move}")
        elif isinstance(content, str) and '[rb:' in content:
            # Already formatted string with [rb:{...}] tag - need to extract and parse
            print(f"[LLMRBCommLayer] Content is pre-formatted [rb:...] string")
            print(f"[LLMRBCommLayer] Full content: {content}")
            try:
                from .rb_protocol import parse_rb
                # Find start of [rb:
                start_idx = content.find('[rb:')
                if start_idx != -1:
                    # Extract everything after [rb:
                    json_start = start_idx + 4  # len('[rb:')
                    # Find the matching ] by counting braces
                    depth = 0
                    in_string = False
                    escape_next = False
                    json_end = json_start

                    for i in range(json_start, len(content)):
                        char = content[i]
                        if escape_next:
                            escape_next = False
                            continue
                        if char == '\\':
                            escape_next = True
                            continue
                        if char == '"' and not escape_next:
                            in_string = not in_string
                        if not in_string:
                            if char == '{':
                                depth += 1
                            elif char == '}':
                                depth -= 1
                                if depth == 0:
                                    json_end = i + 1
                                    break

                    if json_end > json_start:
                        json_str = content[json_start:json_end]
                        print(f"[LLMRBCommLayer] Extracted JSON ({len(json_str)} chars):")
                        print(f"[LLMRBCommLayer] Full JSON: {json_str}")
                        print(f"[LLMRBCommLayer] Extraction range: {json_start} to {json_end}")
                        rb_dict = json.loads(json_str)
                        rb_move = parse_rb(rb_dict)
                        print(f"[LLMRBCommLayer] Parsed RBMove: {rb_move.move}")
            except Exception as e:
                print(f"[LLMRBCommLayer] Failed to parse [rb:...] string: {e}")
                import traceback
                traceback.print_exc()
        elif isinstance(content, dict) and "move" in content:
            # Dictionary representation of RBMove
            try:
                from .rb_protocol import parse_rb
                rb_move = parse_rb(content)
                print(f"[LLMRBCommLayer] Parsed dict as RBMove: {rb_move.move}")
            except Exception:
                pass

        if rb_move:
            nl_text = self._rbmove_to_nl(sender, recipient, rb_move)
            print(f"[LLMRBCommLayer] Converted to NL: {nl_text}")

            # CRITICAL: Preserve [report: {...}] if present in original content
            # The report is needed for UI to update graph with agent's node colors
            report_suffix = ""
            if isinstance(content, str) and '[report:' in content:
                import re
                m = re.search(r'\[report:\s*(\{.*?\})\s*\]', content)
                if m:
                    report_suffix = f" [report: {m.group(1)}]"
                    print(f"[LLMRBCommLayer] Preserved report: {report_suffix}")

            # Return natural language + preserved report
            return nl_text + report_suffix

        # For non-RB content, just return string representation (NO parent paraphrasing)
        print(f"[LLMRBCommLayer] Non-RB content, returning as-is")
        return str(content)

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
        # Always use template-based formatting (LLM can be unreliable)
        # LLM is only used for parsing human natural language input

        move_type = move.move if hasattr(move, 'move') else str(move)
        node = move.node if hasattr(move, 'node') else None
        colour = move.colour if hasattr(move, 'colour') else None

        # === PROPOSE ===
        if move_type in ("PROPOSE", "Propose"):
            if node and colour:
                return f"What if I set {node} to {colour}? Would that work for you?"
            return f"Let me share my current configuration with you."

        # === CONDITIONAL OFFER ===
        elif move_type == "ConditionalOffer":
            conditions = getattr(move, 'conditions', None) or []
            assignments = getattr(move, 'assignments', None) or []

            if assignments:
                assign_str = ", ".join([f"{a.node}={a.colour}" for a in assignments])
                if conditions:
                    # CONDITIONAL: "If you could set X, then I could set Y"
                    cond_str = ", ".join([f"{c.node}={c.colour}" for c in conditions])
                    if len(conditions) == 1:
                        return f"If you could set {cond_str}, then I could make {assign_str} work on my side. Would that help?"
                    else:
                        return f"If you could do {cond_str}, then I could handle {assign_str}. Does that work?"
                else:
                    # UNCONDITIONAL: just announcing their configuration
                    if len(assignments) == 1:
                        return f"I'm planning to set {assign_str}. Let me know if that causes any issues for you."
                    else:
                        return f"I'm thinking {assign_str} for my nodes. Does that create any conflicts?"
            return "I have a proposal for how we might coordinate."

        # === COUNTER PROPOSAL ===
        elif move_type == "CounterProposal":
            if node and colour:
                refers = getattr(move, 'refers_to', None)
                if refers:
                    return f"Instead, what if we try {node}={colour}? That might avoid the conflict."
                else:
                    return f"Actually, I think {node}={colour} would work better. What do you think?"
            return "Let me suggest an alternative."

        # === ACCEPT ===
        elif move_type == "Accept":
            refers = getattr(move, 'refers_to', None)
            if refers:
                return f"That works for me! I'll go with your proposal."
            elif node:
                return f"Yes, {node} looks good. I can work with that."
            else:
                return "Agreed, that should work!"

        # === REJECT ===
        elif move_type == "Reject":
            refers = getattr(move, 'refers_to', None)
            impossible_conds = getattr(move, 'impossible_conditions', None)
            impossible_combos = getattr(move, 'impossible_combinations', None)

            msg_parts = []

            if refers:
                msg_parts.append("Unfortunately, I can't make that work.")
            else:
                msg_parts.append("That won't work on my side.")

            # Add specific impossible conditions
            if impossible_conds:
                imp_list = ", ".join([f"{ic['node']}={ic['colour']}" for ic in impossible_conds])
                if len(impossible_conds) == 1:
                    msg_parts.append(f"I can't do {imp_list} because it conflicts with my constraints.")
                else:
                    msg_parts.append(f"I can't use {imp_list} due to conflicts in my cluster.")

            # Add impossible combinations
            if impossible_combos:
                if len(impossible_combos) == 1:
                    combo = impossible_combos[0]
                    combo_str = " and ".join([f"{ic['node']}={ic['colour']}" for ic in combo])
                    msg_parts.append(f"The combination of {combo_str} doesn't work.")
                else:
                    msg_parts.append("Several combinations won't work for my constraints.")

            return " ".join(msg_parts)

        # === COMMIT ===
        elif move_type in ("CONCEDE", "Concede", "Commit"):
            if node and colour:
                return f"Sounds good! I'll set {node}={colour}."
            return "OK, let's go with that!"

        # === FEASIBILITY QUERY ===
        elif move_type == "FeasibilityQuery":
            conditions = getattr(move, 'conditions', None) or []
            if conditions:
                cond_str = ", ".join([f"{c.node}={c.colour}" for c in conditions])
                if len(conditions) == 1:
                    return f"Quick question: if you set {cond_str}, would that work for you?"
                else:
                    return f"Can you check if {cond_str} would be feasible on your side?"
            return "Can you check if this would work?"

        # === FEASIBILITY RESPONSE ===
        elif move_type == "FeasibilityResponse":
            is_feas = getattr(move, 'is_feasible', None)
            penalty = getattr(move, 'feasibility_penalty', None)
            details = getattr(move, 'feasibility_details', None)

            if is_feas:
                if penalty is not None and penalty == 0:
                    msg = "Yes, that works perfectly! No conflicts on my side."
                elif penalty is not None and penalty > 0:
                    msg = f"That could work, though it would create {int(penalty)} conflict(s) for me."
                else:
                    msg = "Yes, I can make that work."
            else:
                msg = "Sorry, that won't work for me."

            if details:
                msg += f" {details}"

            return msg

        # === ATTACK (legacy) ===
        elif move_type in ("ATTACK", "Attack"):
            if node:
                return f"There's a problem with {node} - it's conflicting with my setup. Can we try a different colour?"
            return "I'm seeing a conflict. Let's try to work around it."

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
                "Parse the human's message into a structured move. Return ONLY valid JSON.\n\n"
                "CRITICAL DISTINCTION:\n"
                "- QUESTIONS (\"Could we..?\", \"What if..?\", \"What about..?\", \"Would... work?\") → FeasibilityQuery or Propose\n"
                "- NEGATIONS (\"can't\", \"cannot\", \"won't work\", \"impossible\") → Reject with impossible_conditions\n"
                "- MULTIPLE nodes (\"X and Y\") → FeasibilityQuery with multiple conditions (NOT single-node Propose!)\n\n"
                "Available moves:\n"
                "- Propose: suggesting a SINGLE node=colour assignment (\"What if I do h4=red?\")\n"
                "  * Use ONLY for single node suggestions\n"
                "- FeasibilityQuery: asking if one or MORE assignments would work\n"
                "  * Use for ANY question about feasibility: \"Could..?\", \"Would..?\", \"What about..?\", \"Can..?\"\n"
                "  * Use for multiple nodes: \"What about h4=red and h1=green?\" → multiple conditions\n"
                "  * CRITICAL: If message mentions MULTIPLE node-color pairs, you MUST include ALL of them in conditions\n"
                "- ConditionalOffer: \"if you do X, I'll do Y\"\n"
                "- CounterProposal: suggesting alternative to previous proposal\n"
                "- Accept: agreeing to a proposal\n"
                "- Reject: disagreeing with a proposal OR stating impossibility\n"
                "  * ONLY use Reject for NEGATIONS: \"X can't be Y\", \"X cannot be Y\", \"X won't work\"\n"
                "  * Extract impossible_conditions: [{\"node\": \"X\", \"colour\": \"Y\"}]\n"
                "  * DO NOT use Reject for questions\n"
                "- Commit: confirming they'll use a specific assignment\n"
                "- FeasibilityResponse: answering whether something works\n\n"
                "Examples:\n"
                "Input: 'What if I set h4 to red?'\n"
                "Output: {\"move\": \"Propose\", \"node\": \"h4\", \"colour\": \"red\"}\n\n"
                "Input: 'What about h4=red and h1=green?'\n"
                "Output: {\"move\": \"FeasibilityQuery\", \"conditions\": [{\"node\": \"h4\", \"colour\": \"red\", \"owner\": \"self\"}, {\"node\": \"h1\", \"colour\": \"green\", \"owner\": \"self\"}]}\n\n"
                "Input: 'Could we do h4 red and h1 green?'\n"
                "Output: {\"move\": \"FeasibilityQuery\", \"conditions\": [{\"node\": \"h4\", \"colour\": \"red\", \"owner\": \"self\"}, {\"node\": \"h1\", \"colour\": \"green\", \"owner\": \"self\"}]}\n\n"
                "Input: 'Would h2=blue work for you?'\n"
                "Output: {\"move\": \"FeasibilityQuery\", \"conditions\": [{\"node\": \"h2\", \"colour\": \"blue\", \"owner\": \"neighbor\"}]}\n\n"
                "Input: 'If you could do h2=blue, I could make a3=green work'\n"
                "Output: {\"move\": \"ConditionalOffer\", \"conditions\": [{\"node\": \"h2\", \"colour\": \"blue\", \"owner\": \"neighbor\"}], \"assignments\": [{\"node\": \"a3\", \"colour\": \"green\"}]}\n\n"
                "Input: 'That works for me!'\n"
                "Output: {\"move\": \"Accept\"}\n\n"
                "Input: 'H4 can't ever be green I'm afraid'\n"
                "Output: {\"move\": \"Reject\", \"impossible_conditions\": [{\"node\": \"h4\", \"colour\": \"green\"}]}\n\n"
                "Input: 'Sorry, I can't do h5=red because it conflicts'\n"
                "Output: {\"move\": \"Reject\", \"impossible_conditions\": [{\"node\": \"h5\", \"colour\": \"red\"}]}\n\n"
                "Input: 'No, h2 cannot be blue'\n"
                "Output: {\"move\": \"Reject\", \"impossible_conditions\": [{\"node\": \"h2\", \"colour\": \"blue\"}]}\n\n"
                "Input: 'h1 can never be red when h4 is green'\n"
                "Output: {\"move\": \"Reject\", \"impossible_combinations\": [[{\"node\": \"h1\", \"colour\": \"red\"}, {\"node\": \"h4\", \"colour\": \"green\"}]]}\n\n"
                "Input: 'Could you try h1=green instead?'\n"
                "Output: {\"move\": \"CounterProposal\", \"node\": \"h1\", \"colour\": \"green\"}\n\n"
                "Input: 'Yes, that would work on my side'\n"
                "Output: {\"move\": \"FeasibilityResponse\", \"is_feasible\": true}\n\n"
                f"Now parse this message:\n'{text}'\n\n"
                "Return ONLY the JSON object, no explanation."
            )

            print(f"[LLMRBCommLayer] Calling LLM to parse: '{text}'")
            response = self._call_openai(prompt, max_tokens=200)
            if response:
                print(f"[LLMRBCommLayer] LLM returned: {response[:200]}")
                try:
                    # Try to extract JSON from response
                    # Handle case where LLM wraps in markdown code blocks
                    cleaned = response.strip()
                    if cleaned.startswith("```"):
                        # Remove markdown code fences
                        lines = cleaned.split('\n')
                        cleaned = '\n'.join(lines[1:-1] if len(lines) > 2 else lines)

                    obj = json.loads(cleaned)
                    print(f"[LLMRBCommLayer] Parsed JSON: {obj}")
                    from .rb_protocol import parse_rb
                    rb_move = parse_rb(obj)
                    print(f"[LLMRBCommLayer] Created RBMove: move={rb_move.move}, impossible_conditions={getattr(rb_move, 'impossible_conditions', None)}")
                    return rb_move
                except Exception as e:
                    print(f"[LLMRBCommLayer] Failed to parse LLM response: {e}")
                    print(f"[LLMRBCommLayer] Raw response: {response}")
            else:
                print(f"[LLMRBCommLayer] LLM call returned None, falling back to heuristics")

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
        colors = re.findall(r'\b(red|green|blue|yellow|orange|purple)\b', text_lower)

        # Extract node=color pairs (more specific parsing)
        assignments = re.findall(r'\b([hab]\d+)\s*[=:]\s*(red|green|blue|yellow|orange|purple)\b', text_lower)

        # Check for conditional patterns: "if you ... then I ..." or "if ... I'll ..."
        if re.search(r'\bif\b.*\b(then|i\'ll|i will|i can)\b', text_lower):
            try:
                from .rb_protocol import RBMove, Condition, Assignment
                # Try to extract conditions and assignments
                conditions = []
                my_assignments = []

                for node, color in assignments:
                    # Simple heuristic: first half = conditions, second half = assignments
                    if_pos = text_lower.find('if')
                    then_pos = text_lower.find('then') if 'then' in text_lower else text_lower.find("i'll") if "i'll" in text_lower else text_lower.find("i will")

                    node_pos = text_lower.find(node)
                    if if_pos < node_pos < then_pos:
                        conditions.append(Condition(node=node, colour=color, owner="neighbor"))
                    else:
                        my_assignments.append(Assignment(node=node, colour=color))

                if my_assignments:
                    return RBMove(move="ConditionalOffer", conditions=conditions if conditions else None, assignments=my_assignments)
            except Exception:
                pass

        # Check for accept keywords
        if any(kw in text_lower for kw in ['accept', 'agree', 'that works', "i'll go with", 'sounds good', 'perfect', 'great']):
            try:
                from .rb_protocol import RBMove
                if assignments:
                    return RBMove(move="Accept", node=assignments[0][0])
                return RBMove(move="Accept")
            except Exception:
                pass

        # Check for reject keywords
        if any(kw in text_lower for kw in ['reject', "can't", "won't work", "not feasible", "impossible", "conflict", "problem"]):
            try:
                from .rb_protocol import RBMove
                impossible = [{"node": node, "colour": color} for node, color in assignments] if assignments else None
                if assignments:
                    return RBMove(move="Reject", impossible_conditions=impossible)
                return RBMove(move="Reject")
            except Exception:
                pass

        # Check for feasibility query
        if any(kw in text_lower for kw in ['would that work', 'can you', 'could you', 'feasible', 'would you', 'is it possible']):
            try:
                from .rb_protocol import RBMove, Condition
                if assignments:
                    conditions = [Condition(node=node, colour=color, owner="neighbor") for node, color in assignments]
                    return RBMove(move="FeasibilityQuery", conditions=conditions)
            except Exception:
                pass

        # Check for counter-proposal
        if any(kw in text_lower for kw in ['instead', 'alternative', 'what about', 'how about', 'try']):
            if assignments:
                try:
                    from .rb_protocol import RBMove
                    return RBMove(move="CounterProposal", node=assignments[0][0], colour=assignments[0][1])
                except Exception:
                    pass

        # Default: treat as Propose if we found assignments
        if assignments:
            try:
                from .rb_protocol import RBMove
                return RBMove(move="Propose", node=assignments[0][0], colour=assignments[0][1], reasons=[])
            except Exception:
                pass

        # Fallback to old logic for backward compatibility
        if not nodes:
            return None

        node = nodes[0]
        color = colors[0] if colors else None

        # Classify move type based on keywords
        if any(kw in text_lower for kw in ['propose', 'suggest', 'set', 'assign', 'i think', 'what if', 'planning']):
            move_type = "Propose"
        elif any(kw in text_lower for kw in ['conflict', 'clash', 'problem']):
            move_type = "Reject"
        elif any(kw in text_lower for kw in ['okay', 'ok', 'yes', 'fine', 'good']):
            move_type = "Accept"
        else:
            # Default to Propose if unclear
            move_type = "Propose"

        try:
            from .rb_protocol import RBMove
            return RBMove(move=move_type, node=node, colour=color, reasons=[])
        except Exception:
            return None
