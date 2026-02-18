"""Enhanced speech layer for multi-layer LLM architecture.

This module provides bidirectional translation between human natural language
and backend LLM structured protocol. It acts as the "speech" layer that makes
the backend LLM's structured outputs understandable to humans, and vice versa.

Architecture:
    Human (NL) ↔ Speech LLM ↔ Backend LLM (structured)

The speech layer ensures that:
1. Human messages are parsed into structured backend protocol
2. Backend structured outputs are rendered as natural, conversational language
3. Report tags ([report: {...}]) are preserved for UI color updates
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import json
import os
import re


class SpeechLLMLayer:
    """Enhanced speech layer for multi-layer LLM architecture.

    This layer provides bidirectional translation:
    - Human → Backend: Parse natural language into structured messages
    - Backend → Human: Render structured outputs as natural language

    Implements BaseCommLayer interface with format_content and parse_content methods.

    Parameters
    ----------
    model : str, optional
        OpenAI model for speech translation (default: "gpt-4-turbo")
    use_llm : bool, optional
        Whether to use LLM for translation (default: True).
        If False, uses template-based fallback.

    Attributes
    ----------
    llm : OpenAI
        OpenAI client for LLM calls
    model : str
        Model name
    use_llm : bool
        Whether to use LLM
    """

    def __init__(self, model: str = "gpt-4-turbo", use_llm: bool = True) -> None:
        """Initialize speech layer.

        Parameters
        ----------
        model : str, optional
            OpenAI model name (default: "gpt-4-turbo")
        use_llm : bool, optional
            Whether to use LLM (default: True)
        """
        self.model = model
        self.use_llm = use_llm

        if use_llm:
            try:
                from openai import OpenAI
                api_key = self._load_api_key()
                self.llm = OpenAI(api_key=api_key)
            except Exception as e:
                print(f"\n{'='*70}")
                print(f"FATAL ERROR: Failed to initialize Speech LLM")
                print(f"Error: {e}")
                print(f"LLM_TOOL mode requires working OpenAI API")
                print(f"Check api_key.txt and OpenAI account credits")
                print(f"{'='*70}\n")
                raise SystemExit(f"Speech LLM initialization FAILED: {e}") from e
        else:
            self.llm = None

    def _load_api_key(self) -> str:
        """Load OpenAI API key from api_key.txt."""
        key_file = "api_key.txt"
        if os.path.exists(key_file):
            with open(key_file, "r") as f:
                return f.read().strip()
        else:
            raise FileNotFoundError("api_key.txt not found")

    def format_content(self, sender: str, recipient: str, content: Any) -> str:
        """Format structured message content into transmissible string.

        This is the main interface method called by agents' send() method.
        Handles special message types like announcements and preserves report tags.

        Parameters
        ----------
        sender : str
            Sender agent name
        recipient : str
            Recipient agent name
        content : Any
            Message content (dict or string)

        Returns
        -------
        str
            Formatted message string with [report: ...] tag if applicable
        """
        # If already a string, pass through
        if isinstance(content, str):
            return content

        # Handle structured message types
        if isinstance(content, dict):
            msg_type = content.get("type", "")

            # Handle announcement type (preserve report tag!)
            if msg_type == "announcement":
                data = content.get("data", {})
                report = content.get("report", {})

                # Announcements are silent - update UI colors but don't show in chat
                # The UI will extract the report tag and skip displaying this message
                nl_message = f"__SILENT__ [report: {json.dumps(report)}]"
                return nl_message

            # For other structured messages, use backend_to_human
            return self.backend_to_human(sender, recipient, content)

        # Fallback for unknown types
        return str(content)

    def parse_content(self, sender: str, recipient: str, message: str) -> Any:
        """Parse received string into structured content.

        Parameters
        ----------
        sender : str
            Sender agent name
        recipient : str
            Recipient agent name
        message : str
            Received message string

        Returns
        -------
        Any
            Parsed structured content (usually dict)
        """
        # For now, just pass through strings
        # Could add parsing logic here if needed
        return message

    def human_to_backend(
        self,
        sender: str,
        recipient: str,
        nl_text: str
    ) -> Dict[str, Any]:
        """Translate human natural language to structured backend protocol.

        Parses human message to extract:
        - Type: question | proposal | acceptance | rejection | constraint
        - Requested changes: {node: color}
        - Constraints mentioned
        - Conditions (if-then statements)
        - Sentiment: positive | neutral | negative

        Parameters
        ----------
        sender : str
            Human agent name
        recipient : str
            Backend agent name
        nl_text : str
            Natural language text from human

        Returns
        -------
        Dict[str, Any]
            Structured message for backend LLM with keys:
            - type: Message type
            - requested_changes: Dict of node→color
            - constraints: List of constraints
            - conditions: List of if-then conditions
            - sentiment: positive/neutral/negative
            - original_text: Original NL text
        """
        if not self.use_llm or self.llm is None:
            return self._parse_human_message_heuristic(nl_text)

        try:
            prompt = f"""You are translating human natural language into structured messages for a graph coloring agent.

