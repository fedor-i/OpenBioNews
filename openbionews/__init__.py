"""OpenBioNews — a free, self-hosted news digest builder.

Gathers news from RSS/Atom feeds, deduplicates stories across outlets, and
composes a clean daily digest. Works with no LLM at all, a local model via
Ollama, or any OpenAI-compatible API. Pure standard library — no third-party
packages required for the core pipeline.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
