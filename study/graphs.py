"""
Graph definitions for the graph-colouring trust study.

Naming convention:
  sN_3c        = N nodes, 3 colours, H-A/H-B cross links, no A-B links
  sN_3c_xab    = same + explicit AgentA-AgentB cross links
  sN_3c_c      = N+3/4/6 nodes (adds AgentC cluster), H-A/H-B/H-C cross links
  sN_3c_xabc   = same + A-B, A-C, B-C cross links

3-agent layout:  Human (top), AgentA (bottom-left), AgentB (bottom-right).
4-agent layout:  Human (top), AgentA (left), AgentB (right), AgentC (bottom).
Sequential colouring order: all H nodes, then A nodes, then B nodes [then C nodes].
"""
from __future__ import annotations

from typing import Dict

from study.config import (
    GraphDef, DEFAULT_POINTS, DEFAULT_AGENTS, POINTS_4P, AGENTS_4P,
)


# ---------------------------------------------------------------------------
# study_12  —  original 12-node graph (3 colours, medium connectivity)
# ---------------------------------------------------------------------------

_STUDY_12_NODES = ["H1", "H2", "H3", "H4", "A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4"]
_STUDY_12_REGIONS: Dict[str, str] = {
    "H1": "Human", "H2": "Human", "H3": "Human", "H4": "Human",
    "A1": "AgentA", "A2": "AgentA", "A3": "AgentA", "A4": "AgentA",
    "B1": "AgentB", "B2": "AgentB", "B3": "AgentB", "B4": "AgentB",
}

STUDY_12 = GraphDef(
    name="study_12",
    nodes=_STUDY_12_NODES,
    edges=[
        ("H1", "H2"), ("H2", "H4"), ("H4", "H3"), ("H3", "H1"),
        ("A1", "A2"), ("A2", "A4"), ("A4", "A3"), ("A3", "A1"),
        ("B1", "B2"), ("B2", "B4"), ("B4", "B3"), ("B3", "B1"),
        ("H3", "A1"), ("H4", "B1"), ("A4", "B3"), ("H2", "A2"),
    ],
    node_order=_STUDY_12_NODES,
    layout_preset="study_12",
)


# ---------------------------------------------------------------------------
# study_15  —  original 15-node graph (3 colours, medium connectivity)
# ---------------------------------------------------------------------------

_STUDY_15_NODES = [
    "H1", "H2", "H3", "H4", "H5",
    "A1", "A2", "A3", "A4", "A5",
    "B1", "B2", "B3", "B4", "B5",
]
_STUDY_15_REGIONS: Dict[str, str] = {
    "H1": "Human", "H2": "Human", "H3": "Human", "H4": "Human", "H5": "Human",
    "A1": "AgentA", "A2": "AgentA", "A3": "AgentA", "A4": "AgentA", "A5": "AgentA",
    "B1": "AgentB", "B2": "AgentB", "B3": "AgentB", "B4": "AgentB", "B5": "AgentB",
}

STUDY_15 = GraphDef(
    name="study_15",
    nodes=_STUDY_15_NODES,
    edges=[
        ("H1", "H2"), ("H2", "H3"), ("H3", "H4"), ("H4", "H5"), ("H5", "H1"),
        ("A1", "A2"), ("A2", "A3"), ("A3", "A4"), ("A4", "A5"), ("A5", "A1"),
        ("B1", "B2"), ("B2", "B3"), ("B3", "B4"), ("B4", "B5"), ("B5", "B1"),
        ("H2", "A1"), ("H5", "B1"), ("A4", "B3"),
        ("H3", "A2"), ("H4", "B2"),
    ],
    node_order=_STUDY_15_NODES,
    layout_preset="study_15",
)


# ===========================================================================
# Shared node lists and region maps — 3-agent (H, A, B)
# ===========================================================================

_S9_NODES = ["H1", "H2", "H3", "A1", "A2", "A3", "B1", "B2", "B3"]
_S9_REGIONS: Dict[str, str] = {
    "H1": "Human", "H2": "Human", "H3": "Human",
    "A1": "AgentA", "A2": "AgentA", "A3": "AgentA",
    "B1": "AgentB", "B2": "AgentB", "B3": "AgentB",
}

