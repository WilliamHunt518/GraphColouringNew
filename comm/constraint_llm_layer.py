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
- Uses anthropic.Anthropic client.
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
    """Read the Anthropic API key from api_key.txt."""
    try:
        key = _API_KEY_PATH.read_text(encoding="utf-8-sig").strip()
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
        model: str = "claude-haiku-4-5-20251001",
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
        """Lazily initialise the Anthropic client."""
        if self._client is None:
            if self._api_key is None:
                raise RuntimeError(
                    "No API key found in api_key.txt.  "
                    "Cannot call Claude in LLM mode."
                )
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._api_key)
            except ImportError:
                raise RuntimeError(
                    "anthropic package not installed.  "
                    "Run: pip install anthropic"
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

        # Pre-analyse the joint table to give the LLM a precise classification
        # so it cannot fall back to vague "avoid X" language.
        joint_analysis_lines: list = []
        if boundary_joint:
            total_combos = len(boundary_joint)
            valid_combos = sum(1 for r in boundary_joint if r["feasibility_count"] > 0)
            if valid_combos == total_combos:
                joint_analysis_lines.append(
                    "CLASSIFICATION: ALL_OPEN — every combination of boundary node colours works. "
                    "The agent has no hard constraints on the human's choices at this stage."
                )
            else:
                # Find colours that are impossible in ALL combinations where they appear
                colour_valid: dict = {}
                for r in boundary_joint:
                    for n, c in r["boundary_assignment"].items():
                        key = (n, c)
                        if key not in colour_valid:
                            colour_valid[key] = False
                        if r["feasibility_count"] > 0:
                            colour_valid[key] = True
                always_blocked = [(n, c) for (n, c), ok in colour_valid.items() if not ok]
                conditionally_blocked = [(n, c) for (n, c), ok in colour_valid.items()
                                         if ok and any(
                                             r["feasibility_count"] == 0
                                             for r in boundary_joint
                                             if r["boundary_assignment"].get(n) == c
                                         )]
                if always_blocked:
                    blocked_strs = [f"{n}={c}" for n, c in always_blocked]
                    joint_analysis_lines.append(
                        f"HARD CONSTRAINTS (impossible in ALL joint combinations — no rescue): "
                        + ", ".join(blocked_strs)
                        + ". These MUST be described as impossible, not as preferences."
                    )
                if conditionally_blocked:
                    cond_strs = [f"{n}={c}" for n, c in conditionally_blocked]
                    joint_analysis_lines.append(
                        f"CONDITIONAL CONSTRAINTS (fail only in some combinations): "
                        + ", ".join(cond_strs)
                        + ". These MUST be described as conditional (works only if...), not as hard blocks."
                    )
                if valid_combos == 0:
                    joint_analysis_lines.append(
                        "CLASSIFICATION: INFEASIBLE — no combination works currently."
                    )

        joint_analysis = "\n".join(joint_analysis_lines)

        _output_rules = (
            "\nOUTPUT RULES — you MUST follow these:\n"
            "  - If a colour is in HARD CONSTRAINTS above → state what IS possible: e.g. 'Only red and green work' or 'h1 and h2 must differ'. Do NOT just say 'X is impossible' — the count already shows that; show the knock-on instead.\n"
            "  - If a colour is in CONDITIONAL CONSTRAINTS → say 'X only works if Y is Z'. NEVER say 'avoid'.\n"
            "  - If ALL_OPEN → say something more specific than 'all options are open' — e.g. 'The agent can handle any combination here', 'No restrictions on your boundary choices'.\n"
            "  - BANNED WORDS: 'avoid', 'prefer', 'better', 'unavailable', 'pick freely', 'all options are open' (too generic — be specific).\n"
            "  1 sentence. No agent node names. No raw numbers. Natural phrasing."
        )

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
            if joint_analysis:
                prompt_lines += ["", joint_analysis]
            prompt_lines += [
                f"",
                f"Identify the SINGLE MOST IMPORTANT RULE from the table above.",
                f"Express it as a simple, decisive rule (e.g. 'h1 and h2 must be different colours',",
                f"  'Green is impossible for h1', 'Blue only works if h2 is red').",
                _output_rules,
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
            if joint_analysis:
                prompt_lines += ["", joint_analysis]
            prompt_lines += [
                f"",
                f"Identify the SINGLE MOST IMPORTANT RULE from the table above.",
                f"Express it as a simple, decisive rule (e.g. 'h1 and h2 must be different colours',",
                f"  'Green is impossible for h1', 'Blue only works if h2 is red').",
                _output_rules,
            ]
            return "\n".join(prompt_lines)

        else:
            # Unknown condition — generic summary
            return (
                f"Summarise the constraint situation for agent '{agent_name}' in 1-2 sentences. "
                f"Data: {json.dumps(structured_data, default=str)}"
            )

    def _call_api(self, prompt: str) -> str:
        """Call the Claude API and return the response text."""
        client = self._get_client()
        resp = client.messages.create(
            model=self._model,
            system=(
                "You are a concise constraint assistant helping a human player. "
                "For node overlay messages: respond with exactly 2 short lines "
                "separated by a newline character. "
                "Line 1: ≤6 words verdict on the current colour. "
                "Line 2: ≤10 words about alternatives or constraints. "
                "For panel summaries: respond with exactly 1 plain English sentence. "
                "NEVER mention agent-internal nodes (e.g. a1, a2, b1, b2). "
                "No bullet points, no headers, no labels like 'Line 1:'."
            ),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.3,
        )
        return resp.content[0].text.strip()

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

                # Pre-classify colours from the joint table so the LLM can be precise
                colour_class_lines = []
                if joint_data and all_consequence_counts and node in all_consequence_counts:
                    counts = all_consequence_counts[node]
                    all_colours = list(counts.keys())
                    globally_impossible = [
                        col for col in all_colours
                        if not any(
                            e["feasibility_count"] > 0
                            for e in joint_data
                            if e["boundary_assignment"].get(node) == col
                        )
                    ]
                    all_fine = not globally_impossible and all(c > 0 for c in counts.values())
                    if globally_impossible:
                        colour_class_lines.append(
                            f"HARD CONSTRAINT: {', '.join(globally_impossible)} is IMPOSSIBLE for {node} "
                            f"in every joint combination — there is no scenario where it works."
                        )
                    if all_fine:
                        colour_class_lines.append(
                            f"ALL COLOURS VIABLE: every colour works for {node} at this stage."
                        )

                pre_classify = "\n".join(colour_class_lines)

                return (
                    f"Node {node} is not yet assigned.\n"
                    f"Boundary nodes: {boundary_nodes_str}\n"
                    f"Current state: {current_state_str}\n"
                    + (f"\nJoint feasibility:\n{joint_hint}\n" if joint_hint else "")
                    + (f"\nConsequence counts:\n{all_counts_table}\n" if all_counts_table else "")
                    + (f"\n{pre_classify}\n" if pre_classify else "")
                    + f"\nWrite exactly 2 short lines:\n"
                    f"Line 1 (~5 words): A brief verdict about dependency or impact — NOT a list of which colours are available.\n"
                    f"  The interface already shows counts per colour, so do NOT say 'All colours open', 'Two colours work', etc.\n"
                    f"  EXCEPTION: mention a colour only if it would surprise the user — a colour appears selectable but has ZERO valid agent configs.\n"
                    f"  Instead: say something about the situation, e.g. 'No constraint from {node} yet', 'Depends on what {boundary_nodes_str} is', 'Agent unconstrained so far'.\n"
                    f"Line 2 (~8 words): The single most decisive cross-node insight.\n"
                    f"  RULES — follow in order:\n"
                    f"  - If a colour is IMPOSSIBLE (shown above) → name the effect: e.g. 'That colour forces a conflict regardless of the other node'\n"
                    f"  - If a colour only fails in SOME combinations → say 'X works only if [other node] is Y'\n"
                    f"  - If all colours work equally → describe the cross-node freedom: e.g. 'Your choice here won't restrict the other boundary node'\n"
                    f"  - If one colour leaves significantly more agent options → say 'X gives the agent most room'\n"
                    f"  BANNED PHRASES: 'avoid', 'prefer', 'better', 'unavailable', 'X cannot be used', 'X is not viable', 'pick freely',\n"
                    f"    'All colours are open', 'N colours viable', 'all three work' — be specific, not generic.\n"
                    f"  No agent names. No raw numbers."
                )

            colour_counts = {col: len(cfgs) for col, cfgs in all_colour_configs.items()}

            # Node's explicit allowed domain (colours the UI lets the user pick).
            # Colours outside this are already excluded visually — don't mention them.
            node_allowed_domain = node_data.get("node_allowed_domain") or list(colour_counts.keys())
            node_allowed_domain_set = {str(c).lower() for c in node_allowed_domain}

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

            # Colours that are selectable by the user (in their domain) but have zero
            # agent configs — the non-obvious "surprise" worth flagging explicitly.
            agent_blocked_in_domain = [
                col for col in globally_blocked if col in node_allowed_domain_set
            ]
            # Colours excluded purely by domain restriction (already shown in UI) — don't mention.
            domain_excluded = [
                col for col in globally_blocked if col not in node_allowed_domain_set
            ]

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

            if agent_blocked_in_domain:
                # Only flag colours that appear selectable but the agent can't use
                blocked_str = " and ".join(agent_blocked_in_domain)
                prompt_lines.append(
                    f"NOTE: {blocked_str} {'is' if len(agent_blocked_in_domain)==1 else 'are'} "
                    f"always blocked for {node} — selectable by the user but no joint combination rescues it. "
                    f"This is non-obvious and worth flagging."
                )
                prompt_lines.append("")
            if domain_excluded:
                # These are already excluded in the UI — don't mention them in your output
                excl_str = " and ".join(domain_excluded)
                prompt_lines.append(
                    f"SILENT (do NOT mention): {excl_str} {'is' if len(domain_excluded)==1 else 'are'} "
                    f"excluded by a domain restriction already visible in the interface. "
                    f"Treat these as non-existent for your message."
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

            # Pre-classify the current colour so the LLM must be precise
            ok_str = " or ".join(ok_colours) if ok_colours else "another colour"
            if globally_blocked and current_colour in globally_blocked:
                verdict_class = "IMPOSSIBLE"
                verdict_guide = (
                    f"The current colour ({current_colour}) is IMPOSSIBLE — "
                    f"no joint combination of boundary nodes can rescue it. "
                    f"Line 1: a short directive — e.g. 'Switch to {ok_str}' or '{current_colour.capitalize()} won't work here'. "
                    f"Do NOT list which colours are available (the UI shows that)."
                )
            elif conditionally_blocked and current_colour in conditionally_blocked:
                verdict_class = "CONDITIONAL"
                verdict_guide = (
                    f"The current colour ({current_colour}) currently fails but COULD work if other boundary nodes change. "
                    f"Line 1: show the dependency without listing colours — e.g. 'Risky — depends on the other node' or "
                    f"'{current_colour.capitalize()} holds only if neighbours shift'."
                )
            elif ok_colours:
                # Check how many options the current colour leaves vs the best
                current_count = len(all_colour_configs.get(current_colour, []))
                max_count = max(len(cfgs) for cfgs in all_colour_configs.values()) if all_colour_configs else 1
                if max_count > 0 and current_count < max_count * 0.5:
                    verdict_class = "LIMITING"
                    verdict_guide = (
                        f"The current colour ({current_colour}) works but leaves significantly fewer options than the best alternative. "
                        f"Line 1: convey tightness without listing colours — e.g. '{current_colour.capitalize()} is tight for the agent' or 'Agent has less room here'."
                    )
                elif current_count == max_count or current_count >= max_count * 0.8:
                    verdict_class = "FINE"
                    verdict_guide = (
                        f"The current colour ({current_colour}) works well with plenty of options. "
                        f"Line 1: convey this positively without listing colours — e.g. 'Agent adapts well to this' or 'No pressure from {node} here'."
                    )
                else:
                    verdict_class = "LIMITING"
                    verdict_guide = (
                        f"The current colour ({current_colour}) is viable but somewhat restrictive. "
                        f"Line 1: convey mild restriction without listing colours — e.g. 'A bit limiting for the agent' or 'Narrows the agent's room slightly'."
                    )
            else:
                verdict_class = "UNKNOWN"
                verdict_guide = f"Line 1: brief verdict on whether {current_colour} helps or hurts — no colour listing."

            prompt_lines += [
                f"CLASSIFICATION: {verdict_class}",
                f"{verdict_guide}",
                f"",
                f"Write exactly 2 short lines separated by a newline.",
                f"Line 1 (~5 words): A brief verdict about IMPACT or DEPENDENCY — NOT a report of which colours are available.",
                f"  The interface already shows counts per colour. Do NOT say things like 'Red and green work', 'Two colours open',",
                f"  'All three viable', etc. — those restate what the human can already read.",
                f"  EXCEPTION: you MAY mention a specific colour if it would SURPRISE the user — i.e. a colour is",
                f"  selectable but has ZERO valid agent configurations (the UI count chip shows it but the agent can't use it).",
                f"  Otherwise focus on impact/dependency: e.g. 'Risky — tied to {', '.join(n for n in (node_data.get('boundary_nodes') or []) if n != node)[:20]}',",
                f"  'No knock-on from this', 'Agent adapts well', 'Switch to {ok_str}', 'Only valid if other changes'.",
                f"Line 2 (~8-10 words): The ONE most useful CROSS-NODE insight. Follow in order:",
                f"  - If IMPOSSIBLE: explain the knock-on — e.g. 'No combo with the other node rescues this' or '{ok_str} gives the agent more room'.",
                f"  - If CONDITIONAL: name the exact dependency — e.g. 'Works if the other boundary node changes to X'.",
                f"  - If LIMITING or FINE: check the consequence counts for OTHER boundary nodes.",
                f"    State the knock-on: e.g. 'This leaves the other boundary node with only one choice' or 'The other boundary node stays fully open'.",
                f"    If truly no cross-node effect, describe the agent's overall flexibility.",
                f"BANNED PHRASES (in both lines): 'avoid', 'prefer', 'better', 'also works', 'offers flexibility', 'unavailable',",
                f"  'blocks the agent', 'agent cannot work', 'X cannot be used', 'X is not viable',",
                f"  'remain equally open', 'pick freely', 'all options are open', 'all colours work', 'X colours viable'.",
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