Human message: "{nl_text}"

Extract the following information:
1. **Type**: question | proposal | acceptance | rejection | constraint | info
   - question: Human is asking about something
   - proposal: Human proposes specific node colors
   - acceptance: Human accepts agent's proposal
   - rejection: Human rejects agent's proposal
   - constraint: Human states constraints (forbidden colors, requirements)
   - info: General information or commentary

2. **Requested changes**: Node-to-color assignments the human wants
   Example: {{"h1": "red", "h2": "blue"}}

3. **Constraints**: Any constraints mentioned
   - forbidden: {{"node": "h1", "colors": ["red", "green"]}}
   - required: {{"node": "h1", "color": "blue"}}

4. **Conditions**: If-then statements
   Example: [{{"if": {{"h1": "red"}}, "then": {{"h2": "blue"}}}}]

5. **Sentiment**: positive | neutral | negative
   - positive: Agreeing, happy, satisfied
   - neutral: Neutral tone, informational
   - negative: Disagreeing, unhappy, frustrated

Return ONLY a JSON object with these keys:
{{
  "type": "...",
  "requested_changes": {{}},
  "constraints": [],
  "conditions": [],
  "sentiment": "...",
  "original_text": "..."
}}
"""

            response = self.llm.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=500
            )

            result = json.loads(response.choices[0].message.content)
            result["original_text"] = nl_text
            return result

        except Exception as e:
            print(f"\n{'='*70}")
            print(f"FATAL ERROR: Speech LLM parsing failed")
            print(f"Error: {e}")
            print(f"LLM_TOOL mode requires working OpenAI API - no fallbacks allowed")
            print(f"{'='*70}\n")
            raise SystemExit(f"Speech LLM parsing FAILED: {e}") from e

    def backend_to_human(
        self,
        sender: str,
        recipient: str,
        structured: Dict[str, Any]
    ) -> str:
        """Translate backend structured output to natural language for human.

        Converts backend LLM's structured decision into natural, conversational
        language while preserving report tags for UI updates.

        Parameters
        ----------
        sender : str
            Backend agent name
        recipient : str
            Human agent name
        structured : Dict[str, Any]
            Structured output from backend LLM. Can be either:
            1. Full decision: {"message_type": "...", "structured_content": {...}}
            2. Just content: {"my_assignments": {...}, "reason": "..."}

        Returns
        -------
        str
            Natural language message with [report: {...}] tag appended

        Example
        -------
        >>> structured = {
        ...     "message_type": "proposal",
        ...     "structured_content": {
        ...         "my_assignments": {"a1": "red", "a2": "blue"},
        ...         "reason": "This resolves conflicts with your nodes"
        ...     }
        ... }
        >>> nl_message = layer.backend_to_human("Agent1", "Human", structured)
        >>> print(nl_message)
        "I propose coloring a1 red and a2 blue. This resolves conflicts with your nodes. [report: {...}]"
        """
        # Extract structured_content if it's a full decision object
        if "structured_content" in structured:
            message_type = structured.get("message_type", "info")
            content = structured.get("structured_content", {})
        else:
            # Assume it's already the content
            message_type = structured.get("message_type", "info")
            content = structured

        if not self.use_llm or self.llm is None:
            return self._render_backend_message_template_content(message_type, content)

        try:
            prompt = f"""You are translating a graph coloring agent's structured output into natural language.

Agent: {sender}
Recipient: {recipient}

Message type: {message_type}
Content:
{json.dumps(content, indent=2)}

Generate a natural, conversational message for the human.

**CRITICAL SPECIFICITY REQUIREMENTS**:
1. ALWAYS use exact node names (e.g., "h4", NOT "a neighboring node")
2. ALWAYS use exact colors (e.g., "blue", NOT "a different color")
3. Use template: "Could you change [node] from [current] to [new]?"
4. Or IF-THEN: "If you set [node]=[color], then I can set [my_node]=[color]"