_S12_NODES = ["H1", "H2", "H3", "H4", "A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4"]
_S12_REGIONS = _STUDY_12_REGIONS

_S18_NODES = [
    "H1", "H2", "H3", "H4", "H5", "H6",
    "A1", "A2", "A3", "A4", "A5", "A6",
    "B1", "B2", "B3", "B4", "B5", "B6",
]
_S18_REGIONS: Dict[str, str] = {
    "H1": "Human", "H2": "Human", "H3": "Human",
    "H4": "Human", "H5": "Human", "H6": "Human",
    "A1": "AgentA", "A2": "AgentA", "A3": "AgentA",
    "A4": "AgentA", "A5": "AgentA", "A6": "AgentA",
    "B1": "AgentB", "B2": "AgentB", "B3": "AgentB",
    "B4": "AgentB", "B5": "AgentB", "B6": "AgentB",
}


# ===========================================================================
# Shared node lists and region maps — 4-agent (H, A, B, C)
# ===========================================================================

_S9C_NODES = ["H1", "H2", "H3", "A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3"]
_S9C_REGIONS: Dict[str, str] = {
    "H1": "Human", "H2": "Human", "H3": "Human",
    "A1": "AgentA", "A2": "AgentA", "A3": "AgentA",
    "B1": "AgentB", "B2": "AgentB", "B3": "AgentB",
    "C1": "AgentC", "C2": "AgentC", "C3": "AgentC",
}

_S12C_NODES = [
    "H1", "H2", "H3", "H4",
    "A1", "A2", "A3", "A4",
    "B1", "B2", "B3", "B4",
    "C1", "C2", "C3", "C4",
]
_S12C_REGIONS: Dict[str, str] = {
    "H1": "Human", "H2": "Human", "H3": "Human", "H4": "Human",
    "A1": "AgentA", "A2": "AgentA", "A3": "AgentA", "A4": "AgentA",
    "B1": "AgentB", "B2": "AgentB", "B3": "AgentB", "B4": "AgentB",
    "C1": "AgentC", "C2": "AgentC", "C3": "AgentC", "C4": "AgentC",
}

_S18C_NODES = [
    "H1", "H2", "H3", "H4", "H5", "H6",
    "A1", "A2", "A3", "A4", "A5", "A6",
    "B1", "B2", "B3", "B4", "B5", "B6",
    "C1", "C2", "C3", "C4", "C5", "C6",
]
_S18C_REGIONS: Dict[str, str] = {
    "H1": "Human", "H2": "Human", "H3": "Human",
    "H4": "Human", "H5": "Human", "H6": "Human",
    "A1": "AgentA", "A2": "AgentA", "A3": "AgentA",
    "A4": "AgentA", "A5": "AgentA", "A6": "AgentA",
    "B1": "AgentB", "B2": "AgentB", "B3": "AgentB",
    "B4": "AgentB", "B5": "AgentB", "B6": "AgentB",
    "C1": "AgentC", "C2": "AgentC", "C3": "AgentC",
    "C4": "AgentC", "C5": "AgentC", "C6": "AgentC",
}


# ===========================================================================
# Internal edge sets (within each cluster)
# ===========================================================================

# 9-node 3c: triangles (odd cycle — requires 3+ colours)
_S9_INT = [
    ("H1", "H2"), ("H2", "H3"), ("H3", "H1"),
    ("A1", "A2"), ("A2", "A3"), ("A3", "A1"),
    ("B1", "B2"), ("B2", "B3"), ("B3", "B1"),
]

_S9_INT_C = _S9_INT + [("C1", "C2"), ("C2", "C3"), ("C3", "C1")]

# 12-node 3c: quad + diagonal (creates triangle — requires 3+ colours)
_S12_INT = [
    ("H1", "H2"), ("H2", "H3"), ("H3", "H4"), ("H4", "H1"), ("H1", "H3"),
    ("A1", "A2"), ("A2", "A3"), ("A3", "A4"), ("A4", "A1"), ("A1", "A3"),
    ("B1", "B2"), ("B2", "B3"), ("B3", "B4"), ("B4", "B1"), ("B1", "B3"),
]

_S12_INT_C = _S12_INT + [
    ("C1", "C2"), ("C2", "C3"), ("C3", "C4"), ("C4", "C1"), ("C1", "C3"),
]

