"""Communication layers.

This module provides classes that implement a communication layer
between agents.  The goal of the communication layer is to translate
internal algorithmic messages into natural-language strings and back
again.  In the original framework this role is fulfilled by large
language models (LLMs), but here we implement simple heuristics to
illustrate the mechanism without requiring network access.

Classes
-------
BaseCommLayer
    Abstract base class for communication layers.
LLMCommLayer
    Simulated LLM-based layer using heuristic formatting and parsing.
PassThroughCommLayer
    Trivial layer that returns the message unchanged.  Useful for
    algorithmic simulations where natural language is not necessary.
"""

from __future__ import annotations

import re
import ast
import os
from typing import Any, Dict, Tuple, Optional, List

import json


class BaseCommLayer:
    """Abstract communication layer.

    A communication layer must implement two operations:

    - ``format_content``: convert internal message content into a
      transmissible (e.g. natural-language) string.
    - ``parse_content``: interpret a received string back into
      structured content.

    Subclasses may also implement additional functionality, such as
    maintaining an ontology alignment between agents.
    """

    def format_content(self, sender: str, recipient: str, content: Any) -> str:
        """Format structured message content into a transmissible string.

        Parameters
        ----------
        sender : str
            Identifier of the sending agent (may be used for context).
        recipient : str
            Identifier of the receiving agent.
        content : Any
            Structured content produced by the agent's algorithm.

        Returns
        -------
        str
            A string to be transmitted to the recipient.  In this
            implementation we simply convert dictionaries to readable
            strings; other types are converted via ``str()``.
        """
        raise NotImplementedError

    def parse_content(self, sender: str, recipient: str, message: str) -> Any:
        """Parse received string into structured content.

        Parameters
        ----------
        sender : str
            Identifier of the agent who sent the message.
        recipient : str
            Identifier of the receiving agent (i.e., this agent).
        message : str
            The raw string received.

        Returns
        -------
        Any
            Structured content such as a dictionary.  Should mirror the
            structure produced by the sender's algorithm.
        """
        raise NotImplementedError


