"""Communication layers for agentic DCOPs.

The communication layer abstracts the process of translating between
internal algorithmic data structures and externally exchanged
messages.  In algorithmic modes, the :class:`LLMCommLayer` uses a
language model (or a simple heuristic in this implementation) to
package structured messages into human-readable strings and to parse
incoming strings back into structured data.  Human-operated modes
replace the LLM with a human interface, but still adhere to the same
interface exposed here.
"""

from .communication_layer import BaseCommLayer, LLMCommLayer, PassThroughCommLayer

__all__ = ["BaseCommLayer", "LLMCommLayer", "PassThroughCommLayer"]