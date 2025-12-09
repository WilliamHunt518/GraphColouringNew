"""DCOP problem definitions.

This package contains classes representing different distributed
constraint optimisation problems (DCOPs).  Each problem defines a
graph of variables, domains of possible values for each variable, and
constraints or utility functions that couple neighbouring variables.

The framework currently includes a basic implementation of the
``GraphColoring`` problem, but additional problems can easily be
integrated by following the same interface.  Problems expose methods
for computing the cost of an assignment and for checking whether a
colouring violates local constraints.
"""

from .graph_coloring import GraphColoring, create_path_graph

__all__ = ["GraphColoring", "create_path_graph"]