# 18-node: 6-cycle + 2 chords per cluster
_S18_INT = [
    ("H1", "H2"), ("H2", "H3"), ("H3", "H4"), ("H4", "H5"), ("H5", "H6"), ("H6", "H1"),
    ("H1", "H4"), ("H2", "H5"),
    ("A1", "A2"), ("A2", "A3"), ("A3", "A4"), ("A4", "A5"), ("A5", "A6"), ("A6", "A1"),
    ("A1", "A4"), ("A2", "A5"),
    ("B1", "B2"), ("B2", "B3"), ("B3", "B4"), ("B4", "B5"), ("B5", "B6"), ("B6", "B1"),
    ("B1", "B4"), ("B2", "B5"),
]

_S18_INT_C = _S18_INT + [
    ("C1", "C2"), ("C2", "C3"), ("C3", "C4"), ("C4", "C5"), ("C5", "C6"), ("C6", "C1"),
    ("C1", "C4"), ("C2", "C5"),
]


# ===========================================================================
# Cross-edge sets (inter-cluster)
# ===========================================================================

# --- H-A and H-B (shared by 3-agent and 4-agent variants) ---
_S9_CROSS_HAB  = [("H1", "A1"), ("H2", "A2"), ("H3", "B1"), ("H3", "B2")]
_S12_CROSS_HAB = [("H2", "A1"), ("H2", "A2"), ("H3", "A2"), ("H4", "B1"), ("H4", "B2"), ("H3", "B1")]
_S18_CROSS_HAB = [("H3", "A1"), ("H4", "A2"), ("H4", "A3"), ("H5", "B1"), ("H6", "B2"), ("H6", "B3")]

# --- H-C cross edges (for 4-agent variants) ---
_S9_CROSS_HC  = [("H2", "C1"), ("H3", "C2")]
_S12_CROSS_HC = [("H3", "C1"), ("H4", "C2"), ("H3", "C2")]
_S18_CROSS_HC = [("H4", "C1"), ("H5", "C2"), ("H4", "C3")]

# --- A-B edges (xab / xabc variants) ---
_S9_AB  = [("A3", "B3"), ("A1", "B1")]
_S12_AB = [("A4", "B3"), ("A3", "B4")]
_S18_AB = [("A5", "B3"), ("A6", "B4"), ("A5", "B5")]

# --- A-C and B-C edges (xabc variants only) ---
_S9_AC  = [("A1", "C1"), ("A3", "C3")]
_S9_BC  = [("B1", "C1"), ("B3", "C3")]

_S12_AC = [("A4", "C2"), ("A3", "C1")]
_S12_BC = [("B4", "C3"), ("B3", "C1")]

_S18_AC = [("A5", "C3"), ("A6", "C4"), ("A5", "C5")]
_S18_BC = [("B5", "C3"), ("B6", "C4"), ("B5", "C5")]


# ===========================================================================
# 9-node 3-agent graphs
# ===========================================================================

S9_3C = GraphDef(
    name="s9_3c",
    nodes=_S9_NODES,
    edges=_S9_INT + _S9_CROSS_HAB,
    node_order=_S9_NODES,
    layout_preset="s9",
    colours=["red", "blue", "green"],
    points_config=DEFAULT_POINTS,
    agent_configs=DEFAULT_AGENTS,
)

S9_3C_XAB = GraphDef(
    name="s9_3c_xab",
    nodes=_S9_NODES,
    edges=_S9_INT + _S9_CROSS_HAB + _S9_AB,
    node_order=_S9_NODES,
    layout_preset="s9",
    colours=["red", "blue", "green"],
    points_config=DEFAULT_POINTS,
    agent_configs=DEFAULT_AGENTS,
)


# ===========================================================================
# 12-node 3-agent graphs
# ===========================================================================

S12_3C = GraphDef(
    name="s12_3c",
    nodes=_S12_NODES,
    edges=_S12_INT + _S12_CROSS_HAB,
    node_order=_S12_NODES,
    layout_preset="study_12",
    colours=["red", "blue", "green"],
    points_config=DEFAULT_POINTS,
    agent_configs=DEFAULT_AGENTS,
)