class LLMCommLayer(BaseCommLayer):
    """LLM-based communication layer.

    This layer attempts to leverage a Large Language Model (LLM) to
    translate structured messages into more human‑readable natural
    language and optionally back again.  It reads an API key from
    ``api_key.txt`` located one directory above this module.  If the
    ``openai`` library is installed and a key is available, the layer
    will call the OpenAI API to summarise outgoing structured
    messages.  Incoming messages are parsed heuristically; if
    heuristic parsing fails and an LLM is available, the layer will
    attempt to extract a dictionary by prompting the model.

    If the API key or ``openai`` package is not present, the layer
    falls back to simple formatting and parsing heuristics.
    """

    def __init__(self, *, manual: bool = False, summariser: Optional[callable] = None, use_history: bool = False) -> None:
        # manual mode flag: if True, bypass LLM calls and use provided summariser or built‑in fallback
        self.manual = manual
        # optional summariser callback used in manual mode
        self.summariser = summariser
        # attempt to read API key from api_key.txt in parent directory
        import os
        self.api_key: Optional[str] = None
        self.openai = None  # type: ignore
        # Determine path relative to this file (comm directory)
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        key_path = os.path.join(base_dir, "api_key.txt")
        if os.path.exists(key_path):
            try:
                with open(key_path, "r", encoding="utf-8") as f:
                    key = f.read().strip()
                    if key:
                        self.api_key = key
            except Exception:
                pass
        try:
            import openai  # type: ignore
            self.openai = openai
        except ImportError:
            self.openai = None

        # conversation history flag
        # When ``use_history`` is True the communication layer will retain all prompts and
        # responses passed to the LLM.  On subsequent calls the accumulated conversation
        # will be included in the prompt sent to the model.  This allows an LLM to
        # maintain context across a sequence of interactions.  If disabled (default)
        # each call is stateless and only the current prompt is sent.
        self.use_history: bool = use_history
        # list of prior messages used when ``use_history`` is enabled.  Each element
        # conforms to the OpenAI chat API format, e.g. {"role": "user", "content": "..."}.
        self.conversation: List[Dict[str, str]] = []

        # ----------------
        # Debug trace
        # ----------------
        # Record every LLM call attempt (prompt, full message list, response, and any
        # parsed/gleaned result). This is experimenter-only and is surfaced in the
        # debug window.
        self.debug_calls: List[Dict[str, Any]] = []
        self._debug_flush_cursor: int = 0

        # Debug information to indicate whether LLM summarisation is enabled
        try:
            if self.openai is None:
                print(
                    "[LLMCommLayer] OpenAI package not available. Falling back to heuristic communication."
                )
            elif self.api_key is None:
                print(
                    "[LLMCommLayer] No API key found. LLM summarisation disabled; using heuristics."
                )
            else:
                print(
                    "[LLMCommLayer] OpenAI package and API key detected. LLM summarisation enabled."
                )
        except Exception:
            pass

    def flush_debug_calls(self, path: str) -> None:
        """Append and clear accumulated debug call traces.

        Writes JSON Lines to ``path`` (one dict per line). This is intended for
        post-hoc debugging when runs fail to converge.
        """
        if self._debug_flush_cursor >= len(self.debug_calls):
            return
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except Exception:
            pass
        try:
            with open(path, "a", encoding="utf-8") as f:
                for entry in self.debug_calls[self._debug_flush_cursor:]:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                f.flush()
        except Exception:
            # never crash the experiment due to debug logging
            pass
        finally:
            self._debug_flush_cursor = len(self.debug_calls)

    def _call_openai(self, prompt: str, max_tokens: int = 60) -> Optional[str]:
        """Helper to call the OpenAI API if available.

        Returns the model's response as a string, or ``None`` if the
        API call could not be performed.  When ``use_history`` is
        enabled, previous prompts and responses are included in the
        ``messages`` argument so that the model receives conversational
        context.  On success the prompt and response are appended to
        ``self.conversation`` for future calls.
        """
        if self.api_key is None or self.openai is None:
            return None
        # debug message before making an API request
        try:
            print(f"[LLMCommLayer] Attempting OpenAI API call with prompt: {prompt[:60]}...")
        except Exception:
            pass
        try:
            # set API key
            self.openai.api_key = self.api_key
            # build chat history
            system_message = {
                "role": "system",
                "content": "You are a helpful assistant for transforming structured messages in a multi-agent coordination problem into concise natural language.",
            }
            # start with system message
            messages = [system_message]
            if self.use_history and self.conversation:
                # extend with prior conversation
                messages.extend(self.conversation)
            # append current prompt
            messages.append({"role": "user", "content": prompt})
            # call the OpenAI ChatCompletion API
            response = self.openai.ChatCompletion.create(
                model="gpt-3.5-turbo", messages=messages, max_tokens=max_tokens, n=1
            )
            # Extract the assistant's reply
            text = response.choices[0].message["content"].strip()

            # record debug trace
            try:
                self.debug_calls.append({
                    "kind": "openai_call",
                    "prompt": prompt,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "response": text,
                })
            except Exception:
                pass
            # update conversation history if enabled
            if self.use_history:
                # record the user prompt and assistant reply
                self.conversation.append({"role": "user", "content": prompt})
                self.conversation.append({"role": "assistant", "content": text})
            return text
        except Exception as exc:
            # Print debug information when an API call fails
            try:
                print(f"[LLMCommLayer] OpenAI API call failed: {exc}")
            except Exception:
                pass
            return None

    def record_debug_call(self, *, kind: str, prompt: str, messages: List[Dict[str, str]] | None, response: Any, parsed: Any = None) -> None:
        """Record a debug trace entry even when no external API is used."""
        try:
            self.debug_calls.append({
                "kind": kind,
                "prompt": prompt,
                "messages": messages,
                "response": response,
                "parsed": parsed,
            })
        except Exception:
            pass

    def build_messages(self, prompt: str) -> List[Dict[str, str]]:
        """Build the full messages list that would be sent to the OpenAI API."""
        system_message = {
            "role": "system",
            "content": "You are a helpful assistant for interpreting and rendering messages in a multi-agent coordination problem.",
        }
        messages = [system_message]
        if self.use_history and self.conversation:
            messages.extend(self.conversation)
        messages.append({"role": "user", "content": prompt})
        return messages

    def parse_assignments_from_text_llm(self, *, sender: str, recipient: str, history: List[str], text: str) -> Dict[str, str]:
        """Attempt to extract node->colour assignments from free text.

        This is primarily used for LLM-F and other LLM conditions where we want the
        agent to interpret *dialogue history*, not only the latest message.

        If an LLM API is available, the call includes history (when enabled).
        Otherwise we fall back to a simple heuristic extraction.
        """
        import re

        # Simple heuristic fallback: matches patterns like h1=red, h1 is red
        def heuristic_extract(t: str) -> Dict[str, str]:
            out: Dict[str, str] = {}
            pat = re.compile(r"\b([hab]\d+)\b\s*(?:=|is|:|->)\s*\b(red|green|blue)\b", re.IGNORECASE)
            for m in pat.finditer(t):
                out[m.group(1).lower()] = m.group(2).lower()
            return out

        # Build a prompt that includes a compact history (last few turns)
        hist = "\n".join([f"- {h}" for h in history[-6:]])
        prompt = (
            "You are interpreting dialogue in a clustered graph-colouring task. "
            "Extract any explicit node-colour assignments the human is stating or confirming. "
            "Return ONLY a JSON object mapping node ids (e.g., 'h1','h4') to colours ('red','green','blue'). "
            "If none are stated, return an empty JSON object {}.\n\n"
            f"Sender: {sender}\nRecipient: {recipient}\n\n"
            f"Recent dialogue history (most recent last):\n{hist}\n\n"
            f"Current message:\n{text}\n"
        )

        messages = self.build_messages(prompt)
        response_text = None
        parsed: Dict[str, str] = {}

        # Call the LLM if available; otherwise use heuristic.
        if (self.openai is not None) and (self.api_key is not None) and (not self.manual):
            response_text = self._call_openai(prompt, max_tokens=120)
            if response_text:
                try:
                    import json
                    tmp = json.loads(response_text)
                    if isinstance(tmp, dict):
                        parsed = {str(k).lower(): str(v).lower() for k, v in tmp.items()}
                except Exception:
                    parsed = {}
        else:
            parsed = heuristic_extract(text)
            response_text = "(manual/no-api) heuristic_extract"

        # Always record a debug trace entry so the experimenter can see the full prompt
        # even when no external API call is made.
        self.record_debug_call(kind="parse_assignments", prompt=prompt, messages=messages, response=response_text, parsed=parsed)
        return parsed

    def format_content(self, sender: str, recipient: str, content: Any) -> str:
        """Format structured content for transmission.

        If ``content`` is a dictionary and an LLM is available, the
        dictionary is summarised into a natural-language description.
        Otherwise, a simple key:value string is returned as before.
        """
        # dictionary content: build a base string and summarise if possible
        # Special-case typed envelopes used in the clustered graph-colouring study:
        #   {"type": "cost_list"|"constraints"|"free_text"|"assignments", "data": ...}
        # These should produce a participant-facing message that is NOT a meta-translation
        # (e.g. avoid "The sender is conveying..."). We attach the structured payload in
        # a hidden [mapping: ...] suffix so other agents can parse it.
        if isinstance(content, dict) and set(content.keys()) >= {"type", "data"}:
            msg_type = str(content.get("type", "")).lower()
            data = content.get("data")
            advice = content.get("advice")
            # Optional report payload for UI display (e.g., neighbour-reported boundary colours)
            # This is *not* used by the algorithm unless a receiver chooses to parse it.
            report = content.get("report")

            # Human-facing text templates
            if msg_type == "constraints" and isinstance(data, dict):
                parts = []
                for var, allowed in data.items():
                    if isinstance(allowed, (list, tuple, set)):
                        allowed_str = ", ".join([str(a) for a in allowed])
                        parts.append(f"{var} ∈ {{{allowed_str}}}")
                    else:
                        parts.append(f"{var}: {allowed}")
                text = "Proposed constraints for your boundary nodes: " + "; ".join(parts) + "."
            elif msg_type == "cost_list" and isinstance(data, dict):
                # data: {var: {colour: cost}}
                parts = []
                for var, cost_map in data.items():
                    if isinstance(cost_map, dict):
                        inner = ", ".join([f"{k}={v}" for k, v in cost_map.items()])
                        parts.append(f"{var}: {inner}")
                    else:
                        parts.append(f"{var}: {cost_map}")
                text = "Cost hints for your boundary nodes (lower is better): " + "; ".join(parts) + "."
            elif msg_type == "assignments" and isinstance(data, dict):
                # used mainly by the RB baseline; still keep it direct
                parts = ", ".join([f"{k}={v}" for k, v in data.items()])
                text = f"My current boundary assignments: {parts}."
            elif msg_type == "free_text":
                text = str(data) if data is not None else ""
            else:
                text = f"{sender} message ({msg_type}): {data}"

            # Optional advice is shown to the participant above the structured
            # hint. This is useful when the agent wants to ask the human for
            # specific help (e.g., propose a change) even in the structured
            # LLM-U/LLM-C conditions.
            if isinstance(advice, str) and advice.strip():
                text = advice.strip() + "\n\n" + text

            # Optional human-facing advice that supplements the structured hints.
            # Used when the agent wants to explicitly request help from the human.
            if isinstance(advice, str) and advice.strip():
                text = advice.strip() + "\n\n" + text

            payload = repr(content)
            # Always include mapping for machine parsing.
            # If a report payload is present, include it in a separate tag so the
            # participant UI can update the colours of neighbour nodes *only when
            # the neighbour has explicitly reported them*.
            suffix = ""
            if isinstance(report, dict) and report:
                suffix += f" [report: {repr(report)}]"
            suffix += f" [mapping: {payload}]"

            # Record a debug trace entry for rendering, even if no external LLM is used.
            try:
                self.record_debug_call(
                    kind="render_typed",
                    prompt=f"render type={msg_type} sender={sender} recipient={recipient}",
                    messages=None,
                    response=text,
                    parsed=content,
                )
            except Exception:
                pass
            return text + suffix

        if isinstance(content, dict):
            # Build a basic string representation for machine parsing.  Use str()
            # on values to handle both numeric and non-numeric entries (e.g., assignments).
            items: List[str] = []
            for key, value in content.items():
                try:
                    # format floats with three decimals
                    items.append(f"{key}:{float(value):.3f}")
                except (ValueError, TypeError):
                    # fallback to plain string for non-numeric values
                    items.append(f"{key}:{value}")
            base_msg = f"Mapping from {sender} to {recipient} -> " + ", ".join(items)
            # manual mode: call summariser if provided
            if self.manual:
                summary = None
                if self.summariser is not None:
                    try:
                        summary = self.summariser(sender, recipient, content)
                    except Exception:
                        summary = None
                if summary:
                    # include mapping for machine parsing
                    return summary + f" [mapping: {base_msg}]"
                # no summariser or summary: return base string and include mapping tag for parsing
                return base_msg + f" [mapping: {base_msg}]"
            # automatic LLM mode: if openai available, produce a summarisation
            prompt = (
                f"Given this mapping of options to scores or assignments: {content}. "
                f"Rephrase it as a concise message from {sender} to {recipient}. "
                "Avoid meta-language (e.g., do not say 'the sender is conveying'). "
                "Include the key:value pairs explicitly."
            )
            summary = self._call_openai(prompt)
            if summary:
                try:
                    print("[LLMCommLayer] Used LLM to summarise dictionary message")
                except Exception:
                    pass
                return summary + f" [mapping: {base_msg}]"
            # fallback to base string if no LLM or summariser
            try:
                print("[LLMCommLayer] Fallback to heuristic formatting for dictionary message")
            except Exception:
                pass
            # always include mapping tag for parsing
            return base_msg + f" [mapping: {base_msg}]"
        # non-dictionary: call LLM to paraphrase if possible
        msg_str = str(content)
        if self.openai is not None and self.api_key:
            prompt = f"Please paraphrase the following message for clarity: '{msg_str}'"
            response = self._call_openai(prompt)
            if response:
                try:
                    print("[LLMCommLayer] Used LLM to paraphrase string message")
                except Exception:
                    pass
                return response
            try:
                print("[LLMCommLayer] Fallback to heuristic formatting for string message")
            except Exception:
                pass
        return msg_str

    def parse_content(self, sender: str, recipient: str, message: str) -> Any:
        """Parse received string back into structured content.

        The method first attempts a heuristic parse for key:value pairs.
        If parsing fails and an LLM is available, it prompts the model
        to extract a JSON object from the message.  If both fail, the
        raw string is returned.
        """
        # If the message is already structured (e.g. a dict), return it unchanged.
        if not isinstance(message, str):
            return message
        # separate potential mapping appended in square brackets
        # e.g., "... [mapping: Scores from a1 to a2 -> red:0.500,...]"
        body = message
        mapping_found = False
        if isinstance(message, str) and "[mapping:" in message:
            try:
                _, mapping_part = message.split("[mapping:", 1)
                # remove trailing ']' and strip
                mapping_str = mapping_part.rsplit("]", 1)[0].strip()
                body = mapping_str
                mapping_found = True
            except Exception:
                body = message
        # Only attempt to heuristically parse key:value pairs when a mapping was found.
        if mapping_found:
            # First try to recover a typed payload (we use repr(content)).
            try:
                if body.startswith("{") and ("'type'" in body or '"type"' in body):
                    recovered = ast.literal_eval(body)
                    if isinstance(recovered, dict) and "type" in recovered and "data" in recovered:
                        return recovered
            except Exception:
                pass
            # remove prefix if present
            if "->" in body:
                _, body = body.split("->", 1)
            try:
                parts = [p.strip() for p in body.split(',') if p.strip()]
                parsed: Dict[str, Any] = {}
                for part in parts:
                    if ':' not in part:
                        continue
                    k, v = part.split(':', 1)
                    k = k.strip().strip("'\"")  # remove surrounding quotes from keys
                    v = v.strip().strip("'\"")  # remove surrounding quotes from values
                    # attempt to convert numeric values to float; keep non‑numeric as string
                    try:
                        parsed[k] = float(v)
                    except ValueError:
                        parsed[k] = v
                if parsed:
                    return parsed
            except Exception:
                pass
        # If no mapping was found or heuristic parsing failed, return the raw message.
        return message


