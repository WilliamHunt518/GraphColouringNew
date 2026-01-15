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
import threading


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

        This must never block the UI indefinitely. We run the request in a worker
        thread and enforce a hard timeout. On timeout/failure we return None so
        callers fall back to heuristic messaging.
        """
        if self.api_key is None or self.openai is None:
            return None
        try:
            print(f"[LLMCommLayer] Attempting OpenAI API call with prompt: {prompt[:60]}...")
        except Exception:
            pass

        system_message = {
            "role": "system",
            "content": "You are a helpful assistant for translating a multi-agent coordination problem into concise natural language.",
        }
        messages: List[Dict[str, str]] = [system_message]
        if self.use_history and self.conversation:
            messages.extend(self.conversation)
        messages.append({"role": "user", "content": prompt})

        result: Dict[str, Any] = {"text": None, "err": None}

        def _worker() -> None:
            try:
                self.openai.api_key = self.api_key
                try:
                    resp = self.openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        messages=messages,
                        max_tokens=max_tokens,
                        n=1,
                        request_timeout=25,
                    )
                except TypeError:
                    resp = self.openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        messages=messages,
                        max_tokens=max_tokens,
                        n=1,
                    )
                txt = resp.choices[0].message["content"].strip()
                result["text"] = txt
            except Exception as e:
                result["err"] = e

        th = threading.Thread(target=_worker, daemon=True)
        th.start()
        th.join(timeout=30.0)

        if th.is_alive():
            try:
                print("[LLMCommLayer] OpenAI call timed out (30s). Falling back to heuristic communication.")
            except Exception:
                pass
            return None

        if result.get("err") is not None:
            try:
                print(f"[LLMCommLayer] OpenAI API call failed: {result['err']}")
            except Exception:
                pass
            return None

        text = result.get("text")
        if not isinstance(text, str) or not text.strip():
            return None

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

        if self.use_history:
            self.conversation.append({"role": "user", "content": prompt})
            self.conversation.append({"role": "assistant", "content": text})

        return text

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
                # NEW STATUS-BASED FORMAT: Check if current boundary works, then report accordingly
                status = data.get("status", "UNKNOWN")

                if status == "SUCCESS":
                    # Human's current boundary works! Show success + agent's coloring
                    current_boundary = data.get("current_boundary", {})
                    my_coloring = data.get("my_coloring", {})

                    boundary_str = ", ".join([f"{k}={v}" for k, v in sorted(current_boundary.items())])
                    coloring_str = ", ".join([f"{k}={v}" for k, v in sorted(my_coloring.items())])

                    text = (
                        f"✓ SUCCESS! Your boundary ({boundary_str}) works perfectly!\n"
                        f"I colored my nodes: {coloring_str}\n"
                        f"Zero conflicts. We have a valid solution!"
                    )

                elif status == "NEED_ALTERNATIVES":
                    # Current doesn't work or is incomplete - show alternatives
                    current_boundary = data.get("current_boundary", {})
                    current_penalty = data.get("current_penalty", 0.0)
                    valid_configs = data.get("valid_configs", [])
                    message = data.get("message", "")

                    parts = []

                    # Show the problem
                    if current_boundary:
                        boundary_str = ", ".join([f"{k}={v}" for k, v in sorted(current_boundary.items())])
                        parts.append(f"✗ Your current boundary ({boundary_str}) doesn't work for me.")
                        parts.append(f"   Penalty: {current_penalty:.2f} (need 0.0 for valid coloring)")
                    else:
                        parts.append("I need you to set boundary node colors first.")

                    # Show the solution(s)
                    if valid_configs:
                        parts.append(f"\n✓ I CAN color my nodes if you use ANY of these {len(valid_configs)} boundary settings:")
                        for idx, config in enumerate(valid_configs[:5], 1):  # Show max 5
                            config_str = ", ".join([f"{k}={v}" for k, v in sorted(config.items())])
                            parts.append(f"   {idx}. {config_str}")
                        if len(valid_configs) > 5:
                            parts.append(f"   ... and {len(valid_configs) - 5} more options")
                    else:
                        parts.append("\n✗ ERROR: I found NO valid boundary configurations!")
                        parts.append("   Check if your constraints are too restrictive.")

                    text = "\n".join(parts)

                # OLD ENUMERATED FORMAT (fallback for compatibility)
                elif "valid_configs" in data and "per_node" in data:
                    valid_configs = data.get("valid_configs", [])
                    per_node = data.get("per_node", {})

                    parts = []
                    if valid_configs:
                        parts.append("Here are the complete configurations that would work for me:")
                        for idx, config in enumerate(valid_configs, 1):
                            config_str = ", ".join([f"{k}={v}" for k, v in sorted(config.items())])
                            parts.append(f"{idx}. {config_str}")
                    else:
                        parts.append("Allowed colors per node:")
                        for var, allowed in sorted(per_node.items()):
                            if isinstance(allowed, (list, tuple, set)):
                                allowed_str = ", ".join([str(a) for a in allowed])
                                parts.append(f"{var} ∈ {{{allowed_str}}}")

                    text = "\n".join(parts)

                # LEGACY FORMAT (oldest fallback)
                else:
                    parts = []
                    for var, allowed in data.items():
                        if var not in ["status", "current_boundary", "my_coloring", "message", "current_penalty", "valid_configs", "per_node"]:
                            if isinstance(allowed, (list, tuple, set)):
                                allowed_str = ", ".join([str(a) for a in allowed])
                                parts.append(f"{var} ∈ {{{allowed_str}}}")
                            else:
                                parts.append(f"{var}: {allowed}")
                    text = "Proposed constraints for your boundary nodes: " + "; ".join(parts) + "."
            elif msg_type == "cost_list" and isinstance(data, dict):
                # Two shapes are supported:
                #  1) legacy: {var: {colour: cost}}
                #  2) options: {boundary_nodes: [...], known: {...}, current: {...}, options: [...], points: {...}}
                if "options" in data and isinstance(data.get("options"), list):
                    known = data.get("known") or {}
                    boundary_nodes = data.get("boundary_nodes") or []
                    current = data.get("current") or {}
                    options = data.get("options") or []

                    # Human-readable, concise summary for LLM-U style messages.
                    # We intentionally do NOT mention penalty if the option is feasible.
                    parts = []
                    if isinstance(known, dict) and known:
                        parts.append("I currently think your boundary colours are " + ", ".join([f"{k}={v}" for k, v in known.items()]) + ".")
                    else:
                        if boundary_nodes:
                            parts.append("I can’t see all your boundary colours yet. Please confirm: " + ", ".join(boundary_nodes) + ".")
                        else:
                            parts.append("I can’t see all your boundary colours yet.")

                    # Current score (agent-local) with massive penalty for conflicts.
                    try:
                        a_score = int(current.get("agent_score", 0))
                        penalty = float(current.get("penalty", 0.0))
                        if penalty > 1e-9:
                            # Apply massive penalty (-1000 per conflict) for invalid colorings
                            effective_score = a_score - 1000
                            parts.append(f"My score: {effective_score} (base {a_score} - 1000 penalty for conflicts).")
                        else:
                            # No conflicts - report actual score
                            parts.append(f"My score: {a_score}.")
                    except Exception:
                        pass

                    # Show clear conditional proposals for all feasible configurations (top 5 by my score).
                    # INCLUDE the current setting so human sees all options clearly.
                    cur_h = current.get("human") if isinstance(current, dict) else None
                    feasible = []
                    for o in options:
                        try:
                            pen = float(o.get("penalty", 0.0))
                            if pen > 0.0:
                                continue
                            feasible.append(o)
                        except Exception:
                            continue
                    def _score(o):
                        try: return int(o.get("agent_score", 0))
                        except Exception: return 0
                    feasible.sort(key=_score, reverse=True)

                    # Show top 5 feasible options (including current if present)
                    shown = feasible[:5]
                    if shown:
                        parts.append("Here are the conflict-free configurations I can support:")
                        for idx, o in enumerate(shown, 1):
                            h = o.get("human")
                            if isinstance(h, dict) and h:
                                cond = ", ".join([f"{k}={v}" for k, v in sorted(h.items())])
                            else:
                                cond = "that setting"
                            score = int(o.get('agent_score', 0))

                            # Mark if this is the current configuration
                            is_current = isinstance(cur_h, dict) and isinstance(h, dict) and cur_h == h
                            current_marker = " ← YOUR CURRENT SETTING" if is_current else ""

                            parts.append(f"{idx}. If you set {cond}, I can score {score}.{current_marker}")
                    else:
                        # If no feasible alternatives, mention there are conflicts
                        if penalty > 1e-9:
                            parts.append("I don't see any conflict-free configurations. We need to resolve the boundary clashes first!")
                        else:
                            parts.append("I don't see any conflict-free configurations I can guarantee from my side right now.")

                    text = "\n".join(parts)
                else:
                    # legacy cost table
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

            # If an external LLM is available, ask it to rewrite the participant-facing
            # message into concise, natural dialogue (not meta-explaining the table). We
            # do NOT ...
            try:
                if recipient.lower() == "human" and self.api_key is not None and self.openai is not None:
                    style_ex = (
                        "Example style (do not copy verbatim):\n"
                        "Human: I currently have h1 and h5 both as green\n"
                        "Agent: Ok. Given those settings I can make a good colouring with score 12. "
                        "If you were to change h1 to blue, I could get 14 ...\n"
                    )
                    prompt = (
                        "You are an agent collaborating with a human on a graph-colouring coordination task.\n\n"
                        "CRITICAL RULES:\n"
                        "1. Be PRECISE and CONCRETE - state exact node names and colors\n"
                        "2. Use NUMBERS - always include scores for options\n"
                        "3. Stay ON-TOPIC - talk about ONE thing only (either proposals OR questions, not both)\n"
                        "4. Be CONCISE - maximum 2-3 sentences\n"
                        "5. NEVER use vague language like 'all is fine', 'looks good', 'maybe'\n"
                        "6. NEVER mention internal terms like 'cost list', 'mapping', 'JSON', 'penalty'\n\n"
                        "GOOD MESSAGE EXAMPLES:\n"
                        "- 'Here are your best options: 1. h1=red, h4=blue → I score 12. 2. h1=green, h4=red → I score 10.'\n"
                        "- 'I currently see h2=green, h5=blue. With these settings I can score 14.'\n"
                        "- 'There's a conflict with your current h1=red. If you change h1 to blue I can resolve it and score 11.'\n\n"
                        "BAD MESSAGE EXAMPLES (DO NOT USE):\n"
                        "- 'I think everything looks good' (too vague)\n"
                        "- 'Maybe you could try some alternatives' (no specifics)\n"
                        "- 'Let me know what you think about the penalty situation' (mentions internal terms)\n\n"
                        "TASK: Rewrite the draft message below to be clear, specific, and helpful.\n"
                        "Focus on actionable information. If showing options, list them clearly with scores.\n\n"
                        f"Agent: {sender} | Recipient: {recipient}\n"
                        f"Structured content: {content}\n"
                        f"Draft to improve: {text}\n\n"
                        "Return ONLY the improved message (no explanation):"
                    )
                    rewritten = self._call_openai(prompt, max_tokens=140)
                    if isinstance(rewritten, str) and rewritten.strip():
                        text = rewritten.strip()
            except Exception:
                pass

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