S12_3C_XAB = GraphDef(
    name="s12_3c_xab",
    nodes=_S12_NODES,
    edges=_S12_INT + _S12_CROSS_HAB + _S12_AB,
    node_order=_S12_NODES,
    layout_preset="study_12",
    colours=["red", "blue", "green"],
    points_config=DEFAULT_POINTS,
    agent_configs=DEFAULT_AGENTS,
)


# ===========================================================================
# 18-node 3-agent graphs
# ===========================================================================

S18_3C = GraphDef(
    name="s18_3c",
    nodes=_S18_NODES,
    edges=_S18_INT + _S18_CROSS_HAB,
    node_order=_S18_NODES,
    layout_preset="s18",
    colours=["red", "blue", "green"],
    points_config=DEFAULT_POINTS,
    agent_configs=DEFAULT_AGENTS,
)

S18_3C_XAB = GraphDef(
    name="s18_3c_xab",
    nodes=_S18_NODES,
    edges=_S18_INT + _S18_CROSS_HAB + _S18_AB,
    node_order=_S18_NODES,
    layout_preset="s18",
    colours=["red", "blue", "green"],
    points_config=DEFAULT_POINTS,
    agent_configs=DEFAULT_AGENTS,
)


# ===========================================================================
# 12-node 4-agent graphs  (s9 + C cluster = 12 total)
# ===========================================================================

S9_3C_C = GraphDef(
    name="s9_3c_c",
    nodes=_S9C_NODES,
    edges=_S9_INT_C + _S9_CROSS_HAB + _S9_CROSS_HC,
    node_order=_S9C_NODES,
    layout_preset="s9_c",
    colours=["red", "blue", "green"],
    points_config=POINTS_4P,
    agent_configs=AGENTS_4P,
)

S9_3C_XABC = GraphDef(
    name="s9_3c_xabc",
    nodes=_S9C_NODES,
    edges=_S9_INT_C + _S9_CROSS_HAB + _S9_CROSS_HC + _S9_AB + _S9_AC + _S9_BC,
    node_order=_S9C_NODES,
    layout_preset="s9_c",
    colours=["red", "blue", "green"],
    points_config=POINTS_4P,
    agent_configs=AGENTS_4P,
)


# ===========================================================================
# 16-node 4-agent graphs  (s12 + C cluster = 16 total)
# ===========================================================================

S12_3C_C = GraphDef(
    name="s12_3c_c",
    nodes=_S12C_NODES,
    edges=_S12_INT_C + _S12_CROSS_HAB + _S12_CROSS_HC,
    node_order=_S12C_NODES,
    layout_preset="s12_c",
    colours=["red", "blue", "green"],
    points_config=POINTS_4P,
    agent_configs=AGENTS_4P,
)

S12_3C_XABC = GraphDef(
    name="s12_3c_xabc",
    nodes=_S12C_NODES,
    edges=_S12_INT_C + _S12_CROSS_HAB + _S12_CROSS_HC + _S12_AB + _S12_AC + _S12_BC,
    node_order=_S12C_NODES,
    layout_preset="s12_c",
    colours=["red", "blue", "green"],
    points_config=POINTS_4P,
    agent_configs=AGENTS_4P,
)


# ===========================================================================
# 24-node 4-agent graphs  (s18 + C cluster = 24 total)
# ===========================================================================

S18_3C_C = GraphDef(
    name="s18_3c_c",
    nodes=_S18C_NODES,
    edges=_S18_INT_C + _S18_CROSS_HAB + _S18_CROSS_HC,
    node_order=_S18C_NODES,
    layout_preset="s18_c",
    colours=["red", "blue", "green"],
    points_config=POINTS_4P,
    agent_configs=AGENTS_4P,
)

S18_3C_XABC = GraphDef(
    name="s18_3c_xabc",
    nodes=_S18C_NODES,
    edges=_S18_INT_C + _S18_CROSS_HAB + _S18_CROSS_HC + _S18_AB + _S18_AC + _S18_BC,
    node_order=_S18C_NODES,
    layout_preset="s18_c",
    colours=["red", "blue", "green"],
    points_config=POINTS_4P,
    agent_configs=AGENTS_4P,
)