class PassThroughCommLayer(BaseCommLayer):
    """Trivial communication layer that does no formatting.

    This layer simply converts content to a string via ``str()`` when
    sending, and returns the original string when receiving.  It can
    be used when natural language is not needed – for example when all
    agents share the same internal representation.
    """

    def format_content(self, sender: str, recipient: str, content: Any) -> Any:
        """Return content unchanged when possible.

        In shared-syntax mode (1Z), agents agree on a common
        representation for messages, so structured content (e.g.,
        dictionaries mapping values to scores or assignments) should
        be transmitted intact.  For other types (e.g., numbers or
        strings) we fall back to ``str()``.
        """
        # do not stringify dictionaries or other structured objects
        if isinstance(content, (dict, list, tuple)):
            return content
        return str(content)

    def parse_content(self, sender: str, recipient: str, message: Any) -> Any:
        """Return the message unchanged.

        When structured content is sent as-is, there is nothing to
        parse.  If messages are strings, users should parse them
        externally.
        """
        return message

# ---------------------------------------------------------------------------
# LLM_RB: Natural-language wrapper around the RB argumentation protocol
# ---------------------------------------------------------------------------

from comm.rb_protocol import parse_rb as _parse_rb_tag, format_rb as _format_rb_tag, pretty_rb as _pretty_rb

