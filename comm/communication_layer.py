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
from typing import Any, Dict, Tuple, Optional, List


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

        # Debug information to indicate whether LLM summarisation is enabled
        try:
            # Avoid printing during module import in test environments
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
            # ignore any printing errors in restricted environments
            pass

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

            payload = repr(content)
            # Always include mapping for machine parsing.
            # If a report payload is present, include it in a separate tag so the
            # participant UI can update the colours of neighbour nodes *only when
            # the neighbour has explicitly reported them*.
            suffix = ""
            if isinstance(report, dict) and report:
                suffix += f" [report: {repr(report)}]"
            suffix += f" [mapping: {payload}]"
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