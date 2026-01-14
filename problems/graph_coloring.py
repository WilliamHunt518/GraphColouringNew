"""Graph colouring DCOP implementation.

This module defines a simple distributed constraint optimisation
problem where each agent controls a node in an undirected graph and
must assign a colour to its node such that no two adjacent nodes share
the same colour.  In addition to the standard colouring constraint, the
problem allows each agent to specify a preference over colours, which
can serve to break symmetry when multiple valid solutions exist.

The implementation is intentionally minimal – it stores only the
structure of the graph, the domain of colours, and provides
utility/penalty functions.  Algorithms such as Max–Sum can query the
problem for constraint costs.  The problem object itself does not
maintain any agent state; it merely evaluates assignments.

Example usage:

>>> nodes = ['a1', 'a2', 'b1']
>>> edges = [('a1', 'a2'), ('a2', 'b1')]
>>> domain = ['red', 'green', 'blue']
>>> prefs  = {'a1': {'red': 0.0, 'green': 0.1, 'blue': 0.2}}
>>> problem = GraphColoring(nodes, edges, domain, preferences=prefs)
>>> problem.evaluate_assignment({'a1': 'red', 'a2': 'green', 'b1': 'red'})
1.0  # one clash on edge (a2,b1)

The helper ``create_path_graph`` can generate small problem instances
used in the paper's human–agent experiments: two 3-node paths with
optional bridging edges between the paths.  See its docstring for
details.
"""

from __future__ import annotations

from typing import Dict, List, Tuple, Iterable, Optional, Any


class GraphColoring:
    """A distributed graph colouring problem.

    Parameters
    ----------
    nodes: list of node identifiers (strings or integers)
        Each node corresponds to an agent in a DCOP.  The same domain
        of colours applies to every node, unless otherwise specified
        via ``domain``.
    edges: list of (node, node) tuples
        Undirected edges connecting nodes that must not share the same
        colour.  Each edge implicitly defines a constraint function
        between the two nodes.
    domain: iterable of hashable values
        The set of colours available to every node.  Colours are
        treated as immutable objects (typically strings).  The domain
        is assumed to be the same for all nodes for simplicity.
    preferences: dict, optional
        Optional mapping from node to a dict mapping colour to a
        preference weight (float).  Higher preference values will be
        subtracted from the total penalty when the node chooses that
        colour.  Preferences can be used to break symmetry between
        equivalent solutions.
    conflict_penalty: float
        Penalty incurred when two adjacent nodes choose the same
        colour.  The default of 1.0 yields a cost of one clash per
        violating edge.

    Notes
    -----
    This class does not perform any optimisation; it merely
    encapsulates the constraint structure.  Optimisation algorithms
    should call :meth:`evaluate_assignment` to compute the global cost
    of a proposed colouring.
    """

    def __init__(
        self,
        nodes: List[Any],
        edges: List[Tuple[Any, Any]],
        domain: Iterable[Any],
        preferences: Optional[Dict[Any, Dict[Any, float]]] = None,
        conflict_penalty: float = 1.0,
        fixed_assignments: Optional[Dict[Any, Any]] = None,
    ) -> None:
        self.nodes = list(nodes)
        # normalise edges to store each edge once with sorted endpoints
        self.edges: List[Tuple[Any, Any]] = []
        for u, v in edges:
            if u == v:
                continue
            # sort to avoid duplicate with reversed order
            if (v, u) not in self.edges:
                self.edges.append((u, v))
        self.domain = list(domain)
        # default preferences: zero for all
        if preferences is None:
            self.preferences: Dict[Any, Dict[Any, float]] = {
                node: {val: 0.0 for val in self.domain} for node in self.nodes
            }
        else:
            # copy preferences and fill missing values with zero
            self.preferences = {
                node: {val: preferences.get(node, {}).get(val, 0.0) for val in self.domain}
                for node in self.nodes
            }
        self.conflict_penalty = conflict_penalty
        # Fixed assignments (immutable node-color constraints)
        self.fixed_assignments: Dict[Any, Any] = dict(fixed_assignments) if fixed_assignments else {}

    def get_neighbors(self, node: Any) -> List[Any]:
        """Return a list of neighbour nodes for a given node."""
        neighbours = []
        for u, v in self.edges:
            if u == node:
                neighbours.append(v)
            elif v == node:
                neighbours.append(u)
        return neighbours

    def cost(self, node_i: Any, node_j: Any, value_i: Any, value_j: Any) -> float:
        """Return the penalty associated with assigning two neighbouring nodes.

        Returns ``conflict_penalty`` if the two values are equal, otherwise
        returns zero.  This function is symmetric: ``cost(i,j,x,y) == cost(j,i,y,x)``.
        """
        return self.conflict_penalty if value_i == value_j else 0.0

    def evaluate_assignment(self, assignment: Dict[Any, Any]) -> float:
        """Compute the total penalty for a given colouring assignment.

        Parameters
        ----------
        assignment : dict
            Mapping from node to selected colour.  Missing nodes are
            treated as uncoloured and assumed to have zero conflicts,
            though this situation should not occur in proper usage.

        Returns
        -------
        float
            The total penalty.  Lower is better; a valid colouring
            yields zero penalty.
        """
        penalty = 0.0
        # compute conflicts on edges
        for u, v in self.edges:
            c_u = assignment.get(u)
            c_v = assignment.get(v)
            if c_u is None or c_v is None:
                continue
            penalty += self.cost(u, v, c_u, c_v)
        # subtract preferences
        for node, colour in assignment.items():
            if node in self.preferences and colour in self.preferences[node]:
                penalty -= self.preferences[node][colour]
        return penalty

    def is_valid(self, assignment: Dict[Any, Any]) -> bool:
        """Return True if the assignment has no colour clashes."""
        for u, v in self.edges:
            c_u = assignment.get(u)
            c_v = assignment.get(v)
            if c_u is None or c_v is None:
                continue
            if c_u == c_v:
                return False
        return True

    def is_internal_node(self, node: Any, cluster_nodes: List[Any]) -> bool:
        """Check if a node is internal to a cluster (has no external neighbors).

        Parameters
        ----------
        node : Any
            The node to check.
        cluster_nodes : List[Any]
            List of nodes in the cluster.

        Returns
        -------
        bool
            True if all neighbors of the node are also in the cluster.
        """
        neighbors = self.get_neighbors(node)
        return all(nbr in cluster_nodes for nbr in neighbors)

    def respects_fixed_constraints(self, assignment: Dict[Any, Any]) -> bool:
        """Check if an assignment respects all fixed node constraints.

        Parameters
        ----------
        assignment : Dict[Any, Any]
            The proposed node-to-color assignment.

        Returns
        -------
        bool
            True if all fixed nodes have their required colors in the assignment.
        """
        for fixed_node, fixed_color in self.fixed_assignments.items():
            if fixed_node in assignment and assignment[fixed_node] != fixed_color:
                return False
        return True

    def is_valid_with_constraints(self, assignment: Dict[Any, Any]) -> bool:
        """Check if assignment is valid (no clashes) and respects fixed constraints.

        Parameters
        ----------
        assignment : Dict[Any, Any]
            The proposed node-to-color assignment.

        Returns
        -------
        bool
            True if the assignment has no color clashes and respects fixed constraints.
        """
        return self.is_valid(assignment) and self.respects_fixed_constraints(assignment)


