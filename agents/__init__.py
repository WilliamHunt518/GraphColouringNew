"""Agent definitions.

The agents package contains various implementations of agents that
participate in distributed constraint optimisation problems (DCOPs).
Each agent class encapsulates the logic for selecting a colour (or
value), generating messages for neighbours, interpreting incoming
messages, and interacting with a communication layer.

The different agent types correspond to the modes proposed in the
framework:

1. **Algorithm-first agents (1A)** keep the internal algorithm intact
   and rely on an LLM merely for message translation【685583168306604†L267-L294】.
2. **LLM-first agents (1B)** invert control by letting an LLM
   orchestrator call algorithmic primitives as tools【685583168306604†L305-L334】.
3. **Hybrid sandwich agents (1C)** combine a deterministic control
   policy with an LLM orchestrator【685583168306604†L336-L367】.
4. **Human-as-communication-layer agents (2A)** allow a human to
   replace the LLM for direct natural language messaging【685583168306604†L402-L431】.
5. **Human-orchestrated agents (2B)** have a human orchestrator
   interactively calling algorithmic tools【685583168306604†L435-L459】.
6. **Human-governed hybrid agents (2C)** generalise the sandwich
   design with human-defined high‑level goals【685583168306604†L468-L489】.

The base ``Agent`` class defines a common interface used by all
implementations.
"""

from .base_agent import BaseAgent
from .max_sum_agent import MaxSumAgent
from .algorithm_first_agent import AlgorithmFirstAgent
from .llm_first_agent import LLMFirstAgent
from .llm_sandwich_agent import LLMSandwichAgent
from .human_cl_agent import HumanCLAgent
from .human_orchestrator_agent import HumanOrchestratorAgent
from .human_hybrid_agent import HumanHybridAgent
from .multi_node_agent import MultiNodeAgent
from .multi_node_human_agent import MultiNodeHumanAgent, MultiNodeHumanOrchestrator
from .multi_node_llm_first_agent import MultiNodeLLMFirstAgent

__all__ = [
    "BaseAgent",
    "MaxSumAgent",
    "AlgorithmFirstAgent",
    "LLMFirstAgent",
    "LLMSandwichAgent",
    "HumanCLAgent",
    "HumanOrchestratorAgent",
    "HumanHybridAgent",
    "MultiNodeAgent",
    "MultiNodeHumanAgent",
    "MultiNodeHumanOrchestrator",
    "MultiNodeLLMFirstAgent",
]