**FORBIDDEN PHRASES** (NEVER use these):
❌ "make a change" / "adjust colors" / "modify nodes"
❌ "let's review" / "we should consider" / "might need to"
❌ "a neighboring node" / "some boundary nodes" / "certain colors"
❌ "reconsider the color" (without specifying which node/color)

**GOOD EXAMPLES**:
✅ "Could you change h4 from red to blue?"
✅ "If you set h1=green and h4=blue, then I can set a2=red"

**BAD EXAMPLES** (DO NOT DO THIS):
❌ "Let's review this setup to reduce conflicts"
❌ "We should modify some boundary nodes"
❌ "Could you adjust your colors?"

**Tone**: Be friendly and collaborative, but ALWAYS specific!
**Length**: 2-3 sentences maximum

Message types:
- proposal: "I propose [specific assignments]. [reason with exact nodes/colors]"
- question: "[specific question about exact nodes/colors]"
- acceptance: "That works for me. [reason]"
- rejection: "I can't do that because [reason]. How about [specific alternative]?"
- info: "[informational statement with specific nodes/colors]"

Return ONLY the natural language message (no JSON, no extra formatting).
"""

            response = self.llm.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # Reduced from 0.7 for more deterministic output
                max_tokens=300
            )

            nl_message = response.choices[0].message.content.strip()

            # CRITICAL: Validate LLM output quality
            # Log warnings for malformed patterns but DO NOT use fallbacks
            # Policy: If LLM fails, crash or use what we have - never substitute alternatives
            malformed_patterns = [
                ", ,",          # Empty item in list: "a, , b"
                ", and .",      # Trailing conjunction with nothing: "a, and ."
                ", .",          # Trailing comma-period: "a, ."
                "assigned ,",   # "assigned , node" (missing first item)
                "assigned  ,",  # Double space variant
                ", to ",        # ", to color" (missing node)
            ]

            for pattern in malformed_patterns:
                if pattern in nl_message:
                    print(f"\n{'='*70}")
                    print(f"WARNING: Speech LLM generated malformed output")
                    print(f"Pattern found: '{pattern}'")
                    print(f"Message: {nl_message}")
                    print(f"Content: {json.dumps(content, indent=2)}")
                    print(f"Policy: Using LLM output as-is (no fallbacks allowed)")
                    print(f"{'='*70}\n")
                    # Continue with LLM output - do not substitute
                    break

            # Add report tag for UI color updates (flat format for UI extraction)
            if "my_assignments" in content:
                nl_message += f" [report: {json.dumps(content['my_assignments'])}]"

            return nl_message

        except Exception as e:
            print(f"\n{'='*70}")
            print(f"FATAL ERROR: Speech LLM failed")
            print(f"Error: {e}")
            print(f"LLM_TOOL mode requires working OpenAI API - no fallbacks allowed")
            print(f"{'='*70}\n")
            raise SystemExit(f"Speech LLM FAILED: {e}") from e

    def _parse_human_message_heuristic(self, nl_text: str) -> Dict[str, Any]:
        """Parse human message using heuristic rules (fallback).

        Parameters
        ----------
        nl_text : str
            Natural language text

        Returns
        -------
        Dict[str, Any]
            Structured message
        """
        nl_lower = nl_text.lower()

        # Detect type
        if "?" in nl_text or any(q in nl_lower for q in ["what", "why", "how", "can you", "could you"]):
            msg_type = "question"
        elif any(a in nl_lower for a in ["yes", "ok", "sounds good", "agree", "accept", "works for me"]):
            msg_type = "acceptance"
        elif any(r in nl_lower for r in ["no", "can't", "won't", "refuse", "reject", "disagree"]):
            msg_type = "rejection"
        elif any(c in nl_lower for c in ["must", "can't be", "forbidden", "constraint", "requirement"]):
            msg_type = "constraint"
        elif any(p in nl_lower for p in ["propose", "suggest", "what if", "how about", "try"]):
            msg_type = "proposal"
        else:
            msg_type = "info"

        # Extract node-color assignments
        requested_changes = {}
        # Pattern: "h1 to red", "h1=red", "set h1 red", "color h1 red"
        patterns = [
            r"(\w+)\s+to\s+(\w+)",
            r"(\w+)\s*=\s*(\w+)",
            r"set\s+(\w+)\s+(\w+)",
            r"color\s+(\w+)\s+(\w+)"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, nl_lower)
            for node, color in matches:
                if color in ["red", "blue", "green", "yellow"]:
                    requested_changes[node] = color

        # Detect sentiment
        positive_words = ["good", "great", "perfect", "excellent", "yes", "agree", "works", "fine"]
        negative_words = ["no", "bad", "problem", "issue", "can't", "won't", "conflict", "wrong"]

        positive_count = sum(1 for word in positive_words if word in nl_lower)
        negative_count = sum(1 for word in negative_words if word in nl_lower)

        if positive_count > negative_count:
            sentiment = "positive"
        elif negative_count > positive_count:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        return {
            "type": msg_type,
            "requested_changes": requested_changes,
            "constraints": [],
            "conditions": [],
            "sentiment": sentiment,
            "original_text": nl_text
        }

    def _render_backend_message_template(self, structured: Dict[str, Any]) -> str:
        """Render backend message using templates (fallback).

        Parameters
        ----------
        structured : Dict[str, Any]
            Structured backend output

        Returns
        -------
        str
            Natural language message with report tag
        """
        msg_type = structured.get("message_type", "info")
        content = structured.get("structured_content", {})
        assignments = content.get("my_assignments", {})
        reason = content.get("reason", "")
        dependencies = content.get("dependencies", {})

        # Format assignments
        if assignments:
            assignment_str = ", ".join(f"{node}={color}" for node, color in assignments.items())
        else:
            assignment_str = "my current configuration"

        # Template by type
        if msg_type == "proposal":
            if dependencies:
                dep_str = ", ".join(f"{node}={color}" for node, color in dependencies.items())
                nl_message = f"I propose {assignment_str}. If you could do {dep_str}, that would help. {reason}"
            else:
                nl_message = f"I propose {assignment_str}. {reason}"
        elif msg_type == "question":
            nl_message = f"I'm wondering: {reason}"
        elif msg_type == "acceptance":
            nl_message = f"That works for me. I'll use {assignment_str}. {reason}"
        elif msg_type == "rejection":
            nl_message = f"I can't do that because {reason}. How about {assignment_str} instead?"
        else:  # info
            nl_message = f"My configuration is {assignment_str}. {reason}"

        # Add report tag (flat format for UI extraction)
        if assignments:
            nl_message += f" [report: {json.dumps(assignments)}]"

        return nl_message

    def _render_backend_message_template_content(self, msg_type: str, content: Dict[str, Any]) -> str:
        """Render backend message using templates given separate type and content.

        Parameters
        ----------
        msg_type : str
            Message type
        content : Dict[str, Any]
            Content dict with my_assignments, reason, dependencies

        Returns
        -------
        str
            Natural language message with report tag
        """
        assignments = content.get("my_assignments", {})
        reason = content.get("reason", "")
        dependencies = content.get("dependencies", {})

        # Format assignments
        if assignments:
            assignment_str = ", ".join(f"{node}={color}" for node, color in assignments.items())
        else:
            assignment_str = "my current configuration"

        # Template by type
        if msg_type == "proposal":
            if dependencies:
                dep_str = ", ".join(f"{node}={color}" for node, color in dependencies.items())
                nl_message = f"I propose {assignment_str}. If you could do {dep_str}, that would help. {reason}"
            else:
                nl_message = f"I propose {assignment_str}. {reason}"
        elif msg_type == "question":
            nl_message = f"I'm wondering: {reason}"
        elif msg_type == "acceptance":
            nl_message = f"That works for me. I'll use {assignment_str}. {reason}"
        elif msg_type == "rejection":
            nl_message = f"I can't do that because {reason}. How about {assignment_str} instead?"
        else:  # info
            nl_message = f"My configuration is {assignment_str}. {reason}"

        # Add report tag (flat format for UI extraction)
        if assignments:
            nl_message += f" [report: {json.dumps(assignments)}]"

        return nl_message

    def format_message(
        self,
        sender: str,
        recipient: str,
        message_data: Dict[str, Any]
    ) -> str:
        """Format message from backend to human (convenience method).

        This is called by agents to format their structured outputs.

        Parameters
        ----------
        sender : str
            Agent name
        recipient : str
            Human name
        message_data : Dict[str, Any]
            Structured message data

        Returns
        -------
        str
            Natural language message
        """
        return self.backend_to_human(sender, recipient, message_data)
