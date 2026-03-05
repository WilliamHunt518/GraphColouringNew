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

    @staticmethod
    def _format_joint_table(joint_data: list) -> str:
        """Format boundary joint feasibility data as a compact table for the prompt."""
        if not joint_data:
            return ""
        total = len(joint_data)
        valid_count = sum(1 for r in joint_data if r["feasibility_count"] > 0)
        lines = [f"({valid_count} valid out of {total} total combinations)"]
        for r in joint_data:
            combo_str = ", ".join(
                f"{n}={c}" for n, c in sorted(r["boundary_assignment"].items())
            )
            count = r["feasibility_count"]
            marker = "[ok]" if count > 0 else "[X]"
            lines.append(f"  {combo_str}: {marker}")
        return "\n".join(lines)

    def _build_prompt(self, agent_name: str, structured_data: Dict[str, Any]) -> str:
        """Build the LLM prompt for the given condition."""
        feasibility_count = structured_data.get("feasibility_count", 0)
        is_feasible = feasibility_count > 0
        full_domain = structured_data.get("full_domain", ["red", "green", "blue"])

        # Joint feasibility table: which boundary node colour combos let agent succeed
        boundary_joint = structured_data.get("boundary_joint_feasibility", [])
        boundary_nodes = structured_data.get("boundary_nodes", [])
        human_boundary = structured_data.get("human_boundary_partial", {})

        # Describe the human's current boundary state
        if human_boundary:
            assigned = {k: v for k, v in human_boundary.items() if v is not None}
            unassigned = [k for k, v in human_boundary.items() if v is None]
            parts = [f"{n}={c}" for n, c in sorted(assigned.items())]
            parts += [f"{n}=?" for n in sorted(unassigned)]
            current_state = ", ".join(parts) if parts else "(nothing assigned)"
        else:
            current_state = "(nothing assigned)"

        joint_table = self._format_joint_table(boundary_joint)

        if self._condition == "C4":
            # Agent-centric: explain the agent's node options and what pattern enables them
            domains = structured_data.get("domain_projection", {})

            if not is_feasible:
                agent_options = "No valid colour options — agent is currently infeasible."
            else:
                opt_parts = []
                for node, colours in sorted(domains.items()):
                    if not colours:
                        opt_parts.append(f"{node}: no options (infeasible)")
                    elif len(colours) == 1:
                        opt_parts.append(f"{node}: MUST be {colours[0]}")
                    elif len(colours) < len(full_domain):
                        opt_parts.append(f"{node}: can be {' or '.join(sorted(colours, key=str))}")
                    else:
                        opt_parts.append(f"{node}: any colour")
                agent_options = "; ".join(opt_parts) if opt_parts else "(no data)"

            prompt_lines = [
                f"You are helping a human player understand the colour options for agent cluster '{agent_name}'.",
                f"The puzzle: no two adjacent nodes may share the same colour (red, green, blue).",
                f"",
                f"Human's current boundary choices: {current_state}",
                f"Agent feasibility: {feasibility_count} valid configuration(s).",
                f"",
                f"AGENT NODE OPTIONS (given the human's current choices):",
                f"  {agent_options}",
            ]
            if joint_table:
                nodes_str = ", ".join(sorted(boundary_nodes))
                prompt_lines += [
                    f"",
                    f"WHICH HUMAN BOUNDARY COMBINATIONS ALLOW THE AGENT TO SUCCEED ({nodes_str}):",
                    joint_table,
                ]
            prompt_lines += [
                f"",
                f"Write 1-2 plain English sentences identifying the KEY PATTERN or constraint.",
                f"Focus on what's most constrained, or what the human needs to maintain.",
                f"Do NOT mention raw numbers. Be natural and specific.",
                f"Good examples:",
                f'  "With your choices, I\'m forced to use green for a2 — everything else is flexible."',
                f'  "I can solve my cluster as long as h1 and h2 aren\'t both the same colour."',
                f'  "Blue is blocked for h1 no matter what — please pick red or green."',
            ]
            return "\n".join(prompt_lines)

        elif self._condition == "C3":
            # User-centric: explain what pattern the human needs to follow
            consequence_counts = structured_data.get(
                "consequence_sets_counts",
                structured_data.get("consequence_sets", {}),
            )

            if consequence_counts:
                cons_lines = []
                for node, counts in sorted(consequence_counts.items()):
                    if isinstance(next(iter(counts.values()), 0), int):
                        colour_strs = [f"{c}->{n}" for c, n in sorted(counts.items(), key=str)]
                    else:
                        colour_strs = [f"{c}->{len(v)}" for c, v in sorted(counts.items(), key=str)]
                    cons_lines.append(f"  {node}: " + ", ".join(colour_strs))
                consequence_text = "\n".join(cons_lines)
            else:
                consequence_text = "  (no boundary nodes assigned yet)"

            prompt_lines = [
                f"You are helping a human player understand what colour choices to make",
                f"so that agent '{agent_name}' can solve its graph colouring puzzle.",
                f"The puzzle: no two adjacent nodes may share the same colour (red, green, blue).",
                f"",
                f"Human's current boundary choices: {current_state}",
                f"Agent feasibility: {feasibility_count} valid configuration(s).",
            ]
            if joint_table:
                nodes_str = ", ".join(sorted(boundary_nodes))
                prompt_lines += [
                    f"",
                    f"WHICH OF YOUR BOUNDARY COMBINATIONS ALLOW THE AGENT TO SUCCEED ({nodes_str}):",
                    joint_table,
                ]
            prompt_lines += [
                f"",
                f"HOW EACH BOUNDARY NODE CHOICE INDIVIDUALLY AFFECTS THE AGENT",
                f"(node: colour->num_valid_agent_configs if you chose that colour):",
                consequence_text,
                f"",
                f"Write 1-2 plain English sentences identifying the KEY PATTERN the human should follow.",
                f"Focus on rules like 'must differ', 'must be X', 'avoid Y', or praise if currently fine.",
                f"Do NOT mention raw numbers. Be natural and specific.",
                f"Good examples:",
                f'  "h1 and h2 just need to be different colours — any combination works as long as they\'re not the same."',
                f'  "You need h1 to be red or green; blue doesn\'t work here regardless of other choices."',
                f'  "Your current choices are perfect — the agent has plenty of options!"',
            ]
            return "\n".join(prompt_lines)

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
                        "You are a concise constraint assistant. "
                        "Respond with exactly 1 plain English sentence. "
                        "Always name specific nodes (e.g. 'a7 cannot be red'). "
                        "Never write generic statements about 'neighbouring nodes in general'. "
                        "No bullet points, no headers."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=150,
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

    @staticmethod
    def _derive_node_constraints(
        node: str,
        current_colour: str,
        configs: list,
    ) -> Dict[str, Any]:
        """Analyse valid-config list to find which agent nodes are constrained.

        Returns a dict with:
          - ``adjacent``: agent nodes that cannot take ``current_colour``
            (inferred adjacency — same-colour rule)
          - ``forced``: agent nodes that have exactly one valid colour
          - ``restricted``: agent nodes with fewer than 3 options
          - ``color_sets``: agent_node -> set of available colours
        """
        from collections import defaultdict
        color_sets: Dict[str, set] = defaultdict(set)
        for cfg in configs:
            for anode, acol in cfg.items():
                color_sets[anode].add(str(acol).lower())

        full_domain = {"red", "green", "blue"}
        cur = str(current_colour).lower()
        adjacent = {}   # anode -> available colours (cannot be cur_colour)
        forced = {}     # anode -> only valid colour
        restricted = {} # anode -> available colours (< 3 options)

        for anode, available in sorted(color_sets.items()):
            missing = full_domain - available
            if cur in missing:
                adjacent[anode] = sorted(available)
            if len(available) == 1:
                forced[anode] = next(iter(available))
            elif len(available) < 3:
                restricted[anode] = sorted(available)

        return {
            "adjacent": adjacent,
            "forced": forced,
            "restricted": restricted,
            "color_sets": {k: sorted(v) for k, v in color_sets.items()},
        }

    def _build_node_prompt(self, node: str, node_data: Dict[str, Any]) -> str:
        """Build a prompt for a single-node overlay summary."""
        if self._condition == "C3":
            current_colour = node_data.get("current_colour")
            configs = node_data.get("configs", [])
            all_colour_configs = node_data.get("all_colour_configs", {})

            if not current_colour:
                return (
                    f"Boundary node {node} is not yet assigned. "
                    f"Write exactly 1 sentence telling the user to assign it to see its effect."
                )

            if not configs:
                # Infeasible: find which other colours would be valid and sample their configs
                alternatives = []
                for col, col_cfgs in sorted(all_colour_configs.items()):
                    if col != str(current_colour).lower() and col_cfgs:
                        sample = col_cfgs[0]
                        sample_str = ", ".join(
                            f"{k}={v}" for k, v in sorted(sample.items())[:3]
                        )
                        alternatives.append(f"{node}={col} (agent e.g. {sample_str})")
                alt_str = "; or ".join(alternatives[:2]) if alternatives else "no other colour works either"
                return (
                    f"{node}={current_colour} leaves the agent cluster with no valid configuration. "
                    f"Feasible alternative(s): {alt_str}. "
                    f"Write exactly 1 sentence explaining the conflict and naming a concrete alternative "
                    f"with specific agent node assignments if available. No jargon."
                )

            # Feasible: derive specific per-agent-node constraints
            constraints = self._derive_node_constraints(node, current_colour, configs)
            adjacent = constraints["adjacent"]
            forced = constraints["forced"]

            # Build a human-readable fact list, prioritising adjacency constraints
            facts = []
            for anode in sorted(adjacent.keys()):
                available = adjacent[anode]
                if anode in forced:
                    facts.append(f"{anode} must be {forced[anode]}")
                else:
                    facts.append(
                        f"{anode} cannot be {current_colour} (can be {' or '.join(available)})"
                    )
            # If no adjacency constraints visible, show forced nodes
            if not facts:
                for anode, col in sorted(forced.items()):
                    facts.append(f"{anode} is forced to {col}")

            facts_str = "; ".join(facts[:3]) if facts else "the agent's options are flexible"
            return (
                f"The human set {node}={current_colour}. "
                f"Direct constraint on agent nodes: {facts_str}. "
                f"Write exactly 1 short sentence stating the most important specific impact. "
                f"Use node names. Example: '{node}=red means a7 cannot also be red.' "
                f"Do NOT write a generic statement about 'neighbours in general'."
            )

        elif self._condition == "C4":
            domain = node_data.get("domain", [])
            full_domain = node_data.get("full_domain", ["red", "green", "blue"])
            if not domain:
                return (
                    f"Agent node {node} has no valid colour options. "
                    f"Write exactly 1 plain English sentence saying it is infeasible."
                )
            if len(domain) == len(full_domain):
                return (
                    f"Agent node {node} can be any colour ({', '.join(sorted(full_domain, key=str))}). "
                    f"Write exactly 1 plain English sentence confirming full flexibility."
                )
            colours_str = " or ".join(sorted(domain, key=str))
            return (
                f"Agent node {node} can only be: {colours_str}. "
                f"Write exactly 1 plain English sentence describing this constraint naturally. "
                f"Do not use the word 'domain' or technical jargon."
            )
        else:
            return (
                f"Describe the constraint for node {node} in one sentence. "
                f"Data: {json.dumps(node_data, default=str)}"
            )

    def _node_plain_text_fallback(self, node: str, node_data: Dict[str, Any]) -> str:
        """Plain-text fallback for a single-node summary."""
        if self._condition == "C3":
            current_colour = node_data.get("current_colour")
            configs = node_data.get("configs", [])
            all_colour_configs = node_data.get("all_colour_configs", {})
            if not current_colour:
                return f"Assign {node} to see its effect on agent options."
            if not configs:
                # Find a feasible alternative colour
                for col, col_cfgs in sorted(all_colour_configs.items()):
                    if col != str(current_colour).lower() and col_cfgs:
                        sample = col_cfgs[0]
                        sample_str = ", ".join(f"{k}={v}" for k, v in sorted(sample.items())[:2])
                        return (
                            f"{node}={current_colour} leaves no valid agent configurations; "
                            f"try {col} instead (e.g. {sample_str})."
                        )
                return f"{node}={current_colour} leaves no valid agent configurations."
            # Derive specific constraints from valid configs
            constraints = self._derive_node_constraints(node, current_colour, configs)
            adjacent = constraints["adjacent"]
            forced = constraints["forced"]
            facts = []
            for anode in sorted(adjacent.keys()):
                if anode in forced:
                    facts.append(f"{anode} must be {forced[anode]}")
                else:
                    avail = adjacent[anode]
                    facts.append(f"{anode} cannot be {current_colour} (can be {' or '.join(avail)})")
            if not facts:
                for anode, col in sorted(forced.items()):
                    facts.append(f"{anode} forced to {col}")
            if facts:
                return f"{node}={current_colour}: {'; '.join(facts[:2])}."
            return f"{node}={current_colour} allows {len(configs)} valid agent configuration(s)."
        elif self._condition == "C4":
            domain = node_data.get("domain", [])
            if not domain:
                return f"{node} has no valid colours (infeasible)."
            return f"{node} can be: {', '.join(sorted(domain, key=str))}."
        return f"Node {node}: see constraint panel."

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def summarise_node(self, node: str, node_data: Dict[str, Any]) -> str:
        """Return a 1-sentence NL summary for a single node overlay box.

        For C3: ``node_data`` should have ``current_colour`` (str or None) and
        ``configs`` (list of agent-assignment dicts for that colour).
        For C4: ``node_data`` should have ``domain`` (list of valid colours) and
        ``full_domain`` (list of all colours).

        Thread-safe and cached.
        """
        cache_key = _make_cache_key(
            {"node": node, "condition": self._condition, "data": node_data}
        )
        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        try:
            prompt = self._build_node_prompt(node, node_data)
            result = self._call_api(prompt)
        except Exception as exc:
            print(
                f"[ConstraintLLMLayer] Node API call failed for {node} ({exc}); "
                f"using plain-text fallback."
            )
            result = self._node_plain_text_fallback(node, node_data)

        with self._lock:
            if len(self._cache) >= _MAX_CACHE:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
            self._cache[cache_key] = result

        return result

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
