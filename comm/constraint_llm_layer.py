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
        Experimental condition (``"C4"`` = user-centric NL,
        ``"C5"`` = agent-centric NL, ``"C6"`` = human-domain NL).
        Determines the prompt template.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        condition: str = "C4",
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

        if self._condition == "C5":
            # Agent-centric: explain what boundary node pattern lets the agent succeed
            prompt_lines = [
                f"You are helping a human player understand what colour choices to make",
                f"so that agent cluster '{agent_name}' can solve its graph colouring puzzle.",
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
                f"Identify the SINGLE MOST IMPORTANT RULE from the table above.",
                f"Express it as a simple rule (e.g. 'Keep h1 and h2 different colours').",
                f"If all combos work, say so briefly. If one colour blocks everything, name it.",
                f"1 sentence. No agent node names. No raw numbers. Natural phrasing.",
            ]
            return "\n".join(prompt_lines)

        elif self._condition == "C4":
            # User-centric: explain what pattern the human needs to follow
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
                f"Identify the SINGLE MOST IMPORTANT RULE from the table above.",
                f"Express it as a simple rule (e.g. 'Keep h1 and h2 different colours').",
                f"If all combos work, say so briefly. If one colour blocks everything, name it.",
                f"1 sentence. No agent node names. No raw numbers. Natural phrasing.",
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
                        "You are a concise constraint assistant helping a human player. "
                        "For node overlay messages: respond with exactly 2 short lines "
                        "separated by a newline character. "
                        "Line 1: ≤6 words verdict on the current colour. "
                        "Line 2: ≤10 words about alternatives or constraints. "
                        "For panel summaries: respond with exactly 1 plain English sentence. "
                        "NEVER mention agent-internal nodes (e.g. a1, a2, b1, b2). "
                        "No bullet points, no headers, no labels like 'Line 1:'."
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
        raise NotImplementedError(
            "Plain-text fallbacks are prohibited by the LLM-Only Policy. "
            "If the API fails, the run should crash. Use --use-llm for C3/C4."
        )

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

    @staticmethod
    def _format_consequence_table(all_consequence_counts: dict) -> str:
        """Format per-node consequence counts as a compact table."""
        if not all_consequence_counts:
            return ""
        lines = []
        for n, counts in sorted(all_consequence_counts.items()):
            parts = [f"{col}={cnt}" for col, cnt in sorted(counts.items())]
            lines.append(f"  {n}: {', '.join(parts)}")
        return "\n".join(lines)

    @staticmethod
    def _format_configs_summary(configs: list, max_show: int = 6) -> str:
        """Summarise a list of agent configs compactly."""
        if not configs:
            return "(none)"
        lines = []
        for cfg in configs[:max_show]:
            parts = [f"{n}={c}" for n, c in sorted(cfg.items())]
            lines.append("{" + ", ".join(parts) + "}")
        if len(configs) > max_show:
            lines.append(f"... ({len(configs)} total)")
        return "\n".join(f"  {l}" for l in lines)

    def _build_node_prompt(self, node: str, node_data: Dict[str, Any]) -> str:
        """Build a prompt for a single-node overlay summary."""
        if self._condition == "C4":
            current_colour = node_data.get("current_colour")
            configs = node_data.get("configs", [])
            all_colour_configs = node_data.get("all_colour_configs", {})
            boundary_nodes = node_data.get("boundary_nodes", [])
            all_boundary_assignments = node_data.get("all_boundary_assignments", {})
            all_consequence_counts = node_data.get("all_consequence_counts", {})

            # Build current state of ALL boundary nodes (needed for both branches)
            state_parts = []
            for n in sorted(boundary_nodes):
                col = all_boundary_assignments.get(n)
                state_parts.append(f"{n}={'?' if col is None else col}")
            current_state_str = ", ".join(state_parts) if state_parts else "(nothing assigned)"

            if not current_colour:
                joint_data = node_data.get("boundary_joint_feasibility", [])
                joint_hint = self._format_joint_table(joint_data) if joint_data else ""
                boundary_nodes_str = ", ".join(sorted(boundary_nodes))
                all_counts_table = self._format_consequence_table(all_consequence_counts)
                return (
                    f"Node {node} is not yet assigned.\n"
                    f"Boundary nodes: {boundary_nodes_str}\n"
                    f"Current state: {current_state_str}\n"
                    + (f"\nJoint feasibility:\n{joint_hint}\n" if joint_hint else "")
                    + (f"\nConsequence counts:\n{all_counts_table}\n" if all_counts_table else "")
                    + f"\nWrite exactly 2 lines:\n"
                    f"Line 1: 'Not yet set.'\n"
                    f"Line 2 (~8 words): based on the data above, give the most "
                    f"useful hint about what colour to pick or avoid for {node}. "
                    f"Only name a colour as 'avoid' if the joint feasibility table shows it fails "
                    f"in ALL combinations — otherwise say it depends on other nodes. "
                    f"No agent names. No raw numbers."
                )

            colour_counts = {col: len(cfgs) for col, cfgs in all_colour_configs.items()}

            # Format the joint table
            joint_data = node_data.get("boundary_joint_feasibility", [])
            joint_table = self._format_joint_table(joint_data) if joint_data else ""

            # Format consequence counts for ALL boundary nodes
            consequence_table = self._format_consequence_table(all_consequence_counts)

            # Summarise the actual feasible configs under current colour
            configs_summary = self._format_configs_summary(configs)

            # Classify blocked colours using the joint feasibility table where available,
            # so we only call a colour "blocked" if it fails in ALL joint combinations
            # (not just when other nodes are frozen at their current values).
            if joint_data:
                globally_blocked = sorted(
                    col for col in colour_counts
                    if not any(
                        entry["feasibility_count"] > 0
                        for entry in joint_data
                        if entry["boundary_assignment"].get(node) == col
                    )
                )
                conditionally_blocked = sorted(
                    col for col in colour_counts
                    if colour_counts[col] == 0 and col not in globally_blocked
                )
            else:
                # Fallback to marginal analysis if no joint data
                globally_blocked = sorted(col for col, cnt in colour_counts.items() if cnt == 0)
                conditionally_blocked = []
            ok_colours = sorted(col for col, cnt in colour_counts.items() if cnt > 0)

            prompt_lines = [
                f"You are helping a human understand their graph colouring choices.",
                f"The human controls boundary nodes: {', '.join(sorted(boundary_nodes))}.",
                f"The agent needs to colour its own nodes with no two adjacent nodes the same colour.",
                f"",
                f"CURRENT STATE OF ALL BOUNDARY NODES: {current_state_str}",
                f"",
            ]

            if joint_table:
                prompt_lines += [
                    f"JOINT BOUNDARY FEASIBILITY (all combos of boundary nodes -> agent configs available):",
                    joint_table,
                    f"",
                ]

            if consequence_table:
                prompt_lines += [
                    f"CONSEQUENCE COUNTS (for each boundary node, how many agent configs each colour allows, given other nodes stay fixed):",
                    consequence_table,
                    f"",
                ]

            prompt_lines += [
                f"FOCUS NODE: {node} = {current_colour}",
                f"Agent configs that work with {node}={current_colour}:",
                configs_summary,
                f"",
            ]

            if globally_blocked:
                blocked_str = " and ".join(globally_blocked)
                prompt_lines.append(
                    f"NOTE: {blocked_str} {'is' if len(globally_blocked)==1 else 'are'} "
                    f"always blocked for {node} — no joint combination with other boundary nodes rescues it."
                )
                prompt_lines.append("")
            if conditionally_blocked:
                cond_str = " and ".join(conditionally_blocked)
                prompt_lines.append(
                    f"NOTE: {cond_str} {'is' if len(conditionally_blocked)==1 else 'are'} "
                    f"currently problematic for {node} given other nodes' current colours, "
                    f"but could work if other boundary nodes also change."
                )
                prompt_lines.append("")

            prompt_lines += [
                f"Write exactly 2 short lines separated by a newline.",
                f"Line 1 (~5 words): Is {node}={current_colour} a good/limited/bad choice? Be specific.",
                f"  Good examples: 'Red works fine here', 'Blue leaves few options', 'Green fits well'.",
                f"  NEVER say 'blocks the agent' — the agent can always attempt a colouring; only say",
                f"  a colour 'rules out' or 'eliminates' the agent if it appears in the 'always blocked' note.",
                f"  For anything less severe, say it 'limits', 'tightens', or 'reduces' choices.",
                f"Line 2 (~8-10 words): Give the ONE most useful rule about {node}.",
                f"  - Look at the joint table: does {node}'s colour interact with another boundary node?",
                f"  - Look at the configs: does the agent have plenty of room, or is it squeezed?",
                f"  - If the agent can handle any colour you pick, say so clearly.",
                f"  - Only say a colour 'rules out' the agent if it appears in the 'always blocked' note above.",
                f"  - If a colour is only conditionally problematic, say it depends on other nodes.",
                f"  - If two boundary nodes together cause a problem, reference that pattern.",
                f"BANNED PHRASES: 'also works', 'offers flexibility', 'provides flexibility', 'more flexibility',",
                f"  'blocks the agent', 'agent cannot work', 'agent is stuck'.",
                f"No agent-internal node names. No raw numbers. Natural conversational phrasing.",
            ]

            return "\n".join(prompt_lines)

        elif self._condition == "C5":
            # C5 node overlays are on boundary AGENT nodes visible to the human.
            # Describe what colours that agent node can take given the human's current state.
            domain = node_data.get("domain", [])
            full_domain = node_data.get("full_domain", ["red", "green", "blue"])
            if not domain:
                return (
                    f"Agent position {node} is stuck — no colour is currently possible. "
                    f"Write exactly 1 plain English sentence saying this position is blocked and "
                    f"the human's nearby choices are causing the conflict. "
                    f"Do NOT say which specific human node to change."
                )
            if len(domain) == len(full_domain):
                return (
                    f"Agent position {node} can freely use any colour: {', '.join(sorted(domain, key=str))}. "
                    f"Write exactly 1 plain English sentence saying this position is unconstrained "
                    f"by the human's current choices."
                )
            colours_str = " or ".join(sorted(domain, key=str))
            return (
                f"Agent position {node} is limited to: {colours_str} given the human's current choices. "
                f"Write exactly 1 plain English sentence describing what this agent position can be coloured. "
                f"Frame it as what the agent CAN do, not what the human should do. No technical jargon."
            )
        elif self._condition == "C6":
            # C6: human-node domain overlay — what can the human still pick here?
            valid_colours = node_data.get("valid_colours", [])
            blocked_agents = node_data.get("blocked_agents", {})  # {colour: [agent_names]}
            current_colour = node_data.get("current_colour")
            all_assignments = node_data.get("all_assignments", {})
            all_human_nodes = node_data.get("all_human_nodes", [])
            full_domain = node_data.get("full_domain", ["red", "green", "blue"])

            # Build current state description
            state_parts = [
                f"{n}={'?' if all_assignments.get(n) is None else all_assignments[n]}"
                for n in sorted(all_human_nodes)
            ]
            current_state = ", ".join(state_parts) if state_parts else "(nothing assigned)"

            # Summarise blocked colours with reasons (agent constraints only)
            blocked_lines = []
            for col in sorted(blocked_agents.keys()):
                agents_str = " and ".join(blocked_agents[col])
                blocked_lines.append(f"  {col}: would leave {agents_str} with no valid solution")
            blocked_block = "\n".join(blocked_lines) if blocked_lines else "  (none)"

            valid_str = ", ".join(sorted(valid_colours)) if valid_colours else "(none)"

            all_blocked = not valid_colours
            all_free = (len(valid_colours) == len(full_domain))

            lines = [
                f"The human is playing a graph colouring puzzle.",
                f"They control their own cluster of nodes: {', '.join(sorted(all_human_nodes))}.",
                f"",
                f"Current state of all human nodes: {current_state}",
                f"",
                f"FOCUS NODE: {node}" + (f" (currently {current_colour})" if current_colour else " (unassigned)"),
                f"Valid colours for {node}: {valid_str}",
                f"Blocked colours for {node}:",
                blocked_block,
                f"",
                f"Write exactly 2 short lines separated by a newline.",
            ]
            if all_blocked:
                lines += [
                    f"Line 1 (~5 words): say {node} is completely stuck.",
                    f"Line 2 (~8 words): explain what needs to change to unblock it.",
                ]
            elif all_free:
                lines += [
                    f"Line 1 (~5 words): say {node} is completely free.",
                    f"Line 2 (~8 words): confirm any colour works, or give the most useful tip.",
                ]
            else:
                lines += [
                    f"Line 1 (~5 words): say which colour(s) are safe for {node}.",
                    f"Line 2 (~8 words): explain WHY those colours are problematic — say they 'leave no valid layout' or 'rule out a solution' (no agent names, no 'blocks the agent').",
                ]
            lines += [
                f"BANNED PHRASES: 'also works', 'flexibility', 'options', 'blocks the agent', 'agent is stuck'.",
                f"No agent-internal node names. Natural conversational phrasing.",
            ]
            return "\n".join(lines)

        else:
            return (
                f"Describe the constraint for node {node} in one sentence. "
                f"Data: {json.dumps(node_data, default=str)}"
            )

    def _node_plain_text_fallback(self, node: str, node_data: Dict[str, Any]) -> str:
        raise NotImplementedError(
            "Plain-text fallbacks are prohibited by the LLM-Only Policy. "
            "If the API fails, the run should crash. Use --use-llm for C3/C4."
        )

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

        prompt = self._build_node_prompt(node, node_data)
        result = self._call_api(prompt)

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
        prompt = self._build_prompt(agent_name, structured_data)
        result = self._call_api(prompt)

        # Store in cache (thread-safe write, evict if full)
        with self._lock:
            if len(self._cache) >= _MAX_CACHE:
                # Evict oldest entry (first key in insertion-ordered dict)
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
            self._cache[cache_key] = result

        return result