# ===========================================================================
# Hub-topology graphs
#
# Each cluster is a star: one hub node connected to all satellites.
# Human hub (H1) connects directly to agent hub nodes, so the human's
# very first choice cascades through the hub to block an entire colour
# from all of the agent's satellite nodes.
#
# Variants:
#   hub12      — 12 nodes (4 each), cross-edges H1-A1 and H1-B1
#   hub12_tri  — same + A1-B1 edge, closing a 3-hub triangle; forces all
#                three hubs to distinct colours
#   hub15_deep — 15 nodes (5 each), hub triangle + H2-A1 and H3-B1 so
#                two human satellite nodes also constrain each agent hub
# ===========================================================================

_HUB12_NODES = ["H1", "H2", "H3", "H4", "A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4"]
_HUB12_REGIONS: Dict[str, str] = {
    "H1": "Human", "H2": "Human", "H3": "Human", "H4": "Human",
    "A1": "AgentA", "A2": "AgentA", "A3": "AgentA", "A4": "AgentA",
    "B1": "AgentB", "B2": "AgentB", "B3": "AgentB", "B4": "AgentB",
}

_HUB15_NODES = [
    "H1", "H2", "H3", "H4", "H5",
    "A1", "A2", "A3", "A4", "A5",
    "B1", "B2", "B3", "B4", "B5",
]
_HUB15_REGIONS: Dict[str, str] = {
    "H1": "Human", "H2": "Human", "H3": "Human", "H4": "Human", "H5": "Human",
    "A1": "AgentA", "A2": "AgentA", "A3": "AgentA", "A4": "AgentA", "A5": "AgentA",
    "B1": "AgentB", "B2": "AgentB", "B3": "AgentB", "B4": "AgentB", "B5": "AgentB",
}

# Star interiors — hub connects to every satellite
_HUB12_INT = [
    ("H1", "H2"), ("H1", "H3"), ("H1", "H4"),
    ("A1", "A2"), ("A1", "A3"), ("A1", "A4"),
    ("B1", "B2"), ("B1", "B3"), ("B1", "B4"),
]

_HUB15_INT = [
    ("H1", "H2"), ("H1", "H3"), ("H1", "H4"), ("H1", "H5"),
    ("A1", "A2"), ("A1", "A3"), ("A1", "A4"), ("A1", "A5"),
    ("B1", "B2"), ("B1", "B3"), ("B1", "B4"), ("B1", "B5"),
]

# Cross-edge building blocks
_HUB_CROSS_HA  = [("H1", "A1")]
_HUB_CROSS_HB  = [("H1", "B1")]
_HUB_TRI       = [("A1", "B1")]            # closes the 3-hub triangle
_HUB15_EXTRA   = [("H2", "A1"), ("H3", "B1")]  # satellite→hub, double-constrains hubs


HUB12 = GraphDef(
    name="hub12",
    nodes=_HUB12_NODES,
    edges=_HUB12_INT + _HUB_CROSS_HA + _HUB_CROSS_HB,
    node_order=_HUB12_NODES,
    layout_preset="hub12",
    colours=["red", "blue", "green"],
    points_config=DEFAULT_POINTS,
    agent_configs=DEFAULT_AGENTS,
)

HUB12_TRI = GraphDef(
    name="hub12_tri",
    nodes=_HUB12_NODES,
    edges=_HUB12_INT + _HUB_CROSS_HA + _HUB_CROSS_HB + _HUB_TRI,
    node_order=_HUB12_NODES,
    layout_preset="hub12",
    colours=["red", "blue", "green"],
    points_config=DEFAULT_POINTS,
    agent_configs=DEFAULT_AGENTS,
)

HUB15_DEEP = GraphDef(
    name="hub15_deep",
    nodes=_HUB15_NODES,
    edges=_HUB15_INT + _HUB_CROSS_HA + _HUB_CROSS_HB + _HUB_TRI + _HUB15_EXTRA,
    node_order=_HUB15_NODES,
    layout_preset="hub15",
    colours=["red", "blue", "green"],
    points_config=DEFAULT_POINTS,
    agent_configs=DEFAULT_AGENTS,
)


