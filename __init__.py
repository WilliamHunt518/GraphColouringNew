"""Top level package for the DCOP agentic framework.

This package exposes the main classes and utilities for building and
running distributed constraint optimisation problems (DCOPs) under
different communication and control configurations.  The goal of
the framework is to allow heterogeneous agents – humans, algorithms and
language models – to cooperate on a shared problem while exchanging
messages in natural language.  The interfaces are deliberately kept
modular so that new problem types or agent modes can be plugged in
without changing the rest of the system.

See the ``problems`` and ``agents`` sub-packages for concrete
implementations.
"""

from .problems import graph_coloring
from .agents import (algorithm_first_agent,
                     llm_first_agent,
                     llm_sandwich_agent,
                     human_cl_agent,
                     human_orchestrator_agent,
                     human_hybrid_agent)

__all__ = [
    "graph_coloring",
    "algorithm_first_agent",
    "llm_first_agent",
    "llm_sandwich_agent",
    "human_cl_agent",
    "human_orchestrator_agent",
    "human_hybrid_agent",
]