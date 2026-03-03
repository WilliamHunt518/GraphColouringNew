"""ConstraintLLMLayer — presentation-only LLM layer for constraint viz mode.

Input  : precomputed structured data (feasibility counts, domain projections)
Output : short NL sentence for display in the UI (1–2 sentences)

Design notes
------------
- One instance per agent cluster; two instances run concurrently (one per agent).
- Caching: md5-keyed dict, max 256 entries, guarded by threading.Lock.
- Batching: one API call per agent per colour-change event, covering all
  constraint data for that agent.  Max 2 LLM calls per click in C3/C4.
- Fallback: if the API call fails, a plain-text formatted string is returned.
  This is intentional — the LLM layer is a *display helper*, not an
  experimental agent.  Fallback does NOT contaminate experimental data.
- Uses openai.OpenAI client (new API style, openai>=1.0.0).
- Reads api_key.txt from the project root (same as other layers).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional


_API_KEY_PATH = Path(__file__).resolve().parent.parent / "api_key.txt"
_MAX_CACHE = 256


def _load_api_key() -> Optional[str]:
    """Read the OpenAI API key from api_key.txt."""
    try:
        key = _API_KEY_PATH.read_text(encoding="utf-8").strip()
        return key if key else None
    except FileNotFoundError:
        return None


def _make_cache_key(data: Any) -> str:
    """Stable md5 key from JSON-serialisable data."""
    serialised = json.dumps(data, sort_keys=True, default=str)
    return hashlib.md5(serialised.encode()).hexdigest()


class ConstraintLLMLayer:
    """Presentation-only LLM layer.

    Parameters
    ----------
    model : str
        OpenAI model name to use for summarisation.
    condition : str
        Experimental condition (``"C3"`` = user-centric NL,
        ``"C4"`` = agent-centric NL).  Determines the prompt template.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        condition: str = "C3",
    ) -> None:
        self._model = model
        self._condition = condition
        self._api_key = _load_api_key()
        self._cache: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._client = None  # Lazy initialisation

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_client(self):
        """Lazily initialise the OpenAI client."""
        if self._client is None:
            if self._api_key is None:
                raise RuntimeError(
                    "No API key found in api_key.txt.  "
                    "Cannot call OpenAI in LLM mode."
                )
            try:
                import openai
                self._client = openai.OpenAI(api_key=self._api_key)
            except ImportError:
                raise RuntimeError(
                    "openai package not installed.  "
                    "Run: pip install openai"
                )
        return self._client

    def _build_prompt(self, agent_name: str, structured_data: Dict[str, Any]) -> str:
        """Build the LLM prompt for the given condition."""
        if self._condition == "C4":
            # Agent-centric: focus on what colour options agent nodes have
            domains = structured_data.get("domain_projection", {})
            feasibility_count = structured_data.get("feasibility_count", 0)
            is_feasible = feasibility_count > 0

            if not is_feasible:
                domain_text = "no valid colour options (infeasible)"
            else:
                parts = []
                for node, colours in sorted(domains.items()):
                    if colours:
                        parts.append(f"{node}: {{{', '.join(sorted(colours, key=str))}}}")
                    else:
                        parts.append(f"{node}: (none)")
                domain_text = "; ".join(parts) if parts else "(no data)"

            return (
                f"Given the human's current colour choices, describe in 1-2 plain English "
                f"sentences what colour options the agent '{agent_name}' has for its nodes. "
                f"Prioritise nodes with the fewest options. "
                f"If infeasible, say so clearly in one sentence. "
                f"Data: {domain_text}"
            )

        elif self._condition == "C3":
            # User-centric: focus on how human choices affect valid configurations
            consequence_counts = structured_data.get("consequence_sets", {})
            feasibility_count = structured_data.get("feasibility_count", 0)

            if not consequence_counts:
                return (
                    f"Describe in 1-2 plain English sentences how the human's current node "
                    f"colours affect the number of valid configurations for agent '{agent_name}'. "
                    f"Currently there are {feasibility_count} valid configurations. "
                    f"Suggest which colour choices are most constraining."
                )

            # Format consequence counts as readable text
            parts = []
            for node, counts in sorted(consequence_counts.items()):
                colour_counts = ", ".join(
                    f"{c}→{n}" for c, n in sorted(counts.items(), key=str)
                )
                parts.append(f"{node} ({colour_counts})")
            consequence_text = "; ".join(parts)

            return (
                f"Summarise in 1-2 plain English sentences how the human's node colours "
                f"affect the number of valid configurations for agent '{agent_name}'. "
                f"Prioritise the most constraining choices. "
                f"Data (node: colour→valid_configs): {consequence_text}"
            )

        else:
            # Unknown condition — generic summary
            return (
                f"Summarise the constraint situation for agent '{agent_name}' in 1-2 sentences. "
                f"Data: {json.dumps(structured_data, default=str)}"
            )

    def _call_api(self, prompt: str) -> str:
        """Call the OpenAI API and return the response text."""
        client = self._get_client()
        resp = client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a concise constraint assistant.  "
                        "Respond with 1-2 plain English sentences only.  "
                        "No bullet points, no headers, no extra formatting."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=120,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()

    def _plain_text_fallback(
        self, agent_name: str, structured_data: Dict[str, Any]
    ) -> str:
        """Generate a plain-text summary without any API call."""
        feasibility_count = structured_data.get("feasibility_count", 0)
        is_feasible = feasibility_count > 0

        if not is_feasible:
            repair = structured_data.get("repair_suggestion", [])
            if repair:
                repair_str = ", ".join(repair)
                return (
                    f"No valid configuration exists for {agent_name}. "
                    f"Try changing: {repair_str}."
                )
            return f"No valid configuration exists for {agent_name} with the current colours."

        if self._condition == "C4":
            domains = structured_data.get("domain_projection", {})
            constrained = [
                f"{n}: {{{', '.join(sorted(cs, key=str))}}}"
                for n, cs in sorted(domains.items())
                if len(cs) < len(structured_data.get("full_domain", ["red","green","blue"]))
            ]
            if constrained:
                return (
                    f"{agent_name} has {feasibility_count} valid configuration(s).  "
                    f"Most constrained: {'; '.join(constrained[:3])}."
                )
            return f"{agent_name} has {feasibility_count} valid configuration(s)."

        elif self._condition == "C3":
            consequence_sets = structured_data.get("consequence_sets", {})
            if consequence_sets:
                # Find the most constraining human node
                min_count_node = min(
                    consequence_sets.items(),
                    key=lambda kv: min(kv[1].values()) if kv[1] else 999,
                )
                node, counts = min_count_node
                min_count = min(counts.values())
                return (
                    f"{agent_name} has {feasibility_count} valid configuration(s).  "
                    f"Node {node}'s colour is most constraining "
                    f"(as few as {min_count} valid configs for some choices)."
                )
            return f"{agent_name} has {feasibility_count} valid configuration(s)."

        return f"{agent_name}: {feasibility_count} valid configuration(s)."

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def summarise(self, agent_name: str, structured_data: Dict[str, Any]) -> str:
        """Return a short NL summary of the constraint data.

        Thread-safe: uses a threading.Lock around the cache.  Safe to call
        from multiple threads simultaneously (one per agent cluster).

        Parameters
        ----------
        agent_name : str
            Name of the agent cluster (for display in the prompt).
        structured_data : dict
            Pre-computed constraint data dict with keys:
            - ``feasibility_count`` (int)
            - ``domain_projection`` (dict[str, list])  — C4
            - ``consequence_sets`` (dict[str, dict[str, int]])  — C3
            - ``repair_suggestion`` (list[str])  — nodes to unassign
            - ``full_domain`` (list)  — full colour domain

        Returns
        -------
        str
            1–2 sentence NL summary.  Falls back to plain text if API fails.
        """
        cache_key = _make_cache_key({"agent": agent_name, "data": structured_data})

        # Check cache (thread-safe read)
        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        # Build prompt and call API
        try:
            prompt = self._build_prompt(agent_name, structured_data)
            result = self._call_api(prompt)
        except Exception as exc:
            # Fallback to plain-text summary — this is a display helper, not
            # an experimental agent, so fallback is explicitly permitted.
            print(f"[ConstraintLLMLayer] API call failed ({exc}); using plain-text fallback.")
            result = self._plain_text_fallback(agent_name, structured_data)

        # Store in cache (thread-safe write, evict if full)
        with self._lock:
            if len(self._cache) >= _MAX_CACHE:
                # Evict oldest entry (first key in insertion-ordered dict)
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
            self._cache[cache_key] = result

        return result