# ---------------------------------------------------------------------------
# hub18 — 18 nodes (6 per cluster), hub topology enriched with extra links
#
# Internal structure (per cluster): star hub→all-5-satellites plus two
# satellite-pair edges (X2-X3 and X4-X5), creating local triangles with
# the hub and adding intra-cluster colour pressure.
#
# Cross-edge structure:
#   Hub triangle:     H1-A1, H1-B1, A1-B1  (forces all 3 hubs to distinct colours)
#   H→A satellite:   H3-A2  (H3 is in the H2-H3 pair; A2 is in the A2-A3 pair)
#   H→B satellite:   H5-B3  (H5 is in the H4-H5 pair; B3 is in the B2-B3 pair)
#   A↔B satellite:   A4-B4  (A4 is in the A4-A5 pair; B4 is in the B4-B5 pair)
#
# Cascade example (H1=Red):
#   A1≠Red, B1≠Red, A1≠B1 → hubs get Blue/Green in some order.
#   If A1=Blue → A2,A3,A4,A5,A6≠Blue; A2-A3 edge further constrains A2,A3.
#   H3 (in the H2-H3 pair, so H3≠H2) also constrains A2 via H3-A2.
#   A4-B4 edge means A4's colour also restricts B4.
# ---------------------------------------------------------------------------

_HUB18_NODES = [
    "H1", "H2", "H3", "H4", "H5", "H6",
    "A1", "A2", "A3", "A4", "A5", "A6",
    "B1", "B2", "B3", "B4", "B5", "B6",
]
_HUB18_REGIONS: Dict[str, str] = {
    "H1": "Human", "H2": "Human", "H3": "Human",
    "H4": "Human", "H5": "Human", "H6": "Human",
    "A1": "AgentA", "A2": "AgentA", "A3": "AgentA",
    "A4": "AgentA", "A5": "AgentA", "A6": "AgentA",
    "B1": "AgentB", "B2": "AgentB", "B3": "AgentB",
    "B4": "AgentB", "B5": "AgentB", "B6": "AgentB",
}

# Star (hub→all satellites) + two satellite-pair edges per cluster
_HUB18_INT = [
    ("H1", "H2"), ("H1", "H3"), ("H1", "H4"), ("H1", "H5"), ("H1", "H6"),
    ("H2", "H3"), ("H4", "H5"),
    ("A1", "A2"), ("A1", "A3"), ("A1", "A4"), ("A1", "A5"), ("A1", "A6"),
    ("A2", "A3"), ("A4", "A5"),
    ("B1", "B2"), ("B1", "B3"), ("B1", "B4"), ("B1", "B5"), ("B1", "B6"),
    ("B2", "B3"), ("B4", "B5"),
]

# Hub triangle + satellite cross-links threading through the satellite pairs
_HUB18_CROSS = [
    ("H1", "A1"), ("H1", "B1"), ("A1", "B1"),  # hub triangle
    ("H3", "A2"),                                # H2-H3 pair → A2-A3 pair
    ("H5", "B3"),                                # H4-H5 pair → B2-B3 pair
    ("A4", "B4"),                                # A4-A5 pair ↔ B4-B5 pair
]

HUB18 = GraphDef(
    name="hub18",
    nodes=_HUB18_NODES,
    edges=_HUB18_INT + _HUB18_CROSS,
    node_order=_HUB18_NODES,
    layout_preset="hub18",
    colours=["red", "blue", "green"],
    points_config=DEFAULT_POINTS,
    agent_configs=DEFAULT_AGENTS,
)


# ---------------------------------------------------------------------------
# hub18b — asymmetric variant of hub18
#
# Each cluster has a different internal sub-structure so the constraint
# patterns differ noticeably between agents:
#
#   Human  — hub + H2-H3-H4 chain (two triangles with hub: H1-H2-H3 and
#             H1-H3-H4); H5 and H6 hang freely off the hub.
#   AgentA — hub + two separate satellite pairs (A3-A4, A5-A6); A2 hangs
#             freely. The two pairs are independent of each other.
#   AgentB — hub + B2-B3-B4 chain (same topology as human's chain, but
#             differently wired cross-cluster); B5 and B6 hang freely.
#
# Cross-edges (all distinct from hub18):
#   Hub triangle:   H1-A1, H1-B1, A1-B1
#   H4→A3          (chain-end of human → first member of A's A3-A4 pair)
#   H2→B2          (chain-start of human → chain-start of B)
#   A6↔B6          (the free leaves of A and B are cross-linked)
#
# Result: human choices propagate differently into A (via H4) and B (via H2).
# A6-B6 creates a lateral constraint independent of the hub chain.
# ---------------------------------------------------------------------------

