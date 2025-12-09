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
from typing import Any, Dict, Tuple, Optional


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

    def __init__(self, *, manual: bool = False, summariser: Optional[callable] = None) -> None:
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
        API call could not be performed.
        """
        if self.api_key is None or self.openai is None:
            return None
        # debug message before making an API request
        try:
            print(f"[LLMCommLayer] Attempting OpenAI API call with prompt: {prompt[:60]}...")
        except Exception:
            pass
        try:
            # set API key and call the OpenAI ChatCompletion API
            self.openai.api_key = self.api_key
            messages = [
                {
                    "role": "system",
                    "content": "You are a helpful assistant for transforming structured messages in a multi-agent coordination problem into concise natural language.",
                },
                {"role": "user", "content": prompt},
            ]
            response = self.openai.ChatCompletion.create(
                model="gpt-3.5-turbo", messages=messages, max_tokens=max_tokens, n=1
            )
            # Extract the assistant's reply
            text = response.choices[0].message["content"]
            return text.strip()
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
        # dictionary messages: format values generically (numeric or not) and summarise via LLM or manual summariser
        if isinstance(content, dict):
            # build a basic string representation that handles non-numeric values
            items = []
            for key, value in content.items():
                if isinstance(value, (int, float)):
                    items.append(f"{key}:{value:.3f}")
                else:
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
                    return summary + f" [mapping: {base_msg}]"
                # no summariser or summary: just return base string
                return base_msg
            # automatic LLM mode: if openai available, produce a summarisation
            prompt = (
                f"Given this mapping: {content}. "
                "Rephrase it as a single sentence describing the sender's current assignment or preferences and include the key:value pairs."
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
            return base_msg
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
        # if the message is not a string (e.g. a dict sent via PassThroughCommLayer),
        # simply return it unchanged.  This prevents regex operations on dicts.
        if not isinstance(message, str):
            return message
        # separate potential mapping appended in square brackets
        # e.g., "... [mapping: Scores from a1 to a2 -> red:0.500,...]"
        import json
        body: str = message
        # if '[mapping:' pattern present, extract mapping string
        if "[mapping:" in message:
            try:
                _main_text, mapping_part = message.split("[mapping:", 1)
                # remove trailing ']' and strip
                mapping_str = mapping_part.rsplit("]", 1)[0].strip()
                body = mapping_str
            except Exception:
                body = message
        # remove prefix if present
        if "->" in body:
            _prefix, body = body.split("->", 1)
        # find key:value pairs heuristically
        pairs = re.findall(r"([^,:\s]+):([\-]?[\d\.]+)", body)
        if pairs:
            scores: Dict[str, float] = {}
            for key, value in pairs:
                try:
                    scores[key.strip()] = float(value)
                except ValueError:
                    break
            if scores:
                return scores
        # if heuristics failed and LLM available, try to extract JSON
        if self.api_key and self.openai:
            prompt = (
                "Extract a JSON dictionary mapping strings to numbers from the following message. "
                "If no such mapping exists, respond with null. Message: " + message
            )
            result = self._call_openai(prompt, max_tokens=120)
            if result:
                try:
                    print("[LLMCommLayer] Used LLM to parse message to JSON")
                except Exception:
                    pass
                try:
                    obj = json.loads(result)
                    if isinstance(obj, dict):
                        # convert all values to float if possible
                        return {k: float(v) for k, v in obj.items()}
                except Exception:
                    pass
            try:
                print("[LLMCommLayer] Fallback to heuristic parsing")
            except Exception:
                pass
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