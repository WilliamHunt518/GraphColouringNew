"""Headless constraint viz test — no GUI required.

Usage:
    python test_headless_constraint.py --condition C3 --use-llm
    python test_headless_constraint.py --condition C2
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_experiment import _build_topology
from cluster_simulation import run_headless_constraint_viz


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--condition", default="C2", choices=["C1", "C2", "C3", "C4"])
    p.add_argument("--graph-preset", default="medium")
    p.add_argument("--use-llm", action="store_true", default=False)
    args = p.parse_args()

    node_names, clusters, adjacency, owners, explicit_fixed = _build_topology(
        args.graph_preset, num_fixed_nodes=1
    )

    # Determine human boundary nodes dynamically
    human_nodes = set(clusters.get("Human", []))
    boundary_hnodes = sorted(
        n for n in human_nodes
        if any(nb not in human_nodes for nb in adjacency.get(n, []))
    )
    print(f"Human boundary nodes: {boundary_hnodes}")

    colour_steps = [
        {},
        {boundary_hnodes[0]: "red"} if boundary_hnodes else {},
        {n: "blue" for n in boundary_hnodes[:2]} if len(boundary_hnodes) >= 2 else {},
        {n: "green" for n in boundary_hnodes},
    ]

    run_headless_constraint_viz(
        node_names=node_names,
        clusters=clusters,
        adjacency=adjacency,
        owners=owners,
        domain=["red", "green", "blue"],
        condition=args.condition,
        colour_steps=colour_steps,
        use_llm=args.use_llm,
        preset_fixed_nodes=explicit_fixed,
        graph_preset=args.graph_preset,
    )


if __name__ == "__main__":
    main()