_HUB18B_INT = [
    # Human: hub star + H2-H3-H4 chain
    ("H1", "H2"), ("H1", "H3"), ("H1", "H4"), ("H1", "H5"), ("H1", "H6"),
    ("H2", "H3"), ("H3", "H4"),
    # AgentA: hub star + two disjoint satellite pairs
    ("A1", "A2"), ("A1", "A3"), ("A1", "A4"), ("A1", "A5"), ("A1", "A6"),
    ("A3", "A4"), ("A5", "A6"),
    # AgentB: hub star + B2-B3-B4 chain
    ("B1", "B2"), ("B1", "B3"), ("B1", "B4"), ("B1", "B5"), ("B1", "B6"),
    ("B2", "B3"), ("B3", "B4"),
]

_HUB18B_CROSS = [
    ("H1", "A1"), ("H1", "B1"), ("A1", "B1"),  # hub triangle
    ("H4", "A3"),                                # human chain-end → A's A3-A4 pair
    ("H2", "B2"),                                # human chain-start → B's chain-start
    ("A6", "B6"),                                # free leaves cross-linked
]

HUB18B = GraphDef(
    name="hub18b",
    nodes=_HUB18_NODES,
    edges=_HUB18B_INT + _HUB18B_CROSS,
    node_order=_HUB18_NODES,
    layout_preset="hub18b",
    colours=["red", "blue", "green"],
    points_config=DEFAULT_POINTS,
    agent_configs=DEFAULT_AGENTS,
)


# ===========================================================================
# Registry
# ===========================================================================

GRAPH_CONFIGS = {
    "study_12":      STUDY_12,
    "study_15":      STUDY_15,
    # 9-node 3-agent
    "s9_3c":         S9_3C,
    "s9_3c_xab":     S9_3C_XAB,
    # 12-node 3-agent
    "s12_3c":        S12_3C,
    "s12_3c_xab":    S12_3C_XAB,
    # 18-node 3-agent
    "s18_3c":        S18_3C,
    "s18_3c_xab":    S18_3C_XAB,
    # 12-node 4-agent (s9 + C)
    "s9_3c_c":       S9_3C_C,
    "s9_3c_xabc":    S9_3C_XABC,
    # 16-node 4-agent (s12 + C)
    "s12_3c_c":      S12_3C_C,
    "s12_3c_xabc":   S12_3C_XABC,
    # 24-node 4-agent (s18 + C)
    "s18_3c_c":      S18_3C_C,
    "s18_3c_xabc":   S18_3C_XABC,
    # hub-topology 3-agent
    "hub12":         HUB12,
    "hub12_tri":     HUB12_TRI,
    "hub15_deep":    HUB15_DEEP,
    "hub18":         HUB18,
    "hub18b":        HUB18B,
}

NODE_REGIONS = {
    "study_12":      _STUDY_12_REGIONS,
    "study_15":      _STUDY_15_REGIONS,
    "s9_3c":         _S9_REGIONS,
    "s9_3c_xab":     _S9_REGIONS,
    "s12_3c":        _S12_REGIONS,
    "s12_3c_xab":    _S12_REGIONS,
    "s18_3c":        _S18_REGIONS,
    "s18_3c_xab":    _S18_REGIONS,
    "s9_3c_c":       _S9C_REGIONS,
    "s9_3c_xabc":    _S9C_REGIONS,
    "s12_3c_c":      _S12C_REGIONS,
    "s12_3c_xabc":   _S12C_REGIONS,
    "s18_3c_c":      _S18C_REGIONS,
    "s18_3c_xabc":   _S18C_REGIONS,
    "hub12":         _HUB12_REGIONS,
    "hub12_tri":     _HUB12_REGIONS,
    "hub15_deep":    _HUB15_REGIONS,
    "hub18":         _HUB18_REGIONS,
    "hub18b":        _HUB18_REGIONS,
}


def get_graph(name: str) -> GraphDef:
    if name not in GRAPH_CONFIGS:
        raise KeyError(f"Unknown graph preset '{name}'. Available: {list(GRAPH_CONFIGS)}")
    return GRAPH_CONFIGS[name]


def get_node_regions(name: str) -> Dict[str, str]:
    return NODE_REGIONS.get(name, {})
