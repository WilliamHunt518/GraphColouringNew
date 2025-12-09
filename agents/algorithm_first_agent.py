"""Algorithm-first agent wrapper (1A mode).

The :class:`AlgorithmFirstAgent` demonstrates the algorithm-first
architecture proposed in the framework: the agent executes the Max–Sum
algorithm internally without modification and uses a communication
layer to translate structured messages into natural language and back.

This class merely derives from :class:`MaxSumAgent` and adds no new
behaviour.  It exists to emphasise the distinction between modes in the
public API.
"""

from __future__ import annotations

from .max_sum_agent import MaxSumAgent


class AlgorithmFirstAgent(MaxSumAgent):
    """Alias for :class:`MaxSumAgent` representing the 1A mode."""
    pass