class LLMRBCommLayer(LLMCommLayer):
    """LLM-backed (or heuristic) translation between free text and RB moves.

    This layer enables a condition where agents use the deterministic RB
    argumentation engine, but humans can type natural language. The layer:

      * Outgoing RB moves (tagged with [rb:{...}]) are rendered into natural text,
        while preserving the [rb:...] tag for reliable parsing on the receiver.
      * Outgoing free text from the human is parsed into a single RB move
        (PROPOSE/ARGUE/ATTACK/CONCEDE/REQUEST/QUERY) and then encoded as [rb:...].
        If parsing fails, the text is passed through unchanged.

    No optimisation is performed here; it is a translation layer.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _rb_to_nl(self, rb_move: dict) -> str:
        # Accept RBMove objects from rb_protocol.parse_rb
        if hasattr(rb_move, 'to_dict'):
            rb_move = rb_move.to_dict()  # type: ignore[assignment]
        # Simple templates; keep concise for participant comprehension.
        move = (rb_move.get("move") or "").upper()
        node = rb_move.get("node")
        colour = rb_move.get("colour")
        reasons = rb_move.get("reasons") or []
        if move in ("PROPOSE", "ARGUE"):
            base = f"I suggest {node} = {colour}."
        elif move == "ATTACK":
            base = f"I don't think {node} should be {colour}."
        elif move == "CONCEDE":
            base = f"OK — I will accept {node} = {colour}."
        elif move == "REQUEST":
            base = f"Can you commit to {node} = {colour}?"
        elif move == "QUERY":
            base = f"Why {node} = {colour}?"
        else:
            base = _pretty_rb(rb_move) or str(rb_move)
        if reasons:
            base += " Reasons: " + ", ".join(reasons) + "."
        return base

    def _nl_to_rb_heuristic(self, text: str, domain) -> dict | None:
        t = (text or "").strip()
        if not t:
            return None
        # Detect node + colour mentions
        node_pat = r"\b([hab]\d+)\b"
        col_pat = r"\b(red|green|blue)\b"
        nodes = re.findall(node_pat, t.lower())
        cols = re.findall(col_pat, t.lower())
        if not nodes or not cols:
            return None
        node = nodes[0]
        colour = cols[0]
        move = "PROPOSE"
        if any(w in t.lower() for w in ["accept", "ok", "concede", "fine", "agree"]):
            move = "CONCEDE"
        elif any(w in t.lower() for w in ["why", "because", "reason"]):
            move = "QUERY"
        elif any(w in t.lower() for w in ["must", "have to", "need to"]):
            move = "ARGUE"
        elif any(w in t.lower() for w in ["not", "can't", "cannot", "avoid"]):
            move = "ATTACK"
        elif any(w in t.lower() for w in ["please", "can you", "could you", "commit"]):
            move = "REQUEST"
        reasons = []
        for r in ["avoids_boundary_conflict", "improves_local_consistency", "reduces_global_penalty", "gives_flexibility"]:
            if r.replace("_", " ") in t.lower():
                reasons.append(r)
        return {"move": move, "node": node, "colour": colour, "reasons": reasons}

    def parse_rb_from_text(self, text: str, domain) -> dict | None:
        # If API LLM is available, try it; otherwise fall back to heuristic.
        try:
            return self.parse_rb_from_text_llm(text=text, domain=domain)
        except Exception:
            return self._nl_to_rb_heuristic(text, domain)

    def parse_rb_from_text_llm(self, text: str, domain) -> dict | None:
        """Parse a single RB move from free text using an LLM (if available).

        Returns a dict with keys: move,node,colour,reasons.
        """
        # If LLM isn't configured, raise so caller uses fallback.
        if not getattr(self, "_llm_enabled", False):
            raise RuntimeError("LLM not enabled")
        schema = {
            "move": "PROPOSE|ARGUE|ATTACK|CONCEDE|REQUEST|QUERY",
            "node": "h1..h5|a1..a5|b1..b5",
            "colour": list(domain),
            "reasons": ["avoids_boundary_conflict","improves_local_consistency","reduces_global_penalty","gives_flexibility"],
        }
        prompt = (
            "Convert the user's message into ONE dialogue move for the RB protocol. "
            "Return ONLY valid JSON with keys move,node,colour,reasons. "
            "If the user mentions multiple nodes, pick the most central request.\n\n"
            f"RB schema: {json.dumps(schema)}\n\n"
            f"User message: {text}"
        )
        raw = self._call_llm(prompt)
        parsed = None
        try:
            parsed = json.loads(raw)
        except Exception:
            # Attempt to extract JSON object from text
            m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
            if m:
                parsed = json.loads(m.group(0))
        if not isinstance(parsed, dict):
            return None
        move = str(parsed.get("move") or "").upper()
        node = parsed.get("node")
        colour = parsed.get("colour")
        reasons = parsed.get("reasons") or []
        if move not in {"PROPOSE","ARGUE","ATTACK","CONCEDE","REQUEST","QUERY"}:
            return None
        if not node or not colour:
            return None
        # Trace
        try:
            self.debug_calls.append({
                "kind": "parse_rb",
                "prompt": prompt,
                "response": raw,
                "parsed": {"move": move, "node": node, "colour": colour, "reasons": reasons},
                "ts": datetime.datetime.utcnow().isoformat() + "Z",
            })
        except Exception:
            pass
        return {"move": move, "node": str(node), "colour": colour, "reasons": list(reasons)}

    def format_content(self, sender: str, recipient: str, content: Any) -> str:
        # If already RB-tagged, render to NL but keep the tag.
        if isinstance(content, str):
            rb = _parse_rb_tag(content)
            if rb is not None:
                nl = self._rb_to_nl(rb)
                # preserve original tag (and any report/mapping)
                # Strip any leading text before tag; keep tag + any trailing payloads.
                m = re.search(r"\[rb:.*\]", content)
                tag = m.group(0) if m else _format_rb_tag(rb)
                # preserve report payload if present
                rep = None
                m2 = re.search(r"\[report:.*\]", content)
                rep = m2.group(0) if m2 else ""
                return (nl + " " + tag + (" " + rep if rep else "")).strip()
            # For free text (human), try to translate into RB move and tag it.
            rb2 = self.parse_rb_from_text(content, domain=getattr(self, "domain", ["red","green","blue"]))
            if rb2 is not None:
                nl = self._rb_to_nl(rb2)
                tag = _format_rb_tag(rb2)
                return (nl + " " + tag).strip()
            return content

        # If a dict RB move is passed, format it.
        if isinstance(content, dict) and "move" in content and "node" in content:
            nl = self._rb_to_nl(content)
            tag = _format_rb_tag(content)
            return (nl + " " + tag).strip()

        return super().format_content(sender, recipient, content)

    def parse_content(self, sender: str, recipient: str, message: str) -> Any:
        # Prefer explicit RB tag if present
        if isinstance(message, str):
            rb = _parse_rb_tag(message)
            if rb is not None:
                return {"type": "rb", "data": rb}
        return super().parse_content(sender, recipient, message)