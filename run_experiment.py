"""
run_experiment.py — thin entry point for one experiment session.

Usage::

    python run_experiment.py --config '{"participant_id": "P01", "mode": "mode1", ...}'

The --config argument is a JSON-encoded StudyConfig dict.
All parameters are optional except participant_id and mode; defaults are
applied for anything not provided.

Alternatively, for quick testing::

    python run_experiment.py --participant P01 --mode mode1 --graph study_12
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def build_default_config(participant_id: str, mode: str, graph_name: str, seed: int):
    """Return a fully populated StudyConfig with sensible defaults.

    If the GraphDef specifies its own colours / points_config / agent_configs,
    those take precedence over the global defaults.
    """
    from study.config import StudyConfig, DEFAULT_COLOURS, DEFAULT_POINTS, DEFAULT_AGENTS
    from study.graphs import get_graph, get_node_regions

    graph_def = get_graph(graph_name)
    node_regions = get_node_regions(graph_name)

    colours       = graph_def.colours       or DEFAULT_COLOURS
    points_config = graph_def.points_config or DEFAULT_POINTS
    agent_configs = graph_def.agent_configs or DEFAULT_AGENTS

    return StudyConfig(
        participant_id=participant_id,
        mode=mode,
        graph_def=graph_def,
        colours=colours,
        points_config=points_config,
        node_regions=node_regions,
        agent_configs=agent_configs,
        max_attempts=3,
        seed=seed,
        output_dir=Path("results/participants"),
    )


def config_from_dict(d: dict):
    """Reconstruct a StudyConfig from a plain dict (e.g. from --config JSON)."""
    from study.config import (
        StudyConfig, GraphDef, ColourPointsConfig, AgentConfig,
        DEFAULT_COLOURS, DEFAULT_POINTS, DEFAULT_AGENTS,
    )
    from study.graphs import get_node_regions
    from pathlib import Path as _Path

    gd = d.get("graph_def", {})
    graph_def = GraphDef(
        name=gd.get("name", "study_12"),
        nodes=gd.get("nodes", []),
        edges=[tuple(e) for e in gd.get("edges", [])],
        node_order=gd.get("node_order", []),
        layout_preset=gd.get("layout_preset", gd.get("name", "study_12")),
    )

    pcd = d.get("points_config", {})
    if pcd:
        points_config = ColourPointsConfig(
            points_by_owner=pcd.get("points_by_owner", {}),
            colours=pcd.get("colours", DEFAULT_COLOURS),
        )
    else:
        points_config = DEFAULT_POINTS

    agent_dicts = d.get("agent_configs", [])
    if agent_dicts:
        agent_configs = [
            AgentConfig(name=a["name"], preferred_colour=a["preferred_colour"])
            for a in agent_dicts
        ]
    else:
        agent_configs = DEFAULT_AGENTS

    node_regions = d.get("node_regions") or get_node_regions(graph_def.name)

    return StudyConfig(
        participant_id=d["participant_id"],
        mode=d["mode"],
        graph_def=graph_def,
        colours=d.get("colours", DEFAULT_COLOURS),
        points_config=points_config,
        node_regions=node_regions,
        agent_configs=agent_configs,
        max_attempts=d.get("max_attempts", 3),
        seed=d.get("seed", 42),
        output_dir=_Path(d.get("output_dir", "results/participants")),
        human_name=d.get("human_name", "Human"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one graph-colouring study session.")
    parser.add_argument("--config", type=str, default=None,
                        help="JSON-encoded StudyConfig dict")
    parser.add_argument("--participant", type=str, default="test",
                        help="Participant ID (ignored if --config provided)")
    parser.add_argument("--mode", type=str, default="mode1",
                        choices=["mode1", "mode2a", "mode2b"],
                        help="Study mode")
    parser.add_argument("--graph", type=str, default="study_12",
                        help="Graph preset name")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed")
    args = parser.parse_args()

    if args.config:
        d = json.loads(args.config)
        config = config_from_dict(d)
    else:
        config = build_default_config(
            participant_id=args.participant,
            mode=args.mode,
            graph_name=args.graph,
            seed=args.seed,
        )

    from study.logger import StudyLogger
    from simulation import ColourSession

    logger = StudyLogger(config.output_dir, config.participant_id)
    session = ColourSession(config, logger)
    session.run()


if __name__ == "__main__":
    main()