def create_path_graph(bridge_density: int = 2) -> GraphColoring:
    """Generate a small path graph for human–agent experiments.

    The graph consists of two 3-node paths (h1–h2–h3 for the human side
    and a1–a2–a3 for the agent side) with optional bridges between
    corresponding nodes.  This setup mirrors the evaluation task
    described in the paper, where each side controls three nodes and
    must cooperate to minimise colour clashes across the bridging
    edges【685583168306604†L533-L545】.

    Parameters
    ----------
    bridge_density : int
        Number of bridging edges between the two paths.  Allowed values
        are 2 or 3.  When ``bridge_density==2``, bridges are placed on
        (h2,a2) and (h3,a3).  When ``bridge_density==3``, bridges are
        placed on (h1,a1), (h2,a2), (h3,a3)【685583168306604†L538-L542】.

    Returns
    -------
    GraphColoring
        The generated graph colouring problem with domain {"red", "green",
        "blue"} and no preferences.
    """
    if bridge_density not in (2, 3):
        raise ValueError("bridge_density must be 2 or 3")
    # define nodes for human and agent sides
    human_nodes = ["h1", "h2", "h3"]
    agent_nodes = ["a1", "a2", "a3"]
    nodes = human_nodes + agent_nodes
    edges: List[Tuple[str, str]] = []
    # path edges on each side
    edges += [("h1", "h2"), ("h2", "h3")]
    edges += [("a1", "a2"), ("a2", "a3")]
    # bridging edges
    if bridge_density == 2:
        edges += [("h2", "a2"), ("h3", "a3")]
    else:
        edges += [("h1", "a1"), ("h2", "a2"), ("h3", "a3")]
    # define domain
    domain = ["red", "green", "blue"]
    return GraphColoring(nodes, edges, domain)