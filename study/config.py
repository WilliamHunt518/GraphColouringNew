"""
StudyConfig and related dataclasses for the graph-colouring trust study.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class ColourPointsConfig:
    """
    Maps each participant's name to the points they earn per colour.

    Example::

        ColourPointsConfig(
            points_by_owner={
                "Human":  {"red": 3, "blue": 1},
                "AgentA": {"red": 1, "blue": 4},
                "AgentB": {"red": 2, "blue": 2},
            },
            colours=["red", "blue"],
            clash_penalty=10,
        )

    For every node coloured ``"red"``, Human earns 3 pts, AgentA earns 1 pt,
    AgentB earns 2 pts, giving a shared-score contribution of 6 per red node.

    ``clash_penalty`` is deducted per clashing adjacent pair (split equally
    between the two owners of the clashing nodes).
    """
    points_by_owner: Dict[str, Dict[str, int]]
    colours: List[str]
    clash_penalty: int = 10

    def total_per_colour(self) -> Dict[str, int]:
        """Return shared-score contribution per colour (sum across all owners)."""
        return {
            c: sum(owner_pts.get(c, 0) for owner_pts in self.points_by_owner.values())
            for c in self.colours
        }


@dataclass
class AgentConfig:
    """Configuration for one AI participant in the study."""
    name: str
    preferred_colour: str   # the colour this agent is incentivised to maximise


@dataclass
class GraphDef:
    """Defines the graph topology and sequential colouring order."""
    name: str
    nodes: List[str]
    edges: List[Tuple[str, str]]
    node_order: List[str]       # mandatory colouring sequence (all nodes)
    layout_preset: str          # key in ui/node_layouts.json
    # Optional per-graph overrides (None = use session/global defaults)
    colours: Optional[List[str]] = None
    points_config: Optional[ColourPointsConfig] = None
    agent_configs: Optional[List[AgentConfig]] = None


@dataclass
class StudyConfig:
    """Complete configuration for one experiment session."""
    participant_id: str
    mode: str               # "mode1" | "mode2a" | "mode2b"
    graph_def: GraphDef
    colours: List[str]
    points_config: ColourPointsConfig
    # node -> visual region owner name (purely for display grouping)
    node_regions: Dict[str, str] = field(default_factory=dict)
    agent_configs: List[AgentConfig] = field(default_factory=list)
    max_attempts: int = 3
    seed: int = 42
    output_dir: Path = field(default_factory=lambda: Path("results/participants"))

    # Human participant name shown in UI / logs
    human_name: str = "Human"

    # Turn-order randomisation
    random_turn_order: bool = False   # shuffle the node sequence each attempt
    include_agent_turns: bool = False  # if True, agent nodes join the shuffle too


# ---------------------------------------------------------------------------
# Default study configuration — 3 colours
# ---------------------------------------------------------------------------

DEFAULT_COLOURS = ["red", "blue", "green"]

DEFAULT_POINTS = ColourPointsConfig(
    points_by_owner={
        "Human":  {"red": 4, "blue": 1, "green": 2},
        "AgentA": {"red": 1, "blue": 4, "green": 2},
        "AgentB": {"red": 2, "blue": 2, "green": 4},
    },
    colours=DEFAULT_COLOURS,
    clash_penalty=10,
)
"""
Default scoring (3 colours):
  Per node — Red:   Human+4, AgentA+1, AgentB+2 = total 7
             Blue:  Human+1, AgentA+4, AgentB+2 = total 7
             Green: Human+2, AgentA+2, AgentB+4 = total 8
Green is shared-optimal. Human individually prefers Red; AgentA prefers Blue; AgentB prefers Green.
"""

DEFAULT_AGENTS = [
    AgentConfig(name="AgentA", preferred_colour="blue"),
    AgentConfig(name="AgentB", preferred_colour="green"),
]

# ---------------------------------------------------------------------------
# 4-player scoring (adds AgentC)
# ---------------------------------------------------------------------------

POINTS_4P = ColourPointsConfig(
    points_by_owner={
        "Human":  {"red": 4, "blue": 1, "green": 2},
        "AgentA": {"red": 1, "blue": 4, "green": 2},
        "AgentB": {"red": 2, "blue": 2, "green": 4},
        "AgentC": {"red": 2, "blue": 1, "green": 4},
    },
    colours=["red", "blue", "green"],
    clash_penalty=10,
)
"""
4-player scoring (3 colours):
  Per node — Red:   Human+4, AgentA+1, AgentB+2, AgentC+2 = total 9
             Blue:  Human+1, AgentA+4, AgentB+2, AgentC+1 = total 8
             Green: Human+2, AgentA+2, AgentB+4, AgentC+4 = total 12
Green is shared-optimal. Human individually prefers Red; AgentA prefers Blue;
AgentB and AgentC both prefer Green.
"""

AGENTS_4P = [
    AgentConfig(name="AgentA", preferred_colour="blue"),
    AgentConfig(name="AgentB", preferred_colour="green"),
    AgentConfig(name="AgentC", preferred_colour="green"),
]
